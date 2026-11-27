# Adapter error channel

**Chapter:** Channel adapter  
**Topic:** Adapter error channel  
**Learning scope:** `SPRING_INTEGRATION_PATTERN` — implementing Enterprise Integration Patterns with Spring Integration, combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation so message flows are testable, observable, and recoverable on failure.

## 1. Lesson objectives

Upon completing this lesson, you will be able to:

- Explain the role of an **error channel** at the channel adapter boundary and distinguish it from normal data channels.
- Know when an exception is **thrown back to the calling thread**, when it is **wrapped into an `ErrorMessage`**, and when it is handed to a listener/container error handler.
- Inspect `MessagingException`, `failedMessage`, headers, and correlation IDs to identify which message failed.
- Design error handling for **polling inbound adapters**, **message-driven inbound adapters**, and **outbound adapters**.
- Combine error channels with retries, transactions, ACK/offsets, dead-letter queues (DLQ), idempotency, and operational observability.
- Write tests that verify real failure behavior rather than merely checking that a log line appeared.

## 2. What is an adapter error channel?

A **channel adapter** moves data across the boundary between an external system and a Spring Integration flow. An **inbound adapter** receives from files, email, JMS, AMQP, Kafka, HTTP, or other sources and constructs `Message<?>` instances for the flow. An **outbound adapter** receives messages from the flow and sends data to an external service.

An **error channel** is a `MessageChannel` used to transport error information as an `ErrorMessage`. It is an **application-level** error-handling path. It lets errors be recorded, classified, alerted on, quarantined, or routed to recovery flows. However, an error channel does not automatically guarantee that a message will be redelivered, a transaction will roll back, or a consumer will NACK: that behavior depends on the adapter, threads, transaction manager, broker, and error handler configuration.

For example, a polling adapter reads a CSV file and sends it to a Transformer. If the transformer fails to parse a column as a number, four separate questions must be answered:

1. **Where did the error occur?** File adapter, Transformer, Service Activator, or target system?
2. **Who observes the exception?** Calling thread, poller, executor, listener container, or gateway?
3. **Where is the error routed?** Exception thrown to caller, `ErrorMessage` on an error channel, retry advice, or transport-specific mechanism?
4. **What happens to the data?** Kept, rolled back, redelivered, moved to quarantine/DLQ, or mistakenly treated as succeeded?

An error channel organizes the answer to the third question; a complete solution must address all four.

## 3. Success flow and error flow

~~~mermaid
flowchart LR
  S["External source: file / broker / HTTP"] --> A["Inbound adapter"]
  A --> C["inputChannel"]
  C --> X["Transformer / Router / Service Activator"]
  X --> O["Outbound adapter"]
  O --> T["External target"]
  A -. "Error caught by adapter/poller" .-> E["errorChannel"]
  X -. "Error caught at async/poller boundary" .-> E
  O -. "Error caught by invoking layer" .-> E
  E --> CL{"Classify"}
  CL --> L["Log + alert"]
  CL --> Q["Quarantine / DLQ"]
  CL --> R["Retry / recovery policy"]
~~~

The dashed arrows represent **possibilities when an appropriate catch-and-publish mechanism exists**, not a guarantee that every exception automatically lands on an error channel. For instance, a handler wired to a `DirectChannel` on the same thread may throw the exception directly back to `send()`; in that case, an error channel is not necessarily used.

### 3.1 ErrorMessage vs. business messages

A business message typically carries a payload such as `OrderPlaced` or `InvoiceFile`. An `ErrorMessage` is a message whose payload is a `Throwable`; in many cases, that payload is a `MessagingException` holding details about the message that failed.

| Component | Purpose |
|---|---|
| `ErrorMessage` | Message envelope for transporting an exception across a `MessageChannel`. |
| `ErrorMessage.getPayload()` | The `Throwable` to classify and record. |
| `MessagingException` | Exception that may be linked to a message; call `getFailedMessage()` to retrieve the related message if present. |
| `ErrorMessage.getOriginalMessage()` | Where available, references the original message supplied by the error publisher. |
| `errorChannel` header | Error-handling channel address per the contract of the endpoint/gateway and specific invocation. |
| `replyChannel` header | Destination for reply results; **do not** use it in place of an error channel. |
| Global `errorChannel` | Standard default error channel name used by the framework when no specific error destination applies. |

Not every exception has a `failedMessage`. An error while **polling the source** can happen before the adapter even creates a Spring `Message`; in that case only the exception and poller context exist.

## 4. Most critical question: which thread is the exception running on?

In Spring Integration, error semantics are tightly bound to how messages are dispatched.

| Context | Typical behavior | What to verify |
|---|---|---|
| Synchronous `DirectChannel` | Handler exception typically returns to the `send()` caller. | Does the caller catch/rethrow? Is an outer poller or adapter catching it and emitting `ErrorMessage`? |
| `ExecutorChannel` or async processing | Caller may finish before the handler throws. | Which executor/error handler receives the failure? Is there an error channel with subscribers? |
| `QueueChannel` + poller | Poller dequeues messages and runs downstream on poll ticks. | Poller error handling and transaction advice; is the message returned on error? |
| Polling inbound adapter (file, JDBC...) | Poller controls when data is fetched and fed into the flow. | Poller/endpoint `errorChannel` setup and how the source tracks fetched items. |
| Message-driven inbound adapter (AMQP/JMS...) | Listener/container receives from external system. | Does the listener emit `ErrorMessage`? How do exceptions affect ACK/rollback/requeue? |
| Outbound adapter in a synchronous flow | External send may throw directly on the processing thread. | Who catches it: caller, advice, gateway, or an upstream poller? |
| Messaging gateway | Caller may await a reply or error via the corresponding channel. | Timeouts, error-to-reply/HTTP status mapping, and exceptions surfaced to the API. |

**Never assume "all errors go to the global errorChannel."** The exact same business error can reach the caller or an error flow depending on where async boundaries sit and how endpoints are configured.

## 5. Dedicated error channel or global errorChannel?

Spring Integration supports several ways to specify error destinations, depending on the endpoint type:

- **Endpoint/poller error channel:** routes errors caught by the adapter or poller itself to a named channel, such as `adapterErrors`.
- **`errorChannel` header:** a message may carry an error-handling destination header, common in request–reply or async flows. How an endpoint uses the header depends on its contract.
- **Global `errorChannel`:** the default channel named `errorChannel` in the context, useful for errors not routed to a dedicated destination.

Destination precedence and whether an error is emitted at all **are not identical across all adapters**. Read the contract of the specific adapter you use and verify with tests; avoid claiming an endpoint-level channel always overrides the header or vice versa across all of Spring Integration.

Use dedicated channels for groups with different handling policies. For example:

| Error channel | Source | Policy |
|---|---|---|
| `invoiceImportErrors` | Poller reading invoice files | Record reason, quarantine file, alert operators. |
| `orderConsumerErrors` | Broker order consumer | Classify transient vs. permanent; tie to appropriate NACK/DLQ. |
| `partnerOutboundErrors` | Sending data to partners | Bounded retry, circuit breaker, record unsent commands. |
| `errorChannel` | Errors without a dedicated path | Observe and alert; avoid letting critical failures vanish into logs. |

If using a `PublishSubscribeChannel` as an error channel, each subscriber must have clear responsibilities; one failing subscriber can impact others depending on dispatch/executor settings. Verify the error path still operates under heavy load.

## 6. Java DSL example: polling adapter routing errors to a dedicated channel

Problem: every second the application checks `/srv/import/invoices` to import CSV invoices. If a file is corrupted or the importer fails, the system needs diagnostics delivered to `invoiceImportErrors`.

The example below focuses on the `poller → flow → error channel` boundary; assume Spring Integration Java DSL, the file adapter, Spring Configuration, and an `InvoiceImporter` bean are in place.

~~~java
@Configuration
@EnableIntegration
public class InvoiceFileIntegration {

    @Bean
    public MessageChannel invoiceImportErrors() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow invoicesFromFolder(InvoiceImporter importer) {
        return IntegrationFlow
                .from(
                    Files.inboundAdapter(
                        new java.io.File("/srv/import/invoices"))
                        .patternFilter("*.csv"),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(java.time.Duration.ofSeconds(1))
                               .maxMessagesPerPoll(5)
                               .errorChannel("invoiceImportErrors"))
                )
                .handle(java.io.File.class, (file, headers) -> {
                    importer.importOnce(file.toPath());
                    return null;
                })
                .get();
    }

    public interface InvoiceImporter {
        void importOnce(java.nio.file.Path csvFile);
    }
}
~~~

**Part-by-part explanation:**

1. `Files.inboundAdapter(...)` creates a message source that emits file-payload messages whenever matching files appear.
2. `Pollers.fixedDelay(...)` actively pulls data; `maxMessagesPerPoll(5)` caps messages per poll cycle.
3. `.errorChannel("invoiceImportErrors")` declares the poller's error destination; when failures pass through the poller's error handler, they are published to this channel per contract.
4. `importer.importOnce(...)` expresses the **idempotency** requirement; real importing must avoid creating duplicate invoices if a file is reprocessed.
5. `return null` terminates the one-way flow after the handler completes.

This example shows only **how errors are routed**. It does not yet implement full archiving/quarantine, database transactions, persistent processed-file filters, or safe post-commit file moves. Those are necessary when crash recovery is required.

### 6.1 Handler receiving ErrorMessage

You can build a Spring Integration component to consume errors from the configured channel:

~~~java
@Component
public class InvoiceImportErrorHandler {

    private static final org.slf4j.Logger log =
            org.slf4j.LoggerFactory.getLogger(
                    InvoiceImportErrorHandler.class);

    @ServiceActivator(inputChannel = "invoiceImportErrors")
    public void onError(org.springframework.messaging.support.ErrorMessage error) {
        Throwable failure = error.getPayload();

        org.springframework.messaging.Message<?> failed = null;
        if (failure instanceof org.springframework.messaging.MessagingException ex) {
            failed = ex.getFailedMessage();
        }

        Object eventId = failed == null
                ? null
                : failed.getHeaders().get("eventId");

        log.error("Invoice import failed, eventId={}", eventId, failure);

        // Next: classify the error, persist a quarantine record, or alert.
        // Do not assume logging alone will retry or requeue the message.
    }
}
~~~

`failedMessage` can be `null`; file-read errors at the source can happen before a message is constructed. On other error paths, `ErrorMessage.getOriginalMessage()` can also help retrieve context when supplied by the error publisher.

**Very important note:** the handler above only **logs the failure**. If retries and data recovery are required, you must also design mechanisms deciding which files are polled again, which move to quarantine, which transactions roll back, and which errors must propagate. Never treat a logging handler as a guarantee of successful handling.

## 7. Error sources by position in the channel adapter

### 7.1 Errors before creating a Message

An adapter can fail on FTP/SFTP, JDBC, or HTTP connections, file permissions, serializer setup, or authentication before constructing a `Message`. In this case:

- There may be no `failedMessage` or full business headers.
- Attach non-message metadata: endpoint name, destination, path/file ID, poll timestamp, exception type, and operation trace ID.
- Retry behavior normally relies on **poller/source or connection policies**, not resending a message that was never created.

### 7.2 Errors during downstream transformation and processing

The inbound adapter may construct a message successfully, only for a downstream `Transformer`, `Filter`, `Router`, or `Service Activator` to throw. If they execute synchronously inside the same poller transaction, the exception can propagate back to the poller and be observed by its error handler. If an async channel sits in between, the error happens on another thread and error handling must be configured at that boundary.

### 7.3 Outbound errors

An outbound adapter can encounter API timeouts, broken broker connections, rejected database statements, or failed HTTP status codes. If the outbound handler runs off a `DirectChannel`, the error can propagate to the caller. If run by a poller or executor, that layer's error handler may emit an `ErrorMessage` per configuration.

Distinguish **timeouts** from **deterministic failures**: a timed-out HTTP request may already have been processed by the partner. Retrying without an idempotency key risks duplicate transactions.

## 8. Message-driven inbound: error channel and broker ACK

A message-driven adapter is typically triggered by a listener/container from RabbitMQ, JMS, or similar systems. When downstream throws an exception, inspect both the **Spring Integration error path** and the **transport acknowledgement path**:

~~~mermaid
flowchart TD
  B["Broker delivers message"] --> A["Inbound listener adapter"]
  A --> H{"Downstream processing"}
  H -->|Success| OK["ACK / commit per config"]
  H -->|Exception| EH{"Who handles exception?"}
  EH -->|Listener/container still sees error| N["Rollback / NACK / retry / DLQ per transport"]
  EH -->|ErrorMessage handled| E["Error channel handler"]
  E --> POLICY{"Return policy"}
  POLICY -->|Error treated as handled| ACK["May ACK/commit"]
  POLICY -->|Error validly propagated| N
~~~

These branches illustrate **possible behaviors**, not defaults for every listener. Under a given configuration, an error flow absorbing the exception may lead the adapter to treat the delivery as complete; under another, the error reaches the container for rollback. Always verify with tests against a real broker and container.

An order-processing consumer should follow clear rules:

- **Transient failure:** retry with backoff and caps; if still failing, preserve redelivery capability via ACK/rollback policy.
- **Permanent failure:** quarantine the payload or route to a DLQ via the broker's mechanism; record reason, `eventId`, timestamp, and attempt count.
- **Business commit succeeded before ACK could be sent:** the message may be redelivered, so business logic must be idempotent.

### 8.1 Special considerations for Kafka

Kafka is a partitioned log and consumers track offsets. On failure, sending an `ErrorMessage` onto a Spring Integration channel **does not automatically control** seeks, offset commits, or retry topics. Coordinate Kafka listener/container setup, error handlers, and retry/DLT policies. Ordering remains per-partition; repeated retries can stall subsequent records on the same partition.

### 8.2 JMS and AMQP

- With **JMS**, acknowledgment modes / transacted sessions and the provider govern commit, rollback, and redelivery; the application error channel is only part of the pipeline.
- With **AMQP/RabbitMQ**, distinguish producer-side publisher confirms from consumer-side ACK/NACK, requeue, and dead-letter exchanges; none of these happen automatically just because a flow has an `errorChannel`.

## 9. Error channel, retry advice, recovery, and DLQ do not replace each other

| Mechanism | Question it answers | What it does not guarantee by itself |
|---|---|---|
| `errorChannel` | Which flow receives error notifications? | Retries, rollbacks, or durable persistence. |
| Retry advice / retry template | Should the failed operation be retried in-process? | Surviving a process crash. |
| Poller/listener transaction | How are reception and transactional resources committed/rolled back? | Rolling back external systems outside the transaction. |
| Broker redelivery | Which unconfirmed messages are re-sent? | Preventing duplicate business effects. |
| DLQ / quarantine | Where are unprocessable messages held for inspection? | Auto-fixing bad data or safe replay. |
| Idempotent consumer | Does re-running an event cause duplicate business effects? | Ensuring producers/brokers never lose messages. |

### 9.1 Avoiding infinite retries

If a handler throws on every attempt, the listener immediately requeues, and there is no backoff, the same poison message can spin endlessly—burning CPU, hammering the database, and starving valid messages.

Sample policy:

1. Classify errors as **transient** (network timeout, rate limit, busy resource) vs. **permanent** (bad schema, missing required field, config-level permission denial).
2. Retry transient errors with bounded attempts, exponential backoff, and jitter.
3. Once thresholds are exceeded, persist payload/reference along with exception and correlation into a clearly owned DLQ/quarantine.
4. Prevent premature ACKs or commits; align exception policy with broker/container mechanics.
5. Support controlled replay after fixing root causes; consumers must be idempotent.

### 9.2 Never swallow exceptions unintentionally

Suppose a DB error occurs, the poller sends an `ErrorMessage` to the error flow, and the error handler merely logs and returns normally. Depending on how the error handler is attached to the poller and transaction boundary, the caller may treat the error as resolved. If rollback or redelivery is required, ensure failure state **surfaces to the layer authorized to roll back/NACK**, or recover the message via an independent durable mechanism. Never infer transaction rollback from a log line in an error channel.

Conversely, simply throwing from an error handler does not guarantee the broker will NACK; sometimes the error flow runs off the original thread or transaction. Always test end-to-end on the real adapter.

## 10. Correlation and preserving context on failure

In a flow spanning Gateway → Router → Transformer → Splitter → Aggregator → outbound adapter, failures can occur after multiple new messages are created. A good error handler must reconstruct which business event was affected.

Maintain:

- **`eventId`**: immutable identifier of the business event, used for idempotency.
- **`correlationId`**: identifier of a message group or request–reply; must stay consistent with the Aggregator strategy.
- **`traceId`/`spanId`**: links logs and distributed traces across adapters/transports.
- **`source`/`destination`**: endpoint name, protocol, queue/topic, or permitted file source info.
- **Retry metadata**: attempt count, first failure timestamp, error category, and applied policy.

`MessageHeaders.ID` (each Spring message's ID) helps debugging, yet **cannot replace `eventId`**. A single business event can traverse multiple transformations and republishes with different Spring message IDs.

When failures occur before a Spring message exists, capture source or poll-cycle metadata separately. Avoid logging tokens, secrets, full sensitive payloads, or personal data just to diagnose ordinary errors.

## 11. How do Router, Filter, Splitter, and Aggregator handle errors?

### 11.1 Router/Filter

A Router may route a message to a channel with no subscribers; a Filter may drop a message based on business conditions. **A legitimately filtered message is not the same as an exception.** Clearly distinguish intentional skips, permanent data errors, and transient technical errors requiring retries.

For example, a `Filter` dropping a duplicate file because `eventId` was already processed is a business decision that can mark completion. Conversely, a Transformer failing to parse a file is a data error needing quarantine and a recorded reason.

### 11.2 Splitter/Aggregator

A Splitter produces multiple child messages from one source; an Aggregator holds group state until a release strategy triggers. If some child messages fail:

- The error channel may receive an error for **a single child message** while the Aggregator waits for the rest of the group.
- Define correlation keys, sequences, and timeouts so groups do not hang forever.
- To recover across restarts, use a persistent `MessageGroupStore` and appropriate duplicate-child protection.
- A failure in one branch does not automatically roll back side effects already committed in another branch.

### 11.3 Messaging Gateway

A Gateway turns message sending into a method call returning a result. When running synchronously, exceptions can be thrown back to the caller. With reply/error channels and async flows, define timeouts, error-to-response mappings, and late-reply handling. For HTTP, an error handler that only logs without producing a response can leave clients hanging until timeout.

## 12. Designing a classifying error flow

An error flow can follow three steps: **normalize error details → classify → apply policy**. Use `ErrorMessage` as input rather than forcing every exception into one class.

~~~mermaid
flowchart TD
  E["ErrorMessage / Throwable"] --> N["Extract source, failedMessage, eventId"]
  N --> K{"Classify root cause"}
  K -->|Bad schema / payload| Q["Quarantine + data alert"]
  K -->|Network / timeout| RT["Bounded retry + backoff"]
  K -->|Auth / config| OP["Ops alert + halt failing source"]
  K -->|Unrecognized| U["Persist context + urgent alert"]
  RT --> D{"Retries exhausted?"}
  D -->|No| X["Retry per policy"]
  D -->|Yes| Q
~~~

**Classification must inspect the root cause**, as `MessagingException` can wrap `IOException`, `DataIntegrityViolationException`, parse exceptions, or timeouts. Even so, exception class alone is not always enough: HTTP 429 may be transient and HTTP 400 usually permanent, but always follow the API contract and response details.

Pseudocode for a policy illustrating behavior rather than binding directly to a specific broker's ACK callback:

~~~text
onError(errorMessage):
    failed = extractFailedMessageIfPresent(errorMessage)
    reason = unwrapRootCause(errorMessage.payload)
    context = correlate(failed, endpointName, eventId, traceId)

    if permanent(reason):
        persistQuarantine(context, reason)
        applyTransportCompletionPolicy()
    else if retryable(reason) and retriesRemaining(context):
        scheduleRetryWithBackoff(context)
        applyTransportRetryPolicy()
    else:
        persistDeadLetter(context, reason)
        alertOperator(context)
        applyTransportCompletionPolicy()

    // completion/retry policy must be tied to the transaction, ACK, or offset
    // of the corresponding adapter; never infer it from ErrorMessage alone.
~~~

Persisting to quarantine/DLQ can itself fail; monitor it and decide whether to ACK or roll back. In workflows where message loss is unacceptable, treat this as a critical failure rather than silently ignoring it.

## 13. Hands-on exercise: three error boundaries

Build an application that imports invoices from files, validates them, and sends them to an invoice service via an outbound HTTP adapter. Attach an `eventId` to each import and use an idempotent handler on the invoice creation side.

**Phase A — Polling source:** Create a CSV file with an invalid amount column. Check whether the poller/error handler emits an `ErrorMessage`; if so, inspect the exception payload and whether `failedMessage` exists. Then check where the file remains and whether it gets picked up again.

**Phase B — Downstream synchronous/async:** Connect the Transformer with a `DirectChannel` and make the handler throw. Switch the boundary to an async channel and repeat. Compare exceptions returning to the caller vs. `ErrorMessage` reaching the error flow; also test what happens when the error channel has no subscribers.

**Phase C — Broker outbound/inbound:** Wire adapters to a broker and simulate failures on both publish and consume. Verify the differences among outbound exceptions, publisher confirms, consumer ACKs, rollback/redelivery, and DLQs. If using Kafka, verify offset commits and replay behavior; do not describe Kafka using RabbitMQ ACK terminology.

Suggested test matrix:

| Case | How to trigger failure | What to measure/observe |
|---|---|---|
| Poller cannot read source | Revoke file permissions or stop external source. | Does error context retain endpoint/source? Do connection retries behave appropriately? |
| Transformer data error | Invalid CSV schema or bad timestamp. | What does `ErrorMessage` contain? Are quarantine handling and `eventId` tagging accurate? |
| Transient Service Activator failure | Simulate DB timeout. | Bounded retry and backoff; do rollback or redelivery happen as expected? |
| Outbound timeout | Slow target or dropped connection. | Could the target have received it before timeout? Is the idempotency key preserved? |
| Duplicate delivery | Resend the same `eventId`. | Only one business outcome is committed. |
| Error handler also fails | Shut down the quarantine DB. | Is the secondary error recorded/propagated? Are data-losing ACKs prevented? |
| Error channel has no subscribers | Leave error channel unsubscribed. | How does the framework report it, and does monitoring alert? |
| Mid-flight restart | Stop process before/after business commit. | Data survives, reprocesses cleanly, and creates no duplicate side effects. |
| Multiple consumers | Run multiple instances/threads. | Observe ordering, retries, consumer lag, DLQ depth, and contention handling. |

**Pass criteria:** you can pinpoint which message failed, which layer threw, which boundary owns retry/ACK, business state after failure, and proof of recovery. Seeing a single `ErrorMessage` log line is **not enough** to prove system safety.

## 14. Production metrics and alerts

Focus on metrics tied to operational actions:

| Metric | Why it is needed |
|---|---|
| `adapter.error.count` by endpoint, exception type | Spot failing external systems or broken converters in clusters. |
| Retry rate and max-attempt hits | Detect transient errors turning into retry storms. |
| Time from first failure to successful processing | Measure recovery latency and SLA impact. |
| DLQ/quarantine backlog and oldest message age | Track how long failed data has been waiting. |
| Consumer lag / unacked messages / offset lag | Measure broker-side bottlenecks per specific technology. |
| Error handler failures | Ensure the error-handling path itself does not fail silently. |
| Duplicate detected / idempotency hits | Measure redeliveries and effectiveness of duplicate prevention. |
| Committed business tasks | Separate "transported message" from "completed business work." |

Set alerts based on business impact: parse errors from one poison file differ from an adapter losing connectivity completely. Propagate trace IDs from external sources through channels, routers, handlers, and outbound adapters to target systems.

## 15. Common design mistakes

1. **Believing `errorChannel` automatically catches every exception.** Exceptions on `DirectChannel` can return to the caller; container failures follow their own paths.
2. **Equating receiving an ErrorMessage with rollback.** Publishing an error message and deciding transaction/ACK outcomes are two separate actions.
3. **Logging and returning.** Failed data can be silently dropped or marked complete without any recovery mechanism.
4. **Infinite or zero-backoff retries.** Creates poison-message loops and starves healthy traffic.
5. **Forgetting `failedMessage == null`.** Source errors occurring before message creation lack business message metadata.
6. **Using Spring message ID as an idempotency key.** A single business event can receive many Spring message IDs across retries and republishes.
7. **Ignoring failures inside the error handler itself.** Quarantine stores, logging sinks, and alert services can fail too.
8. **Not testing crashes after business commit and before ACK.** A classic cause of duplicates under at-least-once delivery.
9. **Confusing Kafka offsets with work-queue ACKs.** Kafka retains logs by retention policy; error handling requires consumer/container-specific rules.
10. **Failing to restrict logged details.** Exceptions and `failedMessage` may contain sensitive payloads.

## 16. Checklist for implementing adapter error channels

- [ ] Identified inbound/outbound adapters, synchronous vs. async threads, and the actual exception-catching layer.
- [ ] Configured error channels per endpoint contract, with subscribers and monitoring on the error flow itself.
- [ ] Error handler handles `Throwable`, `MessagingException`, missing `failedMessage`, and pre-message failures.
- [ ] Preserved `eventId`, `correlationId`, trace context, and source metadata as needed.
- [ ] Retry policy is bounded with backoff, classifies transient vs. permanent errors, and includes quarantine/DLQ and safe replay.
- [ ] Transactions, listener ACK/NACK, or offset commits tested against real adapters/brokers.
- [ ] Idempotency enforced for critical side effects, including crash-after-commit-before-ACK scenarios.
- [ ] Error flow handles failures when persisting errors, alerting, or publishing error messages fails.
- [ ] Metrics, structured logs, traces, and alerts cover recurring errors, backlogs, and retry storms.
- [ ] Tested restarts, source disconnects, async errors, duplicates, poison messages, and backpressure.

**Conclusion:** An adapter error channel is where **exception details are transported and processed inside a Spring Integration flow**, keeping Router, Transformer, Service Activator, and adapters observable and recoverably controlled. System-wide reliability is achieved only when the error channel works hand in hand with thread boundaries, retries, durable storage, transactions, transport ACK/offsets, and idempotency.
