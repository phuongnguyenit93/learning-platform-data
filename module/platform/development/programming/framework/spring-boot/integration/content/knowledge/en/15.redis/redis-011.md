# Network Failures, Node Failover, and Policies When Redis Is Unavailable

Redis frequently appears in Spring Boot systems as a cache, session store, rate-limit counter, distributed lock, deduplication store, or messaging intermediary. Each role imposes different requirements when Redis experiences an incident. An application may continue serving when a cache drops, yet cannot blindly ignore failures in a payment lock or access-control store.

This lesson belongs to the **Redis** chapter of **SPRING_BOOT_INTEGRATION**: organizing Spring Boot integrations across HTTP clients, databases, caches, message brokers, and Spring Integration adapters, emphasizing configuration, data contracts, transactions, errors, deduplication, testing, and observability in real integration flows.

## 1. Objectives and Scope

After this lesson, learners will be able to:

1. Distinguish connection errors, timeouts, Cluster redirection errors, primary-failover interruptions, and data/configuration errors.
2. Explain application behavior when Redis Sentinel or Redis Cluster fails over nodes, including write-loss windows and risk of losing recently acknowledged records.
3. Choose **fail-open**, **fail-closed**, **fallback**, and **degrade** policies matching each feature's business contract.
4. Configure the Redis client in Spring Boot, isolate the Redis integration layer, and set timeouts and retry limits so failures do not cascade to the database.
5. Test disconnect, failover, and recovery scenarios; observe impacts on latency, business errors, and dependent service load.

**Example scope:** Spring Boot 3.x, Spring Data Redis, Lettuce, and a relational database as the authoritative store for a display-price caching example. Specific property names and APIs should be checked against your deployed Spring Boot version.

## 2. How Do Redis Outages Impact Integration Flows?

A Redis call passes through several layers: business service, Redis adapter, client, TCP/TLS connection, proxy or load balancer, and finally the Redis node. Failures at any layer can surface as timeouts; conversely, a client-side timeout never proves Redis did not execute the command.

~~~mermaid
flowchart TD
    HTTP["HTTP request / message consumer"] --> APP["Spring Boot business service"]
    APP --> POLICY{"Role of Redis?"}
    POLICY -->|Cache with DB origin| CACHE["Redis cache adapter"]
    POLICY -->|Lock / idempotency / security| CRITICAL["Redis coordination adapter"]
    CACHE --> REDIS[("Redis primary / Cluster")]
    CRITICAL --> REDIS
    CACHE -->|Miss or allowed fallback error| DB[("Authoritative database")]
    CRITICAL -->|State cannot be verified| STOP["Reject / defer / use strong backup mechanism"]
    DB --> RESPONSE["Response per business contract"]
    REDIS --> RESPONSE
~~~

Four distinct symptom groups must be separated:

| Symptom | Common Signs | Implications for the Application |
|---|---|---|
| Unable to establish connection | DNS errors, TCP refused/reset, TLS or auth failures, connect timeout | Command likely never sent; auth and misconfiguration errors do not self-heal on retry. |
| Command sent, timed out waiting | Command timeout, connection dropped mid-response | **Outcome unknown**: command may have run, not run, or run with response lost. |
| Redis changing roles or topology | Replica promoted to primary, old node lost; `MOVED`, `ASK`, `TRYAGAIN`, `CLUSTERDOWN` in Cluster | Client must discover target and may reconnect; some in-flight operations fail. |
| Redis returns valid protocol error | Wrong data type (`WRONGTYPE`), OOM policy rejections, ACL errors, `CROSSSLOT` | Contract, config, data, or resource errors; never mask as a normal cache miss. |

Spring Data Redis exceptions include **`RedisConnectionFailureException`**, **`QueryTimeoutException`**, and **`RedisSystemException`**; Lettuce exceptions are usually translated by Spring into the **`DataAccessException`** hierarchy. Never tie business policies to a single literal exception name: inspect root causes and separate infrastructure outages from programming, data, or permission bugs.

### 2.1. Critical Case: Timeout Does Not Mean Failure

Suppose the app sends **`INCR`** to increment a counter. Redis executes it, then the response packet drops during a network blip. The app sees a timeout and retries **`INCR`**. The counter increments twice for a single business event.

Likewise, writing an idempotency key and timing out leaves callers unsure whether the key exists. Pure cache reads can usually be retried safely; mutating commands **must never be retried blindly**. Use idempotency keys, atomic conditional writes, authoritative DB state, or reconciliation by business request ID.

A Lua script runs atomically on a primary at execution time, yet a client timeout still leaves an ambiguous outcome; neither does Lua turn asynchronous replication into a durable cross-failover transaction.

## 3. Failover Mechanics: Standalone, Sentinel, and Cluster

| Model | Node Failover | What Spring Boot Must Prepare |
|---|---|---|
| Redis Standalone | No automatic primary election within standalone Redis itself; endpoint changes are handled externally if at all | Disconnect detection, fallback policy, stable endpoint, recovery procedures. |
| Redis Sentinel | Sentinels monitor primary/replicas, confirm failure via quorum, and promote a replica when conditions pass | Configure logical master name and Sentinel list; client discovers new primary and reconnects. |
| Redis Cluster | Data split across 16,384 hash slots; each primary owns slots with optional replicas; cluster elects failover when eligible | Cluster-aware client handles `MOVED`/`ASK`, refreshes slot maps, avoids assuming all keys live on one node. |
| Managed Redis Service | Provider may swap primaries/endpoints/proxies or manage failover internally | Follow provider docs on DNS, TLS, auth, endpoints, failover, and connection limits. |

### 3.1. Sentinel: Automated Primary Election Still Has an Interruption Window

Example setup with one primary, two replicas, and three Sentinels across proper failure domains:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot + Lettuce
    participant S as Sentinel quorum
    participant P as Old Primary
    participant R as Replica
    App->>P: Write or read
    P--xApp: Disconnect / unresponsive
    S->>S: Confirm primary unreachable
    S->>R: Elect and promote replica to primary
    App->>S: Query current primary
    S-->>App: New primary address
    App->>R: Reconnect and execute new commands
~~~

Distinguish the **quorum required to mark the primary down** from the **majority of Sentinels** needed to authorize failover. A single Sentinel cannot deliver high availability for the system.

In-flight requests during promotion can time out or fail. There is no promise that every sent command is automatically replayed safely; the app must know which commands are safe to retry.

**Data consistency note:** standard Redis replication is asynchronous. The old primary can acknowledge success before replicas receive the write. If that replica is promoted, an acknowledged write can vanish from the new primary. Mechanisms like AOF, minimum replica requirements, or **`WAIT`** mitigate risk under specific conditions, yet do not equal synchronous, crash-proof transactions across arbitrary failures.

### 3.2. Cluster: Primary Failover and Hash Slot Migration

In Cluster, several responses carry routing semantics:

- **`MOVED`**: the slot permanently belongs to another node; the client updates its topology/slot map.
- **`ASK`**: temporary redirection during slot migration; the client executes `ASKING` on the target node per protocol.
- **`TRYAGAIN`**: operation temporarily cannot complete, e.g., during slot migration.
- **`CLUSTERDOWN`**: cluster cannot currently serve commands in its present state.
- **`CROSSSLOT`**: multi-key operation spans different slots; this is a key-design error, not a network error. Use hash tags like **`order:{123}:state`** and **`order:{123}:lock`** only when co-location is genuinely required and load distribution is understood.

Lettuce handles redirections and topology refreshes, yet still requires capped redirects, timeouts, and refresh settings tuned to the environment. Having replicas does not guarantee a partitioned minority can accept writes: Cluster needs consensus/election and a majority of primaries; availability depends on partition shape and real reachability.

**Reading from replicas** can return stale data due to replication lag. Never use replica reads to work around connection errors when business rules demand read-your-writes.

## 4. Deciding Policies When Redis Is Unavailable

No single rule fits every application. First ask: **Is Redis holding a speed-optimization copy, or a true/false invariant that correctness relies upon?**

| Redis Role | On Redis Failure | Typical Policy | Key Warning |
|---|---|---|---|
| Cache-aside for catalog/display pricing | Bypass cache, read authoritative DB, return result; write cache best-effort | **Fail-open on cache**, with DB load limits | Prices may be stale up to TTL; re-verify authoritative price at checkout. |
| Cache accelerating reads over capacity-limited DB | Query DB behind bulkhead/rate limit; if saturated, return 429/503 or approved stale data | **Controlled degradation** | Unbounded fallback can crash the DB. |
| Token revocation / access permissions | Switch to trusted alternate auth source or deny sensitive actions | **Fail-closed** when permissions cannot be verified | Never treat Redis errors as "token valid" or "not revoked." |
| Rate limiting protecting login / sensitive APIs | Enforce strong backup limiter or reject predictably | Usually **fail-closed** | Failing open leaves endpoints exposed to abuse while counters are down. |
| Convenience rate limiting on low-risk APIs | Permit bounded traffic with temporary local limiter | May **fail-open/degrade** per SLO | Local limiters lack cluster-wide visibility. |
| Distributed lock guarding critical updates | Abort operation or rely on DB transactions/locks | **Fail-closed** | Losing Redis never grants lock ownership. |
| Idempotency preventing duplicate orders/payments | Use DB unique constraints or durable idempotency tables; reject/defer if absent | **Fail-closed** unless proven safe | Timeouts and failovers can cause duplicate execution. |
| Redis Pub/Sub delivering events | Separate droppable signals from mandatory events | Move critical events to outbox + durable broker | Pub/Sub does not buffer messages for offline subscribers. |

**Fail-open** means proceeding with an action even when a check or optimization is unavailable. **Fail-closed** means blocking actions that rely on unverified state. **Fallback** is an explicit alternate path with its own contract; **degrade** is intentional quality reduction, such as serving indicative pricing or disabling non-essential features.

These options are examples to decide against data criticality, sources of truth, compliance/security needs, and SLOs. Every endpoint should specify status codes, retryability, transaction state, and caller messaging when work cannot proceed.

## 5. Configuring the Spring Boot Client for Bounded Failure Detection

Examples use Spring Boot 3.x properties. Each environment selects **one** matching connection setup: standalone, Sentinel, or Cluster.

### 5.1. Single Connection / Managed Service Endpoint

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: redis.internal
      port: 6379
      connect-timeout: 300ms
      timeout: 700ms
~~~

- **`connect-timeout`**: limits connection establishment time; does not replace command waiting limits.
- **`timeout`**: command duration threshold in Spring Boot config; must fit inside the overall request latency budget.
- **`Lettuce`**: underlying async network client used by Spring Data Redis to manage connections, reconnects, and topology updates when configured.

300 ms and 700 ms are illustrative only. Derive them from measured latency, network hops, and end-to-end requirements; overly tight timeouts create false errors, while overly loose ones exhaust workers/threads and propagate outages.

### 5.2. Sentinel

~~~yaml
spring:
  data:
    redis:
      sentinel:
        master: redis-primary
        nodes:
          - "sentinel-1.internal:26379"
          - "sentinel-2.internal:26379"
          - "sentinel-3.internal:26379"
      connect-timeout: 300ms
      timeout: 700ms
~~~

**`redis-primary`** is the logical master name managed by Sentinel, not an arbitrary Spring host alias. Sentinel addresses must remain reachable from the app, including after failover. Match ACL, password, and TLS settings for Redis and Sentinel to your deployment; never commit secrets to the repository.

### 5.3. Cluster

~~~yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - "redis-node-1.internal:6379"
          - "redis-node-2.internal:6379"
          - "redis-node-3.internal:6379"
        max-redirects: 5
      connect-timeout: 300ms
      timeout: 700ms
~~~

These nodes act as **seeds** for topology discovery, not necessarily a complete fixed primary list. For clusters undergoing frequent resharding or failovers, enable Lettuce Cluster **adaptive topology refresh** and **periodic refresh**. Tune refresh intervals to change rates and topology-query overhead; `max-redirects` stops infinite redirection loops.

Verify hostnames advertised by the Cluster: connecting to seeds succeeds, yet unreachable internal node addresses across Kubernetes namespaces or VPCs still fail after `MOVED`/failover.

### 5.4. Per-Flow Time Budgets

Example HTTP endpoint with a 1,500 ms budget:

| Component | Example Budget |
|---|---:|
| Redis cache lookup | Up to 200–400 ms |
| DB fallback query | Up to 700–900 ms |
| Contract processing, HTTP network, serialization | Remaining time |
| Retries | Strictly within total budget; never add unbounded waits |

This is an allocation model, not a fixed formula. If only 200 ms remain on the request, never start a Redis retry with a 700 ms timeout. Propagate request deadlines into processing layers or use timeouts/bulkheads to keep total wait within SLOs.

## 6. Cache-Aside Pattern: Isolating Redis from Core Business Logic

Suppose a product page needs **display pricing**. The DB is authoritative; Redis holds formatted price strings to offload reads. When Redis fails, the page falls back to the DB if capacity allows. Checkout prices must still be confirmed from authoritative data at order confirmation.

~~~java
import java.math.BigDecimal;
import java.time.Duration;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DisplayPriceService {
    private static final Logger log =
            LoggerFactory.getLogger(DisplayPriceService.class);

    private final StringRedisTemplate redis;
    private final PriceRepository prices;
    private final Counter readFailures;
    private final Counter writeFailures;

    public DisplayPriceService(
            StringRedisTemplate redis,
            PriceRepository prices,
            MeterRegistry meterRegistry) {
        this.redis = redis;
        this.prices = prices;
        this.readFailures = Counter.builder("integration.redis.failures")
                .tag("operation", "read")
                .register(meterRegistry);
        this.writeFailures = Counter.builder("integration.redis.failures")
                .tag("operation", "write")
                .register(meterRegistry);
    }

    public BigDecimal findDisplayPrice(String sku) {
        String key = "display-price:" + sku;

        try {
            String cached = redis.opsForValue().get(key);
            if (cached != null) {
                try {
                    return new BigDecimal(cached);
                } catch (NumberFormatException invalidCacheValue) {
                    log.warn("Malformed cached value, key={}", key);
                }
            }
        } catch (DataAccessException redisError) {
            readFailures.increment();
            log.warn("Failed reading Redis, key={}, cause={}",
                    key, redisError.getClass().getSimpleName());
        }

        // Do not catch DB errors as Redis errors: DB is authoritative.
        BigDecimal price = prices.findDisplayPrice(sku)
                .orElseThrow(() -> new NoSuchElementException("SKU not found"));

        try {
            // Jittered TTL to avoid simultaneous expiration across keys.
            long ttlSeconds = ThreadLocalRandom.current().nextLong(50, 71);
            redis.opsForValue().set(
                    key, price.toPlainString(), Duration.ofSeconds(ttlSeconds));
        } catch (DataAccessException redisError) {
            writeFailures.increment();
            log.warn("Failed writing cache, key={}, cause={}",
                    key, redisError.getClass().getSimpleName());
        }

        return price;
    }
}

// DB adapter provided by application, e.g., backed by Spring Data JPA.
interface PriceRepository {
    Optional<BigDecimal> findDisplayPrice(String sku);
}
~~~

In this example:

1. Cache hits return fast. Cache misses or Redis read failures fall back to the authoritative source.
2. Malformed cache values are never accepted as valid prices.
3. DB errors still propagate up to the HTTP layer because no authoritative source remains.
4. Cache write failures do not undo a valid DB read; they only log and increment metrics.
5. Jittered TTL reduces simultaneous expirations, yet **does not** alone eliminate cache stampedes, stale data, or DB overload.

**Important boundary:** this catch-and-continue style suits non-critical speedup caches. Never copy it to distributed locks, authorization checks, or payment deduplication. Under high traffic, wrap the DB fallback with a bulkhead/concurrency limit and ensure cache invalidation runs after DB updates. When invalidation fails, stale data can linger until TTL expires; tighter guarantees require versioning, event/outbox invalidation, or reading the authoritative source at decision time.

### 6.1. Circuit Breakers, Bulkheads, and Short Retries

When Redis is unavailable, every request can stall for 700 ms before slamming the DB together. Operational defenses typically combine:

- **Finite timeouts** so requests never wait indefinitely.
- **Circuit breakers** around the Redis adapter to short-circuit calls to a failing dependency, probing periodically after a cooldown. Normal cache misses are not errors; DB fallback errors must never trip the Redis breaker.
- **Bulkheads** capping concurrent DB fallback calls to protect connection pools and reserve capacity for critical operations.
- **Bounded retries** on safe operations with exponential backoff and jitter, aborting when the request deadline lacks budget. Config errors like wrong passwords, `CROSSSLOT`, or `WRONGTYPE` require fixing root causes rather than retrying.
- **Load shedding** when out of capacity: return 429/503 per contract with retry guidance instead of queueing requests until resources exhaust.

Resilience4j can wrap the Redis gateway; configure separate breakers for cache reads vs. mutating operations. Never slap a broad retry annotation across an entire service method where it could replay DB writes or event publications.

### 6.2. Why Can Fallbacks Cause Secondary Outages?

Suppose normally 90% of queries hit cache and the DB handles 10%. When Redis drops, the DB suddenly receives nearly 100% of read volume—roughly a 10x surge before counting retries and hot keys. A cache outage can therefore cascade into DB timeouts and HTTP 5xx errors.

Coordinated mitigations:

- Bound concurrency, DB connection pools, and query rates; prioritize critical transactions.
- Optionally add a very short-TTL local cache or serve stale data **only when permitted by contract**, surfacing data age clearly.
- Warm caches selectively after recovery with staggered TTLs rather than having all pods reload hot keys simultaneously.
- Track fallback rates, DB load, p95/p99 latency, and rejection rates to know when to degrade gracefully.

## 7. Redis Operations That Must Never Be Retried Arbitrarily

The table below covers scenarios where **no response is received**:

| Operation | Retry on Timeout? | Safety Conditions |
|---|---|---|
| `GET`, `EXISTS` (pure reads) | Usually safe for short retries | Stay within deadline; accept value could change between reads. |
| `SET` overwriting the same value | Safe under certain contracts | Account for TTL reset, write ordering, and concurrent writers; never assume every `SET` is idempotent. |
| `INCR`, `DECR`, `LPUSH`, `XADD` | Never retry blindly | Requires request IDs, deduplication, or outcome reconciliation. |
| `SET NX` creating lock/idempotency marker | Handle ambiguous outcome | Check ownership/token and expiration contract; never assume failure means no lock was created. |
| Mutating multi-key Lua script | Never retry blindly | Atomic per execution, yet responses can still drop; use deduplicating request IDs. |
| `XACK`, Redis Stream processing | Separate ACK from business processing | Consumers must be idempotent; ACK only after critical side effects commit. |

In HTTP or broker integrations, gateway/consumer retries can still replay requests even without explicit Redis retry config. Enforce idempotency at **business boundaries**—such as a DB unique constraint per request ID—rather than relying solely on Redis TTL keys.

### 7.1. Distributed Locks and Fencing Tokens

A Redis lock lease can expire while its holder pauses or loses connectivity. The old holder can resume executing after a new holder has acquired the lock. Failovers can also drop un-replicated lock state. Therefore:

- Critical operations must verify lock ownership before unlocking; never delete another holder's lock.
- For resources needing strict mutual exclusion, pass monotonically increasing **fencing tokens** validated by the target data update, or rely on locking/transactions inside the authoritative DB.
- If valid ownership cannot be proved, abort or defer the work. Never "temporarily skip locking" when Redis is down.
- Spring Integration's **`RedisLockRegistry`** helps for coordination scenarios, yet does not replace target-system consistency or fencing designs.

### 7.2. Authentication, Sessions, and Rate Limiting

If Redis holds a revoked-token list, losing Redis must never be interpreted as "no tokens are revoked." Switch to an independent verification source or reject sensitive operations cleanly. If Redis only holds sessions recoverable via re-login, graceful degradation may ask users to sign in again—a deliberate product and security choice.

Brute-force rate limiters should have defense at an API gateway/WAF or another resilient store. In-memory limiters per pod enforce only local caps and cannot guarantee a global cluster-wide ceiling.

### 7.3. Redis Pub/Sub, Streams, and Spring Integration

**Redis Pub/Sub** delivers only to connected subscribers; messages published while an adapter is disconnected during failover never reach the app. Reconnecting does not replay missed messages.

**Redis Streams** persist entries with consumer groups, pending entries, and claim/ack semantics, yet still require tuning persistence, handling replication/failover, and handling duplicates. Never equate a broker ACK with a DB transaction.

For events that must be emitted after a DB commit (e.g., confirmed orders), a safer pattern is:

~~~mermaid
flowchart LR
    REQ["HTTP command"] --> TX["DB transaction"]
    TX --> ORDER[("Business row")]
    TX --> OUTBOX[("Outbox row")]
    OUTBOX --> PUBLISH["Outbox publisher"]
    PUBLISH --> BROKER["Durable broker / event stream"]
    BROKER --> CONS["Idempotent consumer"]
    CONS --> INVALIDATE["Invalidate / update Redis cache"]
    INVALIDATE -. "Cache error: retry invalidation, observe" .-> CONS
~~~

The transactional outbox persists both business state and emission intent in one DB transaction; publishers and consumers remain retryable and idempotent. Redis caches may be updated by events, yet should never be the sole record proving an important business event happened.

In Spring Integration, monitor errors on adapters, channels, and **`errorChannel`**, configuring retries, ACKs, dead-lettering, and idempotency per message type. Error channels route failures; they cannot resurrect lost Pub/Sub messages.

## 8. Data Consistency During Failover

Distinguish four stages:

1. **Request sent**: client writes command to socket; does not prove Redis received it.
2. **Executed on primary**: data exists on the current primary.
3. **Client received success**: app sees confirmation, yet writes may not have reached replicas or durable disk.
4. **Survives failure**: depends on replication, persistence, fsync timing, primary election, and exact failure mode.

During failover, two clients can observe different ordering or versions, especially if one reads from a replica. Re-reading after a timeout also does not prove whether a mutating command ran, because another writer may have changed state meanwhile.

**Design rules:**

- Define the authoritative source of truth clearly. For orders, money, permissions, and deduplication invariants, prefer durable DB/ledger constraints over caches.
- Give cache keys TTLs, versions, or invalidation tied to authoritative updates; never assume invalidation always succeeds.
- Accept that operations around failover can replay at request or message layers. Business unique keys and idempotent handlers must tolerate replays.
- When an outcome cannot be verified, represent it as **unknown / pending reconciliation** with a reconciliation job—never assume "success" or "not executed."
- Never confuse **`WAIT`** (waiting for replica ACKs) with multi-node transactions or guaranteed fsync durability on every node.

## 9. Health Checks and Operational Observability

An app using Redis strictly as a cache can stay ready when Redis drops; an app requiring Redis for authentication may no longer be ready. Readiness should reflect **ability to fulfill the business contract**, not merely a `PING` check.

Example where DB is mandatory and Redis cache is optional:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
~~~

Here readiness excludes the **`redis`** health contributor; overall health at another endpoint can still report Redis down. If Redis is strictly mandatory for every operation, include Redis in readiness or expose a business-aware health indicator. Keep liveness focused on process health so pods do not restart in a loop whenever an external dependency fails.

Monitor at minimum:

| Group | Metrics / Events to Watch | Operational Question |
|---|---|---|
| Client | Timeouts, connection failures, reconnects, command durations, pool saturation (if pooled) | Is Redis slow, disconnected, or out of connections? |
| Failover | Primary changes, detection/recovery duration, topology refreshes/redirections | How long until the app connects to the new primary? |
| Redis data | Replication lag, memory, evictions, rejected commands, persistence errors | Are data risks or capacity pressures rising? |
| App policies | Cache hit/miss, fallback count, breaker state, retry count, rejected requests | Is the app actually degrading per policy? |
| Downstream | DB QPS, connection pools, query latency, HTTP 429/503/5xx, consumer lag | Is a Redis failure cascading to other systems? |

Use Micrometer/Actuator to emit metrics from the Redis adapter; log request/correlation IDs, operation type, duration, retry status, and exception class. Never log passwords, tokens, session values, or sensitive payloads. Avoid PII or high-cardinality keys in metric labels: tag by key group and operation instead of full keys.

Base alerts on **error rates and business impact**: high cache misses may be benign, whereas token-revocation check failures or spikes in unknown-state transactions warrant high priority.

## 10. Testing Fault Tolerance

Testing only the happy path with Redis up is insufficient. Include unit tests for the policy matrix, integration tests with real Redis, and fault-injection tests in an environment mirroring production topology when validating failover.

| Fault Scenario | How to Simulate in Test Environment | Outcome to Prove |
|---|---|---|
| Redis down / wrong endpoint | Stop test Redis or point to closed port | Cache reads fall back to DB within deadline; critical ops reject per contract. |
| Latency spike / packet loss | Network proxy like Toxiproxy between Spring Boot and Redis | Bounded timeouts, no retry storm, circuit breaker opens at threshold. |
| Disconnect after sending write | Drop connection/proxy at controlled timing | No duplicate counter increments, payments, or messages from blind retries. |
| Sentinel primary switch | Multi-node Redis + Sentinel fixture; trigger failover | Client finds new primary; bounded error window; no false zero-loss claim. |
| Cluster reshard / failover | Test Redis Cluster; move slots or stop primary | Client handles `MOVED`/`ASK`, refreshes topology, honors timeouts. |
| Redis recovers with cold cache | Flush test cache and restore traffic | No DB-crushing stampede; jittered TTLs and bulkheads hold. |
| DB simultaneously overloaded during cache outage | Constrain DB pool or add query load in test | System sheds load/degrades without unbounded queueing or hangs. |
| Consumer reconnects after drop | Disconnect Pub/Sub or Streams adapter then reconnect | Message loss/redelivery contract verified; consumer idempotent, ACKs properly timed. |

Cache-aside tests should assert three distinct paths: **cache hit**, **cache miss**, and **Redis exception**. The exception path must assert the DB is queried, the caller receives valid data, and cache error metrics increment, alongside tests proving DB errors are not swallowed. For locks and idempotency, assert Redis unavailability causes rejection or uses the defined backup mechanism—never silently proceeding.

Measure **failure detection time**, **failover duration**, **time to recover success rate**, **unknown-outcome request count**, **DB load increase**, and **duplicate record count**. A single Redis container cannot prove Sentinel or Cluster behavior; validating failover requires a matching topology.

## 11. Runbook During a Redis Outage

1. **Assess impact:** Is Redis serving caches or mandatory invariants? Check 5xx rates, rejected requests, unknown transactions, and DB load; identify affected services.
2. **Isolate root cause:** distinguish DNS/TLS/ACL issues, network partitions, Redis overload, primary failover, unreachable Cluster node addresses, or app errors (`WRONGTYPE`/`CROSSSLOT`).
3. **Protect business safety:** keep payment/lock/idempotency operations fail-closed or on authoritative sources; enable tested cache fallbacks/degradation while capping DB load and retries.
4. **Watch recovery:** inspect current primary, replication lag, client reconnects, and topology refreshes; evaluate command errors and latency rather than `PING` alone.
5. **Recover smoothly:** let breakers half-open, ramp cache traffic gradually to avoid reloading every key at once, reconcile unknown-outcome requests, and handle pending/un-ACKed events.
6. **Close with evidence:** compare SLOs, impacted requests, lost/duplicate data (if any), and logs/metrics/traces by request ID; tune thresholds and fault-injection tests.

Never wipe all keys or manually trigger failover in production solely because clients observe timeouts. Verify root causes and follow Redis/Sentinel/Cluster or cloud provider runbooks before intervening.

## 12. Pre-Production Checklist

- [ ] Every Redis usage documents its **role**, **authoritative data source**, and **Redis-outage policy**.
- [ ] Cache misses are separated from Redis failures and data/config errors; business errors are never swallowed.
- [ ] Connect timeouts, command timeouts, request deadlines, retries, and circuit breakers are bounded to SLOs.
- [ ] Mutating commands are never retried blindly; idempotency, unique constraints, or reconciliation handle unknown outcomes.
- [ ] Sentinel/Cluster topologies, reachable node addresses, TLS/ACLs, failovers, and replication are tested realistically.
- [ ] Cache fallbacks are guarded by bulkheads/load shedding, with a plan for cold caches post-failover.
- [ ] Readiness/liveness probes reflect whether Redis is mandatory per the business contract.
- [ ] Metrics, alerts, traces, runbooks, and fault-injection tests cover disconnects, failovers, and recovery.
- [ ] For Spring Integration or message consumers, delivery semantics, ACKs, retries, DLQs, and deduplication are defined.

## 13. Comprehensive Scenario

A retail service runs three paths sharing one Redis Cluster:

1. **`GET /catalog/{sku}`:** Redis product cache fails during a Cluster primary failover. The service falls back to the DB behind a bulkhead, returns display data, and records fallback metrics. If the DB is already saturated, the service returns 503 per SLA instead of opening thousands of DB connections.
2. **`POST /orders`:** Redis holds a duplicate-submission marker, yet times out right after writing the marker. The service does not guess whether the marker was written. The request ID is checked against the DB unique constraint and order state table, returning the existing order or a status lookup result to the caller.
3. **`POST /admin/revoke-token`:** Redis caches token-revocation state. Redis is unreachable and no fallback verification source is available. The service rejects permission-dependent actions and logs the error rather than assuming tokens remain valid.

One network incident leads to three different responses because **the business contracts differ**. That is the core rule for running Redis in Spring Boot: HA topologies are necessary, yet **adapter error policies, idempotency, authoritative sources, and observability** determine whether the system stays correct when Redis is unavailable.
