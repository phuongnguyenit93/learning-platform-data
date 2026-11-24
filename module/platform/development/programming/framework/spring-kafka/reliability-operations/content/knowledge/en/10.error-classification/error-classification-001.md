# Transient and permanent exceptions

In a Kafka system, not every exception should be handled with the same retry policy. Some errors exist only for a short time, such as when a broker is electing a leader or a network connection was briefly interrupted. Some errors will continue to occur until the application changes the data, schema, configuration, or access permissions. Distinguishing between these two groups helps the consumer recover from temporary incidents without looping infinitely on an unprocessable record.

A **transient exception** is an error that is likely to resolve on its own when external conditions recover or after a waiting period. A **permanent exception** is an error that cannot be fixed simply by retrying the same operation with the same data and conditions. Permanent does not mean the error can never be fixed: data can be corrected, a schema can be updated, or an ACL can be granted. It means that retrying immediately without changing the cause usually yields no result.

In Spring Kafka, error classification determines whether a record is retried on the consumer thread, moved to a retry topic, recovered to a Dead Letter Topic (DLT), or stops the flow for intervention. Classification must be based on the root cause and business context, not just on the exception name.

## 1. Transient and permanent exceptions

### 1.1. Transient exceptions

A transient exception occurs when a component is temporarily unable to complete an operation, but the operation can succeed if retried after the system stabilizes.

Examples:

- A broker or partition leader is temporarily unavailable during a leader election.
- A network connection is briefly dropped.
- A request times out because a broker or dependency is overloaded.
- A database temporarily rejects connections because the pool is exhausted or during failover.
- An HTTP service returns a 503 error during a deployment or recovery.
- Some replica/ISR errors may clear after the broker returns and the ISR is restored.

Retries may be appropriate, but they must have a time limit, backoff, and observability. If the error persists, continuous retrying can increase load on the very dependency experiencing the outage.

### 1.2. Permanent exceptions

A permanent exception reflects a condition that prevents the operation from succeeding if the application resends the same request without changing anything.

Examples:

- The payload is missing a required field or has an invalid format.
- Deserialization or schema validation fails due to incompatible data.
- A business rule rejects an order because its state is invalid.
- A topic or resource is misconfigured.
- A principal lacks permission to access the topic or consumer group.
- A record always exceeds the configured size limit.
- The application uses a data type or contract incompatible with the handler.

These errors require fixing the data, changing configuration/permissions, or routing to an error-handling workflow. Retrying the same record infinitely only causes the consumer to repeat the error, increases lag, and delays other records.

### 1.3. Permanent does not mean unrecoverable

An error can be permanent for the current processing attempt yet fixable in the future. For example, an event using a schema version not yet supported by the consumer will continue to fail until the consumer is updated or the event is transformed.

Classification should answer the question: **If retried immediately with the same record and the same system state, is the probability of success high enough?** If not, immediate retry has no value. Persist the error and provide a path to fix/replay it.

## 2. Classifying by cause rather than by exception name alone

An exception name provides partial information, but the same exception class can represent many different causes. A timeout might be caused by a temporarily overloaded broker, incorrect DNS, a firewall blocking the connection, or a destination service that has stopped running.

| Cause category | Examples | Typical classification | Initial action |
|---|---|---|---|
| Network and connectivity | Disconnect, connection reset, network timeout | Transient if infrastructure is recovering | Retry with backoff; check network and broker |
| Broker/partition | Leader not available, not leader, coordinator unavailable | Usually transient | Let client/container retry within limits; inspect cluster if prolonged |
| Replica and durability | Not enough replicas, insufficient ISR | Can be transient or prolonged | Monitor ISR, replication, and min.insync.replicas |
| Quota/throttling | Request throttled due to quota | Usually recoverable after waiting | Respect throttle/backoff; review quota and load |
| Authentication/authorization | Authentication or authorization failure | Permanent until credentials/ACL change | Fix credentials, principal, or ACL |
| Serialization/deserialization | Malformed payload, incompatible schema | Usually permanent for the current payload | Route record to DLT; fix producer/consumer/schema |
| Business validation | Invalid order state, missing business data | Permanent for the current state | Reject or route to data remediation workflow |
| Size limits | Record/request too large | Permanent if payload/limit does not change | Reduce payload or adjust limit in a controlled way |
| Application resources | Full thread pool, exhausted connection pool | Can be transient or a prolonged capacity issue | Apply backpressure, reduce concurrency, scale capacity appropriately |

Do not label every exception containing the keyword timeout as transient, or every 4xx/5xx error as permanent. You need to inspect the status code, root cause, retry-after, dependency state, and API contract.

## 3. Exception classification in the Kafka client

The Kafka client has its own exception hierarchy. Some errors are subclasses of **RetriableException**, indicating that the operation can be retried under appropriate conditions. The producer client automatically retries certain record-sending errors according to configured retries, backoff, and delivery timeout.

Examples of errors typically tied to broker or connection state:

- **NotLeaderOrFollowerException:** the broker receiving the request is no longer the appropriate leader for the partition; metadata may need to be refreshed.
- **LeaderNotAvailableException:** the partition does not yet have an available leader.
- **NetworkException / DisconnectException:** the request was affected by a connection failure.
- **RequestTimedOutException:** the request did not complete within the wait timeout.
- **NotEnoughReplicasException:** the number of replicas in the ISR does not meet the required condition.

These errors are usually recoverable, though infinite retries are not guaranteed to succeed. For example, the ISR may remain insufficient for a long time because a broker is down; in that case, the cluster must be restored rather than increasing retries.

Some errors usually cannot be fixed by retrying the same request:

- **RecordTooLargeException:** the payload exceeds the limit.
- **TopicAuthorizationException:** the principal lacks permissions on the topic.
- **AuthenticationException:** invalid credentials or security mechanism.
- **SerializationException:** the serializer cannot convert the data into valid bytes.
- **InvalidTopicException:** invalid topic name or configuration.

The list and inheritance hierarchy can change across Kafka client versions. In addition, exceptions thrown by the application or dependency libraries may not belong to the Kafka exception tree. Classify by root cause and actual behavior rather than checking only a single superclass.

## 4. Exception classification in Spring Kafka

Spring Kafka provides error-handling mechanisms for listener containers. For non-transactional flows, **DefaultErrorHandler** is a primary component for configuring retry/backoff and recovery. The error handler receives exceptions from the listener and decides whether the record is retried, recovered elsewhere, or stops processing.

Conceptually, the flow is:

~~~
Listener processes record
        |
        +---- Success
        |       |
        |       v
        |    Commit per AckMode
        |
        +---- Throws exception
                |
                v
        DefaultErrorHandler
                |
          Classify exception
                |
        +-------+--------+
        |                |
    Retryable         Not retryable
        |                |
        v                v
   Backoff/retry     Recoverer / DLT
        |                |
        v                v
   Succeeded?        Record error
        |                |
        v                v
   Continue/commit   Commit per recovery policy
~~~

The error handler needs to know which errors can be retried, the number of attempts, the backoff between attempts, and the action after retries are exhausted. Permanent exceptions should be recovered promptly according to policy rather than stalling the partition on a failing record for a long time.

## 5. Configuring retry and backoff with DefaultErrorHandler

A basic configuration can use **FixedBackOff**:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff = new FixedBackOff(
        1_000L,  // wait 1 second between retries
        3L       // maximum 3 retries
    );

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

In this example, the error handler retries the record according to the backoff before invoking the recoverer. The retry counting method and final behavior must be verified against the Spring Kafka API version in use. Some versions classify certain exceptions as fatal/non-retryable by default.

**ExponentialBackOffWithMaxRetries** can be used to increase the wait interval exponentially:

~~~java
ExponentialBackOffWithMaxRetries backOff =
    new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, backOff);
~~~

With this backoff, the wait interval increases progressively while being capped by the max interval. Exponential backoff helps reduce pressure on a recovering dependency. In multi-consumer environments, consider jitter if the application's retry mechanism supports it to avoid all instances retrying simultaneously.

Backoff must not be chosen in isolation from max.poll.interval.ms. If blocking retries run on the consumer thread, total processing and wait time can prevent the consumer from polling on time. For long retries, consider pausing the container or using retry topics.

## 6. Marking exceptions as retryable and non-retryable

Spring Kafka allows configuring classification for **DefaultErrorHandler**. You can add non-retryable or retryable exceptions according to application policy.

Example of marking validation errors as non-retryable:

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 3L));

handler.addNotRetryableExceptions(
    InvalidOrderException.class,
    UnsupportedEventVersionException.class
);
~~~

Example of marking a dependency error as retryable:

~~~java
handler.addRetryableExceptions(
    InventoryServiceUnavailableException.class,
    TemporaryDatabaseException.class
);
~~~

Method names and precedence rules may vary by version. Check the Javadoc for the Spring Kafka version in use. If classification needs to inspect additional details such as HTTP status, error code, or business state, use an appropriate classifier/custom predicate mechanism rather than classifying strictly by class.

An important point is exception wrappers. A listener may throw a **RuntimeException** wrapping a **SQLException** or **HttpServerErrorException**. If classification only inspects the outer layer, it can misclassify the error. Unwrap the root cause or create clear domain exceptions at the dependency call boundary.

### 6.1. Using domain-specific exceptions

Instead of letting the listener depend directly on every database/HTTP client exception, the service can translate them into exceptions with business meaning:

~~~java
public class InventoryServiceUnavailableException
        extends RuntimeException {

    public InventoryServiceUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}

public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

When calling the service:

~~~java
try {
    inventoryClient.reserve(order);
}
catch (ResourceAccessException ex) {
    throw new InventoryServiceUnavailableException(
        "Inventory service is temporarily unavailable", ex);
}
catch (HttpClientErrorException.BadRequest ex) {
    throw new InvalidOrderException(
        "Order cannot be reserved: " + ex.getStatusCode());
}
~~~

Translation must be based on the actual dependency contract. Not every ResourceAccessException is temporary; misconfigured DNS or TLS can persist until fixed. Not every 4xx is permanent; 429 can often be retried after a specified wait interval.

## 7. Retryable and non-retryable are not always fixed

An exception class may require different classifications depending on context.

Example **TimeoutException**:

- Timeout caused by a recent broker leader change: can be retried.
- Timeout caused by a dependency overloaded for a few seconds: can be retried with backoff.
- Timeout caused by a misconfigured endpoint or permanently blocked firewall: retrying will not help.
- Timeout when calling a payment API where the transaction outcome is unknown: do not resend the payment command as a new request without first checking status using an idempotency key.

Example **HTTP 429 Too Many Requests**:

- Can be retried after the Retry-After interval.
- If the application ignores the wait time and retries continuously, throttling can worsen.
- If the quota is misconfigured or a fixed limit is exceeded, the quota or traffic rate needs to be changed.

Example **HTTP 404 Not Found**:

- If the resource truly does not exist, the error may be permanent for the current event.
- If the event was emitted before the resource was created in another system, the error may be transient due to event ordering or eventual consistency.

Therefore, classification may need to combine exception type, status code, error code, event type, retry-after, and business state.

## 8. Permanent exceptions and Dead Letter Topic

When a record cannot be processed after the retry policy, a **Dead Letter Topic (DLT)** is the place to store the failed record along with metadata for later investigation and handling.

Spring Kafka provides **DeadLetterPublishingRecoverer** to publish records to a DLT. Example:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> template) {

    return new DeadLetterPublishingRecoverer(
        template,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );
}
~~~

This example routes records from the orders topic to orders.DLT, preserving the corresponding partition if the DLT topic has enough partitions. Serializers must be configured for both key/value and headers, and the DLT topic must exist with appropriate replication and retention.

The DLT should preserve useful metadata:

- Original topic, partition, and offset.
- Exception class and sanitized message.
- Failure timestamp and retry count.
- Consumer group or application ID.
- Event ID/business key and correlation ID.
- Schema/version if applicable.

Do not place secrets, tokens, or sensitive payloads into headers/logs without corresponding protection policies.

Once the record is successfully published to the DLT, the error handler can consider recovery complete and allow the original offset to be committed per AckMode. If DLT publishing fails, a policy must be defined: continue retrying recovery, stop the container, or let the record be re-read. Do not commit the original offset before the failed record is durably stored as required by the business.

## 9. Distinguishing blocking retry and non-blocking retry

### 9.1. Blocking retry

Blocking retry re-executes the record on the consumer/listener thread before proceeding to subsequent records according to container semantics.

Advantages:

- Easier to preserve processing order within a partition.
- No additional retry topics required.
- Suitable for transient errors with short recovery times.

Disadvantages:

- The consumer thread is held during retry and backoff.
- A failing record can block subsequent records in the partition.
- Prolonged retries can exceed max.poll.interval.ms.
- A poison record can cause lag to spike rapidly if the policy is unbounded.

### 9.2. Non-blocking retry topic

Non-blocking retry moves the failed record to one or more retry topics, typically with different wait intervals. The main consumer can continue processing subsequent records.

Advantages:

- Does not hold the main consumer waiting through long backoffs.
- Allows setting different retry intervals for each tier.
- Separates the error-processing flow and makes retry backlog observable.

Disadvantages:

- Can alter processing order among records with the same key/partition.
- Requires managing retry topics, retention, routing, and DLT.
- Increases operational streams and replay complexity.
- Has limitations when used with transactions and certain batch configurations.

Spring Kafka supports retry topics via **@RetryableTopic** and corresponding configurations. This mechanism fits when the business allows a failed record to be processed after newer records. If ordering is mandatory, consider blocking retry or designing a flow with controlled ordering.

## 10. Retry and consumer transactions

When a listener container uses a Kafka transaction manager, a listener exception can abort the transaction. Output records and input offsets within the transaction are not committed, so the input record can be re-read.

For transactional listeners, Spring Kafka typically uses **DefaultAfterRollbackProcessor** to decide retry and recovery after rollback. This differs from DefaultErrorHandler in non-transactional flows. Once retries are exhausted, the processor can use a recoverer to send the failed record to the DLT.

Points to determine:

- Which exceptions escaping the listener abort the transaction?
- How many times is the record retried and with what backoff?
- Are outputs sent within the transaction aborted together with the offset?
- Does recovery/DLT participate in the transaction as configured?
- When is the original offset committed?
- Can external database/HTTP side effects outside Kafka be duplicated?

Do not assume a Kafka transaction rolls back database or HTTP calls. If the listener calls an API successfully and then the transaction aborts, a subsequent attempt may call the API again. Use idempotency keys, outbox/inbox, or sagas for side effects outside Kafka.

## 11. Handling serialization and deserialization errors

Serialization/deserialization is a special error group because failures can occur before the listener receives an object.

### 11.1. Serialization on the producer

The producer serializer converts key/value to bytes before sending. If the payload is invalid or the schema is incompatible, the producer may throw **SerializationException**. Retrying with the same object usually cannot fix the data.

Handling approach:

1. Identify the field or schema causing the error.
2. Record the event ID and schema version.
3. Fix the producer or source data.
4. Route invalid events into a controlled rejection/replay workflow.

### 11.2. Deserialization on the consumer

If the Kafka consumer cannot deserialize a record, the listener may not be invoked because the error happens during poll. Spring Kafka provides **ErrorHandlingDeserializer** to place deserialization errors into record headers and allow the container/error handler to process them.

Configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

This example only illustrates the structure; delegate classes and trusted packages must be configured for the actual serializers. For permanent deserialization errors, the error handler should generally recover to a DLT rather than retrying the same byte payload infinitely.

Spring Kafka may treat certain exceptions such as DeserializationException, MessageConversionException, or ConversionException as fatal/non-retryable by default in DefaultErrorHandler. The default list depends on the version; check the Javadoc and current configuration before modifying classification.

## 12. Poison records and impact on consumer groups

A poison record is a record that repeatedly fails processing, usually due to an invalid payload, incompatible schema, or unsatisfiable business state. If the consumer retries infinitely without recovery, the partition can get stuck on that record.

Consequences:

- Consumer lag increases on the blocked partition.
- Subsequent records in the partition are not processed in order.
- The consumer thread is occupied by retries/backoff.
- max.poll.interval.ms may be exceeded if retries take too long.
- Rebalances may occur, causing records to be reprocessed.

Permanent exceptions should be routed to a DLT or corresponding error-handling flow after an appropriate number of retries. If the data can be fixed later, retain enough metadata to replay the exact record and avoid applying business logic twice.

Do not automatically resend every DLT record back to the original topic without checking the cause. If the payload is still invalid, the record becomes a poison record again and creates a loop.

## 13. Designing retry budgets and backoff

Retries need a clear budget. A policy should define:

- Maximum number of retries.
- Maximum total time for a single record.
- Initial wait interval and multiplier.
- Maximum wait interval.
- Jitter if multiple consumers retry concurrently.
- Which exceptions are retryable and which are not.
- Recovery action when retries are exhausted.
- Metrics and alerts for retries/DLT.

Illustrative policy example:

| Retry attempt | Wait interval |
|---:|---:|
| 1 | 500 ms |
| 2 | 1 second |
| 3 | 2 seconds |
| 4 | 4 seconds |
| 5 | 8 seconds |
| After attempt 5 | Send to DLT or recover per policy |

Do not choose backoff based solely on attempt count. Base it on the dependency's expected recovery time and the record processing SLO. If the dependency usually recovers in a few seconds, retrying for tens of minutes holds resources and increases lag unnecessarily.

For blocking retry, total backoff must fit within the poll budget. For non-blocking retry, monitor record age and backlog on each retry topic.

## 14. Idempotency during retries

Retries can cause a business operation to execute multiple times. This is especially dangerous if the listener performs side effects such as debiting funds, creating orders, sending emails, or writing to a database.

An idempotent consumer can store processed event IDs in the same database transaction as the business state change:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Flow:

1. Receive the event and extract a stable event ID.
2. Start a database transaction.
3. Insert the event ID into the processed_events table with a unique constraint.
4. If the ID already exists, do not apply side effects again.
5. If inserting the ID succeeds, update the business data.
6. Commit the database transaction.
7. Only after successful processing, allow the container to commit the offset per AckMode.

Checking the event ID and updating business data must be in the same database transaction. If you check first and write later, two consumers or a replay can both pass the check.

Producer idempotence protects the producer's retry protocol; consumer idempotency protects business logic when records are delivered or replayed multiple times. The two mechanisms complement each other.

## 15. Observing and alerting on exception classification

Tracking only the total error count is insufficient. You must distinguish recovering transient retries from permanent exceptions accumulating in the DLT.

Useful signals:

| Metric/signal | Question to answer |
|---|---|
| Exception count by class/root cause | Which type of error is increasing? |
| Retry attempt rate | Is the consumer retrying frequently? |
| Retry success rate | How many transient errors recover after retry? |
| Retry duration | How long does a record take before succeeding? |
| DLT publish rate | How many records have been recovered to the DLT? |
| DLT lag/oldest record age | Are permanent errors accumulating? |
| Consumer lag by partition | Which partition is blocked by a failing record? |
| Listener processing latency | Which dependency or logic is slowing processing? |
| Rebalance count | Are retries causing the consumer to miss poll intervals? |
| Recovery publish failure | Is the DLT/recoverer failing? |

Logs should include exception class, root cause, topic, partition, offset, event ID, retry count, and correlation ID. Do not log full payloads if payloads contain sensitive data.

Set separate alerts for:

- Sustained increase in transient exception rate.
- Permanent exceptions exceeding threshold per topic.
- DLT oldest record age exceeding SLO.
- Decreasing retry success rate.
- Recovery/DLT publishing failures.
- Consumer lag increasing alongside retries or rebalances.

## 16. Classification and handling runbook

When a listener throws an exception, follow this sequence:

### Step 1: Collect the root cause

- Obtain the exception class and root cause.
- Record the topic, partition, offset, and event ID.
- Check whether the exception is wrapped by the listener, framework, or client library.

### Step 2: Identify conditions that can change

- Is the broker, database, or HTTP dependency recovering?
- Is there a Retry-After header or error code indicating a wait duration?
- Is the payload/schema valid?
- Are credentials, ACLs, and configurations correct?
- Can the business state change so that the operation becomes valid?

### Step 3: Choose the classification

- Transient: retry with backoff and limits.
- Permanent: recover to DLT or rejection/data-remediation workflow.
- Unknown/ambiguous: use a conservative policy, avoid duplicate side effects; store enough information to investigate.

### Step 4: Check delivery semantics

- Is the offset committed only after successful processing/recovery?
- Can the record be replayed?
- Are side effects idempotent?
- If transactional, are outputs and offsets in the same transaction?

### Step 5: Confirm recovery

Monitor retry successes, committed offsets, consumer lag, DLT backlog, and dependency health. After fixing a permanent cause, replay records through a controlled process and preserve the original event ID to prevent duplicates.

## 17. Common design mistakes

| Practice | Consequence | Adjustment |
|---|---|---|
| Retrying every exception infinitely | Poison records stall partitions and increase lag | Classify retryable/non-retryable and set a retry budget |
| Treating every timeout as transient | Misconfigurations or wrong endpoints are retried continuously | Inspect root cause, dependency, and outcome state |
| Treating every 4xx as permanent | Misses retryable 429 cases or ordering-dependent errors | Classify by status/error code and API contract |
| Retrying schema/deserialization errors unboundedly | Same byte payload continues failing | Use ErrorHandlingDeserializer and appropriate DLT |
| Using a DLT without monitoring | Failed records accumulate with no one handling them | Track DLT lag, oldest age, and replay workflow |
| Blocking retry for too long | Consumer misses poll cadence and rebalances | Factor backoff into poll budget or use retry topics |
| Swallowing exceptions and returning normally | Container may commit offset even though business logic did not complete | Let errors reach the error handler or mark rollback appropriately |
| Replaying DLT without idempotency | Side effects are executed repeatedly | Use event ID and consumer idempotency |
| Classifying only by exception wrapper | Confuses transient with permanent or vice versa | Unwrap root cause and translate into clear domain exceptions |

## 18. Exception classification design checklist

Before deploying retry/recovery, determine:

1. What is the root exception and at which step of the consumer lifecycle does it occur?
2. If retried immediately with the same record and state, does the operation have a chance of succeeding?
3. Can the error resolve on its own, or does it require fixing data, schema, configuration, permissions, or business state?
4. Does the Kafka client already perform internal retries for that error?
5. Does the Spring Kafka error handler classify the exception correctly?
6. Do the retry count, backoff, and total time fit within max.poll.interval.ms?
7. When retries are exhausted, is the record sent to a DLT or handled by another recovery mechanism?
8. If DLT publishing fails, is the original offset preserved?
9. Are side effects idempotent when the record is replayed?
10. Do dashboards distinguish transient retries, permanent exceptions, DLT, and recovery failures?

Transient exceptions need a chance to recover with clear backoff and limits. Permanent exceptions need to be persisted, explained, and routed to a remediation or rejection workflow. When Spring Kafka classifies errors accurately, consumers can keep progressing past failing records, reduce wasted retries, and maintain replay capability without duplicating side effects.
