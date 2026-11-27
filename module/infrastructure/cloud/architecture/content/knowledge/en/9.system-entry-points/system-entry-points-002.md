# Transport Layer and Application Layer Load Balancing

A cloud-deployed application typically runs multiple replicas of an API, web server, or TCP/UDP service. Users only know a single domain name, yet the system must select healthy servers, stop routing traffic to failing machines, and scale as load grows. A **load balancer** is an entry-point component that distributes traffic across eligible targets according to policies and health status.

Not all load balancers handle traffic the same way. Two commonly referenced categories are **transport-layer load balancing (Layer 4, L4)** and **application-layer load balancing (Layer 7, L7)**. They differ primarily in **what information they can inspect and use to make routing decisions**, which drives trade-offs in features, security, performance, cost, and operations.

This lesson belongs to the **System Entry Points** section of the cloud architecture module. When designing from business requirements through networking, compute, data, and deployment models, choosing between L4 and L7 must align with **actual protocols, user experience, reliability, scalability, protection level, and operational capability**. These are also key questions for a Well-Architected review.

After this lesson, you will be able to:

- Distinguish L4 and L7 by routing signals, protocols, capabilities, and limitations.
- Design entry points for HTTP/HTTPS, gRPC, WebSocket, TCP, and UDP based on concrete requirements.
- Explain TLS termination, TLS passthrough, health checks, session affinity, and connection draining.
- Analyze risks when load balancing across multiple instances, subnets, availability zones, or regions.
- Design observability, access control, redundancy, and capacity estimation flows.
- Compare cloud load balancing services by **required capabilities**, and validate choices through load and failure testing.

## 1. Where Does a Load Balancer Sit in the Architecture?

Suppose a scheduling application runs three Booking API replicas. Customers connect via a single hostname, such as <code>booking.example.com</code>, instead of knowing individual instance addresses. DNS returns the appropriate entry point, and the load balancer accepts connections or requests, selects an eligible backend, and forwards traffic.

~~~mermaid
flowchart LR
    U["Browser / Mobile"] --> DNS["DNS: booking.example.com"]
    DNS --> LB["Public load balancer"]
    LB --> A1["Booking API A"]
    LB --> A2["Booking API B"]
    LB --> A3["Booking API C"]
    A1 --> DB[("Database")]
    A2 --> DB
    A3 --> DB
~~~

The diagram illustrates the **logical path**. DNS does not necessarily proxy each request: clients typically use DNS to locate the endpoint and then connect directly to the resolved address. In the cloud, an endpoint may be a virtual IP, multiple IPs, a provider-managed name, or a distributed network layer.

A load balancer solves several problems:

1. **Distributing traffic** across a backend pool, avoiding direct client coupling to a single application server address.
2. **Selecting eligible backends** via health checks or platform-provided signals.
3. **Decoupling the public address from backends**, allowing instances to scale in/out or change deployment topologies without changing user-facing URLs.
4. **Supporting operations**, such as connection draining during releases, error observability, and traffic splitting across versions where supported.
5. **Establishing security boundaries**, combining TLS, network segmentation, policies, WAF, or other controls depending on the load balancer type.

However, a load balancer **does not automatically make an application stateless, enable a database to absorb load, or make a system survive a full-region outage**. If all three API replicas share one database without an adequate recovery strategy, the database remains a critical point of failure.

## 2. How Do L4 and L7 Differ?

In the OSI model, **Layer 4** corresponds to the transport layer (typically TCP/UDP), while **Layer 7** is the application layer (HTTP and other application protocols). In practice, cloud product names include *Network Load Balancer*, *Application Load Balancer*, *Gateway*, *Reverse Proxy*, or *Ingress*. Always inspect **actual product capabilities**, as naming does not reliably indicate every feature.

| Aspect | Layer 4 (L4) Load Balancer | Layer 7 (L7) Load Balancer |
| --- | --- | --- |
| Primary routing signals | IP address, port, protocol, connection state; possibly flow attributes | Host, path, method, headers, cookies, and supported HTTP properties |
| Typical distribution unit | TCP connection or UDP flow | HTTP request or application stream depending on implementation |
| Protocols | Commonly used for TCP/UDP, with some services supporting TLS listeners | Commonly used for HTTP/HTTPS; some support HTTP/2, gRPC, WebSocket |
| Host/path routing | Cannot route on HTTP contents in a pure L4 model | Can route by domain name and URL path |
| TLS | Can passthrough or terminate TLS on the listener if supported | Usually terminates TLS to read HTTP; can initiate new TLS to backends |
| HTTP features | Generally cannot apply URL/header rules directly | Can support redirects, rewrites, header rules, authentication, WAF, or rate limiting depending on product |
| Health checks | Can check TCP/port; some support HTTP-level checks | Typically checks HTTP status/path and response conditions |
| Observability | Connections, packets/bytes, resets, ports, flows | Adds request rate, status codes, routes, HTTP latency when enabled |
| Trade-offs | Less coupled to application semantics; ideal for non-HTTP protocols | Richer web traffic control; requires evaluating compute overhead and configuration complexity |

**Important note:** the L4/L7 distinction describes *how the load balancer processes traffic*, not a blanket rule that "L4 is always faster," "L7 is always slow," or "L4 cannot do TLS." An L4 service may support TLS termination while still lacking HTTP path routing rules. Capabilities, latency, and cost must be measured on the actual cloud service and workload.

### L4: Selecting Backends from Transport Information

Suppose a client opens a TCP connection to <code>tcp.example.com:5672</code>. The L4 load balancer forwards that connection to an eligible healthy backend. While the connection persists, packets belonging to the same flow must consistently route to the same backend to preserve TCP state.

~~~mermaid
sequenceDiagram
    participant C as TCP client
    participant L as L4 load balancer
    participant B as TCP backend
    C->>L: TCP connection to IP:port
    L->>B: Open/forward flow to selected backend
    B-->>C: Return traffic via appropriate routing path
    Note over L,B: Backend selected per connection/flow
~~~

L4 does not need to inspect the <code>/appointments</code> URL inside HTTPS to choose a backend. That is an advantage for custom TCP protocols, databases behind compatible proxies, or certain UDP protocols. Balancing **UDP flows** also depends on timeouts and how the provider identifies flows, since UDP is connectionless unlike TCP.

### L7: Selecting Backends from Application Information

For example, a single domain can serve:

- <code>GET /api/slots</code> → Booking API pool.
- <code>POST /api/bookings</code> → Booking API pool with dedicated protection policies.
- <code>GET /static/logo.svg</code> → static service pool or storage/CDN.
- <code>admin.example.com</code> → admin backend with stricter authentication and access policies.

~~~mermaid
flowchart TD
    C["HTTPS client"] --> L7["L7 load balancer<br/>TLS / HTTP routing"]
    L7 -- "Host: admin.example.com" --> ADMIN["Admin service"]
    L7 -- "Path: /api/*" --> API["Booking API"]
    L7 -- "Path: /static/*" --> STATIC["Static content origin"]
    L7 -- "No match" --> DEFAULT["Default response or backend"]
~~~

L7 needs to read HTTP attributes to make routing decisions, so in a typical HTTPS setup it **terminates client-side TLS**, then forwards over internal HTTP or a new TLS session to backends. This choice directly affects where certificates are managed, where plaintext exists, and where trust boundaries lie.

## 3. Do Not Confuse Protocol Needs with Load Balancer Product Names

The first question should always be **what protocol the client speaks**, what application-layer semantics exist, and which features are genuinely required:

| Traffic Type | Typical Fit | Must Verify Before Committing |
| --- | --- | --- |
| HTTP/HTTPS web with multiple hosts/paths | L7 HTTP load balancer | HTTP versions, routing rules, TLS, WAF, quotas, pricing |
| Simple single-backend REST API | L4 or L7 depending on needs | Need HTTP metrics/WAF/auth/redirects, or just connection distribution? |
| gRPC over HTTP/2 | L7 **with proper gRPC/HTTP/2 support**, or L4 passthrough | Backend protocol, streaming, timeouts, HTTP/2, health checks |
| WebSocket | L7 supporting HTTP upgrade/WebSocket or L4 passthrough | Idle timeouts, draining, long-lived connections, sticky sessions |
| Custom TCP | L4 or protocol-aware gateway | Source IP, TCP resets, long-lived connections, TLS, ports |
| Custom UDP | L4 **with UDP support** | Flow affinity, health checks, UDP timeouts, NAT, and quotas |
| HTTP/3 over QUIC/UDP | Endpoint/L7 edge **explicitly supporting HTTP/3** | Listener QUIC support, TLS, HTTP/2 fallback, backend protocol |
| Multiple web services behind one IP/hostname | L7 if request-level routing is needed | Host/path matching, rule priority, and safe default route |

**HTTP/3 does not mean any UDP load balancer can parse HTTP/3.** An L4 LB can forward UDP packets, whereas terminating QUIC and enforcing HTTP/3 policies requires a component that understands the protocol and exposes those features.

For **gRPC**, HTTP/2 is essential, yet not every L7 LB supports all streaming modes or gRPC health checks equally. For **WebSockets**, connections often outlive standard HTTP requests; timeouts and graceful backend shutdown during deployments must be configured accordingly.

## 4. TLS Flows and Security Boundaries

TLS establishes an encrypted channel between two endpoints. Where decryption happens determines which component can inspect application payloads and which zones must be trusted.

### 4.1. TLS Passthrough

~~~mermaid
flowchart LR
    C["Client"] -- "TLS encrypted" --> L["L4 LB<br/>Forward flow"]
    L -- "TLS encrypted" --> B["Backend<br/>Terminate TLS"]
~~~

In this model, the backend handles client TLS while the L4 LB primarily forwards the transport flow. Benefits include keeping traffic encrypted all the way to the backend and letting the application manage its own certificates and TLS policies. Trade-off: an LB that does not decrypt HTTP cannot fully inspect URLs/headers or enforce HTTP-based WAF rules at that tier.

TLS passthrough **does not guarantee end-to-end security by itself** if certificate management, hostname verification, TLS updates, or backend protections are misconfigured.

### 4.2. TLS Termination at L7 and Backend Forwarding

~~~mermaid
flowchart LR
    C["Client"] -- "HTTPS/TLS" --> L["L7 LB<br/>Terminate TLS, HTTP rules"]
    L -- "Internal HTTP or new HTTPS/TLS" --> B["Backend"]
~~~

In this model, the L7 LB can apply host/path routing, HTTP rules, logging, and L7 security policies. In return, decrypted HTTP exists inside the LB process and potentially on an internal network segment if backend connections are unencrypted.

If data must remain protected across the LB → backend leg as well, use **TLS re-encryption** with proper backend authentication policies. Simply placing a certificate on the backend without having the LB verify the certificate and server identity does not satisfy security goals.

### 4.3. Configuration Decisions You Must Make

| Item | Design Question |
| --- | --- |
| Certificates | Who issues, renews, and rotates them? Single-host or wildcard certs? |
| Protocols & ciphers | Which TLS versions are accepted? Is there a policy to deprecate weak versions? |
| Backend encryption | Is LB → backend encrypted, and are certificate/hostname checks enforced? |
| mTLS | Do clients need certificates at the edge or between services? Does the LB support the exact model? |
| SNI | When multiple hostnames share an entry point, how are certificates and targets selected? |
| HTTP redirect | Is HTTP on port 80 redirected to HTTPS or rejected? |
| Headers | Are untrusted client-supplied identity headers stripped or overwritten? |
| Secrets | Where do TLS private keys reside, and who has access and audit visibility? |

**Do not extrapolate from layer numbers:** an L4 LB with a TLS listener can terminate TLS, yet that does not turn it into a full HTTP reverse proxy. Conversely, some L7 gateways offer rich routing yet still require proper network segmentation and firewalls to protect backends.

## 5. Load Distribution Algorithms and Long-Lived Connection Issues

When multiple backends are healthy, the load balancer must pick one for incoming traffic. Depending on the product and tier, algorithms may include:

- **Round robin:** cycles sequentially across targets; simple, but ignores per-request processing cost.
- **Weighted round robin:** distributes according to weights; useful for heterogeneous backends or canary rollouts.
- **Least connections:** favors targets with fewer active connections, where supported; connection count does not always reflect CPU usage.
- **Hash-based / affinity:** maps flows consistently to a backend via a key or cookie; useful for certain stateful workloads.
- **Measured latency/load-based algorithms:** offered by some platforms, though availability and behavior vary widely across cloud providers.

### L4 Distribution Differs from HTTP Request Balancing

Suppose a client holds a long-lived TCP connection open and sends many requests over it. L4 typically selects a backend **per connection**, so 100 connections do not necessarily represent 100 equal units of work. One client firing heavy request volume over a single connection can overload one backend.

Similarly, HTTP/2 can **multiplex** many streams over one TCP connection; how an L7 LB distributes streams/requests depends on its implementation and upstream connection pooling. Never assume each HTTP/2 request automatically hits an independent backend.

Therefore, load tests should simulate realistic **connection counts, requests per connection, connection lifetimes, stream concurrency, and heavy/light request mixes**.

### Are Sticky Sessions a Proper State Strategy?

**Session affinity / sticky sessions** attempt to route a client's requests to the same backend for a duration. This can help legacy systems using in-memory sessions, but introduces limitations:

1. Skewed load distribution when certain sessions are unusually active.
2. Loss of local session state if a backend crashes or is replaced during a deployment.
3. Less predictable autoscaling and rolling deployments.
4. Affinity cookies or keys must be secured and given appropriate timeouts.

For modern web/API applications, prefer **stateless applications**, using proper session tokens or externalized state stores when required by business logic. Session affinity is a conditional tactical tool, not a substitute for durable state management.

## 6. Health Checks, Backend Selection, and Failure Handling

A load balancer needs to know whether a backend is eligible to receive new traffic. Two common check types:

**Connection-level checks:** attempts to open a TCP connection to the service port. This proves the port is listening, **not that the booking API is functioning properly**.

**Application-level checks:** calls an endpoint like <code>GET /health/ready</code> and validates the HTTP status/response criteria. This reflects true readiness better, but must avoid becoming overly expensive or needlessly coupled to every downstream service.

### Distinguishing Liveness and Readiness

- **Liveness:** is the process wedged or unrecoverable? Failure may trigger a runtime restart.
- **Readiness:** is the instance ready to accept **new traffic**? If still starting up, draining, or overloaded, it should be removed from rotation.
- **Startup:** some runtimes offer a separate startup probe for slow-booting apps so readiness/liveness checks do not kill them prematurely.

For an L7 LB, the readiness probe is usually an HTTP path; for an L4 LB, it may be a TCP check or a separate HTTP health check endpoint when supported. **Data-plane layer does not dictate health-check layer**: some L4 LBs also support HTTP health checks.

### Example Health Design for the Booking API

| Scenario | Liveness | Readiness | Desired Outcome |
| --- | --- | --- | --- |
| App starting up | May still be pending per startup policy | Failing | Receives no traffic yet |
| API ready to serve | Passing | Passing | Eligible backend target |
| Instance stopping for deploy | May remain passing | Failing | Stops receiving new requests; drains in-flight work |
| Severe thread pool saturation | May remain passing | May fail per policy | Sheds new load from instance while monitoring overall pressure |
| Transient database outage | App may still be alive | Choose check scope carefully | Avoid mass restarts when fault lies in a shared dependency |

Not every downstream failure should mark **all backends** unhealthy. If every API instance ties readiness strictly to a failing database, the load balancer could drain the entire pool without improving resilience. Design clear policies: return controlled errors, apply bounded retries, serve cached reads where safe, or degrade gracefully by business rules.

### Health Checks Have Detection Latency

When tuning check intervals, fail/pass thresholds, and timeouts, teams must accept **detection lag** for unhealthy backends. Checking too infrequently delays traffic shift; checking too aggressively adds noise and instability during transient blips.

To evaluate HA, factor in detection time, target group update propagation, client retries, recovery duration, and impact on in-flight requests. Never equate "having two instances" with "zero downtime."

## 7. Connection Draining, Timeouts, and Zero-Downtime Deployments

During rolling deployments or scale-in events, the system must stop sending **new traffic** to a retiring backend while letting active requests/connections finish within a reasonable window. This process is typically called **connection draining** or **deregistration delay**, depending on the provider and product.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant LB as Load balancer
    participant OLD as Old API instance
    participant NEW as New API instance
    LB->>NEW: Health check
    NEW-->>LB: Ready
    LB->>OLD: Stop routing new traffic
    C->>LB: New request
    LB->>NEW: Forward request
    Note over OLD: Finish in-flight request if within window
    OLD-->>LB: Complete old response
    Note over OLD: Terminate safely after drain timeout
~~~

Review each timeout independently: initial connect, idle, request, response, backend, health check, and drain. An hours-long WebSocket connection cannot be treated like a 200 ms REST call. For streaming/gRPC, define how connections close, how safe retries work, and when clients reconnect.

**Retries are a risk multiplier:** when clients, load balancers, and application layers all retry a write request independently, executions can multiply. For booking or payment operations, enforce **idempotency keys** and duplicate handling in business/database logic. Never blindly retry mutating methods or requests with side effects.

## 8. Where to Place LBs: Public, Internal, Regional, and Global

A workload often has multiple entry points:

| Entry Point | Example | Design Questions |
| --- | --- | --- |
| **Public / Internet-facing** | Customer-facing web and API | DNS, TLS, WAF, DDoS, public IPs, multi-AZ, rate limits |
| **Internal / Private** | Service-to-service APIs or corporate network access | Private routing, segmentation, mTLS, source network restrictions |
| **Regional** | API within a single region | Multi-AZ, intra-region routing, regional dependencies |
| **Global / Cross-region** | Multi-geography application | Latency routing, health, failover, data residency, data sync |

A *public* LB does not require backends to live in public subnets. The standard pattern is a **public frontend** receiving Internet traffic, with backends in private networks accepting connections only from authorized components.

Separate three responsibilities clearly:

1. **DNS / global traffic management:** steers clients to the right endpoint or region based on policy and observed health. DNS caching and TTL govern shift speed and never guarantee instant client updates.
2. **Regional L4/L7 load balancer:** selects backends within the service's configured scope per connection or request.
3. **Backend application:** executes business logic and state transitions with retry, concurrency, idempotency, and data access policies.

### Illustrative Diagram for the Scheduling Application

~~~mermaid
flowchart TB
    CLIENT["Internet Customers"] --> DNS["Public DNS"]
    DNS --> EDGE["CDN / WAF / DDoS protection<br/>If required"]
    EDGE --> ALB["Public L7 load balancer<br/>HTTPS, host/path routing"]
    subgraph VPC["Private application network"]
        ALB --> API_A["Booking API - AZ A"]
        ALB --> API_B["Booking API - AZ B"]
        API_A --> DB[("Managed database<br/>HA per configuration")]
        API_B --> DB
        API_A --> QUEUE["Managed queue"]
        API_B --> QUEUE
        QUEUE --> WORKER["Notification worker"]
        INTERNAL["Internal service client"] --> ILB["Private LB if needed"]
        ILB --> API_A
        ILB --> API_B
    end
~~~

**Do not treat this diagram as a default template.** Verify that your edge and LB integrate cleanly, check backend addressing, security groups/firewalls, health checks, TLS, and autoscaling behavior. CDN or WAF capabilities may be built directly into the edge/L7 product rather than requiring a separate hop.

If you select **L4** as a public frontend for a custom TCP protocol, that LB likely lacks built-in HTTP routing or WAF. Compensating controls must then live at the network, service, or another gateway layer.

### Multi-AZ vs. Multi-Region

Deploying an L7 or L4 LB with backends across multiple **availability zones** improves resilience to zone failures, provided you verify backend capacity and shared dependencies. If one zone fails, surviving zones must have enough headroom to carry the full load.

**Multi-region** is a far larger problem: shifting traffic across regions, managing state/data replication, preserving ordering and consistency, respecting data residency, and testing failover and failback. Putting two load balancers in two regions alone does not yield a reliable multi-region service.

## 9. Source IP, Proxy Headers, and Trust Boundaries

When requests traverse one or more proxies/load balancers, backends often see **the proxy's IP address** rather than the original client IP. If your system relies on IP for rate limiting, forensics, auditing, or access policies, you must define how network identity is propagated.

Common mechanisms:

- **Forwarded / X-Forwarded-For:** HTTP headers recording the proxy/client chain by convention; standard behind L7 reverse proxies.
- **X-Forwarded-Proto / Forwarded proto:** informs backends of the original scheme when TLS terminates at the LB.
- **PROXY protocol:** carries transport-level connection metadata when supported by both ends, often useful with L4.
- **Client IP preservation:** offered by some L4 products depending on target type, topology, networking, and configuration.

**Never implicitly trust an <code>X-Forwarded-For</code> header sent directly by an Internet client.** If an application reads the first value in the header chain without verifying trusted proxies, attackers can spoof IPs to bypass rules or corrupt audit logs.

Proper design requires:

1. Accepting inbound connections only from managed proxies/LBs via strict network policies.
2. Defining a **trusted proxies** list and knowing how the LB strips, appends, or overwrites client-supplied headers.
3. Configuring your application/framework with the trusted hop count or proxy CIDR ranges; verify multi-hop chains like CDN → LB → gateway.
4. Using identity/tokens for business authorization; IP is only a secondary signal, never a substitute for user authentication.

For example, when TLS terminates at the LB and the backend receives HTTP, a misconfigured framework may generate <code>http://</code> redirects, omit the Secure flag on cookies, or build broken callback URLs. Configure scheme/host forwarding strictly along verified trust paths.

## 10. How Do L4/L7 Relate to Security?

Load balancers establish traffic-handling boundaries, yet **security is layered**:

| Risk | Controls to Evaluate |
| --- | --- |
| Unauthorized traffic reaching backends | Private subnets, firewalls/security groups, routes, and rules restricted to LB/gateway sources |
| HTTP attacks and malicious payloads | WAF or HTTP inspection where L7 is visible; application must still validate inputs |
| API abuse and credential stuffing | Identity/IP rate limits, auth, quotas, bot mitigation, sensitive endpoint hardening |
| Network/transport-layer flooding | Provider DDoS protection and absorption capacity; connection monitoring |
| Eavesdropping/tampering in transit | Proper TLS, certificate/secret governance, mTLS where required |
| Sensitive data leaks in logs | Redact tokens and PII; enforce log access controls, retention, and storage region |
| Misrouting to sensitive backends | Audit host/path rules, default actions, ACLs, and authorization tests |
| Client IP spoofing | Trusted proxy configuration; strip/rewrite untrusted headers at trusted boundaries |

**An L7 LB is not automatically a WAF**, and **a WAF does not replace application authorization**. APIs must still enforce object-level permissions per user, prevent injection, validate request bodies, and handle sessions securely.

When routing by domain name, configure the **default route** intentionally. Unrecognized hosts might return 404/403 by design rather than accidentally falling through to an Admin backend. Test edge cases including unusual Host headers, path encoding, trailing slashes/casing, and rule precedence to avoid unintended exposure.

## 11. Impact of L4/L7 on Scalability and Cost

Load balancers distribute load across instances, but they do not eliminate backend resource limits. Size capacity for **real traffic patterns**, especially long-lived requests, large uploads, or WebSockets.

### 11.1. Rough Backend Capacity Estimation

Suppose the Booking API expects **600 requests/second** at peak. Load testing shows one instance sustains **120 requests/second** within acceptable CPU, p95 latency, and error thresholds.

~~~text
Theoretical instance count by throughput
  = ceil(600 requests/sec / 120 requests/sec/instance)
  = 5 instances
~~~

**Five instances only suffice for throughput while all are healthy and load remains steady.** To survive losing an availability zone, remaining capacity must absorb **all 600 RPS**. For example, across two zones while keeping full capacity if either zone fails, you need at least **5 healthy instances in the surviving zone**. A symmetric baseline might start with 5 instances per zone (10 total), before adding headroom, traffic spikes, LB capacity, and other limits.

This illustrates **sizing logic**, not a recommended production count. True per-instance capacity must be measured under realistic mixed workloads including database queries, TLS/proxy overhead, real connections, caching, write contention, quotas, and scale-out lag. If autoscaling takes several minutes to provision new instances, hold sufficient buffer for burst periods.

### 11.2. L4 Is Strongly Influenced by Connections/Flows

For long-lived TCP, monitor **active connections**, connection setup rate, resets, connection duration, and bytes transferred. For UDP, track packet/byte rates, flow timeouts, source distribution, and application latency via dedicated telemetry.

An LB may handle huge connection volumes while backends exhaust **file descriptors, threads, memory, connection pools**, or socket limits. If L4 performs NAT, also watch source port exhaustion/port allocation per topology and service—never size from RPS alone.

### 11.3. L7 Requires Additional Request-Level Observability

Beyond connection metrics, measure **HTTP status codes, request rates, p50/p95/p99 latency, response sizes, route/target groups, TLS handshakes, and request timeouts** where available. Because L7 inspects more application context, resource overhead varies by product, algorithms, connections, rules, logging, and traffic shape.

### 11.4. Cost Goes Beyond LB Hourly Fees

When budgeting, account for:

- Fixed hourly or capacity-unit charges, **where applicable**.
- Variable fees per byte, connection, request, rule, capacity unit, or provider-specific billing metric.
- Cross-zone/cross-region data transfer, Internet egress, NAT, CDN, or private link transfer.
- WAF, TLS/certificate management, access logs, metrics, alerts, and log storage.
- Standby backend capacity required for SLOs and failover headroom.
- Engineering time for configuration, monitoring, certificates, incident response, and security reviews.

There is no rule that "L4 is always cheaper than L7." Traffic volume, billing dimensions, network topology, log volume, and adjacent components can flip the math. Estimate using **actual pricing tables and quotas for the chosen service** across baseline, peak, and growth scenarios.

## 12. Cloud Service Mapping: Conceptual Overview

Providers offer diverse products with varying regional availability and feature sets. The table below is a **starting point for research, not a 1-to-1 equivalence chart or guaranteed feature matrix across all regions**.

| Capability | AWS (Example) | Azure (Example) | Google Cloud (Example) |
| --- | --- | --- | --- |
| L4 TCP/UDP load balancing per product | Network Load Balancer | Azure Load Balancer | Network Load Balancer (passthrough/proxy variants) |
| L7 HTTP/HTTPS load balancing | Application Load Balancer | Application Gateway; Azure Front Door for certain edge/global scenarios | Application Load Balancer (regional/global variants) |
| L7 web application protection | AWS WAF integrated on supported services | WAF on Application Gateway/Front Door per SKU/config | Cloud Armor with compatible LBs |
| Global or edge traffic management | CloudFront, Global Accelerator, or appropriate DNS/routing | Azure Front Door, Traffic Manager, and related services | Global external Application Load Balancer, Cloud CDN, Cloud DNS per design |
| Private/internal traffic | Internal LBs by type and VPC | Internal Load Balancer / private Application Gateway per capability | Internal Application/Network Load Balancer per product |

Notes:

- **AWS:** Application Load Balancer is the standard L7 option for HTTP/HTTPS and rich routing features; Network Load Balancer serves L4 protocols/targets. Do not assume WAF rules, gRPC, or TLS features behave identically across both.
- **Azure:** Azure Load Balancer and Application Gateway address different layers; Azure Front Door targets edge/global web scenarios. Private/public behavior and WAF integration depend on SKU/version and setup.
- **Google Cloud:** offers proxy and passthrough variants of Application/Network Load Balancers in regional and global scopes with distinct capabilities. Read the exact LB mode, protocol support, and data-path docs carefully.

Before committing, build a checklist covering **listener protocols, gRPC/WebSocket/HTTP/3, backend target types, cross-zone/cross-region behavior, TLS, WAF, source IP preservation, health checks, quotas, observability, private connectivity, SLAs, and cost** for the exact SKU in your target region.

## 13. Workflow for Choosing L4 vs. L7 from Business Requirements

### Step 1 — Inventory Entry Points

For each client type, document traffic protocol, user population, data sensitivity, and network reachability. For example, a scheduling app may have a public HTTPS API, a staff-restricted admin web portal, and an internal TCP telemetry service. Never assume all three belong behind one frontend.

### Step 2 — Lock In Required Entry-Point Features

Do you need host/path routing? WAF, HTTP redirects, auth, rate limiting, canary traffic splitting, mTLS, or HTTP metrics? If any L7 capability is mandatory, place an L7-aware component at the point where it is enforced.

### Step 3 — Define TLS and Network Boundaries

Where do certificates live, is LB-to-backend traffic encrypted, do backends sit in private subnets without public IPs, and what sources do firewalls permit? If TLS must reach the application directly, design L4 passthrough or L7 re-encryption per platform support and security requirements.

### Step 4 — Design Reliability and Operations

Define health checks, timeouts, draining, zone/region count, all-backends-unhealthy fallback behavior, retry policies, and rollback plans. Assign clear ownership for certificates, routing rules, target updates, and incident response.

### Step 5 — Benchmark Capacity and Estimate Total Cost

Test meaningful load dimensions: RPS, concurrent connections, streaming/long-lived requests, error rates, cross-zone traffic, response sizes, and scale-out lag. Compare total architecture cost, not just LB hourly rates.

### Step 6 — Record the Architecture Decision

Write an **ADR** (Architecture Decision Record) documenting context, options, rationale, consequences, test scenarios, and review triggers. Example title: "Use public L7 LB for Booking HTTPS API and private L4 LB for TCP telemetry."

### Reference Decision Tree

~~~mermaid
flowchart TD
    START["New entry point"] --> HTTP{"Does traffic require HTTP awareness?"}
    HTTP -- "No: TCP/UDP" --> L4["Evaluate L4 LB and protocol support"]
    HTTP -- "Yes" --> RULE{"Need host/path routing, WAF, HTTP features?"}
    RULE -- "Yes" --> L7["Evaluate L7 HTTP LB / gateway"]
    RULE -- "No" --> SIMPLE["Evaluate both L4 passthrough and simple L7"]
    L4 --> VERIFY["Verify TLS, health, network, HA, quotas, cost"]
    L7 --> VERIFY
    SIMPLE --> VERIFY
    VERIFY --> ADR["Write ADR and run validation tests"]
~~~

This tree provides directional guidance. It does not replace protocol-specific testing, compliance reviews, or technical documentation for your chosen service.

## 14. Practice Exercise: Designing Entry Points for a Scheduling Platform

**Assumed scenario:** A company deploys a scheduling application and admin portal to the cloud across two availability zones. Components:

- **Web frontend:** HTTPS with cacheable images and static assets.
- **Booking API:** REST HTTPS requiring <code>/api/*</code> endpoints, 600 RPS peak, p95 under 300 ms, and 99.9% valid transaction success over 30 days.
- **Admin API:** HTTPS on <code>admin.example.com</code>, accessible only to authenticated staff with audit logging required.
- **Telemetry collector:** proprietary TCP protocol with long-lived connections, restricted to corporate network sources.
- **Backends:** stateless API across two zones, managed database, and queue workers; each API instance sustains 120 RPS in baseline assumptions.
- **Constraints:** Booking flow must survive a single-zone failure and protect customer data in transit; operations team is small.

These numbers are **exercise inputs**, not guaranteed capabilities from any provider.

### Task 1 — Select Load Balancer Types

Propose entry points for each flow. For Web/Booking/Admin, explain why L7 helps with host/path rules, HTTP telemetry, and WAF. For TCP telemetry, explain when a private L4 LB suffices and why HTTP parsing is unnecessary.

### Task 2 — Draw Network Topology and TLS Boundaries

Sketch public frontends, private backends, two AZs, database paths, corporate network access, and the internal TCP entry point. Mark TLS termination locations; if LB → backend uses TLS, specify backend verification. Explain how to ensure the Admin API is not inadvertently exposed to the open Internet just because it sits behind a public LB.

### Task 3 — Size Capacity and Plan Failover

At 600 RPS and 120 RPS/instance sustained, compute the minimum instance count when all instances are healthy. Then propose counts across two AZs so surviving capacity carries full load with reasonable headroom if one zone fails. Evaluate database limits, autoscaling lag, and cost.

### Task 4 — Design Health Checks and Deployments

Define health checks for the Booking API and TCP collector. Specify readiness, liveness, timeouts, draining, and behavior when too few healthy backends remain. Describe how to roll out a new API version without dropping active requests beyond acceptable limits.

### Task 5 — Build a Test Suite

| Test | Condition | Evidence to Collect |
| --- | --- | --- |
| HTTP routing | Call <code>/api/*</code>, <code>/static/*</code>, and admin host | Accurate routing; unmatched hosts/paths hit safe default |
| TLS & client IP | Call through CDN/L7 with spoofed IP headers | Valid TLS; backend resolves real client IP via trusted proxies |
| Backend failure | Terminate one registered API instance | Health check ejects failed target; traffic shifts within budget |
| Zone failure | Simulate single-zone outage in controlled test | Error rate, p95, capacity, and recovery time meet SLO/RTO targets |
| Long-lived TCP | Hold telemetry connections open during rolling deploy | Observe resets, timeouts, reconnects, and message loss/duplication |
| Request retries | Repeat booking POST when response is interrupted | No duplicate bookings created; idempotency proven |
| Load & scale | Run 600 RPS then spike for fixed window | CPU, p95, 5xx, connection count, DB saturation, and scale lag |
| Security | Attempt direct backend access and unauthorized Admin API calls | Blocked by network/auth; audit logs capture events properly |
| Cost observation | Generate controlled test load; measure requests/bytes/connections | Basis to project LB, WAF, data transfer, and logging spend |

### Task 6 — Review Against Six Well-Architected Pillars

| Pillar | Entry-Point Evaluation Questions |
| --- | --- |
| **Operational Excellence** | Are IaC, automated target updates, dashboards, runbooks, rollbacks, and certificate owners in place? |
| **Security** | Do TLS, WAF, client IP handling, auth, network boundaries, and header policies align with trust boundaries? |
| **Reliability** | Are backends health-checked with draining, sufficient single-zone-loss capacity, and recovery plans? |
| **Performance Efficiency** | Are decisions backed by tests of connections, RPS, p95/p99, streams, quotas, and scale-out? |
| **Cost Optimization** | Are LB, request/byte, cross-zone, WAF, logging, and redundant backend costs all accounted for? |
| **Sustainability** | Are excessive idle backends, duplicate logs, and unnecessary data transfers avoided? |

### Suggested Solution Direction

A sensible design uses a **public L7 HTTP LB** for Booking/Web configured with TLS, host/path routing, and appropriate web protection; an **Admin entry point** with strict authentication and restricted access scope; and a **private L4 TCP LB** for the collector reachable only from the corporate network. Stateless API instances run across two AZs with private backend access and tuned health checks.

At 120 RPS/instance, the theoretical minimum with all instances healthy is 5 instances. If one surviving AZ must carry all 600 RPS after an outage, a two-AZ layout needs **at least 5 instances per AZ** under baseline assumptions, plus headroom validated by load testing. Verify database load and autoscaling speed, as API capacity alone does not represent full-system capacity.

This design is only acceptable once **the actual cloud service's features** support every requirement and tests confirm operational targets. Alternatives using a dedicated CDN/edge, API gateway, or stricter Admin isolation may also fit depending on risk tolerance and requirements.

## 15. Common Pitfalls

**1. Picking a "Network Load Balancer" just because it says network.** Inspect actual protocols, layers, target types, TLS, client IP behavior, and routing; never infer capabilities from marketing names.

**2. Assuming L4 is always faster or cheaper than L7.** Latency and cost depend on implementation, traffic mix, TLS, rules, caching, data transfer, and backend architecture. Measure them.

**3. Expecting L4 to route by HTTP path during TLS passthrough.** A component that cannot decrypt HTTP cannot apply URL rules; place L7 where decryption is permitted or adjust requirements.

**4. Using sticky sessions as a substitute for state architecture.** When an instance dies, in-RAM sessions disappear; design explicit state persistence and recovery.

**5. Declaring an app healthy just because a TCP health check sees an open port.** An open port does not prove business transactions succeed; add SLIs and functional checks.

**6. Forgetting connection draining and idle timeouts.** Rolling deployments or WebSocket/gRPC streams can drop abruptly.

**7. Leaving backends publicly reachable because a WAF sits on the frontend.** Block WAF/LB bypass paths via network policies, routing, and authentication.

**8. Trusting every X-Forwarded-For value.** Clients can spoof headers; trust only configured proxy chains.

**9. Treating multiple backends as sufficient HA.** Capacity after zone loss, databases/queues, DNS, and regional failures still require explicit design.

**10. Overlooking limits of long-lived connections or HTTP/2 multiplexing.** HTTP request counts alone fail to predict connection counts, distribution skew, and resource saturation.

**11. Enabling uncontrolled multi-layer retries.** Can amplify load and duplicate mutations; enforce timeouts, backoff, and idempotency.

**12. Copying a reference diagram without documenting assumptions.** Regions, protocol support, target types, and cloud features vary; ADRs and tests clarify when decisions must change.

## 16. Pre-Production Deployment Checklist

- [ ] Inventoried all entry points and classified HTTP/HTTPS, gRPC, WebSocket, TCP, or UDP.
- [ ] Selected L4/L7 based on required routing features; verified capabilities on the exact cloud service/SKU.
- [ ] Defined public/private endpoints, network zones, subnets, routes, firewalls, and permitted sources.
- [ ] Documented TLS termination/passthrough/re-encryption, certificates, and backend identity verification.
- [ ] Configured host/path routing, rule precedence, default actions, and HTTP protections as needed.
- [ ] Defined trusted proxies, forwarded header handling, and accurate client identity auditing.
- [ ] Implemented health checks, readiness, timeouts, draining, and fallback when backends are exhausted.
- [ ] Verified surviving capacity after instance/zone loss meets reliability targets.
- [ ] Tested long-lived connections, HTTP/2/gRPC/streaming, and UDP behavior where used.
- [ ] Defined retries, redirects, rate limits, write idempotency, and load caps.
- [ ] Configured metrics, access/error logs, and alerts for error rates, latency, target health, and quotas.
- [ ] Estimated total cost across LB, standby backends, WAF, networking, and logging.
- [ ] Created IaC, rollback plans, owners, runbooks, load/failure test results, and ADRs for key choices.

Both L4 and L7 are tools for building reliable entry points, each serving different needs. **L4 makes decisions primarily on transport connections or flows; L7 understands and processes application-layer requests.** The right choice matches your workload's protocols, security policies, SLO targets, release model, and cost profile. A clean diagram must be backed by measurements and failure tests proving the system behaves as designed.
