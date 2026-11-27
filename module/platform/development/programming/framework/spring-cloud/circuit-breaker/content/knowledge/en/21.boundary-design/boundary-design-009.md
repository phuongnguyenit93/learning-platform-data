# Local Circuit Breaker Scope vs. System-Wide Protection

A circuit breaker in Spring Cloud typically protects a call from one application to a specific dependency. With Resilience4j, the state and sliding window are held inside the circuit breaker instance of the running process. When the application is deployed across multiple pods or machines, each process usually has its own breaker and statistics. Consequently, a breaker transitioning to `OPEN` only blocks calls going through that instance; it does not automatically open breakers on other replicas, nor does it establish a system-wide protection policy.

Distinguishing these scopes is crucial when designing distributed systems. A local circuit breaker helps one caller stop adding pressure to a dependency from which it observes failures. System-wide protection requires broader-scoped mechanisms such as traffic limits, admission control, load shedding, shared quotas, gateway or service mesh policies, and resource bounds at the dependency itself.

## 1. A circuit breaker protects one call boundary

Consider Order Service calling Inventory Service. On the Order Service side, the circuit breaker typically wraps the HTTP or RPC call to Inventory Service. The breaker records outcomes of that call, computes failure rate and slow-call rate over a sliding window, and decides whether to permit subsequent calls.

```text
Order Service
  └── InventoryClient
        └── CircuitBreaker("inventory")
              └── HTTP/RPC request
                    └── Inventory Service
```

The protection scope is the call path from Order Service to Inventory Service. The breaker does not automatically protect other paths such as Order Service to Payment Service, nor does it manage direct requests from another application to Inventory Service.

In an application with multiple dependencies, create separate breakers for each boundary needing protection. For example, `inventory`, `payment`, and `shipping` have different traffic, latency, criticality, and fallback policies. Sharing one breaker across all dependencies allows failures in one system to influence protection decisions for the remaining systems.

## 2. Resilience4j state usually lives inside each process

With Resilience4j configured in Spring Boot, the registry manages breakers in the application's memory. Example:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

Each Spring Boot process loads this configuration and creates its own `inventory` breaker. Configuration may be identical across pods, but call history, current state, and window counters are not automatically shared across pods.

Example deployment with three replicas:

```text
                 Order Service
          +-----------+-----------+
          |           |           |
       Pod A        Pod B        Pod C
       breaker      breaker      breaker
      inventory    inventory    inventory
       CLOSED        OPEN        CLOSED
          |           X           |
          +-----------+-----------+
                      |
                      v
               Inventory Service
```

If Pod B observes enough failures to meet the threshold, Pod B's breaker transitions to `OPEN`. Pod A and Pod C can remain `CLOSED` and continue sending requests. This is normal local circuit breaker behavior, not a state synchronization bug.

A breaker can be retrieved from the Spring-managed registry:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryProtection {

    private final CircuitBreaker inventoryBreaker;

    public InventoryProtection(CircuitBreakerRegistry registry) {
        this.inventoryBreaker = registry.circuitBreaker("inventory");
    }

    public CircuitBreaker.State state() {
        return inventoryBreaker.getState();
    }
}
```

This registry belongs to the current process's application context. Do not create a new registry on every request or assume the same breaker name means the same state across every machine.

## 3. Why is a local breaker still valuable?

Even without controlling the entire cluster, a local breaker substantially reduces pressure:

- A replica that detects a failing dependency can stop sending additional requests from that replica.
- Caller threads, connections, and processing time are freed faster when the breaker rejects new calls.
- Fallbacks can preserve partial read functionality or return controlled errors.
- When the dependency recovers, `HALF_OPEN` allows a small number of probes from that caller before restoring full traffic.
- Per-instance metrics pinpoint which replica observed failures and when its breaker changed state.

A local breaker works best when placed right at the dependency call boundary and paired with appropriate timeouts, bulkheads, and retry policies. It does not replace traffic limits or the dependency's own capacity limits.

## 4. Impact when a system has multiple replicas

Suppose Order Service has 10 pods, each allowing up to three probes in `HALF_OPEN`. If all 10 breakers transition to `HALF_OPEN` nearly simultaneously, the system can generate up to around 30 probes in a single wave, depending on request distribution and transition timing.

That may be fine for a dependency with ample capacity, or it can trigger a sudden load spike right as the service recovers. `permittedNumberOfCallsInHalfOpenState` is a per-breaker-instance limit, not a global cap across the entire deployment by default.

Several consequences to account for:

| Scenario | Consequence of local state | Additional handling |
| --- | --- | --- |
| One pod has an isolated network issue | Only that pod may open its breaker; other pods still make calls | Monitor per-instance metrics and check network/pod health |
| Dependency fails cluster-wide | Pods open breakers based on their own metrics and timing | Combine with traffic limits at gateway, mesh, or dependency |
| Multiple pods transition to `HALF_OPEN` together | Total probes can equal the sum of all pods' permits | Apply load limits at the dependency, controlled recovery rollout, or broader-layer probe policies |
| A new pod starts up | The new breaker usually has no failure history yet | Do not treat a new pod's `CLOSED` state as proof the dependency is healthy |
| Pod is replaced or restarted | In-memory state and windows are recreated | Use centralized metrics/logs to preserve operational history beyond pod lifecycles |

Do not simply increase `waitDurationInOpenState` to solve every multi-replica issue. Long open durations reduce probe frequency, yet also prolong how long a pod goes without retrying a dependency after it has already recovered. Choose values based on recovery time and the system's probe tolerance.

## 5. System-wide protection requires multiple layers

A system can coordinate multiple mechanisms at different boundaries:

```text
Client
  |
  v
API Gateway
  - Authentication / quota
  - Rate limit / admission control
  - Load shedding
  |
  v
Order Service replicas
  - Local Bulkhead
  - Local Circuit Breaker
  - Local Timeout / Retry policy
  |
  v
Service Mesh / Load Balancer
  - Routing / outlier detection
  - Connection and request limits
  |
  v
Inventory Service
  - Server-side concurrency limit
  - Queue and thread-pool bounds
  - Database connection pool limits
  - Load shedding / overload response
```

Each layer addresses a distinct scope:

- **Gateway:** controls traffic from clients or tenants before requests enter deep into the system.
- **Caller circuit breaker:** stops calls to a dependency from one process when the dependency shows signs of degradation.
- **Caller bulkhead:** limits concurrent tasks a dependency can occupy within a process.
- **Service mesh or load balancer:** enforces routing, health/outlier policies, and connection or request limits at the proxy layer. Exact scope and accounting depend on the implementation; never assume every mesh policy is a cluster-wide quota.
- **Dependency-side limits:** protects thread pools, queues, connection pools, CPU, and resources used by the service itself.
- **Distributed quota or rate limiter:** caps total traffic per tenant, API, or resource across multiple replicas when policy requires a shared counter.

No single layer replaces all the others. For instance, a gateway rate limit controls client request rates yet does not necessarily stop an internal service from sending too many requests to a database. A local circuit breaker reduces requests from a failing caller yet does not block requests from other callers.

## 6. Distinguishing circuit breakers from shared rate limits and quotas

Circuit breakers and rate limiters serve different goals:

| Mechanism | Decision based on | Typical scope | Goal |
| --- | --- | --- | --- |
| Circuit breaker | Failure rate, slow-call rate, and sliding window | One call boundary inside a process or proxy | Stop calling a degrading dependency |
| Local rate limiter | Request count over a time interval | One process | Cap call rate at that caller |
| Distributed rate limiter | Counters or tokens shared across multiple replicas | Multiple processes/clusters or tenants | Enforce total rate under a shared policy |
| Bulkhead | Concurrent tasks, threads, or queues | One pool or process; may also have server-side limits | Prevent one dependency from exhausting resources |
| Admission control / load shedding | Current load and remaining capacity | Usually at gateway or server | Reject early to keep the system stable |

For example, a tenant is permitted at most 500 requests per minute across the entire cluster. If each pod has a local rate limiter of 500 requests/minute and there are 10 pods, total traffic can reach 5,000 requests/minute. To enforce a shared 500 requests/minute quota, a coordinated mechanism or distributed counter with appropriate semantics is needed; a standalone local limiter is insufficient.

Conversely, if the goal is for Order Service to stop calling Inventory Service for a while when Inventory Service starts timing out, a circuit breaker is the better fit. A rate limiter does not automatically detect that a dependency is failing; it only caps request volume by rate rules.

## 7. Should circuit breaker state be shared across machines?

A standard Resilience4j CircuitBreaker is an in-memory mechanism and does not automatically sync state across JVMs. You might consider placing state in a shared data store, but doing so introduces several problems:

- Every call must read or update state over the network, adding latency directly onto the protection path.
- Multiple callers can transition state concurrently; atomicity and event ordering must be defined.
- When the data store or the network between callers and the store fails, the protection mechanism itself may stop working.
- A shared `OPEN` state can block callers that still have healthy connectivity to the dependency when only one network zone is failing.
- Synchronizing `HALF_OPEN` requires cluster-wide probe coordination; otherwise multiple nodes can still probe simultaneously.

Therefore, do not turn a local circuit breaker into a distributed state service just so every pod displays the same `OPEN`/`CLOSED` value. When a shared policy is required, it usually belongs at a layer with the right scope, such as a gateway, service mesh, or distributed rate limiter/admission control. Local breakers can still serve as fast protection at the caller.

Only consider sharing state when there is a concrete business requirement, a clear consistency model, and well-defined failure handling for the state store. Measure access overhead, behavior during network partitions, and the impact of a shared decision on callers across different network zones.

## 8. Configuring local breakers per dependency

A typical configuration for two dependencies with different characteristics:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
      payment:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 20
        failureRateThreshold: 30
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 40
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 1
```

The two instances have separate thresholds and windows because inventory and payment may differ in traffic, latency, failure consequences, and recovery characteristics. These values only illustrate structure. In production environments, select values from actual request rates, client timeouts, SLOs, and dependency capacity.

Each replica loads these settings and maintains local statistics. Identical configuration does not imply identical statistics. When comparing across replicas, export metrics with instance/pod labels and aggregate in the observability platform; do not use one aggregate value to infer the state of every individual breaker.

## 9. Monitoring state per instance and cluster-wide

Dashboards should provide both granular and aggregate views:

| View | What to display | Reason |
| --- | --- | --- |
| Per pod/instance | Breaker state, failure rate, slow-call rate, rejection counts | Detect an isolated replica or network zone issue |
| Per dependency cluster-wide | Request rate, errors, latency, total rejections, and count of `OPEN` pods | Understand overall impact on the dependency |
| Per caller service | Fallback rate, API errors, and end-to-end latency | Assess user experience and service continuity |
| Dependency side | Inbound request rate, queues, threads, connection pools, CPU, and overload responses | Confirm whether the receiving system is overloaded |

Resilience4j metrics normally carry the breaker instance name, but deployment labels such as application, environment, and pod should be added via Micrometer or the scrape platform. Keep cardinality reasonable; never put request ID, user ID, or exception messages into labels.

One pod in `OPEN` while other pods remain `CLOSED` can signal a localized fault. If all pods open their breakers around the same time and dependency-side metrics also show rising latency, the dependency is likely experiencing a broader outage. Cross-check with traces, logs, and network metrics before concluding.

## 10. Testing behavior when scaling to multiple replicas

Testing with only one instance cannot prove scope boundaries in a multi-replica deployment. You can design an integration test or staging environment with two or three instances of the same service:

1. Start the replicas with the same `inventory` breaker configuration.
2. Send requests through one replica and simulate dependency errors only on that replica's network path.
3. Confirm the affected replica's breaker transitions to `OPEN` and its supplier stops calling the dependency.
4. Send requests through another replica with a healthy connection; confirm its breaker can remain `CLOSED` and calls still execute.
5. Restore the dependency and observe `HALF_OPEN` probes generated per replica.
6. Compare total probes against per-replica limits and the dependency's actual capacity limits.

Expected results show that breaker state is local. If total probes or total concurrency must not exceed a shared cap, add a limiting mechanism at a broader layer or on the dependency side.

Additional tests should simulate pod restarts to confirm newly started breakers do not retain the old pod's in-memory sliding window. Pre-restart history must be traced via centralized logs and metrics rather than relying on the runtime state of a replaced instance.

## 11. Common design mistakes

- **Assuming one open breaker opens across the whole cluster:** other replicas normally hold separate state and can still send requests.
- **Using a local rate limiter to enforce a cluster-wide quota:** total quota scales up with the replica count.
- **Counting probes for only a single pod:** cluster-wide probes can equal the sum of permits across all breaker instances.
- **Using one breaker for multiple dependencies:** failures and latency in one dependency affect protection decisions for another.
- **Using aggregate metrics to infer per-pod state:** keep instance labels to identify which node has an issue.
- **Synchronizing state via a shared store without accounting for store failures:** the new protection path can become another critical dependency.
- **Protecting only on the caller:** the dependency still needs thread, queue, and connection limits plus overload rejection capability.
- **Closing breakers on all replicas simultaneously:** traffic can rush back to the dependency before it is ready for full load.

## 12. Rules for choosing protection scope

- Place a Resilience4j CircuitBreaker at each dependency call boundary inside each caller process.
- Use separate breakers for dependencies with different failure behaviors and policies.
- Treat `minimumNumberOfCalls`, sliding windows, and `HALF_OPEN` probe counts as local per-instance limits.
- Combine timeouts and bulkheads to bound wait durations and resources within each process.
- Use gateways, service meshes, distributed rate limiters, or admission control when broader-scoped policies are required; verify clearly whether actual limits are per-proxy, per-node, or global.
- Protect dependency-side resources with bounded queues, thread pools, and connection pools.
- Monitor per-pod metrics alongside per-dependency aggregates to distinguish local faults from widespread incidents.
- Test multi-replica behavior, pod restarts, and recovery probe waves to evaluate aggregate load.

A local circuit breaker is a fast protection layer right where calls originate. It lets a caller stop generating additional load on its own when a dependency shows signs of degradation, without coordinating all replicas. A reliable design pairs local breakers with traffic and resource limits at gateways, proxies, and dependencies, while observing both individual instance state and system-wide impact across Spring Cloud.
