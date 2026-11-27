# Zipkin Exporter in Spring Boot: Configuring and Verifying Distributed Traces

> **Chapter:** Tracer implementation  
> **Lesson:** Zipkin exporter  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments.

## 1. From Spans in the Application to Traces in Zipkin

A Spring Boot application can create spans when receiving HTTP requests, calling other services, or executing a business step. However, **a span created in-process does not mean a trace has already appeared in the Zipkin UI**. The system needs a transport path from the tracer to the trace storage and query layer.

The **Zipkin exporter** is the component that forwards finished spans from the application's tracing implementation to the Zipkin collector. In a Spring Boot stack using Micrometer Tracing, a common choice is Micrometer Tracing + Brave + Zipkin Reporter:

- **Micrometer Tracing** provides the tracing API integrated with Observation.
- The **Brave bridge** connects the Micrometer Tracing API to the Brave tracer.
- **Zipkin Reporter** receives spans from Brave, batches them, and sends them to the Zipkin collector using the Zipkin protocol.
- The **Zipkin server** receives spans, stores them per configuration, and provides the UI/API for trace lookup.

~~~mermaid
flowchart LR
    A["Spring MVC / WebClient / Observation"] --> B["Micrometer Observation"]
    B --> C["Micrometer Tracing"]
    C --> D["Brave bridge / Tracer"]
    D --> E["Zipkin Reporter"]
    E -->|"HTTP POST /api/v2/spans"| F["Zipkin Collector"]
    F --> G["Zipkin Storage"]
    G --> H["Zipkin UI / Search API"]
~~~

This path can also be adapted when an application uses the OpenTelemetry bridge or OpenTelemetry Collector, though configuration and exporters differ. This lesson focuses on the **Micrometer Tracing + Brave + Zipkin Reporter** option common in Spring Boot 3.x.

The goal is to configure the exporter, generate multi-span traces, inspect data in Zipkin, understand sampling/propagation, and diagnose cases where spans never reach the backend.

## 2. Distinguishing Tracer, Bridge, Reporter, and Zipkin Server

These components have distinct responsibilities; missing one link can keep traces from reaching the UI.

| Component | Responsibility | Examples |
| --- | --- | --- |
| **Instrumentation** | Creates Observations/spans at work boundaries | Spring MVC server, HTTP clients, business services |
| **Micrometer Tracing** | Unified tracing API and Observation integration | `Tracer`, `Span`, `BaggageManager` |
| **Tracing bridge** | Connects Micrometer Tracing to a concrete implementation | `micrometer-tracing-bridge-brave` |
| **Tracer** | Creates spans, manages trace/span context and sampling | Brave tracer |
| **Reporter/exporter** | Ships completed spans to the target receiver | Zipkin Reporter |
| **Zipkin collector** | Accepts span payloads and writes to storage | Zipkin server |
| **Storage** | Persists traces per deployment setup | In-memory, Elasticsearch, Cassandra, or compatible backend depending on environment |
| **Zipkin UI** | Searches traces and renders span waterfalls | Web UI typically on port 9411 |

**The reporter does not create instrumentation.** If no instrumentation creates spans, Zipkin has no data to display. Conversely, an application may create spans while the reporter fails to export them due to a wrong endpoint, network issues, sampling, or connection errors.

The Zipkin server also does not automatically instrument HTTP clients/servers inside the application. You need the corresponding starters, auto-configuration, or integrations so those boundaries create spans and propagate trace context.

## 3. Maven Dependencies for Spring Boot 3.x with Brave

Example using the Spring Boot parent/BOM to manage compatible versions:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-brave</artifactId>
    </dependency>

    <dependency>
        <groupId>io.zipkin.reporter2</groupId>
        <artifactId>zipkin-reporter-brave</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Purpose:

- `spring-boot-starter-actuator` provides the management foundation and Observation integration.
- `micrometer-tracing-bridge-brave` provides the bridge between Micrometer Tracing and Brave.
- `zipkin-reporter-brave` integrates the Zipkin reporter with Brave, enabling span delivery to Zipkin.
- `spring-boot-starter-web` is only for the REST MVC example; WebFlux apps use the corresponding starter.

Use the Spring Boot BOM to keep Micrometer/Brave/Reporter versions aligned. Avoid upgrading a single tracing dependency independently without checking compatibility with your Boot version. Artifact names, properties, and auto-configuration can change across major versions; examples here target Spring Boot 3.x.

**Do not add multiple tracing bridges simultaneously** such as both the Brave bridge and OpenTelemetry bridge in the same application without an explicit design. Having two implementations configured together can cause conflicts or ambiguous auto-configuration.

## 4. Running a Zipkin Server in a Learning Environment

A simple way to experiment is running the Zipkin server as a container. Docker example:

~~~bash
docker run --name zipkin -d -p 9411:9411 openzipkin/zipkin
~~~

Once the container is ready, open:

~~~text
http://localhost:9411
~~~

The UI is typically served on port 9411; the v2 collector API accepts spans at:

~~~text
http://localhost:9411/api/v2/spans
~~~

You can check whether the server responds using:

~~~bash
curl -i http://localhost:9411/health
~~~

The health endpoint and response format may vary by distribution or configuration. The goal is to confirm the container is running and reachable by the application; opening the UI alone does not prove the exporter has sent spans.

### 4.1. Illustrative Docker Compose

~~~yaml
services:
  zipkin:
    image: openzipkin/zipkin
    container_name: zipkin
    ports:
      - "9411:9411"
~~~

Run:

~~~bash
docker compose up -d zipkin
docker compose ps
~~~

In production, never assume the default storage of a learning container is a durable long-term solution. Select storage backend, persistence, backups, retention, capacity, and access controls according to operational requirements. Pin specific versions/image tags in managed deployments instead of relying on floating tags.

## 5. Configuring the Zipkin Endpoint in Spring Boot

Example `application.yml` for Spring Boot 3.x:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

Explanation:

- `spring.application.name` provides the service identifier used in metadata/resource/span tags matching the stack.
- `management.tracing.sampling.probability` sets the head sampling probability in a simple setup. A value of `1.0` selects nearly all traces in a demonstration environment.
- `management.zipkin.tracing.endpoint` is Zipkin's span ingestion endpoint, typically the v2 path `/api/v2/spans`.
- The reporter is auto-configured when matching dependencies and properties are present; there is no need to build `AsyncReporter` manually in every service.

**Container networking note:** if the Spring Boot application also runs in Docker Compose alongside Zipkin, `localhost` inside the app container points to the app container itself. In that case, use the service hostname, such as `http://zipkin:9411/api/v2/spans`. If the app runs on the host while Zipkin publishes its port to the host, `localhost:9411` works.

Never expose the collector to the public Internet without proper network controls or protection layers. Zipkin payloads can contain service topology, URL/peer metadata, exception details, and application attributes.

## 6. Creating a Trace with Spans in a Spring Boot Application

For the exporter to have data to send, the application must create spans. Spring Boot can auto-instrument HTTP servers and clients in supported integrations. Let us add a business observation to illustrate an internal span.

### 6.1. Controller and Service

~~~java
package example.orders;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final ObservationRegistry observationRegistry;

    public OrderService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public String createOrder(String channel) {
        return Observation.createNotStarted(
                "orders.create", observationRegistry)
            .contextualName("create order")
            .lowCardinalityKeyValue("channel", normalizeChannel(channel))
            .observe(() -> {
                reserveInventory();
                return "created";
            });
    }

    private void reserveInventory() {
        // Simulate business work.
    }

    private static String normalizeChannel(String value) {
        if ("web".equals(value)) return "web";
        if ("mobile".equals(value)) return "mobile";
        return "other";
    }
}
~~~

~~~java
package example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders")
    public String create(@RequestParam(defaultValue = "web") String channel) {
        return orderService.createOrder(channel);
    }
}
~~~

When tracing is configured:

1. HTTP server instrumentation can create a server span for `GET /orders`.
2. The Observation named `orders.create` creates an internal span when the tracing handler is active.
3. The business span becomes a child of the server span when the current observation/trace context is preserved.
4. Once spans finish and are sampled, the reporter exports them to Zipkin.

`Observation.observe(...)` fits synchronous work. For asynchronous steps, manage lifecycle and context propagation using framework mechanisms to avoid closing spans before work finishes.

### 6.2. Calling the Endpoint to Generate Traffic

~~~bash
curl "http://localhost:8080/orders?channel=web"
curl "http://localhost:8080/orders?channel=mobile"
~~~

Invoke it multiple times in your learning environment, then open the Zipkin UI and search for service `order-service` or the matching operation. If search shows no traces yet, inspect sampling, reporter logs, and the endpoint before modifying instrumentation code.

## 7. Sampling: Why Doesn't Every Request Appear in Zipkin?

Tracing can create context for every request, yet the **sampler** decides which traces are retained and exported.

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

The application samples roughly 10% of incoming traces using the implementation's sampling mechanism. This is a statistical probability, not a strict guarantee that exactly one out of every 10 requests produces a trace.

| Illustrative Value | Meaning | When to Consider |
| --- | --- | --- |
| `1.0` | Sample all traces per probability policy | Local/test, low traffic |
| `0.1` | Sample a fraction | High-traffic environments balancing cost |
| `0.01` | Sample fewer traces | Very high trace volume; consider rare error coverage |

These values are examples only, not fixed recommendations for every environment. If the root of a trace is not sampled, child spans are typically not exported for that trace in standard head-based setups. Thus, **failing to find a specific request in Zipkin does not prove the application lacks instrumentation**.

### 7.1. Sampling Is Not Metrics Step or Scrape Interval

- Sampling picks which **traces** are recorded.
- Step sets the **publish interval** of certain metrics registries.
- Prometheus scrape interval sets when a server scrapes metrics.
- Collector batch timeout sets how long telemetry buffers before forwarding.

Reducing trace sampling does not automatically reduce Counter/Timer metrics. You can have complete aggregated metrics alongside only a subset of detailed traces; this is normal by design.

## 8. Propagation: Stitching Spans Across Multiple Services

Suppose `order-service` calls `inventory-service`. For both spans to share the same trace, the client must inject trace context into the request and the server must extract it.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Zipkin
    participant Inventory as inventory-service
    Client->>Order: GET /orders
    Note over Order: Create server span and orders.create
    Order->>Inventory: HTTP request + tracing headers
    Note over Inventory: Extract context and create server span
    Inventory-->>Order: Response
    Order-->>Client: Response
    Order-->>Zipkin: Export sampled spans
    Inventory-->>Zipkin: Export sampled spans
~~~

Common propagation formats include:

- **B3 single header:** typically uses the `b3` header carrying trace/span and sampling information.
- **B3 multi-header:** uses headers like `X-B3-TraceId`, `X-B3-SpanId`, and `X-B3-Sampled`.
- **W3C Trace Context:** uses `traceparent`, optionally accompanied by `tracestate`.

Brave and Micrometer Tracing support these propagation formats depending on configuration. Both services must agree on the accepted and emitted format. If upstream sends B3 while downstream only extracts W3C, the trace splits into two separate traces.

For HTTP clients in Spring, use integrations/builders instrumented by the framework so headers are injected automatically. If you instantiate a client manually bypassing Spring's builder/configuration, do not assume propagation still happens.

### 8.1. Inspecting Headers

In a local/test environment, you can use a proxy or test server to verify requests carry the expected trace context headers. Never log all Authorization/Cookie headers. Inspect only approved tracing headers, and never turn them into metric labels.

**Trace context is not arbitrary baggage.** Only propagate extra business fields via baggage when explicit propagation, security, and header-size rules exist. A single span attribute is not automatically injected into downstream requests.

## 9. Zipkin Span Model: Service, Operation, Kind, Tags, and Annotations

Zipkin displays spans with core fields mapped from the tracing implementation and semantic conventions:

| Field | Meaning |
| --- | --- |
| `traceId` | Trace identifier |
| `id` | Span identifier |
| `parentId` | Parent span ID, if present |
| `name` | Operation/span name |
| `kind` | `CLIENT`, `SERVER`, `PRODUCER`, `CONSUMER`, or `INTERNAL` depending on model |
| `timestamp` | Start timestamp |
| `duration` | Duration in Zipkin's defined units |
| `localEndpoint` | Service/local endpoint creating the span |
| `remoteEndpoint` | Peer/destination when available |
| `tags` | Key–value metadata describing the span |
| `annotations` | Timestamped event milestones in Zipkin's model; mapping depends on instrumentation/reporter |

Short, stable operation names aid searchability. Avoid embedding order IDs, user IDs, or URL paths containing IDs into span names because variable names hinder querying and risk data leaks. Use route templates or stable operation names.

### 9.1. Tags and Cardinality

A span can carry attributes distinguishing an individual execution, yet backend volume still needs governance. With metrics, especially avoid turning per-request IDs into labels; with tracing, record high-cardinality attributes only when genuinely needed and permitted.

~~~java
Observation.createNotStarted("inventory.reserve", registry)
    .lowCardinalityKeyValue("channel", "web")
    .highCardinalityKeyValue("reservation.attempt_id", attemptId)
    .observe(this::reserve);
~~~

`channel` works well for metric aggregation; `reservation.attempt_id` helps investigate a specific span, subject to data policy, retention, and Zipkin/backend indexing rules. Do not assume every UI indexes every tag with equal performance.

## 10. Reporter and Batching: How Are Spans Sent?

In the Brave + Zipkin Reporter stack, finished spans are typically handed to the reporter asynchronously. The reporter batches multiple spans into one payload instead of making a separate HTTP request per span.

Key concepts:

- **Sender** knows how to deliver payloads to the Zipkin collector over HTTP or a supported transport.
- **Reporter** accepts spans and coordinates sending.
- **Queue/buffer** holds pending spans up to configured limits.
- **Batching** groups multiple spans into one batch to reduce request overhead.
- **Flush/shutdown** attempts to push remaining buffered data before process exit, depending on lifecycle and configuration.

Batching reduces network overhead while introducing a brief delay before spans appear in the UI. When the queue fills up or the exporter fails, spans may be dropped per policy. Never assume the reporter provides exactly-once guarantees or durable long-term storage.

### 10.1. Do Not Confuse Reporter Batching with Sampling

A sampled trace may still be absent from Zipkin temporarily while the reporter waits to flush a batch, the collector is ingesting it, or storage/UI has not updated yet. Conversely, a trace dropped by sampling is never handed to the reporter at all, even when the Zipkin endpoint is healthy.

When diagnosing, distinguish **not sampled**, **waiting in batch**, **send failed**, and **received by collector but not yet visible in storage/search**.

## 11. Inspecting Zipkin via UI and API

After calling the application endpoint, open the Zipkin UI at `http://localhost:9411`.

Inspection steps:

1. Select service name `order-service` (or your configured service name).
2. Select operation `GET /orders` or `orders.create` depending on instrumented spans.
3. Choose a time window wide enough around your request time.
4. Run the search and open a trace to view the waterfall.
5. Inspect `traceId`, `spanId`, parent–child links, start times, and durations.
6. Expand individual spans to check kinds and tags.
7. If an error occurred, inspect tags/error details according to how your reporter/instrumentation maps them.

### 11.1. Querying via the Zipkin API

Zipkin exposes a trace query API. Illustrative example:

~~~bash
curl "http://localhost:9411/api/v2/traces?serviceName=order-service&limit=10"
~~~

Exact API paths and parameters may vary by Zipkin version; check the documentation for your running server. Results typically return lists of traces containing matching spans. Never query production API endpoints without proper access control.

### 11.2. If No Traces Appear

Check in order:

- Is the application creating spans? Is HTTP or Observation instrumentation active?
- Are the bridge and reporter dependencies properly loaded?
- Did sampling probability drop that trace?
- Does the Zipkin endpoint use the right host, port, and path from the application's network namespace?
- Do reporter logs show connection or HTTP response errors?
- Did the Zipkin collector receive the payload? Did storage persist it? Is the UI filtering the wrong service or time range?
- Is trace context propagating across services?

Do not crank sampling to 100% or sprinkle manual spans everywhere before pinpointing where the pipeline failed. Doing so increases load and risks duplicate instrumentation.

## 12. Handling Span Errors with Zipkin

Zipkin represents errors through tags/annotations depending on data model and reporter; its display does not necessarily look identical to OpenTelemetry's `status=ERROR` field. With the Brave bridge, an exception reported to an Observation is mapped to the corresponding tag/event by the bridge and reporter.

Example with Micrometer Observation:

~~~java
Observation observation = Observation.createNotStarted(
        "payments.authorize", observationRegistry).start();

try (Observation.Scope scope = observation.openScope()) {
    authorizePayment();
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

This snippet reports the error to the Observation so matching handlers record it and finish the span. It does not write application logs automatically, nor does it guarantee every backend displays a field literally named `error=true`. Inspect the actual span payload sent.

**Distinguish business failures from technical errors.** A payment declined under business rules may be a valid outcome rather than an infrastructure fault. Use a bounded outcome/tag to express business states; only report an exception/span error when the operation genuinely fails under defined semantics.

Never put unbounded exception messages, tokens, request/response bodies, or sensitive data into tags. Traces can be retained for long periods and viewed by many operations teams.

## 13. Combining Zipkin Traces with Metrics and Logs

Zipkin helps reveal execution paths and durations, yet it does not replace metrics or logs:

~~~mermaid
flowchart TD
    A["Metrics: error rate / p95 rises"] --> B["Narrow down service, route, time window"]
    B --> C["Zipkin: find sampled traces"]
    C --> D["Inspect span waterfall and downstream"]
    C --> E["Read span tags / error metadata"]
    D --> F["Search logs by traceId/spanId"]
    E --> F
    F --> G["Form hypothesis and verify"]
    G --> H["Monitor metrics again after fix"]
~~~

- **Metrics** tell you whether an issue is widespread—for example, the 5xx rate climbing on `POST /orders`.
- **Zipkin** highlights which span is slow or failing in a specific trace.
- **Logs** provide detailed event context when trace/span correlation is enabled.
- **Trace IDs** link spans and log records for a single request; never use them as metric labels.

A missing trace may be due to sampling. Therefore, never use Zipkin trace counts to compute total request counts or replace a Counter. SLIs/SLOs must rely on metrics with clear semantics.

### 13.1. Log Correlation

When logging integration is configured, log lines can include `traceId` and `spanId`. Illustrative format example:

~~~text
INFO  [order-service, traceId=ab12..., spanId=cd34...] Created order
WARN  [order-service, traceId=ab12..., spanId=ef56...] Inventory timeout
~~~

Having the Zipkin exporter does not automatically guarantee your logging pattern prints these two values. Verify logging correlation in Spring Boot configuration and handle context propagation when switching threads.

## 14. Production Configuration: Endpoints, Networking, Retries, and Storage

The Zipkin exporter is an operational component, so configuration must account for more than whether an endpoint replies.

### 14.1. Service Discovery Addresses

Locally, the endpoint is often `http://localhost:9411/api/v2/spans`. In containers or orchestrators, use service DNS or the appropriate collector address. Never hardcode ephemeral pod IPs.

### 14.2. Networking and Data Protection

- Allow only required application workloads to reach the collector.
- If spans contain internal attributes, protect the collector/UI with private networking, an authentication proxy, or equivalent controls.
- Use TLS when crossing untrusted networks; TLS/auth configuration options depend on the reporter/transport and deployment infrastructure.
- Never commit credentials into `application.yml`; use secret management and proper configuration injection.
- Enforce policy limits on tags, event counts, attribute sizes, and retention.

### 14.3. Reporter Failures and Shutdown

When Zipkin is unavailable:

- Monitor reporter error logs and telemetry.
- Check whether queues/buffers fill up and spans are dropped.
- Review retry/backoff and timeout settings for your reporter version.
- Ensure graceful shutdown allows enough time to flush if supported by the reporter.
- Never treat the reporter queue as a persistent event store; restarts or crashes can lose buffered spans.

Tracing is observability data, not a durable transaction audit system. If every business event must be persisted reliably, use a dedicated event or audit store.

### 14.4. Direct Zipkin vs. an Intermediate Collector

An architecture can ship spans directly to Zipkin. When unifying multiple telemetry sources, you can send OTLP to an OpenTelemetry Collector and have the Collector export to a compatible backend. Both approaches involve trade-offs in protocol standardization, pipeline governance, and centralized processing.

Do not add a Collector just because the word "exporter" sounds enterprise-grade. Decide based on real needs for transformation, batching, filtering, retries, multi-destination routing, security, and operations.

## 15. Common Pitfalls When Configuring the Zipkin Exporter

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Zipkin UI works, no traces appear | App lacks tracer/bridge/reporter, sampler dropped trace, or no spans created | Check dependencies, instrumentation, and sampling |
| Connection refused | Wrong host/port, Zipkin container not ready, or wrong network namespace | Curl endpoint from inside app environment; check container networking |
| HTTP 404 when sending spans | Wrong path, such as missing `/api/v2/spans` | Verify the v2 collector endpoint |
| HTTP 400 or payload rejected | Incompatible reporter/protocol/version or invalid data | Check response/logs and dependency alignment |
| Server span exists, client span missing | HTTP client uninstrumented or built bypassing configured builder | Check client instrumentation and propagation |
| Multiple traces instead of one cross-service trace | Inconsistent B3/W3C propagation or stripped headers | Inspect `traceId` and inbound/outbound headers |
| Traces intermittently missing spans | Sampling, async context propagation, queue/drop, or exporter error | Check sampling, reporter logs, and concurrency paths |
| Spans appear slowly | Reporter batching, network, or collector/storage/UI delay | Measure timestamps of span end, send, receive, and search |
| Unusual spike in span counts | Duplicate instrumentation, real retries, or overlapping layers | Check span names, parent–child tree, and call counts |
| Span shows no error despite ERROR log | Logging did not notify Observation or exception was recovered | Call `observation.error(ex)` when appropriate; inspect mapping |
| Zipkin lacks full history | Low sampling, retention/storage limits, or pre-publish data loss | Check sampling, backend retention, and shutdown/reporter queues |
| Trace ID missing from logs | Logging correlation unconfigured or context lost | Check MDC/pattern and async context propagation |

### Diagnostic Workflow

1. Send an identifiable test request and record its timestamp and response.
2. Confirm the Observation/span is created in the application.
3. Confirm the sampler selects the trace and the reporter receives the finished span.
4. Check the endpoint and network path to `/api/v2/spans`.
5. Check Zipkin server logs / collector metrics to see whether payloads arrive.
6. Search the right service and time window in the UI/API.
7. Compare trace IDs across services; if they differ, inspect propagation.
8. After fixing, re-run the same test request and compare the waterfall.

## 16. Real-World Scenario: order-service Calls inventory-service

**Context.** After deploying a new release, `order-service` sees order-creation latency jump from 150 ms to 800 ms. The HTTP error rate barely rises because the application falls back when inventory is slow.

### Step 1 — Metrics Detect the Trend

Dashboards show `orders.create` p95 rising alongside a higher rate of `outcome=fallback`. Metrics pinpoint the affected service and start time.

### Step 2 — Pick a Trace in Zipkin

Search for a trace with operation `GET /orders` inside the incident window. The waterfall might show:

~~~text
order-service: GET /orders                   790 ms
  order-service: orders.create                780 ms
    order-service: inventory.reserve (CLIENT) 690 ms
    order-service: orders.fallback              50 ms
~~~

If the client span is marked with an error/timeout, inspect its tags and recorded exception/event metadata. If `inventory-service` has a corresponding server span, check the shared trace ID and server-side processing time.

### Step 3 — Classify the Issue

- Client span 690 ms while server span is only 50 ms: time may be spent in connection setup, pooling, networking, queuing, or before/after the server handler.
- No server span: the request may not have reached the service, or propagation/instrumentation is missing.
- Two services have different trace IDs: inspect B3/W3C headers and the client builder.
- No trace visible: inspect sampling and reporter/exporter before concluding no request happened.

### Step 4 — Fix and Verify

After tuning connection pools/timeouts or fixing the slow dependency, repeat the test. Check p95/error/fallback metrics, client/server spans, and logs by trace ID. Never conclude an issue is resolved from a single clean trace; verify across a representative volume of requests in metrics.

## 17. Practice Exercises and Self-Check Questions

### Exercise A — Build a Local Zipkin Pipeline

1. Start a Zipkin container exposing port `9411`.
2. Add Actuator, the Micrometer Tracing Brave bridge, and Zipkin Reporter dependencies matching the Spring Boot BOM.
3. Set `management.zipkin.tracing.endpoint` to `http://localhost:9411/api/v2/spans` if running the app directly on the host.
4. Set a high sampling probability in the learning environment.
5. Create a REST endpoint and a custom business Observation.
6. Call the endpoint several times and find the trace in the Zipkin UI.

### Exercise B — Verify Propagation

1. Have `order-service` call `inventory-service` through an instrumented HTTP client.
2. Verify client/server spans share the same `traceId` and proper parent–child linkage.
3. Intentionally configure incompatible propagation formats in a test environment.
4. Observe the split trace, then align on B3 or W3C propagation.
5. Re-verify using trace IDs and headers rather than inferring from service names alone.

### Exercise C — Sampling and Reporter

1. Run 20 requests at 100% sampling and observe trace counts with healthy exporting.
2. Lower sampling, send another batch of requests, and compare trace counts.
3. Introduce delay in the exporter/collector in a test environment and observe how long traces take to appear.
4. Temporarily stop Zipkin, inspect reporter logs/behavior, and observe recovery when the server comes back.
5. Explain why metrics still count every request even when traces only show a sample.

### Exercise D — Security and Data Quality

Inspect spans:

- Do span names contain order IDs or URLs with per-request identifiers?
- Are sensitive tags such as tokens, emails, cookies, or payloads present?
- Are operation names stable and searchable?
- Are duplicate spans appearing because both `@Observed` and manual Observations wrap the same boundary?
- Are log trace/span correlation and async executor context propagation preserved?

### Self-Check Questions

1. How do the Micrometer Tracing bridge, Brave tracer, Zipkin Reporter, and Zipkin server differ?
2. Why might the UI show no traces even when the endpoint is configured properly?
3. What path does Zipkin's v2 span ingestion endpoint typically use?
4. Should sampling probability `1.0` be used by default for high-volume production traffic?
5. Can reporter batching delay span visibility? Why?
6. When running on the same Docker network, why can `localhost:9411` be wrong?
7. How do B3 and W3C Trace Context relate to stitching traces across services?
8. Does a span attribute automatically become a metric label or propagate like baggage?
9. If a trace is dropped by sampling, do metrics still increment?
10. Why shouldn't Zipkin replace a durable audit/event store?
11. When only a server span appears, what should you check on the HTTP client?
12. If client and server spans have different trace IDs, which components need investigation?

**Completion criteria:** configure Brave/Zipkin Reporter in Spring Boot; explain the span path to the collector; generate and locate a trace; understand sampling, batching, endpoint/networking, and B3/W3C propagation; analyze a cross-service trace; protect data and avoid double instrumentation.

## 18. Takeaways

- The **Zipkin exporter** ships finished spans from the tracer to the Zipkin collector; it does not create instrumentation by itself.
- In Spring Boot 3.x examples, a common stack is `micrometer-tracing-bridge-brave` with `zipkin-reporter-brave`; use the BOM for compatible dependencies.
- The v2 span ingestion endpoint typically uses `/api/v2/spans`; use an address reachable from the application's network namespace.
- Sampling decides which traces are kept; reporter batching and networking determine when spans reach the backend. A missing trace does not prove a request never happened.
- B3/W3C propagation must match across services so spans belong to the same trace; client integrations must inject headers and servers must extract context.
- The Zipkin UI helps analyze waterfalls, services, operations, durations, and tags; metrics remain the source of truth for error/latency rates, and logs provide detailed event context.
- Keep tags/attributes safe with bounded cardinality; never send tokens, sensitive payloads, or per-request IDs as metric labels.
- Monitor reporter/collector errors, queues/drops, shutdown behavior, and storage retention. Tracing is operational telemetry, not a replacement for durable audit systems.

## References

- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Tracing — Brave setup](https://docs.micrometer.io/tracing/reference/api.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenZipkin — Zipkin quickstart](https://zipkin.io/pages/quickstart)
- [OpenZipkin — Zipkin API](https://zipkin.io/zipkin-api/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
