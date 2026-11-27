# WebClient and Connection Configuration in Spring Integration WebFlux

## 1. Why Are WebClient and Connection Configuration Important?

In an integration flow, an application might receive orders via Kafka, fetch shipping quotes over HTTP, write results to a database, and emit JMS/AMQP notifications. If every message opens its own HTTP connection or lacks timeouts, the application will waste resources, suffer higher latency, and easily bottleneck when partner APIs slow down.

**WebClient** is Spring WebFlux's HTTP client; it uses a reactive API to build HTTP requests and read responses. A **connection** is a network resource managed by the HTTP transport (typically Reactor Netty). The two concepts have distinct responsibilities:

- `WebClient` configures URLs, HTTP methods, headers, bodies, codecs, filters, and how responses are read.
- Reactor Netty's `HttpClient` configures TCP, DNS, TLS, response timeouts, proxies, and transport parameters.
- `ConnectionProvider` manages the **connection pool**, including limits on active connections, waiting to acquire a connection, and connection reuse.
- Spring Integration uses `WebClient` inside a WebFlux **outbound channel adapter** or **outbound gateway** to turn a `Message<?>` into an HTTP request. The outbound gateway also converts the response into a reply message for downstream processing.

This lesson is part of the **WebFlux Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s; file, SFTP, HTTP, JMS, AMQP, Kafka, and database scenarios can all require such an HTTP call step. Connection configuration governs a critical part of **message contracts, error handling, and connection lifecycles**.

~~~mermaid
flowchart LR
    A["Kafka / JMS / File / Service"] --> B["Message<QuoteRequest>"]
    B --> C["MessageChannel"]
    C --> D["WebFlux outbound gateway"]
    D --> E["WebClient: URI / headers / codecs"]
    E --> F["Reactor Netty HttpClient"]
    F --> G["ConnectionProvider / TCP / TLS"]
    G -->|"HTTP request"| H["Partner API"]
    H -->|"HTTP response"| G
    G --> F
    F --> E
    E --> D
    D --> I["Reply Message<QuoteResponse>"]
~~~

**Boundaries to remember:** WebClient supports non-blocking I/O, yet `QueueChannel`, pollers, blocking JDBC, synchronous handlers, or downstream brokers each have their own dispatching and load limits. Having WebClient does not mean the entire `IntegrationFlow` automatically becomes reactive or gains end-to-end backpressure across all systems.

## 2. Configuration Layers and Their Responsibilities

| Layer | API / component | What to configure |
|---|---|---|
| Integration logic | `IntegrationFlow`, `MessageChannel`, `WebFlux.outboundGateway` | Request-reply contract, payload, reply, and error flows |
| HTTP client | `WebClient.Builder`, `WebClient` | Base URL, default headers, filters, codecs, client connector |
| HTTP transport | `ReactorClientHttpConnector`, `HttpClient` | Connect/response timeouts, protocol, TLS, proxy |
| Connection pool | `ConnectionProvider` | `maxConnections`, `pendingAcquireTimeout`, `maxIdleTime`, `maxLifeTime` |
| Resource lifecycle | Reactor Netty resources, `ReactorResourceFactory` | Shared event loops/pools, startup and shutdown |
| Operations | Micrometer/Actuator, tracing, logs | Active/idle/pending connections, request latency, timeouts |

`WebClient` is designed to be **reused** across many requests. Once `build()` is called, the client configuration is immutable; you can use `mutate()` to create a variant, but there is no need to build a new `WebClient` per message. `WebClient` **is not synonymous with a single socket**: one instance can use many connections, and multiple instances can share transport resources.

## 3. Dependencies and Default WebClient Configuration

With Spring Boot, let Boot's BOM/dependency management coordinate compatible versions of Spring Integration, WebFlux, and Reactor Netty:

~~~groovy
// build.gradle - dependencies section
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

`spring-integration-webflux` provides the WebFlux adapters/gateways. `spring-boot-starter-webflux` typically includes `WebClient`, `reactor-netty`, and JSON codecs. An application using only **outbound** HTTP does not need to create an inbound WebFlux controller.

Basic configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class PartnerClientConfiguration {

    @Bean
    public WebClient partnerWebClient(WebClient.Builder builder) {
        return builder.build();
    }
}
~~~

Boot's auto-configured `WebClient.Builder` is a solid starting point: it picks up Boot-managed customizers and HTTP resources. By default, Reactor Netty uses shared resources including event loops and connection pooling. Only split out a dedicated pool when needed—for instance, per-partner connection limits, different deadlines, or load isolation. If an application includes both Spring MVC and WebFlux, verify which web application type Boot selects; the presence of `WebClient` does not prove the server runs WebFlux.

## 4. Connection Pool: Acquire, Reuse, Release

Connection pooling reduces TCP/TLS handshake overhead across consecutive requests. An HTTP exchange can proceed as follows:

~~~mermaid
sequenceDiagram
    participant Flow as IntegrationFlow
    participant Client as WebClient
    participant Pool as ConnectionProvider
    participant Server as Partner API
    Flow->>Client: HTTP request
    Client->>Pool: Acquire connection
    alt Valid idle connection available
        Pool-->>Client: Reuse connection
    else Capacity to open connection
        Pool->>Server: DNS / TCP / TLS
        Server-->>Pool: Connected
        Pool-->>Client: New connection
    else Pool exhausted
        Note over Pool: Wait in pending acquire if space permits
        Pool-->>Client: Connection or timeout / overflow
    end
    Client->>Server: HTTP request
    Server-->>Client: HTTP response
    Client->>Pool: Release or close connection
    Client-->>Flow: Reply or error
~~~

| Option | Meaning | Operational guidance |
|---|---|---|
| `maxConnections` | Maximum connections in a pool toward the relevant remote endpoint | Match actual concurrency, SLA, and partner limits |
| `pendingAcquireMaxCount` | Maximum acquire requests queued while waiting | Bound backlog instead of using an unbounded queue |
| `pendingAcquireTimeout` | Maximum time to wait for a connection | Shorter than the overall operation deadline |
| `maxIdleTime` | Idle connection becomes eligible for closing after this duration | Align with server/proxy idle timeouts |
| `maxLifeTime` | Connection lifetime before becoming eligible for replacement | Avoid keeping sockets open indefinitely |
| `evictInBackground` | Periodically cleans up eligible connections in the background | Reduces lingering idle connections |

`maxConnections(30)` does **not** mean a maximum of 30 HTTP requests/second. With HTTP/1.1 keep-alive, a connection returns to the pool and serves another request. With HTTP/2, one connection can multiplex multiple streams, so throughput cannot be deduced directly from socket count. Pool defaults can vary by version or environment; check Reactor Netty documentation for your exact runtime version.

When the pool saturates, requests wait in the pending acquire queue **before even leaving the application**. If that queue fills or `pendingAcquireTimeout` expires, failure happens right at connection acquisition, before the TCP handshake and before the server ever sees the request.

## 5. Configuring WebClient with a Dedicated ConnectionProvider

The example below creates a dedicated pool for calling a partner API with bounded connections and timeouts. The numbers are illustrative only; production values must come from measured load, latency budgets, and receiver limits.

~~~java
package com.example.integration;

import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class PartnerWebClientConfiguration {

    // Spring invokes dispose() when ApplicationContext closes.
    @Bean(destroyMethod = "dispose")
    public ConnectionProvider partnerConnectionProvider() {
        return ConnectionProvider.builder("partner-api-pool")
            .maxConnections(30)
            .pendingAcquireMaxCount(60)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(25))
            .maxLifeTime(Duration.ofMinutes(3))
            .evictInBackground(Duration.ofSeconds(30))
            .build();
    }

    @Bean("partnerWebClient")
    public WebClient partnerWebClient(
            WebClient.Builder builder,
            @Qualifier("partnerConnectionProvider") ConnectionProvider pool) {
        HttpClient transport = HttpClient.create(pool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
            .responseTimeout(Duration.ofSeconds(5));

        return builder
            .clientConnector(new ReactorClientHttpConnector(transport))
            .defaultHeader(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
            .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(1024 * 1024))
            .build();
    }
}
~~~

**Reading the configuration:**

1. `ConnectionProvider.builder(...)` creates a named pool so it can be identified in logs/metrics.
2. `maxConnections(30)` caps connections; `pendingAcquireMaxCount(60)` caps requests waiting for a connection.
3. `pendingAcquireTimeout(2s)` limits how long to wait for the pool to grant a connection. It is **not** a TCP connect timeout.
4. `maxIdleTime`, `maxLifeTime`, and `evictInBackground` manage connection age; a connection actively executing a request is not closed mid-flight merely because an idle threshold passes.
5. `CONNECT_TIMEOUT_MILLIS` bounds the TCP handshake; it does not cover all of DNS, pool acquisition, or waiting for the server response.
6. `responseTimeout(5s)` bounds response waiting at the Reactor Netty layer; it does not represent the whole business deadline covering retries, queues, and downstream steps.
7. `ReactorClientHttpConnector` wires the configured transport into `WebClient`. WebClient codecs continue handling HTTP body serialization/deserialization.
8. `maxInMemorySize(1 MiB)` caps buffering for default codecs, preventing unbounded in-memory decoding of huge bodies.

A custom pool must be **disposed on application shutdown**. `destroyMethod = "dispose"` handles this pool's lifecycle, while shared event loops may still be managed separately by Spring Boot/Reactor Netty.

## 6. Wiring WebClient into a Spring Integration WebFlux Outbound Gateway

Assume the partner API exposes `POST /api/quote`, accepts `{"orderId":"ORD-1001","weightKg":2}`, and returns a JSON quote. The gateway turns the response into a message for downstream storage or processing.

~~~java
package com.example.integration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.messaging.MessageChannel;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class PartnerQuoteFlow {
    public record QuoteRequest(String orderId, int weightKg) { }
    public record QuoteResponse(
        String orderId, long shippingFeeVnd, String currency) { }

    @Bean
    public MessageChannel pricingRequests() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow quoteFlow(
            @Qualifier("pricingRequests") MessageChannel requests,
            @Qualifier("partnerWebClient") WebClient webClient,
            @Value("${partner.api.quote-url}") String url) {
        return IntegrationFlow.from(requests)
            .handle(WebFlux.outboundGateway(url, webClient)
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(QuoteResponse.class)
                .mappedRequestHeaders(
                    HttpHeaders.CONTENT_TYPE, "X-Correlation-Id"))
            .channel("pricingResponses")
            .get();
    }

    @ServiceActivator(inputChannel = "pricingResponses")
    public void acceptQuote(QuoteResponse quote) {
        System.out.printf("Quote for %s: %d %s%n",
            quote.orderId(), quote.shippingFeeVnd(), quote.currency());
    }
}
~~~

Environment-specific endpoint configuration:

~~~yaml
# application.yml of the partner-calling application
partner:
  api:
    quote-url: "http://localhost:9090/api/quote"
~~~

A service or Kafka/JMS listener can inject `@Qualifier("pricingRequests") MessageChannel` and send:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.messaging.support.MessageBuilder;

boolean dispatched = pricingRequests.send(
    MessageBuilder.withPayload(
        new PartnerQuoteFlow.QuoteRequest("ORD-1001", 2))
        .setHeader(HttpHeaders.CONTENT_TYPE,
            MediaType.APPLICATION_JSON_VALUE)
        .setHeader("X-Correlation-Id", "req-001")
        .build());
~~~

`dispatched == true` only reflects the channel's contract. **It does not prove the partner API returned HTTP 200, executed business logic, or that `acceptQuote` has run.** WebClient responses can be processed asynchronously; observe the reply channel and error flow.

The URL on the gateway is an absolute URL. If `WebClient.baseUrl(...)` is also set, an absolute URL is not appended onto the base URL. Choose a consistent strategy and never let clients call arbitrary URIs taken from untrusted payloads.

### 6.1. Setting Up a Mock API for Local Testing

Create a **separate WebFlux application** running on port 9090 with records sharing the JSON schema:

~~~java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class QuoteMockController {
    record QuoteRequest(String orderId, int weightKg) { }
    record QuoteResponse(String orderId, long shippingFeeVnd,
                         String currency) { }

    @PostMapping(path = "/api/quote",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<QuoteResponse> quote(@RequestBody Mono<QuoteRequest> body) {
        return body.map(request -> new QuoteResponse(
                request.orderId(), request.weightKg() * 12_000L, "VND"))
            .delayElement(Duration.ofMillis(150));
    }
}
~~~

~~~yaml
# Separate application.yml for the mock service
server:
  port: 9090
~~~

Verify the mock directly before calling through the flow:

~~~bash
curl -i -X POST http://localhost:9090/api/quote \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ORD-1001","weightKg":2}'
~~~

Illustrative body: `{"orderId":"ORD-1001","shippingFeeVnd":24000,"currency":"VND"}`. Next, send into `pricingRequests` and watch for the reply message arriving on `pricingResponses`. Do not use log ordering relative to `send()` to assert strict synchronicity or asynchronicity of the HTTP call.

## 7. Distinguishing Timeout Types

An operation may wait through **pool → DNS → TCP → TLS → send body → server processing → receive response → downstream handler**. Each timeout covers a distinct phase and cannot substitute for another.

| Limit | Where it applies | What it excludes |
|---|---|---|
| `pendingAcquireTimeout` | Waiting for a slot in the connection pool | TCP/TLS and HTTP response |
| `CONNECT_TIMEOUT_MILLIS` | TCP connect | Pool wait, DNS, server processing time |
| DNS resolver timeout | Hostname resolution | Waiting for pool slot, HTTP status |
| TLS handshake timeout | Establishing TLS | External business processing |
| `responseTimeout` | Waiting for response at Reactor Netty layer | Total queue + retry + downstream time |
| Reactor `timeout(Duration)` | Deadline on the wrapped publisher | Automatic rollback of remotely processed requests |
| Spring Integration `replyTimeout` | Messaging gateway waiting for reply | WebClient connect timeout |
| Proxy/ingress timeout | Upstream proxy or HTTP server | Business logic continuing after client leaves |

Consider an 8-second end-to-end budget: you cannot set pending acquire to 10s, connect to 10s, response to 30s, retry 5 times, and expect the whole operation to finish within 8s. Define a total deadline, budget each stage, and stop retrying once no time remains.

For SSE/streaming responses, an overly short `responseTimeout` can terminate a valid connection if the server emits events sparsely; design appropriate heartbeats, idle timeouts, and subscription lifetime limits.

## 8. Resource Lifecycle: Connection Reuse and Shutdown

### 8.1. Reusing WebClient and Connections

Never instantiate a fresh `WebClient` plus `ConnectionProvider` per message. Doing so creates excessive pools/event loops, spikes socket counts, defeats reuse, and complicates cleanup on application shutdown.

~~~java
// Pattern to avoid inside per-event processing:
// new ReactorClientHttpConnector(
//     HttpClient.create(ConnectionProvider.builder("new-pool").build()))

// Instead, inject the Spring-managed @Qualifier("partnerWebClient") WebClient
// into the outbound gateway configuration or shared service.
~~~

`WebClient` is immutable and thread-safe for concurrent use. HTTP/1.1 keep-alive connections are normally reused after a response finishes, provided the server/proxy did not request close and the transport confirms the connection remains valid.

### 8.2. Reactor Netty Shared Resources

Per Spring Framework, Reactor Netty defaults to global `HttpResources` comprising event loops and a connection pool. Spring Boot manages corresponding resources via `ReactorResourceFactory`; in reactive applications, clients built from Boot's configured builder can share resources with the server.

A **custom** `ConnectionProvider` has its own lifecycle. For example, `@Bean(destroyMethod = "dispose")` disposes only that pool; do not arbitrarily dispose global event loops while other clients/servers still rely on them. Applications starting and stopping multiple `ApplicationContext`s in the same JVM require special attention to resource cleanup.

If you need to isolate both event loops and connection pools, Spring Framework supports `ReactorResourceFactory` and the `ReactorClientHttpConnector(resourceFactory, mapper)` constructor; this is an advanced configuration requiring application-level lifecycle management.

### 8.3. Idle Connections and Race Conditions

A server, proxy, or load balancer may close an idle keep-alive connection before the client notices. When the client tries to reuse that socket, an error can occur because the remote closed it. `maxIdleTime` and background eviction reduce stale connections, yet **they do not eliminate every race condition**.

Check your partner's/proxy's actual idle timeout and consider retries for safe or idempotent operations. Never treat a connection-reuse error as proof that the business request was definitely not processed.

## 9. Codecs, maxInMemorySize, and Header Mapping

### 9.1. Buffer Limit When Decoding JSON

HTTP message readers/codecs buffer data in memory when decoding responses. In common default WebFlux configurations, this buffering limit is typically **256 KiB**. Exceeding it causes WebClient to emit a `DataBufferLimitException`.

~~~java
WebClient client = builder
    .codecs(configurer -> configurer.defaultCodecs()
        .maxInMemorySize(2 * 1024 * 1024))
    .build();
~~~

This example raises the limit to 2 MiB. Never set an unlimited buffer size just to read large files: memory pressure scales with concurrent requests. For large responses, prefer streaming APIs with size bounds, concurrency limits, and proper `DataBuffer`/resource management.

### 9.2. Headers: Choosing What Crosses the Boundary

`Content-Type` describes the request body; `Accept` describes the response format the client wants to read. `Authorization`, `X-Correlation-Id`, and idempotency keys serve distinct purposes. In Spring Integration, use `mappedRequestHeaders(...)` and `mappedResponseHeaders(...)` to govern metadata crossing the HTTP boundary.

Do not expose all internal `MessageHeaders` as HTTP headers: `replyChannel`, `errorChannel`, or source-system security details are not data a partner should receive. Likewise, client-supplied headers do not substitute for authentication.

~~~java
.handle(WebFlux.outboundGateway(url, webClient)
    .httpMethod(HttpMethod.POST)
    .expectedResponseType(QuoteResponse.class)
    .mappedRequestHeaders(
        HttpHeaders.CONTENT_TYPE,
        HttpHeaders.ACCEPT,
        "X-Correlation-Id"))
~~~

Application tokens belong in a WebClient filter or OAuth2 client configuration, loaded from a protected secret store/configuration. Never hardcode real tokens in repositories, and never forward a user's token to another service without a valid delegation contract.

## 10. HTTPS, TLS, DNS, Proxies, and Connection Security

### 10.1. HTTPS and mTLS

In production, prefer HTTPS and verify server certificates and hostnames. If a partner requires mTLS, the application needs a client certificate/private key and proper trust configuration, along with a certificate rotation plan.

Never use `InsecureTrustManagerFactory` or disable hostname verification as a "quick fix" for TLS errors. Issues like `PKIX path building failed`, expired certificates, or hostname mismatches must be fixed at the truststore, certificate, or URL source.

### 10.2. Proxies and DNS

DNS can fail before TCP connect even begins. Reactor Netty supports custom DNS resolvers; corporate proxies change how clients reach destinations. Example connecting through an HTTP proxy:

~~~java
import reactor.netty.transport.ProxyProvider;

HttpClient http = HttpClient.create(pool)
    .proxy(proxy -> proxy
        .type(ProxyProvider.Proxy.HTTP)
        .host("proxy.internal.example")
        .port(3128));
~~~

This is an illustrative snippet only. In production environments, account for proxy authentication, HTTPS CONNECT, non-proxy hosts, DNS policies, and firewalls. Reaching the proxy does not prove the final target is reachable.

### 10.3. Dynamic URLs and SSRF

If a gateway constructs URIs directly from external payloads/headers, callers could trick WebClient into calling forbidden addresses, including cloud metadata services, internal IPs, or attacker-controlled servers. Map `partnerId` through a configured URL **allowlist**; restrict scheme to HTTPS, validate hostname/port, control redirects, and enforce egress rules.

`WebClient.baseUrl` is a URI routing convenience, **not** an SSRF defense.

## 11. Error Handling and Retries

| Error type | Common symptoms | Action |
|---|---|---|
| Pool full | Pending acquire grows, timeouts/overflows | Cap concurrency, review pool/queue sizing |
| Connect/DNS/TLS | Refused, timeout, handshake/trust failure | Inspect network, firewall, DNS, certificates |
| Waiting for response | `responseTimeout` | Enforce deadlines and conditional retries |
| HTTP `400/401/403` | Invalid request or credentials | Fix data or credentials; do not retry blindly |
| HTTP `429` | Partner rate limiting | Throttle, back off, honor valid Retry-After |
| HTTP `502/503/504` | Temporary partner/proxy failure | Bounded retries, circuit breaker |
| Response decoding | Mismatched JSON/schema/media type | Fix contract or codec version |
| `DataBufferLimitException` | Response exceeds codec memory limit | Limit payload, stream, or raise limit deliberately |

In a WebFlux outbound gateway, errors can surface asynchronously when the HTTP exchange executes. Do not assume every HTTP error is thrown immediately at `MessageChannel.send(...)`. Design an `errorChannel`, error flow/advice, or error path appropriate for your endpoint and channel type, and verify by testing each failure mode.

### 11.1. Retries Must Not Cause Business Duplicates

An HTTP POST may **already have been processed by the partner** even if the client times out before reading the response. Blind retries can duplicate orders, double-charge, or create duplicate shipments. For side-effecting operations:

1. Attach a stable idempotency key per request; the receiver stores and checks keys.
2. Retry only transient errors permitted by contract, with attempt caps, exponential backoff, jitter, and an overall deadline.
3. Add circuit breakers or rate limiters when partners overload; never open unbounded connections.
4. Persist incomplete requests with an outbox or durable broker if events must survive restarts.
5. Define Kafka/JMS source ACK/commit points after appropriate milestones, accounting for possible duplicate sends.
6. Avoid stacking retries at too many layers: WebClient, `IntegrationFlow` advice, listeners, and schedulers can multiply send attempts.

`ConnectionProvider` solves **network resource management**, not end-to-end message reliability. Delivery guarantees, idempotency, and transactions must be designed separately.

## 12. Observing and Tuning the Connection Pool

There is no single `maxConnections` value optimal for every application. You need to know request rates, how long partners hold connections, remote limits, and actual concurrency. When throughput looks low, do not blindly raise pool size before measuring.

Useful metrics:

- **Active/idle/pending connections** and acquire wait time: is the pool genuinely saturated?
- **HTTP latency p50/p95/p99**, 4xx/5xx errors, timeouts: is the remote or network slow?
- **DNS, TCP connect, TLS errors**, connection close/reuse counts: which connection failure dominates?
- **In-flight messages and queue depth** inside `IntegrationFlow`: is the bottleneck before or after HTTP?
- **Retry rate** and timeout ratio: is a retry storm amplifying load?
- **Memory, event-loop, and thread usage**: are there blocking handlers or excessive buffering?

Reactor Netty integrates with Micrometer metrics; collecting them requires enabling configuration and having the appropriate registry/dependencies for your version. Do not assume all metrics are exposed automatically simply because `WebClient` is present. Avoid putting URLs containing tokens, user IDs, or correlation IDs into metric tags, which causes high cardinality or leaks data.

When increasing `maxConnections`, always evaluate `pendingAcquireMaxCount`, `pendingAcquireTimeout`, response timeouts, remote rate limits, connection reuse, and flow concurrency together. If the remote service is already overloaded, opening more connections usually increases failures rather than throughput.

## 13. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| "Creating a WebClient per request makes it thread-safe" | `WebClient` is immutable and safely shared; recreating pools wastes resources |
| "`maxConnections(30)` means 30 HTTP requests/second" | It is a connection count limit, not per-second throughput |
| "`pendingAcquireTimeout` is the TCP connect timeout" | One waits for the pool; the other bounds the TCP handshake |
| "`responseTimeout` is the total business deadline" | Excludes queues, retries, and downstream steps |
| "`send() == true` means the partner wrote successfully" | Reflects only the channel's send contract |
| "Using WebClient makes every flow non-blocking" | JDBC, pollers, queues, and handlers can still block |
| "Setting `maxInMemorySize` unlimited to read big files" | Risks OOM; use streaming and load limits instead |
| "Connection pool closes global event loops when idle" | Provider and event-loop lifecycles are managed separately |
| "Internal HTTPS needs no certificate verification" | Proper trust and hostname verification are still required |
| "Retrying a POST after timeout is always safe" | Remote may have completed it; idempotency is needed |

## 14. Exercises

1. Run the mock API on `localhost:9090` and the `IntegrationFlow` from Section 6. Send a `QuoteRequest`, verify the JSON response, and check the `pricingResponses` reply message.
2. Lower `maxConnections` to 1 or 2 in a test environment and send many concurrent requests to a delayed mock. Observe pending acquires and timeout/overflow errors.
3. Stop the mock service and send a message; distinguish `connection refused` from connect timeouts in logs/error flows.
4. Increase mock latency beyond `responseTimeout(5s)`. Analyze whether the request may have reached the server and under what conditions retrying is safe.
5. Return JSON larger than `maxInMemorySize`; reproduce `DataBufferLimitException` and choose between a bounded increase or streaming.
6. Add `X-Correlation-Id` to messages and HTTP requests. Correlate logs on both sides without logging tokens or sensitive payloads.
7. Enable HTTPS with a valid certificate; test an invalid certificate/hostname in a test environment to understand handshake failures.
8. Add a Kafka/JMS source to the flow and simulate an HTTP timeout. Design the ACK/commit timing and idempotency key.
9. Reuse one `WebClient` bean multiple times, then create a variant with `mutate()`; verify the original client's configuration remains unchanged.
10. Close the `ApplicationContext` and verify the custom pool is disposed; if the app opens/closes multiple contexts, check for leftover threads/sockets.

**Applied question:** a system receives 200 orders per second; each HTTP call typically takes 300 ms but occasionally stretches to several seconds. The pool starts filling and the pending queue grows. What metrics should you measure to decide among raising `maxConnections`, capping concurrency, adjusting timeouts, adding a queue/outbox, or negotiating rate limits with the partner? Why is simply adding more connections insufficient?

## 15. References

- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): WebClient builder, HTTP connectors, codec limits, and resources.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): managing and sharing Reactor Netty resources.
- [Reactor Netty Reference — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection pools, timeouts, TLS, proxies, and metrics.
- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): WebFlux outbound adapters/gateways and `WebClient`.
- [Spring Integration API — WebFlux Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFlux.html): `outboundGateway(uri, webClient)` and `outboundChannelAdapter(uri, webClient)` overloads.
- [Spring Framework — WebClient Error Handling](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): handling HTTP response statuses and errors.

> **Takeaway:** `WebClient` defines the HTTP contract, `HttpClient` manages transport, and `ConnectionProvider` governs acquiring and reusing connections. In Spring Integration WebFlux, all three must be designed alongside `MessageChannel`s, reply/error flows, per-stage timeouts, load limits, TLS, metrics, and idempotency.
