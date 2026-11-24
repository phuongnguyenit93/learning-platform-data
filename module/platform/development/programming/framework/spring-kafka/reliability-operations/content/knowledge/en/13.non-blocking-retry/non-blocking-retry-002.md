# RetryTopicConfiguration in Spring Kafka

In Spring Kafka, **RetryTopicConfiguration** lets you define **non-blocking retry** using a Spring bean built via RetryTopicConfigurationBuilder. When a listener fails to process a record, the framework can forward the record to a retry topic. The source topic's consumer continues processing other records; the retry topic's consumer attempts reprocessing after a configured wait interval. Once all attempts are exhausted, the record is routed to a dead-letter topic (DLT) or handled according to the recovery policy.

This approach fits when the system wants to avoid holding up a source partition while waiting seconds or minutes for a dependency to recover. It is especially useful when retry policies need to be managed centrally across multiple listeners. On the other hand, retry topics increase topic count, require read/write permissions, must be monitored, and can alter business processing order.

## 1. What Problem Does Non-Blocking Retry Solve?

Suppose a listener consumes OrderCreated and calls an external service. The service is returning HTTP 503. If blocking retry with a long backoff is used, the consumer can hold onto the current record and force subsequent records to wait. With non-blocking retry, the failed record is forwarded to a separate topic to be reprocessed later.

~~~text
orders.created
      |
      v
@KafkaListener
      |
      +--> Success -------------------> Complete
      |
      +--> Retryable exception
                 |
                 v
        Retry destination 1
                 |
                 | Wait interval elapsed
                 v
        Retry listener
                 |
                 +--> Success -------> Complete
                 |
                 +--> Still failing
                          |
                          v
                  Retry destination 2
                          |
                          v
                    Retry listener
                          |
                          +--> Success
                          |
                          +--> Attempts exhausted
                                  |
                                  v
                                 DLT
~~~

These are *logical stages*. The number of physical retry topics may vary depending on the backoff policy and how the framework reuses topics with the same delay. Do not assume every retry attempt creates a separate topic.

The main benefit is that the source consumer can move forward once forwarding the failed record succeeds. This is helpful when records are independent and strict ordering across events is not required.

## 2. How Does RetryTopicConfiguration Differ from RetryTopicConfigurationBuilder?

RetryTopicConfiguration is the object representing the retry topic configuration used by Spring Kafka to create destination topics and associated listener endpoints. RetryTopicConfigurationBuilder is the API used to build that object.

Bean creation example:

~~~java
@Bean
RetryTopicConfiguration ordersRetryConfiguration(
        KafkaTemplate<String, Object> kafkaTemplate) {

    return RetryTopicConfigurationBuilder.newInstance()
            .fixedBackOff(2_000L)
            .maxAttempts(4)
            .includeTopics("orders.created")
            .create(kafkaTemplate);
}
~~~

Meaning:

- fixedBackOff(2_000L): two-second logical wait interval before reprocessing.
- maxAttempts(4): at most four listener invocations, including the initial attempt on the source topic and three retries.
- includeTopics("orders.created"): applies the policy to the specified topic.
- create(kafkaTemplate): creates the configuration, providing the template for the framework to publish records to retry/DLT topics.

A RetryTopicConfiguration bean does **not** by itself alter the behavior of every KafkaTemplate.send in the application. It controls the error-handling flow of listener endpoints whose topics match.

The builder offers option groups such as topic selection, backoff, attempt count, DLT strategy, destination topic naming, topic creation settings, and exception classification. Some specialized methods/overloads differ across Spring Kafka versions; use the API matching your project version.

## 3. Minimal Configuration in Spring Boot

An illustrative configuration:

~~~java
@Configuration
@EnableKafka
@EnableKafkaRetryTopic
public class OrdersKafkaRetryConfiguration {

    @Bean
    RetryTopicConfiguration ordersRetryTopics(
            KafkaTemplate<String, Object> kafkaTemplate) {

        return RetryTopicConfigurationBuilder.newInstance()
                .fixedBackOff(3_000L)
                .maxAttempts(4)
                .includeTopics("orders.created")
                .create(kafkaTemplate);
    }
}
~~~

Listener:

~~~java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersCreatedListener",
            topics = "orders.created",
            groupId = "orders-service"
    )
    public void onOrderCreated(OrderCreated event) {
        orderService.processIdempotently(event);
    }
}
~~~

Configure broker connectivity, consumer group, and serializers, for example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.events
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
~~~

This is a directional example for an application using JSON. Type mapping, serializers, deserializers, and KafkaTemplate must match the actual event contract.

Depending on the version, Spring Kafka provides ways to enable the retry infrastructure via @EnableKafkaRetryTopic or configuration based on RetryTopicConfigurationSupport. Do not register two duplicate infrastructure mechanisms simultaneously. Spring Boot auto-configuration may also provide part of the required components; confirm the configuration approach suited to the version you are running.

## 4. maxAttempts Includes the Initial Processing Attempt

maxAttempts is the **total number of attempts**, not just the retry count.

With:

~~~java
.maxAttempts(4)
~~~

when a record always fails and is eligible for retry, the logical sequence is:

| Attempt | Processing location | If it fails |
|---:|---|---|
| 1 | Source topic | Forward to retry destination |
| 2 | Retry destination | Forward to next retry destination |
| 3 | Retry destination | Forward to next retry destination |
| 4 | Retry destination | Attempts exhausted, invoke recovery/DLT |

Thus there are at most three retries after the initial processing attempt. If the exception is classified as non-retryable, the record can go straight to recovery sooner.

Do not confuse listener attempts with the Kafka producer's retries property. The Kafka producer retries a failed ProduceRequest; non-blocking retry retries the **listener business logic** after the record has been forwarded to a retry topic.

## 5. Fixed Backoff and Exponential Backoff

### Fixed Backoff

Fixed backoff produces equal wait intervals between retry attempts:

~~~java
RetryTopicConfigurationBuilder.newInstance()
        .fixedBackOff(5_000L)
        .maxAttempts(4)
        .includeTopics("orders.created")
        .create(kafkaTemplate);
~~~

This example uses a 5-second delay and at most three retries. It is suitable when the dependency typically recovers after a short period and uniform retries do not cause overload.

### Exponential Backoff

Exponential backoff increases the delay after each failure:

~~~java
RetryTopicConfigurationBuilder.newInstance()
        .exponentialBackoff(1_000L, 2.0, 8_000L)
        .maxAttempts(5)
        .includeTopics("orders.created")
        .create(kafkaTemplate);
~~~

This is an example with an initial delay of one second, a multiplier of two, and a max delay of eight seconds. The logical wait intervals may be one, two, four, and eight seconds. Overload, jitter, or randomization support depends on the API version.

| Retry attempt | Fixed delay 2 seconds | Illustrative exponential |
|---:|---:|---:|
| 1 | 2 seconds | 1 second |
| 2 | 2 seconds | 2 seconds |
| 3 | 2 seconds | 4 seconds |
| 4 | 2 seconds | 8 seconds |

Actual processing time is not millisecond-exact. The retry consumer relies on timestamps and the poll loop to know when a record becomes eligible to run again; broker latency, rebalances, and system load can cause the record to be invoked later than planned.

Choose backoff according to dependency recovery time, SLA requirements, target system load, and total allowable event deferral time. If many instances retry simultaneously, jitter helps reduce thundering-herd effects.

## 6. Why Doesn't Non-Blocking Retry Block the Source Consumer?

When the source listener fails, the framework forwards the record to a retry destination. Once the recovery/forwarding step completes according to policy, the source listener container can process the next record.

~~~text
Source topic:
  Offset 100: A --> failed, forward A to retry topic
  Offset 101: B --> processed successfully
  Offset 102: C --> processed successfully

Retry topic:
  A --> wait until retry timestamp --> retry
~~~

The retry topic consumer can pause the partition while waiting for eligibility, while continuing to poll to maintain consumer group membership. This differs from placing a long Thread.sleep directly inside the source listener.

A non-blocking retry system is not an exact-time business scheduler. If an event must occur at a fixed wall-clock time or be rescheduled independently of Kafka polling, use a dedicated durable scheduler/queue.

## 7. Retry Topic Naming, Topic Count, and Topic Reuse

When retry topics are enabled, the framework must construct a topology consisting of the source topic, retry destinations, and DLT.

Illustrative topic names:

~~~text
orders.created
    |
    +--> orders.created-retry-2000
    +--> orders.created-retry-4000
    +--> orders.created-dlt
~~~

Actual names depend on suffix strategy, backoff delays, topic reuse options, and version. With fixed delay, multiple retry attempts may share the same retry topic or be mapped to different topics. Do not mechanically deduce that maxAttempts(4) will always create three retry topics.

In production, you must know the exact topics that will exist because they affect:

- Topic/partition counts and broker resources.
- Read and write permissions for Kafka principals.
- Retention policies, replication factor, min.insync.replicas.
- Consumer lag metrics per retry stage.
- Topic provisioning and cleanup procedures when retry policies change.

If using custom retry topic names, ensure they do not collide with business topics or other configurations, especially when multiple listeners share the same application context.

## 8. Auto-Creating Retry/DLT Topics vs. Manual Provisioning

The framework can create retry/DLT topics via KafkaAdmin under configurations that permit it. In production environments with IaC, an organization may want to pre-create all topics using Terraform/Helm or governance pipelines.

Example setting partition count and replication factor via the builder:

~~~java
RetryTopicConfigurationBuilder.newInstance()
        .fixedBackOff(2_000L)
        .maxAttempts(4)
        .autoCreateTopicsWith(6, (short) 3)
        .includeTopics("orders.created")
        .create(kafkaTemplate);
~~~

The configuration above illustrates six partitions and a replication factor of three for topics created under supported mechanisms. The cluster must have at least three eligible brokers to create topics with replication factor three.

If managing topics manually, create the exact destination topics the framework will use, allocate sufficient partitions, ensure proper retention, and grant write ACLs to the forwarding producer and read ACLs to retry/DLT consumers.

Do not assume retry topics share all retention, cleanup, or quota settings with the source topic. They are topics with their own operational lifecycle.

## 9. Keys, Partitions, and Out-of-Order Processing Risk

Kafka preserves offset order within a single partition of a single topic. Non-blocking retry moves a record to another topic, so it **does not guarantee business ordering across the source topic and retry topics**.

~~~text
Same key order-9:
  A: status = CREATED --> failed, to retry topic
  B: status = PAID    --> processed successfully on source
  A: retried later    --> may overwrite state backward
~~~

Keeping the same Kafka key sends records with the same key to the same partition within each topic when partitioning is configured accordingly, but it does not force a retrying record to execute before newer records on the source topic.

If an aggregate requires ordering:

1. Attach an event version/sequence and check it before updating.
2. Use optimistic locking or state transition validation.
3. Hold newer events for the same aggregate when an older event is incomplete, if the business allows.
4. Choose blocking retry for flows requiring strict ordering.
5. Design idempotency and reconciliation to restore consistent state.

Non-blocking retry is a better fit when records are independent or when business logic can detect out-of-order events.

## 10. KafkaTemplate Used for Forwarding Records

The create(kafkaTemplate) method accepts the template used by the framework to publish records to retry/DLT destinations. The template must:

- Connect and authenticate to the Kafka cluster.
- Have write permissions on retry/DLT topics.
- Have key/value serializers compatible with payloads to be forwarded.
- Have appropriate producer acknowledgements and timeouts.
- Handle send failures so recovery is not marked successful if the needed record was not stored.

If the consumer receives JSON objects, the template can use JsonSerializer. However, deserialization errors may need to send raw bytes to the DLT. In that case, use a serializer capable of handling both objects and byte[], or a dedicated template/serializer.

The KafkaTemplate used for retry topics may itself retry ProduceRequest calls at the Kafka client layer. That is a different mechanism from listener retry; do not count producer retries toward RetryTopicConfiguration's maxAttempts.

If publishing to the retry topic succeeds but the application stops before the source offset is committed, the source record may be redelivered and produce a duplicate retry copy. Therefore, non-blocking retry does not automatically guarantee end-to-end exactly-once processing.

## 11. Which Exceptions Should Be Retried?

Not every exception should be retried under the same policy.

| Error | Typically appropriate action |
|---|---|
| Temporary database disconnect | Retry with bounded backoff |
| HTTP 429 or 503 | Retry, consider Retry-After and jitter |
| API call timeout | Bounded retry, use idempotency key |
| Malformed JSON syntax | Non-retryable, DLT/quarantine |
| Invalid required field | Non-retryable, fix data/producer |
| Authorization denied | Non-retryable, alert |
| Deterministic logic bug | Limit retries, DLT for investigation |
| Dependency down for hours | Long delays and explicit backlog policy |

RetryTopicConfigurationBuilder supports options to classify retryable/non-retryable exceptions, with method names and nested cause traversal options depending on the Spring Kafka version. Define domain exceptions like InvalidEventException or TemporaryDependencyException and test the classification policy on the listener.

If the same payload always fails validation, retrying after several minutes will still fail. Routing to the DLT early reduces lag, broker cost, and dependency load.

## 12. DLT: The Terminal Stage Requiring Operations

The DLT holds records that cannot be processed after exhausting attempts or encountering a non-retryable error. The DLT is a place for investigation and recovery, not proof of business success.

~~~text
orders.created
     |
     +--> Retry stage 1
     |
     +--> Retry stage 2
     |
     +--> Attempts exhausted / non-retryable
                    |
                    v
              orders.created-dlt
                    |
                    v
            Investigate / fix issue
                    |
                    v
              Controlled replay
~~~

You can configure a DLT handler or DLT error-handling policy according to your version's API. A dedicated handler can record error metadata, emit alerts, or store an incident:

~~~java
public void handleDeadLetter(
        ConsumerRecord<String, OrderCreated> record) {

    incidentService.recordFailure(
            record.topic(),
            record.partition(),
            record.offset(),
            record.key()
    );
}
~~~

This is illustrative logic, not full DLT endpoint wiring. Register the DLT listener/handler properly with the framework and handle the case where the DLT handler itself throws an exception.

DLT operations should define access permissions, retention, sensitive-data handling, DLT backlog monitoring, resolution ownership, and replay procedures. Do not automatically bulk-replay before fixing the root cause.

## 13. @RetryableTopic and RetryTopicConfiguration

Two ways to configure the same feature set:

| Criterion | @RetryableTopic | RetryTopicConfiguration |
|---|---|---|
| Where defined | Annotation on listener | Spring bean using builder |
| Scope | Attached close to listener | Can apply policy to selected topics |
| Reusability | Simple for few listeners | Useful for centralized policies |
| Java config customization | Mainly via annotation attributes | Builds policies programmatically |
| Readability | Immediately visible on listener | Requires checking configuration beans |

Annotation example:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 2_000),
        dltTopicSuffix = "-dlt"
)
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-service"
)
public void onOrderCreated(OrderCreated event) {
    orderService.process(event);
}
~~~

Conceptually equivalent builder example:

~~~java
@Bean
RetryTopicConfiguration ordersRetry(
        KafkaTemplate<String, Object> kafkaTemplate) {

    return RetryTopicConfigurationBuilder.newInstance()
            .fixedBackOff(2_000L)
            .maxAttempts(4)
            .includeTopics("orders.created")
            .create(kafkaTemplate);
}
~~~

Do not accidentally declare both the annotation and a bean for the same endpoint without understanding configuration selection rules. Each listener should have one clearly owned retry policy.

## 14. Combining Blocking and Non-Blocking Retry

Sometimes you want to try a couple of immediate attempts using DefaultErrorHandler before moving a record to a retry topic for longer waits.

~~~text
Listener fails
       |
       +--> Blocking retry 1-2 times (short)
       |           |
       |           +--> Success
       |           |
       |           +--> Still failing
       |
       v
Publish retry topic (long wait)
       |
       v
Retry listener continues
       |
       +--> Success
       |
       +--> Attempts exhausted --> DLT
~~~

Combined configurations must account for the actual total number of executions. For instance, four non-blocking stages with two extra blocking retries per stage could execute business logic up to twelve times, depending on version and error handler configuration.

Do not treat maxAttempts(4) as the absolute ceiling of the whole pipeline if blocking retries have been added at each stage.

Also verify version limitations for non-blocking retry with batch listeners and container transactions. Do not assume every DefaultErrorHandler feature works alongside RetryTopicConfiguration without dedicated configuration.

## 15. Non-Blocking Retry, Transactions, and Idempotency

When forwarding a record from a source topic to a retry topic, publishing and committing the source offset may not be atomic without a shared transaction. Thus there is a failure window:

~~~text
Source listener fails
      |
      v
Publish retry record succeeds
      |
      v
Process stops before source offset commit
      |
      v
Source record is redelivered
      |
      v
Potential second retry record created
~~~

In many Spring Kafka versions, non-blocking retry does not directly support combining with container transactions; explicitly check compatibility before using KafkaTransactionManager on such listeners.

Whether using Kafka transactions or not, database transactions and external HTTP calls are not automatically rolled back by Kafka. A safe consumer should use a stable event ID and idempotent processing.

Example:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal amount
) {}
~~~

~~~java
@Transactional
public void process(OrderCreated event) {
    boolean firstDelivery =
            processedEventRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderRepository.applyOrderCreated(event);
}
~~~

insertIfAbsent represents an insert operation with a unique constraint on event_id. Recording the processed event and updating business data must be in the same database transaction.

Keep the same event ID across retry topics and during DLT replay. When calling a payment gateway or side-effecting API, use the target system's idempotency key and reconciliation if the prior call outcome is uncertain.

## 16. Retention and Resource Planning

Retry topics store records in Kafka. If retention is too short relative to total wait time and downtime, records can be deleted before the consumer gets a chance to retry.

When designing retention:

- Sum all backoff intervals across stages.
- Add buffer time for consumer downtime and deployments.
- Allow for backlogs when dependencies fail for hours.
- Control disk usage and broker quotas.
- Monitor oldest record age and consumer lag.
- Set DLT retention long enough for investigation, replay, and data retention requirements.

If retry topic retention is 10 minutes while total wait policy can span 30 minutes, records risk expiring before retries complete.

Auto-created topics also need sufficient partitions and replication factor. Avoid creating an unbounded number of topics whenever increasing attempts or adding new delays without measuring metadata and broker operational costs.

## 17. Multiple RetryTopicConfiguration Beans

A service may need separate policies for different topics.

~~~java
@Bean
RetryTopicConfiguration orderRetry(
        KafkaTemplate<String, Object> kafkaTemplate) {

    return RetryTopicConfigurationBuilder.newInstance()
            .fixedBackOff(2_000L)
            .maxAttempts(4)
            .includeTopics("orders.created")
            .create(kafkaTemplate);
}

@Bean
RetryTopicConfiguration emailRetry(
        KafkaTemplate<String, Object> kafkaTemplate) {

    return RetryTopicConfigurationBuilder.newInstance()
            .exponentialBackoff(5_000L, 2.0, 60_000L)
            .maxAttempts(6)
            .includeTopics("notifications.email")
            .create(kafkaTemplate);
}
~~~

Different topics have different SLAs and failure modes. For example, notifications can tolerate longer delays than order processing, while payments require strict idempotency.

Keep includeTopics scopes clear. If multiple configurations match the same listener, policy selection can become unpredictable; avoid overlap or verify precedence rules for your version.

## 18. Monitoring and Troubleshooting

Signals to track:

| Metric/signal | What you need to know |
|---|---|
| Retry topic ingress rate | Are many records failing at the source |
| Retry consumer lag | Is the retry flow keeping up with publish rate |
| Attempt count | How many executions records typically need |
| DLT publish rate | How many records are exhausting attempts |
| DLT oldest age/backlog | How long failed records have been sitting |
| Producer send errors | Are failures occurring when publishing to retry/DLT |
| End-to-end event latency | Total time to complete business processing |
| Rebalance count | Are retries disrupted by partition moves |
| Error count by class | Transient vs. permanent errors |
| Duplicate detection | How many redeliveries idempotency is rejecting |

Exact metric names depend on Kafka client, Spring Kafka, Micrometer, and exporters; some metrics must be explicitly recorded by the application.

Logs should include eventId, source topic, partition/offset, current retry topic, exception class, attempt, and recovery outcome. Avoid logging sensitive raw payloads or using eventId as a high-cardinality metric label.

### Common Errors

**Bean exists but no retry flow is created:** check infrastructure setup, includeTopics, bean registration, listener endpoints, and factories.

**Retry topic does not exist:** check topic creation policy, KafkaAdmin, naming, ACLs, and partition counts.

**Serializer error when forwarding:** check KafkaTemplate, payload types, raw byte[], and serializers.

**Miscounting attempts:** maxAttempts includes the first attempt on the source topic.

**Records processed out of order:** retry topics allow later source records to overtake failed records; use versioning/state checks or blocking retry.

**Invalid data retried repeatedly:** classify as non-retryable and route to DLT early.

**DLT has records but nothing handles them:** assign ownership, alerts, and a replay procedure.

**Retry backlog grows continuously:** check downstream dependency, topic consumer lag, retention, attempts, and total wait duration.

**Batch listener/transaction incompatibility:** check non-blocking retry limitations for the Spring Kafka version in use.

## 19. Process for Designing a Non-Blocking Retry Policy

1. Determine whether records can be processed independently or must preserve order.
2. Classify retryable and non-retryable exceptions.
3. Determine maxAttempts, including the initial attempt.
4. Choose fixed/exponential backoff based on dependency recovery time.
5. Create a RetryTopicConfiguration bean and scope includeTopics.
6. Enable retry infrastructure using the mechanism matching your version.
7. Select KafkaTemplate and serializers compatible with retry/DLT payloads.
8. Provision topics, partitions, replication, retention, and ACLs.
9. Design DLT handler, alerts, and replay procedure.
10. Keep event IDs stable and build idempotent consumers.
11. Measure lag, actual retry delay, DLT rate, and end-to-end latency.
12. Test broker outages, dependency 503s, restarts, and rebalances before broad rollout.

An easy-to-understand starter configuration for one topic:

~~~java
@Configuration
@EnableKafkaRetryTopic
public class RetryConfiguration {

    @Bean
    RetryTopicConfiguration ordersRetry(
            KafkaTemplate<String, Object> kafkaTemplate) {

        return RetryTopicConfigurationBuilder.newInstance()
                .fixedBackOff(3_000L)
                .maxAttempts(4)
                .includeTopics("orders.created")
                .create(kafkaTemplate);
    }
}
~~~

Simple listener:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-service"
)
public void onOrderCreated(OrderCreated event) {
    orderService.processIdempotently(event);
}
~~~

If processing succeeds, the event completes. If the listener throws a retryable error, Spring Kafka routes the record through the retry flow. Once attempts are exhausted, the record goes to the DLT or recovery according to configuration. Always verify topology, serializers, exception policy, and DLT handler in the real application.

RetryTopicConfiguration standardizes non-blocking retry policies in code: attempt counts, wait intervals, target topics, and failure forwarding paths. Operational design must add topic management, idempotency, ordering handling, and DLT monitoring so failed events are recovered or stored safely instead of turning into an unbounded backlog.

