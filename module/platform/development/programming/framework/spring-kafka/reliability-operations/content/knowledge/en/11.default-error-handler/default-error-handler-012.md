# Using RetryListener to Track Delivery Attempts

In Spring Kafka, **RetryListener** is a callback interface that allows an application to observe failed record deliveries and the recovery process executed by the error handler. When using **DefaultErrorHandler**, an application can register a RetryListener to receive information about the record, exception, and current delivery attempt number. This callback helps build structured logs, retry metrics, poison-message alerts, and diagnostic data.

A delivery attempt is one instance where the consumer receives and tries to process a record. The initial delivery also counts as an attempt; subsequent redeliveries after retries increment the attempt number. Therefore, **deliveryAttempt** is not simply the number of retries performed. For example, if a record fails at attempt 3, the record has had three deliveries/processing attempts, corresponding to two redeliveries after the first.

RetryListener observes the retry flow managed by the error handler. It does not perform retries itself, does not decide BackOff, does not commit offsets, and does not replace the recoverer. Those decisions remain with **DefaultErrorHandler**, the container, and the recovery configuration.

## 1. Delivery Attempts in the Kafka Processing Flow

A record can be delivered multiple times when a listener throws an exception and the error handler decides to retry. With DefaultErrorHandler's blocking retry, the container processes the record, waits per BackOff, and redelivers the record according to the corresponding seek/retry mechanism.

Example lifecycle of a record:

1. Consumer receives the record for the first time.
2. Listener processes it and throws an exception.
3. DefaultErrorHandler invokes RetryListener to report the failed delivery.
4. Error handler waits per configured BackOff.
5. Record is redelivered.
6. If the listener continues to fail, the callback is invoked with the next delivery attempt.
7. When retries are exhausted, the recoverer handles the record; RetryListener is notified if recovery succeeds or fails.

~~~mermaid
sequenceDiagram
    participant C as Kafka consumer/container
    participant L as Listener
    participant E as DefaultErrorHandler
    participant R as RetryListener
    participant X as Recoverer

    C->>L: Deliver record (attempt 1)
    L-->>E: Throw exception
    E->>R: failedDelivery(record, ex, 1)
    E->>E: BackOff
    C->>L: Redeliver record (attempt 2)
    L-->>E: Throw exception
    E->>R: failedDelivery(record, ex, 2)
    E->>E: Retries exhausted
    E->>X: Recover record
    X-->>E: Recovery succeeded
    E->>R: recovered(record, ex)
~~~

The diagram illustrates a case with two failed deliveries followed by recovery. The actual number of retries depends on BackOff. If the listener succeeds on an attempt, the flow finishes without needing recovery.

## 2. Which Callbacks Does RetryListener Provide?

For record listeners and modern Spring Kafka versions with the RetryListener API, three primary callbacks are commonly used:

| Callback | When Called | Purpose |
|---|---|---|
| **failedDelivery(record, ex, deliveryAttempt)** | After a delivery processing attempt fails, before the next retry or recovery step | Records the failed delivery and attempt number |
| **recovered(record, ex)** | When the recoverer completes recovery successfully | Records that the record was handled by the recovery pipeline |
| **recoveryFailed(record, original, failure)** | When the recoverer throws an error during recovery | Records recovery failure and its cause |

The callbacks carry distinct meanings:

- **failedDelivery** records a failed listener invocation. It can be called multiple times for the same record.
- **recovered** indicates the recoverer completed its recovery operation. If the recoverer publishes to a DLT, this callback signals that the recovery operation returned successfully; it does not mean original business processing succeeded.
- **recoveryFailed** indicates the recovery process itself encountered an error. The record may continue being reprocessed depending on error handler configuration.

Exact interface names and overloads can vary across Spring Kafka versions. The examples below use common record-level methods from Spring Kafka 2.8 and later. Batch listeners and newer versions may provide overloads accepting **ConsumerRecords**; check the API of your running dependency.

### Distinguishing Attempt from Retry Count

Suppose configuration allows two retries after the initial delivery:

| Listener Invocation | deliveryAttempt | Outcome |
|---:|---:|---|
| Initial attempt | 1 | Failed |
| First retry | 2 | Failed |
| Second retry | 3 | Failed, move to recovery |

In this example, there are three delivery attempts yet only two retries after the initial delivery. When exposing metrics or logs, name fields clearly such as **delivery_attempt** and **retry_number** if the application computes both. Do not directly equate deliveryAttempt with retry count.

## 3. Configuring RetryListener with DefaultErrorHandler

RetryListener is registered on the error handler. In modern Spring Kafka, **DefaultErrorHandler** provides **setRetryListeners(...)**.

The example below uses a recoverer that records exhausted records and a RetryListener to observe each step:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.RetryListener;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler() {
        ConsumerRecordRecoverer recoverer = (record, exception) -> {
            // Example: log or forward record to a recovery store.
            // Replace with a DLT recoverer if the system has a DLT.
            log.error(
                    "Recovering topic={} partition={} offset={}",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    exception
            );
        };

        var errorHandler = new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)
        );

        errorHandler.setRetryListeners(new RetryListener() {

            @Override
            public void failedDelivery(
                    ConsumerRecord<?, ?> record,
                    Exception exception,
                    int deliveryAttempt) {

                log.warn(
                        "Delivery failed topic={} partition={} offset={} attempt={}",
                        record.topic(),
                        record.partition(),
                        record.offset(),
                        deliveryAttempt,
                        exception
                );
            }

            @Override
            public void recovered(
                    ConsumerRecord<?, ?> record,
                    Exception exception) {

                log.info(
                        "Record recovered topic={} partition={} offset={}",
                        record.topic(),
                        record.partition(),
                        record.offset()
                );
            }

            @Override
            public void recoveryFailed(
                    ConsumerRecord<?, ?> record,
                    Exception original,
                    Exception recoveryFailure) {

                log.error(
                        "Recovery failed topic={} partition={} offset={}",
                        record.topic(),
                        record.partition(),
                        record.offset(),
                        recoveryFailure
                );
            }
        });

        return errorHandler;
    }
}
~~~

In this example, **FixedBackOff(1_000L, 2L)** requests a 1-second wait between attempts and allows two retries after the initial delivery per Spring BackOff semantics. The recoverer is invoked once the record exhausts retries. RetryListener observes failures and recovery outcomes; it does not alter the retry count.

The code uses logger **log** per application convention. In a plain Java class, declare the logger, such as via SLF4J. If publishing to a DLT is desired, replace the illustrative recoverer with **DeadLetterPublishingRecoverer** and configure KafkaTemplate, destination topic, and publish permissions appropriately.

## 4. Attaching the Error Handler to the Listener Container Factory

An error handler only takes effect when the listener's container is configured to use it. Attach the **DefaultErrorHandler** bean to **ConcurrentKafkaListenerContainerFactory**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Configuration
public class OrderListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerFactory(
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
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
        id = "orderListener",
        topics = "orders.created",
        groupId = "billing-service",
        containerFactory = "orderListenerFactory"
    )
    public void handle(OrderEvent event) {
        billingService.process(event);
    }
}
~~~

When the listener throws an exception, the container delegates the error to the attached DefaultErrorHandler. RetryListener is called on the corresponding callbacks. If an application has multiple factories, verify that the listener whose retries you want to observe actually uses the factory whose error handler registered RetryListener.

### Using Spring Boot's Default Factory

If an application uses Spring Boot's default auto-created factory, you can configure the factory via a customizer or declare the factory bean yourself and attach the error handler. Specific wiring depends on Spring Boot and Spring Kafka versions.

When defining a factory manually, preserve existing settings your application needs, such as ConsumerFactory, message converters, concurrency, AckMode, transaction managers, and customizers. Registering RetryListener on an error handler not used by any listener container will produce no callbacks.

## 5. Tracking Each Failed Delivery

**failedDelivery** is the primary callback for logging attempts. A log event can include:

- Service name and environment.
- Consumer group or listener ID.
- Topic, partition, and offset.
- Event ID or correlation ID if available.
- Delivery attempt number.
- Exception class and SQLState/vendor code if the error comes from a database.
- Callback timestamp.
- Active retry policy or error handler.

Structured log example:

~~~text
event=consumer_delivery_failed
service=billing-service
listener=orderListener
group=billing-service
topic=orders.created
partition=2
offset=1048
event_id=evt-7f9a
delivery_attempt=2
exception=TransientDataAccessException
~~~

This format is illustrative only. Do not write full payloads, credentials, access tokens, or sensitive data into logs. Event IDs should be logged only if your system's data policy permits it.

### Counting Failures

RetryListener can increment a counter each time a delivery fails:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.RetryListener;

public class DeliveryMetricsRetryListener implements RetryListener {

    private final MeterRegistry meterRegistry;

    public DeliveryMetricsRetryListener(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        meterRegistry.counter(
                "spring.kafka.delivery.failures",
                "topic", record.topic(),
                "exception", exception.getClass().getSimpleName()
        ).increment();
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {

        meterRegistry.counter(
                "spring.kafka.delivery.recovered",
                "topic", record.topic()
        ).increment();
    }

    @Override
    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception failure) {

        meterRegistry.counter(
                "spring.kafka.delivery.recovery.failed",
                "topic", record.topic(),
                "exception", failure.getClass().getSimpleName()
        ).increment();
    }
}
~~~

The tags in this example represent dimensions with bounded cardinality. Never use offset, event ID, key, customer ID, or correlation ID as metric tags because they create huge cardinality and can overload the metrics system. Per-record identifiers belong in logs or traces.

## 6. Distinguishing failedDelivery, recovered, and recoveryFailed

These three callbacks describe three distinct stages. When reading dashboards, do not sum them into a single “retry success” metric.

### failedDelivery

This callback runs when a listener invocation fails. A single record can emit multiple failedDelivery callbacks if consecutive attempts fail.

Example:

- Attempt 1 fails due to database deadlock.
- Attempt 2 fails due to downstream timeout.
- Attempt 3 succeeds.

RetryListener may record two failedDelivery calls. There is no recovered callback if the listener eventually processes the record successfully without needing the recoverer.

### recovered

This callback indicates the error handler invoked the recoverer and the recoverer completed. For instance, the recoverer published the record to a dead-letter topic without throwing an exception.

**recovered** does not mean the original business logic succeeded. The record was handed off to a recovery workflow. Dashboards should distinguish listener processing success, records recovered/sent to DLT, and failed recoveries.

### recoveryFailed

This callback occurs when the recoverer fails—for example, the DLT publisher cannot send due to an unavailable broker, authorization failure, or serialization error.

When recovery fails, the record has not been successfully handled by the recovery pipeline. Subsequent behavior depends on error handler, BackOff, state reset, and container configuration. Configure a dedicated alert for recovery failures because they can cause records to keep redelivering or stall a partition behind one bad record.

## 7. RetryListener Is Not a Retry Mechanism

RetryListener only observes and reports events. It does not decide:

- Which exceptions are retried.
- How many retries occur.
- Wait intervals between attempts.
- Whether fixed, exponential, or custom BackOff is used.
- When a record moves to the DLT.
- When offsets are committed.
- Whether the consumer seeks the partition back.

Those decisions belong to DefaultErrorHandler, BackOff, ConsumerRecordRecoverer, container properties, and transaction configuration.

Do not place retry logic directly inside the **failedDelivery** callback. Callbacks should be fast, non-blocking, and free of business side effects. If a callback hits a database, HTTP API, or sends messages synchronously, it can slow down the consumer thread and increase consumer lag.

If alerting is needed, prefer logging/metrics or pushing a lightweight signal to observability systems. Ensure errors inside RetryListener itself do not mask the original exception or break error handler execution.

If recovery actions are needed, implement them through ConsumerRecordRecoverer or DLT publishing. RetryListener only records events and outcomes.

## 8. Delivery Attempt and Offset

Delivery attempt is not the Kafka offset. The two values have different meanings:

| Value | Meaning |
|---|---|
| Topic/partition/offset | Record's position in the Kafka log |
| deliveryAttempt | Number of times the record was delivered/attempted within the error handler's retry flow |
| Retry count | Number of redeliveries after the initial attempt; typically one less than deliveryAttempt when initial delivery counts as attempt 1 |
| Consumer group committed offset | Next position confirmed by the consumer group |

A record at offset 1048 may be delivered at attempts 1, 2, and 3. Its offset remains 1048 across redeliveries. Only when the listener succeeds and the offset is committed per AckMode does the committed position advance past that record.

Delivery attempt is not a global counter durably persisted across the event's entire lifecycle. Across process restarts, rebalances, error handler changes, or routing through a retry-topic system, attempt history may have a different scope. If end-to-end history is required, the application must persist attempts or workflow state in a durable store keyed by event ID.

## 9. Combining RetryListener with DLT Recovery

A common workflow is retrying a record several times and then publishing to a dead-letter topic. RetryListener helps observe both failures and recovery outcomes.

Configuration example:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate,
        RetryListener deliveryRetryListener) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);

    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L)
    );

    handler.setRetryListeners(deliveryRetryListener);

    return handler;
}
~~~

In this configuration, the example's recoverer uses DeadLetterPublishingRecoverer's DLT routing mechanism. In production, explicitly configure destination topics, partition routing, serializers, producer permissions, and retained metadata. **FixedBackOff(1_000L, 3L)** illustrates three retries after the initial delivery; total listener invocations when all attempts fail can reach four.

RetryListener records:

- Failed attempts via **failedDelivery**.
- Successful recovery via **recovered**.
- Failed recovery via **recoveryFailed**.

If DLT publishing succeeds yet the consumer fails to commit the offset due to a rebalance or commit error, understand container semantics to avoid reprocessing and duplicate DLT sends. DLT consumers and replay workflows still require idempotency.

## 10. Exception Classification and Retry Policy

Not every exception should be retried. RetryListener observes attempts, yet the error handler must carry the right error classification.

| Error Category | Commonly Considered Behavior |
|---|---|
| Database deadlock | Bounded retry with backoff after transaction rollback |
| Database connection reset | Bounded retry; monitor database health |
| HTTP 503 or transient timeout | Retry with backoff if operation is safe |
| Validation error | Usually do not retry; recovery/DLT for investigation |
| AuthorizationException | Fix permissions; repeated retries do not grant ACLs |
| Deserialization error | Recovery/DLT or handle bad data per policy |
| Business unique constraint | Determine duplicate/idempotency; do not retry blindly |

You can configure exception classification on DefaultErrorHandler using methods such as **addRetryableExceptions** and **addNotRetryableExceptions**, depending on Spring Kafka version. Inspect the cause chain to avoid misclassifying when database or HTTP exceptions are wrapped inside other exceptions.

A clear policy keeps RetryListener metrics meaningful. If non-retryable errors still get counted as retry failures, dashboards can mislead operators into thinking the system is retrying them.

## 11. Batch Listeners and RetryListener

With a batch listener, a single listener invocation can receive multiple records. When a batch fails, the error handler may reprocess the entire batch or use failed-record metadata to seek/recover appropriately.

Some Spring Kafka versions extend RetryListener with callbacks taking **ConsumerRecords<?, ?>** for batch deliveries. Do not implement batch overloads when your active dependency does not yet expose that API. Check the Javadoc for your exact version.

When tracking batches, also record:

- Number of records in the batch.
- Involved topic-partitions.
- Starting and ending offsets or the failed record's offset.
- Batch listener ID.
- Delivery attempt.
- Exception and recovery outcome.

If a batch contains records from multiple partitions, a per-topic metric alone may not be enough to isolate issues. Log partition/offset details, but avoid using them as high-cardinality metric tags.

If **subBatchPerPartition** is enabled, the container may split batches by partition before invoking the listener per configuration. This changes invocation scope, without replacing the error handler or retry listener.

## 12. Distinguishing Blocking Retries from Non-Blocking Retry Topics

DefaultErrorHandler's RetryListener tracks deliveries and retries managed by that error handler. Spring Kafka also provides non-blocking retries with retry topics, commonly declared via **@RetryableTopic**.

The two models follow different paths:

- **Blocking retry** keeps processing inside the consumer and retries the record per BackOff/error handler.
- **Non-blocking retry** forwards the record to a retry topic so another listener/container picks it up after a delay.

With retry topics, each topic hop is a step in the retry pipeline. Do not treat a single RetryListener on the initial consumer as a global counter for the whole retry-topic chain. Monitor retry topics, the DLT, delivery metadata/headers, forwarded record counts, and consumer health per topic.

If the application uses **@RetryableTopic**, inspect the retry infrastructure created by the annotation and verify which containers have callbacks attached. Use event IDs to correlate logs across the main topic, retry topics, and DLT.

## 13. Observability, Dashboards, and Alerts

RetryListener emits events close to when listener failures happen. Combine them with consumer and DLT metrics to monitor processing health.

### Recommended Metrics

| Metric | Meaning |
|---|---|
| **spring.kafka.delivery.failures** | Count of failed listener deliveries |
| **spring.kafka.delivery.recovered** | Count of successfully recovered records |
| **spring.kafka.delivery.recovery.failed** | Count of recoverer failures |
| Retry attempts by exception class | Error groups triggering retries |
| DLT publish rate | Rate of records routed to the DLT |
| Consumer lag | Group backlog |
| Listener processing duration | Record/batch execution time |
| Recovery latency | Elapsed time from initial failure to recovery |

Metric names follow an illustrative convention; applications can choose names matching internal observability standards. With Micrometer, keep tag cardinality low and consistent.

### Useful Alerts

- Sudden rise in failedDelivery rate by service or topic.
- One exception class generating many consecutive attempts.
- Non-zero recoveryFailed counts.
- DLT publishes rising above normal thresholds.
- Consumer lag climbing alongside retry rates.
- A listener having many records hitting maximum attempts.
- Age of records in the DLT or retry topics exceeding SLAs.

Do not alert on a single failedDelivery occurrence. A transient glitch resolved by retry can be normal behavior. Alerts should trigger on rates, trends, high attempt counts, recovery failures, or lag/SLA impact.

### Correlation in Logs and Traces

Use event ID, correlation ID, listener ID, and consumer group to tie together attempts for the same record. Offsets locate positions in Kafka, yet cannot replace event IDs when the same event is republished as a new record at a different offset.

## 14. RetryListener Must Be Lightweight and Safe

Callbacks run in the error handler's execution path. Heavy work in callbacks slows down the consumer and adds lag.

Do:

- Write structured logs with enough context for tracing.
- Increment fast counters or timers.
- Attach bounded-cardinality listener IDs or service names.
- Avoid synchronous network calls.
- Never store sensitive payloads.
- Never throw new exceptions from callbacks.
- Avoid retaining references to records or exceptions in unbounded collections.

Do not use callbacks to re-invoke the listener, commit offsets, or manually publish records. Those actions can break semantics managed by DefaultErrorHandler.

If recovery actions are required, implement them via ConsumerRecordRecoverer or DLT publishing. RetryListener only records events and outcomes.

## 15. Testing RetryListener

Unit tests can verify callbacks fire and fields are recorded when the handler processes errors. Integration tests with a Kafka broker verify actual delivery, retry, recovery, and offset behavior in a real container.

A test scenario:

1. Create a test topic and dedicated consumer group.
2. Configure a listener to deliberately fail on the first two attempts and succeed afterward.
3. Configure DefaultErrorHandler with a short BackOff and a test RetryListener.
4. Send a record with a fixed event ID.
5. Verify the failedDelivery callback receives increasing attempt numbers.
6. Verify the listener succeeds on the subsequent attempt.
7. Verify the recoverer is not called when the record succeeds before exhausting retries.
8. Create another scenario that always fails and verify the recoverer is called after configured attempts.
9. Verify recovered fires when the recoverer finishes.
10. Create a recoverer that throws an exception and verify recoveryFailed fires.
11. Verify offsets and redelivery per AckMode/container configuration.

Example test listener with a counter:

~~~java
@Component
public class RetryTestListener {

    private final AtomicInteger invocations = new AtomicInteger();

    @KafkaListener(
        topics = "retry-test",
        groupId = "retry-test-group"
    )
    public void consume(String value) {
        int current = invocations.incrementAndGet();

        if (current <= 2) {
            throw new IllegalStateException("Simulated transient failure");
        }
    }

    public int invocationCount() {
        return invocations.get();
    }
}
~~~

In real tests, isolate counters by event ID if multiple records may arrive or tests run in parallel. A shared counter only fits simple examples and can produce non-deterministic results when concurrency exceeds one.

### Testing Callbacks Independently

You can use a recording RetryListener to collect invocations:

~~~java
public class RecordingRetryListener implements RetryListener {

    private final List<Integer> failedAttempts = new CopyOnWriteArrayList<>();
    private final AtomicInteger recoveredCount = new AtomicInteger();
    private final AtomicInteger recoveryFailedCount = new AtomicInteger();

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        failedAttempts.add(deliveryAttempt);
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        recoveredCount.incrementAndGet();
    }

    @Override
    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception failure) {
        recoveryFailedCount.incrementAndGet();
    }

    public List<Integer> failedAttempts() {
        return List.copyOf(failedAttempts);
    }
}
~~~

Tests should use bounded wait assertions with timeouts instead of fixed sleeps. With high listener concurrency, collections and counters must be thread-safe. Do not share a recording listener across multiple tests without resetting state or isolating contexts.

## 16. Common Implementation Mistakes

**Confusing deliveryAttempt with retry count.** Delivery attempt usually includes the initial delivery. Label metric names and logs accurately.

**Logging only failedDelivery.** Not observing recovered and recoveryFailed leaves operations blind to whether records recovered or recovery itself failed.

**Thinking RetryListener performs retries.** Callbacks only observe; BackOff and DefaultErrorHandler drive retries.

**Registering the listener on an unused error handler.** The factory or endpoint may be using a different handler. Verify the active container factory.

**Making HTTP/database calls in callbacks.** Callbacks stall the processing path and can inflate consumer lag. Keep callbacks short.

**Using offsets or event IDs as metric tags.** Cardinality explodes rapidly. Put per-record identifiers in logs/traces.

**Treating recovered as business success.** Recovered means the recoverer completed, such as publishing to a DLT. The record may not have finished original business logic.

**Not handling recoveryFailed.** DLT publishing can fail due to permissions, serialization, or broker issues. Add dedicated alerts and runbooks.

**Using blocking-retry RetryListener to measure an entire retry-topic pipeline.** Non-blocking retries involve multiple containers and topics. Observe each hop in the pipeline.

**Assuming attempt counts persist forever across restarts.** RetryListener reflects retry state managed by the handler. If end-to-end history is required, persist it in a durable store by event ID.

## 17. Runbook When Retry Attempts Spike Unexpectedly

1. Identify listener ID, consumer group, topic, and partition.
2. Find failedDelivery logs by event ID or topic-partition-offset.
3. Inspect the highest deliveryAttempt and corresponding exception class.
4. Check DefaultErrorHandler, BackOff, and exception classification.
5. Determine whether the error is transient, invalid data, or unrecoverable misconfiguration.
6. Check listener processing time, downstream latency, and consumer lag.
7. If recovered callbacks appear, verify the recoverer actually persisted/published the record to the intended target.
8. If recoveryFailed appears, check the DLT topic, ACLs, serializers, and broker connectivity.
9. Check whether the record was routed through retry topics; trace each hop.
10. After fixing the root cause, replay records using an idempotent workflow.
11. Monitor failedDelivery rate, recovery success, DLT rate, and consumer lag post-recovery.
12. Record any exception classification or BackOff changes to prevent recurring retry storms.

Do not raise retry counts merely because attempts are high. If the failure is a schema or authorization error, increasing retries usually just prolongs processing and swells backlogs.

## 18. Pre-Production Checklist for RetryListener

**Configuration**

- [ ] RetryListener is registered on the right DefaultErrorHandler.
- [ ] Listener containers actually use that error handler.
- [ ] BackOff and retry counts are explicitly defined.
- [ ] Retryable and non-retryable exceptions are classified.
- [ ] Callback APIs match your Spring Kafka version.

**Monitoring**

- [ ] failedDelivery records attempt number and exception.
- [ ] recovered is distinguished from listener success.
- [ ] recoveryFailed triggers an alert.
- [ ] Logs include appropriate listener/group/topic/partition/offset and event ID.
- [ ] Metric tags have low cardinality.

**Safety and Recovery**

- [ ] Callbacks are non-blocking and perform no business logic.
- [ ] Callbacks do not throw new exceptions.
- [ ] Recoverer has a DLT/recovery store and proper publish permissions.
- [ ] Records have idempotency to withstand redelivery.
- [ ] Retry topics and blocking retries are monitored in their proper scope.

**Testing**

- [ ] Tested increasing attempts across delivery failures.
- [ ] Tested listener succeeding before exhausting retries.
- [ ] Tested recovered firing after successful recovery.
- [ ] Tested recoveryFailed when the recoverer throws an exception.
- [ ] Tested offsets/redeliveries in a real container or test broker.

## 19. Usage Principles

RetryListener provides visibility into failed deliveries and recovery outcomes from DefaultErrorHandler. **failedDelivery** shows which attempt a record failed on; **recovered** shows the recoverer completed; **recoveryFailed** shows recovery also ran into an error. Together, these three signals supply the data needed to track retries, diagnose root causes, and operate DLTs.

Keep callbacks concise, emit logs/metrics with bounded cardinality, and attach them to the exact error handler used by your listener containers. Let DefaultErrorHandler manage BackOff, retries, and recovery; use a database or durable workflow if attempt history must survive restarts and retry topics.

## 20. Configuring RetryListener as a Shared Bean

When multiple listeners share the same retry policy, you can declare RetryListener as a Spring bean for reuse. Example:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.RetryListener;

@Configuration
public class RetryObservationConfiguration {

    @Bean
    RetryListener deliveryRetryListener(MeterRegistry registry) {
        return new RetryListener() {

            @Override
            public void failedDelivery(
                    ConsumerRecord<?, ?> record,
                    Exception exception,
                    int deliveryAttempt) {

                registry.counter(
                        "spring.kafka.delivery.failures",
                        "topic", record.topic(),
                        "exception", exception.getClass().getSimpleName()
                ).increment();
            }

            @Override
            public void recovered(
                    ConsumerRecord<?, ?> record,
                    Exception exception) {

                registry.counter(
                        "spring.kafka.delivery.recovered",
                        "topic", record.topic()
                ).increment();
            }

            @Override
            public void recoveryFailed(
                    ConsumerRecord<?, ?> record,
                    Exception original,
                    Exception failure) {

                registry.counter(
                        "spring.kafka.delivery.recovery.failed",
                        "topic", record.topic(),
                        "exception", failure.getClass().getSimpleName()
                ).increment();
            }
        };
    }
}
~~~

Attach this bean to the error handler:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(RetryListener deliveryRetryListener) {
    var handler = new DefaultErrorHandler(
            new FixedBackOff(500L, 3L)
    );

    handler.setRetryListeners(deliveryRetryListener);
    return handler;
}
~~~

A single RetryListener bean can be shared across multiple error handlers if it is stateless or thread-safe. Avoid storing record lists or unsynchronized mutable state inside a singleton bean. If individual listeners need distinct metrics or policies, create separate listeners or pass configuration labels with bounded cardinality.

## 21. Analyzing a Delivery Attempt Example

Suppose a record has topic **orders.created**, partition 2, offset 1048, and event ID **evt-7f9a**. The listener calls a database and hits a deadlock on the first two attempts. The third attempt succeeds.

| Timestamp | Callback / Activity | Attempt | Outcome |
|---|---|---:|---|
| T0 | Listener receives record | 1 | Database deadlock |
| T0 | failedDelivery | 1 | Records first failure |
| T0 + BackOff | Listener receives record again | 2 | Database deadlock |
| T1 | failedDelivery | 2 | Records second failure |
| T1 + BackOff | Listener receives record again | 3 | Database commit succeeds |
| T2 | Listener completes | 3 | Container proceeds with acknowledgment/commit per config |

In this case:

- There were three delivery attempts.
- There were two listener failures.
- There were two retries after the initial delivery.
- The recoverer did not need to run.
- recovered and recoveryFailed were not called for this record.

If the third attempt also failed and the error handler routed the record to a DLT, failedDelivery would log the corresponding failure, and recovered would fire once the DLT recoverer finished. If the DLT publisher threw an exception, recoveryFailed would record the recovery error.

This example clarifies three distinct counts: delivery attempts, listener failures, and recovery outcomes. When building operational reports, define metrics clearly so one record is not counted repeatedly as multiple distinct business events.

## 22. Scope of Attempt State and Audit Requirements

Attempt numbers from RetryListener are helpful for diagnosing active retries, yet are not a durable event audit log. To answer “how many times has this event been attempted across its entire lifecycle, including across deploys/restarts and retry topics?”, a separate state persistence model is needed.

You can store a retry history table with fields such as:

| Field | Meaning |
|---|---|
| **event_id** | Stable identifier of the event |
| **source_topic** | Original topic |
| **source_partition** | Original partition |
| **source_offset** | Original record offset |
| **attempt** | Recorded attempt |
| **failure_type** | Exception category |
| **failure_time** | Failure timestamp |
| **recovery_status** | Unrecovered, recovered, or recovery failed |
| **last_error** | Error details stripped of sensitive data |

If writing audit entries from a callback, writes must not interfere with the retry path. One option is pushing telemetry events into a bounded internal queue or sending them to an observability pipeline. If zero audit loss is required, use a durable mechanism and handle audit write failures explicitly. Never open a business database transaction from a callback and hold the consumer thread waiting on synchronous telemetry writes.

With retry topics, event ID is the correlation key linking topic hops. Attempt numbers can be represented via headers or pipeline metadata depending on configuration. Define a single source of truth for global attempts to avoid double-counting across multiple consumer containers.

## 23. Points to Watch When Upgrading Spring Kafka

RetryListener is a Spring Kafka API, so verify dependency versions when upgrading. Changes may affect:

- Method names and overloads supporting records vs. batches.
- APIs for registering callbacks on error handlers.
- How DefaultErrorHandler handles retries, seeking, and recovery.
- Delivery-attempt header behavior.
- Differences between record listeners and batch listeners.
- Differences between blocking retry and non-blocking retry-topic infrastructure.

When upgrading, compile tests to verify method overrides still match. Integration tests should check callback counts, recovery callbacks, and offset behavior. Do not copy a code sample from a different version if your application runs an older Spring Kafka release.

If a listener uses **@RetryableTopic**, inspect the retry-topic infrastructure separately. DefaultErrorHandler's RetryListener reflects only attempts managed by that handler; it does not automatically aggregate hops across retry topics.

## 24. Operational Principles

Use RetryListener to answer three questions: which attempt a record failed on, whether recovery completed, and if recovery failed, what error occurred. Attach the callback to the right DefaultErrorHandler, classify errors and configure BackOff on the error handler, and keep logs and metrics low-cardinality.

Delivery attempt is the count of deliveries/processing attempts within the observed retry flow. It is not a Kafka offset, not the count of retries after the first delivery, and not the global history of an event. When auditing across restarts or retry topics is needed, persist state durably by event ID and combine it with per-hop metadata.
