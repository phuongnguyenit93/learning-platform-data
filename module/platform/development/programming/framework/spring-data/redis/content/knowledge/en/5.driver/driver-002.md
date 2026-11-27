# Choosing a Driver by Synchronous, Reactive, and Topology Models

When a Java application connects to Redis via Spring Data Redis, choosing the **Redis driver** affects how the application manages connections, executes commands, handles concurrency, and connects to Redis clusters. Two common drivers in the Spring Data Redis ecosystem are **Lettuce** and **Jedis**.

There is no single optimal choice for every system. Three factors must be considered together:

1. **Programming model:** does the application interact with Redis synchronously (imperative/blocking) or reactively (reactive/non-blocking)?
2. **Redis topology:** does the application connect to a single Redis instance, a primary–replica setup with Sentinel, or a sharded Redis Cluster?
3. **Operational characteristics:** connection count, latency, failover behavior, timeouts, security, concurrent load, and compatibility with the Spring Boot/Spring Data Redis versions in use.

This lesson focuses on making the right decision and configuring the driver properly in **Spring Data Redis**, including Java examples, Spring Boot configurations, and practical differences that are easily confused.

## 1. Distinguishing Redis server, driver, and Spring Data Redis

The same operation to read a value from Redis passes through multiple layers:

~~~text
Application Controller / Service
          |
          v
StringRedisTemplate / RedisTemplate
or ReactiveRedisTemplate
          |
          v
RedisConnectionFactory
or ReactiveRedisConnectionFactory
          |
          v
Lettuce / Jedis (Redis driver)
          |
          v
Redis protocol over TCP / TLS
          |
          v
Redis standalone / Sentinel-managed Redis / Redis Cluster
~~~

- **Redis server** stores data and executes Redis commands.
- **Driver** implements the protocol to connect to Redis, send commands, receive results, manage network resources, and handle topology characteristics.
- **Spring Data Redis** provides abstractions and templates for the application to manipulate data through the driver.
- **Spring Boot** assists with configuration and auto-creates connection beans when the required dependencies and properties are present.

The driver **does not decide** whether the application uses Redis String, Hash, List, or Sorted Set: those structures belong to Redis. Nor does the driver decide how Java objects are serialized into Redis data; serialization is a choice at the Spring Data Redis layer.

For example, the same service calling `StringRedisTemplate.opsForValue().get("session:42")` can use Lettuce or Jedis underneath without changing the read statement. Differences show up in the connection model, reactive support, and operations.

## 2. The two drivers: Lettuce and Jedis

### 2.1. Lettuce

**Lettuce** is a Netty-based Redis client supporting synchronous, asynchronous, and reactive API styles. Spring Data Redis uses Lettuce for both imperative and reactive APIs; in Spring Boot, Lettuce is typically the default choice of the Redis starter.

Key characteristics:

- **Reactive support:** integrates with Spring Data Redis via `ReactiveRedisConnectionFactory` and reactive templates.
- **Non-blocking I/O at the network layer:** uses Netty and an event-driven model for connections, while still providing synchronous APIs when code calls them imperatively.
- **Native connections can be shared in suitable scenarios:** Lettuce designs regular connections to be used by multiple threads, helping reduce the number of TCP connections to maintain.
- **Supports Redis Standalone, Sentinel, and Cluster:** including node discovery, redirection, and topology refresh mechanisms depending on configuration.
- **Optional pooling:** useful when operations require dedicated connections or resource limits; it does not mean every application using Lettuce must enable pooling.

**Note:** "Lettuce uses Netty" does not mean every call through `RedisTemplate` is non-blocking. An imperative call like `get()` still waits for the result before returning. To have a reactive interface from the application layer, you must use the reactive API.

### 2.2. Jedis

**Jedis** is a long-standing Redis client offering a very direct synchronous working model. In Spring Data Redis, Jedis integration serves the **imperative model**; Spring Data Redis reactive templates do not run on `JedisConnectionFactory`.

Key characteristics:

- **Simple synchronous API**, easy to understand when applications use Spring MVC or services running on standard threads.
- **Supports common Redis topologies**, including standalone connections, Sentinel, and Cluster, with corresponding configuration.
- **Requires careful connection-sharing management:** a single Jedis connection must not be used concurrently by multiple threads arbitrarily. A pool or factory borrow/return mechanism usually fits multi-request applications.
- **Not an option for reactive Spring Data Redis:** if a service needs `ReactiveRedisTemplate`, use Lettuce.

Jedis versions may evolve their own APIs independently, but **the driver decision in Spring Data Redis must be based on the abstractions supported by the Spring Data Redis version in use**, not solely on method names available in the standalone Jedis library.

### 2.3. Quick-selection comparison table

| Criterion | Lettuce | Jedis |
|---|---|---|
| Works with `RedisTemplate` and `StringRedisTemplate` | Yes | Yes |
| Works with `ReactiveRedisTemplate` | Yes | No via Spring Data Redis integration |
| Common styles | Imperative, asynchronous, reactive | Imperative |
| I/O foundation | Netty, event-driven | Synchronous connections |
| Sharing native connections across threads | Typically supported under appropriate conditions | Must borrow/return connections; never share one connection arbitrarily |
| Connection pool | As needed | Usually important under concurrent load |
| Standalone | Yes | Yes |
| Sentinel | Yes | Yes |
| Cluster | Yes | Yes |
| Practical default for new Spring Boot applications | Usually preferred | When specific compatibility/operational needs exist |

**Selection principle:** Without special constraints, Lettuce is a sensible starting point because it supports both imperative and reactive models. Jedis fits when an application is imperative and has clear reasons to standardize on Jedis.

## 3. Choosing for the synchronous (imperative) model

In the imperative model, a Redis read/write call returns only after receiving a result or encountering an error/timeout.

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class VisitCounterService {

    private final StringRedisTemplate redis;

    public VisitCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long incrementViews(String articleId) {
        Long count = redis.opsForValue()
                .increment("article:" + articleId + ":views");

        if (count == null) {
            throw new IllegalStateException("Redis did not return a counter");
        }

        return count;
    }
}
~~~

This is imperative code because `increment(...)` returns the result directly. It suits Spring MVC, scheduled jobs, batch processing, or services designed around regular threads.

For this workload, **both Lettuce and Jedis can work**. The subsequent decision depends on current setup and operational characteristics:

- Use **Lettuce** if you want a unified client across different service types, or might add reactive components in the future.
- Use **Jedis** if the system has standardized on Jedis mechanisms with established pooling, timeout, observability, and operational conventions.
- For a request with multiple sequential Redis calls, switching from Jedis to Lettuce **does not automatically make the request asynchronous**: the service is still executing imperative calls.

### 3.1. Why does connection pooling still matter?

An HTTP request can issue multiple Redis calls. If each request requires an independent connection, a pool bounds and reuses TCP connections instead of repeatedly opening new ones.

With Lettuce, normal operations can leverage a shared connection. However, you should not assume **every command** is safe/correct when sharing a single connection. Blocking commands, transactions, pipelines, or state-isolation requirements may need separate connections and separate management.

With Jedis, pooling is particularly useful so many requests borrow independent connections and return them to the pool afterward. A pool that is too small easily causes connection waiting; a pool that is too large increases memory cost, sockets, and pressure on the Redis server.

Metrics to monitor include: active connections, waiting connections, connection borrow timeouts, command timeouts, Redis latency, and concurrent request count.

## 4. Choosing for the reactive model

Reactive applications process work using publishers such as Reactor `Mono` and `Flux`. When working with reactive Spring Data Redis, choose **Lettuce**.

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveVisitCounterService {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveVisitCounterService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> incrementViews(String articleId) {
        return redis.opsForValue()
                .increment("article:" + articleId + ":views");
    }
}
~~~

The method returns `Mono<Long>` so the pipeline controls subscription timing and result/error handling. Redis communication runs over Lettuce's reactive connections.

### 4.1. What does reactive bring?

Reactive can help when an application handles many concurrent I/O operations without wanting to tie up a platform thread waiting for every result. This model fits services built on Spring WebFlux and Reactor particularly well.

However, reactive does not guarantee every workload is faster. Redis usually has low command latency, and benefits depend on the number of requests waiting on I/O, how operations are chained, and the resources of the entire pipeline.

Key principles:

- **Do not insert imperative Redis calls into the event loop:** calling `StringRedisTemplate` inside a Reactor chain can block the reactive processing thread.
- **Do not use `.block()` in a reactive processing flow:** this loses most non-blocking benefits and can throw errors on threads that disallow blocking.
- **Do not assume `Mono` means instantaneous operation:** network errors, timeouts, retries, and backpressure still require deliberate design.
- **Do not assume surrounding components are already reactive:** calling synchronous JDBC APIs or blocking libraries from the same pipeline can still stall the system.

Spring Data Redis reactive provides APIs for many Redis structures, though operator scope and transaction/pipeline behavior can differ from imperative APIs. Choose APIs directly by business intent rather than mechanically translating method names.

### 4.2. Imperative on Lettuce vs. Reactive on Lettuce

~~~text
Imperative service
  -> StringRedisTemplate
  -> LettuceConnectionFactory
  -> waits for returned result

Reactive service
  -> ReactiveStringRedisTemplate
  -> ReactiveRedisConnectionFactory (Lettuce)
  -> Mono / Flux emits result signals
~~~

**Same driver, two different programming contracts.** The imperative/reactive decision must be consistent at the service or request-pipeline level, not just in the driver config file.

## 5. Choosing by Redis topology

Topology describes which nodes Redis is deployed as and what roles those nodes play.

| Topology | Nature | Driver choice | Special considerations |
|---|---|---|---|
| **Standalone** | A single primary Redis address for reads/writes | Lettuce or Jedis for imperative; Lettuce for reactive | Host, port, timeout, TLS, security |
| **Primary–replica** | Primary accepts writes, replicas copy data | Lettuce or Jedis, depending on topology config | Replica lag, role changes, and read consistency |
| **Sentinel** | Sentinel monitors and helps discover the current primary | Lettuce or Jedis for imperative; Lettuce for reactive | Sentinel nodes, master name, discovery, and failover |
| **Redis Cluster** | Data partitioned by hash slots across nodes | Lettuce or Jedis for imperative; Lettuce for reactive | Cluster-aware client, MOVED/ASK, slots, multi-key |
| **Managed Redis via proxy** | Provider hides part of topology behind endpoint/proxy | Per provider's protocol and guidance | Command compatibility, discovery, TLS, failover, endpoint |

### 5.1. Standalone: simplest connection

In Standalone, the application typically knows the host and port of a single Redis node.

~~~text
Spring Boot ---- Lettuce/Jedis ---- Redis:6379
~~~

The main concerns are connection reliability, timeouts, memory, persistence, and handling node unavailability.

Choice:

- Spring MVC/imperative: Lettuce or Jedis.
- Spring WebFlux/reactive: Lettuce.
- Simple needs, no special requirements: start with Lettuce as the Spring Boot default.

### 5.2. Primary–replica and Sentinel: high availability

Replicas copy data from the primary, so they can be used for reads under certain strategies. However, replication is usually **asynchronous**, meaning reading from a replica right after writing to the primary may see stale data.

Sentinel provides monitoring and supports automatic primary promotion when failures occur. An application that needs to track the current primary must configure a driver capable of **Sentinel discovery** rather than pinning a static old primary address forever.

~~~text
             +--> Sentinel A
Application -+--> Sentinel B ---> discovers new primary
             +--> Sentinel C

             Redis primary
                    |
             Redis replica(s)
~~~

Sentinel and replication **do not shard data**: replicas still hold copies of the dataset managed by the primary. Sentinel solves failover; it does not replace Cluster when keyspace needs to be distributed across multiple shards.

When choosing a driver for Sentinel, verify:

- The client supports Sentinel and uses the exact **master name** managed by Sentinel.
- The list of Sentinel endpoints is sufficient to connect if one Sentinel becomes unreachable.
- Sentinel authentication and Redis node authentication may be **two separate credential sets**.
- Timeouts and retry strategies do not cause the application to wait indefinitely during failover.
- Replica reads, if enabled, can tolerate potential lag behind the primary.

### 5.3. Redis Cluster: sharding by hash slots

Redis Cluster organizes the keyspace into **16,384 hash slots**. Each key maps to a slot, and each slot is owned by a cluster primary node. A cluster-aware driver must discover topology and handle Redis redirections such as `MOVED` and `ASK`.

~~~text
                         Redis Cluster
                         16,384 slots
                                |
                  +-------------+-------------+
                  |             |             |
               Primary A     Primary B     Primary C
               slots ...     slots ...     slots ...
                  |             |             |
               Replica A     Replica B     Replica C
~~~

A direct connection using a Standalone-only client is insufficient to work reliably with Redis Cluster. The application must configure **cluster nodes** properly and let the client track topology.

**Important difference for applications:** not all multi-key operations are allowed when keys reside in different slots.

For example:

~~~redis
MSET cart:42 "..." profile:42 "..."
~~~

In Redis Cluster, multi-key commands requiring keys to share a slot can fail with `CROSSSLOT` if that condition is not met.

Use **hash tags** to intentionally place related keys into the same slot when business logic genuinely needs multi-key operations:

~~~text
cart:{user-42}
profile:{user-42}
preferences:{user-42}
~~~

The part inside the curly braces, here `user-42`, is used to compute the hash slot for those keys. Do not put every key in the system under the same hash tag, as that defeats Cluster's load distribution benefits.

Redis Cluster also supports only logical database 0; do not design sharding via `SELECT` database indices as in Standalone.

### 5.4. Why choosing a driver is not enough when changing topology

Suppose an application previously used Lettuce with Standalone and migrates to Cluster. The driver name is still Lettuce, but bootstrap addresses, topology discovery, slot routing, and many multi-key operations all need to be revisited.

Similarly, moving from Standalone to Sentinel is not just changing the hostname to a Sentinel hostname. The application needs the **master name** and the list of Sentinel nodes. This is topology configuration, separate from choosing Lettuce vs. Jedis.

## 6. Configuring Spring Boot with Lettuce

The following examples use Spring Boot 3.x's `spring.data.redis` configuration branch. They illustrate driver and topology setup; actual credentials should be loaded from environment variables or a secret manager.

### 6.1. Default dependency and Standalone

In a Gradle project using the Spring Boot starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

This starter normally puts Lettuce on the classpath, and Boot auto-configures the corresponding factory. Example `application.yml`:

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

- `connect-timeout` bounds connection establishment time.
- `timeout` sets the Redis operation timeout as supported by configuration.
- In practice, tune timeouts to network latency and application SLOs, avoiding values that are too low or too high.

If Redis enables TLS, SSL settings must match the endpoint and server certificates, for example:

~~~yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
~~~

Do not enable SSL merely because the system is deployed on the cloud; check whether the Redis endpoint actually requires TLS.

### 6.2. Connecting to Sentinel

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.example.internal:26379
          - sentinel-2.example.internal:26379
          - sentinel-3.example.internal:26379
      connect-timeout: 2s
      timeout: 3s
~~~

The name `mymaster` must match the primary group name managed by Sentinel. The addresses above are illustrative. If the environment requires separate passwords/TLS between Sentinel and Redis nodes, configure them separately according to what your Spring Boot and Spring Data Redis versions support.

For Sentinel connections to succeed, the nodes must return Redis addresses that the application can **actually reach**; hostnames valid inside Redis's internal network that are unroutable from the application will still fail.

### 6.3. Connecting to Redis Cluster

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-1.example.internal:6379
          - redis-2.example.internal:6379
          - redis-3.example.internal:6379
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
~~~

These nodes are only bootstrap points for cluster discovery. After connecting, the driver must know which node serves each hash slot.

Cluster topology changes when nodes fail over or slots migrate. Lettuce supports **cluster topology refresh**; periodic or adaptive refresh options should be configured according to library version, failover speed, and network setup. If advertised node addresses are unreachable from the application, listing initial seed nodes alone will not fix the issue.

Distinguish between:

- **Sentinel nodes**: addresses queried to find the primary of a replication group.
- **Cluster nodes**: seed addresses used to discover shards of a Redis Cluster.

These two configurations serve two different topologies and must not be mixed arbitrarily in the same factory.

## 7. Configuring Spring Boot with Jedis

When actively choosing Jedis for imperative Spring Data Redis, add the Jedis library and optionally exclude Lettuce from the starter to keep the classpath consistent.

Example with Gradle Groovy:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-data-redis') {
        exclude group: 'io.lettuce', module: 'lettuce-core'
    }

    implementation 'redis.clients:jedis'
}
~~~

With Spring Boot managing dependency versions, you usually do not need to specify the Jedis version manually. Configuration selecting the client:

~~~yaml
spring:
  data:
    redis:
      client-type: jedis
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

Topology properties such as `sentinel.master`, `sentinel.nodes`, or `cluster.nodes` still describe the corresponding Redis deployment. What matters is that the driver is on the classpath and Spring Boot creates `JedisConnectionFactory`.

**Do not include `ReactiveRedisTemplate` in a Jedis-only configuration.** Reactive applications should use Lettuce and Spring Data Redis's reactive factory.

### 7.1. Pooling with Jedis

If using pooling via auto-configuration, settings can use `spring.data.redis.jedis.pool`. For example:

~~~yaml
spring:
  data:
    redis:
      client-type: jedis
      jedis:
        pool:
          max-active: 32
          max-idle: 16
          min-idle: 2
          max-wait: 2s
~~~

Pool properties require the appropriate pooling dependency (typically Apache Commons Pool 2) and must be verified on your Boot version. Numbers in the example are illustrative, **not standard values for every environment**.

When the pool is exhausted, requests may wait for a connection or hit timeout errors. If an application handles 200 concurrent requests, do not immediately assume you need a 200-connection pool: it also depends on connection hold time, commands per request, and pipelining usage.

## 8. Factory, template, and serializer: scope of responsibilities

An application usually does not create Lettuce/Jedis connections directly in every service, instead relying on Spring beans.

| Component | Role |
|---|---|
| `LettuceConnectionFactory` | Creates/manages Spring Data Redis connections using Lettuce; supports imperative and reactive contexts |
| `JedisConnectionFactory` | Provides imperative connections using Jedis |
| `RedisTemplate<K, V>` | Imperative operations with chosen key/value serializers |
| `StringRedisTemplate` | Convenient imperative variant for string data |
| `ReactiveRedisTemplate<K, V>` | Redis operations using Reactor |
| `ReactiveStringRedisTemplate` | Reactive template for string data |

For example, an imperative service using `StringRedisTemplate` works with any compatible imperative factory. But if a service needs `ReactiveStringRedisTemplate`, the configuration must provide an appropriate `ReactiveRedisConnectionFactory`.

If you declare a custom `RedisConnectionFactory` bean, that configuration can replace or affect Spring Boot's auto-configuration. Only build a custom factory when you genuinely need deep customization such as read preferences, client options, topology refresh, or specialized connection management.

**Serializers are independent of the driver.** Replacing Jedis with Lettuce does not automatically turn a JSON String in Redis into a Redis Hash, nor fix data serialized with a different codec. When switching drivers, keep the serialization strategy consistent so you do not produce unreadable or differently formatted data across service versions.

## 9. A systematic way to decide

You can follow this decision tree:

~~~mermaid
flowchart TD
    A[Application needs Redis access] --> B{Spring Data Redis reactive?}
    B -->|Yes| C[Choose Lettuce]
    B -->|No| D{Existing Jedis constraint?}
    D -->|No| C
    D -->|Yes| E[Choose Jedis for imperative]
    C --> F{Which Redis topology is deployed?}
    E --> F
    F -->|Standalone| G[Configure host and port]
    F -->|Sentinel| H[Configure master and Sentinel nodes]
    F -->|Cluster| I[Configure cluster nodes and check hash slots]
    G --> J[Set timeouts and observability]
    H --> J
    I --> J
~~~

This ordering avoids a common mistake: deciding "Jedis or Lettuce" and assuming topology will automatically work for any Redis setup. **Driver and topology are two related but distinct decisions.**

### 9.1. Scenario A: Spring MVC and a simple Redis cache

A Spring MVC application uses Redis to cache product info and sessions. Redis runs on a single node, and business logic does not require reactive.

**Recommended choice:** Default Lettuce with `StringRedisTemplate` or `RedisTemplate`, clear timeouts, and business-appropriate TTLs. No need to enable pooling purely for high request volume if Lettuce's shared connection meets usage needs.

### 9.2. Scenario B: Spring WebFlux API with high concurrent Redis operations

A WebFlux API uses `Mono`/`Flux`, reading multiple keys and composing results without blocking the event loop.

**Recommended choice:** Lettuce + `ReactiveRedisTemplate` / `ReactiveStringRedisTemplate`. Audit other dependencies in the request pipeline so blocking calls are not accidentally introduced on the event loop.

### 9.3. Scenario C: Existing Java batch job currently using Jedis

A long-standing imperative batch job already uses Jedis with stable pooling and monitoring. There is no reactive requirement.

**Reasoned choice:** Stay on Jedis if it meets requirements while managing pool, timeouts, and topology. No need to switch drivers simply because another library offers reactive APIs.

### 9.4. Scenario D: Redis moves to Sentinel

The application previously configured a static primary host. The new environment uses Sentinel for failover.

**Required changes:** choose a driver supporting Sentinel, configure the master name and Sentinel nodes, set appropriate timeouts, verify authentication, and confirm the application receives the new primary address after failover. Changing the host alone to a Sentinel address is not enough.

### 9.5. Scenario E: Redis Cluster serving at large scale

The system distributes data across multiple primaries and needs the client to redirect properly when slots change.

**Recommended choice:** Lettuce for new systems, or Jedis if standardized for imperative; both must use cluster-aware configuration. Audit multi-key commands, hash tags, node routing, and topology refresh.

## 10. Pitfalls to avoid

### "Lettuce is reactive, Jedis is synchronous"

This is an inaccurate statement. **Lettuce supports both imperative and reactive**, while **Spring Data Redis uses Jedis for imperative**. The Lettuce driver does not automatically make every method non-blocking.

### "Using WebFlux means all Redis operations are reactive"

False if the application still injects `StringRedisTemplate` and makes blocking calls on the event loop. Reactivity must be carried through with the right API and execution flow from service down to client.

### "Bigger connection pools are always faster"

An oversized pool wastes resources and can overload Redis. Pooling only manages connections; it does not reduce Redis command complexity and does not replace optimizing round-trip counts.

### "Sentinel is Cluster"

Sentinel provides monitoring and failover for a replication topology. Cluster shards the keyspace by slots. A system with replicas is not automatically a Redis Cluster.

### "Redis Cluster behaves like one big Standalone Redis"

Cluster has slot rules, redirections, multi-key constraints, and logical database limits. Business commands must align with those rules.

### "Having replicas means read-after-write is always consistent"

Replication can lag. If business logic requires immediately reading the latest write, consider routing reads to the primary or designing consistency explicitly.

### "The driver is responsible for guaranteeing zero data loss"

The driver governs how connections are made and commands are sent. Persistence, replication, failover, and acceptable data loss depend on the Redis server, deployment configuration, and business architecture. Client-side retries are also not automatically safe for commands with side effects.

## 11. Operations and troubleshooting by driver choice

A driver choice should come with observability targets and error-handling policies.

| Symptom | Questions to check | Remediation |
|---|---|---|
| Cannot establish connection | Host/port, TLS, ACL, firewall, DNS, connecting to right endpoint? | Verify network and auth before switching drivers |
| Requests wait a long time | Blocking commands, missing timeouts, pool exhausted, or high Redis latency? | Measure timing per layer; review pool/timeouts |
| Persistent `MOVED` or `ASK` anomalies | Is client running in Cluster mode and receiving reachable node addresses? | Configure cluster-aware mode, topology refresh, routing |
| `CROSSSLOT` | Are multi-key command keys in the same hash slot? | Adjust operations, add hash tags where genuinely needed |
| Sentinel failover fails to recover | Are master name, Sentinel nodes, auth, and new primary address right? | Verify discovery and reachability of the new node |
| Stale reads observed | Reading from replicas, replication lag? | Review read preference and consistency requirements |
| WebFlux slow or reports blocking | Calling imperative Redis on event loop? | Use Lettuce reactive API; audit the whole pipeline |
| Abnormal growth in connection count | Misconfigured pool or recreating factory/client repeatedly? | Reuse factory, bound connections, and monitor pool |

### 11.1. Timeouts and retries must reflect business semantics

At least three distinct intervals should be distinguished:

1. **Connection establishment time:** detects unreachable endpoints.
2. **Command execution time:** bounds waiting for a Redis response.
3. **Pool connection wait time:** bounds waiting when all connections are borrowed.

A timeout can occur after the server actually executed a command but before the client received the response. Therefore, retrying a **state-mutating write** such as incrementing a counter or decrementing inventory must account for idempotency. You cannot assume "timeout means Redis didn't run the command."

### 11.2. Useful operational metrics

- Redis command latency, error rate, and timeout rate.
- Open connection count, pool active/idle/waiters if pooling is used.
- Reconnect count and failover events.
- Redis CPU, memory, eviction, replication lag, and connected clients.
- Key/slot distribution, node latency, and slot migrations if using Redis Cluster.
- Application-layer API response time, not just Redis latency.

These metrics help decide when to tune timeouts/pools, revisit topology, or optimize commands per request. Changing the driver alone will not fix every bottleneck.

## 12. Takeaways for applying to Spring Data Redis projects

A good driver choice must **match the programming model and actual Redis topology**:

- **Imperative:** both Lettuce and Jedis work. Lettuce is usually a sensible default; Jedis is helpful when clear usage constraints exist.
- **Reactive:** use Lettuce via `ReactiveRedisConnectionFactory` and reactive templates; avoid imperative Redis calls on the event loop.
- **Standalone:** configure host/port, timeouts, and security.
- **Sentinel:** configure master name and Sentinel nodes, paying attention to discovery, failover, and replica-read consistency.
- **Cluster:** use a cluster-aware client, understand slots, handle topology changes, and respect multi-key restrictions.

After picking a driver, the application still needs proper Redis templates, serializers, timeouts, connection strategies, and observability. **Lettuce vs. Jedis is a connection-layer choice; the synchronous/reactive model and Redis architecture determine how effectively that choice operates.**
