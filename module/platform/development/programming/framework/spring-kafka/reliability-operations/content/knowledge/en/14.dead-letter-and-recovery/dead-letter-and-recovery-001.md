# Dead Letter Topic and Its Purpose

## 1. What is a Dead Letter Topic?

In Kafka, a consumer reads records from a topic and executes business logic. If a record causes the listener to fail, the system can retry. However, not every error can be resolved by retrying: the payload may be invalid, the schema may be incompatible, the data may violate business rules, or a dependency may suffer a prolonged outage.

A **Dead Letter Topic (DLT)** is a Kafka topic used to store records that cannot be processed in the main flow after applying the retry policy or error classification. This concept is sometimes called a **Dead Letter Queue (DLQ)**; in Kafka, the storage medium is still a topic.

For example, a consumer reads **orders.created**. Valid records are written to the database; records that repeatedly fail are sent to **orders.created.DLT** for the operations team to investigate and replay when safe.

~~~text
Order producer
      |
      v
orders.created
      |
      v
Spring Kafka @KafkaListener
      |
      +--> Processing succeeded --> DB / downstream
      |
      +--> Exception
                |
                v
        DefaultErrorHandler
                |
                v
           Retry + BackOff
                |
          +-----+-----+
          |           |
     Succeeded   Retries exhausted
          |           |
          v           v
      Continue   DeadLetterPublishingRecoverer
                      |
                      v
                orders.created.DLT
                      |
                      v
               Investigate / replay
~~~

A DLT **does not mean processing succeeded**. It indicates that the record has been isolated according to policy and is no longer processed normally in that attempt. The original business operation may still be awaiting completion.

## 2. Why does a system need a DLT?

### 2.1. Preventing a poison record from blocking progress

A **poison record** is a record that keeps failing across multiple processing attempts, such as an event missing a required field. If the consumer retries indefinitely, subsequent records may not be processed in time and consumer lag will grow.

A DLT allows isolating this record from the main flow so the consumer can proceed with other records when business policy permits. This improves resilience, though with a trade-off: the failed event has not yet been applied to business state.

### 2.2. Preserving data and failure causes for investigation

If you only ignore the exception or log a brief message, operators may not be able to recover the original event after logs rotate. A DLT can store the key, value, headers, and failure metadata to trace the root cause:

- Source topic, partition, and offset of the record.
- Timestamps when the event was created and processed.
- Exception class, message, and processing context.
- Event ID or correlation ID if permitted to be stored.
- Consumer group or processing service details.

Specific metadata depends on the Spring Kafka version and publisher configuration; you should not assume all headers are always present.

### 2.3. Decoupling online processing time from remediation time

A pipeline may require latency of a few hundred milliseconds, whereas fixing a data bug can take hours. A DLT allows isolating failed records so the operations team can resolve them outside the live path.

For example, a notification system can keep sending valid notifications while notifications with malformed templates are investigated separately.

### 2.4. Supporting controlled replay

After fixing the data, schema, consumer code, or dependency, DLT records can be replayed. Replay requires deciding the target destination, rate, ordering, and duplicate prevention. A DLT only stores data for recovery; it does not perform safe replay on its own.

## 3. How does a DLT differ from a retry topic?

| Criterion | Retry topic | Dead Letter Topic |
|---|---|---|
| Role | Wait to reprocess after a delay | Isolate records that did not complete per policy |
| Recoverability | Usually expected that the error may clear | Retries exhausted or error is considered terminal |
| Next step | Consumer retries processing | Investigation, fix, replay, or manual intervention |
| Data age | Follows retry schedule | Follows retention and operational procedures |
| Risks | Retry storm, latency, out-of-order delivery | Neglected backlog, replay errors, sensitive data |

With Spring Kafka, **DefaultErrorHandler** can perform retries in the listener container and then invoke a recoverer once retries are exhausted. **@RetryableTopic**, in supported cases, uses retry topics for non-blocking retries and can route records to a DLT.

The two mechanisms do not have to appear together. A consumer can have a DLT without a retry topic. You should not call every error topic a DLT if it is actually an intermediate hop in a retry workflow.

## 4. When should a record be moved to a DLT?

Typical cases:

| Error group | Example | Handling direction |
|---|---|---|
| Invalid data | Missing required field, invalid enum value | May skip long retries; recovery/DLT |
| Schema error | Consumer cannot decode payload version | Check compatibility; isolate or stop flow |
| Transient dependency | DB timeout, HTTP 503 | Bounded retries; DLT when exhausted |
| Consumer bug | NullPointerException after deployment | Alert and rollback/fix; DLT if appropriate |
| Terminal business error | Event violates invariant that cannot auto-heal | DLT or special handling workflow |
| Widespread infrastructure outage | Cluster or downstream is down | Consider pause/stop to avoid flooding DLT |

**Not every error should go to a DLT immediately.** For transient errors, a short retry may resolve the issue without intervention. For widespread outages affecting all events, sending every record to the DLT may merely move the backlog to another topic without making the system healthier.

For payments, accounting, ledgers, or workflows requiring strict ordering, skipping a record can leave business data inconsistent. In those cases, consider pausing the partition/listener or requiring approval rather than automatically moving on.

## 5. Related Spring Kafka components

| Component | Responsibility |
|---|---|
| **@KafkaListener** | Processes records and throws exceptions on failure |
| **ConcurrentKafkaListenerContainerFactory** | Creates listener containers and attaches error handlers |
| **DefaultErrorHandler** | Coordinates retries, backoff, seek/redelivery, and recovery |
| **FixedBackOff / ExponentialBackOff** | Defines wait intervals and retry limits |
| **DeadLetterPublishingRecoverer** | Builds the output record and publishes to the DLT |
| **KafkaTemplate** | Sends records to Kafka |
| **DLT topic** | Stores failed records and metadata |
| **DLT operator / consumer** | Investigates, remediates, and orchestrates replay |

A listener should let the error handler take responsibility for recovery unless the application intentionally designs a different workflow. If a listener catches an exception, logs it, and returns normally, the container may treat the record as processed and commit the offset; the DLT publisher will not be invoked.

## 6. Spring Boot and DefaultErrorHandler configuration

Example using a record listener with Spring Kafka managing offsets:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      ack-mode: batch
      concurrency: 3
~~~

**ack-mode=batch** determines the normal commit boundary after a poll, without requiring the listener to accept a list. Retries and recovery are coordinated by the error handler.

Example configuring a recoverer with a fixed BackOff:

~~~java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(dltTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory,
                    DefaultErrorHandler orderErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);

        return factory;
    }
}
~~~

**FixedBackOff(1_000L, 2L)** requests a wait interval of about one second between retries and up to two retry attempts after the initial attempt, according to FixedBackOff semantics.

The **ConsumerFactory**, KafkaTemplate, serializer/deserializer, and security beans must be configured accordingly. If the application already uses Spring Boot auto-configuration, you do not necessarily have to create a separate factory; ensure the handler is attached to the factory that actually creates the listener.

Example listener:

~~~java
@Service
public class OrderListener {

    private final FulfillmentService fulfillmentService;

    public OrderListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment",
        containerFactory = "orderListenerContainerFactory"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.processIdempotently(event);
    }
}
~~~

When **processIdempotently** throws an exception, the container passes the error to DefaultErrorHandler. Once retries are exhausted according to policy, the recoverer can publish the record to the DLT.

### 6.1. Exception classification

You should not retry an invalid payload multiple times just to reach the retry limit. You can configure non-retryable exceptions:

~~~java
var handler = new DefaultErrorHandler(
    recoverer,
    new FixedBackOff(1_000L, 3L)
);

handler.addNotRetryableExceptions(InvalidOrderException.class);
~~~

Only classify an exception as non-retryable when the error truly cannot recover by retrying. Business exceptions sometimes wrap a transient timeout as a cause; check the exception structure that the handler receives.

## 7. DLT topic name and partition

With the default destination resolver, **DeadLetterPublishingRecoverer** normally sends records from the source topic to a topic with the **.DLT** suffix and preserves the source partition.

Example:

~~~text
Source record:
  topic     = orders.created
  partition = 2
  offset    = 1452

Destination topic:
  topic     = orders.created.DLT
  partition = 2
~~~

This is behavior of the recoverer, not an automatic broker feature. Kafka does not automatically route records just because a topic named **.DLT** exists.

If the recoverer tries to publish to partition 7 of the DLT, the DLT topic must have at least eight partitions. Therefore, with the default mapping, the DLT partition count usually needs to be at least equal to the source topic's partition count.

### 7.1. Changing the destination with a destination resolver

You can use a fixed DLT topic and let the producer choose the destination partition:

~~~java
@Bean
DeadLetterPublishingRecoverer dltRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) ->
            new TopicPartition("fulfillment.failures.DLT", -1)
    );
}
~~~

A negative partition in **TopicPartition** tells the recoverer not to require a fixed destination partition. In that case, do not assume the DLT partition reflects the original partition. Preserve source metadata in headers to support replay.

A separate DLT per source topic is usually easier for managing ACLs, schemas, retention, and metrics. A shared DLT across multiple topics can suit centralized operations, but it must handle multiple payload types and data access controls.

## 8. Creating the DLT topic

A DLT is a normal Kafka topic with a replication factor, retention, cleanup policy, and ACLs.

Example provisioning with Spring Kafka when the application has KafkaAdmin/appropriate permissions:

~~~java
@Bean
NewTopic ordersCreatedDlt() {
    return TopicBuilder
        .name("orders.created.DLT")
        .partitions(6)
        .replicas(3)
        .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
        .build();
}
~~~

This example sets six partitions, a replication factor of three, and seven-day retention. These are illustrative values, not universal defaults. The source topic must have a compatible partition count if using same-partition mapping.

In production, topic creation usually belongs to IaC or a separate administrative pipeline rather than granting broad CREATE permissions to the application runtime.

### 8.1. Retention and durability

DLT retention must be long enough to detect, investigate, and replay records before Kafka deletes data per policy. If it is too short, records may disappear before being handled. If it is too long, storage and the scope of retaining sensitive data increase.

Choose retention based on incident response time, audit requirements, error data volume, and data policies. A DLT is not automatically an indefinite audit archive.

Because a DLT record may be the copy needed for recovery, choose replication factor, min.insync.replicas, and producer acks appropriate to the criticality of the data.

## 9. Metadata in DLT records

DeadLetterPublishingRecoverer can preserve the original key/value, the source record's headers, and add headers describing the exception.

Commonly useful information:

- Source topic, partition, offset, and timestamp.
- Exception class and message.
- Exception stack trace information per configuration.
- Correlation ID or event ID if present in the source.
- Consumer group or other source fields when supported by the version.

Logical example:

~~~text
DLT topic = orders.created.DLT
Key       = order-102
Value     = OrderCreated{eventId=evt-102,...}

Source topic     = orders.created
Source partition = 2
Source offset    = 1452
Error class      = InvalidOrderException
Error message    = missing shippingAddress
~~~

The descriptive field names shown here are not mandatory header constant names. When writing Java code to read headers, use the **KafkaHeaders** constants or appropriate APIs for your actual Spring Kafka version.

Do not use exception messages as a stable protocol for retry/replay because error text can change across versions. If automated classification is needed, use explicitly versioned business error codes.

### 9.1. Securing headers

Exceptions and payloads may contain emails, addresses, personal data, or accidentally logged secrets. The DLT must have READ/WRITE permissions, retention, and masking controls equal to or stricter than the source topic.

## 10. Deserialization errors and the DLT serializer

Two error categories must be distinguished:

1. The listener received a valid Java object and then failed during processing.
2. The Kafka consumer could not deserialize the record, so the listener was never called.

In the second case, the listener cannot throw a business error for a payload it never saw. **ErrorHandlingDeserializer** is commonly used so Spring Kafka can pass deserialization error details to error handling.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
~~~

When deserialization fails, the recoverer may need to publish the original raw bytes to the DLT. The KafkaTemplate used for the DLT must have serializers that handle the actual key/value types. A **JsonSerializer** meant only for business objects is not necessarily suitable for malformed raw bytes.

You may need **DelegatingByTypeSerializer** or multiple KafkaTemplates for different key/value types. Verify the actual data types the recoverer receives when an error occurs before the listener.

## 11. Recovery and offset commit

A record moved to the DLT is considered **recovered** under the handler policy, which does not mean the original business operation succeeded.

After recovery succeeds, the container can advance the offset to continue processing subsequent records. Specific behavior depends on:

- AckMode and the listener container's commit state.
- The error handler's **ackAfterHandle** setting.
- The **commitRecovered** option under supported conditions, typically related to MANUAL_IMMEDIATE.
- Whether the recovery publisher confirms success or throws an exception.
- Whether the container is transactional or non-transactional.

You should not assume every Spring Kafka application always commits offsets immediately after DLT publish; inspect the effective configuration.

### 11.1. DLT publish failure is a reliability failure

For example, the DLT producer lacks WRITE permission. If the recoverer fails to send and the application still commits the source offset, the record risks neither being retried in the main flow nor existing in the DLT.

Therefore:

1. Verify the DLT topic exists.
2. Verify the principal has WRITE permission.
3. Configure compatible serializers.
4. Observe publish outcomes and recoverer errors.
5. Do not swallow recovery exceptions or assume publish succeeded.

### 11.2. Kafka transactions do not roll back the DB

Kafka transactions can coordinate Kafka outputs and input offsets in supported flows. They do not automatically create a distributed transaction with a database or HTTP service.

If a consumer has already written to the DB and crashes before committing the offset, the record may be redelivered. A DLT does not undo side effects that already exist outside Kafka.

## 12. DLT for batch listeners

With a batch listener, one bad record can cause the entire batch to fail. If the listener knows the exact index of the failing record, it can throw **BatchListenerFailedException** with the zero-based index so DefaultErrorHandler processes records before and after the failure per policy.

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "orderBatchContainerFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int i = 0; i < records.size(); i++) {
        try {
            fulfillmentService.process(records.get(i).value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                "Order processing failed",
                ex,
                i
            );
        }
    }
}
~~~

If you only throw a regular exception without identifying the failing element, fallback batch retry may retry the whole batch. Records that already produced side effects may be invoked again, so idempotency remains necessary.

**Non-blocking retries via @RetryableTopic** do not support batch listeners in common Spring Kafka versions that provide this retry-topic mechanism; if per-record retry topics are needed, consider a record listener or a different design.

## 13. Replaying from the DLT

Replay is not simply reading every DLT record and sending it back to the source topic. It is a business operation that requires control.

Recommended workflow:

1. Identify why the record entered the DLT.
2. Confirm the bug, schema, payload, or downstream issue has been fixed.
3. Check whether the event is still valid given the current business state.
4. Check whether partial side effects may already have been created.
5. Choose the replay destination: source topic, recovery topic, or a dedicated handler service.
6. Set replay rate limits and handle ordering.
7. Record the replay attempt, actor, timestamp, and outcome.
8. Use a stable idempotency key to prevent duplicate effects.
9. Monitor errors and do not create an infinite automatic replay loop.

### 13.1. Replaying to the source topic

If replayed to the source topic, the record is appended with a new offset. An older event may appear **after newer events**, altering the business processing sequence even though records within the partition preserve log order.

In addition, every other consumer group reading this topic may receive the replayed event. Therefore, assess the blast radius of replay, especially for payments, notifications, or multi-service workflows.

### 13.2. Dedicated recovery consumer

A dedicated DLT consumer can inspect business state and then apply remediation logic. This approach avoids re-broadcasting events to every downstream consumer of the source topic, though you still must manage offsets, retries, access permissions, and idempotent side effects.

### 13.3. Avoiding replay loops

~~~text
DLT -> replay -> source topic -> error -> DLT -> replay ...
~~~

Without an attempt limit or a step to fix the root cause, the loop can repeat continuously. You need terminal states, replay history, alerts, and a manual intervention process.

## 14. Idempotency during retry and replay

An event sent to the DLT is not guaranteed to have had zero impact on target systems. The consumer may succeed in writing to the database and then fail on a subsequent API call or crash before committing the offset.

~~~text
Consume OrderCreated
       |
       v
DB commit succeeded
       |
       v
Crash before Kafka offset commit
       |
       v
Record re-delivered / replayed
       |
       v
Risk of creating a second fulfillment
~~~

One safeguard is using a stable event ID and an inbox table:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

The side effect and the event ID insert should happen in the same DB transaction. A unique constraint protects against race conditions if two attempts process the same event. Merely checking **existsById** before inserting is insufficient under concurrent execution.

For external APIs, use an idempotency key provided by the dependency or a reconciliation mechanism. A Kafka transaction cannot roll back an HTTP request already accepted by an external system.

## 15. DLT and business ordering

Kafka guarantees ordering within each partition, but when a record is moved to the DLT, the main consumer may continue processing subsequent records depending on policy.

~~~text
orders.created - partition 1

offset 100: OrderCreated(order-1) --> error, sent to DLT
offset 101: OrderPaid(order-1)    --> continues processing
~~~

If OrderPaid depends on OrderCreated having been applied, log order is preserved but business completion order is no longer correct.

Before adopting a DLT, determine:

- Should a subsequent event be processed if the preceding event fails?
- Is it necessary to pause the partition or stop the listener on critical errors?
- Do events for the same entity share a stable partition key?
- How does replaying an older event affect current state?
- Should a "pending manual recovery" state be recorded in the DB?

A DLT helps isolate failures but does not automatically preserve business dependencies across events.

## 16. Observability and alerting

A DLT without an owner, metrics, and handling process becomes a dumping ground for failed records.

| Metric | Operational question |
|---|---|
| DLT ingress rate | How many new records are entering the DLT? |
| Recovery publish failures | Are any DLT publish attempts failing? |
| Oldest unresolved age | How old is the oldest unresolved record? |
| Exception distribution | Which errors dominate? |
| Retry-to-DLT ratio | How many retries end up in recovery? |
| Replay attempts/success | How have replays been attempted and completed? |
| Consumer lag by partition | Is the main flow congested? |
| DLT storage/retention | Is there a risk of running out of disk or retention expiring? |

**The number of records currently in the DLT does not equal the number of unresolved records.** Successfully replayed records remain in Kafka until deleted by retention. If you need an exact unresolved backlog, track processing state separately by event ID or source topic/partition/offset.

A DLT log entry might contain:

~~~text
service=order-fulfillment
eventId=evt-102
sourceTopic=orders.created
sourcePartition=2
sourceOffset=1452
dltTopic=orders.created.DLT
exceptionClass=InvalidOrderException
recovery=published
~~~

Avoid using event ID, offset, or order ID as high-cardinality metric labels. They belong in logs/traces with appropriate controls for sensitive data.

### 16.1. When DLT ingress spikes

If records entering the DLT spike after a deployment, check the consumer version, schema, and downstream dependencies before concluding source data is corrupted. For widespread failures, consider rolling back or pausing the consumer rather than pushing all traffic into the DLT.

If the recoverer fails to publish to the DLT, trigger a high-severity alert because that is a failure in the consumer's last line of defense.

## 17. Access control and security

A DLT is a Kafka topic with its own ACLs:

| Component | Permissions to verify |
|---|---|
| Source consumer | READ source topic, READ consumer group |
| DLT producer/recoverer | WRITE on DLT |
| DLT consumer/operator | READ DLT and READ corresponding group |
| Replay producer | WRITE target topic |
| Topic provisioning | CREATE or administrative permissions per process |

An application may use a separate KafkaTemplate for the DLT with credentials different from the business producer. On a **TopicAuthorizationException**, identify the actual principal used by the recoverer.

DLT payloads and exception messages may contain personal data or stack traces. Grant least-privilege access, manage retention, and audit replay operations.

## 18. End-to-end example: Order Fulfillment

Suppose Order Service publishes **OrderCreated** to **orders.created**. Consumer Fulfillment Service writes shipping requests to the DB, idempotently by event ID.

Policy:

- DB timeout: retry twice, one second apart.
- InvalidOrderException: do not retry long, route to recovery.
- Retries exhausted: send to **orders.created.DLT**.
- Operator classifies the failure, fixes the root cause, and runs a controlled replay.

Listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "orderListenerContainerFactory"
)
public void handle(OrderCreated event) {
    fulfillmentService.processIdempotently(event);
}
~~~

Error handler:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(dltTemplate);
    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );
    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
~~~

When a record has an invalid shipping address, it can be published to the DLT early per policy. When the database experiences prolonged downtime, valid records may enter the DLT after failed retries.

If many events flood into the DLT at once, investigate the outage instead of continuously running replay. If an event already wrote the fulfillment before crashing, replay must recognize the processed event ID to avoid creating two shipping requests.

## 19. Common mistakes

**Assuming Kafka creates DLTs automatically.** Kafka does not move records on its own; the application needs a recoverer or publisher and a properly provisioned topic.

**Assuming entering the DLT means processing succeeded.** A DLT only isolates the failed record; the business operation may still be incomplete.

**Forgetting the partition count.** The default recoverer normally preserves the source partition; a DLT with too few partitions can cause publish failures.

**Forgetting serializers for deserialization errors.** The DLT producer may have to send raw bytes instead of business objects.

**Swallowing exceptions in the listener.** The container may commit the offset without knowing an error occurred to send to the DLT.

**Not checking DLT publish errors.** Failed recovery can leave a record stuck or lost if commit policy is misconfigured.

**Treating total records in the topic as unresolved backlog.** Processed records stay until retention deletes them.

**Replaying unconditionally.** This can cause duplicates, out-of-order business state, or a DLT loop.

**Assuming Kafka transactions roll back the database.** Side effects outside Kafka need separate idempotency/outbox/inbox mechanisms.

**Assigning no owner for remediation.** An unmonitored DLT provides no real recovery capability.

## 20. Implementation and operations checklist

1. Classify errors into retryable, terminal, and flow-stopping errors.
2. Configure DefaultErrorHandler, BackOff, and DeadLetterPublishingRecoverer.
3. Define the DLT name, partition mapping, retention, and replication.
4. Verify the KafkaTemplate and serializers actually used to publish to the DLT.
5. Grant the recoverer's principal the proper WRITE ACL on the DLT.
6. Define the offset commit policy after recovery success or failure.
7. Preserve necessary source and exception metadata without leaking secrets.
8. Design idempotency for side effects across retries and replays.
9. Set alerts for DLT ingress spikes, recovery failures, and unresolved age.
10. Establish an owner, runbook, replay approval, and replay rate limits.
11. Test validation errors, dependency timeouts, DLT publish failures, and crashes before commit.
12. Evaluate business ordering when failed records are separated from the main flow.

## 21. Key takeaways

A **Dead Letter Topic** is where records that a consumer cannot complete under its retry/recovery policy are isolated. In Spring Kafka, **DefaultErrorHandler** coordinates **BackOff** and **DeadLetterPublishingRecoverer** to publish records to the DLT.

A DLT helps prevent poison records from blocking the flow where continuation is acceptable, retains diagnostic information, and supports controlled replay. It does not by itself guarantee exactly-once processing, preserve business ordering, confirm side-effect completion, or replace idempotency.

A reliable DLT design must have **appropriate retention, ACLs, observability, alerts, an owner, a runbook, and a safe replay process**.
