# Distinguishing Runtime Errors from Adapter Errors in Spring Integration

## Lesson Objectives

In **SPRING_INTEGRATION_RUNTIME**, messages flow through **channels, endpoints, consumers, pollers, and executors**, may be persisted in a **MessageStore**, undergo **transactions/retries**, get processed by **correlation**, and interact with brokers, HTTP services, file systems, or databases. When an incident strikes, messages like "message delivery failed," "request timed out," or "error in polling task" are usually **not enough** to tell which layer failed.

This lesson belongs to the **Debugging** chapter, covering **Distinguishing Runtime Errors from Adapter Errors**. Its aim is to locate **the first point of failure**, **the error propagation mechanism**, and **the right remediation decision** instead of fixing the wrong layer.

After this lesson, you will be able to:

1. Distinguish **Spring Integration internal coordination errors** from **integration-boundary errors** in inbound/outbound adapters.
2. Classify failures by **stage**: before Message creation, during dispatch/handle, during external calls, at commit/ack, and during recovery.
3. Read **MessagingException**, **MessageHandlingException**, **MessageDeliveryException**, **ErrorMessage**, **failedMessage**, original messages, and cause chains without jumping to conclusions from exception names.
4. Explain how **DirectChannel, ExecutorChannel, QueueChannel, and pollers** affect error propagation and transactions.
5. Use correlation, logs, metrics, tracing, WireTap/QueueChannel in tests to track lost or duplicate messages.
6. Choose **retry/backoff, rollback/redelivery, quarantine/DLQ, or reconciliation** based on actual root cause.
7. Design tests reproducing one runtime failure and one adapter failure, verifying where the error surfaces and the post-failure message state.

> **Principle:** "Runtime" and "adapter" are **two perspectives on root cause**, not two strictly disjoint exception hierarchies. An adapter error can be wrapped by the framework in `MessagingException`; a runtime error such as an executor task rejection can surface in an inbound adapter's logs.

## 1. Where Is the Boundary Between Runtime and Adapter?

Spring Integration implements **Enterprise Integration Patterns (EIP)**. Within an `IntegrationFlow`, the framework is responsible for moving messages across channels, invoking handlers, scheduling polls, managing endpoint lifecycles, switching threads, storing group state, and publishing errors. Adapters are the parts interacting with **external systems and protocols**.

~~~mermaid
flowchart LR
    EX["Broker / File / HTTP / DB"] --> IA["Inbound adapter"]
    IA --> CH["MessageChannel"]
    CH --> EP["Endpoint / handler"]
    EP --> EA["Outbound adapter"]
    EA --> EXT["External service"]
    CH -. "runtime" .-> RT["Dispatcher / Executor / Poller / Transaction"]
    EP -. "runtime" .-> RT
    IA -. "protocol / binding" .-> AD["Adapter layer"]
    EA -. "protocol / binding" .-> AD
~~~

### Runtime Errors: Internal Coordination Failing Its Contract

Examples:

- **Channel has no subscribers** or messages are sent to the wrong channel.
- **Executor is saturated**, rejects tasks, or the app lacks backpressure control.
- **Polling endpoint is stopped**, lacks a poll schedule, scheduler is inactive, or poller is stuck.
- **Handler/transformer/router** throws due to business logic, wrong schema assumptions, or missing route.
- **Aggregator** fails to release due to wrong correlation key/sequence/`ReleaseStrategy` or `MessageGroupStore` contention.
- **Transaction** does not cover the right thread/resource, so rollback behaves unexpectedly.
- **MessageStore** in-memory state disappears across restarts, or a persistent store cannot deserialize stored payloads.
- **Error flow** is disconnected, a handler swallows errors, recovery marks failure as success, or nested retries multiply.

### Adapter Errors: Boundary Communication Failing Its Function

Examples:

- Kafka/AMQP/JMS consumer fails authentication, broker is unreachable, or partitions/queues are not assigned as expected.
- HTTP outbound gateway times out, hits DNS/TLS errors, upstream returns 401/403/429/5xx, or response body fails conversion.
- File/FTP/SFTP inbound adapter lacks read permissions, file is locked, remote server disconnects, or filter/checkpoint misbehaves.
- JDBC inbound/outbound adapter cannot connect to DB, hits SQL errors, schema drift, or revoked table privileges.
- Adapter maps **payload/headers/content-type** inconsistently with the external system's contract.
- Ack/offset/commit fails or send outcome is **unknown** when the connection drops at the exact wrong moment.

**The two categories can overlap:** A `JdbcMessageStore` failing to write due to database downtime is a DB infrastructure outage inside a **runtime persistence component**. An HTTP outbound adapter throwing `MessagingException` is an **external call** failure expressed as a **runtime exception**. Always record both **location** and **root cause**.

## 2. Initial Identification Matrix

| First Signal | Runtime Suspect | Adapter / External Suspect | Evidence to Collect |
| --- | --- | --- | --- |
| Send fails with no receiver | Wrong channel, missing subscriber, stopped endpoint | Input adapter built valid message, downstream unconfigured | Channel bean name, subscribers, endpoint state, `MessageDeliveryException` |
| Poller gets no messages | Scheduler/poller not started, filter drops all | File/broker/DB returns no data or lost connection | Poll cycles, `receive()` results, adapter exceptions, source checkpoints |
| Slow workers, growing backlog | Full executor queue, lock contention, retry storm | Slow downstream HTTP/DB, broker throttling | Queue depth, active threads, per-stage timers |
| `ErrorMessage` lacks `requestId` | Transformer stripped headers, cross-thread exception | Failure occurred before adapter built Spring `Message` | `originalMessage`, `failedMessage`, source logs |
| Outbound handler timeout | Handler deadlines/`RetryAdvice` stacking | DNS, network, TLS, remote SLA | Root cause, client timeout, remote request ID |
| Message redelivered after restart | Misaligned ack/transaction boundary | Broker at-least-once, visibility timeout, uncommitted offset | Delivery attempts, business `eventId`, commit/ack timeline |
| Aggregator waits indefinitely | Wrong correlation, missing sequence, release strategy | Upstream source never emitted required part | Group metadata, `groupId`, source deliveries |
| Flow stops running after deploy | Bean/endpoint lifecycle, `autoStartup=false` | Adapter misconfigured or failed source subscription | `isRunning`, startup errors, transport health |
| Payload fails to decode | Wrong internal transformer/converter | Adapter received new content-type or schema | Raw bytes at adapter boundary, converter stack, contract version |

A single symptom can stem from **multiple causes**. For instance, "`QueueChannel` stopped growing" could mean the inbound adapter stopped, the adapter received nothing from the broker, or the source ran out of data. **Never treat one metric as final proof.**

## 3. Diagnose by Stage Rather Than Exception Name

Pin each incident to a verifiable stage:

~~~mermaid
flowchart TD
    A["1. External source / protocol"] --> B["2. Adapter reads and converts"]
    B --> C["3. Spring Message created"]
    C --> D["4. Channel dispatch"]
    D --> E["5. Handler / business logic"]
    E --> F["6. Outbound adapter / external effect"]
    F --> G["7. Commit / ack / checkpoint"]
    G --> H["8. Recovery / restart"]
    B -. "Errors may lack failedMessage" .-> X["Source error"]
    D -. "Dispatcher / task scheduling" .-> Y["Runtime error"]
    E -. "Handler exception" .-> Y
    F -. "Protocol/network/remote" .-> Z["Adapter error"]
    G -. "Unknown outcome / redelivery" .-> Z
~~~

Ask three questions:

1. **Did the Message exist yet?** The source can fail while reading files, polling DB, or connecting to the broker **before creating a Spring Message**. In that case, `failedMessage` is unlikely to exist.
2. **Which component raised the error?** A bean/channel/handler, or an external connection, protocol, parser, or client? Inspect the deepest cause and first meaningful stack frame.
3. **Which component observed or wrapped the error?** `MessagePublishingErrorHandler`, a poller, an adapter listener, a transaction interceptor, or a gateway can surface the final error at another layer.

### Example: Same Wrapper Message, Two Different Causes

~~~text
MessagingException: Failed to handle message
  caused by IllegalArgumentException: unsupported order status
  at OrderStatusTransformer...

→ Logic/payload contract issue inside the flow.
~~~

~~~text
MessagingException: Failed to handle message
  caused by ResourceAccessException
    caused by SocketTimeoutException: Read timed out
  at HTTP outbound gateway...

→ External service call issue; check deadlines and unknown outcome.
~~~

**The name `MessagingException` only tells you the error passed through Spring Messaging.** Always inspect the cause chain, endpoint bean, channel, stage, and external outcome before classifying.

## 4. Related Exceptions: Reading Them Accurately

Spring Messaging/Integration uses distinct exceptions across layers. Examples:

| Exception / Symptom | What It Usually Indicates | What You Cannot Conclude Yet |
| --- | --- | --- |
| **MessagingException** | Failure expressed in messaging context, may hold `failedMessage` | Does not mean root cause is runtime |
| **MessageDeliveryException** | Problem sending/dispatching a message | Could be missing subscriber, channel timeout, or downstream handler; check cause |
| **MessageHandlingException** | Failure while a handler processed a message | The handler itself may be an outbound HTTP/DB adapter |
| **MessageTransformationException** | Failure in a transformer | Root cause may be a data contract or a service called by the transformer |
| **MessageConversionException** | Payload/header conversion failed | Inspect converters, content type, raw data, and origin |
| **MessageRejectedException** | Message rejected by a handler/filter/router per specific policy | Does not automatically mean it should be retried |
| **TaskRejectedException/RejectedExecutionException** | Executor refused task | Not necessarily caused by external slowness; inspect pool/queue and load |
| **TransactionException** or rollback | Transaction/commit failed | DB resource may be unhealthy; check tx manager and commit timeline |
| **IOException/SocketTimeoutException/SSLException** | Low-level I/O or protocol failure | Does not guarantee remote side effects failed |

**Do not just grep class names.** An exception can be wrapped multiple times, and different Spring Integration/adapter versions may throw different classes. The table above illustrates analysis patterns, **not an absolute mapping table** for every connector.

### Reading failedMessage and Cause Chains

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;

final class FailureInspector {

    static void inspect(Throwable failure) {
        Throwable cursor = failure;
        int depth = 0;

        while (cursor != null && depth < 20) {
            System.out.printf(
                    "cause[%d]=%s: %s%n",
                    depth,
                    cursor.getClass().getSimpleName(),
                    cursor.getMessage());

            if (cursor instanceof MessagingException messaging) {
                Message<?> failed = messaging.getFailedMessage();
                if (failed != null) {
                    System.out.println("failed message id="
                            + failed.getHeaders().getId());
                    System.out.println("correlation="
                            + failed.getHeaders().get("correlationId"));
                }
            }

            cursor = cursor.getCause();
            depth++;
        }
    }
}
~~~

This is an illustrative utility; never print full payloads or exception details containing secrets in production. **`failedMessage` may be null**, especially when errors occur before the adapter constructs a `Message`. In other cases, `failedMessage` may be an **intermediate message** from a transformer rather than the original source message.

**Preserve context when wrapping exceptions:** If a handler wants to add business context, preserve the original cause and attach business correlation to logs/diagnostics instead of creating a causeless `IllegalStateException` that breaks traceability.

## 5. Inbound Adapter Errors: Before and After Message Creation

An inbound adapter converts an external event into a Spring `Message`. Depending on the adapter, this may involve opening a connection, receiving raw records, deserializing, mapping headers, filtering, constructing a `Message`, and sending it to a channel.

~~~text
Kafka/JMS/AMQP/File/HTTP source
  → connect/authenticate
  → poll/listen/read raw data
  → decode / convert / map headers
  → create Spring Message
  → send to input channel
~~~

### Errors Before Spring Message Creation

- Cannot connect to broker/remote host; DNS/TLS/authentication failures.
- File path missing, insufficient permissions, unreadable remote directory.
- Errors reading/deserializing raw bytes **before the framework builds a message**.
- Adapter container fails to start due to config/bootstrap errors.

In this group, **do not require `failedMessage` to be present**. Rely on **source record metadata, remote filenames, topic/partition/offset, request IDs, or adapter-specific diagnostics** to trace the failing event, depending on adapter capabilities.

### Errors After Spring Message Creation

- Input channel has no subscribers.
- First transformer throws an exception.
- Downstream handler rejects payload type.
- `ExecutorChannel` rejects task, `QueueChannel` is full, or consumer is stopped.

Regarding **detection site**, logs may still appear under the inbound adapter because the adapter called `send()`. Yet the root cause may reside in the **downstream runtime flow**, not the adapter's connection settings.

### Classic Example: File Poller Sees No Data

If `FileReadingMessageSource` returns no messages, do not rush to "file adapter is broken":

1. Is the endpoint **`isRunning=true`**? Is the scheduler triggering the poller?
2. Is polling occurring yet **`receive()` returns null** because the directory is empty or the filter already accepted the file earlier?
3. Do the file's name and extension match the filter and file watcher?
4. Is the file locked or missing read/move permissions?
5. Across restarts, did filter metadata/checkpoints skip the file?
6. Did the input channel actually receive the `Message` after the source read the file?

The root cause could be **runtime lifecycle**, **filter/metadata policy**, **file permissions**, or **downstream dispatch**. Seeing "files aren't processed" alone is not enough.

## 6. Outbound Adapter Errors: Did the Command Execute or Not?

Outbound adapters/gateways send messages to external systems. Example HTTP outbound gateway:

~~~mermaid
sequenceDiagram
    participant H as Spring Integration handler
    participant A as HTTP outbound gateway
    participant R as Remote API
    H->>A: Send PaymentCommand
    A->>R: POST /charge
    R-->>A: Response / timeout / connection reset
    A-->>H: Result or exception
~~~

Separate three scenarios:

1. **Request never reached remote:** DNS, connect timeout, TLS handshake, or wrong URI config; sometimes safely retryable once contract is verified.
2. **Remote returned an explicit error response:** 400 validation, 401 auth, 429 throttling, 5xx; classify per contract and retry policy.
3. **Remote executed the side effect but response was lost:** Read timeout/connection reset **does not prove the effect did not happen**. Requires an idempotency key and query/reconciliation.

### Why Is This an Adapter Error Even If the Handler Catches MessagingException?

Because the root fault lies in the **HTTP/protocol layer or response contract**. Spring Integration may wrap it in `MessageHandlingException` to attach `failedMessage`. Seeing `MessageHandlingException` on `errorChannel` does not turn the root cause into a "dispatcher error."

### Data Contract Errors at the Adapter Boundary

For example, outbound HTTP sends JSON from an older DTO version while the remote requires a new field:

~~~text
Spring Message<OrderCommand>
  → JSON converter
  → POST /orders
  ← HTTP 422: missing currency
~~~

This is a **communication contract** error—never retry it infinitely. Inspect converters, content types, schema versions, headers, and sanitized response payloads. If the bug comes from an internal Java transformer building a malformed DTO upstream of the adapter, record both **origin** and **detection site**.

### For One-Way Outbound Adapters

An outbound adapter may **emit no reply message**. Thus tests should not treat "no reply received" as an error. Instead, verify successful delivery per the adapter's contract (ack callback, external broker event, mock HTTP server, DB state) and verify the exception/recovery path on failure.

## 7. Runtime Errors of Channels and Dispatchers

**MessageChannel** is a major boundary in Spring Integration:

- **DirectChannel** invokes handlers synchronously on the sending thread; exceptions usually propagate back to the sender unless handled otherwise.
- **ExecutorChannel** dispatches to a worker thread; `send` can return before the handler finishes, and transaction/thread context does not auto-propagate.
- **QueueChannel** buffers messages for consumers to poll; persistence across restarts depends on store/transaction setup.
- **PublishSubscribeChannel** can broadcast to multiple subscribers per configuration, with error semantics governed by dispatcher/executor setup.

### No Subscribers

~~~text
Source → DirectChannel("ordersInput") → (no subscribers)

send() may throw MessageDeliveryException.
~~~

This is a **runtime wiring/dispatcher** error, unrelated to the remote broker if the source already built the Spring `Message` cleanly. How to investigate:

1. Verify the channel bean actually named **`ordersInput`** exists.
2. Verify endpoints/consumers are registered and subscribed to the right channel.
3. Check endpoint lifecycle, application context, profiles, and conditional bean configuration.
4. Check whether `DirectChannel` was swapped for another channel type during refactoring or testing.

### Saturated ExecutorChannel

~~~text
Producer send() → ExecutorChannel
  → ThreadPoolTaskExecutor
  → full queue / no free workers
  → TaskRejectedException or equivalent error
~~~

This is a **runtime coordination capacity** failure. Investigate queue capacity, active workers, rejected tasks, handler durations, backpressure, and retries—do not just raise external HTTP timeouts.

**An adapter failure can trigger a secondary runtime failure:** If outbound HTTP stalls for 30 seconds, workers stay tied up, the executor queue fills, and inbound sends start failing. The root cause is downstream latency; the immediate symptom at the input channel is task rejection. Incident reports must capture **the entire causal chain**.

### Router/Filter Errors

A router without a mapping for a key may fail, drop, or route to a default depending on config. A filter may intentionally discard messages. **Receiving no output** is not enough to prove an exception occurred; inspect **discard channels, routing rules, endpoint metrics**, and message state.

## 8. errorChannel: Where Errors Surface Depends on Thread Boundaries

Spring Integration provides **ErrorMessage** to pass a `Throwable` through message flows. However, **not every error automatically becomes an ErrorMessage**. The error path depends on how the endpoint is invoked, the channel, the adapter, and error-handling configuration.

~~~mermaid
flowchart TD
    S["Producer / Adapter"] --> C{"Channel"}
    C -- "DirectChannel" --> D["Handler runs on sender thread"]
    C -- "ExecutorChannel" --> E["Worker thread"]
    C -- "QueueChannel" --> P["Polling consumer thread"]
    D -- "Uncaught exception" --> CALL["Exception may return to sender"]
    E -- "If suitable ErrorMessage publisher exists" --> ERR["errorChannel"]
    P -- "If poller error handling publishes" --> ERR
    ERR --> REC["Error flow: log / retry / DLQ / alert"]
~~~

### DirectChannel — Synchronous Errors Can Return to the Sender

~~~text
test/send thread
   input.send(message)
     → DirectChannel
        → handler throws
   input.send(...) throws
~~~

Here a test can use **`assertThrows`** on send. If an inbound adapter calls send on the same thread, downstream errors propagate back to the adapter and are handled by the adapter container's own ack/rollback mechanics.

### ExecutorChannel — Sender and Handler Run on Different Threads

~~~text
producer thread: send() → accepted/enqueued → return
worker thread:   handle() → exception
~~~

An exception after handoff **does not automatically return** to the sending thread. Inspect the worker's **error publisher/`errorChannel`**, executor task lifecycle, and recovery policies. Simply because `send()` returned true never proves the business operation succeeded.

### Poller — Errors Can Surface in the Poll Task

~~~text
TaskScheduler
  → poller
      → source.receive()
      → handler
      → exception
  → configured error handling / logging / retry
~~~

A polling consumer can have application-configured error handling that publishes an `ErrorMessage`; inspect the endpoint/poller error channel, transaction advice, and scheduler. **Source read failures before Message creation** may carry no `failedMessage`.

### What Does an ErrorMessage Hold?

**ErrorMessage** is a Spring `Message` whose payload is a `Throwable`. It can hold **`originalMessage`** if provided by the creating code/framework. The `Throwable` may be a `MessagingException` carrying **`failedMessage`**.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

final class ErrorMessageInspector {

    static void inspect(ErrorMessage error) {
        Throwable failure = error.getPayload();

        Message<?> original = error.getOriginalMessage();
        Message<?> failed = null;
        if (failure instanceof MessagingException messaging) {
            failed = messaging.getFailedMessage();
        }

        Message<?> related = failed != null ? failed : original;
        String correlation = related != null
                ? String.valueOf(related.getHeaders().get("correlationId"))
                : "UNKNOWN";

        System.out.println("errorType="
                + failure.getClass().getSimpleName());
        System.out.println("correlationId=" + correlation);
        FailureInspector.inspect(failure);
    }
}
~~~

This snippet reuses **`FailureInspector`** from earlier and only illustrates extracting correlation source. In real applications:

- Attach **`eventId`/`operationId`, flow, endpoint, and transport context** when available, rather than relying solely on `correlationId`.
- Avoid printing raw payloads, access tokens, passwords, payment details, or sensitive exception text.
- Handle **null `originalMessage`/`failedMessage`**, especially when source failures occur prior to message creation.
- Use structured logs and proper MDC/tracing; across thread boundaries, MDC does not propagate automatically without explicit context propagation.

**Do not confuse `errorChannel` with retry:** Publishing an `ErrorMessage` does not guarantee the broker will redeliver the original message. If an error flow logs and completes normally, ack/commit behavior still depends on the adapter, container, and transaction boundaries.

## 9. Transactions and Acknowledgements Distort Failure Perception

When a broker consumer, DB transaction, and outbound API coexist in a flow, multiple completion points exist:

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Integration consumer
    participant D as Business DB
    participant H as Outbound HTTP API
    B->>C: Deliver eventId=EV-42
    C->>D: Update business state
    D-->>C: Transaction commit
    C->>H: POST with operationId=EV-42
    H-->>C: Read timeout
    Note over C: API may have already succeeded
    C-->>B: Ack/nack per adapter configuration
~~~

An HTTP failure occurring after a DB commit **does not automatically roll back** the DB. A DB rollback after an HTTP call produced a side effect **does not undo the HTTP effect**. Thus the question "adapter or runtime?" must always be paired with "**which resources already committed?**".

### Table of Common Misconceptions

| Symptom | Common Wrong Conclusion | What to Verify |
| --- | --- | --- |
| Handler throws exception | Broker will definitely redeliver | Adapter ack mode, error handler, tx rollback, and container |
| DB `save()` returns cleanly | DB has committed | Transaction manager, commit, rollback-only, propagation |
| HTTP read timeout | Remote did not execute side effect | Remote idempotency/operation status, request ID, reconciliation |
| Message was enqueued | Business handler processed it | Consumer state, queue persistence, worker execution |
| `ErrorMessage` logged | Error recovered successfully | Whether DLQ/outbox/retry state committed |
| App restarts and duplicates appear | Spring Integration emitted two events | Source redelivery, producer retry, outbox replay, business idempotency |

### DirectChannel vs. ExecutorChannel

With `DirectChannel`, the handler usually runs on the **same thread** as the sender and can join its active transaction if resources/advice are compatible. Across `ExecutorChannel`, code runs on another thread; **the sender's transaction does not follow the task by default**.

If a poller opens a transaction, sends a message to `ExecutorChannel`, and commits right after the task is accepted, a **subsequent** worker failure cannot roll back source intake. That is a **runtime/transaction boundary design** issue, even though the specific error log appears in the worker's outbound adapter.

### At-Least-Once and Post-Crash Duplicates

A consumer crashing **after committing a side effect yet before sending broker ack** will normally receive redelivery under at-least-once semantics. This is not necessarily a broker or adapter bug.

The solution is **durable idempotency**:

- **Inbox/unique constraints** tying `eventId` to business DB mutations within the same transaction.
- **Outbox** for outbound events that must be emitted after commit.
- **Idempotency keys** on HTTP/payment providers, paired with reconciliation when outcomes are unknown.
- **Correlation/tracing** across retries to separate technical attempts of the same operation.

Never rely solely on **Spring `MessageHeaders.ID`** or `ErrorMessage` IDs for deduplication across restarts: adapters can generate fresh `Message` objects on redelivery.

## 10. Retry at the Right Layer—Do Not Retry Every Error

**Retries only help if the cause is likely to clear on re-execution.** Classify causes first:

| Error Type | Example | Possible Strategy |
| --- | --- | --- |
| **Runtime configuration/wiring** | No subscribers, wrong channel ID, unregistered endpoint | Fix config/deploy; tight retries will not help |
| **Runtime saturation** | Full executor queue, lock contention | Backpressure, budgeted delayed retry, adjust capacity |
| **Data contract/permanent** | Malformed JSON, missing required field, bad route key | Quarantine/DLQ; fix producer/schema |
| **Adapter auth/config** | 401/403, expired certificate, bad broker credentials | Fix credentials/config; continuous retries are useless |
| **Transient network** | 503, connection reset, brief broker outage | Bounded retries, exponential backoff + jitter |
| **429/rate limit** | Downstream throttling | Respect `Retry-After` if present, lower concurrency |
| **Unknown side effect outcome** | HTTP timeout after POST charge | Idempotency key + query/reconciliation before unsafe replay |
| **Storage contention/transaction** | Deadlock/serialization conflict | Bounded transaction retry keeping the same business key |
| **Missing correlation/group part** | Aggregator missing a required event | Wait per SLA/timeout/recovery; retrying the current message will not fabricate the missing part |

### Multi-Layer Retry Storms

~~~text
Broker redelivery: 4 deliveries
Handler RetryAdvice: 3 attempts per delivery
HTTP client retry: 2 attempts per handler attempt

Up to 4 × 3 × 2 = 24 external call attempts
for a single business operation.
~~~

A remote adapter error can spike runtime CPU/threads/queues and trigger secondary failures. Designate a **retry owner**, cap total attempts, set end-to-end timeouts, configure backoff, define terminal recovery, and enforce idempotency.

### Classifying Exceptions and Root Causes

Never write "if `instanceof MessagingException` then retry":

~~~java
static boolean isPotentiallyTransient(Throwable failure) {
    Throwable cause = failure;
    while (cause != null) {
        if (cause instanceof java.net.SocketTimeoutException) {
            // Transient signal only; side effect outcome may still be UNKNOWN.
            return true;
        }
        cause = cause.getCause();
    }
    return false;
}
~~~

This snippet is **not a complete retry policy**. A `SocketTimeoutException` after a mutating operation still demands **idempotency/reconciliation**; 401s, validation errors, or bad data must never be classified retryable merely because they are wrapped inside `MessagingException`.

## 11. MessageStore, Correlation, and Runtime State

Not every "no output" issue is an exception. With an **aggregator/resequencer**, messages may be stored cleanly yet not yet satisfy release conditions:

~~~text
groupId = order:O-42:run-7
present steps = PAYMENT, INVENTORY
missing step = ADDRESS
group status = incomplete
~~~

**This is a waiting state, not an adapter error**, if the flow is designed to wait for three parts. Past SLA, however, it becomes a timeout requiring recovery.

### Checking MessageGroupStore Metadata

~~~java
import org.springframework.integration.store.MessageGroupMetadata;
import org.springframework.integration.store.MessageGroupStore;

class GroupDiagnostics {
    private final MessageGroupStore store;

    GroupDiagnostics(MessageGroupStore store) {
        this.store = store;
    }

    void log(String groupId) {
        MessageGroupMetadata metadata = store.getGroupMetadata(groupId);
        if (metadata == null) {
            System.out.println("group missing: " + groupId);
            return;
        }

        System.out.printf(
                "group=%s size=%d complete=%s created=%d modified=%d%n",
                groupId,
                metadata.size(),
                metadata.isComplete(),
                metadata.getTimestamp(),
                metadata.getLastModified());
    }
}
~~~

**Note:** Metadata is only a snapshot. Another thread or instance can update the group immediately after reading. **`size()`** reports the number of messages in the group, not proof of **unique business events**, because redelivery can generate new Spring Message IDs.

### Persistent Store Failures

- **`SimpleMessageStore`** in RAM loses data across JVM restarts; that is a design limit, not a file/broker adapter "eating messages."
- **`Jdbc/Redis/Mongo MessageStore`** preserves state across restarts, yet requires compatible serializers, schemas, transactions, and connection error handling.
- Completed groups may retain metadata to detect late messages. Expiring metadata too aggressively can let late deliveries open a brand-new group.
- Two instances handling the same group need proper locking/concurrency control; if double release occurs under a race, inspect **`LockRegistry`, `MessageStore`, and downstream idempotency**.
- A payload from an older version failing deserialization after deployment is a **runtime persistence compatibility** failure, potentially tied to source data schemas.

### Distinguishing Correlation Bugs from Missing Upstream Data

| Symptom | Check | Classification |
| --- | --- | --- |
| Group O-42 missing | Was `groupId` constructed accurately? | Runtime correlation mapping or producer contract |
| Group has two parts, waiting for third | Did upstream emit that event? | Possible missing source/adapter event or valid pending data |
| Group size met yet no release | Which part types/sequences does `ReleaseStrategy` require? | Runtime logic or duplicate data |
| Completed group discards late message | How is retention/expiry policy configured? | May match contract, not an exception |
| Group recreated after restart | Did persistent store/metadata survive? | Runtime persistence/recovery |

Never retry a `PAYMENT` message endlessly just because `ADDRESS` has not arrived. Retrying `PAYMENT` **will not create `ADDRESS`**, yet can cause duplicates and inflate backlogs.

## 12. Investigation Procedure: Finding the Last Healthy Boundary

An effective runbook walks **from source to destination**, combining timestamps and correlation:

~~~mermaid
flowchart TD
    S["Real source event exists?"] -->|No| A["Check adapter connection, filter, source metadata"]
    S -->|Yes| M["Spring Message created?"]
    M -->|No| B["Check decode, conversion, source exception"]
    M -->|Yes| C["Entered right channel?"]
    C -->|No| D["Check send, bean ID, dispatcher, endpoint state"]
    C -->|Yes| H["Did handler start?"]
    H -->|No| E["Check executor, poller, subscriptions, queue"]
    H -->|Yes| O["Did outbound effect/call start?"]
    O -->|No| F["Check route, filter, validator, transformer"]
    O -->|Yes| R["What did remote respond/commit?"]
    R -->|Unclear| U["UNKNOWN_OUTCOME: reconcile, no blind retry"]
    R -->|Clear| ACK["Check output, commit, ack, recovery"]
~~~

### Step 1 — Define Scope and Timing

Record **flow name, endpoint ID, instance, environment, timestamp, message type, source/destination**. Does the issue affect all messages or only a subset of `orderId`/`eventId`? Only one replica or the entire cluster?

### Step 2 — Check Lifecycle and Ingress

Are endpoints running? Is the poller ticking? Is the inbound adapter connected and assigned partitions/queues? Are real files or raw records present? Check filters/checkpoints, not just handler logs.

### Step 3 — Confirm Messages Crossed Channel Boundaries

Trace at the **input channel**, before/after transformers, and before outbound handlers. Use **`WireTap`**, logging channel interceptors, or per-endpoint metrics; never casually attach extra subscribers to a `DirectChannel`, as it does not broadcast by default and can alter dispatch behavior.

### Step 4 — Inspect Failure Point in the Cause Chain

Read **root cause**, `failedMessage`, `originalMessage`, bean ID, stack trace/endpoint name, and thread state. Did failure happen before message creation, inside the handler, or after an outbound call?

### Step 5 — Match Transactions and Acknowledgements

Did the source ack/commit offsets? Did the business DB commit? Was the outbox event published? Did the remote service accept the request? When outcome is uncertain, mark **`UNKNOWN`** instead of assuming a timeout means guaranteed failure.

### Step 6 — Determine What Recovery Already Did

Was the message retried, redelivered, sent to DLQ, discarded, saved in `MessageStore`, or swallowed by an error handler? Track **where retry attempts increment** rather than looking for a single ERROR log.

### Step 7 — Reproduce with a Test at the Exact Layer

Build a test replacing the exact failing boundary: mock HTTP for outbound failures, mock `MessageSource` for source failures, real channels/endpoints for dispatch errors, and real persistent stores/brokers for crash/ack/restart cases.

**Expected runbook output:** A concise report stating **symptom**, **first failing stage**, **root cause**, **error propagation**, **data impact**, **current recovery behavior**, and **remediation actions**, backed by verification evidence.

## 13. Java Tests: Separating Runtime Dispatch Failures from Adapter Failures

A useful test **deliberately injects failure at the exact boundary**, rather than mocking a generic exception inside a handler.

### Case A — Runtime Error from DirectChannel with No Subscribers

This case is 100% reproducible in-JVM:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.support.MessageBuilder;

class RuntimeDispatchFailureTest {

    @Test
    void failsToDeliverWhenChannelHasNoSubscriber() {
        DirectChannel orphanChannel = new DirectChannel();

        MessageDeliveryException error =
                assertThrows(MessageDeliveryException.class,
                        () -> orphanChannel.send(
                                MessageBuilder.withPayload("O-42")
                                        .setHeader("correlationId", "flow-42")
                                        .build()));

        assertNotNull(error.getFailedMessage());
        assertEquals("flow-42",
                error.getFailedMessage().getHeaders()
                        .get("correlationId"));
    }
}
~~~

**What this proves:** The failure occurs in the **channel dispatcher**, requiring no Kafka, HTTP, or DB. If an adapter sends to `orphanChannel` and logs a similar exception, the primary fault is still missing runtime subscribers/wiring.

### Case B — Adapter Error Simulated via an External Port

To contrast with dispatch errors, explicitly simulate a remote client refusing or timing out:

~~~java
import java.net.SocketTimeoutException;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;

interface PaymentPort {
    void capture(String paymentId) throws SocketTimeoutException;
}

class PaymentOutboundHandler {
    private final PaymentPort paymentPort;

    PaymentOutboundHandler(PaymentPort paymentPort) {
        this.paymentPort = paymentPort;
    }

    @ServiceActivator(inputChannel = "paymentCommands")
    public void handle(Message<String> command)
            throws SocketTimeoutException {
        paymentPort.capture(command.getPayload());
    }
}
~~~

With a fake port:

~~~java
PaymentPort unavailable = paymentId -> {
    throw new SocketTimeoutException("Remote read timed out");
};

PaymentOutboundHandler handler = new PaymentOutboundHandler(unavailable);

SocketTimeoutException error = assertThrows(
        SocketTimeoutException.class,
        () -> handler.handle(
                MessageBuilder.withPayload("PAY-42").build()));
~~~

**This is a unit test of the port/handler**, not running through a real Spring Integration endpoint. It verifies **the root cause from the external boundary**, without asserting the framework keeps `SocketTimeoutException` unwrapped when invoked through `@ServiceActivator`. In a real integration test, the exception may be wrapped in `MessagingException` and involve `errorChannel`.

### Case C — Same Adapter Error Observed at a Spring Integration Endpoint

To verify wrapping and error propagation:

1. Create a **`paymentCommands` `DirectChannel`**.
2. Register **`PaymentOutboundHandler`** as a `@ServiceActivator` bean.
3. Send a `Message` with `paymentId`, `eventId`, and `correlationId`.
4. Assert `send()` throws per endpoint contract; walk the cause chain to find **`SocketTimeoutException`**.
5. Verify **`failedMessage` or `originalMessage` if retained by the framework**.
6. Do not auto-retry payment APIs blindly in tests when the outcome might have succeeded; use fake clients and idempotency keys.

Replacing `DirectChannel` with `ExecutorChannel` **changes the observation path**: the caller may see `send()` succeed while worker exceptions must be captured via error flows, spies, or latches. Never share one `assertThrows(send())` assertion across both topologies.

## 14. Testing Error Flows for Pollers, Executors, and Inbound Adapters

Testing one synchronous handler does not cover all Spring Integration Runtime behavior. When a flow involves **pollers, executors, or broker adapters**, tests must inject errors at the right stage and observe the real error path.

### Testing ExecutorChannel

Model:

~~~text
JUnit thread
   → input.send()
   → ExecutorChannel accepts task
   → returns

Worker thread
   → handler throws
   → error handling / task completion
~~~

A test strategy:

1. Use a **`ThreadPoolTaskExecutor`** or a small controlled executor.
2. Use a **`CountDownLatch`** to know when the worker started and when it may proceed.
3. Inject an exception with a stable error code inside the handler.
4. Wire a test error flow with a `QueueChannel` or mock handler **at the location where the framework actually publishes `ErrorMessage`**.
5. Assert **no success output was emitted**, the error was observed, `failed`/`originalMessage` match when present, and no orphaned tasks remain.
6. Enforce bounded timeouts, release latches, and shut down the executor in `finally`/test teardown.

**Do not assert only `send() == true`**, as that may merely reflect **handoff**, not business success. Also **do not assume** every `ExecutorChannel` task exception appears on a global `errorChannel` unless the application configured it properly.

### Testing Poller Failures Before Message Creation

A mock **`MessageSource`** can throw inside `receive()` before returning any `Message`:

~~~java
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.Message;

class FailingMessageSource implements MessageSource<String> {
    @Override
    public Message<String> receive() {
        throw new IllegalStateException(
                "Cannot read remote file metadata");
    }
}
~~~

To test at the `IntegrationFlow` level:

- Register the source on a polling endpoint with an **explicit ID**.
- Prevent auto-starting before the test is ready; use **`@SpringIntegrationTest(noAutoStartup=...)`** where suitable.
- Trigger a controlled poll or configure a scheduler/test trigger.
- Observe the polling endpoint's error handling; here **do not require `failedMessage`** because `receive()` never returned a `Message`.
- Verify whether the endpoint keeps running/recovers or stops per policy.

### Testing Real Inbound Adapters

Tests with Kafka, AMQP, JMS, SFTP, or JDBC adapters should use proper integration test environments when verifying:

- Authentication, topic/queue/directory/table mappings.
- Serialization and content-type/headers at the ingress boundary.
- Consumer/container lifecycle and partition assignments.
- Ack/nack/offset/redelivery when handlers fail.
- Transaction behavior across restarts or network disconnects.

A mock `MessageSource` proves flow logic and source error paths, yet **cannot prove broker protocol semantics**. For external-JVM adapters, test real transports and fault injection when reliability requires it.

## 15. Observability: Gathering Evidence Instead of Guessing

You cannot tell runtime from adapter errors with a single `"failed to handle message"` log. Instrument **boundaries** instead of logging full payloads at every hop.

### What Should Structured Logs Contain?

~~~text
event=message_processing_failure
flow=orderImport
endpoint=paymentOutboundGateway
stage=OUTBOUND_ADAPTER
channel=paymentCommands
instance=payments-pod-2
messageId=3f9b...
eventId=EV-42
correlationId=checkout-O-42
attempt=2
exceptionType=MessageHandlingException
rootCauseType=SocketTimeoutException
externalSystem=payment-provider
outcome=UNKNOWN
~~~

This is a **custom application log format**, not a built-in Spring Integration format. Never log access tokens, credentials, payment details, or full payloads. Enforce privacy controls on **`eventId`/`correlationId`** and avoid placing them in metric labels.

### Metrics That Pinpoint the Failing Layer

| Metric / Signal | Interpretation |
| --- | --- |
| Inbound receive rate / poll count | Is the adapter still receiving/polling data? |
| Adapter connectivity and reconnect attempts | Are sources/targets disconnecting or failing auth? |
| Channel send failures / no subscribers | Are messages blocked by wiring/dispatch? |
| Executor active workers, queue depth, rejected tasks | Is the runtime saturated? |
| Handler duration P95/P99 | Is internal/DB/HTTP processing slowing down? |
| Outbound HTTP attempt latency, status classes | Are remote 5xx/429/timeouts rising? |
| `MessageStore` read/write failures | Is state persistence failing? |
| Retry attempts, recovery/DLQ outcomes | Are errors resolving or looping? |
| `ErrorMessage` delivered by endpoint | Which failures enter the error path? |
| Incomplete/expired `MessageGroup`s | Are correlation/partial flows timing out? |
| Queue waiting age | Where is backpressure accumulating? |

**Metric names depend on version and instrumentation.** Spring Integration integrates with Micrometer/Observation when configured, yet never assume every backend exposes identical metric names out of the box. Inspect your application's live registry/Actuator/Prometheus output.

**Do not add mismatched units together:** One inbound delivery can trigger three handler attempts and six HTTP calls due to retries. An HTTP adapter counter cannot be labeled "order count." Metrics must clearly distinguish **deliveries, attempts, message outputs, and business operations**.

### How Logs, Traces, and Metrics Work Together

~~~mermaid
flowchart TD
    M["Metric alert: HTTP latency P99 rises"] --> T["Trace: outbound gateway span slow"]
    T --> L["Logs by correlationId/eventId"]
    L --> X["Root cause: remote 503 or timeout"]
    X --> V["Check ack/commit + idempotency"]
    V --> A["Fix adapter/remote policy or runtime capacity"]
~~~

**Correlation IDs do not cross every boundary automatically.** Transformers can strip headers, transport adapters can drop unmapped headers, and tasks on worker threads lack sender MDC. Test header propagation and trace context explicitly rather than relying on one global log field.

## 16. Real-World Investigation Scenarios

### Scenario A — Kafka Inbound Receives, Yet Channel Fails to Deliver

**Symptom:** Listener logs show records received. The latest error is `MessageDeliveryException`.

**Verification chain:**

1. Did the adapter decode the record and call `send`? If yes, this is no longer a Kafka connection issue.
2. Is the channel ID right? Are subscribers present? Was the endpoint created under active profiles/conditions?
3. Was the endpoint stopped via Control Bus or flow lifecycle?
4. Is the error on the sender thread, and how does it affect ack/offset? Check the specific container/adapter.

**Likely diagnosis:** **Runtime wiring/lifecycle** caused dispatch failure, surfacing at the Kafka inbound adapter.

**Fix:** Restore the subscription/endpoint bean and verify ack/redelivery; do not rotate broker credentials when logs prove the consumer is reading records cleanly.

### Scenario B — Remote HTTP Slows Down, Then Executor Rejects Tasks

**Symptom:** Initially the outbound gateway times out. Minutes later, the input channel sees task rejections.

**Causal chain:**

~~~text
Remote API latency spikes
    → workers hold threads longer
    → executor queue builds up
    → pool hits limit
    → ExecutorChannel starts rejecting tasks
~~~

**Initial root cause:** Adapter/downstream latency. **Secondary failure:** Saturation at the runtime executor. Raising the thread pool endlessly can worsen pressure on the remote service.

**Remediation:** Sensible timeouts, backpressure, rate limits, circuit breakers, bounded retries, queue sizing, and idempotency contracts; watch throughput, worker occupancy, and remote health.

### Scenario C — File Inbound Adapter "Cannot Read Files"

**Symptom:** Files sit on disk with no output.

Distinct cases:

- Poller **`isRunning=false`**: runtime/lifecycle failure.
- Poller runs, source `receive()` returns null because **`AcceptOnceFileListFilter`/metadata** already marked the file: inspect filter/checkpoints, not OS read errors.
- Source `receive()` throws **`AccessDeniedException`**: filesystem permission error at the adapter boundary.
- File became a `Message` yet transformer fails parsing: business data contract/transformer error.
- Message entered `QueueChannel` yet consumer is stopped: runtime backlog.

**Solution:** Instrument each boundary instead of wiping metadata stores or restarting repeatedly before understanding duplicate impact.

### Scenario D — Kafka Redelivery Causes Double Charge

**Symptom:** Two payment transactions appear for the same `paymentId` after a pod restart.

**Insufficient conclusion:** "The Kafka adapter has a bug sending twice."

Timeline to verify:

~~~text
Delivery #1
  → HTTP charge succeeds at provider
  → App crashes before consumer acks/commits offset
Delivery #2
  → message is redelivered
  → handler lacks a stable idempotency key
  → second HTTP charge occurs
~~~

**Classification:** Redelivery is source semantics; the business bug is missing idempotency/reconciliation on the outbound side effect, while the crash window/ack boundary is a key runtime factor.

**Fix:** Pass a provider idempotency key, use durable inbox/outbox where appropriate, reconcile `UNKNOWN_OUTCOME`, and test crashes **after effect, before ack**.

### Scenario E — Aggregator Emits Nothing Even Though Every Service "Sent"

**Symptom:** Three services log publishing events, yet the aggregator produces no output.

Check:

1. Does **publish accepted** mean the broker persisted and the consumer received it?
2. Did `CorrelationStrategy` compute the **exact same `groupId`** for all three messages?
3. Did messages lose **`correlationId`/sequence headers** passing through adapters/transformers?
4. Does `ReleaseStrategy` require **three distinct step types** or merely size=3? Any duplicates?
5. Does `MessageGroupStore` hold complete state; is the timeout/reaper running?

**Classification:** Could be adapter delivery, header mapping, runtime release logic, or a source genuinely missing one part. Producer publish metrics alone cannot prove "reached the aggregator."

### Scenario F — Errors Appear Only After Redeploy

**Symptom:** Before deployment everything worked; afterward, persistent `QueueChannel`/`MessageGroupStore` fails to read stored messages.

**Investigation:** Serializers, renamed payload classes/packages, schemas, custom headers, backend connection/version changes, migrations, and reading legacy messages. If the source broker is healthy while `MessageStore` deserialization fails, the fault lies in **runtime persistence compatibility**, not the broker.

**Remediation:** Schema evolution, controlled migration/quarantine, and restart tests using prior-version data. Never delete live message stores just to "clear errors" without verifying business recovery.

## 17. Practice: Finding the Root Cause in a Multi-Layer Flow

**Scenario:** An Order Import service uses Spring Integration:

~~~text
Kafka inbound adapter
  → ordersInput (DirectChannel)
  → validateAndMapOrder (Transformer)
  → validatedOrders (ExecutorChannel)
  → orderHandler
  → business DB
  → HTTP outbound gateway
  → orderConfirmed
  ↘ error flow / DLQ
~~~

Production symptoms:

- Some orders produce no output even though the Kafka consumer read their records.
- Some handlers log `MessageHandlingException` wrapping `SocketTimeoutException`.
- Executor rejections spike after HTTP P95 climbs from 300 ms to 8 seconds.
- After restarts, some `eventId`s appear twice in logs.

### Task 1 — Pick the Right Measurement Points

Add **controlled** instrumentation at:

1. **Inbound adapter received:** source record ID, partition/offset when available, `eventId`.
2. **`ordersInput`:** confirm message was dispatched.
3. **Transformer output:** verify payload type, business key, and correlation headers.
4. **Executor queue/handler start:** measure queue wait and rejected tasks.
5. **DB commit:** source of truth for business updates.
6. **Outbound HTTP:** request/response status, latency, external operation ID.
7. **Error flow:** exception chain, failed/original message, recovery outcome.
8. **Broker ack/offset:** whether the message was committed or remains eligible for redelivery.

Never log full payloads containing customer data. Use `WireTap` or channel interceptors in test profiles at targeted boundaries without accidentally turning `DirectChannel` into a broadcast channel.

### Task 2 — Classify Three Distinct Failures

| Observation | Primary Cause Group | Additional Evidence Needed |
| --- | --- | --- |
| Record received, transformer never ran, channel lacks subscribers | Runtime wiring/lifecycle | `DirectChannel` subscriptions, endpoint IDs, conditional beans |
| Transformer ran, handler called HTTP and remote timed out | Adapter/external boundary | Remote request ID, timeout config, root cause, side effect outcome |
| HTTP slow, queue full, executor rejects | Runtime saturation triggered by external latency | Thread dumps, active/queued/rejected metrics, arrival/retry rates |

What matters is the **causal relationship**, rather than slapping one broad `"adapter broken"` label on all three.

### Task 3 — Inspect Post-Failure Data State

- Did the DB commit the order update? If so, will handler retries create duplicate updates?
- Did outbound HTTP execute the side effect? Read timeouts require reconciliation, not assuming failure.
- Did Kafka offsets commit before or after handler completion? That depends on adapter/container and thread boundaries.
- Did the DLQ successfully persist the message with `eventId`, or only log intent to send?
- With multi-layer retries, did total external attempts exceed budget?

### Task 4 — Run the Reproduction Test Suite

| Test | How to Trigger | Assertions |
| --- | --- | --- |
| No subscribers | `DirectChannel` with no consumer | `MessageDeliveryException`, `failedMessage`/correlation if present |
| Transformer payload error | Feed schema-invalid input | Exception at transformer; outbound never invoked |
| Remote HTTP 503 | Fake HTTP server returns 503 | Classify transient/contract, bounded retry |
| Remote timeout after side effect | Fake provider saves operation then drops response | Outcome `UNKNOWN`, same `idempotencyKey` on reconciliation/retry |
| Executor saturated | Latch holds workers, fill queue | Rejection observed; no false success ack |
| Poller `receive()` throws | Mock `MessageSource` throws | Error handling records source failure without requiring `failedMessage` |
| Async handler throws | `ExecutorChannel` + fake handler throws | Sender send may succeed; matching error flow verified |
| Error flow swallows error | Error handler logs then returns | Verify real ack/commit rather than assuming redelivery |
| Duplicate delivery | Two `Message`s with different IDs, same `eventId` | Idempotent business effect, stable correlation |
| Restart after commit, before ack | Real broker + DB, fault injection | Redelivery possible; business effect occurs once |
| `MessageStore` serializer error | Persist old-version message, upgrade code | Readable or safely migrated/quarantined |
| Correlation missing one part | Send only 2/3 message types | Does not release prematurely; explicit timeout/recovery |

**Testing scope note:** In-JVM tests with `DirectChannel` and fake HTTP do not prove broker acks, DB transactions, or crash recovery. Those require integration/end-to-end tests with real adapters and stores.

## 18. On-Call Incident Checklist

### Before Editing Configuration

- Do you have timestamps, endpoint ID, channel ID, instance, and **correlation/`eventId`** to trace?
- Do you know whether the first error occurred **before or after Spring Message creation**?
- Do you have proof the source adapter **actually received data**, or only producer-side "sent" reports?
- Have you checked **`endpoint.isRunning`**, poller schedules, subscriptions, and executor capacity?
- Have you read the **root cause** and stack trace, not just the top line of `MessagingException`?
- If the error is an `ErrorMessage`, did you check `originalMessage`/`failedMessage` **when present**?
- Did you separate remote HTTP/DB errors from handler wrapper exceptions?
- For connection resets/timeouts, did you verify **`unknown outcome`** before replaying side effects?
- At which layers do retries and recovery sit; how many times can one operation be called?
- Are `MessageStore`/`MetadataStore` durable and serializer-compatible across restarts?
- In what order do transaction commits, broker acks/offsets, and outbound publishes execute?
- Did you check rates/metrics across queues, executors, pollers, and external systems instead of guessing from one log line?

### Before Declaring the Incident Resolved

- Is there a test reproducing the old failure that PASSES after the fix?
- Are retries on permanent errors bounded or routed to quarantine?
- Are messages protected from silent "loss" via error handlers catching and faking success acks?
- Are duplicate business side effects blocked across redeliveries and restarts?
- Does the error path retain `correlationId`/`eventId` and an observable recovery outcome?
- Have alert metrics for both root cause and secondary errors returned to normal?
- Are endpoints/adapters running and throughput stably recovered?
- If manual replay is needed, are idempotency and outcome reconciliation plans ready?

## 19. Self-Check Questions

**1. Logs show `MessageHandlingException` at an HTTP outbound gateway. Can you conclude the bug is in Java handler logic?**

**No.** The handler may be an adapter calling an external service. Inspect the cause chain and remote status. A `SocketTimeoutException` from an external HTTP call can be wrapped as `MessageHandlingException`.

**2. A Kafka adapter logs an error while sending to the input channel, yet the broker connection is healthy. What should you check first?**

**Wiring/subscribers/endpoint lifecycle, channel dispatch, and downstream handlers**, after confirming the adapter created a `Message` and called send. An error surfaced at the adapter is not necessarily Kafka's fault.

**3. Does an `Exception` from a handler behind `ExecutorChannel` always propagate back to the producer thread?**

**No.** Workers run on different threads. You must inspect error handling, task completion, transactions, and source acks separately.

**4. Why do polling sources failing before creating a `Message` typically lack `failedMessage`?**

**Because** no Spring `Message` exists yet to reference. Rely on source metadata, adapter diagnostics, and root cause rather than blaming a transformer for stripping correlation.

**5. Does an HTTP read timeout allow resending a payment charge with a new `operationId`?**

**No.** The outcome may already have succeeded. Use a provider-supported **stable idempotency key**, query/reconcile, and retry per contract.

**6. An aggregator has group size=2 while awaiting 3 steps. Is that a runtime error or an adapter error?**

**Cannot conclude yet.** The group may be waiting validly; check SLAs, the third source message, correlation mapping, release conditions, and timeout policies.

**7. After fixing an HTTP connectivity issue, the executor remains full. Is the root cause still active?**

**Possibly** a backlog/retry storm accumulated. Shed load in a controlled manner, monitor queue wait, active workers, retry budgets, and capacity; fixing the connection alone does not immediately clear secondary backlogs.

## Conclusion

**Distinguishing runtime errors from adapter errors** does not mean picking a label from a single exception class. In Spring Integration, the **runtime** manages dispatch, endpoint lifecycle, pollers, executors, transactions, retries, message stores, and correlation; **adapters** connect those mechanisms to external sources and destinations over protocols. A failure can originate in one layer yet be detected or wrapped in another.

Diagnose by **stage**, from **source → adapter → Spring Message → channel → handler → outbound adapter → commit/ack → recovery**, preserving the **cause chain**, **`failed`/`originalMessage` when available**, **`correlationId`/`eventId`**, per-boundary metrics, and the state of each resource. Only then select the right fix: configuration/lifecycle, backpressure, data contracts, bounded retries, DLQ/quarantine, idempotency, or external outcome reconciliation.

An easily debuggable system does not merely emit lots of logs; it captures **accurate evidence at every boundary**, tests reproducing incidents, and clear recovery policies so adapter failures do not topple the runtime, and runtime failures are never misdiagnosed as connectivity outages.

## References

- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Testing](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Framework API — MessagingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html)
- [Spring Framework API — ErrorMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html)
- [Spring Framework API — MessageDeliveryException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageDeliveryException.html)
