# IO_ERROR in HTTP client observability

> **Chapter:** HTTP client observability  
> **Lesson:** IO_ERROR  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. What is IO_ERROR in an HTTP Client?

An HTTP client sends a request over the network to a dependency. Before receiving an HTTP response, this process can fail because DNS cannot resolve the host, a TCP connection cannot be opened, the TLS handshake fails, the socket is reset, the connection is closed mid-stream, or the request times out.

**IO_ERROR** in the context of HTTP client observability is a way to classify an I/O/transport-layer failure when the client cannot complete the HTTP exchange as expected. It is a useful classification label in lessons and dashboards; it is neither a standard HTTP status code nor a single exception class in Java.

Key distinctions:

- HTTP response 503 means the client received a response with status 503.
- Connection refused means the client could not establish a connection to the server; there is no HTTP response.
- Read timeout means the client waited past the deadline for data; it may have connected and sent the request but did not receive a complete response.
- TLS handshake failure means a secure connection could not be established properly.
- HTTP 404 is a valid response at the protocol layer, even if it represents an error per the API contract.

~~~mermaid
flowchart TD
  A["WebClient sends request"] --> B["DNS resolution"]
  B --> C["TCP connect"]
  C --> D["TLS handshake if HTTPS"]
  D --> E["Send request / receive response"]
  E --> F{"Result"}
  F -->|"HTTP response"| G["Classify status code"]
  F -->|"I/O / transport exception"| H["IO_ERROR"]
  G --> I["Client observation ends"]
  H --> I
  I --> J["Metrics + trace + logs"]
~~~

There is no response status when a request fails before receiving a response. Therefore, do not falsely assign HTTP 500 to every `IO_ERROR`. Record the exception type and outcome separately to distinguish transport failures from server responses.

## 2. Network Phases That Can Produce IO_ERROR

An HTTP exchange passes through multiple phases. Knowing which phase failed helps narrow down the root cause faster.

| Phase | Common Symptom | Example Cause |
| --- | --- | --- |
| DNS lookup | Cannot resolve hostname | Wrong DNS record, resolver error, slow service discovery |
| TCP connect | Connection refused / connect timeout | Service not listening, firewall, network policy |
| TLS handshake | `SSLHandshakeException` | Expired certificate, wrong truststore, protocol/cipher mismatch |
| Request write | Broken pipe / connection reset | Peer closed socket, proxy reset, stale connection |
| Response read | Read timeout / premature close | Slow server, packet loss, truncated response |
| Connection pool acquire | Could not acquire connection within timeout | Exhausted pool, requests holding connections too long |
| Response decode | Codec/decoder exception | Invalid payload or schema mismatch |

Some errors happen after HTTP response headers have arrived, such as the body stream closing mid-transfer. In that case, the client may already know the status code while still failing when reading the body. Not every I/O error means "no response received"; record both the known status and the exception occurring during body consumption if instrumentation provides them.

## 3. IO_ERROR Differs from HTTP Status and Application Errors

| Scenario | HTTP response received? | Example | Observed Classification |
| --- | --- | --- | --- |
| DNS failure | No | `UnknownHostException` | `IO_ERROR` |
| TCP refused | No | `ConnectException` | `IO_ERROR` |
| Connect timeout | Usually no | `ConnectTimeoutException` | `IO_ERROR` |
| TLS handshake failure | No valid HTTP response | `SSLHandshakeException` | Transport/security setup error |
| Read timeout | Usually no complete response | `ReadTimeoutException` | `IO_ERROR` / timeout |
| HTTP 404 | Yes | Not Found | HTTP response outcome |
| HTTP 503 | Yes | Service Unavailable | HTTP response outcome, usually dependency failure |
| JSON decode failure | Response received | `DecodingException` | Client processing/codec error |
| Business validation rejection | Response or domain result | Inventory rejected | Business outcome |

An HTTP client observation can record the status code and exception according to the instrumentation's convention. Systems may group many transport exceptions under one `IO_ERROR` bucket for dashboards, while still retaining the concrete exception type in traces/logs for investigation.

Do not classify errors solely by message strings. The exception hierarchy and cause chain generally provide more reliable information; however, exact exception types depend on the HTTP connector and version.

## 4. Common I/O Exceptions in Java

Some exception types that may appear:

| Exception | Common Meaning | What to Check |
| --- | --- | --- |
| `UnknownHostException` | Unable to resolve hostname | DNS, service discovery, hostname |
| `ConnectException` | TCP connection failed, typically refused | Service listener, port, firewall |
| `SocketTimeoutException` | Socket read/connect timeout depending on config | Timeout settings, server latency, network |
| `SSLHandshakeException` | TLS handshake failed | Certificate chain, truststore, TLS config |
| `SSLPeerUnverifiedException` | Could not verify peer identity | Hostname verification, certificate |
| `ClosedChannelException` | Channel already closed during operation | Connection lifecycle, peer close |
| `IOException` | General I/O error | Cause chain and connector logs |
| `PrematureCloseException` | Connection/response closed prematurely in some Reactor Netty versions | Server/proxy reset, body stream |

`WebClient` does not always throw these exact classes directly. Reactor Netty, JDK `HttpClient`, and other connectors have their own exception types/wrappers. For example, an `IOException` may be wrapped inside `WebClientRequestException`, a Reactor exception, or `CompletionException`.

When classifying, retain both the wrapper and root cause when helpful. Do not rely on a single class name alone to conclude DNS, TLS, or socket failure.

## 5. How Does WebClient Represent I/O Failures?

`WebClient` is a reactive client. Requests usually only get sent when the publisher is subscribed to. Errors may be emitted as a reactive `onError` signal rather than always thrown synchronously at the method call line.

Example:

~~~java
public Mono<Product> findProduct(String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class);
}
~~~

If DNS, connect, or read fails, the publisher may emit an error signal. If the response has a 4xx/5xx status, `retrieve()` by default converts that status into `WebClientResponseException`, unless code configures `onStatus` or handles the response differently.

~~~java
return webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 503,
                response -> response.createException()
                        .flatMap(Mono::error))
        .bodyToMono(Product.class)
        .onErrorMap(
                WebClientRequestException.class,
                ex -> new InventoryIoException(
                        "Inventory transport failed", ex));
~~~

The example illustrates translating a request-level error into a domain exception. Keep in mind:
- `WebClientRequestException` typically wraps errors occurring while sending the request/transport.
- `WebClientResponseException` typically represents an HTTP response treated as an error by `retrieve()`.
- Decode/codec errors can arise when reading the body.
- The `timeout` operator or connector timeouts can produce different exceptions.
- `onErrorMap` should not turn every exception into `IO_ERROR`; map only the appropriate error category and preserve the cause.

## 6. Creating a Taxonomy for HTTP Client Outcomes

A small, clear taxonomy keeps metrics and dashboards consistent. For example:

| Outcome | Meaning | Example |
| --- | --- | --- |
| `SUCCESS` | Exchange completed per policy | HTTP 2xx or accepted response |
| `HTTP_CLIENT_ERROR` | Received HTTP 4xx | 400, 404, 429 |
| `HTTP_SERVER_ERROR` | Received HTTP 5xx | 500, 502, 503 |
| `IO_ERROR` | Transport/I/O did not complete | DNS, connect, socket reset |
| `TIMEOUT` | Timed out at a stage | Connect/read/overall timeout |
| `DECODE_ERROR` | Unable to read/decode response | Invalid JSON |
| `CANCELLED` | Reactive operation canceled | Caller canceled subscription |

The taxonomy above is an application design example, not a mandatory default set from Spring Boot/Micrometer. You can merge `TIMEOUT` into `IO_ERROR` if dashboards only need one transport group, or keep it separate if you need to analyze latency/timeouts.

The key is consistent definition:
- When a status code exists, preserve the status code.
- When there is no response status, do not fake an HTTP code.
- Retain a normalized exception type.
- Distinguish timeout, cancellation, and decode failure when needed.
- Do not use free-form exception messages as metric tags.

## 7. How Does WebClient Observation Record Errors?

Spring Boot can configure `WebClient` instrumentation via the Spring-managed `WebClient.Builder`. When Observation handlers and tracing integration are active, client exchanges can create observations/spans and record response status, exception, and duration.

~~~java
@Configuration
class InventoryClientConfig {
    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Using the injected builder receives customizers/observation instrumentation configured by Boot. A standalone `WebClient` may not exhibit the same behavior.

An Observation can:
- Start when the reactive exchange executes.
- Measure request duration.
- Record `method` and URI template.
- Record response `status` if received.
- Report error if the exchange ends with an exception.
- Create a client span and propagate trace context when a compatible tracing bridge is present.

Do not assume every error produces an `outcome` tag literally named `IO_ERROR`. Default values depend on the convention/version; if you need a custom taxonomy, normalize it at the appropriate metric/observation layer while preserving exception details in traces/logs.

## 8. Metrics to Measure IO_ERROR

A client request timer metric can aggregate duration and call counts. Meter/tag names depend on the version; in the Spring ecosystem the `http.client.requests` meter is commonly seen.

Useful dimensions with controlled cardinality:
- `dependency`: `inventory`, `payment`, `identity`.
- `method`: `GET`, `POST`, `PUT`.
- `uri`: route template.
- `outcome`: `success`, `io_error`, `timeout`, `http_error`.
- `exception`: normalized exception type.
- `status`: HTTP status if a response exists.

Custom `Counter` example:

~~~java
Counter.builder("http.client.failures")
        .tag("dependency", "inventory")
        .tag("failure.type", "io_error")
        .register(meterRegistry)
        .increment();
~~~

This is an illustrative custom metric. Do not create a new meter per request. Register the `Counter` once per finite tag combination or use a builder/registry pattern with appropriate caching.

### 8.1. Calculating the I/O failure rate

PromQL example if the system has custom counters:

~~~text
sum(rate(http_client_failures_total{failure_type="io_error"}[5m]))
/
sum(rate(http_client_requests_total[5m]))
~~~

Actual metric names may differ. Ensure the numerator and denominator use the same dependency/operation scope, and the denominator includes the exact exchanges being measured.

If retries create multiple exchanges, the per-attempt rate differs from the final logical operation failure rate. Name dashboards clearly, e.g., client attempt IO error rate vs. business request final failure rate.

### 8.2. Separate timeout or merge into IO_ERROR?

Timeouts are typically a type of I/O/transport failure, yet many operations teams want a separate dashboard view because timeouts tie directly to latency, pool saturation, and SLAs. Choose one of two approaches:

- Merge timeouts into `IO_ERROR` and add exception/phase metadata in traces.
- Separate the `TIMEOUT` outcome while still grouping it under transport failures in summary dashboards.

Do not count the same event twice in the total failure rate. If you have a dedicated metric for timeouts, clarify the relationship between the counters.

## 9. Cardinality and URI Templates

An HTTP client may call many different URIs. If a metric tag contains raw URLs or path IDs, the series count grows with the number of resources.

Bad:

~~~java
webClient.get()
        .uri("/products/" + productId)
        .retrieve();
~~~

Use a URI template:

~~~java
webClient.get()
        .uri("/products/{id}", productId)
        .retrieve();
~~~

With dynamic base URLs, normalize the dependency into a finite name instead of arbitrary host strings from input. Do not include:
- `productId`/`orderId`/`customerId`.
- query strings.
- raw exception messages.
- dynamic IP/port unless necessary.
- `traceId`/`requestId`.
- tokens or URLs containing credentials.

Use low-cardinality tags for metrics. Traces/logs can hold additional allowlisted and protected diagnostic details, but should not export PII/secrets.

## 10. Traces for IO_ERROR and Context Propagation

When `WebClient` is instrumented, the client span can terminate with an exception event or error status depending on the tracing implementation. Trace context is injected into outbound headers so downstream can attach a server span if the request reaches the service.

With W3C Trace Context, the `traceparent` header carries the trace ID, parent span ID, and flags. If DNS/connect fails before the HTTP request is sent, the header may never reach the dependency; the client span still records the failed attempt.

If the error occurs in DNS/connect before the server receives the request:
- The client span can still exist.
- There may be no downstream server span.
- The trace shows the error on the caller side.
- Exception type/cause helps identify the failed phase.

Illustrative trace example:

~~~text
order-service: POST /orders                 [SERVER]
  order-service: inventory GET /stock/{sku} [CLIENT, ERROR]
    exception.type = java.net.ConnectException
    error.type = io_error
~~~

If downstream has no span, do not immediately conclude instrumentation is broken. The request may never have reached the server. Check the client span, network logs, service health, and Collector/exporter.

Sampling may drop traces before export. Logs/metrics can still exist under their own policies; do not rely solely on traces to count total I/O failures.

## 11. Timeouts Are a Category That Needs Distinction

Timeouts can occur across multiple phases:

| Timeout | Phase | What to Check |
| --- | --- | --- |
| DNS timeout | Hostname resolution | Resolver, DNS latency |
| Connect timeout | Opening TCP connection | Network route, listener, firewall |
| TLS handshake timeout | Establishing TLS | Certificate validation, peer response |
| Response/read timeout | Waiting for response bytes | Server latency, downstream saturation |
| Pool acquire timeout | Waiting for a connection in pool | Pool size, connection leaks, concurrency |
| Overall request timeout | Total operation duration | End-to-end budget and component timeouts |

Not every timeout is a `SocketTimeoutException`. Reactor Netty may emit its own exception; pool acquisition may emit an acquire timeout error; Reactor's `timeout` operator may emit `TimeoutException`.

Design timeouts with an end-to-end budget. Total duration across retries, backoff, connection acquisition, and request attempts must fit within the caller's deadline. If each retry has a timeout exceeding the remaining budget, the request can drag past the SLA.

## 12. Retries and Circuit Breakers When Encountering IO_ERROR

Retries can help with transient errors like connection resets or timeouts, but not every I/O failure is safe to retry.

Consider retrying when:
- The error is likely transient.
- The operation is idempotent or uses an idempotency key.
- Retry budget remains.
- Backoff includes jitter and an attempt limit.
- Fixed configuration errors like a wrong hostname or invalid certificate are not retried endlessly.

Do not unconditionally retry `POST` calls that create transactions without ensuring idempotency. Retries can amplify load when a dependency is already overloaded.

With Reactor, you can configure `retryWhen` with `Retry.backoff` to limit attempts and backoff intervals. Each retry can create a new HTTP exchange; inspect actual client spans instead of assuming every integration creates the same structure.

A circuit breaker stops calling a dependency when the error rate exceeds a threshold. It protects both the caller and downstream, but you must distinguish which failure types count as failures. Expected HTTP 404s probably should not trip the circuit; timeouts/connect failures generally should be considered.

~~~mermaid
flowchart TD
  A["HTTP client call"] --> B["Attempt"]
  B --> C{"Result"}
  C -->|"Success"| D["Return response"]
  C -->|"Retryable IO_ERROR"| E{"Retry budget left?"}
  E -->|"Yes"| F["Backoff + jitter"]
  F --> B
  E -->|"No"| G["Record final failure"]
  C -->|"Non-retryable"| G
  G --> H["Circuit breaker records failure"]
  H --> I["Fallback / error response"]
~~~

## 13. Distinguishing IO_ERROR from Decode and Business Failures

A response can arrive successfully at the network layer yet still be unusable by the application:

- Server returns 200, but body is not valid JSON: decode error.
- Server returns 404 for a non-existent SKU: HTTP response and potentially a valid business outcome.
- Server returns 503: HTTP server response failure.
- TCP connection reset before response: `IO_ERROR`.
- Caller cancels when result is no longer needed: cancellation, not necessarily `IO_ERROR`.

Proper classification avoids blaming the network when the response schema actually changed, or blaming the server when the caller actively canceled.

With body streams, read errors can occur after the response status is already known. Record both the status and the body-read exception if the framework provides them; do not erase the status just because body decoding failed.

## 14. Logging for IO_ERROR

Log records should help answer which dependency, which operation, which phase, and which exception type. Pass the exception object to preserve the stack trace at the boundary responsible for logging.

~~~java
try {
    return inventoryClient.findStock(sku);
} catch (WebClientRequestException ex) {
    log.error(
            "Inventory HTTP transport failed dependency={} operation={}",
            "inventory",
            "find-stock",
            ex);
    throw ex;
}
~~~

This example only suits synchronous code or code that has converted reactive errors into exceptions at the proper boundary. With reactive `WebClient`, use `onErrorResume`/`doOnError`/`onErrorMap` in the flow instead of `try/catch` around creating the `Mono`; that `try/catch` will not catch errors emitted after subscription.

Do not log full URLs with credentials, request/response bodies, authorization headers, cookies, or raw customer identifiers. Attach `traceId`/`spanId` via logging correlation integration instead of generating IDs manually.

Avoid logging the same exception in the client adapter, service, controller, and global handler. Pick one boundary to log the full stack trace; other layers can translate/rethrow while preserving the cause.

## 15. Troubleshooting IO_ERROR

| Symptom | Possible Cause | Inspection Direction |
| --- | --- | --- |
| `UnknownHostException` | DNS/service discovery | Check hostname, DNS resolver, namespace |
| `Connection refused` | No listener or wrong port | Check service endpoints, port, readiness |
| Connect timeout | Network policy, firewall, route, or overloaded service | Check network path and connect latency |
| `SSLHandshakeException` | Certificate/truststore/protocol mismatch | Check chain, SAN, truststore, TLS versions |
| Read timeout | Slow dependency, queuing, or stalled response stream | Compare server latency, pool, and timeout budget |
| Connection reset | Peer/proxy closed socket | Check proxies, load balancers, keep-alive |
| Pool acquire timeout | Exhausted connection pool | Check concurrency, pool metrics, response body release |
| Premature close | Server/proxy truncated response | Check server logs, proxy limits, body stream |
| Metrics exist but no trace | Tracing bridge/sampling/export pipeline | Check span creation, sampling, exporter |
| No `status` tag | No response received or different convention | Distinguish transport failure from HTTP response |
| Error rate spikes after deploy | DNS, endpoint, TLS, timeout, or dependency regression | Compare versions/resources and rollout |
| Retries amplify load | Retry storm or overly broad policy | Limit attempts, add jitter, circuit breaker |

### Investigation workflow

1. Determine whether an HTTP status was received.
2. Read the exception class and cause chain.
3. Identify the phase: DNS, connect, TLS, write, read, pool, or decode.
4. Check `WebClient` connector, timeouts, and pool metrics.
5. Compare dependency latency/errors against caller latency.
6. Inspect the client span; a downstream span may be absent if the request never reached the server.
7. Cross-reference logs, deployment version, and service instance.
8. Check whether retries/circuit breakers are amplifying failures.
9. Create a reproducible test in an isolated environment before changing timeout or retry policies.

## 16. Real-World Scenario: order-service Cannot Connect to inventory

**Context:** `order-service` calls `inventory-service` via `WebClient`. After a deployment, the `IO_ERROR` rate spikes. Client metrics show many failed requests without an HTTP status.

### Step 1 — Classify the exception

Logs show `WebClientRequestException` with cause `ConnectException`. This indicates TCP connections are being refused, not that inventory is returning 503.

### Step 2 — Check service discovery and endpoints

Check hostname, Kubernetes Service selector, EndpointSlices, port mapping, and readiness of inventory pods. A deployment with a mismatched selector can leave the Service with no ready endpoints.

### Step 3 — Inspect traces

The client span ends with an error and has no corresponding server span. This matches the hypothesis that requests are not reaching the inventory process. If a server span were present, continue investigating why requests reached the server and failed during the response phase.

### Step 4 — Review retry policy

If each request retries multiple times, total connect attempts spike. Count attempts separately, cap retries, and use backoff; do not trigger a retry storm when an endpoint has no listener.

### Step 5 — Verify after the fix

After restoring the endpoint, monitor:
- `IO_ERROR` rate and connect exception count drop.
- Client success rate increases.
- Client latency returns to baseline.
- Client/server trace spans reconnect.
- Retry attempts do not spike abnormally.

**Lesson:** `IO_ERROR` is not HTTP 5xx. When there is no response status, investigate network/transport first; use exception causes, client spans, and infrastructure state to find the failed phase.

## 17. Exercises and Self-Check Questions

### Exercise A — Generate transport errors

Use a mock server or test environment to produce:
- An unresolvable hostname.
- A port with no listener.
- A connect timeout.
- A read timeout.
- An untrusted TLS certificate.
- A prematurely closed response body.

Record the exception class, cause chain, whether an HTTP status exists, and how the client observation is exported.

### Exercise B — Distinguish HTTP responses from I/O failures

Mock 404, 503 responses and a connection reset. Verify 404/503 have status codes; connection reset has no HTTP response status. Do not map everything to status 500.

### Exercise C — Timeout budget

Design connect timeout, response timeout, overall timeout, and retry budget for a dependency with an SLA. Calculate maximum total time including attempts and backoff, ensuring it stays within the caller's deadline.

### Exercise D — Metrics and cardinality

Create a custom counter for `io_error` by dependency and exception category. Send requests with many different SKUs; verify SKUs do not create new metric series. Compare attempt failure rate against final operation failure rate.

### Exercise E — Tracing

Enable `WebClient` observation and tracing. Trigger a DNS/connect error to verify the client span has an error while there may be no downstream server span. Then have the mock server return 503 to compare response status and exception semantics.

### Exercise F — Retry/circuit breaker

Simulate a flaky dependency. Configure bounded retries, backoff, and a circuit breaker. Verify retries do not apply to certificate/hostname misconfigurations and do not amplify load.

### Self-check questions

1. How does `IO_ERROR` differ from HTTP 5xx?
2. Why does `ConnectException` usually have no HTTP response status?
3. Which phase does `UnknownHostException` indicate?
4. What should be checked for a TLS handshake failure?
5. How do `WebClientRequestException` and `WebClientResponseException` differ?
6. Why does `try/catch` around creating a `Mono` fail to catch errors occurring at subscription time?
7. In which phases can timeouts arise?
8. Can a response body fail after the status has already been received?
9. When is retrying `IO_ERROR` safe?
10. Why should you not retry endlessly when DNS or certificates are misconfigured?
11. How should a circuit breaker classify expected HTTP 404s?
12. Why might a client span have no downstream server span?
13. How do you keep cardinality low for `IO_ERROR` metrics?
14. What context and cause should an `IO_ERROR` log preserve?
15. How do you distinguish transport failure, decode error, cancellation, and business rejection?

**Completion criteria:** distinguish `IO_ERROR` from HTTP statuses; identify DNS/TCP/TLS/I/O phases; understand `WebClient`/Reactor exception mapping; configure budgeted timeouts/retries; observe metrics/traces/logs; control cardinality; investigate client failures without faking HTTP statuses.

## 18. Remember

- `IO_ERROR` is an I/O/transport error category, not an HTTP status code and not a single exception class.
- DNS, TCP connect, TLS handshake, socket write/read, pool acquire, and response streams can fail at distinct phases.
- HTTP 503 is a received response; connection refused or DNS failure usually has no response status.
- `WebClient` emits errors via reactive signals when the exchange executes; `try/catch` around publisher creation does not catch asynchronous errors.
- `WebClientRequestException` usually represents request/transport errors; `WebClientResponseException` usually represents response statuses treated as errors. Preserve the cause chain and inspect the connector.
- Timeouts can occur at DNS, connect, pool, TLS, read, or overall deadline; do not lump all timeouts into one cause.
- Retries should apply only to transient errors and safe operations; limit attempts, backoff, jitter, and deadlines.
- Use low-cardinality `outcome`/exception category metrics; do not put raw URLs, IDs, or exception messages into tags.
- A client span can carry an error even without a downstream server span if the request never reached the service.
- Distinguish `IO_ERROR`, HTTP response errors, decode failures, and cancellations so dashboards and alerts maintain accurate semantics.

## References

- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Reactor Netty Reference](https://projectreactor.io/docs/netty/release/reference/)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
