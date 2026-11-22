# Message Correlation in Java Logging: Linking Event Chains Between Producer and Consumer

## 1. What is message correlation?

In synchronous HTTP Java applications, a request can be tracked using a request ID and trace. In **message-driven** systems, a unit of work is often split into multiple messages flowing through Kafka, JMS, RabbitMQ, or another broker. A message may sit in a queue, be processed in another process, be retried, redelivered multiple times, fanned out to multiple consumers, or routed to a dead-letter queue (DLQ). If each service only logs locally **without propagating correlation context**, operators will find it very difficult to tell which log lines belong to the same business journey.

Example:

~~~text
HTTP order request
    |
    v
order-service
    | publish msg-1 (ORDER_ACCEPTED)
    | correlation_id=corr-42
    v
orders topic
    |
    v
invoice-service
    | consume msg-1
    | publish msg-2 (INVOICE_REQUESTED)
    | correlation_id=corr-42
    | causation_id=msg-1
    v
invoice topic
    |
    v
notification-service
      consume msg-2
      correlation_id=corr-42
~~~

**Message correlation** is the practice of placing appropriate IDs in the message **headers/properties/envelope**, propagating them across processing steps, and including them in the logs of each producer/consumer. A query for `correlation_id=corr-42` can return the entire processing chain, while `message_id` and `causation_id` identify the specific message and the cause that triggered the next message.

This is different from **simply setting a global `currentRequestId` variable**: messages can run concurrently across multiple threads, so the context must belong to the **message and processing scope**, not the entire JVM.

### Objectives

After this lesson, you will be able to:

- Distinguish between correlation ID, message ID, causation ID, request ID, trace ID, and span ID.
- Design a metadata contract and rules for generating/preserving IDs across services.
- Write a standalone Java 17 example demonstrating propagation across two messages.
- Understand W3C `traceparent` and OpenTelemetry messaging spans, without confusing business correlation with distributed tracing.
- Apply correlation to Kafka headers, `JMSCorrelationID`, and RabbitMQ properties.
- Propagate context properly across thread pools, MDC, asynchronous callbacks, and batches.
- Handle retries, redeliveries, fan-out, fan-in, DLQs, replays, and the transactional outbox.
- Test log correlation without exposing sensitive information or creating excessive metric cardinality.

## 2. Six easily confused IDs in message logging

| Field | Meaning | Typical Scope | What Not to Infer |
| --- | --- | --- | --- |
| correlation_id | Groups events within the same business workflow | Multiple messages and multiple services | Not an authenticated identity |
| message_id | Identifies a logical message/envelope per contract | One message, possibly multiple deliveries | Not synonymous with correlation ID |
| causation_id | Which event/message directly triggered the new event | Parent → child relationship | Does not fully describe multi-cause fan-in |
| request_id | Identifies a request at the entry point, usually HTTP | One request/hop in the system | Does not necessarily live for the entire long workflow |
| trace_id | Identifies related spans within a trace | Distributed trace per the tracing model | Not automatically synonymous with a business workflow |
| span_id | Identifies a specific span | One instrumented operation | Not a message ID |
| delivery_attempt | Which delivery or processing attempt by broker/consumer | One delivery attempt | Not a new logical message |
| idempotency_key | Identifies an operation that needs duplicate-processing protection | Per business operation | Cannot use a shared correlation ID for all messages |

Example of a workflow with `correlation_id=corr-42`:

~~~text
msg-1: ORDER_ACCEPTED
msg-2: INVOICE_REQUESTED, causation_id=msg-1
msg-3: STOCK_RESERVATION_REQUESTED, causation_id=msg-1
msg-4: EMAIL_REQUESTED, causation_id=msg-2
~~~

All four messages share the same correlation ID, but each has its own **message ID**. An event may be redelivered multiple times while still being the same logical message. If a retry creates a new envelope, you need to keep `original_message_id` or `operation_id` per contract to link the two envelopes.

A **business entity ID** such as `order_id` also does not replace `correlation_id`: a single order can go through multiple workflows, and a single workflow can affect multiple entities.

### Correlation is not causation

Finding two logs with the same `corr-42` only means they are tagged with the same workflow; it does not prove log A caused log B. To know causal relationships, use `causation_id`, an event graph, transaction ordering, or appropriate span relationships. Timestamps from multiple nodes can suffer from clock skew and log buffering, so they are not sufficient to conclude exact ordering.

## 3. Who generates the correlation ID and when should it be preserved?

A useful contract could be:

1. **At a trusted entry point:** generate an internal correlation ID if a valid internal ID does not already exist. You can use `UUID.randomUUID()` or an appropriate ID generator.
2. **If an ID comes from a partner/client:** validate its format, length, and trust source. When you need to separate trust boundaries, store `external_reference` separately and generate a new internal ID.
3. **Producer:** preserve the correlation ID of the workflow currently being processed, generate a distinct message ID for the new message, and attach `causation_id` if it originates from a previous message.
4. **Consumer:** extract and validate headers. Do not generate a new correlation ID for each delivery of the same message if the workflow already has a valid ID.
5. **When starting a genuinely independent business process:** you may generate a new correlation ID and store a link to the old workflow if there is a relationship.
6. **Retry/DLQ:** preserve correlation and logical identity according to policy; add separate retry/delivery metadata.
7. **Log collector:** keep the correlation field as a searchable field, not just embedded inside a free-form string.

Example of generating an ID where a workflow is initiated:

~~~java
// Java 17 snippet, not a standalone program.
String correlationId = java.util.UUID.randomUUID().toString();
~~~

`UUID.randomUUID()` generates an ID suitable for many correlation cases. **Do not** put emails, phone numbers, tokens, session IDs, or payloads into the ID for lookup convenience. And a UUID **does not replace authorization**: knowing an ID must not allow someone to view another user's data.

Some services use the same request ID for correlation in a short HTTP-to-message flow; this can be valid if the contract is clear. However, workflows that wait for hours or start from a scheduler may need a business correlation ID that outlives a single HTTP request.

## 4. Designing the message envelope and schema

A message should carry business data and separate metadata:

~~~json
{
  "message_id": "msg-1",
  "event_type": "ORDER_ACCEPTED",
  "schema_version": 1,
  "occurred_at": "2026-11-10T03:00:00Z",
  "payload": {
    "order_id": "O-42"
  },
  "headers": {
    "correlation_id": "corr-42",
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  }
}
~~~

This is a **JSON illustration**: Kafka typically places headers separately from the value, JMS has headers/properties, and RabbitMQ has `BasicProperties`; you do not need to wrap all headers into a JSON body like the example. Depending on the framework, metadata names and types can be mapped to native headers.

| Metadata | When Used | Important Policy |
| --- | --- | --- |
| correlation_id | Across the workflow | Generated at entry point, validated, length-limited |
| message_id | Each logical message | Broker-generated or application-generated with convention |
| causation_id | New message has a prior cause | Points to the message/event that actually triggered it |
| original_message_id | Republish/retry creates a new envelope | Preserves the identity of the original message |
| event_type | Business message | Code-controlled enum/constant, not arbitrarily chosen by user |
| traceparent | Systems using tracing | Injected/extracted using a compatible tracing propagator |
| tracestate | Needed by tracing vendor | No sensitive data or oversized headers |
| baggage | Genuine propagation need | Bounded, avoid tokens/PII and cross-tenant leaks |
| schema_version | Multiple producer/consumer versions | Compatibility policy, replay testing |
| delivery_attempt | Retry/redelivery | Based on trusted broker/consumer rather than client self-reporting |

You need to agree on the **header charset** (for example UTF-8 for custom text IDs), byte limits, and rules for **duplicate header keys**. Do not allow messages from external sources to set the log level, index name, access permissions, or actual tenant solely through a header.

An event logging schema should contain at least: `service`, `event_type`, `message_id`, `correlation_id`, `destination`, `outcome`, `timestamp`. Add `causation_id`, `trace_id`/`span_id`, `attempt`, and `error_type` when meaningful; avoid dumping the entire message body into logs.

## 5. Producer: create envelope, inject context, log actual outcome

A producer typically:

1. Receives a valid business context.
2. If distributed tracing is used, creates a producer span or uses appropriate instrumentation and injects the tracing context into the message carrier.
3. Generates a distinct `message_id` for the new message.
4. Attaches `correlation_id` and `causation_id` when there is a parent message.
5. Publishes via the broker client and logs the **attempt**.
6. When receiving a success or failure callback/ack, logs the corresponding result.

~~~text
event=MESSAGE_PUBLISH_ATTEMPT id=msg-1 correlation_id=corr-42 destination=orders
event=MESSAGE_PUBLISH_ACK id=msg-1 correlation_id=corr-42 outcome=ACKED
~~~

These two lines are illustrative. A `send()` call returning without throwing an exception does not necessarily mean the broker has acknowledged it or the consumer has processed it. Distinguish between **publish attempted, broker acknowledged, consumer received, processing completed, business committed, and message ack/offset commit**.

Do not log a `MESSAGE_PUBLISHED_SUCCESS` event immediately after an async `send` call if the broker can return an error later in the callback. The callback may run on a thread without the original MDC, so you must **capture an immutable correlation ID** before registering the callback or use properly scoped context instrumentation.

## 6. Consumer: extract and log within each message's scope

A consumer needs to:

1. Receive the message along with headers/properties from the broker.
2. Validate the correlation ID and metadata size/source limits.
3. Extract the tracing context using a propagator when instrumentation is present.
4. Open a processing scope for the **current message**.
5. Set MDC/context if used; log received/started and outcome/failed.
6. Execute business logic and publish downstream messages with the proper correlation/causation IDs.
7. Close/restore the scope in a `finally` block, even when an exception occurs.
8. Ack/commit/settle according to the delivery contract and transaction, not based on whether logging succeeded.

~~~text
Broker delivery
    |
    v
Read headers, validate IDs
    |
    v
Extract tracing context, open scope/MDC
    |
    +-- log received message_id, correlation_id
    +-- process business operation
    +-- publish children if needed
    +-- log completed / failure
    |
    v
Close scope, clear/restore MDC
    |
    v
Ack / commit / retry according to broker semantics
~~~

In consumers running on a thread pool, **do not use a static mutable `currentCorrelationId`**. It can be overwritten when two messages arrive concurrently on different threads. The context must live in the message envelope or the context scope of the current task.

## 7. Standalone Java 17 example: two messages linked by correlation and causation

The program below uses only JDK 17: a `record` as the envelope, `ArrayDeque` as an in-memory queue, and `java.util.logging.Logger` (JUL) printing logs to stdout. It requires no Kafka, Spring, or external libraries. ID values are fixed so the output can be verified exact-match.

**File: MessageCorrelationDemo.java**

~~~java
import java.util.ArrayDeque;
import java.util.Map;
import java.util.Queue;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class MessageCorrelationDemo {
    private static final Logger LOG =
            Logger.getLogger("example.messaging.correlation");

    private static final String TRACE_ID =
            "4bf92f3577b34da6a3ce929d0e0e4736";

    // Illustrative parser for traceparent version 00 only.
    private static final Pattern TRACEPARENT_V00 =
            Pattern.compile(
                    "00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})");

    record Message(String id, String type,
                   Map<String, String> headers) {
        Message {
            headers = Map.copyOf(headers);
        }
    }

    private static String extractTraceId(String header) {
        if (header == null) return "none";
        Matcher m = TRACEPARENT_V00.matcher(header);
        if (!m.matches()) return "none";
        if (m.group(1).matches("0{32}")
                || m.group(2).matches("0{16}")) return "none";
        return m.group(1);
    }

    private static String correlation(
            Map<String, String> headers) {
        String id = headers.get("correlation_id");
        if (id == null || !id.matches("corr-[0-9]{1,8}")) {
            throw new IllegalArgumentException(
                    "Invalid internal correlation_id");
        }
        return id;
    }

    private static void publish(
            Queue<Message> queue, Message m) {
        String cid = correlation(m.headers());
        LOG.info("publish id=" + m.id()
                + " type=" + m.type()
                + " correlation_id=" + cid
                + " trace_id=" + extractTraceId(
                        m.headers().get("traceparent")));
        queue.add(m);
    }

    private static void consume(
            Queue<Message> queue, Message m) {
        String cid = correlation(m.headers());
        String cause = m.headers()
                .getOrDefault("causation_id", "-");

        LOG.info("consume id=" + m.id()
                + " correlation_id=" + cid
                + " causation_id=" + cause
                + " trace_id=" + extractTraceId(
                        m.headers().get("traceparent")));

        if ("ORDER_ACCEPTED".equals(m.type())) {
            // Fixed span ID value ONLY for simulation.
            String childTraceparent =
                    "00-" + TRACE_ID + "-b7ad6b7169203331-01";

            Message child = new Message(
                    "msg-2", "INVOICE_REQUESTED",
                    Map.of(
                            "correlation_id", cid,
                            "causation_id", m.id(),
                            "traceparent", childTraceparent));
            publish(queue, child);
        }
    }

    public static void main(String[] args) {
        Handler output = new Handler() {
            {
                setLevel(Level.INFO);
            }

            @Override
            public synchronized void publish(LogRecord r) {
                if (isLoggable(r)) {
                    System.out.println(r.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush(); // Do not close System.out.
            }
        };

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(output);

        Queue<Message> queue = new ArrayDeque<>();
        Message root = new Message(
                "msg-1", "ORDER_ACCEPTED",
                Map.of(
                        "correlation_id", "corr-42",
                        "traceparent",
                        "00-" + TRACE_ID
                            + "-00f067aa0ba902b7-01"));

        try {
            publish(queue, root);
            while (!queue.isEmpty()) {
                consume(queue, queue.remove());
            }
        } finally {
            output.flush();
            LOG.removeHandler(output);
            output.close();
        }
    }
}
~~~

**Compile and run with JDK 17 or later:**

~~~bash
javac -encoding UTF-8 MessageCorrelationDemo.java
java MessageCorrelationDemo
~~~

**Exact stdout:**

~~~text
publish id=msg-1 type=ORDER_ACCEPTED correlation_id=corr-42 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
consume id=msg-1 correlation_id=corr-42 causation_id=- trace_id=4bf92f3577b34da6a3ce929d0e0e4736
publish id=msg-2 type=INVOICE_REQUESTED correlation_id=corr-42 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
consume id=msg-2 correlation_id=corr-42 causation_id=msg-1 trace_id=4bf92f3577b34da6a3ce929d0e0e4736
~~~

### Code analysis

- The root message `msg-1` has `correlation_id=corr-42` and an illustrative version 00 `traceparent`.
- `publish()` logs an event and puts the envelope into the queue. In the in-memory simulation, this is a `queue.add` operation; in a real broker, publish acknowledgment must be handled separately.
- `consume()` **reads the context back from the exact message's headers**, rather than using a global value.
- When processing `ORDER_ACCEPTED`, the program creates `msg-2` with a new message ID and `causation_id=msg-1`, while preserving `correlation_id`.
- The two `traceparent` values in the example share the same trace ID and have different parent-ids, solely to illustrate the metadata concept when there is a new sending span.
- `LOG` does not propagate to the root JUL handler thanks to `setUseParentHandlers(false)`; the custom `Handler` prints only the message, so there are no dynamic timestamps.
- `ArrayDeque` processes sequentially, with no concurrency altering the stdout order.

**Limitations:** This program **does not create OpenTelemetry spans**, does not implement full W3C Trace Context, does not use a real broker, and has no delivery acknowledgment, persistence, or retry. `TRACEPARENT_V00` only checks version 00, format, and that the two IDs are not all zeros. In production, **do not generate fixed span IDs or manually edit `traceparent` strings** as in this example. You must use real instrumentation/propagators to create new spans, inject/extract context, and handle version/`tracestate`/flags per the standard.

The regex `corr-[0-9]{1,8}` is only for sample data. Real systems may use UUID/ULID or opaque strings per their own contract, with different validation and trust-boundary rules. Do not use the demo code as authorization or as a generic filter for all real messages.

## 8. W3C Trace Context: tracing correlation vs. business correlation

A version 00 `traceparent` has the format:

~~~text
version-trace-id-parent-id-trace-flags
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

| Component | Version 00 Format | Role |
| --- | --- | --- |
| version | Two hex digits, 00 | Identifies the format |
| trace-id | 32 lowercase hex digits, not all 0 | ID for the trace |
| parent-id | 16 lowercase hex digits, not all 0 | Sender span ID / parent context |
| trace-flags | Two lowercase hex digits | Flags such as sampled |
| tracestate | Optional additional field | Tracing vendor-specific state |

W3C Trace Context defines the headers and context propagation rules; OpenTelemetry uses propagators to inject/extract across compatible carriers. In HTTP, `traceparent`/`tracestate` are headers; in Kafka/JMS/RabbitMQ, instrumentation can store them in message headers/properties.

**A Trace ID is not a correlation ID as defined by W3C.** A single workflow may span multiple traces due to wait times, sampling, trust boundaries, or batch processing. An application-defined correlation ID can exist independently.

When a producer creates a new message, the tracing library needs to inject **the context of the appropriate producer/create/send span**, rather than keeping the `parent-id` of the consumed message and treating it as a new span. The consumer extracts the message creation context and then creates an appropriate process span or link.

### Parent-child or span links?

Message processing differs from HTTP request-response: messages can wait for a long time, fan out to multiple consumers, or be processed in batches. **OpenTelemetry messaging semantic conventions** describe the operations `create`, `send`, `receive`, `process`, and `settle`. Depending on the broker type, instrumentation, and batch cardinality, a consumer may have a span with a parent-child relationship or use **span links** to the message creation context.

If a batch contains five messages from five different traces, do not assign the trace context of the first record as the parent for the entire batch and claim that represents causality for all five. Use the tracing model supported by your instrumentation and verify the actual relationships in the trace backend.

### Sampling and retention

A log with `correlation_id` may still exist when a trace is sampled out or past its retention period. Conversely, an exported trace might not contain full business logs. Therefore, **two layers of linkage** are needed when appropriate: business correlation to group workflows, and trace context to locate detailed spans.

Baggage can propagate key/value pairs across multiple services, but **do not use baggage to store tokens, cookies, emails, or sensitive information**. Limit both length and field count, because every hop receiving the context can inspect the propagated metadata.

## 9. MDC in SLF4J/Logback: open and close by scope

In applications using SLF4J/Logback, MDC allows the formatter to attach `correlation_id`/`trace_id` to logs:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level corr=%X{correlation_id:-} trace=%X{trace_id:-} %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This is **Logback XML**; it does not run with JUL or Log4j 2. MDC only assists with logging context; it does not create distributed spans.

In the consumer (snippet requires SLF4J/backend and application variables):

~~~java
// cid and traceId are already validated and extracted from the exact message.
try (org.slf4j.MDC.MDCCloseable c =
             org.slf4j.MDC.putCloseable("correlation_id", cid);
     org.slf4j.MDC.MDCCloseable t =
             org.slf4j.MDC.putCloseable("trace_id", traceId)) {

    log.info("process_started id={}", messageId);
    processBusinessMessage();
    log.info("process_completed id={}", messageId);
}
~~~

**Non-standalone snippet:** `log`, `cid`, `traceId`, `messageId`, and `processBusinessMessage` must be provided by the application. `MDCCloseable` removes the key when the scope closes. If scopes are nested and the key already had a value, `remove` does not necessarily restore the previous value; you need snapshot/restore by design.

### Thread reuse and correlation leakage

A worker thread may process `msg-A` and then `msg-B`. If you forget to clear/restore, logs for `msg-B` may still carry `msg-A`'s correlation ID. To prevent this:

- Extract a dedicated context at the start of **each message processing**.
- Use `try`/`finally` or an auto-closeable scope, even on exception/cancellation.
- With thread pools/`CompletableFuture`, capture an immutable context and pass it properly to the task.
- Do not assume MDC/`ThreadLocal` automatically propagates to every executor thread.
- With Reactor/reactive pipelines, use the framework's context propagation instead of relying on `ThreadLocal` in callbacks.
- When an async logging appender offloads formatting to a logging worker, verify whether the backend captures MDC at the time the log event is created.

If a producer callback runs after the `publish` method returns, the callback thread's MDC may differ from the producer's MDC. Capture the correlation/message ID in a `final`/effectively-final variable for the callback, or apply properly scoped instrumentation.

### Example of restoring a key when running a task

~~~java
// SLF4J snippet, not standalone.
String capturedCid = cid;
executor.submit(() -> {
    String previous = org.slf4j.MDC.get("correlation_id");
    try {
        org.slf4j.MDC.put("correlation_id", capturedCid);
        doWork();
    } finally {
        if (previous == null) {
            org.slf4j.MDC.remove("correlation_id");
        } else {
            org.slf4j.MDC.put("correlation_id", previous);
        }
    }
});
~~~

This snippet only propagates a single MDC key; it does **not** propagate OpenTelemetry `Context`, security principals, or transaction context. In real systems, use a tested task decorator/instrumentation to capture/restore all required context.

## 10. Kafka: correlation via record headers

A Kafka record has a topic, partition, offset, key, value, timestamp, and **headers**. Custom correlation IDs usually reside in headers; the broker **does not automatically enforce** `correlation_id` for all applications.

Producer using `kafka-clients` (snippet requires dependency and `producer`/`cid`/`payload` variables):

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, String> record =
        new ProducerRecord<>("orders.events", "order-42", payload);

record.headers().add(
        "correlation_id",
        cid.getBytes(StandardCharsets.UTF_8));

producer.send(record, (metadata, error) -> {
    if (error == null) {
        log.info("publish_ack topic={} partition={} offset={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset());
    } else {
        log.error("publish_failed", error);
    }
});
~~~

Consumer reading the header (`kafka-clients` snippet):

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;

// record is a ConsumerRecord<String, String> from poll().
Header h = record.headers().lastHeader("correlation_id");
String correlation = h == null
        ? null
        : new String(h.value(), StandardCharsets.UTF_8);
~~~

**Notes:**

- Reading `lastHeader` is an API choice, not proof that other headers with the same name are safe. Design a policy for conflicting duplicate headers and byte limits.
- A Kafka topic-partition-offset identifies a record's position within a partition, **not a business message ID across multiple topics**.
- The Kafka record key is used for partitioning/ordering per contract; do not change the key to a correlation ID just to make log searching easier.
- Consumer retries/rebalances/crashes can cause the same record to be reprocessed. Correlation helps with investigation, but the consumer still needs idempotency for side effects.
- The producer `send` callback does not mean the entire workflow has completed; log the broker ack separately from the consumer outcome.
- If a consumer creates a child message on another topic, preserve `correlation_id`, generate a new ID, and add `causation_id`/`original_message_id` when needed.
- With Spring Kafka and OpenTelemetry instrumentation, check how the propagator injects/extracts, batch listener mode, and actual header mapping for your version.
- When processing a batch, each record has its own context; do not apply the first record's MDC to all records.

## 11. JMS/Jakarta Messaging: request/reply and JMSCorrelationID

JMS has the following fields:

- **JMSMessageID:** the message ID handled/assigned by the provider according to its mechanism.
- **JMSCorrelationID:** a correlation field the application can set to link requests and replies.
- **JMSReplyTo:** the reply destination in request/reply.
- **JMSRedelivered:** an indicator that the message may have been redelivered, per broker/provider semantics.

In a request/reply pattern, the reply can set `JMSCorrelationID` to **the request's `JMSMessageID`** so the client can match the pair. This is **a usage convention**, not a rule that every `JMSCorrelationID` must equal the request ID. A business workflow can use its own internal correlation ID across multiple events.

Jakarta Messaging snippet (requires API, `session`, `producer`, and `payload`):

~~~java
jakarta.jms.TextMessage msg =
        session.createTextMessage(payload);
msg.setJMSCorrelationID(cid);
msg.setStringProperty("event_type", "ORDER_ACCEPTED");
producer.send(msg);
~~~

Do not assume `JMSMessageID` has its final value before the provider sends the message. In older Java EE applications using `javax.jms`, imports will differ from Jakarta Messaging using `jakarta.jms`. Do not mix the two namespaces when frameworks are incompatible.

Do not put sensitive bodies, access tokens, or overly long IDs into `JMSCorrelationID`. In the listener, read the ID from the **actual message**, validate it, and then open the MDC/tracing scope before logging.

## 12. RabbitMQ/AMQP: properties and separate acks

The RabbitMQ AMQP 0-9-1 Java client has `BasicProperties` containing `correlationId`, `messageId`, `replyTo`, `headers`, and other attributes. Snippet (requires RabbitMQ client and `channel`/`body` variables):

~~~java
com.rabbitmq.client.AMQP.BasicProperties properties =
        new com.rabbitmq.client.AMQP.BasicProperties.Builder()
                .correlationId(cid)
                .messageId(messageId)
                .contentType("application/json")
                .headers(java.util.Map.of(
                        "event_type", "ORDER_ACCEPTED"))
                .build();

channel.basicPublish(
        "orders-exchange", "orders.accepted",
        properties, body);
~~~

Here, **`correlationId`** is not automatically a `traceparent`. If using tracing, instrumentation/propagators must pass the tracing context through `headers` according to an accepted convention.

Distinguish between:

- Publisher confirm: the broker confirms receipt according to publish/confirm configuration.
- Consumer delivery: the message is delivered by the broker to the consumer.
- Consumer acknowledgment: the consumer acknowledges delivery per policy.
- Business commit: the database or downstream side effect has been committed.
- Log event: merely a logger call/event recorded at an observation point.

A "published" log line in the application does not replace publisher confirms; "processed" does not confirm that the consumer ack has reached the broker.

In RPC-style systems over RabbitMQ, `correlationId` is often used to match a reply with a request. If you want **long-term business correlation**, you must clearly define whether to reuse the RPC correlation or maintain a separate ID in `headers`.

### Other brokers

SQS has a service-generated `MessageId` and producer-sent `MessageAttributes`; FIFO group/deduplication IDs have their own roles. Azure Service Bus and other brokers also have their own message ID/correlation ID APIs. **There is no single standard header across all messaging systems.** You should build a mapping table and per-broker integration tests.

## 13. Retry, redelivery, and DLQ

A failed message may be redelivered:

~~~text
MESSAGE_RECEIVED id=msg-7 correlation_id=corr-42 attempt=1
MESSAGE_PROCESS_FAILED id=msg-7 correlation_id=corr-42 attempt=1 error=TIMEOUT
MESSAGE_RECEIVED id=msg-7 correlation_id=corr-42 attempt=2
MESSAGE_PROCESS_COMPLETED id=msg-7 correlation_id=corr-42 attempt=2
~~~

These lines are an example, not the output of the Java program in section 7. Two delivery attempts do not mean two independent business operations.

### Rules for retries

1. The same redelivered logical message usually retains its correlation ID and identity per broker semantics.
2. If a retry handler **republishes a new envelope**, generate a new `message_id` if required by the contract, but preserve `original_message_id` and `correlation_id`.
3. Obtain `attempt`/`retry_count` from a trusted source; do not let clients report a reduced retry count.
4. Configure backoff, max attempts, timeouts, DLQ policies, and monitoring.
5. **Do not use correlation ID as the sole idempotency key** for different messages in the same workflow; use an appropriate event ID/operation ID.
6. If a crash occurs after the business commit but before the ack, the consumer may reprocess the message. An idempotency mechanism is required, not just log correlation.

### Dead-letter queue

When routing to a DLQ, preserve the metadata needed for traceability:

~~~text
correlation_id=corr-42
original_message_id=msg-7
source_destination=payments
failure_category=VALIDATION_ERROR
last_attempt=5
~~~

This is a **policy diagram**, not standard DLQ header names across all brokers. Some systems add dead-letter reason, source queue/exchange, and delivery count in their own way.

When replaying from a DLQ:

- Distinguish the replayed message ID from the original ID.
- Preserve correlation to trace back the history.
- Do not include the full payload/tokens in error logs.
- Do not assume replay causes no side effects: idempotency is required.
- Verify whether the bridge/redrive tool drops custom headers or tracing context.

## 14. Fan-out, fan-in, and batch

### Fan-out

~~~text
ORDER_ACCEPTED msg-1 (corr-42)
    |
    +--> INVOICE_REQUESTED msg-2 (cause=msg-1)
    +--> STOCK_RESERVATION_REQUESTED msg-3 (cause=msg-1)
    +--> EMAIL_REQUESTED msg-4 (cause=msg-1)
~~~

Each child has its own message ID, while preserving the workflow's correlation ID. If all three consumers retry at the same time, looking only at the correlation ID will not distinguish which branch is failing; you need `message_id`, `event_type`, and `attempt`.

### Fan-in

If `ORDER_READY` is only emitted after `PAYMENT_CONFIRMED` **and** `STOCK_RESERVED`, there are **two direct causes**. A single `causation_id` cannot fully describe this; you may need a list of `causation_ids` or explicitly store an event graph/workflow state.

In tracing, the two messages may carry different trace contexts. A process span for fan-in/batch can use span links to the message creation contexts; do not arbitrarily pick the first record's trace as the parent of all.

### Batch processing

- Extract context for **each record**, rather than sharing the first record's MDC.
- A batch summary log should include `batch_id`, count, failures, and elapsed time; do not arbitrarily attach a single correlation ID to the entire batch.
- When logging an item-specific error, use the `message_id`/`correlation_id` of that exact record.
- Batch commits can cause already-processed records to be replayed after a crash; idempotency is still required.
- If your tracing tool supports batch spans/links, use them according to semantic conventions.

## 15. Security and privacy of correlation headers

Headers are **data**, not proof of identity. Common risks include:

- An attacker sends someone else's `correlation_id` to deliberately merge logs or bypass view permissions.
- A client sends CR/LF/control characters in an ID, causing log injection if the text formatter does not escape them.
- A tenant spoofs a `tenant_id` or `actor_id` header to cause misattribution in logs.
- A message carries large baggage or PII forwarded across multiple services.
- Instrumentation accepts a malformed `traceparent` without enforcing a trust boundary policy.
- Metrics use `correlation_id`/`message_id` as labels, causing high cardinality and high cost.
- A consumer forgets to clear MDC, causing another tenant's logs to carry the wrong context.

**Defenses:**

1. Validate IDs against the chosen standard: type/charset/length and source, with byte limits.
2. Generate a new internal ID when not trusting IDs from an external boundary; store `external_reference` separately.
3. Do not use `correlation_id` as authentication, authorization, or an access token.
4. Derive event type, service, severity, and tenant scope **from server/auth context**.
5. Encode untrusted fields in the formatter; structured JSON encoders must escape properly.
6. Do not put tokens, cookies, emails, secrets, or bodies into baggage/headers/logs.
7. Restrict log backend access by tenant/role, configure retention, and audit access.
8. Block arbitrary dynamic logger/index/destination selection from input.
9. Limit header count/size to reduce memory/broker overload risks.
10. Test duplicate headers, missing headers, corrupted values, cross-tenant queries, and thread reuse.

Tracing IDs can link user behaviors even when not directly PII; classify privacy and retention according to policy.

## 16. Correlation does not guarantee transactions or exactly-once

A log line:

~~~text
MESSAGE_PROCESS_COMPLETED correlation_id=corr-42 message_id=msg-7
~~~

does not by itself prove that the DB committed, the offset was committed, downstream received the new event, or the side effect happened exactly once.

One solution for reliably sending messages alongside database updates is the **transactional outbox**:

~~~text
In the same DB transaction:
  update business state
  insert outbox event:
      event_id
      correlation_id
      causation_id
      payload
COMMIT

Outbox publisher:
  read unsent events
  publish via broker
  record send status

Consumer:
  deduplicate / process idempotently
  commit/ack per contract
~~~

An outbox helps avoid the gap where "DB commits then the process crashes before writing the message," but publishers and consumers can still see duplicate events due to retries. `correlation_id` helps link observations, **it is not a deduplication key**.

Similarly, distributed traces may be sampled and logs have short retention; if business/audit events must be stored in full, use a durable event store/audit log per separate requirements rather than relying solely on MDC or tracing spans.

## 17. Log schema, querying, and observability

An example structured log event:

~~~json
{
  "event_type": "MESSAGE_PROCESS_COMPLETED",
  "service": "invoice-service",
  "messaging_system": "kafka",
  "destination": "invoice.events",
  "message_id": "msg-2",
  "correlation_id": "corr-42",
  "causation_id": "msg-1",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "attempt": 1,
  "outcome": "SUCCESS",
  "duration_ms": 28
}
~~~

This is an **illustrative schema**; OpenTelemetry does not mandate these exact custom fields. If you add `span_id`, it must come from the **current active span** provided by tracing instrumentation—do not arbitrarily take a value from a message header and call it the consumer span.

Some useful event names:

~~~text
MESSAGE_PUBLISH_ATTEMPT
MESSAGE_PUBLISH_ACK
MESSAGE_RECEIVED
MESSAGE_PROCESS_STARTED
MESSAGE_PROCESS_COMPLETED
MESSAGE_PROCESS_FAILED
MESSAGE_RETRIED
MESSAGE_DEAD_LETTERED
MESSAGE_ACKED
~~~

You do not need to log every milestone at INFO for all messages: doing so can increase costs and cause log storms. Choose the necessary milestones, use metrics for throughput/error rate/latency, and assign log levels appropriate to their purpose.

### Querying by correlation

~~~text
Find: correlation_id = corr-42
Then: group by message_id, event_type, attempt, service
Then: follow causation_id to reconstruct message graph
Then: open trace_id in tracing backend if available
~~~

This is a pseudo-query, not literal SQL/OpenSearch/Loki syntax. Timestamps may be delayed by brokers/collectors, and node clocks may skew; use causal IDs rather than sorting solely by time.

**Metric labels should have low cardinality:** `service`, `destination_class`, `message_type`, `outcome`, and `retry_bucket`. Do not use `correlation_id`, `message_id`, `user_id`, or `trace_id` as per-message Prometheus labels.

## 18. Multi-service integration checklist

| Question | Decision to Document |
| --- | --- |
| Which entry point generates the ID? | HTTP ingress, scheduler, command handler, or message bridge |
| Is the external ID trusted? | How to validate/map to an internal ID |
| ID format? | UUID/ULID/opaque; charset, length, uniqueness |
| Where does the Message ID come from? | Broker or application; does it change on republish |
| Causality? | Single `causation_id` or list of causes |
| Tracing? | OTel propagator/instrumentation, semantic links |
| Header names/encoding? | Conventions, UTF-8, duplicate key/size policy |
| Async? | Callback/executor/reactive context propagation |
| MDC? | Open/close/restore for the exact message |
| Retry? | `attempt`, original ID, idempotency key |
| DLQ/replay? | Which metadata must be preserved |
| Observability? | Schema, index/retention, dashboards, metrics |
| Security? | ID spoofing, PII, cross-tenant isolation |
| Versioning? | Will old messages in queues/DLQs still be processed |
| Testing? | Unit + real broker integration + collector readback |

To rename headers or change tracing conventions, you need a **migration window**: a new consumer version may receive old messages from a DLQ weeks later. You can support two field versions during the transition with clear precedence rules, alerting when anomalous data is detected.

## 19. Testing message correlation

### 19.1. Unit tests

| Case | Expectation |
| --- | --- |
| Valid header corr-42 | Consumer logs the correct correlation |
| Child message | Preserves correlation, generates new message ID, causation points to parent |
| Missing/invalid header | Reject/quarantine or generate new ID per policy |
| Header contains CR/LF | Does not cause log injection |
| Malformed traceparent | Not treated as a valid trace |
| All-zero Trace ID | Ignores invalid tracing context |
| Retry message | Correlation preserved, attempt distinguished |
| Republish new envelope | `original_message_id` is correct |
| Fan-out | Children have distinct IDs, same workflow |
| Fan-in | Causation sufficiently represents multiple sources |
| Thread reuse | Previous message's MDC does not leak to the next message |
| Duplicate header | Applies clear rule, does not trust arbitrary value |
| Message from another tenant | Does not bypass view/access permissions |
| DLQ | Preserves origin and correlation without leaking payload |

### 19.2. Integration tests

1. Publish a message through a real client/broker or appropriate test broker.
2. Verify headers at the broker and consumer, not just logs before `send()`.
3. Consumer A receives and publishes a child; consumer B receives and verifies correlation and causation.
4. Simulate an exception, retry/redelivery, and verify identity/attempt.
5. Route a message to the DLQ, redrive/replay it, and verify custom headers are not lost.
6. Enable tracing instrumentation; verify `traceparent` is injected/extracted and spans/links are sensible.
7. Run two messages concurrently, reuse threads, and verify MDC does not mix.
8. Inspect actual logs from the backend/collector and access permissions, not just a mocked Logger.
9. Test invalid headers, duplicate keys, oversized payloads, and charset issues.
10. Verify correlation/trace IDs are not placed into high-cardinality metric labels.

### 19.3. Distinguishing publish, processing, and ack failures

A message may have been sent by a producer while the callback fails; a consumer may process successfully but crash before acking; an outbox may re-emit the same event. In each case, log the accurate milestone name:

- `PUBLISH_ATTEMPT` is different from `PUBLISH_ACK`.
- `RECEIVED` is different from `PROCESS_COMPLETED`.
- `BUSINESS_COMMITTED` is different from `ACKED`.
- `DEAD_LETTERED` should only be asserted when the DLQ actually receives the message per the broker model.
- `TRACE_EXTRACTED` does not mean authorization succeeded.

Avoid logging a success outcome too early, because no amount of correlation can fix an event named inaccurately in reality.

## 20. Troubleshooting

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Producer has corr, consumer does not | Header not attached or dropped by bridge | Inspect message headers at each hop |
| A thread logs the previous message's corr | Forgot to clear/restore MDC | Add scope/`finally` and test thread reuse |
| Same corr but different trace | Long workflow, trace restart/sampling | Keep business correlation; use tracing links where appropriate |
| Has traceparent but trace backend is fragmented | Only copied string, did not extract/start span | Check propagator/instrumentation |
| Retry creates a new workflow | Regenerated correlation each time | Preserve original ID and `original_message_id` |
| Multiple messages falsely deduplicated | Used correlation as idempotency key | Use a distinct event/operation ID |
| DLQ loses corr | DLQ handler/bridge did not copy metadata | Test redrive and header mapping |
| Kafka record missing causation | Producer creating child forgot to attach | Attach causal link from parent message |
| JMS ID differs from expected | Confused `JMSMessageID` and `JMSCorrelationID` | Check request/reply contract |
| Duplicate header names | Producer/interceptor added multiple times | Define duplicate policy |
| Cross-tenant logs wrongly linked | Client-supplied ID trusted too much | Internal correlation + ACL |
| Metric index balloons | Used `message_id`/corr as label | Use finite-value labels |

**Investigation sequence:** pick a `message_id`, find the publish attempt/ack, check broker metadata, find consumer received/processed, follow `causation_id` to child messages, inspect retries/DLQ, and finally open the trace context. If data does not match, identify which hop lost the header or had the wrong scope.

## 21. Practice exercises

**Exercise 1 – Three-message chain.** Extend `MessageCorrelationDemo.java` so that `INVOICE_REQUESTED` produces `PAYMENT_REVIEW_REQUESTED` (`msg-3`). Keep `correlation_id=corr-42`, set `causation_id=msg-2`, and predict and verify stdout.

**Exercise 2 – Malformed headers.** Test a malformed `traceparent`, an all-zero trace ID, and a correlation ID containing a newline. Explain why the demo might reject or output `trace_id=none`, and why production must use a standard propagator and trust-boundary policy.

**Exercise 3 – MDC and thread pool.** Use a single-thread `ExecutorService` to process `corr-A` and `corr-B` sequentially. Intentionally omit cleanup to observe context leakage, then add restore in `finally` and retest.

**Exercise 4 – Kafka retry.** In a project with a Kafka client, publish a record with `correlation_id`, trigger a processing failure once, and log topic-partition-offset, `message_id`, `correlation_id`, and `attempt`. Identify an appropriate idempotency key instead of using the shared correlation ID.

**Exercise 5 – JMS request/reply.** Compare `JMSMessageID`, `JMSCorrelationID`, and `JMSReplyTo` of a request and reply under two conventions: the reply uses the request's message ID, or both keep a business correlation ID; check which contract the client/server agree on.

**Exercise 6 – Fan-out/fan-in.** One `ORDER_ACCEPTED` produces two child messages; only when both complete is `ORDER_READY` created. Draw the `message_id`/`causation_ids` graph and propose span links for multiple contexts.

**Exercise 7 – Security.** A partner sends another tenant's correlation ID and an ID containing CR/LF. Design internal ID mapping, validation, encoding, ACLs, and tests against log injection/cross-tenant leakage.

**Exercise 8 – Dashboard.** Use mock logs from multiple services to build a timeline by `correlation_id`, group by `message_id` and `attempt`, connect the causal graph, and point out limitations due to sampling/clock skew/retention.

## 22. Key takeaways

**Message correlation** combines business correlation, message identity, causality, and tracing context. `correlation_id` links the workflow; `message_id` distinguishes messages; `causation_id` indicates what generated a message; `trace_id`/`span_id` help analyze instrumented operations. These IDs **do not automatically replace one another**.

Producers need to pass metadata properly in messages; consumers must extract and manage the scope of each message; child messages preserve business correlation while having a new identity and clear causal link. For tracing, use OpenTelemetry/W3C propagators and proper span semantics instead of copying strings; for Kafka/JMS/RabbitMQ, test the headers/properties of the actual client you are running. Retries, DLQs, fan-out, fan-in, and batches are cases that must not be overlooked.

Correlation **does not guarantee** authentication, authorization, exactly-once delivery, idempotency, or durable auditing. Limit and validate IDs, do not log secrets/PII, avoid high-cardinality metric labels, and apply retention and access control. Always verify the full path **producer → broker → consumer → collector/backend**, not just a single `logger.info` call.

### References

- W3C Trace Context: https://www.w3.org/TR/trace-context/
- OpenTelemetry Context Propagation: https://opentelemetry.io/docs/concepts/context-propagation/
- OpenTelemetry Messaging Semantic Conventions: https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/
- OpenTelemetry Java Instrumentation: https://opentelemetry.io/docs/languages/java/instrumentation/
- Apache Kafka ProducerRecord: https://kafka.apache.org/clients/javadoc/org/apache/kafka/clients/producer/ProducerRecord.html
- Apache Kafka Headers: https://kafka.apache.org/clients/javadoc/org/apache/kafka/common/header/Headers.html
- Apache Kafka ConsumerRecord: https://kafka.apache.org/clients/javadoc/org/apache/kafka/clients/consumer/ConsumerRecord.html
- Jakarta Messaging Specification: https://jakarta.ee/specifications/messaging/
- RabbitMQ Java Client: https://www.rabbitmq.com/client-libraries/java-client
- RabbitMQ Consumer Acknowledgements and Publisher Confirms: https://www.rabbitmq.com/docs/confirms
- SLF4J Manual: https://www.slf4j.org/manual.html
- Logback MDC: https://logback.qos.ch/manual/mdc.html
- Oracle JDK 17 Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
