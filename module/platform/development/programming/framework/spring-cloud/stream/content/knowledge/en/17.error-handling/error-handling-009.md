# Preserving Payload and Metadata for Investigation

When a message fails to process, operations teams need to know exactly which data caused the error, which binding the message arrived on, what metadata accompanied it, and which attempt failed. Simply logging the exception and discarding the message makes incident reproduction or data replay very difficult. Modifying the payload to embed error information alters the original data and compromises its reliability for investigation.

In Spring Cloud Stream, a message consists of a payload and headers. When processing fails, the framework can emit an `ErrorMessage` containing the exception and the original message; a `MessagingException` can also hold `failedMessage`. Binders also provide their own mechanisms to route failing messages to a dead-letter destination (DLQ). Good design preserves the original payload and key business metadata, attaches separate diagnostic details, and avoids copying credentials or expired transport headers.

## 1. Distinguishing the Original Message from the Error Message

A regular message has two parts:

- Payload: business data or raw bytes received from the broker.
- Headers: metadata such as `eventId`, `correlationId`, schema version, content type, timestamp, and transport headers added by the binder.

When a handler throws an exception, Spring Messaging can represent the failure with an `ErrorMessage`. The payload of `ErrorMessage` is a `Throwable`; the original message is held separately in `originalMessage` if available to the error handler. If the exception is a `MessagingException`, it may also provide `failedMessage`.

Example:

~~~java
@Bean
Consumer<OrderCreated> processOrder() {
    return event -> {
        orderService.process(event);
    };
}
~~~

If `orderService.process` throws an exception, the framework passes the failure through the binding's error-handling mechanism. `ErrorMessage` describes the failure; it does not mean the original payload was overwritten with an error object. Retrieve the actual original message from `ErrorMessage` or the exception for investigation.

## 2. Retrieving `originalMessage` and `failedMessage`

Given an `ErrorMessage`, you can extract the exception and original message as follows:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

public Message<?> findOriginalMessage(ErrorMessage errorMessage) {
    Throwable failure = errorMessage.getPayload();

    Message<?> original = errorMessage.getOriginalMessage();
    if (original == null && failure instanceof MessagingException messagingException) {
        original = messagingException.getFailedMessage();
    }
    return original;
}
~~~

These two locations are the first places to check. Not every failure has an `originalMessage` or `failedMessage`. Failures can arise before the framework constructs a converted `Message`, such as deserialization errors or broker connection failures. In those cases, the binder may supply raw data and transport metadata through its own extensions. Inspect the exception chain, headers, and binder documentation for your deployed version; do not assume every error has the same structure.

When no original message is found, the error handler should explicitly record that the original data is unavailable in `ErrorMessage` and fall back to binder-supported retention mechanisms. Never fabricate a dummy payload or overwrite error content to make it look as though the message was preserved.

## 3. Keep the Payload Intact; Do Not Embed Error Info into Business Data

The original payload is evidence of what the producer sent. Never mutate the payload directly to append a stack trace, exception name, or failure timestamp. Instead, store investigative details in separate metadata or a distinct error envelope.

Example original message:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "total": 250000
}
~~~

Investigative details should be stored in a separate field:

~~~json
{
  "failure": {
    "exceptionType": "com.example.InventoryUnavailableException",
    "message": "Inventory service timed out",
    "failedAt": "2026-11-24T06:30:00Z",
    "attempt": 3,
    "sourceBinding": "processOrder-in-0"
  },
  "original": {
    "eventId": "evt-1001",
    "orderId": "ORD-1001",
    "total": 250000
  }
}
~~~

This envelope is only an error storage/forwarding format. If a replay consumer needs to read the exact original payload, it must understand the envelope and extract the `original` field. If preserving exact wire bytes is required, do not deserialize and re-serialize the payload; use the binder's native DLQ or store the raw bytes alongside content type and necessary metadata.

## 4. Which Metadata Should Be Preserved?

Not every header is valuable during investigation. Define an allowlist of application metadata to preserve:

| Metadata | Purpose |
|---|---|
| `eventId` | Original event identifier, supporting deduplication and lookup |
| `correlationId` | Links steps within the same request or workflow |
| `causationId` | Traces the event/request that caused the current event |
| `eventType` | Identifies the event type and expected handler |
| `schemaVersion` | Selects the right schema or converter during investigation/replay |
| `contentType` | Indicates the original payload format |
| `aggregateId` | Identifies the related business entity |
| `traceparent` or `traceId` | Correlates logs, traces, and distributed spans |
| `tenantRef` | Identifies tenant scope if permitted by policy |
| `sourceBinding`/`destination`/`group` | Identifies message ingestion source and consumer group |

Transport metadata such as delivery tags, consumer tags, offsets, partition assignments, or acknowledgment handles may only be valid during the initial delivery. Do not blindly copy them onto replayed messages. Store them in investigative records if needed, but keep them distinct from reusable business metadata.

## 5. Copy Only Allowlisted Headers

The following example illustrates building an investigative message from the original payload, copying only selected business headers and adding error metadata:

~~~java
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

public Message<?> toDiagnosticMessage(ErrorMessage errorMessage) {
    Throwable failure = errorMessage.getPayload();
    Message<?> original = errorMessage.getOriginalMessage();

    if (original == null && failure instanceof MessagingException messagingException) {
        original = messagingException.getFailedMessage();
    }
    if (original == null) {
        throw new IllegalStateException("Original message is unavailable", failure);
    }

    List<String> allowedHeaders = List.of(
        "eventId",
        "correlationId",
        "causationId",
        "eventType",
        "schemaVersion",
        "aggregateId",
        "traceparent",
        MessageHeaders.CONTENT_TYPE
    );

    Map<String, Object> retainedHeaders = new HashMap<>();
    for (String name : allowedHeaders) {
        Object value = original.getHeaders().get(name);
        if (value != null) {
            retainedHeaders.put(name, value);
        }
    }

    return MessageBuilder.withPayload(original.getPayload())
        .copyHeaders(retainedHeaders)
        .setHeader("failureType", failure.getClass().getName())
        .setHeader("failureMessage", truncate(failure.getMessage()))
        .setHeader("failedAt", Instant.now().toString())
        .build();
}

private String truncate(String message) {
    if (message == null) {
        return "No exception message";
    }
    return message.length() > 500 ? message.substring(0, 500) : message;
}
~~~

This code is a template for applications with custom headers such as `eventId` and `correlationId`; adjust the allowlist to your actual contract. `MessageHeaders.CONTENT_TYPE` retrieves the standard Spring Messaging content-type header name. The `truncate` helper in this example only limits length; real implementations should also redact tokens, personal data, and sensitive information that might appear in exception messages.

Do not use `copyHeaders(original.getHeaders())` when messages may contain arbitrary headers. Copying everything can leak delivery tags, offsets, internal info, tokens, or sensitive data to another destination. Retain only metadata actually required by investigation or replay systems.

## 6. Routing Failed Messages to an Investigation Destination

If the application opts to manage the error flow itself, it can use a `Consumer<ErrorMessage>` as a custom error handler and send the payload-preserved message through a dedicated output binding:

~~~java
@Bean
Consumer<ErrorMessage> preserveOrderFailure(StreamBridge streamBridge) {
    return errorMessage -> {
        Message<?> diagnostic = toDiagnosticMessage(errorMessage);
        boolean sent = streamBridge.send("orders-failed-out-0", diagnostic);
        if (!sent) {
            throw new IllegalStateException("Failed to publish diagnostic message");
        }
    };
}
~~~

Declaring the error handler for the input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          error-handler-definition: preserveOrderFailure
        orders-failed-out-0:
          destination: orders.failed
          content-type: application/json
~~~

A custom handler can persist messages and error details in the application's chosen format. However, a custom error handler replaces the error handlers provided by the framework/binder; once a custom handler is declared, you cannot assume the binder DLQ will still run automatically even if configured. If you want to use the native DLQ, let the binder handle errors and configure the proper DLQ properties instead of expecting both the custom handler and binder handler to process the same failure.

The boolean return value from `StreamBridge` indicates that the message was accepted along the application's send path; it is not independent proof that the broker stored it durably. Handle asynchronous publish errors and consider an outbox if saving investigative records must stay consistent with database changes.

## 7. Using a Binder-Managed DLQ to Retain the Original Message

A Dead Letter Queue is the right choice when you want the broker/binder to hold failing messages for investigation, reconciliation, or replay. Destination names, extra metadata, and republishing capabilities vary by binder.

Rabbit binder example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
~~~

`auto-bind-dlq` tells the Rabbit binder to create and configure a DLQ for the binding. `republish-to-dlq` instructs the binder to republish the failed message with additional diagnostic metadata, such as the exception message or stack trace, depending on version and configuration. The original payload is preserved for subsequent investigation steps. Check the documentation of your Rabbit binder version to confirm queue naming, routing, and header size limits.

The Kafka binder has its own DLQ settings, such as `enable-dlq` and DLT-related properties. Check the Kafka binder docs for your version, including how record keys, headers, offsets, partitions, and exception metadata are preserved. The Pulsar binder has its own dead-letter policy and subscription mechanisms; do not copy Rabbit or Kafka properties to Pulsar.

When using a native DLQ, inspect actual messages inside the error destination: verify the payload is intact, which application headers survived, which headers the binder added, and whether origin/exception details are sufficient for investigation. Never treat the DLQ name as a guarantee that every transport header survives intact across all brokers.

## 8. Distinguishing Retry, Requeue, and DLQ

These three mechanisms serve different purposes:

| Mechanism | Meaning | Where Is Data Kept? |
|---|---|---|
| In-application retry | Re-invokes the handler after a failure, typically with backoff and attempt limits | Message stays within the current processing flow per framework/binder mechanics |
| Requeue/redelivery | Asks the broker to deliver the message again | Broker holds the message per queue, offset, or subscription semantics |
| DLQ | Moves the failing message to a dedicated destination | Payload and metadata are stored according to the binder's implementation |

Retry does not always create a new copy of a message. Requeue is not equivalent to re-recording the payload. A DLQ does not fix the message or resolve the failure cause on its own. Choose policies based on error type and recoverability.

Transient failures such as downstream service timeouts can be retried with backoff. Permanent data errors such as invalid schemas should usually go to a DLQ after bounded attempts. Infinitely requeuing a poison message can create a loop and block other messages in the queue or partition.

## 9. Preserving Raw Data When Errors Occur Before Calling the Function

Some errors happen before the function receives a DTO, such as unparseable JSON, incompatible schemas, or native deserializer failures. At that point, the payload visible to consumer code may not exist as a POJO yet. The original message may contain `byte[]` or raw data placed in error metadata by the binder.

In this situation:

- Prefer a binder DLQ or error path capable of retaining the original record/body.
- Retain content type, schema ID/version, key, and relevant headers.
- If storing manually, save raw bytes alongside encoding, checksum, and source information.
- Do not deserialize using a similar type and re-serialize to approximate the original.
- Save the exception chain and serializer/deserializer version so the failure can be reproduced.

If the original payload is `byte[]`, you can compute a SHA-256 hash to verify that investigative copies remain unaltered. A checksum does not replace digital signatures or provenance proof, but it is helpful for integrity checks during storage and file transfers.

## 10. Storing Stack Traces and Error Details Safely

Stack traces and exception messages can contain SQL, internal URLs, hostnames, file paths, request data, or sensitive values. Do not stuff entire stack traces into broker headers because headers have size limits and may be read by multiple consumers.

A diagnostic record should contain:

- `eventId` and `correlationId` to look up the business flow.
- Binding, destination, consumer group, and binder.
- Exception type and sanitized error message.
- Failure timestamp, plus attempt/delivery count if available.
- Schema version and content type.
- `traceId`/`spanId` if tracing is enabled.
- A reference to logs/traces or object storage holding larger details.

If full stack traces must be stored, store them in a logging system or investigative store with proper access control, retention, and auditing; put a reference ID in the failure record's metadata. Avoid writing tokens, passwords, cookies, personal data, or sensitive payloads into logs and DLQ headers. TLS protects data in transit, not access control on brokers, DLQs, and log stores.

## 11. Replaying Without Corrupting Metadata

Replay means re-emitting a failed message after fixing the root cause. Before replaying, separate business metadata from transport metadata:

- Keep the original `eventId` for tracing and deduplication.
- Keep `correlationId`, `causationId`, `aggregateId`, and `schemaVersion` if they remain meaningful.
- Add `replayId`, `replayedAt`, and `replayAttempt` to track the replay run.
- Do not reuse delivery tags, consumer tags, offsets, or acknowledgment handles from the old delivery.
- Validate the target destination and schema before re-emitting.
- Use idempotent consumers because replays can produce duplicate processing.

Do not automatically replay every message in the DLQ as soon as error rates drop. Classify by cause, check payload/schema, rate-limit, and ensure replay can be halted. For messages with permanent business errors, repair data or decide manually before replaying.

## 12. Testing Payload and Metadata Preservation

Tests should verify both content and provenance:

- Send a valid message and intentionally make the handler fail; confirm the payload in `ErrorMessage`/DLQ matches the original message.
- Compare `eventId`, `correlationId`, `eventType`, `schemaVersion`, and content type before and after routing to the error destination.
- Send a `byte[]` payload or malformed JSON to test the conversion error path before the function is invoked.
- Confirm raw bytes or checksum remain unchanged when byte preservation is required.
- Confirm exception type, sanitized message, and failure timestamp are recorded.
- Verify sensitive headers are stripped or masked before logging/sending to DLQ.
- Verify retry count, redelivery metadata, and DLQ routing per binder.
- Replay a stored message and verify the original `eventId` is preserved, a new `replayId` is added, and the consumer handles it idempotently.
- Test the case where the error handler cannot publish to the error destination and verify the failure is observed/recovered.

The Test Binder can test `ErrorMessage` and handler logic within application scope. It does not replace integration tests with Kafka, RabbitMQ, or Pulsar when verifying original byte payloads, keys, headers, DLQs, offsets, ack/requeue, and broker-added metadata.

## 13. Failed Message Investigation Checklist

- [ ] Retrieved `originalMessage` or `MessagingException.failedMessage` if available.
- [ ] Identified whether the payload is a POJO, `String`, or raw `byte[]`.
- [ ] Preserved the original payload intact; error details are stored in separate metadata or an envelope.
- [ ] Preserved the allowlist of business headers and required content type/schema version.
- [ ] Separated business headers from transient transport metadata such as delivery tags and offsets.
- [ ] Recorded `eventId`, `correlationId`, source binding, exception type, timestamp, and attempt.
- [ ] Sanitized stack traces, exception messages, and sensitive data before saving.
- [ ] Selected either a custom error handler or binder DLQ properly without assuming both run automatically in parallel.
- [ ] Verified exact behavior against the deployed binder and broker.
- [ ] Established a rate-limited replay workflow with idempotency guarantees.

Preserving payloads intact alongside selectively retained metadata lets development teams reproduce failures, identify message origins, and replay data without breaking business contracts. In Spring Cloud Stream, leverage `originalMessage`/`failedMessage` when present, use native DLQs when broker-level retention is needed, and build custom `ErrorMessage` handlers only with a clear understanding of which default error-handling mechanisms they replace. Original payloads, business metadata, and diagnostics should be stored separately, access-controlled, and verifiable.

## References

- [Spring Cloud Stream 5.1 — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/5.1/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
