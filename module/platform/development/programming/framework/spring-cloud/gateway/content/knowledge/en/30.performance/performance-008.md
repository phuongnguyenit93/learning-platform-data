# Evaluating Latency from TLS, DNS, and Connection Setup

## 1. The Problem: The API Processes Fast, Yet the Gateway Responds Slowly

In a microservices system, **Spring Cloud Gateway** accepts HTTP requests, selects routes via route predicates, runs filter chains, transforms paths/headers, discovers services via `lb://`, enforces authentication and rate limiting, performs retries and circuit breaking, and traces requests. Even when a backend endpoint takes only 15 ms to process, users can still wait 150 ms or more due to **DNS resolution, TCP connection setup, TLS handshakes, or connection-pool waits**.

Suppose a `GET /api/catalog/items/42` request travels through:

~~~text
Mobile client -- HTTPS --> Ingress -- HTTP(S) --> Spring Cloud Gateway
                                                |
                                                | HTTPS / lb://catalog-service
                                                v
                                           Catalog backend
~~~

The Catalog application reports 12 ms of processing time. Yet the first call after a deployment may require DNS lookup, TCP connect, and a TLS handshake on the **Gateway → Catalog** hop, whereas subsequent calls reusing a pooled connection can be dramatically faster. Looking only at Catalog processing time leads you to tune the wrong database, Java filters, or replica counts without fixing the real cause.

This lesson, **"Evaluating Latency from TLS, DNS, and Connection Setup,"** belongs to the **Performance** chapter of the **SPRING_CLOUD_GATEWAY** module. The goal is not merely drawing a latency chart, but **breaking latency down per hop, verifying that each metric truly measures the intended layer, running controlled experiments, and optimizing without sacrificing security or reliability**.

### After This Lesson, You Will Be Able To

1. Distinguish DNS, TCP connect, TLS handshake, pool acquisition waits, upstream processing, and response transfer.
2. Explain why **a single request can trigger multiple DNS lookups and multiple TLS handshakes** across different hops, while connection-reusing requests skip them.
3. Use `curl --write-out` to estimate phases on **client → Gateway**, reading cumulative timestamps and measurement limits accurately.
4. Design dedicated measurements for **Gateway → upstream** using HTTP client/pool metrics, tracing, and a backend stub instead of confusing them with client-side timings.
5. Distinguish **OS/JVM/Netty DNS resolution**, TTLs/caches, and `lb://` resolution via service discovery.
6. Understand TLS 1.2/1.3, session resumption, SNI/ALPN, mTLS, connection reuse, and their impact on cold-start latency.
7. Design a **cold connection vs. warm pooled connection** experiment with baselines, p50/p95/p99, counters, and control groups.
8. Diagnose DNS timeouts, TCP connection refused, TLS certificate errors, pool acquire timeouts, stale keep-alive sockets, HTTP/2 stream saturation, and retry amplification.
9. Pick appropriate optimizations for **Gateway Server WebFlux (Reactor Netty)** or **Gateway Server Web MVC (Servlet/HTTP client)** for your exact version.

> **Version scope:** Primary examples target **Spring Cloud Gateway Server WebFlux** and Reactor Netty. Where Web MVC is discussed, Servlet and outbound HTTP client differences are noted explicitly. Exact starter, property, and metric names vary across Spring Boot, Spring Cloud Gateway, and Reactor Netty releases; verify your **dependency BOM and version-specific docs** rather than copying WebFlux settings onto MVC.

## 2. Two-Way HTTP Map: Measure the Right Hop Before Optimizing

A Gateway typically acts both as an **HTTP server** toward clients and an **HTTP client** toward backends. With ingress proxies or service meshes in between, additional HTTP/TLS hops exist.

~~~mermaid
flowchart LR
    C["Browser / Mobile"] -->|"DNS + TCP + TLS"| I["Public ingress / LB"]
    I -->|"TCP or TLS"| G["Spring Cloud Gateway"]
    G -->|"Pool acquire + DNS + TCP + TLS"| U["Catalog upstream"]
    U -->|"Response bytes"| G
    G -->|"Response"| I
    I -->|"Response"| C
~~~

### Components That Commonly Appear on a Request

| Component | Where does it happen? | When is it significant? |
| --- | --- | --- |
| **DNS lookup** | Client resolves public host; Gateway or HTTP client resolves upstream host | Cache misses, expired TTLs, slow resolvers, many hostnames |
| **TCP connect** | Each hop opening a new TCP connection | Cold connections, packet loss, SYN retransmits, cross-region RTT |
| **TLS handshake** | New HTTPS hop before HTTP application data flows | Certificate chains, mTLS, high RTT, TLS version/resumption |
| **Pool acquire** | Gateway outbound client picking or waiting for a connection | Full pools, max connections, pending queues, HTTP/2 stream caps |
| **Route/filter processing** | Gateway application | Predicates, auth, rewrites, retries, circuit breakers |
| **Service discovery** | Gateway picking a `ServiceInstance` for `lb://` | Registry caches, topology, health filtering |
| **Backend application** | Target service | DB, cache, business logic |
| **Response transfer** | Backend → Gateway → client | Large payloads, bandwidth, TCP flow control, slow clients |

**First question to answer:** Does client HTTPS **terminate TLS at the ingress**, or end-to-end at the Gateway? If the ingress terminates TLS and speaks plain HTTP internally, tuning Gateway outbound TLS affects only Gateway → Catalog, **not** client → ingress. A set of `curl` timings from your laptop cannot prove the JVM's outbound DNS or TLS is slow.

### One Request Path Can Span Multiple Connections

~~~mermaid
sequenceDiagram
    participant Client
    participant Ingress
    participant Gateway
    participant Resolver as DNS / Discovery
    participant Catalog
    Client->>Ingress: Public DNS + TCP + TLS (if new connection)
    Ingress->>Gateway: HTTP/TLS request
    Gateway->>Resolver: Select service instance / resolve host (if needed)
    Resolver-->>Gateway: Host + IP / instance
    Gateway->>Catalog: TCP connect + TLS (if no pooled connection)
    Gateway->>Catalog: GET /catalog/items/42
    Catalog-->>Gateway: 200 + body
    Gateway-->>Ingress: HTTP response
    Ingress-->>Client: Response
~~~

On a **warm** request, the client, ingress, and Gateway can reuse existing connections on their respective hops, skipping DNS/TCP/TLS altogether. Conversely, when the Gateway fans out to multiple upstreams or retries another instance, one operation can trigger fresh connections to multiple targets.

## 3. Latency Budget Formula and Limits on Adding Numbers

To locate bottlenecks, model a single Gateway call by phases:

\[
T_{\text{total}} \approx T_{\text{client-to-gateway}}
+T_{\text{gateway-route}}
+T_{\text{pool-wait}}
+T_{\text{resolve}}
+T_{\text{tcp-connect}}
+T_{\text{tls}}
+T_{\text{upstream-wait}}
+T_{\text{response-transfer}}
\]

**This is a conceptual critical-path budget**, not an equation you can blindly populate by adding arbitrary counters. Keep in mind:

- `T_client-to-gateway` can span public DNS, TCP, TLS, ingress queues, request transfer, and internal hops.
- `T_pool-wait` may end in **pooled connection reuse**, making DNS/connect/TLS zero for that request.
- `T_resolve` appears only when resolving an address missing or expired in cache; `lb://` discovery selection and DNS lookup **are not the same operation**.
- HTTP clients can overlap or run steps asynchronously; retries and fallbacks can create **multiple attempts** per inbound request.
- `T_response-transfer` depends on body size, streaming, bandwidth, and client read speed.

### Illustrative Numbers for Cold vs. Warm Requests

| Phase | Illustrative cold request | Illustrative warm request |
| --- | ---: | ---: |
| Backend/route computation & other overhead | 35 ms | 35 ms |
| Outbound DNS | 8 ms | 0 ms |
| Outbound TCP connect | 20 ms | 0 ms |
| Outbound TLS handshake | 30 ms | 0 ms |
| Pool wait / extra response transfer | 7 ms | 5 ms |
| **Total under sequential addition assumption** | **100 ms** | **40 ms** |

These are **hypothetical educational figures**, not Spring Cloud Gateway benchmarks or defaults. Same-zone upstreams can look much smaller; cross-region hops via proxies or packet loss can look far worse. Optimizing a phase only pays off if you prove it matters in your **real traffic mix**.

### Never Add Per-Phase p95s to Derive Total p95

Suppose DNS p95 is 20 ms, TCP p95 is 30 ms, and TLS p95 is 40 ms. **You must not claim** total p95 across the three phases is 90 ms. Percentiles come from separate distributions and do not necessarily hit the same request. To know end-to-end p95, measure **the full end-to-end request distribution**; to diagnose tail causes, correlate phase timings/traces on **the same request or connection attempt**.

### Throughput Differs from Latency

Little's law for a stable system in steady state:

\[
L = \lambda W
\]

At 500 requests/second with an average request duration of 0.1 s, average concurrency is roughly 50. If connection setup and handshakes push `W` to 0.3 s at the same arrival rate, `L` rises to roughly 150. That is **average operation concurrency**, not literally Servlet thread count or Reactor Netty channel count. It illustrates why extra latency pressures **connections, queues, memory, and timeout budgets** even when backend CPU is idle.

## 4. DNS: From Hostname to IP and Why Caching Governs Latency

**DNS resolution** translates hostnames into IP addresses or records. A Gateway deployment can involve several DNS layers:

~~~text
Browser/mobile resolver
    -> public DNS name of ingress
Ingress/proxy resolver
    -> hostname of Gateway service (if used)
Gateway outbound HTTP client resolver
    -> hostname of upstream instance
Backend resolver
    -> further dependencies, outside the Gateway outbound phase
~~~

On the Gateway side:

1. A route may target a URL like `https://catalog.internal.example`; the HTTP client resolves that hostname when opening new connections.
2. A route may use `lb://catalog-service`; Spring Cloud LoadBalancer/discovery picks a `ServiceInstance` first, and if that instance's host **is not an IP**, the HTTP client may still perform DNS resolution.
3. Traffic may pass through a service mesh or local DNS cache; JVM-observed DNS timings can differ from external resolver timings.

### What Contributes to DNS Latency?

| Phase or event | Observation |
| --- | --- |
| Resolver cache hit | Almost no upstream DNS query; memory lookup only |
| Cache miss | Resolver issues a query, potentially recursive DNS |
| CNAME chain | Extra names to resolve; parallelism depends on resolver |
| A/AAAA resolution | May query IPv4/IPv6 and race/order attempts |
| NXDOMAIN / negative cache | Failure results cached per policy |
| DNS timeout / retransmission | High tail latency; can fail before TCP starts |
| TTL expiration | Requires fresh lookup, though not necessarily on every request |
| IP rotation | Already-open connections may keep talking to the old IP |

**A short TTL does not mean DNS runs on every request** if the outbound pool still holds reusable connections. Conversely, under high connection churn, even a fast DNS cache leaves the Gateway paying TCP/TLS costs on frequent new connections.

### JVM DNS and Reactor Netty Resolver Are Not One Shared Cache

Java maintains JVM name-service caching policies (e.g., `networkaddress.cache.ttl` and negative TTL security properties), whereas Reactor Netty/Netty can run its own **DNS resolver, event loop, and cache**. Spring Cloud Gateway Server WebFlux typically uses the Reactor Netty HTTP client; Gateway Server Web MVC uses the Servlet stack's configured outbound client.

Consequently:

- Changing JVM DNS TTL **does not guarantee** Netty's DNS resolver cache changes too.
- Running `dig` or `nslookup` from an operator shell **does not inspect the Gateway process's internal DNS cache**.
- Resolvers cache A and AAAA records per their own rules; load balancers and service meshes may maintain their own endpoint caches.
- Tuning TTLs requires evaluating **IP rollovers, failover speed, DNS query volume, and negative caching**, not only shrinking `time_namelookup`.

Never set TTL to 0 or "cache forever" to chase p99 without verifying your system's **IP rotation and topology recovery requirements**.

## 5. DNS and Service Discovery: Two Distinct Target Selection Steps

Spring Cloud Gateway can define a route like:

~~~yaml
# Conceptual example for Gateway Server WebFlux supporting this namespace.
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1
~~~

In this flow:

1. **Gateway route matching** picks `catalog` by `Path`.
2. **Service discovery/LoadBalancer** picks a `ServiceInstance` for `catalog-service`.
3. If that instance's host is a hostname, the outbound client needs a DNS lookup or cache hit for the IP.
4. **The connection pool** looks for an existing open connection to that endpoint; if none is available, it opens a TCP connection plus TLS for HTTPS.

~~~mermaid
flowchart TD
    A["Route lb://catalog-service"] --> B["Select ServiceInstance"]
    B --> C{"Suitable pooled connection?"}
    C -->|Yes| R["Reuse HTTP connection"]
    C -->|No| D{"Valid resolved address cached?"}
    D -->|Yes| E["TCP connect"]
    D -->|No| Q["DNS resolution / cache"]
    Q --> E
    E --> T{"HTTPS?"}
    T -->|Yes| H["TLS handshake"]
    T -->|No| N["HTTP request"]
    H --> N
    R --> N
~~~

This flowchart is **conceptual**; implementations may query resolvers/caches before pool checks, partition pools by host/IP/proxy/SNI, or multiplex HTTP/2 streams on one connection. Measure the **actual code path of your running version**, rather than treating the diagram as an exact class-level trace.

### Is Slow Service Discovery the Same as Slow DNS?

No. A load balancer may stall waiting for registry refreshes, health checks, zone filtering, or instance list caches even when DNS responds instantaneously. When investigating, separate:

- Time spent choosing an instance from registry/load balancer.
- Time spent DNS-resolving that instance's hostname, if any.
- Time spent on pool acquire, TCP connect, and TLS.
- Time spent in HTTP request/response handling.

Lumping all of these into one `upstream latency` metric hides whether to fix the DNS resolver, registry cache, connection pool, or backend itself.

## 6. Inspecting DNS Properly: Resolvers, TTLs, and Shifting Addresses

When suspecting DNS, answer **three questions**: Did a DNS lookup actually happen during the slow request? Which resolver did it query? After the answer arrived, which IP did the HTTP client connect to?

### Simple Tools and Their Limits

~~~bash
# Query A record from the current machine's default resolver.
dig +noall +answer catalog.internal.example A

# Query AAAA record (if IPv6 is present).
dig +noall +answer catalog.internal.example AAAA

# Example checking resolver responses at different times.
nslookup catalog.internal.example
~~~

The hostname above is **illustrative**—substitute an authorized test hostname. `dig` and `nslookup` bypass the Gateway's JVM/Netty caches and may hit a different resolver, so **you cannot directly conclude the JVM waited that exact number of milliseconds**. The TTL field in a DNS reply shows remaining cache lifetime in the queried resolver, **not the query history of a Gateway request**.

### Separating DNS Failures from Connect Failures

| Event | What happened | Supporting evidence |
| --- | --- | --- |
| DNS NXDOMAIN | Name does not exist in queried DNS | DNS error; no IP target to TCP-connect |
| DNS timeout | Resolver failed to reply before deadline | Resolver timeout/error, often multiple retransmissions |
| DNS returns old IP | Cache TTL not expired or old connection kept | Cache snapshot, remote IP of active connection |
| DNS returns new IP, TCP refused | DNS succeeded; target refused TCP | Connect failure, SYN/RST |
| A works, AAAA unreachable | Suboptimal IPv4/IPv6 selection or racing | Address-family logs and connect attempts |
| Discovery finds no instance | Could not pick an upstream service | LoadBalancer/discovery logs, **not DNS NXDOMAIN** |
| TLS hostname mismatch | Reached TLS peer, identity rejected | Certificate/SAN/SNI validation error |

### Testing DNS TTL and Pooling Separately

Sample lab experiment:

1. Create an internal test hostname with controlled DNS A/AAAA records and TTL.
2. Call the Gateway before any outbound connection exists; record DNS lookup, remote IP, connect, and TLS.
3. Send multiple subsequent calls **within the same Gateway process**, recording connection reuse counts.
4. Flip the DNS record from stub IP A to stub IP B and wait out the test TTL.
5. Observe which IP **new connections** use vs. where **existing pooled connections** continue pointing.
6. Adjust max connection lifetime/idle policy and repeat measurements.

Do not conclude "DNS isn't updating" just because requests still hit stub A; the Gateway may be reusing pooled TCP connections to A. Never forcefully kill all production Gateway connections to "flush DNS" without considering latency spikes and reconnect storms.

### Negative Caching and Recovery

A transient DNS failure can be cached (NXDOMAIN or error per resolver rules). Once the DNS record is fixed, some instances may keep failing until negative-cache TTL expires. During an incident, separate:

- When authoritative DNS received the new record.
- What recursive resolver caches are returning.
- What in-process JVM/Netty resolvers are holding.
- Which IPs existing pooled connections target.

Updating a DNS record does not mean every JVM instance switches to the new IP immediately.

## 7. TCP Connect: One RTT Is Not the Whole Story

TCP establishes a connection before standard HTTP/TLS data flows. For a fresh TCP connection, the **three-way handshake** is:

~~~mermaid
sequenceDiagram
    participant G as Gateway HTTP client
    participant U as Upstream TCP server
    G->>U: SYN
    U-->>G: SYN-ACK
    G->>U: ACK
    Note over G,U: TCP connection established
~~~

Under ideal conditions, the handshake takes roughly **one RTT** before TLS/HTTP bytes start flowing. This is an approximation, not a guarantee: kernel scheduling, listen backlogs, SYN retransmits, packet loss, multi-IP resolution attempts, NATs, proxies, and cross-region distance all add delay.

### Factors That Slow Down Connects

| Cause | Symptom | Where to investigate |
| --- | --- | --- |
| **High geographic RTT** | Both connect and TLS rise on new connections | Check zone/region placement and network path |
| **Packet loss / retransmissions** | Connect p99 spikes sharply while p50 stays normal | TCP retransmission metrics, network telemetry |
| **No listener** | Fast connection refused | Service port, readiness, LB target |
| **Firewall / security group drop** | Long connect timeouts | NetworkPolicy/firewalls; test permitted path |
| **Exhausted SYN backlog or accept queue** | Connection setup slows or fails | Server accept metrics, backlog/drop counters |
| **Slow NAT / sidecar / proxy** | Slow only across a specific network path | Compare direct vs. via-proxy in lab |
| **IPv6/IPv4 fallback** | Occasional very slow attempts | Client resolver / Happy Eyeballs behavior |
| **Full connection pool** | Requests wait while TCP connect counts stay flat | Pool acquire duration and pending queue |

**Pool acquire timeout is not TCP connect timeout.** When `max-connections` is exhausted, requests queue **before** any TCP attempt occurs. Raising connect timeout will not cure pool saturation; raising `maxConnections` blindly can push overload onto the backend.

### Connect Timeout vs. Response Timeout

- **Connect timeout:** bounds establishing the TCP connection to an address per the HTTP client API.
- **DNS resolution timeout:** may be a separate resolver limit not automatically covered by connect timeout in every implementation.
- **Pool pending acquire timeout:** bounds waiting for a connection slot from the pool.
- **TLS handshake timeout:** may be configured separately; distinct from TCP connect timeout.
- **Response/read timeout:** bounds waiting to read the HTTP response afterward, with client-defined semantics.
- **Overall operation deadline:** bounds total request lifetime across retries, discovery, HTTP, and serialization.

Therefore, **setting a 500 ms connect timeout does not mean "every Gateway request finishes within 500 ms."** An operation can spend time in DNS, pool waits, TLS, backend processing, and response transfer before hitting an overall deadline.

## 8. TLS Handshake: Connection Security Latency, Not Just Encryption CPU

TLS protects confidentiality and integrity for HTTPS connections. When opening **a new TLS connection**, both peers negotiate protocol/ciphers, validate certificates, and derive session keys before exchanging HTTP application data.

### Conceptual TLS 1.2 vs. TLS 1.3 Handshakes

| Characteristic | TLS 1.2 full handshake (typical model) | TLS 1.3 full handshake (typical model) |
| --- | --- | --- |
| TLS handshake RTTs before app data | Typically ~**2 RTT** | Typically ~**1 RTT** |
| Runs atop TCP | Still needs standard TCP connect | Still needs standard TCP connect |
| Resumption | Uses TLS 1.2 session resumption mechanisms | Uses PSK/session tickets and resumption |
| Certificate verification | Must verify peer identity/trust | Must verify peer identity/trust |
| mTLS | Can require a client certificate | Can require a client certificate |
| 0-RTT | Not available via TLS 1.3 early data | Optional early data if enabled/supported, with replay risk |

These RTT counts are **protocol-level comparison baselines**, not guaranteed measurements. DNS, TCP connect, queueing, certificate-verification CPU, TLS stacks, ticket/key rotation, packet loss, configured OCSP/revocation checks, and proxy hops all affect actual timings.

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant U as HTTPS upstream
    Note over G,U: TCP connection established
    G->>U: ClientHello (SNI, ALPN, TLS parameters)
    U-->>G: ServerHello, certificates, handshake messages
    Note over G,U: Validate chain, hostname, keys; complete handshake
    G->>U: HTTP request over encrypted channel
    U-->>G: HTTP response over encrypted channel
~~~

### Separating TLS CPU Cost from TLS Network Cost

A TLS handshake spends:

1. **RTT** exchanging handshake messages.
2. **CPU** running cryptography, certificate chain verification, and signing/verifying signatures.
3. **Certificate/config checks** such as CA trust, hostname/SAN, SNI, and client certs for mTLS.
4. **Transport waits** from packet loss, congestion, server overload, or proxy negotiation.

If TLS p95 spikes while RTT stays flat, inspect CPU, handshake concurrency, and certificate verification. If both TCP connect and TLS climb alongside cross-zone RTT, **service placement and network path** matter far more than switching ciphers. Tweaking ciphers without checking security policy or client compatibility can weaken security.

### Two TLS Hops Do Not Share One Session

~~~text
Browser --TLS A--> Public ingress --HTTP/TLS B--> Gateway
Gateway --TLS C--> Catalog
~~~

Sessions, certificates, truststores, and connection pools are **separate**. TLS session resumption between Browser and ingress **does not shorten** a fresh TLS handshake between Gateway and Catalog. If a service mesh sidecar sits in the path, it may add an mTLS hop or move TLS termination; draw the **real topology** before doing math.

### SNI, ALPN, and TLS Errors

**SNI** lets the server choose the right certificate for the target hostname. **ALPN** negotiates the application protocol—such as HTTP/1.1 or HTTP/2—when supported by both peers. Misconfigured SNI/hostnames trigger certificate mismatches; unexpected ALPN results can make the HTTP client choose a different connection/stream model.

In performance tests, **never pass `-k`/`--insecure` to curl, use trust-all SSL contexts, or disable hostname verification** just to get lower numbers. A run that looks faster because peer verification was skipped **no longer upholds the same security contract** and is not a valid optimization.

## 9. mTLS, Session Resumption, and 0-RTT: Performance Must Preserve Security

### Mutual TLS

With **mTLS**, the upstream also authenticates the Gateway's client certificate. That adds handshake checks and identity management, yet must never be stripped out just to shave a few milliseconds when service-to-service security requires it.

What to measure:

- TLS handshake success/failure rates and durations.
- Certificate chain and trust validation on both sides.
- Certificate rotation, expiration, and session resumption behavior.
- Backend TLS accept/handshake concurrency under bursts.
- Truststore/keystore/SNI errors kept distinct from TCP errors.

Never write private keys or client certificates into logs, traces, or latency reports. Use separate test certificates from production and verify **real** hostnames and certificates without bypassing checks.

### Session Resumption Is Not Connection Reuse

Two distinct mechanisms:

| Mechanism | How it works | Remaining cost |
| --- | --- | --- |
| **Connection reuse / keep-alive** | Reuses the exact same already-open TCP+TLS socket | Zero new TCP or TLS handshake on reused requests |
| **TLS session resumption** | Opens a new connection while reusing valid session state/PSK | Still pays TCP connect and partial TLS negotiation |

For routes serving many short GETs, **reusing existing connections** typically saves far more than optimizing fresh full handshakes. Resumption helps when reconnecting is unavoidable, though real gains depend on TLS version, ticket lifetimes, client/server support, and security policies.

### 0-RTT Is Not a Harmless Speed Button

TLS 1.3 early data (**0-RTT**) exists in some stacks, yet carries **replay risk**. Never send order/payment POSTs or state-mutating requests in 0-RTT without dedicated idempotency and replay protections. Gateway HTTP clients and backends may not support or enable early data by default; **never assume "TLS 1.3 == every HTTP request skips a handshake RTT."**

### Ingress TLS Termination Can Hide Outbound Latency

If `curl` from a laptop reports an 18 ms handshake to `api.example.test`, that normally measures **laptop → CDN/ingress TLS**, while Gateway → Catalog may have an independent 35 ms handshake. To see which hop is slow, measure from the **Gateway outbound HTTP client** or inside that network segment.

## 10. HTTP Keep-Alive, Connection Reuse, and HTTP/2 Multiplexing

With HTTP/1.1, sequential requests can reuse a **persistent TCP connection** when both sides allow keep-alive and pooling keeps it valid. With HTTP/2, one connection can carry **multiple concurrent streams**, reducing TCP+TLS connection counts to the same origin subject to stream limits and implementation.

~~~mermaid
flowchart TD
    A["Many inbound requests"] --> P["Gateway outbound pool"]
    P --> H1["HTTP/1.1 connection A"]
    P --> H2["HTTP/1.1 connection B"]
    P --> H3["HTTP/2 connection with multiple streams"]
    H1 --> U["Catalog"]
    H2 --> U
    H3 --> U
~~~

| Model | Benefits | Limits |
| --- | --- | --- |
| New connection per request | Simple cold-path baseline | Repeated DNS/TCP/TLS, high CPU and latency |
| HTTP/1.1 keep-alive + pool | Cuts connects/handshakes; spreads requests across sockets | Idle timeouts, stale sockets, pool waits |
| HTTP/2 multiplexing | Multiple streams per socket; fewer handshakes in some workloads | `MAX_CONCURRENT_STREAMS`, TCP head-of-line blocking under loss |
| HTTP/2 multiple connections | Expands capacity beyond single-socket stream caps | Added connect/TLS, memory/socket overhead |
| HTTP/3 / QUIC | Differs from TCP/TLS-over-TCP; separate handshake model | Applies only when infra and both peers truly support it |

**Never assume Gateway Server WebFlux or Web MVC automatically uses outbound HTTP/2 on every route.** Verify protocol negotiation, client configuration, ALPN, and backend support. HTTP/3 must not be modeled with TCP three-way handshake + TLS-over-TCP formulas; it is a **different transport** outside the HTTP/1.1/TLS-over-TCP examples in this lesson.

### Keep-Alive and Stale Connections

If a backend or LB closes connections after 30 seconds idle while the Gateway pool retains them longer, the next request reusing that socket can hit connection reset / broken pipe. Retrying safe GETs can recover the request afterward, yet raises tail latency and outbound attempts. Align pool **max idle time** below upstream/LB timeouts and track:

- New vs. reused connections.
- Idle connection evictions.
- Connection resets on reuse.
- Retry attempts after stale connection errors.
- Active/pending pool queues and connection lifetimes.

**Never set idle timeout to 0 or infinity just to maximize reuse**; infinite idle keeps stale sockets and misses DNS rotations. Balance reuse, failover, and resource limits using measurements.

## 11. Connection Pools: Don't Mistake Pool Waits for Slow TLS

When many concurrent requests call Catalog, the **outbound connection pool** enables reuse while remaining a finite resource. When every connection is busy or stream caps are reached, new requests wait.

~~~mermaid
flowchart TD
    R["New outbound request"] --> P{"Suitable connection in pool?"}
    P -->|Yes, capacity free| U["Reuse connection / HTTP/2 stream"]
    P -->|No| W{"Can open a new connection?"}
    W -->|Yes| H["Resolve / TCP / TLS"]
    W -->|At limit| Q["Pending acquire queue"]
    Q --> T{"Capacity freed before timeout?"}
    T -->|Yes| U
    T -->|No| E["Acquire timeout / fail-fast"]
    U --> S["Send HTTP request"]
    H --> S
~~~

### Key Parameters and Metrics

| Group | Meaning | Signs of misconfiguration |
| --- | --- | --- |
| **max connections** | Cap on TCP connections the pool maintains within its scope | Setting too high overloads backends and burns TLS/FD/memory |
| **pending acquire limit** | Max waiters allowed for a connection | Huge queues inflate p99 and memory |
| **pending acquire timeout** | Max wait time for pool capacity | Acquire timeouts rise even when DNS/TCP/TLS are fast |
| **max idle time** | Idle lifetime limit for pooled connections | Too long: stale sockets; too short: reconnect churn |
| **max life time** | Max total connection age per policy even when active/reused | Too short: continuous fresh handshakes |
| **active / idle / pending** | Pool state over time | Pending rises while active sits at cap |
| **new connections/s** | Connection churn rate | High at steady QPS points to short idle, resets, or misconfig |
| **connection utilization / HTTP/2 streams** | Real concurrency over TCP sockets | Stream saturation despite low TCP socket count |

Look beyond Gateway CPU. An HTTP client **waiting on the pool** drops throughput while CPU stays low; raising `maxConnections` helps only if the backend has capacity, otherwise it **overloads the downstream** and multiplies timeouts and retries.

### Standalone Reactor Netty HTTP Client Experiment Snippet

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

ConnectionProvider provider = ConnectionProvider.builder("catalog-lab")
        .maxConnections(100)
        .pendingAcquireMaxCount(200)
        .pendingAcquireTimeout(Duration.ofMillis(500))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .build();

HttpClient labClient = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1000)
        .responseTimeout(Duration.ofSeconds(3));

// labClient is used inside a standalone HTTP client benchmark/test.
// Dispose the provider only when the fixture or app shuts down.
~~~

This is a **standalone Reactor Netty `HttpClient` snippet**, not a bean Gateway automatically picks up. Never assume Gateway Server WebFlux routes use `HttpClient.create(provider)` just because `labClient` exists in a class. To customize the Gateway's outbound client, use the **appropriate `HttpClientCustomizer`, configuration properties, or version-supported extension point** and verify wiring via metrics and tests.

Additionally:

- `responseTimeout` is not an overall deadline across multiple retries.
- `CONNECT_TIMEOUT_MILLIS` covers TCP connect, not full DNS, pool wait, or TLS.
- Pools can partition by destination/proxy/protocol; interpret "max 100" per your implementation's actual scope.
- Manage lifecycle cleanly on shutdown; never call `dispose()` on a global provider still serving live requests.

## 12. Multi-Layer Instrumentation: HTTP Metrics, Pools, Tracing, and Network

To prove DNS/TLS/connect causes latency, you need **fine-grained measurements**. An `http.server.requests` or Gateway route timer usually reports only **total inbound handling**, without separating DNS, TCP, and TLS.

### Recommended Measurement Layers

| Layer | Metrics needed | Limitations |
| --- | --- | --- |
| Client / browser | Client-side DNS, connect, TLS, TTFB, total | Measures to public edge, blind to Gateway outbound |
| Gateway server | Inbound request count, duration/status, route ID | Auth/handler errors can reject before routes |
| Gateway route / filter | Route match, filter execution, fallback/retry outcome | Covers only requests entering the filter chain |
| Outbound HTTP client | Pool acquire, new/reused sockets, connect time, TLS handshake time, response time | Exact metric/hook names vary by Reactor Netty/client version |
| DNS resolver | Cache hits/misses, queries, duration, negative answers, timeouts | Available only if client/resolver exposes or instruments it |
| Service discovery | Instance lookup, cache refresh, no-instance | **Not DNS duration** |
| Backend | Accept/handshake, request duration, status | Blind to Gateway-side DNS/TCP unless measured |
| OS / network | TCP RTT, retransmissions, socket states, packet loss | Usually requires host/agent privileges and process filtering |

### Never Guess Metric Names Before Checking Your Version

Meter names and tags across Reactor Netty/Micrometer, Spring Boot Actuator, and Spring Cloud Gateway evolve across releases and configs. Several client metrics require **explicit opt-in** or `ConnectionProvider` flags. Instead of hardcoding `reactor.netty.http.client.*` assuming every version exports it:

1. Check exact Spring Boot, Spring Cloud Gateway, Reactor Netty, and Micrometer versions.
2. Inspect what Actuator/Prometheus actually exports in your **test environment**.
3. Check release-specific docs for exact meter names and tags.
4. Confirm **units** (s vs. ms), histogram buckets, and route/destination tags.
5. Trigger one **cold** request and one **reused** request and watch the counters change.

Never expose all Actuator endpoints to the public Internet just to read metrics. Use secured management endpoints, dedicated roles/scopes, and network isolation.

### Avoid High-Cardinality Metric Labels

Useful bounded labels include finite `routeId`, managed `upstreamService`, `outcome`, `protocol`, and `connectionReused` if exported. **Never put raw URLs, query strings, user IDs, client IPs, or JWTs into metric labels**, which explode time series and leak sensitive data.

For load-balanced targets, keep stable `serviceId` distinct from dynamic/sensitive `instanceAddress`. Expose per-address telemetry only in restricted diagnostic views when genuinely required.

### Distributed Tracing Should Break Down One Inbound Request

~~~text
Trace R-42:
  [Inbound Gateway HTTP: total 100 ms]
    [Security + route/filter: 6 ms]
    [Service discovery selection: 4 ms]
    [Outbound attempt #1: 76 ms]
      [Pool acquire: 2 ms]
      [DNS: 8 ms]
      [TCP connect: 20 ms]
      [TLS handshake: 30 ms]
      [HTTP request/first byte/transfer: 16 ms]
    [Response/other: 14 ms]
~~~

These numbers are **illustrative**, and child spans only appear if actually instrumented. Default HTTP spans often wrap the entire outbound call **without separate DNS/TLS child spans**. Obtaining phase granularity requires appropriate HTTP client/transport hooks or tracing instrumentation.

One connection can serve **many inbound requests**; DNS/connect/TLS for a pre-opened socket occurred **outside** the measured request's lifetime. Attributing full connection setup to reused requests distorts math. Track **per-connection events** alongside **per-request latency**.

## 13. Curl: Reading DNS, TCP, TLS, TTFB, and Total Time Correctly

`curl --write-out` is a convenient starting point for **client → Gateway/ingress**. It reports cumulative timestamps from the start of the curl transfer, not standalone phase durations.

### One HTTPS Request from an Authorized Test Environment

~~~bash
curl --http1.1 --noproxy '*' \
  --connect-timeout 2 --max-time 10 \
  --silent --show-error --output /dev/null \
  --write-out 'dns_end=%{time_namelookup} tcp_end=%{time_connect} tls_end=%{time_appconnect} pretransfer=%{time_pretransfer} first_byte=%{time_starttransfer} total=%{time_total} new_connections=%{num_connects} remote_ip=%{remote_ip}\n' \
  'https://gateway.lab.example.test/api/catalog/items/42'
~~~

**This is an illustrative command, not a live run.** Target only authorized lab domains or URLs. `--noproxy '*'` explicitly bypasses environment HTTP proxies; if you intend to **measure through a real proxy**, omit that flag and document the proxy topology. On Windows PowerShell 5.1, invoke `curl.exe` instead of the `curl` alias (which maps to `Invoke-WebRequest`).

### Interpreting `write-out` Fields

| `curl` field | Conceptual meaning |
| --- | --- |
| `time_namelookup` | Timestamp when initial name resolution finished |
| `time_connect` | Timestamp when connection to the initial remote peer completed |
| `time_appconnect` | Timestamp when TLS/SSL or app-layer handshake completed (when applicable) |
| `time_pretransfer` | Timestamp when ready to begin application data transfer |
| `time_starttransfer` | Timestamp when the first response byte arrived (includes server, proxy, backend) |
| `time_total` | Full transfer duration until completion per curl |
| `num_connects` | Number of new connections curl opened for this transfer |
| `remote_ip` | Remote IP address seen by curl on the client side |

For a **fresh HTTPS request without redirects or complex HTTP proxies**, you can estimate:

\[
\begin{aligned}
T_{\text{DNS}} &\approx t_{\text{namelookup}}\\
T_{\text{TCP}} &\approx t_{\text{connect}}-t_{\text{namelookup}}\\
T_{\text{TLS}} &\approx t_{\text{appconnect}}-t_{\text{connect}}\\
T_{\text{first-byte-after-ready}} &\approx t_{\text{starttransfer}}-t_{\text{pretransfer}}\\
T_{\text{body-after-first-byte}} &\approx t_{\text{total}}-t_{\text{starttransfer}}
\end{aligned}
\]

These are **estimates from cumulative timestamps**; phases depend on protocol, proxies, reuse, and curl's exact timing rules. For plain HTTP without TLS, `time_appconnect` can be 0, making TLS subtraction meaningless. With connection reuse, `num_connects` may be 0 and handshake timestamps do not reflect cold paths. Never call `time_starttransfer - time_pretransfer` pure "backend time": it includes Gateway routing, network, queues, and upstream wait.

### Two Requests in One Curl Process to Observe Reuse

~~~bash
curl --http1.1 --silent --show-error --output /dev/null \
  --write-out 'first new=%{num_connects} dns=%{time_namelookup} tcp=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' \
  'https://gateway.lab.example.test/api/catalog/items/42' \
  --next \
  --http1.1 --silent --show-error --output /dev/null \
  --write-out 'second new=%{num_connects} dns=%{time_namelookup} tcp=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' \
  'https://gateway.lab.example.test/api/catalog/items/42'
~~~

Both transfers share one curl process, giving **the opportunity** to reuse the connection if keep-alive is permitted and valid. **Never assume** the second request definitely reused it: check `num_connects` and actual numbers. Running `curl` as **two separate processes** fails to model long-lived HTTP client pool reuse.

### One Curl Command Cannot Measure Gateway Outbound Internals

When calling `https://gateway.lab.example.test` from a laptop, `time_appconnect` normally measures TLS to the **public ingress or Gateway peer curl connected to**—**not** TLS between the Gateway and Catalog. If curl shows `total = 150 ms`, you need Gateway outbound metrics/traces to know how much came from backend DNS/TCP/TLS rather than guessing from one end-to-end number.

## 14. Auxiliary Measurements: DNS, TLS Certs, and Network Path

### DNS Answers

~~~bash
dig +noall +answer gateway.lab.example.test A
dig +noall +answer gateway.lab.example.test AAAA
~~~

To separate public DNS resolution from connect/TLS in a **controlled lab**, `curl --resolve` maps a hostname to a test IP while preserving the hostname for HTTP `Host` and SNI:

~~~bash
curl --resolve gateway.lab.example.test:443:127.0.0.1 \
  --silent --show-error --output /dev/null \
  --write-out 'dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' \
  'https://gateway.lab.example.test/api/catalog/items/42'
~~~

This command **only works when an HTTPS listener actually runs on `127.0.0.1:443`** with a valid certificate for `gateway.lab.example.test`; it does **not** suggest bypassing TLS verification. `--resolve` skips curl's DNS lookup, **does not alter the Gateway's internal DNS resolver/cache**, and can alter the network path if the IP differs from the real endpoint. Comparing `--resolve` against normal calls is therefore a **conditional experiment**, not absolute proof of production DNS latency.

### Verifying the TLS Peer Without Disabling Security

~~~bash
openssl s_client \
  -connect gateway.lab.example.test:443 \
  -servername gateway.lab.example.test \
  -verify_return_error -brief
~~~

`openssl s_client` verifies protocol, certificate, and trust handshakes against the **connected peer**; it is not a throughput benchmark, does not replace the application's HTTP client, and does not measure Gateway → backend TLS when run from a laptop against public ingress. When mTLS is required, supply an authorized test client identity cleanly; never paste private keys into logs or chats.

### Network RTT and TCP Retransmissions

Tools like `ping`, `mtr`, `traceroute`, or TCP socket telemetry help map network paths, RTT, and packet loss when authorized. Keep in mind:

- ICMP RTT does not equal TCP/TLS handshake duration.
- Network policies may block ICMP while HTTPS works normally.
- Tools run outside the Gateway Pod/namespace/egress policy may traverse different paths.
- Packet captures can contain sensitive payloads; run only under approved permissions and retention policies.

**Always tag measurements with their source** (client laptop, Gateway Pod, sidecar, backend) and protocol/port—never lump everything into one "network latency" column.

## 15. Controlled Experiment Design: Cold vs. Warm Connections

A useful benchmark holds everything outside the test constant and intentionally varies **only one variable**.

### Groups to Compare

| Group | DNS cache | Outbound connection | Purpose |
| --- | --- | --- | --- |
| A — Cold path | Potential cache miss | Opens new connection | Full connection setup cost in that environment |
| B — Warm pool | Potential cache hit | Reuses connection | Steady-state latency |
| C — New connection, cached DNS | Cache hit / address known | Opens new connection | Estimates TCP + TLS without confounding DNS queries |
| D — New connection, TLS resumed (if available) | Valid DNS | New connection with TLS resumption | Isolates resumption benefit |

**Challenge:** DNS cache hits/misses and TLS resumption **cannot be guaranteed simply by calling a URL twice**. You need hooks/counters confirming each group actually experienced those conditions; otherwise label them **observed first-request vs. steady-state** rather than claiming confirmed cold DNS/TLS.

### Basic Lab Procedure

1. Lock **Spring Boot / Gateway / Reactor Netty versions**, Java runtime, hostnames, HTTP version, and topology.
2. Run a Catalog stub with a **small, fixed, DB-free response**; enable HTTPS with a test CA if measuring TLS.
3. Place Gateway and stub on hosts/containers/networks with known specs; record zones.
4. Configure the route/static URI and monitor pool active/idle/pending, new connection counts, DNS queries, and TLS handshakes.
5. Run **warm-up**, then capture the steady-state latency distribution—never just the single fastest request.
6. Produce the cold-path group via a **controlled test mechanism**: a fresh HTTP client/pool or dedicated Gateway test fixture. Never wipe active production Gateway connection pools.
7. Repeat each group enough times, recording request counts, errors, p50/p95/p99, mean, min/max, and duration.
8. Check the **backend request journal** to ensure no hidden retries or redirects added attempts.
9. Compare `curl` client→Gateway against Gateway outbound metrics without adding or relabeling phases.
10. Conclude from **meaningful improvements and configuration risks**, not p50 alone.

### Factors That Must Stay Fixed

- Identical endpoint, method, headers, body, and response payload size.
- Identical TLS protocol/ALPN when testing another variable.
- Identical replica counts, CPU limits, GC pressure, and concurrency.
- Identical service discovery route/instance selection, or record which instance was picked.
- No hidden retries or redirects unless explicitly under test.
- No HTTP/CDN/browser caches making backend hits drop to zero and masquerading as fast backends.
- Never mix runs through public ingress with direct-to-Gateway runs under the same baseline.

### Stress-Testing Warning

Never run an overwhelming load test just to inspect TLS. Creating thousands of fresh connections per second can trigger TLS CPU spikes, exhaust file descriptors, and disrupt neighboring services. Every load test needs an **isolated environment, stop thresholds, bounded duration, and operator approval**.

## 16. Spring Cloud Gateway Server WebFlux: Observing via `GlobalFilter` and HTTP Client

In Gateway Server WebFlux, requests pass through route predicates, the `GlobalFilter`/`GatewayFilter` chain, and the outbound routing filter. When evaluating TLS/DNS/connect, distinguish:

- **Gateway route elapsed time:** duration from filter subscription until the downstream reactive chain completes/errors/cancels at that filter's order.
- **Outbound HTTP attempt time:** duration from when the HTTP client begins an attempt until response/error; may include pool, DNS, TCP, and TLS.
- **Transport phase timings:** pool acquire, DNS, TCP connect, and TLS handshake recorded by the HTTP client/resolver.
- **Backend server processing time:** time spent in the target service after arrival; excludes Gateway DNS/connect.

### 16.1. A `GlobalFilter` Measures Route Elapsed Time, Not TLS Time

Small instrumentation example using **Spring Cloud Gateway Server WebFlux** and Micrometer:

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public final class RouteElapsedGlobalFilter implements GlobalFilter, Ordered {

    private final MeterRegistry meters;

    public RouteElapsedGlobalFilter(MeterRegistry meters) {
        this.meters = meters;
    }

    @Override
    public int getOrder() {
        return -1000;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain
    ) {
        return Mono.defer(() -> {
            long startedNanos = System.nanoTime();

            return chain.filter(exchange)
                    .doFinally(signal -> {
                        Route route = exchange.getAttribute(
                                ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR);
                        String routeId = route == null
                                ? "unknown" : route.getId();

                        meters.timer(
                                "demo.gateway.route.elapsed",
                                "route", routeId,
                                "terminal", signal.name()
                        ).record(
                                System.nanoTime() - startedNanos,
                                TimeUnit.NANOSECONDS);
                    });
        });
    }
}
~~~

**How to interpret this correctly:**

1. `Mono.defer` captures start time **at subscription**, rather than when assembling the `Publisher`.
2. `doFinally` captures the terminal signal (`complete`, `error`, or `cancel`); cancellations can come from clients or subscription scopes.
3. `routeId` comes from app-managed routes; the meter uses bounded tags and **never raw paths or JWTs**.
4. The filter runs only for requests entering the **Gateway filter chain**; 401/403 blocked by Spring Security or unmatched 404s may bypass it.
5. The timer spans the **downstream lifecycle from this filter's position**. With retries, resubscriptions, or different filter ordering, counts can shift; never assume one timer sample equals one TCP attempt.
6. This timer **does not distinguish DNS, TCP, and TLS**. Proving TLS is slow requires transport-level HTTP client metrics or traces.
7. Even when the reactive chain completes, that does not guarantee the client received every body byte, especially under streaming cancellations or transport errors.

This snippet requires a configured Micrometer `MeterRegistry`; the code itself is not evidence of a run. At high traffic, check meter lookup cost and cardinality; use framework built-in metrics instead of stacking redundant timers when equivalent telemetry already exists.

### 16.2. Transport Instrumentation for Reactor Netty

To observe outbound connections in Reactor Netty, use the telemetry capabilities supported by your **actual Reactor Netty version**:

| Measurement point | Expected on new connection | Expected on reuse |
| --- | --- | --- |
| Pool acquire | May wait | Quickly leases idle/available connection |
| Address resolution | Only if resolver/cache lacks a valid entry | Usually skipped |
| TCP connect | One connect attempt | No new TCP connect |
| TLS handshake | Handshake runs if new HTTPS | No new handshake on same socket |
| HTTP request/response | Always runs per sent request | Always runs |

In Netty, distinguish **channel connected**, **TLS handshake completed**, and **HTTP response received**. The gap between two callbacks is not purely TLS duration if queueing or handlers sit between them; use **TLS handshake events and SSL handler timestamps** where supported by your version/instrumentation rather than guessing from `"connection established"` logs.

**Never enable Netty wiretap in production** to measure timings: wiretap can dump raw HTTP headers and bodies—including `Authorization`, cookies, and personal data—alongside heavy overhead. Prefer safe metrics/observability hooks, restricting packet captures or wire logging to sanitized lab setups.

### 16.3. Version-Specific Connect/Response Timeout Configuration

Several Gateway Server WebFlux releases support properties shaped like:

~~~yaml
# Illustrative for Gateway Server WebFlux releases supporting this namespace.
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 1000
            response-timeout: 5s
~~~

In older releases, these live under `spring.cloud.gateway.httpclient.*`. Check **configuration metadata matching your actual dependency**, the unit of `connect-timeout` (commonly milliseconds), and how `response-timeout` parses `Duration`. Never assume writing a property into YAML means it bound and controls the active client.

Even when bound properly:

- Connect timeout **does not bound** pool acquire or DNS resolution in all implementations.
- Response timeout **does not equal** overall request timeout across TLS, retries, and body transfer.
- TLS handshake timeouts and pool lifetimes may require separate APIs or properties.
- Route-specific timeouts or filter overrides can alter behavior on individual routes.

Write negative tests proving connect refused, DNS timeout, TLS failure, pool exhaustion, and slow backend responses respect your **overall deadline**.

## 17. Gateway Server Web MVC: Measure Servlet Container and Outbound HTTP Client Separately

In **Gateway Server Web MVC**, the app runs on a **Servlet container / Spring MVC / WebMvc.fn**. Its outbound HTTP client is not Gateway Server WebFlux's Reactor Netty client by default; therefore:

- **Servlet request threads / busy threads** and inbound connector pools impact total latency.
- Gateway MVC's outbound HTTP client/request factory has **its own connection pooling, DNS resolver, TLS/HTTP stack, and metrics**.
- A WebFlux reactive `GlobalFilter` or `Mono.defer` **does not apply directly** to Server MVC.
- `spring.cloud.gateway.server.webflux.httpclient.*` settings do not configure the MVC HTTP client.

### Measure Both Sides Properly Under Servlet

| Side | What to measure | Approach |
| --- | --- | --- |
| Inbound client → Gateway MVC | HTTP connect, TLS, request-to-response total | JDK `HttpClient`/curl against real Servlet port |
| Inside Servlet | `HandlerMapping`, `SecurityFilterChain`, filters, busy threads | Spring MVC/Servlet metrics and tracing |
| Outbound Gateway MVC → Catalog | Pool wait, DNS, TCP/TLS, response read | Instrument the **actual HTTP client/request factory in use** |
| Catalog backend | Server handling time/status and accept backlog | Backend instrumentation |

`MockMvc` is great for route/security tests yet **opens no inbound TCP socket**, so it cannot measure real client→Gateway DNS or TLS. For HTTP integration tests, use `@SpringBootTest(RANDOM_PORT)` with a real HTTP client hitting the live port and an HTTP/HTTPS backend stub.

### Slow Servlet Threads Can Make You Blame TLS by Mistake

If the backend responds quickly yet Servlet worker threads are tied up by blocking calls, total latency rises due to **request-processing waits** while actual TLS handshake duration stays flat. Measure active/busy threads, request queues, and the outbound client pool together. Java virtual threads (when supported by Boot/JDK) reduce blocking-I/O thread stalls, yet **never eliminate network RTT, TCP pool limits, or backend capacity constraints**.

### Proxy Exchange Is Another Path

A **Proxy Exchange MVC** application using `ProxyExchange<T>` inside a controller also spans two hops, yet does not inherit Gateway Server WebFlux filter or client properties. If your team operates multiple Gateway variants, state the exact **server/proxyexchange variant**, **MVC/WebFlux stack**, HTTP client implementation, and version in every report to avoid invalid comparisons.

## 18. Java HTTP Client: Measuring Warm-Up and Reuse for the Right Goal

To verify user-facing latency against a real Gateway, you can use **JDK `HttpClient`** on Java 17+ in a test. Its purpose is **measuring total HTTP request duration** and observing client-side reuse—**never** claim this snippet alone isolates DNS, TCP, and TLS.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class GatewayWarmConnectionProbe {

    public static void main(String[] args) throws Exception {
        // Use only an authorized lab endpoint returning a small fixed body.
        URI endpoint = URI.create(
                "https://gateway.lab.example.test/api/catalog/health");

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(2))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        List<Long> samplesMs = new ArrayList<>();

        for (int i = 0; i < 20; i++) {
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            long started = System.nanoTime();
            HttpResponse<Void> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.discarding());
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected status: " + response.statusCode());
            }

            // First sample reveals cold-start effects; do not assume DNS is cold.
            samplesMs.add(elapsedMs);
            System.out.println("sample=" + i + " totalMs=" + elapsedMs);
        }

        Collections.sort(samplesMs);
        System.out.println("minMs=" + samplesMs.get(0)
                + " maxMs=" + samplesMs.get(samplesMs.size() - 1));
    }
}
~~~

**Limitations of this example:**

1. Sharing one `HttpClient` **enables** connection reuse, yet whether each call reuses a socket depends on keep-alive, server behavior, network state, and client internals.
2. `System.nanoTime()` measures all of `send()` through `BodyHandlers.discarding()`, without separating TLS/DNS.
3. `min`/`max` do not replace p50/p95/p99. With only 20 samples, **draw no strong statistical conclusions about p99**.
4. The first request **is not guaranteed DNS-cold** due to OS caches, recursive resolvers, or HTTP client TLS session caches.
5. JDK `HttpClient` uses the test environment's truststore: the HTTPS listener needs a valid certificate—**never disable verification**.
6. If testing through an ingress proxy, preserve real routes and proxy settings; this `HttpClient` forces HTTP/1.1 even if production clients use HTTP/2.
7. Never run this against unauthorized hosts; even 20 calls—or many threads if scaled up—can affect a live Catalog backend.

To explain **why** the first sample took longer, pair this with server/Netty HTTP client telemetry: new connections, pool waits, DNS queries, TCP/TLS handshakes, and backend response times. Never call every first-call difference "TLS warm-up."

## 19. Bursts, Retries, and Multiple Upstreams Multiply Handshakes

One inbound request can trigger **multiple outbound attempts**, especially when the Gateway uses `Retry` or a controller fans out across services.

### Count Attempts Before Blaming Handshakes

~~~mermaid
flowchart TD
    I["1 inbound request"] --> A["Outbound attempt 1 to Catalog A"]
    A --> X{"Response / exception?"}
    X -->|Retryable error| B["Outbound attempt 2 to Catalog B"]
    X -->|Success| C["Response"]
    B --> C
    A -. "New TCP/TLS if missing from pool" .-> N["Connection events"]
    B -. "May trigger another new TCP/TLS" .-> N
~~~

If each retry picks a different instance, the pool may lack a cached socket and perform a fresh **DNS/TCP/TLS** sequence. One backend failure can simultaneously drive up:

- Outbound attempts per user request.
- New connections and TLS handshakes/sec.
- Pool acquire latency and queue depth.
- TLS CPU on both Gateway and backends.
- Client-visible p99 latency even when individual backend attempts are short.

**Never use unbounded retries to make "200 rates" look prettier.** Cap attempts, backoff, jitter, and overall deadlines; retry only methods and failures safe under your idempotency contract. A payment/order POST may already have committed at the backend even when the socket errored, so never auto-retry without an idempotency key and deduplication.

### Circuit Breakers and Bulkheads

- An **OPEN circuit breaker** blocks outbound calls, reducing TCP/TLS handshakes because connections are not attempted.
- A **bulkhead / concurrency limit** caps simultaneous backend calls, protecting pools and threads while increasing rejected requests under overload.
- **Rate limiting** blocks excess inbound traffic before routes fire outbound HTTP calls, though it does not speed up connect/TLS for permitted calls.

When measuring, place **inbound request count, outbound attempt count, new connections, handshake count, and fallback count side by side**. If clients see HTTP 200 via fallback while Catalog receives zero requests, never report that as "TLS latency improved."

### Cross-Region Routing and Service Placement

A service in another region incurs higher RTT, making fresh TCP connects and TLS handshakes costlier. Moving backends into the same zone/region carries different operational costs and resilience trade-offs. Evaluate **latency, availability, data residency, failover, and security boundaries** together rather than optimizing RTT in isolation.

## 20. Symptom-Based Diagnosis: DNS, TCP, TLS, or Pool?

A single "p99 rose" symptom has many causes. Classify by **which phase shows slowness or errors**.

| Symptom | Plausible hypothesis | Priority check/measurement |
| --- | --- | --- |
| Cold requests slow, warm requests fast | DNS/TCP/TLS setup or cold app/JIT | New/reused connection counts, per-phase timing, JIT warm-up |
| DNS lookup p95 rises | Slow resolver, cache misses, CNAME/AAAA, timeouts | Resolver queries/timeouts, DNS cache events |
| DNS NXDOMAIN after deploy | Wrong service name/namespace or negative cache | DNS lookup inside exact namespace and process behavior |
| DNS returns new IP, traffic still hits old IP | Pool holds older open connections | Remote IP of active sockets, idle/lifetime policies |
| High pool pending requests | Insufficient connection/stream capacity or slow upstream | Pool active/idle/pending, acquire duration |
| Connect timeouts rise while DNS is fast | Firewall drops, SYN loss, broken network route | TCP connect attempts, retransmissions, network policies |
| Immediate connection refused | Target not listening, bad readiness/target | Listener, LB target/`ServiceInstance` |
| TLS handshake time climbs while TCP is flat | TLS CPU, cert verification, mTLS load | TLS handshake histogram, CPU, cert validation errors |
| TLS cert/hostname mismatch | Wrong SNI/hostname/SAN/CA | TLS validation errors, target host, truststore |
| TLS/connection churn rises after tuning | Idle/lifetime too short; backend closes keep-alive | New connections/s, resets, idle evictions |
| Handshake time high only cross-region | Network RTT/distance | Compare same-region vs. cross-region in lab |
| Some HTTP/2 streams stall | `MAX_CONCURRENT_STREAMS`, connection saturation | Active/pending streams, negotiated protocol |
| DNS fast yet `lb://` route slow | Discovery/LoadBalancer selection | Registry cache / instance selection duration |
| TTFB rises while connect/TLS stay flat | Backend queues/processing, Gateway filters | Backend duration, HTTP client response wait |
| HTTP 503s rise on TLS failures | Gateway returning 503/fallback, not backend | Upstream counter == 0, TLS exception/final status |
| TCP resets after idle period | Stale pooled socket or LB idle expiry | Idle age, reset type, keep-alive mismatch |
| Retries push p99 up when backend errors | Multiple attempts + repeated handshakes | Inbound/outbound attempts, retry budget |
| Only one Gateway replica is slow | Divergent DNS cache/pool/config/CPU | Per-instance metrics and deployment revision |
| Laptop curl is fast, remote users are slow | Public DNS/RTT/ingress differences | Client-region RUM, edge metrics |
| `MockMvc` fast, real HTTP client slow | Inbound transport or outbound network path | `RANDOM_PORT` HTTP test, TLS/pool counters |
| Latency unchanged after enabling TLS 1.3 | Connections are reused; backend is the bottleneck | New handshake rate vs. overall request rate |
| Fast TLS handshake yet requests time out | Response/read timeout or long streaming | TTFB/body transfer, backend queue |

### Least-Disruptive Runbook Order

1. **Bound the blast radius.** Which routes? One backend or many? All Gateway replicas or one zone?
2. **Measure client-facing latency.** Gather p50/p95/p99 and error rates by route, status, and load. Note ingress vs. direct URLs.
3. **Separate requests hitting upstreams from fallbacks/rejections.** 401/403/rate-limit/circuit-breaker responses do not always call the backend.
4. **Measure outbound attempts.** Count inbound requests, retries, redirects, and instance selections.
5. **Measure pool acquire.** If pool wait is high, do not blame DNS/TLS first.
6. **Measure new vs. reused connections.** High reuse and low handshake rates make TLS setup an unlikely cause for overall p99.
7. **Measure DNS/connect/TLS per connection attempt.** Safely record host/instance, protocol, IP family, and outcome.
8. **Cross-check the backend.** Did requests arrive? How are server handling time and accept queues?
9. **Compare cold vs. warm in lab.** Hold HTTP version, payload size, retries, and network path constant.
10. **Change only one knob backed by evidence**, re-benchmark, and keep a rollback ready if errors climb or network identity breaks.

In investigations, a statement like `"TLS p99 is 90 ms"` must specify **start/end boundaries, which new connections were included, which hop, units, and sample count**. A TLS percentile over 100 handshakes never directly represents the p99 of 1 million HTTP requests reusing those sockets.

## 21. Optimize by Root Cause, Not Config Tricks

### 21.1. If DNS Is Truly Slow

- Check resolver stability and network reachability from Gateway to DNS.
- Map all cache layers: JVM, Netty, sidecar, recursive resolver.
- Trim unnecessary CNAME/hostname chains where architecture allows.
- Review TTLs and negative caching against IP rotation/failover needs.
- Never instantiate a new HTTP client per request (which destroys caching and pooling).
- When using service discovery, track registry refresh latency separately from DNS.

**Never set DNS TTL to infinity.** When backend IPs rotate during rollouts or scaling, stale DNS caches keep routing to dead endpoints and break failover.

### 21.2. If TCP Connect Is Slow

- Prefer placing services near backends where availability and data rules allow.
- Check firewalls, NATs, proxies, and packet loss/retransmissions.
- Use connection pooling/keep-alive to curb connection churn.
- Measure IPv4/IPv6 selection and fallback rather than blindly disabling IPv6.
- Check backend accept backlogs, load balancer health, and capacity.
- Configure sensible connect timeouts within an overall deadline.

**Never set connect timeout to infinity** to avoid errors; requests will hang on broken paths and fill queues.

### 21.3. If TLS Handshake Is Slow

- Verify both peers support and **actually negotiate** TLS 1.3—not just setting a flag.
- Maximize keep-alive/connection pooling before tuning individual full handshakes.
- Evaluate TLS session resumption **when reconnects are required**, measuring resumed vs. full handshakes.
- Inspect TLS CPU and concurrent handshakes on Gateway, backend, and sidecar.
- Optimize certificate chains per policy without dropping hostname/CA verification.
- Keep mTLS wherever service identity requires it; fix rotation, SNI, and truststore issues cleanly.
- Audit proxy/mesh TLS termination and per-hop RTT.

**Never treat enabling TLS 1.3 or HTTP/2 as an automatic silver bullet** if the true bottleneck is pool waits, backend DBs, or cross-zone hops. Run controlled benchmarks and compatibility tests.

### 21.4. If Pool Waits or Resets Dominate

- Measure max/active/idle/pending counts, idle ages, and new connections/s.
- Raise capacity incrementally **only when backends can handle more connections/streams**.
- Cap pending queues and acquire timeouts to bound tail latency.
- Align max idle/lifetime below backend/LB idle timeouts; verify stale resets drop.
- Watch HTTP/2 stream caps rather than counting only TCP sockets.
- Use circuit breakers, bulkheads, and rate limiters to protect downstreams from overload.

**Never raise all limits at once**, or you won't know which knob helped and risk overload or connection storms.

### 21.5. If All Handshakes Are Fast Yet Total Latency Is Slow

Focus shifts to:

- Spring Security / JWT validation or remote token introspection.
- Gateway route predicates and blocking or heavy custom filters.
- Service discovery, rate-limiter stores, or external authorization calls.
- Backend processing, DB/caches, queues, and response serialization.
- Response transfer and slow client reads.

More TLS tuning will not fix the root cause here. A **proper multi-span trace** is worth far more than toggling TLS flags.

## 22. Decision-Making Example Using Hypothetical Data

Operations reports:

> "Gateway Catalog p95 jumped from 60 ms to 140 ms after a deployment; HTTPS looks too slow."

Suppose monitoring shows these **illustrative aggregated figures**:

| Metric | Before deploy | After deploy |
| --- | ---: | ---: |
| Inbound requests/second | 300 | 300 |
| New outbound connections/second | 15 | 180 |
| TLS handshakes/second | 15 | 180 |
| Pool idle evictions/second | 10 | 160 |
| Backend processing p95 | 25 ms | 26 ms |
| Gateway total p95 | 60 ms | 140 ms |
| HTTP 5xx rate | 0.2% | 1.3% |

These numbers **do not come from a live system**; this is an analytical exercise.

### Initial Hypothesis

Outbound connection and TLS handshake rates spiked sharply while traffic stayed flat. Backend processing is steady, and pool idle evictions surged. Possible causes: **`max-idle-time` was lowered too far**, a new client/instance is created per request, or the upstream/LB shortened its idle timeout.

### What Is Still Unproven

- The surge in TLS handshakes **may be a symptom**, not the root cause—for example, the backend aggressively resetting sockets or a Gateway upgrade altering pool defaults.
- Gateway's p95 jump **cannot be explained quantitatively by handshake rate alone**. You need TLS handshake duration alongside request/connection attempts and pool wait times.
- 5xxs could stem from resets, stale sockets, TLS errors, or backend failures; classify by `exceptionType` and response provenance.

### Experiment Design

1. Diff `ConnectionProvider`, pool, and idle settings before vs. after the deploy.
2. Replay 300 req/s in a lab **holding Catalog stub, HTTP version, and TLS profile constant**.
3. Measure new connections/s, TLS handshake duration, pool pending/acquire duration, and Gateway p95.
4. Change only `maxIdleTime` (or the verified churn cause) and re-benchmark.
5. Confirm 5xx drops and backend accept/TLS CPU stay within budget.
6. Test DNS rotation and backend/LB idle timeouts before shipping the fix to production.

If tuning lowers p95 yet causes stale-connection errors when backend IPs rotate, **do not declare success**. A sound configuration balances latency with failover, availability, and certificate/identity integrity.

## 23. Hands-On Exercise: Measuring TLS/DNS/Connect Latency for a Gateway Route

**Scenario:** A Gateway routes `GET /api/catalog/**` to Catalog over HTTPS. The goal is decomposing client→Gateway and Gateway→Catalog latency, measuring cold vs. warm traffic, testing pooling changes in a lab, and concluding with data.

### Part A — Prepare a Controlled Topology

1. Choose **Gateway Server WebFlux** or **Gateway Server Web MVC**; record exact starter, BOM, and runtime versions. Never mix APIs across variants.
2. Run a **Catalog HTTP/HTTPS stub** in the lab returning small, stable JSON (e.g., `{"id":"42"}`); safely log request counts and TLS connections/handshakes if supported.
3. For HTTPS, use test certificates with matching SANs, a dedicated test CA/truststore, and proper SNI.
4. Configure either a static HTTPS URI or `lb://catalog-service` with a known test discovery setup; **never take backend URLs from client headers or query params**.
5. Ensure clients reach the Gateway via a test endpoint; if an ingress exists, document where TLS terminates.
6. Enable approved metrics for HTTP server/client, DNS resolver, TLS, and pools where supported.

### Part B — Cold/Warm Baseline

1. Run one curl call to the public/test Gateway; record `time_namelookup`, `time_connect`, `time_appconnect`, `time_starttransfer`, and `time_total`.
2. Send sequential calls **inside a single curl process or HTTP client** to observe **client → Gateway** connection reuse; never infer reuse from one call.
3. On Gateway outbound, collect request/connection telemetry showing whether Gateway→Catalog **opened a new connection** or reused one.
4. Create a cold outbound group in the lab via a fresh provider/instance or controlled reset—**never reset live production pools**.
5. Compare backend hits against inbound request counts; if retries occur, count every attempt.
6. Collect enough samples to spot trends, then gather larger sample counts for p99 analysis; never claim reliable p99 from 5–10 samples.

### Part C — Vary One Factor at a Time

| Experiment | Controlled variable | Expected observation |
| --- | --- | --- |
| DNS cache hit/miss | Controlled DNS test records/cache | Resolver query rate and DNS duration shift |
| Cold TCP | No pooled connection, identical target | Triggers fresh TCP connect attempt |
| Cold/resumed TLS | Same TLS version/cert, different session state | Full vs. resumed handshake counts/durations |
| Pooled reuse | Open connection, identical upstream | New connect/TLS counts drop during steady state |
| Short idle timeout | Pool evicts idle sockets early | Connection churn and handshakes/s rise |
| Backend/LB stale idle | Backend closes before pool | Post-idle resets/retries rise |
| Pending pool saturation | Bounded load above test pool cap | Pool acquire time and pending queue grow |
| HTTP/2 vs. HTTP/1.1 | Only when both peers support and ALPN confirms | TCP socket count and stream counts shift |
| Cross-zone RTT | Alternate authorized lab network path | TCP/TLS setup rises with network RTT |
| Invalid TLS cert | Bad stub cert or untrusted CA | Handshake fails closed; never returns 200 |
| DNS NXDOMAIN / no instance | DNS/discovery stub returns error | Distinguish DNS errors from no-instance errors |

### Part D — Safe Fault Injection

Inside an isolated test network/namespace:

1. Simulate slow DNS via a bounded test DNS proxy; measure DNS timeout behavior.
2. Simulate TCP connection refused via a stub with no listener on a dedicated test port.
3. Simulate slow responses via the backend stub; prove **response timeout differs from TLS timeout**.
4. Use a certificate with a wrong SAN in the lab; confirm clients reject it without logging secrets.
5. Configure a short backend idle timeout to test stale pooled sockets.
6. When testing retries, confirm each inbound request generates a **bounded number of upstream attempts** with no storm.
7. Stop fault injection and confirm pools, DNS caches, and registries return to steady state before the next test.

**Never run commands altering host firewalls, network routes, system DNS, or production TLS** to induce faults. Use authorized test proxies/namespaces with explicit teardown and stop limits so other workloads are unaffected.

### Part E — Fill Out the Results Table

| Metric | Baseline | Cold | Warm | After change |
| --- | --- | --- | --- | --- |
| Gateway inbound requests | ... | ... | ... | ... |
| Outbound attempts | ... | ... | ... | ... |
| New connections | ... | ... | ... | ... |
| Reused connections | ... | ... | ... | ... |
| DNS resolver requests / cache hits | ... | ... | ... | ... |
| Pool acquire p95 | ... | ... | ... | ... |
| TCP connect p95 | ... | ... | ... | ... |
| TLS handshake p95 | ... | ... | ... | ... |
| Backend processing p95 | ... | ... | ... | ... |
| Gateway route p95 | ... | ... | ... | ... |
| Client end-to-end p95/p99 | ... | ... | ... | ... |
| HTTP 5xx, timeouts, TLS errors | ... | ... | ... | ... |

Fill cells only where **matching instrumentation exists**. If TLS handshake duration cannot be isolated yet, enter **N/A — not instrumented** instead of subtracting unrelated p95s.

### Part F — Analysis and Decision

Answer:

1. How much slower were cold requests than warm requests, and **did new-connection counters confirm it**?
2. How long did DNS lookup actually take on attempts that triggered DNS, rather than averaged across all requests?
3. Was TLS 1.3 negotiated? Were handshakes full or resumed?
4. Under load, did pool acquire time exceed TLS handshake time?
5. When changing idle timeout, how did stale resets and DNS failover behavior change?
6. Did Gateway p95/p99 genuinely improve under identical workloads while keeping 5xx/error rates within SLO?
7. Did the optimization preserve mTLS, certificate validation, proxy trust, and token forwarding?
8. With retries/circuit breakers enabled, do inbound requests and outbound attempts match policy?

**Pass criteria:** You produce a **sourced comparison table/chart** separating client-facing timings from outbound DNS/TCP/TLS, prove connection reuse with counters, preserve TLS verification, and state a tuning decision with a rollback plan. Running `curl` once and saying `"TLS takes 40 ms so turn off TLS"` fails completely.

## 24. Production Checklist and Rollout Strategy

A small tweak to connection pools or DNS caching can speed up a Gateway benchmark while causing **failover failures, TLS identity mismatches, or backend overloads**. Never treat network tuning as a low-risk change.

### Pre-Deployment

~~~text
[ ] Confirmed Gateway variant: Server WebFlux vs. Server Web MVC.
[ ] Locked Spring Boot, Spring Cloud BOM, and HTTP client/Netty versions.
[ ] Mapped exact hops: browser/ingress/Gateway/upstream/sidecar.
[ ] Identified where TLS terminates and which hops use mTLS.
[ ] Captured per-route baseline p50/p95/p99 and request/error rates.
[ ] Captured pool acquire, new/reused connections, and handshake counts.
[ ] Measured DNS resolution separately from service discovery selection.
[ ] Verified HTTP client and route timeouts actually bind on the running version.
[ ] Kept Host, Authorization, Cookie, and raw URIs out of metric labels.
[ ] Tested new connections, reuse, DNS rotation, and stale idle connections.
[ ] Tested negative TLS chain/hostname/SNI and mTLS (if used) cases.
[ ] Configured overall timeouts/retry budgets; never retry non-idempotent writes.
[ ] Prepared canary plan, SLO gates, rollback steps, and assigned owner.
~~~

### During Canary

Monitor simultaneously:

| Group | Signs of improvement | Stop / rollback triggers |
| --- | --- | --- |
| Client latency | p95/p99 drops under identical traffic mix | p99 rises or client errors climb |
| Outbound pool | Acquire p95 drops, pending queue stays flat | Pending/rejected acquires climb rapidly |
| DNS | Healthy cache hits, fewer resolver timeouts | Prolonged stale IPs/NXDOMAIN, slow failover |
| TCP | Fewer connect failures/retransmits | Sudden surge in new connections/s |
| TLS | Lower handshake duration/errors | Cert mismatches, trust failures, mTLS rejections |
| Backend | Throughput/CPU/accept queues within bounds | 429/503s, rising TLS CPU, or overload |
| Retry | Attempts/request stay within policy | Retry storms or duplicate side effects |
| Security | TLS verification/mTLS/trust stay intact | Any test requiring disabled verification |

**Compare only under equivalent traffic.** If cache hit ratios or response sizes shift after a deploy, total p95 can drop because the business workload changed—not from TCP/TLS tuning. Record route, upstream, instance, environment, and timestamps alongside deployment revisions.

### When Incidents Happen After a Change

1. Halt canary expansion immediately when error rates or SLOs degrade.
2. Check connection churn, pool saturation, stale DNS records, and TLS handshake errors per replica.
3. Identify the active config source of truth: app config, Config Server, Helm/manifests, JVM flags, or sidecar.
4. Roll back **the specific offending config**, never by disabling TLS validation or weakening security controls.
5. Verify the Gateway loaded the previous config; for pools and DNS caches, **existing open connections** may take a full lifecycle to drain.
6. Confirm failover, backend health, mTLS rotation, and client error rates recover.
7. Document root cause with phase-level measurements rather than guessing from a few log lines.

### When to Stop Optimizing

If Gateway p95 is 45 ms, DNS/TCP/TLS affects only a tiny slice of new-connection requests, and **new connection rates are low**, further TLS handshake tuning rarely justifies the risk. Focus instead on backend latency, rate limiting/fallbacks, appropriate caching, or response transfer if those dominate.

## 25. Misconceptions to Avoid When Reading Metrics

| Misconception | Reality |
| --- | --- |
| "Curl's `time_appconnect` is Gateway → backend TLS." | It normally measures **curl → peer** (e.g., CDN/ingress) TLS, blind to Gateway outbound. |
| "`time_connect` measures only TCP connect." | It is a **cumulative timestamp** from transfer start; subtract `time_namelookup` to estimate TCP connect in matching scenarios. |
| "`time_starttransfer` equals backend processing time." | It spans network, Gateway, queues, and backend work up to the first byte. |
| "Once DNS TTL expires, every HTTP request queries DNS." | Pooled connections and resolver caches skip queries across many requests. |
| "`lb://` is simply a DNS lookup." | It selects a `ServiceInstance` via discovery/LoadBalancer; DNS may follow separately. |
| "Changing JVM DNS TTL always updates Netty's cache TTL." | Reactor Netty can use its own resolver and cache. |
| "A matching Gateway route means the backend is connected." | Route matching does not guarantee healthy instances, DNS, TCP/TLS, or backends. |
| "HTTP 200 proves DNS/TLS is fast." | Could reflect pooled sockets, caches, fallbacks, or fast backends. |
| "Pooled connections always avoid all delays." | Requests can still hit pool acquire waits, stream caps, or stale sockets. |
| "Every new connection performs a full TLS handshake." | Session resumption may run, though it is still a new connection needing TCP. |
| "TLS 1.3 automatically makes every request 0-RTT." | Full handshakes still take RTT; early data is optional and carries replay risk. |
| "HTTP/2 means one connection that can never stall." | Stream caps, flow control, and packet-loss congestion still cause waits. |
| "Raising `maxConnections` always lowers latency." | Can overload backends, TLS CPU, and file descriptors. |
| "Raising connect timeout fixes pool acquire timeouts." | Different phases; inspect pool queues and acquire times. |
| "A `dig` output on my laptop shows the JVM's DNS cache." | `dig` can hit a different resolver/cache than the Gateway process. |
| "Adding DNS p95 + TCP p95 + TLS p95 gives request p95." | Percentiles from separate distributions are not additive. |
| "`MockMvc` measures client TLS handshakes." | `MockMvc` opens no real inbound TCP/TLS sockets. |
| "All `spring.cloud.gateway.httpclient.*` properties work on MVC." | WebFlux and MVC have separate HTTP clients/configs; namespaces also vary by version. |
| "Connection reset after idle proves DNS is broken." | Often caused by backend/LB idle timeouts or stale pooled sockets. |
| "Cutting TLS latency by disabling cert checks is an optimization." | That is a **security downgrade**, never a valid fix. |
| "Firing many requests to measure won't hurt the backend." | Cold-connection storms burn TCP/TLS resources on backends too. |
| "HTTP request rate equals TLS handshake rate." | Keep-alive/pooling amortizes handshakes; retries multiply attempts. |
| "TLS cert rotation has nothing to do with pooling." | Existing pooled connections and new connections can see different identities/keys; plan rollouts/refreshes carefully. |
| "Fast p50 proves users aren't impacted." | p99, tail retries/timeouts, and errors expose cold-path pain. |

## 26. Summary

- A Gateway is both a client-facing **HTTP server** and an upstream-facing **HTTP client**. Always know **which hop is measured**, where TLS terminates, and whether ingress/service meshes sit in between.
- **DNS resolution, service discovery, TCP connect, TLS handshake, pool acquire, backend processing, and response transfer** are distinct phases. Connection-reusing requests skip several of them, while retries/fan-outs can trigger them repeatedly.
- **DNS caches/TTLs and pooled connections** shape lookup frequency. Never confuse `lb://` `ServiceInstance` selection with DNS A/AAAA resolution, and never use `dig` on another host to guess JVM/Netty cache contents.
- **TLS 1.3** typically trims full-handshake RTTs vs. TLS 1.2, yet **does not eliminate TCP setup**; session resumption differs from connection reuse, and 0-RTT introduces replay risk.
- **Connection pooling and HTTP/2 multiplexing** amortize connection setup across many workloads, yet still need bounded pending queues, idle/lifetime caps, and stream limits to prevent stale sockets, saturation, or reconnect storms.
- **Curl timings are cumulative timestamps**: `time_connect`, `time_appconnect`, and `time_starttransfer` are not pure TCP, TLS, and backend durations without accounting for boundaries and topology.
- **Gateway WebFlux** requires Reactor Netty / HTTP client transport instrumentation to measure outbound DNS/TCP/TLS; a `GlobalFilter` captures only route-chain lifecycle. **Gateway Web MVC** requires instrumenting the Servlet stack's outbound HTTP client—never assume Netty metrics or configs apply.
- **Evaluate cold vs. warm under control** using request/connection counters, phase metrics/traces, warm-up, and adequate sample sizes; never sum DNS p95 + TCP p95 + TLS p95 as total p95.
- **Safe optimizations** preserve TLS certificate/hostname verification, mTLS, and timeout/retry budgets; never use trust-all SSL, unbounded connections, or infinite DNS caches to hide issues.
- During rollouts, compare p95/p99, errors, new connections, pool waits, resolver behavior, and backend load **under identical traffic mixes** with canaries and SLO-driven rollbacks.

The goal of evaluating **SPRING_CLOUD_GATEWAY** performance is never just finding one number for "how many milliseconds TLS takes," but **knowing which connections a request opened, where each phase's cost lives, why cold and warm paths differ, and which changes improve real user experience without compromising microservice security and resilience**.

### Version-Matched Official Documentation

- **Spring Cloud Gateway Reference:** https://docs.spring.io/spring-cloud-gateway/reference/
- **Reactor Netty Reference:** https://projectreactor.io/docs/netty/release/reference/
- **Spring Boot Actuator Metrics:** https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- **curl `--write-out` documentation:** https://curl.se/docs/manpage.html
- **TLS 1.3, RFC 8446:** https://www.rfc-editor.org/rfc/rfc8446
- **HTTP Semantics, RFC 9110:** https://www.rfc-editor.org/rfc/rfc9110

Verify your **actual Spring Boot, Spring Cloud Gateway, Reactor Netty, HTTP client, and TLS runtimes** before copying any property, meter name, or Java snippet; accurate measurements require matching versions, network paths, and telemetry sources.
