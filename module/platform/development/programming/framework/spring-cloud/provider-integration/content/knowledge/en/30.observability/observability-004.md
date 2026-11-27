# Correlating traces across HTTP, queues, and background processing

## 1. Context and objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud** using the corresponding Spring Cloud libraries and SDKs. A real-world request rarely stops at a single HTTP controller: it may call an internal API, write to object storage, send a message, get picked up by a worker seconds later, and then access a database or another cloud service.

For example, a user submits a request to generate a document preview. The API validates the request, saves the file to Azure Blob Storage, sends a job to Azure Service Bus, and returns HTTP 202. Another worker receives the message, reads the file, generates a thumbnail in object storage, and updates status. If the worker fails, operations needs to know whether the original request, publish call, receive event, storage operations, and processing error belong together.

**Distributed tracing** solves this by propagating trace context across HTTP, message broker, and asynchronous thread boundaries. This lesson focuses on Spring Boot 3.5, Micrometer Tracing, and OpenTelemetry, while comparing context propagation across Amazon SQS, Azure Service Bus, and Google Cloud Pub/Sub.

After this lesson, you will be able to:

- Distinguish trace ID, span ID, correlation ID, and message ID.
- Configure Micrometer Tracing/OpenTelemetry in Spring Boot.
- Automatically propagate trace context across Spring Boot-configured HTTP clients.
- Attach W3C Trace Context to message metadata and restore context in consumers.
- Choose parent spans or span links for consumers, batches, and fan-out.
- Preserve trace context when switching threads or running background tasks.
- Enable appropriate instrumentation for the AWS SDK, Azure SDK, and Google Cloud Pub/Sub.
- Design sampling, baggage, logging, and safe end-to-end trace tests.

## 2. Traces, spans, and correlation IDs

A **trace** represents the complete journey of a unit of work across multiple components. A trace consists of multiple **spans**; each span describes an operation with start and end times, such as an HTTP request, sending a message, processing a message, or calling Blob Storage.

| Concept | Meaning | Example |
|---|---|---|
| Trace ID | Identifies one distributed journey | Preview creation request and downstream operations |
| Span ID | Identifies a single operation within a trace | Calling POST /jobs or reading a blob |
| Parent span | The span that directly spawned the current span | HTTP server span is parent of HTTP client span |
| Span link | Causal association with another span without forcing a parent relationship | Batch consumer linking to multiple producer spans |
| Correlation ID | Business key for finding related logs/events | requestId or jobId |
| Message ID | Broker-assigned message identifier | SQS message ID or Pub/Sub message ID |

Trace IDs and correlation IDs serve different purposes. Trace IDs serve technical observability; correlation IDs serve business lookups and can span multiple retries or multiple traces. Do not treat a correlation ID as a trace ID by inventing custom headers and bypassing tracing standards.

### 2.1. W3C Trace Context

W3C Trace Context standardizes how traces propagate over HTTP. Two key headers:

- **traceparent:** contains version, trace ID, parent span ID, and trace flags.
- **tracestate:** carries additional vendor/tracing-system state if present.

An illustrative traceparent value:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Do not parse this string manually with substring operations to construct spans. Use Micrometer/OpenTelemetry propagators to inject and extract; propagators handle validation, versioning, and missing or invalid context.

W3C Baggage is a separate mechanism for propagating key/value pairs across a trace. Baggage does not replace traceparent and is not a place to store credentials, tokens, or personal data.

## 3. HTTP → message broker → worker flow

A flow can be modeled as follows:

~~~mermaid
flowchart LR
    U[HTTP client] -->|traceparent| A[Spring Boot API]
    A -->|traceparent| S[Object Storage]
    A -->|message + trace context| Q[(Queue / Topic)]
    Q -->|message + trace context| W[Background worker]
    W -->|traceparent| S2[Object Storage]
    W --> D[(Database)]
    W -->|ack / complete| Q
~~~

Typical spans:

1. An HTTP server span starts when the API receives the request.
2. HTTP client spans describe downstream calls if the client is instrumented.
3. A producer span describes creating/sending the message.
4. A consumer receive/process span describes receiving and handling the message.
5. Client spans describe storage, database, or HTTP operations executed by the worker.
6. A settlement span or equivalent operation records ack/delete/complete on the message.

A trace stays connected only when context propagates across every boundary. Automatic instrumentation can create spans for HTTP or SDK calls, yet **cannot infer the business link between producer and consumer unless the message carries its creation context**.

## 4. Configuring Spring Boot 3.5 and Micrometer Tracing

Spring Boot 3.5 uses Micrometer Observation as a facade for metrics and traces. Basic Maven dependencies for OpenTelemetry and OTLP:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Let Spring Boot's BOM manage compatible versions; do not independently upgrade Micrometer or OpenTelemetry to versions outside the project's dependency management.

Example configuration:

~~~yaml
spring:
  application:
    name: document-api

management:
  tracing:
    sampling:
      probability: 0.1
    propagation:
      produce: W3C
      consume: W3C
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
      transport: http
      timeout: 10s
~~~

Explanation:

- `spring.application.name` helps the backend identify the service.
- `sampling.probability` is the fraction of new root traces sampled; Spring Boot defaults to 10%.
- `propagation.produce` defines the format the application writes into headers/metadata.
- `propagation.consume` defines the format(s) the application accepts when receiving context.
- The OTLP endpoint points to a collector or OTLP-capable backend.

If legacy services in the system use B3, configure consume to accept both W3C and B3 during migration while keeping produce standardized on W3C. Align formats across services and verify each runtime's actual configuration.

Spring Boot 3.5 can provide an OpenTelemetry bean when a tracing bridge and exporter are configured. In this lesson, the OpenTelemetry API is used in the adapter layer to inject/extract context across message carriers; for typical business instrumentation, prefer the Observation/Micrometer Tracing API.

## 5. Automatic trace propagation over HTTP

Spring Boot automatically instruments server-side HTTP requests when tracing is configured. For HTTP clients, use builders auto-configured by Spring Boot:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class DownstreamClientConfiguration {

    @Bean
    RestClient catalogClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.internal")
                .build();
    }
}
~~~

A Spring Boot-configured `RestClient.Builder` automatically propagates trace context. Similarly, use `RestTemplateBuilder` or `WebClient.Builder` injected from the Spring context.

If you instantiate an HTTP client directly via a constructor or an uninstrumented builder, `traceparent` may not be propagated. The trace then breaks at the HTTP call even though both services export traces normally.

### 5.1. Tracing across multiple HTTP services

When API A calls API B, client instrumentation creates a client span in the active trace and sends context over HTTP. API B reads that context to create a server span in the same trace. If B then calls C using a configured builder, the trace continues across C.

There is no need to manually add `traceparent` to requests when the HTTP client is already instrumented. Only write custom propagation for custom transports or libraries lacking auto-instrumentation.

## 6. Propagating trace context through message metadata

A message broker is not an ordinary HTTP server/client. Message data usually consists of a body plus a separate metadata area:

| Broker | Where trace context is stored |
|---|---|
| Amazon SQS | MessageAttributes |
| Azure Service Bus | ApplicationProperties; SDK may use Diagnostic-Id for W3C Trace Context |
| Google Cloud Pub/Sub | Message attributes |

A message can carry these keys:

~~~text
traceparent = 00-<trace-id>-<span-id>-01
tracestate  = <vendor-state if present>
baggage     = <only approved fields>
correlationId = job-42
~~~

Trace context must pass intact through brokers and intermediaries. If the system transforms or forwards messages, preserve tracing metadata per application rules. Do not overwrite the producer's context with a new trace at every hop if your goal is to track the same unit of work.

### 6.1. Why use a propagator?

A propagator converts the active context into carrier-compatible key/value pairs and restores context from the carrier when the consumer receives the message. Carriers can be a Map, SQS message attributes, Service Bus application properties, or Pub/Sub attributes.

Do not hardcode custom trace ID/span ID generation. Do not drop an arbitrary correlation ID into the `traceparent` field; the W3C format has strict structure and semantics.

## 7. Creating a producer span and injecting context

The following example uses the OpenTelemetry API and the OpenTelemetry bean configured by Spring Boot. The sender is passed as an adapter so the same logic works with SQS, Service Bus, or Pub/Sub.

~~~java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapPropagator;
import java.util.HashMap;
import java.util.Map;
import java.util.function.BiConsumer;
import org.springframework.stereotype.Component;

@Component
public class MessageTracePublisher {
    private final io.opentelemetry.api.trace.Tracer tracer;
    private final TextMapPropagator propagator;

    public MessageTracePublisher(OpenTelemetry openTelemetry) {
        this.tracer = openTelemetry.getTracer("provider-integration.messaging");
        this.propagator =
                openTelemetry.getPropagators().getTextMapPropagator();
    }

    public void publish(
            String body,
            BiConsumer<String, Map<String, String>> sender) {

        Span span = tracer.spanBuilder("send document-jobs")
                .setSpanKind(SpanKind.PRODUCER)
                .startSpan();

        Context messageContext = Context.current().with(span);
        Map<String, String> attributes = new HashMap<>();

        propagator.inject(
                messageContext,
                attributes,
                (carrier, key, value) -> carrier.put(key, value));

        try (Scope ignored = messageContext.makeCurrent()) {
            sender.accept(body, attributes);
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            span.end();
        }
    }
}
~~~

This example creates a producer span, injects trace context into a Map, and invokes the sender. Each provider adapter transfers those key/value pairs into actual broker metadata. In production, add useful, stable span attributes such as provider, system, destination, and operation following the semantic conventions used by your instrumentation.

A batch send can contain multiple messages. If each message has its own creation context, create a context per message and maintain per-message context mapping; do not assume the entire batch shares one parent.

## 8. Extracting context and creating a consumer span for a single message

When a consumer receives a message, obtain its metadata carrier and extract context before running the handler:

~~~java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapPropagator;
import java.util.Map;
import java.util.concurrent.Callable;
import org.springframework.stereotype.Component;

@Component
public class MessageTraceConsumer {
    private final io.opentelemetry.api.trace.Tracer tracer;
    private final TextMapPropagator propagator;

    public MessageTraceConsumer(OpenTelemetry openTelemetry) {
        this.tracer = openTelemetry.getTracer("provider-integration.messaging");
        this.propagator =
                openTelemetry.getPropagators().getTextMapPropagator();
    }

    public <T> T process(
            Map<String, String> attributes,
            Callable<T> handler) throws Exception {

        Context extracted = propagator.extract(
                Context.root(),
                attributes,
                (carrier, key) -> carrier.get(key));

        Span span = tracer.spanBuilder("process document-jobs")
                .setParent(extracted)
                .setSpanKind(SpanKind.CONSUMER)
                .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            return handler.call();
        } catch (Exception ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            span.end();
        }
    }
}
~~~

This is a straightforward approach when one message is handled independently and you want the message's creation context as its parent. When metadata lacks a valid trace context, the propagator returns a parentless context; the consumer starts a new trace rather than fabricating IDs.

In a real application, ack/delete/complete the message only after the handler completes according to broker semantics. The processing span should cover business logic; settlement operations can be instrumented separately or captured by SDK instrumentation.

## 9. Batches, fan-out, and span links

A consumer may receive multiple messages at once. A span has only one parent, so you cannot accurately represent a batch produced by multiple producer spans by picking a single message as its sole parent.

OpenTelemetry messaging conventions recommend using **span links** to associate a consumer span with each message's creation context, especially for batching and fan-out. For a single message, instrumentation may choose the message context as parent; keep one consistent rule across the system.

Example creating a consumer span for a batch and linking to each producer:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import java.util.List;
import java.util.Map;

public void processBatch(
        List<Map<String, String>> messageAttributes,
        Runnable handler) {

    var builder = tracer.spanBuilder("process document-jobs batch")
            .setNoParent()
            .setSpanKind(SpanKind.CONSUMER);

    for (Map<String, String> attributes : messageAttributes) {
        Context extracted = propagator.extract(
                Context.root(),
                attributes,
                (carrier, key) -> carrier.get(key));

        SpanContext messageContext =
                Span.fromContext(extracted).getSpanContext();
        if (messageContext.isValid()) {
            builder.addLink(messageContext);
        }
    }

    Span span = builder.startSpan();
    try (Scope ignored = span.makeCurrent()) {
        handler.run();
    } catch (RuntimeException ex) {
        span.recordException(ex);
        span.setStatus(StatusCode.ERROR);
        throw ex;
    } finally {
        span.end();
    }
}
~~~

When a producer publishes to a topic with multiple subscribers, each consumer can create its own span and link back to the same message creation context. This lets the trace backend depict fan-out relationships without forcing independent consumers into an artificial parent-child chain.

## 10. Preserving context in background tasks and across threads

Trace context in Spring applications is typically stored in an execution context/ThreadLocal. When code hops to another thread, context can be lost unless the executor propagates it.

### 10.1. Using ContextPropagatingTaskDecorator

For custom executors, attach `ContextPropagatingTaskDecorator`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BackgroundExecutorConfiguration {

    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("background-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

When using `@Async` or `AsyncTaskExecutor`, ensure the executor running the task is configured to propagate context. With Reactor, enable `spring.reactor.context-propagation=auto` to restore ThreadLocal context inside reactive operators.

Thread-level context propagation only handles boundaries **within the same process**. It does not replace injecting/extracting trace context across message brokers or HTTP.

### 10.2. Scheduled jobs without an HTTP parent

A scheduled task normally does not originate from an HTTP request. Create a new root span for each run, such as `generate-daily-report`, then create child spans for reading data, processing, and writing results.

If a background task is triggered by a message, continue from the extracted message context. If the task is triggered independently by a scheduler, never accidentally attach a stale request's trace just because a worker thread previously handled that request.

For jobs lasting several hours, avoid keeping a single span open across the entire lifecycle if doing so complicates export, sampling, or operations. Create spans per stage/batch and correlate them with job IDs, events, or appropriate span links.

## 11. Propagation differences across AWS, Azure, and Google Cloud

### 11.1. Amazon SQS and AWS SDK for Java 2.x

With SQS, message metadata lives in **MessageAttributes**. An adapter can write W3C `traceparent` and `tracestate` as String attributes:

~~~java
Map<String, MessageAttributeValue> attributes = new HashMap<>();
attributes.put(
        "traceparent",
        MessageAttributeValue.builder()
                .dataType("String")
                .stringValue(traceHeaders.get("traceparent"))
                .build());
~~~

On receipt, read back the message attributes and pass them to `propagator.extract`. If using SQS-capable instrumentation, verify whether it automatically injects/extracts message context in your exact version and configuration; do not assume the `SendMessage` SDK call span automatically links to the consumer.

AWS also has the `AWSTraceHeader` system attribute for the AWS X-Ray trace format. This is an AWS-specific mechanism, distinct from W3C `traceparent`. When a multi-cloud system uses OpenTelemetry, choose an explicit propagation format and avoid writing the same meaning into multiple headers without precedence rules.

For AWS SDK v2 calls such as S3, SQS, or DynamoDB, you can use the AWS Distro for OpenTelemetry (ADOT) Java agent or the OpenTelemetry Java agent to auto-instrument supported libraries. AWS X-Ray SDK/Daemon entered maintenance on 2026-02-25; for new systems, prioritize the OpenTelemetry/ADOT path.

### 11.2. Azure Service Bus and Azure SDK for Java

Azure Service Bus uses `ApplicationProperties` to carry message metadata. Service Bus distributed tracing builds on W3C Trace Context and uses the **Diagnostic-Id** property to carry trace parent information in SDK-supported flows.

If building your own adapter:

- Keep `Diagnostic-Id` formatted as W3C `traceparent` when integrating with the Service Bus contract.
- Do not overwrite values generated by the SDK if the SDK is auto-instrumenting messages.
- On message receipt, restore context from metadata before running the handler.
- Keep the business correlation ID in a separate property.

The Azure SDK for Java can emit spans via the Azure Monitor Java agent or OpenTelemetry Java agent. When using the OpenTelemetry SDK directly, the Azure SDK provides the `azure-core-tracing-opentelemetry` package; Microsoft's documentation marks this manual integration path as preview. For async calls, implicit context may no longer be present on callback threads; the Azure SDK supports explicit context passing via `com.azure.core.util.Context` using the `trace-context` key. Verify your exact client library version and API before adopting it.

### 11.3. Google Cloud Pub/Sub

Pub/Sub models traces across the message lifecycle from publish to acknowledge. The Java client supports enabling OpenTelemetry tracing on `Publisher` and `Subscriber`:

~~~java
Publisher publisher = Publisher.newBuilder(topicName)
        .setOpenTelemetry(openTelemetry)
        .setEnableOpenTelemetryTracing(true)
        .build();
~~~

~~~java
Subscriber subscriber = Subscriber.newBuilder(subscriptionName, receiver)
        .setOpenTelemetry(openTelemetry)
        .setEnableOpenTelemetryTracing(true)
        .build();
~~~

When tracing is enabled, the client library creates spans covering publish, batching, flow control, lease management, and subscribe. The client library also adds tracing-specific attributes prefixed with `googclient_` to propagate context between publisher and subscriber.

If the application needs to link an additional cross-provider business trace, define clearly how the application's standard W3C trace context combines with tracing attributes managed by the Pub/Sub SDK. Never delete or overwrite SDK-generated `googclient_` metadata.

## 12. Creating business spans with Micrometer Observation

Automatic instrumentation reveals how HTTP and SDK calls behave. To expose business stages such as validate document, generate preview, or reconcile job, create custom observations:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class PreviewService {
    private final ObservationRegistry observationRegistry;

    public PreviewService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void generatePreview(String documentType) {
        Observation.createNotStarted(
                        "document.preview.generate",
                        observationRegistry)
                .lowCardinalityKeyValue("document.type", documentType)
                .observe(() -> {
                    // Validate document, read source and generate preview.
                });
    }
}
~~~

Observation can produce both metrics and spans when `TracingObservationHandler` is configured. Use low-cardinality key/values for bounded values such as `document.type` or `provider`. If job IDs or message IDs are needed for diagnostics, put them in controlled span attributes/logs, never as metric labels.

Do not add `@Observed` or a custom Observation to a method already auto-instrumented with the same meaning, or traces may show duplicate nested spans or double-counted metrics. Only instrument business boundaries you genuinely need visibility into.

## 13. Baggage and business data

Baggage lets you propagate select metadata across a trace, such as tenant tier or workflow class. However, baggage is sent across multiple services and may appear in logs/trace backends.

Example configuration propagating only an approved field:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - workflow-class
      correlation:
        fields:
          - workflow-class
~~~

Only place values into baggage that:

- Have a small, controlled set of values.
- Contain no passwords, access tokens, SAS URLs, account keys, or secrets.
- Contain no personal data or unnecessary sensitive data.
- Are safe to share across every service participating in the trace.

Never put customer IDs, emails, phone numbers, or document contents into baggage just for debugging convenience. For traceable business lookups, use controlled correlation IDs and properly access-controlled log stores.

## 14. Sampling and trace export

Spring Boot 3.5 samples roughly 10% of new root traces by default. During local development, you can set probability to 1.0 to see every flow:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Do not leave 100% sampling enabled by default in high-traffic production. High sampling increases span volume, storage cost, and exporter/backend load. Guidelines:

- Use parent-based sampling so downstream services respect the parent trace's sampling decision.
- Keep sampling policies consistent across services participating in the same trace.
- Consider tail sampling in the OpenTelemetry Collector if you want to retain error or high-latency traces; the collector must receive all relevant spans before deciding.
- Monitor exporter queues, timeouts, dropped spans, and collector availability.
- Ensure the application flushes/shuts down telemetry cleanly so buffered spans are not lost.

Sampling does not replace metrics. Metrics must reflect all traffic; traces are typically sampled for detailed investigation.

## 15. Linking logs with traces

When Micrometer Tracing is configured, Spring Boot adds `traceId` and `spanId` to MDC so logs can be looked up in the trace backend.

Example Logback pattern:

~~~yaml
logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
~~~

A log entry may look like:

~~~text
[4bf92f3577b34da6a3ce929d0e0e4736,00f067aa0ba902b7] INFO PreviewWorker - Preview created
~~~

When processing a message, also log message ID, job ID, destination, and delivery attempt as structured fields. These values are helpful in logs, though they do not belong in high-cardinality metric labels.

Trace ID in logs finds the trace; correlation ID finds the job; message ID finds the specific delivery. Keep all three identifiers distinct to preserve traceability.

## 16. Security and trustworthiness of trace context

Trace context is observability metadata, **not proof of authentication or authorization**. Never use `traceparent`, `tracestate`, baggage, or correlation ID to decide whether a user may access a resource.

Protection guidelines:

- Never transmit secrets, access tokens, or SAS URLs inside baggage or message attributes.
- Allow only whitelisted baggage fields.
- Treat trace context arriving from the Internet or another tenant as untrusted input.
- Strip or start a new trace at trust boundaries if security policy requires it; document this behavior so operations understands why traces split.
- Never log full message payloads just to check context propagation.
- Restrict read access to the trace backend because span attributes may contain internal metadata.
- Never use caller-supplied message headers in place of an authenticated identity.

A broken trace does not make a request insecure; an unbroken trace does not prove authorization is right.

## 17. Testing traces end-to-end

Tests should verify trace IDs and span relationships, not just that the application returns HTTP 200.

| Scenario | Expected result |
|---|---|
| HTTP request enters Spring Boot | Server span and trace ID present |
| API calls downstream via RestClient.Builder | Client span exists in the same trace |
| API sends a message | Producer/send span exists and context is injected into metadata |
| Worker receives a single message | Consumer/process span links to producer context |
| Worker calls Blob/S3/GCS | Dependency span belongs to worker trace |
| Consumer processes a batch | Batch span links to each message's context |
| @Async hops threads | Trace/MDC context remains present in the task |
| Independent scheduled job | Each run starts a new root trace |
| Message lacks trace headers | Consumer starts a new trace without errors |
| Message contains malformed context | Propagator treats it as invalid context; handler can still run per policy |
| Handler throws an exception | Span is marked error and exception is recorded |
| Sampling drops a trace | Do not assume every request appears in the backend |

### 17.1. Unit testing inject/extract

You can test context inject and extract across a Map without a real broker:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TracePropagationTest {
    @Test
    void preservesTraceIdAcrossMessageCarrier() {
        SdkTracerProvider tracerProvider =
                SdkTracerProvider.builder().build();
        var openTelemetry = OpenTelemetrySdk.builder()
                .setTracerProvider(tracerProvider)
                .setPropagators(ContextPropagators.create(
                        W3CTraceContextPropagator.getInstance()))
                .build();

        try {
            var tracer = openTelemetry.getTracer("test");
            var propagator =
                    openTelemetry.getPropagators().getTextMapPropagator();

            Span producer = tracer.spanBuilder("send")
                    .setSpanKind(SpanKind.PRODUCER)
                    .startSpan();

            try {
                Map<String, String> carrier = new HashMap<>();
                propagator.inject(
                        Context.current().with(producer),
                        carrier,
                        (map, key, value) -> map.put(key, value));

                Context extracted = propagator.extract(
                        Context.root(),
                        carrier,
                        (map, key) -> map.get(key));

                var extractedSpan = Span.fromContext(extracted);
                assertTrue(extractedSpan.getSpanContext().isValid());
                assertEquals(
                        producer.getSpanContext().getTraceId(),
                        extractedSpan.getSpanContext().getTraceId());
            } finally {
                producer.end();
            }
        } finally {
            tracerProvider.close();
        }
    }
}
~~~

This example sets up a standalone test SDK with the W3C propagator; add `io.opentelemetry:opentelemetry-sdk` in test scope if the project does not already include it. This test verifies the carrier preserves the trace ID; integration tests still need to confirm the adapter writes the right keys/values into `MessageAttributes`, `ApplicationProperties`, or Pub/Sub attributes. When using Spring Boot Test, note that exporter/reporting components may not be auto-configured the same way as during normal application runs.

### 17.2. Integration testing with a broker

In a test environment:

1. Send an HTTP request with a known `traceparent`.
2. Run the API, producer, and consumer through a test broker.
3. Collect traces via OTLP/Zipkin/Cloud Trace.
4. Verify spans share the expected trace ID and links/parents.
5. Trigger an error in the handler to verify exception recording and error status.
6. Run batch/fan-out scenarios to confirm multiple producer contexts are not forced into a single parent.

For AWS, use an SQS test queue and inspect message attributes; for Azure, use a test Service Bus namespace and `ApplicationProperties`; for Google Cloud, use a test topic/subscription with Pub/Sub OpenTelemetry tracing enabled. Do not test propagation with a mock Map and conclude that the SDK/broker preserves metadata properly.

## 18. Common pitfalls and fixes

| Symptom | Common cause | Fix |
|---|---|---|
| HTTP request has a trace but downstream does not | HTTP client built without Spring Boot auto-configured builder | Use `RestTemplateBuilder`, `RestClient.Builder`, or `WebClient.Builder` from context |
| Producer and consumer have different trace IDs | Message omits trace context or consumer fails to extract | Inspect `MessageAttributes`/`ApplicationProperties`/Pub/Sub attributes |
| Consumer span attaches to an unrelated trace | Using the running thread's context instead of message context | Extract context from the message itself; use links for batch/fan-out |
| Trace lost across `@Async` | Executor does not propagate Observation context | Register `ContextPropagatingTaskDecorator` |
| Reactive pipeline loses trace | ThreadLocal context not restored in Reactor | Configure `spring.reactor.context-propagation=auto` |
| Azure SDK span splits from app span during async | Implicit context does not follow callback threads | Use a supported agent or pass explicit trace context per Azure SDK |
| Pub/Sub shows SDK spans but lacks business spans | Client instrumentation only covers transport/lifecycle | Add business Observations and correlation metadata |
| AWS SQS trace does not connect to consumer | SDK call span exists but message attributes lack context | Verify SQS message attribute propagation and agent support |
| Traces missing from backend | Sampling dropped them, wrong exporter endpoint, or no flush on shutdown | Check sampling, OTLP endpoint, exporter queue, and shutdown |
| Too many spans for one operation | Auto instrumentation and manual instrumentation overlap | Keep only one instrumentation per boundary |
| High trace backend cost | 100% sampling, overly granular spans, or huge payload attributes | Lower sampling, filter spans, and cap attributes |
| Traces contain sensitive info | Arbitrary baggage/span attributes added | Whitelist fields and redact at collector/backend |

## 19. Hands-on exercises and self-check questions

**Scenario A — HTTP to SQS:** An API receives a request, saves a file to S3, and sends a message to SQS. Sketch the trace including server span, S3 client span, producer span, and consumer span; identify which metadata must be placed in SQS `MessageAttributes`.

**Scenario B — Azure Service Bus:** Producer and worker use Azure SDK for Java. Verify `Diagnostic-Id` per W3C Trace Context, inspect `ApplicationProperties`, and preserve context when the worker switches threads.

**Scenario C — Pub/Sub fan-out:** One message is published to a topic with two subscriptions. Design consumer spans with links back to the message creation context and explain why a single consumer span should not act as parent for both independent workers.

**Scenario D — `@Async` losing trace:** A controller creates a job and calls a service via `@Async`. Logs inside the task lack `traceId`. Inspect the executor and configure `ContextPropagatingTaskDecorator`.

**Scenario E — Scheduled report:** A report runs at midnight without originating from an HTTP request. Create a root span per execution and child spans for reading data, processing, and writing results.

**Scenario F — Unsafe baggage:** A service puts user emails and access tokens into baggage for debugging convenience. Remove sensitive data, choose an appropriate correlation ID, and define which fields are allowed to propagate.

**Scenario G — Sampling:** The producer's trace is sampled, yet the consumer exports no spans. Check parent-based sampling, context injection/extraction, and exporter settings before raising sampling to 100%.

### Self-check questions

1. **How does a trace ID differ from a span ID?** Trace ID identifies the entire journey; span ID identifies a single operation within that journey.
2. **Does a correlation ID replace a trace ID?** No; correlation ID is a business identifier, whereas trace ID is an observability identifier.
3. **Which headers carry HTTP trace context?** W3C Trace Context uses `traceparent` and optionally `tracestate`.
4. **Why must the producer inject context into the message?** The consumer cannot link back to the producer unless the message carries its creation context.
5. **When should span links be used?** Batches, fan-out, or whenever a consumer span has multiple causal sources.
6. **How does Spring Boot propagate traces via `RestClient`?** By using the auto-configured `RestClient.Builder` from the Spring context.
7. **Where does SQS store context?** In `MessageAttributes`, according to the chosen adapter and propagation format.
8. **Which tracing property does Azure Service Bus use?** `Diagnostic-Id` per W3C Trace Context in SDK-supported flows.
9. **Does Pub/Sub Java have built-in tracing?** Yes; configure OpenTelemetry on `Publisher`/`Subscriber` and enable `enableOpenTelemetryTracing`.
10. **Why propagate context across threads?** If the executor does not propagate context, spans/logs in background tasks can detach from the original trace.
11. **Should baggage hold tokens or PII?** No; propagate only whitelisted, non-sensitive fields.
12. **Should 100% sampling be enabled by default in production?** No; balance visibility, cost, and backend load.

## 20. Summary

To correlate traces across HTTP, queues, and background processing, applications must propagate **trace context** across every boundary. Spring Boot 3.5 and Micrometer Tracing auto-instrument HTTP requests and HTTP clients built from auto-configured builders. For message brokers, producers must inject context into metadata, and consumers must extract context before running handlers.

AWS SQS uses `MessageAttributes`; Azure Service Bus supports `Diagnostic-Id` per W3C Trace Context; Google Cloud Pub/Sub includes built-in OpenTelemetry tracing and client-library tracing metadata. For batches and fan-out, span links usually represent causality more accurately than a single parent-child edge. Across threads, use context propagation; for independent schedulers, start a new root trace.

Keep baggage minimal, never use trace context for authorization, choose appropriate sampling, and correlate logs via `traceId`/`spanId`. Combine provider auto-instrumentation with business spans, test through real brokers, and inspect end-to-end traces to spot breaks in distributed flows.

### Official references

- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [Spring Boot 3.5 — Observability and Context Propagation](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry — Messaging Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/)
- [OpenTelemetry — Java Instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/)
- [AWS — Migrating Java applications to OpenTelemetry](https://docs.aws.amazon.com/xray/latest/devguide/xray-migration-opentelemetry.html)
- [AWS — OpenTelemetry compatibility considerations for AWS](https://opentelemetry.io/docs/specs/semconv/non-normative/compatibility/aws/)
- [Microsoft Learn — Configure tracing in Azure SDK for Java](https://learn.microsoft.com/azure/developer/java/sdk/tracing)
- [Microsoft Learn — Distributed tracing through Azure Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-end-to-end-tracing)
- [Google Cloud — Pub/Sub OpenTelemetry tracing](https://docs.cloud.google.com/pubsub/docs/open-telemetry-tracing)
