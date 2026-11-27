# Driver Read Policies for Primary or Replica

## 1. Why Connecting to Redis Does Not Guarantee Reading the Latest Data Version

Suppose a Spring Boot system stores login sessions, product configurations, and cached results in Redis. For higher availability, Redis is deployed with **one primary** and **two replicas**, while **Sentinel** monitors and performs role transitions when the primary fails.

```text
                        Spring Boot
                            |
                       Redis Client
                            |
                     Sentinel nodes
                  (discover primary)
                            |
                            v
                   +----------------+
         WRITE --> | Primary P      | <--- Default READ
                   +----------------+
                     |            |
          Replication|            |Replication
                     v            v
                +----------+  +----------+
                | Replica A|  | Replica B|
                +----------+  +----------+
                      ^             ^
                      |             |
                 Can READ      Can READ
                via driver    via driver
```

The **primary** accepts write commands and acts as the source from which replicas synchronize data. **Replicas** copy data from the primary and commonly serve read queries. Standard Redis replication is **asynchronous**: at a given point in time, a replica may not yet have received the primary's latest changes.

Because of this, the very same code:

```java
redisTemplate.opsForValue().get("product:42:price");
```

can return different results depending on **which node the Redis client picks for the read**.

A Redis driver such as **Lettuce** provides a read policy (*read routing policy*) to decide whether read commands are sent to the primary or to replicas. In Spring Data Redis, this configuration is typically passed through `LettuceClientConfiguration`.

Key point to understand upfront:

> **Sentinel discovers the primary and assists with failover; Lettuce's `ReadFrom` policy decides the read path. The two mechanisms are related but do not replace each other.**

This lesson focuses on how read policies work, choosing them based on consistency requirements, and configuring them in a Spring Data Redis application using Sentinel.

## 2. Distinguishing Replication, Sentinel, and ReadFrom

### 2.1. What Does Replication Do?

Redis replication copies data-modifying operations from the primary to replicas. Replicas maintain copies to support recovery and optionally offload read traffic.

A typical sequence of events:

```text
t0: Spring Boot -> SET account:7:status "ACTIVE" -> Primary
t1: Primary returns OK to application
t2: Primary emits change over replication stream
t3: Replica A receives and applies change
t4: Replica B receives and applies change
```

There is no default guarantee that `t2`, `t3`, and `t4` have completed **before** the client receives the write acknowledgment at `t1`.

If the application writes and immediately reads from a replica, the replica may still see the **old value** or no key at all.

### 2.2. What Does Sentinel Do?

Redis Sentinel has these main responsibilities:

- Monitoring the primary and replicas of a Redis group.
- Detecting when the primary is unhealthy.
- Coordinating election and failover according to configuration.
- Notifying or allowing clients to discover the current primary address.
- Providing information about monitored replicas.

Sentinel **is not** a node storing all application data and **is not** a proxy accepting every `GET`/`SET` command and forwarding it. Redis clients typically query Sentinel for topology, then connect directly to the appropriate Redis data nodes.

```text
Spring Boot
    |
    | Ask Sentinel: who is the primary for "mymaster"?
    v
Sentinel
    |
    | Return primary address / topology info
    v
Spring Boot ---- SET ----> Primary
      |
      +-------- GET ----> Primary or Replica
                          (per client policy)
```

### 2.3. What Does ReadFrom Do?

Lettuce provides the `ReadFrom` concept to choose where to send **eligible read commands** in a primary–replica topology.

For example:

```java
ReadFrom.REPLICA_PREFERRED
```

expresses the intent to **prefer reading from replicas**, while falling back to the primary when no suitable replica is available per the client's selection policy.

On its own, `ReadFrom`:

- Does not create new replicas.
- Does not alter Redis's asynchronous replication mechanism.
- Does not guarantee a replica has caught up with the primary.
- Does not automatically make a SQL transaction and Redis strongly consistent.
- Does not enable valid write commands to run on a replica just because a read policy was set.
- Does not guarantee zero disruption during every moment of failover.

## 3. Read Policies to Know

Constant names may vary or have aliases/deprecations across Lettuce versions. Modern versions typically use **upstream** to refer to the primary, whereas older versions used **master**.

| Lettuce Policy | Practical Meaning | When to Consider |
|---|---|---|
| `ReadFrom.UPSTREAM` | Sends read commands to the upstream/primary | Read paths needing the latest data applied by the primary |
| `ReadFrom.UPSTREAM_PREFERRED` | Prefers primary; may use replicas when primary is unavailable per client policy | Read paths prioritizing freshness while accepting fallback |
| `ReadFrom.REPLICA` | Selects only replicas for eligible read commands | Reads tolerating lag with error handling when no replica exists |
| `ReadFrom.REPLICA_PREFERRED` | Prefers replicas; falls back to primary when no eligible replica is found | Offloading read traffic from primary while keeping a fallback path |
| `ReadFrom.ANY` | Can select primary or replica | Cases accepting minimal control over read placement |
| `ReadFrom.LOWEST_LATENCY` | Prefers nodes with lower measured latency per client mechanism | When latency matters and shifting node selection is acceptable |

In some versions you may see `ReadFrom.MASTER` / `ReadFrom.MASTER_PREFERRED`, which is the older naming for primary preference. When implementing, use the exact API of your locked Lettuce version.

### 3.1. Reading from the Primary

```java
ReadFrom.UPSTREAM
```

Advantages:

- Once a write completes on the primary with no competing mutations, the next read on the **same active primary** sees the written value.
- Avoids primary-to-replica replication delay on that read path.
- Better suited for views or flows requiring *read-your-writes*.

Limitations:

- Read load continues hitting the primary.
- If the primary becomes unavailable, not every read will automatically succeed.
- During failover, a write acknowledged by the old primary but not yet replicated can be lost on the new primary. Reading from primary **is not an absolute durability promise** across failover.

### 3.2. Preferring Replicas

```java
ReadFrom.REPLICA_PREFERRED
```

Advantages:

- Can reduce read load on the primary.
- Distributes a portion of read traffic across replicas.
- Can fall back to the primary when no suitable replica is present, helping preserve read availability during certain topology changes.

Risks:

- Reading data that has not yet updated.
- A read after a write may observe a stale version.
- Freshness depends on replication lag and which replica the client picks.
- **Falling back to primary does not mean the driver automatically detects a lagging replica.** A replica that is online yet slow may continue being selected.

### 3.3. Reading Only from Replicas

```java
ReadFrom.REPLICA
```

This makes sense when a workload genuinely wants to isolate reads and accepts losing read capability if no replica is available. It is generally **not** a safe default for critical APIs because:

- No eligible replica may exist during startup or failover.
- A degraded replica can increase timeouts.
- Reads can be stale even while the node responds normally.

### 3.4. Selecting by Latency Does Not Mean Selecting by Freshness

```java
ReadFrom.LOWEST_LATENCY
```

The node with the lowest RTT is not necessarily the node with the latest data. A replica located close to the application may reply faster than the primary yet lag behind in applying replication.

If the business requirement is "a user who just changed their password must see the new status immediately," **do not choose nodes based solely on RTT**.

## 4. How Does Redis Distinguish Read and Write Commands?

The `ReadFrom` policy mainly applies to commands the driver recognizes as **read-only** and eligible for replica routing. Examples on the read path:

```redis
GET product:42
HGETALL product:42
MGET cache:1 cache:2
TTL session:42
```

Write path:

```redis
SET product:42 "new"
HSET product:42 price 120
DEL cache:1
INCR metrics:requests
```

Normally write commands must go to the primary. Redis replicas do not allow direct data writes like an active primary by default.

Points to note:

- Do not assume **every command that looks like a "read"** is routed to replicas across all driver versions. The driver must understand the command's semantics.
- `MULTI/EXEC` transactions, Lua scripts, and special server commands require separate consideration and should not be assumed to follow regular read routing.
- Commands relying on session or connection state can behave differently from a standalone `GET`.
- For Redis Cluster, routing also depends on hash slots; do not take Sentinel examples and apply them verbatim to Cluster.

**Important:** `ReadFrom` policies do not inspect business logic. They do not know which operations "require strong consistency" unless developers classify read paths accordingly.

## 5. Replication Lag and Stale Data

### 5.1. Read-After-Write Scenario

A request updates session status:

```text
t0  Spring Boot -> SET user:7:status ACTIVE -> Primary
t1  Primary returns OK
t2  Spring Boot -> GET user:7:status -> Replica A
t3  Replica A still holds BLOCKED
t4  Replica A receives the new copy and applies ACTIVE
```

At `t2`, the application may read **`BLOCKED`**, even though the primary write returned OK.

This is **replication lag**, not the Redis client altering data.

### 5.2. Read-After-Write Consistency

*Read-your-writes* means that after a client completes a write, subsequent reads by that client observe the change.

If this is required:

- Read back from the **primary** after writing.
- Or return the newly written data directly from the request context when appropriate.
- Or use a specific version/replication coordination mechanism, accepting its complexity and real-world limits.

Do not simply switch from `REPLICA_PREFERRED` to `REPLICA` and hope data becomes more consistent.

### 5.3. Which Business Cases Tolerate Replica Lag?

| Data / Feature | May Replica Reads Fit? | Notes |
|---|---|---|
| Infrequently changing product catalog | Possibly | Tolerates brief display delay |
| Dashboard view-count statistics | Possibly | Document expected delay |
| Public article cache | Possibly | Combine with appropriate TTL/invalidation |
| Informational stock display | Possibly, if delay is tolerable | Order placement must perform an accurate check elsewhere |
| User just edited profile and immediately reads it | Prefer primary | Avoid showing old data after update |
| Session logout/revocation | Be cautious; usually needs authoritative source | Replica lag can return old session state |
| Balances and payment commands | Never use stale replicas for final decisions | Requires authoritative store and transaction mechanism |
| Distributed locks / race conditions | Never rely on stale replicas | Must operate consistently where writes are authoritative |

These recommendations classify by **business semantics**. The same key may have a display read path that tolerates staleness and a transactional decision path that needs fresher data.

## 6. Configuring Sentinel in Spring Boot

Spring Boot supports configuring Redis Sentinel connections via properties. Example for Spring Boot 3.x:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
      connect-timeout: 2s
      timeout: 2s
```

In this configuration:

- `master` is the **primary group name** monitored by Sentinels, e.g. `mymaster`. It is not the primary's hostname.
- `nodes` are **Sentinel addresses**, typically on port 26379, not a list of replicas for direct reading.
- The client uses Sentinel to discover Redis data node addresses.
- If the primary changes after failover, the driver must refresh topology/connections accordingly.

In older Spring Boot versions, the prefix may be `spring.redis.*` rather than `spring.data.redis.*`. Use the prefix matching your project's version.

**Sentinel YAML alone does not route read commands to replicas.** The rest depends on the Redis driver's configuration.

## 7. Configuring Read Policies in Lettuce

### 7.1. Using Spring Boot Auto-Configuration

In Spring Boot 3.x with Lettuce, customize the client builder via `LettuceClientConfigurationBuilderCustomizer`:

```java
package com.example.redis;

import io.lettuce.core.ReadFrom;

import org.springframework.boot.autoconfigure.data.redis
        .LettuceClientConfigurationBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LettuceReadPolicyConfig {

    @Bean
    public LettuceClientConfigurationBuilderCustomizer
    readFromReplicaPreferred() {

        return builder ->
                builder.readFrom(ReadFrom.REPLICA_PREFERRED);
    }
}
```

How this works:

1. Spring Boot reads the Sentinel configuration from `application.yml`.
2. Spring Boot builds the Lettuce client configuration, applying the customizer when auto-configuration runs.
3. Lettuce applies the `REPLICA_PREFERRED` policy for read commands supporting routing.
4. Write commands continue going to the primary per Redis mechanics.

**Point of caution:** a customizer on the auto-configured Redis connection factory affects **all read paths sharing that factory**. If your application mixes lag-tolerant data with data requiring primary reads, do not apply `REPLICA_PREFERRED` globally without classifying paths.

Additionally, if your project manually constructs a `LettuceConnectionFactory`, Spring Boot may not apply this customizer. In that case, configure `readFrom` directly on your factory.

### 7.2. Creating LettuceConnectionFactory with a Read Policy

Spring Data Redis Java example:

```java
package com.example.redis;

import java.time.Duration;

import io.lettuce.core.ReadFrom;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce
        .LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce
        .LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class SentinelRedisConfiguration {

    @Bean
    public RedisSentinelConfiguration redisSentinelConfiguration() {
        return new RedisSentinelConfiguration()
                .master("mymaster")
                .sentinel("sentinel-a.internal", 26379)
                .sentinel("sentinel-b.internal", 26379)
                .sentinel("sentinel-c.internal", 26379);
    }

    @Bean
    public LettuceConnectionFactory redisConnectionFactory(
            RedisSentinelConfiguration sentinels) {

        LettuceClientConfiguration client =
                LettuceClientConfiguration.builder()
                        .readFrom(ReadFrom.REPLICA_PREFERRED)
                        .commandTimeout(Duration.ofSeconds(2))
                        .build();

        return new LettuceConnectionFactory(sentinels, client);
    }

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            LettuceConnectionFactory connectionFactory) {
        return new StringRedisTemplate(connectionFactory);
    }
}
```

For readable code, in real Java files write import lines cleanly on a single line:

```java
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
```

Do not put line breaks **in the middle of a qualified name inside an import statement** as formatted above for narrow columns; Java requires unbroken import syntax.

**Notes for real projects:**

- Set proper hostnames and authentication/TLS configuration.
- When using Spring Boot auto-configuration, manually building the entire factory is usually unnecessary; using a customizer as in Section 7.1 is cleaner.
- If registering multiple `RedisConnectionFactory` beans, manage bean names/`@Primary` to prevent wrong injections.
- `LettuceClientConfiguration.readFrom(...)` requires driver/topology support for replica reads. Never assume a single arbitrary Redis address lets the client discover every replica across all NAT/container environments.
- Never expect code to write to replicas just because a read policy was configured.

## 8. One Application Needing Both Read Paths: Primary and Replica

Sending all `GET`s to replicas can cause post-update reads to see stale data. A clean solution is defining **two Redis access paths**:

```text
                      ProductService
                      /            \
                     /              \
         Reads needing latest    Reads tolerating lag
                   |                    |
              Primary reader        Replica reader
                   |                    |
                 PRIMARY              REPLICA
```

Separate them using two factories/templates with distinct `ReadFrom` configurations.

### 8.1. Two Connection Factories in One Configuration

Example:

```java
package com.example.redis;

import java.time.Duration;

import io.lettuce.core.ReadFrom;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class DualReadRoutingConfiguration {

    @Bean
    public RedisSentinelConfiguration sentinelTopology() {
        return new RedisSentinelConfiguration()
                .master("mymaster")
                .sentinel("sentinel-a.internal", 26379)
                .sentinel("sentinel-b.internal", 26379)
                .sentinel("sentinel-c.internal", 26379);
    }

    @Bean("primaryRedisConnectionFactory")
    @Primary
    public LettuceConnectionFactory primaryRedisConnectionFactory(
            RedisSentinelConfiguration topology) {

        LettuceClientConfiguration config =
                LettuceClientConfiguration.builder()
                        .readFrom(ReadFrom.UPSTREAM)
                        .commandTimeout(Duration.ofSeconds(2))
                        .build();

        return new LettuceConnectionFactory(topology, config);
    }

    @Bean("replicaRedisConnectionFactory")
    public LettuceConnectionFactory replicaRedisConnectionFactory(
            RedisSentinelConfiguration topology) {

        LettuceClientConfiguration config =
                LettuceClientConfiguration.builder()
                        .readFrom(ReadFrom.REPLICA_PREFERRED)
                        .commandTimeout(Duration.ofSeconds(2))
                        .build();

        return new LettuceConnectionFactory(topology, config);
    }

    @Bean("primaryRedisTemplate")
    @Primary
    public StringRedisTemplate primaryRedisTemplate(
            @Qualifier("primaryRedisConnectionFactory")
            LettuceConnectionFactory factory) {

        return new StringRedisTemplate(factory);
    }

    @Bean("replicaRedisTemplate")
    public StringRedisTemplate replicaRedisTemplate(
            @Qualifier("replicaRedisConnectionFactory")
            LettuceConnectionFactory factory) {

        return new StringRedisTemplate(factory);
    }
}
```

In this setup, both factories discover the primary and replicas via Sentinel, yet use **different read-node selection policies**.

`@Primary` ensures components without `@Qualifier` default to the primary-oriented factory/template, though in complex Redis configurations you should still inject explicit bean names for critical features.

**Note:** this example creates additional connections and client resources. A project with multiple factories must keep timeouts, pools, lifecycles, monitoring, and security consistent. This is a deliberate trade-off, not a mandatory pattern for every application.

### 8.2. Service Selecting the Read Path by Business Semantics

```java
package com.example.redis;

import java.time.Duration;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductRedisService {

    private final StringRedisTemplate primary;
    private final StringRedisTemplate replicaPreferred;

    public ProductRedisService(
            @Qualifier("primaryRedisTemplate")
            StringRedisTemplate primary,
            @Qualifier("replicaRedisTemplate")
            StringRedisTemplate replicaPreferred) {

        this.primary = primary;
        this.replicaPreferred = replicaPreferred;
    }

    public void updatePrice(long productId, String price) {
        primary.opsForValue().set(
                key(productId),
                price,
                Duration.ofMinutes(10)
        );
    }

    // Example: catalog API can tolerate slightly stale data.
    public Optional<String> readForCatalog(long productId) {
        return Optional.ofNullable(
                replicaPreferred.opsForValue().get(key(productId))
        );
    }

    // Example: read immediately after a user updates the price.
    public Optional<String> readAfterUpdate(long productId) {
        return Optional.ofNullable(
                primary.opsForValue().get(key(productId))
        );
    }

    private String key(long productId) {
        return "product:price:" + productId;
    }
}
```

The important part is not having two `get` methods, but the **rule governing which one to call**:

- Less-sensitive display reads can use replicas.
- Post-write reads or business-decision reads must pick a path with adequate freshness guarantees.
- Writes always go through the primary.
- `REPLICA_PREFERRED` allows fallback per driver policy, yet **does not verify that a replica has caught up with the primary**.

### 8.3. Do Not Mutate Global Read Policy on a Shared Client

Some Lettuce-level APIs allow changing `ReadFrom` on a connection. However, if concurrent requests share the same client/connection and each request flips policies back and forth, unpredictable routing errors can result.

At the Spring Data Redis layer, it is safer to select **preconfigured templates/factories per read-path category** rather than mutating shared routing state while multiple threads or reactive subscriptions are active.

## 9. Default Settings and Differences Between Clients

Spring Data Redis supports multiple drivers, commonly Lettuce and Jedis. Replica selection capabilities and auto-discovery mechanisms are **not necessarily equivalent** across them.

- `LettuceClientConfiguration.readFrom(...)` is an explicit configuration API of **Lettuce**.
- Do not apply Lettuce `ReadFrom` concepts verbatim to a **Jedis** configuration.
- A Redis connection configured only against a single server **does not automatically gain** full Sentinel discovery and failover.
- How Spring creates, shares, and manages connections can alter the actual behavior of calls.

Before choosing a policy, know what your application is running:

```text
Spring Boot version:
Spring Data Redis version:
Redis driver: Lettuce/Jedis
Redis server version:
Redis mode: standalone + replica / Sentinel / Cluster
ConnectionFactory bean:
ReadFrom policy:
Transaction support:
Serializer:
Timeout:
```

An auto-configured Spring Boot app can change behavior when you add a custom `RedisConnectionFactory`. Always inspect the effective configuration and test in an environment matching production topology.

## 10. Replica Lag, TTL, and False Cache Miss Risks

A lagging replica does not just return old values; at times it can also report a **missing key**.

Example:

```text
t0:  Primary SET session:42 ACTIVE EX 60
t1:  Primary returns OK
t2:  GET from replica -> nil because SET not received yet
t3:  Replica applies SET
```

If the application treats `nil` as "session was deleted," it can make wrong decisions.

Or:

```text
t0:  Replica still holds value V1
t1:  Primary updates to V2
t2:  Replica GET returns V1
t3:  Replica receives V2
```

With cache-aside:

```text
GET replica -> cache miss
              |
              v
         Read database
              |
              v
         Write cache primary
```

If a large batch of keys was just written to the primary and has not reached replicas, many replica reads can trigger **false cache misses** and spike database load. Under such workloads, adding replicas does not necessarily make the system faster.

### 10.1. Reading TTL from a Replica

`TTL` reads a key's expiration metadata on the chosen node. Since replica values and metadata can lag, existence and TTL results must also be interpreted in the context of replication.

Do not use a `TTL` read on a replica as an exact clock for access revocation or business expiration decisions.

### 10.2. Reading Multiple Keys Is Not a Consistent Snapshot

If an application reads `profile:42` and `permissions:42`, two commands routed to different replicas or executed at different moments can reflect **different update points**.

Using the same read policy does not create a cross-key snapshot. If keys must be inspected consistently together, design the operation and read target around business needs instead of assuming replicas hold an instant synchronized snapshot.

## 11. How Does Sentinel Failover Affect Read Paths?

### 11.1. Before and After Failover

Suppose:

```text
Initially:
  P1: primary
  R1: replica
  R2: replica

After failure:
  P1: unavailable
  R1: promoted by Sentinel to primary
  R2: follows primary R1
```

Going from failure detection to announcing the new topology is **not instantaneous**.

```text
t0     P1 fails
t1     Sentinel detects and confirms down state
t2     Sentinel selects eligible replica to promote
t3     R1 becomes new primary
t4     Redis client discovers new topology and reconnects
t5     Commands can recover per connection/timeout policy
```

During this window:

- Writes can fail, time out, or require reconnection.
- Primary-targeted reads can be temporarily unavailable.
- Replica-targeted reads may hit a node changing roles or still syncing.
- Never assume all in-flight commands will complete successfully.
- Clients may take time to switch connections after topology changes.

### 11.2. The Promoted Replica May Lack the Most Recent Data

Because standard Redis replication is asynchronous, the old primary may have returned `OK` for some writes that were not fully transmitted to the promoted replica.

Thus, **Sentinel failover is not a guarantee against losing acknowledged writes**.

Using `ReadFrom.UPSTREAM` ensures your reads target the current primary per driver state, but cannot turn a failover event into an unconditionally linearizable/durable model.

For financial state, critical orders, or data that must never be lost, examine authoritative sources and end-to-end durability policies.

### 11.3. REPLICA_PREFERRED During Failover

`REPLICA_PREFERRED` means preferring an eligible replica and falling back per client configuration. It **does not mean**:

- Always finding an available replica in every failure.
- Automatically waiting for a replica to catch up to the primary.
- Automatically confirming all prior writes were replicated.
- Eliminating timeouts.
- Safely retrying write commands automatically.

Therefore, explicit timeout, retry, monitoring, and error-handling policies are required in the application.

## 12. Cluster READONLY Differs from Sentinel ReadFrom Policies

A common conceptual mistake is applying Redis Cluster guidance to Sentinel.

### Redis Sentinel

- One primary and replicas for a single dataset group.
- Sentinel discovers the primary and manages failover.
- Lettuce `ReadFrom` can select primary/replicas for read commands.
- Does not partition data across 16,384 hash slots like Redis Cluster.

### Redis Cluster

- Data is partitioned across hash slots with multiple primaries and replicas per primary.
- Clients route commands by slot.
- Redis provides the `READONLY` command on replica connections in Redis Cluster to allow reads per Cluster semantics.
- Read policies also depend on slot ownership and per-shard topology.

`READONLY` in Redis Cluster **is not** a generic replacement for Lettuce's `ReadFrom.REPLICA_PREFERRED` when connecting to Redis Sentinel.

Similarly, do not design an `MGET` across keys in different slots expecting it to work simply because read-from-replica is enabled on the client.

## 13. RedisTemplate, Transactions, and Read Routing

`RedisTemplate` can use different connections depending on configuration and how operations are dispatched. Pay special attention when using:

```java
redisTemplate.setEnableTransactionSupport(true);
```

or when explicitly using:

```java
SessionCallback
MULTI
EXEC
WATCH
```

Key principles:

1. **`ReadFrom` does not turn separate read commands into a transaction.**
2. **Redis transactions have specific connection and primary semantics.** Do not assume reads inside every transaction route like an isolated `GET`.
3. For `WATCH` and `MULTI/EXEC`, related commands need the same appropriate connection/session context; stale replica reads cannot serve safely as the basis for transactional decisions on the primary.
4. When Spring Data Redis participates in Spring transactions, reads and writes may use separate connections depending on configuration; verify the exact version/semantics.
5. If logic requires read-then-write with strict correctness, execute the check/mutation on the authoritative write side or use a script/atomic command.

**Unsafe** example:

```text
Replica: GET stock:item-1 -> 5 (stale)
Primary: HSET/DECR/SET based on 5
```

If the primary already had `stock=0` while the replica returned `5`, checking on the replica was wrong from the start.

Do not use replica reads for authorization checks, balance deductions, distributed locks, or quota limits requiring strict correctness without verification on the primary.

## 14. Does WAIT Completely Solve Replica Lag?

Redis provides the command:

```redis
WAIT numreplicas timeout
```

Example:

```redis
WAIT 1 1000
```

This command tells Redis to wait until a specified number of replicas acknowledge receiving replication progress for prior writes on that connection, within the timeout.

However:

- `WAIT` **does not turn Redis into a strongly consistent system**.
- With multiple replicas, one replica acknowledging does not guarantee **all replicas** have updated.
- `REPLICA_PREFERRED` may pick a different replica that has not caught up.
- It does not guarantee writes are durable on disk or safe under every failover pattern.
- You must inspect the return value and command limits; never treat a timeout as successful synchronization.

If using `WAIT`, understand **connection context and prior write ordering**, and never issue `WAIT` arbitrarily from a different `RedisTemplate`/connection expecting it to wait on the desired write.

For data requiring *read-your-writes*, re-reading on the primary remains clearer than hoping replica routing and `WAIT` happen to hit the same copy.

## 15. Observing Replication and Sentinel State

### 15.1. Identifying the Primary via Sentinel

On a Sentinel:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL get-master-addr-by-name mymaster
```

Redis returns the current primary address and port.

To view replicas known to Sentinel:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL replicas mymaster
```

This is topology discovery metadata; it does not prove which replica Spring Boot's read commands actually hit.

### 15.2. Checking Roles and Replication Progress

Connect to a Redis data node:

```bash
redis-cli -h redis-primary.internal -p 6379 ROLE
redis-cli -h redis-primary.internal -p 6379 INFO replication
```

On a replica:

```bash
redis-cli -h redis-replica-a.internal -p 6379 ROLE
redis-cli -h redis-replica-a.internal -p 6379 INFO replication
```

Commonly useful fields in `INFO replication`:

| Field | Meaning |
|---|---|
| `role` | Whether the node is primary or replica |
| `connected_slaves` / replica info | Replicas seen by the primary; naming may depend on version |
| `master_repl_offset` | Replication progress reported by primary/replica in context |
| `slave_repl_offset` | Offset reported in certain stats fields per version/role |
| `master_link_status` | Status of the replica's replication connection to the primary |
| `master_last_io_seconds_ago` | Seconds since last primary I/O activity on the replica |

Offset metrics give an indication of replication lag, but **do not replace real-time freshness measurements on business data**.

### 15.3. Observing Where Read Commands Go

To confirm a read policy is taking effect:

- Log the `ReadFrom` actually configured on the connection factory.
- Use Redis client logging/metrics in test environments when needed.
- Observe `GET` command counts and CPU on each data node.
- In an isolated load test, compare `INFO commandstats` before and after read traffic.
- Do not enable `MONITOR` casually on production Redis because it consumes resources and exposes command payloads.

An increase in `INFO commandstats` on a replica helps confirm routing, though in multi-client environments avoid assuming every increment comes from your own app.

### 15.4. Metrics to Monitor

| Metric | Operational Question |
|---|---|
| Replication lag per replica | How far behind is the copy? |
| Primary–replica link status | Can the replica still synchronize? |
| Read/write rate per node | Is load distributed as expected? |
| p95/p99 read latency | Do replicas genuinely make reads faster? |
| Primary fallback count | Is the replica-preferred policy running short of replicas? |
| Reconnect/failover count | Are clients experiencing connection disruptions? |
| Redis timeouts/errors | Is user experience impacted? |
| Stale-read incidents | Is stale data exceeding acceptable bounds? |
| Cache hits/misses | Is lag causing false misses or spiking source load? |

Not every driver exposes every metric out of the box. Where fallback/route metrics are missing, add appropriate instrumentation at the client layer or in test environments.

## 16. Hands-On Practice: Testing Read Policies

### Exercise A: Observing Replica Lag Without Intentionally Breaking Topology

1. Prepare Redis primary + replica + Sentinel in a test environment.
2. Use a primary-targeted client to write a new key with an increasing version.
3. Use a replica-targeted client to read the key back.
4. Record the write timestamp and the time the replica first observes the new version.
5. Repeat across varying payload sizes and load levels.

Example:

```redis
SET demo:replication:version 101
GET demo:replication:version
```

Run `SET` on the primary; for the comparison `GET`, target an explicit node/connection. When reading directly via Redis CLI against a replica, make sure you connect to the actual replica address.

**Not every run will observe stale data**; when replication is very fast, the replica may apply the write before your read. This exercise demonstrates the boundary and measures delay rather than forcing stale reads every time.

### Exercise B: Comparing ReadFrom.UPSTREAM and REPLICA_PREFERRED

Create two templates as in Section 8:

```java
primary.opsForValue().set("demo:price", "120");
String fromPrimary = primary.opsForValue().get("demo:price");
String fromReplica = replicaPreferred.opsForValue().get("demo:price");
```

Repeat across multiple runs in a test environment. Record:

```text
Run | Primary result | Replica result | Elapsed time | Selected node
```

Do not interpret a single run where both return `120` as proof that replicas are **always** instantaneously consistent.

### Exercise C: When a Replica Becomes Unavailable

In a controlled test environment, temporarily make a replica unavailable and compare:

- `REPLICA` may have no eligible node left to read from.
- `REPLICA_PREFERRED` can fall back to the primary per client behavior.
- `UPSTREAM` continues targeting the primary while the primary is healthy.

Observe timeouts, reconnects, and latency. Never shut down a replica in production just to test the fallback path.

### Exercise D: Switching Primary via Failover

In an isolated Sentinel test environment, run a failover following operational guidelines. Then verify:

- Sentinel announced the new primary.
- Lettuce updated its connections.
- New writes go to the new primary.
- Read-from policies continue functioning.
- The application handles timeouts during the transition window.

**Do not assume failover means zero in-flight replication writes were lost**; analyze data and application guarantees.

### Exercise E: Post-Write Read Path

Build an API that updates state and reads it back immediately. Compare:

```text
WRITE primary -> READ primary
WRITE primary -> READ replicaPreferred
```

If the API contract states "once saved, immediately visible on read," keep that read on the primary or design an explicit consistency mechanism.

## 17. Common Mistakes When Choosing Primary vs. Replica

### Mistake 1: Assuming Sentinel Automatically Routes All GETs to Replicas

Sentinel handles primary discovery and failover. The driver applies read routing; configure `ReadFrom` if you want to prefer replicas.

### Mistake 2: Treating Replicas as Instantaneously Up-to-Date Copies

Standard Redis replication is asynchronous. Replicas can return stale data or miss keys right after a write.

### Mistake 3: Using REPLICA_PREFERRED for Critical Business Checks

Reading balances, access rights, or inventory from a stale replica can cause wrong decisions. Use the primary or appropriate concurrency controls for operations requiring accuracy.

### Mistake 4: Thinking REPLICA_PREFERRED Auto-Switches to Primary When a Replica Lags

Replica-preferred policies normally fall back when no eligible replica exists in topology, **not** when a healthy replica simply serves lagging data.

### Mistake 5: Using ReadFrom.REPLICA Without Handling Missing Replicas

If only replica reads are allowed, the application must handle cases where no replica exists or responds. `REPLICA_PREFERRED` is usually more resilient for lag-tolerant data.

### Mistake 6: Mutating Policy Per Request on a Shared Connection

This causes unpredictable cross-request interactions. Separate templates/factories with fixed policies for much clearer control.

### Mistake 7: Confusing Connection Pool Size with Redis Command Behavior

Lettuce can multiplex many commands over a connection. Adding connections does not fix replication lag or ensure correct routing.

### Mistake 8: Thinking Sentinel Proxies Every Command

Sentinel provides topology and failover; clients connect directly to Redis data nodes. If firewalls permit Sentinel while blocking primary/replicas, the app will still fail.

### Mistake 9: Ignoring Failover When Evaluating Consistency

Even reading the new primary after failover does not guarantee every prior write replicated before the old primary failed. Understand the durability limits of Redis replication.

### Mistake 10: Using WAIT and Assuming Every Replica Is Synchronized

`WAIT` waits for a number of replicas to acknowledge prior replication, which does not guarantee `ReadFrom.REPLICA_PREFERRED` picks a caught-up replica or turn Redis into a distributed transaction.

### Mistake 11: Ignoring Timeouts and Retries

Failover/reconnect windows can produce timeouts. Excessive retries amplify load; retrying non-idempotent writes can apply side effects twice.

### Mistake 12: Looking Only at p50 and Ignoring Stale Reads

Replicas may show lower p50 latency while serving stale data on critical paths. Measure both p95/p99 and business-level freshness.

### Mistake 13: Assuming `LOWEST_LATENCY` Selects the Freshest Data

Network latency and replication lag are two distinct metrics. The nearest replica can be the stalest replica.

### Mistake 14: Ignoring API Versions

`MASTER`/`UPSTREAM` names, `ReadFrom` choices, and Boot/Lettuce details vary across versions. Verify locked dependencies and effective configuration.

### Mistake 15: Confusing Sentinel with Cluster

Cluster uses hash slots and has its own routing mechanics; do not apply Redis Sentinel primary–replica logic verbatim to all Redis Cluster operations.

## 18. Designing Read Policies Around System Requirements

A simple decision matrix:

| Requirement | Option to Consider | Trade-Offs |
|---|---|---|
| Catalog display, tolerates staleness | `REPLICA_PREFERRED` | Stale reads during replication lag |
| Immediate read-after-write in same flow | `UPSTREAM` | Read load remains on primary |
| API always prioritizing accurate data | Primary with suitable transaction control | Availability may dip if primary fails |
| High read volume allowing staleness | `REPLICA_PREFERRED` or replica-only with error policy | Eventual consistency |
| Background analytics reads | Replica, workload dependent | Potential lag or temporary missing data |
| Some endpoints need freshness, others throughput | Two templates/factories with explicit policies | More client configuration and resources |
| Data must survive failover without loss | Do not rely solely on ReadFrom/Sentinel | Needs durability design and authoritative store |

A useful layered pattern:

```text
HTTP Controller
      |
      v
Business Service
      |
      +--> Read model tolerating staleness
      |          |
      |          v
      |    Replica-preferred template
      |
      +--> Read needing immediate freshness / validation
      |          |
      |          v
      |     Primary-only template
      |
      +--> Write
                 |
                 v
            Primary
```

Make the primary/replica decision in a **service or repository layer that understands business semantics**, rather than toggling it secretly inside a helper where API callers do not realize data may be stale.

### 18.1. Defining Freshness SLOs

If staleness is acceptable, state the desired bounds explicitly:

```text
Catalog can be stale by up to ~2 seconds under normal load.
Dashboard can lag by up to ~30 seconds.
Reads verifying a user's own update must target the primary.
```

These are **illustrative thresholds**, not guarantees provided automatically by Redis. Measure real replication lag and plan actions when bounds are exceeded.

If stale data exceeds acceptable limits, you can:

- Temporarily shift critical reads to the primary.
- Verify versions against an authoritative source.
- Surface lag warnings or unsynchronized state.
- Throttle reads directed to unhealthy/lagging replicas.
- Adopt another application mechanism if consistency needs exceed what this model offers.

## 19. Self-Check Questions

**1. Does Sentinel directly route every GET to read from a replica?**

No. Sentinel handles monitoring, primary discovery, and failover; Lettuce applies read-node selection policies where supported by driver and topology.

**2. How does REPLICA_PREFERRED differ from REPLICA?**

`REPLICA_PREFERRED` prefers replicas while falling back to the primary if no suitable replica exists; `REPLICA` requires replica routing and easily errors if no eligible replica is available.

**3. If you write and immediately run GET on a replica, are you guaranteed to see the new data?**

No. Replication is asynchronous by default, so the replica may not have received and applied the change yet.

**4. Does reading from the primary solve every consistency issue after failover?**

No. The new primary may not have received writes acknowledged by the old primary prior to its failure.

**5. Why shouldn't replica selection rely solely on network latency?**

Because low RTT does not reflect whether data is fresh. Latency routing and replication lag are separate concepts.

**6. Does `ReadFrom` route SET commands to replicas?**

No. Read policies apply to eligible read commands; standard writes must go to the primary.

**7. Why might an application need two StringRedisTemplate beans?**

Because one read path can tolerate staleness while another needs primary reads after writes. Two templates with fixed read policies make that boundary explicit.

**8. Does `WAIT 1 1000` guarantee all replicas have caught up?**

No. It waits for the requested number of replicas to acknowledge per command semantics; it does not guarantee every replica or every form of data durability.

**9. Does a low pending connection count prove replicas have no lag?**

No. Client connection state and replication lag are distinct metrics.

**10. When running Redis Cluster, can you reuse the exact Sentinel model?**

No. Cluster also involves hash slots, multiple primaries, and distinct routing mechanics. Configure and evaluate accordingly.

## 20. Key Takeaways

- **Redis replication is asynchronous by default.** Replicas can return stale values or fail to see a key just written to the primary.
- **Sentinel manages monitoring, primary discovery, and failover**; **Lettuce `ReadFrom` governs the read policy** across supported topologies.
- **`ReadFrom.UPSTREAM`** fits read paths needing data written on the active primary; **`ReadFrom.REPLICA_PREFERRED`** fits lag-tolerant reads seeking load distribution with driver-level fallback.
- **Fallback does not detect replica lag**; healthy replicas can still return stale data.
- Spring Data Redis can be configured via **`LettuceClientConfigurationBuilderCustomizer`** or **`LettuceClientConfiguration.readFrom(...)`** on the connection factory.
- For applications with mixed read needs, **separating a primary template and a replica-preferred template** keeps consistency decisions transparent.
- **Read routing does not create strong consistency or zero-loss failover.** Evaluate read-your-writes, transactions, durability, retries, and idempotency per business workflow.
- Measure both **latency and data freshness**, along with Sentinel state, replica lag, command routing, and error rates during failover.

### References

- [Spring Data Redis — High Availability: Redis Sentinel](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html).
- [Spring Data Redis — Redis Configuration](https://docs.spring.io/spring-data/redis/reference/redis/redis-configuration.html).
- [Spring Data Redis — LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html).
- [Lettuce — ReadFrom: read preferences](https://redis.github.io/lettuce/ha-sharding/).
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/).
- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
- [Redis — WAIT](https://redis.io/docs/latest/commands/wait/).
