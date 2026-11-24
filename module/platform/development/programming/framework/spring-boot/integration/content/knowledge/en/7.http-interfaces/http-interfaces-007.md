# Errors, Timeouts, and Limits Determined by the Underlying Client

## 1. Context and Goals

In the **SPRING_BOOT_INTEGRATION** module, an HTTP interface is a way to describe an API calling contract using a Java interface and **@HttpExchange**, **@GetExchange**, **@PostExchange** annotations. Spring creates a proxy to turn Java method calls into HTTP requests. The proxy **is not a standalone HTTP transport**: connection establishment, sending/receiving data, HTTP status handling, timeouts, redirects, and many resource limits are governed by the **underlying client** the proxy uses.

For example, the same interface calling an inventory service can run on:

- **RestClientAdapter** → **RestClient** → a **ClientHttpRequestFactory** such as JDK HttpClient or Apache HttpComponents.
- **WebClientAdapter** → **WebClient** → a **ClientHttpConnector** such as Reactor Netty, JDK HttpClient, or Jetty.
- **RestTemplateAdapter** → **RestTemplate** → a corresponding request factory, mainly when maintaining legacy systems.

This lesson focuses on placing error policies, timeouts, and resource limits at the right layer when integrating over HTTP in Spring Boot. After studying it, you should be able to:

1. Explain why HTTP interface annotations do not automatically generate retries, timeouts, or business error translation.
2. Distinguish HTTP errors, transport errors, timeout errors, and response decoding errors.
3. Configure the underlying client for synchronous or reactive HTTP interfaces.
4. Identify connection pool, codec, streaming, blocking, and time-budget limits.
5. Test failure scenarios that directly affect integration correctness.

## 2. Where Does an HTTP Interface Sit in the Request Path?

Suppose a sales application needs to check stock availability before confirming an order. Contract declaration:

~~~java
@HttpExchange(accept = MediaType.APPLICATION_JSON_VALUE)
public interface WarehouseApi {

    @GetExchange("/inventory/{sku}")
    StockResponse getStock(@PathVariable String sku);
}

public record StockResponse(String sku, int available) {}
~~~

Calling **getStock("SKU-01")** describes **the path, HTTP method, and data types**; it does not specify how long DNS/TCP/TLS may take, how many concurrent connections may be used, how to react to 404/503, when to abort missing responses, or whether to retry.

Typical path:

~~~mermaid
flowchart TD
    A["Application service"] --> B["@HttpExchange interface proxy"]
    B --> C["HttpServiceProxyFactory / adapter"]
    C --> D{"Underlying client"}
    D --> E["RestClient"]
    D --> F["WebClient"]
    E --> G["ClientHttpRequestFactory"]
    F --> H["ClientHttpConnector"]
    G --> I["External HTTP server"]
    H --> I
    I --> J["Status / headers / body or I/O error"]
    J --> D
    D --> K["Exception or decoded data"]
    K --> A
~~~

**Core principle:** the interface describes *what to call*; the underlying client determines most of *how to call it*. When a request fails, trace from the adapter down to the client/transport before changing annotations.

## 3. Classify Errors Before Choosing How to Handle Them

Do not treat every exception as HTTP 500. There are at least four failure categories:

| Category | Examples | Typical Signal | Handling |
| --- | --- | --- | --- |
| **HTTP error response** | 400, 404, 409, 429, 503 | Has an HTTP status, possibly with a body | Interpret per API contract; retry only eligible statuses |
| **Transport** | DNS failure, TLS handshake failure, connection reset | No valid HTTP response received | Mark downstream unavailable; consider bounded retry |
| **Timeout** | Connect timeout, waiting too long for response, deadline exceeded | Call did not finish in time | Identify which phase stalled; assess risk that upstream processed it |
| **Data contract** | Malformed JSON, incompatible field types | May receive 2xx yet DTO decoding fails | Treat as integration contract error; inspect schema |

With default HTTP interface call behavior:

- **RestClient** typically throws **RestClientResponseException** or subclasses for 4xx/5xx responses. I/O errors are usually wrapped in **ResourceAccessException**.
- **WebClient** typically emits **WebClientResponseException** for error responses and **WebClientRequestException** for request execution failures. Decoding errors may appear separately.
- **RestTemplate** uses **ResponseErrorHandler** to classify error statuses and corresponding exceptions.

**Missing an HTTP status** is a vital distinction: a `ConnectException` or connect timeout cannot be caught by checking status 503, because the server never returned any status.

### Interpreting HTTP Statuses by Contract

| Status | Common Meaning | Retry? |
| --- | --- | --- |
| 400, 422 | Payload or parameters violate contract | No; fix the request |
| 401, 403 | Authentication or authorization | Do not blindly retry; fix token/permissions properly |
| 404 | Resource missing or wrong API path | Map to "no data" only if permitted by contract |
| 409 | State/version conflict | Resolve per business rules |
| 429 | Rate limited | May retry per `Retry-After` and deadline |
| 500, 502, 503, 504 | Upstream or dependency failure | Selective retry for safe/idempotent operations |

A 404 on a stock-lookup API might mean the SKU does not exist, whereas another 404 might be a wrong base URL after deployment. Never "swallow 404" across every service.

## 4. Centralized Error Configuration on `RestClient`

Example using Spring Boot with **RestClient.Builder**, **JdkClientHttpRequestFactory**, and an HTTP interface, targeting Spring Framework 6.1+ (which includes `RestClient`). Java/Spring imports are omitted to keep focus on the configuration flow.

~~~java
@Configuration
public class WarehouseClientConfiguration {

    @Bean
    WarehouseApi warehouseApi(RestClient.Builder restClientBuilder) {
        java.net.http.HttpClient jdkHttpClient =
                java.net.http.HttpClient.newBuilder()
                        .connectTimeout(Duration.ofMillis(800))
                        .build();

        JdkClientHttpRequestFactory requestFactory =
                new JdkClientHttpRequestFactory(jdkHttpClient);
        requestFactory.setReadTimeout(Duration.ofSeconds(2));

        RestClient restClient = restClientBuilder
                .baseUrl("https://warehouse.example.internal")
                .requestFactory(requestFactory)
                .defaultStatusHandler(HttpStatusCode::isError,
                        (request, response) -> {
                            throw new WarehouseHttpException(
                                    response.getStatusCode().value());
                        })
                .build();

        return HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(restClient))
                .build()
                .createClient(WarehouseApi.class);
    }
}

public final class WarehouseHttpException extends RuntimeException {
    private final int statusCode;

    public WarehouseHttpException(int statusCode) {
        super("Warehouse HTTP error: " + statusCode);
        this.statusCode = statusCode;
    }

    public int statusCode() {
        return statusCode;
    }
}
~~~

Execution steps:

1. Proxy builds the request per **WarehouseApi**.
2. **RestClient** uses **JdkClientHttpRequestFactory**, where JDK HTTP client connect and request timeouts are configured.
3. Upon receiving an error status, **defaultStatusHandler** throws **WarehouseHttpException** carrying an inspectable status code.
4. For DNS, TLS, connection, or decoding failures, the status handler does **not** turn them into `WarehouseHttpException`; the service layer must handle those error types separately.

In real applications, preserve upstream error codes, correlation IDs, and safe metadata; never parse text messages for `"503"` to decide retries, and never log tokens or full sensitive payloads.

**Timeout note:** **JdkClientHttpRequestFactory.setReadTimeout(...)** passes the setting to the JDK HTTP client's request timeout (see **HttpRequest.Builder.timeout**). The method name does not mean every individual byte read or the entire business workflow is protected by one global deadline. Timeout semantics differ across JDK HttpClient, Apache HttpComponents, and Reactor Netty.

### Translating Errors into Business Results in the Service

Suppose the warehouse contract defines 404 as "SKU does not exist":

~~~java
public Optional<StockResponse> findStock(String sku) {
    try {
        return Optional.ofNullable(warehouseApi.getStock(sku));
    } catch (WarehouseHttpException ex) {
        if (ex.statusCode() == 404) {
            return Optional.empty();
        }
        throw ex;
    }
}
~~~

This works when **WarehouseHttpException** is specifically thrown by the configured client and 404 genuinely represents "SKU absent". If keeping the default status handler, catch the matching exception type such as **HttpClientErrorException.NotFound**. Never turn 401, 503, timeouts, or JSON errors into **Optional.empty()**.

## 5. Error and Timeout Configuration on `WebClient`

An HTTP interface can be backed by **WebClient** for reactive flows, high concurrent I/O, or streaming. The contract can then return Reactor types:

~~~java
@HttpExchange(accept = MediaType.APPLICATION_JSON_VALUE)
public interface ReactiveWarehouseApi {

    @GetExchange("/inventory/{sku}")
    Mono<StockResponse> getStock(@PathVariable String sku);
}
~~~

When using Reactor Netty as the connector, baseline timeouts go on **HttpClient**:

~~~java
@Bean
ReactiveWarehouseApi reactiveWarehouseApi() {
    reactor.netty.http.client.HttpClient nettyClient =
            reactor.netty.http.client.HttpClient.create()
                    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 800)
                    .responseTimeout(Duration.ofSeconds(2));

    WebClient webClient = WebClient.builder()
            .baseUrl("https://warehouse.example.internal")
            .clientConnector(new ReactorClientHttpConnector(nettyClient))
            .defaultStatusHandler(HttpStatusCode::isError,
                    response -> Mono.just(
                            new WarehouseHttpException(
                                    response.statusCode().value())))
            .build();

    return HttpServiceProxyFactory
            .builderFor(WebClientAdapter.create(webClient))
            .build()
            .createClient(ReactiveWarehouseApi.class);
}
~~~

**CONNECT_TIMEOUT_MILLIS** bounds the TCP connection phase; **responseTimeout** is enforced by Reactor Netty on responses; **defaultStatusHandler** converts error statuses into exceptions. They are distinct mechanisms. A service can also add a reactive flow deadline:

~~~java
Mono<StockResponse> stock =
        reactiveWarehouseApi.getStock("SKU-01")
                .timeout(Duration.ofSeconds(3));
~~~

**Mono.timeout** limits how long the subscribed pipeline waits for signals and typically triggers cancellation when exceeded. It does not replace pool limits, connection settings, or guarantee the server never ran the request. For synchronous return types routed through **WebClientAdapter**, Spring also supports **blockTimeout** on the adapter; prefer configuring timeouts on the underlying HTTP client for finer control over I/O phases.

**Event-loop caution:** methods returning `Mono` execute requests only upon subscription. Never casually call **.block()** on WebFlux/Reactor Netty event-loop threads, as blocking I/O threads degrades throughput under load.

## 6. Different Timeouts Do Not Replace One Another

An HTTP call can pass through multiple phases:

~~~text
Wait for resource/pool
    → DNS → TCP connect → TLS handshake
    → send request → wait for response headers
    → read response body → decode JSON
    → apply business logic
~~~

| Limit | Purpose | Where Configured |
| --- | --- | --- |
| **Pool acquire/lease timeout** | Bounds waiting for a free connection | Pooled transport, such as connection manager |
| **Connect timeout** | Bounds opening a network connection | JDK HttpClient, Reactor Netty, Apache HttpClient... |
| **TLS/handshake timeout** | Bounds security handshake where transport supports it | HTTP transport |
| **Response/read timeout** | Bounds waiting for response data per client semantics | Request factory or HTTP connector/client |
| **Overall call deadline** | Maximum time the service agrees to wait | Application layer, reactive operator, or unified deadline |
| **Retry budget** | Bounds total retry and backoff duration | Resilience/orchestration layer |

For example, suppose stock verification has a 3-second budget. Retrying three times with **responseTimeout = 2s** plus 200 ms backoff can easily exceed 3 seconds. Therefore:

- Allocate budgets from the business deadline down to individual calls and retries.
- Set connect timeouts shorter than the total budget yet realistic for network conditions.
- Account for pool wait and backoff time, not just response wait time.
- Base values on p95/p99 latencies and downstream SLOs, then measure in a real environment.

Transport timeouts cap I/O phases; they do not automatically guarantee an end-to-end SLA across a multi-step business chain.

## 7. Retries, Rate Limits, and Consequences of Timeouts

An HTTP interface **does not automatically retry** merely because it has **@GetExchange**. Retries must be designed at the orchestration or resilience layer (e.g., Resilience4j, Spring Retry, Reactor **retryWhen**) and aligned with circuit breakers and rate limiters.

Principles:

1. **Retry only potentially transient failures**, such as transient connection errors, selected 5xx statuses, or 429. Never retry malformed payloads (400/422).
2. **Bound attempts, backoff, and jitter** so many clients do not retry simultaneously and overload downstream.
3. **Evaluate idempotency**: GET is usually safe to retry; a transaction-creating POST may have succeeded on the server even when the client times out. Use idempotency keys or deduplication where business rules require it.
4. **Honor `Retry-After`** when upstream provides it, while staying bounded by the original deadline.
5. **Avoid stacked retries**: if the gateway retries three times and the application also retries three times, one logical action can trigger nine calls.

For data-mutating operations, a timeout only means **the client did not receive a timely result**, not that the server skipped processing. Provide reconciliation or status-lookup mechanisms before deciding to resend.

Example bounded retry for a reactive GET:

~~~java
Mono<StockResponse> result = reactiveWarehouseApi.getStock("SKU-01")
        .retryWhen(Retry.backoff(1, Duration.ofMillis(150))
                .filter(error -> error instanceof WarehouseHttpException ex
                        && (ex.statusCode() == 429
                            || ex.statusCode() == 503)))
        .timeout(Duration.ofSeconds(3));
~~~

This allows **one retry** after the initial attempt and only for the two listed statuses; DNS errors or timeouts are not retried because they are excluded by the filter. In real deployments, handle `Retry-After`, jitter, and retry metrics. Placing **timeout** outside **retryWhen** caps the entire retry chain under Reactor's pipeline limit, yet HTTP-layer timeouts are still required.

## 8. Other Limits and Behaviors Governed by the Underlying Client

Two identical HTTP interfaces can behave very differently operationally:

| Concern | Impact |
| --- | --- |
| **Connection pool** | Open connections, lease waits, idle timeouts, and concurrency capacity; an undersized pool creates long queues even when the server is fast |
| **Blocking vs non-blocking** | `RestClient` uses a synchronous API; `WebClient` supports reactive execution; match the thread model |
| **HTTP/2, redirects, proxies, TLS** | Governed by transport and configuration; cannot be inferred from interface annotations |
| **Body buffering and codecs** | Large responses can exhaust memory or hit decoding buffer limits |
| **Streaming** | Return type, codecs, and adapter govern data consumption; `WebClient` supports `Flux` |
| **Headers, filters/interceptors** | Auth, tracing, and logging hooks differ by client |
| **Resource lifecycle** | Event loops and pools may need shared management or graceful shutdown |

Example configuring the decoding buffer limit on **WebClient**:

~~~java
WebClient webClient = WebClient.builder()
        .codecs(config -> config.defaultCodecs()
                .maxInMemorySize(512 * 1024))
        .build();
~~~

The 512 KiB setting above caps the configured in-memory decoding buffer, which is **not identical** to capping total size across all responses or raw network bytes. For large payloads, use pagination, streaming, or chunked processing instead of raising buffer limits endlessly.

For **RestClient**, choosing the **ClientHttpRequestFactory** determines most HTTP transport capabilities. JDK HttpClient offers concise setup; Apache HttpComponents offers richer connection-pool controls. Pick based on real requirements and verify defaults in your library version.

## 9. Handling Errors at the Right Layer with Observability

An operable design separates responsibilities clearly:

| Layer | Responsibility |
| --- | --- |
| HTTP interface | Endpoints, parameters, request/response DTOs |
| Client builder / transport | Base URL, TLS, auth, timeouts, pools, codecs, status handlers |
| Adapter | Connects the proxy to the configured client |
| Application service | Maps errors to business outcomes, chooses fallbacks and retries |
| Observability | Latency, statuses, timeouts, retry counts, pools, and cross-service traces |

If warehouse returns 503, the application service can return *unable to verify stock* and refuse order confirmation. Never treat that error as **available = 0**: "out of stock" is fundamentally different from "stock unknown".

Measure signals using low-cardinality metric labels:

- Call counts by downstream, operation, HTTP status group, and outcome.
- Latency p95/p99; connect/response timeouts, network errors, decoding errors.
- Retry counts and post-retry success rates; deadline exhaustion counts.
- Pool wait times, active connections, and saturation if exposed by the transport.
- Trace ID/correlation ID across caller and downstream.

Never include raw URLs with sensitive data, tokens, or full response bodies in metrics or logs. When using Spring Boot-managed builders, verify observation/metrics customization is active. Manually constructed builders and connectors may need explicit wiring for customizations Boot normally supplies.

## 10. Testing Scenarios That Annotations Alone Do Not Guarantee

Testing 200 responses alone is insufficient. Use **MockWebServer**, **WireMock**, or an HTTP stub server capable of injecting delays, closing connections, and returning malformed bodies. For straightforward status tests, **MockRestServiceServer** works well with `RestClient`.

| Scenario | What to Verify |
| --- | --- |
| 200, valid JSON | DTO and path variables map accurately |
| 404 | Returns empty result only when permitted by contract |
| 429 with `Retry-After` | Bounded retry honoring the indicated delay |
| 503 then 200 | Correct retry count without exceeding deadline |
| DNS failure/connection refused | Hits transport failure branch rather than HTTP status logic |
| Upstream delays response | Timeout genuinely triggers; caller does not hang forever |
| 200 with invalid JSON | Decoding error never turns into "out of stock" |
| Oversized response | Explicit behavior: pagination, streaming, or codec limit error |
| POST succeeds on server then drops response | Retrying does not create duplicate transactions |

Example status test using **MockRestServiceServer**:

~~~java
@Test
void warehouse503IsPropagatedAsHttpError() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://warehouse.test")
            .defaultStatusHandler(HttpStatusCode::isError,
                    (request, response) -> {
                        throw new WarehouseHttpException(
                                response.getStatusCode().value());
                    });

    MockRestServiceServer mockServer =
            MockRestServiceServer.bindTo(builder).build();
    WarehouseApi api = HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(builder.build()))
            .build()
            .createClient(WarehouseApi.class);

    mockServer.expect(requestTo(
                    "https://warehouse.test/inventory/SKU-01"))
            .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

    WarehouseHttpException error = assertThrows(
            WarehouseHttpException.class,
            () -> api.getStock("SKU-01"));

    assertEquals(503, error.statusCode());
    mockServer.verify();
}
~~~

Static imports for JUnit and **MockRestServiceServer** are omitted. To verify connect/response timeouts, run tests using the **exact request factory or connector** your application uses; mocking a status cannot exercise network phases. Mocking the interface method to throw `TimeoutException` only tests the application service branch—it does not prove the transport is configured properly.

## 11. Common Mistakes

**"Adding `@HttpExchange` gives you proper timeouts."** False: default timeouts depend on the client, transport, library version, and system settings. Specify them per SLO and test in practice.

**"Catching all exceptions and returning `Optional.empty()`."** This makes authentication failures, network outages, or invalid JSON look like missing SKUs. Translate only errors defined by the contract.

**"A timeout means the request never reached the server."** Timeouts can happen after upstream already mutated data. Write operations require deduplication and reconciliation.

**"More retries mean more stability."** Unbounded retries worsen overloaded dependencies. Always enforce deadlines, backoff, and concurrency caps.

**"Increasing timeouts fixes pool exhaustion."** Pool exhaustion is a resource or capacity issue; longer waits usually just lengthen queues.

**"Switching an interface from `RestClient` to `WebClient` is strictly equivalent."** Return types, blocking/reactive behavior, streaming, codecs, exceptions, and connector configuration all differ. Verify contracts and run integration tests.

## 12. Checklist for Designing a Reliable HTTP Interface

Before deploying, answer:

1. Does the interface use **RestClient**, **WebClient**, or a legacy client? What exact request factory/connector backs it?
2. What do 404, 409, 429, and 5xx mean in business terms? Which errors must propagate so callers can distinguish them?
3. Where are connect timeout, response timeout, pool timeout, and overall operation deadline configured?
4. Is retry enabled? Is the call idempotent? For writes, is there an idempotency key or reconciliation?
5. When upstream slows down, the pool fills up, or payloads grow large, are concurrency and memory bounded appropriately?
6. Do logs/metrics/traces separate error responses, network errors, timeouts, and decoding failures?
7. Do tests reproduce error responses, network failures, timeouts, and malformed payloads?

If any answer is missing, annotations have only completed the **API call contract**, not a fault-tolerant integration design.

## References

- [Spring Framework — REST Clients / HTTP Service Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): adapters, return types, error handling, and proxies.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): connectors, connect/read/write timeouts, and Reactor Netty response timeouts.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive model and streaming.
