# Coordinating Persistence with Replication and Failover in Spring Data Redis

## 1. Objective: having replicas and automatic failover does not guarantee durable data

Suppose a Spring Boot application writes a critical request to Redis:

```text
T0  Spring Boot -> Redis primary: SET reservation:42 CONFIRMED
T1  Redis primary returns OK
T2  Redis primary fails
T3  A replica is promoted to new primary
T4  Spring Boot GET reservation:42 -> key is missing
```

Why can this happen even when replication and failover are enabled? Because Redis replication is normally **asynchronous**: the primary can respond `OK` before the chosen replica receives the write. If the primary dies or becomes unrecoverable inside that window, the new master may lack the newly written data.

Adding persistence (RDB or AOF) to nodes improves data recovery **from each node's disk**, but does not automatically turn replication synchronous, force failover to pick a node holding every acknowledged write, or guarantee zero data loss in every scenario.

Three axes must be designed together:

1. **Persistence:** how can a single Redis process recover its data after a restart or crash?
2. **Replication:** how far has data from the primary propagated to replicas?
3. **Failover:** when the primary is lost, which node replaces it, and what state does that node hold?

In Spring Data Redis, there is a fourth axis: **client behavior**. The client must rediscover the primary, handle connection errors, and retry without creating duplicate side effects.

> **Principle:** Persistence protects local copies; replication creates copies on other nodes; failover shifts serving responsibility. End-to-end data durability depends on all three alongside application policies, filesystems, networking, and incident recovery.

## 2. Overall architecture

A Redis master–replicas deployment with Sentinel:

```text
                            Spring Boot
                           RedisTemplate
                                |
                          Redis client
                                |
                     +----------+----------+
                     |                     |
                     v                     v
              Sentinel quorum       Redis primary A
              (discovery/HA)          |
                                      | SET key=value
                                      | -> OK may arrive before
                                      |    replica receives write
                                      |
                          +-----------+-----------+
                          |                       |
                          v                       v
                    Replica B                Replica C
                          |                       |
                      local RDB/AOF            local RDB/AOF
                          |
                 failover may promote
                          v
                    New primary B
```

Here:

- Sentinel helps determine which node is the new master.
- The Redis primary and each replica have **separate persistence configurations**.
- Replication propagates changes between nodes through its own mechanism.
- Node A's RDB/AOF files are **not** a shared disk that Node B immediately uses when promoted.
- Once failover completes, the application must write to the newly promoted node rather than continuing to send writes to the old node.

Redis Cluster also provides replication and failover, organized by **shard/hash slot**, without using Sentinel to coordinate failover for cluster shards.

## 3. Distinguishing durability, availability, consistency, and recovery

Four terms that are frequently conflated:

| Property | Question | Related mechanisms |
| --- | --- | --- |
| Durability | Do written changes survive a crash? | RDB, AOF, fsync, storage, backups |
| Availability | When one node fails, can the service keep operating? | Replication, Sentinel/Cluster failover |
| Consistency | When do different clients observe the same state? | Replication lag, primary/replica reads, versioning |
| Recoverability | When multiple nodes fail or data is deleted erroneously, where do we restore from? | Backups, PITR if supported, restore runbooks |

Examples:

- A Redis server with strong AOF but **no replicas**: can restart with saved data, yet may suffer long downtime if the host dies.
- A primary with two replicas but **persistence completely off**: holds multiple copies in RAM and achieves HA when one node fails, yet simultaneous loss or improper restart ordering can wipe the dataset.
- A Redis Cluster with multiple shards and replicas: provides sharding and failover, yet still carries write-loss risk due to asynchronous replication.
- A transactional database storing canonical records while Redis acts solely as a cache: Redis data loss causes cache misses, not necessarily business state loss.

Before tuning `appendfsync` or replica counts, know whether **Redis is a rebuildable cache or an authoritative data source**.

## 4. What is persistence?

Persistence is the mechanism that transfers Redis state from memory to storage so Redis can recover after a restart.

Redis supports these main options:

- **RDB snapshots:** capture dataset state at a point in time into a snapshot file.
- **AOF (Append Only File):** logs data-mutating operations so state can be rebuilt on startup.
- **Combined RDB and AOF:** a deployment may enable both.
- **No persistence:** data lives solely in memory; suitable for fully rebuildable caches, though its risks must be understood when combined with replication/failover.

No option guarantees absolute safety against every failure class: storage failures, misconfiguration, operator deletions, replication of bad data, and losing an entire failure domain all require separate planning.

## 5. RDB: point-in-time snapshots

RDB saves a snapshot of Redis data, typically via background saving.

Example `redis.conf` settings:

```conf
save 900 1
save 300 10
save 60 10000

dbfilename dump.rdb
dir /var/lib/redis
stop-writes-on-bgsave-error yes
```

The `save` lines describe time and mutation thresholds for automatic snapshots; they do not mean a fresh snapshot is guaranteed every 900 seconds on the dot.

Conceptually:

```text
10:00   Redis has dataset version A
10:01   RDB snapshot writes version A
10:03   Writes B, C, D occur in RAM
10:04   Redis process/host crashes
10:05   Restart loads latest RDB -> may contain only version A
```

If no newer snapshot completed, writes after the snapshot may be lost when the node restarts from RDB.

### RDB advantages

- Compact snapshot files, convenient for certain backup/restore workflows.
- Can restart large datasets efficiently under favorable system conditions.
- Represents a consistent point-in-time capture when the snapshot succeeds per Redis mechanics.
- Useful for multi-version backup retention strategies.

### RDB limitations

- **The data-loss window** can span from the last successful snapshot up to the incident.
- Background saves pressure CPU, I/O, memory, and copy-on-write.
- If disk fills up or permissions are wrong, snapshots can fail.
- Having a `dump.rdb` file does not mean it is recent, valid, or copied out of the failure domain.
- Snapshots do not prevent application bugs or accidental deletions from being captured in the next snapshot.

RDB fits when a certain RPO window is acceptable, or as a complementary snapshot/backup layer alongside AOF.

## 6. AOF: logging mutations and fsync policies

AOF logs data-mutating commands via Redis's append log mechanism. Redis uses this log to rebuild state on startup.

Example:

```conf
appendonly yes
appendfsync everysec
```

Three common policies:

| `appendfsync` | Practical meaning | Trade-off |
| --- | --- | --- |
| `always` | Requests syncing AOF to storage frequently, per write | Higher I/O and latency cost, typically more durable |
| `everysec` | Redis proactively fsyncs roughly once per second | Balances throughput and risk of losing latest writes |
| `no` | Lets the OS decide when to flush | Potentially larger data-loss window |

**Do not over-interpret:** with `everysec`, people often say "roughly one second of data can be lost" in typical crash scenarios. This **is not a hard guarantee** that every incident—including disk stalls, power loss, or filesystem errors—loses at most one second.

Likewise, `always` shrinks the window from un-fsynced buffers, yet does not prove absolute safety across hardware, firmware, storage controller, or infrastructure misconfigurations.

### AOF everysec timeline

```text
T0       AOF has fsynced
T0+100ms SET x 1 -> OK
T0+300ms SET y 2 -> OK
T0+500ms host crashes before the next fsync turn
```

Some acknowledged writes may not survive in local AOF recovery, depending on OS/storage state and log buffers.

**A Redis command ACK is not automatically an on-disk fsync ACK.**

## 7. When both RDB and AOF are enabled

Example combined configuration:

```conf
appendonly yes
appendfsync everysec

save 900 1
save 300 10
save 60 10000

dir /var/lib/redis
dbfilename dump.rdb
appenddirname appendonlydir
aof-use-rdb-preamble yes
```

When both RDB and AOF are enabled, Redis normally prioritizes recovering from AOF if valid AOF data exists, because AOF is designed to be fresher than RDB snapshots.

RDB can still serve snapshot or backup purposes. AOF narrows the data-loss window relative to infrequent snapshots alone.

**However, enabling both does not simply equal "RDB + AOF = zero data loss".** You must check:

- How far AOF has fsynced.
- When the last RDB snapshot succeeded.
- Whether files live on durable storage.
- Whether disk space suffices for AOF rewrites and snapshots.
- How up to date copies on other nodes are.
- Whether failover elects a replica holding the just-acknowledged write.
- Whether backups exist independently of the current host.

### AOF rewrite

AOF cannot grow indefinitely without compaction. Redis supports rewriting/compacting the log to reduce the volume of data requiring replay.

In modern Redis versions, AOF can span multiple files with a manifest, base file, and incremental files. Therefore, **never assume copying a single open `appendonly.aof` file safely backs up the entire AOF**.

Backup and restore plans for AOF must follow the consistent layout and workflow of the running Redis version.

## 8. Persistence is configured per Redis node

In a primary–replicas topology, **each Redis process manages its own memory, disk, and local persistence**.

```text
Primary A:
  RAM data A
  /var/lib/redis/dump.rdb
  /var/lib/redis/appendonlydir/...

Replica B:
  RAM replica of A
  /var/lib/redis/dump.rdb
  /var/lib/redis/appendonlydir/...
```

Do not assume that because Primary A has AOF enabled, Replica B automatically uses the same fsync policy. Replication streams data/commands; **it does not synchronize disk/persistence configs across nodes**.

When Replica B is promoted:

- B continues serving the data it currently holds.
- B continues applying process B's own persistence settings.
- If B lacks AOF or uses a weaker policy, durability after failover differs from A.
- When A rejoins configured as a replica of B, resynchronization may overwrite A's local dataset with the new master's data.

Production should therefore maintain consistent persistence configs **across all promotable nodes**, unless a documented role-specific design dictates otherwise.

## 9. Replication: data copies are not synchronous by default

Redis replication is normally asynchronous. The primary sends changes to replicas over the replication stream; replicas apply them based on connectivity and processing speed.

```text
Primary A                         Replica B
---------                         ---------
SET key=v2
apply in memory
reply OK to Spring
   |
   +---------- replication ------> apply key=v2
```

Between the moment the primary ACKs and the moment the replica applies the write, the two nodes diverge.

**Replication offset** is one metric for tracking replica progress, yet advancing offset does not prove every write has been fsynced to the replica's disk.

### Partial resynchronization and full resynchronization

After brief replication disconnects, Redis can perform partial resync if the replication backlog and protocol conditions allow. Otherwise, the replica may require a full resynchronization.

During a full resync:

- Replica data may need to be replaced by a master snapshot/state.
- Network, CPU, disk, and memory incur extra load.
- The replica may not be ready for reads or failover as expected at every instant.
- If bad data was written to the new master, replication spreads that bad state to replicas.

**Replication is not a historical backup.** An accidental `DEL` on the primary replicates to all replicas.

## 10. Case 1: primary ACKs, but replica has not received the write

Timeline:

```text
T0  Primary A and Replica B both have state v1
T1  Spring -> A: SET state v2
T2  A returns OK
T3  A crashes before B receives the write
T4  Failover promotes B
T5  B still has state v1
```

In this case:

- The sharding/replication topology restores service availability.
- Redis data on the new primary is **older** than what Spring received `OK` for.
- Even if A had v2 in its local AOF, that file does not dictate the failover outcome once B becomes master.
- When A rejoins as B's replica, A's state can be resynced to match B.

**Conclusion:** an acknowledged write does not prove "it is definitely on whichever replica gets promoted".

## 11. Case 2: primary fsynced, but promoted replica lacks the write

Suppose Primary A runs AOF `appendfsync always` and fsynced write v2:

```text
A: v2 is saved on disk
B: still v1 because replication has not arrived

A is isolated from the cluster
B is promoted to primary
Spring reads B -> v1
```

A's AOF may still hold v2, yet the cluster now serves from B with v1. When A returns as B's replica, the cluster does not automatically "merge all newest writes from both sides" in a business sense.

This illustrates that **local persistence and failover selection are two distinct mechanisms**.

To lower this risk, consider replication acknowledgments, write policies, or even keeping a stronger transactional source of truth for data that cannot be lost.

## 12. Case 3: replicas hold data, but none has durable disk persistence

```text
Primary A:   persistence off
Replica B:   persistence off
Replica C:   persistence off
```

When node A fails, B/C keep data in RAM and support failover. However, if the entire topology restarts, no durable copy remains to recover the dataset.

One especially dangerous pitfall is **a persistence-less master restarting empty while replication is unmanaged**. If replicas sync from an empty master at the wrong moment, data remaining in replicas' RAM can be wiped out.

For environments where Redis is strictly a rebuildable cache, turning persistence off may be chosen after accepting recovery terms. For Redis storing unique business state, this is high risk.

**Do not equate "multiple copies in RAM" with "a safe backup across a full power outage".**

## 13. Case 4: accidental deletion gets replicated

```text
T0  Primary A and replicas have valid data
T1  Operator/script sends DEL orders:all:important
T2  Primary A deletes it
T3  Replicas also receive the deletion
T4  Failover to replica
T5  Data is still deleted
```

Replication keeps nodes aligned with the master's state, even when that state is **wrong from a business perspective**. Failover cannot travel back to before the erroneous delete ran.

Recovering from accidental deletions requires **independent backups**, retention policies, access controls, and restore runbooks.

A backup that has never been restore-tested is also insufficient proof of recoverability.

## 14. When does persistence still matter if you already have replicas?

There are at least four benefits:

1. **Local restarts:** a node can load data from disk instead of forcing a full sync from the master in every scenario.
2. **Simultaneous failures:** when multiple nodes lose RAM/processes, disk persistence expands recovery options.
3. **Backups/snapshots:** provides inputs for independent copies and DR workflows.
4. **Controlling the local data-loss window:** AOF fsync policies let you trade durability against I/O cost.

Still, persistence does not replace:

- Replicas to minimize downtime.
- A failover controller to switch primaries.
- Backups to recover from logic bugs or corruption.
- Idempotency to prevent duplicate side effects when write outcomes are ambiguous.
- Another authoritative store when consistency requirements exceed Redis's guarantees.

## 15. Sentinel: master discovery and failover coordination

In a non-sharded Redis primary–replica topology, **Redis Sentinel** monitors master/replicas and coordinates failover.

Example:

```text
               Sentinel A
               Sentinel B
               Sentinel C
                    |
                    v
                 Master A
                    |
                   sync
                    v
                 Replica B
```

If Master A fails and quorum/authorization conditions are met, Sentinel can promote Replica B to master.

After failover:

```text
Spring client asks Sentinel -> new master is Replica B
Spring connects data traffic -> B
```

Sentinel does not replicate business data; Sentinel does not store master writes itself. It coordinates topology. Data freshness on B still depends on replication prior to failover.

### Simple Sentinel config

Example Sentinel configuration file:

```conf
port 26379
sentinel monitor mymaster 10.10.0.11 6379 2
sentinel down-after-milliseconds mymaster 10000
sentinel failover-timeout mymaster 60000
sentinel parallel-syncs mymaster 1
```

Addresses and thresholds are illustrative. Sentinel requires enough replicas/Sentinels spread across appropriate failure domains, and clients must be able to reach the master address Sentinel advertises.

**Sentinel count and quorum do not by themselves guarantee "zero lost writes".** They primarily handle failure detection and election.

## 16. Redis Cluster: replication and failover per shard

Redis Cluster distributes keys across hash slots owned by multiple primary nodes. Each primary can have its own replicas.

```text
Redis Cluster
  Primary A (slots A) ----> Replica A1
  Primary B (slots B) ----> Replica B1
  Primary C (slots C) ----> Replica C1
```

When Primary B fails, Replica B1 can be promoted to take over **slots B**. It does not take over keys belonging to A and C.

Three mechanisms operate here:

- **Sharding:** distributes 16,384 slots across primaries.
- **Replication:** each replica copies its corresponding shard's dataset.
- **Failover:** a shard's primary is replaced by its replica.

All durability reasoning must be done **per shard and per replica**, rather than just counting total nodes across the cluster.

### Sentinel and Cluster configurations are not interchangeable

In Spring Data Redis:

- `RedisSentinelConfiguration` uses a master name and Sentinel addresses.
- `RedisClusterConfiguration` uses cluster seed nodes and slot topology.

Redis Cluster has its own built-in failover protocol and does not use Sentinel to fail over cluster primaries.

## 17. Defining RPO and RTO before picking settings

**RPO (Recovery Point Objective)**: the tolerable amount of data loss during recovery, such as losing at most updates from a given period before the incident per business goals.

**RTO (Recovery Time Objective)**: the target time to restore service operation after an outage.

Separate:

```text
Durability target:
  RPO: how much data can be lost?

Availability target:
  RTO: how long can the service be down?
```

Hypothetical examples:

| Data type | Desired RPO | Desired RTO | Direction |
| --- | --- | --- | --- |
| Rebuildable article cache | Entire cache can be lost | Short | Replicas/HA per latency; DB fallback |
| Product cache | Cache copies can be lost | Short | TTL, read-through/cache-aside, HA |
| Login sessions | Bounded by user experience | Short | Replicas, persistence, session policy |
| Critical job queues | Must not drop accepted jobs | Per job SLA | Durable queue/ledger, idempotency |
| Payment data | Very low or near zero | Per system target | Strong transactional source of truth, outbox |

**Never pick `appendfsync everysec` and assume that equals "RPO = exactly 1 second".** RPO must account for failover to a lagging replica, multi-node loss, storage failures, and operational scenarios.

## 18. AOF/RDB policies vs. RPO/RTO

| Mode | Strengths | Main risks |
| --- | --- | --- |
| Periodic RDB | Compact snapshot backups, snapshot recovery | Can lose writes after last snapshot |
| AOF `everysec` | Balances performance and local durability | Can lose un-fsynced log tail, no hard bound across all failures |
| AOF `always` | Shrinks un-fsynced window | I/O/latency cost, depends on storage quality |
| RDB + AOF | Combines snapshots and recent log | Does not eliminate async replication/failover loss |
| Persistence off | Avoids persistence I/O | Multi-node restart can wipe dataset |
| Replicas without backups | HA on partial node loss | Poor recovery from accidental deletes or spreading corruption |
| Backups to independent storage | Recovers from multi-node loss or logic errors | Restore latency; requires testing |

No single mode optimizes every workload. If Redis is purely a cache, local durability may matter less than latency. If Redis is the system of record for critical data, analyze write-loss exposure deeply and consider alternative data architectures if needed.

## 19. Reducing write-loss exposure with min-replicas-to-write

Redis supports:

```conf
min-replicas-to-write 1
min-replicas-max-lag 10
```

Idea: the master can refuse writes when too few replicas are connected with acceptable replication lag.

For instance, requiring at least one connected replica within a 10-second lag policy.

**Effect:** reduces the chance of an isolated primary continuing to accept writes with zero eligible replicas.

**What it does NOT guarantee:**

- That the specific write just acknowledged is already on a replica.
- That a replica has fsynced the write to disk.
- That failover will elect the exact replica that received the write.
- Zero data loss if multiple nodes fail.
- Absence of gaps between condition checks and actual replication.

These settings tighten write acceptance at the cost of **availability**: Redis rejects writes whenever replicas lag or disconnect, even though the primary remains online.

### Why not set min-replicas too high?

If you require many simultaneously healthy replicas while routine maintenance takes one node offline, the application can suffer unnecessary write rejections relative to HA goals.

Choose thresholds based on:

- Actual replica count.
- Network latency and load.
- Target RPO.
- Acceptable write availability.
- Operational realities and monitoring.

## 20. WAIT: awaiting replication acknowledgment, not a synchronous transaction

Redis provides:

```redis
WAIT numreplicas timeout
```

Example in a `redis-cli` session connected to the primary:

```redis
SET order:42 CONFIRMED
WAIT 1 2000
```

Here `WAIT 1 2000` tries to wait for at least one replica to acknowledge processing the replication offset corresponding to prior writes on the **same client connection**; timeout is in milliseconds.

The command returns how many replicas satisfied the condition, which may be fewer than requested.

Example:

```text
WAIT returns 1 -> at least 1 replica acknowledged replication per condition
WAIT returns 0 -> no eligible replica acknowledged within timeout
```

**Critically important:**

- `WAIT` does not convert replication into an absolute synchronous write protocol.
- Replication ACK does not mean the replica fsynced to AOF.
- `WAIT` only observes replication state reached at a point in time.
- Topology and failures can still change after `WAIT`.
- An acknowledging replica can still lose RAM/disk in a subsequent failure.
- Failover has no per-client contract ensuring the promoted replica is the one that ACKed `WAIT`.

Thus, `WAIT` narrows certain risk windows, **without guaranteeing zero data loss**.

### Why does the same connection matter?

`WAIT` is designed to wait on the replication offset of previous writes issued by the client on that connection. If an application sends `SET` and `WAIT` over different connections without controlling connection context, you cannot assume `WAIT` waits for that preceding write.

Pay close attention to this when using connection pooling or Spring Data Redis abstractions.

## 21. WAIT with Spring Data Redis: low-level communication requires control

An important illustration of **connection boundary**:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.core.RedisTemplate;

public class ReplicatedWriteExample {

    private final RedisTemplate<String, String> redis;

    public ReplicatedWriteExample(
            RedisTemplate<String, String> redis) {
        this.redis = redis;
    }

    public Long writeAndWait(String key, String value) {
        return redis.execute((RedisConnection connection) -> {

            byte[] keyBytes =
                key.getBytes(StandardCharsets.UTF_8);
            byte[] valueBytes =
                value.getBytes(StandardCharsets.UTF_8);

            connection.stringCommands().set(keyBytes, valueBytes);

            // Connection-layer pseudocode:
            // Only after writing, invoke WAIT on the *same* connection.
            // The low-level/driver API to send WAIT depends on the version of
            // Spring Data Redis, Lettuce, or Jedis.
            //
            // return numberOfReplicasThatAcknowledged;
            return 0L;
        });
    }
}
```

The snippet above **illustrates where `WAIT` belongs**, not a ready-made replication-safe implementation: `0L` is a placeholder, not an actual Redis result. To use it in practice, invoke the supported `WAIT`/server command API for your Spring Data Redis/driver version, verify same-connection execution, and check the returned count.

If you merely write:

```java
redis.opsForValue().set(key, value);
// An arbitrary WAIT command sent over another connection
```

you cannot claim to have waited for the previous line's write to replicate.

For systems requiring stronger assurances, document exact transaction/connection boundaries and write integration tests against a real Redis setup.

## 22. WAITAOF and its scope of applicability

Newer Redis versions support **`WAITAOF`** (introduced in Redis 7.2) to await AOF write confirmation for prior writes in an appropriate context.

Concept:

```redis
SET order:42 CONFIRMED
WAITAOF 1 1 2000
```

Conceptual syntax:

```text
WAITAOF numlocal numreplicas timeout
```

In the example, the client requests local AOF and one replica condition per command semantics, with a 2000-millisecond timeout.

Keep clear:

- The Redis server must support `WAITAOF`.
- AOF must be appropriately configured on all requested nodes.
- Like `WAIT`, results depend on prior writes on the **client connection**.
- Check the local/replica counts returned by the command; never assume returning without exception means all thresholds passed.
- It helps wait for a level of AOF durability, yet **does not replace backups, business transactions, quorum storage, or a consensus database**.
- Driver/framework versions may not expose convenient high-level methods; use an appropriate command API and test it.

Do not use `WAITAOF` on unsupported Redis versions, and do not treat `WAITAOF` as a substitute for holistic persistence/replication/failover design.

## 23. Spring Boot connecting to Redis Sentinel

With Sentinel, modern Spring Boot can be configured as:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
      connect-timeout: 3s
      timeout: 3s
```

`mymaster` must match the logical master name monitored by Sentinel, not a hostname.

With the appropriate Spring Data Redis dependency, the application can use:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisStateService {

    private final StringRedisTemplate redis;

    public RedisStateService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void putStatus(String id, String status) {
        redis.opsForValue().set("state:" + id, status);
    }

    public String getStatus(String id) {
        return redis.opsForValue().get("state:" + id);
    }
}
```

A Sentinel-configured driver discovers the current master dynamically, yet **does not guarantee write durability merely because Sentinel is used**.

### Do not put persistence settings into Spring YAML thinking Redis enabled AOF

Settings such as:

```conf
appendonly yes
appendfsync everysec
save 300 10
```

are **Redis server/process settings**, not Spring Boot properties that turn on AOF across nodes. Spring's `application.yml` primarily configures **how the client connects to Redis**.

If your team manages Redis with Terraform, Helm, or a Redis Operator, Redis server settings must be managed in the infrastructure layer.

## 24. Spring Boot connecting to Redis Cluster

For Redis Cluster, configuration differs from Sentinel:

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

These nodes act as cluster seeds; the client discovers hash slots and nodes.

Points to remember:

- Each shard has persistence settings on its primary and replicas.
- If a shard loses its primary, a replica of **that shard** can be promoted.
- If both the primary and all replicas of a shard fail, no copy of those slots remains available.
- Cluster resharding is neither replication nor backup.
- When writes span keys in different hash slots, Redis Cluster does not automatically create a distributed transaction.

### Spring Data Redis Java configuration

If not using auto-configuration:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class ClusterConnectionConfig {

    @Bean
    LettuceConnectionFactory redisConnectionFactory() {

        RedisClusterConfiguration cluster =
            new RedisClusterConfiguration(
                List.of(
                    "redis-node-1.internal:6379",
                    "redis-node-2.internal:6379",
                    "redis-node-3.internal:6379"
                )
            );

        cluster.setMaxRedirects(5);
        return new LettuceConnectionFactory(cluster);
    }
}
```

When defining a custom factory, configure auth, TLS, timeouts, and topology refresh yourself as required. Do not create a custom factory and assume all `spring.data.redis.*` properties still bind automatically to that bean.

## 25. Choosing Lettuce/Jedis and handling topology

Spring Data Redis can use Lettuce or Jedis depending on dependencies and version.

Lettuce supports Redis Cluster and Sentinel via their corresponding configurations; the client handles reconnection and topology discovery/refresh.

However, a successful reconnect does not mean:

- Commands sent before disconnection definitely failed.
- Commands sent before disconnection definitely succeeded.
- The new replica definitely holds the just-acknowledged write.
- Non-idempotent commands can be retried unconditionally.

Cases like `MOVED`, `ASK`, `READONLY`, connection resets, and timeouts during failover must be handled per driver and business rules. Applications need metrics, retry policies, and idempotency keys for writes with side effects.

### Reading from replicas and consistency

Some applications configure Lettuce to read from replicas for workloads that tolerate stale data:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .readFrom(ReadFrom.REPLICA_PREFERRED)
        .build();
```

With this option, replicas can return older values due to replication lag. For workflows requiring read-your-writes, designate an authoritative read path; never enable replica reads solely for throughput.

## 26. Handling write timeouts: not knowing if the command ran

More subtle than a clean connection refusal is an **ambiguous outcome**.

```text
Spring -> Redis primary: INCR billing:counter
Redis executes INCR
Redis has not sent response yet
Connection drops
Spring receives timeout
```

The client does not know whether the counter was incremented. Retrying `INCR` blindly can double-increment it; ignoring it can lose an increment.

Operations and retry perspective:

| Operation | Unconditional retry? | Issue |
| --- | --- | --- |
| `GET key` | Often possible, per consistency policy | Data may change between attempts |
| `SET key fixedValue` | Often idempotent if no extra conditions apply | Consider TTL and side effects |
| `INCR key` | No | May increment twice |
| `LPUSH list value` | No | May push duplicate items |
| `SET key token NX PX ...` | Check token/owner | Lock may already have been created |
| Reserve/payment Lua script | Needs idempotency | Script may have executed before timeout |
| `XADD` with auto-generated ID | Not by default | Retry can append a second entry |

Failover increases the likelihood of ambiguous outcomes, though this distributed systems problem exists even without failover.

### Common solutions

1. Issue a stable **requestId/idempotency key** at the business layer.
2. Record request results in the same atomic unit where feasible.
3. Retry using the **same requestId**, without generating a fresh ID.
4. When outcomes are uncertain, check authoritative state before deciding.
5. Never treat a timeout as proof that Redis did not execute the command.

If Redis itself can lose writes on failover, idempotency state kept only in that Redis instance is also at risk; critical business data needs a sufficiently durable authoritative store.

## 27. Is Redis a cache or an authoritative data source?

Two scenarios lead to opposite durability choices.

### Redis is only a cache

```text
PostgreSQL (source of truth)
          |
          v
Redis Cache
          |
          v
Spring API
```

If Redis crashes and loses its cache:

- The API experiences cache misses.
- The application reads again from PostgreSQL.
- The cache is repopulated as long as the source holds.
- Redis persistence can speed up restarts, yet is not required to prevent business data loss.

In this case, **availability and fallback capability** may outweigh fsyncing every Redis write.

### Redis holds unique business state

```text
Spring -> Redis
          |
          +-- only here exist reservations / quotas / job states
```

If a write is lost during failover, no external database can rebuild it. You need serious RPO/RTO targets, replication/persistence/backups, and potentially moving certain data to a database with stronger guarantees.

**Never choose a Redis setup based purely on speed**, especially for balances, payments, orders, or auditable records.

## 28. Transactional outbox when Redis is a replica or downstream processor

A common pattern when a database is the source of truth:

```text
Spring transaction
   |
   +-- UPDATE business record
   |
   +-- INSERT outbox_event
   |
   v
COMMIT database
   |
   v
Outbox worker reads event
   |
   v
Update Redis cache/stream/derived view
   |
   v
Mark processed or retry
```

If Redis fails over right while the worker writes cache:

- The database record remains canonical.
- The outbox event can still be retried.
- The worker must be idempotent and enforce version/ordering checks as needed.
- Redis can drop a cache entry without losing the business transaction.

An outbox does not make Redis and the database a single distributed transaction, yet reliably closes the "DB committed, app crashed before updating Redis" window.

### Out-of-order events

If two versions of an entity are published:

```text
version 7 -> price=110
version 8 -> price=120
```

a slow worker applying version 7 after version 8 can overwrite the cache with the stale price. Either invalidate the cache instead of writing stale snapshots, or check versions atomically when updating Redis per business contract.

Persistence and replication do not solve out-of-order application updates.

## 29. Redis replication does not replace backups

Replication gives another node a copy of current state. If a destructive command runs:

```redis
FLUSHDB
```

or an application writes corrupted data, that change replicates to replicas too.

**Backups** must be independently restorable snapshots isolated from the live cluster and governed by retention policies.

A backup strategy may include:

- Point-in-time RDB snapshots.
- Copies to object storage or a backup system **in another failure domain**.
- Integrity/checksum verification.
- Encryption and access control on backups.
- Retaining multiple versions to recover from logic errors.
- Periodic restore drills.
- Retention policies aligned with compliance requirements.

### Do not copy an active AOF haphazardly

With Redis 7+ multi-part AOF and manifests, copying an arbitrary file while Redis is writing can produce an inconsistent backup. Use snapshot/backup mechanisms supported by Redis and your platform, or take consistent backups per your version's procedure.

With RDB-only backups, accept an RPO tied to snapshot timing. Closer point-in-time recovery requires dedicated architecture and workflows; Redis OSS does not natively provide full point-in-time recovery like dedicated transactional databases.

## 30. Backup and restore in Cluster deployments

Redis Cluster shards data across multiple primaries. Backing up one node **does not back up the entire cluster dataset**.

Example:

```text
Primary A: keys slots A -> backup A
Primary B: keys slots B -> backup B
Primary C: keys slots C -> backup C
```

Backup plans must cover all shards and retain topology metadata for recovery. Taking shard snapshots at different times can leave cross-shard backups skewed relative to a single global timestamp.

Questions to answer:

1. Which snapshot belongs to which shard/primary?
2. Were cluster slots resharded between backups?
3. Are backups complete for all shards at the target time?
4. Are we restoring onto a fresh cluster or existing nodes?
5. Is cluster metadata/configuration compatible with the restored files?
6. How is the restore environment isolated to avoid overwriting production?
7. How will data and slot routing be verified post-restore?

**Do not simply copy `nodes.conf` or AOF files from a running cluster to another cluster** and expect topology to align automatically. Redis Cluster persists node identities and slot ownership; restores must follow platform/tooling procedures.

## 31. Failure scenarios requiring distinct recovery plans

| Failure | What can help? | What must be verified |
| --- | --- | --- |
| Redis process crash, disk intact | Local AOF/RDB | File validity, fsync lag, recovery time |
| Host failure, replica alive | Failover | Whether replica has enough data, write readiness post-promotion |
| High replica lag | Replication + monitoring | RPO exposure, no assumed read-your-writes |
| All nodes lose RAM | Persistence/backups | Storage intact, restore order, point-in-time age |
| Primary disk destroyed | Replica + backups | Failover outcome and independent backup availability |
| Accidental delete / `FLUSHDB` | Historical versioned backup | Deletion already replicated across nodes |
| Resharding failure | Cluster metadata/backups | Slot mapping and per-shard data integrity |
| Network partition | Election/cluster policies | Majority/quorum, split-brain prevention, write loss |
| Redis provider outage | Cross-zone/region DR | Networking, credentials, restore duration |
| Application retry on timeout | Idempotency ledger | Whether side effect already executed |

No single "turn on replication" action covers this entire table.

## 32. Redis server configuration on primary and replicas

Example of a Redis node configured with both AOF and RDB:

```conf
port 6379
dir /var/lib/redis

appendonly yes
appendfsync everysec
aof-use-rdb-preamble yes

save 900 1
save 300 10
save 60 10000
stop-writes-on-bgsave-error yes

min-replicas-to-write 1
min-replicas-max-lag 10
```

**Never copy this verbatim onto every node without checking node roles and goals.** The two `min-replicas-*` lines enforce write-acceptance rules on the primary; in topologies with fewer or no eligible replicas, they can reject writes. Adjust to match your topology.

Persistence and backup settings on each node should match its role, storage layout, and Redis version.

### Replica configuration

A replica may specify:

```conf
replicaof 10.10.0.11 6379
```

With Sentinel or Cluster, live topology changes dynamically upon failover. Avoid configuration-management scripts that forcibly reset replicas back to the old master on restart, overriding newly elected masters.

When using ACLs, configure authentication properly for both replication links and client connections.

## 33. Disk storage and background save pressure

Persistence is not free. When Redis runs an RDB snapshot or AOF rewrite, it may fork a child/background task and trigger copy-on-write.

Operational factors:

- Sufficient RAM for copy-on-write during heavy writes while snapshotting.
- Enough disk space for new snapshots, AOF rewrites, and uncleaned older files.
- Filesystem with suitable latency and durability characteristics.
- Avoiding undersized volumes that cause AOF rewrites or RDB saves to fail.
- Never placing persistence files in ephemeral container filesystems when survival across pod replacements is required.
- Monitoring command latency spikes during heavy disk I/O.
- Verifying directory ownership and permissions.
- Understanding how process shutdown waits for persistence or handles signals.

In Kubernetes, persistence requires a PersistentVolume or suitable storage backend. Yet **having a PVC alone does not prove data fsynced properly, replicated cross-zone, or was backed up**.

### maxmemory and eviction

When Redis serves as a cache, `maxmemory-policy` may actively evict keys. Eviction is normal data-management behavior, not a persistence bug; keys can vanish per policy even while AOF/RDB work properly.

If Redis stores data that must not be lost via eviction, choose a suitable `maxmemory-policy`, normally avoiding policies that drop critical keys.

## 34. Inspecting Redis persistence with operational commands

On each Redis data node:

```bash
redis-cli -h redis-node.internal -p 6379 INFO persistence
redis-cli -h redis-node.internal -p 6379 INFO replication
redis-cli -h redis-node.internal -p 6379 ROLE
redis-cli -h redis-node.internal -p 6379 LASTSAVE
```

Inspect configuration:

```bash
redis-cli -h redis-node.internal -p 6379 CONFIG GET appendonly
redis-cli -h redis-node.internal -p 6379 CONFIG GET appendfsync
redis-cli -h redis-node.internal -p 6379 CONFIG GET save
redis-cli -h redis-node.internal -p 6379 CONFIG GET min-replicas-to-write
redis-cli -h redis-node.internal -p 6379 CONFIG GET min-replicas-max-lag
```

In production, Redis ACLs or managed services may restrict `CONFIG` commands; use provider tooling where appropriate.

### Reading INFO persistence

Key signals to watch:

| Field/Group | What to monitor |
| --- | --- |
| `rdb_last_bgsave_status` | Whether the previous snapshot succeeded |
| `rdb_last_save_time` | Timestamp of the latest RDB save |
| `rdb_bgsave_in_progress` | Whether a background save is running |
| `aof_enabled` | Whether AOF is enabled |
| `aof_last_write_status` | Whether recent AOF writes encountered errors |
| `aof_last_bgrewrite_status` | Whether the latest AOF rewrite succeeded |
| `aof_rewrite_in_progress` | Whether an AOF rewrite is currently running |
| AOF size fields | Track file growth and rewrites |

Exact field names/availability vary by Redis version. Never assume `aof_enabled=1` means the disk is healthy or fsync has caught up with all writes.

### Reading INFO replication

Track:

- `role`: master or slave/replica per Redis version terminology.
- `connected_slaves` or connected replica count.
- Master and replica replication offsets.
- `master_link_status` on replicas.
- Active synchronization or full resync statuses.

Connected replica count alone does not guarantee all replicas hold full data or fsynced AOFs.

## 35. Checking failover with Sentinel

On Sentinel:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL get-master-addr-by-name mymaster

redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL master mymaster

redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL replicas mymaster
```

On the data node reported as master:

```bash
redis-cli -h redis-primary.internal -p 6379 INFO replication
```

These commands verify:

- Which node Sentinel currently considers master.
- Which replicas remain tracked.
- The actual role of the data node.
- Whether topology skew or replication lag exists.

**Note:** mid-failover, Sentinels may temporarily observe differing states. Check logs/events and all participating nodes instead of concluding from one single query.

## 36. Checking Redis Cluster during failover

On a Redis Cluster node:

```bash
redis-cli -c -h redis-node.internal -p 6379 CLUSTER INFO
redis-cli -c -h redis-node.internal -p 6379 CLUSTER NODES
redis-cli -c -h redis-node.internal -p 6379 CLUSTER SHARDS
```

Inspect:

- `cluster_state`.
- Hash slots currently served.
- List of primaries/replicas.
- Which node owns slots after failover.
- Whether each shard has healthy replicas.
- Whether clients refresh topology via seeds/redirects.

During Cluster resharding or failover, clients may see `MOVED`, `ASK`, `READONLY`, or timeouts depending on timing and topology state. Those are not inherently persistence bugs; separate **slot routing**, **role changes**, and **local disk recovery**.

## 37. Test matrix by failure layer

A sound test plan separates **process loss**, **host loss**, **replication link loss**, and **failover**.

| Test | Impact | What to measure |
| --- | --- | --- |
| Graceful process restart | Controlled Redis stop/start | AOF/RDB load, latency, surviving keys |
| Abrupt process crash | Process dies without clean shutdown | Surviving writes, fsync gap |
| Primary loss, replica alive | Failover | RTO, write-loss window |
| Primary–replica network loss | Replication lag/disconnect | `min-replicas` behavior, stale reads |
| Replica offline then reconnects | PSYNC / full sync | Bandwidth, sync time |
| AOF rewrite under load | Disk/CPU/COW | Latency, free space, errors |
| Full disk | AOF/RDB errors | App error handling, alerts |
| Both primary and replicas lost | No live RAM remains | Backup/restore RTO |
| Accidental key deletion | Replication propagates delete | Historical backup recovery |
| Client write timeout | Ambiguous result | Idempotency, duplicate side effects |

All fault-injection tests must run in **isolated** environments—never against production data.

## 38. Lab A: comparing RDB and AOF after a crash

Spin up two test Redis instances:

**Instance A:** RDB only.

```conf
appendonly no
save 60 10
```

**Instance B:** AOF everysec.

```conf
appendonly yes
appendfsync everysec
```

Execute:

1. Write a sequence of values with sequential IDs and timestamps.
2. Observe the last RDB save time and AOF status.
3. Use your test environment to simulate process crashes at various points.
4. Restart and count which IDs survived.
5. Compare write latency and potential data-loss windows.
6. Repeat under varied I/O loads and record trial counts.

**Never use a single trial to claim a strict data-loss bound.** Killing a single process is not equivalent to full host/storage power loss because OS filesystem caches may remain intact.

## 39. Lab B: failover under replication lag

Use a test Sentinel or Redis Cluster setup with at least one primary and eligible replica.

Target timeline:

```text
1. Write keys and track sequence numbers.
2. Introduce controlled replication lag in the test environment.
3. Write additional new keys.
4. Induce a primary failure.
5. Observe replica promotion.
6. Compare sequence numbers before and after.
```

Record:

- Up to which sequence number the primary ACKed.
- Up to which sequence number the replica held.
- Which Redis node was promoted.
- Observed RPO in that trial.
- How long the client took before writes succeeded again.
- Whether retries produced duplicates.

If your chosen topology cannot fail over due to missing quorum/majority, note that separately as an HA topology issue rather than a persistence failure.

## 40. Lab C: WAIT and WAITAOF

In a test Redis setup with AOF and suitable replicas, on the **same `redis-cli` session**:

```redis
SET demo:durability:1 "v1"
WAIT 1 2000
```

Record how many replicas were reported as acknowledging.

If your Redis supports `WAITAOF` and AOF is properly enabled, test:

```redis
SET demo:durability:2 "v2"
WAITAOF 1 1 2000
```

Record the acknowledgment counts returned by the command.

Questions:

- What does `WAIT` confirm, and what does it **not confirm**?
- How many local/replica acknowledgments does `WAITAOF` require?
- What happens upon timeout?
- Could the preceding command have executed even though the client received fewer ACKs than desired?
- If failover promotes a replica different from the one that just ACKed, what happens?
- If storage fails independently after the ACK, what can you infer?

Never conclude "we now have an absolute synchronous transaction" just because wait commands returned sufficient counts.

## 41. Lab D: backup restore

In a test environment:

1. Save sample data sufficient to verify versions, IDs, and checksums.
2. Create a consistent snapshot/backup per Redis tools and version.
3. Copy the backup somewhere independent of the running Redis container.
4. Tear down the test environment completely.
5. Provision a fresh recovery Redis instance/cluster.
6. Restore following the appropriate runbook.
7. Verify data, TTLs, key types, and application behavior.
8. Measure total restore completion time.
9. Note writes excluded from the backup per actual RPO.

For Redis Cluster, back up each shard, slot mappings, and topology restoration steps. Verifying one key on one node does not prove the entire cluster was backed up cleanly.

## 42. Common misconceptions

### "With replication, AOF/RDB is unnecessary"

False. Replicas can lose RAM/processes simultaneously or receive accidental deletes; persistence and backups cover different failure modes.

### "With AOF on the primary, failover never loses writes"

False. A promoted replica may not yet have received writes acknowledged/fsynced by the primary.

### "Using appendfsync everysec guarantees losing at most one second"

Not a hard bound across all cases, especially under storage stalls and other failures. Failover lag must also be factored in.

### "appendfsync always guarantees zero data loss ever"

Cannot guarantee absolute immunity against storage/hardware/topology failures; also does not make replication synchronous.

### "WAIT 1 means the write is completely safe"

No. `WAIT` awaits replica replication offset ACKs, not fsync or promotion selection.

### "WAITAOF is a consensus commit, so backups are unnecessary"

No. It strengthens guarantees within supported fsync acknowledgment limits, without replacing backups or DR.

### "Sentinel stores a copy of the master's data"

No. Sentinel monitors and coordinates failover; it is not a data replica.

### "Redis Cluster protects every shard even without replicas"

No. Losing a shard's primary when it has no replicas breaks availability and recovery for those slots.

### "Backing up RDB from one node backs up Redis Cluster"

No. Data is sharded across multiple primaries; back up all primaries and topology metadata.

### "Redis persistence is controlled via spring.data.redis.*"

No. Spring properties mainly configure the client; AOF/RDB are server settings on Redis nodes.

### "A timeout means Redis did not execute the write"

False. The response can be lost after Redis wrote it. Non-idempotent retries need guards.

### "Replica reads always return the latest data"

False. Asynchronous replication leads to stale reads.

### "Replication saves you if all keys are accidentally deleted"

No. Deletes replicate to all replicas; historical backups are required.

### "Having a backup file means restore will definitely work"

No. Test restores, verify all shards, integrity, key types, and recovery duration.

## 43. Frequently asked questions

**If Redis is only a cache, should AOF be enabled?**

There is no single answer. If an authoritative data source can rebuild the cache, AOF may be unnecessary; base the decision on warm-up cost, DB load, RTO, and operational needs. Replicas/failover may still help availability.

**Can RDB and AOF be enabled simultaneously?**

Yes. Each serves part of the goal; AOF is typically prioritized on startup when enabled, while RDB aids snapshots and backups.

**Does Redis write AOF before returning OK?**

That depends on the AOF policy and execution internals. Never assume `OK` implies `fsync` finished under all modes, especially `everysec` and `no`.

**Does asynchronous replication mean replicas are always far behind?**

Not always noticeably behind, yet lag spikes can occur and there is no guarantee every post-write replica read sees the newest value.

**Can failover pick a replica missing a recently acknowledged write?**

Yes, depending on replication lag, failure timing, and election. This is a well-known source of write loss in Redis HA.

**Are there ways to reduce write loss?**

AOF with suitable fsync, multiple replicas, `min-replicas-*` rules, `WAIT` or `WAITAOF` on supported versions, proper persistence/backups, and solid operations reduce risk—without guaranteeing zero end-to-end loss.

**Do Sentinel and Redis Cluster perform failover the same way?**

Both promote replicas, but Sentinel manages HA for non-sharded master–replicas groups, while Redis Cluster runs built-in shard topology and election per slot group.

**If all Redis data nodes are lost, can we recover from Sentinel?**

No. Sentinel stores no business data. You need persistence files or valid backups from Redis data nodes.

**Should WAIT be sent on a separate connection after RedisTemplate.set?**

Do not assume that works. `WAIT` waits for replication offsets of prior writes on the same client connection; ensure same-connection execution via an appropriate driver API.

**Does WAITAOF replace a transactional database?**

No. It reports Redis fsync acknowledgments, without creating business transactions or coordinating commits with external systems.

**When Redis times out during INCR, should we retry immediately?**

Never retry blindly; verify the outcome or use an idempotency key because the command may already have executed.

**What is needed to back up a Redis Cluster?**

A strategy covering every shard, consistent snapshots per Redis version procedures, preserved topology metadata, and isolated restore drills.

**Is `INFO persistence` reporting AOF enabled enough?**

No. Also monitor statuses, errors, fsync/rewrites, disk health, replica states, backups, and actual RPO.

## 44. Summary: coordinating three mechanisms within their proper scope

A durable and recoverable Redis design requires recognizing:

- **Persistence (RDB/AOF)** helps a node restore state from storage, yet retains a data-loss window and depends on disk/fsync.
- **Replication** copies changes to other nodes, usually asynchronously, introducing lag and temporary divergence.
- **Failover** promotes an eligible replica when a primary fails; it restores availability without guaranteeing the replica holds every acknowledged write.
- **Sentinel and Redis Cluster** coordinate failover for distinct topologies; Spring Data Redis settings configure client discovery rather than server persistence.
- **`WAIT`/`WAITAOF` and `min-replicas-to-write`** reduce certain risks, yet require reading acknowledgment results accurately and do not turn Redis into a consensus database.
- **Independent backups and restore testing** are mandatory to recover from accidental deletions, multi-node failures, or losing an entire failure domain.
- **Client retries and idempotency** protect against ambiguous write outcomes during timeouts and reconnects.
- **RPO/RTO and source-of-truth roles** must drive configuration, not merely the desire for "fast Redis".

When combining these mechanisms purposefully, a Spring Boot application can benefit from Redis HA while keeping clear visibility into remaining failure modes, possible data loss, and proven recovery paths.

## Official references

- [Redis – Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis – Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis – High Availability with Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Redis – Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis – WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis – WAITAOF](https://redis.io/docs/latest/commands/waitaof/)
- [Redis – INFO](https://redis.io/docs/latest/commands/info/)
- [Spring Data Redis – Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html)
- [Spring Data Redis – Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot – Redis Configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis)
