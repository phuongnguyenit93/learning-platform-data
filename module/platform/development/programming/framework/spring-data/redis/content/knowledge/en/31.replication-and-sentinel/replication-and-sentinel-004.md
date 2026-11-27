# Primary Discovery and Topology Changes During Failover

In a Redis deployment using **replication** and **Sentinel**, an application should not assume a fixed server will remain the **primary** forever. Redis replicas replicate data from the primary, while Redis Sentinel monitors instances and coordinates electing and promoting a replica when the primary fails. After failover, the primary address may move from one host to another; stale application connections must be refreshed and new writes must reach the new primary.

In **Spring Data Redis**, primary discovery is typically handled by the Redis client and `RedisConnectionFactory`. With Sentinel configuration, the application supplies a **logical master name** and a list of Sentinel nodes rather than pinning to the initial Redis primary address. The client queries Sentinel to find the current primary, establishes connections, and recovers connections when topology changes.

This lesson explains primary discovery, the stages of failover, Spring Boot/Lettuce configuration, impacts on read–write operations, retries, and how to verify state after a role transition.

## 1. What Do Primary, Replica, and Sentinel Do?

Redis replication normally has one primary accepting write commands and one or more replicas copying data from the primary. Replication is **asynchronous** by default, so replicas can lag behind the primary.

Redis Sentinel is a separate monitoring process that performs failure detection, status notifications, failover coordination, and discovery of the current primary address. **Sentinel is not a proxy forwarding `GET`, `SET`, `HGET` commands** and does not directly store business data like a Redis data node.

| Component | Function | Common Port |
| --- | --- | --- |
| Redis primary | Accepts writes, serves data, and emits the replication stream | `6379` |
| Redis replica | Replicates data; can serve reads if the client is configured | `6379` or configured port |
| Redis Sentinel | Monitors, discovers the primary, and coordinates failover | `26379` |
| Spring Data Redis | Java API for accessing Redis via templates and repositories | Not a Redis server |
| Lettuce or Jedis | Driver connecting to Redis/Sentinel and recovering per configuration | TCP/TLS connection |

Illustrative model:

~~~text
                    Spring Boot application
                             |
                 "Who is the primary for mymaster?"
                             |
                 +-----------+-----------+
                 |           |           |
                 v           v           v
             Sentinel S1 Sentinel S2 Sentinel S3
                 |           |           |
                 +-----------+-----------+
                             |
                         Monitors
                             |
                             v
                    Redis A (PRIMARY)
                      /           \
                     v             v
              Redis B (REPLICA) Redis C (REPLICA)
~~~

The Sentinels jointly monitor a replication group with the logical name `mymaster`. This name is **not a hostname**; after failover, it stays the same even though the physical primary has changed.

## 2. Why Not Pin the Primary Address?

If an application configures only:

~~~yaml
spring:
  data:
    redis:
      host: redis-a.internal
      port: 6379
~~~

it works initially while Redis A is primary. However, if A fails and B is promoted, the application may keep trying to connect to A. When A returns as a replica, write commands sent to A will be rejected.

Potential problems include:

- Connection errors while Redis A is down.
- `READONLY` write errors if A is now a replica.
- Stale connections reset or timing out when roles change.
- Having to edit configuration or restart the application without a mechanism to discover the new primary.

With a Sentinel-aware client, the access flow is:

~~~text
Before failover:
  App → Sentinel: get-master-addr-by-name mymaster
  Sentinel → App: redis-a.internal:6379
  App → Redis A: SET ...

After failover:
  App → Sentinel: get-master-addr-by-name mymaster
  Sentinel → App: redis-b.internal:6379
  App → Redis B: SET ...
~~~

This is **role-based discovery**: the application knows to connect to the current primary without depending on a hardcoded address.

## 3. How Does Sentinel Provide Primary Information?

Sentinel monitors Redis instances, exchanges state with other Sentinels, identifies replicas, and tracks group topology. A client can query:

~~~bash
redis-cli -h sentinel-1.internal -p 26379 SENTINEL get-master-addr-by-name mymaster
~~~

Initial response:

~~~text
1) "redis-a.internal"
2) "6379"
~~~

After failover:

~~~text
1) "redis-b.internal"
2) "6379"
~~~

Other inspection commands:

~~~bash
redis-cli -h sentinel-1.internal -p 26379 SENTINEL master mymaster
redis-cli -h sentinel-1.internal -p 26379 SENTINEL replicas mymaster
redis-cli -h sentinel-1.internal -p 26379 SENTINEL sentinels mymaster
~~~

`SENTINEL master` displays the master metadata monitored by Sentinel, `SENTINEL replicas` lists discovered replicas, and `SENTINEL sentinels` shows peer Sentinels. During failover, Sentinels may not converge metadata instantaneously; a point-in-time response from a single node is not necessarily a globally consistent snapshot of the entire system.

### Master Name and Quorum

Illustrative Sentinel configuration:

~~~text
port 26379
sentinel monitor mymaster 10.0.0.11 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 60000
~~~

Here:

- `mymaster` is the monitored Redis group name.
- `10.0.0.11:6379` is the initial primary address.
- `2` is the quorum required to acknowledge that the master is down per Sentinel criteria.
- `down-after-milliseconds` is the interval related to detecting unresponsiveness.
- `failover-timeout` adjusts failover coordination milestones.

**Quorum is not strictly identical to the votes required to authorize a failover.** Sentinel also uses leader election requiring a majority of eligible Sentinels. With three independent Sentinels, quorum 2 is common, but you must evaluate failure domains and majority reachability when some Sentinels are lost.

Placing three Sentinels on the same host provides no protection if that entire host fails. Distribute Sentinels across appropriate hosts or failure zones.

## 4. Sequence of a Failover

When Redis A stops responding:

1. **SDOWN:** One Sentinel independently deems A *subjectively down* for failing to respond as required.
2. **ODOWN:** Sentinels exchange status, reach quorum, and confirm A is *objectively down*.
3. **Coordinator election:** Sentinels elect a leader for the failover round via voting.
4. **Replica selection:** The leader evaluates available replicas, synchronization state, and relevant priorities.
5. **Promotion:** Replica B is promoted to the new primary.
6. **Replication switch:** Other replicas are pointed to B. When A returns, it can be reconfigured as a replica of B.
7. **Topology notification:** Sentinel updates the master address and emits a master-switch event.
8. **Client recovery:** The Redis driver detects the primary change and reconnects to B; new commands flow to the new primary.

~~~text
             Before failover                    After failover

          Redis A [PRIMARY]                   Redis A [DOWN]
             /         \                           |
            v           v                          | may return
      Redis B [R]   Redis C [R]                     v
                                               Redis A [REPLICA]

                                              Redis B [PRIMARY]
                                                     |
                                                     v
                                              Redis C [REPLICA]

          App → Redis A                      App → Redis B
~~~

**Failover is neither instantaneous nor completely disruption-free.** During failure detection, electing a new primary, and refreshing connections, some commands may time out, be rejected, or encounter connection errors. Spring Data Redis can recover via the driver, yet application-level error policies are still necessary.

### Does Redis Sentinel Guarantee Zero Data Loss?

No. Replication is asynchronous by default. Redis A can return success for a `SET` command before B receives the change. If A goes down at that moment and B is promoted, some writes acknowledged by A may be missing on the new primary.

Measures such as persistence, monitoring replication lag, or replication acknowledgment commands (`WAIT` and mechanisms supported by your Redis version) can reduce risk in some cases, but **do not turn Sentinel into a completely lossless synchronous write protocol**. Clarify whether Redis is acting as a cache or a critical data store to design appropriate recovery policies.

## 5. Configuring Spring Boot to Connect to Sentinel

With Spring Boot 3.x, Sentinel for Lettuce can be configured in `application.yml`:

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

The `nodes` list holds Sentinel addresses reachable by the application. Do not supply a fixed Redis primary address as an alternative connection point when the goal is role-based discovery.

If both Redis and Sentinel enable authentication, distinguish **credentials for data nodes** from **credentials for Sentinel**:

~~~yaml
spring:
  data:
    redis:
      username: redis-app-user
      password: REDIS_DATA_PASSWORD_FROM_SECRET_STORE
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.internal:26379
          - sentinel-2.internal:26379
          - sentinel-3.internal:26379
        username: sentinel-app-user
        password: SENTINEL_PASSWORD_FROM_SECRET_STORE
~~~

Password values are illustrative placeholders; in real applications inject them from environment/secret managers and never commit secrets to source code. If your infrastructure does not require Redis/Sentinel usernames or passwords, configure those fields according to your authentication setup.

Depending on your Spring Boot/Spring Data Redis version, verify exact property names and driver capabilities. In older Spring Boot versions, the `spring.redis` namespace may differ from `spring.data.redis` in modern versions.

### Java Configuration with `RedisSentinelConfiguration`

When you prefer not to rely solely on Spring Boot auto-configured connection factories, configure manually:

~~~java
package com.example.redis.sentinel;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisSentinelClientConfig {

    @Bean
    RedisConnectionFactory redisConnectionFactory() {
        RedisSentinelConfiguration sentinel =
            new RedisSentinelConfiguration()
                .master("mymaster")
                .sentinel("sentinel-1.internal", 26379)
                .sentinel("sentinel-2.internal", 26379)
                .sentinel("sentinel-3.internal", 26379);

        LettuceClientConfiguration client =
            LettuceClientConfiguration.builder()
                .commandTimeout(Duration.ofSeconds(3))
                .build();

        return new LettuceConnectionFactory(sentinel, client);
    }
}
~~~

This example demonstrates discovery and omits Redis/Sentinel ACLs, TLS, or other security settings. When needed, configure them on the Sentinel configuration and Lettuce client configuration accordingly. Avoid accidentally creating multiple inconsistent `RedisConnectionFactory` beans when combining auto-configuration with custom beans.

With a Sentinel-aware factory, `RedisTemplate`, `StringRedisTemplate`, Spring Cache, and many other Spring Data Redis APIs leverage the underlying connection management. Business services do not need to manually execute `SENTINEL get-master-addr-by-name` before each Redis command.

## 6. Primary Discovery at Startup

Initialization flow:

~~~text
           Spring Boot starts up
                    |
                    v
      Read mymaster + Sentinel nodes
                    |
                    v
       LettuceConnectionFactory
                    |
                    v
        Find an available Sentinel
                    |
                    v
    Query primary for group "mymaster"
                    |
                    v
          Receive Redis host:port
                    |
                    v
       Connect to current Redis primary
                    |
                    v
   RedisTemplate / repository / cache manager
                    |
                    v
              GET / SET / HGET
~~~

The client can try multiple Sentinels if one node is unresponsive. However, distinguish two conditions: **one Sentinel answering discovery** and **enough Sentinels to elect a new primary**. When a majority of Sentinels becomes unavailable, the client may still read stale discovery info, yet the system cannot automatically complete a new failover.

Sentinel is a **discovery point**, not a data proxy:

~~~text
App → Sentinel       : ask for primary address
App → Redis primary  : execute GET/SET commands
~~~

After connecting directly to the primary, the application does not send every command through Sentinel port `26379`.

## 7. What Happens to Connections When the Primary Changes?

Suppose Redis A is serving application connections and B gets promoted:

- Connections to A may drop if A crashes.
- Connections to A may linger if A is partitioned or returns under a new role.
- In-flight commands may hit connection resets, timeouts, or `READONLY`.
- Sentinel-aware Lettuce can update the endpoint, reconnect, and use B for eligible connections.
- New operations after driver recovery are sent to the current primary.

Illustrative timeline:

~~~text
T0    SET succeeds on Redis A
T1    Redis A fails / network disconnects
T2    Some commands encounter errors
T3    Sentinels declare ODOWN, coordinate failover
T4    Redis B is promoted
T5    Client updates primary address and opens connections
T6    New commands recover on Redis B
~~~

The `T1–T6` interval depends on Sentinel detection timeouts, election mechanics, network latency, Redis driver behavior, and application load. A fixed number of seconds cannot be guaranteed merely because Sentinel is enabled.

### Do Not Cache the Primary Address from a Single Lookup

An anti-pattern:

~~~java
// Query Sentinel once, then use a standalone client forever.
String primaryHost = discoverPrimaryAtStartup();
RedisStandaloneConfiguration config =
    new RedisStandaloneConfiguration(primaryHost, 6379);
~~~

This turns discovery into a static lookup. When topology changes, `RedisStandaloneConfiguration` does not automatically update roles. Using `RedisSentinelConfiguration` with a supporting driver is the proper approach for Sentinel topologies.

## 8. Reading from Replicas and Consistency Limits

To offload the primary, some applications configure Lettuce to prefer reading from replicas. Programmatic configuration can use:

~~~java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .readFrom(ReadFrom.REPLICA_PREFERRED)
        .commandTimeout(Duration.ofSeconds(3))
        .build();
~~~

`ReadFrom.REPLICA_PREFERRED` prefers replicas for read commands that the driver identifies as read-only; fallback behavior still depends on topology and live connections. Pass this client configuration when building the corresponding `LettuceConnectionFactory`.

**Replica reads can return stale data due to asynchronous replication:**

~~~text
Client -- SET counter=100 --> Primary
                                 |
                     Asynchronous replication
                                 |
                                 v
Client -- GET counter ------> Replica
                                 |
                                 v
                    May still observe counter=99
~~~

If an API requires **read-your-writes** after an important update, consider reading from the primary or designing a dedicated consistency mechanism. During failover, replicas can change roles to primary and others get reconfigured; assuming reads are always as fresh as the primary is wrong.

For ordinary caches, replica reads may be acceptable. For permissions, balances, quotas, or data requiring strict consistency, evaluate replication lag and read semantics carefully before enabling them.

## 9. Retries Within the Failover Window

When Redis loses connectivity right as a client sends a command, a timeout **does not prove** Redis did not execute the command. Retrying the wrong kind of operation can apply a business effect twice.

| Operation | What Can Retries Cause? | How to Reason About It |
| --- | --- | --- |
| `GET key` | Result may change between two reads | Usually safe for bounded query retries |
| `SET key value` | May overwrite newer changes | Idempotent to the same value only when there is no contention |
| `DEL key` | Count of deleted keys returned differs | Can fit if the end goal is key absence |
| `INCR`/`DECR` | Increments/decrements twice if the first ran | Never blindly retry |
| `LPUSH`/`RPUSH` | May append duplicate elements | Needs deduplication if business forbids duplicates |
| `XADD` with auto-generated ID | Creates two entries with the same payload | Needs stable event IDs and duplicate checks |
| `SET` with TTL | Refreshes expiration deadline on retry | Consider business deadlines |

At the application layer, answer:

1. If Redis applied the command but the response was lost, is retrying safe?
2. If Redis switched primaries, which source determines the final business state?
3. How many retries, with what timeout, and is there backoff/jitter?
4. When retries are exhausted, does the API return an error, fall back, or enqueue the work?
5. If hundreds of instances retry simultaneously, can upstream/databases handle the load?

Do not enable unbounded retries for all commands. `INCR`, event writes, balance mutations, or multi-step transactions require deduplication/idempotency designed for the business logic.

### Cache-Aside Example with Fallback on Redis Failure

~~~java
package com.example.redis.sentinel;

import java.time.Duration;
import java.util.Objects;
import java.util.function.Supplier;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;

    public ProductCacheReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String load(
            String id,
            Supplier<String> fetchFromDatabase) {
        Objects.requireNonNull(id);
        Objects.requireNonNull(fetchFromDatabase);

        String key = "cache:product:" + id;
        try {
            String cached = redis.opsForValue().get(key);
            if (cached != null) {
                return cached;
            }
        } catch (RedisConnectionFailureException error) {
            // Cache tolerates temporary misses; production needs metrics.
        }

        String loaded = Objects.requireNonNull(
            fetchFromDatabase.get()
        );

        try {
            redis.opsForValue().set(
                key, loaded, Duration.ofMinutes(5)
            );
        } catch (RedisConnectionFailureException error) {
            // Best-effort cache: still return data from the primary source.
        }
        return loaded;
    }
}
~~~

This pattern is for caches that are **not the authoritative data source**. Do not apply silent fallbacks when Redis holds critical business state. The illustrative code catches only connection failures; real applications may encounter timeouts or other driver errors that need specific classification. Do not catch all `RuntimeException` and hide serialization or programming bugs.

The example does not guard against stampedes on simultaneous cache misses; when failover increases miss rates, add rate limiting, single-flight coalescing, circuit breakers, or concurrency controls to protect the database.

## 10. Impact on Spring Cache, Repositories, and Transactions

If the application uses `RedisCacheManager`, `RedisTemplate`, or Redis Repositories backed by the same Sentinel-aware `RedisConnectionFactory`, these layers benefit from driver-level address discovery.

However, **connection recovery does not mean full recovery of previously sent commands**:

- A pipeline may have transmitted part of its commands without receiving all replies.
- A `MULTI/EXEC` transaction may hit a connection error right when the client does not know whether Redis executed it.
- A Repository may write an entity across multiple keys, such as a Hash and secondary indexes; failover mid-sequence does not make the sequence atomic.
- Spring Cache may experience a spike in cache misses, causing many requests to reload data from the source concurrently.

Sentinel helps find the **new primary**, not act as a cross-system transaction manager. Specifically, asynchronous Redis replication means a command that succeeded on the old primary still risks being absent from the new primary's data.

## 11. Differences Between Redis Sentinel and Redis Cluster

Both topologies are dynamic, but their goals differ:

| Aspect | Redis + Sentinel | Redis Cluster |
| --- | --- | --- |
| Purpose | High availability for a single Redis replication group | Partitioning the keyspace across hash slots on multiple primaries |
| Data writes | One current primary in the group | Primary owning the corresponding hash slot |
| Discovery | Master name + list of Sentinels | Cluster node/slot topology |
| Failover | A replica is promoted for the group | A shard's replica can become primary |
| Automatic key sharding? | **No** | **Yes** |
| Client capabilities required | Sentinel discovery/reconnect | Slot map, `MOVED`/`ASK` redirects, and topology refresh |

Do not configure `spring.data.redis.sentinel.master` to connect to Redis Cluster expecting the client to understand hash slots. For Cluster, use Spring Data Redis's Redis Cluster configuration.

Sentinel does not scale write throughput by partitioning data across multiple independent primaries. If your problem requires sharding, evaluate Redis Cluster or another partitioning scheme.

## 12. Addresses Announced by Sentinel Must Be Reachable

A very common mistake in Docker, Kubernetes, or NAT environments is **the application can reach Sentinel, yet cannot reach the primary address returned by Sentinel**.

~~~text
App outside Docker network
       |
       +-- Connects to sentinel.company:26379 successfully
       |
       +-- Sentinel returns Redis primary = 172.18.0.5:6379
       |
       +-- 172.18.0.5 only exists inside the Docker network
       |
       +-- App cannot connect to the Redis primary
~~~

Ensure the addresses advertised by Redis/Sentinel are reachable by peers and clients. Settings like `sentinel announce-ip`, `sentinel announce-port`, or replica announce settings may be relevant depending on topology.

Opening Sentinel port `26379` through a firewall is insufficient if clients cannot reach Redis data nodes after discovery. In Kubernetes, design DNS/Service/StatefulSet and announce settings to match the application's network scope.

Test connectivity from **where the application actually runs**, not solely from a shell inside a Redis container.

## 13. Inspecting the New Primary and Replication

Useful inspection commands (run only in authorized environments):

~~~bash
# Ask Sentinel which primary it currently recognizes.
redis-cli -h sentinel-1.internal -p 26379 SENTINEL get-master-addr-by-name mymaster

# Inspect group metadata.
redis-cli -h sentinel-1.internal -p 26379 SENTINEL master mymaster
redis-cli -h sentinel-1.internal -p 26379 SENTINEL replicas mymaster

# Check actual roles on Redis data nodes.
redis-cli -h redis-a.internal -p 6379 ROLE
redis-cli -h redis-b.internal -p 6379 ROLE
redis-cli -h redis-b.internal -p 6379 INFO replication
~~~

`ROLE` and `INFO replication` show the current role and synchronization details. Output may still use legacy `master/slave` terms depending on Redis version, even though this lesson uses primary/replica.

Do not conclude the application has recovered merely because Sentinel returns a new host. Check:

- Can the client perform a safe test write/read after the switch?
- Are there `READONLY` errors or repeated reconnect loops?
- Are replicas keeping up with the new primary acceptably?
- Have API p95/p99 latencies and error rates recovered?
- Are cache misses overloading databases or upstreams?

Metrics and logs worth monitoring:

| Source | Signal | Purpose |
| --- | --- | --- |
| Sentinel | `+sdown`, `+odown`, `+switch-master` | Observe failure detection and primary switch timing |
| Redis | `INFO replication`, replication lag/offset | Track replica synchronization progress |
| Client | reconnects, command timeouts, connection errors | Measure application impact |
| API | error rate, p95/p99 latency | Measure business impact |
| Cache | hit/miss, fallback QPS | Detect cache avalanches during Redis disruption |
| Infrastructure | Sentinel node health and network | Evaluate ability to achieve quorum/majority |

Sentinel publishes Pub/Sub notifications on primary transitions, but notifications are not a durable replayable event log. If a monitoring system loses connectivity, it can miss messages; combine notifications with current-state polling/checks.

## 14. Testing Failover in an Isolated Environment

To truly test Redis Sentinel, you need a topology with a primary, eligible replicas, and multiple independent Sentinels. A single Redis container does not demonstrate electing a new primary.

Test topology:

~~~text
Redis A: 10.0.0.11:6379    initial PRIMARY
Redis B: 10.0.0.12:6379    REPLICA
Redis C: 10.0.0.13:6379    REPLICA

Sentinel S1: 10.0.0.21:26379
Sentinel S2: 10.0.0.22:26379
Sentinel S3: 10.0.0.23:26379

master name = mymaster
quorum      = 2
~~~

This is an illustrative diagram, not a ready-to-deploy config file. If using Docker Compose, Testcontainers, or Kubernetes, configure replication, Sentinel monitoring, and announce addresses for your test network.

### Controlled Test Procedure

1. Start the test topology and confirm Sentinel returns Redis A's address.
2. Start the Spring Boot app configured with Sentinel; run `SET`/`GET` on a dedicated test key.
3. Wait for replicas to receive the data and record pre-failure replication state.
4. Stop primary A or run `SENTINEL FAILOVER mymaster` **only in an authorized test environment**.
5. Watch Sentinel identify the new primary B or C; check `ROLE` directly.
6. Keep sending requests through the **same running application**, observe transition errors, and wait for the connection factory to self-recover.
7. Verify post-failover commands read/write successfully without manually editing `spring.data.redis.host`.
8. Restart Redis A and verify it does not reclaim the old primary role automatically, but is configured properly in the new topology.
9. Reconcile operations executed right around the failure, especially non-idempotent commands that timed out.

Never run failover tests in production just to verify an example. Use a dedicated environment, synthetic data, and a recovery plan.

### Avoid Testing with Hardcoded Sleep Durations

A JUnit/Testcontainers test should use **polling with a bounded timeout** to wait for Sentinel to return the new primary, the new Redis node to switch roles, and the application to execute a test command successfully. Do not simply call `Thread.sleep(5000)` assuming failover always finishes within 5 seconds.

Discovery, election, and reconnection happen asynchronously. A test sleeping a fixed number of seconds is prone to flakiness on slow CI runners or varying networks. Likewise, no simple integration test can prove zero writes are lost under every partition scenario.

## 15. Common Errors and How to Fix Them

| Symptom | Common Cause | Remediation |
| --- | --- | --- |
| App still connects to old primary | Fixed host or one-time startup lookup | Configure Sentinel-aware `LettuceConnectionFactory` |
| Connects to Sentinel, cannot reach Redis data node | Sentinel returns unreachable internal/NAT IP | Fix announce settings, DNS, or routing |
| Cannot elect a new primary automatically | Insufficient Sentinels for quorum/majority | Distribute and monitor Sentinels independently |
| Write commands return `READONLY` | App hitting a replica or stale connection | Check roles and reconnect behavior |
| ACKed write lost after failover | Asynchronous replication; replica had not received it | Review durability and business preservation strategy |
| Reads see stale data | Reading from a replica with replication lag | Read from primary if read-your-writes is required |
| Retry increments counter twice | `INCR` ran, client missed response | Use idempotency/reconciliation; never blindly retry |
| Redis A returns but rejects writes | A is now a replica of the new primary | Rediscover primary; do not force writes to A |
| Cache misses spike sharply | Redis failover causes disruption; many requests fall back | Single-flight, rate limiting, backoff/circuit breaker |
| Connections time out after failover | Client hasn't refreshed topology or unstable network | Inspect driver reconnects and Sentinel announced address |
| Trying Redis Cluster with Sentinel config | Topology mismatch | Use the proper Redis Cluster configuration |
| Pipeline/transaction outcome uncertain | Connection failed mid-flight | Reconcile actual state; do not assume rollback |

## 16. Summary

**Redis Sentinel enables role-based primary discovery and coordinates switching the primary when a replica is promoted.** In Spring Data Redis, configuring Sentinel with a master name, multiple Sentinel nodes, and Lettuce prevents the application from needing manual Redis address updates after every transition.

However, this mechanism does not make failover instantaneous or lossless. Replication is asynchronous by default, clients may see timeouts during role transitions, and commands without responses are not always safe to retry. Replica reads also carry stale-data risk.

A solid Sentinel deployment requires: **proper discovery**, **reachable addresses**, **appropriate quorum/majority**, **client reconnects**, **idempotent retries**, **separating replica reads from primary reads**, and **failover testing in a controlled environment**. When these boundaries are clear, Spring Data Redis can continue working with the new primary without turning every failover into an application reconfiguration event.
