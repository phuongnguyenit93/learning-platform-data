# Do Not Use Raw URLs as Metric Tags in Spring Boot

In the **HTTP server observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, a fundamental rule is never to put raw URLs or raw request paths into metric tags. Actual URLs typically contain identifiers such as order IDs, user IDs, tokens, search terms, or query strings. If each request creates a distinct tag value, the number of time series can scale with traffic volume rather than with the number of application operations.

Spring Boot Actuator and Micrometer can automatically collect HTTP server metrics such as `http.server.requests`. Suitable dimensions for aggregation are typically HTTP method, status, outcome, and **route template**. A route template represents a path pattern like `/orders/{orderId}`, whereas a raw path is `/orders/ORD-98431`. Two requests for two different orders should be aggregated into the same route group when the goal is measuring endpoint performance.

In the **SPRING_BOOT_OBSERVABILITY** module, HTTP server metrics complement logs and distributed tracing. Metrics reveal trends in request rates, error rates, and latency; logs and traces supply details to investigate specific requests. Never use metric tags to try to store per-request details. This lesson explains cardinality, route normalization, Spring Boot/Micrometer configuration, low/high-cardinality boundaries, and practical verification.

## 1. What Problems Does a Raw URL Metric Tag Cause?

Suppose an API exposes an endpoint:

```text
GET /orders/ORD-10001
GET /orders/ORD-10002
GET /orders/ORD-10003
...
```

If the `uri` metric tag holds the raw path, each order ID produces a distinct tag value:

```text
http.server.requests{method="GET", uri="/orders/ORD-10001", status="200"}
http.server.requests{method="GET", uri="/orders/ORD-10002", status="200"}
http.server.requests{method="GET", uri="/orders/ORD-10003", status="200"}
```

A metric series is typically identified by its metric name and tag set. When even a single tag has unbounded values, each new tag combination can create an additional time series. With constantly changing request IDs, order IDs, or query strings, cardinality grows almost linearly with request volume.

Consequences:

- **Higher memory usage:** registries, exporters, and backends must track many more series.
- **Higher ingest/index cost:** the backend must store metadata and data points for every series.
- **Slow queries:** queries must scan large numbers of series and label combinations.
- **Less useful dashboards:** charts fragment into thousands of individual per-request lines.
- **Risk of resource exhaustion:** registries/backends can hit cardinality limits, dropping or degrading telemetry.
- **Data leakage:** URLs can contain emails, access tokens, search terms, or business data.

Metric tags should answer aggregate questions like "which route is slow?", "which method is failing?", or "which status class is rising?". They should never serve as a per-request record log.

## 2. Distinguishing Raw URL, Raw Path, and Route Template

| Value | Example | Characteristic |
| --- | --- | --- |
| Full URL | `https://api.example.com/orders/ORD-10001?expand=items` | Includes scheme, host, path, and query |
| Raw path | `/orders/ORD-10001` | May contain per-request IDs or slugs |
| Route template | `/orders/{orderId}` | Represents a route pattern with a finite set of values |

Route templates are better suited for HTTP metric tags because many requests are grouped under the same logical endpoint.

| Actual Request | Route Template |
| --- | --- |
| `/orders/ORD-10001` | `/orders/{orderId}` |
| `/orders/ORD-10002` | `/orders/{orderId}` |
| `/customers/C-301/orders` | `/customers/{customerId}/orders` |
| `/customers/C-988/orders` | `/customers/{customerId}/orders` |
| `/health/readiness` | `/health/readiness` |

Not every path automatically becomes a template. If routes are built dynamically, requests hit a fallback mapping, or the framework cannot determine a handler pattern, the metric may display `UNKNOWN` or a fallback route depending on the integration/version. Always verify actual telemetry rather than assuming the framework always resolves a template.

### Query Strings Are Also a Cardinality Source

Two requests can share the same path while having different query strings:

```text
GET /search?q=micrometer
GET /search?q=spring-boot
GET /search?q=distributed-tracing
```

If the full URL is recorded into a tag, each search term creates a distinct dimension. Query strings can also contain emails, tokens, user-specific filters, or sensitive data. Stripping the query string from the URL tag is still not enough if the raw path still contains IDs; you need a route template.

### Host and Port Must Also Be Controlled

If a service receives traffic across many hostnames or tenant-specific subdomains, a `host` tag can take on very many values. Putting full hostnames or dynamic ports into metrics requires clear justification. If the goal is distinguishing deployments, use stable resource/service metadata or a normalized dimension rather than arbitrary client `Host` headers.

## 3. Cardinality Multiplies Across Tag Combinations

The theoretical maximum number of series by simple multiplication is:

\[
\text{Series} \approx \prod_{i=1}^{n} \text{Number of values of tag}_i
\]

Suppose an HTTP timer has:

| Tag | Assumed Number of Values |
| --- | ---: |
| `method` | 5 |
| `uri` as route template | 30 |
| `status` | 6 |
| `outcome` | 4 |
| `region` | 3 |
| **Theoretical maximum product** | **10,800** |

With raw paths, if 500,000 distinct order IDs occur in a day, tag combinations can jump from a few thousand into the hundreds of millions under this simple model. In practice, registries/backends may enforce caps or different aggregations, yet high cardinality still imposes heavy cost and resource pressure.

With histograms, each series also carries associated bucket time series depending on backend representation. The series count scales with routes, methods, status combinations, regions, and instances. Request count alone is not the only factor; the number of tag combinations and how histograms are exported matter just as much.

**Cardinality is never about one tag in isolation.** Multiple tags with moderate value sets can still multiply into a huge number of series.

## 4. HTTP Server Metrics in Spring Boot/Micrometer

With Spring Boot Actuator and a supported web stack, Micrometer can automatically instrument HTTP server requests. The common meter is `http.server.requests`. It is a Timer for requests, typically providing count, total time, and histograms/distributions if configured.

Common tags depending on stack/version:

| Tag | Example | Why It Fits |
| --- | --- | --- |
| `method` | `GET`, `POST` | Finite set of methods |
| `uri` | `/orders/{orderId}` | Route template, not raw path |
| `status` | `200`, `404`, `500` | Finite set of statuses |
| `outcome` | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` | Finite result categories |
| `exception` | Exception class name or `None` | Value set and semantics must be controlled |

Exact tags and route handling depend on Spring Boot, Spring Framework, Servlet/Reactive stack, and the active convention. Inspect the metrics endpoint or registry output to check actual values. Never hardcode dashboards around unverified tags.

Application configuration example:

```yaml
spring:
  application:
    name: orders-service

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

This snippet illustrates exposing appropriate endpoints and enabling histograms for the HTTP timer on Spring Boot versions supporting these properties. Expose endpoints only per governance policy; never leave metrics endpoints openly public without controls. Enable histograms based on actual need and your cardinality/storage budget.

You can inspect a meter via the Actuator metrics endpoint:

```http
GET /actuator/metrics/http.server.requests
```

The Actuator metrics endpoint shows meter data inside the registry; it is not necessarily in Prometheus scrape format. If using the Prometheus registry, inspect `/actuator/prometheus` to verify the actual exported metric names and labels. Rely only on actual response output to confirm tags.

## 5. Spring MVC: Route Templates Come from Mappings

In Spring MVC, the framework knows handler mappings such as:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse getOrder(@PathVariable String orderId) {
        return orderService.find(orderId);
    }
}
```

Both requests `/orders/ORD-10001` and `/orders/ORD-10002` match the single mapping `/orders/{orderId}`. The HTTP server observation can use that pattern as the `uri` tag.

Do not manually add raw `request.getRequestURI()` to `http.server.requests` via a customizer or filter. If an extra dimension is needed, use the framework-resolved route template or a stable application-defined route name.

When a route is not explicitly mapped, fallback values such as `NOT_FOUND` or `UNKNOWN` may be used depending on convention rather than the raw path. That is far safer because arbitrary unmatched URLs will not create distinct tag values.

## 6. Spring WebFlux: Keeping Route Cardinality Stable

In WebFlux, handler mappings can likewise provide route patterns. For example:

```java
@RestController
@RequestMapping("/payments")
class PaymentController {

    @GetMapping("/{paymentId}")
    Mono<PaymentResponse> getPayment(
            @PathVariable String paymentId) {
        return paymentService.find(paymentId);
    }
}
```

The route template `/payments/{paymentId}` groups requests carrying different payment IDs. In the reactive stack, never grab the raw path and attach it as a metric tag in a `WebFilter`; use the framework-integrated observation/convention to obtain the route pattern once mapping is resolved.

If a custom `WebFilter` starts an observation too early, handler mapping might not have run yet and the route template might not exist yet. In that case, the `uri` value may be unknown. Avoid filling the gap with the raw path; let the convention/framework finalize after mapping or use a low-cardinality fallback.

## 7. Low-Cardinality and High-Cardinality in Micrometer Observation

Micrometer Observation distinguishes low- and high-cardinality key-values:

- **Low-cardinality key-values:** suitable for metrics because the expected number of values is bounded.
- **High-cardinality key-values:** useful for tracing/log context to investigate individual operations, but should not become metric labels.

Example with a business observation:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class OrderService {
    private final ObservationRegistry observationRegistry;

    OrderService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    OrderResponse findOrder(String orderId, String channel) {
        return Observation.createNotStarted(
                    "orders.lookup",
                    observationRegistry)
                .lowCardinalityKeyValue("channel", normalizeChannel(channel))
                .highCardinalityKeyValue("order.id", orderId)
                .observe(() -> loadOrder(orderId));
    }

    private String normalizeChannel(String channel) {
        if ("mobile".equals(channel)) return "mobile";
        if ("partner".equals(channel)) return "partner";
        return "web";
    }

    private OrderResponse loadOrder(String orderId) {
        return orderRepository.findResponse(orderId);
    }
}
```

This is a conceptual example of a custom business observation. `channel` is normalized into a finite set so it can be used in metrics; `order.id` is high-cardinality metadata and may appear in tracing handlers depending on convention/exporter. Placing it in high-cardinality does not mean you should store every order ID in every backend; consider sensitive data, sampling, access controls, and retention.

**Never turn a high-cardinality key into a low-cardinality key just so it shows up on a dashboard.** When you need to query a specific order, use logs or trace attributes per policy; metric labels are not a per-transaction lookup store.

## 8. Customizing Server Observation Without Using Raw URLs

When you need to modify HTTP server observation tags, study the convention/context for your stack and version. In Spring MVC, the framework can provide the URI pattern once the handler is selected; in WebFlux, the route pattern may appear at a later stage in the pipeline. Custom conventions should use normalized metadata, never raw URLs as `uri`.

Design rules:

1. Keep `method` from a normalized HTTP method enum/string.
2. Use a route template, route ID, or fixed fallback.
3. Use finite `status`/status class and `outcome`.
4. The `exception` tag should be a controlled exception type, never the message.
5. Never put query strings, request IDs, user IDs, arbitrary IPs, or raw header values into metric tags.
6. If detailed info is required, place it in tracing span attributes or structured logs per privacy policy.

A custom convention should not try to synthesize a route template from a raw path by stripping numbers or UUIDs with generic regexes. URLs can contain slugs, alphanumeric order codes, nested IDs, and domain-specific segments. Simple regexes easily miss edge cases and occasionally merge two distinct endpoints by mistake. Obtain the route template from framework mappings or declare stable route names.

## 9. Why Not Use Query Parameters, Host, or Client IP as Metric Tags?

| Candidate Tag | Problem | Alternative |
| --- | --- | --- |
| Full URL | Host/path/query create vast combinations | Route template and service/resource metadata |
| Raw path | Path segments contain per-request IDs/slugs | URI template or route name |
| Query string | Search terms/filters/tokens change constantly | Finite category if genuinely needed |
| `Host` header | Callers can send arbitrary values | Normalized deployment/service identity |
| Client IP | Vast address space and potentially personal data | Group by network class/region if justified |
| `User-Agent` | Free-form string, many versions/devices | Normalized client family group |
| Correlation ID/Trace ID | Nearly unique per request | Use logs/traces and exemplars |
| Exception message | Variable content, may contain sensitive data | Exception class or controlled outcome |

Not every dimension with moderate cardinality is safe by default. Client IPs or tenant IDs may be sensitive under organizational policy; beyond cardinality, also evaluate privacy, access, and purpose.

## 10. Correlating Metrics with Logs and Traces

Metrics need low cardinality to show trends; logs/traces can retain controlled detail:

```text
Metric:
http.server.requests{
  method="GET",
  uri="/orders/{orderId}",
  status="500"
}
      |
      v
Dashboard detects route with rising error rate
      |
      +--> Logs: search by correlationId / traceId
      |
      +--> Trace: inspect spans if trace was sampled and exported
```

Log example:

```json
{
  "service.name": "orders-service",
  "event": "order.lookup.failed",
  "route": "/orders/{orderId}",
  "correlationId": "req-7f31c8a2",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "error.type": "OrderNotFoundException"
}
```

Logs can carry Correlation ID/Trace ID to locate a specific request. Traces may be sampled, so not every log is guaranteed to link to a stored trace. Metrics still aggregate all requests across chosen dimensions without needing IDs.

Some metrics backends support **exemplars**, allowing a histogram/counter sample to link to a trace context without adding Trace ID as a label on the entire series. Exemplars require compatible support from registry/exporter through backend/UI; they do not guarantee a trace is retained if sampling already dropped it.

## 11. Verifying Whether Raw URLs Leaked into Metrics

Do not rely solely on reading code—inspect actual registry output:

1. Send multiple requests to the same route template with different path variables.
2. Send requests with varying query parameters.
3. Inspect the `http.server.requests` meter in Actuator or Prometheus exposition.
4. Confirm `uri` is the same route template/fallback without individual IDs or queries.
5. Call non-existent endpoints with multiple raw paths; confirm the fallback does not create a distinct tag value per path.
6. Audit custom metrics and custom observations added by the application.
7. Watch active series/cardinality counts in the backend before and after testing.

Test example:

```bash
curl -i http://localhost:8080/orders/ORD-10001
curl -i http://localhost:8080/orders/ORD-10002
curl -i "http://localhost:8080/search?q=micrometer"
curl -i "http://localhost:8080/search?q=spring-boot"
```

After these requests complete, metric output should show stable route templates like `/orders/{orderId}` and `/search`. If output contains `/orders/ORD-10001` or query strings, track down the convention/filter/customizer injecting raw values.

The Actuator metrics endpoint can show tag values per meter. With Prometheus, inspect actual exposition output and verify series labels after scraping. Backends may normalize metric names, so identify the corresponding meter rather than searching solely for a guessed string.

### Automated Integration Test Check

You can assert against the metrics endpoint response after issuing requests:

```java
mockMvc.perform(get("/orders/ORD-10001")).andExpect(status().isOk());
mockMvc.perform(get("/orders/ORD-10002")).andExpect(status().isOk());

MvcResult metrics = mockMvc.perform(
        get("/actuator/metrics/http.server.requests"))
    .andExpect(status().isOk())
    .andReturn();

String body = metrics.getResponse().getContentAsString();
assertThat(body).contains("/orders/{orderId}");
assertThat(body).doesNotContain("ORD-10001");
assertThat(body).doesNotContain("ORD-10002");
```

This is test pseudocode based on `MockMvc`/AssertJ; exact syntax depends on test setup, path mappings, and exposed metric endpoints. If the Actuator response paginates/formats differently or uses a different metric tag key, adjust assertions to match actual output. Issue multiple requests in the same test to prove two different IDs collapse into the same route tag.

Do not inspect only `uri`. Raw values can sneak in under custom tags like `path`, `url`, `request`, `endpoint`, `tenant`, `client`, or `query`. Inspect the full list of tag keys and govern global custom `MeterFilter`s/`ObservationConvention`s.

## 12. Limits and Handling Unresolved Routes

Some requests do not match a route:

- Static resources or error dispatches.
- Malformed requests rejected before mapping.
- Gateway path rewrites differing from expectations.
- Custom servlet filters creating an observation before handler mapping.
- Reactive routes not yet resolved when tags are built.

Never use the raw request path as a fallback. You can use a fixed value such as `UNKNOWN` or `NOT_FOUND` where semantics fit. Also monitor the rate of `UNKNOWN` as a finite dimension to catch incomplete instrumentation/mapping.

If normal requests consistently show `UNKNOWN`, inspect observation creation order and the framework convention. Never "fix" it by recording the full path; fix the integration so the route pattern is available at the right time.

## 13. Common Mistakes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Putting `request.getRequestURI()` into a metric | Raw path typically contains IDs | Use route template |
| Putting `request.getRequestURL()` | Includes scheme/host/path and creates unique values | Use route + service resource |
| Attaching query strings | Every search/filter creates a new series | Omit query; use finite category if needed |
| Putting Trace ID in a timer | Nearly one series per request | Use exemplars or logs/traces |
| Regex on raw paths to strip UUIDs | Misses alphanumeric IDs and merges distinct routes wrongly | Use framework route mappings |
| Attaching exception messages | Unbounded text, may contain PII | Use exception class/outcome |
| Building custom URI tags too early in a filter | Route template does not exist yet | Read mapping after resolution |
| Checking only dashboards | Backend may already enforce caps/cardinality drops | Inspect registry and scrape output |

## 14. Case Study Exercise

An API has endpoint `GET /customers/{customerId}/orders`. A team adds a metric tag like this:

```java
registry.counter(
        "http.server.requests.custom",
        "method", request.getMethod(),
        "path", request.getRequestURI())
    .increment();
```

After one day, the series count climbs into the millions. Dashboards cannot filter by route because every customer produces a separate line. Meanwhile, Trace IDs are already present in logs.

**Questions:**

1. What is the direct cause of the cardinality explosion?
2. Which value should replace the raw path?
3. If you need logs for a specific customer request, which signal should you use?
4. Can you add Trace ID as a tag to link metrics with logs?
5. Which test should you write to prevent this bug from returning?

**Analysis Hints:**

- `request.getRequestURI()` returns raw paths like `/customers/C-123/orders`; each customer ID can create a new tag value and series.
- Use the route template `/customers/{customerId}/orders` or a stable route name resolved by the framework.
- Use structured logs/Correlation ID/Trace ID and the tracing backend with proper access controls to investigate individual requests.
- No. Trace ID is high-cardinality; use log/trace correlation or exemplars if your metrics stack supports them.
- Send multiple requests with different customer IDs and assert the metrics endpoint/Prometheus labels contain only the shared route template and no raw IDs.

### Completion Checklist

| Topic | Can Explain / Verify |
| --- | --- |
| Raw URL vs. route template | Distinguish full URL, raw path, and route pattern |
| Cardinality | Calculate the impact of tag combinations and histograms |
| HTTP server metrics | Know the role of `http.server.requests` |
| Spring MVC/WebFlux | Use route mappings instead of raw request paths |
| Micrometer Observation | Distinguish low- and high-cardinality key-values |
| Query/host/IP | Avoid free-form values as metric dimensions |
| Logs/traces | Keep IDs in logs/traces instead of metric tags |
| Exemplars | Understand limitations and compatibility requirements |
| Unknown routes | Use finite fallbacks and inspect mappings |
| Integration test | Send multiple distinct IDs and verify metric tags remain stable |

**Key Takeaway:** Never use raw URLs, raw paths, or query strings as metric tags because these values can vary with every request, causing cardinality spikes and accidentally storing sensitive data. For HTTP server metrics in Spring Boot, use route templates or stable route names alongside finite `method`/`status`/`outcome` values. Micrometer Observation separates low-cardinality values intended for metrics from high-cardinality metadata intended for tracing/log context. To investigate a specific request, use Correlation IDs, Trace IDs, logs, and traces per policy; inspect registry output and backend series to ensure actual tags contain no dynamic URLs.
