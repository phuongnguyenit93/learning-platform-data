# Gathering Evidence from Actuator, Access Logs, Metrics, and Tracing

When a request passing through Spring Cloud Gateway fails or responds slowly, looking at the HTTP status alone is rarely enough to pinpoint the cause. Gateway may have failed to select a route, a filter may have rejected the request, service discovery may have returned a dead instance, or a downstream service may be running slowly. To separate these cases, combine evidence from four sources: Actuator reveals active runtime state and configuration, access logs record individual requests, metrics expose trends over time, and tracing shows which components each request traversed.

This lesson focuses on Spring Cloud Gateway running on WebFlux and Reactor Netty. Evidence-correlation principles apply equally to other variants, yet enabling access logs and certain management endpoints may vary across Spring Boot, Spring Cloud Gateway, and HTTP server versions.

## 1. Define the Questions to Answer

Before opening dashboards or reading logs, describe the incident with one concrete request. Minimum details needed:

- Timestamp, including timezone.
- HTTP method, sanitized path, and expected route.
- Returned HTTP status, observed response time, and reproduction count.
- Request ID or trace ID if the system already generated them.
- Application version and environment where the incident occurred if multiple deployments exist.

These values form your correlation keys. Timestamps narrow the search window; route IDs filter metrics; request IDs locate individual log lines; trace IDs open the full distributed trace. Never use full URLs containing query strings, tokens, emails, or personal data as search keys in logs.

A request passing through Gateway normally traverses these stages: client or load balancer sends the request, Gateway chooses a route via predicates, the filter chain processes the request, Gateway routes to upstream, and then receives and returns the response. Each observability source answers a different question:

| Source | Primary Question | Common Evidence |
|---|---|---|
| Actuator | What is Gateway running and which routes/filters are registered? | Health, route list, global filters, active metrics |
| Access logs and application logs | How far did a specific request get and how did it end? | Method, sanitized path, route ID, status, duration, request ID |
| Metrics | Are errors or latency rising by route and over time? | Request rate, error rate, p95/p99, status distribution |
| Tracing | Is time spent in Gateway or in a downstream service? | Trace ID, spans, per-hop duration, errors within trace |

Never conclude from a single source alone. For example, status 404 can come from Gateway finding no route or from upstream returning 404; check route ID and trace to tell them apart.

## 2. Use Actuator to Inspect Runtime State

Spring Boot Actuator provides management endpoints. For Gateway, they verify the app is alive, inspect loaded routes, and read recorded metrics. You must include the Actuator dependency and intentionally configure exposure.

Example YAML configuration for a Spring Boot application:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,gateway
  endpoint:
    gateway:
      enabled: true
  metrics:
    tags:
      application: spring-cloud-gateway

spring:
  cloud:
    gateway:
      metrics:
        enabled: true
```

This is an illustrative configuration; verify the `gateway` endpoint and its controlling properties against your running Spring Cloud Gateway version. Omit `prometheus` if your system does not use Prometheus. Endpoints appear only when matching dependencies, configs, and version support are present.

Commonly useful endpoints:

| Endpoint | Inspection Purpose |
|---|---|
| `GET /actuator/health` | Check overall status and configured health indicators |
| `GET /actuator/health/readiness` | Check traffic readiness if readiness groups are enabled |
| `GET /actuator/gateway/routes` | Confirm loaded route IDs, target URIs, predicates, and filters |
| `GET /actuator/gateway/routes/{id}` | Inspect details of a single route by ID |
| `GET /actuator/gateway/globalfilters` | Inspect registered global filters and their order |
| `GET /actuator/metrics` | List meters currently recorded by the application |
| `GET /actuator/metrics/spring.cloud.gateway.requests` | View aggregate statistics for requests through Gateway |
| `GET /actuator/prometheus` | Export metrics in Prometheus format when a matching registry is installed |

Example reading the route list from a host authorized to access management endpoints:

```bash
curl -sS http://localhost:8080/actuator/gateway/routes
```

When an expected route is missing, inspect route config, active profile, config refresh flow, and service discovery. When the route does appear, that only confirms the route is loaded; it does not prove upstream is healthy or filters process requests properly.

The `gateway` endpoint can also expose state-mutating operations such as refreshing or editing routes depending on version. During routine troubleshooting, only read operations are needed. Never open runtime-mutating management endpoints to public networks. Restrict management ports or paths with network policies, firewalls, and authentication; expose only required endpoints. Avoid exposing `*` indiscriminately in production.

## 3. Record Correlatable Access Logs

Reactor Netty access logs record request details at the HTTP server layer. Enable them via a JVM system property:

```bash
java -Dreactor.netty.http.server.accessLogEnabled=true -jar gateway.jar
```

The system property must be set before the server starts. When running in a container, pass it in the Gateway process's JVM options. Access logs reveal whether a request reached the ingress port, along with method, URI, status, and server-layer duration; exact format depends on Reactor Netty version.

Access logs do not necessarily know application route IDs or trace IDs. For deeper correlation, add a `GlobalFilter` logging at response completion. The example below illustrates core fields:

```java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;

@Component
public class GatewayRequestEvidenceFilter implements GlobalFilter, Ordered {
    private static final Logger log =
            LoggerFactory.getLogger(GatewayRequestEvidenceFilter.class);

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        long startedAt = System.nanoTime();

        return chain.filter(exchange).doFinally(signal -> {
            Route route = exchange.getAttribute(
                    ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR);
            HttpStatusCode status = exchange.getResponse().getStatusCode();
            String routeId = route != null ? route.getId() : "unmatched";
            String path = exchange.getRequest().getPath()
                    .pathWithinApplication().value();
            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedAt);

            log.info(
                    "gateway_request method={} path={} routeId={} status={} durationMs={} requestId={} signal={}",
                    exchange.getRequest().getMethod(),
                    path,
                    routeId,
                    status != null ? status.value() : "none",
                    durationMs,
                    exchange.getRequest().getId(),
                    signal);
        });
    }
}
```

This filter measures duration from entering the filter chain until the publisher finishes. `requestId` here is the ID provided by WebFlux; it does not automatically equal the trace ID. A route may not be attached when a request matches no route, so the log records `unmatched` when no route attribute exists. To identify requests rejected earlier by a component ahead of this filter, also inspect server-level access logs.

Before using this example in production, normalize paths. Real paths can contain customer IDs, emails, or resource IDs; log route templates or redacted paths instead. Never log request bodies, `Authorization`, cookies, access tokens, or all headers. If logging a trusted correlation header, cap its length, validate its source, and prevent clients from injecting noise into logs.

A solid log entry typically includes timezone-aware timestamp, application/instance, method, route ID, status, duration, request ID, and trace ID. Key-value or JSON structured logs query far more reliably than free-form message strings. Synchronize clocks across Gateway, upstreams, and log collectors to avoid searching the wrong incident window.

## 4. Use Metrics to Spot Trends

When Actuator and Micrometer are properly configured, Gateway records the `spring.cloud.gateway.requests` timer. This metric commonly carries tags such as `routeId`, `routeUri`, `outcome`, `status`, `httpStatusCode`, and `httpMethod`. Exact metric and tag names vary by release line; check `/actuator/metrics` for your actual meter list.

Read the aggregate metric:

```bash
curl -sS \
  'http://localhost:8080/actuator/metrics/spring.cloud.gateway.requests'
```

Filter by route ID:

```bash
curl -sS \
  'http://localhost:8080/actuator/metrics/spring.cloud.gateway.requests?tag=routeId:catalog'
```

Actuator returns meter statistics such as count, total time, and max. These are point-in-time aggregates useful for quick checks. For trend analysis and accurate percentiles, scrape metrics with Prometheus or an equivalent system and enable histograms for the monitored timer.

Example enabling histograms for the Gateway timer:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "spring.cloud.gateway.requests": true
```

In Prometheus, queries typically look like this when the registry exports the timer with standard naming:

```promql
# Requests per second by route
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count[5m])
)

# p95 request latency by route; requires exported histogram buckets
histogram_quantile(
  0.95,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket[5m])
  )
)
```

Metric and label names in Prometheus depend on the registry and naming convention config. If a query returns no data, inspect `/actuator/prometheus` first to confirm actual names, then update queries to match the exported metrics and labels.

When reading dashboards, watch these together:

- **Request rate:** sudden traffic spikes can expose resource ceilings or rate limiters.
- **Error rate:** split by HTTP status, outcome, and route ID to see which route concentrates errors.
- **Latency:** inspect p50, p95, and p99; averages hide small cohorts of very slow requests.
- **Saturation:** CPU, heap, active connections, event loop, and connection pools show whether Gateway is overloaded.

Never put request IDs, trace IDs, user IDs, or URLs containing resource IDs into metric tags. Every new value creates a new time series; exploding cardinality consumes Prometheus memory and destabilizes the metrics pipeline. Keep tags bounded to dimensions like route ID, method, and status.

## 5. Use Tracing to Find the Slow or Failing Hop

Metrics reveal where issues occur as trends; tracing investigates a single concrete request across multiple services. When tracing is enabled, each trace carries a trace ID and multiple spans. Each span represents an operation or processing hop, such as receiving the request at Gateway, calling the catalog service, and querying the database.

With Spring Boot 3, systems commonly integrate Micrometer Tracing with an OpenTelemetry bridge and OTLP exporter. Specific dependencies must match your running Spring Boot version. Example sampling and collector endpoint config:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
```

`0.1` illustrates sampling ~10% of requests; choose a rate balancing traffic volume, diagnostic needs, and storage cost. During incidents you may temporarily raise sampling per operational procedures while watching collector and tracing-backend load. Exporter property names and config formats differ across Spring Boot versions; consult docs for your exact version and confirm traces actually reach the collector.

Systems using W3C Trace Context usually propagate correlation context via `traceparent` and optionally `tracestate`. When services are instrumented properly, traces continue seamlessly from Gateway into downstream services. Verify trace IDs in both logs and the tracing UI; a trace ID appearing in logs while missing in the tracing UI can result from sampling, exporter issues, network drops, or broken propagation.

When opening a slow trace, check:

1. Which span starts and finishes latest; that is usually where most time goes.
2. Gaps between spans; empty gaps can reflect waiting on connections, retries, queues, or uninstrumented work.
3. Spans with error status, exceptions, or unexpected status codes.
4. Repeated calls to the same upstream; this may indicate retries or fan-out.
5. Whether the trace traversed the expected service and instance.

Never synthesize trace IDs from arbitrary client input and treat them as trusted evidence. Let the tracing library manage context; if accepting external headers, evaluate trust boundaries and header sanitization policies at ingress. Never place personal data or secrets into baggage, as baggage propagates across downstream services.

## 6. Combine All Four Sources to Classify Incidents

The table below is a starting point during investigations. HTTP codes are only symptoms; confirm with route IDs, logs, and traces before concluding.

| Symptom | Evidence to Check | Investigation Direction |
|---|---|---|
| Gateway returns 404 | Route list, logs showing `routeId=unmatched`, method and path | Predicate mismatch, wrong path after rewrite, wrong method, or route not loaded. If a route ID exists, check whether 404 came from upstream |
| Gateway returns 401/403 | Security filter logs, per-route status, trace if present | Missing/expired token, insufficient permissions, or authn/authz filter rejected the request |
| Gateway returns 429 | Metrics by status and route, rate limiter config, logged limiting key | Check quota, replenish rate, burst capacity, and partitioning key; verify whether request actually exceeded limit |
| Gateway returns 502/503 | Health, route URI, service discovery, connection error logs, and traces | Upstream missing, no available instances, DNS/connect failure, or upstream closed connection |
| Gateway returns 504 or latency rises | Per-route p95/p99, timeout logs, traces of slow requests | Slow upstream, mismatched timeouts, exhausted connection pool, or retries inflating total time |
| Errors rise on only one route | Metrics tagged `routeId`, route details, trace of a failing request | Specific route/filter config, a failing upstream, or a subset of instances |
| All routes slow down together | CPU, memory, event loop, connection pool, overall request rate and latency | Gateway overloaded, shared downstream bottleneck, network, or underlying infra issue |

A practical workflow follows this sequence:

1. **Lock a sample request:** record timestamp, method, sanitized path, expected route, status, duration, and trace/request ID.
2. **Check runtime state:** call the health endpoint, then inspect route list and route details to confirm running configuration.
3. **Search logs:** query by request ID or trace ID within the locked window; inspect access logs and application logs to see whether the request entered Gateway, which route it picked, and where it ended.
4. **Compare metrics:** filter by route ID and time window; compare request rate, error rate, and p95/p99 against pre-incident baselines.
5. **Open traces:** examine Gateway spans and downstream spans to pinpoint the hop consuming time or raising errors.
6. **Verify hypothesis:** change one variable per operational procedure, send an equivalent request, and compare before/after logs, metrics, and traces.

### Example: Requests to the Catalog Route Are Slow

Suppose clients report `GET /api/catalog/items` occasionally takes 4 seconds. Investigate as follows:

- Actuator confirms route `catalog` is loaded and its target URI points to the catalog service.
- Metrics show route `catalog` p95 spiked while other routes stayed near baseline, narrowing the scope to this route or its upstream.
- Access logs show a concrete request returning 200 after ~4 seconds with its request ID, with no evidence Gateway rejected it.
- Opening the corresponding trace shows the catalog-calling span accounts for nearly all the elapsed time, while Gateway spans take only a tiny fraction. Inspect the catalog service, its downstream calls, and client connection pools rather than tweaking route predicates.

If the trace instead shows time mostly spent before any upstream span begins, inspect the filter chain, rate limiter, retries, connection acquisition, and Gateway timeout settings. Base conclusions on span durations and corresponding logs, never inferring solely from total latency.

## 7. Operational Principles When Gathering Evidence

- **Protect management endpoints:** restrict access to operations networks, enforce authentication, and expose the minimal required endpoints. Never expose route details or runtime-mutating endpoints publicly.
- **Minimize sensitive data in logs:** never log bodies, tokens, cookies, passwords, or auth headers. Mask paths and queries that may contain personal info.
- **Keep metric cardinality low:** never use per-request or per-user IDs as tags. Use bounded dimensions like route ID and status classes.
- **Synchronize clocks:** configure NTP across nodes and record timezone-aware timestamps. Clock skew makes correlating logs and traces error-prone.
- **Choose sampling deliberately:** low sampling saves cost yet may miss rare failing requests; maintain an approved procedure for temporarily raising observability during incidents with time limits.
- **Verify data reaches the backend:** metrics endpoints or tracing config alone do not prove collectors receive data. Verify scrape targets, exporter logs, and traces inside the observability UI.
- **Maintain consistent correlation keys:** prefer trace IDs for distributed flows; use request IDs for per-service logs. Document clearly that the two IDs differ when both are used.

## 8. Hands-On Exercises

1. Enable Actuator and expose only `health`, `metrics`, and the read-only Gateway endpoint in a dev environment. Query the route list and note route IDs and target URIs.
2. Enable Reactor Netty access logs. Send one valid request and one unmatched-route request; compare statuses and details recorded in access logs.
3. Add logging containing route ID, status, duration, and request ID. Send multiple requests across two different routes and filter logs by route ID.
4. Read the `spring.cloud.gateway.requests` meter, filter by one route ID, and compare counts/statuses after sending successful and failing requests.
5. Enable tracing with appropriate sampling in dev. Send a request through Gateway to an instrumented service, and confirm the trace shows spans from both components.
6. Simulate a slow-responding upstream in a test environment. Use metrics to spot the affected route, logs to find a concrete request, and traces to pinpoint the slow span.

After completing the exercises, practice explaining an incident using three verifiable pieces of evidence: runtime routes from Actuator, a concrete request from logs, and a corresponding metric trend or trace. Whenever the three sources do not point to the same cause, note the discrepancy explicitly and collect more data before changing configuration.
