# Measuring Latency, Throughput, and Actual Data Size in Spring Data Redis

## 1. Why Measure Instead of Just Saying "Redis Is Very Fast"?

Redis is frequently chosen because it keeps data in memory and handles many operations with low latency. Spring Data Redis lets Java applications talk to Redis via `RedisTemplate`, `StringRedisTemplate`, Redis Cache, Redis Repositories, or reactive APIs. However, claiming "Redis is fast" leaves critical operational questions unanswered:

- How many milliseconds does a single `GET` take **from the application's perspective**?
- What is the p95/p99 latency of a cache-backed HTTP endpoint, and how much of that time is spent in Redis?
- How many requests/second can one Spring Boot instance sustain before p99 crosses the threshold?
- How many Redis commands does one real request generate? Does `RPS` equal `Redis ops/s`?
- Does storing a 1 KiB JSON DTO actually consume exactly 1 KiB of RAM in Redis?
- For one million keys, how much RAM must be provisioned, including metadata, expiration, indexes, and fragmentation?
- Does pipelining cut total batch duration while slowing down other concurrent requests?
- As concurrency rises, is the bottleneck the Java serializer, event loop, network, Redis server, Redis Cluster, or database fallback on cache misses?
- Does a `redis-benchmark` run hitting 100,000 requests/s prove the real application sustains 100,000 business requests/s?

To answer these, you must measure **three related yet distinct groups of metrics**:

1. **Latency:** how long each operation takes, especially at poor percentiles such as p95 and p99.
2. **Throughput:** operations completed per unit time, paired with byte volume and concurrency.
3. **Actual data size:** key/payload bytes on the wire, actual memory allocated by Redis, data structure overhead, indexes, and system components.

An application can have high throughput alongside terrible p99. A 500-byte JSON key can consume far more than 500 bytes in RAM. A Redis command completing in tens of microseconds on the server can still take tens of milliseconds at the Java endpoint due to network transit, serialization, or queueing.

**The goal of performance measurement is not finding the prettiest headline number, but characterizing system behavior under production-like workloads, measuring real limits, and proving optimizations genuinely help.**

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish latency across HTTP, service, Redis client, Redis server, and network layers.
2. Read p50, p95, p99, max, and latency distributions instead of averages alone.
3. Distinguish RPS, Redis commands/s, records/s, bytes/s, and business operation rates.
4. Instrument Spring Data Redis with Micrometer/Actuator and record errors, timeouts, and hits/misses.
5. Use `INFO`, `SLOWLOG`, `LATENCY`, `MEMORY USAGE`, `SCAN`, and Redis benchmarks within proper scope.
6. Measure serialized payload sizes, key bytes, and actual RAM across Redis data types.
7. Estimate capacity with headroom from representative size distributions and real key counts.
8. Design load tests covering warm-up, concurrency, read/write mix, hot keys, TLS, and representative data.
9. Evaluate pipelining, batching, TTLs, serializers, Redis Cluster, Cache, and Streams.
10. Turn measurements into verifiable optimization decisions and production monitoring metrics.

## 2. Where Does a Request in Spring Data Redis Go?

Consider a product read API backed by Redis Cache:

```text
Browser / API client
      |
      v
Ingress / Load balancer
      |
      v
Spring WebFlux / Spring MVC endpoint
      |
      +--> Security / validation
      |
      +--> Service
              |
              +--> Spring Cache / RedisTemplate
              |       |
              |       +--> Generate key / serialize key
              |       +--> Acquire or create Redis connection
              |       +--> Encode Redis command
              |       +--> Network request
              |       +--> Redis server queue/execute
              |       +--> Network response
              |       +--> Decode reply / deserialize value
              |
              +--> Cache miss?
                      |
                      +--> Database / external API
                      +--> Serialize + SET cache
              |
              v
         Map DTO / render response
              |
              v
        HTTP response
```

Looking only at Redis `GET` execution time misses most of the path. Looking only at HTTP latency leaves you guessing whether Redis is the culprit.

Define each measurement boundary explicitly:

| Scope | Start | End | What Is Measured |
|---|---|---|---|
| HTTP end-to-end | Client sends request | Client receives full response | App + network + proxy + Redis + dependencies |
| Server HTTP latency | Request enters server | Server finishes response | App and internal dependencies |
| Business service latency | Business method starts | Method returns | Depends on instrumentation placement |
| App-side Redis operation latency | Command starts via Redis client | Client completes or errors | Serialization/connection/network/Redis/response per timer placement |
| Redis command execution | Redis starts processing command | Redis finishes internal execution | Server execution time, typically excluding network RTT |
| Serialization latency | Start converting DTO to bytes | Bytes produced | CPU and allocation inside the JVM |
| Network RTT | Packet send/receive or probe | Reply received | Network layer; does not replace command timing |

Whenever someone says "Redis latency = 5 ms," ask **where was 5 ms measured?** The same system might report:

```text
Server command execution:     0.05 ms
Redis client round-trip:      1.8 ms
Serialize + Redis + decode:   2.4 ms
HTTP endpoint end-to-end:    16.0 ms
```

These numbers are **illustrative**, not default Redis figures.

### 2.1. Latency Differs from Command Call Count

A Java method:

```java
public ProductDto getProduct(String id) {
    return cache.get(id);
}
```

may trigger:

- One `GET`.
- Two commands due to TTL/metadata checks.
- Multiple commands from repositories/indexes.
- A missed `GET` plus an extra `SET`.
- Retried commands after timeouts.
- Multi-key commands or pipelines.

To measure accurately, determine **how many Redis operations** a method actually issues rather than guessing from lines of Java.

## 3. Latency: Averages Usually Hide Tail Latency

An operation's latency is the elapsed duration between a defined start and end point.

Common aggregations:

- **Mean/average:** total duration divided by sample count.
- **Median/p50:** roughly 50% of samples do not exceed this value.
- **p95:** roughly 95% of samples do not exceed this value.
- **p99:** roughly 99% of samples do not exceed this value.
- **Max:** largest sample in the measured window.
- **Histogram:** distribution of sample counts across duration buckets.
- **Error/timeout rate:** fraction of operations failing or missing their deadline.

Suppose 1,000 calls yield:

```text
990 calls: ~1 ms
 10 calls: ~200 ms
```

The mean is nearly 3 ms—deceptively low—yet 1% of requests stalled for 200 ms. In multi-step pipelines, a handful of tail latencies can dominate user experience and overall endpoint duration.

**Never substitute the mean for p99** when setting SLOs on latency-sensitive APIs.

### 3.1. Reading Percentiles Correctly

If an operation's p99 latency is 25 ms, the practical interpretation is:

> Within the sampled dataset and observation window, approximately 99% of operations completed in at most 25 ms.

It **does not guarantee** all future operations stay under 25 ms, nor does it state how fast the fastest or slowest request was.

Component percentiles also cannot simply be summed:

```text
p99(GET) + p99(DB) != necessarily p99(HTTP)
```

because distributions, time correlations, and concurrency differ. If you need HTTP p99, **measure HTTP directly** rather than adding component p99s.

### 3.2. Percentiles Depend on Sample Size and Time Window

A test with just 100 requests cannot capture rare events like Redis failovers, GC pauses, or tail latency under heavy load.

Always document:

```text
Measurement window: 15 minutes
Requests:           1,200,000
Concurrency:        64
Payload:            matching production distribution
Warm-up:            3 minutes, excluded from results
Metrics:            p50, p95, p99, max, error %
```

These numbers are example test descriptors; replace them with real measured values in practice.

### 3.3. Tail Latency Can Arise from Many Layers

Common causes:

- CPU contention inside the JVM or Redis.
- Garbage collection pauses.
- Network jitter, TLS overhead, or packet retransmissions.
- Client-side queueing when concurrency exceeds capacity.
- Connection acquisition / pool waits.
- Slow Redis commands or long Lua scripts.
- Redis `fork`/persistence/resharding spikes.
- Hot keys / hot slots.
- Extra commands per request caused by cache misses.
- Serializing large JSON payloads.
- Blocked thread pools or event loops.
- Large response payloads slowing network transfer and decoding.

Do not simply add Redis nodes before locating which layer drives p99.

## 4. Throughput: RPS Is Not Redis ops/s

**Throughput** measures completed work per unit time—but "work" has many units:

| Unit | Example | What Must Be Clarified |
|---|---|---|
| HTTP requests/s (RPS) | 2,000 requests/s | Which endpoint? What error rate? |
| Business operations/s | 1,000 checkouts/s | Which steps comprise one checkout? |
| Redis commands/s | 8,000 commands/s | Total commands or `GET` only? |
| Redis Stream records/s | 5,000 `XADD` entries/s | Payload size and consumer lag? |
| Messages/s | 20,000 Pub/Sub messages/s | Subscriber count and fan-out? |
| Bytes/s | 100 MiB/s rx/tx | Payloads, wire overhead, TLS? |
| Keys/s | 50,000 new keys/s | TTLs and memory growth? |

Suppose one HTTP request executes:

```text
1 x GET session
1 x GET product
1 x HGETALL cart
1 x SET cache
```

One business request generates **4 Redis commands** in this scenario.

At 2,000 RPS with that pattern:

```text
2,000 RPS x 4 Redis commands/request
    = 8,000 Redis commands/s
```

In reality, commands/request shift with cache hit/miss rates, batch sizes, retries, and code paths. Pull actual counts from traces/metrics or measure per operation family.

### 4.1. Throughput Always Pairs with Latency and Error Rate

A load test might report:

```text
Throughput: 50,000 RPS
p99:        3,000 ms
Errors:     25%
```

50,000 proves nothing about sustainable useful capacity. Require all of these together:

```text
Throughput >= target
p99 latency <= latency budget
Error rate <= threshold
No unbounded backlog
Stable resources
```

Beyond saturation, completed throughput stops climbing while latency and queue depth surge.

### 4.2. Concurrency and Wait Time

An approximation from Little's Law in steady state:

\[
L = \lambda W
\]

Where:

- \(L\): average number of tasks inside the system.
- \(\lambda\): average completion throughput, e.g., requests/s.
- \(W\): average time spent in the system, in seconds.

At 1,000 requests/s with 0.05 s average system time:

```text
L ≈ 1,000 x 0.05 = 50 in-flight requests on average.
```

This equation helps reason about concurrency and queueing—it is **not a p99 measurement** and applies only under clearly defined system boundaries and steady-state conditions.

### 4.3. When Concurrency Exceeds Limits

```text
Concurrency -> increases
      |
      +--> Initially throughput rises
      |
      +--> Hits CPU/network/Redis limit
      |
      +--> Queues lengthen
      |
      +--> p95/p99 climb
      |
      +--> Timeouts/retries add extra load
      |
      +--> Useful throughput can drop
```

The point where latency begins climbing steeply is informally called the **knee** of the load curve. Capacity planning targets operating with headroom ahead of that knee rather than chasing brief peak benchmark spikes.

## 5. Three Concepts of Data Size

When someone says "this key weighs 1 KiB," distinguish at least three things:

**(1) Logical data size:** character or field count stored by the business domain.

**(2) Serialized / wire byte size:** bytes of the key, fields/values, JSON/MessagePack/binary encoding, RESP protocol framing, and network overhead.

**(3) Redis memory usage:** bytes allocated by Redis in RAM for the key/value and internal structures, plus instance-level overhead.

Example:

```text
Java DTO:
    Product(id, name, price, attributes)

Serialized JSON:
    864 UTF-8 bytes

Redis key:
    "product:123" = 11 UTF-8 bytes

Redis MEMORY USAGE product:123:
    Can exceed 864 + 11 bytes

Redis process RSS:
    Also includes allocator, overhead, fragmentation,
    connection buffers, and other components.
```

No universal multiplier fits every key and Redis version. `String`, `Hash`, `Set`, `Sorted Set`, `List`, `Stream`, TTLs, value sizes, and encodings all carry different overheads.

### 5.1. A 1 KiB JSON Payload Does Not Mean 1 KiB on the Network

A command:

```redis
SET product:123 <json-1024-bytes> EX 600
```

also carries on the wire:

- Command name.
- Argument lengths in Redis Serialization Protocol (RESP).
- Key bytes.
- Expiration argument.
- Protocol framing.
- TCP/IP and optional TLS overhead.

When measuring network throughput, never treat `json.length()` as total network bytes.

### 5.2. A 1 KiB Payload Does Not Mean 1 KiB of Redis RAM

Redis must maintain:

- Key name and value.
- Dictionary entry / internal metadata.
- Object encoding and allocator overhead.
- Expiration metadata when a TTL is set.
- Container metadata for Hashes/Lists/Sets/ZSets/Streams.
- Extra keys/fields maintained by repositories/indexes/caches.
- Instance overhead and memory fragmentation.

**Measure actual bytes inside Redis**, then extrapolate from representative samples.

## 6. Setting Up Multi-Layer Performance Measurement

A Spring Boot system can draw on four telemetry sources:

```text
              Monitoring / Metrics

  HTTP request timing --------------------+
                                           |
  Spring service/custom Micrometer timers -+
                                           +--> Dashboard & correlation
  Lettuce/Redis client latency ------------+
                                           |
  Redis INFO/SLOWLOG/LATENCY/MEMORY -------+
```

Each source plays a distinct role:

| Source | Strengths | What It Misses |
|---|---|---|
| HTTP metrics | Endpoint experience, actual p95/p99 | Redis's share unless spans are split |
| Service metrics | Business method or cache operation time | Whether Redis Server itself was slow |
| Client command metrics | Round-trip, errors, remote node | Full HTTP duration and business correctness |
| Redis commandstats | Server-side execution counts and times | Network RTT, serialization, Java GC |
| Redis memory metrics | Dataset, overhead, RSS, evictions | Individual app payload bytes without extra checks |
| Tracing | Which dependencies one request touched | Throughput/capacity stats if heavily sampled |
| Load generator | External RPS and latency | Internal Redis/process state without instrumentation |

Never replace all of these sources with a single number from `redis-benchmark`.

### 6.1. Metrics to Agree On Before Benchmarking

Example target specification:

```text
Endpoint: GET /api/products/{id}
Workload: 90% cache hit, 10% cache miss
Dataset:  1 million products
Payload:  p50 1 KiB, p99 12 KiB
Target:   3,000 RPS
SLO:      server-side p99 <= 50 ms
Errors:   < 0.1%
Redis:    no unexpected evictions
```

All figures are **illustrative test goals**, not measured Redis benchmarks. Targets must stem from user experience and real project workloads.

## 7. Micrometer and Spring Boot Actuator

In Spring Boot, **Micrometer** typically records metrics, while Actuator exposes monitoring endpoints and integrations depending on dependencies and configuration.

Illustrative Maven dependencies:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
```

When using Spring Boot dependency management, manual versions are usually omitted for managed artifacts.

Example `application.yml` for controlled observability:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 3s

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Exact metrics/observation settings vary by Spring Boot version and exporter. Do not assume every Redis command timer appears automatically simply by adding Actuator. For Redis, driver instrumentation or custom service timers may be required.

**Security:** never expose Actuator endpoints publicly without restriction. Enforce network controls, authentication/authorization, and exclude sensitive data from tags.

### 7.1. Discovering Available Metrics

While the app runs, inspect:

```bash
curl http://localhost:8080/actuator/metrics
```

Read a specific metric:

```bash
curl http://localhost:8080/actuator/metrics/http.server.requests
```

If the Prometheus exporter is enabled:

```bash
curl http://localhost:8080/actuator/prometheus
```

Exact metric names and distributions vary across Spring versions, instrumentation, exporter naming conventions, and tag configs. Always verify against the live endpoint instead of assuming a metric named `redis.latency` is automatically published.

### 7.2. Use Histograms Rather Than Averaging Percentiles

To aggregate p95/p99 across multiple instances, histograms with suitable buckets are far better than averaging precomputed per-instance percentiles.

Example of what not to do:

```text
Instance A p99 = 10 ms
Instance B p99 = 100 ms
=> global p99 = (10 + 100) / 2 = 55 ms
```

This is mathematically invalid whenever traffic volumes or distributions differ across instances. Aggregate raw histogram buckets (when supported by your registry/monitoring backend) or compute distributions from an aggregatable source.

## 8. Example: Measuring Redis GET/SET at the Service Layer with Micrometer

A simple instrumentation pattern using `StringRedisTemplate` and `MeterRegistry`:

```java
package com.example.metrics;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class InstrumentedRedisGateway {

    private final StringRedisTemplate redis;
    private final MeterRegistry registry;

    public InstrumentedRedisGateway(
            StringRedisTemplate redis,
            MeterRegistry registry) {

        this.redis = redis;
        this.registry = registry;
    }

    public String get(String key) {
        long start = System.nanoTime();
        String outcome = "success";

        try {
            return redis.opsForValue().get(key);
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            long elapsed = System.nanoTime() - start;

            Timer.builder("app.redis.operation.duration")
                .description("Spring Redis call latency")
                .tag("command", "GET")
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsed, TimeUnit.NANOSECONDS);
        }
    }

    public void put(
            String key,
            String value,
            Duration ttl) {

        long start = System.nanoTime();
        String outcome = "success";

        try {
            redis.opsForValue().set(key, value, ttl);
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            long elapsed = System.nanoTime() - start;

            Timer.builder("app.redis.operation.duration")
                .description("Spring Redis call latency")
                .tag("command", "SET")
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsed, TimeUnit.NANOSECONDS);
        }
    }
}
```

Notes here:

- `System.nanoTime()` is suited for **elapsed durations**, immune to wall-clock jumps.
- The timer starts right before calling `StringRedisTemplate`.
- Measured time covers everything inside the call: Redis client, network, Redis, and reply decoding depending on the API.
- It **excludes** DTO-to-String serialization if serialization occurs before entering `put`.
- `null` from `GET` is normally a cache miss, yet this example records `outcome=success` because no exception occurred.
- To separate hits from misses, add a dedicated **low-cardinality tag or counter**, rather than lumping cache misses together with Redis network errors.

This provides service-level instrumentation, not a breakdown of the full HTTP request timeline.

### 8.1. Never Use Keys or requestId as Metric Tags

Wrong:

```java
.tag("key", "product:" + productId)
.tag("requestId", requestId)
```

With one million product IDs, the monitoring system can create one million time series, triggering cardinality explosion and high storage costs.

Tags must have small bounded domains:

```text
command: GET / SET / HGETALL / XADD
operation: product-read / session-load / cart-update
outcome: success / error / timeout
cache: product / cart / session
node_group: bounded label if truly needed
```

Never put payloads, session tokens, full Redis keys, or URIs containing IDs into tags.

### 8.2. Separate Hit/Miss from Command Latency

For `GET`, there are two separate questions:

```text
Did the GET command complete?
Did the data exist?
```

A cache miss (`GET` returning `null`) is still a successful Redis command. Track hit rate via a separate counter or bounded outcome tag:

```java
String value = redis.opsForValue().get(key);

registry.counter(
    "app.redis.cache.lookup",
    "cache", "product",
    "result", value == null ? "miss" : "hit"
).increment();
```

Measure hits/misses at the appropriate cache abstraction if Spring Cache already instruments them, avoiding double counting across layers.

## 9. Measuring Serialization Separately from Redis Latency

Spring Data Redis frequently serializes Java DTOs into bytes for Redis. Timing only `redis.opsForValue().set(...)` can hide the CPU cost of building JSON from a DTO.

Example with Jackson:

```java
package com.example.metrics;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

@Service
public class ProductCacheWriter {

    private final ObjectMapper objectMapper;
    private final StringRedisTemplate redis;
    private final Timer serializationTimer;
    private final Timer redisWriteTimer;
    private final DistributionSummary valueBytes;
    private final DistributionSummary keyBytes;

    public ProductCacheWriter(
            ObjectMapper objectMapper,
            StringRedisTemplate redis,
            MeterRegistry registry) {

        this.objectMapper = objectMapper;
        this.redis = redis;

        this.serializationTimer =
            Timer.builder("app.redis.serialization.duration")
                .tag("format", "json")
                .tag("operation", "product-write")
                .publishPercentileHistogram()
                .register(registry);

        this.redisWriteTimer =
            Timer.builder("app.redis.write.duration")
                .tag("operation", "product-write")
                .publishPercentileHistogram()
                .register(registry);

        this.valueBytes =
            DistributionSummary.builder("app.redis.value.bytes")
                .baseUnit("bytes")
                .tag("cache", "product")
                .register(registry);

        this.keyBytes =
            DistributionSummary.builder("app.redis.key.bytes")
                .baseUnit("bytes")
                .tag("cache", "product")
                .register(registry);
    }

    public void write(String productId, ProductDto dto)
            throws JsonProcessingException {

        String key = "product:" + productId;

        String json = serializationTimer.recordCallable(
            () -> objectMapper.writeValueAsString(dto)
        );

        byte[] payload = json.getBytes(StandardCharsets.UTF_8);
        byte[] keyPayload = key.getBytes(StandardCharsets.UTF_8);

        valueBytes.record(payload.length);
        keyBytes.record(keyPayload.length);

        redisWriteTimer.record(() ->
            redis.opsForValue()
                .set(key, json, Duration.ofMinutes(10))
        );
    }

    public record ProductDto(
        String id,
        String name,
        long priceInCents
    ) {}
}
```

Depending on the Micrometer version, `recordCallable(...)` has varying checked-exception contracts; to preserve `JsonProcessingException` cleanly, you can time manually with `System.nanoTime()` in `try/finally`. This example illustrates **measuring serialization separately from Redis I/O**.

Details:

- `json.getBytes(UTF_8).length` captures the JSON String byte size being sent.
- `key.getBytes(UTF_8).length` captures key byte size under matching String serialization.
- `valueBytes.record` tracks application payload size, **not Redis `MEMORY USAGE`**.
- `redisWriteTimer` times the Redis write of the already-serialized String.
- If switching to a binary serializer, measure **actual bytes emitted by that serializer** rather than assuming JSON String length.
- If payloads are compressed, record both pre-compression and post-compression bytes plus CPU cost.

### 9.1. Avoid Double-Counting Metrics

If Lettuce already publishes command latency and your gateway also records a timer, those are **two measurements at different scopes**, not two Redis commands. Name metrics clearly on dashboards—such as `app.redis.write.duration` vs `lettuce.command.latency`—instead of summing counts from both timers as throughput.

### 9.2. Key Size Also Matters

A key like:

```text
p:42
```

is shorter than:

```text
production:tenant-7:catalog:product:42:version:2026
```

Across millions of keys, long key-name overhead can become significant. Still, shortening keys to save a few bytes must balance debuggability, namespacing, multi-tenant isolation, and Redis Cluster hash tags.

**Never shorten keys so aggressively that collisions occur or business identity becomes opaque.** Measure the actual difference before optimizing deliberately.

## 10. ReactiveRedisTemplate: Measure by Subscription, Not Mono Creation

In WebFlux, reactive calls construct lazy Publishers:

```java
Mono<String> value = reactiveRedisTemplate
    .opsForValue()
    .get("product:42");
```

Starting a timer **when creating the `Mono`** when subscription happens much later inflates results with unrelated wait time. Conversely, without a subscriber, the command never executes.

Measure from when subscription/attempt begins:

```java
package com.example.metrics;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveProductReader {

    private final ReactiveStringRedisTemplate redis;
    private final Timer timer;

    public ReactiveProductReader(
            ReactiveStringRedisTemplate redis,
            MeterRegistry registry) {

        this.redis = redis;

        this.timer = Timer.builder("app.redis.reactive.get.duration")
            .tag("cache", "product")
            .publishPercentileHistogram()
            .register(registry);
    }

    public Mono<String> get(String key) {
        return Mono.defer(() -> {
            long start = System.nanoTime();

            return redis.opsForValue()
                .get(key)
                .doFinally(signal -> {
                    long elapsed = System.nanoTime() - start;
                    timer.record(elapsed, TimeUnit.NANOSECONDS);
                });
        });
    }
}
```

`Mono.defer` ensures every subscription gets its own start timestamp. `doFinally` executes on completion, error, or cancellation.

**Scope note:** this timer records cancelled subscriptions too; to separate cancellations, timeouts, and successes, add a low-cardinality `signal` counter or tag. If `retryWhen` wraps the method externally, each attempt is timed separately; if retries sit inside the timed source, the timer covers multiple attempts. Agree on metric definitions before comparing results.

### 10.1. Do Not Block the Event Loop to Benchmark

Avoid:

```java
String value = reactiveRedisTemplate
    .opsForValue()
    .get(key)
    .block();
```

inside a WebFlux request handler just to "make timing easy." `.block()` blocks threads and distorts both performance and the concurrency model.

Let WebFlux subscribe to Publishers and measure via Micrometer, tracing, or an external load generator. Synchronous `block()` in a test thread may be used carefully in integration tests, but never treat those numbers as representative of production WebFlux apps.

### 10.2. Backpressure Does Not Mean Redis Has No Bottleneck

Reactor can throttle downstream demand, yet:

- Already-sent Redis commands still consume network and server capacity.
- Client queues can grow.
- High pipelining/concurrency can lengthen wait times.
- SSE/Pub/Sub have distinct fan-out characteristics.
- Redis Streams can build up unACKed PEL backlogs.

Measure throughput/latency together with in-flight work and backlogs—not Java CPU alone.

## 11. Lettuce Command Latency and Observation

**Lettuce** is Spring Data Redis's default driver, managing connections, command execution, async/reactive APIs, and command latency collection in supported setups.

Available observability depends on:

- Lettuce version.
- Spring Boot / Spring Data Redis version.
- ClientResources and command latency collector setup.
- Whether Micrometer/Tracing bridges are configured.
- Command type, connections, Redis Cluster, and topology.
- Metrics registry/exporter.

Deployments may use Lettuce's command latency collector or Spring Boot's Micrometer/Observation integration on supported versions. **Never assume every project has it enabled out of the box or emits the exact same metric names.**

### 11.1. What Does Client Latency Tell You?

Lettuce command latency typically exposes:

```text
GET latency
SET latency
MGET latency
EVAL latency
XREADGROUP latency
...
```

grouped by remote endpoint/command as configured. It captures client/driver timings or recorded command phases—distinct from Redis Server's `cmdstat_get`.

A Redis server executing `GET` quickly can still yield high client p99 due to network or client event-loop delays.

### 11.2. Do Not Enable Unbounded Metric Tags

Command latency metrics should use command types and bounded label dimensions. Never put key names or `requestId` into every metric.

In Redis Cluster, remote address/node labels can grow as topology shifts; bound cardinality and avoid scraping overly granular unused series.

### 11.3. Client Metrics Are Telemetry, Not Automatic SLAs

Sampling rates, aggregation intervals, histograms/percentiles, and export delays affect numbers. Comparing a 1-minute p99 metric against a 5-minute HTTP p99 metric as if both shared the same window is invalid.

For latency regression checks, align windows, workloads, instances, routing, and percentile methods.

## 12. Redis INFO: Viewing Server-Side Throughput

Redis provides:

```redis
INFO
```

and specific sections:

```redis
INFO stats
INFO commandstats
INFO memory
INFO clients
INFO cpu
INFO persistence
INFO keyspace
```

Common fields:

| Section | Metric | Meaning |
|---|---|---|
| `stats` | `total_commands_processed` | Total commands processed since counter start |
| `stats` | `instantaneous_ops_per_sec` | Estimated recent commands/s near observation time |
| `stats` | `total_net_input_bytes` | Network input bytes recorded by Redis |
| `stats` | `total_net_output_bytes` | Network output bytes recorded by Redis |
| `stats` | `keyspace_hits` | Key lookup hits recorded by Redis |
| `stats` | `keyspace_misses` | Key lookup misses recorded by Redis |
| `stats` | `evicted_keys` | Evicted key count |
| `stats` | `expired_keys` | Expired key count processed |
| `clients` | `connected_clients` | Active client connections |
| `memory` | `used_memory` | Memory allocated by Redis per allocator stats |
| `memory` | `used_memory_rss` | Resident memory reported by the OS |
| `cpu` | CPU time metrics | CPU usage by category |
| `commandstats` | `cmdstat_get`, `cmdstat_set`... | Per-command counts and execution times |
| `persistence` | `rdb_bgsave_in_progress`... | Snapshot/persistence status |

Exact field names vary by Redis version, platform, and managed provider. Rely on your instance's actual output.

### 12.1. Computing Throughput via Counter Deltas

Suppose:

```text
t0: total_commands_processed = 5,000,000
t1: total_commands_processed = 5,060,000
t1 - t0 = 10 seconds
```

Approximate rate:

```text
(5,060,000 - 5,000,000) / 10
    = 6,000 commands/s
```

Notes:

- Counters reset when Redis restarts.
- This rate includes all command types, including admin/monitoring commands and unrelated workloads.
- Redis Cluster spans multiple nodes; distinguish per-node rates and aggregate accurately.
- One pipeline can carry multiple Redis commands per network round trip.
- `commands/s` does not equal HTTP `requests/s`.

### 12.2. Limitations of `instantaneous_ops_per_sec`

This gives a near-real-time rate useful on dashboards, yet misses:

- How workload fluctuated over the last several minutes.
- P99 latency.
- How many business operations succeeded.
- Retry counts.
- Which commands consumed most CPU.

Combine it with counter deltas and application throughput rather than sizing capacity from a single instantaneous sample.

## 13. INFO commandstats: Which Commands Consume Server Time?

Example:

```redis
INFO commandstats
```

Output includes lines such as:

```text
cmdstat_get:calls=100000,usec=550000,usec_per_call=5.50
cmdstat_hgetall:calls=12000,usec=240000,usec_per_call=20.00
cmdstat_eval:calls=5000,usec=750000,usec_per_call=150.00
```

Values above are **illustrative only**.

- `calls`: number of recorded invocations.
- `usec`: total server execution microseconds as measured by Redis.
- `usec_per_call`: average server execution time per command type.

If `EVAL` shows high `usec_per_call`, inspect Lua scripts, data sizes, or multi-element loops. If `HGETALL` grows expensive, Hashes may be bloating and the app may be pulling unnecessary fields.

### 13.1. Why Can't usec_per_call Serve as p99?

`usec_per_call` is **average server execution time**, not a latency distribution. It reveals nothing about the slowest 1% of calls.

Seeing:

```text
cmdstat_get usec_per_call = 5.5 µs
```

does not prove:

```text
client GET p99 <= 5.5 µs
```

Clients still experience network transit, Redis queueing, serialization, and response handling—and server mean is not server p99 anyway.

### 13.2. Measuring Command Mix

Capture `calls` for each `cmdstat_*` before and after a fixed-duration load test, then compute deltas per type.

Example:

```text
GET       700,000
SET       100,000
HGETALL   120,000
EVAL       20,000
```

This mix verifies whether the test matched the intended workload. If 90% reads were expected yet 30% writes occurred, cache misses or another writer may be running more than anticipated.

Do not reset all counters in production just for a benchmark if doing so disrupts monitoring. **Taking deltas between two samples** usually suffices.

## 14. SLOWLOG: Finding Slow-Executing Commands on Redis Server

Redis exposes a slow log:

```redis
SLOWLOG LEN
SLOWLOG GET 10
```

Inspect the threshold:

```redis
CONFIG GET slowlog-log-slower-than
```

`slowlog-log-slower-than` is normally in **microseconds**. For instance, 10,000 µs equals 10 ms execution time when that setting applies.

**Important:** Slow log primarily captures **Redis server command execution time**, excluding client network wait or response delivery to Java.

If Spring reports `GET` taking 80 ms while `SLOWLOG` shows no `GET`s, latency may sit in:

- Network RTT.
- Connection acquisition.
- Client command queues.
- Java event loop / CPU / GC.
- Large responses / deserialization.
- Traffic routed to another node.
- Server-side waits/queues outside slowlog's measured execution slice.
- Threshold set too high, or log rotated/capped.

### 14.1. Should You Set the Slowlog Threshold Very Low?

Setting too low a threshold on high-traffic servers adds overhead and log churn. Changing `CONFIG SET slowlog-log-slower-than ...` should follow operational policy and run only where authorized.

Never turn on verbose diagnostic logging and forget to revert it in production.

### 14.2. `MONITOR` Is Not a Routine Benchmarking Tool

The command:

```redis
MONITOR
```

can inspect live Redis commands during targeted diagnostics, yet imposes significant overhead, adds network traffic, and risks exposing sensitive keys/payloads.

**Avoid running `MONITOR` continuously on production Redis**, especially at high command rates. To inspect command mixes, `INFO commandstats` and controlled tracing are usually better.

## 15. Redis LATENCY Monitoring: Observing Spikes

Redis latency monitoring commands:

```redis
LATENCY LATEST
LATENCY HISTORY <event>
LATENCY DOCTOR
```

Example:

```redis
LATENCY LATEST
LATENCY DOCTOR
```

Recorded events depend on enabling the monitor, threshold config, and Redis version. Inspect:

```redis
CONFIG GET latency-monitor-threshold
```

If latency monitoring is disabled or thresholded poorly, seeing zero events **does not prove the server had no spikes**.

### 15.1. Distinguishing LATENCY and SLOWLOG

| Tool | Primary Observation |
|---|---|
| `INFO commandstats` | Total counts and mean execution time per command |
| `SLOWLOG` | Commands whose execution time exceeded threshold |
| `LATENCY` | Internal Redis latency spikes/events when configured |
| Client timers | Round-trip observed from Java client |
| HTTP metrics | Real endpoint latency |
| Tracing | Request path and spans across dependencies |

Combine tools rather than substituting one for another.

### 15.2. Host-Level Intrinsic Latency

`redis-cli` supports measuring host intrinsic latency in appropriate environments. This measures background scheduling jitter of the host machine, not Spring Boot HTTP throughput.

Running host-level probes consumes CPU and requires access to the Redis host. Use only in test labs or per operational runbooks—never casually on busy production hosts.

## 16. Measuring Actual Key Size with MEMORY USAGE

Key command:

```redis
MEMORY USAGE product:123
```

Redis returns the memory bytes charged to that key/value under its memory accounting.

Try:

```redis
SET lab:tiny a
MEMORY USAGE lab:tiny

SET lab:larger "A longer text value used for memory measurement"
MEMORY USAGE lab:larger
```

Do not assume memory usage grows by the exact String byte difference. Redis uses allocator size classes, object encodings, and metadata.

### 16.1. For Nested Data Structures

Example:

```redis
HSET lab:profile name Alice city HCMC status ACTIVE
MEMORY USAGE lab:profile
```

For multi-element structures, `MEMORY USAGE` accepts:

```redis
MEMORY USAGE lab:profile SAMPLES 0
```

`SAMPLES 0` inspects/estimates across all nested elements per command semantics, which makes measurement **more CPU-intensive** on huge keys. Never bulk-scan large keys during peak hours without controlling impact.

Overhead formulas vary across Redis data types and encodings. Measure representative keys directly.

### 16.2. When a Key Does Not Exist

`MEMORY USAGE missing:key` does not report bytes for a non-existent key. When sampling, distinguish:

```text
Key does not exist
Key exists with empty value
Key had TTL and just expired
Key was evicted during measurement
```

Do not turn missing keys into `0 bytes` when averaging live data sizes, as that skews the distribution.

### 16.3. `MEMORY USAGE` Does Not Reflect Total Process RSS

The command reports Redis-accounted memory for one key. Summing `MEMORY USAGE` across keys does not automatically equal:

```redis
INFO memory -> used_memory_rss
```

because RSS also includes allocator overhead/fragmentation, unreturned OS pages, buffers, persistence/COW, and non-dataset structures.

For capacity planning, combine **per-key samples** with **instance-level memory metrics**.

## 17. Commands for Counting Logical Redis Data Sizes

Commands for inspecting logical sizes:

| Data Type | Command | Result |
|---|---|---|
| String | `STRLEN key` | String value byte count |
| Hash | `HLEN key` | Field count |
| List | `LLEN key` | Element count |
| Set | `SCARD key` | Member count |
| Sorted Set | `ZCARD key` | Member count |
| Stream | `XLEN key` | Entries currently in Stream |
| Any key | `TYPE key` | Data type |
| Expiration | `TTL`/`PTTL` | Remaining lifetime or status code |

Example:

```redis
SET lab:json "{\"name\":\"Alice\",\"city\":\"HCMC\"}"
STRLEN lab:json
MEMORY USAGE lab:json
```

`STRLEN` omits key overhead, expiration metadata, and process memory.

With Hash:

```redis
HSET lab:hash name Alice city HCMC
HLEN lab:hash
MEMORY USAGE lab:hash
```

`HLEN` counts fields, **not bytes**. A 2-field Hash with 10-byte values differs vastly from a 2-field Hash with 1 MiB values.

### 17.1. A Stream Holds More Metadata Than Entry Payloads

A Stream with consumer groups maintains:

```text
Stream entries
Consumer groups
Last-delivered IDs
Pending Entries List
Consumer metadata
```

`XLEN` counts entries currently in the Stream; it measures neither total RAM bytes nor pending messages.

To understand Stream workloads, inspect:

```redis
XLEN orders:events
XINFO STREAM orders:events
XINFO GROUPS orders:events
XPENDING orders:events workers
MEMORY USAGE orders:events
```

With many groups or large PELs, multiplying `average payload bytes * XLEN` underestimates real memory.

## 18. Instance-Level Redis Memory Metrics

Run:

```redis
INFO memory
MEMORY STATS
```

Key metrics:

| Metric | Conceptual Meaning |
|---|---|
| `used_memory` | Bytes allocated by Redis allocator for tracked purposes |
| `used_memory_human` | Human-readable form of `used_memory` |
| `used_memory_rss` | Resident Set Size reported by the OS for the process |
| `used_memory_peak` | Peak `used_memory` recorded |
| `used_memory_dataset` | Estimated portion used by the dataset |
| `used_memory_overhead` | Overhead tracked by Redis |
| `mem_fragmentation_ratio` | Fragmentation ratio as calculated by Redis |
| `maxmemory` | Configured Redis memory cap if set |
| `mem_not_counted_for_evict` | Certain memory excluded from eviction triggers |
| `allocator_*` metrics | Allocator statistics if supported by Redis version |

Exact metric names and definitions vary across versions and builds.

### 18.1. `used_memory` Differs from RSS

```text
used_memory = 5 GiB
RSS         = 7 GiB
```

This does not automatically mean 2 GiB of "leaked data." The gap can reflect fragmentation, allocator behavior, overhead, or system components.

Inspect allocator metrics, workload shifts, prior peaks, and memory trends over time.

### 18.2. Memory Fragmentation

Allocators assign blocks in discrete size classes, so heavy churn can leave fragmented memory. After deleting many keys, process RSS may not drop immediately.

If `MEMORY USAGE` on keys is modest yet RSS stays high, analyze fragmentation/allocator behavior rather than just trying to shorten JSON.

### 18.3. Copy-on-Write and Persistence

During `BGSAVE` or AOF rewrite, copy-on-write (COW) can noticeably raise memory consumption. Provision headroom for this if your workload combines heavy writes with persistence snapshots.

**Never size production Redis RAM right at 100% of summed `MEMORY USAGE` samples**, because buffers, fragmentation, COW, OS usage, and operational spikes also require memory.

## 19. Redis Memory by Data Type: No Universal Multiplier

Compare three ways to store the same data:

**Option A — a JSON String:**

```redis
SET user:42 "{\"name\":\"Alice\",\"city\":\"HCMC\",\"tier\":\"GOLD\"}"
```

**Option B — a Redis Hash:**

```redis
HSET user:42 name Alice city HCMC tier GOLD
```

**Option C — multiple String keys:**

```redis
SET user:42:name Alice
SET user:42:city HCMC
SET user:42:tier GOLD
```

All three satisfy basic read/write needs, yet consume different memory:

- JSON repeats field names inside payloads and adds parse/serialize CPU.
- Hashes store fields/values internally and use compact encodings for small entries depending on Redis version.
- Separate keys incur per-key dictionary entries, key-name storage, and expiration/index metadata.
- Updating one field under Option A requires rewriting the whole JSON String.
- A Hash normally uses key-level TTL across common APIs; separate keys support independent TTLs.
- JSON Strings may compress well, yet add CPU and break partial field updates.

**Never conclude "Hash always uses less RAM than JSON" universally.** Measure all options on the same dataset, Redis version, and equivalent operations.

### 19.1. OBJECT ENCODING

Redis provides:

```redis
OBJECT ENCODING user:42
```

to inspect a key's internal encoding.

Encodings shift based on element counts, value sizes, and Redis version, explaining why growing from dozens to hundreds of fields can suddenly change memory or latency.

Never write application code that depends on a specific internal encoding as a stable contract across Redis versions.

### 19.2. Choose Data Types by Access Pattern, Not RAM Alone

If an API usually reads the whole object, a JSON String can be simplest. If it updates individual fields frequently, a Hash may fit better. If membership tests are needed, a Set matches the semantics.

A benchmark comparing only memory while ignoring CPU, command counts, serialization, and p99 latency is incomplete for picking a data type.

## 20. Measuring Data Size with a Representative Sample

A real dataset often follows a skewed distribution:

```text
80% product JSON:     0.5-2 KiB
15% product JSON:     2-8 KiB
 5% product JSON:     8-64 KiB
```

Measuring only the smallest product skews RAM projections badly. Sample deliberately across:

- Short and long keys.
- Small, medium, and large payloads.
- Few-field and many-field Hashes.
- Lists/Sets/ZSets with varying cardinalities.
- Keys with and without TTLs.
- Repository entities with indexes and shadow copies.
- Streams with groups and PELs.
- Hot keys and cold keys.
- Large and small tenants.

### 20.1. Bucketed Statistics

Example sample of 10,000 Redis keys:

| Group | Sample Keys | Payload p50 | Payload p99 | Redis memory/key p50 | Redis memory/key p99 |
|---|---:|---:|---:|---:|---:|
| Product cache | 4,000 | Measure | Measure | `MEMORY USAGE` | `MEMORY USAGE` |
| Session | 2,000 | Measure | Measure | `MEMORY USAGE` | `MEMORY USAGE` |
| Cart | 2,000 | Measure | Measure | `MEMORY USAGE` | `MEMORY USAGE` |
| Indexes | 1,000 | Measure | Measure | `MEMORY USAGE` | `MEMORY USAGE` |
| Streams | 1,000 | Measure | Measure | `MEMORY USAGE` | `MEMORY USAGE` |

This table is a **measurement template to fill in**, not hypothetical benchmark results.

### 20.2. Weighted Average

Given key groups A, B, C with counts \(N_A,N_B,N_C\) and average memory/key \(m_A,m_B,m_C\), estimated dataset memory is:

\[
M_{\text{dataset}} \approx N_A m_A + N_B m_B + N_C m_C
\]

Also add:

- Instance overhead not attributable to individual keys.
- Memory fragmentation.
- Connection buffers.
- Replication/persistence buffers.
- COW reserve.
- Headroom for traffic bursts, data growth, and failover.
- Redis Cluster slot/key skew across primaries.

If sampling is non-random or unrepresentative, even the right formula yields wrong estimates.

### 20.3. Capacity Calculation Example

Suppose an expected workload has:

```text
1,000,000 keys
Measured average MEMORY USAGE = 1,200 bytes/key
```

Sample-based dataset estimate:

```text
1,000,000 x 1,200 bytes = 1,200,000,000 bytes
```

About 1.2 GB decimal, **before adding process overhead, fragmentation, and headroom**.

Never take this number and provision a node with exactly 1.2 GB RAM. Measure `used_memory`, RSS, and peak usage under load while reserving room for growth and failovers.

## 21. Measuring Many Keys Without Overloading Production Redis

A safe way to sample keys:

```redis
SCAN 0 MATCH product:* COUNT 100
```

Redis returns a **new cursor** and a batch of keys. Continue passing the cursor until it returns `0` to finish a scan pass.

Example:

```redis
SCAN 0 MATCH product:* COUNT 100
SCAN <returned-cursor> MATCH product:* COUNT 100
```

`COUNT` hints at work/sample batch size, **not a guarantee of exactly 100 keys**. `SCAN` can return duplicates while data mutates mid-scan; factor that into statistical summaries.

### 21.1. Never Use KEYS * on Large Production Keyspaces

Avoid:

```redis
KEYS *
```

on a large live keyspace serving traffic, as it scans vast keyspaces in one command and degrades latency.

Use rate-limited `SCAN` or measure against a copied/anonymized test dataset.

### 21.2. Cluster Has Multiple Nodes

In Redis Cluster, keyspace scans and memory measurements must span all primaries. Results from one node do not cover the whole cluster.

Collect:

```text
Per primary:
  number of keys
  used_memory
  used_memory_rss
  ops/s
  command distribution
  latency
  top key/payload distributions
```

Then aggregate cluster-wide while tracking **max primary load**, because one overloaded primary raises p99 on its slots even when total Cluster CPU has headroom.

### 21.3. Sampling MEMORY USAGE Has a Cost

On huge keys—especially nested structures—`MEMORY USAGE ... SAMPLES 0` can take noticeable time. Instead:

- Start with default sampling.
- Cap keys sampled per minute/day.
- Run on staging with representative data.
- Prioritize finding top categories/size buckets.
- Deeply inspect only selected outliers.
- Never scan entire nodes during peak traffic.

Capacity planning needs representative statistics, **not exact `MEMORY USAGE` of every key every second**.

## 22. Redis Cache Hit Rate and How to Interpret It

Spring Cache with Redis typically branches two ways:

```text
Request product:42
       |
       v
Redis GET
   |
   +-- Hit  -> return cached value
   |
   +-- Miss -> call database / origin service
                |
                v
              SET Redis
```

Application-level hit rate:

\[
\text{Hit rate} =
\frac{\text{cache hits}}
{\text{cache hits} + \text{cache misses}}
\]

A high hit rate usually reduces origin load, yet must be evaluated alongside:

- Hit latency.
- Miss latency.
- Database latency.
- Cache `SET` frequency.
- TTLs and evictions.
- Payload sizes.
- Invalidations.
- Stale data risk.

### 22.1. Does `keyspace_hits` Equal Application Cache Hit Rate?

In `INFO stats`:

```redis
keyspace_hits
keyspace_misses
```

reflect Redis's global key-lookup hit/miss counters, spanning all applications and key types sharing that instance.

Therefore:

```text
Redis global hit ratio != necessarily Spring Cache hit ratio
```

If one Redis instance serves sessions, counters, carts, and caches, emit metrics at the Spring Cache or service tier to measure `products` independently.

### 22.2. Hit Rate Does Not Tell the Full Cost

A 99% cache hit rate where each hit returns 500 KiB can still burn huge network/deserialization resources. An 80% hit rate with 100-byte payloads and a fast database may perform better overall.

Measure together:

```text
Hit rate
Hit p95/p99
Miss p95/p99
Payload bytes
Redis memory/key
Database queries/s
HTTP latency
```

Never chase "100% hit rate" if stretching TTLs pushes data staleness past acceptable limits.

### 22.3. Spring Cache Abstraction Adds Overhead

A `@Cacheable` call also passes through:

- Proxy / interceptor.
- Cache key generation.
- Redis key prefixing.
- Value serialization.
- Null-caching handling.
- Cache configuration TTLs.
- Database load on misses.

It is normal for a raw `GET product:42` benchmark to look faster than a `@Cacheable` endpoint. Measure the entire application rather than blaming Redis Server for the gap.

## 23. Spring Data Redis Repositories and Indexes Can Significantly Increase Memory

A Redis Repository can maintain:

```text
Entity Hash
Secondary index Sets
Index bookkeeping metadata
TTL metadata
Shadow/phantom copies when enabled
```

For example, an entity with three `@Indexed` fields can create multiple Redis keys and secondary Set members beyond the primary entity Hash.

Thus, when budgeting RAM:

```text
Entity JSON/Hash size
    + secondary indexes
    + metadata
    + expiration/shadow copies
```

can far exceed the byte size of one DTO.

### 23.1. Measure the Right "Storage Unit"

If one business entity generates four Redis keys, never run:

```redis
MEMORY USAGE entity:42
```

and multiply by entity count. Identify all key families tied to the entity and its index structures.

Likewise, deleting an entity updates multiple keys. Memory reclamation may not show immediately in RSS due to allocator fragmentation.

### 23.2. Database Query or Redis Index?

Secondary indexes enable querying attributes in Redis, yet add:

- Memory overhead.
- Write amplification.
- Index update cost.
- Cleanup risks around TTLs/keyspace notifications.
- Redis Cluster constraints if indexes touch cross-slot keys.

Rare queries served well by the primary database rarely justify extra Redis indexes. Base the trade-off on **read latency + write cost + RAM + correctness**, not just `findBy...` speed in a microbenchmark.

## 24. Benchmarking Redis: Tools and Limits

Redis provides `redis-benchmark`, useful for measuring command performance under controlled parameters.

Example on a test Redis instance:

```bash
redis-benchmark -h 127.0.0.1 -p 6379 -n 100000 -c 50 -t get,set
```

Common flags:

- `-h`: Redis host.
- `-p`: port.
- `-n`: total benchmark requests.
- `-c`: concurrent connections.
- `-t`: command list to benchmark.

With a configured payload size and quiet output:

```bash
redis-benchmark -h 127.0.0.1 -p 6379 \
  -n 100000 -c 50 -d 1024 -t get,set -q
```

`-d 1024` sets payload size for applicable commands. Exact syntax and output vary slightly across `redis-cli`/`redis-benchmark` versions; check `redis-benchmark --help`.

**Commands above are test instructions only, not benchmark results.** Never run heavy benchmarks against production Redis without an approved load plan and authorization.

### 24.1. Concurrency Testing Differs from Payload Testing

A run with:

```text
-c 1, payload 100 B
```

is not directly comparable to:

```text
-c 200, payload 32 KiB
```

because both concurrency and payload volume changed.

Vary **one factor at a time** when diagnosing what drives latency up or down.

### 24.2. `-P` Pipelining Can Dramatically Change Throughput

Example:

```bash
redis-benchmark -h 127.0.0.1 -p 6379 \
  -n 100000 -c 50 -P 16 -t get,set -q
```

`-P 16` pipelines commands in the benchmark. Pipelining cuts network waits across multiple commands, yet **does not mean the real app can pipeline 16 commands per request**.

If production requests send one `GET` and wait for its result before computing the next step, a `-P 16` benchmark shows flattering throughput that does not reflect reality.

### 24.3. `redis-benchmark` Does Not Measure Spring DTO Serialization

`redis-benchmark` skips:

- Your application's Jackson serializer.
- Spring Cache key generators.
- HTTP server security/filters.
- R2DBC/JDBC database miss paths.
- Custom Lua business scripts unless explicitly benchmarked.
- Spring retries/interceptors.
- Application connection-pool waits.
- DTO mapping and response rendering.

It primarily explores Redis/connection/command limits at the command level. Always add load tests **through real Spring endpoints**.

## 25. Designing a Load-Test Matrix

A test configuration matrix varies parameters deliberately:

| Dimension | Values to Test |
|---|---|
| Payload bytes | Realistic small / median / p95 / p99 |
| Read/write ratio | 95/5, 80/20, 50/50 per workload |
| Cache hit rate | Near 100%, production ratio, cold start |
| Concurrency | 1, 10, 50, 100, ... per system |
| Request rate | Step upward to SLO limits |
| Key distribution | Uniform, hot-key / Zipf-like |
| TTL | No TTL, typical TTL, simultaneous expiry |
| Redis structure | String/Hash/Set/ZSet/Stream |
| Client type | Blocking `RedisTemplate`, reactive API |
| Network | Same host, same zone, cross zone, TLS |
| Redis topology | Standalone, Sentinel, Cluster |
| Persistence | RDB/AOF matching production |
| Failure modes | Healthy, retries, reconnects, failover |
| Results | p50/p95/p99, throughput, error rate, memory, CPU |

Do not run every permutation upfront. Start from a baseline scenario and add complexity around the highest risks.

### 25.1. Warm-Up

Initial execution involves:

- JIT compilation / JVM class loading.
- Connection establishment.
- TLS handshakes.
- Empty caches.
- Micrometer initialization.
- JSON serializer caches.
- Unstabilized OS/network state.

These skew measurements compared to steady state. Keep a dedicated warm-up phase excluded from main metrics, and test cold-start separately if your service must absorb traffic immediately on restart.

**Cold-start is not bad data**: it is a distinct operational scenario to measure rather than filter away completely.

### 25.2. Separating Cold vs Warm Cache

**Warm cache:**

```text
Most keys present.
GET -> cache hit.
```

**Cold cache:**

```text
Many keys absent.
GET -> miss -> DB -> SET.
```

Benchmarking only warm cache underestimates risks after Redis restarts, evictions, or redeploys. Benchmarking only cold cache underestimates steady-state capacity.

Measure both whenever caching is critical.

### 25.3. Key Distribution: Hot Keys

In production, certain keys receive disproportionate traffic:

```text
product:popular
stock:flash-sale
config:global
```

A uniform-random benchmark misses:

- Hot slots in Redis Cluster.
- Contention updating a shared counter.
- Large responses on hot keys.
- Cache stampedes when hot keys expire.
- Lua script CPU on hot aggregates.

Match test workloads to actual key popularity skew rather than uniform randomness alone.

## 26. Coordinated Omission: Benchmarks Can Miss Bad Latency

A frequent bias in load testing is **coordinated omission**: the generator paces new requests based on prior requests finishing. When the server stalls, the generator slows down too, recording far fewer slow requests than an independent arrival stream would experience.

Example:

```text
True target: steady 1,000 requests/s.
Server pauses for 1 second.
```

In a closed-loop model, workers block waiting for replies and stop issuing arrivals during the pause. The report records a few slow requests while omitting the backlog that 1,000 independent arrivals/s would build.

Therefore, clarify whether your load generator is:

- **Closed-loop / concurrency-based:** each virtual user sends the next request only after the previous finishes.
- **Open-loop / arrival-rate-based:** dispatches requests on a target arrival schedule regardless of prior completions.

Neither model is universally wrong: closed-loop fits think-time user models, while open-loop measures resilience against external arrival rates. Match the **intended load model** and never over-claim from p99 numbers masked by coordinated omission.

### 26.1. Report Both Actual Arrival Rate and Completion Rate

Under heavy load, record:

```text
Requested arrival rate
Actual arrival rate
Completed responses/s
Timed-out requests
In-flight / queue length
Latency distribution
```

If the generator cannot even sustain the requested arrival rate, the test did not actually exercise the target load.

### 26.2. The Benchmark Client Itself Can Bottleneck

An under-provisioned load generator running out of CPU or network cannot sustain rates or adds fake client latency. Monitor:

- Benchmark machine CPU/RAM.
- Network bandwidth.
- TLS handshakes / session reuse.
- Threads / connections.
- Open files / socket limits.
- Generator errors/timeouts.

Never conclude Redis hit its ceiling if the load generator itself maxed out its CPU.

## 27. Reading the Throughput–Latency Curve

Step load upward incrementally:

```text
Load level 1:  500 RPS
Load level 2: 1000 RPS
Load level 3: 1500 RPS
Load level 4: 2000 RPS
Load level 5: 2500 RPS
```

At each step, record:

```text
Actual completed RPS
p50, p95, p99
error/timeout rate
Redis commands/s
Redis CPU/RSS
App CPU/GC
Network bytes/s
Connection queue
DB miss rate
```

A typical curve looks like:

```text
Latency
  ^
  |                             /   overload
  |                          __/
  |                       __/
  |                  ____/
  |            _____/
  |___________/
  +--------------------------------> Throughput
             stable    knee
```

"Peak throughput" is rarely a safe operating point. If p99 crosses the SLO at a lower level, usable capacity is bounded by the **SLO**, not the maximum RPS printed before collapse.

### 27.1. Saturation Does Not Happen Only in Redis CPU

A Spring instance can saturate before Redis due to:

- HTTP request thread limits.
- Blocking connection pools.
- GC pauses.
- JSON serialization.
- Database cache-miss paths.
- Network stack limits.
- Application lock contention.
- Downstream dependency limits.

If Redis CPU is low while HTTP p99 spikes, check the other layers before scaling Redis.

## 28. Pipelining and Batching in Spring Data Redis

When issuing multiple independent commands, **pipelining** cuts network round trips.

Example with `StringRedisTemplate`:

```java
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.core.StringRedisTemplate;

public List<Object> batchGet(
        StringRedisTemplate redis,
        List<String> keys) {

    List<Object> replies = redis.executePipelined(connection -> {
        for (String key : keys) {
            byte[] rawKey =
                key.getBytes(StandardCharsets.UTF_8);

            connection.stringCommands().get(rawKey);
        }

        return null;
    });

    return replies;
}
```

This conceptual example uses raw commands on `StringRedisTemplate` with UTF-8 keys; exact callback signatures and serialization for `executePipelined` must match your Spring Data Redis version, connection factory, and configured serializers.

When fetching multiple String keys in the same slot, `multiGet`/`MGET` is another option. In Redis Cluster, multi-key or batched commands must account for hash-slot rules and driver support.

### 28.1. What Does Pipelining Improve?

Without pipelining:

```text
GET k1 -> wait for reply
GET k2 -> wait for reply
GET k3 -> wait for reply
...
```

With pipelining:

```text
GET k1
GET k2
GET k3
... sent consecutively
  |
  v
Collect corresponding replies
```

Potential gains:

- Fewer network waits between commands.
- Higher commands/s.
- Faster total batch completion in RTT-bound workloads.

Trade-offs:

- More commands simultaneously in flight.
- Redis/client must buffer replies.
- Large response payloads raise memory/network pressure.
- One slow command can delay subsequent replies in the pipeline.
- Per-command error handling is trickier.
- Does not create an atomic transaction.
- High concurrency + deep pipelines can worsen p99.

### 28.2. Measure Pipelines by Both Batch and Command

Do not report only:

```text
Pipeline 1000 GETs took 50 ms.
```

Record:

```text
Batch completion latency
Number of commands in batch
Batch size distribution
Per-command outcome
Total bytes sent/received
Memory peak
p95/p99 latency of concurrent interactive requests
```

A pipeline boosting aggregate throughput at the expense of user-facing p99 can still be a bad trade-off.

### 28.3. Pipelining Cannot Solve Dependent Commands

If the second command depends on the first command's output, pipelining both before knowing the first result breaks business logic. For atomic read-modify-write, use an appropriate atomic Redis command, Lua script, or same-slot transaction instead of plain pipelining.

## 29. Redis Cluster: Measuring Per-Node, Per-Slot, Per-Command

Redis Cluster shards keys across hash slots. Even with plenty of cluster-wide CPU, one primary can overload from a hot slot.

```text
Cluster:
    Primary A: 90% CPU, high GET p99
    Primary B: 25% CPU
    Primary C: 30% CPU
```

A cluster-wide average CPU dashboard hides Primary A's saturation.

### 29.1. Measure Every Primary

On each primary, track:

```text
instantaneous_ops_per_sec
used_memory / RSS
network input/output
connected_clients
cmdstat_* mix
SLOWLOG / latency
evicted_keys
replication/failover status
```

Aggregations must preserve **max node / hot slot** signals rather than averaging across all nodes.

### 29.2. Hash Tags and Hot Slots

Keys:

```text
cart:{c-101}:items
cart:{c-101}:total
```

share a slot, convenient for atomic multi-key operations. Yet putting all keys under `{global}` defeats Redis Cluster distribution.

Uniform-key tests miss this flaw. Always benchmark with your real key-naming rules and tenant/aggregate skew.

### 29.3. MOVED/ASK and Topology Refresh

During Cluster resharding or failovers, clients see redirects or trigger topology refreshes, elevating tail latency. Steady-state Cluster benchmarks miss slot-migration overhead.

If SLOs must hold during failovers or resharding, **test failure scenarios separately** instead of burying them inside steady-state averages.

### 29.4. Multi-Key Commands on Cluster

`MGET`/`MSET`, Lua scripts, and multi-key transactions carry same-hash-slot constraints. Operations that succeed on standalone fail with `CROSSSLOT` on Cluster.

This is a **correctness/configuration** constraint, not a latency tweak. Track error rates alongside throughput.

## 30. Redis Streams: Throughput Is Not Just XADD/s

For Redis Streams, track at least three distinct rates:

```text
Producer writes:
    XADD records/s

Consumer reads:
    XREADGROUP records/s

Processing:
    handler success + XACK records/s
```

If producers hit 20,000 entries/s while consumers process and ACK 10,000 entries/s, lag and pending entries pile up. High `XADD` speed alone does not prove the processing pipeline keeps up.

Observation commands:

```redis
XLEN orders:events
XINFO STREAM orders:events
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events orders-workers
XPENDING orders:events orders-workers
```

### 30.1. Lag and Pending Are Two Different Backlogs

- **Group lag:** entries not yet delivered to the consumer group (where tracked).
- **Pending:** entries delivered to consumers but not yet ACKed.

Seeing:

```text
Group lag = 0
Pending   = 100000
```

does not mean work is caught up—consumers may be holding huge numbers of unACKed entries.

### 30.2. Stream Size Is More Than Payloads

Multiple consumer groups and large PELs increase memory overhead. Measure:

```redis
MEMORY USAGE orders:events
XLEN orders:events
XINFO GROUPS orders:events
```

and watch total Redis memory as group/consumer counts grow.

### 30.3. Stream Batching Trade-Offs

Increasing `COUNT` on reads cuts round trips, yet:

- Increases concurrent pending entries.
- Increases handler memory consumption.
- Extends latency for items at the end of a batch.
- Enlarges work needing recovery if a consumer crashes.
- Can lift throughput when batches process efficiently.

Measure **records/s, acknowledgment latency, pending growth, handler p99, and memory** together.

### 30.4. Do Not Ignore Retention

`XADD ... MAXLEN`, `XTRIM`, and history limits cap memory yet can delete payloads slow consumers still need to retry.

Never shrink memory via aggressive trimming if business rules require replay or PEL recovery.

## 31. Redis Pub/Sub: Throughput Must Account for Fan-Out

With Pub/Sub:

```text
1 Publisher
  |
  +--> PUBLISH 1000 messages/s
           |
           +--> Subscriber A
           +--> Subscriber B
           +--> Subscriber C
           +--> Subscriber D
```

The publisher sends 1,000 publications/s, while Redis serves multiple outbound streams via **fan-out** to subscribers.

Metrics to track:

```text
Published messages/s
Number of subscribers
Redis network output bytes/s
Subscriber receive rate
Subscriber drops/reconnects
Handler latency
WebFlux/SSE backpressure and buffering
```

`PUBLISH` returns a subscriber delivery count per Redis semantics, **not an ACK that business handlers processed the message**.

Testing with one subscriber when production has thousands of clients completely misses network and output-buffer pressure.

### 31.1. Pub/Sub Is Not a Job Queue Benchmark

Redis Pub/Sub retains no backlog or replay by default. When every message must be processed reliably, raw Pub/Sub throughput does not measure reliability. Choose Redis Streams or an appropriate broker when ACK/retry semantics are required.

## 32. How Do Pipelining, Batching, and Serialization Affect Performance?

A fair comparison keeps data and work equivalent:

| Approach | Redis Commands | Java CPU | Network | Memory |
|---|---|---|---|---|
| N sequential `GET`s | N | N decodes | ~N round trips | Low in-flight |
| N pipelined `GET`s | N | N decodes | Fewer waits between commands | N replies buffered |
| One same-slot `MGET` | 1 | Decode N values | One multi-key command | Batch response |
| Large JSON String | Fewer keys | Parse/serialize whole object | JSON bytes | Redis String overhead |
| Redis Hash fields | One key, many fields | Field mapping | Depends on HGET/HMGET/HGETALL | Hash encoding |
| Server-side Lua | One script call | Fewer client round trips | Keys/args + reply | Script CPU on Redis |

Command count alone never picks the fastest option. One `HGETALL` on a huge Hash can cost far more than several `HGET`s fetching only needed fields. One long Lua script can stall the Redis event loop enough to spike tail latency across unrelated clients.

## 33. Payload Compression: Fewer Bytes, Higher CPU

Compressing values can reduce:

- Network bytes sent/received.
- Redis memory for compressible values.

Yet increases:

- Java serialize/compress CPU.
- Decompression CPU on reads.
- Access latency.
- Byte copying / allocation overhead.
- Loss of direct partial-field access on binary blobs.

Benchmark design:

```text
A. Plain JSON
B. Compressed JSON
```

Hold constant:

```text
DTO
Key distribution
Read/write mix
Concurrency
TTL
Dataset count
Redis topology
```

For each option, measure:

```text
Raw payload bytes
Compressed payload bytes
Compression ratio
Serialize/compress p95/p99
Redis GET/SET p95/p99
End-to-end HTTP p95/p99
Redis MEMORY USAGE
JVM and Redis CPU/RSS
```

For a 200-byte JSON payload, compression framing can actually make it larger. For a 100 KiB payload across a distant network, compression can help substantially. **Never enable compression based purely on algorithm reputation.**

### 33.1. Formats Must Be Versioned

When migrating from plain JSON to compressed binary, readers must know which format is stored. Use schema versions, magic headers, or versioned key namespaces.

Never swap serializers in place expecting old cache entries to decode cleanly; during rollout, deserialization errors turn into cache misses and distort benchmarks.

## 34. Setting TTL Affects Throughput and RAM

TTL governs how long a key lives:

```redis
SET product:42 payload EX 600
```

Short TTL:

- Reduces stale-data window.
- Can reduce live key count.
- Increases cache misses and cache rebuild writes.
- Can raise database load.
- If many keys expire together, triggers miss bursts.

Long TTL:

- Raises hit rate in many workloads.
- Can increase RAM usage.
- Increases stale-data risk.
- Reduces recomputation frequency.

**Never tune TTL purely for RAM while ignoring database throughput and HTTP p99.**

### 34.1. Cache Stampede

If a hot key expires, 500 concurrent requests can miss together and hit the database.

```text
Hot key expires
     |
     +--> 500 concurrent requests
               |
               +--> GET miss
               +--> Database read x 500
               +--> Multiple Redis SETs
```

Redis hit rate drops, HTTP p99 jumps, and DB CPU spikes—even though Redis command execution stayed fast.

Mitigations to benchmark:

- TTL jitter.
- Per-key single-flight.
- Pre-warming.
- Stale-while-revalidate if business rules permit.
- Cache loader concurrency limits.
- Negative caching with appropriate TTL/consistency.

### 34.2. What Is TTL Jitter?

Instead of giving every key an exact 600-second TTL:

```text
TTL = 600s ± a controlled offset
```

to prevent synchronized expirations.

However, jitter is unsuitable when TTL enforces a strict security or legal deadline such as OTP expiry. Separate **cache TTLs** from **business deadlines**.

## 35. Performance Testing with Redis Persistence Enabled

If production runs RDB/AOF persistence, load tests should match it, because:

- `BGSAVE` triggers fork and copy-on-write (COW).
- AOF adds disk I/O and fsync/rewrite overhead.
- Write-heavy workloads amplify COW memory growth.
- Disk pressure induces latency spikes.
- Redis restarts/restores drop warm caches or introduce startup load.

A benchmark on persistence-disabled test Redis can diverge dramatically from production.

Monitor:

```redis
INFO persistence
INFO memory
```

alongside `INFO stats`, client latency, and OS disk/CPU metrics.

### 35.1. Watching p99 During BGSAVE

Compare two windows:

```text
Period A: steady load, no BGSAVE active
Period B: steady load, BGSAVE triggered per test procedure
```

Compare HTTP/Redis client p99, Redis fork latency, COW growth, and disk throughput. Never rely on full-test averages that smooth away short spikes.

### 35.2. Test Durability Must Match Production Durability

Never optimize by disabling AOF/BGSAVE in production just because benchmarks ran faster when business requirements demand data recovery.

Performance is only one constraint: correctness, durability, RPO/RTO, and availability often outweigh a few extra percent of throughput.

## 36. Latency During Connection Timeouts/Retries

A Redis operation with a 2-second timeout and 3 retries can stall an HTTP request for **several seconds**, even when average Redis server execution is microseconds.

Example:

```text
Attempt 1 timeout: 2s
Backoff:           0.2s
Attempt 2 timeout: 2s
Backoff:           0.4s
Attempt 3 success: 0.01s

Total service latency: ~4.61s
```

This calculation is illustrative; check actual deadlines, cancellation, and retry counts.

Measure separately:

```text
Per-attempt Redis latency
Number of retries
End-to-end operation latency
Timeout rate
Unknown outcomes
Connection reconnect duration
```

Timing only the final successful attempt reports artificially low Redis latency while users waited seconds.

### 36.1. Never Blindly Retry Non-Idempotent Writes

Commands like `INCR`, `LPUSH`, and `XADD *` may have executed before the reply was lost. Retrying doubles side effects.

When testing retry performance, separate:

- Pre-send failures.
- Server-executed calls with lost replies.
- Reconnects/failovers.
- Idempotency keys/receipts.
- Whether business side effects already committed.

A benchmark hitting high throughput by retrying blindly while corrupting business state **fails acceptance**.

## 37. A Repeatable End-to-End Benchmarking Workflow

### Step 1 — Define the Question

Example:

> "Can the Spring Boot service sustain 2,000 RPS with 90% product cache hits, JSON p99 under 8 KiB, HTTP p99 under 60 ms, and no abnormal Redis evictions?"

Make the goal a **measurable hypothesis**, not "see if Redis is fast."

### Step 2 — Record the Environment Configuration

Document:

```text
Spring Boot version
Spring Data Redis version
Lettuce version
JDK/GC
Redis version
Redis topology
Redis host CPU/RAM
Network/TLS
Serializer
TTL
Connection configuration
RDB/AOF settings
Dataset size
```

Without this record, comparing Test A and Test B is unreliable.

### Step 3 — Prepare a Representative Dataset

Seed data matching:

```text
Production-scale key count
Production-like payload size distribution
Production key prefixes/tags
TTLs and fraction of keys with TTL
Hot keys
Repository indexes/Streams if used
```

Using 100 keys in testing when production holds 100 million keys misses memory pressure and hot-key behavior.

### Step 4 — Define Workload Mix

Example:

```text
GET product: 70%
GET session: 15%
UPDATE cart: 10%
XADD event: 5%
```

Illustrative only—substitute request/Redis command mixes from real telemetry.

### Step 5 — Run Warm-Up

Warm up the app/Redis clients, JIT, and preloaded caches per scenario. Record warm-up separately, then run steady-state long enough to observe p99 reliably.

### Step 6 — Ramp Load in Controlled Steps

Step through levels long enough at each tier to stabilize or reveal growing backlogs:

```text
25% target
50% target
75% target
100% target
125% target (if test environment permits)
```

Never push shared production Redis to 125% target without explicit authorization and safety controls.

### Step 7 — Collect Metrics Simultaneously

Record:

```text
HTTP p50/p95/p99 + error rate
App Redis call p50/p95/p99
Lettuce/driver command timing if available
Redis INFO stats/commandstats
Redis CPU/RSS/network
GC pauses
Payload bytes/memory usage distributions
DB load on cache misses
```

Align timestamps and measurement windows to correlate events cleanly.

### Step 8 — Identify the Bottleneck

Example:

```text
HTTP p99 spikes sharply
App Redis timer stays steady
DB query latency climbs
=> root cause is likely cache misses/DB, not Redis execution.
```

Or:

```text
HTTP p99 and Redis client p99 climb together
SLOWLOG shows no slow commands
Network RTT rises
=> inspect network/client queue/connections.
```

Or:

```text
Lua/EVAL usec_per_call climbs
Redis CPU spikes
Same hot slot
=> inspect script and data model.
```

### Step 9 — Change One Variable at a Time

For instance, test replacing a JSON String with a Hash, or increasing pipeline batch size from 1 to 16, then re-measure the exact same workload.

Changing serializers, connection configs, TTLs, and Redis instance size together hides which change actually helped.

### Step 10 — Write the Report and Guardrails

Report:

```text
Hypothesis
Environment
Dataset
Workload
Measured metrics
Confidence/limitations
Decision
Rollback plan
Post-deploy monitoring
```

Never write just "30% faster" while omitting p99, error rates, CPU, and RAM.

## 38. Performance Report Template

A table you can use directly:

| Metric | Baseline | Candidate | Conditions |
|---|---|---|---|
| Actual RPS | Fill result | Fill result | Same arrival rate |
| p50 HTTP (ms) | Fill | Fill | Same workload |
| p95 HTTP (ms) | Fill | Fill | Same workload |
| p99 HTTP (ms) | Fill | Fill | Same workload |
| HTTP error rate | Fill | Fill | Same deadline |
| Redis GET p99 (ms) | Fill | Fill | Same method/metric |
| Redis ops/s | Fill | Fill | Per node + cluster |
| Cache hit ratio | Fill | Fill | Split product/session |
| Value p50/p99 bytes | Fill | Fill | Serialized bytes |
| MEMORY USAGE/key p50 | Fill | Fill | Representative samples |
| Redis used_memory/RSS | Fill | Fill | Post warm-up |
| Redis CPU peak | Fill | Fill | Same load |
| JVM CPU/GC pauses | Fill | Fill | Same JDK/GC |
| DB QPS | Fill | Fill | On cache misses |
| Stream pending/lag | Fill | Fill | If workers present |
| Observed bottleneck | Describe | Describe | From traces and counters |

Never enter estimates into measured columns. If a metric was not collected, write `NOT_MEASURED` instead of turning assumptions into results.

## 39. Common Mistakes When Measuring Performance

### 39.1. Measuring Only Average GET Latency

Averages hide tail latency, retries, GC pauses, and network spikes. Always track p50/p95/p99 and error rates.

### 39.2. Comparing `SLOWLOG` to HTTP p99 as Equivalent Metrics

SLOWLOG reflects Redis server execution time, omitting the rest of the request path.

### 39.3. Multiplying JSON Size by Key Count to Estimate RAM

Ignores Redis key/object overhead, TTL metadata, indexes, fragmentation, and process buffers.

### 39.4. Measuring One Small Key and Extrapolating to the Whole Database

Real datasets span varying payloads, outliers, and skewed distributions. Sample per key family.

### 39.5. Substituting `STRLEN` for `MEMORY USAGE`

`STRLEN` counts String value bytes only, not full key RAM footprint.

### 39.6. Running `KEYS *` in Production

Can stall Redis on large keyspaces. Use bounded `SCAN` or a test dataset.

### 39.7. Running `redis-benchmark -P 32` and Reporting Equivalent HTTP RPS

Pipelined raw command benchmarks omit Spring overhead, serialization, endpoints, and databases.

### 39.8. Using One Sequential Connection to Claim Redis Is Slow

Network RTT dominates single-connection loops. Test realistic concurrency within safe limits.

### 39.9. Increasing Concurrency While Ignoring p99

Can lift short-term throughput while blowing up queues and timeouts. Measure both.

### 39.10. Benchmarking an Empty Redis Instance

Memory layout, encodings, cache hit rates, and key distributions look nothing like populated production.

### 39.11. Failing to Separate Warm Cache from Cold Cache

A system may fly at steady state yet collapse the database after a restart.

### 39.12. Disabling RDB/AOF in Tests When Production Enables Them

Hides fork, COW, and fsync spikes. Match persistence configuration in tests to production.

### 39.13. Timing a Reactive `Mono` Before Subscription

Distorts command duration; time from subscription/attempt instead.

### 39.14. Putting Redis Keys Into Metric Tags

Causes cardinality explosion; use bounded prefix/operation labels.

### 39.15. Calling Unchanged RSS After `DEL` a Memory Leak

Often allocator fragmentation or retained pages not yet returned to the OS. Gather more metrics first.

### 39.16. Confusing Redis ops/s with Business Transactions/s

One business transaction triggers multiple commands, retries, and dependency calls.

### 39.17. Measuring Only Producer `XADD/s`

Ignores consumer processing, ACKs, PEL/lag, and retention.

### 39.18. Comparing Two Benchmarks Across Different Redis Versions/Networks/Payloads

When conditions shift, claims like "serializer A beats B" can be completely wrong.

### 39.19. Running `MONITOR` Continuously to Measure Throughput

Adds heavy overhead and leaks data. Use `INFO`, counters, and traces.

### 39.20. Optimizing Memory While Ignoring Correctness

Cutting TTLs, over-trimming Streams, or dropping indexes saves RAM at the cost of lost data, low hit rates, or broken queries. Always verify correctness too.

## 40. Lab 1 — Separating HTTP and Redis GET Latency

Create an endpoint `GET /api/products/{id}` backed by `StringRedisTemplate`.

1. Wrap `GET` with a Micrometer timer.
2. Enable Actuator HTTP metrics.
3. Seed 1,000 product keys with sufficiently long TTLs.
4. Run a controlled warm-cache workload.
5. Record p50/p95/p99 for both Redis operations and HTTP requests.
6. Introduce cache misses on part of the traffic.
7. Compare the Redis timer with HTTP latency.

Question: why can HTTP p99 spike dramatically even when Redis server `GET` execution stays fast?

## 41. Lab 2 — Measuring commandstats

On a test Redis instance:

```redis
INFO commandstats
```

Record `calls` for `GET`, `SET`, and `HGETALL`.

Send 10,000 requests through your Spring service, then re-read `INFO commandstats`. Compute per-command deltas and determine Redis commands per business request.

Analyze discrepancies between predicted and observed command mixes. If the Redis instance is shared with another workload, note the measurement limitation.

## 42. Lab 3 — Payload Bytes vs MEMORY USAGE

Create a JSON DTO:

```json
{
  "id": "p-101",
  "name": "Laptop",
  "priceInCents": 1999900,
  "tags": ["electronics", "featured"]
}
```

Steps:

1. Serialize with Jackson.
2. Measure `byte[].length` in UTF-8.
3. Store via `StringRedisTemplate`.
4. Run `STRLEN product:p-101`.
5. Run `MEMORY USAGE product:p-101`.
6. Measure `INFO memory` before and after loading 10,000 similar keys.
7. Explain why payload bytes, memory/key, and RSS differ.

## 43. Lab 4 — JSON String vs Redis Hash

Store the same user data both ways:

```redis
SET lab:user:json "{\"id\":\"u-1\",\"name\":\"Alice\",\"city\":\"HCMC\"}"
HSET lab:user:hash id u-1 name Alice city HCMC
```

Measure:

```redis
MEMORY USAGE lab:user:json
MEMORY USAGE lab:user:hash
STRLEN lab:user:json
HLEN lab:user:hash
OBJECT ENCODING lab:user:hash
```

Repeat with growing field counts and field value lengths. Measure latency for both full-object reads and single-field reads, then draw conclusions from actual access patterns rather than RAM alone.

## 44. Lab 5 — Pipelining

On a test Redis instance, compare:

```bash
redis-benchmark -h 127.0.0.1 -p 6379 \
  -n 100000 -c 50 -P 1 -d 1024 -t get,set -q
```

and:

```bash
redis-benchmark -h 127.0.0.1 -p 6379 \
  -n 100000 -c 50 -P 16 -d 1024 -t get,set -q
```

Record throughput, latency output, Redis CPU, and network throughput. Add a Spring endpoint test to check whether pipelining genuinely applies to that request path.

Question: does raising commands/s via pipelining automatically improve user endpoint p99?

## 45. Lab 6 — Warm-Cache and Cold-Cache

1. Prepare a product table in a test database.
2. Test warm cache at a 90–100% hit rate.
3. Clear the test cache namespace safely.
4. Test cold cache at the exact same arrival rate.
5. Measure hits/misses, DB QPS, Redis GET/SET, and HTTP p99.
6. Test pre-warming or single-flight on hot keys.
7. Re-measure.

Never run `FLUSHALL` on a shared Redis instance. Use an isolated test Redis or dedicated namespace.

## 46. Lab 7 — TTL Bursts and Jitter

Create many cache keys with matching TTLs so they expire around the same moment. Run a read workload across them and record Redis hits/misses, DB QPS, and p99.

Next, add TTL jitter within allowed cache bounds and compare. Explain why TTL jitter curbs thundering herds yet must not alter OTP deadlines.

## 47. Lab 8 — Redis Cluster Hot Slots

Using a test Redis Cluster:

1. Create keys named `order:{orderId}:...`.
2. Measure commands/s and CPU per primary.
3. Run a workload skewed heavily onto one hot aggregate.
4. Observe the node owning that aggregate's slot.
5. Test a broad tag like `{global}` in a small isolated lab namespace.
6. Compare load distributions.

Explain why cluster-wide average CPU can mask a saturated primary.

## 48. Lab 9 — Stream Throughput and Pending Entries

Create a test Stream and group:

```redis
XGROUP CREATE lab:events lab-workers 0 MKSTREAM
```

Have producers write entries with representative payloads while consumers read and ACK slower than producers.

Measure:

```redis
XLEN lab:events
XINFO GROUPS lab:events
XPENDING lab:events lab-workers
MEMORY USAGE lab:events
```

Compare `XADD records/s`, handler success/s, `XACK records/s`, pending count, and group lag.

Explain why producer throughput does not equal business completion throughput.

## 49. Lab 10 — Serialization and Payload Compression

Prepare 10,000 product DTOs matching realistic size distributions.

1. Measure Jackson serialization time and JSON bytes.
2. Benchmark a compressed-payload version.
3. Measure compressed bytes.
4. Store both variants in a test Redis namespace.
5. Run `MEMORY USAGE` on sample sets.
6. Read and deserialize through a Spring service.
7. Compare end-to-end p95/p99, CPU, and memory.

Conclude which payload tier benefits from compression instead of compressing everything blindly.

## 50. Lab 11 — Latency After Network Timeouts

In a test environment with a network proxy or fault-injection adapter:

1. Measure baseline Redis GET/SET.
2. Inject artificial network delay.
3. Record p99 client command latency, HTTP latency, and server `commandstats`.
4. Enable bounded retries with backoff.
5. Observe how end-to-end latency grows.
6. For a non-idempotent write, design a request ID preventing duplicate side effects.

Question: does fast server-side Redis command execution disprove high application latency?

## 51. Lab 12 — Capacity Report

Suppose a project expects:

```text
2 million product keys
500,000 session keys
100,000 cart keys
Read/write mix from production telemetry
Peak traffic at 3x baseline
```

Build a plan to:

1. Sample representative memory/key for each group.
2. Estimate dataset bytes from counts and measured memory/key.
3. Add indexes, TTLs, fragmentation, COW, and memory headroom.
4. Measure per-primary on Redis Cluster.
5. Estimate command rates from RPS and command mix.
6. Define a p99 latency budget.
7. Load test at 50%, 100%, and peak targets.
8. Pinpoint primary/app/database bottlenecks.
9. Propose scaling steps and verification checks.
10. Produce a report marking unmeasured metrics as `NOT_MEASURED`.

The goal of this exercise is building a **measurement and reasoning methodology**, not guessing the "right" RAM number without dataset measurements.

## 52. Self-Assessment Questions

1. How does server-side Redis command latency differ from Spring client-observed latency?
2. Why can a 50 µs server `GET` still make an HTTP endpoint wait 20 ms?
3. How does p99 differ from an average?
4. Why can't you sum component p99s to claim the HTTP p99?
5. How do sample size and observation windows affect percentiles?
6. How does Redis ops/s differ from HTTP RPS?
7. If one request runs 4 Redis commands, what else must be measured when estimating Redis load?
8. As concurrency increases, why can throughput flatten while latency keeps climbing?
9. How do logical data, serialized bytes, and Redis memory usage differ?
10. What does `STRLEN` measure vs `MEMORY USAGE`?
11. Why must `MEMORY USAGE ... SAMPLES 0` be used carefully?
12. Are `used_memory` and `used_memory_rss` the same?
13. How do fragmentation and COW affect capacity planning?
14. Why can one Redis Repository DTO generate multiple keys and secondary indexes?
15. Does Actuator automatically emit all Redis command latency metrics across every version?
16. Why should `productId`, `requestId`, or key names never be metric tags?
17. Why measure reactive Redis from subscription rather than `Mono` construction?
18. Does `INFO commandstats` measure mean client round-trip or Redis execution time?
19. Why doesn't `SLOWLOG` explain every HTTP latency spike?
20. Does empty `LATENCY DOCTOR` output prove Redis never stalled?
21. Why doesn't a `-P 16` benchmark directly predict Spring service RPS?
22. Where do bottlenecks differ between warm cache and cold cache?
23. What is coordinated omission and how does it distort p99?
24. How does one hot hash slot affect Redis Cluster?
25. Does `XLEN` reflect full Stream memory and pending entries?
26. Why is high `XADD` throughput not enough to prove consumers keep up?
27. When does compression help performance and when can it hurt?
28. How can overly short TTLs increase database load?
29. Why can't capacity be judged from a single `instantaneous_ops_per_sec` sample?
30. What environment conditions must a trustworthy load test report include?

## 53. Key Takeaways

- **Measure three distinct dimensions:** latency (p50/p95/p99), throughput (RPS/commands/s/bytes/s), and actual data size (serialized bytes, `MEMORY USAGE`, process memory).
- **Latency requires clear boundaries.** Redis server execution, Redis client round-trip, Spring service latency, and HTTP p99 are different measurements.
- **Averages hide tail latency**; p95/p99 and error rates are critical for SLOs.
- **Redis ops/s is not business RPS.** One request can trigger multiple commands and retries.
- `INFO stats`, `INFO commandstats`, `SLOWLOG`, and `LATENCY` complement client/HTTP metrics, though none replaces all others.
- **`STRLEN`/`HLEN`/`XLEN` measure logical size**, whereas `MEMORY USAGE` measures Redis-accounted key/value RAM; `used_memory_rss` also includes fragmentation, buffers, and process overhead.
- **Measure representative datasets**, including p50/p95/p99 payloads, key families, TTLs, indexes, hot keys, and large objects; never multiply one tiny key by key count to budget capacity.
- Spring Data Redis can leverage **Micrometer/Actuator**, Lettuce command latency instrumentation, and custom timers. Never use unbounded keys/IDs as metric tags.
- With Reactive Redis, **time from subscription** and never call `.block()` on the WebFlux event loop for benchmarks.
- `redis-benchmark` is helpful for command-level capacity, yet **never replaces load testing through real Spring endpoints**.
- Pipelining can lift throughput by cutting network waits, yet requires watching batch latency, buffers, p99, and correctness.
- Redis Cluster must be measured **per-primary / per-hot-slot**, not only via average cluster CPU; Streams must track producer throughput, consumer ACK throughput, and pending/lag.
- TTLs, serialization, compression, data types, and persistence all carry CPU, RAM, network, latency, and correctness trade-offs.
- A trustworthy benchmark includes **representative datasets, warm-up, workload mix, concurrency/arrival rates, environment specs, latency distributions, and error rates**.
- Optimize only after locating the bottleneck, changing one factor at a time, and **re-measuring**. The goal is meeting business requirements with headroom—not chasing the single highest requests/s number.

### Official References

- [Redis — Latency optimization](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/)
- [Redis — Benchmarking Redis](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/)
- [Redis — INFO](https://redis.io/docs/latest/commands/info/)
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/)
- [Redis — LATENCY](https://redis.io/docs/latest/commands/latency/)
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/)
- [Redis — MEMORY STATS](https://redis.io/docs/latest/commands/memory-stats/)
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis — STRLEN](https://redis.io/docs/latest/commands/strlen/)
- [Redis — OBJECT ENCODING](https://redis.io/docs/latest/commands/object-encoding/)
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/)
- [Redis — Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Reference Documentation](https://docs.micrometer.io/micrometer/reference/)
- [Lettuce — Reference Guide](https://redis.github.io/lettuce/)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
