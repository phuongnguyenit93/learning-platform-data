# Keep-alive, idle time, and connection lifecycle

## 1. Why are connections part of API Gateway architecture?

In a microservices system, **Spring Cloud Gateway** routinely receives requests from web, mobile, and internal service clients, then forwards them to backends via route predicates, filter chains, URL/header transformations, and service discovery. Every request requires a network connection or reuses an existing one. If the Gateway constantly opens fresh TCP/TLS connections, handshake overhead, socket allocation, and resource management can become a bottleneck. Conversely, if connections are held too long, the Gateway may try to reuse a socket already closed by a load balancer, proxy, or backend.

Three operational questions need answers:

1. When is a connection **reused** instead of opened anew?
2. After how long **without activity** is a connection retained or closed?
3. When backend instances change, clients disconnect, TLS fails, or the Gateway shuts down, how does the **connection lifecycle** end?

This is the focus of **"Keep-alive, idle time, and connection lifecycle"** in the **Connections and TLS** chapter. This lesson centers on **Spring Cloud Gateway Server WebFlux** backed by Reactor Netty; configuration examples should be cross-checked against the exact Spring Cloud Gateway/Spring Boot version you deploy.

After this lesson, you will be able to:

- Distinguish **HTTP persistent connections**, **TCP SO_KEEPALIVE**, and **connection pools**.
- Describe the two independent connections on both sides of the Gateway, including TCP/TLS costs.
- Distinguish `maxIdleTime`, `maxLifeTime`, pool acquire wait time, connect timeout, response timeout, and external proxy timeouts.
- Configure the Gateway outbound pool, pick resource limits, and verify outcomes.
- Explain the risks of **stale pooled connections**, long-lived SSE/WebSockets, service discovery changes, and graceful shutdown.
- Monitor active/idle/pending connections, network errors, latency, and pool saturation to operate an API Gateway safely.

## 2. Three "keep-alive" concepts easily confused

### 2.1. HTTP keep-alive: reusing a connection across multiple requests

In **HTTP/1.1**, a TCP connection is **persistent by default**: after the server finishes returning a response, both sides may reuse the connection if the protocol, headers, body length, and socket state permit. If one party sends `Connection: close`, it signals intent to close the connection once the current exchange finishes.

~~~text
HTTP/1.1, single TCP connection:

Client ---- GET /items/1 --------> Server
Client <--- 200 + response ------ Server
Client ---- GET /items/2 --------> Server
Client <--- 200 + response ------ Server
         (connection is reused)
~~~

In **HTTP/2**, multiple HTTP streams can share and multiplex over a single connection. Do not apply HTTP/1.1's `Connection: keep-alive` header to HTTP/2: connection-specific headers like `Connection` are forbidden by HTTP/2 rules. HTTP/2 also manages streams, frames, and flow control; a single stream ending **does not mean** the TCP connection must close.

### 2.2. TCP keepalive: probing to detect unreachable peers

**TCP keepalive** is a socket-layer feature typically controlled by `SO_KEEPALIVE` alongside OS parameters. After a period with no data, the OS can send probes to detect dead connections. It is **not** a guarantee of HTTP connection reuse, not a pooling mechanism, and does not guarantee every middlebox preserves NAT mappings.

TCP keepalive parameters can have very long defaults or be governed by OS/container settings. If short-interval failure detection is needed for a real workload, verify support and settings across **OS, sockets, proxies, and application protocols**; toggling a keepalive flag alone does not guarantee failures are detected within seconds.

### 2.3. Connection pooling: managing opened outbound connections

Reactor Netty HTTP client uses a **connection pool** to reuse TCP/TLS connections to upstreams. The pool tracks active connections, reusable idle connections, and waiting requests when limits are reached.

~~~mermaid
flowchart TD
    R[Request needs backend call] --> Q{Valid idle connection?}
    Q -->|Yes| Reuse[Reuse connection]
    Q -->|No| Cap{Capacity to open new?}
    Cap -->|Yes| New[TCP connect + TLS if HTTPS]
    Cap -->|No| Pending[Wait to borrow from pool]
    Pending -->|Granted before deadline| Reuse
    Pending -->|Deadline expired| Err[Acquire timeout / request failure]
    Reuse --> Work[Send request and read response]
    New --> Work
    Work --> Done{Connection still reusable?}
    Done -->|Yes| Idle[Return to pool for reuse]
    Done -->|No| Close[Close / discard connection]
~~~

These three concepts complement each other yet are **not equivalent**:

| Mechanism | Layer | Purpose |
| --- | --- | --- |
| HTTP keep-alive/persistence | HTTP/1.1 or HTTP/2 connection lifecycle | Allows multiple HTTP exchanges to share a connection |
| TCP keepalive | TCP/OS | Probes a connection whose peer may have vanished |
| Connection pooling | Reactor Netty HTTP client | Reuses, bounds, and manages lifecycle of upstream connections |

## 3. The Gateway has two independent connection sides

The Gateway is an HTTP server to clients, yet an HTTP client to backends. For a typical proxied route, these are **two separate network hops**:

~~~mermaid
flowchart LR
    Client[Browser / Mobile] -->|TCP/TLS A| Gateway[Spring Cloud Gateway]
    Gateway -->|TCP/TLS B, pooled| Inventory[Inventory service]
    Gateway -->|TCP/TLS C, pooled| Orders[Orders service]
~~~

- **Inbound connections (client → Gateway):** controlled by the HTTP server, fronting ingress/load balancer, and client. Clients may speak HTTP/1.1 or HTTP/2 depending on support and configuration.
- **Outbound connections (Gateway → backend):** controlled by the Gateway's proxy HTTP client, route URI, Reactor Netty connection pool, network, and backend.
- **TLS termination:** TLS on hop A and TLS on hop B are distinct security sessions. Clients using HTTPS **does not automatically** mean the Gateway uses HTTPS to backends.
- **Closing one hop does not instantly close the other:** when a client disconnects, the Gateway generally cancels reactive work; however, closing sockets, finishing upstream I/O, and returning connections to the pool depend on protocol state and cancellation mechanics.

For example: 1,000 clients holding connections to the Gateway **do not necessarily** create 1,000 TCP connections to Inventory. The Gateway can serve requests over time using a smaller pool of outbound connections. Conversely, 100 concurrent long-running upstream requests may require many active HTTP/1.1 connections, depending on multiplexing and pool characteristics.

**Observe both sides separately.** Ingress timeouts, Netty server idle timeouts, outbound pools, service timeouts, and sidecar keep-alive policies are not the same knob.

## 4. Lifecycle of an outbound connection

An HTTP(S) connection on the Gateway side can pass through these states:

~~~mermaid
stateDiagram-v2
    [*] --> NoConnection
    NoConnection --> Connecting: Acquire with no reusable connection
    Connecting --> TLS: TCP connect succeeds, HTTPS
    Connecting --> InUse: TCP connect succeeds, HTTP
    TLS --> InUse: Handshake + certificate validation OK
    InUse --> Idle: HTTP exchange ends, connection reusable
    Idle --> InUse: Acquired for reuse
    Idle --> Closed: Idle/lifetime eviction or peer close
    InUse --> Closed: Network/protocol error or non-reusable
    TLS --> Closed: TLS handshake failed
    Connecting --> Closed: Connect timeout / failure
    Closed --> [*]
~~~

This is a **conceptual model**, not an exact mirror of every internal Reactor Netty state. HTTP/2 can serve multiple streams on one connection; finishing one stream does not immediately make the whole connection idle.

In a pooled environment:

1. The Gateway resolves the target URL from the route, e.g., `lb://inventory-service` resolves to a concrete instance.
2. The HTTP client must acquire a connection compatible with the endpoint/protocol/TLS settings.
3. If a usable idle connection exists, the client reuses it; otherwise, the pool opens a new one if capacity allows.
4. A new connection undergoes TCP handshake, followed by TLS handshake if the backend uses HTTPS.
5. The HTTP request/response runs over the connection.
6. When the exchange finishes, the connection returns to the pool **if still usable**; otherwise it closes.
7. When idle too long, reaching lifetime limits, or when the pool is disposed, the connection is evicted.

Never assume **every request opens a connection** or **every request always reuses an old connection**. Reuse depends on version, pool key, chosen endpoint, connection state, HTTP protocol, proxies, and remote closes.

## 5. Different timeouts within a single request

"Timeout" is a blanket word for many clocks starting and stopping at different moments.

| Parameter / concept | Where does it start? | What does it bound? |
| --- | --- | --- |
| **Pool acquire timeout** | When a request must borrow an outbound connection from the pool | Waiting too long when the pool is full or lacks connections |
| **TCP connect timeout** | When opening a new socket to a backend | Failing to establish TCP within the deadline |
| **TLS handshake timeout** | When starting the TLS handshake on a secure connection | Failing to negotiate/verify TLS in time |
| **HTTP response timeout** | While the HTTP client waits for a response per API semantics | Slow backend or lack of progress permitted by policy |
| **Read/write timeout** | During I/O operations if configured | Stalled data reads or writes per timeout condition |
| **Pool max idle time** | While a connection sits unused in the pool | Connections idle too long that should not be reused |
| **Pool max life time** | Measured from connection creation | Limits reusing overly aged connections |
| **Ingress/LB idle timeout** | Managed by an external proxy | Drops connections inactive for too long |
| **Client deadline** | When the client initiates an operation | End-to-end time limit chosen by the client |

Specifically:

- **Pool max idle time is not a response timeout.** A backend streaming data has an *in-use* connection; pool idle settings should not be expected to cut off a stream between two events.
- **Max life time is not a per-request deadline.** It governs retention/reuse in the pool. While a long exchange is running, specific disposal policies and HTTP client rules apply; do not assume a timer cuts off an active exchange right at the lifetime mark.
- **Connect timeout does not bound waiting to borrow from the pool.** If the pool is saturated, requests can hit acquire timeout before ever attempting TCP connect.
- **Response timeout does not cover all end-to-end latency.** Total wall time also includes route selection, filters, acquire, DNS, connect, TLS, upstream processing, streaming, downstream writes, and external proxies.

### Timeline of a request without an existing connection to reuse

~~~text
Request enters Gateway
  |-- Route + GatewayFilter
  |-- Pool acquire (may wait)
  |-- DNS / TCP connect (if opening new)
  |-- TLS handshake (if HTTPS)
  |-- Write HTTP request
  |-- Wait for + read HTTP response
  |-- Write response to client
  |-- Complete, connection may return to pool
~~~

Because multiple independent clocks exist, a request can fail **before calling the backend** (e.g., acquire timeout) or **after sending the request** (e.g., response timeout). Distinguishing them avoids misdirected retries or blindly inflating timeouts without fixing the root cause.

## 6. Choosing pool limits and idle times for real load

Reactor Netty provides connection pooling for its HTTP client. When configuring a **fixed/bounded** pool, key parameters to examine are:

| Parameter | Purpose | Risks if misconfigured |
| --- | --- | --- |
| `max-connections` | Caps connections granted per pool/destination per implementation | Too low: acquire queuing; too high: wasted sockets/CPU/TLS, upstream overload |
| `acquire-timeout` | Max wait for an available connection when the pool queues | Too short: errors during bursts; too long: requests pile up in queue |
| `max-idle-time` | Idle cap to avoid reusing stale connections | Too long: picks up sockets closed by peer/NAT; too short: constant connection churn |
| `max-life-time` | Connection age cap before stopping reuse | Too short: high handshake overhead; too long: retains very old state |
| `eviction interval` | Proactive interval to inspect and drop ineligible connections | Not a strict instant at which every expired connection closes |
| **Pending acquire limit** | Caps waiting requests if configured | Unbounded: queue growth and memory pressure |

### Why no single pool size fits every Gateway

Suppose an upstream receives **300 requests/second** on average, and each HTTP/1.1 request occupies a connection for roughly **200 ms**. Under steady load without multiplexing, average concurrent in-flight requests are approximately:

~~~text
Average concurrency ≈ throughput × latency
                    ≈ 300 req/s × 0.2 s
                    ≈ 60 concurrent requests
~~~

This is an intuitive application of Little's Law for steady state; **it is not a formula saying set pool = 60**. Once bursty traffic, p95/p99 latency, retries, SSE, and multiple backend endpoints factor in, required capacity can differ markedly. HTTP/2 multiplexing also changes the relationship between concurrent requests and TCP connections compared to HTTP/1.1.

What to measure in reality: active connections, idle connections, pending acquires, pending wait time, acquire failures, request latency, CPU, file descriptors, TLS handshakes, error rates, and backend resource limits.

### Setting idle timeouts across a proxy chain

If a backend or network load balancer closes idle connections after a short interval, holding connections in the pool longer can cause the Gateway to encounter **stale connections**. Consider setting **pool max idle shorter than the peer/middlebox idle threshold**, leaving safety margin to reduce the chance of reusing a remotely closed socket.

This is a **rule of thumb**, not an airtight guarantee against all stale sockets. Race conditions can still occur between when the pool checks a connection and when it writes the first byte. Test against real traffic, load balancers, and network infrastructure.

## 7. Configuring Gateway Server WebFlux HTTP client connection pools

Illustrative example using the modern **Spring Cloud Gateway Server WebFlux** configuration namespace:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 3000
            response-timeout: 10s
            pool:
              type: fixed
              max-connections: 150
              acquire-timeout: 3000
              max-idle-time: 20s
              max-life-time: 5m
              eviction-interval: 30s
~~~

**Intended meaning of this configuration:**

- `connect-timeout: 3000` illustrates TCP connect timeout in **milliseconds** on common Gateway lines.
- `response-timeout: 10s` sets a Duration threshold. Check exact response timeout semantics on your Gateway/Reactor Netty release.
- `type: fixed` selects a bounded connection pool.
- `max-connections: 150` is the sample pool cap, **not a global total cap across all services or all Gateway replicas**.
- `acquire-timeout: 3000` illustrates acquire wait timeout in milliseconds where that convention applies.
- `max-idle-time: 20s` caps how long idle connections remain eligible for reuse.
- `max-life-time: 5m` caps connection lifetime for pooling.
- `eviction-interval: 30s` illustrates proactive background eviction interval where supported.

**These are educational values, not defaults and not direct production recommendations.** Property names, types, and namespaces vary by version. On some earlier Spring Cloud Gateway WebFlux releases, the prefix is `spring.cloud.gateway.httpclient` instead of `spring.cloud.gateway.server.webflux.httpclient`. Verify each property like eviction interval or pool type in your exact release's metadata/docs, and confirm values **actually bound** rather than merely passing YAML syntax.

Example route paired with load balancing:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: inventory-route
              uri: lb://inventory-service
              predicates:
                - Path=/api/inventory/**
              filters:
                - StripPrefix=2
~~~

Load balancing resolves `lb://inventory-service` to an instance URL. The outbound pool applies to HTTP calls toward the chosen target, yet **does not replace Spring Cloud LoadBalancer, service discovery, or readiness probes**. When a service has multiple instances, connections spread across multiple destinations; never misread one `max-connections` number as an absolute cap across every backend in the cluster.

**TLS security:** when upstreams use HTTPS, configure truststore/certificate validation and mTLS as needed. Never disable certificate verification just to silence stale-connection or handshake-timeout errors.

## 8. Reactor Netty ConnectionProvider: understanding the underlying API

Spring Cloud Gateway Server WebFlux uses Reactor Netty for standard HTTP proxying. **ConnectionProvider** manages pooling in Reactor Netty's HTTP client. To understand what the settings mean, review this standalone Java example:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

class ReactorNettyPoolExample {

    static HttpClient createSampleClient() {
        ConnectionProvider provider = ConnectionProvider.builder("sample-upstream")
                .maxConnections(150)
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(5))
                .pendingAcquireTimeout(Duration.ofSeconds(3))
                .evictInBackground(Duration.ofSeconds(30))
                .build();

        return HttpClient.create(provider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3000)
                .responseTimeout(Duration.ofSeconds(10))
                .keepAlive(true);
    }
}
~~~

Points to understand:

- `ConnectionProvider.builder(...).maxConnections(...)` limits pool capacity as Reactor Netty partitions connection groups. It is not an HTTP requests/sec limit.
- `maxIdleTime(...)` and `maxLifeTime(...)` govern whether connections remain eligible for reuse.
- `pendingAcquireTimeout(...)` caps how long requests wait when the pool cannot grant a connection immediately.
- `evictInBackground(...)` requests periodic background eviction where supported by the API/version.
- `CONNECT_TIMEOUT_MILLIS` applies to TCP connect for **new connections**, not acquire timeouts.
- `responseTimeout(...)` governs waiting for responses during the HTTP exchange; distinct from pool idle.
- `keepAlive(true)` here refers to HTTP persistent connections, **not** OS `SO_KEEPALIVE`.

> **Important:** `createSampleClient()` above only creates **a standalone HttpClient**; it **does not automatically configure Spring Cloud Gateway's HTTP client**. To use a custom client inside a Gateway app, integrate via the extension point supported by your version or prefer Gateway-supported configuration properties. Never instantiate a new HttpClient inside a filter per request: that breaks reuse, leaks resources, and creates unclosed pools.

Also, when managing a custom `ConnectionProvider` manually, the application must **dispose resources** during shutdown. Never dispose after each request, and never assume Spring automatically cleans up a custom provider you created without registering lifecycle hooks.

## 9. Inbound idle is not outbound pool idle

The Client → Gateway path has different timeouts and limits from Gateway → backend:

| Location | Component deciding timeout | Example impact |
| --- | --- | --- |
| Browser/mobile | Client HTTP stack | Client closes connection when idle or past deadline |
| CDN/WAF | Edge proxy | Closes keep-alive or cuts inactive streams |
| Ingress / Load Balancer | Reverse proxy | Idle timeout, read/write timeout, connection draining |
| Gateway HTTP server | Reactor Netty server/Spring Boot config | Idle, header/body receive limits, server keep-alive policy |
| Gateway HTTP client | Reactor Netty pool and HTTP client | Acquire, connect, response, and pool idle/lifetime |
| Sidecar / service mesh | Proxy on internal hop | Own keep-alive, connection draining, and idle timeouts |
| Backend HTTP server | Service server/framework | Max idle connections, request/read timeouts |

A common mistake is seeing an ingress close an idle connection after one minute of silence and raising the Gateway's **pool max-idle-time**. That parameter may have zero effect on the **client → ingress** connection being closed.

### Keep-alive does not guarantee a connection lives forever

HTTP keep-alive only allows reuse while the connection remains valid. The remote peer can close connections per its resource policy. Load balancers proactively close long-idle connections; servers cap requests per connection or perform graceful shutdowns.

HTTP/1.1 headers like `Connection: keep-alive` or `Keep-Alive: timeout=...` are hints, not enforceable contracts forcing every proxy/backend to hold sockets to the exact second. Either side may close earlier, and HTTP/2 does not use HTTP/1.1 `Connection` headers.

### Do not treat every idle timeout as an error

An **idle connection that finished its request** being proactively closed is normal behavior. True errors are:

- Closing unexpectedly mid-request or mid-response.
- The Gateway reusing an already-closed connection and failing the request.
- Constant opening of fresh connections driving up CPU/TLS handshakes.
- The pool holding excessive idle sockets and exhausting file descriptors or service resources.

To conclude accurately, correlate connection-close events with HTTP exchange timestamps and pool metrics rather than reading `channel inactive` debug lines alone.

## 10. Stale connections and races with load balancers

A **stale connection** is a connection the pool still considers reusable while the peer or middlebox has already closed or is closing it. Example:

~~~mermaid
sequenceDiagram
    participant Gateway as Gateway pool
    participant LB as Network load balancer
    participant S as Backend
    Gateway->>LB: TCP/TLS connection established
    LB->>S: Connection to backend
    Gateway->>LB: GET /items/1
    S-->>Gateway: 200 response
    Note over Gateway,LB: Connection idle
    LB-->>Gateway: Idle connection closed / mapping expired
    Note over Gateway: Pool may not yet observe remote close
    Gateway->>LB: Attempt reuse for GET /items/2
    LB-->>Gateway: Reset / close / I-O failure
~~~

This can surface as `PrematureCloseException`, connection reset, EOF, or other I/O errors. **Not every 502 or 503 is a stale connection**; correlate logs, timing, and actual infrastructure.

Practical mitigations:

1. **Know peer/middlebox idle timeouts.** If the network closes quickly, set pool max idle shorter with a safety margin.
2. **Use appropriate eviction.** Background eviction intervals help prune long-idle connections, though they cannot eliminate every race.
3. **Track reuse failures.** Distinguish errors on reused connections from TCP connect/TLS errors on fresh connections when telemetry provides it.
4. **Retry conditionally.** Retry only when compatible with idempotency/deadline contracts, knowing the request may already have reached the backend before the connection failed.
5. **Readiness/draining.** When an upstream instance is about to rotate out, stop routing new traffic first, then drain/close connections gracefully.
6. **Avoid ultra-short timeouts across the board.** Overly short values trigger connection churn and handshake load; measure real impact.

### Why retrying a POST is not necessarily safe

Suppose the Gateway sends `POST /orders`, the backend creates the order, and the socket closes before the response reaches the Gateway. The Gateway sees a failed request, yet **the side effect already occurred**. Automatically retrying on another connection/instance risks creating a duplicate order.

For operations with side effects, use **idempotency keys**, backend deduplication storage, and bounded retry policies. Load balancing and keep-alive cannot solve the "processed but lost response" problem.

## 11. TLS handshakes, connection reuse, and certificate rotation

New HTTPS connections require a TCP connect followed by a TLS handshake. When reusing **the same open TLS connection**, subsequent HTTP requests run on that existing session without renegotiating TLS from scratch per request. That lowers CPU, handshake latency, and certificate chain checks.

~~~text
New HTTPS connection:
  DNS -> TCP connect -> TLS handshake -> HTTP request/response

Reusing an existing HTTPS connection:
  Existing open TCP/TLS connection -> HTTP request/response
~~~

Do not confuse **connection reuse** with **TLS session resumption**. Resumption lets a **new TLS connection** reuse prior security session parameters under protocol/server/client rules to trim handshake cost; it does not turn a closed TCP socket back into an open one.

### Certificate lifecycle and long-lived connections

Certificates are typically verified during the **TLS handshake**. An already-open TLS connection does not necessarily re-verify certificates on every HTTP request over that connection. When a backend rotates certificates, truststores, or mTLS settings:

- **Existing connections** may keep working until closed by policy/protocol.
- **New connections** use the new certificate and must pass validation.
- Pool max life/idle and graceful draining govern how long old connections remain in use.
- Ensure truststores and TLS client configs reload via a supported system mechanism; merely replacing a file on disk does not guarantee running SSL contexts auto-reload.

Never treat `max-life-time` as a guarantee that "every 5 minutes all TLS certificates are re-checked." It is a pool lifecycle setting, not an independent certificate lifecycle policy.

### When TLS errors occur

Errors like certificate expired, hostname mismatch, unknown CA, or TLS handshake failures occur **before a new HTTP(S) request can transmit normally**. Never "fix" them by switching to HTTP or disabling verification. Check the selected backend scheme, `ServiceInstance` host/IP, certificates, truststore, TLS port, certificate validity dates, and system clocks.

## 12. SSE, NDJSON, streaming, and WebSockets: long-lived connections that are not simply "idle"

Typical APIs have short request/response cycles, returning connections to the pool quickly. Certain traffic types **hold connections or HTTP streams open for long periods**:

| Traffic | Lifecycle characteristics | Common pitfalls |
| --- | --- | --- |
| Short JSON request/response | Completes quickly and returns connection to pool | Pool runs out of capacity under bursts |
| Large download | Response transmits over an extended period | Too-short read/response timeout aborts download |
| SSE (`text/event-stream`) | Continuous response; may have silent gaps between business events | Proxy idle timeout drops the stream |
| NDJSON streaming | Incrementally streams records | Filters buffering the whole body exhaust RAM/break streaming |
| WebSocket | Upgrade and long-lived bidirectional connection | Ping/pong, timeout, and routing policies differ from short HTTP requests |
| Multi-stream HTTP/2 | Multiple streams share one connection | Counting each stream as a TCP connection skews sizing |

### SSE is not automatically protected by HTTP keep-alive

An SSE stream can stay open for minutes with **zero data bytes** between events. If an ingress or proxy enforces an idle/read timeout, it can close the connection even though the HTTP response has not ended. Options to consider:

- Periodic **SSE comment heartbeats** if the contract/clients and entire proxy stack allow them, such as a keepalive comment line.
- **Appropriate timeout settings** across ingress, Gateway HTTP client, and backend for streaming endpoints.
- **Application-level reconnect/resume** with event IDs if zero event loss is required.
- **Do not substitute TCP SO_KEEPALIVE for HTTP keep-alive**: TCP probes may not reset HTTP-layer proxy idle timers.

An SSE comment heartbeat:

~~~text
: keepalive

event: inventory-change
data: {"id":"42","stock":8}

~~~

Some proxies buffer responses or track idle based only on forwarded payload bytes; test heartbeats **all the way to the actual client**, not merely by seeing the backend log an event.

**Distinguish response timeout from stream idle timeout.** Depending on Reactor Netty/Gateway version, `response-timeout` may bound waiting for a response or gaps without incoming data per implementation. Never enforce one short threshold across all endpoints expecting long SSE/downloads to survive; verify semantics on your version and use per-route timeout policies if supported.

### Connection pools for long-lived traffic

When many HTTP/1.1 requests hold upstream connections open long-term, they occupy pool capacity for long stretches. Pools serving short requests may queue for acquire even at modest RPS. Isolating policies/routes, capping stream counts, and sizing for long-lived sessions matters more than infinitely raising `max-connections`.

WebSockets typically go through separate upgrade and routing mechanics; do not assume an HTTP connection pool's `max-idle-time` closes active WebSockets by the same rules.

## 13. Service discovery, instance churn, and connection draining

With `lb://inventory-service`, **ReactiveLoadBalancerClientFilter** picks a `ServiceInstance`, and the routing filter uses the concrete HTTP(S) URL. With multiple instances, the outbound pool can hold connections to each endpoint.

~~~mermaid
flowchart LR
    LB[LoadBalancer] --> A[Instance A]
    LB --> B[Instance B]
    Pool[Outbound connections] --> A
    Pool --> B
    Registry[Discovery updates] --> LB
~~~

An instance leaving the system does not make every TCP connection to it disappear instantaneously:

1. The registry/orchestrator updates instance status.
2. The Gateway may receive the update after a cache/TTL window.
3. The load balancer stops selecting the instance once its candidate list refreshes.
4. Old connections to that instance may still be serving requests/streams or sitting idle in the pool awaiting cleanup.
5. Backend/ingress should proactively drain and close so new requests do not hit a terminating instance.

**Safe scale-down requires coordination across components**, not just tuning `max-idle-time`. If a service stops before in-flight requests finish, clients see resets or truncated responses. Readiness probes, deregistration, drain timeouts, and backend graceful shutdown all matter.

### DNS and pools are not the same lookup table

When routes use service discovery, `ServiceInstance` supplies host/port. When routes use standard HTTP hostnames, DNS resolves addresses when opening new connections; already-open connections are not automatically recreated just because a DNS record changed. Pools retaining old connections can keep hitting the old IP while those connections live.

Therefore, when shifting traffic across regions or rotating endpoints via DNS, treat **DNS TTL, connection lifetime, pool disposal, and draining policy** as separate layers.

## 14. Graceful shutdown of Gateway and backends

During rolling deployments, the goal is not "keep every connection forever," but **stop accepting new work, finish in-flight work, and release resources cleanly**.

~~~mermaid
sequenceDiagram
    participant LB as Ingress/LB
    participant G as Gateway instance
    participant U as Upstream

    Note over G: Shutdown begins
    G-->>LB: Readiness stops accepting new traffic
    LB->>LB: Stops picking Gateway for new requests
    G->>U: Finishes in-flight requests within deadline
    U-->>G: Response
    G->>G: Closes connections / disposes resources
    Note over G: Grace period expires, forced termination may occur
~~~

Sequence to design:

1. **Stop routing new traffic** to the terminating instance (readiness/routing/draining).
2. **Allow in-flight requests to complete** within a realistic grace period.
3. **Define handling for long-lived connections** (SSE, WebSocket, large uploads/downloads). You cannot guarantee they finish before the deadline without a reconnect contract.
4. **Dispose connection pools and HTTP client resources** on shutdown via framework lifecycle hooks.
5. **Monitor post-shutdown errors**: connection resets, pending requests, 502/503s, and incomplete request rates.

Spring Boot and Reactor Netty support graceful shutdown depending on version/config, yet **you must not claim that flipping one property drains all in-flight SSE/WebSockets indefinitely**. Orchestrator, ingress, proxy, and application timers must align.

The same applies to backends: remove an instance from load-balancing pools before closing its server socket so the Gateway avoids sending new requests to a shutting-down instance.

## 15. Resource limits and protecting the Gateway from overload

Connection pooling reuses resources, yet also introduces queues and limits requiring careful design.

Common pressure points:

- **Too many open files / file descriptors:** excessive open TCP connections and sockets.
- **Ephemeral port exhaustion:** too many outbound connections to one or more targets, especially under high churn.
- **TLS handshake CPU:** overly short pool lifetimes forcing constant fresh HTTPS connections.
- **Pending acquire queue:** undersized pool causing requests to pile in queues instead of executing.
- **Event-loop blocking:** Gateway filter code calling `block()` or blocking I/O stalls all connections.
- **Slow clients / slow upstreams:** connections and buffers held too long, driving memory/backpressure issues.
- **Retry storms:** connection failures multiplying backend calls and acquire attempts.

Corresponding protections:

1. **Bounded pools and bounded pending queues** matched to backend capacity instead of unbounded growth.
2. **Rate limiting** at the Gateway to cap inbound load from trusted sources; remember rate limiters count requests and do not replace pool capacity.
3. **Deliberate connect/acquire/response timeouts** per workload group; no single number fits every API.
4. **Never block the event loop**; isolate any unavoidable blocking work onto dedicated resources.
5. **Circuit breakers and bounded retries** to shed load when services degrade.
6. **Body/header and long-connection limits** across WebFlux, ingress, and backend policies.
7. **Control TLS and service discovery sources**, never letting clients arbitrarily specify internal hosts/ports.

**Never solve pool saturation solely by raising `max-connections`.** If the backend is already overloaded, opening more sockets worsens latency and error rates. Examine concurrency, processing times, queues, and resources across both Gateway and backends.

## 16. Metrics, logs, and tracing for connection lifecycles

To verify whether pooling works properly, observe both HTTP and TCP/TLS on the **Gateway outbound side**:

| Signal group | Purpose |
| --- | --- |
| Active connections | How many connections are serving I/O or leased |
| Idle connections | How many connections sit idle and reusable |
| Pending acquires / wait time | Are requests queuing for connections? |
| Acquire timeouts/failures | Pool lacks capacity or cannot grant connections in time |
| TCP connect duration/failures | Network issues reaching backend host/port? |
| TLS handshake duration/failures | Certificate, truststore, or TLS config issues? |
| Connection churn | Unusually high rate of opening/closing connections? |
| HTTP request latency and status | Slow backend or Gateway failing before upstream? |
| Event-loop latency/CPU | Non-blocking runtime stalled? |
| In-flight streams | Many long-lived SSE/WebSocket/upload/download sessions consuming capacity? |

Reactor Netty, Spring Boot Actuator, Micrometer, and Spring Cloud Gateway can emit metrics/traces when enabled and configured properly. **Metric names/labels change across versions**, so never hardcode a metric name assuming every release emits it identically.

### Reading an incident through metrics

| Observation | Possible interpretation |
| --- | --- |
| Pending acquires rising, active at cap | Pool saturated or backend processing slow |
| Idle near 0, TLS handshakes rising | High connection churn, idle/lifetime too short, or rising load |
| Very high idle yet file descriptors exhausted | Pool/config retaining excessive unused sockets |
| Connect errors rising, no-instance flat | Instance selected, yet network connection to upstream failing |
| No-instance rising after rollout | Discovery/readiness/caches not updating cleanly |
| Client 502s spike right after quiet periods | Possible stale connection reuse; verify via logs/packets/telemetry |
| SSE drops after a fixed interval | Likely ingress read/idle timeout, not necessarily pool idle timeout |
| p99 latency rises while request rate stays flat | Slow backend, growing acquire queue, or blocked event loop |

Group metrics by route ID/service ID and bounded-cardinality labels. Never use tokens, raw queries, request IDs, or user IDs as metric tags; never log session keys or certificate private keys. Instance IPs/IDs churn under autoscaling, so guard label cardinality.

If you must debug connection IDs, enable appropriate log levels in a controlled environment, correlate safely via trace/request IDs, and dial logging back down afterward to prevent log flooding and data leaks.

## 17. Troubleshooting table for common failures

| Symptom | Causes worth checking | Appropriate action |
| --- | --- | --- |
| First request slow, subsequent ones fast | DNS/TCP/TLS handshake on fresh connection | Measure connect, handshake, and reuse; do not assume a bug |
| 502/reset after idle intervals | Stale pooled connection closed by proxy/peer | Compare idle timeouts across layers; lower max idle with margin |
| Load rises → 5xx and pending acquires climb | Pool saturation or high backend latency | Measure active/pending/CPU; balance pool and backend capacity |
| Gateway opens too many connections | Pool limits, many destinations, retries, or multiple replicas | Check pool keys, service instance count, and total sockets |
| Failures only when calling HTTPS upstreams | TLS trust/hostname/cert/port, handshake timeout | Inspect certificates and mTLS; never disable verification |
| SSE drops periodically | Proxy/read/response timeouts or buffering | Check every hop, heartbeats, and resume contracts |
| WebSocket disconnects when idle | Ping/pong and proxy/tunnel timeouts | Verify WebSocket routing and exact idle timeouts |
| Instance removed from cluster still gets traffic | Stale registry/cache or active old connections | Check discovery refresh, readiness, and draining |
| DNS changed yet requests still hit old IP | Existing pooled connections or DNS cache | Check DNS TTL, connection lifetime, and draining |
| High CPU under moderate traffic | TLS handshake churn, event-loop blocking, or retry storms | Measure handshakes, reuse, pool stats, and blocking |
| 503 when using `lb://` | No instances or other Gateway/backend error | Distinguish no-instance from connect/response failures |
| Gateway shutdown drops uploads | Short grace period, sockets closed too early | Align readiness, draining, shutdown, and deadlines |

**Outside-in analysis checklist:**

1. Is the client calling **HTTP/1.1 or HTTP/2**, over HTTPS or HTTP?
2. Is any CDN/ingress/WAF/sidecar **closing connections before** the Gateway or backend?
3. What URL does the Gateway route to: `http://`, `https://`, or `lb://`?
4. If `lb://`, is the load balancer picking a valid `ServiceInstance`?
5. Is the HTTP client **waiting on acquire**, opening a new TCP connection, or reusing an old one?
6. Did the error occur at TCP connect, TLS handshake, waiting for response, or mid-stream?
7. Are `max-idle-time`, `max-life-time`, pending timeout, and response timeout compatible across layers?
8. Are **retries, circuit breakers, rate limiters, event-loop blocking**, or instance rollouts involved?
9. Are status/body preserved safely if errors happen after response commit?

Never treat a TCP-layer error as proof that route predicates, header rewrites, or authentication are broken. Pinpointing the exact failure layer yields the smallest, safest fix.

## 18. Hands-on: measuring keep-alive and handling stale connections

**Scenario:** The Gateway has a `GET /api/inventory/**` route to Inventory service. Two backends run on 9001 and 9002; the Gateway uses `lb://inventory-service` or a fixed HTTP URI for simpler testing. The goal is reducing connection setup cost while tolerating backend changes.

### Part A — Verifying HTTP persistence

1. Start the Gateway and test backend with safe logging of connection IDs or TCP connection open counts.
2. Send multiple requests from the same client process:

~~~bash
curl -v --http1.1 \
  'http://localhost:8080/api/inventory/items/42' \
  'http://localhost:8080/api/inventory/items/43'
~~~

3. Observe whether **client → Gateway** reuses the HTTP/1.1 connection. Note: `curl` only reveals the **client → Gateway hop**; it does not prove Gateway → backend reused a socket.
4. Use Reactor Netty or backend test logs/metrics to confirm whether the **outbound hop** reused the connection after the request finished.
5. If your infrastructure supports HTTP/2, compare how multiple streams share one connection; never send `Connection: keep-alive` on HTTP/2.

### Part B — Setting pool limits with evidence

1. Start with the bounded pool configuration from section 7 after confirming exact property names for your Gateway version.
2. Generate controlled GET bursts from an approved load-testing tool in a test environment — never load-test production.
3. Measure active, idle, pending acquires, acquire time, p95/p99 latency, and error rates.
4. Lower `max-connections` in a controlled step to observe queuing. Then raise it modestly to compare; never pick a number from TPS alone.
5. Vary `max-idle-time` and `max-life-time` within sensible bounds; observe how connect/TLS handshake counts change.

### Part C — Simulating stale connections

1. Configure a test backend or proxy with an idle timeout shorter than the pool's intended reuse window.
2. Send one successful request, then let the connection sit idle past the peer's timeout.
3. Send another request and note whether a reset, retry, or fresh connection open occurs. Do not require the failure on **every single attempt** due to timing races and how Netty detects remote closes.
4. Adjust the pool's max idle shorter than the peer idle timeout with a margin, then re-test under the same conditions.
5. Contrast safe retries on GET against side-effecting POSTs; explain why automatic retries must not be used as blanket insurance across all HTTP methods.

### Part D — Streaming, TLS, and rollouts

1. Create an SSE endpoint emitting periodic events; pause events long enough for a test proxy to close an idle stream.
2. Add application-level heartbeats, verify events reach the client, and inspect timeouts on **every hop**, not just the pool.
3. Enable HTTPS to the backend with valid certificates; observe handshakes on new connections vs. reuse of existing connections.
4. Simulate stopping a backend instance via readiness → deselection → drain → shutdown; measure failed requests during rollout.
5. Verify metrics/logs do not expose tokens, private query parameters, or TLS keys.

### Result matrix to record

| Case | Expected observation |
| --- | --- |
| Two sequential GETs from same client | Client hop may reuse connection if both sides permit |
| Two sequential GETs to same upstream | Gateway → backend hop may reuse an eligible pooled connection |
| Pool exhausts capacity | Pending acquires rise; may time out waiting |
| Proxy closes idle connection | Some reuse attempts may fail or open new connections |
| Max idle shorter than peer idle | Reduces stale reuse risk, increases churn if set too short |
| HTTPS opens new connection | Performs TCP/TLS handshake and certificate validation |
| HTTPS reuses existing connection | Skips fresh handshake per request |
| SSE silent for too long | May hit proxy timeout even though response has not ended |
| Rollout/scale-down | Discovery, pooling, and draining must coordinate to minimize resets |

**Pass criteria:** You accurately pinpoint where idle or timeout events happen, separate inbound from outbound, prove pool reuse with connection-level evidence, measure pool limit impact, and handle stale connections safely. Any timeout or retry proposal must rest on application contracts and real measurements.

## 19. Key takeaways

- **HTTP keep-alive, TCP keepalive, and connection pools are three distinct mechanisms.** HTTP enables reuse; TCP keepalive probes sockets; pools manage outbound connection capacity and lifecycles.
- **The Gateway has two independent connection sides**: client → Gateway and Gateway → backend. Timeouts across ingress, Netty server, Reactor Netty client, sidecar, and backend must be understood for **their exact hop**.
- **Max idle time** caps holding idle connections for reuse; **max life time** caps connection age; **acquire timeout** caps waiting on the pool. Never confuse them with **connect timeout**, **TLS handshake timeout**, **response timeout**, or client deadlines.
- **Reuse saves TCP/TLS handshakes**, yet keeping connections too long raises stale socket risk when peers or proxies close early. Tune from real data with safety margins.
- **HTTP/2 multiplexing, SSE, NDJSON, and WebSockets** have different connection behavior from short HTTP/1.1 requests. Never apply one idle/response timeout across all traffic types without end-to-end testing.
- **Service discovery, load balancing, connection pooling, and graceful draining** must coordinate when backend instances change. Terminating a backend before removing it from selection drops in-flight requests.
- To operate Spring Cloud Gateway safely, measure **active/idle/pending connections, handshakes, latency, and error rates**, enforce resource limits, protect TLS, and retry only when business correctness is guaranteed.
