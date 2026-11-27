# Client name in Spring Boot HTTP client observability

## 1. Objectives and Context

An application often calls multiple HTTP services: payment, inventory, identity, shipping, notification, or partner APIs. When latency or error rates increase, the operations team needs to know **which target dependency** is causing the impact. Looking only at the outbound request's method, status, and route is sometimes not enough to group data by service.

Spring Boot and Micrometer provide the low-cardinality key **client.name** in HTTP client observations. By default, this value is derived from the host of the request URI. Metrics can thereby group latency/errors by remote host without putting the entire URL or per-request identifiers into time series.

This lesson belongs to the **HTTP client observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

After this lesson, you can:
1. Explain `client.name` in `http.client.requests`.
2. Distinguish `client.name`, URI template, and `http.url`.
3. Understand how the default value is derived from the request URI's host.
4. Ensure `RestClient`, `RestTemplate`, and `WebClient` are instrumented using the appropriate builders.
5. Customize the client name using `ClientRequestObservationConvention` when needed.
6. Avoid high cardinality caused by dynamic hosts, tenant subdomains, or URLs containing request data.
7. Use metrics, traces, and logs to investigate dependency latency/failures.
8. Test `client.name` and tags in your application.

**Baseline:** Spring Boot 3.5.x, Java 17+, Micrometer Observation, Actuator. Blocking examples use `RestClient`; `WebClient` has its convention in a separate reactive package. Specific APIs must be verified against your actual Spring Framework/Spring Boot version.

## 2. What is client.name?

The default HTTP client observation is named **http.client.requests**. It wraps one outbound HTTP exchange, from when the client executes the request until the response is received and the body is handled according to the client's lifecycle.

Common low-cardinality keys:

| Key | Meaning | Example |
| --- | --- | --- |
| method | HTTP method | GET, POST |
| uri | URI template supplied to the client | /v1/orders/{id} |
| client.name | Target client/host name | inventory.internal |
| status | HTTP status or client error code | 200, 503, IO_ERROR |
| outcome | Result category | SUCCESS, SERVER_ERROR |
| error | Exception class name during exchange | ResourceAccessException |

High-cardinality keys typically include **http.url**, containing the request's specific URI. Do not put high-cardinality values into metric labels.

Request example:

```java
restClient.get()
        .uri("https://inventory.internal/v1/items/{sku}", sku)
        .retrieve()
        .body(Item.class);
```

The observation can produce these values:
- `client.name`: `inventory.internal`
- `uri`: `/v1/items/{sku}`
- `method`: `GET`
- `status`: `200`
- `http.url`: full URL with host, path, and the actual `sku` value (high cardinality)

`client.name` identifies the **target dependency**, while `uri` identifies the route template on that dependency.

## 3. Default Value of client.name

By Spring Framework's default convention, `client.name` is derived from the host in the request URI.

| Request URI | Default `client.name` |
| --- | --- |
| `https://payment.internal/v1/charge` | `payment.internal` |
| `https://inventory.example.com/items/42` | `inventory.example.com` |
| `http://localhost:8081/health` | `localhost` |
| `https://api.partner.example/v2/search?q=abc` | `api.partner.example` |

Protocol, port, and path are not part of a host-derived `client.name`. Two endpoints on the same host with different paths can be grouped under the same `client.name`.

Notes:
- If the environment creates different hosts per tenant/request, the number of `client.name` values can grow high.
- If service discovery generates many per-instance hostnames, metrics can become fragmented.
- If calling through a proxy/gateway, the default `client.name` may be the proxy hostname instead of the logical dependency behind it.
- If the URI has no valid host or the request was not constructed successfully, the value may be `none` depending on the convention/framework version.

The default `client.name` is not a service registry or logical dependency catalog. It reflects how the convention identifies the host from the request.

## 4. Enabling HTTP Client Observation

Spring Boot Actuator manages instrumentation for `RestClient`, `RestTemplate`, and `WebClient`. The critical requirement is using the builder auto-configured by Spring Boot.

### 4.1. RestClient

```java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryClient {
    private final RestClient client;

    public InventoryClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://inventory.internal")
                .build();
    }

    public Item findItem(String sku) {
        return client.get()
                .uri("/v1/items/{sku}", sku)
                .retrieve()
                .body(Item.class);
    }
}
```

The injected builder may already have `ObservationRegistry` and Boot customizers attached. Requests are instrumented when the required observability dependencies/configuration are present.

Avoid creating clients with `RestClient.create(...)`, because the static factory method does not use the auto-configured builder and can bypass observation instrumentation unless the application configures the registry/customizer itself.

### 4.2. RestTemplate

```java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class LegacyInventoryClient {
    private final RestTemplate client;

    public LegacyInventoryClient(RestTemplateBuilder builder) {
        this.client = builder
                .rootUri("https://inventory.internal")
                .build();
    }
}
```

Spring Boot uses `RestTemplateBuilder` to add observation customizers. Do not assume any `RestTemplate` created directly via its constructor is instrumented.

### 4.3. WebClient

```java
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class ReactiveInventoryClient {
    private final WebClient client;

    public ReactiveInventoryClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://inventory.internal")
                .build();
    }

    public Mono<Item> findItem(String sku) {
        return client.get()
                .uri("/v1/items/{sku}", sku)
                .retrieve()
                .bodyToMono(Item.class);
    }
}
```

`WebClient` observation follows the reactive lifecycle. The observation completes along with the subscribe/response/error/cancel flow, not merely when the method returns a `Mono`.

## 5. Customizing client.name by Logical Dependency

A host-derived name suits many systems. However, the technical host may not represent the logical dependency:
- Multiple services share a single API gateway.
- Service discovery generates multiple host instances for the same logical service.
- Hosts differ across dev/staging/production, while dashboards need a stable name.
- Clients go through a proxy, but you need grouping by the actual downstream dependency.

You can customize low-cardinality keys with **ClientRequestObservationConvention**.

Spring Framework has two interfaces depending on the client stack:
- Blocking `RestClient`/`RestTemplate`: `org.springframework.http.client.observation.ClientRequestObservationConvention`.
- Reactive `WebClient`: `org.springframework.web.reactive.function.client.ClientRequestObservationConvention`.

Spring Boot allows registering the corresponding convention bean to customize client observation tags.

### 5.1. Choosing a logical name from an allowlist

A custom convention should:
1. Read the host from `ClientRequestObservationContext`.
2. Map known hosts to a stable logical name.
3. Map unknown hosts to `other`/`unknown`.
4. Retain default low-cardinality keys such as `method`, `uri`, `status`, `outcome`, and `error`.
5. Emit only one `client.name` key.

Mapping example:

```yaml
observability:
  http-clients:
    names:
      inventory.internal: inventory
      payment.internal: payment
      identity.internal: identity
```

For `RestClient`/`RestTemplate`, the convention is in package `org.springframework.http.client.observation`. For `WebClient`, the convention is in package `org.springframework.web.reactive.function.client`. The two stacks have separate contexts and interfaces; do not mistakenly use the blocking interface for `WebClient`.

The API of `DefaultClientRequestObservationConvention` and how Boot selects conventions may change across Spring Framework versions. When implementing, check the docs/API for your exact version and ensure you do not append a second `client.name` key alongside the default value. The final output must have exactly one stable `client.name` value.

If custom behavior is unnecessary, keep the default convention. You can alias/group at the query/dashboard layer if that meets your needs without changing the telemetry contract.

## 6. client.name and Cardinality

`client.name` is designed as a **low-cardinality key**, but a key is only low-cardinality if the actual value set is bounded.

Good:
- `inventory`
- `payment`
- `identity`
- `shipping`

High-cardinality risk:
- `tenant-9821.api.example`
- `pod-7f89c6d9b5-xk2p`
- `customer-12345.partner.example`
- hostnames taken from user input

If hosts vary per tenant/customer/request, a host-derived `client.name` can create many metric series. Map to logical service names from an allowlist.

### 6.1. Do not use raw URLs as metric tags

Do not create tags from full URLs including query parameters, raw paths containing order/customer IDs, request/correlation IDs, user-provided hostnames, or dynamic tenant subdomains.

Bad example:

```java
registry.counter("outbound.calls",
        "client.name", request.getParameter("targetHost"),
        "url", request.getRequestURI()).increment();
```

Good example:

```java
registry.counter("outbound.calls",
        "client.name", "inventory",
        "outcome", "success").increment();
```

Tag values must come from a finite list controlled by the application.

### 6.2. Hosts and proxies

If all outbound requests go through a proxy, a host-derived `client.name` may point to the proxy. There are two approaches:
- Keep the proxy as `client.name` if it is an operational dependency that needs monitoring.
- Use a custom convention to map to the logical downstream if the application reliably knows which service the request targets.

Do not infer downstream services from arbitrary data or untrusted query strings. Logical names should come from controlled client beans/configuration, not user input.

## 7. Using client.name to Investigate Dependencies

Suppose a dashboard has `http.client.requests` with tags `client.name`, `method`, `uri`, `status`, `outcome`, and `error`.

You can analyze:
- Which dependency has rising p95/p99 latency?
- Which dependency returns the most 5xx responses?
- Which client has concentrated timeout/`IO_ERROR` occurrences?
- Is a single route of inventory failing or the entire inventory service?
- Does the error occur only in one deployment/environment or across the whole system?

Summary example:

| client.name | uri | outcome | p95 latency | error rate |
| --- | --- | --- | ---: | ---: |
| inventory | /v1/items/{sku} | SUCCESS | 45 ms | 0.1% |
| payment | /v1/charges | SERVER_ERROR | 820 ms | 8.4% |
| identity | /oauth/token | SUCCESS | 110 ms | 0.2% |

Illustrative numbers. Real dashboards need to query the exported meter backend and tags; p95/error rate are not tags.

`client.name` groups by dependency; `uri` distinguishes operations/routes. Traces show which span a specific request waited on; logs show exceptions/messages; metrics show trends and scope.

## 8. Linking with Distributed Tracing

HTTP client observations typically create a client span when Micrometer Tracing is configured. The span can contain client/dependency context, HTTP method and route/URL attributes, status/error information, `traceId`/`spanId`, and parent relationships.

When propagation works, the outbound request sends trace context downstream. The server span at the target service can link with the client span to view the full dependency call in the trace.

`client.name` is an observation/metric key; it is not a trace ID and does not replace the span name. One logical client can have many spans across individual requests. There is no need to put `client.name` into baggage just to create metric grouping.

## 9. Timeouts, Status, and Error Tags

HTTP client observation records the exchange outcome:
- HTTP 2xx: successful response.
- HTTP 4xx/5xx: response received, but status reflects a request/server-side error.
- `IOException`/connect timeout/read timeout: no normal response received; status/error may reflect IO error or exception class.
- DNS/TLS/connection pool failure: request may fail before receiving a status.

Do not measure only HTTP 5xx. Dependencies can fail to return a response due to timeouts, DNS, or TLS; monitor error/outcome tags and exception logs.

With `RestClient`, `retrieve()` may throw exceptions for 4xx/5xx responses per the default error handler. The observation still measures the exchange; the exception is propagated to the caller. If the application uses `onStatus` or a custom error handler, exception behavior changes, but the exchange's status/outcome still needs to be observed.

## 10. Testing client.name

### 10.1. Testing auto-configured clients

- Create a `RestClient` from the injected `RestClient.Builder`.
- Call a mock server or test endpoint.
- Confirm the `http.client.requests` observation/meter appears.
- Confirm `client.name` equals the request URI host per the default convention.
- Confirm `uri` is a template without path variable values.
- Confirm `http.url` (if stored in tracing/high-cardinality context) is not turned into a metric tag.

Repeat with `RestTemplateBuilder` and `WebClient.Builder` if the application uses those stacks.

### 10.2. Testing custom conventions

- Host `inventory.internal` maps to `inventory`.
- Host `payment.internal` maps to `payment`.
- Unknown hosts map to `other`/`unknown`.
- There are not two `client.name` keys in the same `KeyValues`.
- Low-cardinality tags retain a finite value set.
- The reactive convention is used by `WebClient` and the blocking convention by `RestClient`/`RestTemplate`.

Use an `ObservationRegistry` test handler to check context/`KeyValues` or a test `MeterRegistry` to check meters/tags after the request. Choose the approach matching your Spring Boot version; do not test only the mapping method while ignoring whether the builder actually enables instrumentation.

## 11. Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No `http.client.requests` | Using a self-created client, missing Actuator/registry/customizer | Use auto-configured builder and check dependencies |
| `client.name` is `localhost` | The URI actually uses `localhost` | Check the URL in the runtime environment |
| `client.name` is a proxy name | Requests pass through a gateway/proxy | Map to logical dependency if policy allows |
| Many nearly identical `client.name`s | Different instance/tenant hostnames | Map hosts to a finite set of logical names |
| `client.name` is `other`/`unknown` | Host not allowlisted or invalid URI | Check mapping and request construction |
| `WebClient` does not use convention | Registered blocking convention by mistake | Use reactive `ClientRequestObservationConvention` |
| Metric cardinality spikes | Raw host, URL, tenant, or request ID used as tag | Normalize `client.name` and drop dynamic tags |
| Metrics exist but no client span | Tracing bridge/propagation unconfigured or sampled out | Check tracing integration |
| Span exists but no metrics | Meter registry/exporter or different instrumentation handler | Check metrics pipeline and builder customizers |
| Low error rate but dependency is slow | Looking only at status errors, ignoring latency/timeouts | Monitor timer percentiles and `IO_ERROR` |
| Host/path differs from expectation | URI template not passed or URL built dynamically | Use URI templates and test observation keys |

## 12. Production Checklist

- [ ] Use auto-configured `RestClient.Builder`, `RestTemplateBuilder`, or `WebClient.Builder`.
- [ ] Confirm `http.client.requests` is recorded.
- [ ] Understand that default `client.name` is taken from the URI host.
- [ ] Distinguish `client.name` from `uri` template and `http.url`.
- [ ] Map dynamic hosts to logical dependency names when needed.
- [ ] Keep `client.name` within a low-cardinality value set.
- [ ] Do not use raw URLs, request IDs, tenant IDs, or correlation IDs as metric tags.
- [ ] Use the convention from the right package for blocking vs. reactive clients.
- [ ] Ensure the convention does not emit two `client.name` keys.
- [ ] Test statuses, IO errors, timeouts, and unknown hosts.
- [ ] Link metrics with client spans and logs via trace context.
- [ ] Monitor latency and connection errors, not just HTTP 5xx.

## 13. Self-Study Questions

1. What does `client.name` in `http.client.requests` mean?
2. Why is `client.name` derived from the host by default instead of the full URL?
3. How does a `uri` template differ from `http.url`?
4. Why is `client.name` a low-cardinality key yet still capable of causing high cardinality?
5. Which builders does Spring Boot require for `RestClient`, `RestTemplate`, and `WebClient` to have observations?
6. When do you need to customize `ClientRequestObservationConvention`?
7. Why does `WebClient` use a convention interface in a different package from `RestClient`?
8. If all requests go through a proxy, what does the default `client.name` reflect?
9. How do you map multiple instance hosts to one logical service?
10. How is a timeout with no HTTP response represented in a client observation?
11. Does `client.name` replace `traceId`/`spanId`?
12. What should you check when metrics exist but client spans do not?

## References

- [Spring Boot 3.5 — HTTP Client Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Spring Boot 4.0 — HTTP Client Metrics](https://docs.spring.io/spring-boot/4.0/reference/actuator/metrics.html)
- [Spring Framework — HTTP Client Instrumentation](https://docs.spring.io/spring/reference/7.0/integration/observability.html)
- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html)
- [Micrometer Observation — Concepts](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — API](https://docs.micrometer.io/tracing/reference/api.html)
- [OpenTelemetry — HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/)
