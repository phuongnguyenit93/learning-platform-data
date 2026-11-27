# Designing Business-Impact-Driven Alerts in Spring Data Redis

A Redis system can report 95% CPU, thousands of connections, or a failover event while users continue operating smoothly. Conversely, a Redis using only a few percent CPU can bring checkout to a halt if `SET NX` used for deduplication repeatedly times out. Therefore, **a good alert does not merely say Redis looks abnormal—it clearly states what business impact that anomaly causes, who owns fixing it, and what action to take**.

In Spring Data Redis, an application can use Redis in many roles: a performance cache layer, a session store, a token or rate-limit store, a distributed lock, counters, Redis Streams, Pub/Sub, Spring Cache, or Redis Repositories. The exact same metric—such as `connected_clients`, `evicted_keys`, replication lag, or `RedisCommandTimeoutException`—carries very different severity depending on that role.

This lesson guides alert design from business objectives down to technical signals: defining **user journeys**, establishing **SLIs/SLOs**, instrumenting failures in Spring Data Redis, tiering alerts by **impact level**, combining Redis metrics with downstream metrics, writing Prometheus/Alertmanager examples, structuring runbooks, and testing alert rules. Numeric thresholds are illustrative examples only; production thresholds must be tuned to real SLOs, traffic, and architecture.

## 1. First Principle: Start from Users, Not from Redis

Suppose an e-commerce application uses Redis as follows:

```text
                Customers
                    |
     +--------------+--------------+
     |              |              |
Browse products   Log in      Place orders
     |              |              |
     v              v              v
 Redis cache    Redis session  Redis idempotency/lock
     |              |              |
     v              v              v
 PostgreSQL     Session state  Order database
     |
     +------ Redis Streams for post-processing events
```

If the product cache fails while the database has capacity, customers may only notice slower page loads. If Redis sessions become unreadable, large numbers of users may be logged out or locked out. If Redis idempotency keys are lost and the code allows reprocessing a payment request, the problem is no longer latency—it is **transactional corruption**.

Therefore, the first alerting question is not:

> How much `used_memory` is Redis consuming?

but rather:

> When Redis fails, which business capabilities are impacted, to what degree, and is the system still meeting its user commitments?

### 1.1. Translating Technical Symptoms into Impact

| Symptom | Possible Business Impact | How to Verify Impact |
|---|---|---|
| Redis `GET` timeout | Product pages slow down due to DB fallback | Endpoint p95/p99, DB load, request error rate |
| Redis session read failure | Users cannot log in | Login/auth success ratio, failed session count |
| `SET NX` lock timeout | Orders stall or duplicate actions occur | Completed orders, lock acquisition, duplicate guards |
| Stream pending grows | Shipping/email/order processing lags | Oldest uncompleted event age, backlog, business completion lag |
| Pub/Sub listener disconnects | Local caches fail to invalidate | Data staleness, version mismatch, disconnected consumer count |
| Redis primary failover | Brief wave of failing operations | End-to-end success SLI and recovery duration |
| `evicted_keys` rises | Cache hit rate falls or critical data gets evicted | Cache misses, session evictions, request errors |
| Prolonged AOF rewrite | Latency rises, memory pressure grows | Redis command p99, API latency, cgroup memory |
| `rejected_connections` rises | Some apps fail to connect | Client connection failures and per-service error rates |

Every row requires an **impact definition** rather than a generic conclusion that "Redis has an issue".

## 2. Is Redis a Cache or a Critical Component?

Classify each Redis usage in your architecture.

### 2.1. Redis Is Only a Reconstructible Cache

Example: `@Cacheable` storing product details whose source of truth lives in PostgreSQL.

```text
Redis available:
  GET cache -> fast return

Redis unavailable:
  GET fails -> service queries DB -> still returns accurate data
```

If the DB fallback works and requests succeed, this is **performance degradation** rather than an immediate outage. However, the DB might not survive full traffic without Redis, so measure **fallback capacity**, not merely HTTP 2xx codes.

### 2.2. Redis Holds Data Required for Requests to Succeed

Examples:

- Session state with no alternative store.
- Rate-limit state where the system enforces a fail-closed policy.
- Anti-replay tokens or nonces.
- Job coordination locks.
- Idempotency records.
- Streams serving as a work queue with completion SLAs.

In this category, Redis errors directly block business workflows or risk data integrity. Prioritize alerting on **business operation** success/failure, not merely service health.

### 2.3. Dependency Matrix

| Redis Role | When Redis Fails | Primary Measurement Priority |
|---|---|---|
| Product cache | Fall back to origin store | Latency + DB saturation + cache read errors |
| Session store | Logins and sessions may fail | Auth availability |
| Feature flag cache | Fall back to defaults or fail-closed by feature | Policy adherence and fallback rate |
| Rate limiter | Fail-open or fail-closed | Abuse risk, false-rejection rate |
| Distributed lock | Must not proceed blindly | Job success, lock wait, ownership correctness |
| Idempotency store | Must not accept dangerous duplicates | Duplicate prevention, payment/order correctness |
| Redis Streams | Events accumulate backlog or pending | Processing delay + completion ratio |
| Pub/Sub | Notifications may drop while offline | Listener health + reconciliation/data freshness |
| Counter analytics | Bounded delay or partial loss may be acceptable | Data freshness, error budget |
| Redis Repository as primary data store | Direct data/CRUD loss risk | Read/write availability and durability |

**One Redis instance can serve multiple roles.** The exact same Redis outage might be P3 for product caching yet P1 for sessions or idempotency. Alerts must reflect which business capability is hurt.

## 3. Use User Journeys as the Unit of Alert Design

A user journey is an end-to-end flow a user or system expects to complete:

1. View product page.
2. Log in and maintain a session.
3. Create an order.
4. Process payment exactly once.
5. Receive order confirmation.
6. Synchronize inventory.
7. Query transaction history.

For each journey, define:

- **Success outcome:** clear, measurable criteria.
- **Time window:** e.g. "order confirmed within 30 seconds" or "event processed within 2 minutes".
- **Redis dependency:** cache, key, Stream, lock, or session.
- **Fallback:** whether one exists, whether it handles load, and whether it risks wrong business behavior.
- **Owner:** which team is authorized and able to fix it.
- **Severity:** derived from real impact, not metric names.

Example design table:

| Journey | Primary SLI | Redis Dependency | Diagnostic Redis Signals |
|---|---|---|---|
| View product | Fraction returning correct data within 500 ms | Cache | `GET` errors, cache hits, DB load |
| Log in | Fraction of successful logins | Session | Redis session errors, latency |
| Place order | Fraction of completed orders | Idempotency/lock | Lock failures, duplicate checks |
| Send confirmation | Fraction of events processed within 60 s | Stream | Oldest pending age, lag, consumer errors |
| Sync inventory | Delay between change and read state | Pub/Sub/Stream | Listener disconnects, reconciliation mismatches |

This table serves as an **observability contract** across application teams, SRE, and product owners.

## 4. SLI, SLO, SLA, and Error Budget

### 4.1. What Is an SLI?

A **Service Level Indicator (SLI)** measures how well a service meets expectations.

Example availability SLI:

\[
SLI_{availability}=
\frac{\text{successful valid requests}}
{\text{total valid requests}}
\]

Or latency SLI:

\[
SLI_{latency}=
\frac{\text{valid requests completed within threshold}}
{\text{total valid requests}}
\]

Crucial point: define **valid requests** and **success** by business semantics, not raw HTTP status codes. An endpoint returning `200` with a wrong default value may not be a genuine success.

### 4.2. What Is an SLO?

A **Service Level Objective (SLO)** is the target for an SLI over a rolling window.

Hypothetical examples:

```text
Product page:
  99.9% of valid requests return accurate results in <= 500 ms
  measured over a rolling 30-day window

Login:
  99.95% of valid requests succeed
  measured over a rolling 30-day window

Order processing:
  99.9% of required events complete within <= 60 seconds
```

These values are illustrative only. There is no universal "standard Redis SLO" for every system.

### 4.3. SLA vs. SLO

- **SLO:** internal engineering and operational target.
- **SLA:** customer-facing service commitment, often carrying commercial penalties.
- **SLI:** the measurement itself.
- **Error budget:** the permissible failure allowance during the evaluation window.

With a 99.9% availability SLO, the error budget ratio is:

\[
1-0.999=0.001=0.1\%
\]

A Redis incident raising request errors burns through this budget. Alerting on budget burn rate is usually far more actionable than fixed thresholds like "Redis CPU > 80%".

### 4.4. From Business SLO Down to Redis Alerts

Flow:

```text
Business SLO: order creation succeeds
         |
         v
SLI: order creation errors / valid requests
         |
         v
Alert: fast error-budget burn
         |
         +-- Redis idempotency GET/SET timeout?
         +-- DB transaction errors?
         +-- payment gateway errors?
         +-- traffic spike?
```

**Business alerts detect impact**, while Redis metrics isolate root cause. Never automatically call every order failure a Redis incident merely because the order service talks to Redis.

## 5. Distinguishing Leading Indicators from Impact Indicators

Two signal categories exist:

### 5.1. Impact Indicators: Users Are Already Affected

- Login success rate drops.
- Order creation failures rise.
- Request p99 crosses threshold.
- Event processing age breaches SLA.
- Stale/incorrect cache responses exceed permissible bounds.
- Duplicate payments are detected.

These generally justify **paging** because user impact is already occurring.

### 5.2. Leading Indicators: Risk Is Approaching

- Redis memory headroom shrinks.
- Replication lag rises.
- `aof_delayed_fsync` climbs.
- Pool waiters climb.
- Stream pending climbs before breaching deadlines.
- Redis disk nears capacity.
- Redis latency trends upward.
- Sentinel quorum shrinks while primary stays up.

These fit **early risk alerts/tickets**, or paging only when failure is imminent and consequences are severe. Never assign identical severity to every signal.

### 5.3. Combining Both Categories

A well-designed alert pairs them:

```text
Impact:
  Checkout SLO burn rate high -> PAGE

Context:
  Redis command timeouts rising
  Redis server slowlog showing EVAL
  Redis pool waiters rising
  DB healthy

=> Incident response immediately has context to isolate the issue
```

Instead of:

```text
Redis CPU > 70% -> PAGE
Redis memory > 70% -> PAGE
Redis client count > 100 -> PAGE
```

without showing any user journey failing.

## 6. Choosing Severity from Business Impact

Illustrative severity table:

| Severity | Typical Conditions | Escalation Channel |
|---|---|---|
| **P1 / Critical** | Duplicate payments processed, business data loss, widespread login/checkout outage | Immediate page, incident commander, coordinate owners |
| **P2 / High** | Critical journey breaching SLO significantly, stream lag causing SLA violations | Page relevant on-call |
| **P3 / Medium** | Cache fallback holding yet DB nearing saturation; disk/memory approaching risk | Ticket/business-hours or page depending on headroom |
| **P4 / Informational** | Clean failover with zero SLO impact, node self-recovered | Dashboard / event log |

This matrix is illustrative. Real severity follows your organization's incident policy, market, time of day, user scale, and data safety requirements.

### 6.1. Correctness Incidents May Warrant Paging Even at Low Error Rates

If even a handful of payments execute twice, HTTP error rate may remain near 0%. Yet **an invariant violation** is critical.

Create dedicated alerts for:

- Confirmed idempotency duplicates.
- Lock ownership violations.
- Unacceptable data mismatches detected.
- Abnormal charges or refunds.
- Redis operations where fallback policies permit unsafe progress.

A system relying solely on HTTP 5xx SLOs will miss these business integrity failures.

## 7. Measuring at the Right Layers: Controller, Service, and Redis Client

Maintain at least three observation layers.

```text
[Business journey / HTTP]
        |
        | request outcome, response duration, business invariants
        v
[Spring service]
        |
        | cache hit/miss/fallback, Redis operation outcomes
        v
[Spring Data Redis / client]
        |
        | command latency, connection timeouts, pool waits
        v
[Redis server / topology]
        |
        | memory, CPU, replication, persistence, clients
```

### 7.1. Why Redis Health Checks Alone Are Insufficient

Redis `PING` replies `PONG`, yet:

- A critical Lua script may fail with `WRONGTYPE`.
- A `SET` may fail with `OOM command not allowed`.
- Redis Cluster may miss slots or hit `CROSSSLOT`.
- Session serializers may fail to decode after a rolling upgrade.
- Cache fallbacks may still overload the database.
- Redis Streams may deliver entries whose handlers never finish.

Health checks inspect only one narrow layer, never end-to-end business success.

### 7.2. Why HTTP 5xx Alone Is Also Insufficient

Under fail-open caching:

```text
Redis unavailable
    |
    v
Application falls back to DB
    |
    v
HTTP 200, yet latency climbs and DB nears saturation
```

Initially HTTP 5xx does not budge. Without leading metrics like cache errors, DB pool usage, and fallback rates, operations only get paged once the database collapses.

Solution: **business impact + dependency risk**, with distinct severities and noise-resistant thresholds.

## 8. Defining Structured Metrics for Spring Data Redis

Not every useful metric comes built-in from Spring Boot. For critical workflows, instrument Redis-related outcomes in the application.

Example custom application metric catalog:

| Example Metric Name | Type | Suggested Labels | Meaning |
|---|---|---|---|
| `app_business_requests_total` | Counter | `journey`, `outcome` | Business outcomes |
| `app_business_request_duration_seconds` | Histogram/Timer | `journey`, `outcome` | Journey latency |
| `app_redis_operations_total` | Counter | `role`, `operation`, `result` | Redis operation success/error |
| `app_redis_operation_duration_seconds` | Timer | `role`, `operation`, `result` | Redis call latency |
| `app_cache_access_total` | Counter | `cache`, `outcome` | Hit, miss, fallback, error |
| `app_cache_fallback_total` | Counter | `cache`, `reason` | Origin fallback counts |
| `app_stream_events_total` | Counter | `stream_group`, `result` | Stream processing success/failure |
| `app_stream_processing_delay_seconds` | Histogram | `stream_group` | Delay from event creation to completion |
| `app_lock_acquire_total` | Counter | `workflow`, `result` | Acquired, timeout, denied |
| `app_idempotency_conflicts_total` | Counter | `workflow`, `result` | Replay/duplicate detections |
| `app_dependency_fallback_total` | Counter | `dependency`, `outcome` | Fallback success/failure |

These are **names proposed by this lesson**, not built-in series claimed to come from Spring Boot automatically. Follow your project's metric naming conventions if established.

### 8.1. Cardinality Rules

Safe labels:

```text
service="checkout"
environment="production"
journey="create_order"
operation="get"
role="idempotency"
result="timeout"
```

Labels to avoid:

```text
customer_id="123456789"
order_id="order-123"
redis_key="session:customer:123456789"
request_id="f3a2..."
```

Each distinct label value creates a separate time series, placing severe load on Prometheus and observability backends. Individual IDs belong in access-controlled logs and traces, not metric labels.

### 8.2. Keep Distinct Outcomes Separate

For Redis caches, distinguish at minimum:

```text
HIT
MISS
REDIS_ERROR
FALLBACK_SUCCESS
FALLBACK_FAILURE
```

Never record connection errors as `MISS`, which blinds you to dependency outages.

For `SET NX` idempotency:

```text
CREATED
EXISTS / CONFLICT
REDIS_ERROR / UNKNOWN
```

`EXISTS` is usually not an infrastructure fault; it reflects a duplicate request caught as designed.

## 9. Example Cache Instrumentation in Spring Data Redis

Example service reading a product cache and falling back to a repository on miss. Redis serves strictly as an optimization layer; cache errors are counted separately.

```java
package com.example.product;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;
    private final ProductRepository repository;
    private final MeterRegistry registry;
    private final Timer redisReadTimer;

    public ProductCacheReader(
            StringRedisTemplate redis,
            ProductRepository repository,
            MeterRegistry registry
    ) {
        this.redis = redis;
        this.repository = repository;
        this.registry = registry;

        this.redisReadTimer =
                Timer.builder("app.redis.operation.duration")
                    .description("Redis read duration from application")
                    .tag("role", "product_cache")
                    .tag("operation", "get")
                    .register(registry);
    }

    public ProductDto find(String productId) {
        String key = "cache:product:v1:" + productId;

        String cached = null;

        try {
            cached = redisReadTimer.record(
                () -> redis.opsForValue().get(key)
            );

            if (cached != null) {
                count("app.cache.access", "hit");
                return deserialize(cached);
            }

            count("app.cache.access", "miss");
        } catch (org.springframework.dao.DataAccessException ex) {
            count("app.cache.access", "redis_error");
            // Log/trace error with safe level of detail.
            // Fall back only when policy permits.
        }

        count("app.cache.fallback", "attempt");
        ProductDto product = repository.find(productId);

        if (product == null) {
            count("app.cache.fallback", "not_found");
            return null;
        }

        count("app.cache.fallback", "success");

        try {
            redis.opsForValue().set(
                key,
                serialize(product),
                Duration.ofMinutes(5)
            );
        } catch (org.springframework.dao.DataAccessException ex) {
            count("app.cache.write", "redis_error");
            // Cache write is best-effort in this design.
        }

        return product;
    }

    private void count(String metric, String outcome) {
        Counter.builder(metric)
                .tag("cache", "products")
                .tag("outcome", outcome)
                .register(registry)
                .increment();
    }

    // Application methods to implement according to real DTO/schema.
    private ProductDto deserialize(String value) {
        return ProductJsonCodec.decode(value);
    }

    private String serialize(ProductDto product) {
        return ProductJsonCodec.encode(product);
    }
}
```

`ProductRepository`, `ProductDto`, and `ProductJsonCodec` are application abstractions, not built-in Spring Data Redis APIs.

### 9.1. Boundaries of This Example

- Times `GET` via `Timer`, yet does not separate pool borrow wait from server execution.
- Falls back only on Redis `DataAccessException`; JSON deserialization failures may need a dedicated policy such as invalidating corrupted entries and alerting.
- `repository.find(...)` can still fail; never treat repository exceptions as cache misses.
- Continuous fallbacks can overload the database; monitor DB latency, connections, and error rates.
- `register(...)` normally reuses existing meter identities; in production code, pre-build stable tagged meters to minimize hot-path overhead.
- In Prometheus exposition, Micrometer Timers typically emit `_seconds_count`, `_seconds_sum`, and `_bucket` when histograms are enabled; verify your active registry configuration.

### 9.2. Fallback Failures Can Hurt Worse Than Cache Failures

Suppose Redis `GET` errors jump from 0% to 100%, yet the DB fallback absorbs everything cleanly. Redis cache errors look terrible while users barely notice. Once the DB starts timing out too, **that is when the user journey faces critical danger**.

Maintain at least two alert tiers:

```text
Redis cache degraded + DB healthy:
    early warning / triage

Product page SLO burn high:
    page on business impact
```

Never silence Redis cache error alerts completely just because a fallback exists; the fallback may be burning away reserve headroom.

## 10. ReactiveRedisTemplate: Observe Publishers at the Right Time

In WebFlux, Redis calls return `Mono` or `Flux`. Recording metrics when **constructing** the publisher rather than on subscription can count commands that never executed.

Illustrative example:

```java
public Mono<String> getCachedValue(String key) {
    return reactiveRedis.opsForValue()
        .get(key)
        .doOnNext(value -> metrics.cacheHit())
        .switchIfEmpty(Mono.defer(() -> {
            metrics.cacheMiss();
            return Mono.empty();
        }))
        .doOnError(error -> metrics.redisError(error));
}
```

Note: this attaches hooks only for non-empty read, empty read, and error. Production code also needs:

- `doFinally`/Micrometer Observation to record full duration.
- Never counting errors as misses.
- Clear handling for cancellation and timeouts.
- Never calling `.block()` on a WebFlux event loop just to emit metrics.
- Stable metric labels.

### 10.1. Common Observability Bug: Swallowing Errors and Reporting Success

```java
redisRead()
    .onErrorResume(ex -> Mono.just("DEFAULT"))
```

If metrics only inspect downstream `onNext`, dashboards show "GET succeeded" even while Redis failed. Record **Redis dependency errors** before `onErrorResume`, while separately tracking whether the fallback preserved the user journey.

That is why instrumentation belongs at **both the dependency boundary and the business boundary**.

## 11. Designing Alerts for Spring Cache

With `@Cacheable`, `@CachePut`, and `@CacheEvict`, observe at minimum:

- Cache hit ratio.
- Cache miss ratio.
- Cache read and write errors.
- Origin query latency after misses.
- TTLs and thundering herds on simultaneous expiration.
- Invalidation success and errors.
- Staleness when stale data violates business contracts.
- Redis cache clearing behavior across Cluster if applicable.

### 11.1. Is a Low Cache Hit Ratio Always an Incident?

No. Rising cache misses can stem from:

- Deploying a new release that changed key prefixes.
- Intentional cache flushing/warming.
- Shifting working sets.
- Deliberate TTL reductions.
- Traffic from a new user cohort.
- Redis eviction.
- Code mistakenly counting Redis connection errors as misses.

Hence, **a high cache miss rate should not automatically page as P1**.

A better rule:

```text
Cache hit ratio drops sharply
AND database utilization exceeds safe headroom
AND product endpoint latency degrades
```

or fire a separate warning for low hit ratio, paging only when user SLOs are threatened.

### 11.2. Cache Invalidation Failures

If a Redis cache is purely an accelerator, a cache write failure may be benign. Yet if `@CacheEvict` fails after updating the DB, users can be served stale data.

Track separately:

```text
cache_write_error
cache_invalidation_error
cache_read_error
```

For freshness-sensitive data, invalidation failures can be more serious than write errors. Pair with bounded max TTLs, versioned keys, or reconciliation against the origin store.

## 12. Sessions: Alert on Login and Session Continuity

When Spring Session uses Redis, critical business signals include:

- Login success rate per endpoint group.
- Authenticated requests failing session lookup.
- Abnormal rate of users forced to re-authenticate.
- Session store read/write error counts.
- Session deserialization failures after deployments.
- Session TTL diverging from policy.
- Redis eviction removing active sessions.

Scenario:

```text
Redis node still answers PONG
Yet session serializer changed incompatibly
    |
    v
Session lookup fails
    |
    v
Authenticated requests fail
```

An alert on **login/auth SLIs** catches the user impact, while Redis session decode errors diagnose the root cause.

### 12.1. Never Use a Healthcheck Endpoint as a Login SLI

A successful `GET /health` does not prove Redis can read real serialized session payloads. Test session serialization, rolling upgrades, and TTLs in integration tests, and monitor session failures in production at the right abstraction.

### 12.2. Distinguish Policy Expiration from Infrastructure Failures

Users logging in again because their session naturally hit its TTL is not an incident. If session failures jump after a failover, deploy, or eviction spike, separate:

```text
normal_expiration
explicit_logout
missing_session_unexpected
deserialize_error
redis_unavailable
```

Never lump all of those into a single "Redis session errors" counter and page on it.

## 13. Locks and Idempotency: Prioritize Business Invariants

With Redis locks or idempotency keys, failure goes beyond latency.

Example:

```text
POST /payments
    |
    v
Check/claim idempotency key in Redis
    |
    +-- claimed     -> process payment
    +-- exists      -> return prior result / report duplicate
    +-- Redis error -> apply fail-closed or fail-open decision
```

If Redis fails and the application chooses **fail-open**, it may charge payments without deduplication. HTTP 2xx looks healthy even while the system becomes unsafe.

### 13.1. Dedicated SLIs

- Idempotency check/claim success rate per workflow.
- Requests with `unknown` idempotency state.
- Duplicate requests caught and blocked.
- Confirmed duplicate side effects discovered during reconciliation.
- Lock acquisition timeout rate.
- Lock wait duration.
- Lock ownership violations, if detectable.
- Transactions requiring compensation.

### 13.2. Invariant Alerts Are High-Priority Alerts

For example:

```text
ConfirmedDuplicateCharge > 0
```

can justify immediate high-severity escalation depending on product policy—never wait for a 5% error ratio.

Ensure the detection source is **trustworthy**: counting blocked duplicate requests does not mean duplicate charges occurred. Metric names must clearly separate `duplicate_attempt_prevented` from `duplicate_side_effect_confirmed`.

### 13.3. Lock Acquisition Timeouts Are Not Always a Redis Bug

Sometimes a lock is legitimately held by a worker running a slow task. Rising acquisition timeouts can stem from business contention, stuck workers, or Redis latency.

Correlate:

```text
lock_wait_duration
lock_acquire_result
worker_processing_duration
Redis command latency
business completion ratio
```

Never assume raising lock TTLs or connection pool sizes fixes every lock timeout.

## 14. Redis Streams: Alert on Work Completion Time

For Redis Streams consumer groups, stream length and pending counts are only **indicators**, not complete business SLIs.

Flow:

```text
Producer XADD
     |
     v
Redis Stream
     |
     v
XREADGROUP / ReadOffset.lastConsumed()
     |
     v
Business handler
     |
     v
Commit side effect
     |
     v
XACK
```

A message may be delivered yet stay in the Pending Entries List (PEL) until the handler finishes and acks.

### 14.1. Most Important Alert: Age of Uncompleted Work

Suppose the requirement is:

```text
99.9% of order-confirmation events complete within 60 seconds.
```

`pending = 100` does not mean an SLA breach if workers drain 10,000 events/s in milliseconds. Conversely, a single message pending for **30 minutes** can leave an order stranded.

Measure:

- `processing_delay_seconds` from event creation to side-effect completion.
- Oldest uncompleted business event age.
- Uncompleted event counts by type.
- Successful completions/sec vs. arrivals/sec.
- Retry and reclaim counts.
- Handler failure ratios.
- Pending entries and consumer lag.

### 14.2. `XINFO GROUPS` Lag Is Not Failed Event Count

A group can show `lag=0` while still holding unacknowledged pending entries: all entries were delivered, yet processing has not finished.

Conversely, `pending = 0` does not prove all events succeeded if code **ACKed too early**, created the group at `$`, or trimmed entries away.

For job SLAs, rely on a **business completion metric**, not Redis group lag alone.

### 14.3. Tiered Alerts

| Tier | Signal | Action Level |
|---|---|---|
| Early warning | Backlog growing steadily; consumer rate trailing producer rate | Warning, check capacity |
| SLO risk | Oldest unprocessed age approaching deadline | Page if projected to breach commitment |
| Impact | Event past SLA or completion ratio missing SLO | Page |
| Recovery failure | High pending age; reclaims failing to clear work | Escalate to stream/worker owner |
| Suspected data loss | Source event ID missing from stream and completion records | Investigate data integrity; don't just add consumers |

### 14.4. Do Not Use Stream ID Timestamps as the Sole Clock

Redis Stream IDs take the form `milliseconds-sequence`, yet in many architectures that timestamp is not when the **business event** originated. If events are backfilled, imported, or assigned custom IDs, computing `now - streamIdTimestamp` misleads.

Store a trustworthy `eventCreatedAt` field in payload/metadata and measure:

```text
business event created -> handler committed
```

Synchronize clocks and account for clock skew when collecting timings.

## 15. Pub/Sub: Connection Up Does Not Prove Events Were Received

Redis Pub/Sub keeps no durable backlog for offline subscribers. A `RedisMessageListenerContainer` can reconnect cleanly after failover, yet **messages published during the disconnect are never replayed**.

Metrics:

- Listener subscription state.
- Disconnect and reconnect counts.
- Producer published message counts.
- Subscriber received message counts.
- Handler processing errors.
- Business freshness or version mismatches.
- Timestamp of last successful reconciliation.

### 15.1. Does "Published Minus Received" Equal Lost Messages?

Not simply. With Pub/Sub:

- One publish can fan out to multiple subscribers.
- One subscriber can match overlapping patterns.
- Multiple consuming replicas/instances may listen simultaneously.
- Producer and subscriber metrics may have different scopes or clock alignment.
- Message filtering, subscription races, restarts, or scaling shift raw counts.

To detect real loss, use **event IDs, expected recipients, and business reconciliation**. When Pub/Sub only delivers cache invalidation hints, measure **data staleness** and run periodic reconciliation instead of demanding exact Pub/Sub count parity.

### 15.2. Alert on Correctness, Not Only Disconnects

A 3-second Pub/Sub disconnect may not warrant a page if short TTLs and reconciliation cover it, yet those 3 seconds could leave revoked permissions active in a security workflow.

Tie severity to **the criticality of the data managed by notifications** and self-healing capability.

## 16. Redis Server Metrics: Context and Risk Alerts

Redis `INFO` exposes metrics across sections such as:

```redis
INFO stats
INFO clients
INFO memory
INFO commandstats
INFO persistence
INFO replication
INFO cpu
```

Tools like a Redis exporter turn these fields into Prometheus metrics, though **exact series names vary by exporter and version**. Never write alerts assuming `redis_memory_used_bytes` or `redis_connected_clients` exist verbatim on every cluster.

### 16.1. Memory Pressure

Track:

- `used_memory` and `maxmemory`.
- `used_memory_rss`.
- `used_memory_peak`.
- `mem_fragmentation_ratio` in context.
- `evicted_keys` growth over time.
- `mem_not_counted_for_evict` if present.
- Cgroup/container memory and OOM kills.
- Free disk space if AOF/RDB is enabled.

A good memory alert distinguishes roles:

```text
Cache instance:
  moderate evictions can be normal
  falling hit rate and DB overload drive real impact

Session / critical state:
  unexpected evictions risk losing active sessions or state
  warn much earlier
```

### 16.2. Client Connections

Track:

```redis
INFO clients
INFO stats
CONFIG GET maxclients
```

Signals:

- `connected_clients`.
- `blocked_clients`.
- `rejected_connections`.
- Application pool active, idle, and waiting counts.
- Command timeouts and connection errors.

`blocked_clients` on Redis does not equal Java threads waiting to borrow from a pool. An app can exhaust its local pool while Redis sees very few connections.

### 16.3. Command Latency

Measure from both application and Redis:

- Lettuce/Jedis command latency if instrumentation is enabled.
- Micrometer Timers on business operations.
- `SLOWLOG` and Redis latency monitor.
- CPU and network RTT.
- Lua script execution duration if used.

`SLOWLOG` excludes pool wait and network RTT, so an empty slowlog never proves the dependency adds zero latency.

## 17. Persistence: Alerting on Data Durability Risk

If Redis is only a reconstructible cache, snapshot or AOF failures matter far less than when Redis holds irreplaceable state.

Signals to check in `INFO persistence`:

| Field | Meaning |
|---|---|
| `rdb_last_bgsave_status` | Outcome of latest snapshot |
| `rdb_last_save_time` | Timestamp of latest successful snapshot |
| `rdb_bgsave_in_progress` | Background snapshot currently running |
| `rdb_last_cow_size` | Copy-on-write memory of recent RDB job, if available |
| `aof_enabled` | Whether AOF is enabled |
| `aof_last_bgrewrite_status` | Outcome of recent AOF rewrite |
| `aof_rewrite_in_progress` | Rewrite currently running |
| `aof_delayed_fsync` | Signs of delayed fsync calls |
| `aof_current_size` | Current AOF size reported by Redis |
| `aof_last_cow_size` | Copy-on-write memory of recent rewrite, if available |

Set thresholds on:

- Time since last successful snapshot when RDB underpins durability.
- AOF write or fsync failures.
- Disk capacity and inodes.
- Duration of background persistence jobs.
- Memory headroom for fork/COW.
- Observed RPO verified in drills or reconciliation.

**Never equate `BGSAVE in progress` with an incident.** Background saves are routine; alert only when duration, latency, or memory impact exceeds budgets.

### 17.1. An AOF Failure Might Not Cause Immediate HTTP Errors

Redis can keep serving reads even while durable writes are failing. Waiting until checkout breaks wastes precious lead time to fix storage.

This is a prime case for a **high-severity leading risk alert**, especially when Redis stores critical state.

## 18. Replication, Sentinel, and Cluster: Separate Health from Impact

### 18.1. Replication Lag

Redis replication is typically asynchronous. Growing lag widens the window of potential recent write loss during primary failover, even while current requests succeed.

Measure:

- Replica link status.
- Per-node replication offset and lag.
- Healthy replica count.
- Acceptable data-loss window (RPO).
- Redis persistence health.
- Acknowledged business writes and reconciliation capability.

Separate alerts:

```text
Risk:
  replica lag above target + failover redundancy reduced

Impact:
  primary failover occurred with confirmed data mismatch/loss
```

Never claim `offset difference / commands per second` gives exact lag duration. Replication offsets track bytes in the stream, not logical business commands.

### 18.2. Sentinel Quorum

When a Redis primary stays up yet Sentinel loses majority quorum to perform automatic failover, that is an **HA risk**, not yet a live outage.

If the primary simultaneously becomes unreachable and replicas cannot be promoted, impact turns immediate.

Route quorum-loss alerts promptly to infrastructure owners, deciding between paging vs. ticketing based on availability requirements.

### 18.3. Redis Cluster

Track:

- Coverage across all 16,384 slots.
- `cluster_state`.
- Primary and replica availability.
- `MOVED`, `ASK`, `TRYAGAIN`, and `CLUSTERDOWN`/connection errors.
- Hot slots and CPU/memory skew.
- Application multi-key `CROSSSLOT` errors.

A `MOVED` redirect handled transparently by the client during planned resharding can be harmless. `CROSSSLOT` is usually a key-design/command bug rather than Redis CPU trouble. Do not page solely on redirects if SLIs hold steady during planned topology changes.

## 19. Alerting on Error-Budget Burn Rate

A reliable approach is paging when a service consumes its error budget too quickly.

With a 99.9% availability SLO over 30 days, the allowed error ratio is:

\[
e = 1-0.999 = 0.001
\]

Burn rate:

\[
B = \frac{\text{observed error ratio}}{e}
\]

If the observed error ratio hits 1.44%:

\[
B = \frac{0.0144}{0.001}=14.4
\]

The budget is burning **14.4 times** faster than the sustainable average pace if sustained.

### 19.1. Why Combine Short and Long Windows?

- Short windows catch sudden live outages quickly.
- Long windows filter brief noise and confirm sustained impact.
- Requiring **both** catches real outages while preventing pages over a few seconds of transient errors.

An example multi-window policy often considered for a 30-day SLO:

```text
Fast burn:
  burn rate > 14.4 over a 1-hour window
  AND burn rate > 14.4 over a 5-minute window

Slow burn:
  burn rate > 6 over a 6-hour window
  AND burn rate > 6 over a 30-minute window
```

These are **illustrative multi-window burn-rate patterns**, not mandatory defaults for every service. Tune windows and thresholds to your SLOs, traffic rates, and error classification.

### 19.2. Separate Valid Business Errors from System Errors

If a customer enters a wrong password, returning `401` is a **valid** login journey outcome, not a service outage. If `401` spikes because Redis sessions are unreadable and the code treats failures as unauthenticated, that is a service failure.

SLIs must track **valid requests** and classify outcomes by business contract, never blindly summing `status >= 400`.

## 20. Example Prometheus Recording Rules for Business SLIs

Suppose the application exports:

```text
app_business_requests_total{
  service="checkout",
  journey="create_order",
  result="success|failure"
}
```

In Prometheus, `_total` is an increasing counter. We compute a journey's error ratio over 5-minute and 1-hour windows.

Illustrative rules file:

```yaml
groups:
  - name: business-sli
    interval: 30s
    rules:
      - record: business:journey_requests:rate5m
        expr: |
          sum by (service, journey) (
            rate(app_business_requests_total[5m])
          )

      - record: business:journey_errors:rate5m
        expr: |
          sum by (service, journey) (
            rate(app_business_requests_total{result="failure"}[5m])
          )

      - record: business:journey_error_ratio:5m
        expr: |
          business:journey_errors:rate5m
          /
          clamp_min(business:journey_requests:rate5m, 1e-9)

      - record: business:journey_error_ratio:1h
        expr: |
          sum by (service, journey) (
            rate(app_business_requests_total{result="failure"}[1h])
          )
          /
          clamp_min(
            sum by (service, journey) (
              rate(app_business_requests_total[1h])
            ),
            1e-9
          )
```

If metrics also carry `environment`, `cluster`, or `tenant_tier` labels, retain the labels needed to isolate SLOs and route alerts cleanly. Never merge production and staging into a single ratio.

### 20.1. Handling Very Low-Traffic Windows

An error ratio of:

```text
1 failure / 1 request = 100%
```

may have tiny absolute impact. On low-traffic services, burn-rate rules can be noisy or statistically unreliable. Pair with:

- Minimum request-rate thresholds in the window.
- Synthetic probes.
- Dead-man/absence alerts.
- Absolute failure counts for low-volume journeys.
- Batch/event-level business completion indicators.

`clamp_min(..., 1e-9)` only prevents division by zero; **it does not replace minimum traffic gates** or distinguish "no requests" from "100% success".

### 20.2. Metric Names Are Examples, Not Guaranteed Built-Ins

Micrometer converts Java dots to underscores in Prometheus. Exact names depend on registry and config. Always verify exported metric names and labels before writing PromQL rules.

## 21. Example Business-Impact Alert Rule

Suppose the recording rules above track `create_order` against a 99.9% SLO.

```yaml
groups:
  - name: business-impact-alerts
    rules:
      - alert: OrderCreationFastErrorBudgetBurn
        expr: |
          (
            business:journey_error_ratio:5m{
              service="checkout",
              journey="create_order"
            } > 0.0144
          )
          and on (service, journey)
          (
            business:journey_error_ratio:1h{
              service="checkout",
              journey="create_order"
            } > 0.0144
          )
          and on (service, journey)
          (
            business:journey_requests:rate5m{
              service="checkout",
              journey="create_order"
            } > 0.1
          )
        for: 2m
        labels:
          severity: critical
          owning_team: checkout
          signal: business_impact
        annotations:
          summary: "Order creation is burning error budget rapidly"
          description: |
            create_order journey error ratio exceeded fast-burn threshold
            across short and long windows. Check checkout endpoint,
            Redis idempotency, database, and payment dependencies.
          runbook: "https://runbooks.example.internal/checkout/create-order"
```

`runbooks.example.internal` is an **illustrative placeholder URL**, not a verified live address.

### 21.1. Meaning of the Traffic Gate

The expression:

```promql
business:journey_requests:rate5m > 0.1
```

requires more than ~0.1 requests/s, roughly 30 requests over 5 minutes. This example filters out ultra-low-traffic windows; choose thresholds matching actual traffic and journey criticality.

For high-value payment flows, even a single correctness violation is critical, so **maintain dedicated invariant alerts** independent of traffic gates.

### 21.2. Avoiding Duplicate Pages

When multiple Redis-backed endpoints fail together, per-endpoint alerting can trigger dozens of pages. Group and route by service/journey and link to a Redis symptom dashboard for investigation.

Never disable business alerts just because a Redis infrastructure alert fired; business alerts confirm real user impact and recovery.

## 22. Example Alert for Redis Cache Fallback

Suppose the application exports:

```text
app_cache_access_total{
  cache="products",
  outcome="hit|miss|redis_error"
}
```

Detect rising Redis read errors:

```promql
sum(rate(app_cache_access_total{
  cache="products",
  outcome="redis_error"
}[5m]))
/
clamp_min(
  sum(rate(app_cache_access_total{
    cache="products"
  }[5m])),
  1e-9
)
> 0.05
```

When `app_cache_access_total` records `hit`/`miss`/`error` **once per attempted read**, this ratio is valid. If multiple outcomes are emitted per request, adjust the denominator to avoid double counting.

While Redis errors climb yet the DB fallback holds comfortably, treat this as a warning. Page if:

- Product page latency SLO burn climbs.
- DB pool approaches saturation as fallback rates rise.
- Business journey error rates climb.
- Cache invalidation failures cause unacceptable stale data.

Never enforce a universal "Redis cache error > 5% = critical" rule across all services without weighing impact and fallback capacity.

## 23. Alerting on Latency Distributions Instead of One Slow Request

If a Micrometer Timer exports Prometheus histogram buckets:

```text
app_business_request_duration_seconds_bucket
```

you can compute latency quantiles:

```promql
histogram_quantile(
  0.99,
  sum by (le, service, journey) (
    rate(app_business_request_duration_seconds_bucket[5m])
  )
)
```

Keep caveats in mind:

- Histograms must actually be enabled with buckets aligned to latency targets.
- `histogram_quantile` gives bucket-interpolated estimates.
- p99 under low traffic is noisy.
- A quantile crossing a threshold does not say **how many requests** violated the SLO.
- For latency SLOs, it is often cleaner to measure the fraction of requests **within vs. over the budget** using buckets or classification, then alert on error-budget burn.

For instance, if the SLO requires 99.9% of requests under 500 ms and the histogram includes `le="0.5"`:

```promql
1 -
(
  sum(rate(app_business_request_duration_seconds_bucket{
    journey="view_product",
    le="0.5"
  }[5m]))
  /
  clamp_min(
    sum(rate(app_business_request_duration_seconds_count{
      journey="view_product"
    }[5m])),
    1e-9
  )
)
```

This yields the fraction of requests exceeding 500 ms **within the selected series**, so filter cleanly by environment/service and account for failed requests per your latency SLO rules.

## 24. Alerting on Redis Streams from Event Deadlines

Suppose order confirmation events must complete within 60 seconds. Proposed metrics:

```text
app_stream_processing_delay_seconds_bucket{
  group="order-confirmations"
}
app_stream_uncompleted_events{
  group="order-confirmations"
}
app_stream_oldest_uncompleted_age_seconds{
  group="order-confirmations"
}
```

Here `oldest_uncompleted_age_seconds` is a **gauge computed by the application or reconciler** from business event sources, not emitted automatically by a standard Redis exporter.

Risk warning alert:

```yaml
- alert: OrderConfirmationDeadlineAtRisk
  expr: |
    app_stream_oldest_uncompleted_age_seconds{
      group="order-confirmations"
    } > 45
    and on (group)
    app_stream_uncompleted_events{
      group="order-confirmations"
    } > 0
  for: 2m
  labels:
    severity: warning
    owning_team: orders
  annotations:
    summary: "Order confirmation event nearing 60-second deadline"
```

With a 60-second deadline, a 45-second warning gives early notice. Yet `for: 2m` could delay firing **until after the SLA is already broken**, so tune `for` and thresholds to backlog growth rates and response speed.

For already-missed impact, define a separate rule:

```text
oldest_uncompleted_age > 60 seconds
OR overdue business events > 0
```

When even one overdue event matters, never bury it behind `for: 10m`.

### 24.1. Which Event Set Must the Gauge Cover?

An "oldest pending age" gauge reading only the PEL misses events **never delivered to the group**. A gauge reading only Redis group lag misses delivered entries awaiting `XACK`.

To measure end-to-end deadlines, the reconciler must track **all uncompleted events per the business contract**, not just one Redis queue state. That often requires event IDs, an outbox/status store, and independent reconciliation.

## 25. Detecting Stale Data Instead of Watching Only Pub/Sub Disconnects

Suppose an app uses Redis Pub/Sub to invalidate local caches across nodes.

```text
Product updated
    |
    v
Publisher sends invalidation
    |
    +--> Service A listener -> evicts local cache
    +--> Service B listener -> evicts local cache
```

If Service B disconnects briefly, it misses invalidations and keeps stale local entries.

A more meaningful alert:

```text
Data freshness violations > budget
```

How to implement:

1. Attach `version` or `updatedAt` to cached items.
2. Run a reconciliation check over sampled items or critical keys.
3. Measure the age difference between served values and the source of truth.
4. Page only when violations breach business tolerances.
5. Keep subscription disconnect/reconnect alerts as warning context for investigation.

Never invent a "PubSub lost messages" metric as if Redis tracked delivery receipts across all subscribers. If durable delivery is required, switch to Redis Streams or a durable broker instead of trying to patch Pub/Sub semantics with alerts.

## 26. Coordinating Redis Alerts with Downstream DB and APIs

When a Redis cache fails open, load shifts to the database:

```text
Redis error
    |
    v
Fallback to DB
    |
    +-- DB has headroom -> users unaffected
    |
    +-- DB pool nears saturation -> latency rises
    |
    +-- DB saturated -> user-visible errors
```

This is **dependency failure propagation**.

A well-coordinated alert set watches:

- Redis cache error rate.
- Fallback-to-DB rate.
- DB connection pool active and waiting counts.
- DB query latency.
- Product endpoint success and latency SLIs.
- HTTP worker/event-loop saturation.

If Redis errors while downstream holds ample headroom, opening a ticket to investigate Redis makes sense. Once the DB nears saturation, page **before** user errors spike.

### 26.1. Avoid Overly Rigid AND Conditions That Hide Outages

An overly strict alert:

```text
Redis error high
AND DB CPU high
AND HTTP 5xx high
```

can fail to fire if DB metrics drop out or another cause drives HTTP 5xx. Keep business SLO alerts **independent** of Redis metrics; use dependency metrics as context and separate risk alerts.

## 27. Alert Routing: Who Receives and Acts?

Every alert needs a clear owner.

Examples:

| Alert | Primary Owner | Secondary Owner |
|---|---|---|
| Checkout SLO burn | Checkout team | SRE + Payments |
| Session error spike | Identity team | Platform / Redis |
| Stream processing deadline | Event processor team | Redis platform |
| Redis disk nearly full | Infra / Redis platform | Dependent on-call services |
| Cache fallback + DB saturation | Product API team | Database + Redis |
| Sentinel quorum loss | Redis platform | SRE |
| Confirmed duplicate side effect | Owning business service + incident lead | Data / Payments |
| Redis exporter missing | Monitoring / Platform | Service on-call |

Never broadcast every Redis alert to every team. A shared Redis primary can affect many services, yet paging everyone simultaneously sparks alert storms and blurs ownership.

### 27.1. Route by Impact, Not Only by Instance

A label:

```text
redis_instance="redis-01"
```

helps during investigation, yet `redis-01` does not identify which journey is hurt.

Add routing labels:

```text
service="checkout"
journey="create_order"
owning_team="checkout"
severity="critical"
```

for business-impact alerts. For infrastructure alerts, route by `cluster`/`redis_owner` and link to a service dependency map.

## 28. Example Alertmanager Routing and Grouping

Condensed Alertmanager snippet illustrating structure only:

```yaml
route:
  receiver: platform-default
  group_by: ['alertname', 'environment', 'owning_team']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="critical"
        - owning_team="checkout"
      receiver: checkout-oncall

    - matchers:
        - severity="critical"
        - owning_team="identity"
      receiver: identity-oncall

    - matchers:
        - owning_team="redis-platform"
      receiver: redis-platform

receivers:
  - name: platform-default
    # Receiver integration must be configured for your organization.
  - name: checkout-oncall
  - name: identity-oncall
  - name: redis-platform
```

This is **not a complete ready-to-page configuration**. Wire real Slack, PagerDuty, webhook, or email integrations, manage credentials securely, and validate syntax against your Alertmanager version.

### 28.1. Grouping Must Not Conceal Distinct Impacts

Grouping solely by `redis_instance` can bundle several critical journeys into one vague alert. Grouping by individual Redis keys explodes notification volume.

Sensible grouping typically combines:

```text
environment + owning_team + alertname/service
```

and enriches notification text with the count of affected journeys or instances.

## 29. Alerts Must Carry Runbooks and Concrete Actions

An alert saying only:

```text
Redis connected clients high.
```

forces the responder to guess. A strong alert specifies:

- **Impact:** which user journey and how many requests/events are affected?
- **SLO:** which threshold and evaluation window are breached?
- **Scope:** environment, service, Redis cluster, and role involved.
- **Current symptoms:** error rates, latency, or backlog figures.
- **Possible causes:** candidate directions without asserting unproven claims.
- **Runbook:** exact commands, metrics, and dashboards to check.
- **Owner/escalation:** primary responder.
- **Safety guardrails:** actions forbidden without review.
- **Recovery criteria:** how to verify recovery.

Example page body:

```text
P2 — Order confirmation backlog exceeding deadline

Impact:
  37 events uncompleted past 60 seconds.
  User journey: order confirmation.

Symptoms:
  Worker completion throughput dropped.
  Redis Stream pending age rising.
  DB latency also rising.

Check:
  - Worker error logs + event IDs
  - XPENDING / XINFO GROUPS
  - Handler duration / DB pool usage
  - Consumer group ACK/reclaim state

Do not:
  - Bulk XACK pending entries just to clear the dashboard
  - XTRIM unprocessed stream entries
  - Retry non-idempotent side effects

Recovery:
  Overdue events drop back within budget.
  Completion success ratio returns to SLO.
```

## 30. Runbooks by Spring Data Redis Incident Category

### 30.1. Redis Connection Timeouts

Inspect:

```redis
INFO clients
INFO stats
INFO commandstats
SLOWLOG GET 20
```

Also check:

- Client command timeouts and connect timeouts.
- Pool borrow waiters, active, and idle counts.
- Reconnect counts.
- Redis CPU, memory, and network.
- Redis Sentinel/Cluster topology.
- DNS, TLS, and authentication errors.
- Request error ratio and business impact.

Never simply raise `max-active` or timeouts without finding the bottleneck.

### 30.2. Redis Memory/Eviction

Inspect:

```redis
INFO memory
INFO stats
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

Determine whether Redis holds disposable cache or critical state. For caches, eviction may be acceptable; for sessions or idempotency, eviction can break data guarantees.

Never change `maxmemory-policy` in production mid-incident without evaluating which keys become eligible for removal.

### 30.3. Stream Pending Backlog

Inspect:

```redis
XINFO STREAM stream:orders
XINFO GROUPS stream:orders
XINFO CONSUMERS stream:orders order-workers
XPENDING stream:orders order-workers
```

Correlate:

- Producer traffic.
- Handler success and error rates.
- `last-delivered-id`, lag, and pending counts.
- Oldest uncompleted business events.
- Claim and retry policy.
- Downstream DB/API latency.

Never ACK unprocessed messages just to zero out the pending count.

### 30.4. Persistence Failures

Inspect:

```redis
INFO persistence
INFO memory
```

along with disk bytes/inodes, fsync latency, container OOMs, and fork/COW pressure. If RDB/AOF failures threaten durability, follow backup/incident response runbooks—never disable persistence or delete active AOF files arbitrarily.

## 31. Avoiding Alert Fatigue and Alert Storms

If every Redis instance has 20 metric alerts and a 30-instance fleet hits a network blip, hundreds of pages fire at once.

Noise-reduction practices:

1. **Page on business impact or high-risk actionable conditions**.
2. Keep Redis infrastructure alerts as context, warnings, or tickets when user impact hasn't occurred.
3. Group alerts by shared root cause and scope.
4. Use inhibition when a confirmed broad root cause makes secondary symptom pages redundant.
5. Use `for` durations to filter brief spikes on appropriate metrics.
6. Add `absent()` or scrape-health rules so missing metrics don't look healthy.
7. Never use dynamic high-cardinality labels creating alerts per user or key.
8. Silence temporarily with explicit expiration during approved maintenance.
9. Review alerts periodically and tune or retire any that **never lead to action**.

### 31.1. Why Apply Inhibition Carefully?

During a Redis Cluster outage, suppressing 50 noisy `RedisCommandTimeout` warnings makes sense. Yet never automatically suppress **business SLO alerts**, because teams still need to know users are impacted and when service recovers.

Inhibition should quiet duplicate symptom noise—**never hide correctness failures or user impact**.

### 31.2. Choose `for` Based on Semantics

Different failures need different evaluation delays:

- Brief Redis CPU spike: longer `for` filters transient noise.
- Temporary quorum loss with healthy primary: wait briefly for stabilization.
- Confirmed duplicate payment: waiting 15 minutes for `for` makes no sense.
- Overdue Stream event: overly long `for` delays SLA response.
- Fast error-budget burn: typically pairs multi-window rates with a short `for`.

Never slap `for: 5m` onto every rule just because a template YAML used it.

## 32. Alerting on Missing Metrics or Scrape Failures

A dangerous failure mode: when Redis or an exporter disconnects, time series **vanish**, causing an expression like:

```promql
redis_connected_clients > 1000
```

to return no data. Zero firing alerts **does not mean the system is healthy**.

Alert on:

- Prometheus target `up == 0` for critical apps and exporters.
- Sharp drops in samples per scrape.
- Mandatory business metrics disappearing outside maintenance windows.
- Synthetic probes failing to run or report.
- Alertmanager notification pipeline failures.
- Recording rules failing or yielding empty results.

Example:

```promql
up{job="redis-exporter",environment="production"} == 0
```

Know the difference between:

```text
up == 0: target exists, yet scraping failed
absent(up{...}): no matching target time series exists at all
```

A service dropped from service discovery may stop emitting `up == 0`, so pair with `absent(...)` checks against expected targets or desired replicas.

## 33. Dashboards Structured from Business Journey to Dependency

An incident-friendly dashboard flows top-down:

```text
BUSINESS:
  Login SLO, Checkout SLO, Product latency,
  Event completion delay, confirmed correctness violations

DEPENDENCY:
  Cache miss/error/fallback,
  Lock/idempotency outcomes,
  Stream pending/lag/processing age,
  Pub/Sub listener state

REDIS:
  command latency, clients, CPU, memory,
  evictions, replication, persistence,
  Sentinel/Cluster topology

PLATFORM:
  DB connection pool, network RTT,
  container OOM, disk latency, JVM GC
```

Never dump 100 Redis `INFO` panels onto one page and leave the on-call engineer hunting for what affects users.

### 33.1. "Healthy" vs. "At Risk" Summary View

Example summary matrix:

| Business Capability | Availability/Quality | Redis Symptom | Recovery Status |
|---|---|---|---|
| Product reads | SLO met / breached | Cache errors, fallbacks | DB headroom |
| Login | SLO met / breached | Session errors | Session store health |
| Checkout | SLO met / breached | Lock/idempotency errors | Duplicate risk |
| Order notifications | Deadline met / breached | Stream backlog | Oldest pending / reclaim |
| Data freshness | Stale ratio | Pub/Sub / reconcile | Last successful sync |

This translates metrics into **operational decisions** rather than decorative charts.

## 34. Setting Thresholds from Baselines and Risk Budgets

Traditional static Redis thresholds:

```text
CPU > 80%
Memory > 80%
Pool active > 90%
Replication lag > 100 MB
```

do not tell you by themselves whether anything is actually endangered. A Redis running steady at 85% CPU with great p99 may simply be well utilized. A Redis at 20% CPU running a blocking single-threaded script causing tail latency is in trouble.

Threshold calibration workflow:

1. Define business SLOs and data integrity bounds.
2. Capture baselines under normal and peak traffic.
3. Run stress tests to identify saturation points.
4. Identify leading signals that shift **before** SLOs break.
5. Pick thresholds giving enough lead time to react.
6. Measure false positives and false negatives.
7. Refine thresholds after incidents and drills.
8. Account for maintenance windows, planned failovers, and seasonal traffic.

### 34.1. Forecasting Time to Exhaustion

If disk has 20 GiB free and AOF grows at 10 GiB/hour, alerting on `% disk used` may fire too late.

Estimate instead:

```text
time-to-exhaustion
    = free_capacity / recent_positive_growth_rate
```

This simple model must handle fluctuating growth rates, rewrites shrinking AOF size, reserved disk buffers, and missing metrics. Yet it captures the core idea: **alert when remaining time to react drops below the time required to remediate**, not merely when a gauge crosses an arbitrary percent.

## 35. Testing Alerts with Testcontainers and Fault Injection

Untested alert rules are only "alerts on paper". Test **metric emission**, **rule evaluation**, **routing**, and **runbooks**.

### 35.1. Redis Cache Unavailable

In an isolated test environment:

1. Start Spring Boot and Redis using Testcontainers.
2. Drive baseline requests generating cache hits and misses.
3. Cut Redis connectivity via a fault proxy or container pause/stop.
4. Verify `app_cache_access_total{outcome="redis_error"}` increments.
5. Verify DB fallback executes and emits its own metrics.
6. While business SLOs hold, confirm no false P1 alert fires.
7. When DB saturates under load, confirm the business-impact alert fires.
8. Restore Redis and confirm alerts resolve cleanly per recovery conditions.

### 35.2. Session Store Failure

1. Run a real session store with logged-in test users.
2. Simulate Redis unavailability or incompatible serializers.
3. Confirm authenticated request failures rise.
4. Confirm alerts route to Identity on-call.
5. Ensure errors are not misclassified as normal user logouts.

### 35.3. Stopped Stream Consumer

1. Publish events carrying `eventId` and creation timestamp.
2. Stop consumers while keeping the producer running.
3. Verify backlog and uncompleted event age climb.
4. Verify warning fires before deadline and critical fires after breach.
5. Restart consumers / trigger reclaim and confirm idempotent side effects.
6. Verify alert resolves once overdue counts fall back within contract.

### 35.4. Redis Failover

Against a Sentinel/Cluster topology in staging:

1. Stop the test primary or initiate a planned failover.
2. Observe reconnects and Redis command errors.
3. Measure business journey success and latency.
4. Confirm infrastructure events are captured.
5. Verify paging occurs if SLO burn crosses limits, and does not page if failover succeeds silently within policy.
6. Check recovery and any potential acknowledged-write loss per business semantics.

Never run data-destructive fault injection against shared production Redis without formal approval and a recovery plan.

## 36. Testing Prometheus Rules Before Deployment

YAML rules can pass syntax checks while targeting wrong labels or returning empty series. Verification workflow:

- Pull exact metric names from `/actuator/prometheus` or exporter endpoints.
- Verify labels and counter semantics.
- Run `promtool check rules` against rule files.
- Run `promtool test rules` with synthetic test fixtures to assert firing and recovery.
- Validate in staging with real traffic or synthetic samples.
- Test Alertmanager receivers, grouping, and inhibition.
- Test complete metric disappearance.
- Verify a fleet-wide fault across many pods does not produce 100 duplicate pages.
- Confirm alerts auto-resolve cleanly when SLIs recover instead of sticking on broken recording rules.

Essential test cases:

```text
Case 1: 0 errors, sufficient traffic -> does not fire
Case 2: 1-minute brief error blip    -> does not page falsely
Case 3: sustained outage             -> fires at expected severity
Case 4: zero traffic                 -> does not look like 100% success
Case 5: exporter down                -> observability-missing alert fires
Case 6: service rollout              -> does not spawn 100 duplicate alerts
Case 7: missing metric series        -> does not silently report healthy
```

For low-traffic workflows, use synthetic probes or batch completion metrics rather than relying solely on request-counter rates.

## 37. Evaluating Alerts Against Business Scenarios

Decisive scenarios:

### 37.1. Product Cache Fails Yet Users Still Access Pages

```text
Redis GET errors:            95%
Fallback success:            99.9%
Product page SLO:            still met
Database connection usage:   55%
```

Response: emit a degraded Redis cache warning to investigate and watch downstream headroom. Do not wake everyone with a P1 page.

### 37.2. Cache Failure Overloads the Database

```text
Redis GET errors:            95%
Fallback requests:           20x surge
Database connections:        98%
Product page p99:            breaching SLO
Product 5xx:                 surging
```

Response: page on the Product business SLO carrying Redis cache and DB saturation context. This is a user-impacting incident.

### 37.3. Stream Has Low Pending Yet a Critical Event Is Stuck

```text
Pending count:               1
Oldest uncompleted age:      25 minutes
Business deadline:           2 minutes
```

Response: alert on the overdue event despite a tiny pending count. Investigate the handler, ownership, ACK, and reclaim.

### 37.4. Redis CPU High Without User Impact

```text
Redis CPU:                   88%
GET p99:                     good
Business SLO:                met
Memory/disk headroom:        healthy
```

Response: monitor capacity trends and file an optimization ticket. Do not automatically page P1 solely for 88% CPU.

### 37.5. One Confirmed Duplicate Payment

```text
HTTP 5xx:                    0%
Redis healthcheck:           UP
Confirmed duplicate charge:  1
```

Response: trigger high-severity correctness escalation per policy; investigate idempotency and database/payment invariants. This proves **HTTP availability never covers data integrity**.

## 38. Post-Incident Alert Review

After any Redis-related incident, ask:

1. Did a business SLI alert fire first, or noisy Redis metric alerts?
2. Did alerts arrive early enough to limit impact?
3. Was anyone paged unnecessarily, or was the true owner missed?
4. Did dashboards clearly distinguish Redis errors, cache misses, and fallbacks?
5. Were duplicate or stale-data issues caught?
6. Did Redis exporter or application metrics drop out mid-incident?
7. Did any firing alert lead to zero action?
8. Did any runbook recommend dangerous steps like bulk ACKs, `FLUSHDB`, deleting AOF files, or unbounded retries?
9. Do we need a new SLI that tracks user journeys more faithfully?
10. Should thresholds, `for` windows, grouping, or deployment/rollback steps change?

The goal of review is not simply "fewer alerts", but **fewer useless alerts and faster detection of real critical failures**.

## 39. Implementation Checklist

### 39.1. Business/SLO

- [ ] Every Redis usage maps to an owner and associated business journey.
- [ ] Critical journeys have clear SLIs and SLOs.
- [ ] Availability, latency, freshness, and correctness are distinguished.
- [ ] Dedicated invariant alerts cover duplicates, locks, and data integrity.
- [ ] Valid requests and expected business outcomes are explicitly defined.
- [ ] RTO and RPO are defined wherever Redis holds durable-requirement state.

### 39.2. Application Metrics

- [ ] Redis cache `hit`, `miss`, `error`, and `fallback` are tracked separately.
- [ ] Redis client timeouts and command errors are tagged by role and operation.
- [ ] Session read, write, and deserialization errors are observable.
- [ ] Lock and idempotency outcomes are categorized.
- [ ] Streams track end-to-end processing delay and completion metrics.
- [ ] Pub/Sub tracks listener health and freshness/reconciliation where needed.
- [ ] Metrics omit user IDs, raw keys, and order IDs from labels.

### 39.3. Redis/Dependency Metrics

- [ ] Redis `INFO` clients, stats, memory, persistence, and replication are collected.
- [ ] Redis CPU, network, and command latencies are tracked.
- [ ] Spring app connection pool active/waiter counts and timeouts are tracked.
- [ ] DB and downstream saturation metrics exist wherever Redis backs a cache.
- [ ] Sentinel/Cluster topology health is monitored when using HA/sharding.
- [ ] Observability-missing alerts fire if exporters or scrapes fail.

### 39.4. Alert Policy

- [ ] Severity derives from business impact or actionable leading risk.
- [ ] Fast-burn and slow-burn rules cover applicable SLO journeys.
- [ ] Traffic gates or synthetic probes handle low-traffic periods.
- [ ] `for` windows never delay integrity or deadline alerts excessively.
- [ ] Grouping and inhibition curb noise without hiding business impact.
- [ ] Every alert specifies owner, escalation, runbook, and recovery criteria.
- [ ] Maintenance silences are timeboxed and governed.

### 39.5. Testing/Operations

- [ ] PromQL expressions are verified against actual emitted metric names.
- [ ] Rules are tested for firing, recovery, and missing data.
- [ ] Receivers and routing rules are verified end-to-end.
- [ ] Fault injection tests run in isolated environments.
- [ ] Redis failover/reconnect behavior is tested if used in production.
- [ ] Runbooks forbid data-destructive shortcuts.
- [ ] Post-incident reviews continuously refine SLIs and alerts.

## 40. Conclusion

**Business-impact-driven alerting** in Spring Data Redis starts by asking "which users or business workflows are impaired?" rather than "which Redis gauge crossed a threshold?".

Core principles:

1. **Define user journeys, SLIs, and SLOs first**, then map Redis dependencies and technical signals onto those journeys.
2. **Distinguish Redis as a cache from Redis holding critical state**; the same timeout carries very different severities across roles.
3. **Measure across three layers:** business outcomes, Spring Data Redis client behavior, and Redis server/topology health.
4. **Use error-budget burn rates for SLO-backed services** instead of paging on static CPU or memory numbers.
5. **Track correctness and freshness alongside availability**: duplicate payments, idempotency failures, lock violations, stale caches, and overdue Stream events can be critical even with zero HTTP 5xxs.
6. **Separate cache misses from dependency errors**; track fallbacks and downstream database pressure.
7. **Use Redis metrics for diagnosis and risk forecasting**: replication lag, AOF/RDB failures, memory headroom, pool waiters, blocked clients, and Cluster/Sentinel health.
8. **Prevent alert fatigue** through clear severities, grouping, careful inhibition, bounded labels, and actionable runbooks.
9. **Test alert rules and failure scenarios**, including vanished metrics, zero-traffic windows, and zero-impact failovers.
10. **Iterate after every incident** so alerts reach the right team, at the right moment, reflecting true business severity.

A successful alerting system is not the one with the most Redis graphs—it is the one that helps operators **catch genuine business regressions and risks early**, remediate safely, and verify recovery through real user experience and data integrity.
