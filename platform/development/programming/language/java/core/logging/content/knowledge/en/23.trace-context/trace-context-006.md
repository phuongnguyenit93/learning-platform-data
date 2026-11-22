# Message Propagation in Java Trace Context

**Message propagation** (*message context propagation*) is the process of **injecting the producer's trace context into message metadata** when sending through a broker, and then **extracting and restoring that context on the consumer**. This enables observability systems to correlate operations across multiple services, multiple JVMs, different threads, and different processing times.

In Java, a common approach is to use **OpenTelemetry (OTel)** with the **W3C Trace Context** standard. The **TextMapPropagator** library converts tracing information into key–value pairs such as **traceparent** and **tracestate**, writes them into message headers, and decodes them when the consumer receives the message.

**Important distinction:** *propagation* only concerns passing context. It does not by itself guarantee that the broker received the message, does not guarantee exactly-once event processing, does not automatically add a trace ID to every log line, and does not guarantee that spans have been exported to a tracing backend.

## 1. Why propagate trace context over messages?

In a synchronous flow, a Java application can keep the current Context within the scope of a single call chain:

~~~text
HTTP request
  -> Server span
      -> Service span
          -> Repository span
~~~

However, with asynchronous communication:

~~~text
JVM A / producer               Message broker                JVM B / consumer
+---------------------+      +----------------------+     +----------------------+
| HTTP / work span    |      | Queue / Topic        |     | Message handler      |
| Producer span       |----->| Message body         |---->| Process span         |
| Inject trace data   |      | Trace metadata       |     | Extract trace data   |
+---------------------+      +----------------------+     +----------------------+
                                     |
                              May be delayed,
                              retry, redelivery,
                              or fan-out
~~~

JVM A's ThreadLocal and OpenTelemetry Context **cannot automatically travel across the network** to JVM B. The consumer may run hours later, long after the producer span has ended.

Without propagating context, tracing may record both sides without knowing they share the same origin. If you only pass a string **correlationId** in the payload, operators can search logs by ID, but the tracing SDK **does not automatically know the span relationship**. A consistent propagator and carrier are required.

### Concrete benefits

- Identify which request/operation originated a message.
- Correlate publishing with consuming/processing and error handling.
- Observe fan-out, retries, or dead-lettering without stitching logs together by timestamp.
- Query and investigate root causes across multiple services when spans are exported.
- Avoid forcing consumers to understand the internal tracing implementation of the producer.

## 2. What does trace context contain?

W3C Trace Context uses two important fields:

| Field | Purpose | Required? |
| --- | --- | --- |
| **traceparent** | Trace identifier, sender span identifier, and trace flags | Required when propagating a W3C trace context |
| **tracestate** | Optional vendor-specific tracing metadata for interoperability | Optional |

Example `traceparent` value:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Version 00 format:

~~~text
00 - 4bf92f3577b34da6a3ce929d0e0e4736 - 00f067aa0ba902b7 - 01
|                    |                          |              |
version           trace-id                   parent-id     trace-flags
2 hex              32 hex                     16 hex        2 hex
~~~

- **trace-id** is 16 bytes, represented as 32 hexadecimal characters; all zeros is invalid.
- **parent-id** is 8 bytes, represented as 16 hexadecimal characters; all zeros is invalid.
- **trace-flags** is 1 byte; the sampled bit indicates sampling intent, **not a mandatory command forcing downstream services to store every span**.
- **tracestate** is only included if the context contains permitted vendor-specific data.

When injecting the Producer span's context, `parent-id` in `traceparent` carries the **producer's span ID**. On the consumer side, the extracted context represents a **remote SpanContext**. If the consumer creates a new Process span, it gets a **new span ID**; it must not reuse the producer's span ID.

**Trace ID is not span ID.** A Trace ID represents an entire trace, whereas a span ID represents a single operation execution within that trace. A message also has its own message ID, and a message ID is not synonymous with a trace ID.

### Baggage vs. trace context

W3C **Baggage** can carry additional key–value pairs across service boundaries. It is not needed just to link trace IDs. Baggage can propagate across many systems and increase message header size; never put passwords, access tokens, personal emails, or payment information into baggage unless explicitly permitted by policy.

## 3. Choosing a carrier: metadata, not Java objects

A message typically has this structure:

~~~text
Message
├── Headers / Properties
│   ├── traceparent = "00-...-...-01"
│   ├── tracestate  = "..."         (optional)
│   ├── messageId   = "msg-42"
│   └── contentType = "application/json"
└── Body
    └── {"orderId":"ord-7","event":"order_created"}
~~~

**Do not serialize raw Java `Span`, `Context`, or `Scope` objects into the payload.** Those objects belong to the Java process and library. Only transfer the **wire format** supported by the propagator.

Prefer placing trace context in **headers/properties**, because:

1. The consumer does not need to parse the entire JSON body to extract the trace context.
2. Business schemas can evolve independently of tracing.
3. Brokers/adapters can forward metadata according to contract.
4. Business data and observability metadata have different lifecycles and access permissions.

If the transport does not support headers, you can design an envelope containing a dedicated **metadata** section in the payload with a clear schema/version. In that case, both producer and consumer must agree on where to read/write; a propagator configured for broker headers will not automatically know about custom JSON fields.

## 4. Message lifecycle: inject, publish, receive, extract, process

~~~text
PRODUCER
  Create/get current Context
           |
           v
  Create Create/Send span when needed
           |
           v
  propagator.inject(context, carrier, setter)
           |
           v
  Send message with headers
           |
           v
         BROKER
  Store/forward metadata
           |
           v
        CONSUMER
  Retrieve message, headers
           |
           v
  propagator.extract(root, carrier, getter)
           |
           v
  Get remote SpanContext if valid
           |
           v
  Choose parent or span links
           |
           v
  Create Process/Receive span
           |
           v
  Process, log, ack/nack
           |
           v
  End span, close Scope
~~~

In OpenTelemetry Java, the core API is:

~~~java
// Pseudocode; propagator, carrier, setter, getter, and context are created beforehand.
propagator.inject(context, carrier, setter);
Context recovered = propagator.extract(Context.root(), carrier, getter);
~~~

**TextMapSetter** knows how to put a key/value into the actual carrier type. **TextMapGetter** knows how to retrieve a key/value. **TextMapPropagator** is responsible for the tracing standard; do not manually concatenate or substring `traceparent` strings as a replacement for it.

Protocols may pass header values through multiple layers; verify whether the broker preserves, normalizes, or strips metadata. The fact that the producer created a header does not prove the consumer received it.

## 5. Two ways to link consumer to producer: parent and span link

This is the most commonly misunderstood point.

In synchronous HTTP, a parent–child relationship usually describes a single call chain. Messaging is more complex: a message can be delivered to multiple subscribers, retried multiple times, included in a batch, or processed under an existing HTTP span.

**According to OpenTelemetry Messaging Semantic Conventions, span links are the default linking mechanism** between the message creation context and Receive/Process spans. Links represent causality without forcing every message into a single parent–child tree.

**Exception:** for a single message, when it fits the execution flow, the Process span may use the message creation context as its parent. Instrumentation should make this choice explicit; do not apply parent–child mechanically when multiple sources are involved.

| Scenario | Usually appropriate approach | Why |
| --- | --- | --- |
| Single message, single Process span, no competing ambient parent | Can use parent–child | Simple causal model |
| Batch receiving multiple messages from different traces | Span links | A span can have only one parent |
| Fan-out to multiple consumers | Span links | Independent processing branches |
| Consumer running inside an HTTP SERVER span | Keep ambient parent, link to message creation context | Preserves both origins |
| Retry/redelivery/long delay | Links are usually advantageous | Multiple executions for one message |
| SDK/agent with built-in instrumentation | Follow the instrumentation's semantic conventions | Avoids inconsistent trace structures |

**Important consequence:** when using a **span link**, the consumer Process span **does not necessarily share the same trace ID** as the producer. The relationship is expressed via the link. Therefore, do not use "trace IDs must match" as a success criterion for every messaging system.

The runnable example below **chooses parent–child for a single message** to demonstrate how a remote parent is restored. That is a specific learning example, **not a default recommendation for all queues/batches**.

## 6. OpenTelemetry Java components to understand

| API/Concept | Role |
| --- | --- |
| **Tracer** | Creates spans by operation name |
| **Span** | A single execution, with a SpanContext and status |
| **SpanContext** | Trace ID, span ID, flags, and tracestate |
| **Context** | Context container in Java, which can hold a Span |
| **Scope** | Attaches a Context/Span as current for a processing block |
| **TextMapPropagator** | Injects/extracts metadata via a carrier |
| **TextMapSetter / TextMapGetter** | Adapters to write/read metadata for a specific broker type |
| **W3CTraceContextPropagator** | Implements the W3C traceparent/tracestate format |
| **SpanKind.PRODUCER** | A message send/creation operation |
| **SpanKind.CONSUMER** | A message processing operation |
| **SdkTracerProvider** | Creates spans in the SDK; does not imply they are exported |

In Java, **Span.fromContext(context)** retrieves a Span from an existing Context. **Span.current()** retrieves the span in the current active scope. These are two different operations: an **extracted** Context does not automatically become the thread's current context unless it is attached or used as a parent to create and activate an appropriate span.

## 7. Complete Java 17+ example: propagation with a simulated message

This example uses **JDK 17+, Maven, and OpenTelemetry SDK 1.45.0**. Instead of requiring a running Kafka/RabbitMQ broker, we represent a message as a record containing a headers map and a body. This keeps the focus on **inject/extract**, remote parent, Process span, scope, and handling an invalid `traceparent`.

### 7.1. Project structure

~~~text
message-trace-propagation/
├── pom.xml
└── src/main/java/demo/MessageTraceDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
 <modelVersion>4.0.0</modelVersion>
 <groupId>demo</groupId>
 <artifactId>message-trace-propagation</artifactId>
 <version>1.0.0</version>
 <properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
 </properties>
 <dependencies>
  <dependency>
   <groupId>io.opentelemetry</groupId>
   <artifactId>opentelemetry-api</artifactId>
   <version>1.45.0</version>
  </dependency>
  <dependency>
   <groupId>io.opentelemetry</groupId>
   <artifactId>opentelemetry-context</artifactId>
   <version>1.45.0</version>
  </dependency>
  <dependency>
   <groupId>io.opentelemetry</groupId>
   <artifactId>opentelemetry-sdk</artifactId>
   <version>1.45.0</version>
  </dependency>
 </dependencies>
 <build>
  <plugins>
   <plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
   </plugin>
   <plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.5.1</version>
   </plugin>
  </plugins>
 </build>
</project>
~~~

The versions in this example have been **compiled and verified by running**, rather than claiming to be the latest versions. In a production project, use the dependency management/BOM appropriate for your framework.

### 7.3. MessageTraceDemo.java

~~~java
package demo;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.propagation.TextMapSetter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import java.util.LinkedHashMap;
import java.util.Map;

public final class MessageTraceDemo {
    record Message(Map<String, String> headers, String body) {}

    private static final TextMapSetter<Map<String, String>> SETTER =
            (carrier, key, value) -> carrier.put(key, value);

    private static final TextMapGetter<Map<String, String>> GETTER =
            new TextMapGetter<>() {
                @Override
                public Iterable<String> keys(Map<String, String> carrier) {
                    return carrier.keySet();
                }
                @Override
                public String get(Map<String, String> carrier, String key) {
                    return carrier.get(key);
                }
            };

    public static void main(String[] args) {
        SdkTracerProvider provider = SdkTracerProvider.builder().build();
        OpenTelemetrySdk telemetry = OpenTelemetrySdk.builder()
                .setTracerProvider(provider)
                .setPropagators(ContextPropagators.create(
                        W3CTraceContextPropagator.getInstance()))
                .build();
        try {
            Tracer tracer = telemetry.getTracer("demo-messaging");
            Span producer = tracer.spanBuilder("orders publish")
                    .setSpanKind(SpanKind.PRODUCER)
                    .startSpan();
            Map<String, String> headers = new LinkedHashMap<>();
            telemetry.getPropagators().getTextMapPropagator().inject(
                    Context.root().with(producer), headers, SETTER);
            Message message = new Message(Map.copyOf(headers), "order-7");
            String producerTraceId = producer.getSpanContext().getTraceId();
            String producerSpanId = producer.getSpanContext().getSpanId();
            producer.end();

            Context received = telemetry.getPropagators()
                    .getTextMapPropagator()
                    .extract(Context.root(), message.headers(), GETTER);
            var remoteParent = Span.fromContext(received).getSpanContext();
            Span consumer = tracer.spanBuilder("orders process")
                    .setParent(received)
                    .setSpanKind(SpanKind.CONSUMER)
                    .startSpan();
            try (Scope ignored = consumer.makeCurrent()) {
                System.out.println("headerInjected="
                        + message.headers().containsKey("traceparent"));
                System.out.println("parentRemote=" + remoteParent.isRemote());
                System.out.println("sameTrace="
                        + producerTraceId.equals(consumer.getSpanContext().getTraceId()));
                System.out.println("parentSpanMatched="
                        + producerSpanId.equals(remoteParent.getSpanId()));
                System.out.println("newConsumerSpan="
                        + !producerSpanId.equals(consumer.getSpanContext().getSpanId()));
                System.out.println("scopeTraceMatches="
                        + Span.current().getSpanContext().getTraceId()
                                .equals(producerTraceId));
                System.out.println("bodyUnchanged="
                        + "order-7".equals(message.body()));
            } finally {
                consumer.end();
            }

            Map<String, String> bad = Map.of(
                    "traceparent",
                    "00-00000000000000000000000000000000-0000000000000000-01");
            Context invalid = telemetry.getPropagators()
                    .getTextMapPropagator().extract(Context.root(), bad, GETTER);
            System.out.println("invalidRejected="
                    + !Span.fromContext(invalid).getSpanContext().isValid());
            System.out.println("contextCleared="
                    + !Span.current().getSpanContext().isValid());
        } finally {
            provider.close();
        }
    }
}
~~~

**Note:** `GETTER` and `SETTER` here operate on **Map<String,String>**, a simulated carrier. Real Kafka, JMS, and RabbitMQ messages have different APIs. **Do not reuse this map adapter if the broker library requires header values as `byte[]` or typed properties.**

### 7.4. Compiling, running, and verifying output

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessageTraceDemo
~~~

**Verified stdout on Java 17+ with OpenTelemetry 1.45.0:**

~~~text
headerInjected=true
parentRemote=true
sameTrace=true
parentSpanMatched=true
newConsumerSpan=true
scopeTraceMatches=true
bodyUnchanged=true
invalidRejected=true
contextCleared=true
~~~

Explanation:

| Check line | Meaning |
| --- | --- |
| headerInjected=true | Producer injected `traceparent` into headers |
| parentRemote=true | Extractor created a remote `SpanContext` from received metadata |
| sameTrace=true | With parent–child selected, consumer kept the producer's trace ID |
| parentSpanMatched=true | The remote parent's span ID matches the producer span ID |
| newConsumerSpan=true | The consumer span is a new span and did not reuse the old span ID |
| scopeTraceMatches=true | `Span.current()` is correct while the consumer span is active |
| bodyUnchanged=true | Business payload was not modified by propagation |
| invalidRejected=true | A `traceparent` with all-zero `trace-id`/`parent-id` was rejected |
| contextCleared=true | After closing the scope, no valid current span remains |

**Do not print random IDs as fixed expected stdout.** The code checks relationships between them because trace IDs and span IDs are generated newly by the SDK on each run.

This example **does not configure a span processor/exporter**, so it **does not send spans to a real tracing backend**. It is a direct verification of inject/extract, remote parent, and current scope, not end-to-end telemetry export.

## 8. Replacing Map with Kafka, JMS, or RabbitMQ headers

Do not copy the demo `Map` verbatim into every client. Messaging systems use different carriers:

| System | Where trace context is carried | Implementation notes |
| --- | --- | --- |
| Kafka | Record headers | Text keys, values are typically `byte[]` |
| RabbitMQ | Message properties/headers | Values have client- and protocol-specific types |
| JMS | Message string properties | Properties API has naming/typing rules |
| SQS/cloud queue | Message attributes/metadata | Has size and attribute count limits |
| Custom event bus | Versioned metadata envelope | Both sides must agree on the schema |

### Pseudocode for Kafka

~~~text
producer:
  record = ProducerRecord(topic, body)
  inject(currentContext, record.headers, kafkaTextMapSetter)
  producer.send(record)

consumer:
  record = poll(...)
  recovered = extract(Context.root(), record.headers, kafkaTextMapGetter)
  createReceiveOrProcessSpan(recovered)
  handleBusinessData(record.value)
  ackOrCommitAccordingToPolicy
~~~

**This is pseudocode, not a complete Kafka program.** A Kafka `TextMapSetter` must encode text headers using an appropriate charset; `TextMapGetter` must decode them and handle multiple values for the same key according to policy.

With JMS, you can store `traceparent` as a string property. With RabbitMQ, header values may be byte arrays, strings, or other typed values depending on the library. **Do not assume broker APIs or binary encodings are identical.**

### What if the broker has no headers?

You can use a versioned **application envelope**:

~~~json
{
  "metadata": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  },
  "payload": {
    "event": "order_created",
    "orderId": "ord-7"
  }
}
~~~

This is **an illustrative design**, not a built-in standard field across all messaging SDKs. When using an envelope, both producer and consumer must know where the metadata lives; the propagator adapter must read from that exact location.

## 9. Producer: which context should be injected?

The current span is not always the right span to put into a message. In an HTTP request that emits an event:

~~~text
SERVER span: POST /orders
      |
      +-- Validate order
      |
      +-- PRODUCER span: send orders
                |
                +-- Inject creation context into message
                |
                +-- Broker send / publish
~~~

For a single message, the creation context can be the Send span. For a multi-message batch, a **separate Create span per message** may be appropriate to distinguish origins, while the Send span describes sending the batch as a whole.

To avoid mistakes:

- Inject only when you have a **valid context** you actually intend to propagate.
- Do not let two interceptors or agents both inject or overwrite metadata differently.
- Do not fabricate a trace ID using arbitrary string concatenation.
- When a message already carries an accepted creation context, define a clear rule on whether to preserve or replace it.
- Do not mistake an `inject` call for proof that the broker acknowledged the message.
- On send failures or retries, clearly separate send attempts, message identity, and business idempotency.

If your framework already provides **OpenTelemetry instrumentation** for Kafka/RabbitMQ/JMS, it may automatically create spans and inject headers. Check this before adding manual tracing to avoid **duplicated spans**.

## 10. Consumer: extracting and handling context properly

An illustrative skeleton:

~~~java
// Pseudocode in handler: carrier/getter/propagator/tracer already exist.
Context recovered =
        propagator.extract(Context.root(), carrier, getter);
Span process = tracer.spanBuilder("process message")
        .setParent(recovered)        // Only if parent-child is appropriate.
        .setSpanKind(SpanKind.CONSUMER)
        .startSpan();
try (Scope scope = process.makeCurrent()) {
    processBusinessMessage();
} finally {
    process.end();
}
~~~

**This is an illustrative snippet, not a standalone class.** The `Scope` should only exist for the duration of processing; close the scope before processing another message on the same thread.

To use a **span link** when the creation context is extracted:

~~~java
// Illustrative fragment; requires SpanBuilder/SpanContext imports and declared variables.
SpanContext source = Span.fromContext(recovered).getSpanContext();
SpanBuilder builder = tracer.spanBuilder("process message")
        .setSpanKind(SpanKind.CONSUMER);
if (source.isValid()) {
    builder.addLink(source);
}
Span process = builder.startSpan();
~~~

If the thread already has an appropriate ambient span, the builder can keep the ambient parent and add the link. If you want an independent root, explicitly call **setNoParent()**. Parent/link relationships should follow business semantics and messaging semantic conventions, not merely whether the extractor returned a Context.

### Context on another thread

Code using `ExecutorService` or `CompletableFuture` must transfer context explicitly:

~~~java
// Illustrative fragment inside a method with executor and runTask().
Context captured = Context.current();
executor.execute(() -> {
    try (Scope scope = captured.makeCurrent()) {
        runTask();
    }
});
~~~

**ThreadLocal does not automatically propagate across executors or other services.** You need a framework context propagation mechanism or explicit Context capture as needed. The `Scope` must be opened and closed on the actual thread executing the task.

If a thread pool reuses a worker for the next message without closing the previous `Scope`/MDC, subsequent logs may retain the previous message's trace ID.

## 11. Retries, redelivery, and dead-letter queues

In **at-least-once delivery** systems, a message may be processed multiple times.

~~~text
Message: msg-42, creation context P
      |
      +-- Attempt 1 -> Process span C1 -> timeout
      |
      +-- Attempt 2 -> Process span C2 -> retryable failure
      |
      +-- Attempt 3 -> Process span C3 -> success
~~~

Typically, **each attempt is a new execution** and should have a new span. Do not reuse the same `Span` object across three attempts. The Process spans can have **links to the same message creation context**, aiding investigation even if they belong to different traces.

Distinguish between:

- **Producer retry:** resending after a network error or ambiguous ack, which can produce duplicate messages.
- **Consumer redelivery:** receiving an unacknowledged or nacked message again.
- **DLQ:** moving a message to a dead-letter queue for failure handling. It may need another span and metadata preserving the origin relationship.
- **Delayed processing:** the consumer runs long after the producer span has ended; span links do not require the producer to still be active.

**A Trace ID is not an idempotency key.** One trace can contain multiple messages, and one message can be processed multiple times. Deduplication requires a message ID/business key, processing records, and properly designed transactions.

When a retry is emitted as a new message, define whether it retains the original message's creation context or attaches a context for the republish operation; do not force every message into a single ID just to make trace graphs look continuous.

## 12. Batching, fan-out, fan-in, and links

A batch can contain multiple messages from **different traces**:

~~~text
message A: creation context A ----\
                                   \
                                    > Batch Process span
                                   /
message B: creation context B ----/
~~~

A span can have only **one parent**, but it can have many **links**. Therefore, using the first message's parent to represent the entire batch loses the remaining relationships.

A sensible workflow:

1. Extract the context **individually** for each message in the batch.
2. Obtain the valid `SpanContext` for each creation source.
3. Add links within SDK limits/capabilities and diagnostic value.
4. Attach attributes such as destination, messaging system, and message count when using appropriate instrumentation.
5. Process business data without accidentally mixing the trace contexts of two messages.
6. Verify the result in a tracing backend that supports displaying links.

**Fan-out:** one message delivered to multiple subscribers creates independent Process spans. They can all link to the creation context without needing parent relationships with each other.

**Fan-in:** multiple messages contribute to one result; an aggregating Process span can link to multiple sources. When creating a new outgoing message, choose its creation context by policy rather than overwriting all sources with just the first message's trace ID.

## 13. Messaging spans and the meaning of Receive and Process

OpenTelemetry semantic conventions distinguish several operation types:

| Operation | Meaning | Common SpanKind by convention |
| --- | --- | --- |
| **create** | Creating context for a message | PRODUCER |
| **send** | Sending a message or batch | PRODUCER if Send context is the creation context; otherwise may be CLIENT |
| **receive** | Actively pulling messages from a broker | CLIENT |
| **process** | Processing a message in a callback/handler | CONSUMER |
| **settle** | Ack, nack, reject, or settlement | CLIENT |

For example, a **poll** fetching 100 Kafka records might have a Receive span for the poll operation and multiple Process spans for the processed records, depending on instrumentation. An application developer is not required to create all of these manually.

**Do not start a Process span too early** when a library merely prefetches or caches messages before application code receives them for processing. Place spans at the actual boundary of the observed operation.

Ack/nack is a separate broker action; it can be represented by a settlement span. Ack status must not be inferred from successful propagation.

## 14. Trace context does not automatically appear in Java logs

Even after successful extraction, you might still see logs like:

~~~text
INFO event=message_processed messageId=msg-42
~~~

without a `traceId`. The reason is that **OpenTelemetry Context** and **SLF4J MDC / Logback layout** are not automatically the same thing.

To correlate logs and traces, configure the appropriate logging instrumentation/bridge or an encoder capable of reading trace/span context. An expected JSON log might look like:

~~~json
{
  "level": "INFO",
  "event": "message_processed",
  "messageId": "msg-42",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "aabbccddeeff0011"
}
~~~

This is **illustrative data**, not output from the example program. When a new Process span is created, `spanId` in the log should belong to the **Process span**, not the `parent-id` extracted from the header.

Implementation options depend on your stack:

- Compatible OpenTelemetry log instrumentation.
- Logback/Log4j 2 JSON encoder with trace/span context integration.
- Middleware that populates `traceId`/`spanId` into MDC according to policy and always cleans up the scope.
- Proper context propagation during async processing so the logger can see the current span.

If the Process span uses **links** instead of sharing the producer's trace, both sides do not necessarily share the same `traceId`. A tracing backend must support links to display this relationship; querying by a single `traceId` alone may miss linked spans.

## 15. Sampling, exporters, and missing trace data

`traceparent` has a sampled flag, but **it does not guarantee that all spans will be exported**. Common situations:

- The consumer extracted the context, but the tracer is a no-op.
- The sampler decided not to record span details.
- `SdkTracerProvider` was created **without an exporter/span processor**.
- The span was not ended, or the process exited before flushing.
- The collector hit a network error, its queue was full, or the backend failed to index the data.
- The UI only displays parent–child trees and does not support searching span links.
- The trace is too old and has aged out of retention.

Do not "fix" this by forcing the sampled flag on every message to `01`; that does not fix exporter configuration and can cause unintended tracing costs or overhead.

Verification checklist:

1. Do the headers contain a valid `traceparent`?
2. Does the extractor produce a valid remote `SpanContext`?
3. Does the tracer create the consumer span with the right parent/link?
4. Is the span recorded, ended, and exported?
5. Does the collector receive it?
6. Does the backend query and display the relationship correctly?

The example in section 7 only verifies **the first three steps and cleanup**, with no exporter or collector.

## 16. Security when receiving trace context from external messages

`traceparent` is **formatted metadata**, not a cryptographic signature proving identity. A partner can set any valid-looking trace ID, and a client can send a sampled flag trying to increase your service's tracing cost.

Protective principles:

1. Only trust metadata from sources/brokers/gateways verified as **trusted by policy**; a syntactically valid `traceparent` can still be forged by an external caller.
2. Never use `traceId`/`spanId` for authentication, authorization, or granting access to internal logs.
3. Use a standard propagator to validate format; headers with all-zero `trace-id` or `parent-id` are invalid.
4. Enforce limits on header size, header count, forwarded content, and tracing budgets.
5. Do not log raw untrusted headers when rejecting them; avoid log injection and secret exposure.
6. Do not put tokens, passwords, PII, or raw payloads into `baggage`/`tracestate`.
7. Define trust boundaries across tenants, partners, and internal systems.
8. Establish policies for malformed, missing, or duplicate headers; start a new context when needed instead of using corrupted IDs.
9. Do not treat an external sampled flag as a mandate requiring your system to store every trace.
10. Apply retention, access control, and data policies to trace and log storage.

Invalid example:

~~~text
traceparent: 00-00000000000000000000000000000000-0000000000000000-01
~~~

Both IDs are all zeros, so a standard extractor must not accept this as a valid remote parent. In the test, `invalidRejected=true` confirms this. When there is no valid context, the consumer can start a new root span or follow another defined policy, and must never "repair" invalid IDs through arbitrary string concatenation.

## 17. Performance, message size, and propagation overhead

For each message, propagation adds a few short headers. However, total overhead depends on:

- Broker limits on header count and metadata byte size.
- Long `baggage`/`tracestate` entries increasing payload size.
- Instrumentation creating spans on every send/receive/process.
- Trace sampling rates and exporter data volume.
- Buffers/queues in the SDK and collector.
- Very large batches with thousands of span links.
- JSON logs repeating `traceId`/`spanId` on every event.

Do not optimize by reusing the same trace ID across unrelated messages just to reduce cardinality. Unique IDs are essential for accurate tracing; if volume grows high, tune your sampler, attributes, links, and retention appropriately.

**Do not turn `traceId` into a metric label for each request/message.** Extremely high cardinality can explode time series in your metrics system; keep `traceId` in traces/logs for looking up specific events, and use lower-cardinality labels for metrics.

## 18. Troubleshooting and diagnostics table

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Producer has trace, consumer loses trace | Missing inject/extract or headers did not arrive | Check both ends |
| Header has `traceparent` but remote is invalid | Format, encoding, or all-zero IDs | Use a standard propagator, check policy |
| Consumer span has wrong parent | Context injected at the wrong time/span | Compare producer span ID and extracted parent |
| Consumer reuses producer span ID | Reused `Span` object or copied ID incorrectly | Create a new span for the new operation |
| Batch only links to the first message | Forced one parent for multiple sources | Add links for all sources |
| Consumer runs in HTTP span but loses HTTP relation | Used remote parent instead of ambient parent unintentionally | Keep ambient parent + link message origin |
| Retries create multiple spans that are hard to correlate | Creation context/metadata not preserved | Preserve message context and retry attributes |
| No `traceId` in Java logs | Missing MDC/encoder/instrumentation | Configure log correlation |
| Span exists locally but missing in backend | Sampling/exporter/collector/retention | Check each layer |
| Headers merged or duplicated | Adapters/intermediaries handle headers differently | Define policy and ownership |
| Scope leaks into subsequent message | Scope not closed on the right thread | Use `try-with-resources`/`finally` |
| Async worker does not see context | Context not transferred across thread boundary | Capture/attach `Scope` explicitly |
| Headers lost across broker hop | Adapter or proxy does not preserve metadata | Verify envelope contract |
| Duplicate spans | Both manual tracing and auto-instrumentation create spans | Avoid double instrumentation |
| Link exists but trace ID query misses it | Linked spans are in different traces | Use UI/queries that support span links |
| Baggage contains PII | Uncontrolled fields propagated | Use an allowlist and strip sensitive data |

### Step-by-step investigation order

1. Confirm a **valid producer span** exists at publish time.
2. Inspect headers before calling broker send.
3. Inspect raw headers received by the consumer in a test environment.
4. Confirm the extractor returns a valid remote `SpanContext`.
5. Check parent/link policy and `SpanKind`.
6. Check the current span inside the handler and scope cleanup.
7. For async code, verify Context propagation across executors/callbacks.
8. Check exporter/collector and sampling configuration.
9. Check whether the log encoder outputs `traceId`/`spanId` if needed.
10. For retries/batches/fan-out, verify message IDs, attempt counts, and span links.

Do not lump **propagation errors**, **span creation errors**, **exporter errors**, and **UI display issues** into a single "lost trace" bucket.

## 19. Pre-production test suite

| Scenario | Expected result to verify |
| --- | --- |
| Single normal message | `traceparent` is injected/extracted correctly |
| Single consumer parent–child (when design allows) | Same `traceId`, new span ID |
| Consumer using span link | Link points to message creation context |
| Missing header | No crash; selects a new context per policy |
| All-zero or malformed `traceparent` | Invalid remote context is rejected |
| Kafka/JMS/RabbitMQ headers | Encoded/decoded properly without loss |
| Two messages in a batch | Links to both appropriate sources |
| Fan-out to multiple consumers | Each consumer has an independent process span |
| Retry/redelivery | Separate attempt spans, no span reuse |
| Message sent to DLQ | Origin relationship preserved if contract allows |
| Handler exception | Scope still closes, span ends properly |
| Thread pool reuse | No stale current context on the next task |
| `CompletableFuture` or reactive hop | Context propagated/attached properly |
| Service with auto-instrumentation | No duplicate spans/headers from manual code |
| No exporter/unsampled | Correctly distinguishes propagation from export |
| Log correlation | `traceId`/`spanId` fields present when configured |
| Unsafe baggage | Does not leak across trust boundaries |
| End-to-end backend | Spans, links, and queries are visible |

Test with a **real broker and actual agent** after simulated-carrier unit tests. Especially for link semantics, do not compare `traceId` alone and conclude failure.

## 20. Self-check exercises

**Exercise 1.** Why isn't the producer JVM's OpenTelemetry Context automatically present in the consumer JVM?

**Answer:** Context/ThreadLocal belongs to a process and thread. The broker only transmits message data; for the consumer to restore the trace, metadata must be injected and extracted.

**Exercise 2.** In the `traceparent` header, is `parent-id` the ID of the span the consumer will create?

**Answer:** No. It represents the sender's span; the consumer creates a new span ID and uses the extracted one as its parent when using a parent–child design.

**Exercise 3.** A batch contains two messages with two different trace IDs. Can a single Process span have two parents?

**Answer:** No. A span can only have one parent; you can add **span links** to both creation contexts.

**Exercise 4.** The producer injected `traceparent` and the consumer extracted it properly, yet the logs have no `traceId`. Why?

**Answer:** Tracing context and logging MDC/encoders are separate mechanisms. You need logging instrumentation or an encoder to populate trace/span IDs into logs.

**Exercise 5.** A message is retried three times. Should you reuse the same `Span` object for all three attempts?

**Answer:** No. Each processing attempt is a separate execution and should have its own span; the spans can link to the same creation context.

**Exercise 6.** `traceparent` has sampled flag `01`, but the span does not appear in the backend. Is propagation broken?

**Answer:** Not necessarily. Sampler, SDK, exporter, collector, flush, and retention are also involved. The sampled bit does not guarantee export.

**Exercise 7.** The consumer Process span links to the producer span, but their `traceId` values differ. Is this a bug?

**Answer:** Not necessarily. Span links can connect two different traces; check the links in the backend.

**Exercise 8.** A message contains a valid `traceparent` sent by an external partner. Can `traceId` be used to authenticate the partner?

**Answer:** No. Tracing headers are not proof of identity. Authentication and authorization must use dedicated mechanisms.

## 21. Checklist for implementing message propagation

- [ ] Choose a shared context propagation standard (typically W3C Trace Context).
- [ ] Read/write `traceparent` and `tracestate` via message metadata.
- [ ] Implement a carrier adapter matching the broker's API and encoding.
- [ ] Never serialize raw Java `Span`/`Context` objects into the business payload.
- [ ] Choose the right creation context when publishing.
- [ ] Check existing auto-instrumentation before adding manual instrumentation.
- [ ] Follow messaging span semantics: links as the default; parent–child when appropriate.
- [ ] Handle batch/fan-in/fan-out using links as needed.
- [ ] Give each consumer processing attempt its own span.
- [ ] Attach/close `Scope` according to lifecycle, including on exceptions.
- [ ] Propagate `Context` across thread pools and async boundaries.
- [ ] Never use `traceId` as a message ID, idempotency key, or auth token.
- [ ] Never put secrets or PII into `baggage`/`tracestate`.
- [ ] Enforce policies for malformed/duplicate/untrusted headers and size limits.
- [ ] Verify sampler, SDK exporter, collector, and trace backend.
- [ ] Configure log correlation if you want `traceId`/`spanId` in Java logs.
- [ ] Test retries, DLQ, batching, fan-out, shutdown, and thread reuse.
- [ ] Confirm messages are actually published/acked; propagation does not alter business semantics.
- [ ] Verify span relationships or links in the final tracing backend.

## 22. References

- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`, `tracestate`, format, and validity rules.
- [OpenTelemetry Messaging Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/): message creation context, links, Create/Send/Receive/Process/Settle.
- [OpenTelemetry Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): passing context across service boundaries.
- [OpenTelemetry Java API](https://opentelemetry.io/docs/languages/java/api/): Tracer, Span, Context, and Scope.
- [W3C Baggage](https://www.w3.org/TR/baggage/): conventions for additional context fields.

**Conclusion:** Message propagation is **injecting context from the producer into message metadata, then extracting it on the consumer to establish accurate tracing relationships**. This is especially important when a broker decouples the timing, JVMs, and threads of processing steps. In Java, use the OpenTelemetry propagator and an appropriate adapter, **never manually construct `traceparent`**, choose **span links or parent–child according to messaging semantics**, clean up `Scope` properly, and verify the entire pipeline from headers to backend. Propagation makes causality observable; it does not replace idempotency, authorization, or message delivery guarantees.