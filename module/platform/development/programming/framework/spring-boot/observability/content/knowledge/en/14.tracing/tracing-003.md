# Trace ID in Spring Boot: Linking a Request Across Services

In the **Tracing** chapter of the **SPRING_BOOT_OBSERVABILITY** module, a **Trace ID** is the identifier used to link processing steps belonging to the same distributed trace. When a request travels from an API Gateway to an order service, a payment service, and a database, we do not want to manually hunt through separate log files by approximate timestamps. A properly propagated Trace ID lets us locate spans from the same trace, place them on a timeline, and correlate logs to identify which step failed or slowed down.

Spring Boot can integrate **Micrometer Observation** with Micrometer Tracing, a tracing bridge, context propagation, and an exporter to produce distributed traces. Alongside metrics and logs, the Trace ID is a crucial link for incident investigation, yet **a Trace ID does not replace metrics, does not by itself explain the root cause of an error, and does not guarantee the trace was exported**.

After this lesson, you should be able to distinguish a Trace ID from a Span ID and a request ID, understand W3C Trace Context, inspect Trace IDs in logs/traces, recognize propagation loss across async or inter-service calls, and avoid putting Trace IDs into high-cardinality metric tags.

## 1. What Are Trace, Span, and Trace ID?

A **trace** represents a chain or graph of related operations within a distributed transaction. Each **span** is a unit of work with start/end timestamps, metadata, and potentially a parent–child relationship with another span. **Trace ID** identifies the trace those spans belong to; **Span ID** identifies a specific span.

Example of an order confirmation request:

```text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736

API service
  Span A: POST /orders/confirm              [spanId=a111111111111111]
    |
    +--> Span B: order.confirm               [spanId=b222222222222222]
           |
           +--> Span C: inventory.reserve    [spanId=c333333333333333]
           |       |
           |       +--> Span D: DB call      [spanId=d444444444444444]
           |
           +--> Span E: POST payment-service [spanId=e555555555555555]
                    |
                    +--> Span F: authorize   [spanId=f666666666666666]

All spans above share the same Trace ID, while each span has its own Span ID.
```

The IDs in the diagram are illustrative examples, not actual captured output from a system.

| Concept | Scope | What Is It Used For? |
| --- | --- | --- |
| **Trace ID** | An entire trace; may span multiple services/processes | Locating and linking spans/logs of the same distributed transaction |
| **Span ID** | A single span within a trace | Identifying a specific operation and supporting parent–child relationships |
| **Parent Span ID** | Hierarchy within the span tree | Knowing which span is the parent of the current span |
| **Custom Request ID / Correlation ID** | Per application/gateway convention | Tracking a request or business workflow; does not implicitly equal Trace ID |
| **Business ID** | Domain entity such as order/payment | Querying business state; should not be treated as a trace ID |

Key point: **two spans having the same Trace ID does not mean they are the same span**, and two HTTP requests involved in a workflow do not necessarily share a Trace ID if the workflow creates a new trace by design. To connect a long-running chain across multiple traces, you may need message metadata, span links, or separately managed business correlation.

## 2. Shape of Trace ID and Span ID in W3C Trace Context

In the **W3C Trace Context** standard, a Trace ID (`trace-id`) is **16 bytes = 32 hexadecimal characters**, while a Parent ID (the ID of the span declared in the header) is **8 bytes = 16 hexadecimal characters**. All-zero identifiers are invalid in this format. Example:

```text
trace-id:  4bf92f3577b34da6a3ce929d0e0e4736   (32 hex)
span-id:   00f067aa0ba902b7                   (16 hex)
```

When calling another service, the HTTP `traceparent` header has the form:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^ ^^
             |           trace-id                   parent-id       flags
             version
```

In version `00` format:

- **`00`**: version of the `traceparent` format.
- **`4bf92f...`**: Trace ID used to link spans belonging to the same trace.
- **`00f067...`**: ID of the span **representing the sender side** in the propagated context; the receiving span can be created with a new Span ID using this as its parent.
- **`01`**: trace flags with the sampled bit set in this example; `00` typically indicates the sampled bit is unset. Other flag bits should not be interpreted arbitrarily.

The `tracestate` header can carry vendor-specific extended tracing state. **`tracestate` is not a Trace ID** and should not be used to transport business payloads. **Baggage** is another mechanism for propagating key-value pairs with context; baggage carries risks around header size and privacy.

A W3C Trace ID has a fixed length, though historical conventions for length or formatting may appear across different backends/bridges. Never concatenate, truncate, or regenerate Trace IDs manually just to make the UI look "uniform". Use standard tracers/propagators instead of string-manipulating headers yourself.

## 3. Through Which Steps Is a Trace ID Created and Propagated?

In a Spring Boot application configured with tracing instrumentation, the typical flow is:

1. **Receive request:** HTTP server instrumentation reads trace context from valid headers (if present); if no suitable context exists, the tracer can start a new trace.
2. **Create spans in-process:** an HTTP server span, business observation, or database/client span can share the Trace ID while each has its own Span ID.
3. **Call downstream:** HTTP client instrumentation injects tracing context into the outbound request via a propagator; downstream continues the trace when it extracts the context properly.
4. **Write logs:** when log correlation is configured, the MDC/logging pipeline can attach the active `traceId`/`spanId`.
5. **Export trace:** the exporter sends collected spans to the tracing backend according to sampling, SDK, and pipeline configuration.

```text
Client
  |
  | traceparent (if the client already has a tracing context)
  v
orders-service                    payment-service
  |                                      ^
  | HTTP SERVER SPAN                     |
  | traceId=T                            |
  | spanId=A                             |
  |                                      |
  +-- order.confirm                      |
  |    traceId=T, spanId=B                |
  |                                      |
  +-- HTTP client span ------------------+
       traceId=T, spanId=C       traceparent
                                    |
                                    v
                             HTTP SERVER SPAN
                             traceId=T, spanId=D
```

Each step can be affected by instrumentation, propagator, trust boundaries, thread context, and sampling. If a service calls downstream using an uninstrumented HTTP client or strips headers, downstream may start **a new Trace ID**, splitting the trace.

**Propagation differs from export.** Propagation keeps participating services on the same context; export makes spans visible in the backend. Propagation may work while the exporter fails or the sampler drops spans, leaving no complete trace on the dashboard.

## 4. Setting Up Micrometer Tracing with Spring Boot

In Spring Boot applications using Actuator and Micrometer Tracing, you need a **tracing bridge** (such as the OpenTelemetry bridge or Brave bridge) together with a compatible exporter/backend. Maven example for an OpenTelemetry/OTLP architecture (dependency versions managed by the appropriate Spring Boot BOM):

```xml
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
```

This is a **reference option for Spring Boot/Micrometer generations supporting these dependencies**, not a requirement to use both the OpenTelemetry bridge and Brave bridge simultaneously. Newer Spring Boot versions may have different starters or tracing auto-configuration; verify your actual project version and keep dependencies consistent with the BOM. If choosing Brave/Zipkin, swap the bridge and exporter path accordingly instead of mixing two tracers unintentionally.

Example application configuration in a Spring Boot stack supporting these properties:

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
```

Explanation:

- `sampling.probability: 0.1` is an example of probabilistic sampling; it does not guarantee exactly **10% of every request group** or that a specific single request will always be traced.
- `management.otlp.tracing.endpoint` depends on the Spring Boot version and OTLP exporter; `/v1/traces` is commonly used with OTLP/HTTP on port 4318. If the exporter uses gRPC or custom settings, the endpoint/protocol will differ.
- `localhost` only makes sense when the collector/backend runs in the same network namespace as the application. In Docker/Kubernetes, `localhost` usually points to the running container/pod itself, not automatically to a collector on another host.
- Seeing traces in the backend requires a receiver, exporter, network connectivity, and appropriate ingest policies. Declaring properties or creating spans alone does not prove traces were exported.

**Before testing sampling**, verify dependencies, tracing configuration, service name, propagation format, log correlation, and an operational exporter on your specific version. Never hardcode trace/span IDs or manually inject `traceparent` in controllers as a workaround for missing instrumentation.

## 5. Inspecting Trace ID in Java Code

Micrometer Tracing provides `Tracer` to inspect the active span. When a method runs within an HTTP server tracing context or a custom observation with a tracing handler, you can read the current span's Trace ID.

```java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class TraceContextReader {
    private static final Logger log =
            LoggerFactory.getLogger(TraceContextReader.class);

    private final Tracer tracer;

    public TraceContextReader(Tracer tracer) {
        this.tracer = tracer;
    }

    public void logCurrentTrace() {
        Span span = tracer.currentSpan();
        if (span == null) {
            log.info("No active tracing span on this execution context");
            return;
        }

        String traceId = span.context().traceId();
        String spanId = span.context().spanId();
        log.info("Working in traceId={} spanId={}", traceId, spanId);
    }
}
```

Things to understand:

- `tracer.currentSpan()` can return `null` if no span is active; never assume every invocation has a trace.
- Trace ID identifies the **current trace**, not the user or order. Unless manual logging is required, prefer framework-configured **MDC/log correlation** to avoid redundant output.
- A span appears in the backend only with proper tracing infrastructure, sampling decisions, and successful export. Reading a Trace ID in the JVM **is not proof the backend holds the trace**.

### Custom Observation Creating a Business Boundary

Example where an order confirmation operation needs visibility between HTTP server and HTTP client spans:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationService {
    private final ObservationRegistry registry;
    private final TraceContextReader traceContextReader;

    public OrderConfirmationService(
            ObservationRegistry registry,
            TraceContextReader traceContextReader) {
        this.registry = registry;
        this.traceContextReader = traceContextReader;
    }

    public void confirm(Runnable businessAction) {
        Observation.createNotStarted("order.confirm", registry)
                .lowCardinalityKeyValue("operation", "confirm")
                .observe(() -> {
                    traceContextReader.logCurrentTrace();
                    businessAction.run();
                });
    }
}
```

`Observation.observe(...)` manages the observation lifecycle of a synchronous block. If the registry has a tracing handler, the custom observation **can create a child span** sharing the parent request's Trace ID with its own Span ID. Without a bridge/tracing handler, the observation can still operate without producing a tracing span. When adding an observation, measure **a valuable business boundary**, avoiding duplicating the exact same HTTP/DB call that is already instrumented.

To record outcome/error, use low-cardinality tags with bounded value sets such as `result=success/declined/error`; never attach `traceId` as a metric tag. Micrometer Observation provides APIs to record errors on exceptions; business code must still handle/propagate exceptions according to its normal contract.

## 6. Log Correlation: Finding Logs with the Same Trace ID

One of the most practical benefits of Trace IDs is correlating logs across multiple services. When Micrometer Tracing and MDC/logging integration are configured, log events can include the active `traceId` and `spanId`.

Two hypothetical log lines:

```text
2026-11-22 10:15:02 INFO  orders-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7 Order confirmation started
2026-11-22 10:15:02 WARN  payment-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=1c42dd674d23ab12 Payment provider timed out
```

Both lines share the **same Trace ID** but have different Span IDs. An operator can search the Trace ID in the log backend, open the corresponding trace in the tracing backend, and inspect step ordering.

In several Spring Boot versions, MDC trace/span IDs are added to the log correlation pattern automatically when tracing is properly configured. If using a custom JSON encoder or Logback pattern, verify exactly how MDC fields are emitted and which key names your stack uses. Do not assume every encoder prints `traceId` automatically.

Illustrative Logback layout example (only applies if the app actually uses a pattern encoder and matching MDC keys):

```text
%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] traceId=%X{traceId:-} spanId=%X{spanId:-} %logger - %msg%n
```

Never log **entire HTTP headers** just to capture trace context: headers may contain tokens, cookies, or sensitive baggage. While a Trace ID itself is not a password, it can act as a query key to internal operational records; manage log/trace backend access controls appropriately.

**When logs have a Trace ID but the backend has no trace:** the trace may have been dropped by sampling, exporter errors, ingestion failures, or retention expiry. Do not conclude the Trace ID in logs is invalid solely because no span appears in the backend.

## 7. Propagation Over HTTP: Preserving Trace ID, Creating a New Span

When service A calls service B using an instrumented HTTP client, tracing context can be injected into the outgoing request. Service B extracts the context and creates a child server span. Under W3C Trace Context, both services share the same Trace ID if propagation succeeds.

```text
orders-service                       payment-service
   |
   | traceId=T
   | spanId=CLIENT_SPAN
   |
   +---- HTTP request ------------------------>
           traceparent: 00-T-CLIENT_SPAN-01
                                        |
                                        v
                               traceId=T
                               spanId=SERVER_SPAN_NEW
                               parentSpanId=CLIENT_SPAN
```

Symbols `T` and `CLIENT_SPAN` in the diagram are conceptual variables; they are **not** literal header values sent over the wire. On the network, `trace-id` and `parent-id` must conform to W3C hexadecimal format as shown in Section 2.

Common causes of split traces:

1. The HTTP client lacks appropriate instrumentation for `RestClient`, `RestTemplate`, `WebClient`, or the library in use.
2. Creating clients manually or bypassing observation-integrated bean builders, preventing tracing headers from being injected.
3. A gateway/proxy or security filter stripping or overwriting `traceparent`.
4. Both sides using incompatible propagators/formats or a trust boundary policy intentionally starting a new trace.
5. Downstream receiving context but failing to open a proper scope for asynchronous processing.

**Never extract a Trace ID from headers and stuff it into a static variable or arbitrary ThreadLocal yourself.** Micrometer/OTel/Brave tracers and propagators must keep Trace ID, Span ID, sampled flag, parent relationships, and lifecycle synchronized. Doing this manually easily produces invalid traces or breaks parent–child linkage.

## 8. Propagation Across Threads, Async, and Message Consumers

Things get trickier when work is handed off to an executor, `@Async`, `CompletableFuture`, a message broker, or a scheduler. A thread does not automatically inherit another thread's tracing context; hence **calling `tracer.currentSpan()` on a worker thread may return null**.

Anti-pattern example:

```java
// If the executor does not propagate context, the trace in the new thread may be lost.
CompletableFuture.runAsync(() -> {
    // Background work may no longer have the parent request's currentSpan.
    processOrder();
});
```

With Spring Framework's `ContextPropagatingTaskDecorator` (e.g., Spring Framework 6.1+), you can configure an explicit `ThreadPoolTaskExecutor` to capture/restore context at task submission:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class OrderAsyncConfiguration {

    @Bean(name = "orderTaskExecutor")
    ThreadPoolTaskExecutor orderTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("order-worker-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

This demonstrates an **explicitly configured executor**; it does not mean every default `CompletableFuture.runAsync()` call will automatically use that executor. For propagation to take effect, tasks must actually be submitted to the configured executor (or via `@Async("orderTaskExecutor")` as supported by Spring), with the Micrometer Context Propagation dependency and corresponding tracing integration present.

With messaging, verify that producers inject trace context into message headers and consumers extract/open scope before processing. A step executing hours later might intentionally start a new trace with a **span link** to the previous trace, depending on queue design and transaction semantics; not every case requires keeping one trace alive indefinitely.

## 9. How Does Sampling Affect Trace IDs?

**Sampling** controls which traces/spans are recorded or exported to manage tracing cost. It is distinct from creating and propagating trace context.

| Scenario | Trace ID in Process/Logs | Spans Exported to Backend |
| --- | --- | --- |
| Trace sampled, exporter healthy | Usually present while span context is active | Exported and searchable |
| Trace not sampled | Context/Trace ID may still exist for propagation and log correlation, depending on implementation | Typically no corresponding spans in backend |
| Exporter failing/network broken | Context can still exist inside the application | Lost or delayed ingestion |
| No tracing bridge/handler | Custom Observations can still produce metrics | No tracing spans from those observations |
| Context propagation lost | Threads/downstream may have no span or start a new trace | Trace breaks or splits into multiple traces |

For example, `sampling.probability: 0.1` does not guarantee keeping "exactly 1 out of every 10 requests". Sampling decisions can depend on parent context, tracer/sampler, and service config. When you need to ensure failing transactions are captured for investigation, consider appropriate strategies such as head/tail sampling, error-based policies, and collector/backend capacity; simply raising one probability is not always enough.

Metrics from Micrometer Observation may still be recorded by metric handlers even when a trace is sampled out. **Never use Trace ID as a tag on a Counter/Timer** to "join" metrics with traces: Trace IDs have huge cardinality and explode time-series counts. Use metrics with low-cardinality tags to detect issues, then pull logs/traces in that time window for detailed investigation.

## 10. Is a Trace ID Sensitive Information?

A Trace ID is not a credential or authentication token, and by itself does not prove a user's identity. However, if a trace/log backend allows querying by ID, exposing a Trace ID can let someone **reference operational records**. Distinguish carefully:

- **Do not use Trace ID for authentication or authorization.** Knowing an ID does not grant permission to read associated data.
- **Control access to log/trace backends.** Data inside spans/logs can reveal endpoint names, services, or internal diagnostics.
- **Never write PII/secrets into span attributes or baggage.** Even though a Trace ID is not personal data, data attached to it still can be sensitive.
- **Do not blindly trust every incoming trace context.** At untrusted boundaries, enforce validators, propagators, and resource/sampling protection policies; avoid letting clients force excessive telemetry or corrupt correlation.
- **Do not use Trace ID in place of order ID.** An order may be touched by multiple traces (creation request, retries, batch reconciliation). Use dedicated business correlation when querying an order's lifecycle.

Regarding cardinality, Trace IDs are nearly unique per trace. Attaching `traceId` as a metric label can generate millions of series from a single metric name. Tracing/logging systems are built to store controlled high-cardinality references.

## 11. Investigation Workflow: "Trace Lost Between Two Services"

Suppose an application receives `POST /checkout` and logs:

```text
orders-service  traceId=4bf92f3577b34da6a3ce929d0e0e4736  Payment request started
payment-service traceId=9d4c12e8bc974f32a1a5de33e478c001  Payment request failed
```

Two different Trace IDs do not prove the payment service wasn't called. They are a **signal** that the two logs may belong to different traces, propagation broke, or a service intentionally started a new trace. Investigate in order:

1. **Match the transaction:** confirm the logs truly belong to the same call using timestamps, endpoints, status codes, and permitted business correlation. Do not rely solely on close timestamps.
2. **Inspect the outgoing client:** does `orders-service` have HTTP client observation/instrumentation and a properly configured propagator?
3. **Check headers across boundaries:** in a safe test environment, confirm `traceparent` is injected/extracted validly; avoid logging headers containing secrets.
4. **Inspect gateways/service meshes:** is a proxy stripping, transforming, or regenerating trace context? Is there an intentional policy to start a new trace at a trust boundary?
5. **Check thread/message context:** did a service offload work to an executor/queue without propagation?
6. **Check sampling/exporters:** propagation may have worked at some steps while spans were not exported; do not conclude from a single trace viewer alone.
7. **Check Trace ID field names in logs:** does the JSON encoder read the right MDC key/active scope? Are logs emitted **outside the scope** after the task finished?
8. **Cross-check metrics:** when payment provider timeouts spike, check error rates, HTTP/client latency, and pool saturation to confirm the issue actually affects multiple requests.

### Quick Diagnostic Table

| Symptom | Possibilities to Check | Verification Step |
| --- | --- | --- |
| Same Trace ID across services, different Span IDs | Propagation and span creation likely working | Open the trace, inspect parent–child and timeline |
| Service A log has a Trace ID, service B has a new ID | Header propagation, gateway, async, trust boundary | Compare client instrumentation, propagator, and ingress |
| Same Trace ID but span B missing in backend | Sampling, exporter, collector, missing instrumentation | Check sampled flag, exporter, and SDK telemetry |
| `tracer.currentSpan() == null` on worker thread | No active scope or missing context propagation | Use a context-aware executor; check submission point |
| Trace has spans but logs lack Trace ID | MDC/correlation pattern or logging outside scope | Verify logging integration and lifecycle |
| Metrics show errors but no trace is found | Sampling or missing tracing path | Check sampling ratio, exporter; never tag metrics with traceId |
| One order ID linked to many Trace IDs | Multiple requests, retries, or async workflows | Use appropriate business correlation/links |

## 12. End-to-End Scenario Example

A system consists of `orders-service`, `inventory-service`, and `payment-service`. During peak hours, payment error rates jump from 0.1% to 3%. The operations team observes:

```text
Metrics:
  payment.authorize{provider="bank_a",outcome="error"} increases
  http.server.requests latency p95 increases

Logs:
  orders-service: "Payment call started" (traceId=T)
  payment-service: "Provider timeout"   (traceId=T)

Traces (a sampled request):
  POST /checkout              [traceId=T, spanId=A]
    order.confirm             [traceId=T, spanId=B]
      payment.authorize       [traceId=T, spanId=C]
        HTTP POST provider    [traceId=T, spanId=D, high duration]
```

Thanks to the **shared Trace ID**, the team can open a representative request's trace, identify the provider HTTP call as the slow step, and match it with logs describing timeouts. However, do not conclude from **a single trace** that every failing request shares the exact same error; metrics and backend aggregates reveal scope, rates, and trends. Even if sampling drops a specific failing transaction, logs can still assist diagnosis and metrics still cover overall traffic.

Method for combining signals:

1. **Metrics:** detect *when*, *how many*, and *which provider* is failing; use only bounded-cardinality tags.
2. **Traces:** reveal the *path* and *where time is spent* for recorded requests; Trace ID links the spans.
3. **Logs:** explain *error details* and business decisions; use Trace ID/Span ID to locate the exact context.
4. **Propagation and exporters:** ensure Trace ID continues across services, spans reach the backend when sampled, and data is not lost to misconfiguration or network issues.

## 13. Reinforcement Exercise

Consider these three hypothetical logs:

```text
10:00:00.100 orders-service   traceId=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa spanId=1111111111111111 Checkout started
10:00:00.220 inventory-service traceId=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa spanId=2222222222222222 Inventory reserved
10:00:00.450 payment-service   traceId=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb spanId=3333333333333333 Payment declined
```

Answer the questions:

1. Can we be certain all three logs belong to a single distributed trace?
2. Why do the first two logs have different Span IDs but the same Trace ID?
3. If `payment-service` actually handled a call from `orders-service`, list at least three reasons why its Trace ID differs.
4. Once you know the Trace ID of a slow request, why shouldn't you attach it as a tag on `http.server.requests`?
5. If a log contains a Trace ID but the tracing backend cannot find the trace, which layers should you inspect?

**Reference Answer:** The first two logs share a Trace ID and have distinct Span IDs, matching different steps within one trace; the `payment-service` log has a different Trace ID, so we cannot assert it belongs to the same trace without additional correlating evidence. Header propagation may have been lost, a service intentionally started a new trace, a thread/message transition failed to restore context, or the logs belong to separate transactions. Trace ID is a high-cardinality identifier, unsuitable as a metric label. When a trace is missing from the backend, inspect active spans, sampling, propagators, exporter/collector, and retention before concluding instrumentation is broken.

### Practice Checklist

| Step | Expectation |
| --- | --- |
| Call an HTTP endpoint with tracing instrumentation | Active context/span exists within the proper handling scope |
| Read `Tracer.currentSpan()` within that scope | Can retrieve Trace ID/Span ID; handles `null` safely |
| Call downstream via an instrumented HTTP client | Trace ID is preserved, child/parent spans match |
| Offload a task to a context-propagating executor | Context is restored on the worker, log correlation works |
| Send/receive messages with trace propagation | Producer/consumer handle headers per stack or use span links by design |
| Reduce sampling | Do not mistake missing backend spans for metric or business errors |
| Inspect logs | Trace/span correlation appears when logging integration works, without leaking secrets |
| Inspect metrics | Errors/latency are aggregated by provider/outcome, **without** attaching traceId to tags |

**Remember:** **Trace ID links spans and logs of the same trace**, while Span ID identifies individual operations. For Trace IDs to be useful in Spring Boot, you need a tracing bridge, propagation across HTTP/async/messaging, log correlation, and properly configured exporters/sampling. Metrics use low-cardinality tags to detect incidents; tracing and logs use Trace IDs for deep investigation—yet an ID appearing inside the app does not guarantee the data was stored in the tracing backend.
