# Load Testing by Access Pattern Instead of Single-Command Microbenchmarks

Redis is very fast for many simple operations, yet **a fast `GET` in a microbenchmark does not mean an entire Spring Data Redis application will hold up under real load**. A business request may read multiple keys, update a Hash, set TTLs, execute a Lua script, decode JSON, query a database on cache misses, and dispatch async work. During peak hours, requests also contend for connections, CPU, network bandwidth, and frequently accessed keys.

Therefore, Redis performance testing must start from the **actual access pattern / workload**: who calls it, which commands run, the read–write ratio, key popularity skew, payload sizes, hit/miss and expiration rates, traffic bursts, and how many Redis round trips each request triggers.

This lesson explains how to design meaningful load tests for **Spring Data Redis**: modeling representative workloads, seeding test data, generating load with the right model, measuring throughput and latency across layers, diagnosing bottlenecks, comparing alternatives, and avoiding misleading conclusions from single-command microbenchmarks.

> Guiding principle: **a single-command benchmark measures only that command under benchmark conditions; an access-pattern benchmark measures how the system behaves when the workload resembles production**. Both are useful, yet they answer different questions.

## 1. What Does a Single-Command Benchmark Answer?

Redis includes `redis-benchmark` to generate commands and measure performance in a specific setup. For example:

~~~bash
redis-benchmark -h 127.0.0.1 -p 6379 -t get,set -n 100000 -c 50 -d 256
~~~

This runs GET/SET commands with a chosen request count, concurrency, and payload size. It helps when you need to:

- Verify a Redis node responds normally under baseline conditions.
- Compare the impact of networking, TLS, or infrastructure changes in controlled runs.
- Estimate relative limits of a command family at a given connection count.
- Catch severely misconfigured Redis or client settings even under trivial workloads.

However, the output **does not represent Spring Boot service throughput**. A real HTTP request may traverse:

~~~text
                     HTTP request / Scheduled job
                                  |
                                  v
                     Controller / Business logic
                                  |
                     Serializer / JSON mapping
                                  |
                                  v
                       Spring Data Redis API
                                  |
                       Lettuce / Jedis driver
                                  |
                     Connection / Queue / Network
                                  |
                                  v
                            Redis server
                         /      |       \
                       GET    HGETALL   SET EX
                         \      |       /
                                  |
                        Deserialize / Aggregation
                                  |
                     Cache miss? Call origin?
                                  |
                                  v
                            HTTP response
~~~

A direct `GET` benchmark skips nearly all of those layers. If a service issues 5 Redis commands per HTTP request, **100,000 Redis operations/second does not equal 100,000 HTTP requests/second**—not to mention command dependencies, payload costs, and execution order.

## 2. Distinguishing Four Levels of Performance Testing

| Level | What Is Measured? | Questions Answered | What It Does Not Prove |
| --- | --- | --- | --- |
| **Command microbenchmark** | Single commands like `GET`, `SET`, `HGET` on Redis | How fast is the command under chosen parameters? | Overall business workflow |
| **Client/driver benchmark** | Lettuce/Jedis, connections, pipelining, serializers | How well does the Java app send/receive Redis commands? | Full service request flow |
| **Workload benchmark** | Command mix, keys, payloads, TTLs, concurrency | Can Redis and the client sustain a representative access pattern? | Parts of the system outside the simulation |
| **End-to-end load test** | HTTP/API/event/job traversing all dependencies | What latency, errors, and throughput do users experience? | Specific root cause without layered metrics |

Combine these levels. Microbenchmarks establish a **Redis baseline**; workload benchmarks test command/data distributions; end-to-end tests verify complete application capacity.

For instance, a team observes:

~~~text
redis-benchmark GET:   very high throughput
Spring API /products:  p99 still spikes as QPS rises
~~~

You cannot hastily declare Redis blameless or Spring Data Redis slow. Measure connection wait times, serialization, round trips, cache hit ratios, database load, and key access skew.

## 3. First Step: Describe the Real Access Pattern

A representative workload is more than `80% GET + 20% SET`. Document at least these dimensions:

| Workload Dimension | Questions to Answer | Performance Impact |
| --- | --- | --- |
| **Command mix** | What share is GET, SET, HGETALL, ZRANGE, EVAL, XADD? | Redis CPU, round trips, response shapes |
| **Key cardinality** | Thousands or millions of keys? | Memory, hit ratio, cache footprint, eviction |
| **Key popularity** | Uniform access or 80% hitting 1% of keys? | Hot keys, load skew, shard bottlenecks |
| **Payload size** | What are p50/p95/p99 of values, hash fields, stream entries? | Serialization, network, output buffers, GC |
| **Cache hit/miss** | What is miss rate by key group or time window? | DB load, cache fills, overall throughput |
| **TTL/expiration** | Fixed or jittered TTL; simultaneous expirations? | Active expiration, miss bursts, cache rebuilds |
| **Arrival pattern** | Steady, peaked, bursty, diurnal, spiky? | Queueing, tail latency, overload |
| **Concurrency** | Concurrent requests and how connections are shared? | Connection contention, threads, event loops |
| **Operation dependency** | Dependent GET-then-SET, or independent commands? | Potential for pipelining/batching |
| **Read consistency** | Primary or replica reads; read-your-writes needed? | Routing, latency, read results |
| **Failure behavior** | How many extra commands do timeouts, retries, fallbacks, failovers add? | Load amplification during incidents |

Collect distributions instead of averages alone. "1 KB average payload" can mask 95% 100 B payloads and 5% 20 KB payloads—where that 5% drives bandwidth, memory allocations, and tail latency.

**Protect sensitive data:** when deriving workloads from logs/traces, extract only needed metadata such as command families, byte sizes, key groups, TTL buckets, and timestamps. Never copy real values, tokens, session IDs, PII, or customer identifiers into test suites without strict authorization and redaction.

### 3.1. Examples of Real Business Requests

An API `GET /products/{id}` might execute:

~~~text
GET cache:product:<id>                (~90% cache hit)
  |
  +-- hit:
  |    Deserialize JSON → return HTTP
  |
  +-- miss:
       SELECT product FROM database
       SET cache:product:<id> EX <ttl>
       Deserialize/serialize → return HTTP
~~~

A direct GET benchmark misses the cache-miss branch entirely. If real hit rate drops from 90% to 50%, database load and API latency shift dramatically even while Redis `GET` speed barely changes.

Another API might execute:

~~~text
POST /checkout
   |
   +-- GET cart:<id>
   +-- HGETALL inventory:<sku>
   +-- EVAL quota check script
   +-- XADD orders:events
   +-- DELETE cart:<id>
   |
   +-- HTTP response
~~~

Benchmarking `GET` or `SET` alone fails to capture the command volume, response sizes, dependencies, and side effects of this flow.

## 4. Building a Repeatable Workload Profile

Define a **fixed, versioned profile** in test documentation so future runs stay comparable. Purely illustrative example:

| Component | Profile A: Normal Cache | Profile B: Peak Hour | Profile C: TTL Burst |
| --- | --- | --- | --- |
| Operation mix | 80% GET, 15% SET EX, 5% HGETALL | 85% GET, 10% SET EX, 5% HGETALL | 75% GET, 20% SET EX, 5% HGETALL |
| Keyspace | 100,000 keys | 100,000 keys | 100,000 keys |
| Hot keys | 80% accesses on 2% of keys | 95% accesses on 1% of keys | Focused on recently expired cohort |
| Payload | Mostly 128 B–1 KB, 8 KB tail | Higher share of large payloads | Includes DB-rebuilt payloads |
| Cache miss | 10% of GETs | 15% of GETs | Sudden spike in TTL expiry window |
| Arrival rate | Steady, stepped up | Bursty | Time-correlated bursts |
| Dependencies | Mostly independent Redis reads/writes | Concentrated concurrent reads | Miss → DB → cache re-SET |

These percentages are **not Redis or Spring defaults**. They merely illustrate experiment design. Derive production profiles from anonymized, normalized application telemetry.

For each profile, also record:

- Versions of the application, Spring Boot, Spring Data Redis, Lettuce/Jedis, and Redis.
- Topology: standalone, Sentinel, or Cluster, node counts, connection type.
- Actual serializers and payload sizes.
- TTL, persistence/eviction, pool, and timeout settings.
- Background load on other dependencies.
- Initial state, warm-up, ramp-up, steady-state durations, iterations, and stop criteria.

If any of these change between runs, comparisons become unfair.

## 5. Key Distribution: An Easily Overlooked Factor

Not all keys are accessed equally. Uniform random key selection behaves very differently from production traffic with hot keys, large tenants, or newly created keys.

### 5.1. Uniform vs Skewed Distribution

~~~text
Uniform workload:

Key 1  ███
Key 2  ███
Key 3  ███
Key 4  ███
Key 5  ███

Skewed workload:

Key 1  ████████████████████
Key 2  ███████
Key 3  ██
Key 4  █
Key 5  █
~~~

Common modeling techniques:

- **Uniform:** equal probability per key; useful as a baseline.
- **Hotset:** most requests target a small subset of keys; simple two-tier selection.
- **Zipf-like:** popularity decays by rank, modeling continuous skew.
- **Temporal locality:** recently accessed keys are likely to be accessed again soon.
- **Tenant-specific:** heavy traffic concentrates on one large tenant while smaller tenants stay quiet.

In Redis Cluster, a hot key or large-Hash key can saturate one shard even while total Cluster CPU looks low. Uniform benchmarks spread load evenly across slots and hide that risk.

### 5.2. Keyspace Size Governs Hit Ratio

A benchmark using only 100 preloaded keys achieves near-100% cache hits—far too easy. If the keyspace spans millions of keys while Redis holds only a fraction, misses and evictions occur.

A proper test specifies:

~~~text
Which set are keys drawn from?
How many keys are preloaded?
What fraction of GETs target missing keys?
How many keys expire via TTL during the run?
Do writes mutate the live keyset?
~~~

Do not bump keyspace size to 10 million while leaving `maxmemory` unchanged and then conclude "Redis got slower": the system may have shifted from "all in RAM" to "continuous eviction," which is a different workload.

## 6. Payload Size and Data Structures Change Cost

Redis serving a 64-byte `GET` behaves very differently from a 1 MB `GET`. Payload size affects:

1. Network bytes per request.
2. Byte arrays and objects allocated/copied in Java.
3. UTF-8, JSON, and DTO mapping cost.
4. Garbage collector pressure.
5. Redis output buffers and client queues.

In Spring Data Redis, measurements should distinguish:

~~~text
GET key → byte[] Redis → deserialize → Java DTO
            |                 |
         Network           CPU / GC
~~~

If raw Redis benchmarks use 64-byte values while the app stores 20 KB JSON, p99 gaps may come from network and serialization rather than Redis command execution.

### Different Commands Have Different Complexity

| Access Pattern | What to Simulate |
| --- | --- |
| `GET` / `SET` | Value size, hit/miss, TTL, write amplification |
| `MGET` / `MSET` | Keys per batch, response size, Cluster slot rules |
| `HGET` / `HGETALL` | Hash field count, field sizes, full-read ratio |
| `SMEMBERS` | Set cardinality and oversized response risk |
| `ZRANGE` / `ZREVRANGE` | Returned range size, score distribution, pagination |
| `EVAL` / Lua | Key count/script logic, time holding Redis execution |
| `XADD` / `XREADGROUP` | Entry size, batch size, consumer count, pending/ACK |
| `PUBLISH` | Actual subscriber count, fan-out, app callback work |

Never compare `GET 64B` throughput with `HGETALL 5,000-field Hash` and conclude "Hashes are slow." The two tests involve different data volumes, element counts, and work.

## 7. TTL, Eviction, and Cache Misses Belong in the Workload

TTL is not passive metadata. Expiring many keys simultaneously can trigger sudden miss spikes:

~~~text
Many keys SET EX 300 at 10:00
                    |
                    v
             10:05 expiration
                    |
                    v
      Burst of GET cache misses
                    |
                    v
           DB query surge
                    |
                    v
     Many requests re-SET same keys
~~~

This is a **cache stampede**. A benchmark running `GET` over preloaded non-expiring keys never exposes this risk.

When modeling TTLs, determine:

- Are TTLs uniform or jittered?
- How many keys are created simultaneously?
- Is sliding expiration (extending TTL on read) used?
- Are some keys persistent without TTL?
- On expiry, does the service call a DB, queue, or external API?
- Does single-flight/locking prevent concurrent cache rebuilds?

`maxmemory` and eviction policies also exert major influence. When data exceeds memory limits, Redis evicts keys per policy; benchmarks must monitor **evicted_keys**, **expired_keys**, memory usage, and hit/miss rates alongside latency.

High throughput accompanied by constant eviction overloading the database is not a healthy system.

## 8. Load Generation Models: Closed-Loop vs Open-Loop

How requests are generated directly shapes results. Two common models:

### 8.1. Closed-Loop: Fixed Number of Concurrent Workers

In closed-loop testing, each worker sends a request, waits for completion, and only then sends the next:

~~~text
Worker 1:  request → wait → request → wait → ...
Worker 2:  request → wait → request → wait → ...
Worker 3:  request → wait → request → wait → ...
~~~

When the system slows down, workers wait longer, so **the request arrival rate drops automatically**. This works well for testing a fixed number of concurrent clients, yet can mask inability to sustain a real external arrival rate.

### 8.2. Open-Loop: Maintaining a Target Arrival Rate

In open-loop testing, the generator schedules arrivals at a target rate—such as 2,000 requests/second—regardless of whether previous requests finished:

~~~text
Arrivals:  | | | | | | | | | | | | ...
Responses: |   |      |       |  ...
Queue:     0 1 3 5 8 12 ...
~~~

When Redis or the service falls behind, pending requests pile up and p95/p99 and timeouts climb, clearly exposing saturation points.

### 8.3. Coordinated Omission

**Coordinated omission** occurs when a harness records latency only for requests actually sent after the prior request completed, omitting the arrivals that *should have occurred* while the generator was stalled waiting.

For example, a request stalls for 2 seconds and a closed-loop worker waits without generating scheduled arrivals. Real continuous traffic would queue those arrivals, yet closed-loop timing misses their queueing delay.

To avoid misleading conclusions:

- State explicitly whether each test uses open-loop or closed-loop.
- For fixed-QPS capacity targets, use an independent arrival schedule and measure queue wait.
- Report **offered load** (attempted arrivals) and **achieved throughput** (completed requests) separately.
- Track in-flight counts, rejections, timeouts, and queue depth.
- Use load-testing tools that avoid or account for coordinated omission when measuring SLOs.

Never compare p99 from an open-loop 3,000 QPS test directly against a closed-loop 50-worker test as if both applied identical load shapes.

## 9. What to Measure: Throughput, Latency, and Business Outcomes

A good benchmark reports far more than a single "requests/second" figure. Track together:

| Metric | Meaning | Watch Out For |
| --- | --- | --- |
| **Offered RPS** | Arrival rate the generator attempts to drive | May exceed system capacity |
| **Completed RPS** | Total responses/second, including errors if counted | Does not imply success |
| **Successful RPS** | Valid successful completions/second | Always pair with error rate |
| **p50 latency** | Half of requests finish at or below this value | Reflects only typical cases |
| **p95/p99/p99.9 latency** | Tail latency distribution | Sensitive to queues, GC, large payloads, bursts |
| **Error/timeout rate** | Fraction failing or timing out | Dropping failed requests makes latency look artificially good |
| **In-flight/queue depth** | Requests actively executing or queued | Signals saturation onset |
| **Hit/miss ratio** | Cache hit vs miss split | Must track alongside DB fallback load |
| **Bytes in/out** | Actual network byte rate | Crucial with large payloads |
| **Redis CPU/memory** | Server utilization | Distinguishes Redis vs client bottlenecks |
| **GC/heap/client CPU** | JVM-side cost | Can dominate even when Redis CPU is low |

### Where Should Latency Be Measured?

Across an HTTP request:

~~~text
HTTP ingress
   |
   +-- Routing / filters / authentication
   +-- Business logic
   +-- Pre-Redis serialization
   +-- Connection wait / client queue
   +-- Network request + Redis execution + response
   +-- Deserialization
   +-- Database/API fallback on miss
   +-- Build response
   |
HTTP response
~~~

Capture at least three latency layers:

1. **End-to-end latency:** from request entry to complete response.
2. **Redis client operation latency:** time spent traversing the template/driver and returning.
3. **Redis server command latency:** command execution inside Redis via Redis metrics/tools.

These durations **do not simply add up linearly** because of concurrency, queueing, overlap, and async execution. When app latency is high while Redis CPU is low and slowlog is near empty, investigate network, connection waits, serializers, and client queues.

### Report Latency Per Operation Family

An aggregate p99 can hide fast GETs alongside slow large-payload `HGETALL` calls. Break down separately:

~~~text
GET hit         p50 / p95 / p99
GET miss        p50 / p95 / p99
SET EX          p50 / p95 / p99
HGETALL         p50 / p95 / p99
Service request p50 / p95 / p99
~~~

Never report just "p99 = 25 ms"; attach **units, measurement boundary, profile, offered load, success rate, and test phase**.

## 10. Relationship Between Concurrency, Latency, and Throughput

In steady state, **Little's Law** gives an approximate relationship:

\[
L = \lambda W
\]

Where:

- `L`: average number of items in the system.
- `\lambda`: steady-state arrival or completion rate.
- `W`: average time an item spends in the system.

For example, if 1,000 requests/second complete steadily with 20 ms average end-to-end latency:

\[
L \approx 1000 \times 0.020 = 20
\]

Average in-flight requests are roughly 20. This helps **sanity-check measurements**, not predict max throughput purely from thread counts. Once the system overloads and queues grow continuously, steady-state assumptions break down.

With 32 closed-loop workers, if average latency rises from 10 ms to 100 ms, request generation slows **dramatically** even without lowering worker count. Always report both concurrency and achieved throughput rather than latency alone.

### Spotting the Breaking Point

As offered load steps upward:

~~~text
Offered RPS      500   1000  1500  2000  2500
Success RPS      500   1000  1490  1940  1930
p99 latency      low   rising high  spike extreme
Timeout rate     0%    0%    small rising surging
~~~

These are **illustrative figures**, not an executed benchmark. Once successful throughput plateaus while offered RPS climbs—and p99 and errors escalate—the system has hit a saturation limit. Diagnose whether the bottleneck is Redis CPU, memory bandwidth, network, client connections, serialization, or a downstream dependency.

## 11. Seeding the Dataset Before Measuring

If a workload reads mostly missing keys, results look completely different from a high-hit cache. Before generating load, **seed data** matching the profile and verify key counts, payload sizes, and data structures.

Use an isolated namespace:

~~~text
bench:run-20261113:value:0
bench:run-20261113:value:1
bench:run-20261113:hash:0
bench:run-20261113:hash:1
...
~~~

Use a unique `runId` per run. Never share production key names, and never run `FLUSHALL` on a shared environment.

### Seed Realistic Complexity

- **Warm-cache profile:** preload keys beforehand, then warm up Spring and Redis.
- **Cold-cache profile:** omit preloading miss keys to measure fallback load separately.
- **Payload-mix profile:** seed 128 B, 1 KB, and 8 KB values in realistic proportions instead of a single `"hello"` string.
- **Hash profile:** create Hashes with representative field counts and sizes; `HGETALL` on 4 fields differs vastly from 3,000 fields.
- **TTL profile:** configure realistic TTL ranges, jitter, and creation timing.
- **Skew profile:** generate hotset or Zipf-like access rather than pure uniform random keys.

Keep seeding and cleanup **outside the steady-state measurement window**. Seeding 100,000 keys during measurement mixes setup load into steady-state results.

## 12. Java Example: Generating a Mixed Workload via `StringRedisTemplate`

The example below illustrates a small harness for **test/staging environments**, not a full load-testing framework. It uses:

- `StringRedisTemplate` to exercise the real Spring Data Redis and driver stack.
- Multiple worker threads issuing sequential commands (*closed-loop*).
- A mix of 80% `GET`, 15% `SET` with TTL, and 5% `HGETALL`.
- 80% of accesses concentrated on 2% of keys to simulate a hotset.
- ~10% of GETs intentionally targeting missing keys to simulate cache misses.
- `HdrHistogram Recorder` for thread-safe microsecond latency recording.
- Counters for successes, failures, and cache hits/misses.

**All percentages are illustrative parameters**; substitute observed application telemetry.

Extra dependency for the test/harness:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.hdrhistogram:HdrHistogram:2.2.2'
}
~~~

Place this harness inside `src/test/java` or a dedicated load-testing module. Never wire benchmark execution into `@PostConstruct` or automatic startup in production apps.

### 12.1. Seeding Data with Size Distribution

~~~java
package com.example.redis.performance;

import java.time.Duration;
import java.util.Map;
import java.util.Objects;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class BenchmarkDataSeeder {

    private static final String SMALL = "x".repeat(128);
    private static final String MEDIUM = "x".repeat(1024);
    private static final String LARGE = "x".repeat(8192);

    private final StringRedisTemplate redis;

    public BenchmarkDataSeeder(StringRedisTemplate redis) {
        this.redis = Objects.requireNonNull(redis);
    }

    public void seed(String namespace, int keyCount) {
        if (!namespace.startsWith("bench:") || keyCount <= 0) {
            throw new IllegalArgumentException(
                "Use isolated benchmark namespace and positive keyCount"
            );
        }

        for (int i = 0; i < keyCount; i++) {
            String payload = i % 20 == 0
                ? LARGE
                : (i % 5 == 0 ? MEDIUM : SMALL);

            redis.opsForValue().set(
                namespace + ":value:" + i,
                payload,
                Duration.ofMinutes(30)
            );

            redis.opsForHash().putAll(
                namespace + ":hash:" + i,
                Map.of(
                    "id", Integer.toString(i),
                    "status", "READY",
                    "category", "STANDARD",
                    "description", payload
                )
            );
            redis.expire(
                namespace + ":hash:" + i,
                Duration.ofMinutes(30)
            );
        }
    }
}
~~~

This seeder intentionally gives Hashes few fields with heterogeneous value sizes. If production has Hashes with thousands of fields, build a dedicated profile for that shape; do not assume 4-field `HGETALL` represents all Hashes.

TTL note: this illustrative seeder gives values and Hashes a 30-minute TTL; if a soak test runs longer, keys expire and shift the workload from warm-cache to miss-heavy. For steady-state runs, manage TTLs or intentionally test an expiration profile.

### 12.2. Load Generator and Latency Recorder Class

~~~java
package com.example.redis.performance;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

import org.HdrHistogram.Histogram;
import org.HdrHistogram.Recorder;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisPatternBenchmark {

    private static final long MAX_RECORDED_MICROS = 60_000_000L;
    private static final String SMALL = "x".repeat(128);
    private static final String MEDIUM = "x".repeat(1024);
    private static final String LARGE = "x".repeat(8192);

    private final StringRedisTemplate redis;

    public RedisPatternBenchmark(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public record Scenario(
            String namespace, int clients, int callsPerClient,
            int keyCount, long seed) {
        public Scenario {
            if (!namespace.startsWith("bench:")
                    || clients <= 0
                    || callsPerClient <= 0
                    || keyCount <= 0) {
                throw new IllegalArgumentException(
                    "Invalid benchmark scenario"
                );
            }
        }
    }

    public record Result(
            long successful,
            long failures,
            long hits,
            long misses,
            double elapsedSeconds,
            double successfulOpsPerSecond,
            long p50Micros,
            long p95Micros,
            long p99Micros) {
    }

    public Result run(Scenario cfg) throws Exception {
        Recorder recorder = new Recorder(
            1L, MAX_RECORDED_MICROS, 3
        );
        LongAdder successes = new LongAdder();
        LongAdder failures = new LongAdder();
        LongAdder hits = new LongAdder();
        LongAdder misses = new LongAdder();

        ExecutorService pool =
            Executors.newFixedThreadPool(cfg.clients());
        CountDownLatch ready = new CountDownLatch(cfg.clients());
        CountDownLatch go = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < cfg.clients(); worker++) {
                final int workerId = worker;

                futures.add(pool.submit(() -> {
                    SplittableRandom random =
                        new SplittableRandom(
                            cfg.seed() + workerId
                        );
                    ready.countDown();
                    go.await();

                    for (int n = 0; n < cfg.callsPerClient(); n++) {
                        long started = System.nanoTime();
                        try {
                            executeOne(
                                cfg, random, hits, misses
                            );
                            successes.increment();
                        } catch (RuntimeException error) {
                            failures.increment();
                            // A production harness should record error types
                            // without logging a stack trace per request.
                        } finally {
                            long elapsedMicros = Math.max(
                                1L,
                                TimeUnit.NANOSECONDS.toMicros(
                                    System.nanoTime() - started
                                )
                            );
                            recorder.recordValue(
                                Math.min(
                                    elapsedMicros,
                                    MAX_RECORDED_MICROS
                                )
                            );
                        }
                    }
                    return null;
                }));
            }

            if (!ready.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Workers did not become ready"
                );
            }

            long begin = System.nanoTime();
            go.countDown();

            for (Future<?> future : futures) {
                future.get(5, TimeUnit.MINUTES);
            }

            double seconds =
                (System.nanoTime() - begin) / 1_000_000_000.0;
            Histogram snapshot = recorder.getIntervalHistogram();

            return new Result(
                successes.sum(),
                failures.sum(),
                hits.sum(),
                misses.sum(),
                seconds,
                successes.sum() / seconds,
                snapshot.getValueAtPercentile(50),
                snapshot.getValueAtPercentile(95),
                snapshot.getValueAtPercentile(99)
            );
        } finally {
            go.countDown();
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }

    private void executeOne(
            Scenario cfg,
            SplittableRandom random,
            LongAdder hits,
            LongAdder misses) {

        int hotsetSize = Math.max(1, cfg.keyCount() / 50);
        int index = random.nextDouble() < 0.80
            ? random.nextInt(hotsetSize)
            : random.nextInt(cfg.keyCount());

        int operation = random.nextInt(100);

        if (operation < 80) {
            boolean deliberatelyMissing =
                random.nextInt(10) == 0;

            String key = deliberatelyMissing
                ? cfg.namespace() + ":missing:" + index
                : cfg.namespace() + ":value:" + index;

            String value = redis.opsForValue().get(key);
            if (value == null) {
                misses.increment();
            } else {
                hits.increment();
            }
        } else if (operation < 95) {
            String payload = random.nextInt(20) == 0
                ? LARGE
                : (random.nextInt(5) == 0 ? MEDIUM : SMALL);

            redis.opsForValue().set(
                cfg.namespace() + ":value:" + index,
                payload,
                Duration.ofMinutes(10)
            );
        } else {
            redis.opsForHash().entries(
                cfg.namespace() + ":hash:" + index
            );
        }
    }
}
~~~

This illustrates a **closed-loop harness**: each worker awaits Redis command completion before issuing the next call. Threads synchronize start via `CountDownLatch` so worker startup does not skew the timing window.

HdrHistogram's `Recorder` supports multi-threaded recording and interval snapshot extraction. Both successful and failed calls are timed here. Durations beyond 60 seconds are **clamped** to the histogram ceiling; a production harness should count clamped samples separately and raise the ceiling if needed so tail latency is not underreported.

In `Result`, `hits/misses` count **GETs only**, not Hashes or full business operations. `successfulOpsPerSecond` counts all non-throwing calls, including GETs returning null. If business logic treats cache misses as failures, track a separate metric instead of redefining successful operations.

### 12.3. Running the Harness from a Dedicated Integration Test

~~~java
BenchmarkDataSeeder seeder =
    new BenchmarkDataSeeder(stringRedisTemplate);

RedisPatternBenchmark benchmark =
    new RedisPatternBenchmark(stringRedisTemplate);

String namespace = "bench:" + java.util.UUID.randomUUID();
int keys = 10_000;

seeder.seed(namespace, keys); // Excluded from measurement window.

RedisPatternBenchmark.Scenario scenario =
    new RedisPatternBenchmark.Scenario(
        namespace,
        20,       // Closed-loop worker count
        2_000,    // Commands per worker
        keys,
        42L       // Random seed for profile repeatability
    );

// Run warm-up separately before collecting official results.
RedisPatternBenchmark.Result result = benchmark.run(scenario);

System.out.printf(
    "ok=%d errors=%d tps=%.1f p50=%d us p95=%d us p99=%d us%n",
    result.successful(),
    result.failures(),
    result.successfulOpsPerSecond(),
    result.p50Micros(),
    result.p95Micros(),
    result.p99Micros()
);
~~~

This is an **illustrative invocation snippet**, not an executed benchmark. Never publish assumed numbers from this snippet. Real profile runs require multiple repetitions, warm-ups, steady-state windows, and documented runtime/infrastructure specs.

**Limitations of this sample harness:**

- Closed-loop; does not hold a fixed offered RPS when Redis slows down.
- Command and payload proportions are approximate random samples rather than exact quotas.
- Does not separate histograms per command; real diagnostics need separate GET, SET, and HGETALL histograms.
- Not a distributed multi-host load generator and does not simulate HTTP/controllers/auth.
- Does not cover Redis Cluster routing, Sentinel failover, Stream consumers, or Pub/Sub subscribers.
- Does not include built-in coordinated-omission correction.
- Does not measure JSON serializer CPU directly since `StringRedisTemplate` uses string serialization.

In real projects, extend missing dimensions or adopt dedicated load tools. Even so, this pattern is valuable because it **exercises mixed operations through Spring Data Redis** rather than sending a single raw command directly to Redis.

## 13. Testing the Complete Application Flow

If your goal is determining how many requests a Spring Boot API sustains within an SLO, add **HTTP load tests** traversing controllers, authentication, serialization, Redis, databases, and response rendering.

Two test tiers:

~~~text
                [A] Redis Pattern Benchmark

Java benchmark → StringRedisTemplate → Lettuce → Redis
             (primarily measures Redis access path)

                [B] End-to-End Load Test

Load generator → HTTP/WebFlux/MVC → Service
                                     |
                           +---------+----------+
                           |                    |
                           v                    v
                  Spring Data Redis         Database/API
                           |                    |
                           +---------+----------+
                                     |
                                HTTP response
           (measures real experience and dependencies)
~~~

When an API exposes multiple endpoints, match production traffic proportions:

| Illustrative Endpoint | Traffic Share | Redis Pattern |
| --- | --- | --- |
| `GET /products/{id}` | 60% | GET cache; miss → DB → SET EX |
| `GET /users/{id}/cart` | 20% | HGETALL or multiple HGETs |
| `POST /cart/items` | 12% | HSET/EXPIRE and validation |
| `POST /checkout` | 8% | Read cart, conditional script, write event |

Shares are illustrative only, not defaults. Testing only the easiest cache-hit endpoint underestimates DB load, Redis writes, and tail latency of rarer but heavier endpoints.

### Load Generation Tools to Consider

- **`redis-benchmark`:** simple command-level baseline.
- **`memtier_benchmark`:** tests Redis load with mixed workloads and configurable options; inspect exact key generation, ratios, data sizes, and pipelining flags to interpret accurately.
- **JMeter, k6, Gatling, or similar HTTP tools:** test end-to-end APIs, arrival rates, responses, and SLOs.
- **Custom Spring harness:** exercises specific multi-command flows like GET → HGETALL → EVAL → SET EX that generic command tools do not model well.

Choose tools based on the question being asked, not whichever prints the highest throughput number. Two tools using different arrival models can report different p99 latencies against the exact same system.

## 14. Threads, Connections, Pipelining, and Reactive Redis

Spring Data Redis supports multiple execution models. Synchronous `RedisTemplate` and reactive `ReactiveRedisTemplate` differ in execution semantics; Lettuce and Jedis also manage connections, command queues, and threading differently.

### 14.1. Synchronous with `RedisTemplate`

A worker thread calls:

~~~java
String value = redis.opsForValue().get(key);
~~~

The thread blocks waiting for the result. When concurrency grows and Redis calls take time, threads block or contend on connections/pools. Note that thread count does not automatically equal TCP connection count: sharing and pooling depend on the driver and configuration.

### 14.2. Reactive with `ReactiveRedisTemplate`

A pipeline:

~~~java
Flux<String> values = Flux.fromIterable(ids)
    .flatMap(
        id -> reactiveRedis.opsForValue().get("cache:product:" + id),
        16
    );
~~~

`flatMap(..., 16)` caps concurrently active inner publishers **within that pipeline**. It can utilize non-blocking I/O better, yet cannot make an already saturated Redis server or network faster—excessive concurrency simply grows queues, latency, and timeouts.

When comparing synchronous vs reactive:

- Hold **command mix, keyspace, payloads, hit/miss rates, and TTLs constant**.
- Compare both end-to-end and Redis operation latencies.
- Track CPU, thread count, heap, GC, and in-flight counts.
- Never call `.block()` on an event-loop thread during reactive benchmarks.
- Never compare 20 synchronous workers against an unbounded-concurrency reactive pipeline and claim a framework victory.

### 14.3. Pipelining Changes Round-Trip Count

For multiple independent Redis commands, pipelining reduces round trips:

~~~text
Without pipeline:

SEND GET A → WAIT → SEND GET B → WAIT → SEND GET C → WAIT

With pipeline:

SEND GET A, GET B, GET C → receive replies
~~~

Any comparison must state:

- Batch size `P` or commands per pipeline.
- Total request/response byte volume.
- Redis connection handling and driver flush behavior.
- Memory used to buffer pending commands/replies.
- **Per-batch** latency vs **per-operation** latency; never mix the two units.

Pipelining does not turn multiple commands into a transaction. If command B depends on command A's result, they cannot be pipelined identically to independent commands without changing semantics.

### 14.4. Oversized Batches Are Not Always Better

Pipelining 10,000 commands at once can boost command/second throughput yet also:

- Expand buffer sizes.
- Give the whole batch high tail latency.
- Hold data in JVM memory longer.
- Delay concurrent short requests.
- Spike network traffic and allocations.

Test multiple finite batch sizes under the same workload, e.g., 1, 8, 32, 128. No universal optimum exists across topologies or payload sizes.

## 15. Measuring Both the Application and Redis Server

To locate bottlenecks, observe both sides of the wire.

### 15.1. Spring Boot / JVM Side

Metrics to collect:

| Category | Metrics |
| --- | --- |
| HTTP/API | Requests, success/error rate, p50/p95/p99, timeouts |
| Redis client | Command latency, reconnect count, command timeouts, queue/pool wait |
| Workload | GET hit/miss, SET count, Hash/Set/Stream operation mix |
| Runtime | JVM CPU, heap usage, allocation rate, GC pauses, thread count |
| Concurrency | Active requests, queued tasks, rejections, reactive in-flight |
| Fallback | DB query rate on cache misses, upstream latency, circuit-breaker state |

With Micrometer/Actuator enabled, export built-in metrics and instrument missing business operations. Do not assume all Redis client or per-command histograms appear automatically from adding one starter: metric availability depends on Spring Boot, driver, and configuration.

### 15.2. Redis Side

Useful inspection commands in authorized environments:

~~~bash
redis-cli -h redis.internal -p 6379 INFO stats
redis-cli -h redis.internal -p 6379 INFO commandstats
redis-cli -h redis.internal -p 6379 INFO memory
redis-cli -h redis.internal -p 6379 INFO clients
redis-cli -h redis.internal -p 6379 INFO cpu
redis-cli -h redis.internal -p 6379 SLOWLOG GET 10
redis-cli -h redis.internal -p 6379 LATENCY LATEST
~~~

Fields to track:

- `instantaneous_ops_per_sec` and total processed commands, interpreted over matching sampling intervals.
- Keyspace hits/misses, expired keys, and evicted keys.
- `used_memory`, `used_memory_peak`, fragmentation, and memory policy.
- `connected_clients`, blocked clients, output buffer pressure.
- `commandstats` per command type: calls, cumulative execution time, and error stats where supported.
- Slow log and latency events when thresholds are configured.

`SLOWLOG` measures server-side execution time and omits full network, serialization, and client wait times. If app p99 Redis latency is high while Redis server execution time is tiny, investigate layers outside command execution.

Never run `MONITOR` continuously in production to measure load; it adds heavy overhead and exposes command arguments. Never paste sensitive payloads from SLOWLOG into public reports.

### 15.3. With Redis Sentinel or Cluster

Under Sentinel, track primary/replica roles and replication lag; replica-read benchmarks differ in both consistency and latency. Under Redis Cluster, collect metrics **per shard**, not just cluster-wide averages:

~~~text
Cluster overall average CPU: 45%

Shard A CPU: 95%   ← hot key / hot slot
Shard B CPU: 20%
Shard C CPU: 20%
~~~

A "45%" cluster average hides Shard A saturation. Inspect hash-slot distribution, key popularity, key sizes, and command mix per node when evaluating scale.

## 16. Designing a Comparable Experiment Series

A single run easily breeds overconfidence. Structure experiments in phases:

1. **Baseline:** verify Redis infrastructure and simple commands under standard conditions; record configs and versions.

2. **Seed:** populate keyspace, payloads, TTLs, and structures; confirm no unexpected evictions.

3. **Warm-up:** bring JVM/JIT, connections, caches, and Redis into steady state. Exclude warm-up data from main results.

4. **Ramp-up:** step load upward, e.g., 10%, 25%, 50%, 75%, 100% of target.

5. **Steady-state:** hold target load long enough to observe latency, throughput, resources, and errors.

6. **Burst:** test short spikes, simultaneous TTL expirations, or cache miss surges.

7. **Soak:** sustain load over time to catch GC drift, leaks, memory growth, pool exhaustion, or evictions.

8. **Recovery:** drop load back to baseline and verify backlogs/errors/latency recover cleanly.

9. **Repeat:** re-run profiles using recorded seeds/order to quantify run-to-run variance.

Within one comparison cycle, avoid changing **multiple variables at once**. Switching from Jedis to Lettuce while raising pool size, adding pipelining, and swapping serializers makes it impossible to tell which change helped.

### Sample Results Table

| Profile | Offered RPS | Success RPS | Error % | p50 | p95 | p99 | Redis CPU | JVM GC Pause |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A / low | 500 | 500 | 0 | 4 ms | 11 ms | 18 ms | 23% | 2 ms |
| A / mid | 1,000 | 996 | 0.4 | 6 ms | 23 ms | 55 ms | 52% | 4 ms |
| A / peak | 1,500 | 1,400 | 6.7 | 12 ms | 100 ms | 350 ms | 89% | 20 ms |

**All numbers in this table are hypothetical data illustrating report formatting**, not measured results of Redis or Spring Data Redis in any specific environment.

Real reports should also document per-type operation counts, hit/miss ratios, payload distributions, network throughput, connection usage, hash slots/shards, and load-generator configs so runs remain comparable.

### Ensuring Reliable Comparisons

If Run 1 gives p99 = 25 ms and Run 2 gives 23 ms, you cannot claim an "8% speedup" when normal GC, generator, or network jitter swings 10–20%. Always:

- Run multiple independent trials.
- Compare identical workload profiles and infrastructure.
- Report distribution across trials (median, min/max, or confidence interval).
- Separate meaningful gains from random noise.
- Measure CPU/memory/queues to explain *why* an improvement occurred.

In particular, **a p99 computed from too few samples** is unstable. Collect enough requests and duration to measure tail latency accurately—never just a few hundred commands.

## 17. Reading Results to Locate the Real Bottleneck

Examine **multi-metric patterns** instead of a single number:

| Symptom | Possible Hypothesis | What to Inspect |
| --- | --- | --- |
| High Redis CPU, rising command latency | Redis server CPU-bound or heavy commands | Command mix, slowlog, scripts, big keys |
| Low Redis CPU, high app p99 | Client queue, network, serializer, or another dependency | Pool wait, JVM CPU/GC, network, API traces |
| RPS flat despite more workers | Hit processing limit or queueing | Achieved throughput, in-flight, latency, thread/pool saturation |
| Hit ratio drops, DB QPS rises | TTL/eviction/cache-miss shift | Expired/evicted keys, cache fill, hot keys |
| Timeouts spike during bursts | Queues, backpressure, connection limits | Arrival profile, pool, command timeouts, overload protection |
| One Cluster node has very high p99 | Hot shard, skew, or oversized key | Slot distribution, key popularity, per-node metrics |
| p99 grows with payload size | Network/serialization/GC | Bytes in/out, allocations, response sizes |
| Pipelining boosts ops/s yet API slows | Oversized batches, head-of-line blocking, memory | Batch latency, queues, peak memory |
| Retries multiply Redis traffic | Retry amplification during errors | Retry metrics, backoff, idempotency |
| TTL burst triggers API errors | Cache stampede onto database | Miss cohorts, single-flight, fallback saturation |

Each hypothesis should drive a **single-variable experiment** on the same profile. For example, suspecting serialization:

~~~text
Run A: StringRedisTemplate with 1 KB payload
Run B: RedisTemplate with JSON DTO of matching byte size

Keep key distribution, offered load, and Redis topology fixed.
Measure JVM CPU, allocations, GC, and end-to-end latency.
~~~

Suspecting round trips:

~~~text
Run A: 5 independent sequential GETs
Run B: Equivalent MGET where keys permit
Run C: Pipeline of 5 independent GETs

Keep key count, returned bytes, and arrival load fixed.
Evaluate semantic differences, especially on Cluster.
~~~

Never optimize blindly assuming "Redis is in-memory so it can't be slow." Redis is still bounded by CPU, network, memory bandwidth, command complexity, and topology.

## 18. Mistakes That Invalidate Benchmarks

| Mistake | Why Conclusions May Be Wrong | Fix |
| --- | --- | --- |
| Testing only one small-payload `GET` | Misses command mix, serialization, cache misses | Build multi-profile tests covering business flows |
| Repeating 100 keys over and over | Artificially easy hit ratio and working set | Use realistic keyspace size and popularity skew |
| Purely uniform key selection | Hides hot keys / hot shards | Test hotset / Zipf-like / tenant-skewed profiles |
| Reporting only requests/second | Hides p99 and errors | Include percentiles, success/error rates, in-flight |
| Raising workers and calling it RPS | Closed-loop slows arrivals on stall | Report offered and achieved load; use open-loop when appropriate |
| Timing only successful requests | Drops timeouts/rejections from latency stats | Track errors/timeouts separately and state histogram rules |
| Skipping JVM or connection warm-up | JIT, DNS, and handshakes skew measurements | Run dedicated warm-up; test cold-start separately if needed |
| Seeding data inside the measurement window | Setup traffic alters operation mix | Seed before steady-state measurement |
| Benchmarking 100% cache hits | Ignores DB fallback and cache stampedes | Include realistic miss ratios and expirations |
| Ignoring TTLs | Misses expired keys and cache rebuilds | Use TTL distributions and test TTL bursts |
| Checking only Cluster-average Redis CPU | One shard may be saturated | Inspect per-node/per-slot metrics |
| Comparing batch pipelines vs single commands by batch count | Units differ | Report batches/s, commands/s, and batch latency |
| Changing serializer, pool, and pipeline together | Cannot isolate which change helped | Vary one factor at a time |
| Strong client box, localhost Redis | Misses real RTT, cross-AZ, and TLS | Match load generator placement/topology to target |
| Load generator saturates its own CPU | Actual send rate drops below schedule | Monitor generator CPU, backlog, dropped schedule ticks |
| Copying real production data into tests | Security and privacy exposure | Use anonymized metadata and synthetic matched-distribution payloads |
| Benchmarking against shared production Redis | Causes evictions, timeouts, customer impact | Use isolated test/staging with bounded load and namespaces |
| Treating microbenchmarks as product SLAs | Excludes HTTP, DB, queues, serializers, auth | Validate end-to-end against SLOs |
| Concluding from a single run | Random jitter, GC, network variance | Repeat runs and inspect cross-run spread |
| Enabling retries without counting added load | One logical request sends multiple Redis commands | Measure retry amplification and total command count |

### Passing a Quick Command Test Does Not Mean System Capacity Is Enough

Even if `redis-benchmark` beats your ops/s target, real requests may require three Redis round trips plus a DB fallback on misses. At peak load, real capacity can be gated by the DB pool, cross-AZ links, serializer CPU, or queue waits.

Thus, the right question is not "How many GETs/sec can Redis handle?" but:

> Under realistic request, key, data, and failure distributions, can the system sustain the committed **success rate, throughput, and p99 latency**?

## 19. Defining Evaluation Criteria via SLOs

For benchmarks to drive clear decisions, define **acceptance thresholds** upfront. Hypothetical example for a cache-backed API:

~~~text
Profile: Product Read Peak v3
Offered load: 1,200 requests/second for 15 minutes
Success rate: >= 99.9%
End-to-end p95: <= 80 ms
End-to-end p99: <= 150 ms
No unexpected Redis evictions beyond policy
Database fallback stays within safe capacity
Backlog recovers once load returns to baseline
~~~

These numbers **illustrate how to write SLOs**, not achieved performance or universal Spring Data Redis standards.

Capacity decisions should consider:

1. What representative load can the system sustain over long durations?
2. Is there **headroom** for growth, bursts, and failovers?
3. When a Redis node or app instance fails, does the remainder meet an acceptable degraded SLO?
4. When latency breaches thresholds, do bottlenecks appear in Redis, the driver, the JVM, the network, or another dependency?
5. Do optimizations preserve business semantics such as TTLs, read consistency, ordering, and transactions?

Optimizing solely for higher ops/s while worsening p99 or causing duplicate writes/retries is not a real improvement.

### Build Capacity Margins Deliberately

If a profile meets SLOs at 1,500 requests/s in staging, do not assume production can safely run continuously at 1,500 RPS. Real variability comes from:

- Hourly shifts in production access patterns.
- Keyspace growth over time.
- Requests carrying larger-than-average payloads.
- Failovers temporarily reducing serving replicas/shards.
- Logging, tracing, backups, persistence, and background jobs sharing CPU/network.
- External systems slowing down periodically.

Choose headroom from risk analysis and burst/soak/failover testing rather than applying a blind universal multiplier.

## 20. Checklist for Preparing Reproducible Load Tests

Before starting, answer these in your test plan:

**Workload**

- Is the operation mix described in both **Redis commands** and **business requests**?
- Are keyspace size, hotsets, hit/miss, p50/p95/p99 payloads, and TTLs specified?
- Are primary vs replica reads and Redis topology explicitly defined?
- Are command dependencies and cache-miss branches modeled?
- Are retries, timeouts, cache rebuilds, and background jobs included in scope?

**Infrastructure and Load Generator**

- Are versions of Redis, Spring Data Redis, drivers, serializers, and pools/timeouts documented?
- Does the load generator have ample CPU/network so it does not bottleneck?
- Are open-loop vs closed-loop and the arrival schedule clearly specified?
- Is there an isolated benchmark namespace, TTL/cleanup, and memory limit protecting production?
- Are warm-up, ramp, steady-state, burst, soak, and repeat runs planned?

**Measurement**

- Are offered RPS, successful RPS, error rate, p50/p95/p99, and in-flight counts captured?
- Are Redis `commandstats`, memory, eviction, hit/miss, and per-shard metrics captured?
- Are JVM CPU, heap/GC, connection wait, and database fallback metrics captured?
- Are timed-out, cancelled, and rejected requests tracked?
- Can slow requests be traced across services, Redis operations, and downstream dependencies?

**Evaluation**

- Were target SLOs defined **before** inspecting results?
- Did comparisons hold profiles and infrastructure constant?
- Were enough samples and repetitions run to gauge variance?
- Do conclusions separate **observed measurements** from **bottleneck hypotheses**?
- Do optimizations (pipelining, batching, serializers, replica reads) preserve business semantics?

This checklist ensures tests answer real capacity questions instead of producing tables of numbers without context.

## 21. Practical Workflow for a Spring Data Redis Project

A development team can follow this loop:

~~~text
                  Production metrics / tracing
                               |
                               v
                Describe actual access pattern
             command mix / keys / payloads / TTL
                               |
                               v
                    Define workload profile
                               |
                               v
                 Seed data in isolated staging
                               |
                               v
                     Warm-up and ramp-up
                               |
                               v
             Closed-loop + open-loop as appropriate
                               |
                               v
             Measure throughput / errors / p95 / p99
                     /                 \
                    v                   v
           Spring/JVM metrics       Redis/node metrics
                    \                   /
                     +--------+--------+
                              |
                              v
                    Identify bottleneck
                              |
                              v
                     Change one factor
                              |
                              v
                    Re-run the same profile
                              |
                              v
                   Evaluate vs SLO and risks
~~~

Example optimization cycle:

**Hypothesis:** the product read API has high p99 because multiple Redis keys are fetched via sequential GETs over the network.

**Experiment:** compare the baseline against batching/pipelining **truly independent** reads while keeping traffic, keyspace, payloads, hit/miss rates, and Redis topology identical.

**Observation:** measure Redis operation duration, network round trips, HTTP p99, and memory/connections in both versions.

**Conclusion:** accept the change only if it improves SLO compliance without breaking read consistency, TTLs, failure semantics, or data ordering dependencies.

In another case, measurements may reveal a **cache stampede** on TTL expiry overloading the DB. There, optimizing `GET` helps little; effective fixes are TTL jitter, single-flight coalescing, cache-rebuild concurrency caps, or tuning the origin query.

## 22. Summary

Benchmarking single commands like `GET` or `SET` is useful for baselines, yet **Spring Data Redis application performance is governed by the end-to-end access pattern**, including command mix, key skew, payload sizes, cache miss rates, TTLs, concurrency, serialization, networking, topology, and downstream dependencies.

A trustworthy load test must:

1. **Derive workloads from observed telemetry** rather than inventing an arbitrary command mix and calling it production.
2. **Seed and drive load systematically**, separating warm-up, steady-state, bursts, soaks, and closed-loop vs open-loop models.
3. **Measure across dimensions**, covering offered load, successful throughput, errors/timeouts, p50/p95/p99, Redis server, driver, and JVM.
4. **Preserve business semantics** when experimenting with pipelining, batching, serializers, replica reads, or retries.
5. **Evaluate against SLOs and repeat trials** instead of claiming success from one peak ops/s number.

The best outcome is not "highest Redis commands/second" but **sustaining representative traffic with latency, reliability, and resource costs inside acceptable bounds**. Measuring by access pattern gives teams the evidence needed to optimize the right layer—whether Redis commands, Spring Data Redis client settings, caching strategy, networking, or the business workflow itself.
