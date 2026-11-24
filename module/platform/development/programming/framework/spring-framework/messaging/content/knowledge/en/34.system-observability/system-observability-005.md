# Correlating Logs Using Message IDs and Correlation IDs in Spring Messaging

## Objectives

In a messaging system, a single business operation can generate multiple messages, travel across multiple queues or channels, be processed asynchronously, and invoke several downstream services. When an error occurs, a single isolated log line is usually not enough to tell where the message came from, which workflow it belongs to, which step processed it, or whether it was a redelivery.

The solution is to record consistent identifiers in message headers and structured logs. However, message ID, correlation ID, causation ID, and trace ID serve different purposes. Using a single UUID for everything may make logs appear linked while losing meaning during retries, fan-out, request/reply, or when generating new messages.

This lesson explains how to design those IDs, how to use them with Spring JMS and Spring Integration, how to include them in logs, and how to link them with distributed tracing.

## 1. Distinguishing the ID Types

| Identifier | Question answered | Scope and lifecycle |
| --- | --- | --- |
| Message ID | Which specific message is this? | A single message or a single publish at the transport layer |
| Event ID | Which business event is this? | A single logical event; should remain stable when retrying or republishing the same event |
| Correlation ID | Which conversation or workflow does this message belong to? | Multiple related messages can share one ID |
| Causation ID | Which message directly produced this message? | Points to the immediate parent message/event |
| Trace ID | Which trace do these distributed operations belong to? | One distributed trace can contain multiple spans and multiple messages |
| Span ID | Which specific operation within the trace is running? | A single unit of work; each service or operation has its own span |
| Delivery attempt | Which delivery attempt is the broker making? | One delivery/receipt; increments when the broker redelivers according to policy |

Example of an order-creation workflow:

- Client sends a command with correlation ID `workflow-7f2a`.
- Orders service receives the command with message ID `ID:orders-104`.
- Orders service emits an `OrderCreated` event with event ID `evt-9001` and causation ID pointing to command `ID:orders-104`.
- The event is delivered to two subscribers. Both still use correlation ID `workflow-7f2a`, though each publish/delivery may have its own message ID.
- Billing service emits an `InvoiceIssued` event with a new event ID and causation ID `evt-9001`.
- Trace ID links the spans throughout processing, provided tracing context is propagated across messaging boundaries.

The IDs answer different questions. Message ID locates a specific message; correlation ID groups a workflow; causation ID shows parent-child relationships; trace ID connects spans; event ID identifies a durable business event.

## 2. Why Not Use One ID for Everything?

A message can be reprocessed or spawn another message:

- **Redelivery:** the broker delivers the same message again after the consumer fails to acknowledge it. It is still the same transport message, but the delivery attempt changes.
- **Republish:** the application creates and sends a new message again. The broker usually assigns a new message ID, while event ID and correlation ID can stay the same.
- **Fan-out:** one message produces multiple child messages. Child messages have distinct message IDs but share the same correlation ID; their causation IDs point to the source message.
- **Request/reply:** the reply must be matched to the right request, even when many requests run concurrently.
- **Splitter/aggregator:** one message is split into parts and later reassembled. Correlation ID groups the parts; sequence number and sequence size indicate position and item count.

If you use message ID as correlation ID, child messages lose their link to one another whenever the broker assigns each message its own ID. If you use trace ID as event ID, a trace containing multiple events causes distinct events to be mistaken for the same event. If you use correlation ID as an idempotency key, different messages in the same workflow may be erroneously deduplicated.

A practical rule of thumb:

- Message ID identifies a message.
- Event ID identifies a business event.
- Correlation ID identifies a workflow or conversation.
- Causation ID points to the message/event that produced the current message.
- Trace ID and span ID serve distributed tracing.
- Idempotency key protects an operation from duplicate side effects; it may equal event ID in some designs, but must be defined by business semantics.

## 3. IDs in Spring Messaging

Spring has a common abstraction: `org.springframework.messaging.Message<T>`. Payload holds the data; headers hold metadata for routing, correlation, and processing.

### MessageHeaders.ID

`MessageHeaders.ID` is a UUID identifying a Spring Message instance. It is not a business ID and is not necessarily the broker-assigned message ID. In Spring Integration, when a message is transformed into a new message instance, the new message's ID and timestamp also change.

Therefore, use this ID to diagnose a message within Spring's internal flow. If you need to track the same event across multiple transformations or across systems, retain a separate event ID or correlation ID.

### Spring Integration correlation headers

Spring Integration declares dedicated headers in `IntegrationMessageHeaderAccessor`:

- `CORRELATION_ID`: groups two or more related messages.
- `SEQUENCE_NUMBER`: position of a message within a group.
- `SEQUENCE_SIZE`: total number of messages in the group when known.
- `SEQUENCE_DETAILS`: stack of correlation info used in nested flows such as a splitter followed by an aggregator.

You can read these headers using the accessor:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

public void inspect(Message<?> message) {
    var accessor = new IntegrationMessageHeaderAccessor(message);

    var messageId = message.getHeaders().getId();
    Object correlationId = accessor.getCorrelationId();
    Integer sequenceNumber = accessor.getSequenceNumber();
    Integer sequenceSize = accessor.getSequenceSize();

    log.info(
            "integration_message messageId={} correlationId={} sequence={}/{}",
            messageId,
            correlationId,
            sequenceNumber,
            sequenceSize);
}
~~~

The headers above belong to Spring Integration. Applications using plain Spring Messaging should not assume every message carries `IntegrationMessageHeaderAccessor.CORRELATION_ID`; define application headers or add Spring Integration when those patterns are needed.

## 4. JMS Message ID and JMS Correlation ID

JMS defines standard headers:

- `JMSMessageID`: message identifier generated by the provider on send. Spring maps it to `JmsHeaders.MESSAGE_ID`.
- `JMSCorrelationID`: identifier used to link a message to another message, commonly request and reply. Spring maps it to `JmsHeaders.CORRELATION_ID`.
- `JMSReplyTo`: destination for receiving replies.
- `JMSRedelivered`: indicates whether the message has been redelivered.
- `JMSDestination` and `JMSTimestamp`: destination and send timestamp.

These standard headers are read-only for the sending application. The provider manages message IDs, timestamps, and broker-generated values. A producer may configure the provider to disable message ID generation for performance optimization; if enabled, do not assume every message has a JMSMessageID.

### Request/reply with JMSCorrelationID

A common pattern is:

1. Requester sends the request.
2. Broker assigns `JMSMessageID` to the request.
3. Responder receives the request and sends the reply.
4. Responder sets the reply's `JMSCorrelationID` to the request's `JMSMessageID`.
5. Requester uses a selector or equivalent logic to match the reply to the right request.

Example listener receiving a request and sending a reply:

~~~java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class RequestResponder {

    private final JmsTemplate jmsTemplate;

    public RequestResponder(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "orders.request")
    public void handle(Message request) throws JMSException {
        String requestMessageId = request.getJMSMessageID();
        Destination replyTo = request.getJMSReplyTo();

        if (requestMessageId == null || replyTo == null) {
            throw new JMSException(
                    "Request requires a JMSMessageID and JMSReplyTo");
        }

        jmsTemplate.send(replyTo, session -> {
            TextMessage reply =
                    session.createTextMessage("accepted");
            reply.setJMSCorrelationID(requestMessageId);
            return reply;
        });
    }
}
~~~

This snippet illustrates retrieving the request's message ID and attaching it to the reply. In a real application, handle missing reply destinations according to the application's request/reply contract. Using the `Destination` object directly also avoids depending on provider-specific string representations.

Another variation is for the requester to generate its own correlation ID before sending and the responder to copy that value onto the reply. Both sides must agree on one pattern; do not mix both approaches within the same request/reply flow.

## 5. Correlation ID for Non-Request/Reply Workflows

A workflow can emit multiple events without a single reply. In that case, use a stable application correlation ID, such as `appCorrelationId`, and propagate it across child messages.

With JMS, custom properties only support primitive/simple data types as specified by JMS. One way to send messages using `JmsTemplate`:

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(
            String payload,
            String correlationId,
            String causationId) {

        jmsTemplate.convertAndSend(
                "orders.events",
                payload,
                message -> {
                    message.setStringProperty(
                            "appCorrelationId", correlationId);

                    if (causationId != null) {
                        message.setStringProperty(
                                "causationId", causationId);
                    }
                    return message;
                });
    }
}
~~~

Here:

- The broker generates `JMSMessageID` for the sent message.
- `appCorrelationId` is managed by the application and preserved across the workflow.
- `causationId` points to the event or command that directly produced the new event.
- `JMSCorrelationID` is reserved for request/reply or a separately agreed protocol.

If you want to use `JMSCorrelationID` for workflow correlation, document that convention explicitly and ensure it does not conflict with request/reply. Spring Integration distinguishes the generic `correlationId` header from the JMS header `jms_correlationId`: the generic header usually groups messages for aggregators/resequencers, whereas JMSCorrelationID is typically used to pair request/reply.

## 6. Reading IDs in @JmsListener

A listener can accept a Spring `Message<T>` to read the payload along with JMS headers mapped by Spring:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.jms.support.JmsHeaders;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(destination = "orders.events")
    public void receive(
            Message<String> message,
            @Header(JmsHeaders.MESSAGE_ID) String messageId,
            @Header(JmsHeaders.CORRELATION_ID) String jmsCorrelationId) {

        String payload = message.getPayload();

        log.info(
                "order_message_received messageId={} jmsCorrelationId={} payloadType={}",
                messageId,
                jmsCorrelationId,
                payload.getClass().getSimpleName());

        process(payload);
    }
}
~~~

If you need to read a custom JMS property or other transport attribute, the listener can accept raw `jakarta.jms.Message` and call `getStringProperty("appCorrelationId")`, `getJMSRedelivered()`, or `getJMSMessageID()`. This approach depends on the JMS API; accepting Spring `Message<T>` is appropriate when you want to use Spring's header abstraction.

Do not log raw payloads just to make messages easier to find. Log payload type, safe business identifiers, and standardized IDs.

## 7. Linking Message ID, Correlation ID, and Causation ID in Logs

A log event should have a stable event name and separate ID fields:

~~~json
{
  "event": "jms_message_processed",
  "destination": "orders.events",
  "messageId": "ID:orders-104",
  "eventId": "evt-9001",
  "correlationId": "workflow-7f2a",
  "causationId": "ID:orders-103",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "deliveryAttempt": 1,
  "outcome": "SUCCESS",
  "durationMs": 18
}
~~~

Field names may vary across logging systems, but their meanings must stay consistent. Use the same name for the same concept across producers, broker bridges, consumers, and downstream services. If one system calls workflow correlation `requestId` while another calls it `correlationId`, establish an explicit mapping.

When an error occurs, a log record should allow searching by one or more keys:

- Search `messageId` to inspect a specific transport message.
- Search `eventId` to inspect a business event across publishes or retries.
- Search `correlationId` to view the entire workflow.
- Search `causationId` to trace parent-child message chains.
- Search `traceId` to open the distributed trace and inspect per-span durations.

Record these IDs in both publish logs and process logs. If you only log them on the consumer, it is hard to see where a message originated; if you only log them on the producer, it is hard to tell whether the message was processed or redelivered.

## 8. Safely Attaching IDs to MDC on Listener Threads

MDC lets the logging framework automatically add fields such as `correlationId` to every log line within a processing scope. However, listener containers typically use a thread pool. Threads are reused for subsequent messages; if you do not clear or restore MDC, logs for the next message may carry the previous message's IDs.

Example with SLF4J MDC:

~~~java
import org.slf4j.MDC;

public void processWithCorrelation(
        String correlationId,
        String messageId,
        String payload) {

    String previousCorrelationId = MDC.get("correlationId");
    String previousMessageId = MDC.get("messageId");

    try {
        if (correlationId != null) {
            MDC.put("correlationId", correlationId);
        }
        if (messageId != null) {
            MDC.put("messageId", messageId);
        }

        log.info("processing_order_message");
        process(payload);
        log.info("order_message_processed");
    }
    finally {
        restoreMdc("correlationId", previousCorrelationId);
        restoreMdc("messageId", previousMessageId);
    }
}

private static void restoreMdc(String key, String previousValue) {
    if (previousValue == null) {
        MDC.remove(key);
    }
    else {
        MDC.put(key, previousValue);
    }
}
~~~

This example covers synchronous scope inside a listener method. If processing continues on another executor, callback, or reactive pipeline, MDC does not automatically follow across threads. In those cases, use an appropriate context propagation mechanism or pass the correlation ID explicitly in the message/context.

Do not leave MDC populated after the listener finishes, and do not overwrite existing context without restoring it. This is especially critical when a thread pool reuses worker threads.

## 9. Trace ID and Span ID: Linking Across Services

Distributed tracing adds another observability layer for workflows. Trace ID identifies the trace; each service call or operation creates its own span ID. When a message crosses a broker, the producer must inject trace context into headers and the consumer must extract it to create the next span.

W3C Trace Context commonly uses:

- `traceparent`: trace ID, parent span ID, and trace flags.
- `tracestate`: vendor-specific extension data.
- Baggage: additional properties propagated across boundaries if configured.

Do not simply copy the trace ID into a custom string and assume propagation is complete. Inject/extract must preserve parent-child relationships, sampling flags, and context properties managed by the tracing implementation.

With Micrometer Tracing, use a compatible tracing bridge/exporter and instrumentation. If propagating context manually, use the Propagator API to inject/extract with a carrier instead of parsing or building `traceparent` by hand.

### JMS instrumentation in Spring Framework 7

Spring Framework 7 can use Micrometer's Jakarta JMS instrumentation when the `io.micrometer:micrometer-jakarta9` dependency is on the classpath. The instrumentation creates observations for:

- `jms.message.publish`: time to send a message, typically via `JmsTemplate`, while propagating tracing information through outgoing JMS headers.
- `jms.message.process`: time for the application to process a message, typically via `MessageListener` or `@JmsListener`, while extracting tracing context from incoming headers.

To activate observations, configure `ObservationRegistry` on the `JmsTemplate` and `JmsListenerContainerFactory` in use. For listeners with a custom factory, the registry must be configured on the exact factory referenced by the endpoint. Merely adding the dependency without attaching the registry to these components may not suffice to produce observations.

Default observations include high-cardinality keys for message conversation ID, destination name, and message ID. These fields belong in traces/logs to look up a specific message; do not use these continuously changing values as metric labels.

Spring Framework and Micrometer versions determine which instrumentation is available. With Spring Framework 6.x or Spring Boot 3.x, verify the documentation for your exact versions and dependency management before applying Spring 7 configurations.

## 10. Spring Integration: Correlation, Splitter, and Aggregator

Spring Integration provides built-in correlation headers to group messages in a flow:

- Splitter produces multiple child messages and attaches correlation ID, sequence number, and sequence size.
- Aggregator uses these values to determine which messages belong to the same group and when a group is ready to complete.
- Resequencer uses sequence number to reorder messages within a group.

Do not replace these headers with a custom header without updating aggregator/resequencer logic. If generating a correlation ID from business data, use that same ID as the correlation key according to your designed flow.

### Message history

When you need to know which Spring Integration components a message passed through, you can enable message history:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory
public class IntegrationObservabilityConfiguration {
}
~~~

Spring Integration writes the history header and appends tracked component info as the message moves through the flow. You can restrict which components are tracked to reduce overhead and avoid inflating headers. Message history is useful for investigating internal application routing; it does not replace message IDs, correlation IDs, or distributed traces.

## 11. Choosing Where to Record IDs: Logs, Traces, or Metrics?

| Storage | Should record | Should not record |
| --- | --- | --- |
| Structured log | messageId, eventId, correlationId, causationId, traceId, destination, outcome, deliveryAttempt | Raw payload, tokens, unnecessary personal data |
| Distributed trace | traceId/spanId, messaging operation, destination, message ID/correlation ID per instrumentation | Putting secrets or sensitive payloads in span attributes |
| Metrics | destination type, operation, outcome, low-cardinality consumer group or route | messageId, eventId, correlationId, or user ID as labels |
| Audit record | Business ID, actor, action, timestamp, and outcome per policy | Full message or secrets not required for audit |

Message ID and correlation ID typically have very high cardinality. Using them as metric tags causes time series counts to grow with message volume and can overload the metrics backend. Use logs or traces to inspect individual messages; use metrics to measure trends and rates.

## 12. Retries, Redeliveries, and Message IDs

When a broker redelivers a JMS message, record both the message ID and redelivery status. JMS provides `JMSRedelivered`; some providers also supply `JMSXDeliveryCount` for the delivery count. Verify exact support and semantics for your JMS provider.

Distinguish:

- **Redelivery of the same message:** the transport message is sent again by the broker; the message ID usually stays the same while the delivery attempt increments.
- **Republishing a new message:** the application sends a new message; the broker may assign a new message ID. If it still represents the same business event, event ID and correlation ID should be preserved.
- **Emitting a new event:** new event ID, causation ID pointing to the event/message that triggered it, and correlation ID preserved if within the same workflow.

IDs alone do not protect against duplicate processing. Use an idempotency key or an inbox/deduplication table keyed by event ID/business key to prevent duplicate side effects. Persist idempotency state in the appropriate transaction alongside business processing.

When a message moves to a dead-letter queue, retain the original IDs and add information about the cause, delivery count, and DLQ timestamp. When replaying messages, decide clearly which event ID is kept, which message ID will be new, and whether a replay ID is needed to distinguish the replay.

## 13. Testing Log Correlation

A useful test suite should verify:

1. Producer generates a correlation ID when starting a workflow and propagates it to all child messages.
2. Broker assigns a message ID and the listener reads that ID.
3. Child message's causation ID points accurately to the parent message/event.
4. Concurrent requests still match replies by the right correlation key.
5. Redelivery preserves the appropriate message identifier and records the delivery attempt.
6. Republishing the same event preserves event ID/correlation ID while receiving a new message ID if the broker generates one.
7. MDC is restored after each listener invocation; the next message does not inherit the previous message's IDs.
8. Trace context is propagated across producer and consumer; the trace has accurate span relationships.
9. Logs do not contain secret payloads, tokens, or unauthorized personal data.
10. Metrics do not create labels per message or workflow ID.

You can use integration tests with a real broker to confirm JMS headers/properties are sent and received properly. For Spring Integration, verify message headers and sequence metadata through splitters/aggregators. For tracing, use a test observation handler or test exporter to confirm context injection/extraction.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using message ID as correlation ID | Child messages no longer share a workflow key | Generate a stable correlation ID for the workflow |
| Using trace ID as event ID | Multiple distinct events get merged into one event | Separate trace ID from event ID |
| Using JMSCorrelationID for all correlation types | Request/reply may pair incorrectly or collide | Separate JMS request/reply from workflow correlation |
| Not preserving event ID on republish | Cannot recognize the same event across sends | Use an application-managed event ID |
| Not recording causation ID | Hard to trace parent-child message chains | Attach causation ID to child messages |
| Only logging IDs on the consumer | Unknown where the message originated | Log IDs on publish, process, and errors |
| Leaving MDC populated after listener | Next message's logs get tagged with wrong correlation ID | Restore/clear MDC in finally |
| Using correlation ID as a metric label | Causes excessive cardinality | Keep IDs in logs/traces |
| Copying trace ID manually without parent span | Trace breaks or has wrong relationships | Use Micrometer/OpenTelemetry propagation |
| Logging all headers or payloads | Can leak secrets or personal data | Allow-list fields and redact sensitive data |

## 15. Implementation Checklist

- [ ] Message ID, event ID, correlation ID, causation ID, and trace ID have distinct meanings.
- [ ] Producer records message ID/event ID/correlation ID at the appropriate layer.
- [ ] Consumer logs IDs alongside destination, outcome, and delivery attempt.
- [ ] JMSCorrelationID is used consistently for request/reply if needed.
- [ ] Workflow correlation is preserved across child messages, retries, and republishes.
- [ ] Causation ID points to the message/event that directly produced the current message.
- [ ] Spring Integration uses CORRELATION_ID, SEQUENCE_NUMBER, and SEQUENCE_SIZE according to the pattern.
- [ ] Trace context is injected/extracted via appropriate instrumentation or Propagator.
- [ ] MDC is restored in finally and context is propagated across thread/reactive boundaries.
- [ ] Message history is enabled only on flows needing diagnostics.
- [ ] High-cardinality IDs are not used as metric labels.
- [ ] Logs do not contain raw payloads, tokens, or sensitive data.
- [ ] Tests cover concurrent request/reply, redelivery, republish, fan-out, and context propagation.

## References

- [Spring Framework — Message-driven POJOs with @JmsListener](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): listener signatures, JMS headers, and accessing raw JMS Message or Spring Message.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): JmsTemplate, MessageCreator, request/reply, and JMS support.
- [Spring Framework Javadoc — JmsHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/JmsHeaders.html): MESSAGE_ID, CORRELATION_ID, REDELIVERED, and standard headers.
- [Spring Integration — Message](https://docs.spring.io/spring-integration/reference/message.html): MessageHeaders.ID, IntegrationMessageHeaderAccessor.CORRELATION_ID, and sequence headers.
- [Spring Integration — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): distinguishing generic correlationId and JMSCorrelationID, header mapping, and request/reply.
- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html): enabling and reading the history header in flows.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): JMS publish/process observations and tracing propagation.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracing API, context propagation, and baggage.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent and tracestate formats.

