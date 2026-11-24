# Destination Resolver

In Spring Kafka, a **destination resolver** is the mechanism that determines the **destination topic and partition** when a record cannot be processed successfully and needs to be moved to a **dead-letter topic (DLT)** or another recovery topic. With **DeadLetterPublishingRecoverer**, the application can provide a function that takes the original **ConsumerRecord** and the associated **Exception**, and returns the destination **TopicPartition**. This function enables flexible routing by source topic, error type, or controlled business rules.

This is an important extension point in Spring Kafka's **Dead letter and recovery** model. The resolver only **selects the destination**. It does not decide the retry count, publish the record itself, commit offsets, or turn a failed record into a successful business operation. Those responsibilities are coordinated by **DefaultErrorHandler**, the recoverer, **KafkaTemplate**, the listener container, and the active acknowledgement/transaction policy.

## 1. From listener failure to destination resolver

A typical processing flow:

1. The consumer reads a record from the source topic.
2. The listener executes business logic.
3. If the listener throws an exception, the container delegates the error to the error handler.
4. The error handler applies retries and BackOff as configured.
5. If the error is non-retryable or retries are exhausted, the error handler invokes **DeadLetterPublishingRecoverer**.
6. The recoverer asks the destination resolver which topic/partition the record should be sent to.
7. The recoverer builds the producer record, attaches appropriate recovery headers, and uses KafkaTemplate to publish to the destination.
8. Once recovery is considered complete, the container handles offset progress according to the current AckMode and policy.

~~~mermaid
flowchart TD
    A["Kafka source topic"] --> B["Consumer and @KafkaListener"]
    B --> C{"Processing succeeded?"}
    C -->|Yes| D["Ack/commit per container"]
    C -->|No| E["DefaultErrorHandler"]
    E --> F{"Retries left and retryable?"}
    F -->|Yes| G["BackOff then redeliver record"]
    G --> B
    F -->|No| H["DeadLetterPublishingRecoverer"]
    H --> I["Destination resolver"]
    I --> J["Select destination TopicPartition"]
    J --> K["KafkaTemplate sends recovery record"]
    K --> L{"Publish/recovery succeeded?"}
    L -->|Yes| M["Container handles offset per policy"]
    L -->|No| N["Recovery failure: continue error handling"]
~~~

Key distinction: **the destination resolver does not process the failed data**. It decides where to send the data. Successfully sending to the DLT and handling the record in the DLT are two separate activities.

## 2. Core API of the destination resolver

A commonly used constructor of **DeadLetterPublishingRecoverer** accepts a KafkaTemplate and a **BiFunction**:

~~~java
DeadLetterPublishingRecoverer(
    KafkaTemplate<?, ?> template,
    BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition>
        destinationResolver
)
~~~

The idea of the function:

~~~java
(record, exception) -> {
    String destinationTopic = ...;
    int destinationPartition = ...;

    return new TopicPartition(
        destinationTopic,
        destinationPartition
    );
}
~~~

Three key inputs and outputs:

| Component | Role |
|---|---|
| **ConsumerRecord<?, ?> record** | Provides source topic, partition, offset, key, value, headers, and timestamp |
| **Exception exception** | Describes the failure requiring recovery; may be a wrapper containing the root cause |
| **TopicPartition** | Specifies the destination topic name and partition, or instructs the producer to pick the partition |

The name **TopicPartition** sometimes misleads newcomers into thinking it describes the source partition. In this context, the returned object must describe the **destination to publish to**, not the position the consumer is reading from.

The destination resolver runs on the recovery path after the attempts managed by the error handler. This function should execute quickly, make pure routing decisions, and avoid business side effects.

## 3. Default behavior of DeadLetterPublishingRecoverer

When no custom destination resolver is provided, DeadLetterPublishingRecoverer normally routes the record to a topic named **source topic + ".DLT"**, with the same partition number as the source record.

Example:

| Source record | Default destination |
|---|---|
| orders.events, partition 0, offset 102 | orders.events.DLT, partition 0 |
| orders.events, partition 2, offset 533 | orders.events.DLT, partition 2 |
| payments.events, partition 1, offset 89 | payments.events.DLT, partition 1 |

Minimal configuration:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(kafkaTemplate);
}
~~~

With same-partition mapping like this, the DLT topic must exist and have enough partitions to accommodate the highest partition index sent to it. If the source topic has six partitions and the DLT only has three, records from partitions 3, 4, or 5 may fail to send to the corresponding partition.

When using a different naming scheme, splitting DLTs by error category, or letting the Kafka producer choose the destination partition, supply a custom resolver.

## 4. Complete example: configuring a custom destination resolver

Suppose the system wants to separate invalid-data errors into a dedicated validation DLT topic, while processing errors that exhaust retries go into a general processing DLT.

~~~java
import java.util.function.BiFunction;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

@Configuration
public class DeadLetterRoutingConfiguration {

    @Bean
    DeadLetterPublishingRecoverer deadLetterRecoverer(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition>
                destinationResolver = (record, exception) -> {

            String topic;

            if (causedBy(
                    exception,
                    IllegalArgumentException.class)) {
                topic = "orders.events.validation.DLT";
            } else {
                topic = "orders.events.processing.DLT";
            }

            // Specify a partition with the same index as the source partition.
            return new TopicPartition(
                    topic,
                    record.partition()
            );
        };

        return new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                destinationResolver
        );
    }

    private static boolean causedBy(
            Throwable failure,
            Class<? extends Throwable> type) {

        for (Throwable current = failure;
             current != null;
             current = current.getCause()) {

            if (type.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
~~~

The example assumes the listener is processing the topic orders.events; if the factory is shared across multiple topics, hard-coding DLT names like this may not fit. A reusable resolver should derive from record.topic() or an explicit mapping table per source topic.

From the code above:

- **IllegalArgumentException** in the cause chain is routed to the validation DLT topic.
- Other errors after exhausting retries are routed to the processing DLT.
- The destination partition keeps the same index as the source partition.
- The producer needs WRITE permission on both topics.
- Both DLTs must have enough partitions to accept indices from the source topic.

The example uses IllegalArgumentException to illustrate classification. In a real application, use meaningful business exceptions such as InvalidOrderPayloadException rather than assuming every IllegalArgumentException represents permanently bad data.

## 5. Attaching the recoverer to DefaultErrorHandler

The destination resolver is only used when DeadLetterPublishingRecoverer is invoked. For listener containers not using Kafka transactions, you can attach the recoverer to **DefaultErrorHandler**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            DeadLetterPublishingRecoverer deadLetterRecoverer) {

        var handler = new DefaultErrorHandler(
                deadLetterRecoverer,
                new FixedBackOff(1_000L, 2L)
        );

        handler.addNotRetryableExceptions(
                InvalidOrderPayloadException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);

        return factory;
    }
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
    id = "orderEventsListener",
    topics = "orders.events",
    groupId = "order-processor",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderEvent event) {
    orderProcessingService.process(event);
}
~~~

In the example, FixedBackOff(1_000L, 2L) sets a one-second pause and up to two retry attempts after the initial processing attempt, if the error is considered retryable. For InvalidOrderPayloadException declared as non-retryable, the error handler can proceed to recovery sooner.

**The destination resolver does not decide which errors are retryable.** Routing by exception after retries are exhausted and classifying exceptions before retrying are two related but separate decisions. Align both policies to prevent permanent data errors from going through unnecessary retries.

The business classes OrderEvent and InvalidOrderPayloadException are examples and must be defined in the application.

## 6. Designing routing rules

A resolver can inspect various signals, but the rules must be predictable and easily verifiable.

| Signal | Illustrative rule | Notes |
|---|---|---|
| Source topic | orders.events → orders.events.DLT | Easy to reuse across multiple source topics |
| Exception type | Validation error → validation.DLT | Inspect cause chain; avoid classifying by message text |
| Validated header | Route by permitted business domain | Do not use arbitrary headers as topic names |
| Mapped tenant | Tenant A → DLT A | Use an allowlist; bound topic and partition counts |
| Consumer group | Each consumer workflow has its own DLT | Group ID must be obtained reliably |
| Source partition | Keep partition index in DLT | DLT needs enough partitions |
| Operational policy | Security error → security DLT | Do not create ad-hoc topics on unknown exceptions |

Prefer explicit, bounded, version-controlled routing policies. Do not construct topic names by directly concatenating exception messages, arbitrary tenant IDs, or unvalidated payload values. Those values can contain invalid characters, cause topic explosion, or leak sensitive data into resource names.

### Example mapping by source topic

~~~java
BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
        (record, exception) -> {

    String sourceTopic = record.topic();

    String targetTopic = switch (sourceTopic) {
        case "orders.events"   -> "orders.events.DLT";
        case "payments.events" -> "payments.events.DLT";
        default                -> "shared-recovery.DLT";
    };

    return new TopicPartition(
            targetTopic,
            record.partition()
    );
};
~~~

With shared-recovery.DLT, that topic must have enough partitions for every source if keeping the partition index. If keeping the partition is not required, you can let the producer choose the partition.

## 7. Destination partition: keep the original or let Kafka choose?

The second element of the returned TopicPartition controls how the destination partition is set on the producer record.

### 7.1 Keeping the partition index

~~~java
return new TopicPartition(
        record.topic() + ".DLT",
        record.partition()
);
~~~

Advantages:

- Failed records can be located by the partition index corresponding to the original topic.
- Simple to implement as the default mapping.
- Can assist incident analysis per source partition.

Mandatory condition: the destination topic must have a partition with the specified index. A DLT topic does not automatically expand its partitions just because the resolver returns a higher index.

Keeping the same partition index does not mean the record in the DLT has the same offset as the source record. The DLT offset is assigned by Kafka when the record is appended to the destination log.

### 7.2 Letting the producer choose the partition

If the resolver returns a **negative partition**, DeadLetterPublishingRecoverer can build the producer record without specifying an explicit destination partition, letting the Kafka producer choose the partition based on its partitioner, key, and producer configuration.

~~~java
return new TopicPartition(
        "shared-recovery.DLT",
        -1
);
~~~

This option is useful when multiple source topics have different partition counts and all feed into a single shared DLT. Then you do not have to guarantee the shared DLT has every partition index of the source topics.

However:

- The destination partition may differ from the source partition.
- You cannot infer the source partition from the destination partition.
- You must use DLT headers or business metadata for tracing.
- If keys are unstable or producer partitioning changes, records may land in different partitions.

Verify how negative partitions are handled in your running Spring Kafka version and test that records publish successfully. Do not treat a negative value as a valid Kafka partition; it is a signal for the recoverer **not to specify** a partition on the producer record.

### 7.3 Quick comparison

| Policy | When suitable | Trade-offs |
|---|---|---|
| Keep original partition | Per-topic DLT, compatible partition counts | Must provision enough partitions |
| Producer picks partition | Shared DLT, multiple source topics | Does not preserve partition mapping by index |
| Custom partition mapping | Routing by business/tenant | More complex to operate and test |

## 8. Exception wrappers and cause chains

Errors thrown in a listener are often wrapped by Spring Kafka in another exception, such as ListenerExecutionFailedException. If you only check exception.getClass() at the outer layer, the resolver may route all errors into the fallback branch.

Inspect the cause chain or translate errors into an intentional business exception at the service boundary.

Example helper function:

~~~java
static boolean containsCause(
        Throwable failure,
        Class<? extends Throwable> expected) {

    java.util.Set<Throwable> visited =
            java.util.Collections.newSetFromMap(
                    new java.util.IdentityHashMap<>()
            );

    for (Throwable cursor = failure;
         cursor != null && visited.add(cursor);
         cursor = cursor.getCause()) {

        if (expected.isInstance(cursor)) {
            return true;
        }
    }

    return false;
}
~~~

Using a visited set prevents infinite loops if an unusual cause chain has a cycle. Cause-chain classification still requires care because generic exceptions like IllegalArgumentException can appear deep inside serialization or mapping errors without carrying the same business meaning.

Do not parse exception.getMessage() text as the sole source for choosing a DLT. Message text can change across versions, locales, or drivers, or contain sensitive data.

## 9. Mapping by tenant and business domain

Some multi-tenant systems want recovery records for specific customer groups handled by dedicated teams or given different retention. You can select the DLT by tenant, but you must use an allowlist.

Example:

~~~java
private static final Map<String, String> TENANT_DLT_TOPICS =
        Map.of(
            "tenant-a", "orders.tenant-a.DLT",
            "tenant-b", "orders.tenant-b.DLT"
        );

static TopicPartition resolveByTenant(
        ConsumerRecord<?, ?> record) {

    var header = record.headers().lastHeader("tenant-id");

    String tenant = header == null
            ? ""
            : new String(
                    header.value(),
                    StandardCharsets.UTF_8
            );

    String topic = TENANT_DLT_TOPICS.getOrDefault(
            tenant,
            "orders.quarantine.DLT"
    );

    return new TopicPartition(topic, -1);
}
~~~

This example demonstrates header reading, not tenant authentication. Before routing by tenant, the system must ensure that header was created by a trusted producer or validated at the ingress boundary.

Do not concatenate raw header values directly into topic names, such as creating thousands of unbounded per-ID topics. Routing unknown tenants to a quarantine DLT and emitting an alert metric is safer than auto-creating new topics.

If multiple tenants share a DLT, retain full source metadata and control read access to avoid cross-tenant data exposure.

## 10. DLT headers and traceability

DeadLetterPublishingRecoverer normally adds metadata describing the original record and the failure leading to recovery into the headers of the DLT record. Fields may include:

- Original topic.
- Original partition.
- Original offset.
- Original timestamp and timestamp type.
- Original consumer group when available.
- Exception class.
- Exception cause, message, and stack trace info as appropriate.

Specific constant names are provided by Spring Kafka via **KafkaHeaders** and can vary across versions. When writing code to read headers, use the constants/APIs from your actual dependency rather than hard-coding guessed header names.

Example DLT record:

~~~text
DLT destination topic: orders.events.validation.DLT
DLT partition: 2
DLT offset: 9801

Original topic: orders.events
Original partition: 2
Original offset: 445
Exception: InvalidOrderPayloadException
Event ID: evt-2f84
~~~

The DLT offset is the new offset in the destination topic. It does not replace the original offset. For replay and investigation, combine DLT metadata and the business event ID.

If exception messages or stack traces contain PII or secrets, control retention, ACLs, and log exporting. Do not let everyone with DLT read access automatically receive all sensitive data beyond what they need.

## 11. Should a resolver create topics or call external services?

It should not.

The resolver is invoked on the consumer's error-handling path. If it has to call a database, a remote configuration service, or a synchronous API, recovery itself can hang, time out, or fail when dependencies are degraded.

Practical rules:

- Routing maps should be prepared upfront from validated configuration.
- Rules can inspect record metadata and the cause chain directly in memory.
- Do not create topics inside the callback.
- Do not make HTTP calls to fetch a DLT name per record.
- Do not mutate business databases inside the resolver.
- Do not delete, alter payloads, or mark records processed inside the resolver.
- Do not introduce side effects solely for metrics; logs/metrics should be recorded at points aligned with recovery outcomes.

If routing policies must change frequently, load configuration from a trusted source ahead of time, validate it, and refresh an immutable snapshot via an operational workflow. Never depend on a runtime request to a config service for each failure.

## 12. Retry policy and destination routing are two separate layers

Some errors should not be retried, while others should be retried before hitting the DLT. That decision belongs to the error handler, not the resolver.

~~~text
Listener exception
    |
    v
Error handler: retryable?
    |
    +-- Yes and attempts remain --> retry/backoff
    |
    +-- No or exhausted
             |
             v
     DeadLetterPublishingRecoverer
             |
             v
     Destination resolver --> DLT topic/partition
~~~

Example:

| Exception | Retry policy | Destination after recovery |
|---|---|---|
| InvalidOrderPayloadException | No retry | validation DLT |
| DatabaseDeadlockException | Bounded retry | processing DLT if retries exhausted |
| DownstreamTimeoutException | Retry with backoff | dependency DLT if retries exhausted |
| AuthorizationException | Investigate config | security/operations DLT per policy |
| SerializationException | May require special recovery | quarantine DLT with suitable serializer |

Do not send a transient network error straight to the DLT just because the resolver recognizes a related exception. The resolver only runs once the error handler decides recovery is required. DLT routing must align with how the error handler classifies errors.

## 13. DLT producer and serializers

DeadLetterPublishingRecoverer uses KafkaTemplate to send records to the chosen destination. The producer needs serialization compatible with the key/value being recovered.

Typically, if the listener consumes String keys and JSON payloads, the recoverer can use a KafkaTemplate compatible with those serializers:

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

This is an example producer configuration; the application also needs bootstrap servers, security, and a producer factory.

In the case of a **deserialization failure**, the listener may never receive a valid Java object. When using ErrorHandlingDeserializer, the recoverer may need to publish the original byte array value. A plain JsonSerializer may not work for that.

Spring Kafka supports configuring the recoverer with multiple KafkaTemplates or mapping serializers by data type in certain versions. Choose KafkaOperations/producer serializers compatible with both deserialized objects and raw bytes if your system needs a DLT for deserialization errors.

If the producer cannot serialize the record, the destination resolver may still select the right topic, yet publishing will still fail. Therefore, monitor **routing decisions** and **recovery publish outcomes** separately.

## 14. Security and permissions on destinations

A resolver can route to multiple topics. The producer must have WRITE permission on **all** destinations allowed by policy.

Example:

- orders.events.validation.DLT.
- orders.events.processing.DLT.
- orders.quarantine.DLT.

Permissions to review:

| Component | Required permissions |
|---|---|
| Source topic consumer | READ on source topic and consumer group permission |
| DLT producer | WRITE on DLT topics |
| DLT consumer | READ on DLT and consumer group permission |
| Admin/provisioning | CREATE/ALTER if assigned topic management |
| Transactional producer, if used | Transactional ID and cluster permissions per configuration |

If WRITE ACL is missing, Kafka may throw TopicAuthorizationException. Do not change the resolver to route to a different topic with broader permissions just to hide the error. Grant least-privilege permissions on the proper destination via governance workflows.

Never derive DLT topic names from unverified data, as that could also cause the application to accidentally send sensitive records to a topic readable by another principal.

## 15. Ensuring the destination topic has enough partitions

This is the most common operational mistake when customizing a destination resolver.

Suppose the source topic has partitions 0 through 7, while the DLT topic only has partitions 0 through 3. The following resolver will fail for records from partitions 4, 5, 6, or 7:

~~~java
return new TopicPartition(
        "shared-recovery.DLT",
        record.partition()
);
~~~

Pick one of two approaches:

1. Create the DLT topic with a compatible partition count and verify it whenever expanding source partitions.
2. Return a negative partition so the Kafka producer picks the destination partition if the system accepts not preserving partition mapping.

Do not use arbitrary modulo math to remap partitions without evaluating key ordering, traceability, and data distribution. If custom partition mapping is required, document the policy and test every source partition.

When increasing the partition count of a source topic, review every DLT destination that preserves the index. Increasing source partitions does not automatically add partitions to the DLT.

## 16. Recovery success and offset commit

A common misconception is that once the destination resolver returns a TopicPartition, the failed record is done. In reality, there are multiple steps:

1. The resolver computes the destination.
2. The recoverer creates the ProducerRecord and sends it.
3. The producer may succeed or fail.
4. The error handler determines whether recovery succeeded.
5. The container handles the offset according to acknowledgement/recovery configuration.

**Do not commit the offset early simply because the resolver selected a topic.**

With DefaultErrorHandler and a non-transactional container, settings like AckMode and whether the handler reports recovery affect how the container advances offsets. With certain manual acknowledgement configurations, properties like **commitRecovered** and ack handling apply under specific conditions. Do not infer that every mode commits immediately when the recoverer returns.

If using Kafka transactions, inspect AfterRollbackProcessor and how offsets are sent into the transaction. Transactional recovery has different semantics from standard listener containers.

### Controlling publish failures

DeadLetterPublishingRecoverer has options in modern Spring Kafka versions to wait on and evaluate send results, such as **setFailIfSendResultIsError(true)**. When you need to avoid marking recovery successful if the Kafka send fails, check and configure appropriate send-result observation.

Example API on supported versions:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                resolver
        );

recoverer.setFailIfSendResultIsError(true);
~~~

How send results are awaited and their timeouts can be configured further depending on version. Check the real semantics of KafkaTemplate and the recoverer: if sending is asynchronous and the application treats a record as recovered before knowing the result, records risk being lost in failure windows.

## 17. When the recoverer itself fails

A recovery failure can occur even if the listener exception was classified properly. Examples:

- Destination topic does not exist yet.
- Specified partition is invalid.
- KafkaTemplate lacks a compatible serializer.
- Producer lacks WRITE ACL.
- Broker is unresponsive or quota is exceeded.
- Resolver function throws an exception due to malformed data/headers.
- Topic was renamed but application config was not updated.
- DLT publish fails due to producer transaction/fencing.

When the recoverer fails, the error handler can retain the record for reprocessing per its recovery failure policy. Depending on configuration, retry state or backoff may be reset and the record redelivered. Check your version and options like **resetStateOnRecoveryFailure** when writing runbooks.

Do not catch the recoverer's exception and swallow it in a wrapper so the container thinks the record recovered. That can advance the offset while the record was never stored in any durable destination.

## 18. Logging and metrics for routing

To operate a custom resolver, operations teams need to see **why a record was sent to a specific destination**.

Example structured log:

~~~text
event=dlt_routing
service=order-processor
listener_id=orderEventsListener
source_topic=orders.events
source_partition=2
source_offset=445
exception_class=InvalidOrderPayloadException
destination_topic=orders.events.validation.DLT
destination_partition=2
event_id=evt-2f84
~~~

This is a format example, not an automatic framework log.

Metrics:

| Metric | Meaning |
|---|---|
| Recovery attempts | Number of times the system tried to publish a recovery record |
| Recovery success/failure | Outcome of the publisher/recoverer |
| DLT ingress rate | Rate of records arriving at each DLT |
| DLT backlog/lag | Number of records not yet processed by the DLT consumer |
| DLT oldest record age | Age of the oldest remaining failed record |
| Router fallback count | Number of records hitting the fallback branch |
| Unknown topic/tenant count | Detects sources outside policy |
| Serialization errors | Detects inability to publish recovery records |
| Partition routing errors | Destination missing partitions or invalid mapping |

Metric tags should have low cardinality, such as source topic, destination topic, exception group, and environment. Do not use event ID, offset, customer ID, or exception message as tags, as they can create excessive time series.

Include event ID/offset in logs or traces if security policy permits. Do not log full payloads, tokens, passwords, or stack traces containing sensitive data to uncontrolled systems.

## 19. DLT consumers and the remediation workflow

The destination resolver decides where failed records go. The system must also decide who handles them there.

A practical recovery workflow includes:

1. The record enters the DLT topic with source and exception metadata.
2. A DLT consumer or operations system records the failure.
3. The responsible team analyzes whether the cause is data, configuration, or a dependency.
4. Fix the root cause.
5. Check whether partial side effects already occurred.
6. Run a controlled replay with a stable event ID.
7. Confirm the source listener succeeds or the state is resolved.
8. Monitor backlog and prevent DLT loops.

Do not configure a DLT consumer to read records and immediately send them back to the source topic indefinitely. If the root cause is not fixed, the system can create a loop: source topic → DLT → source topic → DLT, multiplying load and duplicating events.

If each error category has its own DLT, assign an explicit owner, retention, and handling procedure to each DLT. Splitting into too many DLTs can complicate operations without improving resilience.

## 20. Destination resolver vs. @RetryableTopic: not the same concept

Spring Kafka also provides **non-blocking retry** using **@RetryableTopic**. That infrastructure manages a topology of source topic, retry topics, and DLT through its own retry-topic configuration and destination resolution components.

Distinguish them clearly:

| Mechanism | Purpose |
|---|---|
| **DeadLetterPublishingRecoverer destination resolver** | Selects a TopicPartition when a recoverer needs to publish a failed record |
| **@RetryableTopic retry destination logic** | Selects the next stage/topic based on attempt, delay, exception classification, and DLT policy |
| **DefaultErrorHandler** | Handles blocking retries, BackOff, and invokes the recoverer when needed |
| **@DltHandler** | Processes records that arrive at the DLT in a retry-topic topology |

Do not assume a custom BiFunction on the main listener's DeadLetterPublishingRecoverer controls the entire topology created by @RetryableTopic. The two configuration paths can differ depending on framework version and listener factory.

If the application uses @RetryableTopic, inspect the retry-topic infrastructure's mechanisms for creating retry/DLT topics, suffixes, attempts, backoff, and custom destination configuration. Do not use standard recoverer APIs expecting to replace retry-stage logic managed by the framework.

## 21. Batch listeners and exception metadata

With a batch listener, a single invocation can process multiple ConsumerRecords. When an error occurs, the error handler may treat batches differently from record listeners.

If the batch listener identifies the failing record via **BatchListenerFailedException**, the error handler can pinpoint the record to recover. If the error is not tied to a specific record, recovery may apply more broadly depending on API and policy.

DeadLetterPublishingRecoverer's destination resolver still receives a specific ConsumerRecord when the recoverer handles that record. However, do not infer from this that every batch error automatically identifies the failing record.

Test:

- Listener throws an exception before processing any record.
- Listener succeeds on part of a batch and then fails.
- Whether the error handler knows the index of the failing record.
- Which records are sent to the DLT.
- Which offsets are committed or sought again.
- Whether side effects of already-processed records are idempotent.

When requirements call for fine-grained per-record recovery, a record listener is usually simpler for failure ownership. Batch listeners require dedicated offset and retry semantics design.

## 22. Kafka transactions and database transactions

A destination resolver does not provide atomicity between a database and Kafka. If the listener updates a database and then emits another event, moving a failed record to the DLT does not automatically roll back or commit the database.

With a transactional listener container, the error path may go through **AfterRollbackProcessor** instead of a standard DefaultErrorHandler. Attach the recoverer to the appropriate post-rollback component and understand how offsets are enlisted in the transaction.

Principles:

- Do not swallow exceptions in the listener when a rollback is needed.
- Let the database transaction finish/roll back before reprocessing the record.
- If recovery publishing succeeds before the source offset commits, redelivery can occur.
- Use event IDs and inbox/idempotency to prevent duplicate side effects.
- Use the outbox pattern if database updates must be coordinated with event publishing.
- Never claim exactly-once semantics for external APIs or databases solely because Kafka transactions are enabled.

The destination resolver still only selects the topic and partition. Transaction semantics belong to other components.

## 23. Testing a destination resolver

You can test the routing function independently of a Kafka broker to verify that input records and exceptions yield the expected TopicPartition. Then integration tests are needed to verify KafkaTemplate, topic partition counts, ACLs, and send results.

### Unit testing the mapping

Example helper:

~~~java
static TopicPartition resolve(
        ConsumerRecord<?, ?> record,
        Exception failure) {

    if (containsCause(
            failure,
            InvalidOrderPayloadException.class)) {
        return new TopicPartition(
                "orders.validation.DLT",
                record.partition()
        );
    }

    return new TopicPartition(
            "orders.processing.DLT",
            record.partition()
    );
}
~~~

In the test, build a dummy ConsumerRecord for orders.events partition 3 offset 27, pass a validation exception, and assert it returns orders.validation.DLT partition 3. With another exception, verify the processing DLT.

Cases to cover:

| Test case | Expected result |
|---|---|
| Direct validation error | Routes to validation DLT |
| Wrapped validation error | Still routes accurately via cause chain |
| Transient error exhausting retries | Routes to processing DLT |
| Unconfigured source topic | Routes to bounded quarantine/fallback |
| Invalid tenant header | Does not create arbitrary topic names |
| Source partition exceeds DLT partitions | Publish failure is detected or another mapping is used |
| Destination partition = -1 | Producer chooses partition |
| DLT topic does not exist | Recovery failure is logged/metered |
| Kafka producer lacks WRITE ACL | TopicAuthorizationException is observed |
| Serialization failure | Recovery is not marked succeeded |
| Publish timeout | Not marked recovered without result per policy |

### Integration testing with Kafka

Use EmbeddedKafka or Testcontainers appropriate for your application version. Illustrative flow:

1. Create the source topic and DLT topics.
2. Configure a listener that always throws InvalidOrderPayloadException for a test event.
3. Configure DefaultErrorHandler with the custom-resolver recoverer.
4. Send a record to a known partition.
5. Wait until the error handler invokes the recoverer.
6. Read from the expected DLT with an independent test consumer.
7. Verify key/value, destination topic, partition, and source headers.
8. Verify the record does not appear in other DLT branches.
9. Induce a DLT publish error and observe the error handler's recovery failure.
10. Verify offset/replay behavior under the active AckMode.

Do not just mock the BiFunction and declare recovery successful. Unit tests prove the routing rules; integration tests prove end-to-end publishing and recovery.

## 24. Runbook when a record lands in the wrong DLT

When discovering a failed record in the wrong DLT:

1. Identify the listener ID, consumer group, source topic/partition/offset, and event ID.
2. Collect the original exception and full cause chain.
3. Check whether DefaultErrorHandler exhausted retries or treated the exception as non-retryable.
4. Verify which DeadLetterPublishingRecoverer bean the listener container actually uses.
5. Read the active resolver policy: source topic, exception, tenant mapping, and fallback.
6. Verify the returned TopicPartition and actual DLT topic.
7. Check DLT partition count, topic existence, and producer WRITE ACL.
8. Cross-check serialization, KafkaTemplate, and publish results.
9. Inspect headers containing original topic/partition/offset.
10. If using @RetryableTopic, confirm whether it is the retry-topic topology or a standard recoverer.
11. Fix the routing policy or topology through change management.
12. Decide how to handle records already in the old DLT; do not automatically delete data.
13. Run controlled replay, monitoring duplicates and side effects.
14. Update tests to prevent routing regressions.

If a record does not appear in any DLT at all, prioritize investigating recoverer publish failures and offset commit state before concluding the resolver picked the wrong destination.

## 25. Common implementation mistakes

**Confusing the destination resolver with a retry classifier.** The resolver picks the destination when recovery is needed; the error handler decides whether to retry.

**Not inspecting the cause chain.** Spring Kafka can wrap the original exception, causing the resolver to route everything to fallback.

**Keeping the original partition when the DLT has fewer partitions.** The Kafka producer cannot publish to a non-existent partition index.

**Constructing topic names directly from headers or exception messages.** This can cause topic explosion, invalid resource names, or sensitive data leaks.

**Only testing that the resolver function returns the expected value.** Publishing can still fail due to ACLs, serializers, partitions, or broker timeouts.

**Treating DLT publishing as business success.** It is only a recovery path; domain processing may remain incomplete.

**Not verifying send results.** If publish fails yet the handler still treats it as recovered, records risk disappearing after offset commit.

**Lacking idempotency.** DLT publishing and source offset commits have failure windows; records can be redelivered or sent to the DLT multiple times.

**Sharing a DLT without preserving original metadata.** Operations teams cannot identify the source and replay accurately.

**Making synchronous network/database calls inside the resolver.** When dependencies fail, the recovery path is blocked too.

**Too many destinations without owners.** More fragmented routing requires separate retention, ACLs, dashboards, and runbooks.

**Changing routing policy without draining old backlogs.** Records in previous DLTs still need to be consumed and recovered.

## 26. Operational checklist

**Routing policy**

- [ ] Destination topics/partitions are defined for each error group requiring separation.
- [ ] The resolver has an explicit fallback for unexpected exceptions or topics.
- [ ] The cause chain is analyzed under stable rules.
- [ ] Headers and tenants are validated before participating in routing.
- [ ] No arbitrary topic names are constructed from untrusted data.

**Kafka infrastructure**

- [ ] All destination topics exist and have suitable retention.
- [ ] DLT topics have enough partitions if preserving original partitions.
- [ ] The producer has WRITE on all valid DLTs.
- [ ] KafkaTemplate/serializers handle the keys/values needing recovery.
- [ ] Publish failures and partition routing failures are monitored.

**Recovery semantics**

- [ ] DefaultErrorHandler or AfterRollbackProcessor uses the correct recoverer.
- [ ] Retry policy is separated from routing policy.
- [ ] Offset/ack policy only treats a record as recovered when recovery meets designed criteria.
- [ ] Idempotency and a DLT replay procedure are in place.
- [ ] Recovery failures are never swallowed and marked successful.

**Observability and testing**

- [ ] Logs include source and destination topic/partition, offset, and event ID.
- [ ] Metric tags have low cardinality.
- [ ] Unit tests cover exception/topic/tenant mappings.
- [ ] Integration tests cover DLT publishing and producer failures.
- [ ] Runbooks exist for DLT backlogs, misrouting, and missing producer ACLs.

## 27. Design principles

A **destination resolver** for DeadLetterPublishingRecoverer is a routing function from **ConsumerRecord + Exception** to a **destination TopicPartition**. Its strength lies in directing each category of failure to a recovery destination with a clear owner and policy. By default, you can keep the DLT on the same partition as the source topic; with a shared DLT, you can let the producer pick the partition if configuration allows.

Keep the resolver simple, deterministic over finite outcomes, and free of side effects; provision topics/ACLs/serializers completely; verify DLT publish outcomes; and cleanly separate retry classification, routing, offset commits, and replay logic. With logs, metrics, tests, and runbooks covering both the success path and recovery failures, the destination resolver becomes a reliable pillar of Spring Kafka operations rather than a blind spot where failed records go missing.
