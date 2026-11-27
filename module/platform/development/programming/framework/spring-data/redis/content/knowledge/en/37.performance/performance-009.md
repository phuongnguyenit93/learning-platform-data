# Tuning Connection Pools, Connection Counts, and Concurrency in Spring Data Redis

Redis normally delivers ultra-low latency, yet a Spring Data Redis application can still slow down under rising load: requests block waiting to borrow a connection from the pool, too many commands are dispatched concurrently, a few operations hold connections for too long, Redis Server saturates, or multiple instances open thousands of connections collectively. In those moments, blindly raising `max-active` or worker thread counts does not always boost throughput; sometimes it only lengthens queues and degrades p99.

This lesson shows how to **tune pools, connection counts, and concurrency** for real Spring Data Redis workloads. Focus areas include the differences between **Lettuce** and **Jedis**, **shared connections** vs **pooled connections**, isolating blocking/long-lived operations, budgeting connections across multi-instance deployments, controlling concurrency in Spring MVC/WebFlux, and measuring before changing settings.

One core principle to keep front of mind:

> **Connection count does not equal request capacity, and connection pool size does not automatically govern Redis throughput.** Pinpoint whether the bottleneck lies in the pool, Redis client, network, Redis server, or business logic before applying changes.

## 1. Path of a Redis Operation

A `GET` through `StringRedisTemplate` looks simple:

```java
String value = redis.opsForValue().get("cache:product:42");
```

Yet the duration the caller waits spans multiple stages:

```text
HTTP / scheduled job / message handler
          |
          v
Thread or Reactor subscriber
          |
          v
Spring Data Redis template
          |
          +-- serialize key/value
          |
          v
RedisConnectionFactory
          |
          +-- shared native connection?
          |
          +-- borrow from pool?
          |
          +-- establish/reconnect?
          |
          v
Lettuce/Jedis client
          |
          +-- client command queue
          +-- socket / event loop / network
          |
          v
Redis server
          |
          +-- command execution
          +-- CPU/memory/I/O pressure
          |
          v
Response -> deserialize -> business logic
```

Application-observed latency can be broken down conceptually:

```text
T_app
  = T_wait_for_connection
  + T_client_queue_and_serialization
  + T_network
  + T_server_wait_and_execution
  + T_response_processing
```

Stages can overlap, and the framework does not always expose separate metrics for every piece. This model exists to **stop blaming every high latency on "not enough connections."**

Examples:

- High `T_wait_for_connection`: the pool may be exhausted.
- High `T_server_wait_and_execution`: Redis is executing expensive commands, Lua, multi-key ops, or hitting high CPU.
- High network RTT: adding connections will not shrink physical network distance.
- Slow Java GC/serialization: enlarging Redis pools will not fix JVM bottlenecks.
- Commands like `BLPOP` or `XREAD BLOCK` hold connections long: isolate connection types or change worker design.

## 2. Concepts You Should Not Equate

| Concept | Meaning | What It Does Not Automatically Guarantee |
|---|---|---|
| TCP connection | Network socket to a Redis endpoint | Only one request runs per connection at any moment |
| Redis native connection | Connection managed by Lettuce/Jedis | Always thread-safe across all threads in every client |
| `RedisConnection` | Spring Data Redis connection wrapper | Safe to share the same wrapper across multiple threads |
| Connection pool | Set of connections borrowed/returned | Server processes faster simply with a larger pool |
| Pool `max-active` | Active connection ceiling for **that pool** | Ceiling across the entire app, cluster, or all pools |
| Pool `max-idle` | Max idle connections retained | Currently active connections |
| Pool `min-idle` | Target idle count pool tries to maintain | Pool always starts with that exact count immediately |
| `max-wait` | Wait limit when borrowing from an exhausted pool | Timeout for a Redis command itself |
| Command timeout | Wait limit for a command reply per Redis client | That the command never executed on the server |
| Application concurrency | Tasks running simultaneously | Minimum connections must equal concurrent tasks |
| Redis server throughput | Server command processing capacity | Scales linearly with connection count |

In particular, **an application-side pool differs from the client connections counted by Redis Server**. Across 20 pods where each pod runs multiple Redis clients/pools, Redis sees total connections from every source—not just a single `max-active` value in one YAML file.

## 3. Lettuce vs Jedis: First Decision Before Tuning Pools

Spring Data Redis supports Redis clients like **Lettuce** and **Jedis**, with capabilities and configuration varying across Spring Data Redis / Spring Boot versions.

### 3.1. Lettuce: Multiplexing Over a Shared Native Connection

Lettuce builds on Netty and normally supports sharing a **thread-safe native connection** across many concurrent regular commands. The client multiplexes multiple in-flight commands over one connection and correlates replies to each caller.

Model:

```text
Thread A -- GET k1 --+
Thread B -- GET k2 --+
Thread C -- SET k3 --+--> one shared Lettuce native connection
Thread D -- INCR k4 -+          |
                               v
                          Redis server
```

This does **not** mean Redis Server runs all commands in parallel internally; it means callers do not each need their own dedicated socket just to issue regular commands.

Implications:

- One shared native connection can handle many regular requests.
- Enlarging a connection pool for routine `GET`s often yields little effect.
- Multiple connections can help in specialized workloads, yet must be proven by measurement.
- Blocking ops, transactions, and subscriptions follow different connection rules from standard `GET`/`SET`.
- Never equate a **thread-safe native Lettuce connection** with assuming low-level Spring `RedisConnection` wrappers are thread-safe.

### 3.2. Jedis: Connection Management Works Differently

Jedis generally borrows a connection per operation; a `Jedis` connection object must not be shared across threads concurrently.

With Jedis, connection pooling directly governs socket reuse for concurrent operations. If connections run out, callers wait on the pool. If the pool is too large, Redis holds more sockets without necessarily having CPU to process them.

### 3.3. Never Copy Pool Settings Between Clients Blindly

`max-active=32` might help a Jedis workload while leaving most routine `GET` traffic on a shared Lettuce connection unchanged.

Before tuning, verify:

1. Does the app use `LettuceConnectionFactory` or `JedisConnectionFactory`?
2. Does `LettuceConnectionFactory` have `shareNativeConnection` enabled?
3. Are pooling properties and required dependencies (such as `commons-pool2`) actually present?
4. Which operations genuinely borrow dedicated/pooled connections?
5. Are there multiple `RedisConnectionFactory` beans in one application context?
6. Do Pub/Sub, stream polling, transactions, or blocking commands hold connections long?

## 4. `LettuceConnectionFactory` and Shared Native Connections

In common setups, `LettuceConnectionFactory` shares a **native connection** for ordinary non-blocking, non-transactional commands.

Concept:

```text
StringRedisTemplate
      |
      v
LettuceConnectionFactory
      |
      +--> shared native Lettuce connection
      |        |
      |        +-- GET
      |        +-- SET
      |        +-- HGET
      |        +-- INCR
      |
      +--> dedicated connection when needed
               |
               +-- blocking operation
               +-- transaction/session
               +-- specific special cases
```

Exact details on dedicated connections and pooling must be verified against your Spring Data Redis / Lettuce version, yet the key boundary stands: **do not assume every `opsForValue().get()` borrows a connection from a pool**.

### 4.1. Why Might Pool Size Not Affect `GET`?

Suppose an application executes:

```java
redis.opsForValue().get("product:1");
redis.opsForValue().get("product:2");
redis.opsForValue().get("product:3");
```

using a shared Lettuce connection. Routine calls travel over that shared native connection. Changing:

```yaml
spring:
  data:
    redis:
      lettuce:
        pool:
          max-active: 64
```

does not suddenly fan those three `GET`s out across 64 connections. The pool may serve only dedicated connections or configurations explicitly using pooling.

**Proper tuning follows the actual command execution path**, not property names alone.

### 4.2. `shareNativeConnection=false` Is Not a Default Speed Boost

You can configure `LettuceConnectionFactory` not to share the native connection for routine operations:

```java
factory.setShareNativeConnection(false);
```

However, this forces many calls to borrow or open dedicated connections. Without pooling, socket/auth setup overhead explodes. With pooling, requests can queue waiting to borrow connections.

Consider disabling sharing only with evidence that the shared connection is unsuitable—such as isolating specific workloads or specific queueing issues—and benchmark before/after.

### 4.3. Never Hold a `RedisConnection` Across Threads

Incorrect abstraction usage:

```java
RedisConnection conn = connectionFactory.getConnection();

// Store conn globally and let multiple threads call it directly?
```

Spring Data Redis expects connection wrappers to be managed per template call or callback/session, never shared arbitrarily across threads.

Use:

```java
StringRedisTemplate
```

or:

```java
redis.execute((RedisCallback<String>) connection -> {
    // Operate within the callback scope.
    return "...";
});
```

The framework manages connection lifecycle properly, and template objects are designed to be reused safely under concurrency when configured properly.

## 5. When Is a Connection Pool Actually Needed?

Pooling helps when **connections cannot be shared** or when opening fresh connections costs too much relative to operation lifetimes.

Scenarios to evaluate:

| Workload | Connection Issue | Direction to Consider |
|---|---|---|
| Short GET/SET on shared Lettuce connection | Shared connection multiplexes | Measure first; pool is rarely the main knob |
| Jedis under concurrent requests | Each thread must borrow a connection | Bounded pool with borrow timeout |
| Redis `BLPOP`, `BRPOP` | Blocking commands hold connections while waiting | Dedicated connections; size by consumer count |
| `XREAD BLOCK` / stream polling | Polling holds connections for block windows | Separate pool/factory or dedicated budget |
| `MULTI/EXEC` / `WATCH` transactions | Sessions require consistent connection binding | Dedicated/session-safe connections |
| Redis Pub/Sub | Long-lived subscription connections | Isolate from request-serving connections if needed |
| Native Lettuce/Jedis conn per request | Constant socket creation is costly | Pooling or shared connection as appropriate |
| Multi-primary Cluster | Connections span nodes/slots | Account for node count and driver topology |
| Sentinel failover | Connections must fail over and reroute | Reconnect and discovery, not bigger pools |

A well-tuned pool **reuses a finite resource**; it is not a standalone turbocharger.

## 6. Configuring Lettuce Pooling in Spring Boot

With Spring Boot 3.x and typical Redis settings:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 2s
      lettuce:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 2
          max-wait: 300ms
```

These are **starting values for measurement**, not universal standards. Real settings depend on concurrency, dedicated-connection usage, Redis server capacity, and fleet-wide connection budgets.

Matching Gradle dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    // When using commons-pool-backed connection pooling:
    implementation 'org.apache.commons:commons-pool2'
}
```

`commons-pool2` provides the pool implementation used by Spring Data Redis/Lettuce pooling. Under Spring Boot/BOM, let dependency management resolve the compatible version.

### 6.1. Meaning of Each Property

| Property | Meaning | What to Avoid |
|---|---|---|
| `client-type: lettuce` | Selects Redis client per Boot support | Assuming it automatically turns on pooling |
| `connect-timeout` | Wait limit to establish connection | Treating it as Redis command timeout |
| `timeout` | Command reply timeout per Boot/client config | Treating timeout as proof the command never ran |
| `pool.enabled` | Enables pooling if Boot/version/dependency supports it | Assuming pools serve every GET on a shared connection |
| `pool.max-active` | Max active connections in this pool | Blindly multiplying by HTTP request thread count |
| `pool.max-idle` | Max idle connections kept open | Setting huge values holding unnecessary sockets |
| `pool.min-idle` | Target idle count pool tries to maintain | Setting equal to `max-active` on every pod |
| `pool.max-wait` | Max wait to borrow when pool is exhausted | Infinite wait when APIs have tight deadlines |

Property names and defaults can vary across Spring Boot versions; inspect the metadata for your stack. The snippet above reflects common Boot 3.x naming.

### 6.2. `max-active` Is a Ceiling, Not Startup Count

Setting `max-active=16` and `min-idle=2` does **not** mean the app immediately opens and uses 16 sockets. The pool creates connections on demand, retains idle connections per policy, and evicts excess idle ones.

When checking Redis:

```redis
INFO clients
```

`connected_clients` also counts other apps, `redis-cli`, subscriptions, monitoring exporters, and driver-managed connections outside that pool.

### 6.3. When `max-wait` Expires

If every pooled connection is active and more callers arrive:

```text
Requests 1...16 -> holding all 16 pooled connections
Request 17      -> waiting to borrow
Request 18      -> waiting to borrow
...
```

With `max-wait=300ms`, a caller fails if it cannot borrow a connection within 300 ms. That failure differs from a Redis command that was already sent to the server and timed out waiting for a reply.

If the app calls `GET` over a shared Lettuce connection, borrow queueing may **never happen on that GET path**. Verify which operations actually borrow from the pool when interpreting metrics.

## 7. Explicitly Configuring `LettucePoolingClientConfiguration`

When bypassing Spring Boot auto-configuration or configuring the factory explicitly, Spring Data Redis offers `LettucePoolingClientConfiguration`.

Illustrative example:

```java
package com.example.redis;

import java.time.Duration;

import io.lettuce.core.api.StatefulConnection;
import org.apache.commons.pool2.impl.GenericObjectPoolConfig;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettucePoolingClientConfiguration;

@Configuration(proxyBeanMethods = false)
public class RedisPoolConfiguration {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);

        GenericObjectPoolConfig<StatefulConnection<?, ?>> pool =
                new GenericObjectPoolConfig<>();

        pool.setMaxTotal(16);
        pool.setMaxIdle(8);
        pool.setMinIdle(2);
        pool.setMaxWait(Duration.ofMillis(300));
        pool.setBlockWhenExhausted(true);

        LettuceClientConfiguration client =
                LettucePoolingClientConfiguration.builder()
                    .poolConfig(pool)
                    .commandTimeout(Duration.ofSeconds(2))
                    .build();

        LettuceConnectionFactory factory =
                new LettuceConnectionFactory(server, client);

        // The factory's shared connection mode should be
        // chosen intentionally per workload.
        // Do not change the default just because pooling is enabled.
        return factory;
    }
}
```

This uses common Spring Data Redis, Lettuce, and Commons Pool 2 APIs; verify exact builder/generic signatures for your deployed version. Once you declare your own factory bean, many Spring Boot properties **will not automatically apply** unless your code reads them.

### 7.1. Do Not Set `shareNativeConnection(false)` Mechanically

You can add:

```java
factory.setShareNativeConnection(false);
```

when you genuinely want routine operations to stop using the shared native connection. Before doing so, evaluate:

- Pool borrow/return overhead across high command rates.
- Active connection count on Redis.
- Pool wait times and exhaustion errors.
- Throughput and p95/p99 before/after.
- Interaction with transactions, blocking commands, and reconnects.

Enabling pooling does not mean every app should disable shared connections. A shared-by-default factory can perform far better for large volumes of short cache GETs.

### 7.2. `validateConnection` and Validation Overhead

`LettuceConnectionFactory` has an option to validate connections on borrow. Proactive validation catches broken connections in certain setups, yet adds extra work—such as `PING`/I/O—to the connection acquisition path depending on implementation.

Avoid enabling validation on every operation without measuring latency, especially when routine GETs use a shared connection with built-in client reconnection.

### 7.3. Avoid Unintentionally Duplicating Connection Factories

Suppose an application defines:

```text
RedisConnectionFactory A -> StringRedisTemplate
RedisConnectionFactory B -> ReactiveRedisTemplate
RedisConnectionFactory C -> RedisMessageListenerContainer
```

Each factory/client can maintain separate connections, pools, and threads. When targeting one Redis deployment, verify which factories can reasonably be shared and which truly need isolation per workload rather than creating extra beans casually.

When multiple factories exist, sum connection budgets across the **entire application**, not just one pool.

## 8. Jedis Pooling in Spring Boot

If the application selects Jedis:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 2s
      jedis:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 2
          max-wait: 300ms
```

Requires the Jedis dependency and typically Commons Pool 2. Since the default Spring Boot Redis starter usually ships Lettuce, switching to Jedis requires adjusting dependencies and `client-type` consistently—avoid leaving both drivers on the classpath without understanding Boot's auto-configuration precedence.

Key differences:

- A Jedis connection object must not be shared across concurrent threads.
- Pooling becomes an explicit contention point since operations borrow connections.
- Pool sizing must cover **all operations holding connections simultaneously**, not just HTTP request count.
- Broken connections after failover must be replaced by client/pool validation/eviction mechanisms.
- Synchronous/reactive API coverage and topology features differ across drivers and versions.

**There is no single `max-active` number valid across both Lettuce and Jedis.** The same workload can require very different connection strategies.

## 9. Mental Model for Estimating Concurrency

As a starting point, apply **Little's Law**:

\[
L \approx \lambda \times W
\]

where:

- \(L\): average operations concurrently waiting or executing in a stable system.
- \(\lambda\): throughput, e.g., Redis operations per second.
- \(W\): average time an operation spends in the system, in seconds.

Suppose a service issues **1,200 Redis operations/second**, spending **8 ms** on average along the path:

\[
L \approx 1200 \times 0.008 = 9.6
\]

On average, roughly **10 operations are in-flight** along that measured path at any instant.

This **does not prove you need a 10-connection pool**:

- With a shared Lettuce connection, multiple operations can sit in-flight over one native connection.
- With Jedis, connection occupancy includes borrow/return time plus execution.
- Averages hide bursts and tail latency.
- If each HTTP request calls Redis five times, calculate using **Redis operations**, not HTTP requests.
- If operations already wait on the pool, \(W\) includes queueing delay; feeding inflated \(W\) back into pool sizing creates a misleading loop.
- Once Redis Server saturates, raising concurrency inflates \(W\) without proportional throughput gains.

Use this formula to **estimate workload scale and sanity-check numbers**, then validate with real measurements.

## 10. Distinguishing Request Count, Command Count, and Connection Count

Suppose an app handles:

```text
300 HTTP requests/s
Each request:
  GET user
  GET permissions
  GET product
  SET cache
  INCR metric
```

Redis traffic can reach:

```text
300 requests/s × 5 commands/request
= ~1,500 Redis commands/s
```

If those five commands execute sequentially per request, one HTTP request does not hold five concurrent commands at once.

Conversely, if code uses `Mono.zip` or `flatMap` to fan out independent commands in parallel, in-flight commands jump substantially even at the exact same HTTP RPS.

### 10.1. Measuring Connection Occupancy

For a pool where each operation requires a dedicated connection:

```text
Need enough active connections for peak concurrent
connection-holding tasks + a measured safety margin.
```

Example:

```text
Concurrent BLPOP workers:            8
Concurrent Redis transactions:       4
Other dedicated-connection tasks:    2
```

If **sharing one pool**, budget at least 14 active connections before bursts and failovers. If those tasks live on separate factories/clients, do not lump them together inaccurately.

Never set `max-active=200` by default simply because "the servlet container has 200 threads."

## 11. Connection Budgets Across Multiple Instances

Here is where harmless single-pod settings become production outages.

Suppose:

```text
8 application pods
Each pod:
    1 factory for GET/SET
    1 factory for stream listeners
    dedicated pool max 24
    additional shared/subscription connections
```

Theoretical connection ceiling is not `24`, but relates to:

```text
8 pods × 24 pooled connections = 192 pooled connections
```

Plus:

- Shared native connections.
- Redis Pub/Sub subscriptions.
- Blocking stream consumers.
- Redis CLI / monitoring connections.
- Admin / exporter connections.
- Other services sharing the same Redis.
- Connections to replicas or other nodes in Cluster.
- Surge connections during rolling deployments when old and new pods overlap.

**`max-active` caps a single pool, not total Redis connections across the deployment.** Pools may not reach the cap constantly, so this gives a **worst-case** budget rather than current `connected_clients`.

### 11.1. Practical Budgeting Table

Build a table:

| Source | Instances | Max Conn / Instance | Estimated Ceiling |
|---|---:|---:|---:|
| API service A | 8 | 16 | 128 |
| Background worker B | 4 | 12 | 48 |
| Pub/Sub listeners | 8 | 1–n | Topology-dependent |
| Exporters/health/CLI | n | n | Reserve |
| Deployment surge | n | n | Reserve |
| Other clients | n | n | Reserve |

Do not sum example numbers and treat them as a single server's total. Break budgets down **per actual endpoint**, because Cluster has multiple nodes and Sentinel exposes separate monitoring endpoints.

### 11.2. Relationship to `maxclients`

Redis limits client connections via `maxclients` alongside OS file descriptor limits. Check:

```redis
CONFIG GET maxclients
INFO clients
INFO stats
```

Warning signs:

- `connected_clients` approaching the cap.
- `rejected_connections` increasing.
- Application errors opening connections or timing out.
- Redis host hitting OS file descriptor limits.
- Sudden connection spikes during deployments.

Do not simply raise `maxclients` without checking memory and OS limits; every client connection consumes resources and input/output buffers.

## 12. Redis Cluster: Connections Span Multiple Nodes

In Redis Cluster:

```text
Spring service
     |
     v
Cluster-aware client
     |
     +-- Primary A (slots ...)
     +-- Primary B (slots ...)
     +-- Primary C (slots ...)
     +-- replicas if read policy uses them
```

Clients maintain connections to multiple nodes based on topology, read preferences, and workload. Thus:

- One app pod does not open just one total TCP connection.
- Pools and connection limits can multiply per node or client config.
- Nodes with skewed workloads see uneven connections and in-flight commands.
- Resharding shifts where commands route.
- Cluster topology refresh adds connection management overhead.
- Failovers/redirects open new connections during recovery.

When budgeting, inspect `INFO clients` **on every primary and replica**, rather than checking one node as representative of the whole cluster.

### 12.1. Hash Slots and Hot Keys Matter More Than Pool Size

If all keys share one hash tag:

```text
cache:{all}:product:1
cache:{all}:product:2
cache:{all}:product:3
```

they hit the same slot, overloading one primary while others sit idle.

Enlarging the app pool never moves keys to other nodes. Fix key schemas, hot slots, data distribution, and command mixes first.

### 12.2. Pipelining on Cluster

Pipelining saves round trips, yet cross-node routing and error handling depend on driver and Spring Data Redis versions. Never assume a multi-slot pipeline is atomic or travels over one connection.

If round-trip latency per command is the bottleneck, **proper batching/pipelining** beats adding connections—provided you test routing, ordering, timeouts, and retries.

## 13. Sentinel: Reconnecting Is Not Raising Pool Size

With Redis Sentinel, clients must discover the new primary during failover:

```text
Old primary fails
   |
   v
Sentinel promotes a replica to new primary
   |
   v
Client updates endpoint and reconnects
   |
   v
Redis commands resume
```

If timeouts happen during failover, doubling `max-active` will not speed up Sentinel election or client endpoint discovery.

Verify:

- The client is Sentinel-aware rather than pointing at a static primary host.
- Addresses advertised by Sentinel are reachable from the application network.
- Command/connect timeouts and topology refresh/reconnect settings are aligned.
- Stale pooled connections are evicted and replaced cleanly.
- Redis auth/TLS works on the promoted primary.
- Unknown-outcome writes during connection drops are handled safely.

Post-failover, never blindly retry `INCR`, `LPUSH`, or other non-idempotent writes just to hide transient errors.

## 14. Blocking Commands Occupy Connections for the Wait Duration

A regular command:

```redis
GET cache:product:42
```

finishes quickly.

Meanwhile:

```redis
BLPOP queue:jobs 0
```

can block **indefinitely** until an item arrives. A connection executing a blocking command cannot multiplex independent commands on that same waiting flow.

Similarly, Redis Streams:

```redis
XREADGROUP GROUP workers worker-1 BLOCK 5000 STREAMS stream:jobs >
```

can hold a connection waiting up to 5 seconds or until an entry arrives.

### 14.1. Why Can Pools Exhaust?

Suppose a pool has `max-active=8` while 8 workers run unbounded `BLPOP`:

```text
Pool size: 8
Worker 1 -> BLPOP holds connection 1
Worker 2 -> BLPOP holds connection 2
...
Worker 8 -> BLPOP holds connection 8

GET request needing a dedicated connection:
    None left -> waits max-wait -> fails
```

With a shared Lettuce connection, regular GETs may still use the separate shared native connection depending on factory configuration, yet everything borrowing from **the dedicated pool** competes for that shared budget.

Design guidelines:

- Count concurrent blocking consumers explicitly.
- Set finite `BLOCK` timeouts where sensible.
- Isolate blocking consumers into a separate factory/pool when workloads contend.
- Never spawn unbounded consumer threads without connection/server budgets.
- Monitor Redis `blocked_clients` alongside pool active/waiting counts.
- For Streams, manage consumer groups, ACK, pending, and reclaim separately from pool sizing.

### 14.2. Block Timeout Differs from Borrow Timeout

Suppose:

```text
Pool max-wait:          200 ms
XREAD BLOCK timeout:  5000 ms
Redis command timeout: 3000 ms
```

If Redis command timeout is shorter than the client's intended `BLOCK` duration, the client times out even while the server is legitimately waiting.

Align all timeouts together:

- Pool borrow wait time.
- Redis command timeout.
- `BLPOP`/`XREAD` `BLOCK` duration.
- Overall worker/request deadline.
- Shutdown and cancellation behavior.

Do not pick independent numbers just because each YAML property has a field.

## 15. Pub/Sub and Listener Containers: Long-Lived Connections

`RedisMessageListenerContainer` manages a long-lived subscription connection for channels or patterns, serving multiple listeners attached to the container.

```text
RedisMessageListenerContainer
       |
       +-- subscription connection (long-lived)
       |
       +-- callback dispatch executor
                |
                +-- MessageListener A
                +-- MessageListener B
```

Separate two resources:

1. **Redis subscription connection**.
2. **Thread/executor** dispatching and running Java handlers.

If handlers are slow, enlarging the Redis connection pool rarely helps because the bottleneck sits in the callback executor or downstream database.

### 15.1. Subscription Executor and Listener Task Executor

Illustrative configuration:

```java
@Bean
RedisMessageListenerContainer redisMessageListenerContainer(
        RedisConnectionFactory connectionFactory,
        MessageListener listener,
        @Qualifier("redisListenerExecutor") Executor listenerExecutor,
        @Qualifier("redisSubscriptionExecutor") Executor subscriptionExecutor
) {
    RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setTaskExecutor(listenerExecutor);
    container.setSubscriptionExecutor(subscriptionExecutor);

    container.addMessageListener(
        listener,
        new ChannelTopic("catalog.events")
    );

    return container;
}
```

Executor beans are defined elsewhere in application config. Never share a single-threaded executor for both holding long-lived subscriptions and executing callbacks if doing so starves callbacks.

And regardless of executor threads, Pub/Sub still has **no durable ACK/replay**; messages drop if subscribers are offline. Tuning pools or threads never creates durable delivery.

## 16. Spring MVC Thread Counts and Redis Pools

In Spring MVC / Tomcat:

```text
HTTP worker thread
     |
     v
Service
     |
     v
StringRedisTemplate GET
     |
     v
Thread waits for result then resumes
```

If each request waits on Redis, HTTP thread count and total latency shape concurrency. Yet with a shared Lettuce native connection, **you do not automatically set pool size equal to Tomcat thread count**.

Risks to watch:

- Too many HTTP threads can drive traffic to Redis faster than Redis handles it.
- An endpoint issuing 20 Redis calls behaves very differently from one issuing 1 call.
- Multi-second Redis timeouts tie up worker threads, blocking new incoming requests.
- Pool borrow wait adds onto command timeout, inflating total request duration.
- Raising HTTP worker threads may just amplify downstream queueing and timeouts.

When tuning, measure **HTTP concurrency, Redis command concurrency, and pool metrics** together rather than staring at one property.

## 17. WebFlux and ReactiveRedisTemplate: Bounding with Reactor

Spring WebFlux uses `ReactiveRedisTemplate` or `ReactiveStringRedisTemplate`, returning `Mono`/`Flux` instead of blocking synchronously.

Example:

```java
Mono<String> value =
        reactiveRedis.opsForValue().get("cache:product:42");
```

Reactive APIs do not block a worker thread per command. However, that does **not** mean you can launch **unbounded** parallel Redis operations.

Potentially unbounded example:

```java
return Flux.fromIterable(productIds)
        .flatMap(id ->
            reactiveRedis.opsForValue()
                    .get("cache:product:" + id)
        );
```

`flatMap` uses Reactor's default concurrency per version/operator—not a value tuned for production Redis. With huge ID lists, unrestricted fan-out overwhelms drivers, network buffers, and Redis Server.

### 17.1. Bound Concurrency Explicitly

```java
public Flux<String> cachedProducts(List<String> productIds) {
    int concurrency = 16;

    return Flux.fromIterable(productIds)
            .flatMap(
                id -> reactiveRedis.opsForValue()
                        .get("cache:product:" + id),
                concurrency
            );
}
```

`16` is illustrative only. Measure:

- Redis operations/sec.
- Tail latency.
- Netty event-loop/CPU.
- Timeouts and retries.
- Client pending command counts.
- Redis server CPU and command latency.

Across 20 pods, concurrency `16` per request **does not mean** total in-flight commands equal 16; multiply by concurrent requests across all pods.

### 17.2. When Result Ordering Matters

`flatMap` can emit items out of input order.

```java
return Flux.fromIterable(productIds)
        .concatMap(id ->
            reactiveRedis.opsForValue()
                .get("cache:product:" + id)
        );
```

`concatMap` runs sequentially, preserving order at the cost of concurrency. `flatMapSequential` runs inner publishers concurrently while emitting in input order, trading buffer memory and tail latency.

Note: missing Redis keys emit `Mono.empty()` in many APIs; wrap results with the ID if you need a 1:1 entry per input including cache misses.

### 17.3. Reactive Backpressure Does Not Replace `maxmemory` or Redis Capacity

Even if `Flux.take(10)` requests only 10 items downstream, a command like `SMEMBERS` still pulls an entire large dataset. Reactor backpressure **does not instruct Redis Server to read only 10 elements**.

Avoid unbounded data commands; use bounded ranges/scans/cursors. Never raise pool sizes to fix a command returning excessive data.

## 18. Tuning Concurrency for Batching and Pipelining

Redis pipelining cuts network round-trip overhead by sending multiple commands before awaiting replies, without creating an atomic transaction.

Model:

```text
Without pipeline:
  GET A -> wait
  GET B -> wait
  GET C -> wait

With pipeline:
  GET A
  GET B
  GET C
  -> receive responses
```

In Spring Data Redis:

```java
List<Object> results = redis.executePipelined(
    (RedisCallback<Object>) connection -> {
        for (String key : keys) {
            connection.stringCommands().get(
                redis.getStringSerializer().serialize(key)
            );
        }
        return null;
    }
);
```

Here `keys` is a `List<String>` passed into the method; the callback returns `null` per the `executePipelined` contract.

### 18.1. How Does Pipelining Affect Pools and Concurrency?

- A pipeline dispatches multiple commands over one or several connections depending on driver and topology.
- Cutting round trips can lift throughput **without adding connections**.
- Oversized batches inflate response buffering, tail latency, and Redis server load.
- Writes inside pipelines can still yield partial results or uncertain outcomes on timeout.
- In Redis Cluster, cross-slot/node pipelining has driver/version-specific constraints.
- Pipelining never substitutes for Lua or `MULTI/EXEC` atomicity.

Benchmark batch sizes from small → medium → large while tracking p95/p99 and memory. Never treat "cramming more commands into one batch is always faster" as a rule.

### 18.2. Use Native Redis Commands When Appropriate

Some operations are faster and safer as native atomic commands:

```java
redis.opsForValue().increment(counterKey);
```

instead of:

```text
GET counter
parse + 1
SET counter
```

`INCR` saves a round trip and prevents lost updates in non-atomic read-modify-write sequences.

For same-slot or standalone keys, `MGET` helps; when moving to Redis Cluster, check same-slot constraints and client fan-out behavior.

## 19. Why Can Adding Connections Worsen Performance?

Suppose Redis Server sustains roughly **X commands/s** for the current workload. If the app sends more than X:

```text
Arrival rate > service capacity
          |
          v
Queue growth
          |
          v
Waiting + timeouts
          |
          v
Retries (if enabled)
          |
          v
Arrival rate grows even higher
```

Enlarging pools lets more concurrent commands hit Redis, pushing the server into saturation faster. Without backpressure, tail latency climbs even while successful throughput barely budges.

Warning signs:

- Pool active count rises while completed ops/sec stays flat.
- Redis CPU climbs and command latency spikes.
- Client pending commands/queues grow.
- P99 worsens immediately after raising `max-active`.
- `rejected_connections` rises as pods open more sockets.
- Redis memory climbs due to client output buffers.
- Downstream DB or external services overload from higher handler concurrency.

Never judge a setup by one metric such as "number of open connections."

## 20. Isolating Workloads with Separate Pools When Needed

One Redis deployment may serve:

```text
1. Cache GET/SET (latency-sensitive)
2. Background cache warm-up (batch-heavy)
3. Stream workers with XREAD BLOCK
4. Pub/Sub subscriptions
5. Lua scripts / transactions
```

Not every workload should share one connection factory or pool. If one group holds dedicated connections long or creates big bursts, isolate resources.

Model:

```text
                     Spring application
                           |
               +-----------+-----------+
               |           |           |
             Cache       Stream       Pub/Sub
             template    worker       container
               |           |           |
          Factory A    Factory B    Factory C
           (shared)    (dedicated) (subscription)
               |           |           |
               +-----------+-----------+
                           |
                         Redis
```

Potential benefits:

- Blocking stream consumers cannot starve cache requests of pooled connections.
- Cache and stream polling can have distinct timeouts.
- Concurrency/queues can be capped per workload.
- Connection counts, errors, and latencies are easier to monitor separately.

Trade-offs:

- Multiple connection factories increase total open sockets.
- Redis host/auth/TLS configuration must stay consistent across factories.
- More beans increase configuration complexity.
- On Cluster, total managed connections scale with node count.
- Splitting pools **does not create extra Redis Server CPU**; workloads still share server capacity.

Isolate only when measurements justify it or when blocking/subscription semantics require separation.

## 21. Aligning Timeouts Within an End-to-End Budget

An HTTP request with a 1-second deadline yet configured with:

```text
Pool max-wait:     2 seconds
Redis timeout:     5 seconds
DB timeout:        3 seconds
```

is hard to control because each layer's limit far exceeds what the caller accepts.

Define a layered budget:

```text
HTTP request budget
    |
    +-- authentication / business logic
    +-- pool borrow budget
    +-- Redis command budget
    +-- downstream work
    +-- serialization / response
```

Illustrative example:

```text
HTTP SLA/deadline:         800 ms
Pool borrow budget:        100 ms
Redis command budget:      250 ms
Business + DB budget:      350 ms
Response/margin:           100 ms
```

Numbers illustrate budgeting only, not universal defaults. When a request issues multiple sequential commands, total budget must cover all steps plus retries.

### 21.1. Timeouts Do Not Prove Commands Never Ran

For:

```redis
INCR metrics:charged
```

a timeout can occur **after Redis already incremented** yet before the reply reaches the client. Blind retries double-increment.

Pool tuning, retry policies, and idempotency must be designed together. Enlarging pools to "cut timeouts" never replaces handling uncertain outcomes.

### 21.2. Infinite Pool Wait Does Not Fit Request Deadlines

Negative/infinite `max-wait` leaves callers stuck indefinitely waiting to borrow when pools saturate. In deadline-bound services, set finite wait limits, count rejections, and shed overload gracefully.

Conversely, an overly tiny `max-wait` causes false failures during harmless short bursts; size it from p95/p99 borrow wait metrics and business sensitivity.

## 22. Retries Can Trigger a "Connection Storm"

When Redis slows down briefly, systems can spiral:

```text
Redis slows down
  -> command timeouts
  -> all callers retry immediately
  -> concurrent commands surge
  -> Redis slows further
  -> pods autoscale up
  -> new connections surge
  -> cascading failure
```

This is a retry storm / connection storm.

Mitigations:

- Bounded retries with **jittered exponential backoff** only on retryable errors.
- Circuit breakers or bulkheads for non-critical workloads.
- Caller concurrency caps.
- Never retry non-idempotent commands without operation IDs/deduplication.
- Avoid rapid pod autoscaling when Redis is already near connection/server limits.
- Watch pool borrow wait, connect errors, and Redis `rejected_connections`.
- Shed load gracefully if Redis is purely a cache and the origin can sustain traffic.

**Never enable blanket retries on all Spring Data Redis exceptions.** `WRONGTYPE`, `CROSSSLOT`, and script argument errors are design/data bugs that infinite retries will never heal.

## 23. Metrics to Monitor on Both Application and Redis Server

Every tuning cycle must watch both sides.

### 23.1. Application Metrics

| Metric | Purpose |
|---|---|
| Redis command throughput | Commands sent/completed by type |
| Redis command duration p50/p95/p99 | Client-observed latency |
| Pool active | Dedicated connections currently borrowed |
| Pool idle | Idle connections available |
| Pool waiters | Callers waiting to borrow |
| Pool borrow wait duration | Time spent waiting for a connection |
| Pool borrow failures/timeouts | Signals connection shortage or saturation |
| Connect/reconnect attempts | Signals network/topology instability |
| Client command queue/pending requests | Detects excessive fan-out |
| Application request p95/p99 | Real user impact |
| Retry count and retry delay | Separates baseline load from retry amplification |
| Event-loop blocking / GC pauses | Pinpoints JVM bottlenecks |
| Worker/HTTP thread utilization | Impact of synchronous Redis calls |

Not every metric above is exported out of the box by Spring Boot. Availability depends on Lettuce/Jedis, Commons Pool, Micrometer, Actuator, and custom instrumentation.

### 23.2. Redis Server Metrics

Redis CLI:

```redis
INFO clients
INFO stats
INFO commandstats
INFO memory
INFO cpu
INFO persistence

CONFIG GET maxclients
SLOWLOG GET 20
LATENCY LATEST
```

Helpful indicators:

| Indicator | Explanation |
|---|---|
| `connected_clients` | Open client connections |
| `blocked_clients` | Clients waiting on blocking commands and related states |
| `rejected_connections` | Connections refused due to Redis limits/state |
| `instantaneous_ops_per_sec` | Estimated instantaneous command rate |
| `total_commands_processed` | Cumulative commands processed by server |
| `cmdstat_get` / `cmdstat_set` | Per-command stats depending on Redis version |
| `used_memory` and RSS | Memory pressure and overhead |
| CPU time | Whether server is resource-bound |
| Persistence in progress / fork latency | Whether snapshots/AOF rewrites cause latency spikes |

### 23.3. SLOWLOG Does Not Measure Total Latency

`SLOWLOG` inspects server-side command execution time per Redis semantics; it excludes pool wait, network transit, and Java serialization.

Example:

```text
Application GET p99: 500 ms
SLOWLOG: zero slow GETs
```

does not prove Redis access is healthy. Most latency may sit in **pool borrow**, client queues, reconnects, or the network.

Conversely, if `SLOWLOG` reveals heavy commands or long Lua scripts, enlarging the connection pool will never fix that server bottleneck.

## 24. Monitoring Commons Pool 2

When Spring Data Redis uses Apache Commons Pool 2, `GenericObjectPool` statistics can be exposed within application/driver scope.

Corresponding metrics:

```text
numActive
numIdle
numWaiters
mean/max borrow wait
borrowed count
created/destroyed count
```

Access via JMX/MBeans, registries, or client instrumentation depends on Spring Data Redis/Lettuce/Jedis and configuration.

Never assume a fixed Micrometer meter named `redis.pool.active` exists in every project. If writing a custom exporter, pick stable metric names and verify binding to **the exact pool** used by `RedisTemplate`.

### 24.1. Distinguishing Pool Exhaustion from Server Overload

| Symptom | Likely Cause | Next Investigation Step |
|---|---|---|
| `active` near max, `waiters` rising, Redis CPU low | Pool too small or connections held too long | Trace borrow duration, blocking commands, leaks |
| `active` low, Redis CPU high, p99 high | Server/command bottleneck | Commandstats, SLOWLOG, scripts, big keys |
| `connected_clients` huge, many idle | Oversized pools or scaled pods | Lower `min-idle`/`max-idle`, audit factories |
| Connect errors surge during deploy | Connection storm, `maxclients`, auth/network | Inspect Redis/OS/client logs |
| Pool wait low yet HTTP slow | Bottleneck in DB or other logic | Distributed tracing |
| `blocked_clients` high | Many blocking consumers | XREAD/BLPOP workers, pool isolation |
| High memory with many clients | Buffers/queues and overhead | `CLIENT LIST`, `INFO memory` |

Use this table as an investigation guide, not a definitive diagnosis from one metric alone.

## 25. Instrumenting Redis Operation Timing in Spring

A Micrometer `Timer` can measure `StringRedisTemplate` latency from the application:

```java
package com.example.redis;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;
    private final Timer getTimer;

    public ProductCacheReader(
            StringRedisTemplate redis,
            MeterRegistry registry
    ) {
        this.redis = redis;
        this.getTimer = Timer.builder("app.redis.cache.get")
                .description("Redis GET duration from application")
                .register(registry);
    }

    public String get(String productId) {
        String key = "cache:product:" + productId;

        return getTimer.record(
                () -> redis.opsForValue().get(key)
        );
    }
}
```

This measures **total client call duration** without breaking down individual sub-stages. Combining native client command metrics with service `Timer`s helps pinpoint where time is spent.

Never put `productId` or raw Redis keys into metric labels; cardinality explodes. Tag by operation family or cache resource instead.

### 25.1. Separate Borrow Time from Command Time When Possible

A `Timer` wrapping `redis.opsForValue().get(...)` does not show how many milliseconds went into pool wait. To diagnose pool saturation, instrument borrow timing or read pool metrics directly.

A thorough timeline breaks down:

```text
HTTP request start
    |
    +-- pool borrow wait
    |
    +-- Redis command RTT
    |
    +-- Java decode + business logic
    |
HTTP response
```

With distributed tracing, create spans per operation type and layer—never putting sensitive keys/values into traces.

## 26. Preventing Connection Leaks and Long-Held Sessions

A connection borrowed from a pool and never returned drives `active` upward until the pool starves.

With `RedisTemplate`, the framework manages connection lifecycles automatically. When calling the low-level factory directly:

```java
RedisConnection conn = connectionFactory.getConnection();
```

always close/release properly:

```java
try (RedisConnection conn = connectionFactory.getConnection()) {
    // Operate within the connection scope.
}
```

`close()`/release semantics vary by implementation and Spring Data Redis context, so prefer `RedisTemplate.execute(...)` callbacks unless manual connection control is truly required.

### 26.1. Transactions and SessionCallback

When `SessionCallback` pins a connection across multiple commands, never run slow HTTP calls or external API waits inside that session.

Risky example:

```text
Borrow Redis connection
WATCH key
Call external service (waits 5 seconds)
MULTI/EXEC
Release connection
```

During those 5 seconds waiting on an external service, the connection sits pinned doing zero Redis work, starving pool capacity.

For optimistic `WATCH` transactions, long waits between `WATCH` and `EXEC` also raise abort conflict rates. Keep connection hold times and critical sections as short as business logic allows.

## 27. Even One Shared Lettuce Connection Has Limits

Do not swing to the opposite extreme claiming **one Lettuce connection is always optimal**.

One shared connection can hit:

- Client-side command queue/backpressure under extreme fan-out.
- TCP/socket-level head-of-line effects in certain cases.
- Event-loop or serialization contention on large payloads.
- Timeouts when Redis falls behind incoming command volume.
- Connection drops impacting many in-flight commands at once.
- Workloads requiring dedicated connections for special commands.

In very large systems or unusual workloads, multiple connections or separate factories can isolate resources—**verified through measurement**.

Tune in this order:

1. Use proper native Redis commands; eliminate redundant calls.
2. Shrink large payloads / heavy serialization.
3. Cap fan-out and apply sensible batching.
4. Keep blocking commands off the shared connection path.
5. Inspect client queues, event loops, Redis CPU, and network.
6. Only then test adding connections/factories if evidence demands it.

## 28. Oversized Pools and the Idle Connection Problem

Suppose 20 pods each configure:

```yaml
max-active: 100
max-idle: 100
min-idle: 100
```

With fully warmed dedicated pools, the fleet keeps huge numbers of idle connections open even at low traffic.

Consequences:

- Redis and the OS manage thousands of sockets/file descriptors.
- TLS/auth handshakes burst during deployments.
- Redis `connected_clients` stays inflated.
- Concurrent pod startups trigger connection storms.
- Node replacements or failovers cause massive reconnect waves.
- Resources stay tied up without lifting throughput.

Never set `min-idle = max-active` just to shave a couple milliseconds off connection setup unless measurements prove clear value. Pick small `min-idle`, moderate `max-idle`, and bounded warm-up.

### 28.1. Undersized Pools Also Cause Queueing

Conversely, with Jedis or a dedicated pool:

```yaml
max-active: 2
max-wait: 50ms
```

peak traffic triggers borrow timeouts even while Redis Server sits idle. When metrics prove high waiters/borrow wait with spare Redis capacity, stepping the pool from 2 to 4 or 8 helps.

Never judge from connection count alone. Compare **throughput, p99, error rate, and Redis CPU** before/after.

## 29. Tuning When Using Redis as a Cache

For read-heavy caches:

```text
GET: 90%
SET/DEL/EXPIRE: 10%
Values usually small
```

Initial steps:

- Verify cache hit rate and commands per request.
- With Lettuce, start with the shared native connection before thinking about large pools.
- Avoid issuing repeated Redis calls within one request when composition/batching works.
- Set proper TTLs to prevent bloat and stampedes.
- Measure Redis CPU/network alongside RTT.
- Cap fallback queries to the DB when Redis fails.
- Use compact, suitable cache keys and serializers.

### 29.1. Cache Miss Storms Cannot Be Fixed by Bigger Pools

Suppose Redis slows down or caches expire simultaneously:

```text
Cache misses spike
    |
    v
Many requests hit the DB together
    |
    v
DB slows down
    |
    v
Requests hold resources longer
```

Enlarging Redis pools only lets failing requests clear `GET` faster without relieving DB overload.

Use TTL jitter, request coalescing, background refresh, or key-level stampede protection instead.

## 30. Tuning for Counters and High-Write Workloads

Counter workload:

```java
Long current =
        redis.opsForValue().increment("metrics:article:42");
```

When thousands of requests increment one key:

- `INCR` is atomic, yet one hot key still concentrates load on Redis Server.
- Adding connections does not split one key across shards.
- For higher throughput, consider batching or sharded counters aggregated under acceptable consistency semantics.
- For money/balances/strict invariants, never shard arbitrarily at the expense of atomicity.

Wrong pattern:

```text
GET counter
parse current
SET counter = current + 1
```

Regardless of thread or connection count, this causes lost updates. Pool tuning never fixes algorithmic race conditions.

## 31. Tuning Redis Streams and Consumer Groups

For a stream consumer group:

```text
XREADGROUP BLOCK
   |
   v
process message
   |
   v
XACK
```

Consumer count and concurrency affect:

- Blocking connection count.
- Concurrently processed messages.
- Pending Entries List (PEL) depth.
- Side-effect ordering.
- Downstream database/API pressure.
- ACK throughput.
- Claim/retry frequency after consumer crashes.

### 31.1. Never Scale Consumers Mechanically by App CPU Cores

If handlers make slow DB calls, adding Redis stream consumers only overloads the DB and bloats pending counts.

Measure separately:

```text
Redis read throughput
Handler processing duration
ACK throughput
Pending count / idle time
Retry/claim count
```

If reads are fast while handlers are slow, the bottleneck is business processing—not the Redis connection pool. Cap handler concurrency or scale downstream capacity.

### 31.2. Consumer Identity and Pending Recovery

Pool sizing does not handle consumers dying after receiving messages before `XACK`. Redis Streams require explicit pending handling (`XPENDING`, `XAUTOCLAIM`/`XCLAIM` per version) and idempotency.

When scaling consumer instances, maintain unique consumer names/ownership and do not confuse duplicate message processing with connection shortages.

## 32. Tuning Redis Pub/Sub

Pub/Sub typically uses a long-lived subscription connection and a listener executor.

Rather than adding connections per message, examine:

- Is the container receiving messages fast enough?
- Is the dispatch queue backing up?
- Do listeners execute long-blocking logic?
- Are overlapping channels/patterns subscribed multiple times?
- Are message payloads oversized?
- Is the client reconnecting repeatedly?
- Are events lost while subscribers are offline?
- Do services need broadcast or work-queue semantics?

If `onMessage` takes 2 seconds calling an external API, raising `max-active` will not trim those 2 seconds.

And if message loss is unacceptable, switch to Redis Streams or a durable broker instead of trying to compensate with huge Pub/Sub pools.

## 33. Controlled Load Testing to Size Pools

Never pick pool sizes from gut feelings like "production has high traffic." Follow a clear benchmark process:

### Phase 1 — Document Current Configuration

```text
Redis version / topology
Spring Boot / Spring Data Redis
Lettuce or Jedis
Shared connection? Pool enabled?
max-active / max-idle / min-idle / max-wait
connect timeout / command timeout
App pod and thread counts
Workload GET/SET/HGET/INCR/XREAD...
```

### Phase 2 — Configure a Realistic Workload

Example:

```text
70% cache reads
20% cache writes
10% counters/scripts
Production-like value size distribution
Production-like TTL and miss rate
Representative batch requests
```

Never pick pool sizes for an app with Lua scripts and multi-KB JSON payloads using a `PING`-only test.

### Phase 3 — Warm-Up and Baseline

Allow the app, JVM/GC, connection factory, and Redis to stabilize. Measure:

- Successful throughput.
- p50/p95/p99 request latency.
- Redis command durations.
- CPU/memory/network.
- Pool active/idle/waiters.
- Timeout/error rates.

### Phase 4 — Vary One Variable at a Time

Example with a dedicated or Jedis pool:

```text
Run A: max-active = 4
Run B: max-active = 8
Run C: max-active = 16
Run D: max-active = 32
```

Keep workload, topology, key distribution, and timeouts constant. Changing pod count, pool size, and batch size simultaneously obscures which change mattered.

With a shared Lettuce connection, another key experiment is **holding the shared connection fixed while varying workload concurrency**; changing `max-active` alone may have negligible impact on ordinary GET/SETs.

### Phase 5 — Watch for Saturation

A change helps when:

- Successful throughput rises or p99 drops under the same workload.
- Borrow wait shrinks if the pool was genuinely starved.
- Redis CPU/latency is not pushed into saturation.
- Memory/socket overhead stays within budget.
- Timeouts, retries, and connection errors do not increase.

### Phase 6 — Test Peaks and Failures

After selecting settings under steady load, test:

- Traffic bursts.
- Brief Redis slowdowns.
- Connection reconnects.
- Rolling deployments starting many pods together.
- Sentinel/Cluster failovers if used in production.
- Rising blocking consumers.
- Approaching Redis `maxclients` in a controlled lab.

Never report one peak throughput figure while ignoring resilience.

## 34. Example Benchmark Results Table

Suppose a staging suite yields **illustrative** numbers:

| Dedicated Pool max-active | Successful Throughput/s | p99 (ms) | Pool Wait p95 (ms) | Redis CPU |
|---:|---:|---:|---:|---:|
| 4 | 1,100 | 85 | 28 | 38% |
| 8 | 1,800 | 45 | 8 | 54% |
| 16 | 1,950 | 47 | 1 | 78% |
| 32 | 1,960 | 120 | 0 | 98% |

These are **not** executed measurements or universal pool-size recommendations. They illustrate:

- 4 connections genuinely starved the dedicated workload.
- Raising to 8 yielded clear gains.
- Stepping from 8 to 16 brought diminishing returns.
- Raising to 32 drove Redis near saturation, ruining p99 despite zero pool wait.

The right takeaway is **choosing settings at the balance point of throughput, latency, and headroom**, not maximum `max-active`.

If your app uses a shared Lettuce connection, measure the real command path before applying a table like this.

## 35. Redis CLI View: Inspecting Client Connections

Useful lab/staging commands:

```redis
INFO clients
CLIENT LIST
CONFIG GET maxclients
INFO stats
INFO commandstats
```

### 35.1. `CLIENT LIST`

`CLIENT LIST` displays client addresses, connection age, state, last command, and buffer metrics depending on Redis version. Use it to investigate:

- How many clients come from a specific application instance?
- Are many connections sitting idle?
- Are blocking clients active?
- Are client output buffers growing abnormally?
- Are connections held too long by unexpected workloads?

Never publish raw `CLIENT LIST` output publicly if it exposes IPs and sensitive metadata.

### 35.2. `connected_clients` Is Not Active Task Count

One shared Lettuce connection can carry many in-flight commands while `connected_clients` barely changes. Conversely, hundreds of pooled idle connections inflate `connected_clients` even when Redis ops/s is low.

Combine **connection counts + command throughput + pool activity + latency**.

### 35.3. `blocked_clients` Is Not Pool Borrow Waiters

Redis `blocked_clients` counts clients waiting inside Redis blocking commands per Redis semantics. Pool `numWaiters` counts Java callers waiting to **borrow a connection** before even sending a command to Redis.

They measure two different things at two different layers.

## 36. Common Misconceptions

**"A 100-connection pool is 10x faster than a 10-connection pool."** No universal ratio exists. Redis CPU, network, and command latency can be the limit.

**"Lettuce needs one connection per HTTP request."** False for routine operations using a shared native connection.

**"Enabling Lettuce pooling makes every GET use a pooled connection."** Do not assume that when the factory uses a shared native connection.

**"`shareNativeConnection(false)` always increases concurrency."** It can add acquisition overhead and trigger pool contention.

**"HTTP thread count dictates pool size."** False. Account for Redis command mix, concurrency, and driver semantics.

**"One TCP connection handles only one pending Redis command."** False for multiplexing clients like Lettuce.

**"`max-active` caps connections across the entire cluster."** False. It caps one pool; multiply across nodes, factories, and pods.

**"`max-wait` is the command timeout."** False. Borrowing a connection and waiting for a command reply are distinct phases.

**"`BLPOP 0` behaves like `GET` since both are one command."** False. Blocking commands can pin dedicated connections for long durations.

**"A 100-thread Pub/Sub executor opens 100 subscription connections."** Not necessarily. Subscription connections and callback executors are separate resources.

**"Reactor `flatMap` bounds Redis operations to `max-active`."** Do not assume so, especially over a shared Lettuce connection.

**"Adding connections fixes hot keys."** False. Hot keys and heavy Lua scripts are server/data-model bottlenecks.

**"Pipelining equals a transaction."** False. It optimizes command transport without all-or-nothing atomicity.

**"Clean SLOWLOG means the pool is healthy."** False. Borrow wait does not show up in Redis command execution time.

**"Low `connected_clients` means low concurrency."** False. Multiplexing packs many in-flight commands onto one connection.

**"A timeout proves Redis never ran the command."** False. Retrying non-idempotent commands can create duplicates.

**"Scaling app pods scales Redis capacity proportionally."** False. More pods push more connections and requests onto the same Redis server.

**"A 3-primary Redis Cluster simply multiplies pool size by 3."** Inaccurate. Drivers manage per-node connections; measure actual connections and per-node budgets.

**"`min-idle=max-active` is always better for latency."** It can maintain wasteful idle sockets and trigger connection storms during rolling deploys.

**"All Redis workloads should share one pool."** Not always—especially when blocking consumers share a deployment with low-latency caches.

## 37. Operational Checklist for Tuning Pools and Concurrency

### 37.1. Verify Architecture

- [ ] Identify whether the client is Lettuce or Jedis and verify its version.
- [ ] Verify whether the factory uses shared or dedicated connections.
- [ ] Know which operations actually borrow from the pool.
- [ ] Inventory all `RedisConnectionFactory` and template beans in the app.
- [ ] Account for all blocking/persistent connections (Streams, Pub/Sub, transactions).
- [ ] Factor in pod/instance counts and rolling deployment surges.

### 37.2. Choose Evidence-Based Settings

- [ ] Size `max-active` from real concurrency and borrow wait metrics.
- [ ] Keep `max-idle`/`min-idle` from holding idle sockets needlessly.
- [ ] Align `max-wait` and command timeouts inside request deadlines.
- [ ] Bound concurrency at Reactor/worker layers, not solely in the pool.
- [ ] Isolate blocking tasks from latency-sensitive workloads.
- [ ] Never disable shared Lettuce connections without measuring.

### 37.3. Monitor and Benchmark

- [ ] Track p50/p95/p99 Redis and application latencies.
- [ ] Track pool active/idle/waiters and borrow wait when pools are used.
- [ ] Track Redis `connected_clients`, `blocked_clients`, `rejected_connections`.
- [ ] Track CPU, memory, network, `commandstats`, and SLOWLOG/latency monitoring.
- [ ] Test production-like workloads including realistic payloads and cache misses.
- [ ] Test bursts, failures/reconnects, and multi-pod simultaneous startups.
- [ ] Compare before/after under identical measurement conditions.

### 37.4. Preserve Correctness

- [ ] Never blindly retry non-idempotent writes on timeout.
- [ ] Never replace transactions with pipelining for throughput.
- [ ] Never share a manual `RedisConnection` wrapper across threads.
- [ ] Prevent connection leaks in low-level factory calls.
- [ ] Test Redis Cluster routing and Sentinel failovers on realistic topologies.
- [ ] Never raise concurrency so high that the DB or downstream collapses.
- [ ] Keep a rollback plan if pool changes degrade p99 or error rates.

## 38. Tuning Workflows by Application Type

### 38.1. Lettuce Cache Applications

1. Start with the default shared native connection model.
2. Measure actual GET/SET latency and throughput.
3. Check whether blocking or transactional workloads exist.
4. For mostly GET/SET workloads, optimize command counts, payloads, fan-out, and Redis Server first.
5. Change pooling/sharing only when metrics/benchmarks show a bottleneck.
6. Re-measure under peak traffic and reconnects.

### 38.2. Synchronous Jedis Applications

1. Estimate concurrent callers holding connections.
2. Configure a bounded pool with an explicit borrow timeout.
3. Measure active/waiters and latency percentiles.
4. Step `max-active` up gradually only if borrow wait is high and Redis has headroom.
5. Trim `min-idle`/`max-idle` if excess idle sockets accumulate.
6. Ensure connections return promptly and are never held across non-Redis I/O.

### 38.3. WebFlux Applications with Reactive Redis

1. Keep the pipeline non-blocking end-to-end.
2. Never call `.block()` on the event loop.
3. Bound `flatMap` and request fan-out to match Redis capacity.
4. Consider `concatMap`/`flatMapSequential` when ordering matters.
5. Measure pending commands, event-loop pressure, and Redis latency.
6. Never rely on a connection pool as the sole backpressure mechanism.

### 38.4. Redis Streams / Pub/Sub Applications

1. Count blocking consumers and subscription connections.
2. Isolate connection/executor budgets from cache traffic where needed.
3. Align `BLOCK` timeouts with command timeouts.
4. Measure handler throughput and pending/ACK rates, not just read rates.
5. Implement idempotency/reclaiming for Streams; remember Pub/Sub lacks durable replay.
6. Never raise consumer concurrency past downstream processing capacity.

## 39. Conclusion

Tuning pools, connection counts, and concurrency in Spring Data Redis is an **end-to-end resource management problem**, not simply editing `max-active` in YAML.

Key principles:

1. **Understand your Redis client first:** Lettuce usually multiplexes ordinary commands over a shared native connection; Jedis manages connections differently and leans heavily on pooling.
2. **Separate shared from dedicated:** blocking commands, transactions, and subscriptions hold connections differently from GET/SET.
3. **Budget across the entire deployment:** pods, factories, pools, Redis nodes, and rolling deployments all add to `connected_clients`.
4. **Bound concurrency at the source:** thread pools, workers, and Reactor `flatMap` can generate more load than Redis can sustain.
5. **Use pipelining/batching appropriately:** cut round trips without mistaking it for transactions or ignoring Cluster rules.
6. **Align timeouts deliberately:** pool borrow wait, command timeout, and request deadlines form three distinct layers.
7. **Measure the right layer:** combine pool active/waiters, Redis command metrics, `INFO clients`, CPU, and application p95/p99 latency.
8. **Never sacrifice correctness:** timeouts leave outcomes uncertain, write retries require idempotency, and extra connections never fix race conditions.
9. **Benchmark before scaling:** pick the smallest concurrency/pool size meeting throughput, latency, and headroom targets under real load—not the largest possible connection count.

A well-tuned Redis setup is rarely the one with the most connections; it is the one with **enough connections for operations genuinely needing dedicated resources**, letting routine commands flow efficiently, shedding or limiting load when Redis slows down, and keeping p95/p99 steady even as traffic climbs or topologies shift.
