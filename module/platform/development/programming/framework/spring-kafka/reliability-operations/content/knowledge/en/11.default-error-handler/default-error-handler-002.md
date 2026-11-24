# Configuring CommonErrorHandler

In Spring Kafka, the listener container manages listener invocation, exception handling, and deciding whether a record will be retried, recovered, or sent to a dead-letter topic (DLT). Since Spring Kafka 2.8, shared error handling for both record listeners and batch listeners has been standardized through the **CommonErrorHandler** interface. By configuring a handler on the container, an application can control retries, exception classification, record recovery, and error logging under a consistent policy.

**DefaultErrorHandler** is the most commonly used implementation. It supports backoff, bounded retries, recoverers, retryable/non-retryable error classification, and attempt-observation callbacks. CommonErrorHandler is the abstraction used by the container; DefaultErrorHandler provides most of the common behavior. You should only implement the interface yourself when a specialized policy cannot be expressed with the built-in implementation.

## 1. Role of CommonErrorHandler

A listener may fail due to a business error, database timeout, deserialization error, or a temporarily unavailable downstream dependency. If an exception escapes the listener, the container must decide the next step. An error handler can:

- Retry the record after a wait interval.
- Classify errors to skip retries for unrecoverable failures.
- Invoke a recoverer when attempts are exhausted.
- Route the record to a DLT for later investigation or reprocessing.
- Record logs, metrics, and delivery-attempt information.
- Decide whether the container can continue after handling the failed record or needs to stop.

CommonErrorHandler defines the common error-handling contract called by the listener container. It replaces the older model of separate interfaces for record error handlers and batch error handlers. As a result, a single configuration can apply across multiple listener styles.

High-level processing flow:

    Consumer poll
        |
        v
    Listener processes record or batch
        |
        +---- success -------------------> Ack / commit per AckMode
        |
        +---- exception
                 |
                 v
          CommonErrorHandler
                 |
          +------+------------------+
          |                         |
          v                         v
       Retry                    No retry
          |                         |
          v                         |
      Backoff exhausted?            |
       |                            |
       +-- no ---> Listener retries |
       |                            |
       +-- yes ---------------------+
                    |
                    v
                 Recoverer
                    |
          +---------+----------+
          |                    |
          v                    v
         DLT             Other recovery
                    |
                    v
           Container continues or
           stops per policy

The error handler controls how the container reacts to consumption errors. It does not replace producer error handling when calling KafkaTemplate.send(), does not automatically roll back database transactions, and does not guarantee that side effects outside Kafka are exactly-once.

## 2. CommonErrorHandler and DefaultErrorHandler

CommonErrorHandler is an interface. DefaultErrorHandler is the implementation Spring Kafka provides for common error handling with retry and recovery.

| Component | Role |
|---|---|
| CommonErrorHandler | Shared exception-handling contract for the listener container |
| DefaultErrorHandler | Retries records/batches per BackOff and invokes the recoverer when retries are exhausted |
| BackOff | Defines wait intervals and number of retry attempts |
| ConsumerRecordRecoverer | Performs an action once a record has exhausted retries |
| DeadLetterPublishingRecoverer | Publishes failed records to a DLT |
| RetryListener | Observes failed deliveries and recovery outcomes |
| ContainerProperties | Configures error handler, commits, and listener container behavior |

DefaultErrorHandler was introduced in Spring Kafka 2.8 and replaces older error handlers such as SeekToCurrentErrorHandler in newer configurations. When upgrading, migrate configuration to setCommonErrorHandler() on the listener container factory.

A minimal configuration can use DefaultErrorHandler with FixedBackOff:

~~~java
@Bean
CommonErrorHandler commonErrorHandler() {
    return new DefaultErrorHandler(
        new FixedBackOff(1_000L, 2L)
    );
}
~~~

The configuration above uses DefaultErrorHandler's default recoverer after retry attempts are exhausted. In production, specify a recoverer explicitly to determine how failed records are stored or handled.

## 3. Attaching CommonErrorHandler to the Listener Container Factory

Declaring a CommonErrorHandler bean is not enough to guarantee that every listener uses that bean. Attach the handler to ConcurrentKafkaListenerContainerFactory via setCommonErrorHandler().

Example:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    CommonErrorHandler commonErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 3L)
                );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            CommonErrorHandler commonErrorHandler) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);

        return factory;
    }
}
~~~

Listener using this factory:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "kafkaListenerContainerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Each container created from the factory will use the configured CommonErrorHandler. If the application has multiple factories for different listener groups, attach an appropriate handler to each factory. For example, a payment-processing listener may need different retry and DLT settings than an analytics-updating listener.

When using Spring Boot, verify which factory @KafkaListener actually references. Do not assume that merely declaring a CommonErrorHandler bean causes every custom factory to automatically pick it up.

## 4. Configuring Retry with BackOff

BackOff determines the wait duration between attempts. DefaultErrorHandler accepts a BackOff object in its constructor.

### 4.1. FixedBackOff

FixedBackOff uses a fixed wait interval:

~~~java
BackOff backOff = new FixedBackOff(1_000L, 3L);

DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);
~~~

In this example, the container waits one second between retry attempts and allows three retries after the initial processing failure. The total number of times the listener can be invoked is the initial attempt plus the configured retries. Document the counting convention clearly in operational runbooks to avoid confusing attempts with retries.

FixedBackOff is suitable when transient errors usually resolve within a steady timeframe, or when a simple, predictable configuration is desired.

### 4.2. Exponential Backoff

If a downstream dependency is overloaded, multiple consumers retrying on the same fixed interval can create a retry storm. Exponential backoff increases the wait time between attempts, giving the downstream system time to recover.

Spring Kafka provides ExponentialBackOffWithMaxRetries:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);
~~~

The wait interval grows by the multiplier without exceeding max interval. The number of retries remains finite. Choose initial interval, multiplier, max interval, and attempt count based on SLAs, dependency recovery time, and how long a record is allowed to remain in the system.

Backoff does not replace HTTP client or database timeouts. If a service call can hang indefinitely, the listener may never throw an exception for the error handler to start retrying. Set timeouts on dependency calls so the retry policy works properly.

### 4.3. Choosing Policy by Error Type

| Scenario | Recommended Policy |
|---|---|
| Temporary database timeout | Bounded retry with exponential backoff |
| Downstream API returns 503 | Retry with backoff interval and cap |
| Payload schema mismatch | Do not retry indefinitely; route to DLT |
| Missing required field | Do not retry if the data cannot self-heal |
| Invalid credentials | Alert and fix configuration; continuous retries will not resolve the root cause |
| Rate limit | Sufficiently long backoff and concurrency limit |
| Transient contention error | Short retry if the operation is idempotent |

Retry is only appropriate when the root cause has a chance of disappearing over time. A deterministic validation error will continue to fail regardless of how many times it is retried.

## 5. Configuring a Recoverer and Dead Letter Topic

When retries are exhausted, DefaultErrorHandler invokes the recoverer. The recoverer receives the record and the last exception, then decides the next action. A common choice is DeadLetterPublishingRecoverer to forward the record to a DLT.

~~~java
@Bean
CommonErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 3L)
            );

    return handler;
}
~~~

With the common default configuration, a record from the source topic is sent to a topic with the `.DLT` suffix while preserving the corresponding partition. For example, a record from `orders` partition 2 is routed to `orders.DLT` partition 2. Therefore, the DLT needs enough partitions to match the routing strategy. Pre-create DLTs in production or configure a resolver to control topic creation and routing.

The DLT should retain information needed for investigation:

- Original payload and key.
- Source topic, partition, and offset.
- Event ID and correlation ID if present.
- Timestamp and headers.
- Final exception and delivery-attempt information.
- Time the record was routed to the DLT.

Do not treat DLT publishing as successful merely because the recoverer was invoked. Configure and monitor DLT send outcomes. If the broker fails to accept the DLT record, the system must preserve recoverability and raise an alert instead of silently marking the source record as handled.

### 5.1. Customizing the DLT Destination

You can provide a DestinationResolver to route by topic or record type:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );
~~~

This example routes to a DLT with the source name plus the `.DLT` suffix, preserving the source partition. If you want to split DLTs by exception type or topic, implement a resolver with clear rules and ensure destination topics have valid partitions.

Do not put sensitive payloads into topic names or headers. The DLT is part of the storage and operations system, so apply appropriate retention, access controls, encryption, and monitoring.

## 6. Classifying Retryable and Non-Retryable Exceptions

Not every exception should be retried. DefaultErrorHandler supports exception classification to decide which errors can be retried.

Example skipping retries for IllegalArgumentException:

~~~java
DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 3L));

handler.addNotRetryableExceptions(
    IllegalArgumentException.class
);
~~~

For invalid data errors, retrying usually does not change the outcome. The handler can route the record straight to the recoverer. Conversely, transient errors such as timeouts can be retried with backoff.

You can add retryable exception types:

~~~java
handler.addRetryableExceptions(
    TransientDataAccessException.class,
    SocketTimeoutException.class
);
~~~

DefaultErrorHandler already includes default classifications for errors that are typically unrecoverable by retry, especially conversion, deserialization, or listener argument-resolution errors. The exact list and behavior depend on the Spring Kafka version. When adding classifications, check whether the new configuration overrides or supplements the defaults for the API you are calling.

For complex policies, you can use setClassifications() to declare a map of exception classes to retryable flags along with a default classification. Only use this when addRetryableExceptions() and addNotRetryableExceptions() are insufficient, as replacing the entire classification map makes it easy to miss exception types.

### 6.1. Sample Classification Table

| Exception or Error Category | Retry? | Reason |
|---|---|---|
| SocketTimeoutException | Bounded | Service or network may recover |
| TransientDataAccessException | Bounded | Database may be temporarily unavailable |
| IllegalArgumentException | Usually no | Invalid data or arguments |
| MessageConversionException | Usually no | Payload does not match target type |
| DeserializationException | Usually no | Data cannot be deserialized with current configuration |
| AuthorizationException | Do not retry continuously | Permissions or credentials must be fixed |
| RecordTooLargeException | Do not retry continuously | Record size or configuration must be fixed |

This is a reference classification. Exceptions may be wrapped in a cause chain, so inspect the actual exceptions the handler receives and the classification rules of the library version in use.

## 7. Observing Retries with RetryListener

RetryListener lets you record each failed delivery attempt, recovery outcome, and any errors occurring during recovery. This is a good place to add metrics and structured logs.

~~~java
handler.setRetryListeners((record, exception, deliveryAttempt) -> {
    log.warn(
        "Kafka delivery failed topic={} partition={} offset={} attempt={}",
        record.topic(),
        record.partition(),
        record.offset(),
        deliveryAttempt,
        exception
    );
});
~~~

The deliveryAttempt value shows how many times the record has been attempted under the listener retry policy. Logs should include eventId if extractable from headers or payload, while avoiding logging full sensitive payloads.

RetryListener should be lightweight. Do not make blocking database or HTTP service calls from the callback if doing so slows down the consumer thread. Use metric counters to track retry counts, successful recoveries, and failed recoveries.

Signals to monitor:

- Listener failure counts by exception class.
- Retries per topic/partition.
- Time from first failure to successful processing.
- Records recovered to the DLT.
- DLT publish failure counts.
- Age of records in the DLT and DLT growth rate.

## 8. Record Listener and Batch Listener

CommonErrorHandler supports both record listeners and batch listeners, though how the failing record in a batch is identified strongly affects retry behavior.

### 8.1. Record Listener

With a record listener, the container invokes the listener once per record. When a record fails, DefaultErrorHandler can seek the partition to redeliver the failed record and subsequent records according to the retry strategy.

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

If process() throws an exception, the handler applies backoff and retries. Once retries are exhausted, the recoverer is invoked. With a DLT recoverer, the failed record is routed to the destination topic. Subsequent records can proceed once the container finishes recovery per the handler policy.

### 8.2. Batch Listener

With a batch listener, one listener invocation receives multiple records. If a record within the batch fails, the handler needs to know which record caused the error to avoid unnecessarily retrying the whole batch.

Spring Kafka provides BatchListenerFailedException so the listener can indicate the failing record or index:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderEvent>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderEvent> record = records.get(index);

        try {
            orderService.process(record.value());
        }
        catch (Exception exception) {
            throw new BatchListenerFailedException(
                "Could not process batch record",
                record
            );
        }
    }
}
~~~

When the handler receives BatchListenerFailedException, it can commit the records before the failing one that were processed successfully, then retry the failing record and the remainder. This reduces re-executing side effects for the entire batch.

If a batch listener throws an exception that does not identify the failing record, the handler may fall back to retrying the entire batch. For large batches, retrying the whole batch can be costly and cause duplicate side effects. When you can identify the failing record, use BatchListenerFailedException with the appropriate record or index.

Batch listeners require careful transaction and idempotency design. The fact that an earlier record in the batch succeeded in writing to the database does not make a full-batch retry safe if side effects are not idempotent.

## 9. Deserialization Errors and ErrorHandlingDeserializer

Deserialization errors happen before the listener receives an object. If the Kafka deserializer throws an exception directly during poll(), the listener has no chance to catch it normally. To bring deserialization errors into Spring Kafka's error-handling flow, ErrorHandlingDeserializer is typically used to wrap the actual deserializer.

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: "com.example.events"
~~~

ErrorHandlingDeserializer stores exception details in the record headers so the container/error handler can process them. The delegate deserializer configuration must match the key/value types and the application's type-mapping strategy.

If using JSON type headers, check trusted packages, default type, and mapping for your Spring Kafka version. Do not open trusted packages too broadly in systems handling untrusted payloads.

DefaultErrorHandler can classify deserialization errors and route failed records to the DLT. However, if a misconfigured deserializer fails to preserve the necessary payload or headers, DLT investigation becomes difficult. Test real malformed-schema records before deploying.

## 10. Acknowledgment and Commit After Recovery

After the error handler finishes handling an error, the container must decide whether to commit the offset. DefaultErrorHandler has an ackAfterHandle property to control committing after the exception has been handled and the handler returns normally.

Under default behavior, a successfully recovered record can be treated as handled so the container continues and commits per container policy. If you change ackAfterHandle, understand the impact on redelivery. If the handler returns normally but the offset is not committed per configuration, the record may be redelivered.

DefaultErrorHandler also supports commitRecovered under certain acknowledgment modes. When enabling commitRecovered, AckMode.MANUAL_IMMEDIATE is required by the API:

~~~java
handler.setCommitRecovered(true);
~~~

Do not enable this setting just to “be extra sure” without understanding how the container commits. Clarify:

- Which AckMode the listener uses.
- Whether the error handler handles errors per record or per batch.
- Whether the recoverer completed successfully or threw an exception.
- Whether offsets are committed by the container or the handler.
- Whether the consumer group could receive the record again after a restart.

If the database has committed but the offset has not, the record can be redelivered. Use eventId and idempotent business operations so side effects are not duplicated.

## 11. Seek Behavior and Post-Error Processing

DefaultErrorHandler typically uses seek so the consumer re-reads the failed record and unprocessed records in the partition. This is blocking retry: the failing record holds up the partition stream until retry or recovery completes.

In newer Spring Kafka versions, you can configure seekAfterError behavior to retain unprocessed records inside the container instead of seeking in the default manner. In that mode, the container can pause the consumer and poll to maintain group membership, then redeliver the remaining records. Details and configuration depend on the library version.

Blocking retry has the advantage of making partition ordering more predictable. The downside is that one failing record can delay subsequent records in the same partition. If backoff is long, consider poll intervals, heartbeats, and container pausing backoff handlers.

Do not use long blocking retries as a multi-hour delay mechanism. For long delays or when failing records need to be separated from the main stream, a retry topic may be a better fit.

## 12. Distinguishing CommonErrorHandler from Retry Topics

CommonErrorHandler and @RetryableTopic serve two different strategies:

| Mechanism | How It Works | Best Suited When |
|---|---|---|
| DefaultErrorHandler | Retries the record in the current consumer flow with backoff | Transient errors where partition ordering must be preserved |
| @RetryableTopic | Routes the record to a retry topic and redelivers later | Longer delays are needed or blocking the main partition is unacceptable |
| DLT | Stores records that exhausted retries or cannot be processed | Controlled investigation and recovery |

Retry topics can alter event ordering: record A is sent to a retry topic while subsequent record B is processed on the main topic. If business logic requires strict per-key ordering, evaluate this carefully before adopting non-blocking retries.

Do not configure both blocking retry and a retry topic for the same error without calculating the total attempt count. If both retry layers are active, downstream service calls can multiply and unexpectedly inflate processing latency.

## 13. DLT Recovery Failure

The recoverer itself can also fail. For instance, the DLT topic may not exist, the broker may be unavailable, the producer may fail to serialize the record, or publishing may time out. In that case, the source record must not be considered successfully recovered.

DefaultErrorHandler has mechanisms for when the recoverer throws an exception. When recovery fails, retry state can be reset so the record is retried with backoff on the next delivery. Exact reset behavior and configuration depend on the version. Monitor recovery failures separately from listener failures.

Operational points:

- The DLT topic must exist or the broker must be allowed to create topics under a controlled policy.
- The DLT producer's serializer must be able to handle failed payloads and their types.
- The DLT needs enough partitions if the resolver preserves the source partition.
- DLT publishing must be observable via callbacks/metrics, and send failures must be detected.
- Do not discard or commit the source record's offset until the failed record is confirmed stored per recovery policy.
- Maintain a re-drive procedure and preserve the original eventId so idempotent consumers recognize replayed messages.

## 14. Handling Exceptions Across the Cause Chain

Exceptions in listeners are often wrapped by other exceptions. For example, a database error may be wrapped in ListenerExecutionFailedException. If classification only inspects the outermost exception without walking the cause chain, the handler may misclassify it.

DefaultErrorHandler and supporting components have rules to search exceptions in the cause chain. Still, check actual exceptions in logs and the library version in use. When your application wraps exceptions itself, preserve the original cause:

~~~java
try {
    repository.save(entity);
}
catch (DataAccessException exception) {
    throw new OrderPersistenceException(
        "Could not persist order",
        exception
    );
}
~~~

If the original cause is lost, the error handler struggles to recognize transient errors. Avoid creating a single generic exception for all situations if the retry policy needs to distinguish timeouts, validation errors, and permission errors.

## 15. Custom CommonErrorHandler When a Specialized Policy Is Needed

DefaultErrorHandler satisfies most common needs. Implement CommonErrorHandler directly only when specialized control is required, such as forwarding errors to a custom orchestration system or applying rules that cannot be expressed with BackOff and a recoverer.

A custom handler must understand these contract points:

- Handle a single failed record with handleOne() if the strategy can process the record without seeking remaining records.
- Handle the record and remaining records with handleRemaining() when manual seek control is needed.
- Handle batches with handleBatch().
- Handle exceptions thrown outside listener invocation with handleOtherException().
- Declare seeksAfterHandling() accurately so the container knows whether the handler performed seeking itself.
- Define isAckAfterHandle() so the container knows whether it can commit after the handler succeeds.
- Declare deliveryAttemptHeader() if the handler supports the delivery-attempt header.

Method signatures and contracts can change across Spring Kafka versions. Read the Javadoc for your exact dependency version before implementing. Mistakes in seeking or acknowledgment can cause lost records or infinite redelivery loops.

If you only need extra logging, metrics, or a classification rule, configure DefaultErrorHandler instead of rewriting the full contract. Any custom handler must have integration tests covering record listeners, batch listeners, rebalances, and commits.

## 16. Complete Configuration with DLT and Error Classification

The following example combines a DLT, bounded retries, non-retryable errors, and an observation callback:

~~~java
@Configuration
public class KafkaErrorConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaErrorConfiguration.class);

    @Bean
    CommonErrorHandler commonErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 3L)
                );

        handler.addNotRetryableExceptions(
            IllegalArgumentException.class,
            MessageConversionException.class
        );

        handler.setRetryListeners((record, exception, deliveryAttempt) -> {
            log.warn(
                "Kafka retry topic={} partition={} offset={} attempt={}",
                record.topic(),
                record.partition(),
                record.offset(),
                deliveryAttempt,
                exception
            );
        });

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            CommonErrorHandler commonErrorHandler) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);

        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Main imports required depending on application setup:

~~~java
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.util.backoff.FixedBackOff;
~~~

The example may also require imports for MessageConversionException, Logger, and LoggerFactory. Generic types of KafkaTemplate, ConsumerFactory, and the listener must match the application's serializers/deserializers. If the project uses different Spring Kafka versions, verify the RetryListener API and configuration methods in the corresponding Javadoc.

## 17. Spring Boot and Multiple Listener Factories

An application may have multiple listeners with different error requirements. For example:

- orders listener: short retries and a dedicated DLT.
- payments listener: bounded retries, immediate alert on error.
- analytics listener: may skip certain data errors and store in a DLT for analysis.
- batch listener: needs BatchListenerFailedException to pinpoint failing records.

You can create multiple factories and attach the appropriate CommonErrorHandler to each factory. Each factory should have a clear name, concurrency, and appropriate AckMode.

Avoid using a single error handler with a long retry configuration for every listener when processing durations and ordering requirements differ. Error policies should align with the SLA and business impact of each event type.

If the application has both Spring Boot's auto-configured default factory bean and custom factories, check which bean @KafkaListener actually uses. Configuring a bean that is not referenced will have no effect on that listener.

## 18. Managing Retry Storms and Processing Order

A retry storm happens when many records fail simultaneously and consumers retry too aggressively. This can overload the downstream dependency further, increase lag, and stall multiple partitions at once.

To reduce risk:

- Use increasing backoff and cap the number of attempts.
- Set timeouts on databases and HTTP clients.
- Classify permanent errors to avoid futile retries.
- Limit concurrency toward downstream dependencies.
- Track retry rates by exception and dependency.
- Move unrecoverable records to a DLT.
- Use circuit breakers or bulkheads where appropriate for the dependency.

With blocking retry, a failing record can hold a partition until processing finishes or the record is recovered. This keeps per-partition order more predictable, but forces subsequent records to wait. With a retry topic, the main flow can proceed, though event order may change. Choose the mechanism based on ordering requirements, not speed alone.

## 19. Testing CommonErrorHandler

Tests must verify listener behavior, retries, recovery, and offsets—not just that the bean was created successfully.

Recommended scenarios:

1. Listener fails on the first attempt then succeeds on retry: verify attempt count and backoff.
2. Listener always fails: verify recoverer is invoked after retries are exhausted.
3. Non-retryable exception: verify the handler routes straight to recovery per classification.
4. DLT unavailable: verify recovery failure is recorded and the record is not silently skipped.
5. Batch listener throws BatchListenerFailedException: verify records before the failure are not unexpectedly reprocessed.
6. Batch listener throws a generic exception: verify fallback batch retry matches configuration.
7. Deserialization failure: verify ErrorHandlingDeserializer passes the error to the handler.
8. Consumer rebalance during retry: verify offsets and records can be recovered safely.
9. Recovery succeeds: verify offset is committed per AckMode and ackAfterHandle.
10. Side effect succeeds but offset not yet committed: verify consumer idempotency upon redelivery.
11. Retry rate spike: verify metrics, alerts, and load limits.
12. Re-drive from DLT: verify eventId is preserved and business logic is not applied twice.

Use EmbeddedKafka or a test broker appropriate to the project's stack to verify real behavior. Unit tests for classification and recoverers are helpful, but do not replace integration tests because seeking, polling, committing, and rebalancing are coordinated by the container and Kafka client together.

## 20. Production Observability

A good CommonErrorHandler configuration must give operations enough data to understand what state records are in.

**Retry**

- Retry count by topic, partition, and exception class.
- Backoff wait duration.
- Retry success rate.
- Count of records that exhausted retries.

**Recovery and DLT**

- Count of records routed to DLT.
- Age of the oldest record in the DLT.
- Count of failed DLT publishes.
- Count of re-driven records and re-drive outcomes.

**Container**

- Listener error rate.
- Consumer lag.
- Rebalance count and duration.
- Commit latency and commit failures.
- Record processing latency p95/p99.

Logs should include eventId, topic, partition, offset, consumer group, delivery attempt, and exception class. Avoid logging full payloads containing personal or sensitive data. Use correlation IDs to connect producer, listener, dependency, and DLT logs.

When lag rises, distinguish records waiting for initial processing from records held in retries. When DLT volume grows, identify whether the root cause is bad data, dependency failure, or misconfiguration. Retry and recovery metrics help differentiate these situations.

## 21. Common Configuration Mistakes

| Practice | Problem | Resolution |
|---|---|---|
| Only declaring a CommonErrorHandler bean | Custom factory might not use that bean | Call setCommonErrorHandler() on the factory |
| Retrying every exception | Data or config errors loop pointlessly | Classify retryable/non-retryable errors |
| Unbounded backoff | A record can hold a partition for too long | Limit attempt count and configure a DLT |
| DLT missing partitions | Recoverer preserving source partition may fail to publish | Pre-create DLT with enough partitions or use a custom resolver |
| Ignoring DLT publish failures | Original record can drop out of the recovery flow | Monitor recovery failures and do not treat failed recovery as success |
| Batch listener not identifying failing record | Handler may retry the whole batch | Throw BatchListenerFailedException with the proper record/index |
| Mixing retry topics with blocking retry without counting total attempts | Downstream calls can multiply | Design a single overall retry budget |
| Committing offset before side effects | Business actions can be lost | Commit after durable processing |
| Non-idempotent side effects | Redelivered records can cause duplicates | Use eventId, inbox, or idempotency keys |
| Using legacy APIs after upgrade | Configuration becomes incompatible | Migrate to CommonErrorHandler and check version compatibility |

## 22. Production Selection Principles

- Use CommonErrorHandler as the unified error-handling contract for listener containers.
- Prefer DefaultErrorHandler when standard retry, backoff, and recovery are needed.
- Attach the handler explicitly to each ConcurrentKafkaListenerContainerFactory.
- Choose finite backoff based on SLAs and dependency recovery times.
- Classify exceptions so permanent errors are not retried fruitlessly.
- Use a recoverer and DLT for records that cannot be handled automatically.
- Ensure the DLT has appropriate partitions, serializers, retention, and access controls.
- Use BatchListenerFailedException to pinpoint failing records in batch listeners.
- Disable auto-commit when the container manages offsets and choose an appropriate AckMode.
- Distinguish blocking retry from retry topics, especially when business logic requires ordering.
- Make side effects idempotent because retries, recovery, and rebalances can cause redelivery.
- Monitor retries, recovery failures, DLT volume, lag, and commits.
- Test listener failures, DLT failures, and uncommitted-offset cases.
- Verify APIs against the exact Spring Kafka version of your application.

CommonErrorHandler provides a unified configuration point for errors in listener containers. When combined with DefaultErrorHandler, BackOff, exception classification, and an appropriate recoverer, an application can retry transient errors, isolate unprocessable records, and continue consuming under control. Ultimate reliability still depends on committing offsets at the right time, keeping side effects idempotent, and operating the DLT as a monitored recovery pipeline.
