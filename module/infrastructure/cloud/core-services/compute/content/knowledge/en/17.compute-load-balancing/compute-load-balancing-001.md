# Layer 4 and Layer 7 Load Balancing for Workload Groups

When an application runs across multiple virtual machines, containers, or compute groups, the system must distribute traffic to the appropriate instances. Load balancing helps distribute load, remove unhealthy nodes from the serving path, support horizontal scaling, and provide a stable access endpoint for users. However, Layer 4 and Layer 7 load balancers process traffic at different levels, so the choice cannot be made based solely on the service name or machine count.

Layer 4 (L4) operates primarily on connection information and transport protocols such as TCP or UDP. Layer 7 (L7) understands application protocols such as HTTP, HTTPS, WebSocket, or gRPC when supported. L4 is typically suited for TCP/UDP streams requiring high throughput, low latency, or independence from application payload content. L7 is suited when routing must be based on hostname, path, headers, cookies, or request attributes.

This lesson explains how both types of load balancing work, how to choose between them for different workload groups, and how to configure health checks, TLS, session persistence, draining, observability, and security. After this lesson, you will be able to:

- Distinguish the inspection points and traffic distribution behavior of L4 versus L7.
- Choose a load balancer type for web/API, databases, gRPC, WebSocket, UDP, and background processing workloads.
- Select distribution algorithms and session policies aligned with application characteristics.
- Design health checks, connection draining, and rollouts to avoid sending traffic to failing nodes.
- Understand how TLS termination, client IP, proxy headers, and network policies affect architecture.
- Evaluate the scalability, availability, and cost of a cloud load-balancing tier.

## 1. Where Does a Load Balancer Sit in a Compute Architecture?

A load balancer typically sits in front of a group of backends. Users or systems call a stable address; the load balancer selects a healthy backend and forwards traffic to it. A backend can be a VM, container, pod, service, or a managed group of machines.

~~~mermaid
flowchart LR
    C["Client / User"] --> E["Service endpoint"]
    E --> LB["Load balancer"]
    LB --> A["Backend A"]
    LB --> B["Backend B"]
    LB --> D["Backend C"]
    A --> DB[("Shared database / storage")]
    B --> DB
    D --> DB
~~~

A load balancer can be a managed service from a cloud provider, a proxy running on a VM/container, or a component within an orchestration platform. Regardless of the implementation, common responsibilities include:

- Receiving traffic at a published address and port.
- Selecting a backend based on an algorithm and health state.
- Forwarding connections or requests to the backend.
- Tracking timeouts, connection errors, and health checks.
- Applying TLS, routing, logging, or rate-limiting policies if supported by the product.

A load balancer does not automatically make an application scalable. If all backends share a single database that is already saturated, adding more backends can overload the database even faster. Load balancing must be paired with capacity planning, autoscaling, caching, queues, database scaling, and system observability.

## 2. How Does Layer 4 Load Balancing Work?

L4 processes traffic based on transport- and network-layer information, typically including source/destination IP addresses, source/destination ports, and the TCP or UDP protocol. For TCP, the load balancer selects a backend when a connection is established and then forwards data for that connection to the chosen backend.

L4 does not need to understand HTTP content. A single TCP connection can carry multiple HTTP requests via keep-alive; if L4 only distributes per connection, requests on the same connection still go to the same backend. This differs from an L7 proxy, which can terminate the HTTP connection and choose a backend for each request.

### Key Characteristics

- Operates at the connection or flow level without needing to parse paths, headers, or application payloads.
- May support TCP and UDP; specific protocol coverage depends on the product.
- Typically has lower processing overhead and is suited for high traffic volumes.
- Can preserve or pass source IP information depending on platform mechanisms.
- Suited for custom protocols, TCP-layer database proxies, game servers, or non-HTTP services.

### Common Forwarding Modes

- **Proxy/connection termination:** The load balancer accepts a connection from the client and opens a separate connection to the backend. It manages both sides of the connection.
- **Direct server return (DSR) or near pass-through routing:** Some solutions forward packets to the backend in a way that lets the backend reply directly to the client or keeps the data path less proxy-heavy. This model requires specific network and IP address configurations.
- **NAT-based forwarding:** Rewrites addresses or ports in packets to forward to a backend; the return path must pass through the corresponding mechanism to maintain connection state.

Not every cloud L4 load balancer supports every mode. Check product documentation for source IP preservation, PROXY protocol, cross-zone balancing, connection limits, and how return traffic is handled.

### When Should You Use L4?

- Non-HTTP TCP services, such as certain database services or internal protocols.
- UDP workloads such as DNS, game traffic, or telemetry when the platform supports that protocol and requirement.
- Services needing high throughput without request-content routing.
- Applications that handle TLS themselves or require TLS pass-through so backends terminate encryption.
- Long-lived connection streams or custom protocols that an L7 proxy does not fully support.

L4 does not inherently know which API a user is calling, which request needs which backend, or which header indicates a tenant. If you need routing based on HTTP content, consider L7.

## 3. How Does Layer 7 Load Balancing Work?

An L7 load balancer acts as a proxy that understands application protocols. For HTTP/HTTPS, it can terminate the client connection, read the hostname, path, method, headers, or cookies, and decide the backend. When forwarding, the proxy typically establishes a separate connection to the backend.

For example, the same service endpoint can route:

- `api.example.com/orders` to the order processing group.
- `api.example.com/catalog` to the catalog group.
- `admin.example.com` to the admin UI group.
- `/v2/` to a new API version during a canary phase.

### Common Capabilities

- **Host-based routing:** Selects a backend by hostname.
- **Path-based routing:** Selects a backend by URL path.
- **Header or method routing:** Selects a backend based on HTTP headers or methods if supported by the product.
- **Cookie/session affinity:** Keeps a client or session on the same backend for a period of time.
- **TLS termination:** Decrypts TLS at the proxy to inspect HTTP and apply application policies.
- **HTTP-aware health check:** Sends requests to a specific endpoint and checks status codes or response bodies depending on product capabilities.
- **Request-level policy:** Applies redirects, header rewrites, request limits, or protection rules if supported.

Exact capabilities vary across providers and products. Some features such as WAF, gRPC routing, WebSocket, HTTP/3, or response body inspection may be separate features or require additional configuration.

### TLS Termination and Backend Encryption

When L7 terminates TLS, the client establishes TLS with the load balancer. The proxy decrypts the request, applies routing, and can establish a new TLS connection to the backend. You should clearly decide on:

- **TLS termination at the load balancer:** Simplifies certificate management on backends, though traffic between the load balancer and backend must be protected by a private network or continued TLS if security requirements demand it.
- **TLS re-encryption:** The client encrypts to the load balancer and the load balancer re-encrypts to the backend. Requires managing certificates, verifying backend identity, and maintaining the trust chain.
- **TLS pass-through:** The load balancer forwards the encrypted stream without decrypting its content. In this mode, it cannot route by path/headers inside encrypted HTTP; this behavior is typically closer to L4 load balancing.

Listener naming and TLS features vary by platform. Verify exactly where TLS is terminated and where data is in plaintext.

## 4. Comparing L4 and L7

| Criterion | L4 | L7 |
|---|---|---|
| Information used to select backend | IP, port, protocol, flow/connection | Host, path, method, header, cookie, and application context |
| Distribution unit | Typically a connection or flow | Can be a request, stream, or session depending on protocol |
| Common protocols | TCP, UDP, and supported transport-layer protocols | HTTP, HTTPS, WebSocket, gRPC, and supported application protocols |
| Inspect HTTP content | No | Yes, when the proxy terminates/decrypts the protocol |
| TLS | Can pass through or terminate TLS depending on product | Typically terminates TLS to inspect HTTP; can re-encrypt to backends |
| URL-based routing | No | Yes |
| Processing complexity | Generally lower | Higher due to protocol parsing and policy enforcement |
| Observability | Connections, bytes, flows, resets, and timeouts | Can include requests, status codes, latency, selected host/path, and headers |
| Suitable scenarios | TCP/UDP, custom protocols, high-volume streams | Web, APIs, multi-service routing, and HTTP policies |

Do not conclude that L4 is always faster in every scenario or that L7 always has unacceptable latency. Actual performance depends on instance size, connection count, TLS, enabled features, request size, algorithms, and load. Benchmark with representative traffic.

## 5. Choosing a Load Balancer Type for Each Workload Group

| Workload Group | Typically Suitable Choice | Rationale and Checks Needed |
|---|---|---|
| Websites and REST APIs | L7 | Requires host/path routing, TLS termination, HTTP health checks, and request metrics |
| Multiple HTTP microservices | L7 or L7 combined with a service mesh | Can route by host/path/header; avoid creating too many proxy hops |
| TCP-based databases | L4 or a dedicated database-aware proxy | Needs to preserve TCP connections; check connection limits, timeouts, and failover |
| SSH/RDP or custom TCP protocols | L4 or a dedicated access gateway | Does not need HTTP parsing; must restrict access sources and session duration |
| DNS or UDP services | L4 with UDP support | Check timeouts, flow handling, packet size, and statefulness |
| Game servers | L4 or a specialized solution | May use UDP/TCP, long sessions, and low-latency requirements |
| WebSocket | L7 with WebSocket support or L4 | L7 can apply HTTP routing on upgrade; requires appropriate timeouts and connection draining |
| gRPC | L7 with HTTP/2/gRPC support or L4 | L7 enables service/method routing when supported; L4 preserves the TCP stream |
| GPU inference APIs | L7 is often useful; L4 can be used at the front tier | L7 can route by endpoint/model/version; must account for request duration and streaming |
| Batch workers reading queues | Queues and worker autoscaling are usually the primary mechanism | An HTTP load balancer does not replace message distribution and acknowledgement |

### Stateless and Stateful Workloads

With stateless workloads, any healthy backend can handle the next request because the necessary state is stored outside the instance or carried with the request. This is the easiest case to load balance and autoscale.

With stateful workloads, sessions or data may be tied to a specific backend. There are three approaches:

1. Externalize state to a shared system such as a database, cache, or session store.
2. Use consistent hashing or key-based routing so the same group of data generally routes to the same backend.
3. Use session affinity when the application genuinely requires pinning a client to a backend for a limited period.

Session affinity does not replace durable storage design. If a backend fails or is scaled in, sessions may be lost or users may have to log in again. For critical systems, design session recovery capabilities rather than relying entirely on sticky sessions.

## 6. Backend Distribution Algorithms

A load balancer can use various algorithms. Exact names and behaviors depend on the product.

### Round Robin

Selects backends sequentially in rotation. Suitable when backends have equivalent capacity and requests have relatively uniform cost. If requests vary greatly in processing time or backends have different specs, round robin can overload a node.

### Weighted Round Robin

Distributes based on weights. Larger or benchmarked backends can receive a higher proportion of requests. Weights should be based on measured capacity and updated when backend configurations change.

### Least Connections

Prefers backends with fewer active connections. Suitable when connections have varying lifetimes, though connection count does not always equate to workload. An idle connection may persist for a long time, while a short request may consume heavy CPU.

### Least Outstanding Requests

At L7, some proxies can choose the backend with the fewest in-flight requests. This approach is better suited when request processing times vary, though concurrency limits and state-tracking overhead must be considered.

### Client or Key Hashing

Hashes the client address, cookie, or an application key to select a consistent backend. This can support cache locality or session affinity. If client IP is used, many users behind NAT may be grouped onto the same backend. Consistent hashing reduces the number of remappings when backends are added or removed, but does not eliminate the need to handle node failures.

### Random and Power of Two Choices

Selects randomly or picks two backends and chooses the one with lower load. Some systems use variants of this to avoid maintaining strict cluster-wide ordering. Check the product's actual algorithm and evaluate through benchmarking.

| Algorithm | When Suitable | Risks to Watch |
|---|---|---|
| Round robin | Homogeneous backends, roughly uniform requests | Does not reflect current load |
| Weighted | Backends with differing capacities | Stale weights skew load |
| Least connections | Long-lived connections where count roughly reflects load | Idle connections can distort the signal |
| Least outstanding requests | HTTP requests with uneven processing times | Requires proxy tracking of in-flight requests |
| Hash/consistent hash | Affinity or locality needed | Hot keys/clients can overheat one backend |

## 7. Health Checks: Sending Traffic Only to Healthy Backends

Health checks help the load balancer know whether a backend can receive traffic. Distinguish between:

- **Liveness:** Is the process alive and able to keep running?
- **Readiness:** Is the backend ready to accept new requests?
- **Dependency health:** Are databases, caches, or dependent services functioning?

A load balancer health check should generally test readiness at a level sufficient to confirm the backend can serve traffic. If it checks every dependency too aggressively, a transient issue in a shared dependency can cause all backends to be marked unhealthy simultaneously. That can make an outage worse.

A health check must specify:

- Protocol and port to check.
- HTTP path if L7.
- Interval between checks.
- Timeout for each check.
- Consecutive failures before marking unhealthy.
- Consecutive successes to return a backend to healthy.
- Accepted status codes or response conditions.

Parameters should reflect startup time and workload stability. Timeouts that are too short cause false positives; timeouts that are too long allow failing backends to keep receiving traffic longer.

### Health Checks Are Not Comprehensive Audits

A readiness endpoint should be lightweight, stable, and free of side effects. It should not run heavy queries or probe a long list of dependencies on every check. Deeper checks can be performed by a separate monitoring system.

For L4, a health check might only verify a TCP connection to the port. A successful TCP accept does not prove the application handles requests properly. If you need to check HTTP logic, use an L7 health check or application-level synthetic monitoring.

## 8. Session Persistence, Long-Lived Connections, and Draining

### Sticky Sessions

Sticky sessions ensure requests from the same client or session return to the same backend. This can be implemented via load-balancer-issued cookies, application cookies, or hashing on client attributes.

Enable sticky sessions only when there is a clear reason. They can skew load distribution if one backend holds more active sessions, complicate scale-in, and reduce redistribution after failures. A shared session store generally reduces reliance on affinity.

### Long-Lived Connections

WebSocket, gRPC streaming, SSH, and some TCP protocols maintain long-lived connections. Once a connection is bound to a backend, the load balancer usually cannot migrate the remainder of that connection to another backend if the target node fails. Applications need reconnect mechanisms, retries with backoff, and appropriate session recovery.

Check idle timeout, maximum connection lifetime, and keepalive across the client, load balancer, intermediate proxies, and backend. Mismatched timeouts can cause connections to close unexpectedly.

### Connection Draining and Deregistration Delay

During maintenance or scale-in, do not remove a backend immediately while it is still processing requests. A graceful removal flow typically includes:

1. Marking the backend to stop receiving new connections or requests.
2. Waiting for in-flight requests to complete within the configured drain period.
3. Allowing the application to finish work, flush data, and close connections.
4. Terminating the instance or container after the timeout expires.

If a workload has requests lasting longer than the drain timeout, decide whether forced termination is acceptable and design client retries. For queue workers, use appropriate visibility timeouts, acknowledgements, and graceful shutdown rather than relying solely on HTTP connection draining.

## 9. TLS, Certificates, and Traffic Protection

With L7 HTTPS, the load balancer typically manages certificates for published hostnames. Track expiration dates, automate renewal where possible, and ensure every required hostname has an appropriate certificate.

When re-encrypting to backends:

- Verify the backend certificate against the trust chain and hostname/SAN.
- Use organization-approved TLS versions and cipher suites.
- Protect private keys and restrict access permissions.
- Consider mutual TLS if two-way authentication between the proxy and backend is required.
- Do not log tokens, cookies, Authorization headers, or sensitive payloads.

With L4 TLS pass-through, the backend is responsible for terminating TLS and managing certificates. The load balancer cannot inspect encrypted payloads to route by HTTP path. If using TLS termination at L4, verify exact capabilities; provider listener terminology may not map one-to-one with OSI classifications.

## 10. Client IP Preservation and Proxy Headers

Applications may need the original client IP for auditing, rate limiting, or policy enforcement. When a load balancer proxies a connection, the backend usually sees the proxy's address instead of the client's.

Common ways to pass this information:

- **Source IP preservation:** The backend receives the original source IP at the network layer if the architecture supports it.
- **PROXY protocol:** The proxy prepends client IP/port metadata at the start of the connection; the backend must be configured to parse this protocol.
- **X-Forwarded-For:** An HTTP header containing the client address and proxy chain; commonly used with L7.
- **Forwarded header:** A standardized HTTP header structuring proxy information.

Do not trust `X-Forwarded-For` from arbitrary Internet clients. Only accept headers overwritten or appended by trusted proxies, clearly identify which hops are trusted, and strip forged headers sent by clients. If backends are directly reachable from the Internet, attackers can spoof headers and falsify logs or IP policies.

## 11. Load Balancing for VMs, Containers, and Serverless

| Compute Platform | Typical Integration Pattern | Key Considerations |
|---|---|---|
| VM | L4/L7 listener forwarding to a target group or backend pool | Health checks, instance registration, zones, draining, and autoscaling |
| Container | L7 ingress/gateway or L4 service depending on platform | Pod readiness, endpoint discovery, rollouts, service mesh, and node draining |
| Kubernetes | Service, Ingress, or Gateway API combined with controller/cloud LB | Distinguish node, pod, and application health; avoid unnecessary double load balancing |
| Serverless | HTTP gateway or managed load balancer supporting function/service targets | Concurrency quotas, cold starts, timeouts, payload limits, and retries |
| Batch/queue worker | Message broker distributing jobs to consumers | Backpressure, visibility timeout, retries, dead-letter queues, and queue-depth autoscaling |

### VMs and Autoscaling Groups

When a new VM is created, the system registers it with the backend pool and sends traffic only after health checks pass. During scale-in, instances should be deregistered and drained before termination. Integration between autoscaling and the load balancer must handle slow-booting or boot-failing VMs.

### Containers and Kubernetes

When a pod is created, its readiness probe determines whether it is added to serving endpoints. Ingress or Gateway can route HTTP to services; an L4 Service can distribute TCP/UDP to pods. Understand which load balancer the controller provisions and how many proxy layers traffic traverses.

If you have a cloud L7 load balancer, an ingress controller, and a service mesh simultaneously, each layer adds hops, health checks, timeouts, and logs. A multi-tier architecture can be useful for security boundaries or routing, but clearly define each layer's responsibilities and avoid duplicate configurations.

### Serverless

Serverless platforms typically use a managed gateway or load balancer to receive HTTP requests and invoke functions or services. Check timeouts, payload size, concurrency quotas, cold starts, retries, and request limits. If requests are long-running or streaming, verify that the platform supports that protocol and session duration.

### Background Workers

Do not put an L4/L7 load balancer in front of every type of workload. Batch workers usually pull jobs from a queue. The message broker handles distribution, acknowledgement, retries, and backpressure. Worker autoscaling can be driven by queue depth, age of the oldest message, or completion rate.

## 12. Multi-Tier L4 and L7 Design

You can combine L4 and L7 when separating the network entry point from application routing:

~~~mermaid
flowchart TD
    C["Client"] --> L4["L4: TCP/UDP entry"]
    L4 --> L7["L7: HTTP gateway"]
    L7 --> API["API service"]
    L7 --> WEB["Web service"]
    L7 --> ADMIN["Admin service"]
    API --> DATA[("Shared data services")]
    WEB --> DATA
    ADMIN --> DATA
~~~

For example, L4 provides a stable TCP address or distributes connections across multiple L7 proxies; L7 performs TLS termination, host/path routing, and HTTP policies. This approach can improve scalability or establish clear network boundaries, though it also adds latency and monitoring points.

When designing multiple tiers, determine:

- Which tier owns the public IP and receives Internet traffic?
- Which tier terminates TLS?
- Which tier records the client IP and generates proxy headers?
- How does the front tier's health check verify the next tier?
- How are timeouts and retries configured to prevent retry storms?
- How many hops exist between the client and the backend?
- If one tier fails, does the system still have a fallback serving path?

## 13. Availability and Scalability

Load balancers must be deployed with redundancy according to the provider's architecture or across multiple instances/zones. Consider:

- Distributing backends across multiple availability zones if the workload supports it.
- Independent health checks for each backend and monitoring of the load balancer itself.
- Capacity limits on connections, requests/second, TLS handshakes, and bandwidth.
- Proxy scaling capability as connections or traffic surge.
- Redundancy for DNS, certificates, target registration, and the control plane.
- Impact when a zone loses connectivity or a group of backends becomes unhealthy simultaneously.

### Cross-Zone Load Balancing

Some platforms allow a load balancer in one zone to send traffic to backends in another zone. This improves distribution when one zone is short on backends, but increases cross-zone traffic, latency, and data transfer costs. Weigh cluster-wide even distribution against zone-local balancing.

### Autoscaling and Load Balancing

Load balancers typically expose metrics such as request count, active connections, target response time, or unhealthy host count. Autoscalers can use these metrics to scale capacity up or down. However:

- Choose metrics appropriate for the workload; request count may not reflect processing cost if requests vary in weight.
- Configure cooldown or stabilization windows to avoid constant scaling oscillation.
- Account for startup time, image pulls, warm-up, and readiness of new backends.
- Keep spare capacity while old nodes are draining.
- Ensure downstream dependencies like databases and queues can handle the increased load.

The load balancer distributes existing load; the autoscaler changes the amount of resources. Both mechanisms complement each other but have distinct responsibilities.

## 14. Load Balancer Observability and Troubleshooting

Monitor metrics from both the load balancer and backends:

| Metric | Meaning |
|---|---|
| Request/connection count | Traffic received and distributed |
| Active connections | Current open connections; useful for TCP/WebSocket |
| Healthy/unhealthy targets | Number of backends eligible to receive traffic |
| Backend response time | Time taken by backends to respond per product definition |
| 4xx/5xx or resets | Client errors, backend errors, or proxy errors |
| Rejected/queued connections | Capacity exhaustion or connection limit reached |
| TLS handshake failures | Certificate, protocol, or TLS resource issues |
| Bytes in/out | Bandwidth and data transfer trends |
| Distribution per target | Detects backends receiving skewed load |

When an incident occurs, follow this sequence:

1. Determine the scope: entire service, one zone, one hostname/path, or one backend.
2. Check listeners, rules, certificates, and load balancer health status.
3. Check healthy backend count, health check results, and target registration.
4. Inspect access/error logs, timeouts, resets, and status codes.
5. Test the backend directly on the management network to separate proxy issues from application issues.
6. Check dependencies, capacity, autoscaling, and recent changes.
7. Recover by fixing rules, restoring healthy backends to the pool, or rolling back identified changes.

Do not remove a backend from the pool solely because a single metric spikes temporarily without understanding the cause. Overly sensitive health checks can trigger cascading removal of all backends at once; have fail-open/fail-closed behavior aligned with the product and service risk profile.

## 15. Security for the Load-Balancing Tier

- Expose only required listeners and protocols.
- Restrict administrative access sources; do not expose internal management ports on public listeners.
- Use security groups/firewalls between the load balancer and backends to accept traffic only from valid proxy sources.
- Protect backends from direct access if the architecture requires all requests to pass through L7 policies or a WAF.
- Manage TLS certificates, private keys, rotation, and access permissions.
- Trust proxy headers only from authenticated proxies or trusted network ranges.
- Do not write credentials, tokens, cookies, or sensitive payloads to access logs.
- Use rate limiting, WAF, or DDoS protection where appropriate and monitor for false positives.
- Audit changes to listeners, routing rules, target groups, and certificates.

L7 can support WAF or request inspection, but it does not replace application security, identity, authorization, and network segmentation. L4 also requires protection against floods, connection exhaustion, and unauthorized traffic sources.

## 16. Example: Traffic Distribution for an Order System

An order system has three workload groups:

- A website and REST API receiving HTTPS from users.
- An internal TCP service receiving connections from a legacy warehouse system.
- Workers processing email sending and status update jobs from a queue.

An appropriate design might include:

1. **L7 public load balancer** receiving HTTPS, managing certificates, routing `/api/orders` to the API service and `/` to the web service.
2. **L4 internal load balancer** distributing TCP connections from the warehouse system to the corresponding backend group within the private network.
3. **Message queue** distributing jobs to email/status workers; an autoscaler adjusts worker count based on queue depth and oldest message age.

For the API, the team uses a readiness health endpoint, monitors p95 latency and 5xx errors, and drains backends before deployment. For the internal TCP service, the team monitors active connections, resets, and timeouts; clients must reconnect when backends are replaced. For workers, the team uses acknowledgements and retries with backoff so jobs are not lost when a worker stops.

This design avoids forcing every workload type through a single mechanism. HTTP needs request-level routing, internal TCP needs connection forwarding, and background jobs need stateful message distribution.

## 17. Pre-Deployment Load Balancer Checklist

- [ ] Documented protocol, request types, connection lifetimes, and expected load.
- [ ] Selected L4, L7, or a combination based on routing and protocol-handling needs.
- [ ] Defined listeners, hostnames, ports, protocols, and backend pools.
- [ ] Distribution algorithm matches backend capacity and homogeneity.
- [ ] Health checks reflect readiness and are not overly sensitive to shared dependencies.
- [ ] Session affinity policy is explicit and justified.
- [ ] Timeouts, keepalives, maximum connection lifetimes, and draining are configured appropriately.
- [ ] TLS termination/pass-through/re-encryption strategy is clearly defined.
- [ ] Client IP and proxy headers are handled securely.
- [ ] Security groups, firewalls, and routes allow only necessary traffic flows.
- [ ] Backends have adequate capacity and are distributed across appropriate zones.
- [ ] Autoscaling does not oscillate or overload downstream dependencies.
- [ ] Metrics, logs, alerts, and incident runbooks are in place.
- [ ] Tested failover, unhealthy backends, deployments, and scale-in.

## 18. Practice Exercise

A compute platform has three services:

1. A customer-facing HTTP API requiring routing by hostname and path.
2. An internal TCP data-transfer service where each connection can last 45 minutes.
3. Asynchronous job workers where job volume spikes sharply by the hour.

Propose a distribution mechanism for each service and answer:

- Which service should use L7, and which is suited for L4?
- Why is a queue more suitable than an HTTP load balancer for job workers?
- How should health checks and connection draining be configured for the long-lived TCP service?
- How should the API handle TLS, client IP, and readiness?
- Which metrics help detect an overloaded backend or skewed distribution?

Hint: Use L7 for the API to route by host/path and perform HTTP readiness checks; use L4 for the TCP service if the protocol does not require payload inspection, while designing appropriate reconnects and long draining. Use a message queue with acknowledgement/retry for the workers. Monitor request/connection counts, active connections, healthy targets, p95 latency, errors/resets, queue depth, and oldest job age.

## Conclusion

L4 distributes traffic primarily by connection and transport protocol, making it suitable for TCP/UDP and workloads that do not require inspecting application content. L7 understands HTTP or supported application protocols, enabling routing by hostname, path, and headers as well as request-level policies. Choosing the right tier depends on protocol, workload statefulness, connection lifetime, TLS requirements, observability, and scaling model. Health checks, draining, network security, and client resilience determine whether load balancing keeps a service available in practice.
