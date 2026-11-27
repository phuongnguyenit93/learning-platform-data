# Algorithm limitations when real-time load information is missing

Spring Cloud LoadBalancer performs client-side load balancing: from a **service ID**, an application fetches available `ServiceInstance`s and chooses one instance to send an HTTP request to. Simple algorithms like **Round Robin** or **Random** can divide selection counts relatively evenly. However, **distributing selections evenly does not mean distributing actual load evenly**, because instances can vary in capacity, latency, and active request count.

This lesson belongs to the **Selection Algorithms** chapter in the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. When using RestClient, WebClient, or OpenFeign to call a service ID, distinguish carefully: service discovery and the supplier chain provide **candidates**, health checks reflect **one aspect of availability**, and the algorithm can only optimize based on **data it actually sees**. This lesson explains that limitation, gives quantitative examples, and presents observability practices and improvement paths to prevent overload, timeouts, and cascading retries.

## 1. What information does the selection algorithm actually see?

A call to `http://inventory-service/api/items/42` can follow this sequence:

~~~mermaid
flowchart LR
    A["order-service"] --> B["HTTP client with @LoadBalanced"]
    B --> C["LoadBalancer selects target"]
    D["ServiceInstanceListSupplier"] --> C
    E["Discovery / cache / health / filter"] --> D
    C --> F["inventory-a"]
    C --> G["inventory-b"]
    C --> H["inventory-c"]
~~~

A `ServiceInstance` list typically contains `serviceId`, `host`, `port`, `secure`, `metadata`, and certain discovery-dependent fields. A supplier can filter by zone, hint, health check, or application policy.

However, a `ServiceInstance` **does not inherently contain** dynamic metrics such as:

- Active HTTP requests currently running on the instance, including requests from other callers.
- Queue length, remaining free threads/connections, or database pool saturation.
- CPU, memory pressure, and actual processing speed at the time of selection.
- Endpoint-level p95/p99 latency, error rate, or recent timeout rate.
- Per-request work volume, such as a lightweight cache lookup versus a long write task.

Without a dedicated telemetry source, the algorithm sees only a **candidate list**, possibly with static metadata, plus a slice of client-local state. From that alone, it cannot know for certain which instance has spare capacity to handle more requests.

### “Present” differs from “ready” and “has spare capacity”

| State | Meaning | What is not yet guaranteed |
|---|---|---|
| Found by discovery | Registry knows the instance address | Whether the instance is still running |
| Health check passes | Health endpoint returns a passing result | Whether business endpoints are fast enough |
| Selected by algorithm | Instance is in the policy's candidate pool | Whether instance has capacity for a new request |
| Returns HTTP 200 | That specific request completed | That the next request will also be fast and succeed |

An instance can return `200 OK` on its health endpoint while stalling on a database connection pool, holding hundreds of queued requests, or experiencing CPU throttling. This is why health and actual load must be observed independently.

## 2. Round Robin distributes selection turns, not processing cost

`RoundRobinLoadBalancer` selects instances in turn from the list. With two instances A and B, a simple sequence might be:

~~~text
Request:          1  2  3  4  5  6  7  8
Instance:         A  B  A  B  A  B  A  B
Selection counts: A = 4, B = 4
~~~

The goal is distributing **selection turns**, not CPU time, active task counts, or queue depth. Exact behavior also depends on whether the instance list stays stable, how multiple callers use load balancers, and specific version configuration.

### Example: equal request volume, vastly different concurrency

Suppose steady traffic is **20 requests/second**, and Round Robin splits nearly evenly:

| Instance | Average latency | Dispatched requests/second | Estimated steady-state concurrent requests |
|---|---:|---:|---:|
| A | 50 ms | 10 | 0.5 |
| B | 500 ms | 10 | 5 |

Using Little's approximate relation, `L = λ × W`, B must maintain roughly ten times as many active in-flight requests on average as A. These figures illustrate steady-state average latency rather than directly measured threads. If B has a tight thread pool or connection limit, queuing can begin even earlier.

### Example: instances with unequal capacity

Suppose at measurement time, A sustains up to **30 requests/second**, whereas B can only handle **6 requests/second**. When total traffic is 30 requests/second:

| Instance | Assumed sustainable capacity | Turns received under Round Robin |
|---|---:|---:|
| A | 30 requests/second | 15 requests/second |
| B | 6 requests/second | 15 requests/second |

A retains spare capacity while B receives more than double its sustainable rate. B can suffer growing queues, p99 latency spikes, timeouts, and error rates; meanwhile, a “selections per instance” chart still looks nearly 50/50.

Even instances with identical CPU/RAM specs experience uneven load when receiving different mixes of heavy/light endpoints, different data hotspots, or fresh cold starts.

**Round Robin is a good baseline** when instances are roughly uniform and requests carry comparable cost. It does not magically become a load-aware algorithm merely because instances come from service discovery.

## 3. Random is fair in expectation, but makes no short-window guarantee

`RandomLoadBalancer` chooses randomly from the candidate list. With N instances and uniform selection, expected probability per instance is roughly `1/N`. Yet within a short window, Random can send a streak of requests to the same instance:

~~~text
Selection turn:  1  2  3  4  5  6
Target:          A  A  B  A  A  A
~~~

This remains a completely plausible outcome. Plain Random does not check whether A is busy or B is idle. Under bursty traffic, temporary clumping can overload an instance before average selection ratios balance out.

Distinguish **uniform Random** from **power of two choices**: picking two candidates at random and preferring the less loaded one. The latter requires load telemetry and comparison logic; it is not `RandomLoadBalancer`'s default.

## 4. Weighted routing is only as good as weights reflect capacity

One improvement for unequal-capacity instances is weighted distribution. In the Spring Cloud LoadBalancer ecosystem, `WeightedServiceInstanceListSupplier` helps prepare lists for weighted selection using metadata or configured weight logic.

For example, assuming A has five times B's capacity, choose weights:

~~~text
weight(A) = 5
weight(B) = 1

Expected selection ratio:
A = 5/6 ≈ 83.3%
B = 1/6 ≈ 16.7%
~~~

At 30 requests/second, A receives an estimated 25 and B receives 5 requests/second. Compared to the 30 vs. 6 requests/second capacity example above, this ratio fits better, though capacity headroom is still needed for traffic bursts and random variance.

**Static weights grow stale** if:

- A's CPU limit is reduced or it runs resource-intensive background tasks.
- B is upgraded or just restarted with a cold cache.
- Both A and B bottleneck on a shared database or downstream service.
- Request mix shifts, causing the same request rate to consume different CPU than before.
- Weights were based on old benchmarks and never recalibrated.

Weight=5 does **not** mean A is limited to five concurrent active requests. Weighted routing tunes **selection ratios**; capping concurrency requires a separate mechanism such as semaphores, bulkheads, or admission control.

## 5. Health checks detect availability, not full load

`HealthCheckServiceInstanceListSupplier` can restrict choosing instances failing the health endpoint. Yet when the health endpoint only performs a lightweight check, it can return `200` even while business endpoints are overloaded.

| Scenario | Can health check detect it? | Signals needed in addition |
|---|---|---|
| Instance stopped running | Usually yes, after one check interval | Client connection failures and timeouts |
| High CPU while health stays fast | Possibly not | CPU utilization, throttling |
| Worker pool exhausted | Depends on endpoint | Active workers, queues, rejected requests |
| Database pool waiting long | Depends on endpoint | Pool wait time, DB latency |
| Heavy endpoint p99 climbing | Possibly not | Per-operation latency |
| Network failing only from one caller | Possibly not in time | Per-zone/per-caller connection outcomes |

Distinguish liveness, readiness, and ability to serve a specific endpoint. Avoid turning health checks into continuous load benchmarks because health requests themselves cost resources, add noise, and can even add load.

**A passing health check does not guarantee the next request succeeds.** An instance can fail immediately after being probed.

## 6. Caching and telemetry lag make decisions stale

`CachingServiceInstanceListSupplier` reduces discovery polling, yet a cached list may still hold a recently removed instance or omit a newly registered one. Even with a fresh list, load telemetry can lag behind traffic bursts.

~~~mermaid
sequenceDiagram
    participant D as Discovery
    participant C as Cache
    participant LB as LoadBalancer
    participant B as Instance B

    D-->>C: List A, B
    C-->>LB: A, B
    Note over B: B starts overloading
    LB->>B: Select and send request
    B-->>LB: Slow response or timeout
    Note over C: Cache still returns A, B
    LB->>B: May continue selecting B
~~~

There are two kinds of missing information:

1. **Missing data dimensions**: the source only provides host/port, lacking concurrency, queues, CPU, or latency.
2. **Missing freshness**: data exists, but is measured/updated too slowly compared to real-time shifts.

Lowering instance cache TTL refreshes registry changes faster, yet cannot invent load metrics the registry does not supply. Conversely, continuously streaming telemetry raises monitoring overhead and can make algorithms oscillate on noise.

## 7. Client-side LoadBalancer only has a local view

A calling application knows the requests it has sent and received, yet **does not inherently know load from other callers**:

~~~mermaid
flowchart LR
    A["Caller A"] --> LA["LB A"]
    B["Caller B"] --> LB["LB B"]
    C["Caller C"] --> LC["LB C"]
    LA --> X["Instance X"]
    LB --> X
    LB --> Y["Instance Y"]
    LC --> X
    LC --> Y
~~~

If LB A counts “in-flight requests to X” as 0, that does not prove X is idle. LB B and LB C might simultaneously be sending hundreds of requests to X.

Even an algorithm that “picks the instance with fewest active requests” must clarify whether it relies on **single-client in-flight** or **server-wide in-flight**. Knowing cluster-wide load requires server-side telemetry, monitoring infrastructure, a service mesh, or an external feedback source. Centralized data also has lag and must avoid overreacting to stale snapshots.

Independent callers' Round Robin selectors do not necessarily share a counter either. Each caller generates its own selections, causing total system-wide distribution to diverge from an ideal single Round Robin sequence.

## 8. Clean dashboards can still mask overload

Suppose a one-minute measurement yields these numbers:

| Metric | inventory-a | inventory-b |
|---|---:|---:|
| Selected requests | 900 | 900 |
| Successfully completed requests | 892 | 724 |
| Timeouts | 3 | 144 |
| p95 latency | 75 ms | 1,400 ms |
| Average CPU | 43% | 92% |
| Average queue length | 1 | 36 |

Round Robin balanced **selection counts** evenly. Yet B is saturated, completing fewer requests and causing timeouts to spike. Switching to Random provides no information to avoid B.

When observing, distinguish:

- **Selected requests**: how many times LoadBalancer chose an instance.
- **Started attempts**: how many times the HTTP client actually started sending, including retries.
- **Completed requests**: completed requests broken down by status and latency.
- **Active/in-flight**: requests currently running or queued at a point in time.
- **Work cost**: CPU, I/O, and resources consumed by each operation.

Aggregate request counts can hide an instance receiving a disproportionate share of heavy endpoints. Break metrics down by operation or route with controlled label dimensionality.

## 9. What to measure to decide if a different algorithm is needed?

Before building a load-aware policy, establish a baseline:

| Data | Question |
|---|---|
| Request rate by service and instance | Where is traffic going? |
| p50/p95/p99 latency | How do median and tail latencies look? |
| HTTP status, timeouts, connection errors | Did failures originate in network, client, or server? |
| In-flight requests, queue length | Is the instance accumulating work? |
| CPU, heap, GC, worker pools | Which resource is nearing saturation? |
| Database pool, downstream latency | Which dependency holds the bottleneck? |
| Instance count, health/filter results | Is the candidate list accurate? |
| Retry attempts and tried instances | Are retries amplifying load? |
| SLOs, error budgets | Does actual behavior meet targets? |

Spring Cloud LoadBalancer offers lifecycle hooks such as `LoadBalancerLifecycle` to observe selection events and outcomes; these can combine with HTTP client instrumentation, Micrometer/Actuator, and server metrics. A metric collected solely in LoadBalancer **does not automatically reflect** internal CPU, queues, or processing time inside an instance.

When tagging metrics by instance ID or operation, control cardinality. Never put tokens, user IDs, or personal data into metric tags or logs.

## 10. Improvement paths and limits of each approach

| Approach | Required data | Limits |
|---|---|---|
| Round Robin | Candidate list | Load-blind; splits selection turns evenly |
| Random | Candidate list | Short-term variance and load-blind |
| Static weights | Relative capacity estimates | Weights can become stale |
| Zone preference | Zone/metadata | Optimizes locality, does not measure saturation |
| Health filtering | Health endpoint | Binary, updated periodically |
| Caller-local least in-flight | Local active-request counter | Blind to other callers' traffic |
| Custom latency-aware / EWMA | Sufficiently sampled, fresh latency | Noise from request types and network |
| Adaptive concurrency | Latency and saturation signals | Needs damping to prevent oscillation |
| Server-side / service mesh policy | Telemetry where aggregate load is visible | Adds cost, latency, and infrastructure dependencies |
| Scale out / optimize server | Capacity bottleneck profiling | Resource provisioning cost and startup lag |

Several strategies in the table are **design or customization directions**, not a claim that Spring Cloud LoadBalancer provides all of them out of the box. Using latency or in-flight telemetry in a custom selector requires adding collection, propagation, and handling for missing or expired metrics.

The best policy is not necessarily the most complex. If instances share equal capacity and load is moderate, Round Robin may suffice with low operational overhead. If the bottleneck is a shared database, changing the instance selection algorithm will not fix database capacity.

## 11. Adaptive algorithms can cause load oscillation

Suppose the selector sees A slow down and immediately cuts traffic to A sharply. B absorbs most new requests and slows down in turn. The selector swings traffic back to A. When multiple independent clients react similarly to latency metrics, the system can oscillate continuously.

~~~mermaid
flowchart LR
    A["A slows down"] --> B["Reduce traffic to A"]
    B --> C["Shift traffic to B"]
    C --> D["B saturates"]
    D --> E["Reduce traffic to B"]
    E --> A
~~~

Anti-oscillation safeguards typically include:

1. **Appropriate measurement windows**: do not react to a few outlier requests.
2. **Hysteresis**: shift policy only when differences exceed a clear threshold.
3. **Weight-change rate limiting**: never swing all traffic after a single sample.
4. **New-instance warm-up**: avoid slamming caches, JIT, and connection pools before readiness.
5. **Track request types**: aggregate latency can shift due to changing mixes of heavy/light tasks.
6. **Safe fallback**: when metrics drop or expire, never drop every instance automatically.
7. **Failure-mode testing**: measure behavior when a zone loses connectivity or a shared dependency slows.

The more volatile load signals are, the more decisions must balance freshness against noise. An adaptive algorithm lacking stabilization mechanisms can cause more harm than Round Robin.

## 12. Timeouts, retries, and concurrency limits remain mandatory

A selected instance can fail after selection time. LoadBalancer does not guarantee request success, so HTTP clients still need timeouts, bounded retries, and resource safeguards.

Suppose the caller receives 100 requests/second; on failure, each request is attempted **up to three times total**. If most requests keep failing, the backend can receive up to roughly **300 attempts/second** under the same conditions. Retries can worsen overload.

Distinguish clearly:

- **Load balancing** picks an instance from the candidate list.
- **Timeout** bounds connection or response wait duration.
- **Retry** re-attempts certain errors under a bounded policy; the next turn does not automatically pick a different instance.
- **Circuit breaker** gates or pauses calls when a dependency fails repeatedly.
- **Bulkhead / concurrency limit** bounds consumed resources.
- **Load shedding** rejects excess requests when the system lacks capacity.

For operations with side effects, such as deducting inventory or creating orders, retries must address idempotency and idempotency keys. Avoid stacked retries across HTTP client, Spring Cloud LoadBalancer, and gateway pushing attempt counts past the overall time budget.

## 13. Hands-on: proving Round Robin is load-blind

Prepare two instances registered under service ID `inventory-service`. Create a test endpoint `GET /api/check`:

- Instance A simulates 40–60 ms latency.
- Instance B simulates 350–450 ms latency.
- Both are healthy and discoverable from the caller.

From a `@LoadBalanced`-configured client, send requests by service ID:

~~~java
// restClient built from @LoadBalanced RestClient.Builder
String body = restClient.get()
    .uri("http://inventory-service/api/check")
    .retrieve()
    .body(String.class);
~~~

Have the endpoint return an instance identifier in the test environment to pinpoint the target. Avoid exposing internal hostnames in public responses.

### Step 1: sequential calls

Send around 100 sequential requests. Log selected instance, response time, and status. With Round Robin and a stable list, A and B selection counts are usually nearly equal. Latency when calling B will be noticeably higher.

### Step 2: bounded concurrent calls

Ramp concurrency in stages, measuring p95/p99, in-flight, CPU, queues, and timeouts per instance. Keep the instance list unchanged; watch where B starts queuing or timing out even while selection counts remain roughly 50/50.

### Step 3: alter B's capacity

Reduce B's CPU limit or increase processing time in the test environment. If request distribution does not adapt to latency, it clearly shows Round Robin uses no real-time capacity data.

### Step 4: compare weights

Try weighted routing if your application version and setup support it. Set weights from measured capacity, record selection ratios and latency, then alter B's capacity again to observe the downside of static weights.

Record results:

| Scenario | A/B selection ratio | Per-instance p95/p99 | Timeouts | In-flight/queue | What to conclude |
|---|---|---|---|---|---|
| A and B identical | Per policy | Compare | Compare | Compare | Is the baseline good enough? |
| B slower | Does it change? | B rises? | B rises? | B builds up? | Selection counts differ from processing cost |
| B CPU reduced | Does it change? | B rises? | B rises? | B saturates? | No load feedback loop |
| Adjust weights | Follows ratio? | Improves? | Drops? | Shifts load to A? | Under what conditions do weights hold? |

Do not extrapolate simulated examples directly into production figures. Conclusions must rest on measurements under concrete traffic, resources, and dependencies.

## 14. Checklist for choosing a strategy in production systems

Before changing algorithms, verify:

- Do instances share comparable CPU/RAM capacity, worker counts, and connection pools?
- Are **completed request** distribution, p95/p99 latency, error rate, and concurrency balanced?
- Is the `ServiceInstance` set accidentally excluding valid instances via caching or filters?
- Is load/latency data fresh and sufficiently sampled to drive decisions?
- Are multiple independent callers causing local in-flight metrics to miss most traffic?
- Do differences across endpoints cause request counts to misrepresent processing cost?
- Are retries, timeouts, circuit breakers, and concurrency limits coordinated into a unified time budget?
- Have bursts, cold starts, instance failures, and shared database bottlenecks been tested?
- Can you observe `ServiceInstance` selection failures, connection failures, and HTTP errors separately?
- Has the new algorithm been tested against oscillation or herding load onto another instance?

**Core principle:** no algorithm can optimize load using signals it does not receive. Round Robin and Random are simple starting points; weights help when relative capacity is known upfront but do not self-adapt. When the goal is cutting p99 latency and preventing overload, collect per-instance latency, concurrency, saturation, and error rates, locate the true bottleneck, and only then decide if a more sophisticated routing policy is needed. Spring Cloud LoadBalancer selects the `ServiceInstance`, while RestClient, WebClient, and OpenFeign communication quality still depends on the whole system plus timeouts, retries, and resource bounds.

