# Client timeout

Order Service calls Inventory Service to check stock availability. When Inventory is slow, Order's requests can hold threads and connections longer than expected. If many requests wait simultaneously, the thread pool or connection pool can become exhausted, spreading latency to other APIs. Timeouts bound the wait time at each phase of the HTTP client; HTTP client Observation shows whether an outbound request ended with a response, an HTTP error, or a timeout.

The **Client timeout** lesson belongs to the **HTTP client observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understanding context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

> **Principle:** There is no single timeout that automatically bounds the entire duration of an HTTP call. Connect timeout, read/response timeout, connection-pool acquisition timeout, and business deadlines protect different waiting intervals. Configuration must match the actual request factory/HTTP client, the caller's latency budget, and the retry policy. When a timeout occurs before receiving a response, the Observation typically has no real HTTP status; inspect `exception`, duration, and fallback status separately.

## 1. Learning Objectives

After this lesson, you can:
1. Explain why HTTP clients need timeouts in Spring Boot systems.
2. Distinguish connect, read/response, pool acquisition timeouts, and end-to-end deadlines.
3. Understand how timeouts are applied by `ClientHttpRequestFactory` and the HTTP client implementation.
4. Configure global timeouts via Spring Boot properties and per-client timeouts via `RestTemplateBuilder`.
5. Recognize timeout API differences across Spring Boot versions.
6. Distinguish timeout exceptions from HTTP 5xx responses.
7. Read client Observations, metrics, and traces when requests time out.
8. Design retry/backoff policies suited to the timeout budget and idempotency.
9. Prevent cascading overload across request threads, connection pools, or downstream services.
10. Test timeouts using a slow mock server and connection failure scenarios.
11. Investigate timeouts by phase: DNS, pool, connect, TLS, response, and body read.

## 2. Why Must Client Timeouts Be Configured?

An HTTP call can wait across multiple phases:
- Hostname/DNS resolution.
- Waiting for an available connection in the pool.
- Establishing the TCP connection.
- Performing the TLS handshake.
- Sending the request.
- Waiting for response headers.
- Reading the response body.
- Retrying one or more attempts.

Without proper bounds, requests can occupy threads and connections for a long time. When traffic increases, waiting requests pile up; the service may run out of threads, pools become saturated, queues lengthen, and latency cascades to other requests.

~~~mermaid
flowchart TD
    A["HTTP client call"] --> B["Acquire connection"]
    B --> C["DNS / TCP connect"]
    C --> D["TLS handshake"]
    D --> E["Send request"]
    E --> F["Wait for response"]
    F --> G["Read response body"]
    G --> H["Complete"]
    B -. "pool acquisition timeout" .-> X["Fail"]
    C -. "connect timeout" .-> X
    D -. "TLS/handshake timeout" .-> X
    F -. "response/read timeout" .-> X
    G -. "read timeout" .-> X
~~~

The diagram shows logical phases; specific HTTP clients may merge or implement certain phases differently. Not every request factory exposes separate timeouts for every phase.

## 3. Types of Timeouts to Distinguish

| Timeout Type | Which Wait Interval Does It Bound? | Example Errors/Symptoms |
|---|---|---|
| Connection-pool acquisition | Waiting to acquire a connection from the pool | Pool exhausted, lease timeout |
| DNS timeout | Hostname resolution | Unknown host or resolver timeout |
| Connect timeout | Establishing TCP connection | Connection timed out/refused |
| TLS handshake timeout | TLS negotiation | Handshake timeout/SSL exception |
| Response/read timeout | Waiting for response or next data | Read timed out, response timeout |
| Write timeout | Sending request/body to peer | Write timeout, broken pipe |
| End-to-end deadline | Total permitted business duration | Caller deadline exceeded |

Not every request factory lets you configure all timeout types. For example, a client may only expose connect and read timeouts, while pool acquisition timeout belongs to a separate connection manager. DNS/TLS timeouts may be managed by the HTTP implementation or use different settings.

### 3.1 Connect timeout

Connect timeout bounds how long the client waits to establish a connection to the host/port. It is not the maximum time for the server to process the request. Once the connection is established, connect timeout no longer limits waiting for the response.

### 3.2 Read/response timeout

Read timeout usually limits how long to wait for data when reading from the socket or response; exact semantics depend on the client implementation. Some HTTP clients define response timeout as time waiting for the response, while others apply a socket read timeout per read call. With streaming, timeouts between data chunks can differ from the overall deadline.

Do not assume read timeout is always the total duration from sending until receiving the full body. Check the documentation for the request factory in use.

### 3.3 Pool acquisition timeout

When using a connection pool, a request may wait for an idle connection before connecting to the server. Pool acquisition timeout protects this wait interval. If you only configure connect/read timeouts without a pool acquisition timeout, requests can still wait a long time even when connect timeout is low.

### 3.4 End-to-end deadline

A deadline is the total budget for the entire business operation, e.g., checking stock must complete within 800 ms. The deadline can encompass pool wait, connect, TLS, response, retries, serialization, and other business code.

A request with a 200 ms connect timeout and 500 ms read timeout can still exceed 800 ms if there is pool wait, retries, or multiple dependency calls. Therefore, you need deadlines at the caller/use-case layer combined with appropriate transport timeouts.

## 4. Configuring Global Timeouts in Spring Boot

Current Spring Boot versions support HTTP client defaults via the `spring.http.client` property group. Example:

~~~yaml
spring:
  http:
    client:
      connect-timeout: 2s
      read-timeout: 5s
~~~

These defaults apply to client builders/request factories managed by Spring Boot auto-configuration, depending on client type and version. Clients that create their own request factory or replace the builder may not receive these defaults.

Global timeouts establish a consistent baseline, though they may not fit every downstream service. Critical services may need shorter timeouts; reporting APIs may have a different budget. Create dedicated configurations when SLAs/use cases differ.

Documentation: [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html).

## 5. Configuring Timeouts via RestTemplateBuilder

In Spring Boot versions with the corresponding `RestTemplateBuilder` API, you can set connect and read timeouts:

~~~java
import java.time.Duration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
class InventoryClientConfiguration {

    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("https://inventory.internal")
                .connectTimeout(Duration.ofMillis(200))
                .readTimeout(Duration.ofMillis(600))
                .build();
    }
}
~~~

Builder APIs vary across versions. Spring Boot 3.4 and later have `connectTimeout`/`readTimeout` methods; the older `setConnectTimeout`/`setReadTimeout` APIs are deprecated in newer releases. Do not copy method names across versions without verifying the API in use.

If the application defines its own `RestTemplateBuilder` bean, preserve Boot's configuration using `RestTemplateBuilderConfigurer`; replacing the builder without the configurer can lose `RestTemplateCustomizer`s and auto-configured defaults.

### 5.1 Global timeouts vs. per-client timeouts

Use global timeouts for a baseline and separate builders for downstreams with different budgets.

| Client | Connect timeout | Read timeout | Reason |
|---|---:|---:|---|
| Inventory | 200 ms | 600 ms | Internal API needing fast responses |
| Payment | 500 ms | 2 s | External gateway with higher latency |
| Catalog | 300 ms | 1 s | Read-heavy, but should not hold requests long |

These are illustrative numbers only, not universal recommendations. Choose values based on latency distributions, SLOs, network characteristics, and dependency capacity.

## 6. Differences Between Spring Boot Versions

Timeout APIs and request factory configuration vary across versions:

| Spring Boot version | Common Configuration Approach |
|---|---|
| 3.0–3.3 | `RestTemplateBuilder` with `setConnectTimeout`/`setReadTimeout` |
| 3.4–3.5 | `connectTimeout`/`readTimeout`; `set*` methods deprecated; `requestFactorySettings` available since 3.4 |
| 4.x | `RestTemplateBuilder` API in a new package and client settings/request factory builders; check version reference |

Starting in Spring Boot 3.4, request factory settings enable more centralized configuration; Spring Boot 4.x continues evolving client settings and builder APIs. The package of `RestTemplateBuilder` also changed across major versions. Do not mix Boot 3 and Boot 4 imports in the same example.

References:
- [Spring Boot 3.4 RestTemplateBuilder](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/web/client/RestTemplateBuilder.html)
- [Spring Boot 4.0 RestTemplateBuilder](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/restclient/RestTemplateBuilder.html)
- [Spring Boot 4.2 RestTemplateBuilder](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/restclient/RestTemplateBuilder.html)

## 7. The Request Factory Determines Actual Timeouts

`RestTemplate` delegates HTTP exchanges to `ClientHttpRequestFactory`. The request factory can be backed by the JDK client, Apache HttpComponents, Jetty, or another implementation configured by the application.

Different factories do not necessarily share the same semantics or the same set of timeout options. Some support connection pooling and pool acquisition timeouts; others do not. Some apply read timeouts at the socket level; others expose a separate response timeout.

~~~mermaid
flowchart TD
    A["RestTemplate"] --> B["ClientHttpRequestFactory"]
    B --> C["JDK-based client"]
    B --> D["Apache HttpComponents"]
    B --> E["Jetty client"]
    C --> F["Implementation-specific timeout semantics"]
    D --> F
    E --> F
~~~

When changing the request factory or classpath dependencies, timeout behavior can change even if YAML does not. Inspect the actual factory, connection manager/pool, TLS settings, and version documentation.

### 7.1 When configuring a request factory manually

If providing a custom `ClientHttpRequestFactory` or builder, set timeouts at the proper layer of that implementation. Creating a factory manually can prevent some Boot defaults from being applied. Test actual timeouts with a slow request, rather than merely asserting that properties bound.

## 8. Timeouts and HTTP Client Observation

`RestTemplate` Observation records outbound exchanges. When a request completes:
- Response received: `status` and `outcome` can be recorded.
- 5xx response: status 5xx; `DefaultResponseErrorHandler` may throw `HttpServerErrorException`.
- Connect/read timeout before response: no HTTP status from server; instrumentation may record fallback `UNKNOWN` and the exception type.
- Pool acquisition failure: may occur before sending the request; error context reflects the exception from the pool/client implementation.

Example:

~~~text
method = GET
uri = /api/items/{sku}
clientName = inventory.internal
status = UNKNOWN
error = ResourceAccessException
duration = 612 ms
~~~

This is illustrative data. The actual exception type depends on the request factory; timeouts may be wrapped as `ResourceAccessException`, `IOException`, `SocketTimeoutException`, or an HTTP client-specific exception.

**Do not change a timeout into `status=504` in a client Observation if the client did not receive HTTP 504 from the server.** 504 is only valid when an actual HTTP 504 response occurred. If a gateway/caller generates a 504 response itself after a dependency times out, the server Observation on the caller side may have status 504 while the outbound client Observation has status `UNKNOWN`.

## 9. Reading Timeouts in Traces

When an inbound request calls multiple dependencies, client spans show how long each outbound call took and where it failed.

~~~mermaid
flowchart LR
    A["Order server span<br/>920 ms"] --> B["Inventory client span<br/>600 ms"]
    A --> C["Payment client span<br/>200 ms"]
    A --> D["Validation/response<br/>120 ms"]
~~~

The example illustrates a total request of roughly 920 ms; the Inventory call took 600 ms. If the Inventory span ended with a timeout after 600 ms, the trace helps identify the dependency as the largest wait.

In the trace backend, inspect:
- Client span start/end and duration.
- Error event/exception type.
- Status code if a response was actually received.
- Parent server span and sibling client spans.
- Retry attempts if each attempt has its own span.
- Whether trace context propagated downstream.

Sampling can omit some traces from export; timeout/error rate metrics remain useful for spotting overall trends.

## 10. Timeout Budgets and Retries

Retries do not make timeouts disappear; they consume additional budget. A logical operation with a 1-second deadline that retries 3 times with a 600 ms read timeout per attempt can overshoot the deadline significantly if attempts and backoff are not bounded.

A retry budget should account for:
- The caller's overall deadline.
- Per-attempt timeout.
- Maximum retry attempts.
- Backoff and jitter.
- Pool acquisition/connect time per attempt.
- Remaining time before the deadline.
- Idempotency of the operation.
- `Retry-After` from the server, if present.

~~~text
Caller deadline: 1000 ms
Attempt 1 budget: 300 ms
Backoff: 50 ms
Attempt 2 budget: 300 ms
Backoff: 100 ms
Attempt 3 budget: remaining 250 ms
Reserve for response/cleanup: remaining budget
~~~

This example only illustrates how to split a budget. Do not let combined attempt budgets and backoffs exceed the deadline. When insufficient time remains for a useful attempt, fail fast rather than starting a request guaranteed not to finish within budget.

### 10.1 Do not blindly retry every timeout

- GET/idempotent operations can usually be retried per policy.
- A `POST` creating a payment/order may already have been processed by the server even though the client timed out; retrying can create duplicate transactions without an idempotency key.
- 4xx such as 400/401/403 should generally not be retried as transient errors.
- 429/503 may be retried if policy and `Retry-After` allow.
- TLS certificate/configuration errors are not solved by continuous retries.
- DNS/connect failures may be transient but require backoff/jitter and limits.

A client-side timeout does not prove the server did not process the request. Before retrying mutations, design idempotency or reconciliation.

## 11. Timeouts, Connection Pools, and Bulkheads

For pooled HTTP clients, a connection is held while a request waits for a response. If downstream slows down, the pool quickly runs out of connections. New requests wait to acquire a connection and can time out even before connecting.

Monitor separately:
- Pool leased/available/pending connections.
- Pool acquisition duration/timeouts.
- Connect failures and connect latency.
- Active requests and request queues.
- Response latency and timeout counts.

A bulkhead limits concurrent calls to a dependency so a slow service cannot consume all of the application's resources. Semaphore/thread-pool isolation or connection-pool limits can be used depending on architecture. Timeouts and bulkheads complement each other: timeouts limit duration; bulkheads limit concurrent resource consumption.

## 12. DNS, TLS, and Other Timeout Phases

Not every connection error is a connect timeout:

| Phase | Symptoms | Investigation Direction |
|---|---|---|
| DNS | `UnknownHostException`, resolver delay | DNS server, search domains, TTL, resolver timeout |
| Pool acquire | Lease timeout, pending rising | Pool max, leaks, unclosed response bodies, concurrency |
| TCP connect | Connect timed out/refused | Routing, firewall, endpoint health |
| TLS handshake | `SSLHandshakeException`, handshake timeout | CA chain, certificates, protocol, peer |
| Write | Broken pipe, write timeout | Peer close, request body size, network |
| Read/response | `SocketTimeoutException`, response timeout | Downstream latency, network, server saturation |
| Body decode | Conversion exception after response | `Content-Type`, payload, message converter |

When a TLS handshake fails, the client has not sent an HTTP request yet; hence there is no HTTP status. Do not disable certificate verification to work around timeout/handshake errors. Fix the CA, hostname, certificate validity, and truststore properly.

## 13. Controlled Timeout Testing

A reliable timeout test needs to simulate the exact waiting phase. Use a mock server or a local test server with delayed endpoints.

Scenarios:
1. Server accepts the connection but delays response headers past read/response timeout.
2. Server sends headers promptly but delays body chunks to test read inactivity timeout.
3. Unopened port to test connect refused (does not necessarily wait for full connect timeout).
4. Unresolvable host to test DNS failure.
5. Small pool limit holding a connection to test acquisition timeout if the client supports it.
6. TLS server with an untrusted certificate to test handshake failure.
7. Multiple retry attempts to test the total deadline.

### 13.1 Slow test server example

~~~java
@RestController
class SlowController {

    @GetMapping("/slow")
    String slow() throws InterruptedException {
        Thread.sleep(1500);
        return "done";
    }
}
~~~

If the client read timeout is under 1.5 seconds, the request can fail before the server returns a response. This is an illustrative test; use controlled delays and avoid long sleeps in the main test suite when a latch or mock server can be used instead.

### 13.2 Asserting Observations

Use a test `ObservationRegistry` or `MeterRegistry` to verify:
- Observation starts and stops even when the request throws an exception.
- Duration is recorded.
- Error contains the appropriate exception.
- Status is `UNKNOWN` when there is no response.
- Status is 503 if the mock server actually returns 503.
- Retry attempts produce the expected number of Observations.
- No metric tags contain raw URLs/SKUs/request IDs.

Do not assert only that the client throws an exception; verify the signals and context that the system relies on in operations.

## 14. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Request waits very long despite short connect timeout | Waiting on pool or response; connect timeout does not apply | Configure appropriate acquisition/read/deadline timeouts |
| Read timeout has no effect | Request factory does not support it or custom factory ignores settings | Check factory/implementation and run actual tests |
| Request times out before connect | Pool acquisition or DNS timeout | Inspect pool pending count and DNS |
| Client span status `UNKNOWN` | No HTTP response received before failure | Check exception type and timeout phase |
| Client span status `504` | Actual HTTP 504 response from proxy/server | Investigate gateway/downstream; distinguish from local timeout |
| Timeouts appear after dependency change | Request factory/client implementation changed | Check classpath and selected factory |
| Pool pending rises and latency spreads | Connections held too long or pool too small | Check response body lifecycle, pool sizing, and bulkhead |
| Retries overload dependency | Unbounded attempts/backoff or retrying every error | Set retry budget, jitter, and retryable classification |
| `POST` executed twice after timeout | Caller unsure if server processed request | Idempotency keys and reconciliation |
| Trace lacks downstream server span | Request never reached server or propagation stripped | Check client duration, network, and trace headers |
| Flaky timeout tests | Relying on tight sleeps/timing | Use latches, mock servers, and clear margins |
| TLS errors retried continuously | Treating configuration errors as transient | Fail fast, fix CA/certificate/truststore |

## 15. Playbook: Inventory Call Exceeds Latency Budget

**Scenario:** Order API p95 exceeds its SLO; traces show the Inventory call waiting a long time and occasionally timing out.

1. Filter traces by the affected route and time window.
2. Open the Inventory client span and compare its duration with the Order API deadline.
3. Check status and error: a 503 response differs from a local `UNKNOWN` timeout.
4. If the timeout occurred before connect, inspect pool pending/acquisition and DNS.
5. If connect succeeded but response was slow, inspect Inventory's server span/logs and network latency.
6. Compare p50/p95/p99, timeout counts, and pool metrics.
7. Check retry attempts, backoff, idempotency, and total duration.
8. Choose per-attempt timeouts smaller than the overall deadline, leaving budget for remaining work.
9. Limit concurrency/add a bulkhead if the dependency can saturate.
10. Retest with delayed responses and verify the client Observation records duration/error/status properly.

Do not merely increase timeouts to reduce exceptions. Overly long timeouts hold resources longer and let incidents cascade.

## 16. Self-Check Exercises

**Exercise 1 — Distinguishing timeouts.** A request waits 400 ms on the connection pool, 50 ms to connect, and 200 ms to read. Which timeout bounds pool wait time? Why does connect timeout not solve it?

**Exercise 2 — No HTTP response.** DNS lookup fails. What status should the client Observation record? Why should you not assign a fake 500 or 504 to the outbound call?

**Exercise 3 — Deadline.** The caller has a 900 ms deadline, each attempt has a 700 ms read timeout, and up to two retries are allowed. Why can this configuration exceed the deadline? Allocate a more reasonable budget.

**Exercise 4 — Spring Boot versions.** Why might `setReadTimeout` examples be deprecated in Spring Boot 3.4+, and what should you check before copying code?

**Exercise 5 — Request factory.** An application switches from the JDK request factory to Apache HttpComponents and timeout behavior changes. Which semantics should be checked?

**Exercise 6 — POST retries.** A payment request times out after sending the body. Why could retrying create a duplicate charge? What is the role of an idempotency key?

**Exercise 7 — Pool saturation.** Pool pending increases, and no connect timeouts appear. What does this suggest and which metrics should be measured?

**Exercise 8 — Traces.** A client span has duration 600 ms, status `UNKNOWN`, and error `SocketTimeoutException`. List possible causes and an investigation order.

### Suggested Answers

1. Pool acquisition timeout bounds the wait for a connection. Connect timeout only starts when the client begins establishing the connection.
2. `UNKNOWN`/fallback per convention because no HTTP response was received. 500/504 are only valid when the server/proxy actually returned those statuses.
3. Two 700 ms attempts plus backoff and pool/connect time can exceed 900 ms. Split the deadline into per-attempt budgets, backoff, and reserve for response/cleanup.
4. Newer builder APIs use `connectTimeout`/`readTimeout`; older `set*` methods are deprecated. Verify your Spring Boot version and request factory API.
5. Connect/read/response timeout semantics, pool acquisition, TLS, redirects, cancellation, and default values.
6. The server may already have processed the charge before the response was lost; an idempotency key lets the server recognize retries belonging to the same logical operation.
7. Requests are waiting for the connection pool, not connecting. Measure leased/available/pending counts, acquisition duration, and acquisition timeouts.
8. Check read/response timeout, server latency, network, body streaming, pool, and retries; `UNKNOWN` status means no HTTP response was received.

## 17. Official References

- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): `RestTemplateBuilder`, global HTTP client settings, request factories, and timeout configuration.
- [Spring Boot 3.4 — RestTemplateBuilder API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/web/client/RestTemplateBuilder.html): `connectTimeout`/`readTimeout` and `requestFactorySettings`.
- [Spring Boot 4.0 — RestTemplateBuilder API](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/restclient/RestTemplateBuilder.html): builder/client settings in Boot 4.
- [Spring Boot 4.2 — RestTemplateBuilder API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/restclient/RestTemplateBuilder.html): current API and deprecated methods.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestTemplate` and `ClientHttpRequestFactory`.
- [Apache HttpComponents Client](https://hc.apache.org/httpcomponents-client-5.5.x/current/user-manual/html/): connection manager, connection request timeout, and socket/response timeout.
- [JDK HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): connect timeout and request timeout of the JDK client.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle and handlers.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): client spans, error recording, and context propagation.
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/): HTTP client duration, status, and error attributes.

**Remember:** Timeouts protect the caller's resources and latency budget. Connect timeout does not limit pool wait or response reads; read timeout is not necessarily the total deadline. The request factory determines actual semantics, so test after changing client implementations or Spring Boot versions. Observe duration, exceptions, status, pool metrics, and retry attempts together; timeouts before a response usually have no HTTP status. Base retries on deadlines and idempotency, and limit concurrency so a slow dependency cannot take down the caller.
