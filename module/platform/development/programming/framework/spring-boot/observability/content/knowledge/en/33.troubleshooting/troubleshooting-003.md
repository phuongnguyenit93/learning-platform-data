# Lost Trace Context in Spring Boot

Trace context is lost when a downstream operation is no longer linked to the trace started upstream. In the trace backend, common symptoms include a span unexpectedly becoming a root span, the Trace ID changing between two services, logs missing `traceId`/`spanId`, or a trace containing only an HTTP server span without client/database/consumer spans. This issue fragments distributed traces and makes investigating latency, dependency failures, or asynchronous behavior much harder.

In the SPRING_BOOT_OBSERVABILITY module, trace context is the foundation connecting metrics, logs, and distributed tracing across HTTP, messaging, executors, and database calls. This lesson belongs to the Troubleshooting chapter and focuses on diagnosing lost trace context: recognizing symptoms, checking propagation headers, distinguishing context extraction issues from sampling, handling thread boundaries, Reactor and message headers, verifying instrumentation, writing integration tests, and establishing a runbook.

## Learning Objectives

1. Explain Trace ID, Span ID, parent relationship, and active context.
2. Recognize broken traces across HTTP, async executors, messaging, or reactive pipelines.
3. Inspect W3C Trace Context and B3 propagation headers.
4. Distinguish missing context injection/extraction from sampling or export drops.
5. Propagate context across `Executor`, `CompletableFuture`, and Spring `@Async`.
6. Handle context in Reactor and messaging consumers.
7. Verify JDBC/client instrumentation and logging correlation.
8. Write tests proving Trace ID/parent relationships across boundaries.
9. Investigate safely without logging or exposing sensitive data.

## 1. Trace Context and Propagation

Trace context is the metadata that allows a span to know which trace it belongs to and its relationship to its parent span. Key concepts:

- Trace ID: identifier for the entire distributed trace.
- Span ID: identifier for a single operation within the trace.
- Parent Span ID: the parent span of the current operation.
- Trace flags: flags, including the sampled bit in W3C Trace Context.
- Trace state: vendor-specific state carried along with the context.

~~~text
Trace A
  HTTP server span (traceId=T1, spanId=S1)
    └─ HTTP client span (traceId=T1, spanId=S2, parent=S1)
         └─ Remote server span (traceId=T1, spanId=S3, parent=S2)
~~~

When context is propagated properly, the downstream span keeps the same Trace ID and its parent points to the corresponding upstream span. A downstream operation may use a span link instead of a parent-child relationship in batch/async fan-in models; what matters is that the relationship is explicitly represented.

### 1.1. Active Context and Scope

The tracing SDK holds the current span in the execution context. When starting a child operation, instrumentation reads the current context to establish the parent relationship. The scope must be closed when the operation finishes so that the previous current context is restored.

If a scope is not closed, context can leak into the next operation on the same thread. If context is not activated on a worker thread, the downstream span may become a root span or fail to be created.

### 1.2. Context Propagation Is Not Log Correlation

MDC is a map for logging. Trace context is the context used by the tracing API/SDK to create spans and parent relationships. Copying `traceId`/`spanId` into MDC can make logs display correlation fields, but it does not create an active span or propagate parent context on its own.

## 2. Symptoms and Indicators

| Symptom | Possibilities to Check |
| --- | --- |
| Trace ID changes after an HTTP call | Client didn't inject header or server didn't extract |
| Downstream span becomes a root | No active context or parent was lost |
| Logs have `traceId` but backend has no child span | MDC still holds data while instrumentation/context didn't run, or sampling/export |
| Only HTTP server span is present | Client/JDBC instrumentation not enabled or context boundary lost |
| Async task creates a new trace | Executor doesn't propagate context or task creates a root span |
| Consumer doesn't link to producer trace | Message headers lack context or consumer doesn't extract |
| Reactor chain lacks parent | Context was read from `ThreadLocal` at the wrong time |
| Some spans disappear | Sampling, Collector routing, exporter drop, or late spans |

Do not conclude that context was lost solely because a trace is missing from the backend. The span might never have been created, might have been sampled out, dropped in the exporter/Collector, sent to another tenant, or queried with the wrong time range.

## 3. Inspecting W3C Trace Context Headers

W3C Trace Context typically uses:
- `traceparent`: version, trace ID, parent ID, and trace flags;
- `tracestate`: vendor-specific tracing state.

Example:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

The Trace ID in the header must be extracted downstream to continue the trace. The sampled flag is not the Trace ID and is not sole proof that the span exists in the backend.

### 3.1. Start at Ingress

Check the first request entering the application:
1. Did the caller send `traceparent` or a format supported by the system?
2. Did a gateway/proxy strip or modify the header?
3. Did server instrumentation extract using the right propagator?
4. Does the Trace ID in the server span match the trace context from the caller?

Do not dump all headers into application logs for debugging; headers can contain cookies, tokens, and personal data. Only log a correlation identifier processed according to policy if needed.

### 3.2. Header Format Mismatch

One service may emit W3C Trace Context while another is configured only for B3, or vice versa. When formats do not match, downstream may start a new trace. Check propagator configuration on both sides and at the gateway.

### 3.3. Multiple Propagation Formats

A system may support both W3C and B3 simultaneously during a migration period. Choose a primary format and avoid having conflicting headers. If `traceparent` and B3 headers appear together with different IDs, behavior depends on the propagator configuration and implementation.

## 4. Distinguishing Context Loss from Sampling/Export Loss

This is an important step so you do not fix propagation by mistake.

| Observation | Context Loss | Sampling/Export Loss |
| --- | --- | --- |
| Downstream Trace ID is different | Possible | Usually not if the trace stays linked |
| Child span exists in app/test exporter but not backend | No | Possible |
| Parent ID is wrong | Possible | Not necessarily |
| Collector reports refused/dropped spans | Not context loss | Yes |
| Sampling flag is unsampled | Does not prove context loss by itself | Possible |
| Logs have `traceId` but backend has no trace | Possible, or sampling/export | Needs multi-layer inspection |

Procedure:
1. Verify the current trace context immediately before the boundary.
2. Verify that header/message metadata is injected.
3. Verify that downstream extracts the same Trace ID.
4. Check whether the child span was created inside the process.
5. If the span was created properly, check the sampler, exporter, Collector, and backend.

## 5. Spring Boot and Micrometer Tracing Configuration

Spring Boot Actuator together with Micrometer Tracing can auto-configure tracing for supported integrations. Example dependencies with the OpenTelemetry bridge:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Keep dependency versions managed by the Spring Boot BOM. For HTTP client/server, JDBC, and messaging, corresponding integration/instrumentation is needed; the tracing bridge alone does not guarantee every library is instrumented.

Example sampling probability:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

In tests, 100% sampling can be used to avoid traces being dropped by head sampling. Do not default to 100% in production without accounting for volume.

### 5.1. Propagator Configuration

The Micrometer Tracing bridge and tracing implementation may support W3C/B3 propagators. Property names and default formats depend on the Spring Boot/Micrometer version. Check the reference documentation for your exact version and verify the headers actually emitted/read. Do not add guessed properties and assume propagation is enabled.

### 5.2. Instrumentation Boundaries

Check the required integrations:
- HTTP server instrumentation;
- HTTP client instrumentation;
- JDBC/DataSource instrumentation;
- messaging producer/consumer instrumentation;
- executor/async context propagation;
- Reactor context propagation.

A trace with only a server span may occur because downstream boundary instrumentation is not enabled, not necessarily because the W3C header was lost.

## 6. Context Lost Across HTTP Client/Server

When service A calls service B, client instrumentation must inject the current context into request headers; B's server instrumentation extracts the context before creating the server span.

~~~mermaid
sequenceDiagram
    participant Caller
    participant A as Service A
    participant Client as HTTP client instrumentation
    participant B as Service B
    Caller->>A: Request
    Note over A: Server span T1/S1
    A->>Client: Call B under active span
    Client->>B: HTTP request + traceparent
    Note over B: Extract T1/S2 as remote parent
    B-->>A: Response
    A-->>Caller: Response
~~~

### 6.1. Use an Instrumented HTTP Client

Use a Spring Boot-managed `RestClient`, `WebClient`, or an HTTP client integration compatible with your version and tracing setup. An HTTP client instantiated manually outside the application context may not receive observation/tracing customizers.

### 6.2. Check Request Interceptors

If using a custom interceptor, do not overwrite `traceparent` with a self-generated Trace ID. Let tracing instrumentation inject headers. If a gateway modifies headers, check propagation configuration and header allowlists at the gateway.

### 6.3. Check Server Extraction

Service B needs server instrumentation supporting the framework in use. If B receives the header yet starts a new trace, check the propagator format, server filter chain, custom tracing configuration, and whether a root span is being created manually before extraction.

## 7. Context Lost Across Executor, @Async, and CompletableFuture

`ThreadLocal` context is not automatically copied to worker threads. This is a common cause when synchronous code transitions to asynchronous execution.

### 7.1. TaskDecorator and Context Propagation

With Spring Framework 6.1+ and Micrometer Context Propagation, `ContextPropagatingTaskDecorator` can capture/restore registered context accessors:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncConfiguration {
    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-async-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

The decorator only propagates contexts that have matching accessors. Verify tracing/MDC accessors and the actual integration version. Do not assume every `ThreadLocal` is propagated automatically.

### 7.2. @Async

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class InvoiceAsyncService {
    @Async("applicationTaskExecutor")
    public void generateInvoice() {
        // Current trace context should be available through configured propagation.
    }
}
~~~

Enable async processing and invoke the bean through a Spring proxy. Self-invocation within the same bean can bypass `@Async`. Verify that the method actually runs on the configured executor.

### 7.3. CompletableFuture

Explicitly specify an executor for async continuations:

~~~java
CompletableFuture.supplyAsync(this::load, applicationExecutor)
        .thenApplyAsync(this::transform, applicationExecutor);
~~~

Overloads without an explicit executor may run on the common `ForkJoinPool`, where application context propagation is not configured as expected. Each continuation boundary should be tested separately.

### 7.4. Do Not Copy MDC Manually as a Tracing Solution

Copying the MDC map may make logs display `traceId`, but it does not restore the Span context. Use Micrometer Context Propagation/tracing scope to propagate active context; logging integration is responsible for populating IDs into MDC.

## 8. Context in Reactor and WebFlux

Reactive execution can switch threads within a pipeline. `ThreadLocal` is not a reliable context source for reactive chains. Reactor uses a `Context` attached to the subscriber; instrumentation must integrate context propagation so the current span is restored when operators execute.

Checkpoints:
- Reactor instrumentation/observation is enabled for the stack/version;
- context is written to Reactor `Context` at the boundary;
- async operators such as `publishOn`/`subscribeOn` do not drop context;
- custom callbacks do not read `ThreadLocal` arbitrarily;
- cancellation/error terminal signals close the observation/span;
- blocking bridges do not lose context when offloading to an executor.

### 8.1. Testing Across Scheduler Boundaries

Trigger a WebFlux request that passes through `publishOn`/`subscribeOn` and invokes an instrumented downstream client. Assert that the Trace ID matches and the parent relationship is valid. Tests that run only a single operator on the same thread can miss context propagation bugs.

## 9. Context in Messaging

With Kafka, RabbitMQ, or another message broker, the producer must inject trace context into message headers; the consumer must extract headers before creating a processing span. A consumer can be modeled using parent-child or span links depending on messaging semantics, batch processing, and multiple parent messages.

~~~text
Producer service
  └─ Produce span (traceId=T1)
       └─ Message headers: traceparent, tracestate

Broker

Consumer service
  └─ Extract context
       └─ Process span (traceId=T1 or linked context)
~~~

### 9.1. Inspecting Headers

Verify that the producer injects trace context, the broker/client does not strip headers, serializers/deserializers preserve metadata, the consumer extracts before the processing span, and retry/dead-letter flows have a clear context policy.

Do not copy entire message payloads into trace attributes to debug propagation. Use only trace context headers and allowlisted metadata.

### 9.2. Batching and Fan-In

A consumer processing a batch of messages may receive multiple trace contexts. Picking a single parent can misrepresent relationships; span links usually represent multiple causal contexts better. Check the trace model for your messaging instrumentation version.

## 10. Context in JDBC and Database Calls

JDBC calls usually execute synchronously on the current thread. If a parent context is active and JDBC instrumentation is enabled, the database span will be a child span. If repository calls execute on an executor or reactive bridge, context must be propagated to where execution occurs.

Check whether JDBC instrumentation actually creates spans; whether DataSource proxies/agents duplicate or conflict; whether transaction/repository calls run on a different thread; whether the span is created before or after the context closes; and whether the database span has the same Trace ID and appropriate parent.

Pool metrics are not database spans. Having Hikari metrics without JDBC spans does not prove context was lost; JDBC instrumentation may simply not be installed.

## 11. Logs and Correlation IDs

Spring Boot/Micrometer Tracing can integrate `traceId`/`spanId` into logging MDC depending on logging setup. Log correlation helps locate the corresponding trace, but it does not replace the span hierarchy.

Example formatted log:

~~~text
INFO traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7
InvoiceService - Invoice generation started
~~~

When logs are missing `traceId`:
1. Verify an active span exists at the log statement.
2. Check logging correlation integration and MDC format.
3. If logging inside an async worker, check context propagation.
4. If logging after the span scope has closed, adjust the logging boundary or establish the proper operation context.

Do not generate random `traceId` values just to fill the log field; that creates fake correlation.

## 12. Testing Trace Context Propagation

Tests should prove the same Trace ID and parent relationship, not just inspect an MDC string.

### 12.1. Testing Parent-Child with an In-Memory Exporter

With a tracing SDK test setup:
1. Create a parent span and activate its scope.
2. Invoke the operation across the boundary under test.
3. Collect the child span from the in-memory exporter.
4. Assert the child has the same Trace ID.
5. Assert the parent Span ID is correct.
6. End the parent and verify the scope is restored.

Exact APIs depend on the Micrometer Tracing/OpenTelemetry SDK version. Tests must exercise the boundary's real instrumentation.

### 12.2. Testing HTTP Propagation

Use two application contexts or MockWebServer/WireMock:
- service A receives a request;
- A calls B via an instrumented HTTP client;
- B records a server span;
- the test exporter verifies trace IDs and parent relationship;
- test header formats and sampling flags.

Mocking an HTTP client method without running instrumentation interceptors does not prove propagation works.

### 12.3. Testing Executor Thread Reuse

Use a single-worker executor:
1. Caller has parent span T1.
2. Submit task A and assert the worker sees T1.
3. Complete task A.
4. Submit task B with no context.
5. Assert task B does not see T1.
6. Have task C throw an exception and verify the scope is still restored.

Thread reuse tests catch context leakage that single-task tests often miss.

### 12.4. Testing Messaging Propagation

Use an embedded broker or test container when verifying client integration. Assert that the producer injects headers and the consumer extracts the matching Trace ID. For batch/fan-in, assert span links as designed rather than forcing an inappropriate single parent.

### 12.5. Testing Sampling Separately

In propagation tests, use a deterministic sampler or 100% sampling to avoid traces being dropped at random. Once propagation tests pass, write separate tests for sampling policies and exporter behavior.

## 13. Troubleshooting by Boundary

| Boundary | Symptom | First Check |
| --- | --- | --- |
| Ingress → Spring MVC | Server span starts a new root | `traceparent`, gateway, server propagator |
| Spring MVC → HTTP client | Client span has no parent | Active Observation/Tracing scope |
| Service A → Service B | Different Trace ID | Header injection/extraction and format |
| Caller → Executor | Task span becomes root | `TaskDecorator`/context accessor |
| `@Async` | Missing context or self-invocation | Proxy, executor bean, propagation |
| `CompletableFuture` | Only later continuations lose trace | Executor of each async stage |
| Reactor | Context lost after scheduler switch | Reactor `Context`/instrumentation |
| Producer → Broker → Consumer | Consumer starts new trace | Message headers and extraction |
| Service → JDBC | No DB span | JDBC instrumentation and thread boundary |
| Span → Log | Log missing IDs | MDC integration and active scope |
| App → Collector | Span created properly but missing in backend | Sampling, queue, exporter, Collector |

### 13.1. Standard Investigation Workflow

1. Pick a request with a known source trace ID.
2. Check the first server span and parent context.
3. Walk through each boundary: HTTP, executor, messaging, Reactor, JDBC.
4. At each boundary, inspect context before leaving and after entering.
5. Verify Trace ID, Span ID, parent, or span link.
6. If context is correct in-process, check sampling and exporter.
7. Check Collector refused/dropped spans, exporter queue, and backend tenant.
8. Inspect MDC separately from tracing context.
9. Write a regression test for the failing boundary.

### 13.2. Distinguishing Failure Classes

- No span created: instrumentation or Observation is not enabled.
- Span exists but Trace ID differs: extraction/parent context issue or intentional root creation.
- Trace ID matches but parent is wrong: scope/parent selection or async semantics.
- Span is correct in test exporter but missing in backend: sampling/export/Collector/backend.
- Trace is correct but logs lack IDs: logging correlation/MDC.
- Metrics exist while spans are missing: metrics handlers operate independently of tracing context.

## 14. Production Checklist

| Criterion | Required Evidence |
| --- | --- |
| Propagation format agreed upon | W3C/B3 config and ingress policy |
| HTTP client/server instrumented | Cross-service integration test |
| Async context propagated | Executor thread reuse test |
| Reactor context verified | Scheduler boundary test |
| Messaging headers injected/extracted | Producer/consumer integration test |
| JDBC instrumentation present | Trace contains database span when expected |
| Scope restored | Success/error/cancel tests |
| Sampling separated from propagation | Deterministic propagation tests |
| Collector/export monitored | Dropped/refused/exporter metrics |
| Log correlation accurate | MDC fields match active span |
| Privacy controlled | No logging of raw headers/payloads/secrets |
| Regression tests in CI | Boundary tests run on version upgrades |

## 15. Practice Exercise: Fixing a Broken Trace in order-service

**Context:** The `order-service` API receives a request and creates a server span. When calling `inventory-service` over HTTP, the trace ID changes. An audit logging step running via `CompletableFuture` also creates an independent trace; logs in the worker lack `traceId`. HTTP metrics continue working normally.

**Tasks:**
1. Verify Trace ID and parent span on the incoming server span.
2. Check that `traceparent` is injected into the HTTP request to `inventory-service`.
3. Verify `inventory-service` extracts the same Trace ID.
4. Check whether the HTTP client is configured with Spring Boot tracing instrumentation.
5. Specify an explicit executor for `CompletableFuture` async stages.
6. Configure `TaskDecorator`/context propagation for the executor.
7. Verify the worker has an active span and logs have MDC correlation.
8. Test thread reuse to ensure context does not leak between tasks.
9. Check JDBC instrumentation separately if audit persistence requires a database span.
10. Use a deterministic sampler in propagation tests.
11. If spans are created properly yet missing in the backend, check the Collector/export pipeline.
12. Add regression tests and a runbook for HTTP/async context loss.

**Expected outcome:** A continuous trace from the incoming request to the inventory call and async operation with appropriate parent/link semantics; logs have accurate correlation; tests prove context propagation and cleanup.

## 16. Key Takeaways

Lost trace context typically occurs at boundaries where execution transitions from HTTP to a client call, thread pool, `CompletableFuture`, Reactor, or message consumer. Inspect Trace ID and parent relationships on both sides of the boundary. W3C `traceparent`/`tracestate` must be injected/extracted by compatible instrumentation; never fabricate or overwrite headers arbitrarily.

`ThreadLocal` does not propagate automatically to workers; use proper context propagation and `TaskDecorator`/accessors. Reactor requires context-aware instrumentation, messaging requires header injection/extraction, and JDBC requires dedicated instrumentation. Distinguish context loss from sampling/export drops and log correlation failures. Use a test exporter/integration tests to verify matching Trace ID, parent/link, and scope restoration. Metrics can keep working even when tracing context is broken; combine logs, metrics, traces, and Collector diagnostics to identify the exact broken layer.

**References:**
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [OpenTelemetry — Trace SDK Sampling](https://opentelemetry.io/docs/specs/otel/trace/sdk/#sampling)
