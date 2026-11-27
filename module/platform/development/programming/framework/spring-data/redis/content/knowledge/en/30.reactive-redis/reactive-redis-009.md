# Throttling Demand and Limiting Concurrency to Protect Redis

## 1. Problem: A Reactive API Does Not Mean Redis Can Handle Infinite Load

Suppose a Spring WebFlux API needs to fetch the statuses of 5,000 devices from Redis. Spring Data Redis provides `ReactiveRedisTemplate` and `ReactiveStringRedisTemplate`, allowing Redis calls via `Mono` or `Flux` without blocking a Java thread for each reply.

A snippet looks quite natural:

```java
return Flux.fromIterable(deviceIds)
        .flatMap(id ->
                reactiveRedisTemplate.opsForValue()
                        .get("device:status:" + id)
        );
```

Yet an important question arises: **how many commands is the application sending to Redis at once?**

If hundreds of HTTP requests run concurrently and each spawns thousands of Redis operations, the number of commands awaiting responses grows rapidly. Redis may not have hit 100% CPU yet, while client connections, outbound command queues, buffers, bandwidth, decoding time, and p99 latency have already spiked.

```text
Many HTTP requests
       |
       v
Spring WebFlux / Reactor
       |
       | If issuing unbounded Redis GETs
       v
Large number of pending commands / client queues
       |
       v
       Redis
       |
       +-- Response times rise
       +-- Timeouts, reconnects, retries
       +-- Heap and buffers grow
       +-- Other requests are impacted
```

A *reactive* system organizes asynchronous I/O and propagates **demand** signals across components. It **does not magically grant extra CPU, bandwidth, or memory to Redis**. Protecting Redis requires active throttling:

- How many **concurrent** Redis operations can one workflow run?
- How many in-flight Redis operations can all requests on one instance have?
- How many commands per second may be issued?
- Can the data source emit faster than downstream processes, and if so, what happens?
- When load exceeds thresholds, does the system **wait, reject, drop, or durably store work**?

This lesson belongs to the **Reactive Redis** chapter of Spring Data Redis and focuses on Reactor *backpressure*, `flatMap` bounds, instance-wide **in-flight** budgets, rate limiting, timeouts, retries, and measuring to select proper load budgets.

## 2. What Is Backpressure in Reactive Streams?

### 2.1. Publisher, Subscriber, and request(n)

In Reactive Streams, a producer (`Publisher`) sends items to a consumer (`Subscriber`) via a `Subscription`. The subscriber tells the publisher how many items it is ready to receive via:

```java
subscription.request(n);
```

Conceptual flow:

```text
Publisher                         Subscriber
    |                                 |
    | <------- request(5) ------------|
    | -------- onNext(item1) -------->|
    | -------- onNext(item2) -------->|
    | -------- onNext(item3) -------->|
    | -------- onNext(item4) -------->|
    | -------- onNext(item5) -------->|
    |                                 |
    | <------- request(5) ------------|
    | -------- subsequent items ----->|
```

A backpressure-compliant stream does not emit `onNext` beyond the requested demand. In Reactor, `Flux` and `Mono` are the two standard Publisher types.

**Demand** is not the same as "limiting Redis to at most 5 commands per second." It expresses **how many output elements downstream is requesting**, without directly defining QPS budgets, connection counts, or Redis command limits.

### 2.2. Two very different kinds of input streams

A **cold publisher** can emit on demand:

```java
Flux.fromIterable(keys)
```

The key list is already in hand and iterated upon subscription. Downstream operators can pace upstream demand.

A **hot publisher** can keep emitting regardless of whether a specific subscriber is slow—for instance, a live event source, external callbacks, or a `Sinks.Many` fed by another thread.

```text
Cold source:
  downstream requests -> upstream emits accordingly

Hot source:
  events keep arriving -> downstream is slow
                    |
                    +-- Needs buffer / drop / error / durable storage policy
```

`flatMap(..., concurrency)` bounds how many inner tasks are subscribed simultaneously, yet **does not turn an unbounded hot source into a durable queue**. If events arrive faster than Redis can process them over sustained periods, the system needs an explicit overload policy.

### 2.3. Backpressure does not mean the Redis server sees request(n)

Redis does not receive Reactor `request(n)` signals. Those signals exist between Publishers and Subscribers inside the application.

Protecting Redis relies on using demand and operators to **reduce how many commands the application sends to Redis**. Once a command has been written to the socket, canceling a subscription does not guarantee Redis did not execute that command.

This distinction is especially critical for write operations.

## 3. Distinguishing Three Limits: Demand, Concurrency, and Rate

| Concept | What it bounds | Example | Guarantees Redis QPS? |
|---|---|---|---|
| **Demand/backpressure** | Elements requested from Publisher by downstream | `request(10)`, `limitRate(32)` | No |
| **Concurrency** | Operations executing concurrently | `flatMap(fn, 8)` | No |
| **Rate limit** | Requests accepted within a time window | Max 500 Redis reads/sec | Can bound emission rate within applied scope |
| **Queue/buffer limit** | Items held waiting for processing | Max 1,000 pending tasks | Not directly |
| **Connection limit** | Physical connections in pool | 16 connections | Not equivalent to concurrent commands |

A Redis client like Lettuce can **multiplex** many commands onto a single connection, so "16 connections" does not mean "16 commands in flight." Conversely, `flatMap` with 16 inner subscriptions does not mean Redis sees at most 16 commands if **each inner publisher** itself issues multiple commands.

### 3.1. Concurrency is not QPS

Suppose an average Redis command takes 20 ms from send to application receipt. With at most 10 operations in flight, ideal throughput is roughly:

```text
concurrency / latency = 10 / 0.020 = 500 operations/sec
```

This is only a directional calculation relating concurrency, rate, and service time; actual throughput depends on the client, Redis, network, and latency distribution.

With the same cap of 10 concurrent operations, if latency drops to 2 ms, the application can generate significantly higher load. Therefore, **a concurrency limit does not replace a rate limit** when Redis has an explicit QPS budget to respect.

### 3.2. Rate limits do not replace concurrency limits either

Suppose you admit 100 requests/sec, yet each operation takes 3 seconds. In-flight work can pile up dramatically even though the admission rate is capped.

A stronger design typically combines:

```text
Incoming requests
      |
      v
Rate limit: do not accept too many requests/sec
      |
      v
Concurrency limit: do not let too many tasks hit Redis simultaneously
      |
      v
Timeout + bounded queue + overload policy
      |
      v
Redis
```

## 4. Limiting Concurrency in Reactor with flatMap

### 4.1. flatMap with a concurrency argument

With Spring Data Redis Reactive, each `get(key)` typically returns a `Mono<String>` representing one asynchronous read. Reactor's `flatMap` can bound how many inner publishers are subscribed concurrently:

```java
Flux.fromIterable(keys)
        .flatMap(
                key -> redis.opsForValue().get(key),
                8
        );
```

Meaning: at most around **8 inner publishers subscribed at one time** within **a single subscription to this Flux**. When each inner publisher is a simple Redis `GET`, this is a practical way to cap concurrent GETs from that workflow.

Notes:

- This is a **per-pipeline limit**, not a JVM-wide limit.
- `flatMap` may emit results **out of input key order** because commands complete at different times.
- If an inner publisher issues multiple Redis operations, the inner cap is not a strict command cap.
- When many HTTP requests each create their own pipeline, limits multiply across concurrent requests.

For example, 100 requests each running `flatMap(..., 8)` can produce up to roughly **800 in-flight inner subscriptions** on one instance if all run concurrently with no shared limit.

### 4.2. flatMap(mapper, concurrency, prefetch)

An important overload:

```java
.flatMap(
        key -> redis.opsForValue().get(key),
        8,  // concurrency
        1   // prefetch
)
```

- `concurrency` caps active inner publishers.
- `prefetch` tunes how much data the operator pre-requests from **each inner publisher**, affecting internal buffering.

When inner publishers are `Mono`s returning at most one item, `prefetch = 1` signals no need to pre-request multiple items per inner. When inner publishers are `Flux`es emitting thousands of items, a large prefetch can queue much more pending data.

`prefetch` is **not** a total memory limit or Redis QPS limit. Tune it alongside source shape and downstream operators.

### 4.3. concatMap: one operation after another

When you want ordered processing and essentially one active task at a time:

```java
Flux.fromIterable(keys)
        .concatMap(key -> redis.opsForValue().get(key));
```

`concatMap` waits for the current inner to complete before subscribing to the next. It fits when order or minimal concurrency outweighs throughput, though over high-RTT networks it can be significantly slower.

If `get(key)` returns `Mono.empty()` for a missing key, the corresponding element **is not emitted** unless the application explicitly maps misses to a result object. That matters when matching output items back to input keys.

### 4.4. flatMapSequential: bounded concurrency while preserving output order

```java
Flux.fromIterable(keys)
        .flatMapSequential(
                key -> redis.opsForValue().get(key),
                8,
                1
        );
```

`flatMapSequential` subscribes to multiple inner publishers concurrently while emitting results in source order. Useful when an API must return items in input key order.

In return, if an early inner publisher stalls, completed results from later inners must be **buffered in memory**. Measure memory and latency rather than assuming it is always superior to `flatMap`.

### 4.5. limitRate is not a rate limiter

Example:

```java
Flux.fromIterable(keys)
        .limitRate(32)
        .flatMap(key -> redis.opsForValue().get(key), 8);
```

`limitRate(32)` adjusts how elements are requested from upstream in smaller batches. It **does not** guarantee Redis receives at most 32 commands/sec or 32 commands at once.

When Redis responds quickly, the pipeline can still fire thousands of commands per second. If you need a QPS cap, use a dedicated rate-limiting mechanism.

## 5. Spring Data Redis Example: Reading Many Keys with Bounded In-Flight Work

### 5.1. ReactiveStringRedisTemplate

In a Spring Boot app with Spring Data Redis Reactive and a suitable Lettuce connection, inject `ReactiveStringRedisTemplate`:

```java
package com.example.redis.reactive;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DeviceRedisService {

    private final ReactiveStringRedisTemplate redis;

    public DeviceRedisService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }
}
```

`ReactiveStringRedisTemplate` uses string serializers for keys and values. If Redis stores JSON or Hashes, use `ReactiveRedisTemplate`/operations and serializers matching the actual data. Never assume every Redis value is a plain String.

### 5.2. Returning both cache hits and cache misses

When reading a list of keys, a missing `GET` returns `Mono.empty()`. With plain `flatMap`, missed keys vanish from the output stream, making ID correlation difficult.

Define a result type:

```java
package com.example.redis.reactive;

public record DeviceLookup(
        String deviceId,
        String status,
        boolean found
) {
}
```

A complete service:

```java
package com.example.redis.reactive;

import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DeviceStatusReader {

    private static final int MAX_CONCURRENCY = 8;

    private final ReactiveStringRedisTemplate redis;

    public DeviceStatusReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Flux<DeviceLookup> findMany(List<String> deviceIds) {

        return Flux.fromIterable(deviceIds)
                .flatMap(
                        this::findOne,
                        MAX_CONCURRENCY,
                        1
                );
    }

    private Mono<DeviceLookup> findOne(String deviceId) {

        String key = "device:status:" + deviceId;

        return redis.opsForValue()
                .get(key)
                .map(value -> new DeviceLookup(
                        deviceId, value, true
                ))
                .switchIfEmpty(Mono.fromSupplier(
                        () -> new DeviceLookup(
                                deviceId, null, false
                        )
                ))
                .timeout(Duration.ofMillis(800));
    }
}
```

Explanation:

1. `Flux.fromIterable(deviceIds)` streams keys **when subscribed to**.
2. `flatMap(..., 8, 1)` bounds how many `findOne` calls are subscribed concurrently **within one read call**.
3. `get(key)` returns `Mono<String>` without blocking a thread while waiting for Redis.
4. `map(...)` turns a Redis hit into a result with `found=true`.
5. `switchIfEmpty(...)` turns a Redis miss into a result with `found=false`, preserving every input ID.
6. `timeout(800 ms)` sets an illustrative wait budget per inner operation; exceeding it errors and terminates `findMany` by default unless handled per item.
7. Never call `.block()` or `.subscribe()` inside the service. The service **returns a Flux** so WebFlux or the consumer controls subscription.

**These are illustrative budgets, not universal optimal defaults.** Timeouts and concurrency caps must come from your system's SLOs and measurements.

### 5.3. flatMap does not preserve output order

Given input:

```text
A, B, C, D
```

If Redis returns C faster than A, results can arrive as:

```text
C, A, D, B
```

That is why multi-key read APIs should keep correlation via `deviceId`. If strict output order is mandatory, consider `flatMapSequential` and measure its buffering cost.

### 5.4. Do not subscribe inside a loop

A very common mistake:

```java
for (String key : keys) {
    redis.opsForValue().get(key)
            .subscribe(value -> handle(value));
}
```

Each iteration starts an independent subscription, making total concurrency, completion ordering, error handling, and cancellation hard to control. Without tracking `Disposable` and lifecycle, tasks can keep running after the request ends.

Instead:

```java
return Flux.fromIterable(keys)
        .flatMap(
                key -> redis.opsForValue().get(key),
                8
        );
```

Keep operations inside **a single reactive chain** and let the caller at the application boundary subscribe.

## 6. Instance-Wide Concurrency Limits

`flatMap(..., 8)` protects **a single pipeline**, not the entire application when hundreds of pipelines run concurrently.

Suppose:

```text
100 concurrent HTTP requests
Each request: maxConcurrency = 8
=> Up to ~800 active inner GET operations
```

If Redis and the driver only tolerate fewer concurrent operations, add a **shared in-flight budget** across requests passing through the service.

### 6.1. Non-blocking Semaphore on the event loop

You can use `java.util.concurrent.Semaphore` with `tryAcquire()` to **fail fast** when permits are exhausted, instead of calling `acquire()` which would block the event-loop thread.

Example:

```java
package com.example.redis.reactive;

public class RedisOverloadedException extends RuntimeException {

    public RedisOverloadedException() {
        super("Redis operation budget is busy");
    }
}
```

In-flight-bounded service:

```java
package com.example.redis.reactive;

import java.util.concurrent.Semaphore;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ProtectedRedisReader {

    // Shared budget for this service instance.
    private final Semaphore permits = new Semaphore(40);
    private final ReactiveStringRedisTemplate redis;

    public ProtectedRedisReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<String> get(String key) {

        return Mono.defer(() -> {

            if (!permits.tryAcquire()) {
                return Mono.error(new RedisOverloadedException());
            }

            // Second defer also guards publisher creation:
            // if creating/getting fails, doFinally still releases.
            return Mono.defer(() ->
                    redis.opsForValue().get(key)
            ).doFinally(signal -> permits.release());
        });
    }
}
```

Mechanism:

- Attempts to acquire a permit **only when subscription begins**, not when creating the `Mono`.
- If all 40 permits are busy, emits `RedisOverloadedException` so the caller can return HTTP 429/503 or shed load appropriately.
- `doFinally` releases the permit when the `Mono` completes, errors, or is canceled.
- `tryAcquire` never blocks the Reactor event loop.
- The 40-permit cap is **per application instance**, not across the entire Redis Cluster.
- When each inner runs one `GET`, permit count tracks active in-flight operations passing through this service.

Crucial detail: **all Redis paths requiring protection must route through this shared gate**. Any endpoint calling `ReactiveStringRedisTemplate` directly bypasses the semaphore.

### 6.2. Combining per-request and per-instance limits

```java
public Flux<DeviceLookup> findManyProtected(List<String> deviceIds) {

    return Flux.fromIterable(deviceIds)
            .flatMap(
                    id -> protectedRedisReader
                            .get("device:status:" + id)
                            .map(status ->
                                    new DeviceLookup(id, status, true))
                            .switchIfEmpty(
                                    Mono.just(
                                            new DeviceLookup(id, null, false)
                                    )
                            ),
                    8,
                    1
            );
}
```

Two layers:

```text
One HTTP request
      |
      | flatMap concurrency=8
      v
ProtectedRedisReader
      |
      | Semaphore 40 across the JVM
      v
Redis
```

Once 40 permits are in use, new requests **fail fast**. This is a **bulkhead/fail-fast policy**, not a queue.

If you want to wait for permits instead of failing immediately, design a **bounded queue with an explicit wait timeout**—never use blocking semaphore waits directly on the event loop. Unbounded waiting simply shifts overload from Redis into application RAM and latency.

### 6.3. Permits reflect subscriptions, not guaranteed command cancellation

`doFinally` runs when the reactive chain terminates or is canceled. On timeout/cancel, the permit is released in the application. Yet if the Redis command was already written to the socket, it **may still be executing or finishing on Redis**.

Therefore, if your goal is **strictly bounding physical commands alive on Redis**, understand client cancellation, queuing, and timeout mechanics. A `Mono`-level semaphore is a practical load-shedding tool, not an absolute server-side concurrency guarantee under frequent timeouts and cancellations.

## 7. Multiple Instances Multiply the Total Budget

A service with 10 pods, each allowing 40 permits:

```text
Pod 1:  40 in-flight operations
Pod 2:  40 in-flight operations
...
Pod 10: 40 in-flight operations
----------------------------
Theoretical total: up to 400 operations
```

Thus, local limits do not automatically protect a shared Redis server from the aggregate load of all application replicas.

To enforce a global budget:

- Size per-instance quotas from expected replica counts and real traffic.
- Place limits at an API gateway or shared coordination tier.
- Use a distributed rate limiter if synchronized cross-instance quotas are truly required.
- Plan how limits react when autoscaling adds instances.
- Monitor total Redis commands at the cluster level, not only per-pod metrics.

If you use **the very Redis instance you are trying to protect** to evaluate distributed rate limits for every request, the rate-limit commands themselves add load to Redis. Factor that cost into your design and consider enforcing limits upstream of Redis when appropriate.

### 7.1. Multiple shards in Redis Cluster do not mean balanced load

A `GET` routes to the node owning the key's hash slot. If most requests target a handful of hot keys, one shard takes far more load than others.

Monitor:

- Commands/sec per node.
- CPU, network, and memory per shard.
- Latency by key group or feature.
- Pending outbound/inbound commands inside the client.
- Hot-key distribution.

A global concurrency limit protects total load, not necessarily a hot shard under heavily skewed key access. Where needed, add per-workload, per-key-group, or per-shard budgets, accepting the added complexity.

## 8. Limiting Command Emission Speed: Rate Limiting

`flatMap(concurrency=8)` prevents too many operations **at once** inside one pipeline. Yet when Redis responds very fast, completed inners are immediately replaced by new ones, so throughput can still be very high.

**Rate limiting** caps how many operations are admitted over a time window, for example:

```text
Budget: 200 GET operations/sec
Allowed burst: up to 50 operations over a short interval
```

A common algorithm is **token bucket**:

```text
Token bucket (capacity 50)
        |
   +1 token at configured refill rate
        |
Request needs 1 token
        |
  +-----+--------+
  |              |
Token available  Empty
  |              |
Allow            Reject or
                 enqueue with bound
```

In Spring WebFlux you can integrate a reactive rate limiter into the chain or enforce quotas at the gateway. What matters is not the library name, but:

1. Have you defined the unit being limited: HTTP requests, Redis operations, or batches?
2. Have you defined burst size and max queued requests?
3. Do you prioritize critical writes over cache reads?
4. Is there a shared limit across pods?
5. When the limit is exceeded, does the caller receive a clear overload signal?

### 8.1. delayElements is not a general-purpose rate limiter

A common attempt:

```java
Flux.fromIterable(keys)
        .delayElements(Duration.ofMillis(10))
        .flatMap(
                key -> redis.opsForValue().get(key),
                8
        );
```

Within a single pipeline, `delayElements` spaces out emissions. However, with 100 concurrent HTTP requests, **each request has its own independent timer** and total emission rate can still vastly exceed expectations.

`delayElements` also lacks production rate-limiter features such as shared quotas, burst policies, fairness, and overload rejections. Use it for testing or intentionally pacing a single stream—never as a system-wide Redis protection mechanism.

## 9. Queues and Backpressure: Set Limits Instead of Unbounded Accumulation

### 9.1. Unbounded buffers are dangerous

Suppose events arrive at 10,000/sec while Redis only processes 2,000/sec. Putting every event into an unbounded in-memory queue causes backlog growth:

```text
10,000 events/sec arriving
 2,000 events/sec processed
--------------------------------
 8,000 events/sec accumulating
```

After one minute, hundreds of thousands of pending items can accumulate. Large payloads rapidly exhaust heap, triggering GC pauses or `OutOfMemoryError`.

Backpressure works fully only when **the upstream producer can slow down** in response to downstream demand. For push-based sources that emit regardless of demand, enforce explicit backlog limits.

### 9.2. Bounded onBackpressureBuffer

Example for a fast-emitting hot Flux:

```java
Flux<Event> guarded = incomingEvents
        .onBackpressureBuffer(1000);
```

When downstream falls behind, the operator buffers at most roughly 1,000 items. Exceeding that limit signals a buffer overflow error per configuration.

**Never use unbounded `onBackpressureBuffer()`** on high-throughput streams without a memory budget. Buffering only absorbs short bursts; it cannot fix a producer that outpaces processing **over sustained periods**.

Other options include:

- `onBackpressureDrop`: drops events when downstream falls behind; suited only when data loss is acceptable.
- `onBackpressureLatest`: keeps only the latest value per downstream demand; fits live status displays where intermediate states can be skipped.
- Emit an error or reject incoming work so upstream slows down.
- Persist requests to a durable queue/stream when **work must never be dropped**.

### 9.3. Never drop mandatory business tasks

A "latest screen temperature" event may allow dropping older samples, whereas "record order payment" cannot silently be dropped just because Redis is busy.

Choose policies by data criticality:

| Work type | Typically suitable policy |
|---|---|
| Latest UI status updates only | Keep latest when intermediate states may be skipped |
| Cache pre-warming | Can skip under overload, since later reads refill |
| API cache reads | Return load-shedding/timeout error or bounded fallback |
| Mandatory business events | Durable queue, controlled retries, idempotency |
| Financial writes | Authoritative transactions, deduplication, never drop |

## 10. Timeouts, Retries, and Cancellation Must Be Designed Together

### 10.1. Timeouts bound application wait time

Example:

```java
redis.opsForValue()
        .get(key)
        .timeout(Duration.ofMillis(500));
```

When time expires, Reactor emits a timeout error and cancels the upstream subscription per operator semantics. However, **never assume Redis canceled the physical command**. If already sent, the server may still execute it.

For `GET` reads, retrying is usually lower risk regarding side effects than writes. Still, when many timeouts happen concurrently, unbounded retries increase Redis pressure right when Redis is already struggling.

### 10.2. Bounded, conditional retries with jitter

An example with application-level retries:

```java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<String> getWithRetry(String key) {

    return redis.opsForValue()
            .get(key)
            .timeout(Duration.ofMillis(500))
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(100))
                            .maxBackoff(Duration.ofSeconds(1))
                            .jitter(0.5)
                            .filter(this::isTransientRedisFailure)
            );
}
```

`isTransientRedisFailure(Throwable)` is an application-defined predicate distinguishing transient failures from non-retryable ones; for example, never retry malformed data or programming bugs.

Rules:

- Cap retry attempts.
- Use backoff and jitter to avoid synchronized retry storms.
- Set a total deadline for the whole request, not only per attempt.
- Never retry every error blindly.
- Include retries inside rate and concurrency budgets.
- When Redis is overloaded, **failing fast** is often better than issuing more retries.

### 10.3. Write commands risk duplicating side effects on retry

Example:

```java
redis.opsForValue().increment("views:page:42");
```

If a request times out after Redis already executed `INCR`, the application misses the reply even though Redis incremented the counter. Blindly retrying increments it again.

Similarly, `LPUSH`, `XADD`, and other writes can duplicate side effects. When business rules forbid double execution, require an idempotency key or conditional write mechanism.

`retryWhen` does not provide **exactly-once semantics**. It simply re-subscribes and re-runs the source operation.

### 10.4. Cancellation is not transaction rollback

When an HTTP client closes the connection, the subscription can be canceled. This saves the application from unnecessary downstream work, yet does not guarantee sent Redis commands are undone.

Therefore:

```text
Cancel a Mono
      |
      +-- May stop listening for the response
      +-- May release Reactor resources
      +-- Does not automatically roll back the Redis command
```

That is why cancellation must never be relied upon as the sole guard against side effects for sensitive writes.

## 11. Schedulers and Event Loop: Keep Blocking Work Out of Reactive Flows

Spring Data Redis Reactive uses non-blocking APIs for I/O waiting. Yet if application code calls:

```java
String value = reactiveRedis.opsForValue()
        .get(key)
        .block();
```

inside a WebFlux handler, you turn a non-blocking call into a blocking wait. This ties up the event-loop thread and degrades capacity for other requests.

Nor should you call `subscribe()` arbitrarily and return a response before the operation completes.

A WebFlux handler should return `Mono` or `Flux`:

```java
@GetMapping("/devices/{id}/status")
public Mono<ResponseEntity<String>> status(
        @PathVariable String id) {

    return redis.opsForValue()
            .get("device:status:" + id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

If a flow contains genuinely blocking work (e.g., calling a synchronous JDBC library), isolate that piece on an appropriate resource-bounded scheduler such as `boundedElastic`. **Do not move every Redis call onto `Schedulers.boundedElastic()` just because you are using Reactive**: that only adds unnecessary scheduler hops without fixing Redis overload.

`publishOn`, `subscribeOn`, and `parallel()` shift execution threads; they do not limit how many Redis commands are running. Using them without understanding internal queues/prefetch can make load harder to observe.

## 12. Batching and Pipelining in Reactive Redis

When reading many keys, besides bounding concurrency, you can **batch commands** to reduce round trips.

For instance, Redis supports `MGET` across multiple Redis Strings:

```redis
MGET device:status:A device:status:B device:status:C
```

Spring Data Redis Reactive offers multi-key APIs such as `multiGet(...)` for applicable operations, but keep in mind:

- Results may be buffered in memory as a single list.
- Response payload size can be large despite being one command.
- Redis Cluster imposes hash-slot requirements on multi-key commands.
- A huge `MGET` can stall Redis and raise latency for concurrent requests.
- Batching does not eliminate the need to bound concurrent large jobs.

Conceptual batching layout:

```text
5,000 keys
   |
   +--> 100 keys/batch
   |        |
   |        +--> MGET or suitable operation group
   |        +--> Process and release results
   |
   +--> at most 4 active batches at a time
```

Do not blindly pick `buffer(1000)` thinking it protects Redis; it can allocate large RAM lists and fire heavier commands. Measure bytes, latency, and memory pressure.

In Redis Cluster, when keys reside in different slots, not every multi-key command can be sent directly. Choose topology-compatible strategies and avoid hot-shard bottlenecks.

## 13. Designing Multi-Layer Redis Protection in a Real Service

A layered defense architecture can look like:

```text
Client / Gateway
      |
      | Layer 1: Request rate limiting
      v
WebFlux controller
      |
      | Layer 2: Validate, reject oversized requests
      v
Service
      |
      | Layer 3: flatMap concurrency per task
      v
Shared Redis Access Layer
      |
      | Layer 4: Instance-wide in-flight budget
      v
Reactive Redis client
      |
      | Layer 5: Connection/pending-command limits
      v
Redis / Redis Cluster
      |
      +--> Metrics and alerts
```

### 13.1. Validate and bound input element counts

Never blindly accept a list of 1,000,000 keys from a single HTTP request, even when `flatMap(..., 8)` caps in-flight commands. The request can still monopolize CPU, memory, and connections for too long.

An API can enforce:

- Maximum keys per request.
- Maximum input payload size.
- Maximum concurrent requests per user/client.
- Total time budget per request.
- Maximum batch count and response size.

For very large datasets, consider pagination, bounded background jobs, or cancelable streaming.

### 13.2. Size budgets by operation cost

Not all Redis operations cost the same:

```text
GET a small key          -> usually relatively cheap
HGETALL a large Hash     -> can return massive payloads
LRANGE a long slice      -> load scales with returned elements
SCAN whole keyspace      -> many iterations and resources
Complex Lua script       -> can block Redis for a long time
```

A semaphore counting "one permit per operation" is a clear starting point, yet does not capture total work. For heavy commands, you may need to:

- Bound returned element counts.
- Allow fewer heavy commands concurrently.
- Partition budgets across read/write or workload classes.
- Prevent background scans from starving latency-sensitive requests.

### 13.3. Define explicit overload policies

When the budget is exhausted, options include:

1. **Fail fast:** return HTTP 429/503 or a retryable application error.
2. **Bounded wait:** place work into a small queue with an explicit timeout.
3. **Fallback:** read another source when allowed and that source has capacity.
4. **Drop/Latest:** only when data may be skipped or coalesced.
5. **Persist:** write to a durable queue/Stream when work must not be lost.

Do not apply one policy to every job type. Cache pre-warming can be skipped when Redis is busy, whereas transactional writes require proper confirmation/persistence.

## 14. Observing Redis and Reactor Before Setting Thresholds

Measuring only a single `ops/s` number makes it hard to tell whether Redis is actually protected or load has merely shifted into client queues.

Measure both the **application** and the **Redis server**.

| Metric | Why it is needed |
|---|---|
| Redis commands/sec | Measures actual workload |
| Redis command latency p50/p95/p99 | Reveals tail latency spikes |
| Application in-flight operations | Shows whether concurrency caps are reached |
| Rejected requests from bulkhead/rate limit | Tracks demand exceeding budget |
| Pending commands / client buffers | Exposes queues inside the driver |
| Timeouts and retry attempts | Checks whether retries amplify load |
| JVM heap, GC pauses | Spots buffering/queuing inside the app |
| Redis CPU, memory, network | Identifies server-side bottlenecks |
| Pool pending/acquire time | Spots connection contention |
| Per-shard load in Cluster | Reveals hot shards |

Useful Redis inspection commands:

```redis
INFO stats
INFO commandstats
INFO cpu
INFO memory
INFO clients
SLOWLOG GET 10
LATENCY LATEST
```

`SLOWLOG` mainly records server-side command execution time, excluding network wait and client-side decoding. Thus server execution can look fast while HTTP p99 is high due to client command queues or buffers.

`LATENCY LATEST` reports Redis latency events when latency monitoring is enabled. Understand metric definitions so you do not directly compare non-equivalent numbers.

### 14.1. Instrumenting in-flight execution points

For a Redis `Mono`, measure per-subscription duration:

```java
public Mono<String> timedGet(
        String key,
        io.micrometer.core.instrument.Timer timer) {

    return Mono.defer(() -> {

        long started = System.nanoTime();

        return redis.opsForValue()
                .get(key)
                .doFinally(signal -> {
                    long elapsed = System.nanoTime() - started;
                    timer.record(
                            elapsed,
                            java.util.concurrent.TimeUnit.NANOSECONDS
                    );
                });
    });
}
```

The measured duration spans from subscription to completion/cancellation—not only Redis execution time. Name the metric accordingly, such as `redis.client.operation.duration`.

When handling many keys, **never attach raw key names or userIds as metric tags** because cardinality explodes. Tag by command type, endpoint, or bounded workload group.

### 14.2. What to watch during load ramp-up tests

As request rate ramps from low to high:

```text
Low load
   |
   v
Throughput rises nearly linearly
   |
   v
A resource approaches saturation
   |
   v
p95/p99 latency climbs
   |
   v
Timeouts/retries climb, heap/queues grow
   |
   v
System can degrade severely
```

The goal of concurrency limits is **preventing the application from entering severe degradation**, not trying to hold every request open at all costs.

## 15. Experiment to Determine an Appropriate maxConcurrency

### 15.1. Preparing the workload

Suppose an API reads 1,000 device statuses, each averaging 1 KiB. Seed test data in a dedicated namespace:

```text
device:status:test:1
device:status:test:2
...
device:status:test:1000
```

Data should have a TTL/cleanup strategy and never contain real user data. Use the same serializer as production.

### 15.2. Testing concurrency levels

| Configuration | Per-request concurrency | Instance cap | Concurrent requests |
|---|---:|---:|---:|
| A | 1 | 40 | 1, 10, 50 |
| B | 4 | 40 | 1, 10, 50 |
| C | 8 | 40 | 1, 10, 50 |
| D | 16 | 40 | 1, 10, 50 |
| E | 32 | 40 | 1, 10, 50 |

This is a **test matrix**, not a claim that 8 or 40 are always optimal.

In each scenario, record:

- Request throughput/sec and Redis commands/sec.
- Request p50, p95, and p99 latency.
- Rejected permits count.
- Timeouts and retries.
- Driver pending commands, if exposed by metrics.
- Redis CPU, network, and JVM heap/GC.

### 15.3. Interpreting results against latency budgets

A **hypothetical** outcome:

```text
Concurrency 1:  low load, throughput below target
Concurrency 4:  throughput improves, latency stable
Concurrency 8:  throughput climbs further, p99 stays within SLO
Concurrency 16: throughput barely grows, p99 rises
Concurrency 32: retries/timeouts spike sharply
```

In this hypothetical run, concurrency 8 is a better candidate than 32. Still, verify across varying HTTP concurrency levels and against a Redis topology close to production.

The objective is finding the **stable performance plateau**, not chasing maximum commands/sec at the expense of stability.

### 15.4. Controlled overload testing

After picking thresholds, test:

1. Ramp input rate above budget in a controlled manner.
2. Confirm requests are rejected/shed instead of building unbounded queues.
3. Confirm in-flight counts stay within the application budget.
4. Watch p99 of accepted requests.
5. Drop load back down and verify recovery without lingering retry storms.
6. Simulate slow Redis or disconnects in an isolated test environment.

If a timeout triggers immediate multi-retries on every request, the system can still collapse under overload even with a local concurrency limit.

## 16. Common Implementation Mistakes

### Mistake 1: Assuming reactive automatically prevents overload

`Mono` and `Flux` support demand propagation and non-blocking I/O, yet many concurrent pipelines can still generate massive command volumes. Define explicit load budgets.

### Mistake 2: Using flatMap without considering concurrency

Using unbounded or overly high concurrency lets active inner subscriptions exceed safe limits. Specify `concurrency` explicitly for multi-key workloads.

### Mistake 3: Treating limitRate(100) as 100 Redis GETs/sec

`limitRate` paces upstream element requests, not QPS. Use a proper rate limiter when time-window quotas are required.

### Mistake 4: Limiting only per request

`flatMap(..., 8)` on a single request does not prevent 100 concurrent requests from launching ~800 simultaneous operations. Add shared service- or gateway-level budgets.

### Mistake 5: Using Semaphore.acquire() inside reactive pipelines

`acquire()` can block the running thread, including the event loop. Use `tryAcquire` to fail fast or a non-blocking bounded waiting queue.

### Mistake 6: Keeping unbounded queues when Redis slows down

Large buffers merely shift pressure from Redis to JVM heap. Define caps, wait timeouts, and overflow behavior.

### Mistake 7: Using onBackpressureDrop for non-droppable events

Dropping only fits data that may be lost or coalesced. Mandatory work requires durable storage and reprocessing.

### Mistake 8: Retrying all errors immediately

When Redis is slow, immediate retries add load and trigger cascading failures. Bound retries with backoff, jitter, and error filtering.

### Mistake 9: Assuming timeout means Redis definitely did not execute

Especially dangerous for writes like `INCR`, `XADD`, and `LPUSH`. Client timeouts do not imply rollback; ensure idempotency before retrying.

### Mistake 10: Using publishOn/parallel to "boost Redis capacity"

Switching schedulers does not give Redis more capacity. Schedulers do not replace in-flight limits, pending-command caps, or rate limiting.

### Mistake 11: Ignoring serializers and payload sizes

A `GET` returning a multi-MiB JSON payload does not cost the same as a `GET` returning a few bytes. Pair command caps with byte and time budgets.

### Mistake 12: Ignoring pod count

A limit of 40 in-flight per pod becomes 400 across 10 pods. Account for total fleet load and autoscaling.

### Mistake 13: Looking only at Redis CPU

Redis CPU may look fine while client buffers, event loops, network, or connection pools are saturated. Measure both sides.

### Mistake 14: Unfairly sharing one budget between cache reads and critical writes

A background scan or cache-warming job can consume all permits, starving critical writes. Partition priorities and budgets by workload class when needed.

### Mistake 15: Confusing completed operations with canceled subscriptions

A canceled `Mono` releases its application permit while the already-sent command may still execute on Redis. Factor timeouts/cancellations into capacity analysis.

## 17. Step-by-Step Practice

### Exercise A: Observing flatMap concurrency

Generate 100 test keys and a `Flux` simulating slow work:

```java
Flux.range(1, 100)
        .flatMap(
                n -> Mono.delay(Duration.ofMillis(100))
                        .map(ignore -> n),
                4
        );
```

Measure total elapsed time at concurrency 1, 4, and 8. This uses `Mono.delay`, not Redis commands, to build intuition for active inner counts.

### Exercise B: Switching to Redis GET

Against 100 development Redis keys:

```java
Flux.range(1, 100)
        .flatMap(
                n -> redis.opsForValue()
                        .get("test:device:" + n),
                4
        );
```

Try concurrency 1, 4, 8, and 16 and measure total duration, commands/sec, and application request p95/p99. Never draw conclusions from a single run.

### Exercise C: Multiple concurrent requests

Send concurrent HTTP requests reading the same 100 keys. Compare:

- Only per-request `flatMap(..., 8)`.
- Adding a shared 40-permit semaphore.

Observe latency, timeouts, pending commands, and fail-fast rejections under overload.

### Exercise D: Rate limiting

Add a rate limiter at the API or service boundary before Redis calls while keeping concurrency fixed. Increase input rate and verify actual Redis commands stay within quota. Test with multiple instances if running multi-pod deployments.

### Exercise E: Slow or disconnected Redis

In a safe test environment, inject failures or simulate timeouts. Verify that:

- Retry attempts are bounded.
- Buffers do not grow unboundedly.
- Requests surface explicit overload or timeout errors.
- Once Redis recovers, no prolonged retry storm lingers.
- Side-effecting writes are never retried without control.

## 18. Self-Check Questions

**1. Does backpressure in Reactive Streams send `request(n)` directly to the Redis server?**

No. `request(n)` is a signal between Publisher and Subscriber. The application must use operators and load limits to reduce actual commands sent to Redis.

**2. What does `flatMap(fn, 8)` limit?**

It limits concurrent active inner subscriptions within a single pipeline. It is neither a QPS budget nor a JVM-wide command limit.

**3. With 100 HTTP requests each using flatMap concurrency 8, how many operations can Redis face from that instance?**

Up to around 800 active inner Redis operations if each inner runs one GET and no shared cap exists.

**4. Does `limitRate(32)` guarantee at most 32 commands/sec?**

No. It paces upstream element demand, not time-based rate limits.

**5. Why must concurrency and rate limits be considered separately?**

Concurrency caps simultaneous work, whereas rate limits cap arrivals per time interval. As latency shifts, the same concurrency produces different QPS.

**6. Why avoid `Semaphore.acquire()` in WebFlux?**

Because it can block the event-loop thread. `tryAcquire` with fail-fast or a bounded non-blocking queue is far safer.

**7. Does `timeout` guarantee Redis did not execute an `INCR` command?**

No. The command may already have been sent and completed on Redis even though the client missed the reply.

**8. When is `onBackpressureDrop` appropriate?**

When data loss is acceptable or only the latest value matters. Never use it silently for mandatory business tasks.

**9. Why does a per-pod shared semaphore not guarantee safety for an entire Redis Cluster?**

Because multiple pods have separate budgets and different shards can receive uneven load. Monitor total fleet load and coordinate when needed.

**10. Which metrics should be watched besides throughput when tuning concurrency?**

Watch p95/p99 latency, in-flight counts, rate rejections, timeouts/retries, pending commands, Redis CPU/network, and JVM heap/GC.

## 19. Takeaways

- **Reactive Redis does not mean infinite capacity**: non-blocking I/O improves thread efficiency, not Redis server capacity.
- **Backpressure/demand, concurrency, and rate limits are three distinct concepts**. Do not use one operator to substitute for all limits.
- **`flatMap(mapper, concurrency, prefetch)`** is the core tool to cap inner operations per pipeline; `flatMapSequential` keeps order at buffering cost, while `concatMap` runs sequentially.
- With many concurrent HTTP requests, add **shared in-flight limits** and potentially instance- or fleet-wide rate limits.
- **Buffers must be bounded**, retries must use backoff/jitter, and timeouts never roll back sent commands.
- **Measure both Redis and the application**—especially p95/p99, pending commands, heap, and overload errors—and pick limits based on real workloads and topologies.

### References

- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html).
- [Spring Data Redis — ReactiveRedisTemplate API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/ReactiveRedisTemplate.html).
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- [Reactive Streams — Specification](https://www.reactive-streams.org/).
- [Redis — Latency monitoring](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency-monitor/).
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/).
- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
