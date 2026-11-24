# Log exception chain

In a real-world Spring Kafka system, an error rarely reaches the logger as a bare primitive exception. A record that fails deserialization can arrive in the error handler wrapped by Spring Kafka; a database call failure can be translated into `DataAccessException` and wrapped in a business exception; a `KafkaTemplate.send(...)` failure can arrive inside `CompletionException` or `ExecutionException`; and an error while writing to a dead-letter topic (DLT) can obscure the original processing failure. If you only log `ex.getMessage()`, the on-call engineer easily sees “Listener method failed” or “Execution failed” without knowing whether the root cause was malformed JSON, a database timeout, permission denied, or a fenced producer.

**Logging the exception chain** is the practice of capturing and analyzing the **causal relationship chain of a Throwable** — the current exception, nested `cause` exceptions, and `suppressed exceptions` when applicable — along with enough Kafka context to identify the record, processing stage, and recovery action. The goal is not to print every stack trace on every retry; the goal is to **preserve causal details, log at the right boundary, classify errors, and protect sensitive data**.

This lesson explains the Java exception chain mechanism, right/wrong SLF4J patterns, common wrapper classes in Spring Kafka, logging in listeners and error handlers, pre-listener deserialization errors, asynchronous producers, transactions, retry/DLT, structured logging, tracing, testing, and production diagnostic runbooks.

## 1. What is an exception chain?

Java `Throwable` has a causal chain represented by `getCause()`. The outer exception typically describes **the processing context**, while deeper exceptions describe **the underlying technical failure**.

Example:

~~~text
ListenerExecutionFailedException
  message: "Listener method failed"
    |
    +-- caused by: OrderProcessingException
          message: "Cannot persist order event"
            |
            +-- caused by: DataAccessResourceFailureException
                  message: "Database unavailable"
                    |
                    +-- caused by: SocketTimeoutException
                          message: "Read timed out"
~~~

In the chain above:

- **Outer exception** shows the error surfaced at the listener boundary.
- **Business exception** shows which business action failed.
- **Data access exception** shows the database layer was impacted.
- **Root cause** reveals a deep network communication timeout.

If you only log:

~~~java
log.error("Kafka listener failed: {}", exception.getMessage());
~~~

operators may only see “Listener method failed”, losing the root cause and stack trace.

### 1.1. What does a Throwable contain?

| Component | How to obtain | Meaning |
|---|---|---|
| Exception class | `getClass().getName()` | Error type at the current layer |
| Message | `getMessage()` | Additional description; may contain sensitive data |
| Cause | `getCause()` | The error that led to the current exception |
| Stack trace | `getStackTrace()` | Call stack where the throwable was created |
| Suppressed | `getSuppressed()` | Secondary errors attached to the throwable, often during cleanup |
| Full Throwable | Pass the exception properly to the logger | Logger typically prints class, message, stack trace, cause, and suppressed |

**A cause chain is not a chronological log of all system events.** It only represents relationships wired by code and frameworks through exception objects. If a layer swallows an error or instantiates a new exception without passing the cause, the chain breaks.

### 1.2. Is the root cause always the most important cause?

Not necessarily. The deepest exception may merely be `SocketTimeoutException`, whereas the key detail for deciding retry/recovery sits at an outer layer: did the timeout happen while writing the payments table, querying Schema Registry, or publishing to the DLT?

A good incident report usually captures:

1. **Failure stage**: deserialize, listener, database, Kafka publish, transaction commit, DLT recovery.
2. **Outer exception class**: where the framework caught the error.
3. **Root cause class**: the deepest traceable technical failure.
4. **Cause chain**: important intermediate layers.
5. **Source record metadata**: topic, partition, offset, group.
6. **Recovery outcome**: will retry, sent to DLT, recovery failed, or unknown.

## 2. Wrapping exceptions properly in Java

A service can translate a technical error into a more contextual business exception:

~~~java
public class OrderProcessingException extends RuntimeException {

    public OrderProcessingException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Business layer:

~~~java
public void processOrder(OrderEvent event) {
    try {
        orderRepository.save(toEntity(event));
    }
    catch (DataAccessException ex) {
        throw new OrderProcessingException(
                "Failed to persist order event",
                ex);
    }
}
~~~

`super(message, cause)` preserves the link from the business error back to the database error. When Spring Kafka wraps the exception further at the listener boundary, the root cause remains discoverable.

### 2.1. Ways to break an exception chain

~~~java
catch (DataAccessException ex) {
    throw new OrderProcessingException(
            "Database failed",
            null); // Wrong: loses the original cause.
}
~~~

Or:

~~~java
catch (DataAccessException ex) {
    throw new RuntimeException(ex.getMessage());
    // Wrong: keeps only the message, losing original cause/stack trace.
}
~~~

Both make diagnostics harder. Exception messages can look identical across different root causes, and the original stack trace cannot be reconstructed from text alone.

### 2.2. Do not wrap exceptions at every layer unnecessarily

If every helper method wraps another `RuntimeException("Failed")`, the chain becomes long and hard to read. Wrap only when the new layer adds **clear semantics, ownership, or handling policy**, such as distinguishing “order persistence failed” from a generic network error.

A new wrapper should:

- Have a meaningful class or message.
- Preserve the cause.
- Never embed raw payloads or PII in the message.
- Let error handlers classify transient/permanent errors when needed.

## 3. SLF4J: logging the full Throwable properly

With SLF4J, the standard pattern is passing the exception as the **last argument** so the logger receives it as a `Throwable` and prints the stack trace.

~~~java
log.error(
        "Kafka record processing failed: topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset(),
        ex);
~~~

This log statement has three placeholders for metadata and the exception as the final argument. The logger renders the stack trace along with `Caused by` entries without manually walking the chain and concatenating text.

### 3.1. Logging patterns that lose information

| Pattern | Problem |
|---|---|
| `log.error(ex.getMessage());` | Loses exception class, stack trace, and cause |
| `log.error("Failed: {}", ex.getMessage());` | Prints only the message |
| `log.error("Failed: " + ex);` | May print only `toString()` |
| `log.error("Failed {}", record.key());` | Missing throwable |
| `log.error("Failed", ex);` | Properly logs throwable, but lacks source metadata |
| `log.error("Failed for offset {}", record.offset(), ex);` | Correct with one placeholder and trailing Throwable |

A short yet useful call:

~~~java
log.error("Kafka processing failed", ex);
~~~

And a contextual call:

~~~java
log.error(
        "Kafka processing failed: group={}, topic={}, partition={}, offset={}",
        groupId,
        record.topic(),
        record.partition(),
        record.offset(),
        ex);
~~~

### 3.2. Do not use getStackTrace().toString()

~~~java
log.error("Stack trace: {}", ex.getStackTrace().toString());
~~~

`getStackTrace()` returns a `StackTraceElement[]` array. Calling `toString()` on an array does not print the expected stack trace. When a stack trace is needed, **pass the Throwable directly** to the logger.

### 3.3. Do not log the same Throwable three times in one call stack

If the listener logs a full ERROR and rethrows, `DefaultErrorHandler` may log the error again. When the recoverer sends to the DLT and logs too, the system can generate dozens of stack traces for a single record.

Establish an **authoritative logging owner** for each failure stage, for example:

- The listener adds context when wrapping exceptions, without necessarily logging every time.
- The error handler or retry listener logs warnings scaled to severity and retry count.
- Terminal recovery logs ERROR when final failure/DLT routing occurs.
- Aggregate observability uses counters rather than a stack trace per attempt.

Do not strip all exception logs to avoid duplicates; simply pick the right layer and log level.

## 4. Stack trace, cause chain, and suppressed exceptions

When a logger receives a Throwable, typical Java output looks like:

~~~text
ERROR Kafka record processing failed topic=orders.events partition=1 offset=420
org.springframework.kafka.listener.ListenerExecutionFailedException:
    Listener method failed
    at ...KafkaMessageListenerContainer...
Caused by: com.example.OrderProcessingException:
    Failed to persist order event
    at ...OrderService...
Caused by: org.springframework.dao.DataAccessResourceFailureException:
    Database unavailable
    at ...Repository...
Caused by: java.net.SocketTimeoutException:
    Read timed out
    at ...SocketInputStream...
~~~

This is illustrative output, not a stack trace from a live system. Loggers/layouts can add timestamps, threads, MDC, trace IDs, and JSON formatting.

### 4.1. Suppressed exceptions

`Throwable.getSuppressed()` represents secondary errors, such as a resource failing to close in `try-with-resources` after the body already threw an exception:

~~~java
try (Resource resource = openResource()) {
    doWork(); // throws primary exception
} // close() also throws secondary exception
~~~

The primary exception is kept as the main throwable, while the `close()` error becomes a **suppressed exception**. Walking only `getCause()` and ignoring suppressed exceptions can miss critical cleanup failures or resource leaks.

### 4.2. Cause chains do not hold all concurrent failures

In asynchronous workflows, multiple futures can fail independently. One future's `getCause()` does not automatically contain exceptions from sibling futures. To track multiple failures, manage them in state or an aggregate exception with appropriate `suppressed`/metadata.

Never stuff thousands of exceptions into one Throwable's suppressed list and log it in one record: log event size can exceed limits and overload the observability system.

## 5. Root cause helper: use with control

Sometimes structured logs need a separate `rootCauseClass` field for dashboards or alerts. You can traverse `getCause()` to find the deepest throwable:

~~~java
public final class Exceptions {

    private Exceptions() {}

    public static Throwable rootCause(Throwable throwable) {
        if (throwable == null) {
            return null;
        }

        Throwable current = throwable;
        Set<Throwable> seen =
                Collections.newSetFromMap(
                        new IdentityHashMap<Throwable, Boolean>());

        int depth = 0;
        while (current.getCause() != null && depth < 64) {
            if (!seen.add(current)
                    || seen.contains(current.getCause())) {
                break;
            }
            current = current.getCause();
            depth++;
        }
        return current;
    }
}
~~~

Depth bounds and identity tracking guard against anomalous cause cycles or overly deep chains from buggy code. This helper only **adds a classification field**; it does not replace passing the original Throwable to the logger.

### 5.1. Do not rush to apply policies based solely on the deepest exception

For example, `SocketTimeoutException` can sit beneath:

- A database query.
- A downstream HTTP request.
- A Schema Registry lookup.
- A Kafka producer request.

Retry policies can differ per stage. Root cause class is a signal, not the sole classifier. Consider wrappers, stage, business idempotency, and transaction state.

### 5.2. Root cause message is not a safe metric tag

Messages can contain hostnames, SQL, input content, or customer information. Putting raw `rootCause.getMessage()` into a Prometheus label creates both high cardinality and data exposure risks.

Use normalized classes instead:

~~~text
failure_stage=database
root_cause_class=SocketTimeoutException
reason=downstream_timeout
~~~

Small-cardinality fields fit metrics; controlled message details belong in logs/traces.

## 6. Where do exceptions occur in the Spring Kafka pipeline?

Knowing where errors happen shows where exception chains can be logged.

~~~text
Kafka broker record bytes
      |
      v
KafkaConsumer.poll()
      |
      +-- key/value deserializer
      |      |
      |      +-- Serialization/Deserialization failure
      |
      v
Spring Kafka listener container
      |
      +-- message converter / adapter
      |      |
      |      +-- conversion failure
      |
      v
@KafkaListener
      |
      +-- business validation
      +-- database access
      +-- HTTP downstream
      +-- KafkaTemplate.send()
      |
      v
Listener normal return / exception
      |
      v
CommonErrorHandler / AfterRollbackProcessor
      |
      +-- retry / seek / recover
      +-- DeadLetterPublishingRecoverer
      |
      v
Offset commit / Kafka transaction commit
~~~

**Not every exception happens inside the body of `@KafkaListener`.** Deserializer failures can occur inside `KafkaConsumer.poll()` before the listener is called. Transaction commit errors can happen after the listener returns normally. DLT producer errors can happen during the recovery stage.

Therefore, wrapping every listener method in `try/catch` is not enough to capture all system errors.

## 7. Common wrappers in Spring Kafka

Exact exception types depend on Spring Kafka, Kafka client, and business libraries, yet recognizable patterns include:

| Exception class | Common source | What to read next |
|---|---|---|
| `ListenerExecutionFailedException` | Adapter/container when invoking listener fails | Cause from listener/business method |
| Spring Kafka `DeserializationException` | Key/value deserialization failure handled by wrapper | Codec/parser cause and raw-data metadata |
| Kafka client `RecordDeserializationException` in supported versions | KafkaConsumer failed to deserialize record | Topic-partition, offset, and cause |
| `SerializationException` | Key/value serialization/deserialization | Delegate codec, schema, format |
| `MessageConversionException` | Converting message between Kafka and listener type | Conversion cause, target type |
| `KafkaException` | Kafka container/recovery/transaction errors in many places | Cause, lifecycle stage |
| `DataAccessException` | Database/JPA/JDBC via Spring | Underlying DB driver exception |
| `CompletionException` / `ExecutionException` | Asynchronous future/callback | Actual cause of Kafka send |
| `ProducerFencedException` | Transactional producer fenced | Transactional ID, pod collision/lifecycle |
| `TimeoutException` | Network/broker/downstream timeout | Stage and configured timeout |

**Do not classify every exception containing the word “Kafka” as a broker failure.** A `ListenerExecutionFailedException` can mask an application validation bug.

### 7.1. Listener errors usually have wrappers

Example:

~~~text
ListenerExecutionFailedException
  -> OrderProcessingException
     -> DataIntegrityViolationException
        -> SQLException (duplicate key)
~~~

If the root cause is an inbox idempotency duplicate key, it may be legitimate duplicate handling or a data bug requiring analysis, not necessarily a Kafka broker outage.

### 7.2. Spring Kafka versions change chain shapes

A library upgrade can change wrapper classes, nesting depth, or error paths. Do not write alerts tightly coupled to literal message strings like “Listener method failed” without version compatibility tests.

To keep dashboards stable, normalize `failure_stage` and `reason` using intentional classification rules while still storing the full Throwable in diagnostic logs.

## 8. @KafkaListener pattern: preserving cause and metadata

Suppose a listener processes orders:

~~~java
@Component
public class OrderEventsListener {

    private final OrderService orderService;

    public OrderEventsListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-worker")
    public void onRecord(
            ConsumerRecord<String, OrderEvent> record) {

        try {
            orderService.processIdempotently(record.value());
        }
        catch (OrderDomainException ex) {
            throw ex; // Preserve the business exception itself.
        }
        catch (RuntimeException ex) {
            throw new OrderProcessingException(
                    "Failed to process Kafka order event",
                    ex);
        }
    }
}
~~~

The listener preserves the cause; it does not log a stack trace on every retry. The Spring Kafka container/error handler observes the thrown exception and decides whether to retry, seek, or recover.

In systems with centralized logging policies, this `try/catch` may be unnecessary if the wrapper adds nothing useful. A simpler handler:

~~~java
@KafkaListener(topics = "orders.events", groupId = "orders-worker")
public void onOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

may preserve the original exception cleaner than wrapping at every layer.

### 8.1. Do not swallow exceptions without recovering

~~~java
@KafkaListener(topics = "orders.events")
public void wrong(OrderEvent event) {
    try {
        orderService.process(event);
    }
    catch (Exception ex) {
        log.error("Processing failed", ex);
        // Wrong if returning means the record succeeded.
    }
}
~~~

Under many ack/commit policies, normal listener return causes the offset to be acknowledged. Logging the full exception chain while **breaking retry capability** is still a broken design. Rethrow or confirm durable recovery before marking success.

## 9. Logging in DefaultErrorHandler

`DefaultErrorHandler` is the standard record error handler in Spring Kafka non-transactional listener containers. It can retry, back off, seek/redeliver, and recover records via a `ConsumerRecordRecoverer` such as `DeadLetterPublishingRecoverer`.

Configuration example:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltKafkaTemplate);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 2L));

    return handler;
}
~~~

This example only shows basic wiring. The DLT template needs serializers and partition/topic routing compatible with recoverable record types. With custom listener factories, confirm the error handler bean is actually attached to the active factory; Spring Boot auto-configuration can differ when the app declares custom beans.

### 9.1. Using RetryListener to log attempts with context

In Spring Kafka versions supporting `RetryListener`:

~~~java
handler.setRetryListeners(new RetryListener() {

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception ex,
            int deliveryAttempt) {

        Throwable root = Exceptions.rootCause(ex);

        log.warn(
                "Kafka retry attempt: topic={}, partition={}, " +
                "offset={}, attempt={}, outerClass={}, rootClass={}",
                record.topic(),
                record.partition(),
                record.offset(),
                deliveryAttempt,
                ex.getClass().getSimpleName(),
                root == null
                        ? "unknown"
                        : root.getClass().getSimpleName());
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception ex) {
        log.error(
                "Kafka record recovered after processing failure: " +
                "topic={}, partition={}, offset={}",
                record.topic(),
                record.partition(),
                record.offset(),
                ex);
    }
});
~~~

Here, `failedDelivery` logs concise attempt metadata, while `recovered` logs the full Throwable at recovery time. This is a choice to curb log volume, not a strict rule. Because a recoverer may successfully send the record to a DLT, `recovered` can be ERROR or WARN depending on SLOs and system policy; do not equate successful recovery with business success.

**Important:** Using `DefaultErrorHandler` for non-transactional containers differs from the after-rollback flow of transactional listener containers. Do not take non-transactional error handler code and assume it covers every Kafka transaction failure.

### 9.2. Log once at the terminal boundary

A practical strategy:

| Stage | Suggested log | Content |
|---|---|---|
| First retry | Brief WARN | Reason, topic/partition/offset, attempt |
| Subsequent retries | DEBUG or rate-limited WARN | Avoid repeating full stack traces endlessly |
| Recovered to DLT successfully | WARN/ERROR per SLO | Original error class, DLT destination, correlation |
| Recovery failed | ERROR with full Throwable | Original failure and recovery failure |
| Container stopped due to fatal error | ERROR with full Throwable | Lifecycle state, partition, group |

Choose logging points based on service ownership. If the framework already logs full exceptions by default, adjust logger categories appropriately instead of adding duplicate loggers.

## 10. Exceptions occurring before the listener is invoked

The Kafka client deserializes keys/values during `poll()`. A `JsonDeserializer` or Avro/Protobuf codec can throw an exception before the listener is called. When that happens:

~~~text
Broker raw bytes
        |
        v
KafkaConsumer.poll()
        |
        v
Kafka deserializer
        |
        +--- exception
              |
              v
     Listener not invoked yet
~~~

A `try/catch` inside the listener never sees this error. Logging only in the listener misses deserialization errors completely.

### 10.1. ErrorHandlingDeserializer

Spring Kafka provides `ErrorHandlingDeserializer` to wrap a delegate deserializer. When the delegate fails, the wrapper stores exception metadata in Kafka headers used by the framework so error handling/recovery can operate on the record.

Spring Boot example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-worker
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.trusted.packages]": com.example.orders.events
~~~

Adjust this example for your application's actual event types/serializers. If the key deserializer can also fail, configure key error handling accordingly.

### 10.2. Log the right failure stage

When a `DeserializationException` enters the recovery path, structured logs should state:

~~~text
failure_stage=deserialize_value
source_topic=orders.events
source_partition=2
source_offset=345
outer_class=DeserializationException
root_class=JsonParseException
recovery=dlt
~~~

This data is illustrative. Never log raw bytes or unvalidated partial deserializations just to inspect “message contents”.

### 10.3. Raw payloads and DLT serializers

For deserialization errors, the DLT may need to store raw `byte[]` instead of domain objects. If the DLT producer is configured to serialize only JSON objects, recovery can fail and raise a **second exception chain** during the DLT send.

When investigating, distinguish:

1. Original deserialization failure.
2. DLT publish/serialization failure.

Never overwrite the original error with the DLT error and lose evidence of the initial cause.

## 11. Message conversion and method argument errors

After the Kafka deserializer, Spring Kafka may still perform message conversion or listener parameter binding. Errors can occur when:

- A required header is missing.
- Payload type does not match the method signature.
- JSON payload parses yet fails to map to the expected model.
- Adapter-layer validation fails.
- Message converter picks the wrong target type.

Example:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(
        @Payload OrderCreated event,
        @Header("event-type") String eventType) {
    orderService.process(event);
}
~~~

If the required `event-type` header is missing, an error can occur during argument resolution before the business method runs. Logs should record `failure_stage=listener_adapter` or `message_conversion` instead of misdiagnosing a database issue.

### 11.1. A cause chain can hide validation errors

Example:

~~~text
ListenerExecutionFailedException
  -> MessageConversionException
     -> IllegalArgumentException
~~~

The wrapper message may be generic; inspect the appropriate cause class and message. Still, do not use raw messages containing payloads as alert tags or print them to public logs.

## 12. Logging exception chains for asynchronous KafkaTemplate.send

In modern Spring Kafka, `KafkaTemplate.send(...)` returns `CompletableFuture<SendResult<K,V>>`. Send failures surface when the future completes exceptionally.

Example:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        Throwable root = Exceptions.rootCause(exception);

        log.error(
                "Kafka publish failed: topic={}, eventType={}, " +
                "outerClass={}, rootClass={}",
                "orders.created",
                "OrderCreated",
                exception.getClass().getSimpleName(),
                root == null
                        ? "unknown"
                        : root.getClass().getSimpleName(),
                exception);
    }
});
~~~

If `exception` is `CompletionException` and its cause is a Kafka producer error, passing the entire Throwable to the logger preserves both the wrapper and the root cause.

### 12.1. Errors can also be thrown synchronously

Not all producer errors appear exclusively in the future. Record creation, payload conversion, or validation/config checks can throw synchronously on the API call. Publish paths must ensure synchronous errors are also propagated or logged at the right boundary.

### 12.2. join() and get() produce different wrappers

With Java futures:

~~~java
future.join(); // may throw CompletionException.
future.get();  // may throw ExecutionException.
~~~

When logging, pass the original wrapper Throwable to keep the chain. When deciding classification/retries, you can inspect known technical wrappers, but do not blindly unwrap all the way to the root cause and lose stage/scope.

### 12.3. Do not swallow asynchronous errors

A callback that only logs an exception after an external service already returned “publish succeeded” can leave business data without an event. You need a durability workflow such as outbox, pending-state persistence, or a caller completion strategy.

Full logging does not replace proper error propagation and retry/recovery.

## 13. Producer send failure vs. transaction commit failure are two stages

In Kafka transactions, a Kafka producer may successfully send a record inside a transaction, only for the transaction to abort or fail to commit afterward.

~~~text
BEGIN Kafka transaction
       |
       v
KafkaTemplate.send(record A)
       |
       +-- broker ack succeeds
       |
       v
COMMIT transaction
       |
       +-- may fail: timeout, fencing, coordinator issue
~~~

If logs only state:

~~~text
Kafka send acknowledged
~~~

that does not prove the record committed or that downstream `read_committed` consumers will see it.

For transactional flows, track states:

- `send_acknowledged`.
- `transaction_commit_succeeded`.
- `transaction_aborted`.
- `transaction_commit_failed`.

Never assume a producer span or send result equals a committed transaction outcome.

### 13.1. ProducerFencedException

`ProducerFencedException` can occur when an older transactional producer is replaced by another producer using the same transactional ID. Helpful logs should include:

- Service instance/pod.
- Transactional ID or controlled diagnostic identifier.
- Kafka transaction stage.
- Producer lifecycle/restart context.
- Full exception chain.

Never continue using a fenced producer to commit. This is a critical lifecycle/ownership error requiring root-cause resolution, not endless retries.

### 13.2. Transactional listener containers

For listener containers with a Kafka transaction manager, listener exceptions normally roll back the transaction. After-rollback logic and DLT recovery have their own mechanisms, such as `DefaultAfterRollbackProcessor`. Do not take non-transactional `DefaultErrorHandler` logging patterns and assume they catch every commit/rollback-phase exception.

## 14. When failures occur during recovery/DLT

A single record can have **two independent errors**:

1. Original processing exception.
2. Recovery exception when publishing to the DLT or updating state.

Example:

~~~text
Original:
  ListenerExecutionFailedException
    -> OrderProcessingException
       -> SQLException

Recovery:
  KafkaException
    -> TimeoutException (DLT producer)
~~~

If you log only the recovery Throwable, you see “DLT timeout” but lose why the record failed originally. If you log only the original Throwable, you miss that the system **failed to persist the failed record** and may not be advancing offsets safely.

### 14.1. Log events can capture both chains

At the recovery boundary, you can log both Throwables in **two log entries sharing an incident/correlation key**:

~~~java
log.error(
        "Kafka DLT recovery failed: topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset(),
        recoveryFailure);

log.warn(
        "Original processing failure for same record",
        originalFailure);
~~~

This example is for actual recovery failures, not advice to always log two stack traces on every retry. Choose an approach matching your log volume and observability tools. If the app constructs an aggregate exception attaching the original exception as cause/suppressed per proper semantics, a single Throwable can be logged instead of two entries.

### 14.2. DLT headers and metadata

`DeadLetterPublishingRecoverer` can add original topic/partition/offset and exception metadata into DLT headers per version/configuration. These headers aid forensic replay but **do not replace original stack trace logs**: DLT retention, header size limits, privacy policies, and serializers have their own constraints.

Never serialize entire Throwable objects into Kafka headers or payloads without an explicit format/trust policy; serialized exceptions can carry unintended classes or sensitive data.

### 14.3. Recovery success differs from business success

When a record is successfully sent to a DLT, the accurate status is:

~~~text
recovery_status=dlt_published
business_status=not_completed
~~~

Do not report `processing_success=true` just because the consumer moved past the source offset. A DLT is an error storage path for investigation/replay, not business completion.

## 15. Blocking retries and log storms

With `DefaultErrorHandler` and backoff, the same record can be processed multiple times:

~~~text
offset 100
  |
  +-- attempt 1 -> DB timeout
  |
  +-- attempt 2 -> DB timeout
  |
  +-- attempt 3 -> DB timeout
  |
  +-- recover / DLT / stop per policy
~~~

If listener, service, repository adapter, and error handler all log ERROR full stack traces on every attempt, one record can generate dozens of huge log events; a downstream outage can turn into a **log storm**.

### 15.1. Policy by attempt

One design approach:

| Attempt / state | Suggested severity | Content |
|---|---|---|
| First retryable failure | WARN | Stage, normalized reason, record location |
| Subsequent attempts | DEBUG or rate-limited WARN | Attempt, backoff, root cause class |
| Final unrecovered retry | ERROR | Full Throwable and recovery decision |
| DLT publish succeeded | WARN/ERROR per business policy | DLT destination, original error |
| DLT publish failed | ERROR/CRITICAL | Recovery Throwable and original chain |

No single severity rule fits all services. Transient failures may only need metrics + WARN; unrecoverable payment records may require ERROR and paging.

### 15.2. Rate-limiting logs by appropriate keys

You can rate-limit by:

- Service.
- Normalized exception class.
- Failure stage.
- Topic.
- Time window.

Never put raw record keys, event IDs, or exception messages into metric tags. When needing to cross-check a single record, structured logs carry topic/partition/offset or protected event IDs.

### 15.3. Exponential backoff vs. log rate limiting

Backoff governs **when the record is reprocessed**; log rate limiting governs **how many logs are emitted**. The two mechanisms are independent. Reducing logs does not fix a Kafka retry storm; increasing backoff does not guarantee a custom error handler won't log duplicates.

## 16. Non-blocking retry topics and exception chains across messages

With `@RetryableTopic`, a failure can publish the record to another retry topic:

~~~text
orders.events
       |
       v
orders.events-retry-1000
       |
       v
orders.events-retry-5000
       |
       v
orders.events-dlt
~~~

Each step can execute in a fresh consumer invocation and throw a fresh Throwable. Therefore, **do not assume a single Java cause chain spans across all retry topics**. Attempts reside in separate records/transactions.

To trace the full journey, use:

1. A stable event ID across republishes.
2. Original source topic/partition/offset when available.
3. Retry topic and attempt metadata.
4. Propagated trace/correlation context if preserved.
5. Logs for the original failure and terminal retry outcome.

### 16.1. Retry headers are not exception objects

A Kafka record in a retry topic carries bytes and headers, not the live JVM stack trace from the previous pass. The framework may serialize error metadata, yet any Throwable in the next pass is a brand-new object.

Do not try comparing object identity or Java stack frames across attempts; rely on event IDs and message metadata.

### 16.2. Do not confuse trace ID with event ID

Trace ID links observability spans when context is preserved and sampled, but can change during a manual replay hours later. Event ID is the stable business identifier for deduplicating and tracking recovery. The two values serve different purposes.

## 17. A minimal structured log for Kafka errors

Structured logging (JSON or key-value) enables querying by group, topic, partition, and failure stage.

Example:

~~~json
{
  "level": "ERROR",
  "service": "orders-worker",
  "instance": "pod-a",
  "consumerGroup": "orders-worker",
  "topic": "orders.events",
  "partition": 2,
  "offset": 345,
  "stage": "listener_processing",
  "attempt": 3,
  "outerException": "ListenerExecutionFailedException",
  "rootCause": "SocketTimeoutException",
  "reason": "database_timeout",
  "recovery": "dlt_requested",
  "traceId": "sample-trace-id",
  "eventId": "sample-event-id"
}
~~~

This is illustrative data, not a mandatory schema. Stack traces can sit in a separate field supported by the logging backend. In real applications, **do not log unauthorized traceId/eventId values** and never put high-cardinality values into metric labels.

### 17.1. Key fields

| Field | Why is it useful? |
|---|---|
| `service`, `instance` | Locate the pod/JVM where the error occurred |
| `consumerGroup` | Identify group progress |
| `topic`, `partition`, `offset` | Locate the source record in Kafka logs |
| `stage` | Distinguish deserialize, business, publish, commit, recover |
| `attempt` | Distinguish first retry from terminal failure |
| `outerException` | See the framework boundary |
| `rootCause` | See the deepest technical error |
| `reason` | Normalized label for alerts/dashboards |
| `recovery` | Know retry, DLT, committed, or failed |
| `traceId`/`eventId` | Link to traces and business records when policy permits |

### 17.2. Kafka offsets are meaningful only with topic and partition

Offset 345 is not unique across a cluster. At minimum you need topic + partition + offset, and across multiple clusters you need cluster/environment. An event after DLT has a **new offset on the DLT**, so never substitute the DLT offset for the source offset.

### 17.3. Avoid vague “Kafka recovered” statuses

“Recovered” could mean:

- The record was published to the DLT successfully.
- The listener retried and succeeded.
- After rollback, the container skipped the record per policy.
- A business workflow ran compensation.

Use explicit `recovery` values such as `retry_scheduled`, `dlt_published`, `replay_completed`, or `recovery_failed` to avoid state confusion.

## 18. MDC and trace context

Systems using Micrometer Tracing/OpenTelemetry can place `traceId` and `spanId` into MDC so loggers automatically attach correlation fields.

When a Kafka record flows through a listener:

~~~text
Producer trace headers
          |
          v
Kafka ConsumerRecord
          |
          v
Spring Kafka Observation/Tracing
          |
          v
Active trace context
          |
          v
MDC traceId/spanId (if bridge configured)
          |
          v
Structured application log
~~~

This requires consumer observation/tracing integration, matching propagation formats, and corresponding logging config. Do not assume Kafka headers are automatically copied into MDC unless tracing is enabled.

### 18.1. Async threads can lose MDC

For example, when a listener submits work to a thread pool, MDC/trace context normally does not follow automatically:

~~~java
executor.submit(() -> processInBackground(event));
~~~

If correlation must be preserved, use context propagation compatible with your Micrometer/Spring version and close scopes after the task. Also ensure offsets/acks are handled safely; a log with the right trace ID does not prove a background task finished before commit.

### 18.2. Never put sensitive data into MDC

MDC is typically included in every log on that thread. Never place raw payloads, access tokens, customer emails, or payment data into MDC. Beyond leakage risk, uncleaned MDC can cross-contaminate requests when thread pools reuse threads.

## 19. Logging throwables safely: PII, secrets, and size

Exception messages and stack traces sometimes contain:

- SQL queries and parameters.
- URLs with tokens or query strings containing PII.
- Hostnames, internal IPs, or sensitive endpoints.
- Kafka record payloads embedded by a custom deserializer into the message.
- Usernames, account IDs, or tenant metadata.
- Credentials if an underlying library formats errors unsafely.

Thus, “logging the full exception chain” does not mean exposing everything in public logs.

### 19.1. Preserve error structure, filter sensitive data

Measures:

1. Never embed raw payloads in custom exception messages.
2. Never call `record.value().toString()` in error logs if events hold sensitive data.
3. Use logging encoders with tested masking/redaction.
4. Restrict log read permissions and retention.
5. Use event ID/offset to look up data in controlled storage.
6. Protect DLTs/quarantines with equivalent ACLs, encryption, and privacy policies.

Specifically for deserialization errors, raw bytes may be untrusted or hold unparsed/unvalidated data; do not convert them directly into log strings.

### 19.2. Bound stack trace size

A deep cause chain or large suppressed exceptions can push a log event past collector limits. Pick a logging backend/encoder that supports sensible size bounds while retaining controlled full diagnostics during incidents.

Do not truncate a Throwable down to `ex.getMessage()` just to save bytes, since that strips stack traces and causes. Consider:

- Full stack traces at terminal/fatal boundaries.
- Concise root/outer classes per retry.
- Sampling/rate limiting for repetitive exceptions.
- Dedicated forensic storage when long logs are needed.

## 20. Exception classification based on the chain

An error handler must decide whether an exception should retry. Some transient failures:

- Database connection timeout.
- Downstream HTTP 503.
- Temporary Kafka broker unavailability.
- Schema Registry request timeout.

Some failures are typically permanent for the same payload:

- Malformed JSON.
- Schema invalid against the current contract.
- Missing required header.
- Business validation errors unfixable by retrying.

However, looking only at the root cause can mislead. Example:

~~~text
ListenerExecutionFailedException
 -> RetryableBusinessException
    -> IllegalStateException
~~~

`IllegalStateException` at the root does not convey the full policy; the business wrapper may indicate a retry is appropriate because a dependency is transitioning states.

Conversely:

~~~text
ListenerExecutionFailedException
 -> PermanentInvalidEventException
    -> IllegalArgumentException
~~~

Do not retry indefinitely just because the root cause has a generic name.

### 20.1. Do not use regex on exception messages to decide retries

Exception messages can change across versions, locales, or drivers. Classify via known exception types, stages, and cause chains. Emit normalized `reason` labels for observability.

### 20.2. When exceptions are wrapped across multiple layers

Spring Kafka's error handler has version-dependent mechanisms for inspecting causes/wrappers. When adding custom exception types to `addNotRetryableExceptions(...)` or classification maps, verify in practice that the wrapper/cause chain is recognized under your current configuration; do not just look at the deepest class name and assume the classifier traverses it as expected.

## 21. When to log only classes vs. full stack traces?

Not every attempt needs a full stack trace. Choose by purpose:

| Context | Appropriate log |
|---|---|
 Retry transient errors many times | Structured WARN with outer/root class, attempt, stage |
| Unresolved terminal error | ERROR + full Throwable |
| DLT push failure | ERROR + recovery Throwable and original cause |
| Aggregate monitoring | Metric counts, reason labels, no stack trace |
| Manual replay audit | Event ID, source, operator, outcome |
| Controlled debugging | Full stack trace when needed without data leaks |

If the system already logs a stack trace at the terminal boundary, service layers can simply throw exceptions preserving causes to avoid duplicates. If no layer logs terminal errors, add instrumentation at the responsible boundary.

## 22. Error-handler logging does not replace metrics

One million retries of the same `SocketTimeoutException` should not produce one million full stack traces. Useful metrics:

| Metric | Purpose |
|---|---|
| Exception attempts by reason/stage | Count retries/errors by group |
| Recoveries to DLT | Count records routed to recovery |
| DLT publish failures | Failures on the recovery path |
| Listener processing duration | Execution latency |
| Kafka consumer lag | Backlog and progress |
| Oldest unprocessed record age | Impact against SLA |
| Producer send failures | Publish errors |
| Kafka transaction abort rate | Transaction problems |
| Database/HTTP timeout rate | Dependency failures |

Metric tags should be `service`, `topic` (bounded set), `stage`, `reason`, and a few other finite dimensions. **Never use full exception messages, Kafka offsets, event IDs, or trace IDs as metric tags.**

## 23. Runbook: logs only show “Listener method failed”

When encountering an overly generic log line:

1. Check whether the current log statement passes the Throwable object.
2. Check whether the app only prints `ex.getMessage()` or includes the full stack trace.
3. Search for `Caused by` in the corresponding log event.
4. Check whether the structured logger/collector truncates stack traces.
5. Capture topic, partition, offset, group, and attempt.
6. Classify the stage: conversion, business, database, producer.
7. If the chain is broken, check whether custom exception constructors pass `cause`.
8. Add logging at the terminal boundary without duplicating across every layer.
9. After recovery, use metrics/offsets to verify the pipeline is advancing.

Do not merely make the message longer. Preserve the Throwable chain and record metadata.

## 24. Runbook: Kafka listener is not invoked yet consumer reports errors

1. Check whether the failure occurs in `KafkaConsumer.poll()` or the listener adapter.
2. Check key/value deserializer configuration.
3. Check whether `ErrorHandlingDeserializer` is used if raw bytes need recovery.
4. Check exception class: `RecordDeserializationException`, `SerializationException`, conversion failure.
5. Confirm topic, partition, offset, and schema ID/framing when present.
6. Do not log raw payloads in normal production logs.
7. Verify the DLT producer supports raw `byte[]`.
8. Verify offset commit after recovery to avoid prolonged poison pills.

If the error occurs before the listener, adding `try/catch` inside the method will not help. Fix the deserializer/error handling path.

## 25. Runbook: multiple ERROR logs for the same record

1. Cross-check topic/partition/offset/event ID.
2. Check whether the record is retrying or is genuinely a duplicate event.
3. Inspect logs from the service method, listener, error handler, and recoverer.
4. Identify which layer owns terminal logging.
5. Drop per-attempt stack traces where unnecessary.
6. Keep one full throwable at the recovery/fatal boundary.
7. Use metrics to measure attempt counts rather than a huge log per attempt.
8. Check log retention and collector throttling.

Do not delete all logs because of one noisy incident; preserve root-cause and recovery-state visibility.

## 26. Runbook: DLT recovery failed

1. Locate the original processing failure log.
2. Locate the recovery exception log for the same source record identity.
3. Inspect the DLT KafkaTemplate/serializers, especially for raw bytes.
4. Inspect DLT topic existence, ACLs, quotas, message size limits, and broker health.
5. Inspect transaction/offset recovery semantics.
6. Verify the source offset is not marked complete until the DLT publish succeeds safely.
7. Restore the DLT and replay/retry per policy.
8. Cross-check event IDs so DLT duplicates do not cause duplicate side effects.

In the incident report, distinguish clearly which error is **original** and which is **recovery**; otherwise operations might fix only the DLT producer while ignoring the underlying data bug.

## 27. Runbook: unfamiliar exception classes after a Spring Kafka upgrade

1. Record Spring Kafka/Kafka client/Boot versions before and after the change.
2. Read the outer class and the entire cause chain.
3. Compare failure stages and retry/DLT behavior before vs. after deployment.
4. Inspect exception classification rules configured for older wrappers.
5. Check whether log parsers/dashboards depend on literal message strings.
6. Confirm exceptions are still rethrown and not swallowed.
7. Run integration tests with intentional failures.
8. Update normalized reason mappings if needed, keeping an audit trail of the change.

Do not work around it by catching `Exception` and ignoring new wrappers; that can disable error recovery.

## 28. Technical testing for exception chain logging

Unit tests can verify custom exceptions preserve causes. Integration tests must verify Spring Kafka paths.

### 28.1. Test constructor preserves cause

~~~java
@Test
void preservesOriginalCause() {
    IOException root =
            new IOException("Network timeout");

    OrderProcessingException failure =
            new OrderProcessingException(
                    "Cannot process order",
                    root);

    assertThat(failure.getCause()).isSameAs(root);
    assertThat(Exceptions.rootCause(failure))
            .isSameAs(root);
}
~~~

### 28.2. Test wrapper chain

~~~java
@Test
void extractsDeepestCause() {
    Throwable root =
            new SocketTimeoutException("Read timed out");

    Throwable middle =
            new IllegalStateException("Database call failed", root);

    Throwable outer =
            new OrderProcessingException(
                    "Kafka order processing failed",
                    middle);

    assertThat(Exceptions.rootCause(outer))
            .isSameAs(root);
}
~~~

This is a pure Java helper test; it does not prove Kafka listeners/recoverers log properly—real pipeline integration tests are still needed.

### 28.3. Test SLF4J appender

With Logback in a test environment, `ListAppender<ILoggingEvent>` can capture events and verify the throwable proxy exists when the logger receives a Throwable:

~~~java
Logger logger =
        (Logger) LoggerFactory.getLogger(OrderEventsListener.class);

ListAppender<ILoggingEvent> appender =
        new ListAppender<>();
appender.start();
logger.addAppender(appender);

try {
    RuntimeException root =
            new RuntimeException("Root failed");

    logger.error("Listener failed: topic={}", "orders.events", root);

    assertThat(appender.list).hasSize(1);
    assertThat(appender.list.get(0).getThrowableProxy())
            .isNotNull();
}
finally {
    logger.detachAppender(appender);
    appender.stop();
}
~~~

This test example uses Logback classes and AssertJ, not a mandatory API across all logging backends. Real tests should isolate loggers/test contexts to avoid interfering with parallel tests.

### 28.4. Test listener error handler

1. Send a valid record whose business service throws a multi-layer exception with causes.
2. Assert `@KafkaListener` does not swallow it.
3. Assert the error handler receives the Throwable chain.
4. Check attempt counts per backoff configuration.
5. Assert full stack traces at the terminal boundary per policy.
6. Assert the record retries/routes to DLT per classification.

### 28.5. Test deserialization failure

1. Send malformed payload bytes to the deserializer.
2. Assert the listener is not invoked if decoding fails before the listener.
3. If using `ErrorHandlingDeserializer`, assert the recovery path receives appropriate raw bytes.
4. Assert logs include failure stage and class/cause.
5. Ensure sensitive payloads are not leaked into logs.

### 28.6. Test asynchronous producer failure

1. Induce a controlled failure in the Kafka producer/broker.
2. Assert the future completes exceptionally.
3. Assert outer/inner exceptions are logged completely.
4. Verify the method/caller knows publishing failed per durability policy.
5. Ensure callbacks and callers do not log infinite duplicates.

### 28.7. Test DLT recovery failure

1. Force the listener to throw a non-retryable exception.
2. Force the DLT producer to fail (e.g., ACL in test).
3. Assert both original and recovery exceptions are traceable.
4. Assert the source record is not marked complete with data loss.
5. Restore the DLT and verify state after recovery.

## 29. Common mistakes

**Logging only `getMessage()`.** Loses class/cause/stack trace, making root cause identification very hard.

**Wrapping exceptions without passing cause.** Breaks the chain and loses the original stack trace.

**Logging ERROR full stack traces at every layer.** A retry storm can escalate into a log storm.

**Treating root cause as the entire retry policy.** Stage and business wrappers also matter.

**Catching exceptions and returning normally.** Can commit offsets even though the business operation failed.

**Assuming the listener catches every Kafka error.** Deserialization/commit/recovery can happen outside the listener.

**Logging original failure while ignoring DLT failure.** Hides that recovery lost safety.

**Logging DLT failure while forgetting original failure.** Hides why the record failed initially.

**Using raw payloads as log metadata.** Risks exposing PII, secrets, and creating huge logs.

**Using exception messages as metric labels.** Uncontrolled cardinality and data exposure risk.

**Failing to distinguish send acknowledged from transaction committed.** Leads to false conclusions about delivery.

**Assuming retry topics preserve the Java exception chain.** Republishing creates new invocations/Throwables; use event IDs and Kafka metadata.

**Using trace ID as an idempotency key.** Trace IDs serve observability, not stable event identity.

**Failing to bound logging during major incidents.** Collectors can drop logs, losing critical signals.

## 30. Production readiness checklist

### Exception construction and propagation

- [ ] Custom exceptions provide constructors accepting `cause`.
- [ ] Listeners do not swallow unrecovered errors.
- [ ] Exceptions are not pointlessly wrapped at every layer.
- [ ] Original failures and recovery failures can be distinguished.
- [ ] Checked/runtime exceptions align with transaction/rollback policies.

### Logging

- [ ] SLF4J receives the original Throwable as the final parameter.
- [ ] Topic/partition/offset/group are included when record source is known.
- [ ] Failure stage, outer class, root cause class, and attempt are included.
- [ ] Full stack traces appear at terminal/fatal boundaries.
- [ ] Retry logs use appropriate severity and rate limits.
- [ ] Raw payloads, credentials, and PII are never logged.

### Kafka error paths

- [ ] Pre-listener deserialization errors are handled when needed.
- [ ] Error handlers/retry listeners log accurate types and attempts.
- [ ] DLT recovery logging preserves both original and recovery failures.
- [ ] Successful DLT publish is never treated as business success.
- [ ] Asynchronous `KafkaTemplate` errors are observed.
- [ ] Kafka transaction commit/abort is observed separately from send.

### Observability

- [ ] Structured logs include appropriate service, instance, and correlation metadata.
- [ ] MDC/trace scopes do not leak across async thread pools.
- [ ] Metric reason tags have low cardinality.
- [ ] Consumer lag, retry/DLT rates, and business completion signals exist.
- [ ] Collectors handle log volume/stack traces per policy.
- [ ] Runbooks exist for wrapper-only logs, poison pills, and DLT failures.

### Testing

- [ ] Tested that custom exceptions preserve causes.
- [ ] Tested that log appenders receive Throwable proxies.
- [ ] Tested that listener error handlers receive exception chains.
- [ ] Tested pre-listener deserialization errors.
- [ ] Tested async `KafkaTemplate` send failures.
- [ ] Tested DLT recovery failures without losing source records.
- [ ] Tested that logs do not leak sensitive data per policy.

## Conclusion

**Logging the exception chain** in Spring Kafka is the practice of preserving the full relationship between **the exception at the current boundary**, **deeper nested causes**, and **suppressed exceptions where applicable**, enriched with topic, partition, offset, attempt, and recovery stage metadata. The most fundamental rule is **never drop the cause when wrapping exceptions** and **pass the original Throwable directly to the SLF4J logger** rather than logging only `getMessage()`.

For Kafka reliability, monitor multiple failure boundaries: deserialization can fail before `@KafkaListener`; listener errors can be wrapped by Spring Kafka; `KafkaTemplate` can report errors via futures; transaction commits can fail after sends; and DLT recovery can throw a second exception. Pick one full logging point at the terminal stage, record attempts concisely/via metrics, separate original failures from recovery failures, protect sensitive data, and use event IDs/trace context to link retries and replays. **A clear causal stack trace aids diagnostics, while only sound error handling, offset/transaction correctness, and durable recovery truly protect data.**
