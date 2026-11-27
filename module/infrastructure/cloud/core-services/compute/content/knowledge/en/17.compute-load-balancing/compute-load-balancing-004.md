# Load Distribution Algorithms and Connection Limits

A load balancer receives traffic from clients and distributes it to backends such as virtual machines, containers, or compute services. How backends are selected directly affects latency, resource utilization, fault tolerance, and scaling efficiency. If the algorithm is poorly suited, one machine can become overloaded while others sit idle; if connection limits are not sized properly, the load balancer or backends may reject requests even while aggregate CPU capacity remains available.

Load-balancing design must answer two questions: **which request goes to which backend** and **how many concurrent connections or in-flight tasks each layer is allowed to hold**. The answers depend on protocol, processing time, session state, connection lifetime characteristics, and cloud platform limits.

## 1. Load Balancing at L4 and L7

A load balancer can distribute traffic at different network layers:

- **Layer 4 (L4):** Decides based on transport metadata such as source/destination IP, port, and TCP/UDP protocol. L4 typically forwards connections or packet flows without needing to inspect HTTP content.
- **Layer 7 (L7):** Understands application protocols such as HTTP/HTTPS and can route by host, path, header, cookie, or request attributes.

| Characteristic | L4 | L7 |
|---|---|---|
| Routing information | IP, port, protocol, and flow | Host, path, header, cookie, method, or supported protocol content |
| Typical distribution unit | Connection/flow | Application-layer request or stream |
| Processing cost | Typically lower due to minimal payload inspection | Additional cost for parsing, TLS termination, policy, and routing |
| Capabilities | TCP/UDP forwarding, NAT, flow affinity | TLS offload, host/path routing, cookie affinity, header rewrites |
| Suitable use cases | Database proxies, TCP services, gaming/streaming, non-HTTP traffic | Web/APIs, HTTP microservices, routing by hostname or URL |

An important point: L4 typically picks a backend when creating a flow/connection. If a TCP connection is long-lived, traffic on that connection continues going to the same backend. L7 can select a backend per HTTP request, though behavior still depends on the protocol and proxy configuration. With HTTP/2 or HTTP/3, multiple requests/streams can be multiplexed over a single connection; never assume one connection equals one request.

## 2. Round Robin

**Round Robin (RR)** distributes each connection or request sequentially to backends in circular order. With three backends A, B, and C, the selection sequence might be A → B → C → A → B → C.

Advantages:

- Simple, easy to understand, and predictable.
- Distributes fairly evenly when backends are equivalent and requests have similar processing costs.
- Requires no complex connection counters beyond rotation state.

Limitations:

- Does not consider how busy each backend currently is.
- Requests with widely varying processing times can cause one backend to accumulate heavy work.
- If backends have different specs, splitting request counts evenly may not balance actual load.

RR works well when machines have equivalent capacity, requests are relatively uniform, and processing times are short. For workloads involving report generation, large uploads, or variable-cost queries, consider another algorithm.

## 3. Weighted Round Robin

**Weighted Round Robin (WRR)** assigns weights to each backend so higher-capacity machines receive a larger share of requests. If A has weight 5, B has weight 3, and C has weight 2, target distribution ratios are roughly 50%, 30%, and 20% over a sufficiently large cycle.

The target share of backend `i` can be estimated as:

\[
P_i = \frac{w_i}{\sum_{j=1}^{n} w_j}
\]

Where `w_i` is the weight of backend `i` and the denominator is the sum of weights of backends eligible to receive load.

For example, a machine group has two 8-vCPU instances and one 4-vCPU instance. You might start testing with weights 2:2:1 if benchmarks show throughput scales roughly in that ratio. Do not derive weights solely from vCPU count: performance also depends on CPU generation, RAM, cache, I/O, network limits, and application characteristics.

WRR is useful when backends have heterogeneous specs or for canary rollouts. You can assign a low weight to a new version, monitor errors and latency, and gradually increase it. When using weights for canaries, still maintain health checks, load limits, and clear rollback criteria.

## 4. Least Connections and Weighted Least Connections

**Least Connections** picks the backend with the fewest active connections. The idea is that a backend with fewer connections is more likely to have spare capacity. This algorithm fits better than RR when connection lifetimes vary significantly.

For example, A currently has 80 connections, B has 25, and C has 40. A new connection may be routed to B. However, connection count does not always reflect actual work: an idle connection may be much lighter than one running a heavy query.

**Weighted Least Connections** combines connection count with capacity weights. A common interpretation compares the ratio of current connections to weight; the backend with the lower ratio is preferred. Exact calculations vary by product, so check the load balancer's documentation.

Least Connections fits TCP connections with varying lifetimes or backends handling long-running requests. It may be ineffective if:

- HTTP/2 multiplexes many requests over a single connection.
- Backends hold many idle keep-alive connections.
- Some connections are very heavy while counted equally with lightweight ones.
- Connection counts across distributed load balancer nodes are not synchronized.

For HTTP/2, an L7 proxy may need an algorithm based on active requests/streams or application-layer load metrics rather than counting TCP connections alone.

## 5. Least Response Time and Adaptive Algorithms

**Least Response Time** favors backends with lower observed response times, often combined with connection counts or weights. The goal is to send more load to machines serving faster.

Adaptive algorithms can use multiple signals:

- Average response time or EWMA (Exponentially Weighted Moving Average).
- Active request count or queue depth.
- CPU/memory pressure or application metrics.
- Error rates, timeouts, and health status.
- Configured backend weights.

A conceptual model might compute a backend score:

\[
Score_i = \alpha \cdot Latency_i + \beta \cdot ActiveWork_i + \gamma \cdot ErrorPenalty_i
\]

The backend with the lowest score is preferred, subject to weights and health conditions. This is only an explanatory model; real products may use different formulas and signals.

Adaptive algorithms respond well to fluctuating load, but can oscillate if metrics are noisy or updated too aggressively. If all requests suddenly shift to the fastest machine, that machine can become overloaded and drop out of favor, causing traffic to swing back and forth. Use smoothing, rate-limit weight adjustments, and test under gradual backend degradation to prevent oscillation.

## 6. Random and Power of Two Choices

**Random** selects an eligible backend at random. With high request volumes and homogeneous backends, distribution converges toward uniform over time. Random is simple and avoids ordering overhead.

**Power of Two Choices** picks two backends at random and sends the request to the one with fewer connections or less active work. This significantly improves balance compared to pure random selection without needing to gather state from every backend on every decision.

This algorithm is useful in systems with many backends and heavy traffic. Result quality depends on metric freshness, how active work is defined, and whether candidate selection is uniform.

## 7. Hashing by Client, URL, or Business Key

Some workloads need the same client or data key to consistently reach the same backend. Hashing algorithms can provide that stability:

- **Source IP hash:** Hashes the source IP address to pick a backend. Many users behind NAT may share one IP, skewing distribution.
- **Consistent hashing:** Maps keys onto a hash ring to minimize key movement when nodes are added or removed.
- **URI/path hash:** Uses the URI or path to keep related requests on the same backend if supported by the product.
- **Header/cookie affinity:** Uses request attributes or cookies to maintain session affinity.

Hashing fits local caches, partitioned data, or legacy applications storing sessions in instance memory. However, affinity can hurt load balance when one client generates heavy traffic or a key becomes hot. When a backend fails or topology changes, keys may remap to other nodes; the application must handle cache misses and session recovery.

Do not use source IP hashing as an exact user-identification mechanism. One IP can represent thousands of clients behind NAT, proxies, or mobile networks; IP addresses can also change mid-session.

## 8. Session Affinity and Application State

Session affinity (sticky sessions) attempts to send requests from the same client to the same backend for a period of time. It is helpful when an application keeps sessions in local RAM or relies on unshared caches.

Drawbacks of sticky sessions:

- Load can skew if certain clients are much more active than others.
- A backend failure can lose sessions if state lives only in node RAM.
- Scale-in or topology changes can break affinity.
- Cookie affinity requires proper configuration of domain, secure flags, expiry, and data protection.

A more resilient design stores sessions in a shared store or uses protected stateless tokens. Then the load balancer can distribute freely and backends are easy to replace. If sticky sessions are unavoidable, set an appropriate TTL, test backend failures, and monitor per-node load distribution.

## 9. Understanding Connection Limits at Every Layer

A request can pass through multiple components, each with its own limits. There is no single "max connections" number for the entire system.

| Layer | Common Limits | Impact When Limit Is Hit |
|---|---|---|
| Client | Sockets, connection pools, ephemeral ports | Unable to open new connections or timeouts |
| Edge/load balancer | Concurrent connections, new connection rate, stream/request rate | Rejections, resets, queuing, or throttling depending on product |
| Proxy/gateway | Client connections, backend connections, workers/threads, buffers | Growing queues, 502/503/504 errors, or connection resets |
| Backend instance | FDs, listen backlog, thread pools, workers, connection pools | Failed accepts, queued requests, or application errors |
| Database/cache | Max clients, connection pools, query concurrency | Connection refused, pool exhausted, or query queuing |
| NAT/firewall | Session table, port mappings, throughput, PPS | New connections fail or time out |

Limits are counted differently across providers. Some services limit concurrent connections per listener or load balancer; others count per target, zone, instance type, or request/stream count. Distinguish **connection rate** (new connections per second), **concurrent connections** (open existing connections), **request rate** (requests per second), and **active requests** (requests currently in flight).

## 10. Sizing Connection Limits for Backends

Backend limits must reflect processing capacity and actual held connections. For each backend, average concurrency can be estimated using Little's Law:

\[
L = \lambda \times W
\]

Where `L` is the average number of requests in the system, `λ` is the arrival rate (requests/second), and `W` is the average response time (seconds). The formula yields average concurrent requests; it does not automatically equal the number of TCP connections when keep-alive or HTTP/2 multiplexing is used.

For example, a backend receives 400 requests/second with an average processing time of 50 ms:

\[
L = 400 \times 0.05 = 20\text{ concurrent requests}
\]

If p95 latency or processing time rises, required concurrency can be higher. Measure under peak load and inspect the latency distribution rather than relying only on averages.

An initial approach to sizing connection limits:

1. Measure connection counts and concurrent requests under normal load.
2. Determine peak RPS, bursts, p95/p99 latency, and connection lifetimes.
3. Identify backend capacity before queuing or error rates spike sharply.
4. Reserve headroom for health checks, administration, rollouts, and failover.
5. Cap limits so one backend does not absorb excessive connections when other nodes fail.
6. Test limits during scale-in, loss of an AZ, or a slow backend.

Do not set max connections arbitrarily high just to avoid errors. If a backend accepts more requests than it can process, queues and latency can grow unboundedly before resources exhaust. A well-chosen limit protects the backend from overload and produces clear signals for clients to retry or shed load.

## 11. Connection Pool Limits and Downstream Connections

Applications typically maintain connection pools to databases, caches, or HTTP services. Pools that are too small make requests wait even when dependencies have spare capacity; pools that are too large can overwhelm databases or target services.

For example, if there are 10 backend instances and each configures a max database pool of 50 connections, potential total connections reach 500, before counting workers, migrations, monitoring, and other apps. The database must have capacity for the real total client count.

When sizing pools, consider:

- Maximum instance count during autoscaling and failover.
- Connections needed to sustain target throughput.
- Query duration and the fraction of requests that actually hit the DB.
- Database connection limits and other competing clients.
- Acquisition timeout, idle timeout, and max connection lifetime.
- Whether an intermediate proxy/pooler can multiplex connections.

Connection pools need finite timeouts, hard maximum sizes, and active/idle/pending metrics. If a pool exhausts, raising pool size is not always right; slow queries or connection leaks may be the culprit. Monitor both pool wait time and query execution time.

## 12. Queues, Timeouts, and Overload Behavior

When all backends hit their limits, the load balancer or proxy may queue requests, reject connections, or return errors. Queues can absorb brief bursts, but cannot solve sustained arrival rates exceeding processing capacity.

A queue needs:

- Bounded length or capacity.
- Maximum wait timeout a request is allowed in the queue.
- Priority or drop policies where appropriate.
- Metrics for queue depth, queue wait time, and dropped requests.
- Backpressure so clients or upstreams slow down request rates.

If a queue is unbounded, stale requests may wait until after the client has already timed out, creating wasted work and slowing recovery. Rejecting early with `429 Too Many Requests` or `503 Service Unavailable` is often better than holding requests too long. For retryable APIs, return `Retry-After` when appropriate and design client retries with exponential backoff and jitter.

Timeouts must be coordinated across client, load balancer, proxy, and backend. Outer-tier timeouts should be long enough for inner steps, yet short enough not to tie up resources pointlessly. Avoid unbounded retries at every layer; stacked retries amplify load when backends are failing.

## 13. Connection Draining and Slow Start

When a backend undergoes maintenance, scale-in, or version replacement, the load balancer should stop sending new work to that node while allowing active connections to finish within a defined window. This mechanism is commonly called **connection draining** or deregistration delay.

Basic sequence:

1. Mark the backend not to accept new connections/requests.
2. Stop selecting the backend in the distribution algorithm.
3. Wait for in-flight requests and necessary connections to finish within the drain limit.
4. Close remaining connections per policy once the deadline expires.
5. Perform the restart, machine replacement, or application update.

Drain duration must fit maximum processing times and the protocol. WebSockets, TCP streams, gRPC streams, or long downloads can outlast typical drains; define explicit policies so drains do not wait forever. Applications should also support graceful shutdown and stop accepting new work before exiting.

**Slow start** gradually ramps up traffic to a newly healthy backend. This lets caches warm up and connection pools initialize without slamming the application with full load immediately. Slow start is especially helpful after scale-out or new deployments. Ramp duration and curves depend on the product; measure actual warm-up times.

## 14. Health Checks and Removing Backends from Distribution

Load balancers typically check backends with periodic health checks. If a backend fails criteria, it is removed from the active distribution pool. Health checks can operate at TCP or HTTP:

- TCP checks confirm the port accepts connections.
- HTTP checks hit an endpoint to confirm the application returns expected status.
- Some systems support checking response bodies or multiple conditions.

Health checks should test readiness required to serve requests, not merely whether the process is alive. If the endpoint depends on too many non-essential services, a minor dependency outage could eject all backends even when core functions still work.

Parameters to design:

- Interval between checks.
- Timeout for a single health check.
- Consecutive failures before marking unhealthy.
- Consecutive successes to mark healthy again.
- Port, path, protocol, and source network of the health checker.
- Impact of health checks on the application and database.

Overly fast or overly sensitive health checks cause flapping: backends rapidly cycle in and out. Overly slow health checks leave broken backends receiving traffic. Track state transitions and tune thresholds to real recovery times.

## 15. Connection Limits and Virtual Machine Resource Limits

A backend VM must have sufficient resources to handle the connections sent by the load balancer. Relevant limits include:

- File descriptors (`RLIMIT_NOFILE`) for open sockets and files.
- TCP listen backlog and accept queues.
- Ephemeral ports when opening many outbound connections.
- Thread, worker, event-loop, and process limits.
- CPU, RAM, kernel memory, and network PPS/throughput of the instance type.
- Connection pools to databases/caches and destination service limits.

If a load balancer allows 100,000 concurrent connections while each VM only sustains 5,000 under real configuration and load, size capacity across healthy backends and node-loss scenarios. Never rely solely on theoretical load balancer limits.

On Linux, monitor FD counts, `ss -s`, listen queues, CPU, memory, socket states, and network metrics. If a backend holds many connections with a low request rate, keep-alive or long-lived connections may be holding sockets open. If request rates are high and FDs climb steadily, check for connection leaks or improperly closed pools.

## 16. NGINX Upstream Configuration Example

NGINX can distribute requests to upstreams using default round robin or `least_conn`. Example:

```nginx
upstream orders_api {
    least_conn;
    server 10.20.16.11:8080 max_conns=300;
    server 10.20.16.12:8080 max_conns=300;
    server 10.20.16.13:8080 max_conns=150;
    keepalive 64;
}

server {
    listen 443 ssl;
    server_name orders.example.internal;

    location / {
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_pass http://orders_api;
        proxy_connect_timeout 3s;
        proxy_read_timeout 30s;
    }
}
```

This is an illustrative example for NGINX OSS; verify the exact version and deployment context. `least_conn` chooses the upstream with the fewest active connections. `max_conns` caps active connections to an upstream server; without a shared memory zone, the limit applies per worker process. Idle connections in the keepalive cache are not counted like active connections, so total open sockets can exceed `max_conns`. Therefore, consult NGINX documentation and measure in practice when running multiple workers.

`keepalive 64` sets the number of idle connections cached per worker in the upstream group under NGINX semantics; it is not a hard cap on total backend connections. `proxy_read_timeout` is the timeout between two successive read operations from the upstream, not necessarily a total request duration limit. Distinguish connect timeout, send timeout, read timeout, and overall client timeout.

## 17. Algorithm Selection Examples by Workload Type

| Workload | Potentially Suitable Algorithm/Mechanism | Rationale and Checks Needed |
|---|---|---|
| Stateless API, fairly uniform requests | Round Robin or Weighted Round Robin | Simple; use weights if backend capacities differ |
| API with widely varying request durations | Least Connections or active-request-based algorithm | Reduces piling work onto busy nodes; watch HTTP/2 and keep-alive |
| Long-lived TCP streams | Least Connections or hashing depending on session nature | Connection count reflects utilization better than RR; long streams need draining |
| Backends with key-partitioned local cache | Consistent hashing | Keeps keys near prior nodes on topology changes; handle cache misses on node failures |
| Apps relying on in-RAM sessions | Temporary sticky sessions | Eases legacy compatibility but reduces load balance and resilience |
| Heterogeneous backend specs | Weighted Round Robin/Weighted Least Connections | Traffic ratios reflect benchmarked capacity |
| Large fleet needing lightweight selection | Random or Power of Two Choices | Low state overhead; verify distribution balance |
| Canary rollouts | Weighted routing | Gradually increase traffic to new version under safety criteria |

No single algorithm is best in every situation. Benchmark with a traffic profile close to production, including request mix, processing times, keep-alive, HTTP/2, payload sizes, and retry behavior.

## 18. Illustrative Scenario: Backend Hits Connection Limit

An API has three backend VMs behind a load balancer using round robin. During peak hours, the first VM frequently returns 503 and logs `Too many open files`, while the other two VMs show lower CPU.

An investigation workflow might be:

1. Compare request rate, active connections, and latency per backend.
2. Check FD counts, `RLIMIT_NOFILE`, socket states, and connection pools on each VM.
3. Determine whether clients hold long keep-alives, heavy requests hit one node, or connections leak.
4. Check whether RR is balancing connection counts while skewing actual work.
5. Re-size backend limits to measured capacity; fix leaks or cap concurrency if needed.
6. Test least connections or an active-request algorithm if suitable for the workload.
7. Set max connections/queues and timeouts to protect backends; monitor 503s, queue wait, and p99.
8. Test removing one VM from the pool to confirm the remaining two survive failover load.

Simply switching from RR to least connections might reduce symptoms without eliminating the problem. If the first VM has an FD leak, it will still hit the limit over time. Fix the backend root cause and verify load distributes cleanly under both normal operation and failover.

## 19. Common Design Mistakes

- **Using RR for heterogeneous backends:** Equal request counts result in unequal resource utilization. Use benchmark-based weights.
- **Using Least Connections for HTTP/2 without accounting for streams:** One connection can carry many concurrent requests. Track active requests or streams if supported.
- **Overusing sticky sessions:** A large client group can overload one node. Prefer a shared session store whenever possible.
- **Setting connection limits too high:** Backends accept more connections than they can serve, driving up queues and latency. Cap based on real capacity.
- **Setting limits too low:** Requests are rejected while backends still have headroom. Benchmark and tune for peak.
- **Unbounded queues:** Holds requests too long and inflates latency. Enforce finite queue sizes and timeouts.
- **Synchronized retries:** Clients retry simultaneously after errors, creating retry storms. Use backoff, jitter, and retry budgets.
- **Health checks not reflecting readiness:** Backends take load before ready or get dropped over optional dependencies. Design appropriate endpoints.
- **Omitting draining during scale-in:** In-flight requests are terminated abruptly. Use deregistration delays and graceful shutdown.
- **Not testing node/AZ loss:** Normal capacity looks fine, but failover overloads survivors. Plan for N-1 capacity.

## 20. Checklist for Choosing Algorithms and Connection Limits

- [ ] Identified whether the load balancer operates at L4 or L7 and whether distribution is per flow, connection, request, or stream.
- [ ] Measured request characteristics, connection lifetimes, keep-alive, and HTTP/2 multiplexing.
- [ ] Selected RR/WRR/Least Connections/Hash/Adaptive algorithm based on workload and backend capacity.
- [ ] Weights reflect measured capacity, not merely vCPU counts.
- [ ] Sticky sessions enabled only with clear justification and tested against backend failures.
- [ ] Distinguished connection rate, concurrent connections, request rate, and active requests.
- [ ] Sized connection limits across load balancer, proxy, backend, and dependencies.
- [ ] Connection pools have max sizes, timeouts, active/idle/pending metrics, and bounded growth.
- [ ] Queues have explicit bounds, timeouts, backpressure, and clear overload behavior.
- [ ] Health checks measure proper readiness and avoid flapping.
- [ ] Connection draining, graceful shutdown, and slow start configured for rollouts/scaling.
- [ ] Tested bursts, slow backends, failed backends, scale-in, and single-AZ loss.
- [ ] Monitoring request rate, active connections, queues, p95/p99 latency, error rate, and backend saturation.

Load distribution algorithms determine how work is divided across backends, while connection limits protect each component from overload. When you match algorithms to protocol and workload traits, size limits from measured capacity, enforce finite queues/timeouts, and test failover, your load-balancing layer maintains stable latency and uses compute more efficiently.
