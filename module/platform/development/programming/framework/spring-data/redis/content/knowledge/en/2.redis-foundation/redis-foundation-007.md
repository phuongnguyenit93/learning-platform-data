# Distinguishing Standalone Redis, Replication, Sentinel, and Cluster

When adopting Redis in a Spring Data Redis application, the four terms **standalone**, **replication**, **Sentinel**, and **Cluster** are often treated as four equivalent deployment tiers. In reality, they solve different problems:

- **Standalone Redis**: a single Redis server holds all data and serves both reads and writes.
- **Replication**: copies data from a primary node to replicas, primarily for redundancy and read scaling.
- **Redis Sentinel**: monitors a primary–replica group, detects failures, and coordinates automatic primary failover.
- **Redis Cluster**: shards keys across multiple primaries to scale capacity and throughput; each primary can have replicas for automatic failover.

Key point: **replication is a data-copying mechanism, Sentinel is a high-availability management mechanism, and Cluster adds data sharding**. A Sentinel setup uses replication; a Cluster setup normally uses replication as well. These terms are not four mutually exclusive “upgrade” levels.

## 1. Big-Picture Comparison

| Criterion | Standalone | Plain Replication | Sentinel + Replication | Redis Cluster |
|---|---|---|---|---|
| Data distribution | One server holds all keys | Primary and replicas hold copies of the same keyset | Primary and replicas hold copies of the same keyset | Multiple primaries hold **different subsets of keys** |
| Write endpoint | One server | Primary | Primary recognized by Sentinel | Primary owning the key's hash slot |
| Write scaling | Limited by one node | Still limited by one primary | Still limited by one primary | Writes scale across multiple primaries |
| Read scaling | Limited by one node | Can read from replicas | Can read from replicas when client is configured | Can read from primary/replicas per client config |
| Automatic primary failover | No | No | Yes, given quorum and eligible replica | Yes, given replica and majority of primaries reachable |
| Discovering new primary address | Not needed | Handled externally by app/ops config | Client queries Sentinel | Client understands slot map and Redis Cluster redirects |
| Coordination component | None | None | Separate Sentinel processes | Redis nodes exchange Cluster state directly |
| Best suited for | Development, testing, small workloads | Read offload or backup copies | HA for datasets that do not need sharding | Sharding and HA across multiple primaries |

**High availability (HA)** means the system can restore service after a node failure with minimal intervention; it **does not mean zero data loss**. Redis replicates **asynchronously** by default, so recent writes can be lost if a primary fails before replicas receive them.

## 2. Standalone Redis

~~~text
Spring Boot / Spring Data Redis
             |
             v
       Redis :6379
       [all keys]
~~~

A single Redis process receives every command and holds the entire keyspace, such as `user:1`, `product:27`, and `cart:5`. The application only needs one host/port address.

Example:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 PING
# PONG

redis-cli -h 127.0.0.1 -p 6379 SET user:1 "An"
redis-cli -h 127.0.0.1 -p 6379 GET user:1
~~~

**Strengths:** simple, lightweight on resources, easy to operate and debug. **Limitations:** a single node is a single point of failure; upgrading or restarting that node interrupts service. Memory capacity and write throughput are bounded by one machine.

You can enable RDB or AOF so Redis recovers data after a restart. However, **persistence does not create replicas, does not restore availability while the node is down, and does not replace a backup strategy**.

## 3. Replication: One Primary, Multiple Replicas

~~~text
                      writes
Application ----------------------> Primary
                                       |
                            asynchronous replication
                              /                \
                             v                  v
                         Replica A          Replica B
                      (optional reads)   (optional reads)
~~~

All data managed by the primary is streamed to replicas. Redis uses **primary/replica** terminology; older docs and config keys sometimes say **master/slave**. By default, replicas are read-only and reject direct writes.

### How Does Replication Work?

1. A replica connects to the primary via `replicaof`.
2. On initial sync or when incremental sync is impossible, the replica receives a base dataset transfer followed by ongoing changes from the primary.
3. While connected, mutating commands are streamed from the primary to replicas.
4. After a brief disconnect, **PSYNC** can resynchronize missing offsets if the replication backlog and history still match; otherwise a full resync is triggered.

Example configuration on a replica host:

~~~conf
# replica's redis.conf
replicaof 10.0.0.11 6379
replica-read-only yes
~~~

Or configured at runtime:

~~~bash
redis-cli -h 10.0.0.12 -p 6379 REPLICAOF 10.0.0.11 6379

# Inspect role, primary, and replica status
redis-cli -h 10.0.0.11 -p 6379 INFO replication
redis-cli -h 10.0.0.12 -p 6379 INFO replication
~~~

Replicas can serve read queries and offload the primary, yet read results **may lag behind recent writes** due to replication delay. If a request writes to the primary and immediately reads from a replica, the application might not see the new value yet. Flows requiring *read-after-write consistency* should read from the primary.

### When the Primary Fails

Plain replication **does not automatically elect a new primary**. An operator or external tool must decide which replica to promote, fence off the old primary from accepting writes, and repoint the application to the new address. For instance, after isolating the old primary:

~~~bash
# Illustrative manual failover step only
redis-cli -h 10.0.0.12 -p 6379 REPLICAOF NO ONE
~~~

Promoting a replica while the old primary still accepts writes can cause two primaries accepting diverging changes (**split brain**). Due to asynchronous replication, the promoted replica may also lack the final writes acknowledged by the old primary.

**When to choose plain replication:** you need replicas for backups/reads or an external orchestrator already handles primary promotion. If automatic failover is the goal, look at Sentinel or Cluster.

## 4. Sentinel: Automated Monitoring and Primary Failover

Sentinel **does not store application data and does not proxy GET/SET commands**. Sentinels are monitoring processes that exchange health assessments, promote a replica to primary, and expose the current primary address to clients via service discovery.

~~~text
                    Spring Data Redis
                        |
             ask Sentinel: where is primary?
                        |
          +-------------+-------------+
          |             |             |
      Sentinel 1    Sentinel 2    Sentinel 3
          \             |             /
           \     monitor and vote    /
            \           |           /
                        v
                    Primary A
                   /         \
                Replica B   Replica C

If A fails and failover conditions are met:
B (or C) becomes primary; Sentinel updates discovery info.
~~~

In this diagram, Sentinel processes should run in sufficiently independent failure domains so a single machine outage does not prevent a quorum decision. Deploying **3 Sentinels** with **quorum 2** is a common setup. Replicas and Sentinels can share hosts in appropriate environments, provided you account for losing multiple processes on a single host outage.

### Failover Steps

1. One Sentinel stops receiving timely responses from the primary and marks it **SDOWN** (*subjectively down*: that Sentinel suspects failure).
2. When enough Sentinels agree, the primary is marked **ODOWN** (*objectively down*). The agreement threshold is the configured **quorum** for that primary group.
3. Sentinels elect one Sentinel as leader to coordinate failover. Authorizing failover also requires a **majority of total known Sentinels**; reaching ODOWN quorum alone is not enough to execute failover.
4. The coordinating Sentinel selects an eligible replica, promotes it to primary, and reconfigures remaining replicas to follow the new primary.
5. Sentinel-aware clients discover the new primary address and reconnect.

Minimal `sentinel.conf` example for one Sentinel:

~~~conf
port 26379
sentinel monitor mymaster 10.0.0.11 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 60000
~~~

Here `mymaster` is the **logical name** of the primary group, `10.0.0.11:6379` is the initial primary address, and `2` is the quorum to confirm ODOWN. Three Sentinels are configured to watch the same group; timeout values are illustrative and should be tuned to real infrastructure.

You can query Sentinel state directly:

~~~bash
redis-cli -h sentinel-1 -p 26379 SENTINEL get-master-addr-by-name mymaster
redis-cli -h sentinel-1 -p 26379 SENTINEL replicas mymaster
redis-cli -h sentinel-1 -p 26379 SENTINEL CKQUORUM mymaster
~~~

### What Sentinel Solves—and What It Does Not

- **Does:** detect primary failure, promote a replica, let clients discover the current primary.
- **Does not:** split keys across multiple primaries to increase total memory or write capacity.
- **Does not guarantee:** zero lost writes before failure. The primary may acknowledge a write before replicas receive it.
- **Does not guarantee:** zero client errors during failover. Open connections may fail, time out, or require retries.

Sentinel is usually a good fit when a single primary has enough capacity and throughput, yet the application needs automated node recovery.

## 5. Redis Cluster: Sharding and Distributed Failover

Redis Cluster partitions data into **16,384 hash slots**, numbered `0` through `16383`. Each key maps to a slot by the core rule:

~~~text
slot = CRC16(key) mod 16384
~~~

Redis Cluster hashes only the **hash tag** inside valid curly braces if the key contains one (see below). Slots are distributed across multiple primaries; each primary holds a portion of the dataset. Replicas copy data from **their assigned primary**, not the entire Cluster.

~~~text
                    Cluster-aware client
                         /    |     \
                        v     v      v
                   Primary A  B       C
                    slots    slots   slots
                    0..5460  5461.. 10923..
                             10922   16383
                       |      |       |
                       v      v       v
                    Replica  Replica  Replica
                       A1      B1      C1
~~~

The slot ranges above illustrate a three-primary layout. When nodes are added or removed, Redis can **migrate slots and keys across primaries**; the total slot count stays 16,384.

### How Clients Find the Right Primary

1. A Cluster-aware client knows one or more seed node addresses.
2. The client fetches slot mappings and sends commands to the primary owning each key's slot.
3. When slot ownership has changed, Redis may reply **MOVED** pointing to the current slot owner.
4. During slot migration, Redis may reply **ASK** to temporarily redirect the command to the target node; the client handles it per protocol.
5. The client refreshes its slot map and continues routing.

Therefore, pointing a standalone-only client at Redis Cluster causes redirect errors or unexpected failures. Spring Data Redis needs a **Cluster-aware** driver and configuration—for example, Lettuce with `spring.data.redis.cluster.nodes`.

### Hash Slots and Multi-Key Operation Limits

Suppose there are two keys:

~~~text
cart:{user42}:items
cart:{user42}:total
~~~

Both use hash tag `{user42}`, so they always map to **the same slot**. This helps commands or Lua scripts that operate on multiple keys on a single node.

Conversely:

~~~bash
# Multi-key commands across different slots are rejected by Redis Cluster
MGET user:1 user:2
# (error) CROSSSLOT Keys in request don't hash to the same slot
~~~

This is how multi-key commands behave **directly on Redis Cluster**. Some library APIs split operations across multiple nodes behind the scenes, but do not assume that splitting preserves atomicity. For transactions, scripts, or multi-key operations requiring atomicity, place keys in the same slot and verify API limitations.

Do not use **the same hash tag for every key**: doing so funnels all data and traffic into one slot, defeating Cluster load distribution.

### Cluster Setup Example

Minimal configuration per Redis node:

~~~conf
port 6379
cluster-enabled yes
cluster-config-file nodes.conf
cluster-node-timeout 5000
~~~

After starting **6 standalone-configured cluster nodes**, the command below creates a Cluster with 3 primaries and one replica per primary:

~~~bash
redis-cli --cluster create \
  10.0.0.11:6379 10.0.0.12:6379 10.0.0.13:6379 \
  10.0.0.14:6379 10.0.0.15:6379 10.0.0.16:6379 \
  --cluster-replicas 1
~~~

Test Cluster-redirect access and inspect status:

~~~bash
redis-cli -c -h 10.0.0.11 -p 6379 SET product:42 active
redis-cli -c -h 10.0.0.11 -p 6379 GET product:42

redis-cli -h 10.0.0.11 -p 6379 CLUSTER INFO
redis-cli -h 10.0.0.11 -p 6379 CLUSTER SHARDS
redis-cli --cluster check 10.0.0.11:6379
~~~

This is an illustrative setup. Production deployments must also address authentication, TLS, persistence, host/failure-zone placement, announced node addresses, and cluster-bus networking between nodes. Every address announced by the Cluster must be reachable from the application; otherwise clients fail after receiving `MOVED` or reading the slot map.

### When a Cluster Primary Fails

A replica of that primary can be elected to replace it if eligible and a majority of Cluster primaries remain reachable to authorize failover. Affected slots experience brief disruption during transition. If a slot loses its primary without an eligible replica, keys in that slot become unavailable; depending on slot-coverage settings, the impact can be broader.

Cluster provides sharding and failover, **without turning asynchronous replication into synchronous durable writes or guaranteeing zero data loss**. Cluster fits when a single primary no longer suffices for RAM, write traffic, or load distribution and the application accepts slot-based partitioning rules.

## 6. Corresponding Configuration in Spring Data Redis

The examples below illustrate **Spring Boot 3.x** conventions with Spring Data Redis and Lettuce. Each block is **an independent option**; do not merge all three blocks into one application. Hostnames are examples; replace them with real addresses.

### 6.1. Standalone or Replication Connecting Only to a Fixed Primary

~~~yaml
spring:
  data:
    redis:
      host: redis-primary.internal
      port: 6379
      timeout: 2s
~~~

With plain replication, this still points to one specific primary. If the primary changes after a manual failover, the application needs updated configuration or external service discovery to learn the new address.

### 6.2. Sentinel

~~~yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.internal:26379
          - sentinel-2.internal:26379
          - sentinel-3.internal:26379
      timeout: 2s
~~~

`master` is **the Redis group name in Sentinel**, not a hostname. The client contacts the Sentinels to locate the active primary. Configure proper authentication for Redis data nodes and, if protected separately, for Sentinels; Sentinel credentials can differ from Redis node credentials.

### 6.3. Redis Cluster

~~~yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-1.internal:6379
          - redis-2.internal:6379
          - redis-3.internal:6379
      timeout: 2s
~~~

The `nodes` list provides **seed nodes** for Cluster discovery and does not need to list every node. The client fetches slot assignments and updates routing when Cluster topology changes. Seed nodes must be reachable, and all Cluster-announced node addresses must also be reachable from the app.

### 6.4. Does Spring Data Redis Application Code Differ?

For **single-key** operations, developers generally use the exact same API regardless of topology:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class VisitCounter {
    private final StringRedisTemplate redis;

    public VisitCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(String userId) {
        return redis.opsForValue().increment("visits:" + userId);
    }
}
~~~

When topology changes, differences live mostly in **`RedisConnectionFactory`, the driver, and node discovery config**. Still, topology choice affects application behavior:

- **Reading from replicas:** never assume reads go to replicas by default. To offload reads, configure an appropriate Lettuce read preference and accept potentially stale data.
- **Retries and timeouts:** during failover, commands can time out or connections can drop. Retries must match command semantics; for non-idempotent writes, you cannot deduce automatically whether the prior write failed or succeeded.
- **Multi-key commands:** in Cluster, account for slots, transactions, Lua scripts, and APIs that split across nodes.
- **Cache/TTL:** single-key commands keep working normally, but evaluate behavior across failover, slot changes, and replica lag.
- **Security:** configure auth, ACLs, and TLS to match infrastructure; minimal YAML examples do not represent production security settings.

If you create `LettuceConnectionFactory` programmatically in Java instead of relying on Spring Boot auto-configuration, select the right configuration class: `RedisStandaloneConfiguration`, `RedisSentinelConfiguration`, or `RedisClusterConfiguration`. Changing only the host list while keeping the wrong configuration type is not enough.

## 7. Comparing Four Primary-Failure Scenarios

| Scenario | What Happens in Redis? | What Must the Application Do? |
|---|---|---|
| Standalone: Redis server stops | No other server serves the data | Wait for repair/restart, or switch to manual recovery |
| Replication: primary stops, replica stays up | Replica still has a copy, but does not promote itself | Fence old primary, promote replica, update write endpoint; inspect unsynced writes |
| Sentinel: primary stops | If quorum/majority and eligible replica exist, Sentinel promotes a new primary | Sentinel client rediscovers primary, handles transient connection errors |
| Cluster: primary for a slot group stops | If eligible replica exists and failover conditions pass, replica takes over those slots | Cluster client refreshes slot map/redirects, handles brief disruption |

Distinguish two metrics when evaluating options:

- **RTO (Recovery Time Objective):** acceptable outage duration before service resumes. Sentinel and Cluster automate recovery, though no single fixed recovery time is guaranteed across all infrastructures.
- **RPO (Recovery Point Objective):** acceptable amount of recent data loss. Because replication is asynchronous by default, both Sentinel and Cluster carry a window of potential write loss during failover.

The `WAIT` command can ask a primary to wait until a specified number of replicas acknowledge writes, narrowing the data-loss window in some cases. However, **`WAIT` does not turn Redis into a strongly durable consensus store**; you must still evaluate persistence, failover behavior, and application consistency requirements.

## 8. Which Model Should Your Project Choose?

**Case A — learning Redis or small apps tolerant of downtime:** start with standalone. It is also the simplest setup for local development and testing.

**Case B — data fits on one primary, but extra read capacity or copies are needed:** use replication. Explicitly account for stale replica reads and manual primary promotion on failure.

**Case C — data fits on one primary and automated recovery is required:** use replication + Sentinel. Place enough Sentinels across independent failure domains, verify quorum, and use Sentinel-aware Spring Data Redis connections.

**Case D — dataset size or write throughput exceeds one primary:** use Redis Cluster. Design keys around slots, provision replicas for every primary, configure a Cluster-aware client, and evaluate fault tolerance per slot group.

### Misconceptions to Avoid

1. **“Having a replica means automatic failover.”** False: plain replication copies data; it does not coordinate primary election.
2. **“Sentinel distributes data across nodes.”** False: Sentinel manages a primary–replica topology for a single dataset, not sharding.
3. **“Cluster always has replicas.”** False: Cluster can run multiple primaries with zero replicas; in that case no node can take over a lost primary automatically.
4. **“Sentinel/Cluster never lose writes.”** False: asynchronous replication still leaves a data-loss window.
5. **“Spring Data Redis auto-detects every topology from host/port.”** False: standalone, Sentinel, and Cluster require matching connection configuration.
6. **“Multi-key commands in Cluster work just like standalone.”** False: hash-slot constraints and atomicity boundaries must be designed in.
7. **“Enabling AOF/RDB gives HA.”** False: persistence recovers a node's data; HA requires multi-node topology and failover orchestration.

## 9. Remember with a Decision Tree

~~~text
Can a single Redis primary hold all RAM and handle write load?
 |
 +-- Yes --> Need automatic failover?
 |            |
 |            +-- No  --> Standalone (or plain replication if copies/reads needed)
 |            |
 |            +-- Yes --> Replication + Sentinel
 |
 +-- No  --> Redis Cluster with multiple primaries
               |
               +-- Need node fault tolerance --> Provision replicas for primaries
~~~

In Spring Data Redis applications, remember the three corresponding discovery configurations: **`host/port` for standalone**, **`sentinel.master/nodes` for Sentinel**, and **`cluster.nodes` for Cluster**. Choose topology based on scalability, acceptable downtime, and data-loss tolerance; then configure clients, monitoring, and error handling accordingly.
