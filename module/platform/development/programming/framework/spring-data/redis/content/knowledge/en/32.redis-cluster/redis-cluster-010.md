# Distinguishing Sharding from Replication and Failover in Redis Cluster

## 1. Why must these three mechanisms be distinguished?

A Spring Boot system using Redis for sessions, product caches, shopping carts, or counters may need to **scale data capacity**, **keep serving when a node fails**, and **minimize outage duration**. In Redis Cluster, those three needs are addressed by three related yet fundamentally distinct mechanisms:

1. **Sharding / partitioning:** distributes Redis keys across multiple **primary/master nodes**. Its primary goal is scaling capacity and throughput.
2. **Replication:** each primary can have one or more **replicas** holding copies of that primary's data. Its purpose is redundancy and optionally serving replica reads.
3. **Failover:** when a primary becomes unavailable, Redis Cluster can **promote an eligible replica** to primary, transferring responsibility for the hash slots managed by the failed primary.

Example cluster with three primaries and three replicas:

```text
                              SPRING BOOT
                                  |
                         Lettuce Cluster client
                                  |
                 +----------------+----------------+
                 |                |                |
                 v                v                v
             Primary A        Primary B        Primary C
             slots A          slots B          slots C
                 |                |                |
          replication       replication       replication
                 |                |                |
                 v                v                v
             Replica A1       Replica B1       Replica C1
```

**Primary A and Primary B do not hold the same half of the dataset**, because they manage different slots. **Replica A1 replicates Primary A's data**, not the data of the entire cluster.

When Primary B goes down, Replica B1 can be elected to replace it and take over **slots B**. That is **failover**, not **resharding**.

> Rule to remember: **Sharding splits data; replication copies data; failover replaces the primary role upon failure.** The three mechanisms complement one another without substituting for one another.

## 2. What is Redis Cluster?

Redis Cluster is a multi-node Redis deployment mode in which data is partitioned across **16,384 hash slots**, numbered `0` through `16383`. The Cluster tracks which node owns each slot.

A key's slot is computed conceptually by:

```text
slot(key) = CRC16(key) mod 16384
```

When a key contains a **valid hash tag** inside curly braces, only the substring inside the hash tag is used to calculate the slot instead of the entire key.

Example:

```text
user:42:profile       -> a deterministic slot
product:100:stock     -> may belong to another slot
cart:{user-42}:items  -> slot of "user-42"
cart:{user-42}:total  -> same slot as "user-42"
```

Redis Cluster does not have every node store all 16,384 slots. Slot ownership is **partitioned across active primaries**.

Illustrative example:

| Node | Role | Slot Range |
| --- | --- | --- |
| Primary A | Read/write slots A | `0–5460` |
| Primary B | Read/write slots B | `5461–10922` |
| Primary C | Read/write slots C | `10923–16383` |
| Replica A1 | Copy of A | Follows Primary A |
| Replica B1 | Copy of B | Follows Primary B |
| Replica C1 | Copy of C | Follows Primary C |

The ranges in the table are merely an illustrative distribution, not a requirement to divide evenly. When a cluster adds/removes primaries or balances load, slots can be migrated to other primaries.

### How does Redis Cluster differ from one big Redis server?

A single server hits limits in RAM, CPU, and network bandwidth. Redis Cluster lets multiple primaries process disjoint key sets; adding shards increases aggregate capacity and throughput.

Yet sharding introduces architectural costs:

- Clients must know which node owns each key.
- Multi-key operations can be constrained by slots.
- Transactions or Lua scripts touching multiple keys face same-slot constraints.
- When slots migrate, clients must handle redirects.
- Topology, replication, failover, and failure domains require operational care.

Do not enable Redis Cluster solely to get HA for a small dataset. Redis primary–replica with Sentinel is an alternative when slot-based sharding is unnecessary.

## 3. Sharding: partitioning data across hash slots

**Sharding** answers the question: **where does this key live and get processed?**

Suppose you have 30 million cached keys. Instead of storing all of them on one Redis primary, the cluster distributes them across three primaries:

```text
                      Redis keyspace
                            |
               CRC16 + hash slot mapping
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
          Primary A     Primary B     Primary C
        one key group one key group one key group
```

Each primary manages a **subset** of the data. Primaries do not replicate each other's keys by default. When Primary D is added and slots migrate from A/B/C to D, data is **rebalanced**.

### What does sharding scale?

- **Memory:** keys/values live across multiple primaries, increasing total capacity.
- **Throughput:** primaries execute commands across disjoint slots in parallel.
- **Network load:** traffic distributes across multiple nodes.
- **Dataset size:** can exceed a single Redis node's RAM, provided each shard fits within its own resources.

However, sharding by itself does not:

- Create backup copies.
- Preserve data when a node dies.
- Perform failover.
- Enable atomic transactions across multiple slots.
- Eliminate all hotspots; a single super-hot key still resides in one slot.

A cluster with three primaries and **zero replicas** still performs sharding, yet if one primary fails, its slots become unavailable. Thus "sharded across multiple nodes" does not mean "highly available".

## 4. Replication: copying data within a shard

**Replication** answers the question: **if the primary holding a key goes down, is there a copy of that data?**

Within a single shard:

```text
Primary B (slots 5461–10922)
          |
          | replication
          |
          +------> Replica B1
          |
          +------> Replica B2
```

Replicas B1/B2 copy data from **Primary B**, not from Primaries A or C.

When the primary receives:

```redis
SET product:42:price 120000
```

for a key in slots B, Primary B executes the write and streams the change to B's replicas via replication.

### Is replication synchronous?

Redis replication is normally **asynchronous**. The primary can acknowledge success to the client before a given replica receives and applies that write.

Timeline:

```text
T0   Client -> Primary B: SET key=value
T1   Primary B executes write
T2   Primary B returns OK
T3   Replication stream sends write to Replica B1
T4   Replica B1 applies write
```

From T2 to T4, the replica can still hold the old value. Delay depends on network, load, replication state, and transient issues.

**Replication is a copy-creation mechanism, not a guarantee that every write ACKed on the primary always survives failover.**

### Can replicas be read from?

Clients like Lettuce support optional read-from-replica policies. This can offload read traffic from primaries, at the cost of **eventual consistency** and risking stale reads right after writes.

Product price update example:

```text
Client writes price=120000 to Primary B
Client immediately reads Replica B1
Replica has not synced yet -> returns price=100000
```

For dashboards or non-critical caches, slight staleness may be tolerable. For checking balances, inventory, or payment confirmation, read from an authoritative source with appropriate consistency guarantees.

## 5. Failover: changing primaries to restore availability

**Failover** answers the question: **who takes over slot processing when the current primary becomes unavailable?**

Suppose Primary B fails while Replica B1 remains healthy:

```text
Before outage:

Primary B (slots B) ----replication----> Replica B1


After cluster confirms failure and fails over:

Primary B (offline)

Replica B1 ----------------------------> New primary (slots B)
```

In this situation:

- No key slots need recalculating.
- Slots B do not need moving to Primary A or C to preserve partitioning.
- Replica B1 is **promoted** to primary and takes over slots B.
- Clients must refresh topology awareness and connect to the new primary.

That is failover; logically the slot distribution **keeps the exact same slot groupings**, while the owning node changes.

### Is failover guaranteed to succeed?

No. Redis Cluster can only fail over automatically when cluster state, network connectivity, replica eligibility, and quorum/consensus among remaining active primaries are satisfied.

Examples:

- Primary B fails while replica B1 stays healthy and eligible: failover can succeed.
- Primary B and all of B's replicas fail: no replica exists to promote.
- Severe network partition leaves too few primaries to reach required majority: automatic failover may stall.
- Replica lagged too far or stayed disconnected too long: may be ineligible per configuration.
- Nodes have unconverged role/slot metadata: clients may hit transient errors.

**Having a replica does not guarantee failover always succeeds.** Real testing must cover failure conditions and topology health.

## 6. Comparison table of the three mechanisms

| Criterion | Sharding | Replication | Failover |
| --- | --- | --- | --- |
| Question | Where does the key live? | Where is the key's copy? | Which node replaces a failed primary? |
| Primary goal | Scale capacity/throughput | Data redundancy | Restore service availability |
| Scope | Hash slots / key groups | One primary and its replicas | One primary–replica shard |
| Effect on data | Splits keys across primaries | Duplicates shard state | Transfers role/slot ownership |
| When it occurs | Initial distribution or resharding | Continuously during operation | When a primary needs replacing |
| Increases logical dataset capacity? | Yes | No, replicas consume extra RAM | No |
| Protects when a primary dies? | Not by itself | Holds copies, does not auto-switch roles | Promotes a replica |
| Requires client topology awareness? | Yes | Depends on read path | Yes |
| Typical risks | `CROSSSLOT`, hotspots, resharding | Replication lag | Downtime, write loss, ambiguous retries |

Mental shortcut:

```text
Need capacity?       -> sharding
Need backup copies?  -> replication
Need automatic role
replacement?         -> failover

Production HA Cluster = sharding + replicas + failover
```

Do not treat these three terms as synonyms for the same mechanism.

## 7. Minimal topology vs. HA topology

### Three primaries, no replicas

```text
Master A     Master B     Master C
slots A      slots B      slots C
```

Advantage: data is sharded, pooling capacity across three primaries.

Drawback: if one primary dies, that shard has no replica to take over. Depending on cluster coverage settings and cluster state, many operations may become unavailable.

### Three primaries, one replica each

```text
Master A ----> Replica A1
Master B ----> Replica B1
Master C ----> Replica C1
```

This is the classic reference topology for an HA Redis Cluster. Place each shard's master and replica in separate failure domains (hosts, racks, availability zones) so one outage does not kill both.

### Is one primary with two replicas a three-shard Redis Cluster?

No. That is still **one shard** with two copies. In Redis Cluster automatic failover and elections, primary majority rules matter greatly. One master with replicas is not equivalent to a three-primary cluster capable of scaling and coordinating elections.

If only HA is needed without sharding, **Redis Sentinel** may fit some deployments better.

## 8. Hash slots: how Redis decides where a key goes

Redis Cluster uses 16,384 slots. Redis computes:

```text
CRC16(key) mod 16384
```

applying the hash tag rule if the key contains a valid non-empty `{}` pair.

Keys:

```text
cart:{user-42}:items
cart:{user-42}:total
```

are hashed on `user-42`, placing them in the **same slot**.

Conversely:

```text
cart:user-42:items
cart:user-42:total
```

have no shared-slot guarantee merely from sharing a prefix.

You can check:

```bash
redis-cli -c -h redis-node-a.internal -p 6379 \
  CLUSTER KEYSLOT 'cart:{user-42}:items'

redis-cli -c -h redis-node-a.internal -p 6379 \
  CLUSTER KEYSLOT 'cart:{user-42}:total'
```

Both commands should return the same slot for keys sharing a hash tag.

### What do hash tags enable?

- Running multi-key operations on keys that must share a slot.
- Running Lua scripts accessing multiple keys in the same slot.
- Keeping a related business key group on one shard for atomic Redis operations.
- Avoiding `CROSSSLOT` errors in multi-key transactions/commands.

### Risks of hash tags

Using one tag for all keys:

```text
cart:{all-users}:user-1
cart:{all-users}:user-2
cart:{all-users}:user-3
```

forces everything into one slot, causing hotspots and losing sharding benefits.

Scope tags to the **business unit needing co-location**, such as per user, small tenant, or single aggregate—never a global tag just to make multi-key commands "run".

## 9. MOVED and ASK: clients must understand topology

In Redis Cluster, a request can hit the wrong node. Redis uses redirects to point the client to the slot-owning node.

### MOVED

Example:

```text
-MOVED 9281 10.10.0.12:6379
```

Meaning: slot `9281` belongs to `10.10.0.12:6379`; the client should update its topology view and send commands there.

### ASK

During **resharding/migration**, a slot can be in transition. Redis can return `ASK` telling the client to forward the next command to the target node during migration, preceded by `ASKING` on that target connection per protocol.

### Differences

| Signal | Context | Interpretation |
| --- | --- | --- |
| `MOVED` | Slot ownership resides on another node | Redirect and refresh topology |
| `ASK` | Slot is migrating, temporary state | Temporary redirect per protocol |
| `READONLY` | Client sent a write to a replica or node no longer writable | Identify new master/connection |
| `CROSSSLOT` | Multi-key command spans multiple slots | Redesign keys/hash tags/logic |

Use a Redis Cluster-aware client like Lettuce through Spring Data Redis so the client handles redirects and topology rather than parsing `MOVED` inside every service.

**Redis Cluster is not a single proxy endpoint.** Seed nodes bootstrap cluster discovery, while the driver communicates directly with slot-owning nodes.

## 10. Resharding is not failover

Two operations frequently confused:

### Resharding: intentionally moving hash slots

Goal: balance capacity/load or add/remove primaries.

```text
Before:
  Primary A: slots 0–5460
  Primary B: slots 5461–10922

Reshard:
  Move a batch of slots from A to B

After:
  Primary A: fewer slots
  Primary B: more slots
```

Keys in the moved slots follow the migration workflow. During transition, clients may observe `ASK`/`MOVED`.

### Failover: a replica takes over a failed primary

```text
Before:
  Primary A owns slots 0–5460
  Replica A1 follows A

Failover:
  Primary A unreachable
  Replica A1 promoted

After:
  Primary A1 owns slots 0–5460
```

This does not increase shard count; Redis replaces a node within the same logical shard position.

### Comparison

| Scenario | Primary Operation |
| --- | --- |
| Adding a Redis primary to expand capacity | Reshard/rebalance slots |
| Relieving a primary overloaded by a key group | Migrate slots as appropriate |
| Master dies, replica promoted | Failover |
| Replica dies, primary healthy | Restore/replace replica; no failover needed |
| Client sees MOVED as slots migrate | Topology/resharding redirect |
| Client sees READONLY after role swap | Connection still pointing at replica/old node |

Sharding and failover can overlap in the same system, yet troubleshooting must isolate the true root cause.

## 11. Scope of Redis atomicity in a Cluster

A single Redis command runs on the node owning its key. **Multi-key operations** face slot constraints.

Example:

```redis
MGET user:1 user:2
```

If the two keys live in different slots, Redis Cluster can return:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

This is not because a replica lagged or failover occurred. It is a consequence of **sharding**.

To put related keys in the same slot:

```redis
MGET session:{user-42}:access session:{user-42}:refresh
```

Sharing a valid hash tag routes both keys to the same slot.

### Transactions and Lua scripts

In Redis Cluster, multi-key commands, transactions, and Lua scripts touching multiple keys typically require all keys to belong to the same hash slot. A Lua script cannot arbitrarily execute an atomic transaction spanning Primary A and Primary B.

Business example:

```text
Transfer:
  account:{A}:balance  -> slot X
  account:{B}:balance  -> slot Y
```

If X differs from Y, you cannot solve it by wrapping both commands in `MULTI` or a Lua script and expecting Redis Cluster to coordinate across shards.

Design paths:

- Adjust the key model so keys needing atomic updates share a slot, if load distribution remains reasonable.
- Use transactions in an authoritative database for cross-aggregate business logic.
- Use workflows/sagas with idempotency and durable state for inherently distributed transactions.
- Never collapse the entire system into one hash tag solely to dodge `CROSSSLOT`.

## 12. Configuring Spring Boot for Redis Cluster

In modern Spring Boot using `spring.data.redis.*`, basic configuration looks like:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-node-1.internal:6379
          - redis-node-2.internal:6379
          - redis-node-3.internal:6379
        max-redirects: 5
      connect-timeout: 3s
      timeout: 3s
```

Nodes listed under `cluster.nodes` are **seed nodes** for client topology discovery. They do not need to be every node in the cluster, though listing multiple reachable addresses avoids a single-seed failure during initial connection.

After discovery, the client uses slot ownership info to send commands to the right node. Never hand-roll key partitioning across seed lists with `hashCode() % 3`, as Redis Cluster already standardizes hash slots and routing.

### Spring Boot version differences

Older Spring Boot versions used the `spring.redis.*` prefix. Match configuration metadata to your deployment's version. Never mix standalone, Sentinel, and Cluster properties expecting the framework to guess your intent.

`max-redirects` limits the redirect chain per client configuration—it is **not** a business retry count or failover threshold. Application-level retries must still be managed separately.

## 13. Java configuration with RedisClusterConfiguration

When configuring Spring Data Redis explicitly:

```java
package com.example.redis;

import java.time.Duration;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisClusterConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {

        RedisClusterConfiguration cluster =
            new RedisClusterConfiguration(
                List.of(
                    "redis-node-1.internal:6379",
                    "redis-node-2.internal:6379",
                    "redis-node-3.internal:6379"
                )
            );

        cluster.setMaxRedirects(5);

        LettuceClientConfiguration client =
            LettuceClientConfiguration.builder()
                .commandTimeout(Duration.ofSeconds(3))
                .build();

        return new LettuceConnectionFactory(cluster, client);
    }
}
```

When defining `RedisConnectionFactory` yourself, the application is responsible for all required settings; do not assume Spring Boot will keep applying all auto-configured Redis properties onto that custom bean.

### Configuring authentication

If Redis nodes require ACLs or passwords, Spring Data Redis Cluster configuration accepts credentials:

```java
import org.springframework.data.redis.connection.RedisPassword;

// After creating RedisClusterConfiguration:
cluster.setUsername("app-redis-user");
cluster.setPassword(
    RedisPassword.of("PASSWORD_FROM_SECRET_CONFIGURATION")
);
```

The password above is an API placeholder. In production, inject secrets via secret manager or environment variables; never commit passwords to repositories.

Redis Cluster may also require TLS. When TLS/SSL is enabled, verify certificates, CA/truststore, hostname verification, and TLS connectivity across **all nodes returned by cluster topology**, not just the initial seed node.

### Do not use Sentinel config in place of Cluster

These two classes serve distinct architectures:

```text
RedisClusterConfiguration
  -> seed nodes + hash slots + cluster topology

RedisSentinelConfiguration
  -> master name + Sentinel discovery endpoints
```

A system with replicas and failover is **not automatically Redis Sentinel**. Redis Cluster includes built-in node-based failover without needing Sentinel to manage its shards.

## 14. Using StringRedisTemplate in a Cluster

Once the connection factory is configured for Cluster mode, application-level `StringRedisTemplate` usage stays largely unchanged:

```java
package com.example.redis;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheService {

    private final StringRedisTemplate redis;

    public ProductCacheService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void cachePrice(String productId, String price) {
        redis.opsForValue().set(
            "product:price:" + productId,
            price,
            Duration.ofMinutes(5)
        );
    }

    public String findCachedPrice(String productId) {
        return redis.opsForValue().get(
            "product:price:" + productId
        );
    }
}
```

The service supplies keys and values; the Redis Cluster-aware driver computes slots and routes commands.

Example:

```text
cachePrice("42", "120000")
  -> SET product:price:42 120000 EX 300
  -> driver finds slot for key
  -> sends to primary owning that slot
```

When slots move or a primary fails over, the client updates topology according to driver mechanics and settings.

**Do not** maintain a manual `productId -> Redis host` table inside business services. That directly conflicts with cluster resharding.

## 15. Read-from-replica configuration and stale data warnings

With Lettuce, you can select replica read policies where supported. Example:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .readFrom(ReadFrom.REPLICA_PREFERRED)
        .commandTimeout(Duration.ofSeconds(3))
        .build();
```

When configuring replica reads, keep in mind:

- Replication is asynchronous.
- Reading immediately after writing does not always return the new value.
- Failover changes replica roles and topology.
- Replica reads can suit caches/dashboards; they are generally inappropriate by default for decisions needing fresh state.

### Read-your-writes failure example

```text
T0: SET user:42:status ACTIVE on Primary B
T1: Primary B returns OK
T2: GET user:42:status on Replica B1
T3: Replica B1 has not received write yet -> returns stale status
```

For use cases needing strong freshness, read from the primary or an authoritative datastore under a validated consistency policy. Reading from the primary still does not make replication/failover a strictly durable transaction.

## 16. Asynchronous replication and write loss risk during failover

Scenario:

```text
T0   Client sends SET order:42 PAID to Primary B
T1   Primary B executes and returns OK
T2   Primary B crashes abruptly
T3   Replica B1 is promoted to new primary
T4   B1 had not yet received T1's write
T5   PAID status is missing on the new master
```

This can occur because standard replication is asynchronous.

Redis offers commands like `WAIT` to wait for acknowledgment from a number of replicas for prior writes on a connection. Yet `WAIT` **does not turn Redis Cluster into a fully synchronous transactional database** and cannot guarantee zero data loss across all crash, failover, or persistence failure scenarios.

Evaluate:

- Is Redis a cache or a source of truth?
- Can data be rebuilt from a database?
- Would losing one write carry financial impact?
- What replica lag is acceptable?
- What are RDB/AOF persistence settings and durability expectations?
- Should an authoritative transactional database or system own the canonical state?

Never attribute durability guarantees to sharding or failover that they do not provide.

## 17. How is Redis Cluster failover decided?

Redis Cluster exchanges node states and slot metadata over the cluster bus. When a primary stops responding, peers mark it in failure states, and an eligible replica can request election as the new primary.

Terms commonly seen in `CLUSTER NODES` or Redis docs:

- `PFAIL`: a node suspected unreachable from a single node's perspective.
- `FAIL`: confirmed failure state agreed upon by the cluster under required conditions.
- Eligible replica holding reasonably up-to-date data and failover authorization.
- Election requiring majority approval from primary nodes to avoid split-brain during partitions.
- Promoted replica becoming primary and taking over the old slots.

**Do not confuse Redis Sentinel quorum with Redis Cluster election.** Both provide HA, yet they are distinct coordination mechanisms.

### Why is losing majority dangerous?

Suppose a Cluster has three primaries and suffers a network partition:

```text
Partition 1: Primary A

Partition 2: Primary B + Primary C
```

The isolated side holding only Primary A cannot continue operating as a complete cluster in all situations. Majority and cluster-state rules restrict operations to prevent severe inconsistencies during splits.

Availability depends on:

- Which primaries remain connected.
- Which hash slots remain served.
- Where replicas sit across partitions.
- Cluster state and coverage configuration.
- Failover/election rules.

Never promise every key remains readable/writable merely because a few cluster nodes are still running.

## 18. Cluster slot coverage and availability when a shard fails

Redis Cluster normally requires all 16,384 slots to be assigned, and command serving depends on cluster state.

A key configuration option is `cluster-require-full-coverage`. When full coverage is required, losing service for a subset of slots causes the cluster to reject operations broadly rather than only failing keys in the missing slots.

When configured for partial coverage, operations targeting healthy slots may continue in some scenarios, yet this **does not make unowned slots available**.

Decision matrix:

| Scenario | Impact |
| --- | --- |
| One replica down, primary healthy | Shard keeps serving; reduced redundancy |
| One primary down, replica promoted | Shard recovers after the failover window |
| Primary and all replicas of a shard down | Affected slots have no node serving them |
| Majority of primary nodes lost | Failover/availability can be severely impaired |
| Slot actively resharding | Clients may receive temporary ASK/MOVED responses |

Exact behavior depends on Redis version and configuration. Never conclude "only the failed node is affected" without verifying full-coverage settings and cluster state.

## 19. Operating Redis Cluster with redis-cli

Connect in cluster-aware mode:

```bash
redis-cli -c -h redis-node-1.internal -p 6379
```

Depending on shell and environment, run inside `redis-cli`:

```redis
CLUSTER INFO
CLUSTER NODES
CLUSTER SHARDS
CLUSTER SLOTS
```

Key commands:

| Command | Purpose |
| --- | --- |
| `CLUSTER INFO` | View cluster state, assigned/ok slots, node count |
| `CLUSTER NODES` | View node IDs, roles, link states, slot ranges |
| `CLUSTER SHARDS` | Shard, primary, and replica details on supported Redis versions |
| `CLUSTER SLOTS` | Slot-to-node mapping, commonly used for client discovery |
| `CLUSTER KEYSLOT key` | View the slot of a key |
| `INFO replication` | View role and replication status on a node |
| `ROLE` | View the current node's role |

Slot inspection example:

```bash
redis-cli -h redis-node-1.internal -p 6379 \
  CLUSTER KEYSLOT 'cart:{user-42}:items'
```

The `\` in shell snippets represents Unix line continuation; in Windows PowerShell run the command on a single line without that backslash.

### Using -c

`redis-cli -c` follows cluster redirects when accessing keys on other nodes. Running `redis-cli` without cluster-aware mode can display `MOVED` responses; that does not by itself indicate Redis is broken.

Never run experimental resharding or failovers directly in production without an approved change procedure.

## 20. Distinguishing errors from sharding, replication, and failover

| Symptom | Likely Mechanism | Where to Look |
| --- | --- | --- |
| `CROSSSLOT` | Sharding / key model | Do keys share a hash slot? |
| `MOVED` | Wrong node or topology shifted | Cluster-aware client, topology refresh |
| `ASK` | Slot migration | Is resharding currently active? |
| Replica returns stale value | Replication lag | Replica read path, offset/lag |
| `READONLY` after role change | Failover / stale connection | Which node is client sending writes to? |
| `CLUSTERDOWN` | Cluster availability/coverage | `CLUSTER INFO`, slots, majority |
| Multi-second timeout when primary dies | Failover / reconnect | Role change, client timeouts, retries |
| Single hot key despite multiple nodes | Hot key/slot | Key distribution and traffic skew |
| Primary down with no replica | Missing redundancy | Replication topology |
| ACKed write lost after promotion | Async replication/durability | RPO, replication/persistence |
| Only seed node reachable | Network/topology discovery | Are advertised node addresses reachable? |

Accurate troubleshooting begins by **identifying the mechanism**. Never try to fix `CROSSSLOT` by adding replicas; never fix replication lag by resharding; never fix failover timeouts by changing key hashing.

## 21. Networking: seed nodes are not proxies

In Redis Cluster, clients may start at a seed node and subsequently connect to other nodes per topology. Redis data nodes also use the **cluster bus** to exchange internal state.

Default port layout example:

```text
Redis client port: 6379
Cluster bus port: 16379 (typically base port + 10000)
```

Depending on Redis config, the cluster bus port can be customized; never assume every deployment uses `16379`.

### Networks must support both traffic types

```text
Spring Boot ---> Redis data nodes (client ports)

Redis node A <--> Redis node B (cluster bus ports)
```

Notes:

- Clients must reach **all Redis nodes returned in topology**, not just seed nodes.
- Redis nodes must reach one another over the cluster bus.
- Advertised DNS/IPs/ports must match the client's network.
- Docker NAT or Kubernetes networking can make advertised addresses differ from client-reachable addresses.
- On failover, a promoted replica must have an endpoint reachable by the application.

A cluster can look healthy on an internal Redis network while a Spring container fails to connect because nodes advertise private addresses from another network.

## 22. Docker/Kubernetes and cluster announce addresses

Common mistake:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:6379
```

If Spring runs inside a Docker container separate from Redis, `127.0.0.1` points to **the Spring container itself**, not Redis.

In Kubernetes, seed nodes may be DNS names of appropriate pods or services:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-0.redis-headless.svc.cluster.local:6379
          - redis-1.redis-headless.svc.cluster.local:6379
          - redis-2.redis-headless.svc.cluster.local:6379
```

These names are **illustrative only**, depending on your actual Redis operator/topology.

Alongside seed nodes, Redis must announce appropriate addresses and ports so clients and cluster nodes can connect. Settings such as `cluster-announce-ip`, `cluster-announce-port`, and `cluster-announce-bus-port` may apply depending on topology.

Do not "fix" networking issues with workarounds hardcoded in Java business logic. Fix discovery/advertised endpoints and test directly from the application's namespace or container.

## 23. Node loss does not impact data equally in every case

Consider three scenarios:

### Losing a replica

```text
Primary A ----> Replica A1 (DOWN)
```

If Primary A stays healthy, reads/writes on shard A continue. However, HA degrades because no replica remains ready for failover.

### Losing a primary while a replica survives

```text
Primary B (DOWN)
Replica B1 (UP) ---> eligible for promotion
```

The cluster can recover slots B. Brief downtime, timeouts, and transient errors may occur during election and reconnection.

### Losing both primary and replicas

```text
Primary C (DOWN)
Replica C1 (DOWN)
```

No surviving copy of slots C exists in memory. Having Primary A/B alive does not allow the cluster to regenerate C's data. Depending on persistence/backups and topology, data or shard nodes must be restored.

**Sharding does not back up data; replication creates copies.**

## 24. Why doesn't adding replicas increase dataset capacity?

If Primary A holds 20 GB of data and has two replicas:

```text
Primary A     20 GB
Replica A1    20 GB (approx.)
Replica A2    20 GB (approx.)
```

Total consumed RAM triples, yet the **logical dataset of shard A remains ~20 GB**, not 60 GB of independent writable storage.

By contrast, adding Primary D and resharding slots to D:

```text
Before:
  A = 20 GB, B = 20 GB, C = 20 GB

After adding D and rebalancing:
  A = 15 GB, B = 15 GB, C = 15 GB, D = 15 GB
```

These numbers illustrate an even split. Total logical data stays 60 GB, while load and capacity per primary drop.

Adding replicas can help scale read workloads when clients enable replica reads; it does not increase a shard's write throughput, since writes still go through the primary.

## 25. Measuring per-shard load and hotspots

Sharding distributes by slot, yet uniform key distribution **does not guarantee uniform load**.

Example:

```text
Key                Requests/second
product:hot:42          80,000
product:101                20
product:102                15
...
```

Even though `product:hot:42`'s slot is hashed across 16,384 slots, every request for that key hits the single shard owning that slot.

Options depending on use case:

- Local in-memory caching for read-heavy keys if staleness is acceptable.
- Offloading selected read traffic deliberately.
- Adjusting the data model or splitting counters where consistency permits.
- Adding primaries and resharding to rebalance slot groups, noting **a single hot key still lives in one slot**.
- Shrinking payloads, batching commands, or avoiding heavy CPU operations.

Never promise "adding nodes solves every hot key". Sharding splits multiple keys across nodes; it does not split one giant hot key across multiple independent slots.

## 26. Redis Cluster and Spring Cache

Spring Cache abstraction (`@Cacheable`, `@CachePut`, `@CacheEvict`) can use Redis via `RedisCacheManager`. When `RedisConnectionFactory` is cluster-aware, the client routes cache keys to their respective slots.

Example:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final ProductRepository products;

    public ProductQueryService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductView findById(Long id) {
        return products.findViewById(id);
    }
}
```

In this example, `ProductRepository` and `ProductView` represent the application's data/domain layer; the focus is the cache annotation.

Points to distinguish:

- Redis Cluster **partitions cache entries by slot**.
- Replicas keep copies of the shard holding each cache entry.
- Failover lets a shard recover via replica promotion.
- `@Cacheable` does not automatically maintain strong consistency when the database updates.
- Cache TTLs and invalidation remain necessary.
- Bulk cache clears or pattern evictions can be affected by scan/cluster mechanics; verify how your cache writer implements them in your Spring Data Redis version.

When Redis acts strictly as a cache, applications can fall back to the database if the cluster is unavailable per business policy. Never apply that same fallback pattern to Redis locks, authoritative counters, or critical queues if doing so breaks correctness.

## 27. Pipelines, scripts, and multi-key operations

### Pipelines

Pipelining cuts round trips yet does not turn commands spanning multiple slots into a transaction. A cluster-aware driver can route/pipeline per node depending on API and implementation; verify your client version's support.

### Lua scripting

Redis scripts execute on the node holding the involved keys. Keys accessed by a script must be declared and obey slot rules.

Example:

```text
KEYS[1] = cart:{user-42}:items
KEYS[2] = cart:{user-42}:total
```

Both belong to the same slot. The script can execute a critical section on the node owning that slot.

Conversely:

```text
KEYS[1] = cart:{user-42}:items
KEYS[2] = stock:{sku-99}
```

likely map to two different slots and cannot be assumed cross-shard atomic.

### Transactions

`MULTI/EXEC` executes compatible operations on a single node/slot within Redis Cluster constraints. It does not create a distributed transaction coordinator spanning multiple primary shards.

For monetary or order workflows requiring updates across keys in multiple slots, rely on an authoritative transactional datastore and design consistency/idempotency from the ground up.

## 28. Failover and writes with uncertain execution status

A critical failure case:

```text
App -> Primary B: INCR billing:count
Redis increments counter
Network drops before app receives reply
Replica is promoted
App receives timeout
```

The application does not know whether the command ran. Retrying unconditionally risks incrementing twice; skipping retry risks missing an update. If asynchronous replication lost the write during failover, post-promotion state becomes even trickier.

Retry classification:

| Command | Is Simple Retry Safe? |
| --- | --- |
| `GET key` | Usually retryable, though result may reflect newer mutations |
| `SET key fixedValue` | Usually idempotent absent conditions or side effects |
| `INCR key` | Unsafe to retry blindly |
| `LPUSH list value` | Can insert duplicate entries |
| `SET key token NX PX ...` | Requires checking lock ownership and TTL |
| Lua reservation | Requires an idempotency ID and processed-state check |

**Failover does not provide exactly-once execution.** Use stable business IDs and deduplication when side effects matter.

## 29. Recovery and resharding impact on user experience

Consider an e-commerce system:

```text
Product Cache      -> Redis Cluster
Shopping Cart      -> Redis Cluster
Payment State      -> Database source of truth
```

When Primary B fails over:

- Cached keys in slots B may be temporarily unreadable.
- Carts in slots B may hit brief errors absent graceful fallbacks.
- Payment state remains authoritative in the database.
- Once the replica promotes, clients must discover the new topology.

During resharding:

- Keys in migrated slots move to another node.
- Cluster-aware clients handle `MOVED`/`ASK`.
- Operations may see brief latency spikes.
- Monitor network, CPU, and memory during data migration.

Both scenarios can shift latency, yet their causes and remedies differ. Never jump to "Redis failed over" solely because you spot `MOVED` in logs.

## 30. Configuring Lettuce topology refresh

Lettuce manages cluster topology. In deployments with node churn or resharding, applications must discover and refresh slot mappings.

Typical configuration considerations:

- Refresh topology upon receiving redirects.
- Periodic topology refresh where appropriate.
- Connection reconnects and adaptive topology refresh.
- DNS/advertised endpoints.
- Command timeouts and redirect limits.

Lettuce API-level example (conceptual illustration; integration into Spring Data Redis depends on version):

```java
import io.lettuce.core.cluster.ClusterClientOptions;
import io.lettuce.core.cluster.ClusterTopologyRefreshOptions;
import java.time.Duration;

ClusterTopologyRefreshOptions refresh =
    ClusterTopologyRefreshOptions.builder()
        .enablePeriodicRefresh(Duration.ofSeconds(30))
        .enableAllAdaptiveRefreshTriggers()
        .build();

ClusterClientOptions options =
    ClusterClientOptions.builder()
        .topologyRefreshOptions(refresh)
        .build();
```

This snippet merely builds Lettuce options; it **does not automatically attach** them to `LettuceConnectionFactory`. To apply them, build a client configuration or client resources per your Spring Data Redis version's API and wire `options` in appropriately.

Refreshing too frequently increases topology query overhead; refreshing too slowly leaves clients holding stale routes longer. Measure overhead and behavior during failover/resharding drills.

## 31. Smoke test example in Spring Boot

Suppose the application already has a `StringRedisTemplate` configured by Spring Boot for Redis Cluster.

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class RedisClusterSmokeTest {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void canReadAndWriteThroughClusterClient() {
        String key = "test:cluster:smoke";

        redis.opsForValue().set(key, "connected");

        assertThat(redis.opsForValue().get(key))
            .isEqualTo("connected");

        redis.delete(key);
    }
}
```

This test verifies one key routes successfully at test time. It **does not prove**:

- Multiple real primaries exist.
- Replication is keeping up.
- Automatic failover works.
- Keys on other shards are reachable.
- Same-slot multi-key commands work.
- No data is lost after promotion.

To verify cluster topology and failover, run integration tests against multiple real Redis nodes in an isolated environment. Never run node-killing fault tests in production.

## 32. Integration test scenarios for all three mechanisms

### Scenario A — Proving sharding

1. Set up a cluster with three primaries.
2. Compute slots of several keys using `CLUSTER KEYSLOT`.
3. Inspect `CLUSTER SHARDS`/`CLUSTER NODES`.
4. Verify keys in different slots route to their respective primaries.
5. Test a multi-key operation across different slots to observe `CROSSSLOT`.
6. Test two keys sharing a hash tag to demonstrate same-slot placement.

### Scenario B — Proving replication

1. Write a key to the primary owning its slot.
2. Inspect `INFO replication` on both primary and replica.
3. Verify the replica follows the primary and its replication link status.
4. Exercise a supported replica read path in test and compare values.
5. Introduce controlled write load to observe potential replication lag.

### Scenario C — Proving failover

1. Verify a three-primary topology, each with a replica.
2. Write test keys to the target shard.
3. Trigger a controlled failover or stop the primary in the test environment.
4. Watch the replica promote to primary and assume slot ownership.
5. Check application reconnects, post-failover writes, and transient errors.
6. Verify retry rules on non-idempotent writes.

A command usable **on a replica in a test environment** to request a coordinated failover:

```redis
CLUSTER FAILOVER
```

This command is not meant to be run casually in production and has specific eligibility rules. Real power-loss or network-cut tests must be designed differently from coordinated failovers to observe realistic failure behavior.

### Scenario D — Testing resharding

1. Add a new primary.
2. Migrate a subset of slots in the test environment.
3. Observe slot map updates and `MOVED`/`ASK` redirects.
4. Confirm keys remain readable once migration completes.
5. Record latency/CPU/network during migration.

Report results for A/B/C/D distinctly rather than bundling them under a vague "Redis Cluster works" label.

## 33. Production checklist per mechanism

### Sharding

- All slots assigned according to operational strategy.
- No severe hotspots on single keys or slots.
- Hash tags used only where co-location is genuinely needed.
- Every multi-key command/script obeys slot constraints.
- Advertised node addresses are reachable.
- Resharding is planned and monitored.

### Replication

- Every critical primary has a replica in an independent failure domain.
- Replication links and lag are monitored.
- Redis persistence/backups meet required RPO.
- Replica reads are enabled deliberately with a stale-data policy.
- Replicas are never mistaken for extra logical dataset capacity.

### Failover

- Cluster has enough primaries and replicas for HA goals.
- Election and cluster bus networking are properly configured.
- Failover has been rehearsed in an isolated environment.
- Application configures timeouts, reconnects, and topology refresh.
- Non-idempotent operations follow strict retry policies.
- Alerts exist for role changes, unavailable slots, and cluster state.

### Spring Data Redis

- Use `RedisClusterConfiguration` or `spring.data.redis.cluster.*`.
- Driver supports Redis Cluster (e.g., Lettuce) at a compatible version.
- Never route `key-to-host` manually inside services.
- Never confuse Sentinel configuration with Cluster.
- Serializers/key naming stay consistent across services.
- Cache fallbacks fit Redis's actual role.
- Metrics exist per shard, node, and application error code.

## 34. Common misconceptions

### "Three Redis nodes means data is copied three times"

No. If all three are primaries, data is sharded into three distinct partitions. Copies require replicas per shard.

### "Adding a replica doubles dataset capacity"

No. Replicas hold copies of shard data, consuming RAM without expanding logical dataset capacity.

### "Failover means redistributing hash slots"

No. Failover promotes a replica to take over its failed primary's existing slots. Resharding intentionally moves slot ownership to rebalance data/load.

### "Sharding lets one hot key run across multiple primaries"

No. One key maps to one slot. All commands on that key hit the shard owning that slot.

### "MOVED means data was lost"

No. MOVED is a cluster redirect pointing to the node owning the slot. A cluster-aware client updates routing.

### "ASK and MOVED are identical"

No. ASK relates to temporary slot migration redirects; MOVED indicates changed slot ownership.

### "Replication is synchronous, so an OK write can never be lost"

No. Standard Redis replication is asynchronous. Even ACKed writes risk not reaching a promoted replica before failure.

### "Cluster automatically runs multi-slot transactions"

No. Multi-key operations obey slot limits. Redesign the key model or move transactions outside Redis.

### "Adding replicas makes the primary process writes faster"

Not directly. Writes still execute on the primary; replication even consumes network/CPU. Selected read workloads can shift to replicas if stale reads are acceptable.

### "Clients only need to reach the seed node"

No. After discovery, clients must reach all Redis nodes owning hash slots as well as promoted/newly added nodes.

### "Cluster failover has zero downtime"

No. Failure detection, election, promotion, topology refresh, and reconnecting all take time; brief errors and timeouts can occur.

### "READONLY after failover is a serializer error"

No. It typically signals writes hitting a replica or demoted node; inspect connection routing and topology.

### "Using Redis Cluster completely replaces backups"

No. Sharding, replication, and failover do not eliminate the need for persistence, backups, recovery drills, and RPO/RTO planning.

## 35. Design exercises

### Exercise A — Tracing where data lives

You have three primaries, each with one replica. Determine:

- Which primary holds a key based on its slot?
- Which replica holds a copy of that key?
- When the primary fails, which node can take over?
- What differs between moving slots to a new primary vs. promoting a replica?

### Exercise B — Fixing CROSSSLOT

Keys:

```text
cart:user-42:items
cart:user-42:total
```

The application wants to update both via Lua. Change the key naming to guarantee the same slot, then explain the risk if all users are collapsed into a single hash tag.

### Exercise C — Replication lag

The application writes `available=5` to the primary and immediately reads a replica seeing `available=6`. Explain why this happens, its impact on sales decisions, and how to pick the proper read path.

### Exercise D — Failover

Primary B dies; Replica B1 is promoted. Explain why slots B continue to be served by that shard despite the primary node changing, and why clients must refresh topology.

### Exercise E — Resharding

Primary D is added to increase capacity. Describe what happens to hash slots, key migration, `MOVED`/`ASK`, and application latency. Explain why this is not failover.

### Exercise F — Retrying on lost reply

An `INCR` may have executed before the connection dropped. Design an idempotency key and verification check to prevent uncontrolled duplicate business increments.

## 36. Frequently asked questions

**How many primaries does Redis Cluster need?**

A common HA setup uses at least three primaries with replicas, though exact topology depends on fault tolerance, data size, failure domains, and operational needs. Do not assume every small system requires the exact same node count.

**Does a single replica hold the entire cluster dataset?**

No. A replica typically replicates only the primary it follows, corresponding to one shard of the cluster.

**Does adding a replica require resharding?**

Not by default. A new replica copies an existing shard without receiving independent hash slots. Resharding mainly shifts slot allocations among primaries.

**Does failover change a key's hash slot?**

Normally no. The key keeps the same CRC16 slot; the node owning that slot changes when a replica promotes.

**Can multiple keys be used in Lua on Redis Cluster?**

Yes, provided the Redis keys accessed by the script share a hash slot and comply with Cluster rules. Never assume scripts are atomic across shards.

**Why does a GET right after SET see an old value?**

If reading from a replica while replication lags, stale reads can happen. Also check other cache layers, TTLs, and data source consistency.

**Does Redis Cluster need Sentinel?**

No. Redis Cluster has its own topology management and failover protocol. Sentinel fits non-sharded primary–replica deployments.

**Can I configure just one seed node?**

Technically a client can bootstrap from one reachable seed, yet to avoid single-point-of-failure at startup, configure multiple seed nodes and ensure all advertised data nodes are reachable.

**Is MOVED an application bug?**

Not necessarily. MOVED is a Redis Cluster protocol redirect. Cluster-aware clients handle it; if MOVED surfaces to service code, check client configuration and topology refresh.

**Does failover guarantee zero data loss?**

No. Standard Redis replication is asynchronous, meaning ACKed writes may not yet have reached the promoted replica.

**Why does one node failing break the whole API on Redis Cluster?**

Possible causes include full-coverage rules, lost majority, a shard lacking replicas, network topology, or app dependencies on keys in unavailable slots. Inspect cluster state and exact error codes.

## 37. Summary

- **Sharding** partitions keys across **16,384 hash slots** over multiple primaries to scale capacity and throughput.
- **Replication** creates copies per primary/shard, typically **asynchronously**, introducing replication lag and write-loss risk during failover.
- **Failover** promotes an eligible replica to replace a failed primary and inherit its slots; it is not resharding.
- **Resharding** transfers slot ownership across primaries to rebalance data; clients must handle `MOVED`/`ASK`.
- **Redis Cluster does not make multi-key operations atomic across shards.** Hash tags co-locate keys when needed, yet risk hotspots.
- **Spring Data Redis** uses `RedisClusterConfiguration`/Lettuce or `spring.data.redis.cluster.*`; client discovery/routing depends on seed nodes and reachable advertised endpoints.
- **Replica reads can be stale**, failover can cause timeouts, and non-idempotent retries require careful design.
- **HA is neither backup nor absolute durability.** Monitor roles, slots, replication lag, and failovers, and test recovery in isolated environments.

Clearly separating sharding, replication, and failover helps design Redis Cluster intentionally: knowing to **add shards** for capacity/throughput, **add replicas** for redundancy, and **test failover/topology** for outage recovery without conflating the mechanisms.

## Official references

- [Redis – Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis – Redis Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis – CLUSTER SLOTS](https://redis.io/docs/latest/commands/cluster-slots/)
- [Redis – CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/)
- [Redis – CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/)
- [Redis – Redis Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis – WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis – CLUSTER FAILOVER](https://redis.io/docs/latest/commands/cluster-failover/)
- [Spring Data Redis – Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis – Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html)
- [Spring Data Redis – RedisClusterConfiguration API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/RedisClusterConfiguration.html)
- [Spring Data Redis – LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html)
