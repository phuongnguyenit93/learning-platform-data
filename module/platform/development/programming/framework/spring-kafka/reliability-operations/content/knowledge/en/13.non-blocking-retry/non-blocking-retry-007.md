# DeadLetterPublishingRecoverer for Retry Topics

In Spring Kafka, **non-blocking retry** forwards a failed record from the main topic to one or more retry topics to attempt processing after a configured delay. When a record has exhausted its retry attempts and still fails, the system can route it to a **dead-letter topic (DLT)**. `DeadLetterPublishingRecoverer` is a key component of this flow: it builds and publishes the record to the next topic when the listener fails and a forwarding step is required.

The name `DeadLetterPublishingRecoverer` easily leads learners to think this component only sends records to a DLT. In reality, within the retry-topic mechanism, Spring Kafka uses the recoverer together with a destination resolver to route records to **either a retry topic or a DLT**, depending on delivery attempt, exception, retry policy, and record state. Computing retry timing, creating retry endpoints, and deciding the route belong to Spring Kafka's retry-topic infrastructure; the recoverer executes the corresponding publish step.

## 1. Where the Recoverer Sits in the Non-Blocking Retry Flow

Suppose a consumer reads `OrderCreated` events from topic `orders`. The system allows four total attempts, consisting of the initial attempt on the main topic and three attempts on retry topics.

```text
               orders (main topic)
                       |
                   listener
                       |
                     error
                       v
              DeadLetterPublishingRecoverer
                       |
                       v
              orders-retry (stage 1)
                       |
                 retry listener
                       |
                     error
                       v
              DeadLetterPublishingRecoverer
                       |
                       v
              orders-retry (stage 2)
                       |
                 retry listener
                       |
                     error
                       v
              DeadLetterPublishingRecoverer
                       |
                       v
              orders-retry (stage 3)
                       |
                 retry listener
                       |
                 still failing
                       v
              DeadLetterPublishingRecoverer
                       |
                       v
                   orders-dlt
```

The diagram shows **logical steps**, without guaranteeing actual retry topic names. Spring Kafka can name topics with suffixes by delay, by attempt index, or reuse one topic depending on `SameIntervalTopicReuseStrategy` and version configuration. Check actual topics in operation.

When a processing step succeeds, the record does not need to be forwarded to the next destination. When a step fails, the retry-topic infrastructure determines the destination and invokes the recoverer to publish. Once forwarding is considered successful per configuration, the source topic consumer can complete progress for the source record; another consumer will read the published record from the destination topic.

## 2. Distinguishing Two Uses of DeadLetterPublishingRecoverer

`DeadLetterPublishingRecoverer` is also commonly used directly with `DefaultErrorHandler` for blocking retry:

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

DefaultErrorHandler errorHandler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
);
```

In that case, the handler retries in place according to `FixedBackOff`; once retries are exhausted, the recoverer sends the record to the destination it determines, usually the DLT. This is a configuration for container **blocking retry**.

In non-blocking retry via `@RetryableTopic`, Spring Kafka creates the forwarding infrastructure and corresponding recoverer. The destination changes by attempt and retry-topic policy. You normally do not need to manually instantiate a `DefaultErrorHandler` containing `DeadLetterPublishingRecoverer` to enable this flow.

| Aspect | Blocking retry with `DefaultErrorHandler` | Non-blocking retry with retry topics |
|---|---|---|
| Where is the record retried? | Inside the current topic's consumer processing flow. | On a retry topic's consumer after the record is published there. |
| What decides wait time? | Error handler's `BackOff`, e.g. `FixedBackOff`. | Retry-topic configuration and the retry consumer's processing schedule. |
| When does recoverer publish? | Typically after blocking retries are exhausted and recovery is needed. | Whenever the record must be forwarded to the next retry topic or DLT. |
| When does DLT receive the record? | Per the handler's recovery policy. | When attempts are exhausted, exception is non-retryable, or resolver picks DLT. |
| Ordering impact? | Can hold the partition waiting on the failed record. | Other records can continue, so business ordering can change. |

Choose the mechanism matching your wait durations and ordering requirements. Using `@RetryableTopic` does not mean you have configured extra blocking retries; the two layers can be combined in supported versions, but attempt counts and error policies for each layer must be calculated separately.

## 3. @RetryableTopic Example and Forwarding Flow

A listener declaring retry topics via annotation:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0),
    retryTopicSuffix = "-retry",
    dltTopicSuffix = "-dlt",
    kafkaTemplate = "retryKafkaTemplate",
    autoCreateTopics = "false"
)
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

With this configuration, the maximum total processing attempts under retry-topic is four: one attempt on `orders` and up to three additional attempts. Expected wait intervals are generated from 1,000 ms and multiplier 2.0. Actual delivery timing depends on the scheduler, load, and consumer polling activity.

`autoCreateTopics = "false"` means the main, retry, and DLT topics must be pre-created with the defined names, partition counts, and retention policies. If you want the framework to auto-create topics, you must configure permissions and corresponding attributes; that does not replace topic governance in production.

In the example above, the `retryKafkaTemplate` bean is the producer template used to forward records. The producer needs serializers compatible with keys, values, and payload types that may need forwarding to retry/DLT. If an appropriate default template already exists, you can point `kafkaTemplate` to that bean name rather than creating an extra template.

Example of a `KafkaTemplate` bean using an existing producer factory in the application:

```java
@Bean("retryKafkaTemplate")
KafkaTemplate<Object, Object> retryKafkaTemplate(
        ProducerFactory<Object, Object> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

The producer factory here must be defined by the application or provided by Spring Boot with appropriate serializer settings. In real applications, if only one payload type is received and republished, generics can be narrower; when handling deserialization failures, values sent to the DLT are sometimes `byte[]`, requiring a serializer capable of handling that type.

## 4. What Decides Which Retry Topic a Record Goes To?

Do not hard-code destinations inside business callbacks. The non-blocking retry infrastructure manages routing via Spring Kafka components, including `DestinationTopicResolver` and the factory creating `DeadLetterPublishingRecoverer`. Destination choice depends on:

- The source topic where the record is currently being processed.
- Attempt info and retry timestamp stored with the record.
- Maximum attempts, backoff, and retry topic reuse configuration.
- Whether the exception type is retryable or must go straight to the DLT.
- Policy on whether to create a DLT and how DLT errors are handled.

When a record fails on the main topic, the recoverer configured by retry-topic infrastructure publishes the record to the appropriate retry topic. When the retry consumer fails again, the same mechanism forwards the record to the next destination. After the final attempt, the destination is typically the DLT.

If the exception is classified as non-retryable, the record can go straight to the DLT after the first failure. Therefore, `attempts = "4"` is an upper bound for an allowed retry chain, not a guarantee that every failing record will undergo four listener invocations.

## 5. How Are Retry Metadata and Headers Preserved?

A record moving from topic to topic must retain enough metadata for the retry infrastructure to know when to try next and for operations to trace back to the original record. `DeadLetterPublishingRecoverer` can add headers related to the exception and source record; the retry-topic infrastructure also manages headers specific to attempts and timestamps.

Commonly useful information includes:

| Information group | Purpose |
|---|---|
| Original topic, partition, offset | Locate the original record during investigation and reconcile committed offsets. |
| Exception class, message, stack trace | Understand why the listener failed and why the record was forwarded. |
| Attempt / retry timestamp | Determine attempt count and when the record is due for reprocessing. |
| Key and correlation/event ID | Correlate deliveries belonging to the same business action. |
| Custom headers | Preserve tracing, tenant, or business routing data where permitted. |

For records routed to the DLT, standard headers such as `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET`, `KafkaHeaders.DLT_EXCEPTION_FQCN`, and `KafkaHeaders.DLT_EXCEPTION_MESSAGE` can be read when provided by the infrastructure. Exact headers, whether original or latest headers are kept, and header repetition depend on Spring Kafka version and recoverer configuration.

Do not assume a record's offset in a retry topic equals its offset in the main topic. Each topic-partition has its own offset sequence. An event that has moved across three topics can have three different offsets. To trace across publishes, use a durable event ID in the payload or headers combined with original record metadata.

Exception and stack trace headers can grow quite large; as a record passes through multiple retries, control header accumulation to avoid unexpectedly bloating message size. Also apply sensitive-data protection policies before writing exception messages or stack traces to the DLT.

## 6. Configuring a DLT Handler for Retry Topics

After retries are exhausted, the record is published to the DLT for a dedicated listener to process. You can declare `@DltHandler` alongside the `@RetryableTopic` listener:

```java
@DltHandler
public void onDeadLetter(ConsumerRecord<String, OrderCreated> record) {
    log.error(
        "Order sent to DLT: topic={}, partition={}, offset={}, key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );

    incidentService.recordFailure(record.key(), record.value());
}
```

`@DltHandler` processes the record **after** it has been published to the DLT. It does not perform publishing to the DLT and is not the same callback as `DeadLetterPublishingRecoverer`. If the application persists failed events to a database, logic inside the DLT handler must be idempotent because the DLT consumer itself can receive redeliveries.

When no DLT handler is provided, Spring Kafka applies default behaviors according to the retry-topic mechanism and configured DLT strategy. Do not assume a record has been inspected or handled just because it entered the DLT. In production, have a DLT consumer or management workflow, notifications, and replay guidelines.

For example, a DLT containing undeserializable payloads needs a matching listener and serializer/deserializer. Do not force every DLT record into type `OrderCreated` if the DLT can receive failed records from the deserialization step.

## 7. Customizing the DeadLetterPublishingRecoverer Created by Retry-Topic

When using `@RetryableTopic`, the retry-topic infrastructure creates the needed recoverer and error handlers. If you need to change shared recoverer behavior—such as checking publish results, adding headers, or setting timeouts—Spring Kafka provides extension points on `RetryTopicConfigurationSupport` in supported versions.

Illustrative example of customizing the recoverer:

```java
@Configuration
public class RetryTopicInfrastructure extends RetryTopicConfigurationSupport {

    @Override
    protected void configureCustomizers(CustomizersConfigurer customizers) {
        customizers.customizeDeadLetterPublishingRecoverer(recoverer -> {
            recoverer.setFailIfSendResultIsError(true);
            recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));
        });
    }
}
```

In this configuration, if the methods and callbacks are supported by your Spring Kafka version, the recoverer is instructed to detect send errors returned from the producer future and bound how long it waits for the result. This is especially important because publishing to retry/DLT is the handoff boundary for progress between two topics.

`RetryTopicConfigurationSupport` is infrastructure configuration; do not create multiple subclasses and do not combine it with `@EnableKafkaRetryTopic` if your version requires choosing only one configuration style. Verify the signatures of `configureCustomizers`, `setFailIfSendResultIsError`, and `setWaitForSendResultTimeout` against your project's API version before applying the example.

Do not replace the standard destination resolver with custom logic solely to change topic suffixes. Retry/DLT names, backoff, attempts, and exception classification already have configuration options on `@RetryableTopic` or `RetryTopicConfigurationBuilder`. Only customize the recoverer when you need to change publish behavior or metadata at a level not covered by those settings.

## 8. Why Must Publish Failures Be Handled Carefully?

A dangerous point in the retry-topic flow is that a record may fail on the source topic yet **fail to publish successfully** to the next topic. If the container still marks the source record as recovered and commits the source offset prematurely, the record risks disappearing from business processing.

Consider the scenario:

1. The listener reads an event at `orders-0`, offset `100`, and throws an exception.
2. The recoverer prepares to send the event to the retry topic.
3. The producer hits a broker error or authentication error, so publishing fails.
4. If the publish failure is ignored, the source consumer may advance the offset past `100` without a copy of the event in the retry topic.

Therefore, ensure send failures are detected and surfaced as recovery failures when necessary. Related measures include configuring the producer with `acks=all`, appropriate idempotent producer settings, sensible retries/request timeouts, and waiting for/checking the recoverer's publish result. At the same time, monitor publish-failure logs, retry/DLT publish latency, and source topic committed offsets.

A recoverer reporting publish success does not by itself create an atomic transaction between source offset commit and target topic publish in every configuration. Nor does non-blocking retry automatically grant exactly-once semantics to external effects like database writes or payment API calls. Design idempotency and analyze crash windows between publish, acknowledgment, and commit.

## 9. Distinguishing Listener Failures, Publish Failures, and DLT Handler Failures

Three failure types occur at three different stages:

| Failure type | Where does it happen? | Operational meaning |
|---|---|---|
| Listener failure | Listener on main topic or retry topic throws an exception. | Framework must choose next retry topic, DLT, or skip retry per classifier. |
| Recoverer publishing failure | Sending the record to the retry topic or DLT fails. | Record handoff cannot be considered complete; a recovery failure policy is required. |
| DLT handler failure | Listener consuming the DLT throws an exception. | Record entered the DLT, but DLT processing is incomplete; retry behavior depends on `DltStrategy` and configuration. |

Do not lump all errors into a single `listener_error` metric. Maintain separate metrics for initial processing errors, retry counts, retry publish errors, DLT publish errors, DLT consumer errors, and queue depth on each retry topic.

If the DLT handler fails, the DLT error strategy may allow retrying, stop retrying, or omit creating a DLT depending on configuration. Because retry topics can use separate group IDs and consumers, monitor the groups and lag of all related topics. Dropping lag on the main topic does not mean all business work is complete.

## 10. Exception Classification and Retry Exhaustion

Some exceptions are transient, such as a target service returning 503 or a database timeout. Others almost certainly will not resolve by retrying the same payload, such as invalid business schema or an invalid value.

With retry-topic, you can declare non-retryable exceptions on the annotation:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2_000),
    exclude = {InvalidOrderException.class, UnsupportedCurrencyException.class}
)
@KafkaListener(topics = "orders")
public void consume(OrderCreated event) {
    orderService.process(event);
}
```

If an error falls into the `exclude` group per classifier policy, the record does not continue through the entire retry chain and can be routed to the DLT early. Thus, actual attempts can be fewer than `attempts`.

Similarly, a record may succeed on the second attempt; it then does not proceed to the next retry topic or DLT. A successful execution does not emit new records just to finish the retry chain.

Define the boundary between "recoverable errors" and "errors needing investigation" from business semantics rather than retrying every exception. Repeatedly retrying an invalid payload increases cost and delays valid records.

## 11. Serializers, Partitions, and Target Topic Prerequisites

For the recoverer to publish successfully, it needs a producer with write permissions, serializers matching the data types, and valid target topics. Situations to watch for:

- **Topic does not exist:** if auto-create is disabled, all retry topics and the DLT must be created beforehand or during deployment. Topic names must match Spring Kafka's naming policy.
- **Insufficient partitions:** if the recoverer publishes to a selected partition that does not exist on the destination, the producer can fail. Verify partition counts on retry topics and the DLT.
- **Incompatible serializer:** if values are POJOs on the happy path yet `byte[]` on deserialization errors, a serializer fixed to a POJO may not handle both types. Consider `DelegatingByTypeSerializer` or templates suited per value type.
- **Insufficient ACLs:** a consumer group having read access on the main topic does not mean the producer template has write access on retry topics and the DLT.
- **Oversized payload/headers:** multiple retries, exception headers, and stack traces can inflate message size, causing publish failures against broker/producer limits.
- **Schema evolution:** retry/DLT topics may retain records longer than the main topic; serializers and consumers must consider schema compatibility for older events.

These issues typically manifest as `SerializationException`, timeouts, authorization failures, unknown topic/partition errors, or publish futures completing exceptionally. During investigation, record the chosen destination, source topic/partition, event ID, exception class, and publish outcome.

## 12. Processing Order and Retry Topic Limitations

Non-blocking retry lets the main topic consumer keep processing other records while a failed record waits in a retry topic. That improves throughput at the cost of ordering effects.

Example of events for the same order on the main partition:

```text
orders-0:  event A -> event B -> event C

event A fails -> forwarded to retry topic
event B succeeds on main topic
event C succeeds on main topic
event A is reprocessed later
```

If business rules require A to finish before B and C, retry topics can break that assumption. Having the same key does not guarantee business order once a record moves to another topic. Consider blocking retry, per-aggregate processing with version checks, or transitioning business state through an ordered workflow.

Spring Kafka's non-blocking retry also has version-specific compatibility limits. Common versions design it for record listeners and do not support batch listeners in the same way; integration with Kafka transactions has limitations. Always check documentation for your exact Spring Kafka version before enabling retry topics on batch listeners or containers with a transaction manager.

## 13. DLT Operations and Replay Procedures

The DLT holds records that could not be processed within allowed attempts. The DLT does not fix data itself and does not guarantee anyone is watching it. An operational procedure must answer:

1. Which team receives alerts when new records enter the DLT?
2. Who determines whether it is a data bug, code bug, or dependency failure?
3. Can the record be reprocessed as-is, or must data/state be repaired first?
4. Replay to the main topic, a special topic, or a manual workflow?
5. How to prevent duplicate business side effects on replay?
6. How to track which records were replayed and whether they succeeded or failed?

Example metadata to store in an error-tracking system:

```text
event_id=order-7835-created
original_topic=orders
original_partition=2
original_offset=18403
current_topic=orders-dlt
exception=PaymentGatewayUnavailableException
last_attempt_time=2026-11-15T14:30:00Z
replay_status=PENDING_REVIEW
```

This is illustrative data; real timestamps, topics, IDs, and exceptions come from records and logs. Do not rely on the DLT offset to infer the original record's offset.

When replaying, a record can traverse the exact same retry-topic chain if it keeps its original configuration. Build replay limits, alerts for repeated failures, and idempotency keys—otherwise a bad record can create a long loop across the DLT and retry workflow.

## 14. Observing the Recoverer in Production

Signals to collect per topic, consumer group, and destination:

| Signal | Interpretation |
|---|---|
| Records published to retry topics | Error rate requiring retries at each step of the chain. |
| Records published to DLT | Records unresolved within the attempt budget. |
| Recoverer publish failure rate | Risk of failing to transfer records between topics. |
| Publish latency | Broker/producer or network may be slow. |
| Retry-topic consumer lag | Failed records waiting for reprocessing; cannot look only at main topic lag. |
| DLT consumer lag | Records not yet observed or processed by the DLT workflow. |
| Delivery attempt distribution | Shows whether errors usually recover quickly or span many attempts. |
| Rebalance count and commit errors | Can affect record redeliveries. |

In logs, prioritize `eventId`, `originalTopic`, `originalPartition`, `originalOffset`, `currentTopic`, `destinationTopic`, `attempt`, and `exceptionType`. With tracing, carry correlation IDs across publishes, while controlling header volume and keeping secrets out of logs.

Never judge system health solely by `orders` having zero lag. The main consumer may have forwarded many failed records to retry topics or the DLT, making main topic lag 0 while business processing is still failing. Build dashboards reflecting all three stages: main processing, retry, and DLT.

## 15. Common Incidents and Investigation Approaches

| Symptom | Possible cause | Investigation direction |
|---|---|---|
| Listener fails yet retry topic receives no records | Recoverer publish failed, wrong target topic, or exception classified non-retryable. | Check publish logs, destination, topic naming, serializers, and classifier. |
| Record jumps straight to DLT | Exception excluded from retry, attempts exhausted, or backoff/destination policy picks DLT. | Check `exclude`, attempt count, retry metadata, and exception chain. |
| DLT receives records yet handler does not process them | DLT listener not running, wrong group ID, deserialization error, or DLT handler failing. | Check assignments, DLT group lag, and listener logs. |
| Main consumer has zero lag yet work is unfinished | Records were forwarded to retry topics/DLT. | Check lag and pending record counts in retry/DLT. |
| Publish to retry/DLT fails | Serializer, ACLs, timeout, topic/partition, or message size. | Check producer futures, exceptions, broker, and destination config. |
| Record processed twice | Crash between business operation and commit, or multiple retry/replay cycles. | Use event ID, idempotency keys, unique constraints, and history reconciliation. |
| Business order inverted | Failed record split off to retry topic while later records continued. | Evaluate ordering requirements and suitable retry architecture. |
| Headers or payload grow after retries | Stack trace/exception metadata accumulated. | Control header retention, payload size, and recoverer settings. |

## 16. Safe Rollout Process

When introducing `DeadLetterPublishingRecoverer` in a non-blocking retry system, follow this sequence:

1. Define max attempts, backoff schedule, and retryable exception types.
2. Name retry topics and DLT, pre-creating topics with proper partition counts, retention, and ACLs.
3. Configure `@RetryableTopic` or `RetryTopicConfigurationBuilder` with a producer template having the right serializers.
4. Define and implement a DLT handler or DLT operational procedure.
5. Configure recoverer publish-error detection using your Spring Kafka version's API.
6. Ensure the consumer treats handoff as complete only after the recoverer succeeds per chosen policy.
7. Design idempotent business logic and evaluate processing-order impact.
8. Monitor retry-topic lag, DLT ingress, publish failures, delivery attempts, and consumer errors post-deployment.
9. Prepare controlled investigation and replay procedures for records in the DLT.

`DeadLetterPublishingRecoverer` is the record-handoff link in Spring Kafka's non-blocking retry mechanism. By understanding that the recoverer can publish to both retry topics and the DLT, configuring producers and destinations properly, handling publish failures, and operating the DLT cleanly, applications can retry transient failures while retaining traceability and recoverability for unprocessable records.
