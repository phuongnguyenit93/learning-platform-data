# @RetryableTopic

In Spring Kafka, **@RetryableTopic** is an annotation used to implement **non-blocking retry** for a **@KafkaListener** method. When the listener fails to process a record and the error matches the retry policy, Spring Kafka forwards the record to one or more **retry topics**. A consumer dedicated to the retry topic receives the record and performs the next processing attempt after a delay. If all attempts are exhausted or the error does not belong to a retryable group, the record can be routed to a **dead-letter topic (DLT)**.

This approach is suitable when a downstream dependency is temporarily unavailable for several seconds or minutes, yet the application still needs to process subsequent records from the original topic. A single failure no longer stalls the original topic's consumer for the entire backoff duration. In return, the system introduces a retry producer, retry topics, listener containers, and a DLT; forwarding records across topics can also **break business completion ordering per key**.

## 1. Execution Model

A listener calls a payment API, encounters HTTP 503, and throws an exception. With blocking retry, the consumer retries on the same thread after a BackOff. With non-blocking retry, Spring Kafka publishes the failed record to a retry topic and allows the original topic to continue advancing once forwarding and checkpointing complete.

~~~mermaid
flowchart LR
    A["Producer"] --> B["orders.events"]
    B --> C["Main listener"]
    C -->|Success| S["Business processing complete"]
    C -->|Transient error| D["orders.events-retry-1000"]
    D --> E["Retry listener"]
    E -->|Success| S
    E -->|Error| F["orders.events-retry-2000"]
    F --> G["Retry listener"]
    G -->|Success| S
    G -->|Exhausted| H["orders.events-dlt"]
    H --> I["@DltHandler or recovery service"]
~~~

Topic names in the diagram are illustrative. Actual names depend on the suffix strategy, attempt count, topic reuse behavior, and Spring Kafka version.

Key components:

| Component | Role |
|---|---|
| @KafkaListener | Processes records from the original topic |
| @RetryableTopic | Declares total attempts, backoff, exception groups, suffixes, and DLT |
| Retry-topic publisher | Sends failed records to a retry topic or DLT |
| Retry topics | Store records waiting to be reprocessed |
| Retry listeners | Receive records from retry topics when they become eligible |
| @DltHandler | Processes records routed to the DLT if declared |
| KafkaTemplate | Producer used to forward records |
| Kafka broker | Stores topics/partitions and serves fetches; does not decide retry business logic |

A record sent to a retry topic is a new Kafka record at a different topic and offset. The business Event ID must remain stable to correlate records throughout the retry lifecycle.

## 2. Declaring @RetryableTopic

Example of a business listener:

~~~java
import org.springframework.dao.TransientDataAccessException;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    private final OrderService orderService;
    private final DeadLetterService deadLetterService;

    public OrderConsumer(OrderService orderService,
                         DeadLetterService deadLetterService) {
        this.orderService = orderService;
        this.deadLetterService = deadLetterService;
    }

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
            delay = 1_000L,
            multiplier = 2.0,
            maxDelay = 8_000L
        ),
        include = {TransientDataAccessException.class},
        autoCreateTopics = "false"
    )
    @KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-processor"
    )
    public void handle(OrderEvent event) {
        orderService.applyIdempotently(event);
    }

    @DltHandler
    public void onDlt(OrderEvent event) {
        deadLetterService.recordForInvestigation(event);
    }
}
~~~

The classes OrderEvent, OrderService, and DeadLetterService are illustrative domain components. In a real system, you must configure the consumer deserializer, producer serializer, KafkaTemplate, broker connectivity, topics, and ACLs.

Meaning of each attribute:

- **attempts = "4"** sets the maximum total number of delivery attempts in the retry flow, **including the initial processing attempt on the original topic**. In this example, there is at most one initial attempt and three retries.
- **backoff** defines the wait interval before subsequent attempts.
- **include** specifies the exception groups eligible for retry. Exceptions outside this group are handled according to policy and may go to the DLT.
- **autoCreateTopics = "false"** requires the corresponding topics to be provisioned externally.
- **@DltHandler** is the method that handles records on the DLT; it does not mean the original business processing succeeded.

Do not assume adding the annotation alone completes the setup. The retry infrastructure also needs a producer capable of forwarding records and available target topics.

## 3. Enabling the Retry-Topic Infrastructure

Depending on the Spring Kafka and Spring Boot versions, the retry-topic infrastructure may need to be enabled via a configuration annotation:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafkaRetryTopic;

@Configuration
@EnableKafkaRetryTopic
public class KafkaRetryConfiguration {
}
~~~

This is an explicit way to enable the Spring Kafka components needed to create retry endpoints. In environments where auto-configuration already sets up the infrastructure, avoid duplicate registration. Focus on verifying that the runtime has created the listener containers for the original topic, retry topics, and DLT according to the expected topology.

The minimum prerequisites are a KafkaTemplate used to forward records, appropriate producer serializers, existing or auto-creatable retry/DLT topics, publish/consume permissions, and a listener container factory matching the application.

## 4. Distinguishing Delivery Attempts and Retry Count

Suppose a record always fails processing and attempts is configured to 4:

| Attempt | Source | Outcome |
|---:|---|---|
| 1 | Original topic | Failed; forwarded to retry |
| 2 | Retry topic | Failed; forwarded to next retry |
| 3 | Retry topic | Failed; forwarded to next retry |
| 4 | Retry topic | Failed; attempts exhausted |
| Afterward | DLT | Awaits recovery according to policy |

Here, the total number of attempts is 4, while the number of retries after the first attempt is 3. If the record succeeds on any attempt, subsequent attempts are unnecessary.

When building metrics, clearly distinguish between **total delivery attempts**, **blocking retries within a container**, and **forwards across retry topics**. These numbers can differ, especially when combining DefaultErrorHandler with @RetryableTopic.

## 5. Backoff: Fixed and Exponential

The backoff attribute uses Spring Retry's Backoff annotation. Common configurations:

~~~java
// Fixed delay: wait interval of approximately 5 seconds each time
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 5_000L)
)
~~~

~~~java
// Capped exponential delay
@RetryableTopic(
    attempts = "5",
    backoff = @Backoff(
        delay = 1_000L,
        multiplier = 2.0,
        maxDelay = 10_000L
    )
)
~~~

With the exponential delay in the second example, the illustrative wait intervals can grow as 1, 2, 4, and 8 seconds. With more attempts, maxDelay caps the duration of subsequent wait intervals. Actual processing timing is not millisecond-exact because it also depends on the poll loop, thread scheduling, broker/network conditions, and rebalances.

**The Kafka broker does not natively support scheduling a record according to @RetryableTopic delays.** Spring Kafka uses timestamp metadata on the record along with consumer pause/resume or delay mechanisms to deliver the record to the listener only once the threshold is reached. Therefore, you may observe an actual retry delay longer than the configured backoff.

Choosing backoff values must account for downstream outages, rate limiting, typical recovery times, and SLAs. A retry delay that is too short can cause a retry storm; one that is too long can leave events backlogged unnecessarily.

## 6. Exception Classification

Not every error should be retried. Transient errors may disappear once a dependency recovers; permanent errors typically require fixing data or configuration.

| Error group | Typical behavior to consider |
|---|---|
| Database deadlock | Bounded retry after transaction rollback |
| HTTP 429 / 503 | Retry with BackOff and a total time limit |
| Network timeout | Retry if the external operation is idempotent |
| ValidationException | Do not retry; recovery/DLT |
| Incompatible schema | Investigate producer/consumer contract, possibly DLT |
| AuthorizationException | Fix permissions; retrying will not grant ACLs |
| Permanent business invariant violation | Do not retry; record and handle via business workflow |
| Duplicate event | Handle idempotently; do not treat valid duplicates as transient errors |

You can configure include and exclude:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2_000L),
    include = {
        org.springframework.dao.TransientDataAccessException.class
    },
    exclude = {
        IllegalArgumentException.class
    }
)
~~~

Exceptions may be wrapped by Spring listener exceptions, driver exceptions, or HTTP client exceptions. Verify the cause-chain traversal and classification rules in the Spring Kafka version you are running. If include is configured too broadly, permanent errors can occupy retry topics for a long time. If exclude is misconfigured, a recoverable error may go straight to the DLT.

## 7. Topic Naming and Retry Stages

Spring Kafka typically uses suffixes for retry topics and the DLT. For an original topic orders.events, the names might look like:

~~~text
orders.events
orders.events-retry-1000
orders.events-retry-2000
orders.events-retry-4000
orders.events-dlt
~~~

These names are only to illustrate the topology. Never assume the number of retry topics equals attempts minus one in every case: the same delay can reuse a retry topic depending on policy, suffix strategies can attach either delay or index, and behavior varies across versions.

You can specify suffixes explicitly:

~~~java
@RetryableTopic(
    retryTopicSuffix = "-retry",
    dltTopicSuffix = "-dlt",
    attempts = "4",
    backoff = @Backoff(delay = 1_000L, multiplier = 2.0)
)
~~~

When changing retry topic naming or attempt counts on a running deployment, check for any backlog remaining in old topics. An old topic no longer subscribed to by new listeners can retain records until retention deletes them. Changing topology requires a migration or backlog-draining plan.

## 8. Topic Provisioning and ACLs

When autoCreateTopics is set to false, retry and DLT topics must be created beforehand. When auto-creation is enabled, you must control Admin permissions, partition count, replication, retention, and platform team policies.

Example of an approved topology:

| Topic | Partitions | Replication | Purpose |
|---|---:|---:|---|
| orders.events | 6 | 3 | Source events |
| orders.events-retry-1000 | 6 | 3 | Retry stage 1 |
| orders.events-retry-2000 | 6 | 3 | Retry stage 2 |
| orders.events-retry-4000 | 6 | 3 | Retry stage 3 |
| orders.events-dlt | 6 | 3 | Investigation/replay |

These values are illustrative only. Provision according to the **actual topology** after Spring applies its strategy. Ensure the partition counts of retry/DLT topics are compatible with how Spring forwards partition indexes. If a target topic lacks the targeted partition, publishing can fail.

Typical required permissions:

- Consumer principal: READ on original/retry/DLT topics matching deployed listeners, plus appropriate consumer group permissions.
- Retry publisher principal: WRITE on retry/DLT topics.
- Provisioning principal: CREATE/ALTER permissions if infrastructure creates topics in a governed way.

Never grant ALL across the entire cluster just to make @RetryableTopic work. Grant the exact principal, resource, and operations following security procedures.

## 9. DLT and @DltHandler

After retries are exhausted or when a non-retryable error occurs, the retry infrastructure can route the record to the DLT. A method annotated with @DltHandler can receive the record and persist it for investigation:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.DltHandler;

@DltHandler
public void handleDlt(
        ConsumerRecord<String, OrderEvent> record) {

    recoveryService.storeForReview(
        record.topic(),
        record.partition(),
        record.offset(),
        record.value()
    );
}
~~~

In production systems, store the event ID, original topic (from appropriate headers/metadata), failure cause, timestamp, and processing status. Do not simply log and discard the record if the business requires recoverability.

If no DltHandler is declared, the infrastructure may use a default handler depending on the version and configuration. Do not rely on defaults without knowing whether the DLT is consumed, logged, or requires a separate recovery service.

Some systems intentionally do not start a DLT handler, allowing operations teams to inspect data before replaying. This decision must be reflected in configuration, ownership, and runbooks.

### If the DLT Handler Also Throws an Error

Spring Kafka supports DltStrategy policies to control behavior when DLT processing fails. For example:

~~~java
import org.springframework.kafka.retrytopic.DltStrategy;

@RetryableTopic(
    attempts = "4",
    dltStrategy = DltStrategy.FAIL_ON_ERROR
)
~~~

Check the exact enum values and semantics for the version in use. A failing DLT handler may cause the record to be redelivered according to policy or let the error be reported instead of treating it as recovered. Track DLT handler failures separately from original-topic listener failures.

## 10. Why Can @RetryableTopic Alter Ordering?

Suppose the same partition contains three events for order 42:

~~~text
offset 100: OrderChanged(order=42, version=1)
offset 101: OrderChanged(order=42, version=2)
offset 102: OrderChanged(order=42, version=3)
~~~

If version 1 fails and is forwarded to a retry topic, the original topic consumer can process versions 2 and 3 before version 1 is retried. Side effects may complete in the order 2, 3, 1.

Kafka still guarantees ordering within each partition of **each individual topic**. Forwarding a record to a retry topic creates a separate path and does not preserve the original business completion order.

If strict ordering per aggregate is required, consider:

- Bounded blocking retry or a dedicated per-key sequencing mechanism.
- Checking the version/sequence number before updating.
- Using conditional updates that only accept newer versions.
- Holding subsequent records for the same aggregate in a workflow until the preceding record completes.
- Designing business logic that can tolerate out-of-order events.

This is a core design decision. Do not enable non-blocking retry merely to reduce consumer lag when the domain requires strict ordering.

## 11. Blocking Retry vs. Non-Blocking Retry

| Criterion | DefaultErrorHandler blocking retry | @RetryableTopic non-blocking |
|---|---|---|
| Where waiting happens | Inside the current listener processing path | Separate retry topic and retry consumer |
| Delays of seconds/minutes | Can stall the partition | Source topic can continue advancing |
| Per-partition ordering | Typically preserves processing order in current flow | Can invert completion order between source topic and retry |
| Additional topics | Not required | Requires retry/DLT topology |
| Monitoring | BackOff, exception, attempts at container level | Retry stages, topic lag, forward success, DLT |
| Capacity | Fewer components | Increases topic/container/producer traffic |
| Best suited for | Short failures where ordering matters | Long failures without strict ordering requirements |

You can combine a few fast blocking retries with non-blocking retries as supported by your version's features and configuration. When doing so, account for total business invocations, backoff, latency, and callbacks/metrics at each layer. Do not let two retry layers multiply uncontrollably.

## 12. Limitations with Batch Listeners and Kafka Transactions

In Spring Kafka versions implementing the retry-topic feature under this model, non-blocking retries **do not support batch listeners** and **do not integrate directly with container Kafka transactions**. Always verify limitations against your current dependency version.

Consequences:

- Do not attach @RetryableTopic to a batch listener and expect each failed record to be split out cleanly like a record listener.
- If a container uses a Kafka transaction manager to process and commit offsets within a transaction, do not assume the retry-topic infrastructure can participate in the same semantics.
- A Kafka transaction does not turn a database transaction or an HTTP API call into an atomic transaction.
- If consistency across multiple systems is needed, use transactional outbox, inbox, idempotency, or an explicitly designed workflow.

If the use case is Kafka-to-Kafka exactly-once processing, separately evaluate transactional listeners, AfterRollbackProcessor, and an appropriate retry strategy before choosing @RetryableTopic.

## 13. Idempotency and Duplicate Delivery

When a record is forwarded from the original topic to a retry topic, there is a step to publish the new record and a step to acknowledge the source offset. If publishing succeeds but committing the source offset fails, the source record may be redelivered and forwarded again. A restart or rebalance can also cause redelivery after a database side effect has already committed.

Idempotent consumer example:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void applyIdempotently(OrderEvent event) {

    boolean firstTime =
        processedEventRepository.insertIfAbsent(event.eventId());

    if (!firstTime) {
        return;
    }

    orderRepository.apply(event);
}
~~~

The insertIfAbsent method must be atomic—for example, using a unique constraint on event ID and the database's equivalent insert-on-conflict operation. The processed marker and business changes must reside in the **same database transaction**. If it rolls back, the marker also rolls back so the retry attempt can execute again.

When calling a payment API, send a stable idempotency key if the API supports it. If events must be emitted after updating the database, consider an outbox. Never use the topic/partition/offset of a retry record as a unique business key, because the new record has a new offset.

## 14. Tracking Attempts Across Multiple Topics

A record traveling from the original topic across retry topics gets new Kafka metadata at every hop. In logs and traces, preserve:

- Stable Event ID and correlation ID.
- Current topic, partition, and offset.
- Source topic and partition if headers/metadata are available.
- Retry stage and expected delay.
- Original exception and latest exception.
- Failure timestamp and retry-eligibility timestamp.
- Publish outcome and final processing result.

Retry headers managed by Spring Kafka can vary by version. When writing code that reads metadata/headers, use constants or APIs provided by the current dependency instead of hard-coding a header name from an old example.

A **RetryListener** attached to DefaultErrorHandler observes attempts within that specific error handler; it does not automatically count all topic hops of @RetryableTopic. If end-to-end auditing across restarts and multiple topics is required, build a record keyed by event ID in a durable store.

## 15. Failures When Publishing to Retry or DLT

Non-blocking retry relies on a producer to forward records. Forwarding can fail because of:

- Broker unavailability or request timeout.
- Target topic has not been created.
- Principal lacks WRITE permission on the retry or DLT topic.
- Target topic does not have the selected partition.
- Serializer does not support the current payload or headers.
- Inadequate quotas, network issues, or misconfigured producer settings.
- Consumer rebalance and offset commit failure during forwarding.

When a forwarding failure occurs, distinguish whether the listener failed, whether publishing succeeded, and the committed offset of the source consumer. Do not treat a record as forwarded merely because a business error was detected.

Logs and alerts should separate **retry forwarding failure** from listener processing failure. If publishing to the DLT fails, the recovery workflow is also incomplete; the record may still need to be redelivered according to container/error handler semantics.

## 16. Serializers and KafkaTemplate

The retry publisher must be able to serialize the record's key/value types. For a simple JSON event, configuration might look like:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        enable.idempotence: true
~~~

If the consumer uses ErrorHandlingDeserializer or needs to forward records containing raw bytes upon deserialization failure, the retry/DLT publisher must support the actual data types being sent. Test deserialization failure cases separately because the listener method may never have received a valid domain object.

If the application has multiple KafkaTemplate beans, @RetryableTopic can reference the appropriate template bean name:

~~~java
@RetryableTopic(
    kafkaTemplate = "retryKafkaTemplate",
    attempts = "4",
    backoff = @Backoff(delay = 1_000L)
)
~~~

The bean named retryKafkaTemplate must be defined with the appropriate ProducerFactory, serializers, and security settings. Avoid using a business template that can only serialize one event type when the retry infrastructure must send multiple payload types.

## 17. Retention and Capacity

Records may wait for long periods in retry topics. The DLT typically needs longer retention for investigation and replay. Topic retention must cover configured delays, downtime duration, backlog, and incident response schedules.

| Resource | What to plan for |
|---|---|
| Retry topic retention | Longer than wait durations and expected outages |
| DLT retention | Enough time for detection, investigation, and replay |
| Partition count | Matches consumer concurrency and routing |
| Replication | Matches business data durability requirements |
| Disk/network | Withstands retry storms and multiple publishes |
| Consumer lag | Observable backlog for each retry stage |

A DLT with overly short retention can delete records before operators detect them. A retry topic with retention shorter than the maximum delay can also lose records before they become eligible for reprocessing.

## 18. Concurrency of Retry Containers

Retry listeners have their own containers, so their concurrency must be evaluated independently from the original topic listener. Increasing concurrency can drain backlog faster after an outage, but it can also put renewed pressure on a recovering downstream service.

The right value depends on partition count, instance count, rate of records entering retry stages, database connection pools, API rate limits, and business workload type. Never assume highest concurrency is always best. If the business logic has contention on the same aggregate, running retries in parallel can cause database deadlocks or duplicate side effects.

Some versions expose properties to configure concurrency for retry containers. Verify the API of the version in use and measure actual consumer assignments rather than looking only at annotation settings.

## 19. Observability and Alerting

Dashboards for non-blocking retry must cover the entire topology.

| Metric | Purpose |
|---|---|
| Original listener failure rate | Detect processing errors at the source |
| Retry forwarding failure | Detect inability to forward records |
| Retry topic backlog/lag | Observe number of waiting records |
| Oldest record age | Assess records breaching SLA |
| Scheduled versus actual retry delay | Detect abnormally prolonged delays |
| Retry processing success rate | Measure effectiveness of retry attempts |
| DLT ingress rate | Detect prolonged or non-retryable failures |
| DLT handler/replay failures | Observe the recovery path |
| Producer send latency/errors | Monitor the retry/DLT publish channel |
| Downstream error rate/latency | Correlate with root causes |

Log example:

~~~text
event=retry_forwarded
service=order-processor
event_id=evt-42
source_topic=orders.events
source_partition=1
source_offset=847
destination_topic=orders.events-retry-1000
retry_stage=1
exception_class=DownstreamUnavailableException
~~~

Event ID, offset, and correlation ID should appear in logs/traces to locate specific records; do not use these values as metric tags due to high cardinality. Never log credentials or full payloads containing sensitive data.

A single retry can be normal. Alert on error rates, backlog, oldest age, DLT spikes, and forwarding failures rather than alerting on every individual transient exception.

## 20. Safe DLT Replay

A record in the DLT does not mean the business event is complete. An owner and recovery procedure are required:

1. Retrieve the event ID, source payload, and exception from the DLT.
2. Determine whether the error is schema, configuration, dependency, or business-related.
3. Check for side effects that may have already occurred before the failure.
4. Fix the root cause and verify the downstream dependency has recovered.
5. Decide which topic to replay to and whether ordering must be preserved.
6. Keep the same event ID/idempotency key if executing the same business action.
7. Replay at a controlled rate to avoid overload.
8. Monitor success, retry, and DLT rates after replay.
9. Record scope, operator, and outcome.

Do not bulk-replay all DLT records immediately when a dependency returns. Some records may have permanent errors or no longer be valid given the current business state.

## 21. Testing Non-Blocking Retry

Use a real Kafka broker or Testcontainers to verify topology, ACLs/serializers, delays, and consumer groups. Unit tests on the listener method do not prove record forwarding across topics.

Scenarios to test:

| Scenario | Expected outcome |
|---|---|
| Listener succeeds immediately | No retry/DLT records emitted |
| Retryable error then recovery | Record goes to retry and is processed successfully |
| Errors exhaust all attempts | Record enters DLT according to policy |
| Non-retryable error | Does not go through unnecessary retry stages |
| Missing retry topic | Forwarding failure is detected |
| Wrong serializer on KafkaTemplate | Forwarding error is logged/alerted |
| Producer lacks ACL | Authorization failure with clear cause |
| Consumer restarts while waiting for delay | Record can still be reprocessed after restart |
| Prolonged downstream outage | Backlog and retention withstand the load |
| DLT handler fails | Behavior follows DltStrategy as observed |
| Multiple events with the same key | Verify reordering and idempotency |

When testing delays, record the timestamps of the failure and the next delivery; use timeout-based polling assertions. Never use a single fixed sleep expecting the callback to fire at an exact millisecond.

## 22. Troubleshooting Runbook

When a record is not retried as expected:

1. Verify the service, listener ID, original topic, partition, offset, and event ID.
2. Check the @RetryableTopic annotation and confirm the infrastructure is enabled.
3. Identify the root exception and how classification applies.
4. Check attempts/backoff and the retry-eligibility timestamp.
5. List the actual retry/DLT topics.
6. Verify topic existence, retention, partition count, and ACLs.
7. Check KafkaTemplate, producer serializers, and publish results.
8. Confirm the retry listener container is running and assigned partitions.
9. Check retry topic lag, pause state, rebalances, and broker connectivity.
10. Search for the record in retry stages or the DLT by event ID.
11. Check for duplicate forwarding or already-committed side effects.
12. Fix the root cause, then monitor backlog decrease and success rate recovery.

If the original topic advances quickly while business processing remains slow, check retry topic backlogs and delays. If the record does not appear in a retry topic after the listener fails, prioritize checking exception classification and the retry publisher.

## 23. Common Misconceptions

**The annotation automatically creates Kafka permissions.** The application still needs ACLs on retry/DLT topics, group IDs, and related resources.

**attempts means the number of retries.** It usually includes the initial delivery; configuring attempts to 4 means at most 4 deliveries.

**Backoff is the exact execution time.** Delay is a threshold; scheduling and consumer state can make the retry happen later.

**Using retry topics still preserves ordering.** Splitting an event off the original topic allows later events to be processed first.

**Increasing concurrency always improves recovery.** High concurrency can overload a downstream system or increase database contention.

**Zero lag on the original topic means business processing is done.** Events may still be waiting in retry topics or the DLT.

**DLT means processing succeeded.** The DLT only holds records that failed business completion for further handling.

**Retries cannot create duplicates.** Publishing to a retry topic and committing the source offset still have failure windows leading to redelivery.

**Changing the retry suffix needs no migration.** Old retry topics may still hold backlog no longer subscribed to by new consumers.

**Using it with batch listeners or container transactions without checking.** These are important limitations of the retry-topic feature depending on version.

## 24. Pre-Production Checklist

**Business design**

- [ ] Define retryable and non-retryable errors.
- [ ] Choose attempts/backoff based on SLA, downtime, and rate limits.
- [ ] Assess the impact of losing ordering.
- [ ] Ensure consumers and side effects are idempotent.
- [ ] Have a DLT handling and replay procedure.

**Kafka topology**

- [ ] Runtime creates the expected retry/DLT listener endpoints.
- [ ] Retry/DLT topic names and reuse strategy are verified.
- [ ] Partitions/replication/retention are sized appropriately.
- [ ] Principals have least-privilege READ/WRITE/group ACLs.
- [ ] KafkaTemplate and serializers support forwarding.
- [ ] Have a plan for changing topology between deployments.

**Operations**

- [ ] Alerts exist for forwarding failures and DLT publish failures.
- [ ] Dashboards include retry topic lag and oldest record age.
- [ ] Tested restarts, rebalances, and downstream outages.
- [ ] Checked version limitations for batch/transactions.
- [ ] Integration tests cover success, retry, exhausted, and DLT paths.
- [ ] Replay procedure preserves event IDs and prevents duplicate side effects.

## 25. Principles of Usage

**@RetryableTopic** implements non-blocking retry by forwarding failed records through Kafka retry topics and to a DLT when needed. It is especially useful for long retry delays because the original topic listener can continue working.

For reliable operations, understand that attempts include the first delivery, backoff does not guarantee exact execution timing, topic forwarding can produce duplicates and alter processing order. Design for idempotency, provision topics/ACLs/retention, monitor the entire retry pipeline, and test publish failure paths before using in production.
