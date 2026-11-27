# Distinguishing Health Checks, Readiness, and Load Capacity

In a **Spring Data Redis** application, Redis replying `PONG` to a `PING` is a helpful signal, yet **it does not mean** the application is ready to accept requests, all Redis operations succeed, or the system still has enough capacity for peak hours.

A Redis server can answer `PING` in a couple of milliseconds while already hitting `maxmemory` and rejecting `SET`. An application pod can be running cleanly while Redis Cluster is missing slots or clients hold stale topology. A service relying on Redis strictly for caching can keep serving via its database even when Redis disconnects. Meanwhile, a service using Redis as the sole store for sessions or task queues may no longer meet its business contract if Redis becomes unreachable.

To observe properly, distinguish three questions:

1. **Health check:** Is a specific component or operation functioning at the moment of inspection?
2. **Readiness:** Should this application instance receive **new traffic** for the functions it owns?
3. **Load capacity (*capacity/load tolerance*):** Does the system still have **headroom** to sustain throughput, latency, error rate, and resource limits as traffic grows?

These three questions are related yet non-interchangeable. This lesson explains how to design probes and monitoring with **Spring Boot Actuator, Spring Data Redis, Lettuce, Redis server metrics, and Kubernetes probes**, and how to evaluate systems when Redis is an optional cache versus a critical dependency.

## 1. Mental Map: "Alive", "Ready", and "Able to Handle Load"

```text
                      Spring Boot Application
                               |
                  +------------+-------------+
                  |            |             |
                  v            v             v
               Liveness    Readiness      Capacity / SLO
                  |            |             |
             Can the       Can it serve   HOW MANY requests
             process keep  new requests   can it serve at target
             running?      right now?     p99, error rate, memory?
                  |            |             |
             Severe        Depends on     Redis CPU, clients,
             deadlock      Redis critical command latency,
             needing       vs. optional   queues, pools, GC
             restart
```

**Liveness** asks "is this instance in a state where restarting it has a chance to recover it?". **Readiness** asks "can this instance accept additional new requests right now?". **Capacity** asks "do current and projected loads stay within what can be served while meeting SLOs?".

Examples:

| Scenario | App Liveness | App Readiness | Load Capacity |
|---|---|---|---|
| App running, Redis/cache healthy, low load | Good | Good | Has headroom |
| Redis network lost, cache falls back to DB | Likely good | May remain ready | May degrade as DB absorbs cache misses |
| Redis network lost, app cannot verify sessions | Likely good | May become not ready depending on design | Functional capacity may be 0 |
| Redis answers `PING` yet `SET` fails OOM | Good | Depends on whether writes are mandatory | Below requirement for write workloads |
| Redis running, p99 surges due to a hot key | Good | May remain ready | Lacking headroom / SLO violated |
| App starting up, initialization incomplete | May not be ready yet | Not ready | Not yet assessable |
| True application deadlock, unable to process work | Likely failed | Not ready | Zero serving capacity |
| One Redis replica lags while primary still accepts writes | Good | Depends on read routing | Read capacity and data freshness may degrade |

Never turn every bad metric into `DOWN`. If readiness flaps continuously on transient latency spikes, load balancers will drop pods one by one, concentrating load onto surviving pods and worsening the incident.

## 2. Distinguishing Terms Before Configuring

| Term | What Is Checked | Typical Action Tied to It |
|---|---|---|
| **Component health** | Redis endpoint responds, single simple command succeeds | Alerting / diagnostics |
| **Application liveness** | Application process can keep functioning | Kubernetes may restart the container |
| **Application readiness** | Instance can safely receive new traffic | Kubernetes removes/restores pod in Service endpoints |
| **Startup probe** | Application has finished booting | Delays liveness/readiness checks during startup |
| **Capacity** | Serving throughput, latency, resource usage, backlog | Scaling, load shedding, optimization |
| **SLO/SLI** | User-facing outcomes measured against service targets | SLO/error-budget alerts, remediation priority |
| **Durability/consistency** | Writes persist reliably, reads are fresh enough | Data governance, replication, fallback design |

A Redis health indicator typically checks a **narrow** set of conditions. It is not a certificate of consistency, failover capability, permissions across all ACL commands, or capacity under load.

## 3. What Does "Redis PING Succeeded" Actually Prove?

Example:

```bash
redis-cli -h redis.internal -p 6379 --user app_reader --askpass PING
```

Expected reply:

```text
PONG
```

A successful `PING` generally shows:

- The client connected to a **specific endpoint**.
- The Redis protocol responded to `PING`.
- On that connection path, authentication required to run `PING` succeeded.
- The Redis server could process **one lightweight command at that instant**.

It **does not** prove:

- The user holds `GET`/`SET`/`XACK`/`EVAL` permissions on business key namespaces.
- Redis has enough free memory for further writes.
- All Redis Cluster primaries and hash slots are reachable.
- Replicas have received recent writes so reads return fresh data.
- Whether a prior timed-out write actually executed.
- Whether a Redis Stream consumer group exists and can `ACK`.
- That the application can sustain 10,000 requests/second with p99 under 50 ms.
- That Redis won't hit a hot-key stall or failover disruption seconds later.

**`PING` is a tiny connectivity probe, not a load test or an end-to-end business validation.**

## 4. A Health Check Should Have an Explicit Scope

Instead of a vague label "Redis healthy", specify the probe contract:

```text
Name: redis-connectivity
Goal: Does the Redis endpoint reply to a lightweight command?
Call path: RedisConnectionFactory -> Redis PING
Time budget: e.g. 500 ms or per infrastructure
Result domain: UP / DOWN / UNKNOWN
Does not check: write permissions, maxmemory, multi-key, capacity
```

Another probe can define a different contract:

```text
Name: redis-critical-write-path
Goal: Can the service user perform SET with TTL in an allowed lab namespace?
Call path: StringRedisTemplate -> SET key value EX
Bounds: short timeout, dedicated key, short TTL
Does not check: peak throughput or SQL/Redis consistency
```

**Write-based** probes are costlier and have side effects compared to `PING`. Never run them at very high frequency or embed them in liveness just "to be extra sure".

## 5. Spring Boot Actuator Health Checks for Redis

In a Spring Boot application with `spring-boot-starter-actuator` and Spring Data Redis, Actuator can provide a Redis health contributor/indicator when auto-configuration conditions match.

Illustrative Gradle dependencies:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

If the application uses WebFlux, replace `spring-boot-starter-web` with `spring-boot-starter-webflux` per your chosen stack. The default Redis driver in the starter is typically Lettuce.

A local Redis configuration:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s

management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: never
```

The `prometheus` endpoint works only when the application includes the matching registry/auto-configuration (such as the Micrometer Prometheus registry); merely listing `prometheus` under `include` does not generate Prometheus data.

When the Actuator health endpoint is enabled, the base path is typically:

```text
GET /actuator/health
```

A response may look like:

```json
{
  "status": "UP"
}
```

If configured to expose components/details to authorized callers, the Redis contributor appears there. Never leak internal endpoints, authentication errors, or sensitive topology publicly to the Internet just for debugging.

### 5.1. What Does RedisHealthIndicator Mean?

The Redis health contributor is designed to check whether a Redis connection responds per the indicator contract of your Spring Boot / Spring Data Redis version. Depending on configuration, it may fetch Redis info or run a lightweight command rather than exercising full business workflows.

Therefore, never claim it verifies every key, every Redis Cluster node, or every operation type. Confirm exact behavior for your dependency versions and **name metrics/health indicators to match their actual scope**.

### 5.2. Reactive Health Indicator

When using `ReactiveRedisConnectionFactory`/WebFlux, Spring Boot can configure a matching reactive Redis health indicator. Whether imperative or reactive, a health check's meaning remains narrower than readiness or capacity.

Never call `block()` on the application's Netty event loop to build a reactive health check; for custom probes, use reactive APIs and appropriate schedulers. If a health check performs multi-step I/O, decouple it from user-facing requests and bound its frequency.

## 6. Liveness Should Not Depend on Remote Redis

Liveness is normally used to decide **when to restart an instance**. If Redis is failing while the Java process itself is healthy, restarting the application usually **cannot fix the Redis server** and only creates extra damage:

- A surge of fresh Redis connection attempts.
- Loss of in-process/local caches.
- In-flight requests interrupted mid-processing.
- Startup overhead reloading classes, JVM warmup, and connection pools.
- All pods restarting simultaneously during an outage, amplifying load.
- A "thundering herd" of connections and retries when Redis comes back up.

Dangerous example:

```text
Redis outage
    |
    +--> 40 application pods: liveness calls Redis PING
    |
    +--> PING fails
    |
    +--> Kubernetes restarts all 40 pods
    |
    +--> pods reconnect/retry simultaneously
    |
    +--> Redis outage drags on and application availability worsens
```

A **good liveness probe** reflects conditions that restarting the process can actually cure, such as a severely deadlocked runtime or an internal component unable to continue.

Even if a service strictly depends on Redis, a Redis outage can make the service **not ready**, yet still is not a default reason to mark it **not live**.

## 7. Readiness Answers Questions About New Traffic

Kubernetes readiness controls whether a pod is kept in Service endpoints to receive traffic. This differs from liveness.

A readiness probe can consider:

- Whether the application has booted and completed minimal initialization.
- Whether internal request-handling components are ready.
- Whether a dependency **required** for most workloads is usable.
- Whether the instance is gracefully shutting down and should stop accepting new requests.
- Whether the instance itself is temporarily unable to accept more traffic due to local state.

However, readiness **should not** blindly depend on **every external service**. If Redis goes down system-wide, marking all pods not ready leaves load balancers with zero endpoints, even if the application could still operate validly in degraded mode.

**Design rule:** readiness is a **traffic-routing decision**, not an aggregated status board of every Redis/DB/queue failure.

## 8. Spring Boot Actuator Liveness and Readiness Probes

Spring Boot Actuator supports health groups dedicated to Kubernetes probes when enabled.

Illustrative configuration:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info
```

Typical health group paths are:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

In Spring Boot versions supporting `add-additional-paths`, the application can expose additional paths such as:

```text
GET /livez
GET /readyz
```

on the **application's primary HTTP port**, avoiding certain "false healthy" states where a separate management server stays up while the main traffic port fails. Confirm exact paths and properties for your Spring Boot version.

Normally, the two groups rely on:

- `livenessState`: `ApplicationAvailability` liveness state.
- `readinessState`: `ApplicationAvailability` readiness state.

External indicators like Redis are **not necessarily included in the default readiness group**. That is intentional, preventing a remote dependency failure from knocking every pod out of rotation.

### Statuses and HTTP Codes

Actuator defines statuses such as `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN`, with configurable HTTP status mappings. `DOWN` and `OUT_OF_SERVICE` typically map to HTTP 503 by default.

Kubernetes probes evaluate HTTP status codes in the success range rather than parsing the JSON body. Ensure **health HTTP status mappings** align with probe behavior and never blindly map every status to HTTP 200.

## 9. Kubernetes Probes Serve Distinct Purposes

An illustrative deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: api
          image: orders-api:example
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            failureThreshold: 24
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
```

These values are illustrative only; tune them to real startup time, networking, HTTP stack, and SLOs. Never deploy an `example` image tag in production.

Meaning:

- **startupProbe:** gives the application sufficient startup time before routine liveness/readiness checks enforce limits. Repeated startup failures past the threshold can restart the container.
- **livenessProbe:** consecutive failures past threshold trigger kubelet to restart the container.
- **readinessProbe:** failure removes the pod from Service endpoints; readiness failure by itself does not restart the container.
- **failureThreshold/periodSeconds:** prevent overreacting to brief hiccups.
- **timeoutSeconds:** must cover network and probe runtime overhead.

**Never point both readiness and liveness at a custom Redis `PING` endpoint** without carefully weighing the very different consequences of failing each probe.

## 10. When Redis Is Only an Optional Cache

Consider a service reading products from PostgreSQL and caching in Redis via cache-aside:

```text
GET /products/42
      |
      v
Redis GET product:42
      |
      +--> HIT: return cached value
      |
      +--> MISS: PostgreSQL SELECT -> Redis SET -> return
      |
      +--> Redis error: PostgreSQL SELECT -> return (degraded mode)
```

Here, a Redis outage does not necessarily stop the endpoint from serving. Readiness can remain `UP` as long as the database satisfies SLOs and policy permits fallback.

However:

- Rising cache misses can overload PostgreSQL.
- Latency can spike sharply.
- Redis write and eviction errors must still be tracked.
- Not every endpoint can fall back safely.
- Concurrent database queries must be bounded.

Thus **Redis component health = DOWN** while **application readiness may stay UP**; meanwhile, **usable capacity drops** or requires load shedding.

Never treat fallback as free. An app sustaining 500 RPS without cache vs. 5,000 RPS normally may stay ready under light load yet lack capacity for peak traffic.

## 11. When Redis Is a Mandatory Dependency

Redis may hold data or enforce capabilities essential to requests:

- Session state with no fallback store.
- A rate limiter configured to fail-closed when unavailable.
- Primary command/event queue with no durable fallback.
- Distributed locks/coordination required before processing.
- Business state where Redis is the authoritative store.
- An endpoint relying on Redis Streams to ingest and process work.

If core operations cannot run without Redis, the app may need to report **not ready** or actively reject affected requests.

Example:

```text
Checkout API
   |
   +--> Redis required for session validation
   |
   +--> Redis unavailable
           |
           +--> return controlled error / fail-closed
           |
           +--> readiness decision per policy
```

Still, distinguish a **global dependency outage** from a **local instance fault**. If Redis goes down across an entire region, marking every pod not ready will not restore Redis. In some designs, keeping pods ready lets them return controlled errors rather than dropping all load-balancer endpoints. Decisions depend on routing, fallbacks, error budgets, and endpoint mixes.

## 12. Do Not Stuff Every Dependency into the Readiness Group

Suppose one application serves:

```text
GET /catalog              -> Redis cache optional
POST /orders              -> SQL required
GET /sessions/me          -> Redis session critical
POST /email/notifications -> Kafka/Stream async
```

If one readiness group includes every dependency (Redis, SQL, Kafka, search), losing any single dependency **removes the entire pod** even though other endpoints still work.

Consider:

1. Can the application be split into deployments/services by dependency profile?
2. Can endpoints degrade gracefully individually instead of taking down the whole pod?
3. Are there endpoints truly incapable of serving when a dependency fails?
4. Can the load balancer route by capability rather than only by pod?
5. During a region-wide dependency outage, does dropping every pod worsen downtime?
6. Should you separate an **operational health dashboard** from traffic readiness?

Actuator health contributors give dependency visibility; **not every contributor needs to gate Kubernetes readiness**.

## 13. Including Redis in Readiness Deliberately

If Redis is truly mandatory and readiness should depend on it, configure the health group explicitly.

Example Spring Boot YAML:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,redis
```

This illustrates an application whose health contributor ID is `redis`. Confirm the **exact contributor ID** in Actuator/auto-configuration, especially when using multiple Redis factories or custom indicators.

`readinessState` preserves application availability state, while `redis` folds the Redis health contributor into the group verdict. If the Redis indicator is `DOWN`, the readiness group returns HTTP 503 under default aggregation.

**Never apply this blindly to every Redis-backed service.** For an optional Redis cache, this stops all traffic the moment Redis fails even though the database could keep serving.

### Changing a Health Group Does Not Replace Business Error Handling

Even when readiness is `UP`, an `XADD` can fail with `NOPERM` or `SET` with `OOM`. Health groups never replace error handling, retries, idempotency, and degraded-mode logic in service code.

## 14. Separating Dependency Health Dashboards from Traffic Readiness

A clean, observable separation:

```text
/actuator/health/liveness
    -> livenessState, minimal internal checks

/actuator/health/readiness
    -> readinessState and dependencies that truly govern traffic

/actuator/health
    -> aggregated overview, restricted to authorized operations access

Metrics + traces + logs
    -> Redis latency, errors, memory, saturation, cache efficiency
```

Never point an external load balancer or orchestrator at the aggregate `/actuator/health` and assume any `DOWN` contributor means the app must be restarted.

If you want dedicated health groups like `redisDependency` or `criticalWritePath`, define them in Actuator independently of readiness. Regardless of grouping, restrict access and never leak Redis server or ACL details publicly.

## 15. Read-Only vs. Synthetic Write Health Checks

A Redis `PING` tests very little. A functional probe can verify write permissions or keyspace access by writing a synthetic key.

### Read-Only Probe

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Component;

@Component("redisConnectivityProbe")
public class RedisConnectivityProbe implements HealthIndicator {

    private final RedisConnectionFactory factory;

    public RedisConnectivityProbe(RedisConnectionFactory factory) {
        this.factory = factory;
    }

    @Override
    public Health health() {
        try (var connection = factory.getConnection()) {
            String reply = connection.ping();
            return "PONG".equalsIgnoreCase(reply)
                    ? Health.up().build()
                    : Health.down().withDetail("reason", "Unexpected PING").build();
        } catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("type", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
```

This example checks connectivity of one connection per the Spring Data Redis API. Do not label it "capacity healthy".

Depending on configuration and driver, the factory may wrap connections with specific lifecycle rules; follow your Spring Data Redis version's contract in production. Reuse built-in contributors when sufficient rather than duplicating `PING` calls.

### Synthetic Write Probe

A custom probe can write to a dedicated Redis key:

```java
import java.time.Duration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component("redisWriteProbe")
public class RedisWriteProbe implements HealthIndicator {

    private static final String KEY = "health:app:write-probe";

    private final StringRedisTemplate redis;

    public RedisWriteProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public Health health() {
        try {
            Boolean result = redis.opsForValue().set(
                    KEY, "ok", Duration.ofSeconds(15));

            return Boolean.TRUE.equals(result)
                    ? Health.up().build()
                    : Health.down()
                        .withDetail("reason", "Write not acknowledged")
                        .build();
        } catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("type", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
```

This is a **probe with side effects**. If included in a health group polled frequently by Kubernetes, every pod generates continuous Redis writes. Keep in mind:

- Use a dedicated key namespace and least-privilege ACLs.
- Always set a TTL so keys do not linger forever.
- Bound timeouts, frequency, and resource impact.
- Never store sensitive data in the key or value.
- If multiple pods share one key, they overwrite the same entry; that does not independently validate business keys.
- One successful `SET` does not verify scripts, stream groups, other slots, or other commands.
- Redis Cluster: a single probe key maps to **one hash slot**, not all primaries.
- Never place a write probe into liveness.
- Usually run synthetic writes **less frequently** than readiness polls—for instance, in a scheduled diagnostics job with cached status—if your architecture genuinely needs it.

## 16. Choose Checks by Workflow, Not Technology Name

If a service only calls `GET`, `PING` helps verify connectivity yet misses key serializers, prefixes, or `GET` permissions. If a service produces Redis Stream events, `PING` certainly does not confirm `XADD` works.

Probe matrix:

| Workload | Narrow Check | Deeper Check | Risks to Watch |
|---|---|---|---|
| Cache reads | `PING`/connectivity | `GET` a pre-created synthetic key | Cache miss is not an infra error |
| Cache writes | `PING` | `SET` with TTL on dedicated key | OOM/ACLs can block writes |
| Redis sessions | Connectivity | Read/write synthetic session matching schema | Never overwrite real sessions |
| Counters / rate limiters | Connectivity | Synthetic `INCR` with TTL/bounds | Side effects, TTLs, and retries |
| Redis Streams producer | Connectivity | `XADD` to an isolated lab stream | Stream growth and retention |
| Stream consumer | Connectivity | Verify group/ACK path in controlled env | Never ACK real user messages |
| Redis Cluster | Seed reachable | Probe slots/node endpoints within scope | Single-key probe misses whole cluster |
| Lua logic | Connectivity | Synthetic script on dedicated key | `EVAL` ACLs and side effects |

Deep probes belong in **diagnostics or controlled periodic checks**, not blindly executed inside an endpoint Kubernetes hits every few seconds.

## 17. Redis Answers PING While Writes Fail with OOM

Redis can reply:

```text
PONG
```

yet when the application runs:

```bash
redis-cli SET cache:product:42 some-value
```

the server responds:

```text
OOM command not allowed when used memory > 'maxmemory'.
```

Causes typically involve `maxmemory`, `maxmemory-policy`, key expiration/eviction, or non-evictable data.

Consequences:

- Connectivity health remains `UP`.
- Readiness may stay unchanged if Redis is an optional cache.
- Services that must write to Redis can fail their workflows.
- Write capacity drops to near zero for commands requiring extra memory.
- `GET` may keep succeeding, creating asymmetric read/write failures.
- Redis Streams `XADD` can fail even while consumers keep reading existing messages.

**A `PING`-only health check cannot replace memory metrics and real command success/error monitoring.**

## 18. Redis Server Data to Monitor

An authorized Redis admin/operator can inspect:

```bash
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO memory
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO stats
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO clients
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO commandstats
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO replication
```

Commands may be restricted by Redis ACLs or managed services. Never grant admin privileges to the application just so a health check can inspect extra metrics.

Typical metrics:

| Metric / Group | What to Understand |
|---|---|
| `used_memory` / `maxmemory` | Does Redis still have memory headroom under its policy? |
| `used_memory_rss` | Is resident memory approaching container/host budgets? |
| `mem_fragmentation_ratio` | Is there notable allocator overhead or fragmentation? |
| `evicted_keys` | Is Redis evicting keys under memory pressure? |
| `expired_keys` | Keys expiring by TTL over time |
| `rejected_connections` | New clients rejected due to limits or related errors |
| `connected_clients` | Current connections vs. operational ceiling |
| `blocked_clients` | Clients waiting on blocking operations |
| `instantaneous_ops_per_sec` | Recent command rate, not business throughput |
| `commandstats` | Cost and frequency per Redis command |
| `total_error_replies` | Cumulative error replies; monitor rate and breakdown |
| `role` and replication offset/lag | Primary/replica state and stale-read risk |
| CPU / network / disk | Where the Redis process and host are bottlenecked |
| Latency diagnostics | Signs of slow commands or server latency events |

Exporter metric names and availability vary across Redis versions and managed offerings. Track cumulative counters by **rate of change**, not raw lifetime totals since startup.

## 19. Load Capacity Has No Single PING Threshold

Capacity should be evaluated against **SLO compliance** under expected workloads.

Suppose a service defines:

```text
Target:
  2,000 HTTP requests/second

Invariants:
  p99 end-to-end latency <= 150 ms
  error rate <= 0.5%
  zero dropped critical business work
  JVM heap / Redis memory does not grow unboundedly
  backlogs drain after traffic bursts
```

Under load testing:

- 500 RPS: p99 40 ms, 0% errors.
- 1,500 RPS: p99 95 ms, 0.1% errors.
- 2,000 RPS: p99 230 ms, 1.2% errors.
- 2,500 RPS: Redis command timeouts and growing queues.

Here, Redis `PING` may still succeed at 2,500 RPS, yet **the application already failed its SLO at 2,000 RPS**. "Redis healthy" via `PING` cannot override that reality.

**Capacity must be tied to a specific workload and SLO**, not a generic claim like "Redis can handle N operations/s" copied from another environment.

## 20. Throughput and Tail Latency Must Be Measured Together

Optimizations like increasing pipelining or batch sizes can raise throughput while worsening p99 due to:

1. Batch formation wait.
2. Connection queuing.
3. Reply buffering and serialization.
4. Head-of-line blocking.
5. Redis CPU-bound commands or long Lua scripts.
6. Client event-loop saturation.
7. JVM garbage collection.
8. Retry bursts triggered when Redis times out.

Measuring only Redis commands/second hides user experience.

A simple model:

```text
HTTP request latency
    =
    App queue wait
    + Business processing
    + Redis command wait / network / server
    + Deserialization
    + Fallback or retry
    + Response serialization
```

Measure **end-to-end p50/p95/p99** and isolate each stage to locate bottlenecks. A Redis `GET` p99 of 20 ms cannot explain an HTTP request p99 of 500 ms if lock contention, DB fallback, or downstream queuing dominates.

## 21. Little's Law: Higher Latency Increases In-Flight Queues

In a relatively stable state, Little's Law states:

\[
L = \lambda W
\]

Where:

- `L`: average number of concurrent work items inside the system.
- `λ`: average arrival/completion rate.
- `W`: average time each item spends in the system.

For example, at 5,000 ops/second with each operation taking 40 ms:

\[
L = 5\,000 \times 0.04 = 200
\]

If Redis slows down so latency jumps from 40 ms to 200 ms without arrival rate dropping, in-flight work climbs toward 1,000 concurrent operations. Consequently:

- Futures, reply buffers, and queues swell.
- Thread pools and connection pools saturate.
- Timeouts rise and clients retry more.
- Memory grows even while Redis `PING` still responds.

Little's Law explains buffering pressure and saturation, **not an exact predictor during sudden bursts or unstable systems**.

## 22. Bottleneck Sources to Distinguish

| Bottleneck Source | Symptoms | Where to Measure |
|---|---|---|
| Redis CPU | Rising command latency, throughput plateau | Redis CPU, commandstats, slowlog/latency |
| Redis memory | Evictions/OOM, rising RSS | `INFO memory`, `maxmemory`, memory pressure |
| Network | Rising RTT, timeouts, retransmissions | Network latency, bandwidth, connection errors |
| Connection limits | Connection refused/rejected | Connected/rejected clients, pools |
| Lettuce client | Slow event loop, pending commands | Client metrics/traces, command latency |
| JVM heap/GC | p99 spikes, Java OOM | Heap usage, GC pauses |
| Thread pool | Deep queues, maxed active threads | Executor gauges |
| Redis Cluster hot slot | One primary busy, others idle | Slot/key distribution, per-node metrics |
| Read replica lag | Reads miss recently committed writes | Replication lag, source version |
| Cache miss storm | DB QPS surges after Redis failure | Cache hit/miss, DB pool, fallback rate |
| Stream consumer lag | Growing pending, falling ACK throughput | `XINFO GROUPS`, `XPENDING`, consumer processing |
| Long Lua/`MULTI` | Unrelated commands stall | Command latency, slowlog, tracing |

Sometimes a Redis health indicator reads `UP` while **another application pod's connection** fails DNS or TLS. Observe per application instance and per Redis node—never treat a check from an operator laptop as representative of every pod.

## 23. Redis Cluster Needs Per-Node and Per-Slot Health

Redis Cluster spans multiple primaries and replicas. A `PING` to a seed node does not prove **all hash slots** are reachable.

```text
Cluster:
  Primary A -> slots 0..5000        UP
  Primary B -> slots 5001..10000    node/endpoint unreachable
  Primary C -> slots 10001..16383   UP

App PING Primary A -> PONG
App GET key in B   -> timeout / redirection failure
```

During diagnostics, authorized operators can inspect:

```bash
redis-cli -c -h redis-a -p 7000 CLUSTER INFO
redis-cli -c -h redis-a -p 7000 CLUSTER SHARDS
redis-cli -c -h redis-a -p 7000 CLUSTER NODES
```

These commands show topology and slot coverage, though they are not load tests.

Cluster monitoring should cover:

- `cluster_state` and slot coverage.
- Primary/replica roles and failover events.
- Whether advertised endpoints are reachable from the application network.
- Redis memory, CPU, and latency **per primary**.
- Hot keys/hot slots and key distribution.
- Frequency of Lettuce `MOVED`/`ASK` redirects or topology refresh failures.
- Error rates by hash-slot range or logical key namespace where feasible.
- Replication lag if reading from replicas.

A service can suffer poor latency solely for a subset of users whose keys live in a hot slot on a busy node. An aggregate Redis dashboard can conceal this.

## 24. Redis Sentinel and Health During Failover

With Redis Sentinel, a primary can be replaced by a promoted replica. During failover:

- The old primary endpoint may go offline or transition into a replica.
- Some write commands may time out or return `READONLY`.
- Lettuce/Sentinel-aware connections must discover the new primary.
- Redis may recover quickly while application connection pools take longer to stabilize.
- Writes right around failover face risk depending on replication and durability semantics.

Application liveness **should generally not flip to DOWN over a brief Redis failover**. Readiness depends on how critical Redis is and whether degraded mode exists; metrics and alerts should track recovery time and uncertain writes.

An overly sensitive health probe (200 ms timeout, `failureThreshold: 1`) can mark pods not ready on brief network jitter, causing unnecessary traffic shifts. Conversely, overly long timeouts delay incident detection. Balance against SLOs and environment variability.

## 25. Replica Reads Can Be Healthy Yet Stale

A replica can answer `PING` and `GET` normally while still lagging behind primary updates.

Example:

```text
T1: app SET token:revoked:42 = true on primary
T2: app reads from a replica that has not yet received the update
T3: replica GET token:revoked:42 -> nil
```

Here:

- The node is **healthy** for connectivity.
- It may still be **ready** for queries tolerating eventual consistency.
- Yet the result is unsuitable for security checks requiring the latest revoked-token state.

Therefore separate **health** from **freshness/consistency SLOs**. When freshness is strictly required, monitor replication lag and/or version against the source rather than treating a successful `GET` as proof of freshness.

## 26. Reads and Writes Differ Even on the Same Redis Instance

A single Redis server can:

- Permit `GET` yet fail `SET` with `NOPERM` due to ACLs.
- Answer `PING` yet fail `SET` with `OOM` due to `maxmemory`.
- Permit reads on a replica yet reject writes with `READONLY`.
- Hold Stream entries yet fail `XREADGROUP` with `NOGROUP`.
- Permit `XREADGROUP` yet fail `XACK` due to permissions.
- Permit single-key commands yet fail multi-slot `MGET` with `CROSSSLOT`.

Health checks must distinguish **capability by command**.

For example, an order flow writing to Redis Streams:

```text
POST /orders
    -> SQL COMMIT
    -> XADD orders:events
```

If `PING` succeeds yet `XADD` fails with `NOPERM` or `OOM`, events can be dropped after SQL commits. You need a reliable outbox or retry mechanism; a health indicator cannot recover a lost event.

## 27. Do Not Use PING as a Performance Benchmark

A tiny `PING` payload does not measure:

- Large value payloads in `MGET`.
- CPU cost of `ZREVRANGE` on large Sorted Sets.
- Latency of Lua scripts performing many operations.
- Spring Data Redis JSON/JDK serialization overhead.
- Redis `MULTI/EXEC` transactions spanning hundreds of commands.
- Redis Streams consumer ACK and recovery throughput.
- Hot keys called thousands of times per second.
- Pending command buildup inside Lettuce.
- Downstream database wait time on cache misses.

A meaningful performance test must use a **command mix and key distribution matching the real workload**, not a loop of `PING` calls.

### Redis Benchmark vs. Application Benchmark

Redis benchmark tools measure raw command throughput, whereas a Spring application also exercises HTTP, security, serialization, Reactor/thread pools, cache misses/fallbacks, and SQL. Measure all of:

1. Redis server command capacity in a lab environment.
2. Spring Data Redis operation latency.
3. HTTP end-to-end throughput and SLOs.
4. Degraded-mode performance when Redis fails.
5. Recovery time after failover or restart.

## 28. SLIs and SLOs Should Be Tied to Specific Capabilities

Example Service Level Indicators:

| SLI | Meaningful Definition |
|---|---|
| HTTP success rate | Percentage of requests completing per contract |
| HTTP p95/p99 latency | End-to-end latency per endpoint class |
| Redis command success rate | Success across `GET`, `SET`, `XADD`, `XACK`, Lua... |
| Redis command latency | p50/p95/p99 by command and topology |
| Cache hit ratio | `hit / (hit + miss)` for cache use cases |
| Redis fallback rate | Fraction of requests bypassing cache to DB |
| DB pressure after fallback | DB QPS and pool wait while Redis is degraded |
| Memory headroom | Distance from `maxmemory` and container limits |
| Error rate by type | Timeout, `NOPERM`, `OOM`, `READONLY`, `MOVED`/`CROSSSLOT`... |
| Stream pending age | Oldest pending message age |
| Event processing lag | Elapsed time from `XADD` to business completion/`ACK` |
| Replica freshness | Time lag or version lag behind primary/source |

Example SLO targets must state their conditions:

```text
Catalog API, when cache is healthy:
  p99 <= 150 ms
  99.9% successful requests over 30 days

Catalog API, when Redis is unavailable:
  still returns origin data with error rate <= 1%
  and minimum throughput matching fallback capacity

Order event consumer:
  99.9% of events processed within <= 60 seconds
  pending age does not exceed 5 minutes under normal conditions
```

Targets are illustrative only; ground them in product needs and real infrastructure capacity. Never apply one generic Redis SLO as if every endpoint depended on Redis identically.

## 29. Spring and Lettuce Metrics

In a Spring Boot/Micrometer application, you can collect:

- HTTP server request durations and status codes.
- JVM memory and garbage collection pauses.
- Executor active threads and queue depth.
- Connection pool gauges, if pooling is used.
- Lettuce Redis command latencies/metrics when instrumentation is enabled.
- Cache hits/misses, cache operations, and fallback counts.
- Circuit breaker state and rejections.
- Retry attempts by exception type.
- Application-specific event processing rates and lag.
- Redis dependency state via health indicators.

Metric names vary across Spring Boot, Micrometer, Redis client, and registry versions. Never hardcode a metric name and assume it exists across every application.

### Metric Cardinality

Never attach Redis keys containing user IDs as metric labels:

```text
Avoid:
  redis_operation_latency{key="user:42:session"}
  redis_operation_latency{key="user:43:session"}
  ... millions of series

Prefer:
  redis_operation_latency{operation="GET",namespace="session"}
```

High cardinality can overwhelm Prometheus or your metrics backend, and sensitive keys risk leaking user data via telemetry.

## 30. Multi-Layer Observability Dashboards

A well-structured dashboard separates four regions:

```text
[APPLICATION]
  HTTP throughput, p95/p99 latency, error %
  readiness/liveness trends, active instances
  JVM heap, GC, thread pools

[REDIS CLIENT / LETTUCE]
  GET/SET/XADD/XACK latency
  timeout/error rate, reconnects, pending commands
  retry and fallback counts

[REDIS SERVER / CLUSTER]
  per-primary CPU/memory, maxmemory headroom
  evictions/OOM, connected/rejected clients
  replication lag, Cluster slots/topology

[BUSINESS]
  cache hit/miss, DB fallback saturation
  Stream lag / pending age / ACK throughput
  missed events, duplicate suppression
```

**Important reminder:** a `UP` readiness endpoint never makes capacity charts unnecessary. Conversely, a few seconds of failed Redis `PING` probes does not automatically require restarting the application.

## 31. Health Alerts and Capacity Alerts Should Differ

Example alert guidelines:

| Signal Category | Signal | Response |
|---|---|---|
| Redis connectivity fault | Sustained rise in Redis command errors | Investigate Redis/network/ACLs |
| Multiple pods readiness DOWN | Service losing traffic capacity | Check readiness policy and dependency scope |
| Rising liveness restarts | Crash loops, stuck app, bad probe config | Investigate app process, not only Redis |
| Redis memory > alert threshold | Low headroom | Capacity planning, TTL/eviction, lawful cleanup |
| Redis OOM errors > 0 | Write capability impacted | Prioritize data protection and producers |
| Redis command p99 exceeds SLO | Latency degradation | Inspect CPU, hot keys, network, client queues |
| Cache hit ratio drops sharply | DB may face heavy load | Protect DB, check invalidation/TTL |
| Stream PEL oldest idle climbs | Slow or failing recovery/consumers | Check ACKs, reclaim, poison messages |
| Replica lag climbs | Risk of stale reads | Adjust read routing / consistency |
| Redis Cluster primary lost | Slot coverage / failover | Track failover and reconnects |

Avoid firing on isolated single-sample blips during brief jitter, yet do not smooth over a 30-minute average that hides a multi-minute outage. Use appropriate durations, burn rates, and severities matched to business impact.

## 32. Failure Scenario: Region-Wide Redis Cache Outage

Suppose 20 application pods share a Redis cache backed by PostgreSQL as the source of truth.

```text
T0 Redis unavailable
T1 GET cache errors rise
T2 Pods fall back to PostgreSQL
T3 Database CPU and pool wait climb
T4 HTTP p99 climbs
T5 Database faces overload risk
```

If readiness is configured as "Redis PING fails = not ready" on every pod, all 20 pods get pulled simultaneously and users lose the entire service.

A resilient design includes:

- Readiness independent of Redis when caching is optional.
- Fallbacks with explicit timeouts and no unbounded Redis retries.
- Circuit breakers curbing repeated attempts against a broken Redis.
- Rate limits or bounded concurrency protecting PostgreSQL.
- Temporary stale cache serving if business allows with staleness controls.
- Alerts covering Redis outage, DB fallback rate, DB pool, and HTTP SLOs.
- Bounded warm-up when Redis recovers to avoid stampedes.

**Conclusion:** Redis health can be `DOWN` while readiness stays `UP`, yet capacity drops dramatically. Without capacity visibility, a Redis outage cascades into a secondary database outage.

## 33. Failure Scenario: Redis as a Mandatory Session Store

A web application cannot authenticate sessions if its Redis session store is lost.

```text
Redis unavailable
    |
    +--> Session GET/SET fails
    |
    +--> Authentication workflow unavailable
    |
    +--> Endpoints requiring sessions cannot succeed
```

Here, the service must return contract-defined errors or transition readiness per policy. Note:

- If Redis goes down region-wide, all pods may turn not ready simultaneously.
- Restarting individual pods will not repair the Redis session store.
- If some public endpoints do not require sessions, consider separating deployments or routing.
- Guard against retry storms when Redis recovers.
- A Redis `PING` check does not verify session read/write ACLs or serialization compatibility.

Alerts should track **session operation failure rates** and HTTP authentication success rates, not merely Redis `PING`.

## 34. Failure Scenario: Redis Answers PING Yet Hits maxmemory

Suppose Redis uses `maxmemory-policy noeviction` and data keeps growing.

```text
PING -> PONG
GET  -> OK
SET  -> OOM
XADD -> OOM
```

Each observation layer reacts differently:

- **Connectivity:** UP.
- **Write capability:** FAILED.
- **Readiness:** depends on how essential writes are to the service.
- **Capacity:** zero headroom left for memory-allocating writes.
- **Alerting:** memory threshold, OOM reply rate, evictions.
- **Recovery:** adjust TTL, retention, or capacity carefully; never rush into `FLUSHALL`.

If Redis is a cache that can tolerate skipped `SET`s and fall back to the DB, read paths can continue. Yet if Redis Streams is the sole store for emitted events, failing `XADD` is a severe data issue requiring a durable outbox fallback.

## 35. Failure Scenario: One Slow Primary in Redis Cluster

```text
Primary A: p99 GET 3 ms
Primary B: p99 GET 120 ms, CPU nearly saturated
Primary C: p99 GET 4 ms
```

`PING` health across all nodes may be `UP`, and app readiness stays `UP`. Still, users whose keys live on B get poor performance.

Inspect:

- Which keys/slots reside on B.
- Whether a hot key, giant ZSet, or stream sits in one slot.
- Whether heavy Lua scripts or multi-key commands are hitting B.
- Whether replica read routing introduces unacceptable staleness.
- Whether p99 differs across endpoints or user cohorts.
- Whether slot rebalancing/resharding is safe and appropriate.

Never declare a Redis Cluster has plenty of capacity solely from low cluster-wide average CPU; a single hot primary can breach SLOs.

## 36. Failure Scenario: Redis Streams PING Fine Yet Backlog Grows

Example:

```text
Producer XADD: 2,000 events/s
Consumer ACK:    800 events/s
Backlog growth: 1,200 events/s
```

Redis still replies to `PING`. Consumer pods remain live. Readiness may even stay `UP` because consumers keep reading and acking, yet **processing capacity lags behind arrival rate**.

Measure:

- `XINFO GROUPS` lag and its semantic limitations.
- `XPENDING` total pending count and oldest pending age.
- End-to-end event age from `XADD` to completion.
- Consumer success, failure, and ACK rates.
- Retry/reclaim counts and poison messages.
- Producer throughput and downstream DB/API pressure.
- Stream length and retention; `XACK` does not delete physical entries.

Raising a listener's `batchSize` may reduce polling overhead, but it will not fix a slow business handler or database bottleneck. If backlog grows steadily, plan capacity, scale consumers, or throttle upstream producers.

## 37. Readiness Is Not an Auto-Scaling Tool

Marking a pod not ready because CPU ticked up forces traffic onto remaining pods. If every pod is heavily loaded, removing endpoints only makes collapse faster.

In general:

- **Readiness:** whether an instance should receive traffic.
- **Horizontal scaling:** adding instances driven by demand/metrics.
- **Backpressure/load shedding:** capping the work an instance accepts.
- **Circuit breakers:** preventing failing dependencies from cascading.
- **Capacity alerting:** warning before SLOs break.
- **Liveness:** detecting conditions recoverable by restarting.

Nor does Redis Cluster gain capacity by scaling out application pods. If a Redis primary is the bottleneck, adding pods only increases pressure on Redis. Locate the bottleneck before choosing how to scale.

## 38. Choosing Probe Intervals and Thresholds

A probe involves multiple parameters:

| Parameter | Meaning |
|---|---|
| `periodSeconds` | How often kubelet runs the check |
| `timeoutSeconds` | Time limit for one probe attempt |
| `failureThreshold` | Consecutive failures before marking probe failed |
| `successThreshold` | Consecutive successes required to recover, per probe rules |
| HTTP path/port | Traffic or management endpoint checked |
| Health group membership | Which contributors affect the verdict |
| Redis/client timeout | Maximum time a command/probe can wait |
| Startup grace | Appropriate `startupProbe` or initial delay |

Never set Redis command timeout longer than the HTTP probe timeout and assume clean handling. If the HTTP probe times out while the Redis command keeps running in the client, queued work can pile up without proper cancellation/lifecycle management.

Similarly, setting `livenessProbe` `failureThreshold` too low on a JVM with occasional GC pauses triggers unnecessary restarts. Balance responsiveness against short-lived jitter.

## 39. Graceful Startup and Shutdown

During startup, a service not yet ready may:

1. Build the Spring context.
2. Initialize the Redis connection factory.
3. Run required migrations or setup.
4. Register consumers or start listeners if applicable.
5. Prepare internal state/configuration.
6. Transition readiness to accept traffic.

There is no need to block liveness during startup if a sensible `startupProbe` is configured.

During shutdown:

```text
Pod begins termination
    |
    +--> readiness flips to stop accepting new traffic
    |
    +--> in-flight HTTP requests complete within grace period
    |
    +--> Redis Stream consumers stop polling new messages
    |
    +--> successfully processed tasks send XACK
    |
    +--> connections and executors close cleanly
```

If workers process Redis Streams, shutting down a pod does not guarantee pending messages finish processing. Maintain proper consumer recovery, reclaim, and idempotency mechanisms.

## 40. Testing Probes in Integration Tests

Do not merely mock a `HealthIndicator` and assume Kubernetes wiring works. Write integration tests against a real Spring Boot context and test Redis instance.

Test matrix:

| Test | Setup | Expected |
|---|---|---|
| LIVE-01 | App running normally | Liveness UP |
| LIVE-02 | Redis down, app alive | Liveness still reflects app health; no restart solely over Redis |
| READY-01 | Startup incomplete | Readiness rejects traffic |
| READY-02 | Optional Redis cache down | Readiness follows policy, may remain UP |
| READY-03 | Critical Redis down | Readiness/endpoints fail per contract |
| READY-04 | Graceful shutdown | Pod stops accepting new requests |
| HEALTH-01 | `PING` succeeds | Redis connectivity contributor UP |
| HEALTH-02 | User lacks `SET` permission | Synthetic write probe catches it even if `PING` is UP |
| HEALTH-03 | Redis `maxmemory` `noeviction` | `SET` may fail OOM while `PING` stays UP |
| HEALTH-04 | Endpoint is a Redis replica | Write probe fails with `READONLY` |
| HEALTH-05 | One Redis Cluster primary down | Single seed `PING` does not represent whole cluster |
| CAP-01 | Load ramps up | Identify SLO breach point even while probes stay UP |
| CAP-02 | Redis timeout/fallback | Measure DB load and degraded service capacity |
| CAP-03 | Stream producer outpaces consumer | Rising lag/PEL detected |

With Kubernetes, run deployment tests on a test cluster to verify **exact probe paths/ports, HTTP status codes, `startupProbe`, and Service endpoint membership**. Unit-testing `HealthIndicator.health()` alone does not verify kubelet or Service routing.

## 41. Fault Injection Tests Should Follow Clear Hypotheses

In a Redis lab or isolated staging environment, simulate:

- Redis server paused or connection severed.
- Redis returning `NOPERM` for `SET` while allowing `PING`.
- Redis enforcing tight `maxmemory` for controlled OOM.
- App Redis client accidentally targeting a replica and hitting `READONLY`.
- Redis Cluster primary/slot ownership changing.
- Network latency injected at test thresholds.
- Redis Stream consumer stalling or stopping ACKs.
- Cache miss storm following a Redis outage.

Every test should answer:

1. Which probes changed state?
2. Is traffic still routed to the pod?
3. Does the application return errors matching its contract?
4. Do client retries amplify load or cause duplicate side effects?
5. Do metrics and alerts catch the capacity drop?
6. When the dependency recovers, does the app recover without needless restarts?
7. Are business data integrity and pending recovery preserved?

**Never trigger failovers, cut `maxmemory`, or revoke ACLs on production Redis just to test probes.** Use Testcontainers, a Redis lab, and fault-injecting proxies in staging.

## 42. Interpreting Cases Where Readiness and Health Differ

### Case A

```text
/actuator/health           -> DOWN (redis contributor DOWN)
/actuator/health/liveness  -> UP
/actuator/health/readiness -> UP
HTTP catalog requests      -> 200, elevated latency
```

This is **not necessarily misconfigured**. If Redis is only an optional cache and the origin DB is healthy, the app can remain ready even while aggregate health reports a degraded dependency.

Watch DB pressure, fallback rate, and p99 closely.

### Case B

```text
/actuator/health/liveness  -> UP
/actuator/health/readiness -> DOWN
Redis session unavailable
```

Appropriate if Redis sessions are strictly mandatory per policy and the instance should stop taking traffic. Restarting the pod via liveness would be pointless.

### Case C

```text
PING Redis -> PONG
App readiness -> UP
HTTP p99 -> 700 ms
Redis command p99 -> 100 ms
Redis CPU -> 98%
```

The system has a capacity/performance problem even though probes are green. Optimize workload, apply backpressure, analyze hot keys, or scale Redis at the actual bottleneck.

### Case D

```text
PING Redis -> PONG
GET -> OK
SET -> OOM
Redis maxmemory near limit
```

Read-only flows may keep working while write paths fail. Check workflow requirements, memory policy, permissions, and fallbacks.

## 43. Common Mistakes

**"Redis returning `PONG` means the whole system is healthy."**  
False. `PING` only reflects answering one lightweight command at one point; it does not verify command permissions, memory, all slots, or capacity.

**"If Redis is `DOWN`, liveness must be `DOWN` too."**  
Usually wrong. A dependency outage cannot be fixed by restarting pods and risks restart storms.

**"Readiness must check every database, cache, broker, and external API."**  
Not by default. Losing one dependency may not break every endpoint, and dropping all pods can amplify an outage.

**"If the health endpoint is `UP`, no load testing is needed."**  
False. Health checks do not prove peak throughput or p99 compliance.

**"If the cache fails, just fall back to the DB without limits."**  
False. Unbounded fallback can saturate the database; enforce concurrency limits and circuit breakers.

**"Pinging one Redis Cluster node covers all hash slots."**  
False. One primary can be healthy while another node is unreachable or overloaded.

**"Adding more pods always increases Redis throughput."**  
False. If a Redis primary is the bottleneck, adding pods increases contention.

**"If Redis Stream `XREADGROUP` works, consumers are healthy."**  
Insufficient. Measure business processing, ACK success, pending age, and reclaim behavior.

**"Putting a synthetic `SET` in liveness makes it safer."**  
Usually the opposite. Write probes carry side effects, can fail under OOM/ACL errors, and trigger useless restarts.

**"Readiness `DOWN` means Kubernetes restarts the pod."**  
No. Readiness controls traffic routing; liveness and startup failures drive restarts per configuration.

## 44. Checklist for Implementing Redis Observability

- [ ] Classify whether Redis is an **optional cache** or **critical dependency** per workflow.
- [ ] Keep liveness tied strictly to internal process states recoverable by a restart.
- [ ] Design readiness to govern new traffic, not mirror aggregate dependency health blindly.
- [ ] Give the startup probe enough time for realistic application boot durations.
- [ ] Name and scope Redis health indicators clearly: `PING`, read, or synthetic write.
- [ ] Give probes timeouts and thresholds; never run heavy commands or full keyspace scans.
- [ ] Keep synthetic writes on dedicated keys with TTLs and least-privilege ACLs; never touch business keys.
- [ ] Never expose error details, Redis endpoints, or credentials on public Actuator endpoints.
- [ ] Measure end-to-end p50/p95/p99 per endpoint and Redis command.
- [ ] Measure Redis memory, `maxmemory` headroom, OOM, evictions, CPU, and connections.
- [ ] Measure cache hit/miss, Redis fallback rate, and downstream DB saturation.
- [ ] Ensure Redis Cluster has per-primary metrics and slot visibility, not just one seed probe.
- [ ] Alert on Stream lag, pending age, and ACK throughput if using Streams.
- [ ] Run load tests to verify true headroom under production-like traffic.
- [ ] Test Redis outages and failovers in isolated environments.
- [ ] Protect downstreams with circuit breakers, backpressure, or rate limits during cache failures.
- [ ] Verify the service reconnects and recovers cleanly without retry storms when dependencies return.
- [ ] Confirm readiness and liveness paths work on the exact port Kubernetes probes.
- [ ] Keep user IDs, tokens, and high-cardinality keys out of metrics and tags.
- [ ] Maintain runbooks separating connectivity failures, read/write permissions, memory, and capacity.

## 45. Self-Check Questions

**1. What does a successful Redis `PING` prove?**  
Mainly that a connection to a specific Redis endpoint could execute `PING` at that moment. It does not prove write capacity, ACLs for all commands, or reachability across all Cluster slots.

**2. Why shouldn't a Redis outage directly fail liveness?**  
Because restarting application pods usually cannot fix Redis, and simultaneous reconnects/retries can worsen the outage.

**3. How does readiness differ from liveness in Kubernetes actions?**  
Readiness controls whether a pod receives new traffic via Service endpoints; repeated liveness failures cause kubelet to restart the container.

**4. If an optional Redis cache goes down, must the app become not ready?**  
No. If origin data still meets the contract, the app can stay ready, though capacity and p99 may degrade.

**5. If Redis is a mandatory session store and fails, what should you evaluate?**  
Whether endpoints can still honor contracts, fail-closed policies, readiness behavior, and the impact of all pods going not ready together—never rely solely on `PING`.

**6. Is Redis replying `PONG` while `SET` returns OOM a contradiction?**  
No. `PING` is lightweight, whereas writes needing extra memory are governed by `maxmemory` and eviction policies.

**7. How do you check Redis Cluster beyond one node?**  
Monitor cluster slot coverage, node roles, endpoints, per-primary metrics, and test paths within scope; pinging a single seed node is insufficient.

**8. Should you run synthetic `XADD` every 1 second inside liveness?**  
Normally no. It creates side effects, swells the stream, and can cause restarts over dependency errors; use appropriate probes instead.

**9. If `GET` works yet `SET` fails with `NOPERM`, will a `PING` health check catch it?**  
Not necessarily. Validate write/permission paths with controlled synthetic probes aligned to the use case.

**10. Can high HTTP p99 while readiness stays `UP` be valid?**  
Yes. Readiness and capacity are separate signals; use SLOs/metrics along with scaling or backpressure.

**11. When a Redis cache fails, why can the database become the new bottleneck?**  
Because every cache miss or Redis error falls back to reading origin data, spiking DB QPS, pool waits, and p99.

**12. What does rising Redis Stream lag while `PING` stays fast mean?**  
The server still answers lightweight commands, yet consumer processing/ACK capacity trails producer arrival rate.

**13. Why doesn't one synthetic key prove all Redis Cluster slots are healthy?**  
Because any single key hashes to one slot and one primary, leaving other primaries untested.

**14. What minimum metrics evaluate load capacity?**  
Throughput, p95/p99 latency, error rate, memory/CPU, pending commands/queue depth, and downstream impact.

**15. When might you consider marking pods not ready due to Redis?**  
When Redis is genuinely mandatory to serve the traffic governed by readiness, after weighing the impact of dropping pods during a region-wide outage.

## 46. Summary

Three terms are easily confused yet must be operated distinctly:

- **Health check** evaluates a specific component or operation, such as Redis connectivity via `PING` or synthetic `SET` with a TTL.
- **Liveness** evaluates whether the process can keep running or needs a restart; **it should not depend by default on external Redis**.
- **Readiness** governs whether an instance should accept new traffic, depending on Redis's true business role and degraded-mode strategy.
- **Capacity** measures the ability to sustain throughput, p95/p99 latency, error rates, and resource limits under load; Redis `PONG` is never proof of capacity.

In Spring Data Redis, best practice is to use **Spring Boot Actuator** for clean liveness/readiness separation; observe Redis connectivity, ACLs, OOM, roles/failover, and Cluster topology within their proper scopes; and use **Micrometer/Redis metrics, load testing, and fault injection** to measure real serving capacity.

When Redis is only a cache, the service may stay ready while Redis is unhealthy—provided database fallback load is bounded. When Redis is a mandatory dependency, readiness needs an intentional policy that avoids triggering restart storms. When Redis `PING` stays fast while p99 and errors climb, the issue lies in **load capacity**, not server liveness.

A mature observability setup answers four questions: **"Is Redis still responding?", "Should this app take traffic?", "Under how much load do we still meet SLOs?", and "If a dependency fails, how does the system degrade and recover?"**

## References

- [Spring Boot Actuator — Production-ready Features](https://docs.spring.io/spring-boot/reference/actuator/index.html): health endpoints, monitoring, and health groups.
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness/readiness, startup probes, and additional paths on the main port.
- [Spring Boot — Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health): health indicators, groups, and HTTP status mappings.
- [Spring Data Redis — Redis Connection](https://docs.spring.io/spring-data/redis/reference/redis.html): `RedisConnectionFactory` and Redis operations.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): templates, serializers, and error handling.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache manager, TTL, and fallback considerations.
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): cluster nodes, slot routing, and topology.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): Streams listeners, groups, ACKs, and pending entries.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): probe semantics and configuration.
- [Redis — PING](https://redis.io/docs/latest/commands/ping/): semantics and `PING` responses.
- [Redis — INFO](https://redis.io/docs/latest/commands/info/): memory, clients, stats, replication, and commandstats.
- [Redis — Key Eviction](https://redis.io/docs/latest/develop/reference/eviction/): `maxmemory`, eviction, and OOM.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, failover, and cluster behavior.
- [Redis — XINFO GROUPS](https://redis.io/docs/latest/commands/xinfo-groups/): metrics for Redis Streams consumer groups.
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/): inspecting pending messages.
- [Micrometer — Reference](https://docs.micrometer.io/micrometer/reference/): timers, metrics, histograms, and registries.
