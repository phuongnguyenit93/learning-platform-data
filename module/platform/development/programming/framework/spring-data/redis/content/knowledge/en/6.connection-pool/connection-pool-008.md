# Handling Broken Connections, Redis Restarts, and Server Changes

Redis frequently sits on the hot path of latency-sensitive features: caches, sessions, counters, distributed locks, queues, or ephemeral state. In practice, a Redis connection can drop even when no Java code changed: the server restarts, a node is replaced, an IP address changes, Sentinel elects a new primary, Redis Cluster migrates hash slots, a network device terminates an idle connection, or a pool holds a dead connection.

With **Spring Data Redis**, three questions must be separated:

1. **Is the current connection still usable?** The driver must detect failures, close, or recreate connections appropriately.
2. **Where is the new Redis destination?** Topology and node discovery must update to the right server handling commands.
3. **Did the just-sent command actually execute?** Retries must respect business semantics, especially for writes with side effects.

A lesson under **Connections and Pools** should focus on connection lifecycle, Lettuce/Jedis, pool management, timeouts, reconnection, failover, and how applications restore correct behavior when Redis hits failures.

## 1. Which Layers Does a Redis Connection Pass Through?

A Spring Boot application typically has the following call path:

~~~text
HTTP request / Scheduled job / Message consumer
                    |
                    v
           Application service
                    |
                    v
 RedisTemplate / StringRedisTemplate
 or ReactiveRedisTemplate
                    |
                    v
        RedisConnectionFactory
          /                  \
 LettuceConnectionFactory   JedisConnectionFactory
          \                  /
           Driver / connection / pool
                    |
               TCP or TLS
                    |
       Standalone / Sentinel / Cluster
~~~

Each layer has distinct responsibilities:

| Layer | Role on failure |
|---|---|
| Service | Decides whether to retry, fall back, fail, or reject the business operation |
| Spring Data Redis | Translates driver exceptions into data-access exceptions; provides Redis operation abstractions |
| Connection factory | Creates or supplies connections matching the driver and topology |
| Lettuce/Jedis driver | Maintains transport, detects disconnects, reconnects, or creates new connections |
| Connection pool (if used) | Borrows/returns connections; evicts broken connections; caps connection count |
| Redis topology | Identifies primary, replicas, hash-slot owners, or service endpoints |
| Network/DNS/TLS | Determines whether the endpoint can be resolved, verified, and reached |

**Automatic driver reconnection does not mean the business command automatically succeeded.** If Redis disconnects while the service is sending a command, the driver reconnecting only gives subsequent commands a chance to run. The application must still handle the exception and uncertain outcome of the in-flight command.

## 2. Types of Connection Errors to Distinguish

Seeing a Redis error does not always mean you should retry. Before writing error-handling policies, classify which category the error belongs to.

| Situation | Typical Symptom | Impact | Approach |
|---|---|---|---|
| Cannot connect initially | Connection refused, DNS failure, TLS handshake failure | Network session never established | Check host, port, network, TLS, auth; bounded retry only if transient |
| Active socket closed | Connection reset, broken pipe, connection closed | In-flight command may fail | Driver reconnects/replaces connection; service handles indeterminate outcome |
| Command exceeded timeout | Command timeout | Client did not receive reply in time | Inspect latency; separate safe read retries from writes |
| Redis is restarting | Connection refused followed by recovery | Brief outage window; cache may be cold | Tolerate brief outage, apply backoff, avoid flooding on recovery |
| Primary changed | Writes rejected, client still points to old node | Routing to wrong primary | Use Sentinel/Cluster discovery or a stable endpoint |
| Redis Cluster migrated slots | `MOVED`, `ASK`, timeout on old node | Needs routing to new node | Cluster-aware client; refresh topology, verify advertised node addresses |
| Pool returned dead connection | Immediate error on borrow, error spikes after idle period | Batches of requests fail | Evict broken connections, check validation/eviction policies |
| Pool exhausted | Pool wait, borrow timeout | Requests slow down even while Redis is healthy | Check active/idle/waiters and connection hold times |
| Redis rejected command due to permissions or data type | NOAUTH, NOPERM, WRONGTYPE | Usually configuration or data bug | Fix configuration/permissions/commands; blind retries will not help |

Exact error messages depend on driver version, Redis version, TLS, and Spring Data Redis layer. Avoid building logic strictly around exception text strings; whenever possible, handle by exception type and operation context.

### 2.1. Three Critical Moments of a Failure

~~~text
A. Before sending the command:
   Client --X--> Redis
   Can be certain the command was not sent over that connection.

B. Sent, reply not yet received:
   Client ---- command ----> Redis
   Client <--X-- reply
   Uncertain whether the server applied the command.

C. Reply received successfully:
   Client ---- command ----> Redis
   Client <--- result ---- Redis
   Client knows the server returned a result for the command.
~~~

Case **B** is usually the hardest. For example, the application sends `INCR payment:attempts`, Redis increments the counter, and then the socket drops before the reply reaches the client. Retrying once can increment the counter **twice**. Reconnecting successfully does not resolve this ambiguity.

For high-impact business flows, design idempotency or state reconciliation backed by a reliable data store. Never treat a timeout as proof Redis did not process the command.

## 3. What Happens When Redis Restarts?

During a restart, the following sequence can occur:

~~~text
T0  Application holds open connections to Redis
T1  Redis stops accepting commands / closes sockets
T2  In-flight requests receive errors or timeouts
T3  Driver detects connections are no longer valid
T4  Redis starts up and begins accepting new connections
T5  Driver reconnects or pool opens new connections
T6  New requests succeed; previously failed requests
    only rerun if the service has a suitable policy
~~~

**There is no guarantee every in-flight request will be re-executed.** Some failed requests during a restart are expected behavior. Applications must limit blast radius rather than assuming connections stay open forever.

### 3.1. Redis Comes Back, Yet Data May Differ from Before

Network recovery does not mean all data survived intact from before the restart. State depends on:

- **Persistence:** Was Redis configured with RDB, AOF, or both; when was the last durable snapshot/fsync?
- **Replication:** Is the returning node a primary or replica, and has it synced all data?
- **Cache:** If Redis acts as an optional cache, evicted/lost entries may need reloading from the primary store.
- **TTL:** Keys with expiration may still have expired while Redis was down.
- **Application usage:** Are Redis keys representing critical business state?

For example, after a restart, `GET cache:product:42` returning null can be a normal cache miss. The service should read from the primary database and repopulate the cache as needed if Redis is only a cache. However, if Redis is the sole store for critical state, data recovery and persistence requirements are far stricter.

### 3.2. Avoiding a “Reconnect Storm” When the Server Comes Back Up

If many instances lose connections simultaneously, every instance may retry continuously at the exact same moment. Once Redis comes back online, the sudden flood of connections and requests can overload the server again.

Common safeguards:

1. Set finite **connect timeout** and **command timeout**.
2. Retry with **bounded attempts**, exponential **backoff**, and randomized **jitter**.
3. Ensure the service's retry budget fits within the HTTP request/job deadline.
4. Enforce concurrency limits or a circuit breaker during prolonged Redis unavailability.
5. For caches, fall back to the primary source and consider cache stampede protection when many requests reload the same key simultaneously.

Retries must not run infinitely simply because Redis is an infrastructure service.

## 4. Lettuce: Automatic Reconnection and Limits to Understand

**Lettuce** is built on Netty and supports imperative, asynchronous, and reactive APIs. Lettuce has an **automatic reconnection** mechanism for dropped connections when enabled; in standard usage, auto-reconnect is enabled by default.

A basic sequence:

~~~text
Spring service --> Lettuce native connection --> Redis
                          |
                    transport lost
                          |
              driver detects disconnect
                          |
                attempts reconnect
                          |
             new connection established
                          |
                new commands proceed
~~~

Key points to grasp:

- Lettuce can share a suitable native connection across multiple operations/threads. Consequently, one broken native connection can impact multiple concurrent requests before reconnecting.
- **Auto-reconnect restores transport**; it does not guarantee every previously sent command executed exactly once, nor does it replace business retry policies.
- Queuing commands temporarily during disconnects differs from knowing outcomes of previously sent commands. Request queue settings, timeouts, and auto-reconnect behavior vary by version.
- Operations requiring independent connections or isolated state—such as certain blocking, pipeline, or transaction cases—must be considered separately.
- In Cluster topologies, reconnecting to **the right new node** also requires topology discovery, not merely reopening TCP to an old IP.

### 4.1. LettuceConnectionFactory in Spring Data Redis

`LettuceConnectionFactory` enables Spring Data Redis to supply connections to templates. The factory can manage a shared native connection for ordinary operations and optionally manage dedicated connections when needed.

With `RedisTemplate`, calls remain **imperative/blocking** even though the underlying driver is Lettuce. With `ReactiveRedisTemplate`, commands go over reactive connections; connection recovery does not automatically replay failed subscriptions or business pipelines.

For instance, a Reactor publisher terminating with `onError` because Redis was unreachable will not “magically resume” when Redis returns. Decide whether to resubscribe, retry the publisher, or return a fallback at the reactive layer.

### 4.2. When Do You Need a Pool with Lettuce?

A pool is not mandatory for every Lettuce operation. Valid reasons for pooling or dedicated connections include capping connections for specialized tasks, isolating workloads, and bounding resources.

When pooling is enabled, monitor borrowed/idle connections, borrow wait times, upper limits, and broken-connection handling. Never enlarge pool size just to mask timeouts caused by an overloaded Redis server or network failures.

## 5. Jedis: Managing Broken Connections Through the Pool

**Jedis** in Spring Data Redis primarily serves imperative APIs. A direct Jedis connection instance must not be invoked concurrently across multiple threads without proper synchronization.

Multithreaded applications typically use pooling so each request borrows a connection and returns it when finished:

~~~text
Request A --> borrow --> Jedis connection 1 --> Redis
Request B --> borrow --> Jedis connection 2 --> Redis
Request C --> wait for free connection (if pool exhausted)
                   |
                 return
                   |
              connection pool
~~~

When Redis restarts:

1. Open connections can be severed.
2. Requests using them receive exceptions.
3. Broken connections must be evicted, never returned to the pool for the next request as healthy.
4. Subsequent borrows can use remaining valid connections or open new connections to Redis.
5. If the server is still down, opening new connections fails as well.

A pool does not make Redis more available. It is solely a client-side resource management mechanism.

### 5.1. “Stale” Connections in a Pool

A connection may be closed by Redis or a network appliance while sitting idle. The pool may not detect it immediately and can hand that connection to a new request. The first request after an idle period may fail even though Redis is now healthy.

Common policies to evaluate:

- Validate connections on borrow (**test on borrow**) if validation overhead is acceptable.
- Periodically validate or evict idle connections based on intervals and idle thresholds.
- Do not retain idle connections longer than network appliance idle timeouts.
- Evict confirmed broken connections; never return them to the pool as healthy.
- Set a finite `max-wait` so pool exhaustion does not stall requests indefinitely.

Validating a connection with a `PING` only proves health at **the moment of the check**. The socket can still drop immediately afterward, so applications must still handle errors when sending real commands.

### 5.2. Distinguishing Connection Timeout from Pool Wait Timeout

| Concept | Meaning | Incident Example |
|---|---|---|
| Connect timeout | Maximum time to establish a network connection | Redis is down, firewall drops packets |
| Command/read timeout | Time waiting for a command reply | Redis is stalled, network lags, or reply lost |
| Pool max-wait | Time waiting to borrow a connection from the pool | All connections are held by other requests |
| Idle eviction/validation | Policy for cleaning and testing idle connections | Pool retained dead connections after a restart |

All three timeouts can appear during one outage. Seeing “Redis timeout” without knowing which type often leads to tuning the wrong parameter.

## 6. Spring Boot Configuration to Limit Disconnection Blast Radius

The following example illustrates Spring Boot 3.x configuration using Lettuce with standalone Redis:

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: redis.internal.example
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

`connect-timeout` controls connection establishment wait time. `timeout` relates to the Redis operation time limit in Spring Boot's configuration. Real values must come from latency targets and network/Redis characteristics; 2 and 3 seconds here are illustrative only.

If the endpoint uses TLS, configure SSL appropriately:

~~~yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
~~~

TLS must be paired with the proper endpoint and trusted certificates. Certificate or ACL errors will not vanish by retrying repeatedly.

### 6.1. Jedis with Pool Example

Spring Data Redis can use Jedis instead of Lettuce when the Jedis dependency is added and selected:

~~~yaml
spring:
  data:
    redis:
      client-type: jedis
      host: redis.internal.example
      port: 6379
      connect-timeout: 2s
      timeout: 3s
      jedis:
        pool:
          max-active: 24
          max-idle: 12
          min-idle: 2
          max-wait: 1500ms
~~~

Pool configuration requires the corresponding pooling library on the classpath and must match your Spring Boot version. These numbers are examples, not fixed recommendations.

For Lettuce, Spring Boot also offers `spring.data.redis.lettuce.pool` when pooling is used. Avoid enabling pools across an entire service without a clear need: a pool holding many connections also means many connections impacted during a restart.

### 6.2. Why Is a Stable Hostname Helpful?

When Redis changes machines, ideally clients connect through an endpoint that can track the new node:

~~~text
Application
   |
   v
redis.service.internal  (DNS / Service / Managed endpoint)
   |
   +----> Old Redis node  [replaced]
   |
   +----> New Redis node  [brought online]
~~~

However, **DNS is not a magical failover mechanism**. Drivers may still hold sockets to the old IP; the JVM, resolver, proxy, or network layer may cache DNS lookups. Connections must be recreated and an appropriate refresh strategy is needed to pick up the new target. If an endpoint is fronted by a load balancer/proxy, understand how the proxy supports the Redis protocol and handles primary transitions.

Applications should not hardcode the IP address of a transient Redis primary when infrastructure can replace nodes.

## 7. Redis Restarting on the Same Host

This is the most common scenario in standalone environments or local testing.

### 7.1. Before Restart

- Existing connections are open and may have commands awaiting replies.
- Transactions, blocking reads, Pub/Sub subscriptions, or consumers may be active.
- Redis may persist data according to persistence settings or act strictly as an in-memory cache.

### 7.2. During Restart

- The driver reports connection loss or timeouts.
- HTTP requests depending on Redis may fail.
- If using an optional cache, the service can read from the fallback database.
- If Redis is mandatory for correctness, the service should return a controlled error rather than faking success.

### 7.3. After Restart

- The driver/client must re-establish connections, or the pool must provide new connections.
- Redis may still be loading persisted data during startup; opening TCP does not guarantee target operations are ready yet.
- Missing cache keys can be repopulated on demand.
- Failed business workflows must be retried or reconciled according to their own policies.

If the application subscribes via Pub/Sub, do not assume messages published while the subscriber was disconnected can be retrieved: **Redis Pub/Sub retains no backlog for offline subscribers**. If replay is required, consider Redis Streams with processing checkpoints and consumer group recovery.

## 8. Redis Moving to Another Server: Three Operational Models

### 8.1. Standalone and Direct Endpoint Changes

For example, the old server is `redis-old.internal:6379` and the new server is `redis-new.internal:6379`. If the service only knows the old address and lacks discovery, reconnects keep targeting the old machine.

Ways to handle this:

1. Update the endpoint configuration and redeploy/refresh the application context per application lifecycle rules.
2. Use DNS or a stable service name if infrastructure swaps backends behind a single endpoint.
3. Verify old sockets were replaced or force the client to reconnect when needed.
4. Confirm data on the new server matches expected scope; switching endpoints can switch **the entire dataset**, not just the network address.

Simply changing `host` in a config file does not mean the `RedisConnectionFactory` bean automatically reloads values at runtime. In typical Spring Boot applications, many properties bind when beans initialize. You need an explicit configuration refresh mechanism or a controlled application restart/rollout.

### 8.2. Redis Sentinel Switching Primary

Sentinel monitors a primary–replica group and provides information about the current primary. When the primary fails, Sentinel can promote a replica to replace it, subject to quorum and failover rules.

~~~text
Application
   |
   +--> Sentinel A
   +--> Sentinel B  ---> queries current primary
   +--> Sentinel C
                     |
                Redis primary P1
                     |
                 Redis replica R1

On failover: R1 is promoted to the new primary.
~~~

Example Spring Boot configuration:

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.internal:26379
          - sentinel-2.internal:26379
          - sentinel-3.internal:26379
      connect-timeout: 2s
      timeout: 3s
~~~

Mandatory points to understand:

- The **master name** (`mymaster`) is the Sentinel configuration name, not the hostname of a Redis node.
- Sentinel endpoints serve **discovery**; the current Redis primary endpoint executes data commands.
- The Redis node address returned by Sentinel must be reachable from the application's network; across containers, NAT, or multiple VPCs, advertised addresses may be unreachable from the client.
- Redis auth and Sentinel auth may need separate configuration.
- During failover, commands can error; the driver must discover the new primary and the service must handle failed requests.
- Replicas can lag. Writes acknowledged on the old primary risk being absent on the new primary during certain failover scenarios; replication is not strictly synchronous commit.

A static primary endpoint does not handle Sentinel failover. To automatically discover a new primary, use a Sentinel-aware connection setup or suitable proxy infrastructure.

### 8.3. Redis Cluster Migrating Nodes and Hash Slots

Redis Cluster partitions the keyspace into **16,384 hash slots**. When a node fails or the cluster rebalances, slot ownership changes.

~~~text
Spring Data Redis
       |
       v
Lettuce/Jedis Cluster-aware client
       |
       +----> Node A: slot range A
       +----> Node B: slot range B
       +----> Node C: slot range C
                   |
             MOVED / ASK
                   |
            Update routing
~~~

Example configuration:

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-a.internal:6379
          - redis-b.internal:6379
          - redis-c.internal:6379
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
~~~

The `nodes` list serves as initial seed nodes for cluster discovery, **not a fixed map** where the application shards keys manually.

Two key responses:

- **MOVED:** the node indicates the slot now belongs to another node; a cluster-aware client redirects and may update its topology map.
- **ASK:** a temporary redirection occurring during slot migration; the client follows the corresponding redirection protocol.

Lettuce supports cluster topology refresh via periodic or adaptive event-driven options. Configure it to match your driver version and environment. Never treat `max-redirects` as a fix for a cluster advertising IPs unreachable from the application.

**Do not switch to a new host/port by bypassing hash slots.** With Cluster, applications must keep using a slot-aware client; multi-key operations remain constrained to keys in the same hash slot.

## 9. Safe Retries: Reads, Writes, and Uncertain State

### 9.1. Classifying by Business Effect

| Operation | Retry on connection/timeout error? | Reason |
|---|---|---|
| `GET key`, `HGET key field` | Usually safe with bounded retries | Read does not mutate Redis data |
| `EXISTS key`, `TTL key` | Usually safe with bounded retries | Reads current state |
| `SET key sameValue` | May be value-idempotent, but inspect TTL/overwrites | Re-writing can reset TTL or overwrite newer updates |
| `INCR`, `LPUSH`, `XADD` | Do not blindly retry | Command may have run before the reply was lost |
| Inventory deduction / payment / order write | Needs idempotency and an authoritative confirmation store | Must prevent applying business side effects multiple times |
| Multi-command transactions | Cannot blindly treat the whole sequence as safely retryable | Part or all of the work may have executed |

Retries must be evaluated by both **Redis side effects** and **business meaning**. For example, repeating `SET key value` might preserve the final value, yet resetting a TTL or interleaving with another writer can still produce wrong outcomes.

### 9.2. Imperative Pattern: Cache Read with Bounded Retry

This example is appropriate only when Redis **is an optional cache** and the application has a primary data source to query if `Optional.empty()` is returned:

~~~java
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {
    private static final Logger log =
            LoggerFactory.getLogger(ProductCacheReader.class);

    private final StringRedisTemplate redis;

    public ProductCacheReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Optional<String> getCachedName(String productId) {
        String key = "product:" + productId + ":name";

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                return Optional.ofNullable(redis.opsForValue().get(key));
            } catch (RedisConnectionFailureException | QueryTimeoutException ex) {
                if (attempt == 2) {
                    log.warn("Redis unavailable for cache key {}", key, ex);
                    return Optional.empty();
                }

                // Imperative code only: retry after a short jittered delay.
                try {
                    Thread.sleep(
                        ThreadLocalRandom.current().nextLong(30, 81));
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return Optional.empty();
                }
            }
        }

        return Optional.empty();
    }
}
~~~

Key takeaways:

- `GET` is a read, so retrying carries less risk than writes with side effects.
- Retries catch only the two illustrative exception types rather than swallowing all `DataAccessException` subclasses such as `WRONGTYPE` or configuration errors.
- Returning `Optional.empty()` makes a cache miss and a cache outage look identical to callers; this is **intentional for best-effort caching**, so emit separate logs/metrics to preserve observability.
- `Thread.sleep` blocks the thread and is **unsuitable on a Reactor event loop**. In reactive code, use Reactor retry/backoff operators.
- Retry counts must fit within the remaining HTTP request deadline. If Redis is mandatory for correctness, returning empty like a cache miss is wrong; propagate a controlled failure instead.

### 9.3. Reactive Pattern: Fallback for Cache Reads

With `ReactiveStringRedisTemplate`, handling can look like:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductCacheReader {
    private static final Logger log =
            LoggerFactory.getLogger(ReactiveProductCacheReader.class);

    private final ReactiveStringRedisTemplate redis;

    public ReactiveProductCacheReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<String> getCachedName(String productId) {
        return redis.opsForValue()
            .get("product:" + productId + ":name")
            .onErrorResume(RedisConnectionFailureException.class, ex -> {
                log.warn("Redis cache temporarily unavailable", ex);
                return Mono.empty();
            });
    }
}
~~~

Here `Mono.empty()` signals no cached result. For timeouts or retry with backoff, add handlers matching the real exception types using appropriate Reactor operators. Never call `.block()` to “wait for Redis to come back” inside a reactive request pipeline.

### 9.4. Idempotency for Critical Write Operations

Suppose a service receives an order-creation request carrying `requestId`. One pattern records `requestId` in a durable store and ensures processing state transitions only once. Redis can assist short-term deduplication with `SET NX`:

~~~redis
SET idempotency:order:req-123 "processing" NX EX 600
~~~

The command creates the key only if it does not already exist. However, **SET NX alone does not guarantee exactly-once processing**: the service could create the key and crash before saving the order, the TTL could expire before a late retry, or two systems could race on state. For payments and orders, you need verifiable idempotency state, completion/recovery logic, and a reliable business store.

## 10. Readiness, Liveness, and Degraded Mode

When Redis fails, the application must decide whether it can still serve requests.

| What is Redis used for? | Generally suitable strategy |
|---|---|
| Optional cache, source of truth in database | Keep running; cache miss/fallback; log and track Redis outage metrics |
| Mandatory session store for login | May reject requests requiring sessions; align readiness with architecture |
| Coordination lock or correctness guard | Fail-closed for lock-dependent actions when Redis state is uncertain |
| Redis queue/events as primary processing source | Pause/throttle consumers cleanly, rely on checkpoints and recovery mechanisms |
| Rebuildable data | Controlled warming after restart, avoiding stampedes |

**Liveness** reflects whether the application process itself is healthy; a Redis outage rarely means the JVM should be restarted in a loop. **Readiness** reflects whether an instance should receive traffic, depending on mandatory dependencies. If Redis is only an optional cache, failing readiness whenever Redis disconnects can pull every instance out of the load balancer and amplify an outage.

Spring Boot Actuator provides a Redis health indicator in matching configurations. Decide which health groups should include Redis health based on actual service dependency, rather than letting one `DOWN` status drive both liveness and readiness by default.

### 10.1. Circuit Breakers and Bulkheads

If Redis remains unavailable for an extended period, retrying on every request raises latency and consumes threads. A circuit breaker pauses calls to Redis after an error threshold and probes recovery in a controlled manner.

Bulkheads or concurrency limits prevent requests waiting on Redis from exhausting all service resources.

Choose strategies per business domain: **a fallback that is safe for caching** can be **dangerous for distributed locks** if the service proceeds as if the lock were acquired.

## 11. Preserving Correct State After Reconnecting

A fresh connection only restores transport. Several task types require restoring state at the application level:

### 11.1. Redis Pub/Sub

Pub/Sub delivers messages to connected subscribers. After a disconnect, verify subscribers resubscribed and recognize that messages published while offline may be lost.

If the application requires replayability, use an event log such as Redis Streams rather than relying solely on plain Pub/Sub.

### 11.2. Redis Streams and Consumer Groups

After a restart/reconnect, consumers can resume reading stored entries if Redis persisted the data. Manage `XREADGROUP`, `XACK`, and pending entries when consumers crash or shift across instances.

Consumer reconnection does not automatically determine whether an entry already completed business processing before the failure. Design idempotent processing and pending-entry claiming where needed.

### 11.3. Transactions, Pipelines, and Blocking Commands

- **Transactions:** a broken connection mid-transaction requires determining how far the transaction executed; never assume a network error means zero commands ran.
- **Pipelines:** losing replies for batched commands leaves uncertainty about which commands executed; do not blindly replay an entire write pipeline.
- **Blocking commands:** commands waiting on data such as blocking pops/reads may terminate with an exception on disconnect; consumers should restart their read loop per policy.
- **Distributed locks:** after a network interruption, a client may not know whether a lock was granted or whether its TTL expired. Do not proceed with exclusive work unless lock ownership is still certain.

## 12. Observability and Diagnostics During Disconnections

A Redis incident needs enough telemetry to find the root cause without logging passwords or sensitive payloads.

| Observation | Purpose |
|---|---|
| Connection error count over time | Detect outage windows and reconnection frequency |
| Command timeout / connect timeout / pool wait timeout | Separate failure categories |
| Redis command latency | Identify slow server vs. network-only issues |
| Pool active, idle, waiters, borrow timeouts | Detect pool exhaustion or connections held too long |
| Redis client count, rejected connections | Detect server-side connection pressure |
| Redis memory, CPU, evictions, blocked clients | Detect server overload |
| Replication lag and node roles | Detect read staleness and failovers |
| Redis Cluster slot coverage / node states | Detect routing/topology problems |
| DNS resolution, socket resets, TLS errors | Detect infrastructure issues and endpoint changes |
| Restart/failover/deployment timestamps | Correlate error onset with operational events |

To distinguish network failures from pool failures, inspect **both sides**: a service may report pool wait timeouts while Redis is healthy, or open many new connections while Redis rejects them due to hitting client limits.

### 12.1. An Ordered Diagnostic Workflow

1. **Scope the impact:** are all instances failing or only one host/availability zone?
2. **Classify the error:** DNS, connect, TLS, command timeout, borrow timeout, or `MOVED`/`ASK`?
3. **Check Redis availability:** has restart finished, and are primary/replicas or cluster in healthy states?
4. **Check the active endpoint:** are hostnames/IPs/ports and Sentinel/Cluster-advertised addresses reachable from the application?
5. **Check resources and pools:** pool exhaustion, stale idle connections, Redis client limits, CPU, and network latency.
6. **Verify business correctness:** writes with uncertain outcomes must be verified before replaying.
7. **Controlled recovery:** allow the driver to reconnect/switch endpoints, or restart/reinitialize the application when config/factories bind only at startup.
8. **Verify post-recovery:** error rates drop, latency normalizes, and critical data is intact.

During diagnostics, never log raw passwords, access tokens, or user payloads.

## 13. Practice Scenarios to Understand Recovery Behavior

You can simulate failures in development or staging to observe behavior. The following are **learning scenarios**, not commands executed in this lesson.

### Scenario A: Standalone Redis Restart

1. Start a service performing periodic cache reads.
2. Record baseline before restart: Redis connection count, latency, and read outputs.
3. Temporarily stop Redis.
4. Observe exceptions/timeouts, retry attempts, and fallbacks.
5. Start Redis again.
6. Observe how long it takes the driver to run new commands, cache misses, and post-restart data state.

Key takeaway: **Redis coming back online does not turn previously failed calls into successes.**

### Scenario B: Stale Jedis Connections in a Pool

1. Open several connections and leave them idle.
2. Restart Redis or sever old sockets.
3. Send new requests using the pool.
4. Observe which connections fail on the very first borrow/command.
5. Inspect validation and eviction policies; verify whether the pool recovers.

Key takeaway: a pool holding connections does not mean they are always healthy; validation still does not replace error handling when sending commands.

### Scenario C: Changing Standalone Endpoint

1. Point the application at a logical hostname.
2. Switch the backend Redis or DNS record in test infrastructure.
3. Observe when the application actually opens sockets to the new host.
4. If it keeps hitting the old machine, inspect held connections, DNS caching, and configuration refresh mechanisms.
5. Confirm data at the new target meets business requirements.

Key takeaway: changing an IP and changing Redis topology are distinct; stable endpoints aid operations but do not replace connection lifecycles.

### Scenario D: Sentinel Failover

1. Use a primary–replica Redis setup managed by Sentinel.
2. Trigger a primary failure using the environment's test mechanism.
3. Observe Sentinel electing a new primary and the client discovering it.
4. Verify whether the application can write to the new primary and whether replica lag occurs.
5. Inspect write operations that occurred right around failover.

Key takeaway: **a successful infrastructure failover does not guarantee every pre-failover write was replicated.**

### Scenario E: Redis Cluster Slot Migration

1. Connect using a cluster-aware client.
2. Migrate several hash slots in the test cluster.
3. Observe redirection replies and client topology refresh.
4. Verify commands accessing keys after migration reach the right node.
5. Check whether the application relies on invalid multi-key operations across different slots.

Key takeaway: Cluster reconnection requires **routing and topology refresh**, not just fresh TCP sockets.

## 14. Synthesis Example: Choosing Recovery Policies by Redis Role

Suppose an e-commerce application uses Redis in three places:

~~~text
ProductController
   |
   +--> ProductService --> Primary Database
   |                          |
   |                        Redis cache
   |
OrderService
   |
   +--> Transactional Database
   +--> Redis temporary dedup / rate-limit
   |
EventConsumer
   |
   +--> Redis Stream
~~~

When Redis restarts:

| Component | Reasonable Reaction |
|---|---|
| Product cache | Read from primary database, limit retries, repopulate cache on demand |
| Order creation | Do not repeat transactions solely on Redis timeout; check order status and request ID |
| Rate limit | Decide fail-open vs. fail-closed based on security/load requirements; never assume all systems are alike |
| Redis Stream consumer | Reconnect, resume reading, reclaim pending entries, and prevent duplicate side effects |
| Service health | Align readiness with mandatory capabilities; keep liveness focused on process health |

A single connection policy cannot be applied identically to every business flow. **Write correctness must be designed at the business layer; connection and pool management solve only the transport layer.**

## 15. Principles to Remember

- **Broken connections are an expected state in distributed systems.** Require finite timeouts, observability, and clear recovery behavior.
- **Lettuce provides auto-reconnect**, while **Jedis typically relies on connection and pool lifecycles** in imperative apps. Neither guarantees exactly-once retries.
- **A Redis restart can drop both connections and part of the data**, depending on persistence, replication, and how Redis is used.
- **Server changes require discovery or updated endpoints:** Standalone may need endpoint updates; Sentinel needs master discovery; Cluster needs slot routing and topology refresh.
- **Pools can hold dead connections** or become exhausted. Validation, eviction, and max-wait help manage resources, yet operation error handling remains necessary.
- **Retries must be bounded and account for idempotency.** A write command already sent without a reply may have executed.
- **Applications must distinguish optional caches from mandatory data.** Cache fallbacks make sense, whereas assuming success on distributed locks or payments causes business bugs.
- **Recovery must be verified by behavior and data:** opening a new socket is necessary, not sufficient to conclude the service has fully recovered.

Mastering these points enables Spring Data Redis applications to survive Redis restarts, dead pooled connections, and server changes while maintaining stability and business correctness.
