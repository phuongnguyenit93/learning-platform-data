# Impact of Logging, Tracing, and Body Transformations

## 1. Context: Gateway Performance Is More Than Upstream Call Time

In a microservices architecture, **Spring Cloud Gateway** sits in the path of many HTTP requests. The Gateway selects routes via predicates, runs filter chains, rewrites paths/headers, resolves service instances, and calls backends; authentication, rate limiting, circuit breakers, retries, TLS, and request observability all run along that same path.

A typical request flow:

~~~text
Client ──HTTP──> Gateway ──HTTP──> order-service
                  │
                  ├─ route predicates
                  ├─ authentication/authorization
                  ├─ path/header filters
                  ├─ rate limiting / resilience
                  ├─ HTTP client / TLS
                  └─ metrics / logs / tracing
~~~

Because the Gateway processes centralized traffic, a seemingly minor change—enabling `DEBUG`, logging entire bodies, sampling 100% of traces, or adding a JSON rewrite—can drive up CPU, memory allocations, disk/network I/O, and latency for **every request passing through the route**.

For example:

- At low traffic, an extra log line is barely visible in p50.
- As request volume rises, synchronous logging or backed-up span exports can make **p99** spike sharply even though the upstream has not changed.
- Switching from streaming to decoding/re-encoding full JSON bodies increases **heap/pooled buffer** usage proportionally to body size and concurrent requests.
- Wiretap or misconfigured header/body logging can **leak tokens or PII**, creating security risk beyond performance.

This lesson, **"Impact of Logging, Tracing, and Body Transformations,"** belongs to the **Performance** chapter of the **SPRING_CLOUD_GATEWAY** module. We analyze the real cost of each mechanism, how to measure it with controlled benchmarks, and how to pick production-ready settings.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **access logs**, **application logs**, **Reactor Netty wiretap**, **traces**, and **metrics**.
2. Explain the CPU, I/O, allocation, queue, and backpressure costs of each observability mechanism.
3. Configure logging and tracing appropriately for Gateway Server WebFlux, recognizing 4.x vs. 5.x differences.
4. Understand why `ModifyRequestBody`/`ModifyResponseBody`, body caching, and body logging can break streaming advantages.
5. Read p50/p95/p99 latency, throughput, error rates, event-loop lag, heap/GC, direct memory, and exporter drops.
6. Design a benchmark progression: **baseline → enable one mechanism at a time → combine → test under high load**.
7. Write HTTP tests against a mock upstream to verify body/header/status correctness alongside performance measurements.
8. Propose logging, sampling, payload-size, rate-limiting, and alerting policies before production.

> **Scope:** The focus is **Spring Cloud Gateway Server WebFlux** on Reactor Netty. Server Web MVC runs on Servlets and uses different executors and filters; principles regarding CPU, I/O, and buffering still hold, yet **never copy WebFlux `GlobalFilter`, `DataBuffer`, or Netty settings** directly onto Server Web MVC. Properties that depend on the Spring Cloud Gateway / Spring Boot release train are noted explicitly; verify against your actual version.

## 2. Setting Up a Measurement Model: Latency, Throughput, and Resources

### 2.1. End-to-End Latency Has Multiple Components

A request can spend time across:

~~~text
Client -> Gateway:
  network_in
  + accept / decode / security / route match
  + request filters
  + acquire outbound connection / DNS / TLS
  + upstream processing / network
  + response filters
  + write response / network_out

Plus (when enabled):
  log formatting + log sink I/O
  trace observation / span creation + exporter pressure
  body decoding + transformation + encoding
  GC/allocator pressure + scheduler/queue contention
~~~

Do not mechanically sum these terms as though they are **always sequential**: HTTP streaming, asynchronous queues, and concurrency cause stages to overlap. This breakdown is valuable for **forming hypotheses** and placing instrumentation, not as an exact adder for every request.

### 2.2. Metrics You Must Collect

| Metric | Reflects | When rising, consider |
| --- | --- | --- |
| **RPS / throughput** | Requests completed per second | Load capacity and saturation |
| **p50 latency** | Typical request experience | Average per-hop cost |
| **p95/p99 latency** | Tail latency, slow requests | Queueing, I/O blocking, GC, slow backends |
| **Error rate** | 4xx/5xx/timeouts per route | Overload, upstream failures, policies |
| **CPU usage / throttling** | Compute usage and cgroup quota | Serialization, logging, GC, TLS |
| **Heap used / allocation rate** | Java objects and GC pressure | JSON/log objects, body copies |
| **Direct/pooled memory** | Netty off-heap buffer memory | Payload/buffer retention, leaks |
| **GC pause and frequency** | Garbage collector pauses | Allocation pressure, memory sizing |
| **Active outbound connections** | HTTP client pool | Concurrency, connection bottlenecks |
| **Event-loop lag / blocked threads** | Whether Reactor Netty event loops are held too long | Sync logging, JSON parsing, file I/O |
| **Log queue / dropped logs** | Logging pipeline pressure | Async appender capacity, slow sinks |
| **Span export queue / drops** | Tracing pipeline pressure | Sampling rate, collector errors, OTLP timeouts |
| **Bytes in/out** | Network volume | Body logging, payload expansion, retries |
| **Backend p95/p99** | Upstream latency | Separating Gateway issues from service issues |

**The optimization goal is preserving the HTTP contract and security within a resource budget**, not chasing peak RPS by turning off all logging and tracing.

### 2.3. Watch Tail Latency, Not Just the Average

Example **hypothetical illustrative numbers**, not a real benchmark run:

| Scenario | RPS | p50 | p95 | p99 | Gateway CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| Simple baseline route | 1,200 | 14 ms | 29 ms | 46 ms | 38% |
| Add per-request metadata logging | 1,180 | 15 ms | 32 ms | 53 ms | 44% |
| Enable wiretap under heavy load | 890 | 20 ms | 71 ms | 160 ms | 79% |
| Rewrite large JSON bodies | 760 | 23 ms | 95 ms | 210 ms | 86% |

These numbers merely illustrate **plausible directions**. Never treat them as rules like "wiretap is always 31% slower" or "body rewrites always add 5 ms": real impact depends on hardware, payloads, log sinks, tracers, sampling, TLS, upstreams, and concurrency.

## 3. Cost of Logging: Five Layers to Distinguish

### 3.1. Access Logs

An **access log** is typically one line per HTTP request containing method, path, status, duration, or bytes, depending on formatter and server. It is useful for spotting traffic and errors at the Gateway boundary.

Characteristics:

- Can emit one record for **every request**.
- Cost lies mainly in **formatting, queueing, writing, and shipping logs**.
- Much cheaper than body logging when restricted to bounded metadata.
- Can still cause cardinality/PII leaks if logging raw URLs/queries containing tokens or emails.
- If the sink backs up, appenders or stdout/container logging can exert backpressure onto request threads.

Access logs are not traces: they do not automatically draw the Gateway → order → inventory call tree.

### 3.2. Application Logs in Filters and Business Code

Example:

~~~java
log.info("route={} method={} status={}",
        routeId, method, status);
~~~

One line may be cheap; however, if **each filter** emits 2–3 lines per request, total log events scale with filter count × RPS.

Suppose 2,000 RPS × 6 records/request:

~~~text
2,000 requests/s × 6 log events/request
  = 12,000 log events/s

Assuming 1 event ≈ 400 bytes (hypothetical):
  ≈ 4.8 MB/s raw log content, before framing/metadata/compression
~~~

This calculation is only a **log-pipeline capacity estimate**, not a Spring Cloud Gateway benchmark. In reality, log formatters, JSON encoding, stdout drivers, collectors, and indexing alter byte volumes substantially.

### 3.3. Reactor Netty Wiretap

**Wiretap** is Reactor Netty's HTTP client/server connection-level debug facility. When configured with an appropriate flag and log level, it logs network activity and even **raw bytes/headers/payloads** depending on the wiretap format.

Wiretap **must not stay enabled continuously** on a loaded production Gateway because:

- It emits a huge volume of I/O-level log events.
- Converting bytes → strings/hex/log objects drives CPU and allocations.
- Logging can run close to the event loop or saturate async queues, raising tail latency.
- It can log HTTP `Authorization` headers, cookies, request/response bodies, and PII.
- Impact depends on log levels and formatting; enabling the property without matching logger levels may yield no output at all.

### 3.4. Full Body Logging

Body logging carries even higher risk than access logging:

- Requires observing/reading payload bytes, often forcing **caching or copying** so the pipeline can still forward the body.
- Large bodies consume substantial memory under high concurrency.
- Formatting bytes as UTF-8/JSON can trigger extra decoding passes.
- The log sink absorbs roughly request/response size × traffic volume.
- Payloads contain credentials and PII; redacting **after dumping to logs** is already too late.

In the Gateway, body logging must never be implemented by calling `.subscribe()` on the request body and reading bytes independently: reactive bodies are single-use/bounded streams that get exhausted or leak if `DataBuffer` ownership is mishandled.

### 3.5. Structured Logs

JSON logs aid querying and parsing, while also spending CPU and bytes:

~~~json
{
  "service": "edge-gateway",
  "routeId": "orders-api",
  "method": "POST",
  "status": 201,
  "durationMs": 28,
  "traceId": "example-trace-id"
}
~~~

This is an **illustrative schema**, not automatic Gateway output. Place high-cardinality fields (raw paths, trace IDs, user IDs) inside **protected log events**, never as **metric labels**. Do not assume structured JSON is always faster or slower than plain text: benchmark your specific formatter, async appender, collector, and storage.

## 4. Configuring Gateway WebFlux Logging by Version

### 4.1. Gateway Server WebFlux 4.x: Temporary Wiretap Only

In an **isolated local/staging** environment, 4.x branches commonly use:

~~~yaml
spring:
  cloud:
    gateway:
      httpserver:
        wiretap: true
      httpclient:
        wiretap: true

logging:
  level:
    reactor.netty: DEBUG
~~~

Verify property and logger names against your exact Spring Cloud Gateway and Reactor Netty releases. Setting `reactor.netty: DEBUG` broadly can emit far more output than expected; narrow the logger to the specific package/class used by your version.

**Use only for short-lived investigations** with test/synthetic traffic. Never enable wiretap on public production traffic to debug errors by capturing raw `Authorization` headers or bodies.

### 4.2. Gateway Server WebFlux 5.x: New Namespace

Gateway 5.x configuration docs specify:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpserver:
            wiretap: true
          httpclient:
            wiretap: true

logging:
  level:
    reactor.netty: DEBUG
~~~

The newer property paths are verified in docs as `spring.cloud.gateway.server.webflux.httpserver.wiretap` and `spring.cloud.gateway.server.webflux.httpclient.wiretap`.

**Do not set both 4.x and 5.x namespaces** hoping one takes effect. An unbound prefix can silently leave wiretap off while you think it is on, invalidating your benchmark.

### 4.3. Reactor Netty Access Log Is Configured Differently from Wiretap

For the Reactor Netty HTTP server, the characteristic system property is:

~~~text
-Dreactor.netty.http.server.accessLogEnabled=true
~~~

Example when launching a JAR in a lab:

~~~bash
java -Dreactor.netty.http.server.accessLogEnabled=true -jar gateway.jar
~~~

This system property must be set **before the Reactor Netty HTTP server is created**. It is **not** `spring.cloud.gateway.httpclient.wiretap`. Access logs and wiretap differ in scope and granularity.

Pass Java process options appropriate to your deployment; never roll out debug flags across all production replicas without change approval, retention limits, and data protection.

### 4.4. What Should a Normal Baseline Look Like?

A safer baseline:

~~~yaml
spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      server:
        webflux:
          httpserver:
            wiretap: false
          httpclient:
            wiretap: false
          observability:
            enabled: true

logging:
  level:
    root: INFO
    reactor.netty: WARN
~~~

This snippet illustrates the **Gateway Server WebFlux 5.x** branch; not every project must use `root: INFO` verbatim. What matters is **keeping network/body debug logging off permanently** while keeping metrics and observability responsibly configured.

In production, keep **sanitized metadata access logs** and **sampled/structured error logs**; never silence logging so completely that incidents become uninvestigable.

## 5. Designing Logs Around Cost and Operational Needs

### 5.1. Minimal Structured Log

Information usually sufficient for route investigations:

| Field | Example | Notes |
| --- | --- | --- |
| timestamp | UTC | Enables timeline correlation |
| service/environment | edge-gateway / production | Never include secrets |
| routeId | orders-api | Stable identifier |
| method | GET | Low-cardinality |
| route pattern | `/api/orders/**` | Better than raw paths with user IDs |
| status/outcome | 201 / success | Grouped status |
| duration | 28 ms | Metrics can replace per-log timing |
| traceId/spanId | Identifier string | Only when tracing scope is valid |
| error category | timeout/connect/tls | Never log raw exceptions containing secrets |
| upstream group | ORDER-SERVICE | No personal IPs or sensitive URLs |

Do not dump all headers or bodies when all you need to know is which route slowed down.

### 5.2. Log Conditionally—Never Build Strings Before Checking the Level

Avoid:

~~~java
// ANTI-PATTERN: serialization runs even before the log call.
log.debug("body=" + expensiveJsonSerialization(payload));
~~~

Even when `DEBUG` is off, `expensiveJsonSerialization(payload)` **still executes** because Java evaluates arguments before invoking the logger.

Better:

~~~java
if (log.isDebugEnabled()) {
    log.debug("route={} payloadSizeBytes={}",
            routeId, safeBodyLength);
}
~~~

Prefer **payload size** over payload content. For sensitive data, never pass sensitive objects to loggers even at `DEBUG`; an accidentally enabled debug flag would expose them.

Even with SLF4J 2 fluent/lazy suppliers, verify that the supplier is truly lazy in your logger implementation; never build a full JSON `String` before passing it into a supplier and call it "lazy."

### 5.3. Async Logging: Cuts Blocking, Not Free

Async appenders move heavy formatting/writing off the request path. Still:

~~~text
Request/event loop
  -> enqueue log event
  -> bounded/unbounded queue
  -> async worker
  -> stdout/file/network collector
~~~

Trade-offs include:

- **Bounded queues:** can drop logs when full, losing audit or debug records.
- **Unbounded queues:** can accumulate in memory and trigger OOM.
- **Blocking enqueue:** can still block the event loop once the queue fills.
- **Context capture:** copying MDC and arguments carries overhead.
- **Shutdown:** must flush cleanly without hanging the request path indefinitely.

Async appenders do not eliminate event creation or field serialization costs. When logs serve **mandatory audit** purposes, drop policies differ from ordinary debug logs.

### 5.4. Log Sampling

Often a better strategy than logging everything:

- Log **errors/timeouts** with appropriately redacted context.
- Log **metadata for a stable sampled fraction of successful requests**.
- Maintain metrics for **100% of traffic** where cost permits.
- Allow temporary, time-bounded debug elevation on **a single replica or route**.
- Never use uncontrolled user identities as sampling seeds; consider fairness and privacy.

Access-log sampling **is not the same as trace sampling**. Do not assume "1% logs" captures the exact same 1% of requests as sampled trace spans unless you align correlation strategies.

## 6. Example `GlobalFilter` Timing Duration: Limits of Custom Logging

In Gateway Server WebFlux, a `GlobalFilter` participates in the **Gateway filter chain of a matched route**. Example logging metadata after the chain completes:

~~~java
package example.gateway.performance;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class MinimalRouteTimingFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(MinimalRouteTimingFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, GatewayFilterChain chain) {

        return Mono.defer(() -> {
            long startedAt = System.nanoTime();

            return chain.filter(exchange)
                    .doFinally(signal -> {
                        long millis =
                                (System.nanoTime() - startedAt) / 1_000_000L;

                        Route route = exchange.getAttribute(
                                ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR);
                        String id = route != null
                                ? route.getId() : "unknown";

                        if (log.isInfoEnabled()) {
                            log.info(
                                "route={} method={} status={} durationMs={} signal={}",
                                id,
                                exchange.getRequest().getMethod(),
                                exchange.getResponse().getStatusCode(),
                                millis,
                                signal);
                        }
                    });
        });
    }

    @Override
    public int getOrder() {
        return -10;
    }
}
~~~

**Key points to understand:**

1. `Mono.defer` starts the clock on subscription, avoiding measuring pre-execution assembly time.
2. `doFinally` fires on completion, error, or cancellation; `signal` distinguishes how the chain terminated.
3. `routeId` comes from the exchange attribute; raw URLs are never used as log labels.
4. It reads no body and logs no tokens, cookies, query strings, or PII.
5. `status` can be `null` if no status was set yet or an early error occurred; never treat `null` as 200.
6. `doFinally` is a synchronous callback; **a slow log sink can keep the event loop busy longer**.
7. This filter runs inside the **route filter chain**, so requests matching no route or blocked earlier by Spring Security may **never hit it**.
8. This is an **illustrative example**, not a replacement for built-in Gateway/Micrometer observations. When automatic metrics/tracing already exist, adding per-request logs duplicates data at higher cost.

In production, prefer framework-provided observations and metrics over stacking custom timing `GlobalFilter`s; log only custom events not covered by built-in telemetry.

## 7. Cost of Distributed Tracing

### 7.1. What Work Does Tracing Add?

A trace across the Gateway and downstream services can include:

~~~mermaid
flowchart TD
    C["Client"] --> G["Gateway SERVER span"]
    G --> GC["Gateway HTTP CLIENT span"]
    GC --> O["order-service SERVER span"]
    O --> IC["inventory HTTP CLIENT span"]
    IC --> I["inventory-service SERVER span"]
    G --> E["Exporter / Collector"]
    O --> E
    I --> E
~~~

Each span can involve:

- Generating IDs or extracting parent context.
- Recording timestamps, attributes, statuses, and exceptions/events.
- Propagating context across reactive async boundaries.
- Injecting `traceparent` into outbound HTTP headers.
- Evaluating sampling decisions.
- Serializing and exporting spans (typically batched).
- Queueing and buffering toward the Collector/backend.

**Propagation and export are separate concerns.** The Gateway can forward W3C `traceparent` so downstreams link traces even when certain spans are unsampled for export. Conversely, a request with valid headers can still be missing from the trace UI if the Collector errored or an export queue dropped spans.

### 7.2. Tracing Overhead Is Not a Constant

Overhead depends on:

- Spans per request and hop count.
- Sampling probability / parent-based sampling.
- Number of attributes/events/links and string sizes.
- Baggage/`tracestate`; header counts and payload bytes.
- Whether full exception stack traces are attached to spans.
- SDK bridge: Micrometer Tracing / Brave / OpenTelemetry / Java agent.
- Exporter batching/queues/timeouts and network path to the Collector.
- Tracer context propagation across Reactor.
- Behavior when the Collector slows down, disconnects, or throttles.

Setting `management.tracing.sampling.probability: 0.1` **does not guarantee a 90% drop in all tracing overhead**: propagation, context handling, and partial observation still run. It primarily cuts **sampled span volume and export work** per policy.

### 7.3. You Can Enable Metrics Without Tracing 100% of Requests

A balanced observability setup typically looks like:

| Signal | Coverage | Purpose |
| --- | --- | --- |
| Aggregated HTTP/route metrics | Most or all requests where affordable | SLOs/RPS/statuses/latency |
| Metadata error logs | Per error policy | Incident investigation |
| Access logs | Selective/sampled | Reasonable correlation and auditing |
| Distributed traces | Controlled sampling | Investigating slow requests/hops |
| Wiretap | Short-term debug only | Network/protocol diagnostics |
| Full body dumps | Avoid; synthetic/redacted only when essential | Debugging broken contracts |

When sampling traces, **do not compute p99 SLOs from arbitrarily sampled spans** without accounting for bias. Dedicated timers/metrics are far better suited for whole-traffic SLOs.

## 8. Configuring Tracing for Spring Boot 3.5 and 4.x

### 8.1. Spring Boot 3.5 with Micrometer Tracing and OTLP

In a Spring Boot 3.5 project with compatible Spring Cloud Gateway 4.x, a common Maven combination is:

~~~xml
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
~~~

Illustrative **lab** configuration:

~~~yaml
spring:
  application:
    name: edge-gateway

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

`probability: 1.0` is for **low-traffic labs only**. In production, test lower sampling rates, size capacity/retention, verify parent-based sampling, and secure the OTLP export path.

`localhost:4318` inside containers only works when the Collector runs in the same network namespace's loopback. In Kubernetes, use the appropriate Service DNS, node agent, or sidecar per your architecture.

### 8.2. Spring Boot 4.x with the OpenTelemetry Starter

For Spring Boot 4.x, official docs introduce:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
~~~

Illustrative config using the newer property group:

~~~yaml
spring:
  application:
    name: edge-gateway

management:
  tracing:
    sampling:
      probability: 0.1
  opentelemetry:
    otlp:
      endpoint: http://otel-collector:4318
~~~

Or use trace-specific OTLP exporter properties `management.opentelemetry.tracing.export.otlp.*` when supported by your version and separate configuration is needed. **Do not swap them blindly** with Boot 3.x's `management.otlp.tracing.endpoint`.

Setting sampling to `0.1` here is a **tracing budget example**, not a mandatory rule for all traffic. Across multi-hop upstreams, tail sampling or error-trace policies may fit well when the Collector is properly sized.

### 8.3. Enabling Tracing Does Not Automatically Enable Gateway Routing Metrics

In Gateway WebFlux 5.x, configuration docs include:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          observability:
            enabled: true
          metrics:
            enabled: true
            path-tags:
              enabled: false
~~~

`observability.enabled` controls Gateway Micrometer observation integration; `metrics.enabled` enables Gateway route metrics when the supporting infrastructure is present. **Do not enable raw path tags** for performance measurement: dynamic path IDs create high cardinality.

In Gateway 4.x, properties may sit under `spring.cloud.gateway.observability.*` and `spring.cloud.gateway.metrics.*`. Always check `configprops` for your release; misplaced properties silently make a "tracing on vs. off" benchmark test the exact same state.

## 9. Sampling, Exporters, and Queue Contention Risks

### 9.1. Relationship Between Sampling and Span Volume

Suppose one request produces an average of 5 sampled spans across the system at 1,000 RPS:

~~~text
At 100% sampling if every request emits 5 spans:
  1,000 requests/s × 5 spans/request = 5,000 spans/s

At ~10% sampling under a simple policy:
  ~500 sampled spans/s
~~~

This is an **illustrative estimate**, not measured throughput. Actual span counts shift when circuit breakers block calls, retries add attempts, some services are uninstrumented, or parent/tail samplers apply different policies.

### 9.2. Exporters Must Not Turn the Gateway Into a Bottleneck

Exporters typically use bounded queues, batching, and background workers, yet still have limits. When the Collector slows down:

- Queues accumulate sampled spans.
- Export timeouts and retries in the telemetry pipeline burn network and CPU.
- Full queues **drop spans**, leaving gaps in the trace UI.
- If an exporter or custom instrumentation blocks, request latency can suffer.
- Impact depends on the SDK/exporter; never claim all exporters block Gateway event loops.

Monitor dropped spans/export failures, queue utilization, CPU/memory, and **request disruption** when testing with the Collector offline.

### 9.3. Tail-Based Sampling

Tail sampling at the Collector retains traces containing errors or high latency after inspecting spans. It helps capture rare failures, yet:

- The Collector needs full trace data in memory until making a decision.
- Buffering, timers, HA, and trace-ID-based sharding add infrastructure cost.
- If ingress or tracers dropped spans upstream, the Collector **cannot recover spans never exported**.
- Huge traces and traffic bursts can cause memory pressure in the Collector.

**Do not assume tail sampling eliminates span-creation overhead at the Gateway**: instrumentation and export to the Collector still happen before the final keep/drop decision.

## 10. Reactor Context: Boundary Between Clean Tracing and Needless Overhead

Gateway WebFlux uses **reactive, non-blocking execution**. A single request can hop across threads; if tracing or logging code relies on `ThreadLocal` or `MDC` without proper context propagation, log correlation breaks.

Counterproductive example:

~~~java
MDC.put("traceId", requestTraceId);
// Continues reactive chain while forgetting cleanup or switching threads.
return chain.filter(exchange);
~~~

Problems:

- `MDC` is usually thread-bound; reactive operators can resume on a different thread.
- `ThreadLocal` does not represent the logical subscriber context.
- Without cleanup, a reused event-loop thread can carry stale metadata from an earlier request.
- Manual scope/context copying in every filter adds overhead and bugs.

The right approach is **using Micrometer Tracing and Reactor Context Propagation** per your framework version so server/client scopes and log correlation are managed consistently.

### 10.1. Never Call `subscribe()` Independently Just to Log or Trace

~~~java
// ANTI-PATTERN: detached subscription outside the main request lifecycle.
someWebClient.get()
    .uri("/debug")
    .retrieve()
    .bodyToMono(String.class)
    .subscribe();
~~~

Failures include lost parent traces, unintended extra traffic, and unhandled errors/cancellations. For genuine side work, compose the `Mono` into the chain with proper timeouts, authorization, and observability.

### 10.2. Never Block the Event Loop to Ship Logs or Traces

Never write:

~~~java
// ANTI-PATTERN: never do this on a Reactor Netty event loop.
String data = blockingHttpClient.call();
Files.writeString(logPath, data);
~~~

inside a `GlobalFilter` assuming Reactor magically makes it non-blocking. Blocking I/O, heavy synchronous JSON serialization, or large cryptographic work stalls unrelated requests sharing that event-loop thread.

When small bounded blocking work is unavoidable, isolate it onto a dedicated scheduler/executor with queue concurrency caps and measure overhead. **`boundedElastic` is not magic** for hiding CPU-bound JSON transforms or unbounded output.

## 11. Body Transformations: Small Feature, High Cost

### 11.1. Plain Streaming vs. Body Rewriting

A route modifying only paths or headers streams the body directly:

~~~text
Inbound DataBuffer stream
      │
      ├─ match route
      ├─ rewrite path/headers
      └─ stream DataBuffer to upstream
~~~

Adding `ModifyRequestBody` or `ModifyResponseBody` changes the pipeline:

~~~text
Inbound byte stream
      │
      ├─ read/aggregate/decode via body readers and target type
      ├─ materialize String/DTO/JsonNode
      ├─ transformation
      ├─ encode back to bytes
      └─ send new stream/buffer to upstream/client
~~~

Rewriting usually requires **buffering enough of the body to convert types and transform it**. Costs can include:

- Reading/aggregating buffers and raising peak live bytes.
- Charset decoding and JSON parsing.
- Building object graphs and running mapping logic.
- Serializing and encoding.
- Recomputing or stripping `Content-Length` when body size changes.
- Pressure on heap, direct memory, GC, and the Netty allocator.
- Added latency while waiting for data before rewriting.

**Do not assume every filter always buffers the entire body**: exact behavior depends on the filter, codec, and streaming strategy. Still, rewriting bodies via `String` or DTO types clearly signals the need for explicit buffering and concurrency budgets.

### 11.2. Concurrent-Request Memory Math

Hypothetical **theoretical estimate**, not live JVM measurements:

~~~text
Concurrent requests:              500
Body size per request:            1 MiB
Coexisting live body equivalents: 2

Estimated live payload:
  500 × 1 MiB × 2 = 1,000 MiB (~0.98 GiB)

Not yet counting:
  + object graphs / char[] / JsonNode / serialization buffers
  + Netty direct pooled buffers
  + request/response metadata
  + remaining app heap and GC headroom
~~~

A Gateway with a 1 GiB heap cannot safely assume this workload fits. In production, copy counts vary, payload sizes have long tails, and requests hold multiple byte/char buffer forms. **Measure peak heap + direct memory + GC directly**, rather than treating simple multiplication as an exact limit.

### 11.3. Why Does p99 Suffer Heavily?

At low traffic, parsing one 100 KiB JSON payload looks fast. Under heavy load, many concurrent bodies waiting for processing will:

- Drive up allocation rates.
- Increase GC pause time and memory pressure.
- Build queues in HTTP client pools or schedulers.
- Tie up Netty event loops if CPU-heavy transforms run inline.
- Drag unrelated small-payload requests into high tail latency.

Therefore, benchmarks must vary **payload size × concurrency × RPS**, not merely fire a single small JSON request.

## 12. Java DSL Example for `ModifyRequestBody` and `ModifyResponseBody`

For Gateway **Server WebFlux**, official docs describe these two filters as **configured via Java DSL**, rather than a simple YAML shortcut like `StripPrefix=1`.

An educational example intentionally transforming **`text/plain`** to make decode/encode cost easy to inspect:

~~~java
package example.gateway.performance;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.http.MediaType;
import reactor.core.publisher.Mono;

@Configuration
public class BodyTransformationRoutes {

    @Bean
    RouteLocator transformDemo(RouteLocatorBuilder builder) {
        return builder.routes()
                .route("text-transform-demo", r -> r
                    .path("/lab/transform/**")
                    .filters(f -> f
                        .stripPrefix(1)
                        .modifyRequestBody(
                            String.class,
                            String.class,
                            MediaType.TEXT_PLAIN_VALUE,
                            (exchange, body) -> body == null
                                ? Mono.empty()
                                : Mono.just(body.toUpperCase(Locale.ROOT)))
                        .modifyResponseBody(
                            String.class,
                            String.class,
                            (exchange, body) -> body == null
                                ? Mono.empty()
                                : Mono.just("gateway:" + body)))
                    .uri("http://localhost:8081"))
                .build();
    }
}
~~~

**Use only on a lab endpoint**—never upper-case arbitrary payloads in production:

- Requests with text body `hello` become `HELLO` before reaching the upstream.
- Text responses `ok` from the upstream become `gateway:ok` before reaching the client.
- Verify codecs and `Content-Type` with real tests; this example assumes valid `text/plain`.
- When a body is **absent**, the rewrite callback can receive `null`; return `Mono.empty()` to preserve the bodyless state.
- `modifyRequestBody` accepts `newContentType` to declare the output representation; `modifyResponseBody` uses the corresponding media-type writers/config.
- Responses with 204/HEAD or compression need separate tests; never assume rewriting produces a body for every status.
- Even a `String` transform forces the Gateway to decode/encode and allocate new objects; measure performance across payload sizes.

This example **does not log request/response bodies**. Combining body transformation with body logging adds extra decode/copy passes and raises data-exposure risk.

### 12.1. JSON Transformation Costs More

A filter like `modifyRequestBody(String.class, DomainDto.class, APPLICATION_JSON_VALUE, rewriteFn)` can:

1. Decode the input `String`.
2. Parse/map into a `DomainDto` object.
3. Transform fields.
4. Serialize back to JSON.
5. Encode bytes.

**Do not pick `String.class` and manually parse JSON in every filter out of habit.** With well-configured codecs and types, pick appropriate target types to avoid redundant steps. Even then, JSON codecs carry allocation and validation costs—measure them.

If you only need to **add or remove a request header** or rewrite a path, use header/path filters instead of parsing the entire body. Keep routing concerns separate from business payloads whenever possible.

### 12.2. Handling Empty Payloads Properly

When a body is missing, `null`, `Mono.empty()`, and JSON literal `null` **are not necessarily equivalent**. Never call `Mono.just(null)` (Reactor forbids null values). For REST contracts, test:

- No body.
- Zero-length body.
- Body containing JSON literal `null`.
- Empty JSON object `{}`.
- Mismatched `Content-Type`.
- Body exceeding size limits.

Never rewrite bodies of requests blocked prior to routing (such as a 401 from Spring Security) as if route filters always ran.

## 13. `DataBuffer`, Pooling, Backpressure, and Memory Bounds

### 13.1. `DataBuffer` Is Not an Unmanaged `byte[]`

Spring WebFlux represents streaming bodies as `DataBuffer`s, backed by Reactor Netty's buffer pools. Any custom filter reading bodies must obey **ownership and release rules**, or else you risk:

- Consuming the body stream so the upstream receives an empty body.
- Retaining buffers too long, inflating direct memory.
- Double-releasing or reading a buffer after release.
- Breaking backpressure and growing queues unboundedly.
- Caching huge payloads until OOM.

Spring WebFlux provides `DataBufferUtils`, `DataBufferLimitException`, and decoding/aggregation helpers where needed. **Never call unbounded `DataBufferUtils.join()` and retain references** merely to log requests.

### 13.2. Anti-Pattern: "Read the Body for Debugging"

~~~java
// ANTI-PATTERN — DO NOT use in a production Gateway.
exchange.getRequest().getBody()
    .subscribe(buffer -> {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        log.info("body=" + new String(bytes));
    });

return chain.filter(exchange);
~~~

Problems:

- `subscribe()` detaches from the main request lifecycle.
- Competes for/consumes the body stream needed downstream.
- Lacks charset handling, size limits, and redaction.
- Can fail to release pooled buffers cleanly.
- Synchronously logs large byte arrays.
- Fails to propagate cancellations or errors along the chain.

The better approach is usually **not logging bodies at all**. To inspect payloads, use a mock upstream in integration tests or a **purpose-built debug component with strict limits, redaction, tests, and limited lifetime**.

### 13.3. Enforcing Size Limits at the Right Layers

Different limits protect different layers:

| Mechanism | Protection |
| --- | --- |
| Gateway `RequestSize` filter | Rejects requests exceeding a configured route threshold |
| Spring WebFlux codec `maxInMemorySize` | Caps aggregation/decoding for certain operations |
| Ingress / API load balancer limit | Blocks oversized payloads before the Gateway |
| Backend size limit | Protects the target service |
| Netty connection/pool/timeouts | Bounds transport resources and wait times |
| Rate limiting / concurrency limits | Reduces aggregate request pressure |

One limit **does not replace the others**. Raising `maxInMemorySize` to "fix 413 errors" increases OOM risk when body transformations run concurrently.

### 13.4. Backpressure Does Not Protect Against Unbounded Buffers

Reactor supports backpressure, yet if a filter:

- Calls `collectList()` on an unbounded stream,
- Uses an unbounded queue,
- Caches every response body in a map,
- Uses `flatMap` with excessive concurrency, or
- Uses `publishOn` without backlog bounds,

memory can still explode. "Reactive" does not mean "immune to OOM"; design **explicit finite bounds** on sizes, concurrency, and wait durations.

## 14. Combining Body Rewrites with Retry, Compression, and Security

### 14.1. Retry Can Multiply Payload Processing

Retrying a `POST` with a body may require **caching/replaying** the body. Costs include:

- Retaining the body buffer for replay.
- Re-running filters located downstream of `Retry`.
- Multiplying outbound bytes across attempts.
- Repeating backend side effects if idempotency is missing.

Even when `Retry` applies only to `GET`, response-body buffering/filtering adds latency to each attempt. For order/payment POSTs, **never turn on retries blindly**; require `Idempotency-Key`, backend deduplication, and timeout-after-commit tests.

### 14.2. Compression Changes Body Comparisons

When an upstream returns `gzip`, wire bytes are smaller than the decompressed body. When `ModifyResponseBody` reads text/JSON:

- Codecs may or may not decompress depending on HTTP client settings.
- Rewriting the body may require re-encoding and updating `Content-Encoding`/`Content-Length`.
- Decoding and re-encoding add CPU and memory cost.
- Chunk boundaries are not guaranteed to stay identical through a proxy.

Tests must distinguish **wire bytes** from **semantic JSON/body content**. Do not compare compressed gzip bytes against UTF-8 plaintext and conclude a filter corrupted the body.

### 14.3. Body Transformation vs. Streaming Proxy

For large file uploads/downloads, a **pass-through streaming route** usually makes far more sense than converting bodies to `String` or DTOs.

For signed webhooks, changing a single byte or whitespace character can break backend signature verification. Never rewrite signed JSON payloads when the contract requires byte-for-byte preservation.

### 14.4. PII and Sensitive Content

**Do not enable request/response body logging to benchmark body transforms.** Benchmarks can use synthetic payloads and verify checksums/counters without logging real content.

Logging `Authorization` headers, cookies, passwords, refresh tokens, card numbers, or raw PII creates severe data-security exposure. "DEBUG only" does not make it safe when log aggregators, CI artifacts, and retention policies persist the logs.

## 15. Combined Impact: Logging + Tracing + Body Transformation

These three mechanisms can **multiply each other's impact** rather than merely adding up:

~~~mermaid
flowchart TD
    R["Request enters Gateway"] --> L["Metadata log / wiretap"]
    R --> T["Tracing context & sampled spans"]
    R --> B["Body decode / rewrite / encode"]
    L --> Q["Log queue / stdout / collector"]
    T --> X["Span exporter / OTLP collector"]
    B --> M["Heap + direct buffers / GC"]
    Q --> S["CPU / network / I/O pressure"]
    X --> S
    M --> S
    S --> P["Queueing / p95 p99 latency"]
~~~

For example:

1. A body transform allocates a new `String`/DTO.
2. A debug logger serializes the DTO to log the full payload.
3. Tracing instrumentation attaches oversized attributes.
4. Log collectors and OTLP exporters compete for network and CPU.
5. GC pauses and cgroup CPU throttling rise.
6. Requests on routes **that do not transform bodies** still slow down due to shared Gateway resources.

Consequently, a benchmark that "turns on all three vs. baseline" shows only **combined impact** without identifying the dominant cost. Run an **ablation study**: toggle each factor individually.

### 15.1. Controlled Experiment Matrix

| Group | Logging | Tracing | Body transform | Purpose |
| --- | --- | --- | --- | --- |
| A | Minimal metadata | Span export off or minimal sampling | None | Baseline |
| B | Metadata access log | Same as A | None | Access-log cost |
| C | 1 app log event/request | Same as A | None | Per-request log cost |
| D | Wiretap in lab | Same as A | None | Protocol debug cost |
| E | Same as A | 10% sampling | None | Low-rate tracing cost |
| F | Same as A | 100% sampling | None | High-intensity lab tracing cost |
| G | Same as A | Same as A | Small body rewrite | Transformation cost |
| H | Same as A | Same as A | Large body rewrite | Payload-size impact |
| I | Metadata log | 10% sampling | Body rewrite | Production-like combined impact |
| J | Wiretap | 100% sampling | Large body rewrite | **Lab stress/debug**, not a production profile |

Across groups A–J, document exactly which observations run in the baseline. "Turning off span export" and "disabling Micrometer Observation entirely" **are not the same**; changing multiple variables in one group makes results hard to interpret.

## 16. Proper Benchmark Procedure: From Baseline to Conclusion

### 16.1. Hold External Variables Constant

Fix or record:

- Spring Boot / Cloud Gateway version, JDK, GC, and container image.
- CPU cores, cgroup quotas, heap/direct memory, and pod limits.
- Gateway replica count and CPU affinity if applicable.
- Mock/service upstream latency, body sizes, HTTP keep-alive, and TLS mode.
- Concurrency, arrival rate, request mix (GET/POST, size distribution).
- Log sink (stdout/file/async queue) and collector/backend topology.
- Sampling probability and spans per request.
- HTTP client pool, max connections, and pending acquire timeout.
- Security, rate limiting, Retry, and circuit breaker settings.
- Warm-up duration and steady-state window.
- In Kubernetes: node contention, HPA, throttling, and autoscaling policies.

Never compare group A on a laptop against group B in a production pod and conclude B slowed down because of tracing.

### 16.2. Test by Arrival Rate, Not Just Virtual Users

In a closed-loop benchmark, when the Gateway slows down, virtual users wait longer and **inadvertently send fewer requests**, masking overload.

With open-loop / `constant-arrival-rate`, the load generator strives to maintain the configured arrival rate, exposing queueing and p99 growth under load. Still, verify the generator has enough VUs, connections, and CPU to hit the target RPS.

### 16.3. Illustrative k6 Script

In a lab project you can use k6 with `BASE_URL` from the environment:

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    steady: {
      executor: "constant-arrival-rate",
      rate: 200,
      timeUnit: "1s",
      duration: "3m",
      preAllocatedVUs: 100,
      maxVUs: 400
    }
  }
};

export default function () {
  const response = http.get(
    `${__ENV.BASE_URL || "http://localhost:8080"}/api/catalog/42`,
    { headers: { "X-Benchmark-Case": "baseline" } }
  );

  check(response, {
    "expected success": (r) => r.status === 200
  });
}
~~~

This snippet is an **illustrative load script**, not executed in this lesson. Run it only against Gateways and upstreams **you own** in lab/staging; never blast public services. Combine k6 output with CPU/GC/Netty/Collector metrics to isolate bottlenecks.

For body transforms, add POST scenarios with **explicit payload size distributions** (e.g., 1 KiB, 32 KiB, 256 KiB, 1 MiB) and check request body integrity. Never embed production payloads containing PII in test scripts.

### 16.4. Measurement Phases

1. **Warm-up:** let JIT, connection pools, and caches stabilize; exclude warm-up data from conclusions.
2. **Low load:** verify correctness and baseline overhead without saturation.
3. **Steady load:** measure p50/p95/p99 at target RPS.
4. **High load:** step up RPS until error rates or latency breach SLOs.
5. **Burst load:** check queues, log/span exporters, and spike absorption.
6. **Faults:** Collector offline, slow log collector, upstream timeouts.
7. **Recovery:** verify log queues and buffers drain cleanly and heap returns to baseline.
8. **Repeat:** run multiple interleaved A/B rounds to reduce thermal, JIT, and node-contention bias.

### 16.5. Record Results Using a Consistent Template

| Field | What to report |
| --- | --- |
| Test ID / commit / image | Exact build tested |
| Scenario | A/B/C… and logging/tracing/body settings |
| Request mix | GET/POST, payload sizes, gzip, auth |
| Offered RPS / achieved RPS | Target vs. actually emitted by generator |
| p50, p95, p99 | Client-observed latency |
| Error/timeout rate | By status/exception |
| CPU / throttling | Both Gateway and Collector |
| Heap, direct memory, allocation rate | Body buffering/Netty |
| GC pause/count | Memory pressure |
| Log events/s and dropped | Logging |
| Sampled spans/s and exporter drops | Tracing |
| Upstream p95/p99 | Separates backend bottlenecks |
| Notes | JIT warm-up, retries, anomalies |

Do not simply write "k6 ran at 200 RPS." If the generator targeted 500 yet achieved only 310 due to VU exhaustion, **actual load differed** between groups; latency comparisons must account for that gap.

## 17. Signals to Inspect via Micrometer / Actuator

Spring Cloud Gateway Server WebFlux and Spring Boot/Micrometer expose HTTP and Gateway metrics when the right dependencies, configuration, and observation infrastructure are present.

Common signals:

| Signal | Meaning | Notes |
| --- | --- | --- |
| `http.server.requests` | Inbound HTTP server timer/status | Covers more than Gateway routing alone |
| `http.client.requests` | Outbound HTTP client observations | May include Gateway outbound HTTP |
| `spring.cloud.gateway.requests` | Version-dependent route-level Gateway timer | Requires Gateway metrics filter/integration |
| Reactor Netty metrics | Connections, bytes, resource stats | Exact names depend on Reactor Netty/Micrometer |
| JVM GC/memory/CPU | Heap, pools, GC pauses | Remember direct/pooled buffers too |
| Log queue metrics | Queue depth/drops if appender supports them | Not automatic in all logging backends |
| OTel exporter metrics | Export successes/failures/drops | Depends on SDK/Collector |
| Custom body transform timer | Decode/rewrite/encode duration | Custom project instrumentation |
| Custom payload-size histogram | Input/output sizes | Never log raw bodies |

For histogram/SLO quantiles, Prometheus summaries and histograms have trade-offs. Aggregate p95/p99 at the **metrics backend** via compatible histogram buckets; never average single-instance p99 values into a cluster p99.

### 17.1. Never Enable Metric Tags with Unbounded Cardinality

Never use these as metric labels:

- Raw `/api/orders/123456` or individual order IDs.
- `traceId`/`spanId`/`X-Request-Id`.
- Access tokens, session IDs, emails, or phone numbers.
- Full upstream URIs with dynamic query strings.
- Request bodies or JSON fields containing user data.

Use **route IDs** like `orders-api`, status/outcome, HTTP method, and controlled service groups. When you need to trace a single request, use secured logs and traces instead of exploding Prometheus time series.

## 18. Body Transforms and Performance Tests Must Pair with Correctness Tests

A "faster" optimization that drops bodies or alters statuses is a **regression**, not an improvement.

### 18.1. HTTP Contract Tests Against a Mock Upstream

Design:

~~~mermaid
flowchart LR
    TC["WebTestClient / HTTP test"] --> GW["Gateway Server WebFlux<br/>RANDOM_PORT"]
    GW --> MOCK["MockWebServer<br/>ephemeral port"]
    MOCK -->|RecordedRequest| ASSERT["Assert method/path/headers/body"]
    GW -->|Response| TC
    TC --> CHECK["Assert status/headers/body"]
~~~

For body-transform routes, tests must assert:

- `StripPrefix`/`RewritePath` paths remain accurate.
- Request `Content-Type`/`Content-Length` remain valid after rewriting.
- Backend receives the valid transformed payload.
- Response body/status/headers match after rewriting.
- Missing bodies and `204` responses behave properly.
- Unmatched routes / `401` / `429` do not accidentally run body filters.
- Retries do not multiply attempts unintentionally.
- Large streams are not buffered uncontrollably.

### 18.2. Example Payload Test Cases

| Test | Input | Expectation |
| --- | --- | --- |
| B1 | POST text 1 KiB | Body transformed accurately |
| B2 | POST JSON 32 KiB | Schema and charset intact |
| B3 | POST with no body | Does not invent a body outside contract |
| B4 | JSON literal `null` | Not confused with missing body |
| B5 | POST 1 MiB | Memory, status, and timeout stay within bounds |
| B6 | Binary upload | Not mistakenly converted to `String` |
| B7 | `204` upstream response | No body created for 204 status |
| B8 | `gzip` upstream response | No double compression; client decodes cleanly |
| B9 | Retry `GET` | Expected attempt count; no unintended extra body copies |
| B10 | Timeout after upstream commit | No POST replay causing duplicate side effects |
| B11 | Client disconnect | Proper cancellation and buffer cleanup |
| B12 | Request rejected with `401`/`403`/`429` | Blocked cleanly with zero outbound calls |
| B13 | Wiretap enabled | Lab/test uses no real secrets and cleans up logs |
| B14 | Collector unreachable | Business traffic continues per policy; track span drops |

### 18.3. Do Not Use the Benchmarked Logging Filter to Verify Bodies

If you benchmark the cost of body logging while assertions inspect raw bodies written by that very logging filter, you introduce **measurement-induced overhead** and couple tests to the suspect component.

Use a mock backend recording requests in correctness tests, and turn off detailed mock logging (or return minimal controlled upstream responses) during throughput benchmarks. Separate **correctness runs** from **throughput runs** while using the exact same route contract and version.

## 19. Bottlenecks Specific to Each Configuration

### 19.1. Wiretap Enabled, CPU Climbs and p99 Worsens

Hypotheses:

- Formatting wire bytes burns CPU.
- Logging queues/sinks fall behind RPS.
- Event loops execute extra callbacks.
- Container stdout blocks or log agents throttle.

Checks:

1. Confirm wiretap is genuinely enabled per namespace and log level.
2. Compare logs/sec, CPU, event-loop lag, p99, and dropped log events.
3. Hold upstream latency identical to baseline.
4. Disable wiretap and re-measure in the same environment.
5. Use **secured** network-level captures or synthetic traffic for further debugging—never turn wiretap on across all of production.

### 19.2. Tracing at 100%, Collector Full or Disconnected

Hypotheses:

- Span serialization/queueing/exporting drives up CPU/network.
- Collector/OTLP backend slows down, backing up queues.
- Too many exception attributes attached.
- Duplicate spans emitted by both an agent and a bridge.

Checks:

1. Actual spans per request.
2. Sampling and exporter configuration.
3. Queue, dropped-span, and export-failure metrics.
4. SDK and Collector CPU/memory.
5. Test with the Collector offline to verify bounded deadlines.
6. Verify the Gateway never blocks requests waiting on span exports.

Do not "disable all tracing" as a permanent fix if it blinds incident response; adjust sampling, trim attributes, fix the exporter, or scale the Collector.

### 19.3. `ModifyResponseBody` Added, Heap Scales with Payload

Hypotheses:

- Multiple decode/encode passes for `String`/DTOs.
- Response buffering breaks streaming.
- Rising GC overhead.
- Timeouts during concurrent large responses.

Checks:

1. Body-size histograms (without logging raw payloads).
2. Live heap, allocation rate, and direct memory.
3. GC pauses and buffer leak warnings.
4. p95/p99 segmented by payload size.
5. Test disabling body transformation on a lab route.
6. For large responses, consider transforming at the backend (which owns the schema) or adopting a streaming-capable design where functionally valid.

### 19.4. Heap Looks Flat Yet the Pod Is `OOMKilled`

Gateway WebFlux uses **Netty direct/pooled buffers** outside the Java heap. Container memory covers heap plus **native/direct memory**, thread stacks, code cache, metaspace, memory-mapped files, and runtime overhead.

Checks:

- `jvm.memory.*` and buffer pool metrics if instrumented.
- Native Memory Tracking where feasible.
- Process/container RSS and cgroup memory usage.
- Netty resource leak diagnostics in safe environments.
- In-flight requests, body sizes, and connection pool backlogs.

Never blindly increase `-Xmx` for an OOM if the pod limit lacks room for direct memory or if a buffer leak exists.

### 19.5. Higher RPS Alongside More 429/503 Errors

A config change can raise accepted RPS while lowering **successful** RPS. If rate limiters or LoadBalancers return 429/503 quickly, measuring total HTTP responses misleads.

Measure:

- Business-level successful RPS.
- 4xx/5xx rates and upstream attempts.
- Backend p99, saturation, and pool occupancy.
- Retry amplification.
- Rate-limit policies and quotas.

**Never crank up retries and rate limits indiscriminately** to "optimize the Gateway"; doing so merely shifts overload onto upstreams.

## 20. Designing Limits Around Payloads and Concurrency

### 20.1. Request Size Limits

For routes serving only small JSON, combine `RequestSize` with ingress limits. Example:

~~~yaml
# Illustrative WebFlux 5.x route; verify against your release.
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: small-json-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - name: RequestSize
                  args:
                    maxSize: 2MB
~~~

Note:

- `RequestSize` rejects requests over the limit per filter contract, typically returning `413 Payload Too Large`.
- This does not mean any body transformation uses at most 2 MiB of RAM: concurrency, copies, codecs, and response bodies can still add up.
- Align codec aggregation limits and ingress/backend size caps by endpoint class.
- For large uploads, split out dedicated streaming or object-storage direct-upload routes where fitting.

### 20.2. Concurrency Budgets Are More Than RPS

Little's Law gives the steady-state approximation:

\[
L = \lambda W
\]

Where:

- \(L\): average number of tasks/requests currently inside the system.
- \(\lambda\): actual throughput (requests/s).
- \(W\): time spent in the system (s).

If the Gateway handles **1,000 requests/s** with an average residence time of **0.2 s**, average in-flight requests are roughly **200**. When latency climbs due to body transforms or logging I/O, concurrent in-flight counts climb even at fixed load, amplifying buffer and memory pressure.

This is a **steady-state relationship**, not a guarantee during bursts or overload. Measure live in-flight counts when timeouts or queues change.

### 20.3. Coordinating Complementary Limits

- Rate limits keyed by authenticated principal/tenant.
- Max concurrent requests / pending queues per service/route.
- HTTP client pools and connect/response timeouts.
- Request body size + codec max in-memory limits.
- Log event/queue budgets.
- Trace sampling and span attribute limits.
- Circuit breakers and bulkheads/isolation where needed.
- HPA/autoscaling driven by CPU, RPS, concurrency, and SLOs.

**Enlarging pool sizes does not speed things up** when the upstream is already saturated. Balance capacity end-to-end.

## 21. Observability of Observability Itself

Whenever logs, tracing, and metrics are enabled, monitor **their own cost and failure modes**:

| Component | Signals | Response |
| --- | --- | --- |
| App logger | Events/s, queue fill, drops | Lower verbosity/sample, fix sink |
| stdout/container logging | Bytes/s, blocked writes, agent errors | Adjust collector config and limits |
| Tracer | Spans created/exported | Enforce RPS-based budget |
| OTLP exporter | Queue depth, batches, timeouts, dropped spans | Tune scaling/timeouts/backoff |
| Collector | CPU/memory, queues, downstream export success | Scale, shard, or add HA |
| Body transform | In/out sizes, rewrite duration, error rate | Tighten caps; profile code/codecs |
| Netty | Event-loop lag, direct memory, connections | Investigate blocking or pool contention |
| JVM | GC pauses, allocations, RSS | Reduce allocations; balance heap/direct memory |
| Gateway route | p50/p95/p99, status | Compare against SLOs |
| Backend | Latency, errors, saturation | Isolate upstream causes |

Do not turn on verbose logging just to see why logging is slow—that makes the problem worse. Use aggregated metrics and properly scoped/authorized profilers.

### 21.1. When Do You Need a Profiler?

When benchmarks show significant overhead without clarifying where CPU goes:

- JVM Flight Recorder (JFR) or `async-profiler` with controlled sampling and overhead.
- Heap/allocation profiling and analyzed GC logs.
- Netty event-loop thread stack samples when blocking is suspected.
- HTTP client pool metrics and log appender metrics.
- OTLP Collector self-metrics.

**Never take heap dumps in production with sensitive data** without strict security procedures: heap dumps can contain tokens and user data.

## 22. Incident Response Workflow When Latency Spikes After a Config Change

Suppose p99 jumps from 80 ms to 400 ms and Gateway CPU climbs right after a deployment.

### 22.1. Triage

1. Identify the change window: was wiretap enabled, sampling raised, or a body transform added?
2. Confirm **which route IDs** are impacted and the blast radius.
3. Compare p50, p95, p99, error rates, and offered/achieved RPS.
4. Check backend latency: did the upstream slow down at the same time?
5. Check CPU throttling, heap/direct memory, GC, and log/export queues.
6. Check whether retries are amplifying outbound calls.
7. Check per-replica request counts to rule out load imbalance.

### 22.2. Ordered Action Flow

~~~mermaid
flowchart TD
    A["p99 rises after observability/body config change"] --> B{"Security bug or data leak?"}
    B -->|Yes| C["Stop body logging/wiretap, isolate sink, handle security incident"]
    B -->|No| D["Compare baseline and measure Gateway/Backend"]
    C --> D
    D --> E{"Logger/OTLP queue backed up?"}
    E -->|Yes| F["Lower verbosity/sampling, fix collector"]
    E -->|No| G{"Heap/direct memory/GC climbing?"}
    G -->|Yes| H["Cap body/concurrency, roll back transform"]
    G -->|No| I["Inspect Netty event loops, pools, upstream latency"]
    F --> J["Re-run benchmark + regression tests"]
    H --> J
    I --> J
    J --> K{"p99/errors and HTTP contract meet SLO?"}
    K -->|Yes| L["Keep config, audit change, and monitor"]
    K -->|No| M["Safely roll back change and continue investigation"]
~~~

**Rollbacks must preserve correctness**: if a body transform was stripping sensitive fields for security, turning it off to raise RPS leaks data. Put equivalent upstream or route protections in place before removing a security transform.

### 22.3. Minimal Incident Report Template

~~~text
Change:
  Enable debug wiretap on gateway-a for 10 minutes

Observed:
  Gateway p99 up
  CPU and log volume increased
  Backend p99 nearly unchanged
  Error rate and retry attempts monitored

Action:
  Disable wiretap
  Verify privacy/log retention
  Re-run synthetic load
  Compare p99 and log queue drops

Conclusion:
  Benchmark with real measurements required to quantify exact overhead
~~~

This is an **illustrative incident report template**, not a real historical incident or measured result.

## 23. Common Mistakes

| Mistake | Consequence | Right practice |
| --- | --- | --- |
| Watching only average latency | Misses p99 and queueing | Collect p50/p95/p99 under realistic load |
| Comparing RPS at different offered loads | Invalid A/B conclusions | Track offered and achieved RPS |
| Leaving wiretap enabled permanently in production | High CPU/log I/O, leaks bodies/headers | Enable briefly in bounded lab/staging only |
| Assuming access log == wiretap | Misestimates log volume | Distinguish HTTP metadata from wire dumps |
| `log.debug("..." + serialize(body))` | Serializes even when DEBUG is off | Use level guards/lazy eval; log sizes |
| Unbounded async log queues | OOM when collector stalls | Bound queues with drop/backpressure policies |
| Logging arbitrary JSON/text bodies | Buffering overhead + PII leaks | Avoid; synthetic/redacted only |
| Building `traceparent` headers manually | Broken trace trees | Use framework instrumentation/propagators |
| Sampling 100% of all requests | Overloads exporters and collectors | Enforce a tracing budget |
| Setting 0.1 sampling and expecting 90% CPU drop | Misunderstands propagation/observation | Measure actual overhead |
| Blocking Gateway when OTLP collector is offline | Business latency tied to telemetry | Async bounded export + monitoring |
| Storing Spans in singletons/`ThreadLocal` | Trace leaks/corruption | Reactor Context / instrumented clients |
| Calling `subscribe()` just for logging | Loses lifecycle, body, and context | Compose into reactive pipeline |
| Transforming all large response bodies | Breaks streaming, spikes peak memory | Selective routes, caps, backend transforms |
| Calling `DataBufferUtils.join()` and retaining buffers | Memory leaks / retention | Proper lifecycle and release |
| Only raising `maxInMemorySize` | Increases OOM risk | Enforce size + concurrency caps; redesign |
| Retrying non-idempotent body POSTs | Duplicate transactions + extra buffering | Idempotency and business-safe retries |
| Monitoring only JVM heap | Misses Netty direct memory | Monitor RSS/direct/GC/pools |
| Putting raw path/`traceId` in metric labels | High cardinality | Use route IDs / templated paths |
| Disabling body-redaction filters to benchmark faster | Leaks customer data | Benchmark with synthetic data; keep security |
| Testing one tiny request for performance | Misses concurrency and stress | Mixed payloads, steady/burst loads |
| Asserting only HTTP 200 | Misses corrupted bodies/headers/statuses | Bidirectional contract tests |
| Upgrading Boot/Cloud while keeping old property names | Settings behave unexpectedly | Check live release `configprops` |
| Comparing 1-replica staging directly to 8-replica prod | Non-comparable | Fix topology and document differences |

## 24. Comprehensive Practice Exercise

**Scenario:** A Gateway Server WebFlux instance routes `/api/orders/**` to a mock backend, needing route metadata logs, tracing to investigate timeouts, and JSON response transformation per the API contract.

### Requirements

1. Pick **one** Gateway WebFlux version; document exact Boot/Cloud/JDK versions and matching starters.
2. Create the baseline route: `Path=/api/orders/**`, `StripPrefix=1`, pointing to the mock upstream.
3. Write contract tests verifying path, request/response headers, body, and status.
4. Run the baseline with wiretap off and low/disabled tracing export per Group A.
5. Use k6 to generate steady load at 3 RPS levels, recording offered/achieved RPS and p50/p95/p99.
6. Enable one **metadata log event/request**; measure CPU, log bytes/s, and p99.
7. Enable access logs and measure separately; verify logs never record tokens or raw queries.
8. Enable wiretap **in isolated staging**, measure overhead on synthetic traffic, then disable it.
9. Enable tracing at `0.1` sampling; verify W3C context propagation upstream and OTLP exports.
10. Temporarily set sampling to `1.0` in a short lab run; measure span rate, CPU, and exporter drops.
11. Enable `ModifyResponseBody` for small text/JSON responses; measure allocations and GC.
12. Step payload size from 1 KiB up to 1 MiB; monitor heap, direct memory, and p99.
13. Combine metadata logging + 10% tracing + body transform; compare ablation results.
14. Simulate Collector unavailability; verify the Gateway keeps serving business traffic per policy.
15. Test backend timeouts and `GET` retries while measuring attempts; never auto-retry `POST`.
16. Re-run contract tests to ensure statuses and bodies still match the contract.
17. Produce a data-backed report concluding which mechanism costs the most, where saturation begins, which production settings to adopt, and how to roll back.

### Acceptance Matrix

| ID | Check | Required outcome |
| --- | --- | --- |
| P1 | Baseline route | Backend receives expected method/path/query |
| P2 | Body transform | Request/response bodies match contract |
| P3 | Wiretap off | No wire-level dumps outside policy |
| P4 | Wiretap on in lab | Controlled debugging; disabled after test |
| P5 | Metadata logging | Logs route/status/latency with zero raw tokens |
| P6 | Tracing 10% | Valid propagation; exporter operational |
| P7 | Collector offline | Business errors stay within defined SLO |
| P8 | 1 KiB / 1 MiB payloads | No buffer overflow/OOM; p99 recorded |
| P9 | Retry `GET` | Attempt counts accurate and latency measured |
| P10 | Important `POST` | No duplicate side effects from blind retries |
| P11 | High RPS | CPU, queues, error rates, and p99 monitored |
| P12 | A/B ablation | Compared under identical conditions with repeats |
| P13 | Body logging | Zero PII logged; no detached `subscribe()` reads |
| P14 | Metrics | Zero dynamic raw request IDs or paths as labels |
| P15 | Rollback | Debug disabled or transform reverted without breaking security |

These criteria define **lab acceptance targets**, not claims that an actual benchmark run has already been executed.

## 25. Pre-Production Checklist

- [ ] **HTTP contract tests** verify paths, headers, bodies, and statuses after every change.
- [ ] Baseline p50/p95/p99, throughput, and errors documented with clear RPS and request mix.
- [ ] Reactor Netty wiretap stays off normally; enabled only briefly with approval for debugging.
- [ ] Access and application logs contain sanitized metadata only—no raw tokens, cookies, or PII.
- [ ] Logging uses level guards/lazy evaluation; payloads are never serialized when the level is off.
- [ ] Log queues are bounded with drop, blocking, and collector-latency monitoring.
- [ ] Tracing is sampled within budget; never left at 100% indefinitely without proven capacity.
- [ ] Collector/OTLP exporter configured with TLS/auth, retry/queue caps, and dropped-span metrics.
- [ ] Inbound/outbound trace context uses standard propagators, never manual `traceparent` copying.
- [ ] Reactor Context/MDC correlation stays intact across thread switches without detached subscriptions.
- [ ] Observability introduces no blocking I/O or heavy CPU work onto event loops.
- [ ] Bodies are never parsed or transformed when only path, header, or status changes are needed.
- [ ] All body transforms tested with empty bodies, JSON `null`, `204`/`HEAD`, compression, and charsets.
- [ ] Bounded request sizes, codec aggregation, concurrency, and HTTP pool backlogs.
- [ ] Memory monitoring covers heap, direct buffers, RSS/cgroup usage, and GC.
- [ ] Custom `DataBuffer` filters checked for leaks, double releases, and double body reads.
- [ ] Any retry with a body enforces idempotency and a replay/memory budget.
- [ ] Large uploads/downloads are streamed rather than forced into `String` aggregation for logs or transforms.
- [ ] Metric labels use only route IDs and bounded-cardinality dimensions.
- [ ] Benchmarks capture offered/achieved RPS, steady/burst traffic, payload distributions, and repeats.
- [ ] Turning off logging/tracing/transforms never weakens **security or business correctness**.
- [ ] Runbook ready to revert cleanly, verified per replica, with alerts on p99, CPU, and OOM.
- [ ] Verified all configuration against your **exact Spring Cloud Gateway and Spring Boot release**.

## 26. Summary and References

**Logging, tracing, and body transformations** each add real value in Spring Cloud Gateway, yet each adds cost to the request path:

- **Logging:** formatting/queue/I/O cost plus event-loop blocking or data-leak risk when dumping bodies or headers.
- **Tracing:** context/span/attribute creation, header propagation, and sampling/export cost; essential for multi-service diagnosis, yet requires budgets and Collector capacity.
- **Body transformation:** decode/aggregate/parse/rewrite/encode cost, which breaks streaming and sharply drives up memory, GC, and p99 under large payloads or high concurrency.

No universal formula says "tracing slows things down by X%" or "`ModifyResponseBody` always uses Y MiB." Run **controlled measurements** under identical offered load, collect p50/p95/p99 alongside resource metrics, verify HTTP contracts with a mock upstream, and then decide.

A sound production baseline starts with **SLO-grade metrics, redacted metadata logs, budgeted tracing, wiretap off, and selective body transforms**. During incidents, elevate observability **with strict time bounds**—never trade away security or Gateway stability.

### Official References

- [Spring Cloud Gateway Server WebFlux — Global Filters and Gateway Metrics Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Spring Cloud Gateway Server WebFlux — ModifyRequestBody](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/modifyrequestbody-factory.html).
- [Spring Cloud Gateway Server WebFlux — ModifyResponseBody](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/modifyresponsebody-factory.html).
- [Spring Cloud Gateway Server WebFlux — RequestSize](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestsize-factory.html).
- [Spring Cloud Gateway — Configuration Properties 5.x, Netty wiretap and observability](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html).
- [Spring Boot 3.5 — Tracing with Micrometer and OTLP](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html).
- [Current Spring Boot — Tracing/OpenTelemetry, sampling and exporters](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Framework WebFlux — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).
- [Project Reactor — Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).
- [Reactor Netty — HTTP Server Access Log](https://projectreactor.io/docs/netty/release/reference/http-server.html).
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).
