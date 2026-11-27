# Choosing a Tracer for Your System

In the **Tracer implementation** chapter of the **SPRING_BOOT_OBSERVABILITY** module, choosing a tracer means choosing the implementation behind the tracing abstraction that your Spring Boot application uses. Micrometer Tracing provides a unified API for the application; a bridge connects that API to a tracing implementation such as **OpenTelemetry** or **Brave**. The implementation, exporter, and backend must fit your existing infrastructure, context propagation mechanism, sampling policy, operational capabilities, and telemetry budget.

This module teaches how to establish observability for Spring Boot using **Micrometer Observation, metrics, logs, and distributed tracing**; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments. Choosing a tracer affects cross-service request stitching, export pipelines, metadata conventions, operational tooling, and future migration plans.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **Micrometer Observation**, **Micrometer Tracing**, the tracing bridge, the tracer implementation, the exporter, and the backend.
2. Evaluate when to adopt the OpenTelemetry bridge versus when an existing system can continue using Brave/Zipkin.
3. Choose a tracer based on backend, participating services, instrumentation, propagation, sampling, security, and operational readiness.
4. Configure Spring Boot dependencies and properties for an appropriate implementation.
5. Avoid installing competing bridges/tracers or creating unintended parallel tracing pipelines.
6. Verify trace IDs, parent–child spans, resource attributes, and the export path end-to-end.
7. Plan a migration between implementations while preserving correlation during the transition period.
8. Combine tracing with metrics and logs without using trace counts as a substitute for traffic or error metrics.

## 2. Distinguishing Layers in the Tracing Stack

The following components are often loosely called "the tracer," yet their roles differ:

| Component | Responsibility | Examples |
| --- | --- | --- |
| **Micrometer Observation** | Describes the lifecycle of an operation at the application level: name, key-values, scope, events, errors. | `order.lookup`, `payment.authorize`. |
| **Micrometer Tracing** | Abstraction for spans, tracers, current span, propagation, and baggage. | Tracing API integrated with Spring Boot. |
| **Tracing bridge** | Connects the Micrometer Tracing abstraction to a concrete implementation. | OpenTelemetry bridge or Brave bridge. |
| **Tracer implementation** | Manages spans/context and application-side tracing behavior. | OpenTelemetry SDK or Brave. |
| **Propagator** | Injects/extracts trace context across HTTP headers or message carriers. | W3C Trace Context, B3. |
| **Exporter/reporter** | Sends spans out of the process in a supported protocol or format. | OTLP exporter, Zipkin reporter. |
| **Collector/agent** | Receives, batches, filters, routes, or forwards telemetry. | OpenTelemetry Collector or platform agent. |
| **Backend** | Stores, searches, analyzes, and visualizes traces. | Jaeger, Tempo, Zipkin, or compatible APM. |

A common flow:

~~~mermaid
flowchart LR
    App["Spring Boot application"] --> Obs["Micrometer Observation"]
    Obs --> MT["Micrometer Tracing"]
    MT --> Bridge["One tracing bridge"]
    Bridge --> Impl["Tracer implementation"]
    Impl --> Prop["Propagator"]
    Impl --> Export["Exporter / reporter"]
    Export --> Collector["Collector / agent"]
    Collector --> Backend["Trace backend"]
    App --> Metrics["Metrics: MeterRegistry"]
    App --> Logs["Logs / MDC"]
    Backend --> Search["Trace search / waterfall"]
    Metrics --> Correlate["Combined investigation"]
    Logs --> Correlate
    Search --> Correlate
~~~

Micrometer Observation is the business instrumentation point; the bridge/tracer creates and manages spans; the exporter ships data; the backend is where operators search traces. **An OTLP-capable backend does not automatically force applications to use the OpenTelemetry bridge**: other compatible paths exist. Conversely, a tracer may create spans properly while a misconfigured exporter/reporter prevents the backend from seeing any data.

A trace consists of related **spans**. Each span describes a stage: a server handling an HTTP request, a database call, an outgoing HTTP client request, or a business processing step.

~~~text
Trace ID: 4f17c38a927d4b55a90714b02f8e6d19
└── SERVER GET /orders/{id}                780 ms
    ├── INTERNAL order.lookup                45 ms
    └── CLIENT POST inventory-service       690 ms
        └── SERVER POST /inventory/reserve   650 ms
~~~

In this hypothetical example, the trace helps pinpoint the time-consuming branch. Do not arbitrarily add nested durations: a parent span encompasses its children's time, and branches can run concurrently. Trace ID identifies the trace; span ID identifies a span; parent span ID represents hierarchy; attributes/status/events describe operations and errors; resource attributes describe the service/process, such as `service.name`.

## 3. Common Options in Spring Boot

In the Spring Boot 3.x ecosystem, the two commonly discussed bridge choices are **OpenTelemetry** and **Brave**.

| Criterion | Micrometer Tracing with OpenTelemetry Bridge | Micrometer Tracing with Brave Bridge |
| --- | --- | --- |
| Implementation | OpenTelemetry SDK/API via Micrometer bridge. | Brave via Micrometer bridge. |
| Ecosystem | Open standard, broad instrumentation/exporters, multi-language/platform support. | Mature Zipkin/Brave ecosystem, fits existing Zipkin/B3 systems. |
| Common export path | OTLP to Collector or OTLP-capable backend; other exporters also exist. | Zipkin reporter to Zipkin endpoint; compatible alternatives depending on config. |
| Propagation | W3C Trace Context is common; supports configured propagators. | B3 is common in Zipkin systems; must align across services. |
| Best fit when | Standardizing multi-language telemetry, using OTLP/Collector or an OTel platform. | Stable Brave/Zipkin infrastructure already meets current needs. |
| What to verify | Resource attributes, exporter, sampler, propagators, semantic conventions, SDK config. | Reporter endpoint, B3/W3C propagation, span model, exporter compatibility. |

This is a directional comparison. Both paths work with Micrometer Tracing, yet they are **not the same bridge**. Check the dependency tree and auto-configuration of your actual Spring Boot/Micrometer versions before deploying.

### OpenTelemetry Bridge

Often the right choice when:

- The system spans multiple languages and needs a shared telemetry standard.
- The observability platform already ingests OTLP or standardizes on the OpenTelemetry Collector.
- You want to leverage OpenTelemetry's instrumentation, resource attributes, and exporter ecosystem.
- There is a plan to unify metrics, traces, and logs onto one pipeline or metadata standard.
- You are building tracing greenfield without existing Brave/Zipkin constraints.

### Brave Bridge

Can be a sensible choice when:

- Existing Spring Boot services already run reliably on Brave/Zipkin and partner services use B3.
- Dashboards, operational tools, and runbooks depend on Zipkin.
- The operations team deeply understands the current pipeline's sampling, reporter, dependencies, and limits.
- Switching implementations does not yet yield enough value to justify migration and compatibility testing costs.

Do not keep Brave merely because "the old system works" if backends, tooling, and future requirements have moved to another standard. Likewise, do not switch to OpenTelemetry just because of buzz without planning the transition of propagation, resource metadata, and instrumentation.

## 4. Decision Matrix: Choosing by System

Start by asking **what problem does the current system need to solve?**

| System Situation | Path to Evaluate First | Reason |
| --- | --- | --- |
| New services, polyglot stack, OTLP-capable platform | OpenTelemetry bridge | Standardizes protocol, metadata, and pipelines across services. |
| Already using OpenTelemetry Collector and OTLP for most workloads | OpenTelemetry bridge | Reuses pipelines, configuration, and operational expertise. |
| Existing Java/Spring Boot running stably on Brave and Zipkin | Brave bridge or phased migration | Avoids changing multiple working layers simultaneously. |
| Backend only speaks Zipkin format, new apps use OTel | Evaluate compatible OTel exporter or Collector translation | Changing tracers does not automatically require replacing the backend at the same time. |
| APM platform provides its own agent | Compare agent, bridge, and OTLP ingest support | Avoids double instrumentation or missing spans. |
| Upstream uses B3, new service uses W3C | Choose an interoperable propagation strategy | Tracers must extract/inject matching headers at every boundary. |
| Tracing cost too high, need to trim ingest | Keep appropriate implementation and design sampling | Swapping tracers does not solve data volume by itself. |
| Traces break across async/threads/messaging | Check context propagation and instrumentation | Swapping exporters will not repair lost context. |

You can use an internal scoring table with weights from 1 to 5:

| Evaluation Factor | Suggested Weight | Question |
| --- | ---: | --- |
| Backend/pipeline compatibility | 5 | Does the backend accept the implementation's protocol and metadata? |
| Cross-service propagation | 5 | Can it stitch W3C/B3/custom headers currently in use? |
| Framework/client instrumentation | 4 | Does it instrument Spring MVC/WebFlux, HTTP clients, DBs, messaging? |
| Sampling and cost control | 4 | Does it support head/tail sampling, limits, and dropped-span visibility? |
| Operations and security | 4 | Are TLS, auth, retention, access control, and dashboards available? |
| Migration/maintenance | 3 | Can the team upgrade bridges/exporters and test them reliably? |
| Backend-specific features | 2 | Do you rely on vendor-specific queries, attributes, or UI? |

This is a discussion framework, not an official Micrometer score. A compatible backend paired with mismatched propagation still yields split traces. The right tracer without a team able to operate the Collector/agent still loses spans silently.

## 5. Configuring the OpenTelemetry Bridge in Spring Boot

Example for **Spring Boot 3.x**, Java 17+, Spring MVC, with dependency versions managed by the Spring Boot BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

OTLP/HTTP configuration to an OpenTelemetry Collector:

~~~yaml
spring:
  application:
    name: order-api

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Meaning:

- `micrometer-tracing-bridge-otel` connects Micrometer Tracing to OpenTelemetry.
- `opentelemetry-exporter-otlp` provides the OTLP exporter compatible with auto-configuration.
- The example endpoint uses OTLP/HTTP traces, commonly port 4318 and path `/v1/traces`.
- `sampling.probability: 0.1` is an example retaining roughly 10% of head-sampled traces where supported; it is not a universal recommendation.
- `order-api` is the service name to verify in resource attributes at the Collector/backend.

If the application and Collector run in separate containers, `otel-collector` must resolve within the application's network. Never use `localhost` unless exporter and receiver genuinely share the appropriate network namespace.

### OTLP/gRPC Is Another Transport Choice

If the receiver only enables gRPC, the exporter must use matching OTLP/gRPC. The common default port for OTLP/gRPC is **4317**, while OTLP/HTTP typically uses **4318**. Never change only the port number in an HTTP URL and expect the transport to switch to gRPC automatically.

Also verify TLS/auth over real networks. An `http://` endpoint is only suitable for labs or protected networks; production should use TLS/mTLS and credentials per platform policy.

## 6. When to Keep Using the Brave Bridge?

If an existing Spring Boot system already uses Brave and Zipkin, a reference configuration for Spring Boot 3.x may look like:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
}
~~~

Example Zipkin endpoint configuration:

~~~yaml
spring:
  application:
    name: order-api

management:
  tracing:
    sampling:
      probability: 0.1
  zipkin:
    tracing:
      endpoint: http://zipkin:9411/api/v2/spans
~~~

This example assumes infrastructure accepts Zipkin spans at that endpoint and your Spring Boot version supports these properties. Verify packages, dependency management, and property names for your exact release. Do not add both the Brave bridge and OpenTelemetry bridge to the same registry/pipeline simultaneously just to test which one is "better."

### Zipkin Backend vs. OTLP

Zipkin is a backend with its own ingestion format/API; OTLP is OpenTelemetry's protocol. You can place a Collector in between to receive OTLP and export to a supported backend/format. Verify actual exporter/conversion capabilities, including attribute, resource, status, event, and sampling mappings.

Do not assume every OTLP span attribute renders identically after conversion to Zipkin. Inspect the payload and backend search behavior, especially when dashboards depend on specific tag names.

## 7. Using Micrometer Observation in Business Code

In Spring Boot applications using Micrometer Observation, prefer instrumenting business operations via the **Observation API** whenever that abstraction meets your needs:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ObservationRegistry registry;
    private final OrderRepository repository;

    public OrderService(ObservationRegistry registry,
                        OrderRepository repository) {
        this.registry = registry;
        this.repository = repository;
    }

    public Order load(long id) {
        return Observation.createNotStarted("order.load", registry)
                .contextualName("load order")
                .lowCardinalityKeyValue("operation", "load")
                .lowCardinalityKeyValue("component", "order-service")
                .observe(() -> repository.findById(id)
                        .orElseThrow(() ->
                                new IllegalArgumentException("Order not found")));
    }

    public interface OrderRepository {
        java.util.Optional<Order> findById(long id);
    }

    public record Order(long id, String status) {}
}
~~~

When the OpenTelemetry bridge, metrics handler, and tracing handler are configured, this single observation can contribute both timing metrics and a span. Business code does not need direct OpenTelemetry SDK dependencies just to use Micrometer's abstraction.

Using the OpenTelemetry API directly can make sense if a library/platform standardizes on the OTel API, needs a tracing feature not yet exposed by Micrometer's abstraction in your version, or involves a polyglot component requiring a specific API. If both Micrometer and the OTel API instrument code, clearly define how tracer/context are shared. Never create two spans for the exact same operation simply because both APIs are invoked.

### Controlling Cardinality

`operation=load` and `component=order-service` have bounded value sets. Never attach order IDs, emails, tokens, or request IDs as low-cardinality key-values. If you need a reference identifier in traces, consider a high-cardinality attribute governed by privacy, retention, and indexing cost policies; never send sensitive data into telemetry by default.

## 8. Propagation Must Match the Rest of the System

A trace only links across services when context is propagated properly. W3C Trace Context typically expresses this via the `traceparent` header:

~~~http
GET /inventory/42 HTTP/1.1
Host: inventory-service
traceparent: 00-4f17c38a927d4b55a90714b02f8e6d19-3a9c31cdb4dcbd74-01
~~~

Long-standing Brave/Zipkin systems may use B3, such as the `b3` header or B3 multi-headers. Header names and encoding must be configured consistently across caller and callee.

| Upstream / Downstream State | Action Required |
| --- | --- |
| All services use W3C Trace Context | Standardize on W3C and verify inject/extract across HTTP/messaging. |
| Many legacy services use B3 | Configure compatible propagators or a transition period supporting the legacy format. |
| Gateway receives W3C, target service only understands B3 | Use a gateway/bridge capable of translating context and test parent links. |
| Service accepts both W3C and B3 | Define precedence to avoid two competing trace contexts on one request. |
| Async threads or Reactor lose parent | Check context propagation on executors / reactive stack. |
| Messaging lacks linked spans | Check message headers and inject/extract instrumentation. |

Changing the tracer implementation does not automatically convert all headers across the system. If upstream sends B3 while downstream only extracts W3C, the trace can split into two roots. If both formats appear with different trace IDs, explicitly define which propagator takes precedence.

### Context Propagation via HTTP Clients

Spring Boot typically provides matching instrumentation when using auto-configured clients or builders. Example using a Spring-managed `RestClient.Builder` in a supported version:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {

    private final RestClient client;

    public InventoryClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service:8080")
                .build();
    }

    public InventoryResponse find(long id) {
        return client.get()
                .uri("/inventory/{id}", id)
                .retrieve()
                .body(InventoryResponse.class);
    }

    public record InventoryResponse(long id, int quantity) {}
}
~~~

The hostname and endpoint in the example must exist on the application network. If you instantiate an HTTP client manually outside instrumentation, propagation may not happen automatically. Inspect outgoing requests to verify `traceparent` or the system's agreed-upon header is present.

### Async and Reactive

An observation/tracing scope on one thread does not automatically transfer to every other thread. With `@Async`, `CompletableFuture`, custom executors, or Reactor, use the context propagation mechanism suited to your Spring Boot/Micrometer version and runtime stack. Never carry an open `Observation.Scope` across to another thread and close it outside its execution context.

With Reactor, work may execute only upon subscription; the observation lifecycle must track terminal signals (complete/error/cancel), not finish as soon as a `Mono`/`Flux` is constructed.

## 9. Sampling: Do Not Swap Tracers to Fix Cost

Even the right tracer requires a sampling policy. Head sampling decides early which traces are recorded; parent-based sampling can follow the upstream decision. Tail sampling in the Collector can select traces after receiving spans per policy, such as prioritizing errors or slow requests.

Lab example keeping all traces:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Test example with a lower probability:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

These rates are illustrative only. There is no single sampling number right for every service. Base the decision on traffic volume, rare error rates, ingestion costs, investigative value, and backend capacity.

| Question | OpenTelemetry Bridge | Brave Bridge |
| --- | --- | --- |
| Does the app support sampling? | Yes, via matching tracing SDK/configuration. | Yes, via Brave/Micrometer sampling integration. |
| Does the Collector support tail sampling? | Yes, when spans go to an OTel Collector with the corresponding processor. | Possible when spans flow through a supporting pipeline; verify ingestion mechanics. |
| Does changing bridges reduce cost on its own? | No. | No. |
| Are metrics sampled at the same rate? | Not by default. | Not by default. |

Metrics generally continue aggregating traffic independently of stored trace counts. Never use trace counts to compute request rates, error rates, or SLOs. Tail sampling can only decide on spans the Collector receives; if the application's head sampler dropped a trace, the Collector cannot recreate spans that were never sent.

## 10. Exporters and Backends: Check Compatibility

| Backend / Infrastructure | Questions to Verify |
| --- | --- |
| **Jaeger** | Does the deployed version accept OTLP directly? If not, which Collector exporter/protocol is needed? |
| **Grafana Tempo** | Where is the OTLP trace endpoint? How are resource attributes and retention configured? |
| **Zipkin** | Which API receives Zipkin spans? Is the Brave reporter or a translating Collector needed? |
| **APM vendor** | What are the specific API keys, endpoints, regions, TLS, sampling, and ingest quotas? |
| **OpenTelemetry Collector** | Are receivers, processors, exporters, queues, retries, and memory limiters configured and monitored? |

Do not guess endpoints from a backend's brand name. Obtain addresses, paths, protocols, and auth details from actual platform configuration.

An intermediate Collector decouples backend addresses from individual app configs and centralizes authentication/TLS, routing, batching, sampling, and dropped-telemetry monitoring. However, the Collector becomes a new operational component requiring HA, capacity planning, memory, queues, retries, and alerts. Direct export can be simpler for smaller systems; weigh operational overhead in your choice.

## 11. Resource Metadata and Semantic Conventions

When selecting a tracer, verify the **resource attributes** and **span attributes** that the backend uses for filtering and search.

A useful trace typically needs:
- `service.name`: a stable service name.
- Environment/deployment metadata such as namespace or environment when needed.
- Operation/span names clear enough for analysis.
- HTTP method, route template, and status following appropriate conventions.
- Dependency/DB/messaging attributes as supported by instrumentation.
- Error status/events when operations fail.

Do not attach short-lived pod names or user/request IDs as shared resource identity for all spans if semantically wrong. Resource describes the process/service instance; span attributes describe a single operation.

Semantic conventions and naming can evolve across instrumentation versions. When switching bridges or upgrading, compare raw spans to catch changed span names, changed service names, raw URLs replacing route templates, missing error statuses/attributes, or tag mappings that break dashboards.

## 12. Correlating Metrics, Logs, and Tracing

| Operational Question | Metrics | Logs | Traces |
| --- | --- | --- | --- |
| How many requests failed? | Rates/counts by route and status. | Specific error events. | A subset of sampled/retained error traces. |
| Where did P95 rise? | HTTP/dependency timers, histograms. | Timeouts, retries, pool waits. | Waterfalls and span durations. |
| Which request was affected? | Usually no per-request ID. | Request ID and trace ID if present. | Trace ID and span tree. |
| Which service is bottlenecked? | Pool, JVM, queue, request metrics. | Per-service logs. | Cross-service client/server spans. |

Micrometer Observation can emit both metrics and spans from the same operation when matching handlers are configured. Logs can carry trace ID / span ID via MDC. However, metric labels require low cardinality; trace attributes must still respect privacy and cost; logs operate independently of the tracing sampler; the trace exporter does not replace a metrics exporter; and not every request has a stored trace.

A good tracer choice is one that **preserves end-to-end investigative capability**, not merely one that exports spans from a single service.

## 13. Migrating Between Brave and OpenTelemetry

Tracing migration is a protocol and operational change, not merely swapping a dependency.

### Phase 1 — Inventory

Document the bridge/tracer currently used in each service; propagation formats (W3C, B3, baggage, and custom headers); backends, endpoints, reporters/exporters, and Collectors; sampling rules, resource attributes, span names, tags, and log correlation; and which fields dashboards, alerts, saved queries, and runbooks rely on.

### Phase 2 — Pick a Boundary

Avoid changing every service, gateway, Collector, and backend in one big bang if unnecessary. Choose a service with representative traffic and dependencies; run it in a controlled environment and capture before/after traces for the same scenario.

### Phase 3 — Test Interoperable Propagation

Test legacy caller → new service; new caller → legacy service; new service → new service; HTTP through gateways across at least two services; and messaging/async if used. Verify trace IDs, parent span IDs, sampling flags, and parentage. If supporting both W3C and B3 during transition, configure precedence and test what happens when two headers carry conflicting contexts.

### Phase 4 — Compare Data

Compare ingested trace ratios against expected sampling; span names, attributes, resource identity, and error status; per-dependency latencies; log correlation; exporter errors, Collector drops, and backend ingestion; and ingest volume, index size, retention, and cost.

### Phase 5 — Rollout and Rollback

Roll out by service group or traffic slice. Keep prior configs/versions ready for a controlled rollback window. Never let two tracing implementations instrument the same request simultaneously and emit accidental duplicate spans.

If the new backend falls short, rollback must restore the bridge, exporter, and propagation policy together; reverting only the dependency while forgetting the header strategy can keep traces split.

## 14. Common Mistakes When Choosing and Deploying a Tracer

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| No tracer bean or startup failure | Missing bridge, conflicting dependency versions, or auto-config inactive. | Inspect dependency tree and conditions for your Spring Boot release. |
| Two spans for the same operation | Operation instrumented by two APIs/agents/bridges. | Choose one instrumentation source and define boundaries. |
| Trace splits across services | B3/W3C incompatibility, uninstrumented client/server, or lost context. | Inspect headers and propagators at every hop. |
| OTLP exporter cannot connect | Wrong transport/port/path, DNS/network, TLS, or auth. | Verify receiver, exporter endpoint, and Collector logs. |
| Collector receives spans, backend is empty | Backend exporter/pipeline failure or backend failed to ingest/index. | Check Collector exporter errors and backend ingestion. |
| Service appears under multiple service names | Inconsistent resource attributes or naming. | Standardize `service.name`, environment/namespace, and mappings. |
| Dashboards lose data after migration | Span names, tags, or semantic conventions changed. | Compare raw spans and update queries/dashboards. |
| Fewer traces than request metrics | Sampling or export/ingest drops. | Review sampling policy and pipeline; do not treat trace count as traffic. |
| Backend overloaded after changing bridge | Increased sampling, extra attributes, or unsuited batching/limits. | Measure ingest, trim cardinality, tune sampling and Collector capacity. |
| Logs missing trace ID | Wrong MDC/correlation or async propagation. | Check log patterns, context, and executor/reactive setup. |
| Async span has no parent | Observation closed before async work or context not propagated. | Tie lifecycle to completion and propagate context across execution contexts. |

## 15. Runbook for Evaluating a Tracer on a Running System

1. **Define the investigative goal:** rare errors, dependency latency, fan-out, or polyglot correlation? Write down the questions traces must answer.
2. **Map the system:** services, frameworks, HTTP clients, messaging, databases, gateways, agents, and current backends.
3. **Audit propagation:** which boundaries use W3C/B3 and baggage? Is context lost across async paths?
4. **Compare backends/ingest:** direct OTLP, Collector, Zipkin API, or agent? Evaluate compatibility and operational effort.
5. **Select a candidate bridge:** OpenTelemetry or Brave based on current constraints and long-term goals.
6. **Build a test flow:** an HTTP request crossing at least two services, with a custom observation and a dependency span.
7. **Verify end-to-end:** trace ID, parent–child links, resource metadata, errors, log correlation, and backend search.
8. **Measure cost:** sampling rate, exported spans, dropped spans, storage/index footprint, and Collector load.
9. **Test controlled failures:** slow downstream, error responses, timeouts, async, or messaging if applicable.
10. **Decide rollout:** finalize implementation, propagation policy, sampling, ownership, and rollback plan; record evidence.

A tracer should never be chosen simply because a local demo draws a nice waterfall. It must preserve context across the exact communication paths your system uses, with useful metadata and acceptable cost.

## 16. Self-Check Exercises

### Exercise 1 — Choosing a Bridge

A new system includes Java/Spring Boot, Node.js, and Go; the observability platform already ingests OTLP via a Collector. Which path should be evaluated first?

**Answer:** The OpenTelemetry bridge is the natural candidate to standardize on OTLP across a polyglot ecosystem. You still need to verify instrumentation per service, propagation, resource attributes, sampling, and the backend.

### Exercise 2 — Keep Brave or Switch?

An existing Java system runs Brave/Zipkin, B3 propagation, and stable dashboards. There are no new requirements for polyglot services or OTLP. Is switching to the OpenTelemetry bridge mandatory?

**Answer:** No. You can continue using Brave if the stack remains supported, operations meet needs, and risk/cost are acceptable. Plan a migration when there is a concrete benefit, not merely to follow trends.

### Exercise 3 — OTLP Succeeds, Yet Traces Split

The Collector receives spans from both `order-api` and `inventory-api`, yet they have different trace IDs. Should you fix the exporter or propagation?

**Answer:** Inspect propagation first: check whether `traceparent`/B3 is injected and extracted, whether HTTP client/server instrumentation is active, and whether async context is lost. Exporters ship spans that were already created; they do not stitch separate traces together by service name.

### Exercise 4 — Choosing Sampling

An API handles 20,000 requests/second and backend ingestion exceeds budget. Should you switch from OpenTelemetry to Brave to reduce trace volume?

**Answer:** No, there is no basis for that. Address cost through sampling policies, attributes/cardinality, exporter batching, Collector capacity, and retention. Swapping implementations does not reduce sampling rate or data volume on its own.

### Exercise 5 — Two Bridges in One Application

An application adds both `micrometer-tracing-bridge-otel` and `micrometer-tracing-bridge-brave` hoping to send the same span to two backends. Is this a recommended default design?

**Answer:** No. Two bridges can create competing auto-configurations or duplicate pipelines depending on version and config. If you need to export to two destinations, evaluate exporter/Collector fan-out from a single tracing implementation, and verify there are no duplicate spans or split contexts.

### Exercise 6 — More Metrics Than Traces

The metrics dashboard shows 5,000 requests while the backend stores 500 traces. Can you conclude 4,500 requests are uninstrumented?

**Answer:** No. Tracing sampling may retain 10%, while metrics aggregate nearly all requests. Verify sampling and the export pipeline; use metrics for traffic/error rates and traces for sampled investigations.

## 17. Checklist for Choosing and Operating a Tracer

- [ ] Identify existing backends, ingestion protocols, and exporter/Collector pipelines.
- [ ] Choose one suitable tracing bridge, avoiding multiple competing implementations.
- [ ] Manage dependency versions compatibly with Spring Boot/Micrometer.
- [ ] Keep resource attributes, especially `service.name`, consistent across services.
- [ ] Align and test W3C/B3 propagation across gateways, HTTP clients/servers, and messaging.
- [ ] Verify context propagation across `@Async`, executors, `CompletableFuture`, and Reactor.
- [ ] Tune sampling to traffic, SLOs, rare error visibility, and backend budget.
- [ ] Ensure OTLP/Zipkin reporters use the right transport, endpoint, TLS/auth, and network boundaries.
- [ ] Monitor Collector/agent queues, exporter failures, dropped spans, and resource usage.
- [ ] Keep span names/attributes meaningful, with controlled cardinality and privacy.
- [ ] Correlate logs with trace IDs whenever active context is present.
- [ ] Keep metrics as the source for traffic, error rates, and aggregated latency; never infer SLOs from trace counts.
- [ ] Re-test dashboards/alerts after changes to span names, attributes, or semantic conventions.
- [ ] Plan migrations with canaries, data comparison, and synchronized propagation/bridge rollback.

**Remember:** Choose a tracer based on **backend, propagation, instrumentation, sampling, and end-to-end operability**. In Spring Boot, Micrometer Tracing keeps applications on a clean abstraction; the OpenTelemetry bridge fits OTel/OTLP and polyglot standardization, while the Brave bridge can remain a solid fit for well-running Zipkin/B3 systems. What decides success is that traces stitch across services, export to the right destination, carry useful metadata, and pair with metrics and logs for evidence-based incident investigation.
