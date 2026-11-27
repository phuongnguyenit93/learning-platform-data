# Testing Burst and Sustained Load

## 1. Problem: A Rate Limiter Passing Small Tests May Still Fail Under Load

In the **SPRING_INTEGRATION_PATTERN** module, Spring Integration connects Enterprise Integration Patterns (EIP) into loosely coupled message flows: **Gateway** receives requests, **Filter** validates, **Transformer** normalizes payloads, **Router** selects branches, **Service Activator** calls dependencies, **Splitter** splits work, and **Aggregator** combines results. When an external API has a quota or capacity limit, we place a **rate limiter** at the right point to prevent traffic from exceeding what is allowed.

A test that "sends 11 requests and sees the 11th blocked" only checks a single instant. It does not prove the limiter:

- Handles **bursts**: many requests arriving simultaneously, potentially from multiple threads or pods.
- Sustains the right rate under **sustained load**: a continuous request stream over several minutes or longer.
- Replenishes permits accurately over time without double-granting due to race conditions.
- Does not inflate latency unboundedly or hold threads waiting when permits run out.
- Properly distinguishes **requests rejected by the limiter**, **requests failing upstream**, and **deferred messages**.
- Does not multiply quota by pod count or let retries or Splitters silently exceed the limit.
- Still returns contractual outcomes and preserves **correlation IDs** across Gateway, Router, error channel, and Aggregator.

**Goal of this lesson:** design a test suite with clear assumptions, measurements, and pass/fail criteria for both burst and sustained load, then integrate the results into Spring Integration.

~~~mermaid
flowchart LR
    A[Load generator] --> B[Gateway / Consumer]
    B --> C[Filter / Router]
    C --> D{Rate limiter}
    D -->|ALLOW| E[Stock Client]
    D -->|REJECT| F[RATE_LIMITED outcome]
    E --> G[Reply / Aggregator]
    F --> G
    D -.-> H[Permit metrics]
    E -.-> I[Upstream calls / latency]
    G -.-> J[Gateway outcomes]
~~~

## 2. Defining Burst and Sustained Load Precisely

| Concept | Meaning | Example |
| --- | --- | --- |
| **Offered load** | Requests sent to the limiter, including rejected ones | 200 requests/second |
| **Admitted load** | Requests granted a permit | Roughly 50 requests/second after burst exhaustion |
| **Completed throughput** | Actual work completed downstream | Can be lower than admitted if upstream is slow/failing |
| **Burst** | Sharp traffic spike within a very short span | 100 requests nearly simultaneously |
| **Sustained load** | Prolonged, relatively steady traffic | 200 requests/second for 10 minutes |
| **Capacity** | Maximum permits accumulable in a token bucket model | 20 tokens |
| **Refill rate** | Speed at which tokens replenish over time | 10 tokens/second |
| **Rejection** | Refusing permission for a request | `RATE_LIMITED` or HTTP 429 |
| **Wait policy** | Wait for token, reject immediately, or defer processing | Timeout 0 or bounded wait |

**Burst tests** primarily exercise capacity, concurrent contention, and behavior when permits run dry. **Sustained-load tests** primarily exercise refills, average rate after the initial phase, stability under prolonged heavy load, and backlogs.

The two tests can diverge. A limiter granting 20 permits to 100 concurrent requests yet refilling 10x too fast every second will overrun the quota within minutes. Conversely, a limiter averaging 10 requests/second yet allowing a 1,000-request burst in one millisecond can knock out upstream immediately.

### 2.1. Do Not Confuse Rate Limiter with Bulkhead or Circuit Breaker

- **Rate limiter** caps the number of calls over time or per quota algorithm.
- **Bulkhead/concurrency limiter** caps the number of *concurrently running* calls.
- **Circuit breaker** cuts off new calls when a dependency fails/slows per policy.
- **Retry** retries transient errors and can emit additional physical calls.
- **Queue/backpressure** regulates work that cannot be processed immediately.

A 50 requests/second limiter can still accumulate thousands of concurrently active requests if each request holds a connection open for a long time. Therefore, sustained-load tests must also measure **in-flight concurrency**, latency, and pool/thread health, not only permit counts.

## 3. Choose the Algorithm Before Writing Assertions

Different algorithms have **different burst semantics**. You cannot write one test asserting "exactly 10 requests every second" and apply it to every limiter type.

| Algorithm | Model | What to test |
| --- | --- | --- |
| **Token bucket** | Tokens accumulate up to capacity, refilling over time | Initial burst, refill, and interval upper bound |
| **Leaky bucket / paced queue** | Smooths outbound emission rate | Output spacing, queue length, and waiting deadlines |
| **Fixed window** | Counts requests per calendar/clock window | Per-window cap; possible burst across two-window boundaries |
| **Sliding window** | Counts within a moving window | Cap over any fixed-length window, if implementation guarantees it |
| **Resilience4j RateLimiter by refresh cycle** | Grants permits per refresh period | Permits per cycle, permit waiting, and near-boundary behavior |

Resilience4j RateLimiter uses `limitForPeriod` and `limitRefreshPeriod`; do not automatically equate it with a continuously refilling token bucket. If choosing that library, test against **its per-refresh-period contract**. The token bucket examples below are standalone models meant to clarify the math and concurrency.

### 3.1. Token Bucket Upper Bound

Suppose the bucket starts full with capacity **C**, continuous refill **r tokens/second**, each request spends **1 token**, and there are no resets or mid-run config edits. Over an interval of length **T**, maximum granted attempts satisfy:

\[
A(T) \le C + rT.
\]

Because request counts are integers, you can use integer bounds matching your implementation's rounding. Over **5 seconds** with C = 20 and r = 10 tokens/second, total granted requests must not exceed **70** under the ideal model. Over **60 seconds**, the bound is **620**.

Note:

- This bound **includes initial burst tokens**; it does not claim every single second allows exactly r.
- Over short windows, requests can exceed r due to accumulated tokens.
- Any sliding window can start with at most C tokens, so long-term bounds still take the form C + rT.
- With floating-point arithmetic, boundary timestamps need small tolerances and defined rounding rules.
- If one request costs multiple tokens, measure **total cost**, not just request count.

For example, the system receives an offered load of **200 requests/second** for 60 seconds, with C = 20 and r = 10/second. Out of 12,000 incoming requests, granted calls under the ideal model **do not exceed 620** and rejections are **at least 11,380**, assuming each request asks for one permit, never waits indefinitely, and policies do not change. Actual grants may be lower if arrivals miss refill timings or the backend cannot keep up.

### 3.2. Sustained Rate After Burst Exhaustion

Once initial tokens are spent and requests remain dense enough, long-term admitted throughput must converge toward the refill rate **r**, without scaling up with offered load. For C = 20, r = 10/second:

- Within the first few milliseconds, up to 20 requests may be granted.
- After depleting tokens, roughly **100 ms** is needed for one new token.
- Under sufficient load, around 10 new requests per second can be granted over the long run.
- After an idle spell, the bucket can accumulate tokens again and permit another burst.

**Sustained-load tests do more than check total granted requests**: they must measure p95/p99 latency, CPU, queue age, upstream errors, and how many messages returned results versus were deferred.

## 4. Planning Tests Around Measurable Assumptions

A test plan should state at least:

| Parameter | Example | Rationale |
| --- | --- | --- |
| Limiter placement | Before `StockClient` | Every HTTP attempt is controlled |
| Quota scope | `stock.read:GLOBAL` | Multiple pods share one budget |
| Algorithm | Token bucket | Clear capacity/refill model |
| Capacity | 20 | Initial burst allowed |
| Refill | 10 tokens/second | Target long-term throughput |
| Cost | 1 token per HTTP attempt | Retries also require permits |
| Policy when empty | Reject immediately | Do not block waiting threads |
| Offered load | 200 requests/second | Exceeds allowance capacity |
| Duration | 60 seconds | Observe sustained behavior post-burst |
| Upstream behavior | Fake Stock API returns 200 in 10 ms | Isolate upstream failures from limiter |
| Pass criteria | Upper bound, no overshoot, clear outcomes | Verifiable assertions |

Whenever changing a parameter such as retries, pod count, upstream duration, or queue policy, re-verify **the unit of quota**. One Gateway request can trigger multiple outbound calls via a Splitter; never compare inbound requests directly against per-call permits while ignoring the fan-out factor.

### 4.1. Three Recommended Test Layers

1. **Deterministic unit tests:** use a fake clock to verify capacity, refill, boundaries, and thread safety without sleeping.
2. **Spring Integration tests:** send messages through Gateway/Filter/Router and verify `StockClient` is not called when `RATE_LIMITED`, preserving correlation and outcomes.
3. **Load/distributed tests:** use an independent load generator, multiple processes/pods, and the real shared quota backend or limiter implementation; measure throughput, latency, and errors under burst/sustained load.

Single-JVM unit tests **do not prove cluster-wide quotas**, even when many threads call one shared object.

## 5. Building a Clock-Controlled Token Bucket for Learning and Testing

To keep unit tests independent of thread schedulers, we use a simple token bucket accepting a **`LongSupplier`** as a nanosecond monotonic time source. Tests update an `AtomicLong` instead of waiting in real time.

**This is a single-JVM illustrative implementation**, not a distributed limiter; it lacks policy versioning/hot reload, lacks persistence, and does not replace a battle-tested production library.

~~~java
public final class DeterministicTokenBucket {

    private final int capacity;
    private final double refillPerSecond;
    private final LongSupplier tickerNanos;

    private double tokens;
    private long lastNanos;

    public DeterministicTokenBucket(
            int capacity,
            double refillPerSecond,
            LongSupplier tickerNanos
    ) {
        if (capacity <= 0 || !Double.isFinite(refillPerSecond)
                || refillPerSecond <= 0 || tickerNanos == null) {
            throw new IllegalArgumentException("Invalid bucket config");
        }
        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
        this.tickerNanos = tickerNanos;
        this.tokens = capacity; // Bucket starts full.
        this.lastNanos = tickerNanos.getAsLong();
    }

    public synchronized boolean tryAcquire() {
        long now = tickerNanos.getAsLong();

        if (now > lastNanos) {
            double elapsedSeconds =
                    (now - lastNanos) / 1_000_000_000.0;
            tokens = Math.min(
                    capacity,
                    tokens + elapsedSeconds * refillPerSecond
            );
            lastNanos = now;
        }

        if (tokens < 1.0) {
            return false;
        }

        tokens -= 1.0;
        return true;
    }
}
~~~

Explanation:

- **`synchronized`** ensures two threads in the same JVM never deduct the same token concurrently.
- **`tickerNanos`** can use **`System::nanoTime`** in normal execution and **`AtomicLong::get`** in tests. This clock measures elapsed intervals, not wall-clock timestamps for logs.
- Refill runs only when `now` exceeds `lastNanos`, avoiding negative elapsed time if a fake clock steps backward.
- **`Math.min(capacity, ...)`** prevents tokens from accumulating past burst capacity.
- Uses **`double`** for simplicity; production requires stricter arithmetic, rounding, overflow, and deadline rules.
- Starting with a full bucket is a **policy choice**. Some systems start empty or warm up to prevent startup bursts.

With a fake clock, start from a fixed value and only advance forward. Do not use **`System.currentTimeMillis`** to measure elapsed time in short-interval algorithms because wall clocks can jump.

## 6. Unit Testing a Burst at the Same Timestamp

With capacity = 5 and refill = 2 tokens/second, while the clock has not advanced:

- The first five `tryAcquire` calls must succeed.
- The sixth call must be rejected.
- After 500 ms, exactly one token is replenished.
- With no further elapsed time, the call right after the sixth permit is rejected again.

~~~java
@Test
void burstConsumesCapacityAndThenRejects() {
    AtomicLong nanos = new AtomicLong(0);
    DeterministicTokenBucket bucket =
            new DeterministicTokenBucket(
                    5, 2.0, nanos::get
            );

    for (int i = 0; i < 5; i++) {
        assertTrue(bucket.tryAcquire());
    }
    assertFalse(bucket.tryAcquire());

    nanos.addAndGet(500_000_000L); // 500 ms, exactly 1 token.
    assertTrue(bucket.tryAcquire());
    assertFalse(bucket.tryAcquire());
}
~~~

With zero sleeps, the test is rock-solid. It verifies **capacity, post-burst rejection, and refill**, though not yet concurrency.

### 6.1. 40 Threads Contending for 10 Permits

~~~java
@Test
void concurrentBurstNeverGrantsMoreThanCapacity()
        throws Exception {
    AtomicLong nanos = new AtomicLong(0);
    DeterministicTokenBucket bucket =
            new DeterministicTokenBucket(10, 1.0, nanos::get);

    ExecutorService pool = Executors.newFixedThreadPool(40);
    CountDownLatch ready = new CountDownLatch(40);
    CountDownLatch start = new CountDownLatch(1);
    List<Future<Boolean>> futures = new ArrayList<>();

    try {
        for (int i = 0; i < 40; i++) {
            futures.add(pool.submit(() -> {
                ready.countDown();
                start.await();
                return bucket.tryAcquire();
            }));
        }

        assertTrue(ready.await(5, TimeUnit.SECONDS));
        start.countDown();

        int granted = 0;
        for (Future<Boolean> future : futures) {
            if (future.get()) {
                granted++;
            }
        }

        assertEquals(10, granted);
        assertEquals(30, futures.size() - granted);
    } finally {
        start.countDown();
        pool.shutdownNow();
    }
}
~~~

**Observation:** 40 threads contend simultaneously for a full 10-token bucket; because the fake clock stays fixed, **only 10 calls receive ALLOW**. If the implementation used non-atomic "read tokens → check → write tokens," two threads could claim the same token and cause an overshoot.

This tests thread safety **within one process**, not whether Redis/scripts/databases or live pods share the same counter.

## 7. Unit Testing Sustained Load with Fake Time

After exhausting the initial burst, a limiter refilling at 10 tokens/second must grant at most one token every 100 ms. We can simulate **60 seconds of sustained load** in a single sleep-free test.

~~~java
@Test
void sustainedLoadConvergesToRefillRate() {
    AtomicLong nanos = new AtomicLong(0);
    DeterministicTokenBucket bucket =
            new DeterministicTokenBucket(10, 10.0, nanos::get);

    // Drain initial burst to measure refill behavior alone.
    for (int i = 0; i < 10; i++) {
        assertTrue(bucket.tryAcquire());
    }
    assertFalse(bucket.tryAcquire());

    int allowed = 0;
    int rejected = 0;

    for (int step = 0; step < 600; step++) {
        nanos.addAndGet(100_000_000L); // 100 ms.
        if (bucket.tryAcquire()) {
            allowed++;
        }

        // Another request arrives at the exact same instant.
        if (!bucket.tryAcquire()) {
            rejected++;
        }
    }

    assertEquals(600, allowed);  // 60 s x 10 tokens/s.
    assertEquals(600, rejected); // No tokens accumulated past capacity.
}
~~~

**Test limitation:** time is synthetic with zero network/scheduler overhead. Thus the test proves **the refill algorithm**, not that the system can sustain 10 HTTP calls/second when upstream slows down.

A real sustained-load test should measure:

- **Offered RPS** from an independent load generator.
- **Allowed RPS**, **rejected RPS**, and **outbound RPS**.
- **Gateway and Stock Client p50/p95/p99 latency**.
- **Thread count, CPU, memory, connection pool, and in-flight calls**.
- **Queue depth/oldest age** if requests are deferred.
- **Error codes and fallback outcomes** so accepted requests are not confused with successful transactions.

## 8. Testing Resilience4j RateLimiter: Refresh-Period Semantics

When using **Resilience4j RateLimiter** instead of a custom token bucket, a typical configuration is:

~~~java
RateLimiterConfig config = RateLimiterConfig.custom()
        .limitForPeriod(10)
        .limitRefreshPeriod(Duration.ofSeconds(1))
        .timeoutDuration(Duration.ZERO)
        .build();

RateLimiter limiter = RateLimiter.of("stock-read", config);
~~~

In this example, the limiter grants permits per **refresh cycle** and does not wait when empty since `timeoutDuration` is zero. Do not impose continuous 100 ms token-bucket refill assertions on this implementation. Calls straddling a refresh-period boundary can admit multiple requests within a very short sliding window.

### 8.1. Simple Test for a Very Long Cycle

You can configure a test with a refresh period much longer than test execution to verify bursts before any refresh:

~~~java
@Test
void resilienceLimiterRejectsAfterPeriodPermits() {
    RateLimiterConfig config = RateLimiterConfig.custom()
            .limitForPeriod(3)
            .limitRefreshPeriod(Duration.ofHours(1))
            .timeoutDuration(Duration.ZERO)
            .build();

    RateLimiter limiter =
            RateLimiter.of("burst-test", config);

    int allowed = 0;
    for (int i = 0; i < 10; i++) {
        if (limiter.acquirePermission()) {
            allowed++;
        }
    }

    assertEquals(3, allowed);
}
~~~

A one-hour refresh period serves only to test **bursts within a very short span**; it is not a runtime config. For tests crossing refresh boundaries, prefer clock/timing mechanisms the implementation can control, or integration tests with time tolerances and sufficient sample counts. Never rely on a fixed sleep call to assert millisecond-exact timing.

**Verify the actual Resilience4j API and version** when bringing code into a project. These examples use common Java APIs: `RateLimiterConfig`, `RateLimiter.of`, and `acquirePermission`.

## 9. Placing the Limiter at the Right Call Site in Spring Integration

When the provider counts quota **per HTTP attempt**, the rate limiter belongs **right next to `StockClient`**, after Filter/Transformer/Router and before the outbound call. If a Gateway or Splitter creates multiple branches, each branch uses the quota key matching its dependency.

### 9.1. Request and Outcome Contracts

~~~java
public record StockQuery(String sku, String correlationId) {}

public record StockOutcome(
        String sku,
        String correlationId,
        String status,
        Integer availableUnits
) {}

public interface StockClient {
    int availableUnits(String sku);
}
~~~

With outcomes:

- **FRESH**: received fresh data from `StockClient`.
- **RATE_LIMITED**: limiter denied a permit; `StockClient` was never called.
- **UNAVAILABLE**: dependency or quota provider errored; cannot return a reliable result.

Never return **`availableUnits = 0`** when `RATE_LIMITED`; 0 means "out of stock" in business terms, which differs from failing to check inventory.

### 9.2. Spring Integration Java DSL

~~~java
@MessagingGateway(defaultRequestChannel = "stock.lookup.requests")
public interface StockGateway {
    StockOutcome lookup(StockQuery query);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockRateLimiterConfig {

    @Bean
    public RateLimiter stockReadLimiter() {
        RateLimiterConfig config = RateLimiterConfig.custom()
                .limitForPeriod(10)
                .limitRefreshPeriod(Duration.ofSeconds(1))
                .timeoutDuration(Duration.ZERO)
                .build();
        return RateLimiter.of("stock-read", config);
    }

    @Bean
    public IntegrationFlow stockLookupFlow(
            StockClient client,
            RateLimiter stockReadLimiter
    ) {
        return IntegrationFlow.from("stock.lookup.requests")
                .handle(StockQuery.class, (query, headers) -> {
                    if (!stockReadLimiter.acquirePermission()) {
                        return new StockOutcome(
                                query.sku(),
                                query.correlationId(),
                                "RATE_LIMITED",
                                null
                        );
                    }

                    int units = client.availableUnits(query.sku());

                    return new StockOutcome(
                            query.sku(),
                            query.correlationId(),
                            "FRESH",
                            units
                    );
                })
                .get();
    }
}
~~~

The example uses a **single-process** limiter, suited for demonstrating EIP and single-instance testing. Never use it to promise **10 requests/second cluster-wide** when multiple independent pods exist. To test cluster-wide quotas, replace the acquire call with a **`SharedRateGate`** performing atomic operations on a shared backend, and test across multiple processes.

This flow returns `RATE_LIMITED` merely as an **outcome**. If ingress is a REST API, the boundary can map it to HTTP **429** and `Retry-After` per contract. Spring Integration does not automatically turn a record with status `RATE_LIMITED` into HTTP status 429.

## 10. Gateway Integration Test: When Blocked, Never Call the Client

The goal is testing message flow behavior, not just a standalone `RateLimiter` object.

Example with a Spring Boot/Spring Integration test context having a registered Gateway and mocked `StockClient`:

~~~java
@Test
void gatewayReturnsRateLimitedWithoutExtraClientCalls() {
    // Isolated test fixture using a limiter with exactly 2 permits,
    // without waiting for new tokens during the test window.
    when(stockClient.availableUnits("SKU-1"))
            .thenReturn(7);

    StockQuery query = new StockQuery("SKU-1", "corr-101");

    StockOutcome first = gateway.lookup(query);
    StockOutcome second = gateway.lookup(query);
    StockOutcome third = gateway.lookup(query);

    assertEquals("FRESH", first.status());
    assertEquals("FRESH", second.status());
    assertEquals("RATE_LIMITED", third.status());

    assertNull(third.availableUnits());
    assertEquals("corr-101", third.correlationId());
    verify(stockClient, times(2))
            .availableUnits("SKU-1");
}
~~~

**Mandatory fixture:** in the test context, configure a limiter capped at **2 permits** with a sufficiently long refresh period, isolating the test's limiter instance from other tests. Leaving a default 10-permit limiter or sharing a singleton across tests can make the assertions fail due to non-deterministic fixtures rather than broken flows.

Additional tests to include:

1. Filter drops invalid SKUs **before the limiter**.
2. Router sending to the Pricing branch does not spend Stock permits.
3. Gateway reply/correlation is accurate for both `FRESH` and `RATE_LIMITED`.
4. When `StockClient` throws a timeout after acquiring a permit, physical quota was spent; error path must be explicit.
5. When one Splitter branch is rate-limited, the Aggregator does not hang forever missing a reply.

## 11. Realistic Burst Load Testing: Avoiding Boundary Errors and Choosing Load Tools

For a token bucket with C = 20, r = 10 tokens/second, a burst-load test should include at least two waves:

**Wave A — at the same logical instant:** send 100 concurrent requests into a bucket starting full. With zero elapsed time and one token per request, at most **20 ALLOW** and at least **80 REJECT**.

**Wave B — after draining tokens:** let 500 ms elapse. At 10/s refill, **5 new tokens** become available if the bucket was at 0. If no tokens were spent before the second wave, at most 5 new requests are permitted and the rest are rejected.

With a real load generator, 100 network requests cannot arrive at **the exact same nanosecond**. Refills can occur while requests arrive, so **never assert an exact count of 20** for a test spanning hundreds of milliseconds; compare against bounds based on **actual elapsed time**, sensible tolerances, and limiter-side timestamps if needed.

### 11.1. Choosing a Load Generator

You can use k6, Gatling, JMeter, or an internal tool; what matters is not the tool's name, but **how it emits requests**.

- **Open-loop:** emits requests on a schedule at a target arrival rate without slowing down when the server slows down. Useful for testing limiters under overload.
- **Closed-loop:** each virtual user sends the next request only after receiving a response. As latency rises, offered load **drops automatically**, making the limiter look like it passed a sustained-load test even though it was under-driven.

When testing overload, use open-loop or at least track **actual arrival rate** and requests skipped by the load generator due to self-overload. **Coordinated omission** can make latency and saturation look artificially rosy if the driver stops generating requests whenever the target slows down.

Separate **the load generator** from the machine running the application when accuracy matters; CPU contention between them skews measurements.

### 11.2. Multi-Tenant Bursts

If quotas exist per tenant, send concurrent bursts from tenants A and B:

- If A and B have independent buckets, A running out of tokens must not reject B.
- If both tenants belong to the same quota group, total permits must stay within the shared bucket's bound.
- Tenant context must be authenticated; requests spoofing tenants must not spawn fresh buckets to bypass quotas.

Tests must verify **bucket scope**, not just total 429 responses.

## 12. Sustained-Load Test: Holding Load Over Time and Measuring Full Lifecycle

An illustrative load test plan in test/staging environments:

| Phase | Duration | Offered load | Purpose |
| --- | --- | --- | --- |
| Warmup | 30 seconds | 5 req/s | Stabilize JVM, connection pools, and monitoring |
| Burst | 1–2 seconds | 200 req/s | Verify capacity, rejections, and races |
| Sustained | 5 minutes | 200 req/s | Verify refill, throughput, latency, and leaks |
| Recovery | 1 minute | 5 req/s | Check whether backlog drains and normalizes |
| Idle then burst again | 30s idle + burst | 200 req/s | Verify bucket re-accumulates after idle |

Durations are design exercises and should be tuned to SLAs and staging capacity. **Never send unthrottled load against production or third-party APIs**; use fake dependencies or authorized test environments.

### 12.1. Sustained-Load Assertions

For a token bucket with C = 20, r = 10/s, under sufficient load lasting **T = 300 seconds**, maximum total admitted calls are roughly **20 + 10 × 300 = 3,020** if starting full with no resets. To check stability, evaluate over sub-intervals:

- Total ALLOW obeys the bucket's **upper bound** over the entire span.
- Once the initial burst drains, **average admitted rate** converges toward 10/s rather than rising with the 200/s offered rate.
- **Rejected rate** rises proportionally with overload; no silent message drops.
- **Outbound calls** do not exceed granted permits if each attempt acquires a permit.
- **Gateway p95/p99** on the `RATE_LIMITED` path does not grow unboundedly from blocked threads.
- **CPU, memory, threads, heap, and connection pools** do not grow without bound.
- If queuing/deferring, **queue depth/age** follows cap policies rather than accumulating endlessly.
- When the fake upstream slows down, the limiter is not mistaken for a bulkhead.

Watch **measurement windows**: if warmup already consumed tokens, you can no longer assume "full bucket at the start of sustained." Use a controlled reset point or compute bounds from actual starting state without double-counting the initial burst.

### 12.2. Why Not Assert Exactly 10 Requests Every Second?

A token bucket allows tokens to accumulate up to capacity; requests can also land right before or after window boundaries. One second may show more than 10 ALLOWs using prior accumulated tokens, while another second shows fewer. Asserting "every second must equal exactly 10" will fail spuriously.

Instead, check **the model's upper bound across windows** and the long-term average rate. If upstream requires a hard cap per rolling window, switch to an algorithm enforcing that contract and write matching assertions.

## 13. Multi-Pod Load Testing: Total Quota Must Not Scale by Instance Count

Suppose the cluster-wide quota is **120 permits/second**. Three pods each holding a local 120 permits/second configuration can emit 360 permits/second total. Single-pod tests miss this bug.

~~~mermaid
flowchart LR
    A[Load generator] --> B[Load balancer]
    B --> C[Pod 1]
    B --> D[Pod 2]
    B --> E[Pod 3]
    C --> F[Shared atomic bucket]
    D --> F
    E --> F
    F --> G[Fake upstream]
~~~

**Mandatory distributed test:**

1. Use **multiple real processes/pods**, not merely multiple threads in one JVM.
2. Every pod targets **the same authoritative bucket key**; state is never created per pod.
3. Start with a bucket holding **120 permits**, pausing refills or using a controlled-refill window.
4. Send more than **120 concurrent requests** across at least three pods.
5. Verify **total ALLOW is at most 120**, even when every pod receives heavy traffic.
6. Scale up to four or six pods and verify total quota **does not multiply**.
7. Test the real Redis/database backend under races, timeouts, and failover.

If **global + per-tenant quotas** coexist, test both limits. When deducting from multiple buckets, operations must be atomic per contract; sequential deductions can skew budgets on mid-way failures.

**Guarantee note:** a shared atomic store can grant permits accurately per key on a single node, yet failover/replication and network partitions can lose updates. If never exceeding quota under any failure is required, verify the backend's HA/consistency guarantees rather than testing concurrency only while the cluster is healthy.

## 14. Interactions with Retry, Circuit Breaker, Queue, and Aggregator

### 14.1. Retries Increase Permit Demand

If a Gateway request retries three times and the provider counts quota per **HTTP attempt**, the limiter must grant a token for **each attempt**. Placing the gate outside Retry can let one permit cover three physical calls, exceeding the provider's quota.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Bounded Retry]
    B --> C[Rate limiter]
    C -->|ALLOW| D[StockClient]
    C -->|REJECT| E[Do not retry immediately]
~~~

A `RATE_LIMITED` failure should not be caught by Retry and looped continuously in the same handler. For async messages, defer to a later schedule if TTL and attempt budget allow.

Tests should cover:

- A request taking 1, 2, or 3 physical attempts.
- Permit grants matching actual outbound calls.
- When a permit is denied, `StockClient` **is not called** on that attempt.
- No infinite retry loops on token exhaustion.
- Write operations carry an **idempotency key** rather than blindly re-sending on lost responses.

### 14.2. Rate Limiter Must Not Poison the Circuit Breaker

A limiter `REJECTED` is a **quota decision**, not the Stock API failing. Wrapping `RATE_LIMITED` and `UPSTREAM_TIMEOUT` in the same generic exception and feeding both into a breaker can trip the breaker `OPEN` even when the dependency is healthy.

Separate:

- **`RATE_LIMITED`**: permit denied; usually bypasses client/breaker so it does not count as an upstream failure.
- **`BREAKER_REJECTED`**: circuit refuses calls due to dependency health.
- **`UPSTREAM_TIMEOUT`**: client was invoked and failed.
- **`BULKHEAD_FULL`**: concurrency slots exhausted.

The ordering of `RateLimiter`, `CircuitBreaker`, and `Retry` produces different effects. Document the exact order and verify using **permit counters + remote-call counters + exception categories**.

### 14.3. Gateway, Filter, Router, and Aggregator

- **Filter** should drop invalid requests before the limiter so validation errors never consume outbound quota.
- **Router** routes messages to the right dependency/operation bucket; avoid unintentionally sharing buckets between Stock and Pricing.
- **Gateway** must receive a contractual `RATE_LIMITED` result or exception; never hang callers indefinitely.
- **Splitter** can fan out one message into many outbound calls; each branch acquires permits in the right quota unit.
- **Aggregator** must receive a `RATE_LIMITED` outcome for blocked branches, or have group timeouts/partial results; never wait forever for missing replies.
- **Error channel** must distinguish normal rejections from technical exceptions. Never assume a limiter returning `false` automatically generates an `ErrorMessage`.
- **Correlation ID** and sequence metadata must survive rejections/fallbacks for message tracing.

If a request is deferred to a durable queue, include `nextAttemptAt`, max attempts, TTL, DLQ, backpressure, and idempotency so the queue does not grow unboundedly when sustained load exceeds permit capacity.

## 15. Complete Test Matrix

| Scenario | Pass criterion |
| --- | --- |
| Bucket starts full | First C permits granted; next request rejected at same timestamp |
| Bucket starts empty | Permits granted only after sufficient refill |
| Empty tokens and static clock | No extra tokens granted |
| Refill after 500 ms | New tokens match rate and rounding rules |
| Long idle spell | Tokens never exceed capacity |
| 40-thread burst in 1 JVM | Grants never exceed capacity; no races |
| Burst crossing refresh boundary | Assertions match algorithm; do not apply token-bucket formulas to fixed windows |
| Sustained offered rate above quota | Long-term admitted rate does not climb with offered rate |
| Sustained offered rate below quota | No spurious rejections while permits exist |
| Multi-minute sustained load | CPU/memory/threads/queues stay bounded |
| Multiple pods, same bucket | Total ALLOW does not scale with pod count |
| Global and tenant quotas coexist | Each limit enforced within its scope |
| Unauthenticated tenant | Cannot forge new keys to bypass quota |
| Mid-run quota reduction | No overshoot beyond migration guarantee |
| Retry on outbound timeout | Each HTTP attempt spends permits per policy |
| Limiter rejection | Client not called; no immediate retry |
| Circuit breaker OPEN | `RATE_LIMITED` not counted as upstream failure |
| Splitter with a blocked branch | Aggregator returns partial/error cleanly without hanging |
| Shared quota store timeout | Fail-open/fail-closed/defer per policy, with metrics |
| Lost acquire response | Ambiguous state handled safely without double-spending tokens |
| Backend failover | Quota guarantees match design, verified with dedicated tests |
| Autoscaling | Total quota and metrics stay accurate as pod count changes |
| Metrics/tracing | Allowed, rejected, remote calls, correlation, and outcomes reconcile |

Never declare "tests pass" merely because total 200 responses look high. For a limiter, **a policy-compliant `REJECTED` is also a valid outcome**. Pass/fail must be judged against defined quotas, fairness, latency, and degradation bounds.

## 16. Metrics and Interpreting Load Test Results

| Metric | Meaning |
| --- | --- |
| **`attempted_total` / `offered_rps`** | Total requests entering the limiter |
| **`allowed_total` / `admitted_rps`** | Total permits granted |
| **`rejected_total` / `rejected_rps`** | Total requests rejected due to quota |
| **`client_calls_total`** | Actual HTTP calls executed |
| **`gateway_latency` p50/p95/p99** | Caller-observed response time |
| **`rate_gate_latency`** | Cost of permit decision |
| **`in_flight` / connection pool usage** | Concurrency, avoiding confusion with rate |
| **`retry_attempts`** | Extra calls generated by Retry |
| **`fallback_total`** | Cached/unavailable responses, not fresh |
| **`queue_depth` / `oldest_message_age`** | Backlog when deferring |
| **`aggregator_expired_groups`** | `RATE_LIMITED` branches causing missing replies |
| **`quota_store_errors` / `config_version`** | Health of backend and rollout |

Useful identities to check within a well-defined scope:

~~~text
attempted = allowed + rejected + other_terminal_decisions

client_calls <= allowed
    (when one ALLOW authorizes at most one outbound attempt)

completed_success <= client_calls
    (when measuring actual upstream successes)
~~~

These identities apply over **the same measurement interval, same bucket, and same counting unit**, accounting for in-flight requests at boundaries. When counters are scraped asynchronously across pods, brief scrape-lag skew can occur; do not immediately blame the algorithm from a millisecond-skewed snapshot.

**Do not put request IDs, SKUs, or correlation IDs in metric tags** when cardinality is huge. Use stable tags such as **limiter name**, **operation**, **tenant group**, **region**, and **outcome**. Keep detailed IDs inside access-controlled logs/traces.

### 16.1. Common Symptoms of Misconfiguration

- **Burst passes yet sustained exceeds quota:** refill math is wrong or each pod uses a local bucket.
- **Sustained passes yet bursts overload upstream:** capacity is too high or bulkhead is missing.
- **RPS looks fine because load generator slowed down:** compare target arrival rate against observed offered rate.
- **High allowed yet low client calls:** requests stuck pending, served from cache/fallback, or failing in the flow before the client.
- **Fast rejects yet very high Gateway latency:** retries, queues, or Aggregator are still waiting.
- **Many upstream HTTP 429s despite few local rejects:** wrong quota key, retries bypassing the gate, or external traffic sharing the upstream quota.
- **One tenant consumes nearly all permits:** missing quota partitioning/fairness or overly broad shared scope.

## 17. Hands-On Checklist

- [ ] Document scope, algorithm, capacity, refill/refresh period, and cost per request.
- [ ] Distinguish token-bucket, fixed-window, and Resilience4j refresh-cycle semantics.
- [ ] Unit test bursts and refills with a fake clock; avoid long sleeps.
- [ ] Test concurrent races so empty buckets never grant past capacity.
- [ ] Drive offered load above quota in sustained tests; measure actual arrival rate.
- [ ] Track admitted, rejected, completed throughput, and p95/p99 latency.
- [ ] Verify burst caps and long-term upper bounds; do not assert every second equals r.
- [ ] Monitor CPU, memory, threads, connection pools, queue depth, and recovery.
- [ ] Integration test Gateway/Filter/Router alongside a `StockClient` call counter.
- [ ] Test Retry, Circuit Breaker, timeouts, and `RATE_LIMITED` outcomes separately.
- [ ] Ensure Splitter/Aggregator preserve outcomes/correlation and handle group timeouts for blocked branches.
- [ ] Test multiple pods against a real shared backend; do not mistake thread tests for distributed tests.
- [ ] Test tenant/global quotas, config updates, autoscaling, and backend outages.
- [ ] Never unleash uncontrolled load against production or external providers.
- [ ] Ensure dashboards distinguish `ALLOW`/`REJECT`/`ERROR`, client calls, and latency per scope.

**Testing burst and sustained load** validates two distinct capabilities of a rate limiter: **absorbing instantaneous load spikes** and **holding long-term throughput within bounds**. Combining synthetic-clock tests for the algorithm, integration tests across Spring Integration Gateway/Router/Filter, and multi-pod load tests with full telemetry proves the limiter protects dependencies as intended without dropping messages, masking retry bugs, or stalling Aggregators on rejection.
