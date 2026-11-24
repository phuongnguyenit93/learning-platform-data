# Producer Exceptions and Classification

Producer exceptions are errors raised when an application prepares, sends, awaits broker acknowledgement, or manages send state for records going to Kafka. In a durable producer model, error handling determines whether a record is retried, rejected, potentially written without received confirmation, or whether the producer must stop to recover state.

Not every exception carries the same meaning. A serialization error occurring before a record is sent requires fixing data or the serializer. A connection drop can be retried automatically by the Kafka client. A timeout after sending a request can leave an ambiguous outcome. A fencing error in a transaction indicates the current producer lost ownership of its transactional ID and must not keep using that transaction.

Properly classifying exceptions lets the application pick the right action: fix data, perform bounded retries, wait for system recovery, route to an error flow, or recreate the producer/transaction. Retrying every exception the same way prolongs incidents and can cause business duplicates.

## 1. Record Send Lifecycle and Where Exceptions Appear

A send through a Kafka producer can fail at multiple stages:

1. The application builds a record and serializers convert key/value to bytes.
2. The producer checks size, metadata, and target partition.
3. The producer places the record in the accumulator and waits for the batch to be sent.
4. The producer sends a request to the partition's broker leader.
5. The broker validates the request, writes the record, and returns an acknowledgement per `acks`.
6. The producer completes the future/callback with success or failure.

Two timing groups must be distinguished:

- **Synchronous errors:** occur directly during the `send()` call, before the application receives a future. Examples include serializer errors, invalid records, unavailable metadata, or the producer failing to allocate buffer space within its wait limit.
- **Asynchronous errors:** `send()` already returned a future, yet the send request later fails or delivery expires. Errors arrive via the callback/future; when using transactions, errors can also surface during flush or commit.

High-level flow:

~~~
Application calls send(record)
          |
          v
Serialize and validate record
          |
     +----+----+
     |         |
   Error     Valid
     |         |
     v         v
Synchronous  Accumulator / batch
exception         |
                v
          Send to broker
                |
          +-----+-----+
          |           |
       Success     Failure
          |           |
          v           v
       Metadata    Internal retry
       succeeds        |
                      v
                Future/callback
                succeeds or fails
~~~

Applications must observe both synchronous exceptions and asynchronous outcomes. Simply wrapping `send()` in a `try/catch` is insufficient for errors that only appear after the call returns.

## 2. Classification by Error Nature

A practical classification looks at where the error happened, whether it can self-recover, and whether the write outcome is clear.

| Group | Example | Meaning | Handling direction |
|---|---|---|---|
| Data / serialization | `SerializationException`, schema errors, or invalid data | Producer cannot build a valid payload | Fix data, serializer, or schema; do not retry the same payload endlessly |
| Config / access permissions | `ConfigException`, `AuthenticationException`, `TopicAuthorizationException` | Client lacks valid config, authentication, or permissions | Fix config, credentials, or ACLs; retry only after conditions change |
| Transient broker / metadata errors | `NotLeaderOrFollowerException`, `LeaderNotAvailableException`, certain replica errors | Partition leader or cluster state is changing | Let producer retry within bounds; check brokers and partitions if prolonged |
| Network / request errors | `NetworkException`, `DisconnectException`, `RequestTimedOutException` | Request did not complete or acknowledgement did not return in time | Check network, brokers, and timeouts; distinguish ambiguous outcomes |
| Delivery time expired | `TimeoutException` when `delivery.timeout.ms` expires | Producer could not report success within the delivery deadline | Inspect root cause; treat as a potentially ambiguous outcome and handle duplicates |
| Resource / size limits | `RecordTooLargeException`, buffer errors, or prolonged metadata wait | Record/request exceeds limits or producer lacks resources | Adjust size, batching, buffers, or load; do not retry unchanged if limits stay fixed |
| Producer / transaction state | `ProducerFencedException`, `InvalidProducerEpochException`, `OutOfOrderSequenceException` | Producer may have lost ownership or sequence state is invalid | Stop/close the failed producer and reinitialize per rules; roll back/recover transactions properly |

Specific exceptions vary by Kafka client, broker, and Spring Kafka versions. Some exceptions belong to the Kafka client's retriable hierarchy; others are only retriable in specific contexts. Rely on exception types and documentation for your running version rather than classifying solely by message strings.

### 2.1. Data and Serialization Errors

The producer must convert keys and values into bytes before sending. If the serializer cannot handle the data type, encounters missing required fields, hits an incompatible schema, or fails conversion, the send can fail immediately inside `send()`.

Example:

~~~java
public class OrderSerializer implements Serializer<OrderCreated> {

    @Override
    public byte[] serialize(String topic, OrderCreated data) {
        if (data == null || data.orderId() == null) {
            throw new SerializationException("orderId is required");
        }
        return encode(data);
    }
}
~~~

If the error stems from an invalid payload, resending the same payload will keep failing. Define which data is valid to emit, validate before sending, and record failures with the business key so data can be fixed or routed to an error-handling flow.

With a schema registry or serializers depending on external services, connection failures to the registry may be transient while incompatible schemas are persistent. These two cases require different policies even though both surface during serialization.

### 2.2. Configuration, Authentication, and Authorization Errors

Errors such as misconfigured bootstrap servers, security protocol, truststore, SASL credentials, or ACLs are usually not resolved by repeated resends.

Common examples:

- `AuthenticationException`: the broker rejects the credentials or authentication mechanism.
- `TopicAuthorizationException`: the principal lacks permission to operate on the topic.
- `ClusterAuthorizationException`: the principal lacks cluster-level permissions.
- `ConfigException`: invalid configuration value or missing mandatory setting.

These typically require configuration or administrative intervention. Applications should emit clear alerts, include safe-to-expose topic/cluster/principal context, and avoid logging credentials or secrets.

### 2.3. Recoverable Broker and Metadata Errors

A partition may be electing a leader, the leader broker may be temporarily unavailable, or metadata cached by the producer may be stale. Exceptions like `NotLeaderOrFollowerException` and `LeaderNotAvailableException` commonly tie to partition state transitions.

The Kafka producer has mechanisms to refresh metadata and retry certain retriable errors. If the cluster recovers within the allowed window, the application can receive success without manually resending records. If errors exceed the delivery deadline, the future ultimately fails and the application must handle that outcome.

`NotEnoughReplicasException` and `NotEnoughReplicasAfterAppendException` must be interpreted in the context of replication settings, `min.insync.replicas`, and `acks`. They signal that brokers did not satisfy the replica condition required by the request. Inspect ISR and cluster health instead of immediately lowering `acks` to silence errors.

### 2.4. Network and Timeout Errors

Dropped connections, request timeouts, or slow broker responses can prevent the producer from receiving an outcome on time. A request may have reached the broker and been written while the acknowledgement was lost on the return path. Thus, a timeout does not always prove a record was not written.

This matters critically when designing application-level retries. Resending as a brand-new business send can make the record appear twice. An idempotent producer protects internal retries of the same producer under the Kafka protocol; it does not automatically recognize two independent `send()` calls from the application as the same business operation.

When the outcome is ambiguous, use a stable event ID/business key and design idempotent consumers if duplicates could affect business state.

### 2.5. Size and Resource Errors

`RecordTooLargeException` can appear when a record or request exceeds limits on the producer, broker, or topic. Check relevant limits such as `max.request.size`, `message.max.bytes`, and topic `max.message.bytes`, as well as size after serialization and compression.

If a record exceeds a fixed limit, retrying the exact same record does not help. You may need to shrink payloads, store large data in object storage and send a reference, or adjust limits carefully across the entire producer-broker-consumer pipeline.

The producer can also wait for buffer space or metadata up to `max.block.ms`. When buffers fill because brokers are slow or the producer cannot drain fast enough, send calls can block and then fail. Increasing buffer memory absorbs short bursts, yet cannot solve sustained input throughput exceeding output throughput.

## 3. Retriable, Non-Retriable, and Fatal Exceptions

The Kafka client classifies exceptions in its type hierarchy, where `RetriableException` denotes errors for which a request may be retried. Even so, applications should not rely on a simple type check to retry infinitely. Combine error type, delivery deadline, transaction state, and business impact.

### 3.1. Retriable Exceptions

Retriable exceptions typically reflect conditions that can change over time: leader transitions, dropped connections, temporarily unavailable brokers, or replicas not yet meeting conditions. The Kafka producer already performs internal retries for many of these errors.

Desired behavior:

1. Allow the producer to execute internal retries within configured limits.
2. Monitor retry counts, send latency, and final failure rates.
3. Perform application-layer retries only after the send has finished failing.
4. Cap application retry duration and attempt counts to avoid infinite loops.

If an error is merely a brief leader election, internal retries are usually sufficient. If errors persist, treat them as a cluster or dependency incident.

### 3.2. Non-Retriable Exceptions

Non-retriable exceptions generally do not clear by resending the same request under the same conditions. Examples:

- Payload cannot be serialized.
- Invalid topic or access denied.
- Invalid client configuration.
- Record consistently exceeds size limits.

The right action is usually fixing the root cause, rejecting invalid data, or routing records to an error-handling workflow. Automatic retries only make sense after the underlying condition changes, such as ACLs being granted or schemas fixed.

### 3.3. Fatal Exceptions and Producers That Cannot Continue

Certain errors leave producer state unsafe to continue using. Examples in transactional publishing:

- `ProducerFencedException`: another producer initialized with the same transactional ID and fenced the current producer.
- `InvalidProducerEpochException`: the producer's epoch is no longer valid.
- Certain `OutOfOrderSequenceException` cases: the producer's sequence is no longer consistent with protocol requirements.

For fencing errors, check whether transactional IDs are duplicated across instances. Every application instance needs a unique transaction ID prefix, and that prefix must remain stable over the instance's lifecycle.

Do not continue sending with a fenced producer. Let the Spring Kafka transaction manager/container handle rollback under its mechanism, close the failed producer, and initialize a new producer with a valid transactional identity. Do not generate a brand-new transactional ID per record; identity must represent the producer instance by design.

## 4. Distinguishing Producer Timeouts

Several timeouts have different meanings and are often confused:

| Setting | Scope | Meaning |
|---|---|---|
| `max.block.ms` | Synchronous send call on client side | Max time producer waits for metadata or buffer space before returning control/error to caller |
| `request.timeout.ms` | Single request sent to a broker | Time client waits for a response to that request |
| `delivery.timeout.ms` | Entire delivery lifecycle of one record | Time limit from when record is ready to send until reporting success or failure, including batching, requests, and retries |
| `Future.get()` timeout | Caller waiting for result | How long the application thread waits on the future; not Kafka's record delivery limit |

`delivery.timeout.ms` is the key overall limit for record delivery outcomes. `request.timeout.ms` must be less than or equal to the delivery limit under valid Kafka client rules. Raising timeouts helps tolerate slow brokers or high-latency networks, yet also delays error reporting and holds resources longer.

For example, `Future.get(2, SECONDS)` can throw `java.util.concurrent.TimeoutException` because the calling thread waited two seconds. That does not automatically cancel the record in the producer accumulator. The future can still complete afterward. Never treat a `get()` timeout as proof Kafka did not write the record.

When the producer throws `TimeoutException` because the delivery deadline expired, the application knows the producer could not confirm success within the configured limit. Depending on `acks`, disconnect timing, and broker state, the actual outcome may remain ambiguous. Avoid re-emitting a business operation as a new event without idempotency safeguards.

## 5. Internal Producer Retries vs. Application Retries

The Kafka producer can automatically retry failed requests when exceptions are retriable. This mechanism uses sequence numbers and idempotence (when enabled) to protect against duplicates from protocol retries within the producer session.

An application retry is a fresh `send()` call after a prior send failed. It can carry a new sequence and be treated as a new record. Thus, the retry layers have distinct responsibilities:

| Retry layer | Who executes it? | Scope | Notes |
|---|---|---|---|
| Internal retry | Kafka producer client | Requests/batches of the current send | Governed by retries, backoff, and delivery timeout; idempotence protects protocol retries |
| Application retry | Application service or workflow | Re-emitting business event after prior failure | Requires stable event ID, retry limits, and ambiguous-outcome handling |
| Consumer retry | Consumer or listener error handler | Reprocessing a record already written to Kafka | Does not replace producer record-send retries |

Do not configure retries at every layer without a shared time budget. For example, a producer retrying internally for 2 minutes, a service retrying 5 times, and a workflow retrying further can prolong incidents, amplify load, and emit the same business action many times.

### 5.1. Baseline Configuration for a Durable Producer

Spring Boot configuration example:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        max.in.flight.requests.per.connection: 5
~~~

This is an illustrative configuration; timeout values must suit cluster latency and application SLAs. For an idempotent producer, Kafka client constraints on `acks`, `retries`, and in-flight requests must remain valid. Modern Kafka versions enable idempotence by default in many setups, though declaring it explicitly makes operational intent clearer.

`acks=all` requires acknowledgement from replicas in the ISR per broker rules. It must be paired with appropriate replication and `min.insync.replicas`. `acks=all` does not mean every replica in the cluster must acknowledge, and cannot compensate for an under-configured replication factor or ISR.

## 6. Handling Exceptions with KafkaTemplate

In Spring Kafka 3.x, `KafkaTemplate.send()` returns `CompletableFuture<SendResult<K,V>>`. Older versions use `ListenableFuture`; adapt examples to your project's library version.

One asynchronous handling approach:

~~~java
public void publish(OrderCreated event) {
    try {
        kafkaTemplate.send("orders.created", event.orderId(), event)
            .whenComplete((result, error) -> {
                if (error != null) {
                    Throwable cause = unwrap(error);
                    handleProducerFailure(event, cause);
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.info("Published orderId={} topic={} partition={} offset={}",
                    event.orderId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset());
            });
    }
    catch (RuntimeException error) {
        // Synchronous error when preparing or registering the send.
        handleProducerFailure(event, error);
    }
}

private Throwable unwrap(Throwable error) {
    if (error instanceof CompletionException && error.getCause() != null) {
        return error.getCause();
    }
    return error;
}
~~~

This example illustrates two error-capture points: `catch` handles errors occurring before the future is returned; `whenComplete` handles asynchronous outcomes. In real applications, `handleProducerFailure` must classify exceptions, record metrics, and select the right policy. Do not merely log and ignore if the event is mandatory to emit.

When using `KafkaTemplate` inside a transactional flow, ensure send errors are not swallowed. Asynchronous exceptions may surface during transaction flush/commit; allow errors to roll back the transaction when business logic requires it. For flows needing definite confirmation of each outcome before proceeding, wait on the future with an appropriate deadline, but avoid unbounded waits or treating caller timeouts as conclusions about broker state.

### 6.1. Bounded Result Waiting

Sometimes the application needs the send outcome immediately in the processing thread:

~~~java
public SendResult<String, OrderCreated> publishAndWait(
        OrderCreated event) {
    try {
        return kafkaTemplate
            .send("orders.created", event.orderId(), event)
            .get(10, TimeUnit.SECONDS);
    }
    catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Interrupted while publishing", ex);
    }
    catch (ExecutionException ex) {
        throw new IllegalStateException("Kafka publish failed", ex.getCause());
    }
    catch (TimeoutException ex) {
        // This is the timeout of the Future.get() wait operation.
        // The send future may still be running.
        throw new IllegalStateException("Timed out waiting for publish result", ex);
    }
}
~~~

Do not call `get()` for every send under high throughput: it turns asynchronous sending into sequential waiting and can degrade throughput. When waiting is necessary, choose timeouts based on business requirements and properly handle cases where the caller times out while the future has not yet finished.

### 6.2. Observing via ProducerListener

Spring Kafka allows attaching a `ProducerListener` to `KafkaTemplate` to receive success/failure callbacks in one central place. This helps with shared logging and metrics, though it does not replace error-handling responsibility in the business code initiating the send.

Logs should include:

- Topic and partition if determined.
- Business key or event ID, avoiding full sensitive payloads.
- Root exception class and classification group.
- Application retry count, if any.
- Correlation ID/trace ID to link with the originating request.

Do not log credentials, tokens, personal data, or sensitive payloads just to debug producer errors.

## 7. Classifying and Choosing an Action

A simple decision flow:

~~~
Producer send fails
        |
        v
Identify root exception
        |
        +--> Data / serialization?
        |       |
        |       +--> Fix payload/schema or route to error flow
        |
        +--> Authentication / authorization / config?
        |       |
        |       +--> Alert and fix configuration/permissions
        |
        +--> Retriable network / broker error?
        |       |
        |       +--> Let internal retries run; monitor delivery timeout
        |
        +--> Timeout / ambiguous outcome?
        |       |
        |       +--> Use stable event ID and control duplicates
        |
        +--> Producer fenced / epoch / fatal sequence?
                |
                +--> Stop current producer and recover transaction
~~~

Once the final exception is obtained, record:

1. The root exception after unwrapping `ExecutionException` or `CompletionException`.
2. Topic and business event ID.
3. Whether the exception is retriable per the Kafka client.
4. Whether the send belongs to a transaction.
5. Whether the record might have been written while the acknowledgement was lost.
6. Next policy: fix data, retry, save pending state, route to DLT/outbox, or halt flow.

Do not use `exception.getMessage().contains("timeout")` or match log strings to classify errors. Messages change across versions and fail to capture full exception state. Rely on exception types, root causes, and send context.

## 8. Application-Layer Retries and Duplicate Control

If the application decides to retry after a future fails, enforce an explicit policy:

- Cap maximum retry attempts or total retry duration.
- Use exponential backoff with jitter so instances do not retry in lockstep.
- Retry only recoverable errors or ambiguous outcomes protected by duplicate controls.
- Keep event ID/business key unchanged across retries.
- Persist pending/dead-letter state so recovery survives restarts.
- Cap total time from receiving business input until publishing succeeds or fails permanently.

Example policy:

~~~java
RetryPolicy policy = new RetryPolicy(
    5,                 // up to 5 attempts at the application layer
    Duration.ofMillis(200),
    Duration.ofSeconds(10),
    true               // exponential backoff with jitter
);
~~~

This is pseudo-code describing policy, not a standard Spring Kafka API. Implement it with a mechanism suited to your application, such as a scheduler, retry library, or durable workflow.

For data errors that cannot be fixed automatically, do not retry repeatedly. Store the failed record with diagnostic details somewhere traceable, allowing operators or a data-repair workflow to replay it later.

### 8.1. Consumer-Side Idempotency

If a producer re-emits a business event due to an ambiguous earlier outcome, the consumer may receive two records with the same event ID. The consumer can use an inbox table or unique constraint to apply business logic only once:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Inside the same database transaction as business updates, the consumer checks and records `event_id`. If the ID already exists, skip the duplicate update. Ensure checking, recording, and business updates occur in the same database transaction to prevent race conditions.

An idempotent consumer does not replace producer idempotence. The two solve different scopes: producer idempotence protects the producer's protocol retries; idempotent consumers protect business state when records are re-emitted or redelivered multiple times.

## 9. Exceptions in Kafka Transactions

Transactional producers introduce states requiring careful handling. When a transaction is open, a failed send can prevent safe commit. Applications must let errors propagate to the transaction boundary and roll back according to Spring Kafka configuration.

### 9.1. Never Swallow Exceptions Inside Listeners

Example listener sending output:

~~~java
@KafkaListener(topics = "orders", groupId = "billing")
public void handle(OrderCreated event) {
    kafkaTemplate.send("billing.requests", event.orderId(),
        createBillingRequest(event));
}
~~~

When the container is configured with a Kafka transaction manager, the transaction wraps both output and input offsets. If the listener catches a send error, merely logs it, and returns normally, the container may treat processing as successful and commit the transaction/offset normally. When an error must trigger rollback, let the exception propagate or mark the transaction rollback-only using the appropriate mechanism.

### 9.2. ProducerFencedException

Fencing errors usually arise when another producer uses the same transactional ID. The broker bumps the epoch so the new producer owns that identity; the old producer is rejected. This commonly stems from non-unique prefixes across pods, two instances initializing the same identity, or an old process not yet shut down.

Actions:

1. Record the transactional ID/prefix and the affected instance.
2. Check how prefixes are generated per pod/instance.
3. Stop using the fenced producer.
4. Let the current transaction roll back or be terminated by the coordinator per Kafka's mechanism.
5. Reinitialize the producer once identity uniqueness is guaranteed.

Do not keep retrying on a fenced producer; this error requires resolving identity ownership.

### 9.3. Timeouts During Transaction Commit

Timeouts during commit differ from caller timeouts waiting on a single send future. The producer may not receive the commit result on time even though the coordinator already processed the request. Therefore, follow the contract of your Kafka client and Spring Kafka version to recover transactions; do not assume commit definitely failed or definitely succeeded.

Do not replay the entire business flow as a new transaction just because the thread calling commit timed out. First resolve producer/transaction state per framework guidelines, then rely on event IDs and idempotency to protect business state if the workflow must rerun.

## 10. Monitoring and Diagnosing Producer Exceptions

Track error rates by exception type, topic, and application. An aggregate error metric can hide one specific topic constantly rejected by ACLs or one partition repeatedly lacking ISR.

Signals to observe:

| Signal | What to detect |
|---|---|
| Send success/failure rate | Success and failure rates per topic |
| Retry rate | Whether the producer is retrying frequently |
| Record error rate by exception class | Which error category is rising |
| Request latency and record queue time | Slow brokers or producer backlog |
| Buffer available bytes / waiting threads | Producer running out of buffer or blocking threads |
| Record send rate and byte rate | Input/output throughput |
| Batch size and compression rate | Batching/compression efficiency |
| Delivery timeout count | Records expiring before delivery |
| Transaction abort/fencing count | Transaction or transactional ID issues |
| Under-replicated partitions and ISR shrink | Broker-side causes triggering producer errors |

Exact metric names depend on Kafka client, Spring Kafka, Micrometer, and monitoring stack. Verify actual exported metrics in your application rather than assuming all versions share identical names.

### 10.1. Quick Diagnostic Runbooks

**When SerializationException increases:**

1. Identify topic, serializer, and payload type.
2. Check schema or input data changes near the onset of errors.
3. Check schema registry dependency errors if applicable.
4. Separate bad data from automatic retries and fix data source/serializer.

**When TimeoutException or NetworkException increases:**

1. Compare request latency, record queue time, and delivery timeout.
2. Check producer-to-broker connectivity, DNS, TLS, and broker request latency.
3. Check partition leaders, ISR, under-replicated partitions, and broker load.
4. Assess ambiguous outcomes of recent sends and duplicate risk upon replay.

**When NotEnoughReplicasException increases:**

1. Check replication factor and `min.insync.replicas`.
2. Check ISR of affected partitions.
3. Identify which broker disconnected or is recovering.
4. Restore replication health before considering durability policy changes.

**When ProducerFencedException appears:**

1. Identify the failing producer's transactional ID/prefix.
2. Check application replica count and how instance identity is generated.
3. Find the older instance or duplicate-identity process.
4. Reinitialize the producer with a unique identity and verify new transactions work.

## 11. Common Design Mistakes

| Practice | Consequence | Adjustment |
|---|---|---|
| Retrying every exception infinitely | Configuration/data errors persist and add load | Classify retriable, non-retriable, and fatal; set retry budgets |
| Catching exceptions only around `send()` | Misses asynchronous errors from future/callback | Handle both synchronous errors and future completion |
| Treating `Future.get()` timeout as record not written | Resending can create duplicates | Distinguish caller wait timeout from delivery timeout |
| Using only application retries with idempotence off | Duplicates from request retries can increase | Enable proper idempotence and use stable event IDs |
| Lowering `acks` to reduce replica errors | Weakens durability while cluster root cause remains | Restore ISR and configure replication properly |
| Swallowing send errors in transactions | Offsets or transactions may commit down the success path | Let errors propagate to transaction boundaries when rollback is needed |
| Sharing transactional IDs across multiple pods | Older producers get fenced | Generate unique transaction ID prefixes per instance |
| Logging only messages without event ID/topic | Hard to investigate and accurately replay | Log exception class, topic, key/event ID, and correlation ID |

## 12. Pre-Handling Classification Checklist

When a producer raises an exception, answer in sequence:

1. Did the error occur synchronously inside `send()` or asynchronously via the future/callback?
2. What is the root exception type after unwrapping `ExecutionException`, `CompletionException`, or Spring wrappers?
3. Is it a data, config/permission, broker/metadata, network/timeout, size/resource, or producer/transaction state error?
4. Can the Kafka client retry this error internally, and how much `delivery.timeout.ms` remains?
5. Could the record have been written by the broker while the acknowledgement was lost?
6. Is producer idempotence enabled and validly configured?
7. Does the send belong to a transaction? Should the exception roll back the transaction?
8. If the application resends, does the event ID stay unchanged and is the consumer idempotent?
9. Can the root cause be fixed before retrying, or should the record route to an error-handling flow?
10. Which metrics, logs, and alerts show whether the error is recovering or spreading?

A durable producer must handle both transient and unrecoverable errors. The Kafka client handles protocol retries within configured limits; the application is responsible for classifying final outcomes, bounding business retries, maintaining traceability, and protecting the system from duplicates. When exceptions involve transactions or producer identity, state recovery must complete before continuing to emit records.
