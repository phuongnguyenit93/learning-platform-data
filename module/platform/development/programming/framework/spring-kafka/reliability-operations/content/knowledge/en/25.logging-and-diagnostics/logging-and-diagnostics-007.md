# Log transaction id

In Spring Kafka, when a message is sent using a Kafka transaction, logging the right **transaction identity** connects events across the producer, broker, listener container, and consumer group in a single investigation. When encountering errors such as transaction aborts, timeouts, or `ProducerFencedException`, logs need to reveal which producer was transacting, which business operation was involved, which record was processed, and how the transaction ended.

However, the phrase **transaction ID** is often overloaded for different values. In Kafka, `transactional.id` is the stable identifier of a transactional producer, used to identify the producer across restarts and enforce fencing. It is **not a fresh ID per transaction commit**. A single producer with the same `transactional.id` can execute many sequential transactions. Kafka also tracks broker-managed producer IDs and epochs; applications usually do not generate those values manually.

For sound diagnostics, log separately:

- **Kafka transactional.id:** the transactional producer identifier configured/allocated by the producer factory.
- **Transaction attempt ID:** an application-generated ID for a specific processing/transaction attempt.
- **Event ID:** the stable business identifier of the message, preserved across retries/re-drives.
- **Trace ID / Span ID:** identifiers for distributed tracing activity.
- **Consumer group, topic, partition, offset:** consumption position and context.
- **Transaction outcome:** committed, rolled back/aborted, or unknown/failure.

This lesson belongs to the **Logging and Diagnostics** topic in Spring Kafka Reliability Operations. Its goal is building logs capable of tracing a transaction across producers, consumer listeners, transaction completion, retries, and DLTs without confusing transaction identity with business identity.

## 1. What does Transaction ID mean in Kafka?

Kafka producer transactions use the `transactional.id` configuration. The producer sends this ID to the transaction coordinator to initialize and manage transactions.

Example:

~~~properties
transactional.id=orders-service-pod-7-0
~~~

This identifier binds to **one logical producer identity**. The producer can run many cycles:

    transactional.id = orders-service-pod-7-0

    initTransactions()
       |
       +--> beginTransaction() -> send A -> commitTransaction()
       |
       +--> beginTransaction() -> send B -> commitTransaction()
       |
       +--> beginTransaction() -> send C -> abortTransaction()

All three transactions share the same transactional.id. Thus, logging only transactional.id identifies the producer without showing which individual execution failed.

To distinguish each execution pass, the application should generate a separate **transactionAttemptId**. This ID is application-managed observability metadata; it does not replace Kafka transactional.id and is not passed into Kafka producer properties.

## 2. Distinguishing identifier types

| Value | Scope | Changes across retries? | Used for |
|---|---|---|---|
| `transactional.id` | Logical transactional producer | Usually kept stable across producer identity lifecycle | Fencing, recovering producer transactions |
| Producer ID | Broker-assigned to producer | Can change when identity reinitializes per protocol | Identifying producer at protocol level |
| Producer epoch | Broker-managed per producer identity | Increments when producer identity is fenced/reinitialized | Blocking stale producers |
| Transaction attempt ID | One application-defined processing/transaction pass | Should be newly created per attempt | Locating logs for a single attempt |
| Event ID | One business event | Kept constant across retries/re-drives of the same event | Idempotency, auditing |
| Correlation ID | One business workflow | Usually preserved across multiple events in a workflow | Joining business steps |
| Trace ID | One distributed trace | May change when retries/re-drives start a new trace | Tracing spans |
| Consumer group ID | Consumer group | Follows group configuration | Tracking offsets and assignments |

Do not use `transactional.id` as an event ID. Do not use trace ID as an idempotency key. Do not substitute producer ID/epoch for business transaction codes.

## 3. Why does Kafka need transactional.id?

Transactional ID allows Kafka to recognize a transactional producer across producer recreations. When a new producer initializes with the same transactional.id, the broker can bump the epoch and **fence** the older producer.

Example:

    Old Producer A:
      transactional.id = orders-pod-7-0
      producerId = 1234
      epoch = 4

    New Producer B initializes with same transactional.id:
      transactional.id = orders-pod-7-0
      broker assigns new epoch

    Producer A using old epoch:
      -> gets fenced
      -> cannot keep committing as an active valid producer

Fencing protects transaction correctness when an old producer stays alive after losing valid control, such as an old process suffering a network partition while a new instance takes over the same identity.

During investigation, logging transactional.id pinpoints the conflicting producer identity. To see which business invocation was running, you still need transactionAttemptId, eventId, and trace context.

## 4. How does Spring Kafka generate transactional.id?

In Spring Kafka, transactional producers are typically created via `ProducerFactory`. With `DefaultKafkaProducerFactory`, the application can configure a transaction ID prefix. The factory combines that prefix with managed suffixes to construct transactional producer IDs matching cached/created producers.

Spring Boot typically configures the prefix via:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-service-${INSTANCE_ID}-
~~~

Here `INSTANCE_ID` is an environment variable supplied by the deployment, such as pod identity. The prefix must be **unique across active application instances** if those instances share the same Kafka cluster and producer identity namespace.

Never configure an identical static prefix across all pods if the factory can generate colliding transactional IDs. Continuous producer fencing can occur when multiple instances share the same transactional.id.

Notes:

- The prefix forms the start of transactional IDs created by the factory.
- The factory may append suffixes and manage cache/suffix reuse.
- Do not concatenate the prefix with a thread number yourself and assume you know the exact runtime transactional.id.
- Check the configuration and API of your actual Spring Kafka version.
- Never assign the exact same transactional.id to multiple concurrently active producers.

## 5. Do not confuse transaction ID with transaction attempt ID

Suppose a listener processes a record with eventId `evt-901`. On the first pass the transaction aborts due to a database/API error; on the next pass the consumer redelivers the record and succeeds.

    Kafka transactional.id: orders-worker-pod-2-0

    Attempt 1:
      transactionAttemptId = txa-01
      eventId = evt-901
      outcome = ABORTED

    Attempt 2:
      transactionAttemptId = txa-02
      eventId = evt-901
      outcome = COMMITTED

Transactional ID stays identical because it is the same logical producer identity. Attempt ID differs because these are two executions. Event ID stays constant because it is still the same business event.

This log structure answers three questions:

1. Which producer identity had trouble?
2. Which attempt committed/aborted?
3. Which business record was reprocessed?

Logging only transactional.id blurs both attempts into events that are hard to separate.

## 6. Fields that belong in transaction logs

A useful log generally includes these fields:

| Field | Example | Purpose |
|---|---|---|
| `kafka.transactional_id` | `orders-pod-2-0` | Producer identity |
| `app.transaction_attempt_id` | `txa-7f3...` | Single execution pass |
| `event.id` | `evt-901` | Business event |
| `correlation.id` | `order-flow-55` | Workflow |
| `trace_id` | `4bf9...` | Distributed trace |
| `span_id` | `00f0...` | Current span |
| `kafka.topic` | `orders.created` | Source/destination topic |
| `kafka.partition` | `2` | Partition |
| `kafka.offset` | `901` | Source offset |
| `kafka.group_id` | `orders-worker` | Consumer group |
| `transaction.phase` | `begin/send/commit/abort` | Stage |
| `transaction.outcome` | `COMMITTED` | Final result |
| `error.type` | `ProducerFencedException` | Error classification |

Not every log requires every field. A `begin` log may not know topic offsets yet; consumer logs need group/topic/partition/offset; producer logs need destination topic and event ID.

Use structured logging to keep fields separate. Avoid flattening everything into one message string if log systems need to filter or aggregate by field.

## 7. Logging transaction ID does not mean logging payloads

Investigating transactions does not require logging the entire message value. Payloads can contain customer info, payment details, addresses, or tokens.

Log:

- Normalized event ID.
- Topic, partition, offset.
- Key if the key contains no sensitive data.
- Transactional ID or producer identity.
- Transaction attempt ID.
- Trace ID and error class.
- Outcome and duration.

Avoid logging:

- Passwords, access tokens, API keys.
- Card numbers, payment details, or unnecessary personal data.
- Full JSON payloads on every retry.
- Unvetted baggage/headers.
- Secrets from Kafka producer/consumer properties.

Transactional ID is normally operational metadata rather than a credential. Still, follow log retention and access-control policies since it can reveal service names, pods, and deployment structure.

## 8. Configuring Kafka transactions in Spring Boot

Example transactional producer configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-service-${INSTANCE_ID}-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        acks: all
        enable.idempotence: true
    consumer:
      group-id: orders-worker
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
    listener:
      ack-mode: record
~~~

Explanation:

- `transaction-id-prefix` causes the producer factory to create transactional producers.
- `enable-auto-commit=false` prevents consumer offsets from auto-committing outside the container/transaction.
- `isolation.level=read_committed` ensures downstream consumers receive only committed transactional output.
- `acks=all` and idempotence support producer durability/safety per cluster settings.
- `ack-mode` controls how the container manages acknowledgments; with transactions, offsets can be sent into the Kafka transaction per container lifecycle.

Spring Boot auto-configuration may create KafkaTransactionManager when a transaction prefix is configured, depending on version and custom factories. If defining custom listener container factories or ProducerFactory beans, verify the transaction manager and KafkaTemplate actually participate in the same transaction.

## 9. Generating transaction attempt ID at the application layer

Kafka does not issue a fresh business-style transactionAttemptId on every beginTransaction call. To log each attempt distinctly, the application can generate a UUID before starting an operation.

Example service sending events in a Kafka transaction:

~~~java
@Service
public class OrderPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(OrderPublisher.class);

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publish(OrderEvent event) {

        String attemptId = UUID.randomUUID().toString();

        log.info(
            "Kafka transaction work started: attemptId={}, eventId={}, topic={}",
            attemptId,
            event.eventId(),
            "orders.created"
        );

        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );

        registerTransactionCompletion(attemptId, event.eventId());
    }

    private void registerTransactionCompletion(
            String attemptId,
            String eventId) {

        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            log.warn(
                "No transaction synchronization active: attemptId={}, eventId={}",
                attemptId,
                eventId
            );
            return;
        }

        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCompletion(int status) {
                    String outcome = switch (status) {
                        case STATUS_COMMITTED -> "COMMITTED";
                        case STATUS_ROLLED_BACK -> "ROLLED_BACK";
                        default -> "UNKNOWN";
                    };

                    log.info(
                        "Kafka transaction completed: attemptId={}, eventId={}, outcome={}",
                        attemptId,
                        eventId,
                        outcome
                    );
                }
            }
        );
    }
}
~~~

Key imports:

~~~java
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
~~~

This example assumes Spring Kafka/Spring Framework supports these APIs and defines a transaction manager named `kafkaTransactionManager`. Event DTO methods `eventId()` and `orderId()` follow an illustrative model.

Key point: `afterCompletion` runs when the Spring transaction finishes. Thus this log reflects the outcome reported by the transaction manager upon completion, rather than assuming commit just because `send()` was invoked.

## 10. Why log after transaction completion?

The snippet below is insufficient to conclude the transaction committed:

~~~java
kafkaTemplate.send("orders.created", key, event);
log.info("Kafka transaction committed");
~~~

`send()` typically returns a future. Calling the method without immediate error does not mean the broker accepted the record or the transaction committed. The producer can still hit send errors, timeouts, or commit failures afterward.

Distinguish milestones:

    T0: Kafka transaction begins
    T1: KafkaTemplate.send() is called
    T2: Producer receives send result
    T3: Listener/service finishes
    T4: Transaction manager commits or aborts
    T5: afterCompletion logs outcome

Logs at T1 should say `send_requested`. Logs at T2 can say `send_acknowledged` if the future completes normally. Only log `COMMITTED` after transaction completion confirms commit.

With `@Transactional`, the interceptor normally commits after the method body returns. Hence a "method finished" log at the end of the method still runs **before** the transaction commits.

## 11. Logging send results separately from transaction outcomes

Attach a callback to the future to capture record send results:

~~~java
CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error(
            "Kafka send failed: attemptId={}, eventId={}, topic={}",
            attemptId,
            event.eventId(),
            "orders.created",
            error
        );
    }
    else {
        RecordMetadata metadata = result.getRecordMetadata();

        log.info(
            "Kafka send acknowledged: attemptId={}, eventId={}, topic={}, partition={}, offset={}",
            attemptId,
            event.eventId(),
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }
});
~~~

Imports:

~~~java
import java.util.concurrent.CompletableFuture;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.support.SendResult;
~~~

Place this inside a method holding `attemptId` and `event`. Spring Kafka 3.x uses CompletableFuture for send APIs; older versions use different future types.

Log two outcomes separately:

- Send future succeeded: the broker acknowledged the send per producer API.
- Transaction commit succeeded: the transaction coordinator completed the transaction.

In a transaction, if a record sends successfully yet the transaction later aborts, downstream `read_committed` consumers do not treat it as committed output.

The future callback may run on another thread. If logs need trace context or MDC, propagate context explicitly into the callback; never assume thread-locals carry over automatically.

## 12. Using MDC to attach attempt ID to all logs in scope

Mapped Diagnostic Context (MDC) enriches logs emitted on the same thread. Set transactionAttemptId, eventId, and correlationId before processing.

~~~java
String previousAttempt = MDC.get("transactionAttemptId");
String previousEvent = MDC.get("eventId");

try {
    MDC.put("transactionAttemptId", attemptId);
    MDC.put("eventId", event.eventId());

    log.info("Starting Kafka transactional publish");

    kafkaTemplate.send("orders.created", event.orderId(), event);
}
finally {
    restoreMdc("transactionAttemptId", previousAttempt);
    restoreMdc("eventId", previousEvent);
}

private void restoreMdc(String key, String previousValue) {
    if (previousValue == null) {
        MDC.remove(key);
    }
    else {
        MDC.put(key, previousValue);
    }
}
~~~

Import:

~~~java
import org.slf4j.MDC;
~~~

This is an illustrative pattern; in real code, the helper method lives in the class and transaction completion is registered before returning.

**Always restore prior MDC** instead of calling MDC.clear() if the scope may execute inside a broader context. Thread pools reuse threads; improper cleanup leaks the prior request's IDs into the next request's logs.

MDC is bound to a thread. It does not propagate automatically across executors, CompletableFuture stages, or callbacks running on other threads.

## 13. Logging after completion once MDC has been cleaned up

An easy detail to miss: with `@Transactional`, `afterCompletion` usually runs after the method body finishes. If MDC is restored in finally before the transaction interceptor commits, the callback may no longer find attempt ID in MDC.

The safe approach is **capturing the ID in a closure** and passing it directly to the completion log:

~~~java
String attemptId = UUID.randomUUID().toString();

TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCompletion(int status) {
            log.info(
                "Kafka transaction outcome: attemptId={}, status={}",
                attemptId,
                status
            );
        }
    }
);
~~~

Do not leave MDC open on the consumer thread just so the callback can read it later. Capturing required fields in immutable variables clarifies context ownership and lowers leakage risk across records.

If transaction synchronization is not active, log a configuration warning or use another instrumentation hook; never pretend a commit outcome was observed.

## 14. Logging runtime transactional.id via ProducerFactory listener

In Spring Kafka, `ProducerFactory` manages creating and closing Kafka producers. Versions supporting `ProducerFactory.Listener` provide callbacks when producers are added to or removed from the factory.

Example:

~~~java
producerFactory.addListener(
    new ProducerFactory.Listener<String, OrderEvent>() {

        @Override
        public void producerAdded(
                String id,
                Producer<String, OrderEvent> producer) {

            log.info(
                "Kafka producer added to factory: producerFactoryId={}",
                id
            );
        }

        @Override
        public void producerRemoved(
                String id,
                Producer<String, OrderEvent> producer) {

            log.info(
                "Kafka producer removed from factory: producerFactoryId={}",
                id
            );
        }
    }
);
~~~

Imports:

~~~java
import org.apache.kafka.clients.producer.Producer;
import org.springframework.kafka.core.ProducerFactory;
~~~

This assumes the app configures a custom ProducerFactory and registers the listener on the factory actually used by KafkaTemplate. Verify listener APIs and the exact meaning of the `id` parameter against the Javadoc of your running Spring Kafka version. In some implementations, that value is the factory's internal producer management ID; **do not assert it is transactional.id unless the version contract specifies so**.

If your goal is logging the actual transactional.id, use callbacks/APIs documented by that version for transactional producer identity or enable Kafka client logs at an appropriate level. Never fabricate the complete ID by concatenating the prefix with an app-chosen thread number.

## 15. Prefix logs vs. runtime producer identity differ

Configuration:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-service-pod-7-
~~~

tells only the prefix. The factory may append suffixes to create distinct producer identities and manage suffixes across cache lifecycles.

A log reading:

~~~text
transactionIdPrefix=orders-service-pod-7-
~~~

does not equal:

~~~text
transactional.id=orders-service-pod-7-0
~~~

To trace the exact fenced producer, logging the factory prefix narrows down the instance yet may be insufficient to pinpoint the specific producer.

Log together:

- service.name and instance/pod ID.
- Normalized transaction-id prefix from configuration.
- Producer factory identifier if supplied by callbacks.
- Kafka client ID.
- Actual transactional.id if supported by version APIs/logs.
- transactionAttemptId for each processing pass.

## 16. Putting transaction IDs in structured logs

With JSON logging, use independent fields:

~~~json
{
  "level": "INFO",
  "message": "Kafka transaction completed",
  "service": "orders-service",
  "instance": "orders-service-pod-7",
  "kafka.transactional_id": "orders-service-pod-7-0",
  "app.transaction_attempt_id": "txa-7f3c",
  "event.id": "evt-901",
  "kafka.topic": "orders.created",
  "transaction.outcome": "COMMITTED"
}
~~~

This is a structural example, not output from a live system.

Benefits:

- Filter by transactional.id when investigating fencing.
- Group by attempt ID to find start/send/commit logs together.
- Trace eventId across retries and DLT.
- Join logs with traceId.
- Query by topic/partition/offset.

Keep field names consistent across services. Service A using `transactionId`, Service B using `tx_id`, and Service C using `kafkaTxn` makes dashboards and queries hard to maintain.

## 17. Logging transaction begin, send, commit, and abort

A readable event logging convention:

| Event name | When logged | Key content |
|---|---|---|
| `kafka.transaction.begin` | When transaction scope starts | attempt ID, producer identity if available |
| `kafka.record.send.requested` | When send is called | topic, event ID, safe key |
| `kafka.record.send.acknowledged` | When send future succeeds | topic, partition, offset |
| `kafka.transaction.commit` | When transaction completion confirms commit | attempt ID, duration |
| `kafka.transaction.rollback` | When transaction completion confirms rollback | attempt ID, exception category |
| `kafka.transaction.outcome_unknown` | When client cannot confirm outcome | attempt ID, error, recovery action |

Not every transaction manager exposes callbacks for every phase with identical semantics. You may need to combine application logging, Spring transaction synchronization, and Kafka client logs.

Avoid logging `commit` right after `send()`. Use `send_requested` or `send_acknowledged` for those respective milestones.

## 18. Measuring transaction duration

Record the start time and compute duration in the completion callback:

~~~java
long startedNanos = System.nanoTime();
String attemptId = UUID.randomUUID().toString();

TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCompletion(int status) {
            long durationNanos = System.nanoTime() - startedNanos;

            log.info(
                "Kafka transaction completed: attemptId={}, status={}, durationMs={}",
                attemptId,
                status,
                TimeUnit.NANOSECONDS.toMillis(durationNanos)
            );
        }
    }
);
~~~

Imports:

~~~java
import java.util.concurrent.TimeUnit;
~~~

Use `System.nanoTime()` for duration measurement because it is a monotonic clock suited for elapsed intervals. Use `Instant.now()` or log timestamps for wall-clock timestamps.

Duration in a Spring transaction callback spans from measurement start to completion callback, which may cover business processing, sends, commit/abort, and other synchronizations depending on registration point. Label the scope clearly as `application_transaction_scope_duration` rather than calling it broker-only commit latency.

To measure coordinator commit duration alone, use Kafka client metrics or dedicated instrumentation at the producer/transaction manager layer.

## 19. Attaching event ID and Kafka record coordinates

In a consumer listener, log record coordinates to find the message back in Kafka:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "orders-worker"
)
public void consume(ConsumerRecord<String, OrderEvent> record) {

    OrderEvent event = record.value();

    log.info(
        "Consuming Kafka record: eventId={}, topic={}, partition={}, offset={}, key={}",
        event.eventId(),
        record.topic(),
        record.partition(),
        record.offset(),
        safeKey(record.key())
    );

    orderService.process(event);
}
~~~

`safeKey` is an application helper deciding whether the key can be logged or must be masked. If keys hold emails/customer identifiers or sensitive info, never log raw values.

Topic/partition/offset coordinates are crucial for investigating consumer lag, DLT metadata, and redeliveries. Offsets are unique within a partition, not across the entire topic; always log both topic and partition.

When a listener reprocesses the same record, eventId and coordinates may remain identical while transactionAttemptId should differ per attempt.

## 20. Consumer transactions: logging group and source offset

In a transactional listener, Kafka outputs and input offsets can share the same Kafka transaction. Logs should reflect that link:

    Transaction attempt txa-01
      groupId = orders-worker
      input = orders.created-2@901
      output = orders.validated-1@440
      outcome = COMMITTED

If the transaction aborts:

    Transaction attempt txa-02
      groupId = orders-worker
      input = orders.created-2@901
      output send was acknowledged
      outcome = ROLLED_BACK

The consumer may redeliver offset 901 on the next pass. Outputs from the aborted transaction are not seen as committed by `read_committed` downstream consumers.

Never log the source offset as committed right when the listener method finishes. In container-managed transactions, the container sends offsets to the transaction and commits afterward. Log outcomes at the proper completion point.

If a poll yields multiple records, the transaction boundary may cover multiple records depending on listener type/config. Log an appropriate list or coordinate summary instead of assuming one transaction holds exactly one offset.

## 21. Handling retries: keep event ID, create new attempt ID

A record may retry multiple times:

    eventId = evt-901

    attemptId = txa-A -> exception -> rollback
    attemptId = txa-B -> timeout   -> rollback
    attemptId = txa-C -> success   -> commit

Keep stable:

- eventId.
- Original topic/partition/offset (while still processing the same record).
- Business correlation ID.
- Payload identity or schema version as applicable.

Typically changing:

- transactionAttemptId.
- spanId.
- Consumer instance/client ID if rebalanced to another pod.
- Delivery attempt count.
- Processing duration and exception.

If a retry topic creates a new record on another topic, log both original source coordinates and current retry topic coordinates. Do not log only the current topic, since investigators need to know where the record originated.

## 22. Logging when a transaction aborts

A rollback log should state:

- attempt ID.
- transactional.id/producer identity if identifiable.
- event ID and source coordinates.
- Exception class.
- Retry attempt/backoff if known.
- Transaction outcome.
- Consumer group and instance.
- Correlation/trace IDs.

Example:

~~~text
level=WARN
event=kafka.transaction.rollback
transactionAttemptId=txa-02
transactionalId=orders-pod-7-0
eventId=evt-901
sourceTopic=orders.created
sourcePartition=2
sourceOffset=901
groupId=orders-worker
exception=TransientDataAccessException
outcome=ROLLED_BACK
~~~

Do not print payloads or full stack traces on every retry if log volume is high. Log exception classes and stack traces on the first/last failure or per sampling policy while keeping enough context to trace the error.

Rollback does not imply the listener made no side effects outside Kafka. If DB/API calls already succeeded before the Kafka transaction aborted, idempotency and separate business outcome logs are needed.

## 23. Logging ProducerFencedException

One critical error tied to transactional.id is `ProducerFencedException`.

Example error handling at the application boundary:

~~~java
try {
    publisher.publish(event);
}
catch (ProducerFencedException exception) {
    log.error(
        "Kafka transactional producer fenced: eventId={}, instance={}",
        event.eventId(),
        instanceId,
        exception
    );
    throw exception;
}
~~~

ProducerFencedException may arrive wrapped in another exception depending on the commit path and Spring Kafka version. In practice, walk the cause chain to detect the underlying exception rather than matching only top-level type.

Investigation:

1. Log transactional.id or producer factory identity.
2. Compare instances/pods using the same identity.
3. Check rolling updates, zombie processes, and shutdowns.
4. Verify transaction-id-prefix is unique per instance.
5. Inspect producer factory lifecycle/cache and when new producers initialize.
6. Verify consumer group and transaction outcome.
7. Fix identity/lifecycle before endlessly restarting pods.

Never immediately retry using the same fenced producer. An old producer cannot become valid again by repeating the same commit call.

## 24. Logging timeouts and uncertain outcomes

A timeout during transaction commit does not always prove the broker did not commit. The response may have been lost after the broker completed commit, leaving client state indeterminate.

Log example distinguishing uncertainty:

~~~text
event=kafka.transaction.commit_attempt
transactionAttemptId=txa-77
outcome=UNKNOWN
error=TimeoutException
action=inspect_before_retry
~~~

Do not log `ABORTED` solely because the client missed the commit response. If the broker already committed, retrying the business command under a new event ID can duplicate outputs.

When outcome is unknown:

- Keep eventId/commandId stable.
- Check transaction/client logs and downstream read_committed state if possible.
- Use idempotent consumers downstream.
- Reconcile using business/audit state.
- Do not blindly commit source offsets or skip the record.
- Design retries so re-executing the same business command does not duplicate side effects.

The Kafka transaction protocol handles many internal errors, yet applications must still log uncertain states honestly.

## 25. Logging with KafkaTemplate.executeInTransaction

KafkaTemplate provides `executeInTransaction` for certain producer-initiated use cases, creating a local transaction for the callback.

Example:

~~~java
public void publish(OrderEvent event) {

    String attemptId = UUID.randomUUID().toString();

    kafkaTemplate.executeInTransaction(operations -> {
        log.info(
            "Kafka transaction callback started: attemptId={}, eventId={}",
            attemptId,
            event.eventId()
        );

        operations.send(
            "orders.created",
            event.orderId(),
            event
        );

        return null;
    });

    log.info(
        "Kafka executeInTransaction returned: attemptId={}, eventId={}",
        attemptId,
        event.eventId()
    );
}
~~~

Here the log after `executeInTransaction` returns only executes if the callback/transaction completes normally per API contract. If an exception is thrown, that line does not run unless placed in catch/finally.

Distinguish this API from a `@Transactional` method participating in KafkaTransactionManager. `executeInTransaction` has its own semantics and should not be assumed to join an active transaction the same way an ordinary `KafkaTemplate.send()` does.

For code needing detailed commit/abort logs, combine exception handling and timing around the call while checking your API version.

## 26. Logging with @Transactional and KafkaTransactionManager

A method can explicitly name its transaction manager:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publish(OrderEvent event) {
    kafkaTemplate.send("orders.created", event.orderId(), event);
}
~~~

This requires:

- KafkaTransactionManager configured.
- A transaction-capable ProducerFactory.
- KafkaTemplate using the matching ProducerFactory.
- Method invocation through the Spring proxy.
- Rollback-triggering exceptions not caught and swallowed.
- Properly understood transaction boundaries if joining an existing transaction.

When invoked via proxy, the interceptor begins/commits the transaction around the method call. A log at method entry starts business work; a log at the end of the body still runs before commit. To log completion, use transaction synchronization or instrumentation at the transaction manager.

If multiple transaction managers exist, always specify the manager name in the annotation so you never log a database transaction and mistake it for a Kafka transaction.

## 27. Does Spring's transaction name replace transactional.id?

Spring can expose the current transaction name via TransactionSynchronizationManager in certain transaction contexts:

~~~java
String springTransactionName =
        TransactionSynchronizationManager.getCurrentTransactionName();
~~~

This value is **Spring transaction metadata**, not Kafka transactional.id. It may be the method/class name used by the transaction interceptor, or null depending on context.

Log them separately:

~~~text
spring.transaction.name=OrderPublisher.publish
kafka.transactional.id=orders-pod-7-0
app.transaction_attempt_id=txa-77
~~~

Do not populate `transactional.id` with `getCurrentTransactionName()`. Those two values answer different questions.

Similarly, `TransactionSynchronizationManager.isActualTransactionActive()` only tells whether Spring has an active transaction on the thread context, not whether the broker committed.

## 28. Logging producer ID and epoch

The Kafka broker manages producer IDs and epochs for transactional producers. Producer fencing relates to epochs because brokers reject stale producers after identity reinitialization.

These values help when reading Kafka client/broker logs, yet Kafka's public Producer API does not provide a simple, portable getter for applications to read producer ID/epoch for every transaction.

Do not use reflection to read private fields of KafkaProducer or TransactionManager just to log them. Client internals can change across versions, and unsafe access can break the producer.

Recommended approach:

- Use framework-supported transactional.id/factory identity.
- Enable controlled Kafka client DEBUG/TRACE logs during investigations.
- Use broker logs and appropriate metrics to correlate fencing.
- Record instance ID and transactionAttemptId at the application layer.
- Never fabricate fake producer IDs/epochs.

## 29. Selectively enabling Kafka client logs

In Spring Boot, you can temporarily raise log levels for relevant packages:

~~~yaml
logging:
  level:
    org.springframework.kafka.transaction: DEBUG
    org.springframework.kafka.core.KafkaTemplate: DEBUG
    org.springframework.kafka.listener: INFO
    org.apache.kafka.clients.producer.internals.TransactionManager: DEBUG
    org.apache.kafka.clients.consumer.internals.ConsumerCoordinator: INFO
~~~

Exact logger names and content depend on version. Some internal Kafka packages are not stable public APIs; logs may change when upgrading the client.

Best practices:

1. Enable DEBUG/TRACE only during investigations or scoped to needed instances.
2. Estimate log volume before enabling cluster-wide.
3. Never log producer/consumer configs containing credentials.
4. Collect sufficient logs before/after errors, not just the final exception line.
5. Lower log levels once the incident closes.
6. Pair with structured application logs to query attempt/event IDs.

Never leave TRACE continuously enabled for producers handling tens of thousands of messages per second without evaluating I/O and storage costs.

## 30. Logging correlation ID and trace context with transaction ID

A good log bridges both Kafka operations and tracing:

~~~text
service=orders-service
instance=orders-pod-7
transactionalId=orders-pod-7-0
transactionAttemptId=txa-77
eventId=evt-901
correlationId=order-flow-55
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
topic=orders.created
partition=2
offset=901
phase=commit
outcome=COMMITTED
~~~

Each ID serves one goal:

- transactionalId locates producer identity.
- transactionAttemptId joins logs within one transaction attempt.
- eventId tracks the same event across retries/re-drives.
- correlationId tracks the business workflow.
- traceId/spanId opens the distributed trace.
- topic/partition/offset locates the record in Kafka.

When using Micrometer Tracing, traceId/spanId can populate MDC per config. Transaction attempt ID still needs separate management; never assign traceId to transactional.id.

## 31. Consumer retries and delivery attempts

When a listener fails, Spring Kafka can retry via DefaultErrorHandler or AfterRollbackProcessor depending on container type and transaction setup. A record can undergo multiple deliveries.

Logs should record:

~~~text
eventId=evt-901
sourceTopic=orders.created
sourcePartition=2
sourceOffset=901
deliveryAttempt=2
transactionAttemptId=txa-B
transactionalId=orders-worker-pod-2-0
outcome=ROLLED_BACK
exception=TransientDataAccessException
~~~

The API for reading delivery attempt headers depends on error handling/version. If no header or reliable API is present, log retry stages from the error handler or application-managed metadata.

Do not increment an attempt counter in an in-memory variable detached from the record because rebalances/restarts reset it. If durable attempt counts are needed, use headers/retry-topic metadata or a policy-governed state store.

When the same record reprocesses on another pod, transactional.id can change due to instance identity; eventId and source coordinates link the two executions.

## 32. How should DLT and re-drive log identity?

When a record moves to a DLT, retain details needed for investigation:

- Original Event ID.
- Original topic/partition/offset.
- Exception type and safe metadata.
- Transaction attempt ID of the recovery pass.
- Recoverer's transactional producer identity if applicable.
- DLT topic/partition/offset.
- Recovery transaction outcome.
- Re-drive operation ID when replayed.

Example:

~~~text
event=kafka.dlt.recovery
eventId=evt-901
source=orders.created-2@901
destination=orders.created.DLT-2@44
transactionAttemptId=txa-recover-01
transactionalId=orders-recovery-pod-1-0
outcome=COMMITTED
~~~

If DLT publish succeeds yet source offset commit fails, the source record may redeliver and recovery may run again. Design recovery to be idempotent and log both coordinates.

Never treat the existence of a DLT record as proof the source offset committed. The two operations are atomic only when included together in an appropriate Kafka transaction.

## 33. Batch listeners: one transaction with multiple records

With batch listeners, a single transaction can cover multiple input records. One transactionAttemptId can apply to the whole batch, while each record has its own eventId and coordinates.

Example:

    transactionAttemptId = txa-batch-12

    inputs:
      orders.created-0@100 / evt-A
      orders.created-0@101 / evt-B
      orders.created-1@220 / evt-C

    outputs:
      orders.validated-0@500
      orders.validated-1@610

    outcome = COMMITTED

Do not log a single eventId to represent the entire batch when the batch holds multiple events. Log batch size and a summary, plus record-level details as needed.

If one failing record aborts the transaction, outputs across the whole transaction can abort; logs should show the shared transactionAttemptId and the failing record if accurately provided by the framework.

## 34. Kafka transactions alongside database transactions

A listener can both write to a database and publish Kafka output. Two resource managers maintain separate transactions unless using a fully configured distributed transaction protocol.

Example:

    DB transaction:
      UPDATE orders

    Kafka transaction:
      send orders.updated

If the Kafka commit aborts after the database committed, database changes do not roll back automatically. When the source record redelivers, DB side effects may run again.

Logs should separate:

- `db.transaction_attempt_id`
- `kafka.transaction_attempt_id`
- `kafka.transactional.id`
- `event.id`
- `db.outcome`
- `kafka.outcome`

Never reuse one `transactionId` field for both DB and Kafka, as they can collide or become ambiguous.

If using a transactional outbox, the DB transaction inserting the outbox row and the publisher transaction sending to Kafka are two distinct phases. Use eventId to join them.

## 35. Never use transaction ID as a metric label

Logs and metrics serve different goals. Transactional IDs scale with instance count, producer caches, and deployment lifecycles; transaction attempt IDs are typically fresh UUIDs per execution.

Putting these into Prometheus labels:

~~~text
kafka_transaction_duration_seconds{
  transactional_id="orders-pod-7-0",
  transaction_attempt_id="txa-..."
}
~~~

explodes time-series counts, causing high cardinality and storage cost.

Use low-cardinality metric labels instead:

- application/service.
- consumer group.
- stable listener ID.
- topic (if topic count is controlled).
- outcome: committed/aborted/unknown.
- normalized exception category.

To locate a specific transaction, use structured logs or tracing. Never put attempt ID, event ID, offset, or span ID into default metric labels.

## 36. Log sampling and avoiding excessive volume

If every record starts a transaction and writes 4–5 lines for begin/send/commit, log volume grows huge.

Example:

    20,000 transactions/s
    4 log lines/transaction
    = 80,000 log events/s

Strategies:

- Log transaction starts at DEBUG.
- Log commit successes at DEBUG or use counter/summary metrics.
- Log rollbacks/failures at WARN/ERROR per policy.
- Log full stack traces on first/last failure or under controlled sampling.
- Always keep eventId and coordinates in critical logs.
- Log batch summaries instead of per-record payloads.
- Keep structured logs for lifecycle events and failures needing investigation.

Never sample away severe failures or unknown transaction outcomes. At high success volume, metrics usually beat emitting an INFO line per transaction.

## 37. Correlating with ConsumerStoppedEvent and fencing

When a consumer container stops because its transactional producer was fenced, a ConsumerStoppedEvent may fire with a matching reason depending on Spring Kafka version.

Logs should connect:

    ConsumerStoppedEvent
       |
       +-- reason=FENCED
       +-- listenerId=ordersListener
       +-- instance=orders-pod-7
       |
       +-- Kafka client logs
       |      transactional.id=orders-pod-7-0
       |      ProducerFencedException
       |
       +-- application transaction logs
              attemptId=txa-77
              eventId=evt-901
              outcome=UNKNOWN/ROLLED_BACK

Not every ProducerFencedException fires through the exact same event or callback order. Use logs/events from your running version and cross-check group/transaction state.

If a consumer has lost ownership, never use transaction ID logs as justification to force-commit offsets from the old owner. Fencing and group ownership are separate safeguards; logs aid diagnostics, not authorization to bypass locks.

## 38. Testing transaction ID logging

A unit test can verify adapters/logging services receive normalized metadata. However, proving transactional producer identity and transaction completion requires integration tests against a Kafka broker.

Scenarios:

### 38.1. Happy path

1. Configure a dedicated transactional.id prefix for the test instance.
2. Send an event with a fixed eventId.
3. Assert logs contain transactionAttemptId.
4. Assert transaction completion logs outcome COMMITTED.
5. Assert output appears to a read_committed consumer.
6. Cross-check topic/partition/offset against send acknowledgment logs.

### 38.2. Abort

1. Send output inside a Kafka transaction.
2. Intentionally throw an exception before commit.
3. Assert completion logs record ROLLED_BACK or matching status.
4. Assert downstream read_committed sees no aborted output.
5. Assert a new attempt ID on retry.
6. Assert eventId stays unchanged.

### 38.3. Producer fencing

1. Use a controlled test transactional.id.
2. Initialize a new producer with the same identity to fence the old producer per protocol.
3. Assert client logs/exceptions show fencing.
4. Assert application logs carry producer identity and instance.
5. Never reuse this ID in shared or production environments.
6. Fix the identity and verify recovery.

### 38.4. Timeout / uncertain outcome

1. Simulate a network/response failure during commit.
2. Assert logs record timeout/unknown when outcome cannot be determined.
3. Check downstream read_committed and business state by eventId.
4. Retry per idempotency policy without creating unintended new business commands.

### 38.5. Retry and DLT

1. Send a failing record so the transaction rolls back.
2. Observe a new transactionAttemptId on each attempt.
3. After retries exhaust, publish to DLT per configuration.
4. Log DLT destination and source coordinates.
5. Assert source offset recovery only registers upon successful recovery mechanics.
6. Re-drive with the original eventId and a new attempt ID.

Do not assert a hardcoded transactional.id suffix if the factory uses cache/suffix allocation that can vary across runs. Tests should assert valid ID format/namespace per version contract or use documented producer-factory callbacks.

## 39. Dashboards and log queries

Useful queries in a centralized log system:

**Find all attempts for one event:**

~~~text
event.id = "evt-901"
~~~

**Find all transactions for a producer identity:**

~~~text
kafka.transactional_id = "orders-pod-7-0"
~~~

**Find aborted transactions:**

~~~text
event = "kafka.transaction.rollback"
~~~

**Find uncertain outcomes:**

~~~text
transaction.outcome = "UNKNOWN"
~~~

**Find fencing errors:**

~~~text
error.type contains "ProducerFencedException"
~~~

**Find a specific consumer record:**

~~~text
kafka.topic = "orders.created"
AND kafka.partition = 2
AND kafka.offset = 901
~~~

Exact query syntax depends on Elasticsearch/OpenSearch, Loki, Splunk, or other backends. Examples show logical fields only.

Dashboards can aggregate transaction duration, commit/abort rates, and fencing counts; log searches drill down into specific attempts/events.

## 40. Runbook when transaction IDs show conflict signs

When seeing ProducerFencedException or repeated transaction aborts tied to the same producer identity:

1. Identify service, instance, and transactional.id/factory identity.
2. Find all pods/processes logging the same identity.
3. Inspect deployment rolling updates, zombie processes, and shutdowns.
4. Verify transaction-id-prefix is unique across instances.
5. Check producer factory suffixes/caches and lifecycle.
6. Check client/broker logs for producer fencing/epoch bumps.
7. Identify impacted transactionAttemptId and eventId values.
8. Determine whether output/offset transactions committed, aborted, or remain unknown.
9. Check consumer group, partition ownership, and redeliveries.
10. Verify non-Kafka side effects are idempotent.
11. Fix identity/lifecycle configuration.
12. Perform a controlled restart once the root cause is resolved.
13. Monitor abort rates, stopped events, lag, and duplicate detection.

Never delete offsets or reset groups to cure producer fencing. This error relates to producer identity/lifecycle; changing consumer offsets does not fix the cause.

## 41. Common logging mistakes

| Mistake | Consequence | Right approach |
|---|---|---|
| Treating transactional.id as per-transaction ID | Cannot tell attempts apart | Add transactionAttemptId |
| Using eventId as transactional.id | Producer identity changes per record, misusing protocol | Keep factory-managed transactional.id |
| Concatenating prefix + thread number | Logs may not match runtime ID | Use version-supported APIs/factory identity |
| Logging commit right after send() | False success when transaction aborts | Log outcome after completion |
| Using Spring transaction name as Kafka transactional.id | Confuses two identity layers | Log separate fields |
| Logging full payloads to trace transactions | Data leaks, huge log volume | Log event ID and coordinates |
| Omitting topic/partition/offset | Hard to locate source record | Include record coordinates |
| Using trace ID as dedup key | Replays can mint new traces | Use eventId |
| Putting transactionAttemptId in metric labels | High cardinality | Put IDs in logs/traces |
| Failing to restore MDC | Stale IDs leak to next record | Save/restore MDC |
| Assuming MDC crosses async callbacks | Logs lose or swap trace context | Propagate context explicitly |
| Treating send future success as transaction commit | Output may still abort | Log send and transaction outcomes separately |
| Blindly retrying after timeout | Can duplicate business output | Keep eventId, reconcile outcome |
| Leaving DEBUG/TRACE on cluster-wide | Log floods and high costs | Enable selectively with time limits |
| Using reflection to read producer epoch | Couples to client internals, fragile | Use client/broker logs and supported APIs |

## 42. Production implementation checklist

Before relying on transaction ID logging in operations:

- Defined transactional.id as a stable producer identity, not a per-transaction attempt ID?
- Is transactional ID prefix unique across active instances?
- Is there a dedicated transactionAttemptId per processing/transaction pass?
- Does Event ID stay stable across retries/re-drives?
- Are topic, partition, offset, and consumer group logged when processing inputs?
- Are send requested, send acknowledged, and transaction committed clearly separated?
- Are rollbacks/aborts and unknown outcomes logged?
- Are transaction synchronization or proper instrumentation used to record completion?
- Have ProducerFactory listeners/APIs been verified for your version?
- Are instance/client IDs logged to investigate fencing?
- Are traceId/spanId and correlationId logged when tracing is enabled?
- Is MDC properly saved/restored, especially in thread pools?
- Are secrets, PII, and full payloads excluded from logs?
- Are transactional/attempt/event IDs kept out of metric labels?
- Are sampling/log-level policies tuned to throughput?
- Do integration tests cover commit, abort, fencing, timeouts, and DLT?
- Are runbooks ready to verify transaction outcomes before retrying?
- Are non-Kafka database/API side effects protected by idempotency?

## 43. Conclusion

**Logging transaction id** in Spring Kafka requires distinguishing producer transactional.id from application transactionAttemptId, Kafka protocol producer ID/epoch, and business event ID. Transactional ID identifies the producer and aids fencing investigations; attempt ID links logs within one execution pass; event ID tracks the same record through retries and recovery.

Effective logs capture begin, send, and commit/abort stages along with topic/partition/offset, group, instance, trace, and error categories. Above all, log COMMITTED only after transaction completion is confirmed; a successful send future or listener method return alone does not prove the transaction committed.

On timeouts or fencing, logs must honestly reflect known state and keep unknown outcomes distinct until resolved. Combining structured logs, Kafka client metrics, Spring transaction lifecycles, tracing, and idempotency lets operations pinpoint the right producer/attempt/record without sacrificing delivery guarantees or exposing business data.
