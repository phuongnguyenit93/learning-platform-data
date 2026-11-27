# Hands-On Measurement and Classification of Each Timeout Type

A request from `order-service` to `catalog-service` can fail after 300 ms because it **could not lease a connection from the pool**, after 800 ms because it **could not establish TCP**, or after 1,000 ms because **the server has not returned a response**. All three are casually called “timeout,” yet they have completely different root causes and fixes.

In **Spring Cloud LoadBalancer**, you must also separate the **finding the `ServiceInstance` list and picking a replica** stage from the HTTP client's request execution stage. Increasing `readTimeout` rarely solves discovery issues; raising pool timeouts may merely mask connection shortages or unreleased requests.

This hands-on lesson in the **Timeouts** chapter builds a small measurement harness using `RestClient` with Apache HttpClient 5 as the primary lab, then compares `WebClient`/Reactor Netty and Spring Cloud OpenFeign. The goal is to **reproduce a controlled symptom, measure actual timing, pinpoint the right layer, and tune the right parameter**.

> All configurations, endpoints, and time thresholds in this lesson are strictly for local/test environments. Never deploy delay-injecting endpoints or packet-dropping techniques in production.

## 1. Timing Map of a Service Call

An HTTP call can pass through the following legs:

~~~mermaid
flowchart TD
    A["Application builds request by service ID"]
    B["Discovery / cache / filter ServiceInstance list"]
    C["LoadBalancer selects instance"]
    D["Wait for connection pool to lease connection"]
    E["DNS if endpoint uses hostname"]
    F["New TCP connection"]
    G["TLS handshake if HTTPS"]
    H["Send request"]
    I["Wait for response headers / first byte"]
    J["Read response body"]
    K["Decode and return result to business logic"]
    A --> B --> C --> D --> E --> F --> G --> H --> I --> J --> K
~~~

This diagram shows **possible stages**, not that every request executes all of them. When the connection pool returns a live connection, DNS, TCP, and TLS steps can be **skipped on that call**. With HTTP/2 and proxies, the path also differs due to multiplexing or routing.

| Stage | Common limit | Primary owner | On failure, what to ask? |
|---|---|---|---|
| Discovery/selection | Discovery timeout or data-source timeout | Spring Cloud LoadBalancer, discovery client, supplier | Was any instance found? |
| Waiting for pool connection | Pool acquisition/lease timeout | Apache HttpClient, Reactor Netty connection provider | Is the pool out of slots or are connections held too long? |
| DNS | Resolver query timeout | DNS resolver/transport | Can the instance host be resolved? |
| TCP connect | Connect timeout | HTTP transport | Can the address/port accept a connection? |
| TLS handshake | SSL/TLS handshake timeout | TLS stack/HTTP transport | Did the security handshake complete? |
| Waiting for reply | Response/read timeout depending on library | HTTP transport | Did the server start or continue sending a response? |
| Reading response body | Socket read inactivity/response timeout | HTTP transport and body decoder | Did the body pause too long? |
| Total single operation | End-to-end deadline | Application layer or reactive pipeline | Did all attempts exceed the business budget? |

**There is no single “LoadBalancer global timeout” controlling all of these stages.** Any concrete timeout property must always be tied to the exact API, HTTP client, and library version in use.

## 2. Preparing the Test Environment

For the clearest observations, start with **one** `catalog-service` replica on port `8081` and one `order-service` as the client. With a single instance, pool leasing is not spread across different routes. Once each failure mode is classified, add a second instance on `8082` to observe load-balancing effects.

Example Gradle Kotlin DSL dependencies for the **mock server**, with a compatible Spring Boot and Spring Cloud BOM configured in the project:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

For the **test client using RestClient and Apache HttpClient 5**:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("org.apache.httpcomponents.client5:httpclient5")
}
~~~

These snippets assume Java 17+ and a Spring Framework version with `RestClient` (6.1+). Dependencies omit a separate service registry because the lab uses `SimpleDiscoveryClient`.

### Configuring a Single Static Instance

In the client application:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
~~~

`127.0.0.1` only works when server and client run on the same host or network namespace. In containers, replace it with a hostname/IP reachable by the client.

Using a static list isolates `ServiceInstance` selection from registry fluctuations. However, when the server stops, `SimpleDiscoveryClient` **does not automatically remove** the endpoint from configuration.

## 3. Building a Backend Simulating Fast, Slow, and Interrupted Responses

Create a controller **enabled only in the lab environment**:

~~~java
import java.nio.charset.StandardCharsets;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class TimeoutLabController {

    @GetMapping("/lab/fast")
    String fast() {
        return "fast-ok";
    }

    @GetMapping("/lab/delay-headers")
    String delayHeaders(
            @RequestParam(defaultValue = "2500") long ms
    ) throws InterruptedException {
        long delay = Math.max(0, Math.min(ms, 5000));
        Thread.sleep(delay);
        return "delayed-ok";
    }

    @GetMapping(value = "/lab/gap-body",
                produces = MediaType.TEXT_PLAIN_VALUE)
    void gapBody(
            @RequestParam(defaultValue = "2500") long ms,
            HttpServletResponse response
    ) throws Exception {
        long delay = Math.max(0, Math.min(ms, 5000));

        response.getOutputStream().write(
                "part-1\n".getBytes(StandardCharsets.UTF_8));
        response.flushBuffer(); // Flush headers and first part of body.
        Thread.sleep(delay);
        response.getOutputStream().write(
                "part-2\n".getBytes(StandardCharsets.UTF_8));
        response.getOutputStream().flush();
    }
}
~~~

Three routes create three scenarios:

| Endpoint | Server behavior | Used to measure |
|---|---|---|
| `/lab/fast` | Returns immediately | Baseline and connectivity verification |
| `/lab/delay-headers?ms=2500` | Waits before producing response | Initial response wait time |
| `/lab/gap-body?ms=2500` | Sends first chunk, flushes, waits, then sends second chunk | Gap while reading response body |

`Thread.sleep` intentionally holds a servlet worker thread to simulate a slow backend; never use this pattern in production applications. Some proxies, buffers, or runtimes can shift when bytes actually reach the client; for `gap-body`, verify with packet/network traces or client logs if results look unexpected.

### Baseline Before Measuring Timeouts

Send a test `GET /lab/fast` and verify:

- The server receives the request and returns HTTP 200.
- The client resolves `catalog-service` to instance `127.0.0.1:8081`.
- No unexpected retries, circuit breakers, or intermediate proxies skew the measurement.

Without a passing baseline, do not use subsequent failures to infer timeout effects.

## 4. Configuring RestClient with Explicit Limits per Type

Apache HttpClient 5 can separate **pool lease wait**, **connect**, **socket I/O**, and **response**. The configuration below sets one connection per route to make pool contention easy to reproduce.

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class TimeoutLabClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient timeoutLabApacheClient() {
        var connectionManager =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(2)
                        .setMaxConnPerRoute(1)
                        .setDefaultConnectionConfig(
                                ConnectionConfig.custom()
                                        .setConnectTimeout(
                                                Timeout.ofMilliseconds(800))
                                        .setSocketTimeout(
                                                Timeout.ofSeconds(5))
                                        .build())
                        .build();

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(
                        Timeout.ofMilliseconds(300))
                .setResponseTimeout(Timeout.ofSeconds(1))
                .build();

        return HttpClients.custom()
                .setConnectionManager(connectionManager)
                .setDefaultRequestConfig(requestConfig)
                .disableAutomaticRetries()
                .build();
    }

    @Bean("timeoutLabRestClientBuilder")
    @LoadBalanced
    RestClient.Builder timeoutLabRestClientBuilder(
            CloseableHttpClient timeoutLabApacheClient) {
        return RestClient.builder().requestFactory(
                new HttpComponentsClientHttpRequestFactory(
                        timeoutLabApacheClient));
    }

    @Bean("timeoutLabRestClient")
    RestClient timeoutLabRestClient(
            @Qualifier("timeoutLabRestClientBuilder")
            RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Configured values:

| Apache HttpClient 5 parameter | Lab value | Meaning |
|---|---|---|
| `setConnectionRequestTimeout` | 300 ms | Wait for a connection slot from the pool |
| `ConnectionConfig#setConnectTimeout` | 800 ms | Establish a new connection |
| `ConnectionConfig#setSocketTimeout` | 5 s | Underlying socket read/I/O value |
| `setResponseTimeout` | 1 s | Wait for response per HttpClient 5 semantics; can override socket timeout during message exchange |
| `setMaxConnPerRoute` | 1 | Makes pool contention easy to reproduce when multiple requests hit the same endpoint |
| `setMaxConnTotal` | 2 | Manager's total connection limit |
| `disableAutomaticRetries` | Enabled | Prevents transport from auto-retrying and skewing single-attempt measurements |

**Remember:** in newer Apache HttpClient 5 versions, `RequestConfig#setConnectTimeout` is deprecated; use `ConnectionConfig#setConnectTimeout` to configure connect timeout. `RequestConfig#setResponseTimeout` **is not an overall deadline** for the whole operation, especially with retries or multiple I/O steps.

In this example, `@LoadBalanced` is attached to `RestClient.Builder` to pick instances; the Apache client still owns HTTP and pooling. If your project needs Spring Boot customizers, consider integrating `RestClientBuilderConfigurer` instead of creating a raw builder that accidentally drops Boot-configured observability or converters.

## 5. Measuring Elapsed Time and Printing the Exception Cause Chain

Use `System.nanoTime()` to measure elapsed time from invocation until receiving a result or exception. This is **total application-observed time**, not an isolated TCP or DNS measurement.

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class TimeoutLabProbe {

    private final RestClient client;

    TimeoutLabProbe(
            @Qualifier("timeoutLabRestClient") RestClient client) {
        this.client = client;
    }

    void run(String relativeUri) {
        long started = System.nanoTime();

        try {
            String body = client.get()
                    .uri(relativeUri)
                    .retrieve()
                    .body(String.class);

            System.out.printf(
                    "OK uri=%s elapsedMs=%d body=%s%n",
                    relativeUri,
                    elapsedMillis(started),
                    body);
        } catch (Exception error) {
            System.out.printf(
                    "FAILED uri=%s elapsedMs=%d%n",
                    relativeUri,
                    elapsedMillis(started));

            Throwable current = error;
            while (current != null) {
                System.out.println(
                        "  cause=" + current.getClass().getName()
                        + " message=" + current.getMessage());
                current = current.getCause();
            }
        }
    }

    private static long elapsedMillis(long start) {
        return TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);
    }
}
~~~

Example invocations from the test app:

~~~java
probe.run("/lab/fast");
probe.run("/lab/delay-headers?ms=2500");
probe.run("/lab/gap-body?ms=2500");
~~~

Measured values depend on scheduling, networking, machine load, proxies, and transport. Do not set a pass criterion of “exactly 1,000 ms”; compare ranges and exception types instead.

### Sample Log Record to Collect

~~~text
traceId=lab-001
serviceId=catalog-service
selectedInstance=127.0.0.1:8081
endpoint=/lab/delay-headers
elapsedMs=1008
error=...timeout...
attempt=1
~~~

This is a **learner-designed log format**, not default Spring Cloud fields. `selectedInstance` and `attempt` must be instrumented from the LoadBalancer/HTTP layer to record real values.

## 6. Lab A — Slow Response: Response Timeout

**Goal:** see the difference between a slow-responding server and a connect error.

Preconditions: server on `8081` is running, client has one instance configured, `responseTimeout = 1 s`.

Steps:

1. Call `/lab/fast` to verify the connection path works.
2. Call `/lab/delay-headers?ms=2500`, making the server wait 2.5 s before sending a response.
3. Record elapsed time, exception chain, and whether server logs show the request arrived.
4. In a separate measurement run, raise response timeout to 4 s and call the same endpoint again.
5. Compare success/failure when changing only the response timeout.

Typical observations:

| Request | Response timeout | Expected |
|---|---|---|
| `/lab/fast` | 1 s | Succeeds faster than timeout |
| `/lab/delay-headers?ms=2500` | 1 s | Client typically times out waiting for reply |
| `/lab/delay-headers?ms=2500` | 4 s | Likely succeeds if network and server are stable |

If the server logged receiving the request yet the client did not receive a timely response, the primary suspect is backend/proxy response generation or HTTP reading—**not LoadBalancer failing to find an instance**.

Do not use this measurement to claim production's worst-case server delay is 2.5 seconds: this is a mock server without DBs, queues, GC, thread pools, or downstream dependencies.

## 7. Lab B — Interrupted Body: Read/Socket Inactivity

**Goal:** distinguish “received response headers / first byte” from “finished reading the entire body.”

Call:

~~~http
GET http://catalog-service/lab/gap-body?ms=2500
~~~

The server sends `part-1`, flushes, and waits 2.5 s before sending `part-2`. With `retrieve().body(String.class)`, the call finishes only once the entire body has been read and decoded, or when an error occurs.

If the transport applies a read/response limit shorter than the pause in sending the body, the client **can time out mid-stream**, even though the server accepted the request and headers already arrived.

To verify it is a body-read timeout rather than judging solely by total elapsed time:

- Record timestamps when the server sends the first part and the second part.
- Check HTTP client logs or packet traces to confirm headers/`part-1` arrived.
- Compare against `/lab/delay-headers` (where the server has not sent anything yet).
- Check whether `responseTimeout` overrides `socketTimeout` in your library/transport version.

**Warning:** Apache HttpClient 5 defines response timeout at the HTTP exchange level and can apply it during reading; do not assume it only bounds “time to first byte.” To measure **TTFB** accurately, use HTTP transport hooks or network traces; `System.nanoTime()` around `body(String.class)` only measures time to receive the **full body**.

## 8. Lab C — Connection Pool Wait: Pool Acquisition Timeout

**Goal:** trigger a timeout before the second request is even sent to the backend.

Keep `maxConnPerRoute = 1`, `connectionRequestTimeout = 300 ms`, and one instance on `8081`. For this test, **raise response timeout to 5 seconds** so the first request holds the connection long enough.

1. Send the first request to `/lab/delay-headers?ms=3000` in one thread.
2. Once the server logs receiving the first request, immediately send a second request from another thread to the same endpoint.
3. Because the pool allows only one connection per route, the second request must wait for a slot.
4. Observe the second request timing out waiting for the pool after roughly 300 ms, while the server **may never receive** the second request.
5. Re-measure after increasing `maxConnPerRoute` to 2; both requests can now execute concurrently.

~~~mermaid
sequenceDiagram
    participant A as Thread A
    participant B as Thread B
    participant Pool as HTTP connection pool
    participant Server as catalog-service
    A->>Pool: Request connection
    Pool-->>A: Grant sole slot
    A->>Server: GET /delay-headers 3000ms
    B->>Pool: Request connection for same route
    Note over B,Pool: Waits over 300ms
    Pool-->>B: Pool lease timeout
    Server-->>A: HTTP 200 after 3000ms
    A->>Pool: Return connection to pool
~~~

In this situation, B's failure does not prove the backend was slow to answer B: B did not even have a connection to send on. **Raising connect timeout will not fix a shortage of pool slots.**

Starting two threads simultaneously does not guarantee which thread leases the connection first; for reproducible runs, wait until the server receives request 1 or observe `leased=1` before firing request 2.

### How to Measure the Pool

With Apache HttpClient 5, call `PoolingHttpClientConnectionManager.getTotalStats()` and `getStats(route)` on the connection manager to inspect `leased`, `pending`, and `available` counts. To observe them, keep the created manager as a bean or instrument it; the basic configuration snippet only shows pool creation and does not emit these metrics by itself.

## 9. Lab D — TCP Connect Timeout vs. Connection Refused

**Goal:** avoid confusing a closed port with dropped connection packets.

Two distinct scenarios:

| Experiment | How to trigger | Typical result |
|---|---|---|
| **Connection refused** | Stop the server on a port still returned by discovery | OS typically returns a refusal error very quickly, **without waiting for connect timeout** |
| **Connect timeout** | In a test network, use a proxy/network fault injection to **drop** TCP handshake packets without sending RST | Connection waits until connect timeout or another system limit |

Do not pick an IP that “looks nonexistent” expecting a guaranteed connect timeout: depending on routing, you may get `Network unreachable`, `No route to host`, or an instant refusal.

Procedure:

1. Keep `connectTimeout = 800 ms` and ensure the pool must open a **new connection** (not reuse an old socket).
2. Test the `Connection refused` case with the server stopped.
3. Use a fault-injection tool in the lab network to drop SYN packets; measure elapsed time and exception.
4. Remove fault injection; confirm `/lab/fast` succeeds again.

Here, inspecting packet/network traces helps prove TCP never established, rather than relying solely on `elapsedMs`.

## 10. Lab E — DNS and TLS Handshake Timeouts

Both stages also occur before the business HTTP request receives a response, yet **you must not assume they share the same `connectTimeout`** in every client.

### DNS

If an instance has a URI like `http://catalog.internal:8081`, the HTTP transport may need to resolve hostname `catalog.internal`. Conversely, with `http://127.0.0.1:8081`, no DNS lookup runs for the target host.

- A wrong or nonexistent domain can trigger `UnknownHostException` / name resolution failure very fast; **that is not automatically a DNS timeout**.
- A true DNS timeout requires an unresponsive DNS resolver or dropped DNS queries in a test environment.
- Java/JDK HTTP transport, Apache HttpClient, and Reactor Netty use different resolvers and timeout controls. No single Spring Cloud LoadBalancer property governs DNS timeouts across all adapters.

With Reactor Netty, the DNS resolver exposes `queryTimeout` and resolver timing metrics. Never copy Reactor Netty settings into Apache HttpClient or Feign running another transport.

### TLS Handshake

For HTTPS endpoints, after TCP opens there is a TLS negotiation phase. Distinguish:

- `SSLHandshakeException` due to bad certificates, protocol mismatch, or truststore issues: this is a **TLS error**, not necessarily a timeout.
- TLS handshake timeout: peers failed to finish negotiation on time; inspect transport handshake timeouts and traces.
- Connect timeout may include part of transport-security overhead depending on implementation; do not assume all versions account for time identically.

To practice TLS timeouts, use a **test TLS proxy** configured to hold connections open without answering the handshake—never disable certificate validation in production. Reactor Netty provides `handshakeTimeout` on the SSL provider; Apache HttpClient has its own TLS connection API/lifecycle.

## 11. WebClient/Reactor Netty: Comparing the Same Tests

When using `WebClient` with Reactor Netty, configure pools, connect timeouts, and response timeouts using Netty APIs rather than copying Apache HttpClient 5 settings.

Example client using Spring WebFlux and Spring Cloud LoadBalancer:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
class ReactiveTimeoutLabConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider timeoutLabConnectionProvider() {
        return ConnectionProvider.builder("timeout-lab")
                .maxConnections(1)
                .pendingAcquireTimeout(Duration.ofMillis(300))
                .build();
    }

    @Bean
    @LoadBalanced
    WebClient.Builder timeoutLabWebClientBuilder(
            ConnectionProvider timeoutLabConnectionProvider) {

        HttpClient httpClient = HttpClient
                .create(timeoutLabConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 800)
                .responseTimeout(Duration.ofSeconds(1));

        return WebClient.builder().clientConnector(
                new ReactorClientHttpConnector(httpClient));
    }
}
~~~

With this WebClient, the APIs mean:

| Reactor Netty | Purpose |
|---|---|
| `pendingAcquireTimeout` | Time waiting to lease a connection |
| `CONNECT_TIMEOUT_MILLIS` | Time to establish TCP connection |
| `responseTimeout(Duration)` | Wait/read response limit per Netty |
| SSL provider `handshakeTimeout` | TLS handshake limit |
| DNS resolver `queryTimeout` | Limit per DNS query |
| Reactor `Mono.timeout(Duration)` | Time limit at the subscribed publisher level |

Example deadline over the **entire publisher**:

~~~java
WebClient client = timeoutLabWebClientBuilder
        .baseUrl("http://catalog-service")
        .build();

String body = client.get()
        .uri("/lab/delay-headers?ms=2500")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2))
        .block();
~~~

In this example, Netty-layer `responseTimeout(1s)` can fire **before** `Mono.timeout(2s)`. To observe `Mono.timeout` in isolation, raise the response timeout in a separate run and compare results.

When `retryWhen(...)` is present, `timeout(...)` placement is crucial: placing timeout **outside** the whole retry chain limits total subscription time, whereas placing it inside the retried branch re-applies per attempt. Also remember client-side request cancellation does not guarantee the backend stopped working.

Reactor Netty exposes per-phase metrics such as `reactor.netty.http.client.connect.time`, `...tls.handshake.time`, `...address.resolver`, and `reactor.netty.connection.provider.pending.connections.time` when the relevant Micrometer instrumentation is enabled. Do not infer phase timings solely from a timer wrapping `block()`.

## 12. OpenFeign: connectTimeout/readTimeout and Measurement Limits

Spring Cloud OpenFeign provides two common named-client timeout properties:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            connectTimeout: 800
            readTimeout: 1000
~~~

The values above use **milliseconds** per Feign configuration. A Feign interface may declare:

~~~java
@FeignClient(name = "catalog-service")
interface CatalogProbeFeignClient {

    @GetMapping("/lab/fast")
    String fast();

    @GetMapping("/lab/delay-headers")
    String slow(@RequestParam("ms") long ms);
}
~~~

`connectTimeout` bounds new connections; `readTimeout` governs response reception per Feign/transport. They do not break out pool lease, DNS, or TLS stages when looking only at Feign config. If Feign uses Apache HttpClient 5 underneath, those stages also obey connection manager options.

To keep experiment results interpretable:

- Run a `fast()` request as a baseline.
- Run `slow(2500)` and record elapsed time and the exception chain.
- Toggle a fixed URL only when comparing direct transport against service-ID calls.
- Check whether `FeignBlockingLoadBalancerClient` or another customized Feign `Client` is active.
- Ensure retry behavior is explicitly known. Spring Cloud OpenFeign typically registers `Retryer.NEVER_RETRY` by default, yet LoadBalancer or another resilience layer can add retries depending on dependencies and settings.

**Never conclude that `readTimeout: 1000` means the whole business call always finishes within 1 second** when queuing, DNS, multiple attempts, or pre/post-HTTP processing exist.

## 13. Discovery/LoadBalancer Delay Differs from Network Timeouts

A call by service ID can slow down **before the HTTP client even has a physical target**:

~~~text
order-service
  -> retrieve instance list for catalog-service
  -> filter by health/zone/hint
  -> select ServiceInstance
  -> lease connection / DNS / TCP / TLS
  -> send HTTP and wait for response
~~~

If discovery is slow or a supplier runs health/refetch synchronously with requests, waiting in this stage inflates total duration. Spring Cloud LoadBalancer exposes properties like `spring.cloud.loadbalancer.service-discovery.timeout` in supported versions, but verify **which discovery flow it applies to** and do not equate it with Apache/Netty connect timeouts.

Three scenarios to distinguish:

| Symptom | Likely cause |
|---|---|
| No `ServiceInstance` after lookup | Empty discovery/supplier or all candidates filtered out; no HTTP request necessarily sent to backend |
| Instance selected, HTTP connect times out | Transport connection failure to the chosen instance |
| Instance selected, server received request, response slow | Backend, proxy, or response-reading latency/error |

Code measuring `start` before calling Feign/RestClient and `end` after receiving the body **lumps everything together**: discovery, pooling, connect, response, decoding, and possibly retries. Separating stages requires instrumentation at instance selection and at the HTTP transport.

## 14. Avoiding Measurement Distortion from Retries and Overlapping Limits

A request can time out and automatically re-send at multiple layers:

- The HTTP client has its own retries.
- Spring Cloud LoadBalancer has retry support if dependencies/policies match.
- Spring Retry or Resilience4j applies application-level retries/circuit breakers.
- Gateways or proxies may also retry depending on config.

When measuring **one timeout type**, disable or explicitly control retries at every layer. Otherwise, `elapsedMs` may reflect three attempts, each hitting a different limit.

Illustrative total-time example:

~~~text
Attempt 1:  response timeout ~1000ms
Backoff:                          100ms
Attempt 2:  response timeout ~1000ms
Backoff:                          200ms
Attempt 3:  response succeeds     300ms
Total operation:                 ~2600ms + overhead
~~~

This is not a universal formula: acquisition, connect, retry/backoff, CPU scheduling, body transfer, and other limits can shift results.

For `POST` calls creating orders or payments, a timeout does not prove the server did not process the request. Every retry design must evaluate idempotency and use idempotency keys or deduplication logic where appropriate.

### Overall Deadlines Must Be Derived from the Business Budget

Example calling a pricing service with a 2-second budget:

1. Define the budget for the **entire business operation**, not just one attempt.
2. Allocate budget across discovery/pool, connect, response, and retries.
3. Subtract elapsed time before starting each next attempt.
4. If insufficient time remains for a useful result, stop retrying and return a clear error.

Tune settings from actual p95/p99 measurements and backend capacity rather than guesswork. Deadlines need client-side cancellation/coordination; backends may continue processing unless they also support cancellation.

## 15. Post-Experiment Error Identification Table

| Situation | Observable clues | How to verify | Do not fix by |
|---|---|---|---|
| Pool lease timeout | Leased hits cap, pending grows; request never reached backend | Per-route pool stats/metrics | Increasing connect timeout |
| TCP connect timeout | TCP handshake fails to finish in time | Packet trace, connect-related exception | Increasing read timeout |
| Connection refused | Host sends RST or port has no listener; usually fails fast | Check server listener and network connectivity | Waiting out connect timeout to conclude |
| DNS resolution error/timeout | No target IP or unresponsive resolver | Resolver logs/metrics, DNS lookup test | Raising LoadBalancer TTL alone |
| TLS handshake error/timeout | TCP may be open, SSL unfinished | TLS trace, SSL exception, or handshake timer | Disabling certificate verification |
| Slow response headers | Server received request, has not sent reply in time | Server logs, HTTP transport tracing | Raising connection pool indefinitely |
| Body read gap | Partial response received, waiting on remaining data | Per-chunk logs, packet trace | Calling it a connect timeout |
| End-to-end deadline | Whole operation exceeds budget, possibly with retries | Trace spans and attempt counts | Treating one readTimeout as total deadline |
| No instances available | Supplier/LoadBalancer picked no target | Discovery logs, selected instance=null | Increasing socket timeout |

When Spring wraps an exception in `ResourceAccessException`, traverse the **cause chain**. The innermost exception type and per-stage timestamps matter far more than a generic “Request timed out” line.

## 16. Recording Data and Evaluating Results

Use a consistent result table across runs, changing **one parameter at a time**:

| Run | Client | Endpoint / condition | Timeout under test | Actual elapsed | Selected instance | Exception / cause | Conclusion |
|---|---|---|---|---|---|---|---|
| 1 | RestClient | `/lab/fast` | Baseline | Measure | Record | — | Path works |
| 2 | RestClient | `/delay-headers?ms=2500` | Response 1 s | Measure | Record | Record | Confirm response timeout |
| 3 | RestClient | `/gap-body?ms=2500` | Body read gap | Measure | Record | Record | Compare headers vs. body |
| 4 | RestClient | 2 requests same route, pool=1 | Lease 300 ms | Measure | Record | Record | Pool contention |
| 5 | RestClient | Closed port | Connect/refused | Measure | Record | Record | Fast failure, not timeout |
| 6 | WebClient | Pool wait / delay-headers | Acquire/response | Measure | Record | Record | Compare Reactor Netty |
| 7 | Feign | `slow(2500)` | Read timeout 1 s | Measure | Record | Record | Compare Feign config |

**Note:** `/delay-headers` and `/gap-body` in the table use the `/lab` prefix from the controller in Section 3; when invoking for real, use the full paths `/lab/delay-headers` and `/lab/gap-body`.

To reach sound conclusions:

1. Run multiple iterations to distinguish scheduling/network noise from reproducible faults.
2. Record configuration and HTTP transport versions for each run.
3. Verify a `ServiceInstance` was selected before blaming HTTP.
4. For pool/TCP/TLS/DNS, use stage-specific metrics or traces; **outer elapsed time is supporting evidence, never sole proof**.
5. When re-testing a new setting, change only one factor while keeping load, instance count, endpoint, and pool state constant whenever possible.

## 17. Practical Timeout Optimization Checklist

- Does the service-ID call truly go through Spring Cloud LoadBalancer?
- Did discovery find instances, and is a dedicated discovery query timeout needed?
- Is the active HTTP transport Apache HttpClient 5, Reactor Netty, JDK HttpClient, or another Feign delegate?
- Have **pool acquisition**, **TCP connect**, **TLS handshake**, **response**, and **body read** been measured separately where needed?
- Are `Connection refused` or `UnknownHostException` being mistaken for an expired timeout?
- Is the connection pool bottlenecked by per-route limits or unclosed responses?
- Do proxies or gateways have shorter timeouts or retries skewing results?
- Is an overall business deadline needed instead of isolated per-stage timeouts alone?
- Have attempt counts, backoff, and idempotency been reviewed before enabling retries?
- Are metrics, tracing, and correlation IDs sufficient to tie the chosen instance to the HTTP error?

**Conclusion:** “Request timeout” is not a single failure mode. Controlled experiments must prove whether a request is **awaiting discovery data**, **waiting on the pool**, **opening a connection**, **performing TLS handshake**, **awaiting a response**, **reading the body**, or **exceeding the overall deadline**. Only after identifying the exact stage can you tune the right parameter on `RestClient`, `WebClient`, or OpenFeign without blindly inflating wait times.

**Official references:**

- [Apache HttpClient 5 – RequestConfig.Builder](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/apache/hc/client5/http/config/RequestConfig.Builder.html)
- [Apache HttpClient 5 – ConnectionConfig.Builder](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/apache/hc/client5/http/config/ConnectionConfig.Builder.html)
- [Reactor Netty – HTTP Client: Timeout Configuration and Metrics](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Spring Cloud OpenFeign – Timeout Handling](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
