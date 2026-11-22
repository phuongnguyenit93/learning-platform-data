# Multi-Pod Restore and Controlling Load on Dependent Services

When deploying Java with CRaC (Coordinated Restore at Checkpoint) on Kubernetes, a checkpoint can help each Pod start and reach readiness faster. However, when multiple Pods are restored or scaled up within a short window, all of them may simultaneously connect to databases, Redis, message brokers, authentication services, and external APIs.

If every Pod opens connection pools, refreshes caches, registers subscriptions, and runs warm-up immediately inside its post-restore callback, the total generated load can far exceed normal serving load. Databases may run out of connections, Redis may suffer a connection storm, brokers may receive too many consumers at once, or authentication services may be overloaded by token requests.

Therefore, two separate levels must be managed:

- **Pod level:** each process restores resources, checks dependencies, performs bounded warm-up, and reports readiness only when it can serve.
- **Fleet level:** coordinates the restore or scale pace across multiple Pods, caps total connections and requests to dependencies, spreads out retries, and prevents all Pods from executing the same background work.

CRaC callbacks only coordinate the lifecycle of a single process. They do not automatically coordinate all replicas in Kubernetes. To protect dependent services, combine application lifecycle management with rollout strategies, autoscaling policies, rate limits, backpressure, and system-level observability.

## 1. Why Can Restoring Multiple Pods Cause Load Spikes?

Suppose a Deployment has 40 replicas. Pods are restored from the same checkpoint or created nearly simultaneously. Each Pod may perform the following operations:

- Open 20 connections to a database pool.
- Connect to Redis and refresh topology.
- Connect to a broker, create consumers, and register subscriptions.
- Fetch access tokens from an identity provider.
- Load configuration caches and reference data.
- Call health endpoints of dependent services.
- Run warm-up requests to warm code and caches.
- Start schedulers or background workers.

The database pool alone could create 800 connections if 40 Pods open all 20 connections at once. Actual numbers depend on pool configuration and when the pool creates connections, yet the example shows that total fleet load must be calculated as Pod count multiplied by per-Pod usage.

### 1.1. Connection Storms and Request Storms

Two types of spikes often appear together:

A **connection storm** occurs when many Pods simultaneously open TCP/TLS connections, authenticate, perform handshakes, and initialize pools. Databases or Redis may hit connection limits before the application serves a single request.

A **request storm** occurs when many Pods simultaneously warm up, refresh caches, call configuration APIs, download metadata, or execute health checks. Even if the connection count is modest, the number of requests in a short window can still exceed dependency capacity.

Example:

| Activity per Pod | Pod count | Total activity when restoring together |
|---|---:|---:|
| Open up to 15 DB connections | 40 | 600 DB connections |
| Refresh 30 cache keys | 40 | 1,200 cache reads |
| Fetch 2 tokens | 40 | 80 token requests |
| Create 4 broker consumers | 40 | 160 consumers |
| Send 5 warm-up requests | 40 | 200 warm-up requests |

This is an illustrative multiplication. Pools may open connections on demand, caches may batch requests, and brokers may limit consumers. However, without explicit design, all of these activities can pile into the same time window.

### 1.2. Why Doesn't a Checkpoint Stop Dependencies?

A checkpoint saves Java process state. Databases, Redis, brokers, and external APIs keep serving other workloads while Pods are checkpointed.

Upon restore, each Pod may restore old client objects yet still must validate or recreate connections. If all Pods reconnect together, dependencies receive a wave of new load while still handling traffic from other applications.

~~~mermaid
sequenceDiagram
    participant K as Kubernetes / restore controller
    participant P1 as Pod 1
    participant P2 as Pod 2
    participant Pn as Pod N
    participant D as Database / Redis / Broker

    K->>P1: Restore
    K->>P2: Restore
    K->>Pn: Restore
    par Concurrent reconnect
        P1->>D: Connect, authenticate, warm-up
        P2->>D: Connect, authenticate, warm-up
        Pn->>D: Connect, authenticate, warm-up
    end
    D-->>P1: Slow response / connection limit
    D-->>P2: Timeout / queueing
    D-->>Pn: Retry
    P1->>D: Retry
    P2->>D: Retry
    Pn->>D: Retry
~~~

If retries lack backoff and jitter, load can surge right when the dependency is already slow. A brief initial recovery wave can turn into a loop of timeouts and retries.

## 2. Two Coordination Levels: Pod and Fleet

The entire problem cannot be solved by an `afterRestore()` callback alone. Responsibilities must be split.

### 2.1. Pod Level

Each Pod is responsible for:

- Marking the application unready during restore.
- Recreating resources owned by the Pod.
- Using timeouts for connections and warm-up operations.
- Limiting internal concurrency.
- Retrying with backoff and jitter.
- Opening admission only when essential dependencies are ready.
- Not re-running duplicate business side effects just because the process was restored.

### 2.2. Fleet Level

A Kubernetes controller, rollout controller, or external orchestration component is responsible for:

- Limiting the number of Pods updated or created within a time window.
- Controlling scale-up velocity.
- Grouping or batching restores.
- Avoiding all replicas warming up a dependency simultaneously.
- Monitoring dependency load and pausing the next batch when needed.
- Maintaining enough capacity to serve existing traffic while new Pods are starting.

A CRaC callback cannot reliably know the total number of Pods restoring cluster-wide without a separate coordination mechanism. Each Pod should manage only its own work; total load caps must be enforced at the fleet level or at the dependency itself.

~~~mermaid
flowchart TD
    A["Restore / scale request"] --> B["Fleet rollout controller"]
    B --> C["Limit Pods per batch"]
    C --> D["Pod restored"]
    D --> E["CRaC afterRestore"]
    E --> F["Bounded dependency initialization"]
    F --> G["Warm-up and health check"]
    G --> H{"Pod ready?"}
    H -->|Yes| I["Readiness = READY"]
    H -->|Not yet| J["Retry with backoff / NOT READY"]
    I --> K["Allow next batch"]
    J --> L["Keep load within limit"]
    L --> H
~~~

## 3. Controlling Restore Pace with Kubernetes Deployments

With a Deployment, rolling updates allow limiting how many new Pods and old Pods can be unavailable during version changes.

Two key fields are:

- `maxSurge`: number of Pods above the desired replica count that can be created during a rollout.
- `maxUnavailable`: maximum number of Pods that can be unavailable during a rollout.

Example of a more sequential rollout configuration:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 12
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: registry.example.com/orders-api:2026.11
          ports:
            - name: http
              containerPort: 8080
~~~

With this configuration, during a rolling update, the Deployment can create at most one extra Pod above the desired replica count and does not proactively reduce available Pods per `maxUnavailable: 0`. The new Pod must reach readiness before the controller continues replacing further Pods per rollout rules.

Specific values must fit cluster capacity and dependency load. If each new Pod creates 100 connections during startup, `maxSurge: 1` can still create noticeable load. Pods being created by other Deployments must also be accounted for.

### 3.1. maxSurge Does Not Limit All Forms of Scale-Up

Understand the scope of the rollout strategy:

- `maxSurge` and `maxUnavailable` govern Deployment rolling updates.
- When increasing `spec.replicas` or during HPA scale-up, Pod counts can increase according to separate scaling rules.
- Multiple Deployments may roll out concurrently, each with its own `maxSurge`.
- A custom restore controller may have its own Pod creation mechanism.

Therefore, do not treat `maxSurge: 1` as a cluster-wide limit. If multiple workloads start simultaneously, a total load budget or higher-level coordination mechanism is needed.

### 3.2. HPA and Scale-Up Velocity

HorizontalPodAutoscaler can create many additional replicas when metrics rise. If the application is restoring from a checkpoint, HPA may increase the Pod count faster than dependencies can absorb.

Scale-up velocity can be capped using `behavior.scaleUp`:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 4
  maxReplicas: 30
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      selectPolicy: Min
      policies:
        - type: Pods
          value: 2
          periodSeconds: 60
        - type: Percent
          value: 25
          periodSeconds: 60
~~~

This example limits how many Pods can be added per window according to the declared policies. This is an illustrative configuration; adjust for Kubernetes version, metrics, and load requirements.

HPA does not directly understand that Redis or a database is overloaded if it only monitors Pod CPU. Custom metrics or external metrics reflecting queue depth, dependency latency, connection utilization, or backend capacity may be required.

### 3.3. Avoiding Autoscaling Adding Load When Dependencies Are Bottlenecked

A system can enter a feedback loop:

1. A slow database prolongs Pod requests.
2. CPU or request queues rise.
3. HPA increases Pod count.
4. New Pods open connections and warm up simultaneously.
5. The database receives additional load and slows down further.

If the bottleneck is in a dependency, adding application replicas can worsen the situation. Set scale limits and inspect dependency metrics before allowing rapid HPA scale-up.

## 4. StatefulSets and Ordered Recovery

For workloads needing stable identity or dedicated storage, a StatefulSet may fit better than a Deployment. StatefulSets support ordered Pod creation, deletion, and updates by ordinal.

By default, `podManagementPolicy: OrderedReady` requires Pods to be created sequentially and the previous Pod to become Ready before creating the next Pod. `Parallel` allows creating or deleting Pods more concurrently.

~~~yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: worker
spec:
  serviceName: worker
  replicas: 6
  podManagementPolicy: OrderedReady
  selector:
    matchLabels:
      app: worker
  template:
    metadata:
      labels:
        app: worker
    spec:
      containers:
        - name: app
          image: registry.example.com/worker:2026.11
~~~

With `OrderedReady`, each Pod's readiness becomes part of the progression order. This can reduce spikes when sequential startup is needed.

### 4.1. Rolling Updates with Partition

StatefulSets support `updateStrategy.rollingUpdate.partition` to control which ordinals get updated. This is a way to stage updates, useful when testing restore on a subset of Pods first.

Example:

~~~yaml
spec:
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      partition: 5
~~~

For a StatefulSet with ordinals 0 through 5, partition 5 leaves Pods with ordinals below 5 un-updated while Pods with ordinal 5 and above are in the update scope. The partition can be lowered step by step after checking updated Pods.

Verify exact StatefulSet semantics and rollout state before using this in a real workflow. Partition controls updates; it is not a request limiter to the database.

### 4.2. When Should Ordering Not Be Forced?

Sequential startup reduces bursts but lengthens rollout duration. If each Pod takes 90 seconds to reconnect and warm up, 20 Pods sequentially can take a very long time.

You can choose a batch size greater than one, or perform lightweight warm-up first and then allow multiple Pods to reach readiness in waves. Parallelism must be based on dependency capacity and acceptable recovery time.

## 5. Readiness, Startup Probes, and Liveness Probes

Kubernetes probes distinguish whether a process has started, can serve traffic, and is alive. They are critical tools for preventing unready Pods from receiving requests.

### 5.1. Startup Probe

The startup probe is intended for applications needing long startup times. While the startup probe has not yet succeeded, Kubernetes does not run readiness and liveness probes in the usual way.

The startup probe can give the application enough time to restore, initialize the JVM, and complete required startup steps.

### 5.2. Readiness Probe

The readiness probe determines whether a Pod should receive traffic from a Service. When readiness fails, the Pod is not considered a ready endpoint for the corresponding Service.

Readiness should verify prerequisites for serving requests, for example:

- The application has finished restoring and initializing.
- Clients to the database or Redis are ready if requests require them.
- Essential caches have been warmed up or have safe fallbacks.
- Consumers or workers have started if the Pod handles jobs.
- The admission gate is open.

**Readiness does not restrict outbound requests.** An unready Pod can still call databases, Redis, or identity providers inside callbacks and background initialization. Therefore, load must still be limited inside the application and at the fleet level.

### 5.3. Liveness Probe

The liveness probe determines whether a container needs to be restarted. Do not make liveness directly depend on a database or Redis that can become temporarily slow. If a slow dependency causes all Pods to fail liveness, Kubernetes can restart them en masse and increase reconnect load further.

Liveness should focus on whether the process is still running and able to make progress. Readiness is more appropriate for indicating unready dependencies.

### 5.4. Probe Example

~~~yaml
containers:
  - name: app
    image: registry.example.com/orders-api:2026.11
    ports:
      - name: http
        containerPort: 8080
    startupProbe:
      httpGet:
        path: /health/startup
        port: http
      periodSeconds: 5
      failureThreshold: 60
    readinessProbe:
      httpGet:
        path: /health/ready
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
    livenessProbe:
      httpGet:
        path: /health/live
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
~~~

The paths are application-provided endpoints. `failureThreshold` and `periodSeconds` must align with restore times and SLAs. Do not set timeouts too low such that probes themselves add pressure while the JVM is busy initializing.

### 5.5. Pod Readiness and Readiness Gates

Readiness gates can add conditions from an external controller via Pod conditions. For example, a restore coordinator can mark a Pod eligible to receive traffic only after checking dependencies or granting a slot in the restore budget.

Readiness gates only take effect when a controller or component updates the corresponding condition. Kubernetes does not automatically know CRaC callback status unless the application provides a signal.

## 6. Readiness Is Not a Dependency Throttling Mechanism

A common design mistake is keeping a Pod in the NotReady state while still letting post-restore callbacks immediately create full pools and run warm-up.

Services will not send inbound traffic to an unready Pod, yet the Pod can still actively:

- Open connections to the database.
- Create Redis connection pools.
- Load data from APIs.
- Register hundreds of consumers.
- Send health checks to dependencies.
- Execute warm-up requests.

Thus, readiness protects the inbound path, while outbound load needs a dedicated mechanism.

A Pod can have staged internal states:

| State | Action | Readiness |
|---|---|---|
| RESTORING | Recover process and JVM | NOT_READY |
| REINITIALIZING | Recreate required resources | NOT_READY |
| WAITING_FOR_BUDGET | Wait for a slot or token to warm up | NOT_READY |
| WARMING | Run bounded warm-up | NOT_READY |
| VERIFYING | Verify dependencies and functionality | NOT_READY |
| READY | Allow accepting traffic | READY |
| DEGRADED | An optional dependency failed, fallback allowed | Per capability/policy |

Applications should expose an explicit readiness state rather than merely checking whether the process returns HTTP 200.

## 7. Limiting Concurrency During Dependency Initialization

Even when Kubernetes restores only a few Pods at once, each Pod can still generate many parallel internal requests. Concurrency must be bounded at the Pod level.

For example, instead of opening full connection pools and warming up 100 keys simultaneously, you can:

- Create few initial connections.
- Expand the pool according to actual demand.
- Load caches in small batches.
- Limit concurrent warm-up requests.
- Separate critical and optional warm-up.
- Use semaphores or bounded executors.
- Set timeouts on each operation.

### 7.1. Semaphore Limiting Concurrent Operations

Example abstraction in Java:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class DependencyGate {

    private final Semaphore permits;

    public DependencyGate(int maxConcurrent) {
        this.permits = new Semaphore(maxConcurrent);
    }

    public <T> T execute(
            CheckedSupplier<T> operation,
            long timeout,
            TimeUnit unit) throws Exception {

        if (!permits.tryAcquire(timeout, unit)) {
            throw new IllegalStateException(
                "Dependency warm-up capacity is unavailable"
            );
        }

        try {
            return operation.get();
        } finally {
            permits.release();
        }
    }

    @FunctionalInterface
    public interface CheckedSupplier<T> {
        T get() throws Exception;
    }
}
~~~

This semaphore limits concurrency inside a single Pod. If each Pod has 4 permits and there are 50 Pods, the fleet can still produce up to 200 concurrent operations. Capping total load requires an additional fleet-wide mechanism or limits at the dependency.

### 7.2. Separating Warm-Up Pools from Request-Serving Pools

Warm-up can contend for connections with live serving traffic. Dedicated pools or quotas can be used for initialization work, yet total connections must still remain within the dependency budget.

For example, if the database allows the application only 500 connections:

- Reserve the majority for serving traffic.
- Cap warm-up connections.
- Keep a reserve for failovers and operational tasks.
- Do not let each Pod pick its maximum pool size independently without accounting for total replicas.

Splitting pools helps classify and prioritize, but does not create additional database capacity.

## 8. Limiting Load at the Fleet Level

A local semaphore cannot cap the total number of Pods. Several strategies exist to coordinate load across the fleet.

### 8.1. Batched Rollouts

Create or restore a small batch of Pods, wait for them to reach readiness and for dependency load to stabilize, and only then proceed to the next batch.

Advantages:

- Easy to understand and observe.
- No separate distributed limiter needed if the rollout controller is sufficient.
- Progression can be halted when the backend shows signs of overload.

Limitations:

- Rollout duration increases.
- Different Deployments or clusters may still start simultaneously.
- Scale-ups outside rollouts may not follow the same batching.

### 8.2. Restore Budget or Admission Tokens

A fleet-level orchestration component can issue a limited number of tokens. Each Pod starts heavy connection/warm-up steps only while holding a token.

For example, if the budget is 3 Pods warming up concurrently, only 3 Pods are permitted to run that step. When a Pod finishes or times out, the token is returned.

This can be implemented via:

- A controller/operator managing Pod conditions.
- An external queue or coordinator.
- Leases with TTLs in a control-plane store.
- A token-issuing service.
- A rollout system with pause/resume and analysis steps.

If using Redis or a database to issue tokens, account for the coordinator's own load. Avoid turning the very dependency being protected into a single bottleneck for the restore budget. TTLs/leases are needed so tokens are not held forever if a Pod crashes.

### 8.3. Token Buckets at Gateways or Dependencies

Rate limiters at API gateways or dependencies can limit total requests over time. A token bucket allows small bursts while capping average rates.

For example, a dependency permits 100 requests/second with a burst of 20. Requests exceeding the limit can be delayed or rejected in a controlled manner.

Rate limits at dependencies protect the backend even when multiple applications start together. However, applications must handle 429 responses or quota errors with backoff rather than retrying immediately.

### 8.4. Batching by Node Pool or Zone

If multiple Pods restoring together can pressure networks, storage, or dependencies, staging across availability zones or node pools helps spread infrastructure load.

However, spreading across zones does not automatically limit requests to a shared database. Rate limits or concurrency budgets for the dependency are still required.

## 9. Retrying with Backoff and Jitter

After restore, dependencies may not yet be ready. Retries are necessary, yet simultaneous retries from many Pods amplify load.

### 9.1. Exponential Backoff

Wait intervals increase with failure count:

| Attempt | Illustrative delay |
|---|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.6 s |
| 5 | 3.2 s |

Set an appropriate maximum delay, overall deadline, and retry count. Do not endlessly retry configuration or authentication errors.

### 9.2. Jitter

If every Pod uses the same fixed backoff schedule, they can retry simultaneously after 200 ms, 400 ms, 800 ms. Jitter adds randomness to spread requests out.

Full jitter example:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryDelay {

    public static Duration fullJitter(
            int attempt,
            Duration base,
            Duration maximum) {

        long multiplier = 1L << Math.min(attempt, 20);
        long cap;

        try {
            cap = Math.min(
                maximum.toMillis(),
                Math.multiplyExact(base.toMillis(), multiplier)
            );
        } catch (ArithmeticException e) {
            cap = maximum.toMillis();
        }

        long delay = ThreadLocalRandom.current()
                .nextLong(Math.max(1, cap + 1));

        return Duration.ofMillis(delay);
    }
}
~~~

This is an illustrative example. In production, handle negative attempts, overflow, and overall deadlines. A proven retry library can be used if it supports jitter and retry budgets.

### 9.3. Retry Budgets

Limiting total retry count or total retry duration prevents a fleet from continuously generating load when a dependency is broken.

When the budget is exhausted:

- Keep the Pod NotReady if the dependency is mandatory.
- Switch to degraded mode if fallback is safe.
- Emit metrics and logs.
- Let the controller decide to continue, pause, or roll back the rollout.

Do not let the liveness probe restart Pods merely because a dependency has not recovered; restarts repeat the reconnection process and can create a larger storm.

## 10. Connection Pools and System-Wide Connection Budgets

Pool sizes must be calculated at the fleet level, not just for a single Pod.

Suppose a database has a 600-connection limit allocated for the application. The system has:

- 30 Pods currently serving.
- 10 new Pods restoring.
- Some connections reserved for migrations, monitoring, and operations.

If each Pod has a maximum pool size of 20, the potential total connections for 40 Pods is 800, not counting other components. A pool size that looks reasonable for a single Pod can still exceed limits when multiplied by replicas.

### 10.1. Simple Budget Formula

You can estimate:

\[
C_{\text{total}} =
N_{\text{ready}} \times C_{\text{ready}}
+
N_{\text{restoring}} \times C_{\text{restore}}
+
C_{\text{other}}
\]

Where:

- \(N_{\text{ready}}\): number of Pods currently serving.
- \(C_{\text{ready}}\): average or maximum connections per serving Pod.
- \(N_{\text{restoring}}\): number of Pods initializing.
- \(C_{\text{restore}}\): connections created by each Pod during restore.
- \(C_{\text{other}}\): connections from jobs, migrations, admins, and other applications.

This total must stay below the connection budget allocated to the application, with headroom for failovers and load fluctuations.

### 10.2. Lazy Pool Initialization

A pool can be configured not to open all connections immediately upon creation. Lazy initialization or capping minimum idle connections reduces bursts.

Verify the semantics of the pool library in use. Some pools create connections on demand, while others prefill or run validation at startup.

### 10.3. Splitting Limits by Workload

Separate budgets can be allocated for:

- Synchronous requests.
- Background workers.
- Cache warm-up.
- Scheduled tasks.
- Health checks.

If warm-up consumes all connections, real requests can be blocked as soon as the Pod becomes Ready. If request pools are too large, background workers can starve or exhaust connections while the system is recovering.

## 11. Cache Warm-Up and Avoiding Thundering Herds

Many Pods restoring local caches together can trigger a flood of queries to Redis or the database.

### 11.1. Warm Up Only Essential Data

Categorize caches into groups:

| Group | Example | Strategy |
|---|---|---|
| Critical | Configuration and metadata needed for all requests | Preload, with timeout |
| High-use | Popular keys | Warm up in batches |
| Optional | Infrequently used data | Lazy load |
| Sensitive | Permissions, tokens, sessions | Refresh or check source |
| Versioned | Generation-tagged data | Keep if version still matches |

Do not clear and reload the entire cache across all Pods if only part of the data needs refreshing.

### 11.2. Batching and Concurrency Limits

Instead of reading 10,000 keys at once, split into small batches, limit concurrent batches, and set a timeout per batch.

Multi-get or pipelining can be used if the Redis/database client supports it and semantics fit. Batching reduces round trips, though overly large payloads can cause memory and latency spikes.

### 11.3. Per-Key Single-Flight

Within the same Pod, if multiple requests hit a cache miss simultaneously, only one request should fetch the data; other requests wait for the same result or use a stale value if allowed.

Local single-flight only prevents duplication inside one Pod. Multiple Pods can still refresh the same key together. If fleet-wide coordination is needed, distributed locks or a cache refresh coordinator can be used, though the added complexity and load of that mechanism must be accounted for.

### 11.4. TTL Jitter

Avoid setting identical TTLs for batches of entries or Pods if expiration could synchronize. Adding jitter to expiry or staggering warm-up times reduces simultaneous query waves.

For tokens, permissions, or sensitive data, do not add jitter that allows data to be used past its valid expiration.

## 12. Controlling Broker Consumers and Background Workers

Restoring multiple Pods can hit the broker with a large wave of new consumers. Creating consumers en masse can trigger rebalances, increase heartbeats, and disrupt partition assignments.

Consider:

- Limiting consumers per Pod.
- Starting consumers after dependencies and worker pools are ready.
- Staggering consumer startup.
- Limiting concurrently processed messages.
- Applying backpressure when worker queues are full.
- Handling pending or redelivered messages.
- Using idempotency to tolerate duplicate deliveries.
- ACKing/committing only after business processing has been persisted.

If one Pod has 8 consumers and 30 Pods restore together, the broker may have to handle 240 new consumers in a short span. Compare this against partition counts and broker capacity.

### 12.1. Distinguishing Pod Startup from Starting Consumption

A Pod can reach process-ready status before starting consumption. A safe sequence:

1. Restore the JVM.
2. Initialize connections and worker pools.
3. Verify the broker.
4. Register consumers in batches or under a budget.
5. Confirm subscriptions and partition assignments.
6. Begin receiving messages.
7. Transition the Pod to Ready for its worker role.

For workers not serving HTTP traffic, readiness can be represented via a custom health state or dedicated controller mechanism. Do not use a simple HTTP probe merely reporting the process is alive if the worker cannot yet accept jobs.

## 13. Controlling Warm-Up Requests and Health Checks

Warm-up requests are typically designed to warm up JIT, serializers, or caches. Yet if every Pod calls the same endpoints at once, the system can generate load indistinguishable from real traffic.

Recommendations:

- Pick a small representative set of endpoints.
- Use read-only or sandbox data.
- Limit concurrent requests.
- Add jitter between Pods.
- Use internal endpoints or a controlled warm-up mode.
- Do not warm up every rare branch.
- Avoid running warm-up through payment systems or real side effects.

Health checks must also be lightweight. If readiness runs a heavy database query every 2 seconds across 100 Pods, probes themselves can generate significant load.

It is better for the application to update readiness state from rate-limited checks rather than calling all dependencies on every probe.

## 14. Circuit Breakers, Bulkheads, and Backpressure

These three design patterns prevent a slow dependency from impacting the entire application.

### 14.1. Circuit Breakers

A circuit breaker tracks errors and latency. When errors exceed a threshold, it pauses sending requests to the dependency to avoid adding load.

Common states:

- Closed: allows requests.
- Open: rejects or falls back for a period.
- Half-open: allows a few trial requests to check if the dependency has recovered.

After restore, do not let all Pods transition to half-open and send probes at the exact same moment. Jitter or limits on probes per interval are needed.

### 14.2. Bulkheads

Bulkheads isolate resources per dependency or workload. For example, a Redis pool does not share a semaphore with the database; warm-up does not exhaust the executor reserved for requests.

This limits blast radius when one backend slows down.

### 14.3. Backpressure

Backpressure slows down or rejects new work when the system lacks capacity.

Examples:

- Cap queue sizes.
- Cap concurrent requests.
- Return 429 or 503 when overloaded.
- Pause consumers when worker queues are full.
- Do not open additional connections once the pool reaches its limit.

Do not leave queues unbounded. Large queues only mask overload while increasing latency and memory usage.

## 15. Avoiding Duplicate Background Work When Restoring Multiple Replicas

If multiple Pods are created from the same checkpoint, they may restore identical heap state. This is especially important for:

- Schedulers that have already scheduled a job.
- Counters or sequences stored only in memory.
- Singleton tasks.
- Leader election state.
- In-memory locks.
- Stateful random generators or ID generators.
- Consumer state.
- Jobs running at checkpoint time.

If every Pod continues the same task, side effects may repeat multiple times.

### 15.1. Do Not Rely on In-Heap Singletons to Guarantee Cluster-Wide Singletons

A static variable or singleton in a Spring context is only a singleton within one process. When restoring 20 Pods, there are 20 copies of that singleton.

If a scheduled task must run at most once system-wide, a distributed mechanism is needed:

- Leader election.
- Distributed leases.
- Database job claims.
- Queue consumer groups.
- Unique constraints or idempotency keys.

After restore, a Pod must verify current lease ownership before resuming work. Do not use a lock object restored in the heap as proof that the Pod is still the leader.

### 15.2. Jobs Need a Durable Source of State

Business tasks should be represented by a job ID or command descriptor stored durably. After restore, Pods check job status and claim work atomically.

If multiple Pods see the same pending job, only one Pod claims it successfully. Remaining Pods move on to other work.

### 15.3. Fencing and Leases

A lease may expire while a Pod is checkpointed. An old Pod restoring later may believe it still holds ownership.

Fencing tokens or monotonically increasing generations help the target system reject operations from old owners. For critical sections, checking a boolean in the heap is not enough.

## 16. Java Example: Readiness and Bounded Dependency Initialization

The example below illustrates a Pod-level lifecycle coordinator. The interfaces are application abstractions, not built-in CRaC or Kubernetes APIs.

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class PodRestoreResource implements Resource {

    public enum State {
        RESTORING,
        WAITING_FOR_CAPACITY,
        INITIALIZING,
        WARMING,
        READY,
        UNAVAILABLE
    }

    private final DependencyFactory dependencyFactory;
    private final WarmupService warmupService;
    private final ReadinessPublisher readiness;
    private final int maxConcurrentWarmups;

    private final AtomicReference<State> state =
            new AtomicReference<>(State.RESTORING);

    private volatile DependencyRuntime runtime;

    public PodRestoreResource(
            DependencyFactory dependencyFactory,
            WarmupService warmupService,
            ReadinessPublisher readiness,
            int maxConcurrentWarmups) {

        this.dependencyFactory = dependencyFactory;
        this.warmupService = warmupService;
        this.readiness = readiness;
        if (maxConcurrentWarmups <= 0) {
            throw new IllegalArgumentException(
                "maxConcurrentWarmups must be positive"
            );
        }
        this.maxConcurrentWarmups = maxConcurrentWarmups;

        readiness.notReady();
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        state.set(State.RESTORING);
        readiness.notReady();

        warmupService.stopAccepting();
        warmupService.drain();

        DependencyRuntime old = runtime;
        runtime = null;

        if (old != null) {
            old.close();
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        readiness.notReady();
        state.set(State.WAITING_FOR_CAPACITY);

        DependencyRuntime restored = null;

        try {
            state.set(State.INITIALIZING);

            restored = dependencyFactory.createAndConnect();

            restored.verifyRequiredDependencies();

            state.set(State.WARMING);
            warmupService.warmCriticalData(
                restored,
                maxConcurrentWarmups
            );

            warmupService.attach(restored);
            runtime = restored;
            warmupService.resumeAccepting();

            state.set(State.READY);
            readiness.ready();

        } catch (Exception e) {
            state.set(State.UNAVAILABLE);
            readiness.notReady();

            if (restored != null) {
                runtime = null;
                restored.close();
            }

            throw e;
        }
    }

    public State state() {
        return state.get();
    }
}
~~~

The example demonstrates several principles:

- Readiness is set to NOT_READY during preparation.
- Warm-up receives a per-Pod concurrency limit; `WarmupService` must enforce that limit using a bounded executor or semaphore.
- Dependencies are created and verified before opening admission.
- If initialization fails, the Pod remains in an unavailable state.
- The old runtime is closed before checkpoint.

The `maxConcurrentWarmups` limit in the example applies only within one Pod. It does not cap the total number of Pods warming up. A fleet-wide limit requires an external coordinator or rollout/scale caps. `WarmupService` also needs to ensure all tasks finish or are handled before the callback returns.

In production, add separate timeouts for connect, health checks, and warm-up; manage error state if `beforeCheckpoint()` fails; assign the new runtime only after verification and initialization succeed; and align each client's lifecycle with its exact library.

## 17. Kubernetes Example: Pod Ready Only After Dependencies Are Ready

An application can expose three endpoints:

- `/health/startup`: the JVM and restore process have finished basic initialization.
- `/health/ready`: essential dependencies and critical warm-up are ready.
- `/health/live`: the process can still make progress, with no deadlocks or severe internal corruption.

Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 8
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: registry.example.com/orders-api:2026.11
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

This configuration illustrates a rollout with bounded surge where Pods receive traffic only when readiness succeeds. It does not automatically limit outbound connections created by callbacks. That part still requires pool sizing, semaphores, retry budgets, and fleet-wide pacing.

### 17.1. PodDisruptionBudget Is Not a Rate Limiter

PodDisruptionBudget (PDB) limits how many Pods can be disrupted by voluntary disruptions through the eviction API, such as certain node drain operations.

A PDB does not:

- Limit requests sent by each Pod to the database.
- Throttle reconnects to Redis.
- Limit HPA scale-up.
- Replace Deployment rolling update strategies.
- Coordinate warm-up workloads across the fleet.

PDBs are useful for keeping enough serving capacity during certain node maintenance scenarios, but must be used for their intended purpose.

## 18. Calculating Batch Size by Dependency Capacity

Suppose a database has a 240-connection budget for this application. Serving Pods use up to 160 connections. 40 connections must be reserved for traffic fluctuations and operational tasks. That leaves only about 40 connections for the restore phase.

If each new Pod creates up to 8 connections during warm-up, the number of Pods that can initialize concurrently within this budget is:

\[
N_{\text{batch}} \leq
\left\lfloor \frac{40}{8} \right\rfloor = 5
\]

This is only a simple estimate. Add connections from other applications, pools growing under load, idle connections, and failover operations. Use real measurements and maintain headroom.

### 18.1. Account for Request Rate Too

Connection count does not reflect total load. One connection can send hundreds of requests per second; many other connections may merely sit idle.

Also account for:

- Requests per second.
- Concurrent requests.
- Query duration.
- Connection acquisition wait.
- Dependency CPU and I/O.
- Cache hit/miss ratios.
- Authentication rate.
- Consumer count and rebalance rate.

Batch size should be based on actual limiting metrics of the dependency.

### 18.2. Start Small Then Increase Conditionally

A rollout workflow can:

1. Restore one Pod.
2. Wait for the Pod to become Ready and observe dependencies for a period.
3. Check connection counts, latency, and error rates.
4. Restore another small batch.
5. Pause if a dependency exceeds thresholds.
6. Resume once the system stabilizes.

This slows down rollouts, yet allows adapting to real load instead of assuming capacity.

## 19. Dependency Initialization Ordering

A Pod may depend on multiple services. Do not create all connections and warm-up in parallel without considering dependencies.

Example order:

1. Read current configuration and secrets.
2. Establish DNS/service discovery.
3. Connect to required foundational dependencies.
4. Authenticate and verify permissions.
5. Initialize required caches or metadata.
6. Start worker pools.
7. Restore consumers and subscriptions.
8. Run warm-up requests.
9. Open admission and readiness.

The exact order depends on architecture. For example, if Redis is used to issue restore tokens, Redis must be ready before the token-acquisition step. Conversely, if Redis itself is the dependency being protected, do not generate a large wave of coordinator requests against Redis.

### 19.1. Sequential and Bounded Parallel Initialization

Some independent dependencies can initialize in parallel, though concurrency must be bounded. Dependencies with dependency relationships must initialize in order.

A startup coordinator can be grouped:

- Mandatory group: database or configuration service.
- Cache group: Redis, local cache, metadata.
- Messaging group: broker and consumers.
- Optional group: telemetry exporters or auxiliary integrations.

If an optional dependency is unavailable, the application can continue in degraded mode if business logic permits. Do not let a broken telemetry exporter block an entire Pod if it is not a request-serving dependency.

## 20. Multi-Pod Restores and Special Scenarios

### 20.1. Multiple Deployments Restoring Together

Each Deployment may configure `maxSurge: 1`, yet if 10 Deployments roll out together, 10 new Pods may initialize simultaneously.

Coordinate at the release or cluster level:

- Order rollouts across services.
- Use pipelines with approval/analysis steps when needed.
- Use a shared restore coordinator.
- Limit total concurrently running warm-ups.
- Monitor shared dependencies.

### 20.2. Scaling from Zero to Many Replicas

Scaling from 0 to 50 replicas is not always subject to the same limits as rolling updates. Limit HPA scale-up, use batching, or use a dedicated controller if controlled recovery is needed.

### 20.3. Node Restarts or Zone Recovery

When a node or zone recovers, many Pods may be rescheduled at once. PodDisruptionBudgets do not protect against unexpected outages and do not throttle reconnect storms after node failures.

Capacity planning, topology spread, autoscaling limits, and application-side backoff are required.

### 20.4. Dependencies Also Restoring

If the database, Redis, or broker is also recovering, applications should not retry rapidly in lockstep. Use retry budgets, jitter, circuit breakers, and readiness. Platform-orchestrator-managed dependency startup ordering may be needed.

### 20.5. Checkpoints Containing Scheduled Tasks or Leader State

If multiple Pods are restored from identical state, every Pod may carry the same scheduled tasks. Identify which tasks must run only once system-wide and shift ownership to leases/leader election with fencing. Do not rely on in-heap singletons.

## 21. Observing Load and Rollout Pause Conditions

To coordinate the fleet, monitor both Pods and dependencies.

### 21.1. Pod-Level Metrics

- Restore duration.
- Time to startup probe success.
- Time to readiness.
- Reconnect count.
- Retry count.
- Warm-up duration.
- Queue depth.
- Active/idle connection count.
- Warm-up request count.
- Readiness state and degraded state.

### 21.2. Dependency-Level Metrics

| Dependency | Metrics to monitor |
|---|---|
| Database | Active connections, connection wait, query latency, CPU, lock wait |
| Redis | Connected clients, command latency, rejected connections, memory |
| Message broker | Consumer count, rebalances, pending messages, lag |
| Identity provider | Token request rate, latency, 429/5xx, auth failures |
| HTTP service | Request rate, concurrent requests, p95/p99, error rates |
| DNS/service discovery | Lookup latency, error rate, query volume |

### 21.3. Pause Conditions

Pause the next batch when:

- Dependency latency exceeds thresholds.
- Connection utilization approaches limits.
- Error rates rise.
- Queues or consumer lag grow rapidly.
- Authentication provider returns 429.
- Retries exceed the retry budget.
- New Pods fail to reach readiness within the expected window.

A rollout controller or pipeline can use these conditions to pause and resume once the system stabilizes.

### 21.4. Correlated Logs

Tag logs with Pod UID, application version, checkpoint ID, and restore attempt. Do not use an identical ID across all replicas when individual Pods must be distinguished.

Useful events:

- Restore started/completed.
- Dependency initialization started/completed.
- Restore budget acquired/released.
- Warm-up started/completed.
- Readiness changed.
- Consumer assignment completed.
- Retry exhausted.
- Rollout paused/resumed.

Do not write credentials or sensitive payloads to logs.

## 22. Testing Multi-Pod Recovery Scenarios

Testing a single Pod is insufficient to uncover connection storms or thundering herds. Test both the fleet and dependencies.

Scenarios to include:

1. Single Pod restore under healthy dependencies.
2. Multiple Pods restoring concurrently.
3. Small-batch versus large-batch restores for comparison.
4. HPA scaling up while the database is near connection limits.
5. Redis restarting while multiple Pods reconnect.
6. Identity provider returning 429 when all Pods refresh tokens.
7. Broker rebalancing when multiple consumers join together.
8. Slow DNS or endpoint changes.
9. Simultaneous cache misses across multiple Pods.
10. One Pod failing warm-up and staying NotReady.
11. Dependency recovering after an outage.
12. Pod killed while holding a restore token or lease.
13. Node restart causing many Pods to reschedule.
14. Multiple Deployments rolling out together sharing a database.

Measure:

- Time for the entire fleet to reach desired ready replicas.
- Peak connection count.
- Peak request rate to each dependency.
- Dependency p95/p99 latency.
- Rate of 429s, timeouts, and 5xx errors.
- Retry counts and retry durations.
- Queue depth and message lag.
- Time from restore until system stability.

The goal is not merely that all Pods eventually become Ready. Prove dependencies are not overloaded along the way to reaching that state.

## 23. Practical Deployment Workflow

### Before Checkpoint

1. Identify dependencies used by each Pod.
2. Calculate connection and request budgets for maximum replicas.
3. Stop new work, drain tasks, and drain listeners.
4. Close or re-prepare resources per the CRaC lifecycle.
5. Identify which background tasks must not be duplicated across multi-Pod restores.
6. Create the checkpoint and attach the appropriate manifest/runtime profile.

### When Starting Restore or Rollout

1. Cap the number of Pods created per batch.
2. Apply appropriate HPA scale-up policies.
3. Keep Pods at NOT_READY during initialization.
4. Issue restore budgets if total warm-up needs capping.
5. Create connections and initialize dependencies under concurrency limits.
6. Retry with exponential backoff, jitter, and retry budgets.
7. Warm up caches in batches and only for essential data.
8. Restore consumers/subscriptions in order.
9. Open readiness only after essential capabilities are ready.
10. Monitor dependencies and pause the next batch if thresholds are exceeded.

### After the Fleet Stabilizes

1. Confirm ready replica count meets target.
2. Verify connection counts and request rates return to normal levels.
3. Confirm no jobs or scheduled tasks run redundantly.
4. Check cache consistency and consumer lag.
5. Record restore durations and metrics to tune batch sizes next time.

## 24. Multi-Pod Recovery Checklist

### Fleet Coordination

- [ ] There is a cap on Pods rolling out or restoring concurrently.
- [ ] HPA scale-up has appropriate policies and `maxReplicas`.
- [ ] Multiple Deployments sharing a dependency are coordinated in waves.
- [ ] Restore budgets or a coordinator exist when total warm-up must be bounded.
- [ ] Rollout pause conditions exist when dependencies are overloaded.

### Per-Pod Lifecycle

- [ ] `afterRestore()` sets the application to NOT_READY.
- [ ] Resources are recreated according to proper ownership.
- [ ] Warm-up has concurrency limits and timeouts.
- [ ] Retries have exponential backoff, jitter, and retry budgets.
- [ ] Consumers and schedulers operate only after dependencies are ready.
- [ ] Old leader leases or locks are not continued solely based on heap state.

### Kubernetes Health

- [ ] Startup probe has sufficient time for restore.
- [ ] Readiness reflects true serving capability.
- [ ] Liveness does not restart Pods merely because a dependency is temporarily slow.
- [ ] PDB is used properly for voluntary disruptions.
- [ ] Deployment strategy or StatefulSet policy matches batch sizes.

### Dependency Protection

- [ ] Pool sizes are calculated by total replicas.
- [ ] Warm-up requests are bounded.
- [ ] Rate limits or concurrency budgets exist.
- [ ] Circuit breakers, bulkheads, and backpressure are in place.
- [ ] Safe fallbacks exist without causing database stampedes.
- [ ] Metrics cover connections, latency, retries, and queues.

### Testing

- [ ] Concurrent multi-Pod restores have been tested.
- [ ] Slow or unavailable dependencies have been tested.
- [ ] HPA scale-up and node recovery have been tested.
- [ ] Consumer rebalancing and cache invalidation have been tested.
- [ ] Pod crash while holding a restore token has been tested.
- [ ] Peak load and time for the entire fleet to reach Ready have been measured.

## 25. Frequently Asked Questions

### Does Kubernetes automatically coordinate CRaC callbacks across Pods?

No. CRaC callbacks run within the lifecycle of each Java process. Kubernetes manages Pods and workloads via controllers, yet does not inherently understand full callback warm-up or dependency logic. Applications and deployment mechanisms must connect readiness, rollouts, and restore coordination.

### If a Pod is not Ready yet, can it still generate load on the database?

Yes. Readiness primarily controls whether the Pod receives traffic from a Service. Callbacks and background initialization can still open connections or send outbound requests. Load must be bounded at both the application and fleet levels.

### Does maxSurge: 1 guarantee only one Pod starts cluster-wide?

No. It applies to the rolling update of a single Deployment. HPA scale-up, scaling from 0, other Deployments, or custom controllers can create Pods simultaneously. Additional limits are needed on those mechanisms.

### Does a PodDisruptionBudget prevent connection storms?

No. A PDB protects Pod counts against certain voluntary disruptions via the eviction API. It does not limit outbound connections or requests to dependencies.

### Should the startup probe be used to wait for Redis and the database?

The startup probe can give the application time to finish starting up, but is not a rate limiter. Readiness should reflect whether essential dependencies are ready; liveness should not fail merely because Redis or the database is temporarily slow.

### Should the entire cache be warmed up on every Pod?

Usually no. Warm up only data needed to serve initial requests. Infrequently used data can be lazy-loaded. If many Pods warm up together, use batching, jitter, and concurrency limits.

### How do we limit the total number of Pods warming up?

You can cap rollouts/scaling, use a controller issuing restore tokens, or use a centralized rate limiter. A local semaphore only limits within a single Pod and is insufficient when a fleet-wide budget is needed.

### What if the database overloads during restore?

Keep new Pods at NotReady, reduce or pause the next batch, cap retries and connection creation, and use circuit breakers/backoff. Do not let liveness restart Pods en masse and create a larger reconnect storm.

### Can multiple Pods be restored from the same checkpoint?

That depends on the platform and how checkpoints are packaged. When deploying this way, examine duplicated heap state: schedulers, counters, random state, leader leases, and running jobs. Each Pod must generate an appropriate identity and verify distributed work ownership after restore.

### How do we prevent scheduled jobs from running redundantly on every Pod?

Use leader election, leases, durable job queues, atomic claims, or idempotency mechanisms. An in-heap singleton is only a single-process singleton, not a cluster-wide singleton.

### Must we wait for all Pods to be Ready before starting to accept traffic?

Not necessarily. Services can send traffic to already-Ready Pods while other Pods are restoring, provided ready Pod counts have enough capacity and rollout policies permit. Keep headroom and ensure traffic does not exceed the capacity of the currently available Pod group.

## Conclusion

Restoring multiple Pods from a checkpoint can cause sharp spikes in load against databases, Redis, brokers, identity providers, and external APIs. Readiness probes keep unready Pods from receiving inbound traffic, yet do not limit outbound connections and requests created by callbacks or warm-up. `maxSurge`, HPA policies, StatefulSet ordering, and PDBs each have distinct scopes; no single tool solves an entire dependency storm on its own.

A resilient design combines fleet-level batch coordination with per-Pod concurrency limits, connection budgets based on total replicas, retries with backoff and jitter, rate limits, circuit breakers, backpressure, and true readiness. At the same time, protect business state from duplication: schedulers, locks, and jobs must use leases, leader election, or durable state stores. Measuring peak connections, request rates, dependency latencies, and time for the entire fleet to reach Ready in multi-Pod tests will guide appropriate batch sizes and warm-up policies.
