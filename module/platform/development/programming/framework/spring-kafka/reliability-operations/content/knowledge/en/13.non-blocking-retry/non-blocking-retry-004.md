# Delay-Based Retry Topics

In Spring Kafka, **non-blocking retry** uses intermediate Kafka topics to hold records needing retry and route them to retry consumers after a delay. Instead of blocking the original topic's listener for the entire wait period, the application forwards the failed record to a retry topic; the original listener can continue receiving new records. This mechanism fits when a dependency needs several seconds or minutes to recover while the consumer must still maintain throughput and process non-failing records.

**Delay-based retry topics** organize subsequent attempts based on desired wait durations. Spring Kafka supports defining multiple retry stages via `@RetryableTopic` or `RetryTopicConfiguration`, automatically setting up the corresponding retry topics and listeners, and routing failed records to a Dead Letter Topic (DLT) when the policy ends.

A point to understand right away: **the Kafka broker does not automatically delay record delivery just because a topic name contains milliseconds**. Spring Kafka's retry mechanism stores metadata for the retry attempt and the timestamp when the record becomes eligible for processing; the retry listener coordinates polling and pausing partitions when records are not yet due. Actual execution time may deviate from configured milestones due to polling, scheduling, rebalances, and system load.

## 1. Why Separate Retries into Dedicated Topics?

With blocking retry, a listener processing a failed record retries after a backoff period. Subsequent records in the same partition typically must wait, causing consumer lag to grow during prolonged dependency outages.

With non-blocking retry:

1. The original topic's listener receives the record.
2. The error is classified as retryable.
3. Spring Kafka publishes the record to the retry topic corresponding to the attempt and delay.
4. The source record's offset is handled according to the container's recover/forward policy.
5. The original topic's listener continues processing other records.
6. The retry listener passes the record to business logic only when the delay milestone permits.
7. If it still fails and retry budget remains, the record is published to the next retry topic; if attempts are exhausted, the record goes to a DLT or a configured terminal destination.

~~~mermaid
flowchart TD
    A["Source topic: orders"] --> B["Listener processes"]
    B -->|Success| C["Complete and commit progress"]
    B -->|Retryable error| D["Publish to retry topic"]
    D --> E["Wait until eligible time"]
    E --> F["Retry listener processes"]
    F -->|Success| G["Retry complete"]
    F -->|Retries remaining| D
    F -->|Exhausted or fatal error| H["DLT / quarantine"]
~~~

Topic forwarding frees the initial processing flow but introduces extra publishing, consuming, offset management, and topic management steps. The impact of forwarding records must be accounted for in delivery guarantee design.

## 2. How Are Delays Represented by Topics and Metadata?

Suppose an application needs one initial attempt and three retries, with wait intervals of 1 second, 2 seconds, and 4 seconds respectively. An illustrative topology:

~~~text
orders
  |
  +-- first failure --> orders-retry-1000  (retry after ~1 second)
                          |
                          +-- error --> orders-retry-2000  (~2 seconds)
                                          |
                                          +-- error --> orders-retry-4000  (~4 seconds)
                                                          |
                                                          +-- error --> orders-dlt
~~~

The names above are **examples only**. Spring Kafka may use suffixes based on delay or index, reuse topics sharing the same delay, and vary naming rules by configuration or version. Do not use topic names as the sole source of truth for retry policy.

When forwarding a record, the framework attaches metadata such as expected backoff timestamp, original topic/partition/offset, and attempt info in appropriate headers. The retry listener uses this metadata to decide when the record can be processed. If received before its due time, the infrastructure pauses the partition and keeps checking until the appropriate time arrives.

Example timeline (ignoring business call and publish duration):

| Milestone | Processing location | Behavior |
|---|---|---|
| `t = 0` | `orders` | Initial attempt fails |
| `t ≈ 1s` | Retry attempt 1 | Reprocess after 1-second delay |
| `t ≈ 3s` | Retry attempt 2 | If attempt 1 fails, wait an additional 2 seconds |
| `t ≈ 7s` | Retry attempt 3 | If attempt 2 fails, wait an additional 4 seconds |
| After final retry fails | `orders-dlt` | Store record for investigation or replay |

The table uses cumulative timestamps. Delays of 1s, 2s, and 4s do not mean the three retries happen at t=1s, t=2s, and t=4s from the initial receipt.

## 3. Quick Configuration with @RetryableTopic

Spring Kafka supports declaring a retry topology on a listener via `@RetryableTopic`. Example of non-blocking retry using exponential backoff:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 4_000
    ),
    autoCreateTopics = "false",
    include = {TemporaryInventoryException.class},
    exclude = {InvalidOrderEventException.class}
)
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-projection")
public void onOrder(OrderEvent event) {
    orderProjectionService.apply(event);
}
~~~

Here:

- `attempts = "4"` is the **total number of processing attempts**, including receipt from the original topic: the initial attempt plus up to three retries.
- `@Backoff(delay = 1_000, multiplier = 2.0, maxDelay = 4_000)` produces expected delays of 1s, 2s, and 4s.
- `include` and `exclude` illustrate error classification. Non-retryable errors route to recovery per policy instead of traversing every retry topic.
- `autoCreateTopics = "false"` fits when topics are provisioned via IaC/cluster admin. You must create all original, retry, and DLT topics with matching partitions before running.

Depending on the Spring Kafka version and application setup, retry topic support must be enabled via `@EnableKafkaRetryTopic`, corresponding support configuration, or Spring Boot's built-in configuration mechanism. Use a single configuration approach consistent with your deployed version, avoiding duplicate registration of the same topology.

Example enabling retry topics in an application configuration:

~~~java
@Configuration
@EnableKafka
@EnableKafkaRetryTopic
public class KafkaRetryTopicConfiguration {
}
~~~

The class name is an application class name, not a mandatory Spring Kafka class. Before applying, check your `spring-kafka` version because the API and rules for enabling retry topics have evolved across versions.

## 4. Fixed Delay and Exponential Delay

Not every topology needs increasing intervals. You can use a fixed delay to wait the same duration between attempts:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 5_000),
    autoCreateTopics = "false"
)
@KafkaListener(topics = "notification-events", groupId = "notification-service")
public void onNotification(NotificationEvent event) {
    notificationService.send(event);
}
~~~

With this configuration, all three retries have an expected 5-second delay. Actual naming and number of retry topics depend on the strategy for reusing topics with the same interval. Do not assume there must be three physical Kafka retry topics when all delays are equal.

Comparison:

| Criterion | Fixed delay | Exponential delay |
|---|---|---|
| Wait interval | Constant across attempts | Increases by multiplier |
| Example | 5s, 5s, 5s | 1s, 2s, 4s |
| Predictability | Very easy | Must calculate sequence and max delay |
| Best suited for | Short outages or steady retry cadence | Dependencies needing growing recovery time |
| Risk | Many consumers retrying in lockstep | Can still synchronize without jitter |

When retries need to be spread out to prevent a retry storm, consider random/exponential-random backoff if supported by your version and configuration. Do not assume fixed delay automatically adds jitter.

## 5. Total Attempts and Retry Budget

A common point of confusion is the meaning of `attempts` in `@RetryableTopic` versus `maxAttempts` of `FixedBackOff` in blocking retry.

| Mechanism | Configured value | How it counts |
|---|---|---|
| `@RetryableTopic(attempts = "4")` | 4 | Total processing attempts: 1 initial + up to 3 retries |
| `new FixedBackOff(1000L, 3L)` | 3 | Three retries **after** the initial attempt, up to 4 total runs |

With non-blocking retry, total time before routing to the DLT can be estimated as:

~~~text
total processing time
≈ sum of delays used
+ business call duration across attempts
+ publish/consume/rebalance overhead
+ recovery duration
~~~

For instance, three delays of 1s, 2s, and 4s sum to 7 seconds of wait time, but that is not the final processing time limit. If each dependency call takes 3 seconds, total time rises by about 12 seconds across four executions, excluding overhead.

The retry budget must align with SLOs. An order flow requiring completion within 30 seconds can accept short delays; a notification flow may tolerate minutes of waiting or transition to another processing workflow.

## 6. Kafka Has No Native Delayed Delivery Mechanism

Kafka stores records in offset order within a partition. The broker does not proactively hold a record and deliver it only when a business timestamp arrives. Spring Kafka's non-blocking retry uses **consumer-side scheduling**:

1. The failed record is published to a retry topic.
2. The infrastructure writes metadata specifying when the next attempt can run.
3. The retry consumer polls records from Kafka.
4. If not yet due, the corresponding partition is paused.
5. The consumer/container keeps polling, maintains group membership, and resumes when the delay condition is met.
6. The business listener reprocesses the record once due.

This explains why the delay is a **desired earliest threshold**, not a millisecond-exact processing SLA. When brokers are overloaded, consumers rebalance, or a partition is blocked by a record not yet due, records can be processed later.

Also distinguish container `pause()` from `stop()`. Pause keeps the consumer running to maintain consumer group membership, whereas stop ends the consumer lifecycle and typically triggers partition reassignment.

## 7. Delay Topics vs. Blocking Retry

| Criterion | Blocking retry in `DefaultErrorHandler` | Non-blocking retry topic |
|---|---|---|
| Where record waits for retry | Processing flow of original listener/container | Separate retry topic |
| Additional topics | Usually not required | Has retry topic(s) and usually DLT |
| Long backoff | Can hold partition/consumer during retry cycle | Forwards record to retry stream, letting original topic advance |
| Ordering for same key | Easy to preserve processing order in original partition | Business ordering can be inverted |
| Simplicity | Fewer components | More consumers, topics, producers, and offsets |
| Limitation | Poison record can stall partition | Requires managing topology and idempotency |

You can combine brief blocking retries for transient blips with longer non-blocking retries where supported by your version and configuration. When combining them, count attempts at each layer so a record does not hit a dependency more times than intended.

## 8. Processing Order Is No Longer Guaranteed Across Retry Topics

Kafka only guarantees record order within a single partition of a single topic. When record A fails and moves to a retry topic, record B arriving later with the same key on the original topic can succeed before A.

~~~mermaid
sequenceDiagram
    participant O as Source topic (partition p)
    participant L as Source listener
    participant R as Retry topic
    participant D as Database
    O-->>L: Event A, offset 100
    L-->>R: A fails, publish retry
    O-->>L: Event B, offset 101
    L->>D: Apply B successfully
    Note over R: Wait for delay
    R-->>L: Event A retried
    L->>D: Apply A after B
~~~

If A is `OrderCreated` and B is `OrderCancelled`, applying B before A can violate the state machine if the consumer relies strictly on ordering.

Handling options depend on business logic:

- Design idempotent operations and rely on state version, event sequence, or optimistic locking to reject stale events.
- For flows requiring strict sequential execution, consider blocking retry or a dedicated per-aggregate/per-key workflow.
- Use intermediate states and dependency checks: an early-arriving event can be stored awaiting business preconditions instead of being applied immediately.
- Avoid assuming that using the same partition number on the retry topic preserves relative order between the original topic and retry topic.

Non-blocking retry trades observable ordering for freeing the original processing stream. That decision must be grounded in business invariants.

## 9. Choosing Partition Count and Concurrency for Retry Topics

Retry topics are also read by Kafka consumer groups. You must provision partition counts, replicas, and retention aligned with the original topic and recovery capacity.

Directional guide:

| Attribute | Why it matters |
|---|---|
| Partition count | Enough to hold forwarded partitions and utilize retry concurrency |
| Replication factor | Protects retry data if a broker fails |
| Retention | Long enough for delays and handling backlogs/outages |
| Consumer concurrency | Enough throughput for retries without overloading a recovering dependency |
| Producer serialization | Forwarding producer must serialize received key/value, including deserialization-failed payloads |
| ACL/topic policy | Allows create/read/write/describe matching the provisioned topology |

When forwarded records preserve source partitions, target topics must have matching partitions. If partition counts mismatch, publishing can fail or require intentional custom routing.

Do not automatically set retry concurrency equal to the original topic's concurrency in every case. A struggling dependency may need slower retries to avoid worsening the incident. Conversely, a large backlog after an outage may need dedicated recovery capacity. Base this on failure rate, outage duration, and dependency throughput.

## 10. Limitations by Listener Type and Transactions

Spring Kafka's non-blocking retry topics are designed primarily for **record listeners**. Commonly used versions do not support applying `@RetryableTopic` in the same way to batch listeners; when processing batches, check your version's API limits and consider splitting into a record listener or dedicated retry handling.

For Kafka transactions, pay special attention to the relationship between forward-to-retry and source offset commit. Standard non-blocking retry setups are not directly compatible with transactional listener containers. Do not take a non-transactional retry topic example and attach it to a flow requiring atomic consume-transform-produce without analyzing transaction boundaries.

A Kafka transaction can atomically commit Kafka outputs and offsets within a configured transactional flow. Non-blocking retry introduces an extra forward step and separate consumers; retry publishing and offset advancement must be managed according to the actual topology's semantics.

If business logic requires Kafka-to-Kafka exactly-once semantics, design specifically for transactions and verify end-to-end. When interacting with databases or HTTP APIs, add idempotency and replay-tolerant workflows.

## 11. Handling Deserialization Errors Before the Listener

A malformed JSON record can cause the deserializer to fail during consumer `poll()`, before the listener receives an object. With Spring Kafka, you can configure `ErrorHandlingDeserializer` to turn deserialization failures into error info that the error handler can process and route to the DLT.

Example consumer configuration:

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderEvent
        spring.json.trusted.packages: com.example.events
~~~

Malformed JSON errors are usually **non-retryable** because waiting a few seconds will not make the payload valid. For undeserializable records, you need a properly designed recovery/DLT mechanism paired with a serializer for raw byte arrays.

If sharing a producer to publish retries and DLT records, confirm the producer can serialize every payload form that may appear. When a deserialization failure is forwarded, the payload may be a byte array rather than a normal Java object. A serializer accepting only `OrderEvent` can cause DLT publishing to fail.

## 12. Error Classification: Retryable vs. Fatal

Not every exception should traverse all delay topics:

| Error | Suggested policy |
|---|---|
| HTTP 503, rate limit, secondary timeout | Retry with delay/backoff, bounded attempts |
| Temporary database connection failure | Retry with delay, control load |
| Payload missing unrecoverable required field | Non-retryable, DLT/quarantine |
| Unsupported schema version | DLT/quarantine and upgrade alert |
| Terminal business rule violation | Do not retry; store rejection or intentionally send to DLT |
| Widespread programming bug | Alert, avoid flooding DLT, fix release |

Express error categories using specific exceptions, such as `TemporaryInventoryException` and `InvalidOrderEventException`, rather than throwing generic `RuntimeException` everywhere.

You can classify errors via `include`/`exclude` on `@RetryableTopic`. Default fatal exception lists and cause-chain inspection rules differ across Spring Kafka versions; verify against actual API/classification behavior during implementation.

If multiple event types share a topic yet need different delays/attempts, consider splitting topics/listeners or configuring per-endpoint retry settings. A single annotation on one listener does not automatically understand per-event-type SLAs.

## 13. Dead Letter Topic and DLT Handler

When the retry budget is exhausted or an exception is classified as non-retryable, the record is typically published to the configured DLT. The DLT serves as a quarantine zone for analysis, data correction, and replay. It does not prove the initial business step succeeded.

Example listener with a DLT handler:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0),
    autoCreateTopics = "false"
)
@KafkaListener(topics = "orders", groupId = "order-projection")
public void handle(OrderEvent event) {
    orderProjectionService.apply(event);
}

@DltHandler
public void handleDlt(
        ConsumerRecord<String, OrderEvent> record) {
    log.error(
        "Order sent to DLT: topic={} partition={} offset={} key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );
    // Persist operational state or emit alert per policy.
}
~~~

`@DltHandler` must be placed within the proper retry-topic configuration context, and the handler signature must match how the framework registers endpoints. If not handling the DLT via a handler, design a dedicated consumer/ops workflow to monitor DLT records.

The DLT should retain traceability info: original topic/partition/offset, event ID, exception class, attempt count, failure timestamp, and schema version. Replay must be controlled to avoid loops when the root cause has not been fixed. Do not write full payloads containing sensitive data verbatim into operational logs.

## 14. Do Not Assume Exactly-Once When Forwarding to Retry Topics

In a typical retry topology, the original listener goes through these moments:

~~~text
1. Business record processing fails.
2. Publish record to retry topic.
3. Container processes/commits source offset.
4. Retry consumer reads forwarded record.
~~~

If the process stops between publishing and committing the offset, the record may be redelivered from the original topic while a copy already exists on the retry topic. If publishing the retry fails, error handling must detect it so the record is not skipped without durable storage.

Therefore, retry topics do not mean every business event is guaranteed to be processed exactly once. Design an **idempotent consumer** keyed by a durable event ID:

~~~java
@Transactional
public void apply(OrderEvent event) {
    if (!processedEventRepository.insertIfAbsent(event.eventId())) {
        return; // Event already applied
    }

    orderRepository.apply(event);
}
~~~

`insertIfAbsent` here is a conceptual operation that must rely on a unique constraint and a database transaction to prevent race conditions. The processed marker and business changes must commit together. For external HTTP APIs, use the provider's idempotency key or a workflow with durable state.

Do not generate a new event ID when forwarding a record through retry topics. The ID must stay unchanged so consumers detect redeliveries of the same business event.

## 15. Relationship Between Delay and Backlog

Delay topics can accumulate backlogs during long outages. Suppose a producer generates 2,000 records/minute, a dependency fails for 10 minutes, and half the records must retry: roughly 10,000 records will need reprocessing (not counting copies across multiple retry stages). When the dependency recovers, retry consumers can create a large traffic spike.

Issues to plan for:

- **Retention:** must be longer than wait time + expected backlog duration. Kafka log retention does not adjust automatically for retry delays.
- **Capacity:** retry consumers may need higher concurrency after an outage, without exceeding dependency capacity.
- **Backpressure:** rate limiting may be needed to avoid a retry storm.
- **SLO:** measure final completion latency, not just original listener latency.
- **Ordering:** after an outage, older events may return after newer events on the original topic.
- **Storage:** each retry forward creates a new record on its topic; many stages multiply writes/reads and disk usage.

Sanity-check example:

~~~text
original-topic rate:     2,000 events/minute
failure proportion:         50%
outage duration:            10 minutes
records entering retry: 10,000
~~~

The figure 10,000 is only the number of records entering retry during the outage under these assumptions, not the final number remaining in retry topics. Actual remaining volume depends on attempts, routing, retention, processing speed, and records moved to DLT.

## 16. Observability for Delay-Based Retry Topics

Track a single event's journey across multiple topics instead of looking only at original topic consumer lag.

| Metric/event | Operational meaning |
|---|---|
| Original topic lag | How many original records are waiting for processing |
| Per-retry-topic lag | Backlog at each retry stage |
| Forward-to-retry rate | Failure rate causing flow diversion |
| Attempt count by exception | Transient error vs. poison record |
| Time from first attempt to success | Actual end-to-end latency |
| Delay relative to retry schedule | Whether retry listener is stalled past due time |
| Records entering DLT | Extent of unsuccessful recovery |
| Retry/DLT publish failures | Risk of records failing to reach destination |
| Consumer rebalances/pauses | Whether delay scheduling is disrupted |

Logs should include current topic, source topic, partition, offset, event ID, attempt, exception class, and target retry topic. Use event ID to correlate logs/traces, but avoid using event ID as a metric label due to potentially huge cardinality.

Set alerts when DLT grows abnormally, retry backlog rises rapidly, oldest record age breaches SLO, or publishing to retry topics repeatedly fails. Looking only at original topic lag can create the impression the app is keeping up while thousands of events wait in retry topics.

## 17. Provisioning Topics via Infrastructure and ACLs

If using `autoCreateTopics = "false"`, topics must be created before the listener runs. Example illustrative topology with topics:

~~~text
orders
orders-retry-1000
orders-retry-2000
orders-retry-4000
orders-dlt
~~~

This list is an **example**; obtain actual topic names from your retry topic configuration, suffix strategy, and deployed version. Provision exact names, partition counts, replication factors, retention, and ACLs.

Consumer groups need read permissions on the corresponding retry/DLT topics; the retry producer needs write permissions. If topics do not exist or ACLs are missing, the framework may fail to publish or subscribe, stalling the retry pipeline.

When changing attempt counts or backoff, the physical topology may change. Treat this as an infrastructure change: update IaC, ACLs, monitoring dashboards, and rollback plans before rolling out new code.

## 18. Runbook: Retry Topic Has Records Not Being Processed

When records stay in a retry topic longer than expected:

1. Confirm the active topic names and delay/attempts configuration.
2. Check whether the retry consumer group has active members, partition assignments, or authorization errors.
3. Check when records are marked eligible for retry; distinguish **not yet due** from **overdue but consumer not processing**.
4. Inspect consumer pause/resume state, poll timeouts, rebalances, and listener thread availability.
5. Check whether the dependency is still failing; if so, records may already be forwarding to the next stage.
6. Check for publish errors to the next retry topic or DLT; do not inspect only business listener exceptions.
7. Verify topic retention is long enough to hold records across outage duration and backlogs.
8. After fixing, trace event IDs through stages, confirming end-to-end latency and idempotency.

If a retry topic has high lag because records are not yet due, adding consumer threads will not process records before their delay. If records are due yet unprocessed, check consumer membership, task executors, deserialization, ACLs, and dependencies.

## 19. Common Design Mistakes

### Confusing Delay with Exact Execution Time

Delay is a desired minimum wait. Actual timing is affected by polling, pausing, scheduling, and load. Never use retry topics as a millisecond-accurate scheduling system.

### Assuming Retry Topics Preserve Per-Key Ordering

A record moved to another topic may be processed after newer records from the original topic. For stateful workflows, use version/sequence numbers or a dedicated ordering mechanism.

### Miscounting Attempts

`@RetryableTopic(attempts = "4")` means four total processing attempts, not four retries after the first attempt. Also account for retry budgets inside HTTP clients/services called by the listener.

### Letting Kafka Auto-Create Topics Without Control

In production, use provisioning workflows and review retention/replication/partitions. Missing topics or mismatched partition counts can cause forwarding to fail.

### Sending Every Exception Through Delay Topics

Invalid payloads or unsupported schema versions usually do not self-heal. Classify them as non-retryable and route to DLT/quarantine in a controlled way.

### Monitoring Only the Original Topic

Original topic lag can be low while retry backlogs and DLT are high. Dashboards must cover the entire topology.

### Generating a New Event ID on Replay

This breaks deduplication and can duplicate side effects. Preserve the original ID, origin, and replay metadata.

## 20. Choosing a Retry Strategy by Business Requirement

| Requirement | Design direction |
|---|---|
| Short errors under a few seconds, partition ordering matters | Blocking retry with small backoff |
| Dependency needs seconds/minutes, original topic must keep running | Delay-based non-blocking retry topics |
| Errors unrecoverable by retrying | Immediate DLT/quarantine |
| Payment flow requiring strict ordering and explicit exactly-once | Custom transaction/workflow design; enforce ordering and idempotency |
| Major outage causing retry storms | Exponential/random backoff, rate limiting, circuit breaker |
| Multiple event types with different SLAs | Split listeners/topics or appropriate retry configurations |

Delay-based retry topics are an effective tool when wait times are long and failed records must not stall the main processing stream. To operate safely, clearly define attempts and delay sequences, classify exceptions, provision topics accurately, monitor backlogs across the entire retry topology, and accept that processing order may change. In every case, idempotency design and DLT recovery are inseparable parts of reliability.
