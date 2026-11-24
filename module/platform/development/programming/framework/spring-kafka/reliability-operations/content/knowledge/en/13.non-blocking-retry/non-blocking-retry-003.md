# How Retry Topics Work

In Spring Kafka, **non-blocking retry** is a mechanism that forwards a failed record to dedicated Kafka topics for retrying. Instead of holding the original topic's consumer for the entire backoff duration, the framework sends the failed record to a retry topic so the original topic's consumer can continue processing other records. A consumer on the retry topic redelivers the record to the listener when the configured retry time arrives. If it still fails after the allowed attempts, the record is forwarded to a dead-letter topic (DLT) or goes through the appropriate terminal mechanism.

In Spring Kafka Reliability Operations, understanding this mechanism is especially important because it changes execution flow, latency, record ordering, error tracking, and consumer group load resilience. Retry topics solve the problem of **not blocking the main flow due to a single record needing a long wait**, but they do not automatically provide exactly-once processing, fix bad data, or preserve processing order across records.

## 1. Why Are Retry Topics Needed?

Suppose a listener processes OrderCreated events and needs to call a payment service. The service returns HTTP 503, and expected recovery time is several minutes. If blocking retry with a long backoff is used, the consumer thread may have to wait on that record; other partitions owned by the same consumer can also be delayed.

With retry topics, Spring Kafka forwards the failed event to a separate topic and lets the main consumer keep reading:

~~~text
Original topic: orders

offset 100: OrderCreated A -> transient failure
                            |
                            v
                       orders-retry

offset 101: OrderCreated B -> processed on original topic
offset 102: OrderCreated C -> processed on original topic

Retry consumer:
  Wait until due -> reprocess A
~~~

Thus, event A still gets a chance to be processed once the dependency recovers, while B and C do not have to wait for A's entire retry period. This is the main benefit, though it also changes ordering: B and C may complete before A.

Retry topics suit errors that can recover after a relatively long wait, such as a temporarily unavailable API, downstream rate limiting, or a service needing time to stabilize. If the error is an invalid schema or unconvertible data, routing through multiple retry topics usually only delays incident detection.

## 2. The Main Topic → Retry Topic → DLT Flow

Spring Kafka can build a **retry topology** consisting of a listener for the original topic, retry topics with different wait intervals, and a DLT.

Example of a record allowed at most four processing attempts, including the first:

~~~text
                     Attempt 1
                  +----------------+
                  | orders (main)  |
                  +----------------+
                          |
                     Listener error
                          |
                          v
                    +-------------+
                    | Retry #1    | wait ~1 second
                    +-------------+
                          |
                     Listener error
                          |
                          v
                    +-------------+
                    | Retry #2    | wait ~2 seconds
                    +-------------+
                          |
                     Listener error
                          |
                          v
                    +-------------+
                    | Retry #3    | wait ~4 seconds
                    +-------------+
                          |
                     Still failing
                          |
                          v
                    +-------------+
                    | orders-dlt  |
                    +-------------+
~~~

The names Retry #1, Retry #2, and Retry #3 in the diagram are role names. Spring Kafka can generate topic names with a retry suffix and delay info; exact names depend on version, suffixes, topic reuse strategy, and application configuration.

Each stage has a consumer processing records on its corresponding topic:

1. The original topic's consumer receives the record and invokes the business listener.
2. The listener throws an exception.
3. Spring Kafka's retry infrastructure checks the exception, attempt count, and backoff.
4. If retries remain, the recoverer publishes a corresponding record to the selected retry topic with required metadata.
5. The retry topic's consumer receives the record, but only invokes the listener once the backoff time is due.
6. If the listener on the retry topic succeeds, the record's retry journey ends.
7. If it still fails and retries remain, the record is published to the next retry topic.
8. If attempts are exhausted or the exception is not retryable, the record is routed to the DLT per policy.

Spring Kafka organizes these components via RetryTopicConfiguration or the @RetryableTopic annotation along with listener containers created for retry and DLT. You do not need to manually write a sleep loop and resend records inside the business listener.

## 3. Retry Topics Store Records Like Normal Kafka Topics

A retry topic is a real Kafka topic on the cluster. It has partitions, offsets, retention, replication, ACLs, and consumer groups just like any other topic. When a record is forwarded from the orders topic to a retry topic, Kafka stores a **new record with a new offset** in the target topic.

Example:

~~~text
orders, partition 2, offset 410
    |
    | publish to retry topic
    v
orders-retry-1000, partition 2, offset 87
    |
    | retry fails; publish onward
    v
orders-retry-2000, partition 2, offset 24
    |
    | retry succeeds
    v
Done
~~~

Offsets 410, 87, and 24 belong to three different logs. Never use a retry topic's offset in place of the original offset to locate an event in the original topic. To trace an event across the retry topology, carry a stable event ID or correlation ID.

When forwarding a record, the system can attach headers indicating origin, attempt count, exception, and backoff timestamp. Payload and key are forwarded according to producer, serializer, and recoverer configuration. Treat publishing to a retry topic as a new Kafka write action that can succeed or fail just like any normal produce.

A retry topic is not a timer capable of executing work on its own. The Kafka broker only stores records; the **Spring Kafka retry consumer** is responsible for waiting until due and re-invoking the listener.

## 4. How Does Spring Kafka Implement the Wait Time?

With non-blocking retry, when forwarding a record, the framework computes the earliest time the record is allowed to be reprocessed from the current time and the retry delay. Backoff info is stored as metadata/headers for the retry consumer.

The timeline can be visualized as:

~~~text
12:00:00.000  Original listener fails
12:00:00.050  Record published to retry topic
12:00:01.000  Expected retry time
12:00:01.xxx  Retry listener starts processing if consumer is ready
~~~

When the consumer reads a retry record before its due time, Spring Kafka can pause the corresponding partition and keep polling under the container mechanism. When the backoff time arrives, the partition is resumed so the record is redelivered to the listener. This avoids putting the consumer thread to sleep for a long delay just to wait on a record.

Several operational consequences to understand:

- **Retry time is an earliest-eligible time, not a millisecond-exact guarantee.** Records can be processed late due to poll timeouts, rebalances, lack of consumers, backlogs, or slow brokers.
- **Do not use retry topics as a real-time scheduling system.** They are meant for delayed retries, not millisecond-accurate timers.
- **Pausing applies to the retry consumer's partition.** It does not mean all consumers on the original topic must wait.
- **A record not yet due can make subsequent records in the same retry partition wait.** A retry topic still follows offset ordering within a partition.

Therefore, non-blocking retry frees up processing on the main topic, while a retry topic can experience head-of-line waiting when multiple records share a partition with different due times.

## 5. How Attempt Counts and Backoff Are Calculated

The attempts attribute of @RetryableTopic includes **the first processing attempt on the original topic**. For example, attempts = 4 means at most one initial attempt and three retry attempts, provided all errors qualify for retry.

Suppose this configuration:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 4_000))
~~~

A retry schedule can be represented as:

| Attempt | Where processed | Delay before this attempt | Outcome if it fails again |
|---|---|---:|---|
| 1 | Original topic | None | Forward to first retry |
| 2 | First retry topic | ~1 second | Forward to next retry |
| 3 | Second retry topic | ~2 seconds | Forward to next retry |
| 4 | Third retry topic | ~4 seconds | Forward to DLT |

This example illustrates exponential backoff with multiplier 2. Actual delay also depends on when the record was forwarded, retry scheduling, and when the consumer is ready; it is not an exact measure of total processing time.

**Fixed delay** uses a constant wait interval across all retries. **Exponential backoff** increases the wait interval to reduce load on a failing dependency. **Randomized backoff/jitter** can help avoid many consumers retrying simultaneously after a shared outage when supported by the version and configuration.

If the listener succeeds on one of the retry topics, the framework stops forwarding the record to further stages. If the error is classified as non-retryable, the record can go straight to the DLT without consuming all attempts.

## 6. Configuring @RetryableTopic and @KafkaListener

In modern Spring Kafka applications, a convenient approach is placing @RetryableTopic on the @KafkaListener method.

~~~java
@Service
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 1_000,
                    multiplier = 2.0,
                    maxDelay = 4_000),
            autoCreateTopics = "false",
            retryTopicSuffix = "-retry",
            dltTopicSuffix = "-dlt")
    @KafkaListener(
            topics = "orders",
            groupId = "orders-service")
    public void onOrder(OrderCreatedEvent event) {
        orderService.process(event);
    }

    @DltHandler
    public void onDlt(OrderCreatedEvent event) {
        orderService.reportFailedEvent(event);
    }
}
~~~

Example breakdown:

- attempts = 4: one initial attempt and up to three retries.
- backoff increases from 1 to 4 seconds with multiplier 2.
- autoCreateTopics = false: topics must be prepared beforehand.
- retryTopicSuffix and dltTopicSuffix describe the suffixes for naming target topics.
- @DltHandler designates the method handling records delivered to the DLT.

Types OrderCreatedEvent and OrderService belong to the illustrative application; appropriate serializers/deserializers, consumer factory, producer factory, and dependencies are required. @DltHandler itself can also fail; the application must have an operational policy for the DLT instead of treating this handler as guaranteed to succeed.

Depending on the version and application setup, retry topic infrastructure can be enabled via @EnableKafkaRetryTopic:

~~~java
@Configuration
@EnableKafkaRetryTopic
public class KafkaRetryConfiguration {
}
~~~

Do not declare duplicate retry topic bootstrap mechanisms if the framework auto-configures them. Check your Spring Kafka version and how the application creates listener endpoints to choose one consistent approach.

If you prefer not to use annotations, Spring Kafka provides RetryTopicConfigurationBuilder or equivalent configuration to set up the retry topology in Java config. This helps when multiple listeners share a policy or when centralizing topic naming and retry strategies.

## 7. How Does Spring Kafka Create Listeners and Topics?

When an application initializes a listener with retry topics, Spring Kafka creates additional endpoints/containers to consume the retry topics and DLT. Each endpoint has a corresponding subscription; specific consumer and group IDs are assigned according to framework mechanics and configuration.

Example logical topology:

~~~text
Listener orders
   subscription: orders

Listener orders-retry-1000
   subscription: orders-retry-1000

Listener orders-retry-2000
   subscription: orders-retry-2000

Listener orders-retry-4000
   subscription: orders-retry-4000

Listener orders-dlt
   subscription: orders-dlt
~~~

The topic names above are examples. Depending on strategy and version, Spring Kafka may use different names or reuse a retry topic across multiple attempts. Do not hardcode an assumption that one retry topic always maps to exactly one delay when operating or building dashboards.

Retry topics and DLT must exist with appropriate partition counts, replication, retention, and access permissions. With autoCreateTopics, Spring Kafka can register topic beans to create them at startup if cluster and permissions allow. In production, many operations teams prefer creating topics proactively to control replication factor, min.insync.replicas, ACLs, and retention.

Retry topic listeners also consume resources: consumer members, connections, threads, fetches, partition assignments, and monitoring. The more retry topics, the more complex the topology; account for resources beyond the original topic.

## 8. Which Retry Topic Is a Record Routed To?

Routing decisions typically depend on the configured policy:

1. Which stage of the retry topology is the record currently in?
2. How many processing attempts have occurred?
3. Does the current exception belong to a retryable group?
4. What is the backoff for the next step?
5. Has the attempt limit or overall timeout been reached?
6. If not retrying, should the record go to the DLT or another terminal action?

Example:

~~~text
orders
  |
  +-- IllegalArgumentException
  |       |
  |       v
  |   Do not retry per classifier -> orders-dlt
  |
  +-- TemporaryPaymentException
          |
          v
       retry topic 1
          |
          +-- success -> done
          |
          +-- still failing -> retry topic 2
                              |
                              +-- attempts exhausted -> orders-dlt
~~~

In practice, configure the exception classifier according to business semantics. Network or transient dependency errors can be retried; invalid data or business rule violations should usually go straight to the DLT or dedicated recovery.

Do not routinely retry every RuntimeException over long periods. An unrecoverable exception can occupy retry topic capacity, delay resolution, and obscure the real root cause.

## 9. DLT Is the Terminal Stage, Not Business Success

The dead-letter topic holds records that could not be completed after the retry policy or were excluded from retries due to an ineligible exception. The DLT name can be configured; for example, orders-dlt.

A record on the DLT should contain enough information for investigation:

- Payload and key, if safe to store.
- Business Event ID or correlation ID.
- Original topic, partition, and offset.
- Exception details, cause, and final-stage failure info.
- Number of processing attempts and retries executed.
- Timestamps for the initial attempt and most recent forward.

Putting a record into the DLT only means the record was routed to the error-handling path per policy if the publish succeeded. It does not mean OrderCreated was processed properly or side effects completed.

DLT requires an operational workflow: alerts on new records, dashboards by exception class, error inspection tools, controlled replay rules, and safeguards against infinite replays. If replaying an event that already produced side effects earlier, the consumer must have idempotency.

If publishing to the DLT fails due to permissions, serializer issues, or broker unavailability, do not silently treat the record as resolved. Configure recoverer/DLT error-handling policies and monitor the final outcome clearly.

## 10. Why Does Non-Blocking Retry Alter Processing Order?

Kafka preserves read order within a partition, but a retry topic is a different topic with its own log and consumer. When a failed record is forwarded, the original topic can continue processing subsequent records. Consequently, business completion order may differ from the original append order.

Example with the same orderId:

~~~text
orders / partition 0:
  offset 10: OrderCreated  -> failed -> forwarded to retry
  offset 11: OrderPaid     -> succeeded
  offset 12: OrderShipped  -> succeeded

orders-retry:
  OrderCreated             -> waited 30 seconds -> succeeded

Observed completion order:
  OrderPaid -> OrderShipped -> OrderCreated
~~~

For a business workflow requiring OrderCreated before OrderPaid, that order can corrupt data. Assigning the same key sends records to the same partition on the original topic, but **does not preserve order across retry topics**.

Mitigation depends on business needs:

- If records are independent, out-of-order processing may be acceptable.
- If side effects must be sequential, consider short blocking retries before moving to the error flow.
- Design the consumer to check version, state, or prerequisites before applying changes.
- Use event IDs, sequence numbers, or a state machine to detect out-of-order events.
- For stricter requirements, consider a dedicated processing model guaranteeing per-entity ordering.

Do not enable non-blocking retry for events modifying balances, order states, or order-dependent workflows without first deciding how to handle this issue.

## 11. Offsets, Acknowledgements, and Duplicate Processing Risk

When a failed record is forwarded to a retry topic, the original topic's consumer can advance once the framework handles the error and commits the offset per container configuration. This avoids blocking the original record forever in the main flow.

However, **forwarding the record** and **committing the source offset** are two separate actions that must be coordinated. If the application crashes right during forwarding, the record may be sent to the retry topic before the source offset is committed. After restart, the source record may be read again and forwarded a second time. Conversely, committing too early before publish truly succeeds risks losing the processing opportunity.

Therefore, never assume end-to-end exactly-once semantics just because the framework forwarded the record through retry topics.

A duplicate processing scenario:

~~~text
1. Original listener processes eventId=E123 -> fails
2. Recoverer publishes E123 to retry topic
3. Application crashes before source offset is committed
4. New consumer reads original event E123 again
5. E123 is forwarded a second time

Retry topic may contain two records with eventId=E123.
~~~

Defensive business design should use a stable event ID across every stage. If the listener updates a database, record the processed event ID in the same database transaction as the side effect and skip duplicate executions. If calling an external API, use an idempotency key if the service supports one.

A retry attempt can also fail after a side effect occurred but before the listener signals success. Thus, idempotency must apply at the business execution step, not solely in the record-forwarding logic.

## 12. Where Do Blocking Retry and Retry Topics Differ?

| Criterion | Blocking retry | Non-blocking retry topic |
|---|---|---|
| Where retries happen | Original listener/container consumption flow | Separate retry topics consumed by dedicated listeners |
| Backoff waiting | Handler holds record processing in original container | Retry consumer waits for due time on retry topic |
| Impact on original topic | Can block consumer thread and co-assigned partitions | Original topic can usually keep advancing |
| Business ordering | Better when sequential per-partition processing is needed | Later records can finish before failed record |
| Topic overhead | No separate retry topics needed | Requires provisioning, retention, ACLs, monitoring for retry topics |
| Suitable errors | Transient errors with short delays | Errors needing long delays where out-of-order handling is acceptable |
| Observability | Retry attempts/backoff inside one consumer flow | Requires tracing events across multiple topics and offsets |

Blocking retry can still be useful before non-blocking retry for very brief errors, but when combining two layers you must calculate maximum attempts and total wait time explicitly. Do not stack retry layers without knowing exactly how many times a record will be attempted.

A selection guide:

- Brief database connection blips of a few hundred milliseconds: short blocking retry may suffice.
- Downstream service needs several minutes to recover and events are independent: retry topics fit better.
- Events require strict per-key ordering: prioritize ordering-preserving solutions or redesign the business flow.

## 13. Retry Topics and Cluster Topic Configuration

Each retry topic should be operated as an important topic in the reliability chain. Parameters to consider include:

| Configuration group | Why it matters |
|---|---|
| Partition count | Determines parallelism and consumer concurrency limits on the retry topic |
| Replication factor | Determines replica count and broker fault tolerance |
| min.insync.replicas | Works with acks=all to enforce minimum replication durability |
| Retention | Must exceed wait times, backlogs, outages, and investigation needs |
| ACL / authentication | Consumers must read retry/DLT; producer must write destination topics |
| Serializer / deserializer | Payloads must be forwarded and read back with matching types |
| Cleanup policy | Avoid deleting or compacting records inappropriately before retry |
| Monitoring | Need to detect retry topic backlogs and abnormal DLT growth |

For example, if backoff spans hours while retry topic retention is only minutes, records can expire before being retried. Retention must account for maximum wait time plus potential topic backlogs or consumer downtime.

Do not assume retry topics have the same partition count as the original topic. Inspect the generated topology and actual partition counts, especially when forwarding preserves partition numbers. If a recoverer targets a partition that does not exist on the destination topic, publishing can fail. Partitioning, key routing, and consumer counts must align.

The producer used for forwarding also needs reliable settings, such as acks=all and idempotence where appropriate; meanwhile, the system must monitor publish errors. Reliability of a retry topology depends on both the forwarding producer and the retrying consumer.

## 14. Fixed Delay, Exponential Delay, and Retry Topic Reuse

The same number of retries can be organized under different topologies.

### Fixed Delay

All retries wait the same interval, such as 5 seconds:

~~~text
Main -> retry 5s -> retry 5s -> retry 5s -> DLT
~~~

Depending on version and configuration strategy, Spring Kafka may use multiple topics or reuse one topic for retries sharing the same delay. Reusing a topic reduces resource count, though it does not remove the need to manage attempt counts and backoff metadata.

### Exponential Delay

Wait intervals grow per attempt:

~~~text
Main -> retry 1s -> retry 2s -> retry 4s -> retry 8s -> DLT
~~~

This pattern reduces call frequency against a struggling service, though total completion time can become large. Once backoff reaches maxDelay, subsequent attempts may share the same delay. Some Spring Kafka versions support reusing a single topic at the max delay to avoid creating extra identical topics.

Do not choose a policy based solely on topic count. Consider Kafka quotas, consumer count, failed event volume, maximum delay, retention, and traceability.

## 15. A Newly Arrived Record in a Retry Topic May Wait Behind Another Record

Non-blocking retry does not guarantee every record in a retry topic is processed the instant it becomes due. Consumers read records in offset order within each partition. If the record at the head of a partition is not yet due, the partition may be paused. Subsequent records behind it, even if already eligible, must wait for the head record to be delivered in partition read order.

Example:

~~~text
Retry partition P1:

offset 50: event A, due 12:05
offset 51: event B, due 12:03

At 12:03:
  A is not due yet.
  Consumer cannot skip past A to process B.

When A becomes due:
  consumer can resume reading in partition order.
~~~

This can happen when multiple events are forwarded with different delays into the same retry partition. Thus, retry topics avoid blocking the main topic yet still exhibit local head-of-line waiting inside a retry topic.

If relatively predictable retry latency under heavy load is needed, monitor the age of waiting records, partition lag, and records due yet unprocessed. Consider delay-based topic splitting strategies or partition distribution suited to the workload.

## 16. Serializer and Deserializer Errors in a Retry Topology

A record can fail before the business listener is invoked—for example, when a deserializer cannot convert bytes into an object. For such errors, determine whether the failure occurred in the Kafka consumer layer or inside the listener.

Several considerations:

- When deserialization fails before the listener, ErrorHandlingDeserializer or a matching error handler mechanism may be required so the framework receives error info and recovers.
- Retrying the same bytes multiple times will not fix an invalid schema.
- The forwarding producer must support serializing the payload appropriately; in some recovery flows, the payload may still be raw byte[].
- If retry topics and DLT use incompatible serializers, records may fail to forward even when business exceptions are handled properly.
- As event schemas evolve, original listeners, retry topics, and DLT consumers must all understand stored payload versions.

Classify deserialization, conversion, and schema errors as requiring investigation or early DLT routing unless there is clear reason to believe retrying will help. If a schema registry is temporarily unavailable, classification may differ from truly invalid payloads.

## 17. Integration Limitations with Batch Listeners and Transactions

Spring Kafka's non-blocking retry has important limitations that must be checked against the version in use.

**Batch listeners:** The retry topic mechanism is designed primarily for record listeners. Common Spring Kafka versions do not support combining non-blocking retry with batch listeners in the same way as record listeners. If using a batch listener, verify support limitations and choose batch error handling or change the processing model before adopting @RetryableTopic.

**Container transactions:** Non-blocking retry is not directly combined with Kafka container transactions under common Spring Kafka support. Transactional listeners use their own rollback/AfterRollbackProcessor mechanisms. Do not assume forwarding to a retry topic and committing the source offset become a single Kafka transaction merely because the producer has a transaction-id-prefix.

**Guarantees with external systems:** Kafka transactions also do not automatically roll back databases, emails, or payment APIs. For external side effects, use idempotency, outbox, or appropriate consistency mechanisms.

**Blocking + non-blocking retry:** A combined policy may be needed for certain scenarios, but confirm version-compatible implementation, total attempts, ordering, and recovery points. Do not attach a DefaultErrorHandler with long retries to every retry listener without calculating the entire record lifecycle.

## 18. Monitoring Retry Topics in Production

A reliable dashboard must distinguish activity across the main topic, retry topics, and DLT. Monitoring only the original topic's lag can create the illusion that everything is processed while many records remain waiting in retry topics.

Useful metrics:

- Number of records failing on the original topic and forwarded to retry topics.
- Publish success/error rate of the retry publisher.
- Consumer lag per retry topic and per partition.
- Actual time from initial failure to retry.
- Age of the oldest waiting record.
- Success rate at each retry attempt.
- Number of records entering the DLT and their causes.
- DLT handler or DLT publisher failures.
- Rebalance count, consumer uptime, and paused partition count.
- Retry topic bytes, retention pressure, and storage capacity.

For each event, logs should include event ID, original topic/partition/offset, current topic/partition/offset, attempt, exception category, and correlation ID. Do not use event ID or offset as metric labels because cardinality can become huge.

Example for investigation:

~~~text
eventId=E123
original=orders-2@410
current=orders-retry-2000-2@24
attempt=3
error=TemporaryPaymentException
nextAction=retry
~~~

The log format above is illustrative application output, not a default framework format.

When DLT volume spikes suddenly, check exception distribution and downstream status before bulk replaying. Replaying all records while a dependency is still broken creates a new retry loop, increases Kafka load, and puts pressure on the very service trying to recover.

## 19. Failure Scenarios to Anticipate

### Retry Topic Does Not Exist or Lacks Write Permission

The framework may fail to forward records. Check topic provisioning, broker ACLs, producer configuration, target partitions, and publish results. If using autoCreateTopics=false, ensure every topic in the topology is created before the listener starts.

### Retry Consumer Stopped for a Long Period

Records remain in the retry topic until consumed or retention expires. Once the consumer restarts, unprocessed records can resume processing if they are still in the log. That is why retention and lag alerts are critical.

### Dependency Recovered Yet Retries Are Still Slow

Check backoff due times, paused retry partitions, head-of-partition records not yet due, consumer count, and backlog. A record may be due yet still waiting behind earlier records in the same partition.

### Record Processed Twice

Check original offset commits, retry topic publishing, crashes/rebalances, and side-effect idempotency. Retry topics do not automatically deduplicate two independent forwards of the same event ID.

### Record Goes Straight to DLT

Check the exception classifier, remaining attempts, and retry time-limit policies. A non-retryable exception can be routed to the DLT even without going through all retry topics.

### Record Missing from Main Topic Yet Business Logic Incomplete

Check retry topics, DLT, and linked metadata by event ID. A record forwarded out of the main flow does not mean business processing succeeded.

## 20. Testing the Full Retry Journey

Write integration tests with a Kafka test broker or equivalent environment to observe behavior across multiple topics. Key cases include:

1. Listener succeeds on first attempt: no records emitted to retry/DLT.
2. First attempt hits retryable error, second succeeds: record goes through one retry stage and completes.
3. Retryable error on all attempts: record reaches DLT after exhausting attempts.
4. Non-retryable error: record skips the full retry chain.
5. Exponential delay: actual execution time is no earlier than policy's scheduled time.
6. Retry consumer temporarily paused/stopped: records remain in retry topic before retention expires.
7. Retry publish fails: system records the error and does not silently drop the record.
8. Crash between forward and source commit: consumer tolerates duplicate record appearances.
9. Two events with the same key: confirm business order can invert when the earlier event is retried.
10. DLT handler fails: operations knows the record has not finished processing.

In tests, use unique event IDs per record and inspect the relevant topics. Avoid long fixed sleeps to measure backoff; use short delays with timeouts and bounded polling assertions. Distinguish scheduler/poll jitter from retry policy bugs.

## 21. Common Misconceptions

**Retry topics make the Kafka broker reprocess records by itself.** Incorrect. The broker stores records; the Spring Kafka retry consumer checks due times and re-invokes the listener.

**Non-blocking retry means nothing ever waits.** Incorrect. The original topic can continue, but the retry topic consumer still waits for backoff and may pause partitions.

**attempts=4 means four retries after the first attempt.** Incorrect. attempts usually includes the initial attempt; a value of 4 means at most four processing executions.

**Records keep the same offset when moved to a retry topic.** Incorrect. Each topic has its own log and offsets. Use original metadata or event ID for tracing.

**Same key guarantees ordering after moving to retry topics.** Incorrect. Retry topics and the original topic have separate consumers, offsets, and schedules.

**Once forwarded to a retry topic, data is guaranteed to be processed exactly once.** Incorrect. Publishing and source commits have failure windows; retries can repeat side effects. Commit policies and idempotency are needed.

**Entering the DLT means the business workflow finished.** Incorrect. It was simply routed into an error stream for further handling or investigation.

**Adding more retry topics always speeds up processing.** Incorrect. It adds resources and complexity; throughput still depends on partition count, consumers, and downstream capacity.

**A 1-second delay guarantees retrying at exactly 1 second.** Incorrect. That is the earliest eligible time per policy; actual execution also depends on the consumer and cluster.

**Non-blocking retry works for every batch or transactional listener.** Incorrect. Check Spring Kafka support limitations; batch and transactional listeners have their own semantics.

## 22. Guide to Designing Retry Topics

When adding non-blocking retry to a new listener, first determine which exceptions are truly recoverable and whether the business tolerates out-of-order processing.

An implementation workflow:

1. Identify retryable and non-retryable errors based on dependency behavior, schemas, and business rules.
2. Choose attempts and backoff from expected recovery times, avoiding infinite retries.
3. Evaluate ordering impact, especially for events sharing an entity key.
4. Use @RetryableTopic or RetryTopicConfigurationBuilder to describe the topology.
5. Provision retry topics and DLT with appropriate partitions, replication, retention, ACLs, and serializers.
6. Control record forwarding, monitoring publish failures and source offsets.
7. Use stable event IDs and design idempotent side effects across every retry attempt.
8. Monitor lag on retry topics and DLT, not just main topic lag.
9. Establish alerts, error inspection procedures, and controlled DLT replay.
10. Test retry success, attempt exhaustion, DLT failures, consumer downtime, crashes, and reordering.

Retry topics are a way to decouple recovery wait time from the main processing flow. They let the main consumer keep reading records while failed records are processed across a separate topic chain according to backoff. To operate reliably, you must fully understand topology, retry timing, offsets, ordering, publish failures, and idempotency; merely adding @RetryableTopic without managing these factors is not enough to guarantee business outcomes.
