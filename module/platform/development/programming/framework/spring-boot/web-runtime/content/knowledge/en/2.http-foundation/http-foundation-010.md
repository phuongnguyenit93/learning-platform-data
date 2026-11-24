# Distinguishing Connection Time, Response Wait Time, and Processing Time

## 1. Why Separate These Time Categories?

When a Spring Boot application makes an HTTP call to another service, the latency observed by the user comes from multiple stages: DNS resolution, acquiring a connection from a pool, TCP setup, TLS handshake, sending the request, waiting for the first response byte, and downloading the body. On the server side, the request also passes through queues, controllers, business logic, and downstream calls such as databases or other APIs.

The three concepts in this topic describe different segments of that journey:

- **Connection time:** time required to obtain a usable connection to the server. Depending on the client and measurement, this may include or separate DNS, TCP, TLS, and proxy setup.
- **Response wait time:** time the client waits for response data from the server. Distinguish time to first byte from the maximum allowed gap without receiving additional data.
- **Processing time:** time spent on the server receiving and handling the request, running business logic, calling dependencies, and building the response.

These are not three names for the same timeout. A request can connect almost instantly yet wait a long time for server processing; conversely, a server can process rapidly while the client spends substantial time establishing a connection or downloading a large body.

An approximate model for total observed client time is:

~~~text
Total time observed by client
  = connection pool wait
  + DNS
  + TCP connect
  + TLS / proxy handshake
  + send request
  + wait for and receive response
~~~

Server processing time sits inside the interval from when the server receives the request until it finishes the response. It contributes to client response wait time, yet the two measurements are not identical because of network latency, proxies, queues, and body transfer.

## 2. Connection Time and Connect Timeout

### Stages Before the Request Is Processed

When a client calls a hostname, establishing a connection can involve:

1. **DNS lookup:** resolving the hostname to an IP address, from cache or a DNS resolver.
2. **Pool acquisition:** if using a connection pool, the request may wait for an idle connection. That is pool wait time, not TCP connect time.
3. **TCP handshake:** establishing the TCP connection to the server or proxy.
4. **TLS handshake:** over HTTPS, client and server negotiate TLS, verify certificates, and derive keys.
5. **Proxy negotiation:** if routing through an HTTP proxy, the client may establish a CONNECT tunnel before sending the HTTPS request.

**Connect timeout** bounds the time for establishing a new connection according to the HTTP client implementation. Do not assume it covers every stage listed above. DNS lookup, TLS handshake, and connection pool wait may each have separate settings or limits. Check the documentation of your request factory or HTTP client.

Connect timeout matters only when a new connection must be created. If a request reuses a keep-alive or pooled connection, the client may skip a new TCP handshake. With HTTP/2, multiple requests can even share one connection via multiplexing.

Common reasons connection time increases:

- Slow or unreachable DNS resolver.
- Server not listening, broken network route, or firewall dropping packets.
- Slow TLS handshake due to network RTT, certificate verification, or cipher setup.
- Connection pool exhausted of idle connections, forcing requests to queue.
- Client creating too many fresh connections because connection reuse is disabled or failing.

### Configuring Connect Timeout on RestTemplate

In Spring Boot 3.4+, connect timeout and read timeout can be configured via RestTemplateBuilder:

~~~java
import java.time.Duration;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
class HttpClientConfiguration {

    @Bean
    RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder
                .connectTimeout(Duration.ofSeconds(3))
                .readTimeout(Duration.ofSeconds(5))
                .build();
    }
}
~~~

In older Spring Boot minor versions, the builder methods may be named setConnectTimeout(...) and setReadTimeout(...). Actual enforcement happens through the underlying ClientHttpRequestFactory used by the builder.

Setting a 3-second connect timeout means the client limits new connection setup according to the request factory's semantics. It does not guarantee the entire HTTP request completes within 3 seconds. If using a pooled HTTP client, configure pool wait separately—for instance, connection-request timeout in Apache HttpClient.

## 3. Response Wait Time: TTFB and Read Timeout

The phrase "waiting for a response" can refer to two distinct measurements.

**Time to First Byte (TTFB)** is the elapsed time observed by the client from starting the request until receiving the first response byte. TTFB often includes connection setup if no connection was pooled, sending the request, server processing time, and return network latency. Hence, high TTFB alone does not prove the controller is slow.

**Read timeout** (or response timeout) bounds how long the client waits for incoming data while reading the response. Enforcement depends on the HTTP client:

- With traditional socket read timeout, a single read times out if no bytes arrive within the configured window. As long as data keeps arriving steadily, individual reads succeed even if total transfer time is much longer.
- With Reactor Netty, responseTimeout is the maximum idle interval between network reads. It detects silent/stalled responses, yet is not necessarily a cap on the entire stream's total duration.
- Some APIs offer an overall request timeout or deadline spanning multiple stages of a call. Do not confuse those with socket read timeouts.

For example, if the server sends one byte every 4 seconds and the client has a 5-second read timeout, each read succeeds before 5 seconds elapse, allowing the response to run far beyond 5 seconds. If the business rule is "the whole call must finish within 10 seconds," a 5-second read timeout alone is insufficient; an overall deadline is required.

### Configuring WebClient with Reactor Netty

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

class RemoteApiClient {

    private final WebClient webClient;

    RemoteApiClient() {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
                .responseTimeout(Duration.ofSeconds(5));

        this.webClient = WebClient.builder()
                .baseUrl("https://api.example.com")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }

    Mono<Item> getItem() {
        return webClient.get()
                .uri("/items/42")
                .retrieve()
                .bodyToMono(Item.class)
                .timeout(Duration.ofSeconds(8));
    }
}
~~~

In this example:

- CONNECT_TIMEOUT_MILLIS caps new TCP connect setup.
- responseTimeout caps the silent gap between Reactor Netty network reads.
- timeout on Mono sets a deadline for that call's publisher. If no result arrives within 8 seconds, Mono emits a timeout error and cancels the upstream subscription.

Each limit serves a distinct purpose. With pooling, also configure connection acquisition timeout. TLS handshake, DNS, and proxy negotiation may also need separate bounds depending on the chosen client. Verify exact semantics for your Reactor Netty and Spring versions.

For streaming responses returning Flux, timeout(Duration) normally bounds the gap between consecutive signals—the silence between items. A stream emitting events steadily can run longer than Duration. To cap total stream lifetime, enforce a separate deadline or cancellation; Flux.take(Duration) truncates the stream and completes normally, so choose termination behavior that fits your API contract.

## 4. Processing Time on the Spring Boot Server

Processing time is how long the server spends serving a request. It can include:

- Waiting for request dispatch or an available worker thread.
- Reading and decoding the request body.
- Running filters, interceptors, controllers, and services.
- Checking authorization, validation, and business logic.
- Querying databases, calling other HTTP services, or accessing storage.
- Serializing and writing the response body.

Exact measurement scope depends on the instrumentation's start/stop hooks. For instance, an HTTP server timer typically measures server-side request handling until the response completes in the server lifecycle. It does not measure DNS or TCP connect performed by the client beforehand.

A slow endpoint can stem from slow database queries, slow downstream APIs, lock contention, saturated thread pools, or heavy CPU work. Raising connect timeout will not fix any of those. Raising read timeout only makes the client wait longer before giving up; it does not speed up the server.

### Server Timeouts Are Not Controller Timeouts

Distinguish these settings:

- **Server/container connection timeout:** controls certain connection-acceptance or request-read phases depending on the servlet container. It is not a general cap on controller execution time.
- **Spring MVC async request timeout:** configurable via spring.mvc.async.request-timeout for async handlers like Callable, DeferredResult, or WebAsyncTask. It does not automatically bound synchronous controllers.
- **Database and downstream HTTP client timeouts:** bound internal dependency calls. This is usually the layer you must configure so a request cannot hang indefinitely on a dependency.
- **Business deadline:** caps remaining total budget across an entire call chain. Services should propagate or compute remaining time for downstream hops.
- **Reverse proxy / load balancer timeout:** bounds how long a proxy waits on an upstream or on incoming data. Settings like Nginx's proxy_read_timeout bound the gap between consecutive upstream reads, not the total request deadline.

Example timeout configuration for Spring MVC async requests:

~~~yaml
spring:
  mvc:
    async:
      request-timeout: 30s
~~~

This setting applies to Spring MVC's async request lifecycle. If a synchronous controller executes a 60-second SQL query, this property will not interrupt that query automatically. Set query timeouts, downstream HTTP client timeouts, or appropriate deadline mechanisms.

In WebFlux, a reactive pipeline can be bounded using the timeout operator:

~~~java
Mono<Result> result = service.loadResult()
        .timeout(Duration.ofSeconds(5));
~~~

This applies a deadline to the Mono publisher in the snippet. It does not replace per-dependency timeouts or create a global cap across every server request. With Flux streaming, distinguish total deadlines from inter-signal timeouts as noted earlier.

## 5. How to Measure Each Stage

Never infer server processing time from a single client latency number. Combine client measurements, server metrics, and distributed tracing.

### Measuring from the Client with curl

Curl exposes useful timing breakdowns:

~~~bash
curl -sS -o /dev/null \
  -w 'dns=%{time_namelookup}s\nconnect=%{time_connect}s\ntls=%{time_appconnect}s\npretransfer=%{time_pretransfer}s\nttfb=%{time_starttransfer}s\ntotal=%{time_total}s\n' \
  https://api.example.com/items/42
~~~

Meaning of each field:

| Field | Meaning |
|---|---|
| time_namelookup | Elapsed time from start until DNS resolution completes |
| time_connect | Elapsed time from start until TCP connection to host or proxy completes |
| time_appconnect | Elapsed time from start until TLS/SSL handshake completes |
| time_pretransfer | Point when the client is ready to start transmitting the request |
| time_starttransfer | Time to first byte of the response, commonly called TTFB |
| time_total | Total time until curl finishes receiving the response |

These timings are cumulative from request start. Subtracting them estimates individual stages: time_connect minus time_namelookup approximates TCP setup after DNS; time_appconnect minus time_connect approximates the TLS handshake. time_starttransfer minus time_pretransfer captures time from request-send readiness to the first byte, yet still includes network latency, proxies, and server processing. It is not a pure measure of controller time.

You can bound connect and total time separately in curl:

~~~bash
curl --connect-timeout 3 --max-time 10 https://api.example.com/items/42
~~~

connect-timeout bounds connection setup per curl semantics; max-time caps total command execution time. This is a client diagnostic tool, not timeout configuration for Spring Boot apps.

### Measuring from Spring Boot with Actuator and Micrometer

With Spring Boot Actuator and Micrometer, common HTTP metrics include:

- **http.server.requests:** server-side request handling duration, tagged with method, uri, status, and outcome.
- **http.client.requests:** client-side HTTP exchange duration across instrumented clients.

Client metrics usually reflect the entire client call and do not automatically break out DNS, pool acquisition, TCP, TLS, TTFB, and body transfer. To inspect those stages, add HTTP client/pool metrics, targeted logs, or tracing spans.

Distributed tracing follows a request across services. A trace shows how long service A spent in its controller, how long it spent calling service B, and how long service B waited on a database. Comparing client spans against server spans reveals whether extra time came from network, proxy, queuing, or processing.

Never log URLs containing tokens, passwords, or personal data. When adding tags or logs for latency analysis, avoid unbounded values such as user IDs, request IDs, or full URLs as metric labels to prevent cardinality explosion.

## 6. Interpreting Real-World Scenarios

| Observation | Likely causes to investigate |
|---|---|
| DNS or TCP time rises, and TTFB rises too | DNS resolver, network routing, firewall, proxy, server availability |
| TCP is fast yet TLS is slow | TLS handshake, certificate chain, proxy, or security configuration |
| High pool wait yet low TCP connect | Pool too small, prior responses not releasing connections, high request concurrency |
| Both TTFB and http.server.requests are high | Slow controller, queue, database, or downstream service |
| TTFB is high yet server metric is low | Network latency, proxy buffering, queuing ahead of server instrumentation, or scope mismatch |
| First byte arrives fast yet total time is high | Large body, low bandwidth, slow client reads, or long-running stream |
| Read timeout fires while stream emits nothing | Hung server/dependency, idle gap exceeding timeout, or proxy dropping upstream |
| Client times out yet server logs completion | Client gave up while server did not detect disconnect or backend work was not canceled |

Illustrative scenarios:

**Fast connect, slow processing:** client completes TCP/TLS in 80 ms yet TTFB is 4 seconds, and server metrics also show ~4 seconds. Investigate services, databases, locks, or thread pools. Raising connect timeout from 3 to 10 seconds will not fix the root cause.

**Slow connect, fast processing:** server metric is only 40 ms yet the client waits 1.5 seconds for the first byte; DNS/TLS or pool wait time is elevated. Check DNS, connection reuse, pooling, and TLS.

**Long-lived stream without triggering read timeout:** the server sends a chunk every few seconds, always under the read timeout interval. Total duration can grow huge. If business rules require a total cap, enforce a separate overall deadline.

**Client times out while server keeps running:** the client hits a timeout and closes the request while the controller continues running a query or background work. Client timeouts do not guarantee canceling server work. Applications should handle cancellation/disconnects where possible and set timeouts on databases, downstream HTTP clients, and background tasks.

## 7. Choosing Timeouts by Purpose

Before picking numbers, identify what each timeout protects:

1. **Pool acquisition timeout:** prevents requests from waiting indefinitely when no pooled connection is free.
2. **Connect timeout:** avoids waiting long when a new connection cannot be established.
3. **TLS/DNS timeout:** controls those specific phases if supported by the client.
4. **Read/response inactivity timeout:** detects an upstream that stops sending data for too long.
5. **Overall request deadline:** caps total elapsed time for a call.
6. **Server/dependency timeout:** bounds server work and individual database/API calls.

Timeouts must align across layers. If an overall request deadline is 8 seconds, a single dependency must not be allowed to spend 30 seconds. Leave time budget for subsequent steps and error handling. Once a request has spent part of its deadline, downstream hops should receive the remaining budget rather than starting a fresh full timeout.

Retries consume budget too. Three attempts at 5 seconds each can push total elapsed time far beyond expectations. Retry only operations with safe semantics or an idempotency key; avoid automatically repeating data-creating POSTs when you do not know whether the previous attempt ran. Use backoff and bound total retry duration.

Too short a timeout triggers false errors during brief slowdowns. Too long a timeout holds connections, threads, request contexts, and resources longer, amplifying cascading overload. Choose values based on SLOs, observed latency distributions (p95/p99), system load, and business requirements; then monitor timeout rates and tune.

## 8. Common Misconceptions

- **Increasing connect timeout to fix a slow API:** connect timeout only affects new connections; inspect server processing time and dependencies.
- **Treating read timeout as total response time:** many clients apply it per read or per idle interval; add a separate overall deadline when needed.
- **Equating TTFB with controller time:** TTFB also includes network, proxy, connection setup, and pre-server queues.
- **Confusing connection pool wait with TCP connect:** requests can wait for an idle connection even when the server is healthy.
- **Using server connection timeout as a request processing timeout:** that setting belongs to the connection/container layer with its own semantics; it does not abort business code.
- **Assuming client timeout cancels server execution:** the server or dependencies may keep running; configure cancellation and timeouts at the right layers.
- **Retrying every timeout error:** the server may have executed the operation; unsafe retries create duplicate data.
- **Looking only at one service's logs:** correlate client metrics, server metrics, pool metrics, and traces to see where time increased.

## 9. Latency Investigation Workflow

When a Spring Boot API is slow, proceed in order:

1. Measure total time and TTFB from the client; record DNS, TCP, TLS, and total via curl or an equivalent tool.
2. Check the client connection pool: acquisition wait time, active connections, max pool size, and connection reuse ratio.
3. Locate the corresponding request in server metrics/logs and compare server processing time against TTFB.
4. If the server is slow, use traces to break down time across controllers, databases, HTTP dependencies, queues, and business steps.
5. If the server is fast yet the client is slow, inspect DNS, TLS, proxies, network, buffering, and body download time.
6. Identify which timeout actually fired: pool, connect, read/response, overall deadline, server async, or proxy.
7. Set timeouts at the right layers, add cancellation support, and test slow upstreams, unresponsive upstreams, trickle responses, and client disconnects.

Clearly separating connection time, response wait time, and processing time pinpoints the exact layer causing latency, leads to meaningful timeouts, and prevents masking problems by blindly increasing client wait limits.