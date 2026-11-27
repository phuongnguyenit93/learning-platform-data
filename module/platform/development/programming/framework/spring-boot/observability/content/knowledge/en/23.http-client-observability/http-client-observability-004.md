# WebClient observation in Spring Boot

> **Chapter:** HTTP client observability  
> **Lesson:** WebClient observation  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Why Observe HTTP Clients?

A Spring Boot service rarely operates in isolation. When handling a request, the service may call inventory, payment, identity, or an external API. If you only measure HTTP server duration, the operations team knows the request is slow but does not yet know whether time is being spent in the database, business logic, or an HTTP dependency.

**WebClient observation** records HTTP client activity performed by Spring `WebClient`. Observation can feed data to metrics and distributed tracing: method, URI template, response status, duration, exceptions, and context linked to the current request.

Example flow:

~~~mermaid
sequenceDiagram
  participant Caller as API caller
  participant Order as order-service
  participant Obs as Observation / tracing
  participant Web as WebClient
  participant Inv as inventory-service
  Caller->>Order: POST /orders
  Order->>Obs: Start client observation
  Obs->>Web: Instrument exchange
  Web->>Inv: HTTP request + trace context
  Inv-->>Web: HTTP response
  Web-->>Obs: status / error / duration
  Obs->>Obs: Stop observation and span
  Order-->>Caller: HTTP response
~~~

Do not measure only "whether the API was called." You need to know which dependency the request was sent to, how long it took, what response status came back, whether a transport error occurred, and whether the trace connects properly with the dependency's server span.

## 2. What is WebClient and Where Does Instrumentation Sit?

Spring `WebClient` is a reactive, non-blocking HTTP client built on Reactor and commonly used in Spring WebFlux. It can be used in Spring MVC applications as an HTTP client without turning the entire server into WebFlux.

`WebClient` instrumentation can be integrated at the builder/exchange function/filter layer. When using Spring Boot Actuator and Micrometer Observation with a supported version, a `WebClient` configured via the auto-configured builder can automatically create client observations.

This has an important consequence: **use the Spring-managed `WebClient.Builder`** if you want to receive the customizers/observation instrumentation configured by Boot.

~~~java
@Service
public class InventoryClient {
    private final WebClient webClient;

    public InventoryClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Do not call `WebClient.create()` everywhere and assume all Spring Boot builder customizers will apply automatically. A standalone `WebClient` may lack instrumentation or shared configuration.

## 3. Dependencies and Baseline Configuration

With Spring Boot 3.x, Actuator integrates observability and Micrometer Observation. `WebClient` needs the starter/module corresponding to the reactive client and HTTP connector.

Maven example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
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

This is an illustrative choice for tracing via the OpenTelemetry bridge and OTLP exporter. If using Brave/Zipkin or another stack, the tracing/exporter dependencies will differ. Use the Spring Boot BOM to manage compatible versions, and do not mix multiple tracing bridges in the same application context.

Tracing configuration example:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Specific properties and auto-configuration depend on the Spring Boot minor version and exporter. In Docker/Kubernetes, replace `localhost` with a DNS/service endpoint reachable by the application.

## 4. WebClient.Builder and Auto-Configuration

Spring Boot can provide a `WebClient.Builder` customized through `WebClientCustomizer`s. These customizers can configure codecs, connectors, the observation registry, observation conventions, and other shared components.

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Injecting the builder instead of creating a new `WebClient` per method helps:
- Share configuration and customizers.
- Apply Boot-configured observation instrumentation.
- Standardize connectors, timeouts, codecs, and filters.
- Make testing easier by swapping the base URL or connector in tests.

Do not create a new builder outside the Spring context if you need those customizers. If you have multiple `WebClient`s for different dependencies, you can create multiple beans from the builder and set separate base URLs/configs.

### 4.1. Intentionally creating a standalone client

There are cases where you need a `WebClient` without the default configuration, such as tests or a dedicated connector. In those cases, you must actively configure the corresponding `ObservationRegistry`/filter and verify instrumentation. Do not assume a standalone client gets full metrics/tracing just because Actuator is on the classpath.

## 5. Lifecycle of a WebClient Observation

A client observation typically starts when `WebClient` executes the exchange, then tracks the response or error. With reactive flows, subscription timing matters: a `WebClient` request usually does not actually execute until the publisher is subscribed to.

~~~mermaid
flowchart TD
  A["Build WebClient request"] --> B["Create reactive publisher"]
  B --> C["Subscribe / exchange begins"]
  C --> D["Start client observation/span"]
  D --> E["Inject propagation headers"]
  E --> F["Send HTTP request"]
  F --> G{"Exchange result"}
  G -->|"Response"| H["Capture status / response metadata"]
  G -->|"Transport or exchange error"| I["Record error"]
  H --> J["Stop observation when exchange completes"]
  I --> J
~~~

If code creates a `Mono`/`Flux` without subscribing, the request may never be sent; there is no complete client observation for an exchange that never happened. If a publisher is subscribed to multiple times, each subscription can create a new HTTP exchange and corresponding observation.

For the response body, lifecycle and when the body is consumed depend on the API/connector and how `WebClient` is used. Do not buffer the response body indefinitely or read the body twice just for logging.

## 6. Metrics Produced by WebClient Observation

Micrometer observation handlers can record metrics from client observations. In Spring Boot/Micrometer, meter names and tag conventions depend on the version and integration. A common name is:

~~~text
http.client.requests
~~~

Common dimensions for HTTP client metrics can include:
- `method`: HTTP method.
- `uri`: URI template or normalized route pattern.
- `client.name`: host/service name or destination group per convention.
- `status`: response status code.
- `outcome`: result category.
- `exception`: exception type or `none`/`unknown`.
- other names/values depending on the convention and version.

Inspect the actual meter in the registry/Actuator endpoint; do not hard-code assumptions from another version.

Illustrative PromQL query examples:

~~~text
Request rate:
  sum(rate(http_client_requests_seconds_count[5m]))

Client 5xx ratio:
  sum(rate(http_client_requests_seconds_count{status=~"5.."}[5m]))
  /
  sum(rate(http_client_requests_seconds_count[5m]))
~~~

Metric names may be transformed when exported to Prometheus, and suffixes depend on timer/histogram configuration. Queries must be adjusted to match actual metrics.

### 6.1. URI templates and cardinality

Use URI templates such as `/products/{id}` instead of full URLs like `/products/12345`. If every ID creates a tag value, the number of time series grows rapidly.

Do not put into metric tags:
- order ID, customer ID, user ID.
- query strings or raw URLs.
- request/response bodies.
- tokens, cookies, or authorization headers.
- arbitrary exception messages.

Client name/host should also be controlled. If the destination is dynamically constructed from input data, normalize it into a finite group or appropriate service identity.

## 7. Distributed Tracing and Propagation Headers

When `WebClient` is instrumented with tracing integration, the client observation can create a client span and inject trace context into the outbound request. Server instrumentation on the dependency extracts the context to create a server span with a parent relationship.

With W3C Trace Context, the header typically looks like:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

If the dependency supports B3, propagation headers may differ. Propagator configuration must be compatible across caller, proxy, and callee.

A distributed trace may display:

~~~text
order-service: POST /orders                 [SERVER]
  order-service: inventory GET /items/{id}  [CLIENT]
    inventory-service: GET /items/{id}      [SERVER]
~~~

The client span and the server span on the dependency are two sides of the same network call; they are not duplicate instrumentation when span kind and parent-child relationships are right.

If the trace is split, check:
- Whether `WebClient` was created from an instrumented builder.
- Whether W3C/B3 propagators are compatible.
- Whether the proxy/service mesh forwards headers.
- Whether downstream server instrumentation extracts context.
- Whether async/reactive context is preserved up to subscription time.

## 8. WebClient Observation and Error Semantics

Not every 4xx/5xx response produces an exception at the `WebClient` exchange layer. `WebClient` may receive a normal HTTP response at the transport level, and application code then decides how to handle the status via `retrieve`/`onStatus` or `exchangeToMono`.

Example:

~~~java
webClient.get()
    .uri("/items/{id}", itemId)
    .retrieve()
    .bodyToMono(Item.class);
~~~

When using `retrieve()`, 4xx/5xx statuses are typically converted into `WebClientResponseException` by default status handling. With `exchangeToMono()`, code can branch based on response status itself.

~~~java
webClient.get()
    .uri("/items/{id}", itemId)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(Item.class);
        }
        if (response.statusCode().is4xxClientError()) {
            return response.createException()
                    .flatMap(Mono::error);
        }
        return response.createException()
                .flatMap(Mono::error);
    });
~~~

Client observation can record the status code even when code does not throw an exception. Exception metadata reflects transport/decode errors or error mapping in the client API. When reading traces/metrics, distinguish response status from exception type.

An HTTP 404 from inventory may be an expected result; a 503 may be a dependency availability issue. Outcome depends on contracts and retry/fallback policies.

## 9. Timeouts, Retries, and Cancellation

Timeouts and retries alter the number of client exchanges and the latency observed by operators.

Reactor timeout example:

~~~java
webClient.get()
    .uri("/stock/{sku}", sku)
    .retrieve()
    .bodyToMono(Stock.class)
    .timeout(Duration.ofSeconds(2));
~~~

The `timeout` operator can terminate the subscription with a `TimeoutException`. Depending on where the timeout is placed, it may occur before the response arrives, while the body is being consumed, or at a connector layer. Inspect the actual span/error instead of assuming all timeouts produce the same exception.

Bounded retry example:

~~~java
webClient.get()
    .uri("/stock/{sku}", sku)
    .retrieve()
    .bodyToMono(Stock.class)
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));
~~~

Each retry can create a new HTTP exchange. Depending on instrumentation and subscription boundaries, there may be multiple client spans or an operation span with attempt spans. Observe the actual waterfall and avoid manually creating duplicate spans for the same attempt.

Cancellation is also an outcome that needs to be distinguished. Client disconnect, Reactor cancellation, or timeout is not always a server error. Record cancellation/timeout according to semantics rather than labeling all cases as 5xx.

## 10. Customizing WebClient ObservationConvention

Micrometer allows customizing conventions to add low-cardinality/high-cardinality metadata to client observations. The specific API depends on the Micrometer/Spring Boot version and client observation type.

Illustrative convention example:

~~~java
public class InventoryClientObservationConvention
        implements ClientRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ClientRequestObservationContext context) {
        return KeyValues.of(
                KeyValue.of("dependency", "inventory"),
                KeyValue.of("operation", "lookup-stock"));
    }
}
~~~

This example is an illustrative skeleton; interfaces, context types, and bean registration must match your actual dependency versions. Conventions can be used to rename observations or add stable per-client/dependency metadata.

Only add low-cardinality values from a finite set such as `dependency=inventory`, `operation=lookup-stock`, region group, or API version. Do not add SKU, order ID, raw URI, or customer ID as metric tags.

### 10.1. URI mapping and custom filters

If URLs are constructed dynamically, configure URI templates properly:

~~~java
webClient.get()
    .uri("/items/{sku}", sku)
    .retrieve()
    .bodyToMono(Item.class);
~~~

Using templates lets instrumentation know the route pattern. If concatenating strings directly:

~~~java
webClient.get()
    .uri("/items/" + sku)
    .retrieve()
    .bodyToMono(Item.class);
~~~

instrumentation may only see the full URI or fail to normalize it, leading to high cardinality. Avoid dynamic hosts/paths from untrusted data; use allowlists and configured base URLs.

## 11. Is Adding ExchangeFilterFunction Necessary?

`WebClient` supports `ExchangeFilterFunction` to process requests/responses, add headers, or observe behavior. However, a custom filter should not create an extra observation/span if built-in instrumentation already does so.

Example filter for safe metadata logging:

~~~java
ExchangeFilterFunction requestLog = ExchangeFilterFunction.ofRequestProcessor(request -> {
    log.debug("Calling dependency method={} url={}",
            request.method(), request.url().getPath());
    return Mono.just(request);
});
~~~

This is an illustrative log. Avoid logging query strings, credentials, or URLs containing identifiers. Do not log request bodies by default because bodies can contain PII/secrets and reading the body can consume the publisher.

When adding a filter:
- Only add behavior not already provided by default instrumentation.
- Do not log full headers.
- Do not generate trace IDs manually.
- Do not call `subscribe` inside a filter.
- Do not consume the response body and return an already-consumed response.
- Verify filter ordering and exception behavior.

## 12. Context Propagation in Reactive Flows

`WebClient` requests execute via reactive subscriptions. Trace context needs to be preserved across Reactor operators and thread switches. Spring Boot/Micrometer tracing integration can provide appropriate context propagation when dependencies and configuration are compatible.

~~~java
return Mono.deferContextual(contextView ->
        webClient.get()
            .uri("/items/{id}", itemId)
            .retrieve()
            .bodyToMono(Item.class));
~~~

This example does not create or inject trace context by itself; it only illustrates reactive context access. Use the `WebClient` instrumentation and context propagation of your running stack.

Avoid:
- Storing trace IDs in static variables.
- Manually copying MDC across every callback without restoring/clearing properly.
- Calling `subscribe()` inside a service, detaching the flow from the caller.
- Using self-managed `ThreadLocal`s instead of context integration.
- Using a self-created `WebClient` builder and assuming Boot customizers apply automatically.

Check the trace ID on the caller's server span, client span, and dependency server span when executing across schedulers/parallel operators.

## 13. WebClient and Log Correlation

Logs for client calls should help identify dependency, operation, status, and trace context. If logging correlation is configured, `traceId`/`spanId` can be added to logs via MDC or structured logging integration.

Safe log example:

~~~text
WARN order-service traceId=4bf92f... dependency=inventory operation=lookup-stock status=503 retry=1
~~~

Do not log authorization headers, cookies, access tokens, raw response bodies, or sensitive query parameters. Use structured fields and allowlisted values.

Do not put trace IDs into metric labels. Log correlation uses IDs to look up traces; metrics require low-cardinality labels. If a trace is dropped by sampling, logs can still exist according to their own logging policy.

## 14. Testing WebClient Observation

Do not test only the response body. Verify that instrumentation actually creates observations and propagates context properly.

### 14.1. Testing with MockWebServer or WireMock

You can use a mock HTTP server to control status, latency, and responses. Tests should verify:
- `WebClient.Builder` is injected from the Spring context.
- Requests hit the right URI template.
- 2xx responses record success.
- 4xx/5xx responses have appropriate status and exception semantics.
- Timeouts/cancellations are observed.
- Trace context headers are injected when tracing is enabled.

### 14.2. Testing ObservationRegistry

You can use an `ObservationRegistry` test handler to record start/stop and key-values. How handlers are created depends on the Micrometer version.

~~~java
TestObservationRegistry registry = TestObservationRegistry.create();

Observation observation = Observation.createNotStarted(
        "http.client.test", registry);

observation.observe(() -> {
    // Execute a controlled operation.
});
~~~

This example illustrates Micrometer's test API; add handlers or assertions matching the version in use. For `WebClient` auto-instrumentation, test with the real Spring application context and builder to verify customizers are applied.

### 14.3. Testing propagation

A mock server can inspect `traceparent` or B3 headers when an active trace exists. Do not hard-code random trace IDs generated by the SDK; verify header structure, valid trace IDs, and parent relationships in tracing integration tests.

## 15. Common Troubleshooting

| Symptom | Possible Cause | Inspection Direction |
| --- | --- | --- |
| No client metrics | Using `WebClient.create()` without customizers or missing registry/handler | Use injected `Builder`, check `ObservationRegistry` |
| Metrics exist but no spans | Missing tracing bridge/exporter or sampling drops trace | Check tracing integration and sampling |
| Client span does not share trace ID with server | Context propagation broken | Check Reactor context, propagator, and headers |
| URI tag has thousands of values | Using raw URL/path with IDs | Use URI templates |
| Status 503 but exception tag `none` | Response handled normally or different mapping | Check `retrieve`/`exchangeToMono` and convention |
| Timeout does not appear as expected | Timeout at another layer or subscription/body lifecycle | Identify timeout operator and span lifecycle |
| Duplicate spans | Java agent, custom filter, and Boot instrumentation all creating spans | Inspect waterfall/span kind/parent |
| Builder customizer does not run | Self-created `WebClient` or builder outside context | Inject `WebClient.Builder` |
| Trace lost after `publishOn`/`subscribeOn` | Context propagation incompatible/unconfigured | Check Reactor/Micrometer versions and context hooks |
| Logs missing `traceId` | Logging correlation disabled or context lost | Check MDC integration and async flow |
| App slows down when logging requests | Logging bodies/headers or blocking filter | Remove body logging, avoid blocking |
| Metrics do not match request count | Retries create multiple client exchanges | Distinguish logical operation from each attempt |

### Investigation workflow

1. Verify `WebClient` is created from the Spring-managed `Builder`.
2. Confirm Actuator/Observation and registry/handlers are present.
3. Verify the client metric appears in the registry.
4. Enable tracing bridge/exporter and verify the sampler.
5. Inspect `traceparent`/B3 on outbound requests and downstream.
6. Verify URI templates and actual tags.
7. Check retry/timeout/cancellation semantics.
8. Remove duplicate instrumentation/filters.
9. Cross-reference logs using `traceId`/`spanId`.

## 16. Real-World Scenario: order-service Calling inventory-service

**Context:** `order-service` uses `WebClient` to check stock availability. p95 latency for `POST /orders` increases. HTTP server metrics show slow requests, but it is not yet clear which dependency is the cause.

### Step 1 — Create WebClient using the builder

~~~java
@Configuration
class InventoryClientConfiguration {
    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

### Step 2 — Call using a URI template

~~~java
public Mono<Stock> findStock(String sku) {
    return webClient.get()
            .uri("/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(Stock.class);
}
~~~

### Step 3 — Observe the dependency

Client metrics show request rate, latency, and status by dependency/URI template. Traces show the inventory client span under the `order-service` server span. If retries occur, each attempt should be identified accurately.

### Step 4 — Find the root cause

If the client span accounts for almost all of the duration, inspect inventory service, network, connection pool, and timeouts. If the client span is short while the server span is long, inspect business logic, database, or queues in `order-service`.

### Step 5 — Verify after the fix

Monitor HTTP server and client p95, 5xx/timeout rates, retry counts, and trace waterfalls. Confirm trace context flows through `WebClient` and there is no URI cardinality explosion.

**Expected outcome:** the operations team sees which dependency makes requests slow, which request statuses/exceptions occur, and traces link the caller with the callee.

## 17. Exercises and Self-Check Questions

### Exercise A — WebClient auto observation

Create a Spring Boot app with Actuator and WebFlux. Inject `WebClient.Builder` and call a mock service. Verify client observation and meter creation. Compare with standalone `WebClient.create()` in a test.

### Exercise B — Tracing propagation

Enable Micrometer Tracing with a chosen bridge. Call downstream via `WebClient`. Check the shared trace ID, client/server span relationship, and propagation headers. Try dropping the header to observe a broken trace.

### Exercise C — Status and exception

Mock 200, 404, 429, 503 responses and a transport timeout. Observe the `status` attribute, exception metadata, and span status. Explain why an HTTP 404 response is not necessarily a transport exception.

### Exercise D — URI cardinality

Call `/items/{id}` for thousands of IDs. Compare URI templates with raw path string concatenation. Inspect tag value/time series counts and fix to use templates.

### Exercise E — Retry and timeout

Configure a 2-second timeout and up to two retries. Make downstream slow and then fail. Inspect the number of client exchanges/spans, latency, and exceptions. Ensure a logical operation is not mislogged/miscounted semantically.

### Exercise F — Custom observation metadata

Create a convention adding `dependency=inventory` and `operation=lookup-stock`. Verify low-cardinality tags on metrics and span attributes on traces according to the active handlers.

### Self-check questions

1. Which lifecycle does `WebClient` observation measure?
2. Why should you use the Spring-managed `WebClient.Builder`?
3. Does observation start when creating the publisher or at subscription/exchange time?
4. What dimensions do client metrics typically have?
5. Why are URI templates important for cardinality?
6. How does `WebClient` tracing inject propagation headers?
7. How do a client span and a downstream server span differ?
8. Why might a 404 not be a transport exception?
9. At what points can a timeout operator terminate a reactive flow?
10. How do retries affect the number of HTTP exchanges and spans?
11. Is cancellation always a server error?
12. When should you use a custom `ClientRequestObservationConvention`?
13. Why should you not create a span inside a custom `ExchangeFilterFunction` if instrumentation is already present?
14. How does context propagation work across Reactor schedulers?
15. How can you verify `WebClient` observation via the registry, trace backend, and a mock server?

**Completion criteria:** configure `WebClient` using the Spring-managed `Builder`; understand the Observation lifecycle; read metrics/tags; link client/server spans via context propagation; handle status/exception/timeout/retry/cancel; control cardinality; test instrumentation and diagnose duplicate spans.

## 18. Remember

- `WebClient` observation provides metadata and lifecycle for HTTP client calls; metrics/tracing handlers can turn observations into signals.
- Use `WebClient.Builder` managed by Spring Boot to receive customizers/instrumentation when supported by auto-configuration.
- Reactive requests typically execute when the publisher is subscribed to; each subscription can create a new exchange.
- Client metrics usually describe `method`, URI template, `status`, `outcome`, `exception`, and dependency per convention/version.
- Use URI templates and low-cardinality metadata; do not put IDs, raw URLs, query strings, or bodies into metric tags.
- Tracing instrumentation injects trace context to link client spans with downstream server spans; verify W3C/B3 compatibility.
- HTTP response status and exceptions are two different pieces of information. 4xx/5xx do not always produce the same exception semantics.
- Timeouts, retries, and cancellations have separate lifecycles; observe each attempt and logical operation appropriately.
- Context propagation in Reactor requires compatible integration; do not rely on self-managed `ThreadLocal`s.
- Avoid duplicate spans across Boot instrumentation, Java agents, and custom filters. Inspect the actual waterfall.
- Metrics, traces, and logs have separate policies; use metrics for trends, traces for request paths, and logs for event details.

## References

- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Reactor Reference — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
