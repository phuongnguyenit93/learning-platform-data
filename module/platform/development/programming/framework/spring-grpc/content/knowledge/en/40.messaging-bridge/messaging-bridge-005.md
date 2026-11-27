# Correlation Between RPCs and Messages

## 1. Why Is Correlation Needed Across a Message Flow?

In **SPRING_GRPC**, clients invoke RPCs according to a Protocol Buffers contract against a Spring service. The service may authenticate the caller, convert the request into a command, publish through a broker, and let a consumer process it at a different time or in a different process. At that point, a business operation no longer lives inside a single continuous call stack.

If you only log the gRPC method at the ingress and log the message ID at the consumer, it becomes very difficult to answer questions such as:

- Which RPC originated this message?
- Which events and commands belong to the same user operation?
- Which consumer processed a message and emitted the next message?
- Is a retry a new attempt of the same operation or a different operation?
- Why did the client receive `ACCEPTED` yet the workflow has not completed?

**Correlation** links related steps using an end-to-end identifier. It connects logs, traces, operation status, and messages without depending on steps running on the same thread, instance, or point in time.

~~~mermaid
flowchart LR
    A["gRPC request"] --> B["Ingress / use case"]
    B --> C["Command message"]
    C --> D["Broker"]
    D --> E["Consumer"]
    E --> F["Domain event"]
    F --> G["Another consumer"]
    G --> H["Next event / result"]
    A -.->|correlationId| C
    C -.->|correlationId| F
    F -.->|correlationId| H
~~~

A correlation ID does not replace a message ID, operation ID, or distributed trace ID. Each identifier answers a different question.

## 2. Distinguishing Identifier Types

A message flow should define the meaning of each identifier before implementation:

| Identifier | Scope | Used to answer |
|---|---|---|
| requestId | One request/attempt received at the ingress | Which RPC call does this log belong to? |
| correlationId | One logical interaction or workflow | Which steps belong to the same business flow? |
| operationId / commandId | One business intent stable across retries | Which operation is this create-order command? |
| messageId / eventId | One specific message | Which message is being published or redelivered? |
| causationId | Direct relationship between two messages/actions | Which message directly caused the current message? |
| traceId | One distributed trace | Which technical spans belong to the same trace? |

For example, a client sends `SubmitOrder` three times due to timeouts. Each arrival at the ingress can have a different `requestId`, but if it represents the same intent, `operationId` and the idempotency key must remain stable. The correlation ID should also stay stable if the client wants to link the entire workflow across retries.

An operation can emit multiple messages, each with its own `messageId` while sharing `operationId` and `correlationId`. A subsequent event can set `causationId` to point directly to the `messageId` that triggered it.

## 3. Correlation ID vs. Trace ID

These two identifiers often appear together, yet they should not be used interchangeably:

- **Correlation ID** is an application/business identifier defined by the system. It can be stored in operation records, the outbox, and message envelopes to look up workflows over long periods.
- **Trace ID** belongs to distributed tracing, typically managed by OpenTelemetry. It links technical spans and follows sampling, retention, exporter, and trace backend rules.

A workflow spanning minutes or days can outlive a single trace. One operation can also produce multiple traces when retries, scheduled jobs, or delayed workflow continuations occur. Therefore, store the correlation ID in business data and use the trace ID for diagnosing individual executions.

Do not craft a trace ID manually by placing it into `x-correlation-id`. Let OpenTelemetry generate and propagate `traceparent`/`tracestate` per W3C Trace Context. Correlation ID can be propagated alongside as a separate field.

## 4. Receiving Correlation ID from gRPC Metadata

A client can pass a correlation ID via metadata, such as `x-correlation-id`. gRPC metadata keys must be lowercase; ASCII values use `Metadata.ASCII_STRING_MARSHALLER`.

~~~java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Context;
import io.grpc.Contexts;

import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIdInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> HEADER =
            Metadata.Key.of(
                    "x-correlation-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Context.Key<String> CORRELATION_ID =
            Context.key("correlation-id");

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._:-]{1,128}");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String supplied = headers.get(HEADER);
        String correlationId =
                supplied != null && SAFE_ID.matcher(supplied).matches()
                        ? supplied
                        : UUID.randomUUID().toString();

        Context context = Context.current()
                .withValue(CORRELATION_ID, correlationId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

This is an example interceptor for gRPC Java. Register it in the server interceptor chain of the Spring gRPC starter you are using. If the system requires callers to supply a correlation ID, reject missing/malformed values instead of generating one; otherwise, generate a new ID at the ingress.

Restrict length and character sets to prevent log injection, oversized headers, or malformed data. A client-supplied correlation ID is untrusted input: it does not prove identity, tenant, or access permissions.

## 5. Reading the Correlation ID in the Service Adapter

Once the interceptor sets the value on `io.grpc.Context`, the service implementation can retrieve the current ID:

~~~java
@Override
public void submitOrder(
        SubmitOrderRequest request,
        StreamObserver<SubmitOrderReply> observer) {

    String correlationId =
            CorrelationIdInterceptor.CORRELATION_ID.get();

    CreateOrderCommand command = mapper.toCommand(
            request,
            callerContext.current(),
            correlationId);

    // The use case persists correlationId into operation/outbox alongside the command.
    OperationReceipt receipt = submitOrderUseCase.execute(command);

    observer.onNext(SubmitOrderReply.newBuilder()
            .setOperationId(receipt.operationId())
            .setState("ACCEPTED")
            .build());
    observer.onCompleted();
}
~~~

Do not read the correlation ID from a static mutable field or store it in a singleton service field. `io.grpc.Context` binds values to the current RPC; each call has its own context.

If execution switches to a callback or another executor, explicitly propagate the needed context. `io.grpc.Context` provides wrap/attach/detach utilities, but do not assume every thread pool or external library preserves context automatically. More importantly, when work is published to a broker, write the correlation ID into the durable message; do not rely on thread-locals once the RPC ends.

## 6. Putting Correlation into Commands and Message Envelopes

Commands and envelopes should preserve correlation independently of transport:

~~~java
public record SubmitOrderCommand(
        String operationId,
        String correlationId,
        String requestId,
        String tenantId,
        String customerId,
        java.util.List<OrderLine> lines) {}

public record MessageEnvelope<T>(
        String messageId,
        String messageType,
        int schemaVersion,
        String operationId,
        String correlationId,
        String causationId,
        java.time.Instant occurredAt,
        T payload) {}
~~~

When the ingress creates a command, `correlationId` comes from the gRPC context, `requestId` identifies the current attempt, and `operationId` is generated or looked up from the idempotency store. When the command is published, `messageId` identifies that message; `causationId` can point to the prior request/command according to system convention.

If one command produces three events, each event has its own `messageId` while sharing the same `operationId` and `correlationId`. Each event can set `causationId` to the command's message ID to express the direct causal relationship.

## 7. Propagating Correlation via Kafka Headers

Correlation ID can live in both the payload envelope and broker headers. The envelope is durable, schema-governed data used by consumers as part of the message contract. Headers are useful for middleware, tracing instrumentation, and broker tooling.

If stored in both places, derive them from the same source and verify they match. Never allow the payload to record one correlation ID while the header carries another.

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import java.nio.charset.StandardCharsets;

ProducerRecord<String, MessageEnvelope<SubmitOrderCommand>> record =
        new ProducerRecord<>(
                "orders.commands",
                command.customerId(),
                envelope);

record.headers().add(new RecordHeader(
        "x-correlation-id",
        envelope.correlationId().getBytes(StandardCharsets.UTF_8)));

record.headers().add(new RecordHeader(
        "x-operation-id",
        envelope.operationId().getBytes(StandardCharsets.UTF_8)));

kafkaTemplate.send(record);
~~~

This example uses Spring Kafka and Kafka `ProducerRecord`; configure a serializer for the envelope. If OpenTelemetry Kafka instrumentation is enabled, let the propagator/instrumentation inject W3C trace context into headers rather than crafting `traceparent` manually.

## 8. Outbox Relays Must Preserve Correlation

An outbox relay usually runs after the RPC has ended, potentially on a different thread or instance. Therefore, the correlation ID must be persisted with the outbox record or payload:

~~~text
gRPC metadata
     |
     v
Application command
     |
     v
Database transaction
  - business state
  - operation receipt
  - outbox payload + correlationId
     |
     v
Outbox relay (different process/thread)
     |
     v
Broker message headers + envelope
~~~

Do not call `Context.current()` inside the relay expecting the old RPC's context. Request context does not survive across database and process boundaries. The relay must read persisted values.

If the relay retries the same outbox record, keep `messageId`, `operationId`, and `correlationId` unchanged. Trace context headers for that publish attempt may be updated per tracing policy, but must not alter the message's business identifiers.

## 9. Consumers Restore Context and Log with Correlation

Consumers read correlation from the envelope or header using a single precedence rule. For example, using the envelope as the source of truth:

~~~java
@KafkaListener(topics = "orders.commands")
public void handle(
        ConsumerRecord<String, MessageEnvelope<SubmitOrderCommand>> record) {

    MessageEnvelope<SubmitOrderCommand> envelope = record.value();
    String correlationId = envelope.correlationId();

    MDC.put("correlationId", correlationId);
    MDC.put("operationId", envelope.operationId());
    MDC.put("messageId", envelope.messageId());
    try {
        createOrderUseCase.execute(envelope.payload());
    } finally {
        MDC.remove("correlationId");
        MDC.remove("operationId");
        MDC.remove("messageId");
    }
}
~~~

This is a skeleton; a real consumer must also handle deserialization, idempotency, transactions, acknowledgements, retries, and dead-lettering. Clearing MDC in `finally` is mandatory because consumer threads are typically reused for subsequent messages. Otherwise, logs for the next message could carry the wrong correlation ID.

When a consumer emits a new event, copy `correlationId` and `operationId` from the handled message; set `causationId` to the message ID that triggered the new event. Do not generate a new correlation ID at each step in the same workflow if the goal is to trace the entire workflow.

## 10. Distributed Tracing Across Asynchronous Boundaries

Correlation IDs help search logs and operations; distributed tracing provides span relationships and timing across components. With OpenTelemetry:

- gRPC server instrumentation creates a server span for the RPC.
- Producer instrumentation injects trace context into message headers.
- Consumer instrumentation extracts context and creates a consumer span.
- Spans can continue a trace or use span links when fan-out, batching, or asynchronous processing makes a simple parent-child relationship unsuitable.

W3C Trace Context commonly uses `traceparent` and `tracestate`. Baggage can carry small extra context, but it must be allowlisted, size-bounded, and free of sensitive data. Do not place access tokens, emails, phone numbers, or customer data into baggage.

Not every message in a long-lived workflow needs to belong to the same trace. Retries or scheduled continuations may start a new trace while keeping the correlation ID and operation ID. Span links can connect the new trace to the context that triggered the work.

## 11. Request/Reply Needs an ID per Pending Call

In request/reply over a broker, a correlation ID matches replies to waiting requests. However, one workflow may emit multiple concurrent requests sharing the same correlation ID. In that case, keying a pending map solely by `correlationId` will mismatch responses.

Distinguish:

- `correlationId`: links the entire workflow.
- `replyCorrelationId` or `requestId`: uniquely identifies one request/reply pair.
- `operationId`: stable business identifier.

Example:

~~~text
Workflow correlationId = wf-100
  Request A requestId = req-A -> Reply A correlation = req-A
  Request B requestId = req-B -> Reply B correlation = req-B
  Request C requestId = req-C -> Reply C correlation = req-C
~~~

The pending request registry should have timeouts, cancellation cleanup, entry limits, and late-reply handling. If the ingress restarts, decide whether pending requests must be persisted durably or moved to an operation status API. Do not retain entries indefinitely after the client deadline has expired.

## 12. Retries, Redelivery, and Fan-Out

Correlation IDs should remain stable across retries of the same workflow:

- Client retries the same operation: keep `operationId`, idempotency key, and correlation ID; `requestId` can be fresh per attempt.
- Broker redelivers the same message: keep `messageId` and correlation ID; increment delivery attempt in separate metadata.
- Consumer emits a new event: generate a new `messageId`, keep correlation ID/operation ID, and set `causationId` to the source message.
- Fan-out to multiple consumers: branches share the common correlation ID; each message/event gets its own ID.
- Starting a new independent workflow: create a new correlation ID and optionally store a parent operation/trace link to connect them.

Do not use correlation ID as a deduplication key. Many valid messages within the same workflow will share a correlation ID. Deduplication must use `messageId`, `eventId`, `commandId`, or an appropriate business key.

## 13. Security and Correlation Data Quality

Correlation IDs frequently enter logs, traces, message headers, and operational tools, so enforce controls:

- Accept only an allowlisted character set and bounded length.
- Never use correlation ID for authentication, authorization, or tenant selection.
- Never embed PII, credentials, or secrets into the ID.
- Never log arbitrary caller metadata verbatim.
- Bound header/baggage sizes to avoid bloated requests/messages.
- Keep correlation IDs scoped to tenants and apply appropriate log/trace access controls.
- Prevent callers from intentionally choosing colliding IDs to confuse investigations; namespace or replace invalid IDs at the ingress.

Tenant ID must come from the authenticated principal. If tenant filtering is needed, set the tenant log field from the security context and apply dedicated data protection policies; a correlation ID does not replace tenant identity.

## 14. Do Not Use High-Cardinality IDs as Metric Labels

Correlation IDs, operation IDs, request IDs, and message IDs can have millions of distinct values. Putting them into metric labels creates high cardinality, inflating memory usage and cost in metrics backends.

Recommended separation:

- **Logs:** correlation ID, operation ID, request ID, message ID, and causation ID.
- **Traces:** trace ID/span ID and controlled span attributes.
- **Metrics:** bounded-cardinality dimensions such as service, RPC method, message type, consumer group, status, and outcome.

Example suitable metric: `message_publish_total` with `topic=orders.commands` and `outcome=success`. Specific correlation IDs belong in logs/traces for looking up an individual workflow, not in metric labels.

## 15. Testing End-to-End Correlation

Tests should verify that IDs are preserved accurately across boundaries:

| Scenario | What to verify |
|---|---|
| Client sends valid correlation ID | Ingress preserves that ID per policy |
| Missing or malformed header | Ingress generates a new ID or returns error per contract |
| RPC invokes use case | Command receives exact correlation ID and operation ID |
| Outbox commit | Correlation ID is persisted with the record |
| Relay publish | Envelope and broker headers are consistent |
| Relay retry | Message retains message ID and correlation ID |
| Consumer receives message | Logs contain exact correlation/operation/message IDs |
| Consumer emits event | Event retains correlation ID, gets new message ID and correct causation ID |
| Two concurrent request/replies | Replies match by request-specific ID, not only workflow correlation |
| Client retry | Same operation creates no duplicate workflow/side effects |
| Consumer thread reuse | MDC from previous message does not leak into next message |
| OpenTelemetry sampling | Correlation ID still finds the operation even if trace is not sampled |

Unit tests for interceptors and mappers verify ID extraction and propagation. Integration tests with a gRPC server, database/outbox, and broker verify context is not lost across async boundaries. You can inspect captured logs or a tracing exporter in tests to verify attributes are attached properly.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using trace ID as operation ID | Retries or continuations create unstable technical IDs | Separate trace, correlation, and operation IDs |
| Generating a new correlation ID in each consumer | Cannot locate the full workflow | Preserve correlation ID across related messages |
| Using correlation ID as deduplication key | Drops distinct messages in the same workflow | Deduplicate by message/event/command ID |
| Keeping ID only in ThreadLocal | Context lost across executors or process boundaries | Persist into outbox/envelope and broker headers |
| Relay reads old RPC context | Correlation is wrong or empty | Read IDs from outbox record |
| Using only correlation ID for concurrent request/reply | Mismatched replies | Use request-specific reply correlation ID |
| Not clearing MDC | Subsequent message logs carry previous message IDs | Clear MDC in `finally` |
| Putting correlation ID in metric labels | Exploding cardinality and metric cost | Put IDs in logs/traces |
| Trusting correlation ID as identity | Authorization or tenant isolation vulnerability | Use authenticated principal for identity |

**Key takeaway:** Correlation ID connects steps of the same workflow from gRPC metadata through commands, outbox, broker, and consumers. Distinguish it from request ID, operation ID, message ID, causation ID, and trace ID. Put correlation into commands/envelopes and persist it with the outbox; propagate trace context via OpenTelemetry/W3C; restore log context in consumers and clean up MDC afterward. Keep IDs stable across retries, use request-specific IDs for concurrent request/reply, and never use correlation ID as a deduplication key, identity, or metric label.
