# Resource Sizing for Redis, Drivers, and Applications in Spring Data Redis

When deploying a Spring Boot application that uses Spring Data Redis, asking “How much RAM does Redis need?” solves only **part** of the problem. A stable operating system requires sizing the resources of the **Redis Server**, **Redis client/driver**, **Java application**, **network**, **storage**, and **replicas**, along with resilience when the cache stops helping or topology changes.

A Redis instance with a 6 GiB dataset does not mean a 6 GiB container RAM limit is sufficient. Beyond logical data, there is metadata, allocator fragmentation, connection buffers, replication buffers, copy-on-write (COW) memory during RDB/AOF rewrites, and OS-accounted memory. Similarly, an application with 500 HTTP threads does not necessarily need 500 Redis connections: **Lettuce can multiplex many commands over a shared native connection**, whereas Jedis and certain blocking/transactional operations require different connection strategies.

The goal of this lesson is to build a **verifiable capacity plan**: characterize the workload, budget per component, choose an initial configuration, measure with benchmarks, and monitor so you can adjust before production overloads. The numbers below are **illustrative examples**, not safe defaults for every application.

## 1. System Resource Map

A deployment typically has multiple layers:

```text
                      Internet / API Clients
                               |
                               v
                    Load Balancer / Ingress
                               |
                     +---------+---------+
                     |                   |
                     v                   v
               Spring Pod A         Spring Pod B ... N
                - JVM heap           - JVM heap
                - thread stacks      - thread stacks
                - Netty/direct RAM   - Netty/direct RAM
                - Lettuce/Jedis      - Lettuce/Jedis
                - connection pool    - connection pool
                     |                   |
                     +---------+---------+
                               |
                          Network / TLS
                               |
                      Redis data primary
                     +-------------------+
                     | in-memory dataset |
                     | expires/metadata  |
                     | client buffers    |
                     | replication buf.  |
                     | persistence child |
                     +-------------------+
                         /             \
                        v               v
                  Redis replica A   Redis replica B
                        |
                   Disk / AOF / RDB
```

If using Redis Cluster, the diagram includes multiple primaries, each owning a subset of hash slots. With Sentinel, Sentinel nodes monitor and coordinate failover. With managed Redis, some components are operated by the provider, yet real costs and limits still apply.

**The budget must be created for the entire system**, not just the `maxmemory` setting of a single Redis instance.

### 1.1. Capacity Planning Questions to Answer

1. How many keys does Redis hold, and what are the value sizes and data types?
2. How long do keys live? When does the dataset grow fastest?
3. Is Redis an evictable cache, or does it hold sessions/locks/queues/state that must not be evicted?
4. How many GET/SET/HGET/ZADD/XADD/INCR commands per second occur?
5. What are the p95/p99 payload sizes, RTT, and command latency?
6. What are the read/write ratios, cache hit/miss rates, timeouts, and retries?
7. How many Spring Boot instances, workers, consumers, and Redis factories exist?
8. Is the client Lettuce or Jedis; shared connections or pooled connections?
9. Are RDB snapshots, AOF, replicas, Sentinel, Cluster, or TLS enabled?
10. When a Redis node is lost or the cache is cold, how much headroom does the system have?
11. What latency, availability, and durability do business SLOs require?
12. How much resource headroom must be reserved for deploys, failover, resharding, and growth?

Where numbers are not yet available, mark them as an **assumption** and design measurements instead of presenting estimates as fact.

## 2. Start from the Workload and Business Boundaries

Before selecting node sizes, compile a workload inventory.

| Category | Information to Measure |
|---|---|
| Product cache | Key count, key/value size, TTL, hit ratio, GET/SET rate |
| Session | Concurrent sessions, serializer size, TTL, reads/writes per request |
| Rate limiter | Key cardinality, TTL, INCR/EXPIRE throughput |
| Lock/idempotency | Active locks, token size, lease, retry rate, business correctness |
| Hash/Set/ZSet | Member/field counts and size distribution |
| Redis Streams | Entries, payload size, retention, pending count, consumer groups |
| Pub/Sub | Publisher rate, listener count, message bytes |
| Lua/scripts | P95/p99 duration, key count, max execution time |
| Batch/warm-up | Burst frequency, command count, pipeline size |
| Redis background jobs | Snapshot/rewrite windows, replication sync, resharding |

### 2.1. Averages Do Not Represent Peaks

Suppose traffic is:

```text
Normal:           2,000 Redis operations/sec
Daily peak:       8,000 operations/sec
Post-deploy:     25,000 operations/sec for 30 seconds due to cache warm-up
```

Sizing for 2,000 ops/s may fail under a 25,000 ops/s burst. Collect:

- p50/p95 and **peak** throughput over sufficiently short windows.
- Commands per HTTP request; one request can trigger many commands.
- Average and percentile payload sizes, not just key count.
- Existing data and projected growth over the next several months.
- Scheduled jobs that create bursts.
- Failover/reconnect conditions that amplify command retries.

Redis can handle high volumes of simple commands yet stall on a few heavy Lua scripts or commands scanning large collections. Do not infer capacity from a `PING` benchmark alone.

### 2.2. Identify Data Sources and Loss Policies

A Redis instance storing caches may use `allkeys-lru` or an equivalent policy as required. However, if Redis stores sessions, locks, idempotency keys, or business streams, eviction can cause unsafe behavior.

Capacity planning must include:

```text
Data criticality
    -> Can it be evicted?
    -> Can it be rebuilt?
    -> What are RPO/RTO?
    -> Does it need backup/persistence?
    -> Can it fail-open when Redis errors?
```

**Resource sizing cannot be separated from the business meaning of the data.**

## 3. Redis RAM Estimation Model

A starting formula:

\[
M_{\text{logical}} \approx
\sum_{i=1}^{n}
N_i \times B_i
\]

Where:

- \(N_i\): number of keys/entries in data group \(i\).
- \(B_i\): actual average Redis memory per entry in group \(i\), **including appropriate overhead**.
- \(M_{\text{logical}}\): estimated logical memory budget for the dataset.

Do not assume:

\[
B_i = \text{UTF-8 key length} + \text{UTF-8 value length}
\]

because Redis also uses object representations, dictionary entries, pointers, allocator rounding, expiration metadata, and internal data structures.

### 3.1. Why a 1 KiB Payload Does Not Cost Exactly 1 KiB of RAM

A String key typically incurs extra memory for:

- Key object/representation.
- Entry in the Redis keyspace dictionary.
- Value object/representation.
- Allocation overhead and alignment.
- Expiration metadata if a TTL is set.
- Internal metadata depending on Redis version/encoding.

A Hash, Sorted Set, or Stream carries per-field/member/entry overhead, and its internal representation can change depending on size/encoding thresholds.

Sizing from payload bytes alone usually **underestimates RAM**.

### 3.2. Use `MEMORY USAGE` for Sampling

On a real Redis instance:

```redis
MEMORY USAGE cache:product:42
MEMORY USAGE session:example
MEMORY USAGE stream:orders SAMPLES 0
```

`MEMORY USAGE` returns bytes according to Redis's accounting for that key. For nested data types, `SAMPLES` affects the cost and accuracy of estimation; `SAMPLES 0` inspects all nested values per command semantics, which can be expensive on large structures.

Do not run deep sampling in bulk during production peaks just to generate a report. Perform it in staging or with bounded sampling.

Create a key set **representative of real data**:

```text
1,000 small product DTOs
1,000 large product DTOs
1,000 user sessions
1,000 rate-limit counters
100 streams with realistic entry counts
...
```

Measure `MEMORY USAGE` across multiple samples, compute averages/percentiles per group, and multiply by projected cardinality.

### 3.3. Measuring via `used_memory` Delta

Another method:

1. Start with a clean test Redis instance configured like production.
2. Read `INFO memory` to record baseline `used_memory`.
3. Load a sufficiently large number of keys, e.g., 100,000 keys matching the workload.
4. Read `used_memory` again.
5. Divide the difference by the number of loaded keys.

\[
B_{\text{per-key, measured}}
\approx
\frac{M_{\text{after}}-M_{\text{before}}}{N_{\text{loaded}}}
\]

This measurement captures more overhead than payload size alone, though it is not an absolute constant: Redis allocator, object encoding, dict resizing, TTLs, key distribution, and version can alter results.

To examine encoding details and data complexity, combine `OBJECT ENCODING`, `MEMORY STATS`, and Redis server metrics on a suitable test dataset.

## 4. Redis Data Types Have Different RAM Characteristics

| Redis Type | RAM Drivers | Sizing Notes |
|---|---|---|
| String | Key/value sizes and object allocation | Many tiny keys have relatively high overhead |
| Hash | Field count, field/value sizes, encoding | Can be more compact than many String keys, though not always |
| List | Element count, element size, representation | Huge lists cause latency on wide range operations |
| Set | Member count and encoding | Each member carries overhead |
| Sorted Set | Member count, score, representation | Usually costs more than Set for the same payload |
| Stream | Entry payload, entry ID, retention, groups/PEL | Pending/consumer state and trim policy have impact |
| HyperLogLog | Representation and number of HLL keys | Estimates cardinality rather than storing all members |
| Geo | Data stored atop Sorted Sets | Account for key/member/score and geo queries |
| Bitmap | Highest offset range | Setting a bit at a very high offset can make the value large |

With a Redis Hash, a user profile containing 20 fields can have a different memory profile from 20 separate String keys. However, do not pack every record into one giant Hash just to reduce key overhead, as that can create a hot key and increase operation times.

### 4.1. Do Not Forget Key Cardinality

A key like `rate-limit:{userId}:{minute}` can generate millions of new keys per hour, even if each value is only a few bytes. If TTLs are forgotten or misconfigured, memory grows rapidly.

Estimate live keys:

\[
N_{\text{live}} \approx
\text{new keys per second}
\times
\text{average lifetime in seconds}
\]

An **idealized model** example:

```text
100 unique new keys/s
600-second TTL
=> roughly 60,000 live keys at steady state
```

Actual numbers depend on bursts, key reuse, traffic distribution, and expiration timing. Under CPU or memory pressure, Redis may not reclaim an expired key at the exact millisecond its TTL ends, though read commands still treat expired keys as absent per command semantics.

### 4.2. TTL and Eviction Are Not Uniform

- **TTL:** expiration based on time assigned to the key.
- **Eviction:** Redis proactively removing keys due to `maxmemory` policy.
- **Deletion:** the application calling `DEL`/`UNLINK`.
- **Persistence restore:** datasets can be restored with their corresponding TTL/expiration state.

Do not rely on eviction to fix missing TTLs in a workload that requires retaining data until an exact deadline. For critical data, choose policies that prevent unintended eviction.

## 5. From `used_memory` to Actual Node RAM

Common Redis metrics:

```redis
INFO memory
MEMORY STATS
INFO clients
```

In `INFO memory`, inspect:

| Field | Role |
|---|---|
| `used_memory` | Memory allocated by the Redis allocator per accounting |
| `used_memory_dataset` | Dataset memory per Redis accounting |
| `used_memory_overhead` | Overhead per Redis accounting |
| `used_memory_rss` | Process RSS reported by the OS |
| `used_memory_peak` | Peak allocation recorded |
| `maxmemory` | Threshold used for eviction/writes per policy |
| `mem_fragmentation_ratio` | Indicator of RSS/memory divergence; read alongside other metrics |
| `allocator_allocated` | Memory allocated by the allocator |
| `allocator_active` | Active allocator memory |
| `allocator_resident` | Resident allocator memory |
| `mem_not_counted_for_evict` | Certain buffers excluded from eviction memory accounting |

Field names depend on Redis version and allocator; do not assume every field is always present.

### 5.1. `maxmemory` Is Not the cgroup Limit

Redis may be configured with:

```conf
maxmemory 8gb
maxmemory-policy noeviction
```

Yet if the container memory limit is also exactly 8 GiB, it can OOM before Redis reaches `maxmemory` due to:

- Memory fragmentation.
- Client/replication/AOF buffers.
- Copy-on-write during background save/rewrite.
- The RDB/AOF child process.
- Container page cache and memory accounting.
- Other processes if sharing the memory cgroup.

`maxmemory` must be configured with **headroom** relative to the RAM available from the OS/container, based on real measurements.

### 5.2. RSS, Fragmentation, and Shared Pages

A Redis parent process having RSS higher than `used_memory` can happen normally. When `fork()` creates a child process, many physical pages are initially shared between parent and child. Therefore:

- Do not mechanically sum parent RSS + child RSS as if every page were separate.
- Do not look only at parent RSS and conclude the cgroup has spare memory.
- Measure **`memory.current`/working set, OOM events, and swap**, alongside Redis `INFO`, to understand peak memory.
- Check memory after background jobs finish, not just at steady state.

In Kubernetes, `OOMKilled` can occur even when Redis has not reported `OOM command not allowed`: those are two distinct limits.

## 6. Copy-on-Write (COW): The Often Forgotten RAM Region

RDB `BGSAVE` and AOF `BGREWRITEAOF` can spawn a child process via `fork()`. Initially parent and child share memory pages; when the parent modifies a page that the child still needs to read in its old form, the OS must maintain two physical copies.

```text
Immediately after fork:
 parent ----+
            +---- memory page P
 child  ----+

After a write:
 parent -------- memory page P' (new)
 child  -------- memory page P  (old)
```

Cost depends on:

- Dataset size.
- Number of **memory pages modified** while the child is running.
- Duration of the background job.
- Write rate and distribution of updated keys.
- Redis allocator and OS behavior.
- Child storage throughput and CPU.

**There is no fixed rule that “COW is always 50% of the dataset” or “BGSAVE always needs double RAM.”** Measure under production-like load.

### 6.1. Why Slow Disks Increase Peak RAM

```text
Disk writes snapshot slowly
      |
      v
RDB/AOF child stays alive longer
      |
      v
Parent keeps modifying data
      |
      v
More pages undergo copy-on-write
      |
      v
Memory pressure increases
```

Thus, storage capacity and memory capacity are linked. A slow disk not only prolongs background jobs but also raises the chance of OOM under heavy write loads.

### 6.2. Observing Actual COW

```redis
INFO persistence
INFO stats
```

Look for these fields when supported by your Redis version:

```text
rdb_last_cow_size
aof_last_cow_size
rdb_last_bgsave_time_sec
aof_last_rewrite_time_sec
latest_fork_usec
```

These fields typically record the most recent job; do not interpret `rdb_last_cow_size` as total current cgroup memory usage at read time. To choose a RAM limit, measure the **concurrent peak cgroup memory** during background jobs under the target workload.

## 7. Budgeting RAM for a Redis Primary

A mental formula:

\[
M_{\text{required}} \gtrsim
M_{\text{steady resident}}
+
M_{\text{incremental COW peak}}
+
M_{\text{other non-overlapping pressure}}
+
M_{\text{safety margin}}
\]

Measure components so you avoid **double-counting** memory already included in RSS/cgroup metrics.

For an initial budget, break down:

```text
A. Dataset / projected Redis used_memory
B. Allocator fragmentation + resident overhead
C. Buffers: client, replication, AOF, command queues
D. Incremental COW peak while persistence runs
E. OS/page cache and background processes
F. Reserve for growth, bursts, and failover
```

Do not apply one universal RAM multiplier to every system. A read-mostly cache with little COW has a very different profile from a write-heavy Stream/ZSet with frequent AOF rewrites.

### 7.1. Size Per Node

In Redis Cluster:

```text
Primary A holds 40% of data
Primary B holds 30% of data
Primary C holds 30% of data
```

A 24 GiB total cluster RAM figure does not prove 8 GiB per primary is enough; Primary A may need more due to uneven data distribution or hot slots.

Measure:

- `used_memory` per primary.
- Peak RAM per primary.
- Replication/resharding events per node.
- Hot keys and large values.
- Per-shard growth forecasts.

**Cluster capacity is bounded by the hottest/weakest node**, not just total cluster RAM.

## 8. Replicas: Their Cost Is Not Just a Few Percent

A replica generally needs to hold a full copy of its primary's dataset and manage connections, buffers, and persistence as configured.

For example:

```text
1 primary + 2 replicas
```

is not “one dataset and two lightweight nodes.” If each node holds a full copy, memory and storage resources must be provisioned across **all three data nodes**.

A budget model:

\[
M_{\text{cluster data nodes}}
\approx
M_{\text{one role-equivalent node}}
\times
(1 + \text{replica count})
\]

This is only a rough scale when nodes are similarly configured. Replicas can have different write-apply, buffer, resync, and persistence peaks than the primary.

### 8.1. Full Resynchronization Can Create Peaks

When a new replica joins or stays disconnected too long, it may need a full resync. Depending on Redis version/config, this consumes:

- CPU/IO to create or stream a snapshot.
- Network bandwidth.
- Replication backlog/buffers.
- Memory pressure while the primary continues accepting writes.
- Disk or memory on the replica while loading the dataset.

A system with just enough resources for steady state may lack the capacity **to recover from failures**.

### 8.2. Sentinel Nodes Also Need Resources and Independence

Sentinel is lighter on dataset memory than data nodes, yet still needs:

- CPU/RAM for the process.
- Network access to data nodes and peer Sentinels.
- File/config write permissions.
- Monitoring/logging.
- Placement across independent fault domains.

Running three Sentinels on the same host may suffice for a lab, but it does not provide the infrastructure fault tolerance of three independent nodes.

## 9. Redis CPU: Size by Command Type, Not Just Ops/s

Redis executes commands across paths whose cost depends heavily on data size and command mix.

Example:

```redis
GET small:key
SET small:key small-value
HGET user:42 name
ZRANGE leaderboard 0 100
SMEMBERS huge:set
EVAL long-script ...
```

These commands do not have the same CPU cost.

CPU drivers include:

- Value and response sizes.
- Algorithmic complexity of the command.
- Lua script loops.
- RDB compression/serialization.
- AOF rewrites.
- TLS encryption/decryption.
- Network packet processing.
- Key expiration and eviction.
- Replication/resharding.
- Background tasks/threaded I/O depending on Redis version.

“Redis handles 100,000 GET/s” is no guarantee it can handle 100,000 ZSet range queries/s with large payloads.

### 9.1. Server Command Latency

Useful observation commands:

```redis
INFO cpu
INFO commandstats
SLOWLOG GET 20
LATENCY LATEST
```

Combine:

- CPU usage per Redis instance/container.
- Commands/sec per type.
- Command execution latency.
- Application-side p95/p99 response latency.
- Persistence/replication load.
- Redis event loop/I/O metrics applicable to your version.

`SLOWLOG` generally excludes time callers spend waiting on the network or connection pool; so if Java p99 is high while `SLOWLOG` is empty, inspect client queues, pool waits, and the network.

### 9.2. Cores and Resource Throttling

Redis typically executes its main command-processing path sequentially per data node, even though certain I/O tasks support threads. Assigning very high CPU core counts to a single Redis process does not guarantee linear command throughput scaling.

In Kubernetes, low CPU quotas can cause throttling and tail latency spikes. Measure:

```text
container CPU usage
CPU throttling time/periods
Redis ops/s
Redis command latency
application p99
```

Consider scaling node specs, sharding, or optimizing workloads when Redis saturates, rather than merely increasing client connections.

## 10. Network: Two-Way Commands and Responses

Many network estimates only count commands:

```text
10,000 GET/s
```

without accounting for data transfer.

A rough formula:

\[
BW_{\text{app↔redis}} \approx
Q_{\text{ops/s}} \times
(B_{\text{request}} + B_{\text{response}})
\]

Illustrative example:

```text
10,000 operations/s
Average request: 0.5 KiB
Average response: 1.5 KiB

Total payload traffic ≈ 20,000 KiB/s
                      ≈ 19.5 MiB/s
                      ≈ 164 Mbit/s
```

This figure excludes TCP/TLS framing, retransmissions, Redis protocol overhead, replication, metrics, and other overhead.

### 10.1. Read-Heavy vs. Write-Heavy Network Profiles

- `GET` returning large values: high server → client bandwidth.
- `SET` with large values: high client → server bandwidth.
- Redis replicas: primary → replica replication streams.
- Redis Cluster: clients connect to multiple nodes, and resharding transfers keys between nodes.
- Pub/Sub: one message can fan out to many subscribers.
- Stream consumers: batch/payload deliveries and ACK commands generate bidirectional traffic.

Do not look at a nominal 1 Gbit/s link and assume Redis gets the full 1 Gbit/s if service meshes, TLS, overlay networks, and other apps share it.

### 10.2. Latency by Network Distance

Small Redis commands have very fast server execution; **network RTT** can dominate application-observed latency.

Example:

```text
App and Redis in same zone: low RTT
App cross-zone: higher RTT
App cross-region: RTT can be substantially higher
```

Measure RTT in your actual infrastructure zones rather than applying a generic cloud RTT figure.

If an HTTP request calls Redis sequentially 20 times, even a small RTT per `GET` adds up to significant total latency. Batching, pipelining, or better data modeling often helps more than adding Redis nodes.

## 11. Persistence: RAM and Disk Go Together

If Redis enables RDB and/or AOF, storage needs more than just the current file sizes.

### 11.1. RDB Snapshots

`BGSAVE` may require:

- Space for the snapshot file being written.
- Space for the previous snapshot file until replacement completes.
- CPU for serialization/compression.
- Disk write throughput.
- Fork/COW memory headroom.

### 11.2. AOF and Rewrites

When AOF is enabled:

```conf
appendonly yes
appendfsync everysec
```

Redis appends mutations to the AOF according to policy. AOF rewrite produces a more compact representation, requiring:

- Active/base/incremental AOF components.
- New files written during rewrite.
- Disk bandwidth and fsync capacity.
- Fork/COW memory.
- Temporary space and metadata/manifest, especially with multi-part AOF in Redis 7+.

**Never take `aof_current_size` and set the disk limit equal to that exact number.** During rewrites or backups, old and new files coexist, and page cache adds pressure as well.

### 11.3. A Disk Budget Formula

\[
D_{\text{needed}} \approx
D_{\text{active persistence}}
+
D_{\text{temporary rewrite/snapshot peak}}
+
D_{\text{local backups, if any}}
+
D_{\text{logs and growth}}
+
D_{\text{margin}}
\]

Values must be measured for your Redis version, policy, and data structures. Do not treat a “2× RDB” or “3× AOF” multiplier as a guarantee.

### 11.4. Disk Throughput Impacts p99

If slow disks prolong rewrites, COW memory grows and Redis experiences pressure. With AOF `appendfsync always` or `everysec`, fsync delays can also affect write latency and durability windows.

Collect:

```redis
INFO persistence
INFO stats
```

along with OS metrics:

```text
disk used/free bytes
free inodes
read/write throughput
IOPS
I/O latency
filesystem errors
cgroup memory/page cache
```

On managed Redis, equivalent metrics are typically exposed via provider monitoring rather than SSHing into the host.

## 12. Spring Data Redis Drivers: Distinguish Lettuce and Jedis

Inside the Java application, the driver also consumes:

- Memory for connections and command buffers.
- Threads/event loops.
- Sockets/file descriptors.
- Serialization/deserialization buffers.
- Connection pool objects.
- CPU for TLS/network handling.
- Pending requests and retry queues.

### 12.1. Lettuce: Shared Native Connection and Multiplexing

Lettuce, built on Netty, generally allows normal commands to share **a single thread-safe native connection**.

```text
HTTP thread A -- GET  -->+
HTTP thread B -- GET  -->+-- Lettuce shared connection -> Redis
HTTP thread C -- SET  -->+
```

That does **not** mean Spring's `RedisConnection` wrapper can be shared arbitrarily across threads, nor that blocking, transactional, or Pub/Sub operations use the same mechanism.

Operations such as `BLPOP`, blocking Streams, subscriptions, and transactions typically require dedicated connection management as supported by the client/factory.

### 12.2. Jedis: Pools Play a Different Role

With Jedis, connection objects should not be shared concurrently across threads arbitrarily. Pooling allows sockets to be borrowed and released safely across callers.

Hence a setting like:

```yaml
spring:
  data:
    redis:
      jedis:
        pool:
          max-active: 16
```

directly governs borrowing on synchronous Jedis paths, whereas a Lettuce pool setting might not affect regular `GET` calls at all if the factory uses a shared native connection.

**Do not size pools equal to the number of HTTP workers without understanding the driver's connection semantics.**

## 13. Calculating a Deployment-Wide Connection Budget

Suppose you have:

```text
12 Spring Boot pods
Each pod:
  1 Lettuce shared/native connection for regular ops
  1 dedicated pool with max 20 connections
  2 long-lived Redis Streams subscriptions
```

Ceiling for pooled dedicated connections:

\[
12 \times 20 = 240
\]

You must also add shared/long-lived connections, other pools/factories, client/admin/monitoring connections, rolling deployments, Cluster node discovery, and reconnect bursts.

This is a **theoretical configuration ceiling**, not the number of sockets open at all times.

### 13.1. Connection Budget Template

| Connection Source | Instances | Max Connections/Instance | Total Estimate |
|---|---|---|---|
| API instances | 12 | 20 pooled | 240 |
| Worker instances | 4 | 8 pooled | 32 |
| Shared native connections | Per factory/node | Per client | Measure |
| Streams/PubSub listeners | Per consumer | Per topology | Measure |
| Monitoring/exporters | Per deployment | Per tool | Reserve |
| Rollout surge | Old + new pods | Per config | Reserve |
| Other applications | n | n | Inventory required |

Redis `CONFIG GET maxclients` and OS file descriptor limits are constraints to verify against. Each client connection consumes memory buffers; raising `maxclients` does not create extra CPU capacity.

### 13.2. `INFO clients` Is Not Concurrent Requests

```redis
INFO clients
CLIENT LIST
INFO stats
```

This reveals `connected_clients`, `blocked_clients`, and `rejected_connections`. However:

- One shared Lettuce connection can carry many in-flight commands.
- Many idle pooled connections still increase `connected_clients`.
- `blocked_clients` is Redis server state, **different** from Java callers waiting to borrow from a pool.
- On Redis Cluster, inspect **each node**.

Therefore, correlate server metrics with client/pool metrics.

## 14. Spring Boot Configuration for Lettuce with Bounded Pooling

Example for Spring Boot 3.x:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: redis-primary.internal
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

Dependency when using Commons Pool 2:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.apache.commons:commons-pool2'
}
```

Property names and defaults depend on Spring Boot version. If using a custom factory bean, some Boot properties may not apply automatically; verify the actual `RedisConnectionFactory` bean.

### 14.1. Configuration Meaning

| Property | Controls |
|---|---|
| `connect-timeout` | Connection establishment deadline |
| `timeout` | Command deadline per client/Boot |
| `pool.enabled` | Enables pooling as supported by Boot/client |
| `max-active` | Limit of active connections in that pool |
| `max-idle` | Idle connections retained |
| `min-idle` | Target minimum idle connections |
| `max-wait` | Wait time to borrow when pool is exhausted |

`max-wait` is **not** command timeout. A borrow failure can occur before any Redis command is even sent to the server.

### 14.2. Pooling Does Not Automatically Increase Throughput

With a Lettuce shared connection, increasing `max-active` may **not change** ordinary `GET`/`SET` paths at all. Conversely, if most connections are tied up in `XREAD BLOCK`, the pool can exhaust quickly.

To tune, measure:

```text
pool active / idle / waiters
borrow wait duration
Redis commands/s
Redis command p95/p99
application endpoint p95/p99
Redis CPU/network
```

Do not look solely at `connected_clients`.

## 15. Netty Event Loops and Lettuce Native Memory

Lettuce uses Netty and client resources to manage I/O. Within a JVM, there may be:

- I/O event-loop threads.
- NIO/direct buffers.
- Command queues/pending futures.
- DNS/TLS buffers.
- Connection state and topology refresh tasks.
- Thread-local/cache/allocator overhead.
- Metrics/tracing metadata.

An application with `-Xmx2g` will not necessarily use only 2 GiB of RAM, because **JVM process memory = heap + non-heap + native**.

Creating multiple `RedisClient`/`LettuceConnectionFactory` instances without sharing or properly closing resources can inflate threads, connections, and buffers.

### 15.1. Do Not Create a Redis Client Per Request

Architectural mistake:

```java
@GetMapping("/products/{id}")
public String get(@PathVariable String id) {
    // Creating a new RedisConnectionFactory/RedisClient per HTTP request?
    // -> leaks sockets, threads/resources, and unnecessary connections.
}
```

Normally declare `RedisConnectionFactory` and `RedisTemplate` as application-scoped Spring beans and reuse them appropriately.

If multiple factories are needed for cache, Streams, and Pub/Sub, account for their combined resource usage rather than letting each factory spin up oversized event-loop thread pools needlessly.

### 15.2. Pending Commands and Memory Pressure

A dangerous failure loop:

```text
Application generates 100,000 Redis commands rapidly
Redis server can only process 10,000/s
      |
      v
Client pending queue grows
      |
      v
Memory / futures / buffers grow
      |
      v
Timeouts + retries
      |
      v
Even more pending commands
```

Increasing connections does not fix the root cause when arrival rate exceeds service capacity. Apply **backpressure or concurrency limits** at the source, bounded retries, and bounded queues.

## 16. Sizing Spring Boot Application Resources

Not only Redis Server needs RAM and CPU. A Spring Boot process using Redis also needs:

\[
M_{\text{JVM process}} \approx
M_{\text{heap}}+
M_{\text{metaspace}}+
M_{\text{code cache}}+
M_{\text{thread stacks}}+
M_{\text{direct/native}}+
M_{\text{other}}
\]

This is an accounting model; actual components should be measured with JVM/OS tools to avoid double-counting.

### 16.1. Heap

The heap holds:

- DTOs/values deserialized from Redis responses.
- HTTP request/response objects.
- In-process Java caches if present.
- Reactor publishers/futures.
- Queues and batch buffers.
- Data transformation objects.
- Connection/pool management objects.

If Redis returns 100 KiB of JSON, the resulting Java object graph after deserialization can exceed 100 KiB. Do not size app memory solely from network payload bytes.

### 16.2. Thread Stacks

Spring MVC, background workers, Pub/Sub listener executors, and scheduler threads all consume stack memory.

An example **that is not a constant across all JVMs**:

```text
400 threads × ~1 MiB stack reservation
=> roughly 400 MiB virtual stack address space
```

Actual committed physical memory can differ from reserved virtual stack space depending on JVM/OS and stack depth. Do not multiply `-Xss` by thread count and treat it as exact RSS; measure actual native memory and thread stacks.

### 16.3. Native/Direct Memory

Netty, TLS, NIO, compression, JNI, and native libraries consume memory outside the Java heap. Setting `-Xmx` equal to the container memory limit risks OOM.

Illustrative example:

```text
Pod memory limit = 4 GiB
JVM -Xmx        = 3.0 GiB
```

The remaining 1 GiB **may or may not be enough**, depending on thread count, direct buffers, metaspace, code cache, agents, and workload. There is no fixed safe ratio for every Spring Boot service.

To size accurately, measure `memory.current`/cgroup, JVM heap/non-heap, GC, thread counts, and Netty/direct memory under peak load.

### 16.4. CPU and GC

If Redis returns many large objects or code deserializes JSON continuously, Java-side CPU and Garbage Collection can become the bottleneck even when Redis command latency is low.

Monitor:

```text
JVM process CPU
GC pause p95/p99
allocation rate
heap occupancy
thread utilization
event loop blocking
Redis command duration
end-to-end API duration
```

Do not scale up Redis node sizes to fix what is actually a Jackson serialization or Java GC problem.

## 17. Spring MVC: HTTP Threads Do Not Equal Redis Connections

In Spring MVC:

```text
Tomcat/Servlet worker
      |
      v
Service
      |
      v
StringRedisTemplate -> Redis
      |
      v
Thread waits for result
```

If each HTTP request calls Redis multiple times, a single request generates multiple commands. HTTP worker thread count bounds request concurrency, yet **does not require each thread to hold a dedicated Redis TCP connection** when using Lettuce's shared native connection.

### 17.1. Calculating Command Demand from HTTP Traffic

Example:

```text
HTTP throughput:            1,000 requests/s
Redis commands per request: 4
=> Redis demand:            4,000 commands/s
```

If the 4 commands run sequentially, the request incurs roughly four times the network/command latency. If executed concurrently, in-flight concurrency and memory buffers change.

Measure command mix per endpoint rather than applying a single average `Redis ops/s` figure to everything.

### 17.2. Thread Limits Are Also Backpressure

Raising Tomcat worker threads from 200 to 1,000 allows more concurrent requests to hit Redis, the database, and payment gateways simultaneously. If downstream lacks capacity, p99 can worsen.

When sizing Spring MVC, evaluate together:

- HTTP concurrency/queueing.
- Thread count.
- Redis connection semantics.
- DB pool size.
- Retry policy.
- Load balancer timeouts.
- Request deadlines.

## 18. WebFlux and `ReactiveRedisTemplate`: Size In-Flight Load, Not Just Threads

Reactive Redis supports many asynchronous operations without tying up a blocking thread per command. That does not mean resources are infinite.

Risky example:

```java
return Flux.fromIterable(productIds)
        .flatMap(id ->
            reactiveRedis.opsForValue()
                .get("cache:product:" + id)
        );
```

If the list is very large and many HTTP requests run concurrently, total in-flight commands can skyrocket.

### 18.1. Explicit Concurrency Limits

```java
public Flux<String> getProducts(List<String> ids) {
    int redisConcurrency = 16;

    return Flux.fromIterable(ids)
        .flatMap(
            id -> reactiveRedis.opsForValue()
                .get("cache:product:" + id),
            redisConcurrency
        );
}
```

The number 16 is only an example. Calculate:

```text
16 concurrent Redis operations / request
× 100 requests in-flight / pod
× 12 pods
= modeled upper bound of up to 19,200 in-flight operations
```

This multiplication gives a **fan-out upper bound at a point in time** if every request reaches full concurrency—not throughput or Redis connection count. Reactor scheduling, shared clients, and upstream speed affect reality.

Do not set `flatMap(concurrency=16)` and assume the entire deployment only ever executes 16 concurrent commands. If a pod-level cap is needed, use a shared bulkhead/semaphore or admission control with explicit overload behavior.

### 18.2. Backpressure and Large Payloads

Reactive backpressure regulates item emission downstream, yet a command like `SMEMBERS huge:set` still produces a massive response before Java processes items one by one. To bound memory, use paginated commands/data models, `SCAN`, ranges, or chunking.

### 18.3. Never `.block()` on the Event Loop

With WebFlux, calling `.block()` on an event-loop thread stalls I/O processing and raises latency under load, skewing Redis measurements.

Measure Redis RTT separately from event-loop blocking/CPU. Adding Redis connections cannot rescue a blocked event loop.

## 19. Using Little's Law to Sanity-Check Concurrency

In a stable system:

\[
L \approx \lambda \times W
\]

Where:

- \(L\): average number of concurrent operations in the measured system.
- \(\lambda\): operations completed per second.
- \(W\): average time an operation spends in that system.

Example:

```text
3,000 Redis operations/s
Average application-observed Redis latency = 15 ms
```

Then:

\[
L \approx 3000 \times 0.015 = 45
\]

Meaning on average roughly 45 Redis operations are in-flight or waiting within the measured boundary, assuming steady state and consistent counting.

**Do not conclude you need a pool of 45 connections**:

- Lettuce shared connections multiplex.
- Jedis dedicated pool occupancy depends on borrow duration.
- Averages hide bursts and p99 tail behavior.
- Commands may wait on pools, Netty queues, network, or the Redis server.
- Once saturated, raising concurrency can increase \(W\) without increasing \(\lambda\).

Little's Law sanity-checks measurements; it does not replace benchmarking.

## 20. Pool Sizing: Avoid “`max-active` Equals HTTP Threads”

A better model:

```text
Pool active demand
    = operations holding dedicated connections
```

Measure:

- Blocking consumers (`BLPOP`, `XREAD BLOCK`).
- Concurrent transactions/session callbacks.
- Jedis callers needing to borrow.
- Dedicated Lettuce operations per configuration.
- Connection hold durations.
- Pool borrow waiters.
- Peak and failure-mode occupancy.

### 20.1. Why Blocking Commands Are Special

```redis
BLPOP queue:jobs 0
```

can wait indefinitely. If 20 workers each hold a dedicated connection, a pool with `max-active=10` leaves 10 workers blocked at borrow time before ever sending a command to Redis.

You must:

- Count blocking workers.
- Set bounded `BLOCK` timeouts.
- Ensure command timeouts exceed valid blocking wait times where needed.
- Separate pools/factories for blocking workloads if they contend with the request path.
- Monitor Redis `blocked_clients` and Java pool waiters separately.

### 20.2. Pub/Sub Also Uses Long-Lived Connections

`RedisMessageListenerContainer` holds long-lived subscription connections and a callback executor. Adding listener threads does not imply adding one Redis connection per thread. Slow handlers can create Java backlogs even while the Redis subscription remains healthy.

Distinguish:

```text
Subscription socket
Listener dispatch executor
Business handler concurrency
Downstream DB/API capacity
```

Optimize the actual bottleneck instead of raising pool sizes randomly.

## 21. Cache-Miss Fallback and Load Amplification Risk

A cache is only beneficial if the source of truth does not collapse when Redis is lost or cold.

Example:

```text
Normal:
  10,000 product reads/s
  cache hit ratio = 95%
  DB reads ≈ 500/s

When Redis is lost:
  10,000 reads/s must fall back
  DB reads can surge up to 10,000/s
```

That is **up to a 20× spike** under these assumptions if every request falls back without coalescing, rate limiting, or secondary caches.

If the database only sustains 2,000 reads/s within latency SLOs, the system can go down even though Redis was “an optional cache.”

### 21.1. Reserve Fallback Capacity

Design at least:

- Cache hit ratio tracking per resource/endpoint.
- DB capacity testing under elevated cache miss rates.
- Bounded fallback concurrency.
- Request coalescing/single-flight when many requests miss the same key.
- TTL jitter or background refresh to prevent synchronized expirations.
- Circuit breakers/bulkheads for Redis or DB failures.
- Explicit failure policies: serve stale data, degrade gracefully, shed load cleanly, or query directly.

**Never increase the Redis client pool to fix a database overloaded by fallbacks.**

### 21.2. Cache Warm-Up Also Needs a Budget

After a deploy or restore:

```text
Cold cache
    |
    v
Many requests miss
    |
    v
Database load rises
    |
    v
Application repopulates cache
    |
    v
Redis write throughput spikes
```

Both DB reads and Redis writes burst simultaneously. Capacity tests run only against a warm cache will underestimate startup resource needs.

## 22. Redis Cluster: Resources by Hash Slot, Hot Shards, and Failover

Redis Cluster distributes 16,384 hash slots across primaries. Total capacity depends on key and traffic distribution.

```text
Primary A:  35% memory, 60% operations
Primary B:  33% memory, 25% operations
Primary C:  32% memory, 15% operations
```

Even though memory looks balanced, Primary A is a CPU/network hotspot.

### 22.1. Hash Tags Can Create Hot Slots

Example:

```text
cart:{customer-42}:items
cart:{customer-42}:total
```

sharing a slot is useful for multi-key transactions.

However:

```text
cache:{ALL}:product:1
cache:{ALL}:product:2
...
```

forces all product keys into one slot, defeating Cluster load distribution.

Choose hash tags matching the true atomic business aggregate rather than a global tag just to make `MGET` convenient.

### 22.2. When a Primary Is Lost

In a Cluster with replicas, failover promotes a replica to primary. During that window:

- Clients reconnect/reroute.
- Command retries may spike.
- Replication may have lagged.
- CPU/network on surviving nodes may rise.
- Warm-ups/resharding can add extra traffic.
- Some acknowledged writes may not have reached the new primary.

Capacity testing should cover **degraded mode**, not only steady state. A cluster that barely meets steady-state load may become unstable during failover.

### 22.3. Scaling Out Does Not Solve Every Command

Adding primaries helps distribute keys and throughput, but:

- Multi-key commands usually require same-slot placement.
- Lua scripts operate within node/slot boundaries.
- Hot keys do not split across nodes automatically.
- Clients need topology discovery/redirects.
- Rebalancing/resharding consumes network and CPU.
- Data and connection distributions are not guaranteed to balance immediately.

Do not compute Cluster capacity as single-primary throughput × primary count without benchmarking real key distributions.

## 23. Sentinel: Resources for Failover and Replica Promotion

In a Sentinel topology, when a primary goes down:

```text
Primary down
  -> Sentinel detects / reaches quorum
  -> replica promoted
  -> clients discover new primary
  -> application reconnects
```

Beyond Redis data nodes, you need:

- A healthy Sentinel quorum.
- Network connectivity among Sentinels, data nodes, and applications.
- Driver configuration to query for the new primary.
- Connection, timeout, and retry budgets.
- Enough RAM/CPU/IO on replicas to take over as primary.
- Testing for when the old primary returns and resyncs.

**Do not provision weaker hardware for replicas thinking they only receive data.** After failover, a replica must carry the primary's full write workload.

## 24. RDB/AOF, Durability, and Storage Choices

Your resource plan must align with data-loss targets:

| Mode | Benefit | Cost/Risk |
|---|---|---|
| No persistence | Reduces background disk work | Node data is not recovered after restart |
| RDB | Compact snapshots | Fork/COW, disk I/O, writes since last snapshot can be lost |
| AOF `everysec` | Logs changes with periodic fsync | Disk/fsync, rewrite/COW, does not guarantee exact 1-second RPO on all crashes |
| AOF `always` | More frequent fsync requests | Disk latency/throughput can suffer |
| Replicas | Data copies and failover | Extra nodes; replication is usually asynchronous |

`WAIT` or `min-replicas` settings affect write-loss exposure and availability, yet **do not turn Redis into a distributed durable transaction system**.

For payment or order data with strict invariants, Redis can act as a supporting cache/idempotency layer while the authoritative source resides in storage with appropriate transaction guarantees.

## 25. Choosing CPU/RAM Requests and Limits on Kubernetes

Kubernetes has two common resource settings:

- **Requests:** inform the scheduler how much resource to reserve for a pod.
- **Limits:** enforce runtime limits via containers/cgroups; exceeding memory limits triggers OOM-kill, while CPU quotas cause throttling.

Illustrative example **for a Redis container**, not a complete production manifest:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-cache
spec:
  serviceName: redis-cache
  replicas: 1
  selector:
    matchLabels:
      app: redis-cache
  template:
    metadata:
      labels:
        app: redis-cache
    spec:
      containers:
        - name: redis
          image: redis:7.2.5-alpine
          ports:
            - containerPort: 6379
          command:
            - redis-server
            - --maxmemory
            - 5gb
            - --maxmemory-policy
            - allkeys-lru
          resources:
            requests:
              cpu: "500m"
              memory: "6Gi"
            limits:
              cpu: "2"
              memory: "10Gi"
```

This is an **educational example**, omitting persistent volumes, authentication, network policies, readiness/liveness probes, anti-affinity, and HA. Do not deploy it verbatim to production.

These numbers are not universal rules: `maxmemory 5gb`, request `6Gi`, and limit `10Gi` must be replaced with measured figures. Under write-heavy AOF/RDB workloads, COW overhead could make `10Gi` insufficient.

### 25.1. Why Redis Usually Needs StatefulSet/PVC or Managed Redis

If persistence and recovery of on-disk state are required, losing a Kubernetes pod can wipe ephemeral filesystems. You need:

- `PersistentVolumeClaim` and an appropriate storage class.
- Off-node backup strategies.
- Restore testing when pods or nodes are replaced.
- Security/ACL/TLS.
- Pod placement/anti-affinity across fault domains.
- Monitoring of storage latency and free space.
- Upgrade and rolling failover procedures.

Fully rebuildable Redis caches may use different options, but **never call Redis stateful and durable without a clear storage lifecycle**.

### 25.2. JVM App Requests and Limits

Example **application pod**:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
  limits:
    cpu: "2"
    memory: "3Gi"
```

Also configure JVM heap, direct memory, and threading for the container, and measure GC and native memory under peak traffic.

Do not set `-Xmx3g` in a container with a `3Gi` limit and assume room remains for thread stacks, metaspace, and Netty. Reserve non-heap/native headroom based on observation.

### 25.3. Rolling Deployments Temporarily Multiply Load

If 12 pods are running and the rolling strategy allows 3 extra pods during rollout:

```text
Old pods: 12
Concurrent new pods: 3
=> 15 pods connecting to Redis
```

Connection counts, warm-up traffic, authentication handshakes, and cache requests all increase. Capacity plans must account for **max surge**, not just desired replicas.

## 26. Step-by-Step Example of Calculating a Redis RAM Budget

Suppose a product cache system has the following **assumed illustrative numbers**:

```text
Current key count:                      3,000,000
Avg memory/key measured in staging:     1.4 KiB
Data growth factor:                     1.5x
Observed RSS/used_memory ratio:         1.20
COW peak during BGSAVE test:            2 GiB
OS/page-cache pressure reserve:         1 GiB
Additional safety margin:               20%
```

### Step 1 — Logical RAM for Current Dataset

\[
M_{\text{current}}
= 3{,}000{,}000 \times 1.4\ \text{KiB}
= 4{,}200{,}000\ \text{KiB}
\approx 4.0\ \text{GiB}
\]

### Step 2 — Projected Growth

\[
M_{\text{future}}
\approx 4.0 \times 1.5
= 6.0\ \text{GiB}
\]

This figure is a **sample-based projection**; add or measure other memory overheads if not yet reflected in the sample.

### Step 3 — Estimate Steady-State RSS

\[
M_{\text{RSS steady}}
\approx 6.0 \times 1.20
= 7.2\ \text{GiB}
\]

The `RSS/used_memory` ratio can shift as dataset, allocator, and workload evolve. This is an estimate, not a constant.

### Step 4 — Add Observed Peak Pressures

```text
Steady-state RSS projection:   7.2 GiB
Incremental COW peak:          2.0 GiB
Other pressure allowance:      1.0 GiB
------------------------------
Subtotal:                     10.2 GiB
```

Some OS/page cache usage may already be reflected in measured cgroup metrics; this illustrative model assumes this is **non-overlapping incremental pressure**. When using production metrics, avoid double-counting.

### Step 5 — Reserve a Safety Margin

\[
M_{\text{budget}}
\approx 10.2 \times 1.2
= 12.24\ \text{GiB}
\]

You might pick a container/node allocation like **14–16 GiB** for extra headroom, yet **do not treat this as a final deployment conclusion** until benchmarks, storage, and replication checks pass.

### Step 6 — Choose `maxmemory` Intentionally

If projected dataset `used_memory` is around 6 GiB, setting `maxmemory` right up against the container limit is unsafe. A starting point could be `maxmemory` around 6.5–7 GiB, **provided the eviction policy and measured overheads permit**, then verify via testing.

Questions to answer:

- If `maxmemory` is reached early, is cache eviction acceptable?
- If the policy is `noeviction`, how does the application handle write errors?
- Does the COW peak under a write surge exceed the measured 2 GiB?
- Do replicas experience a similar peak?
- Could slow disks keep the child process alive longer?
- Could the cgroup OOM during failover or full resync?

This is an **assume → measure → adjust** sizing workflow, not an exact formula deriving instance types from key counts alone.

## 27. Example CPU and Network Budget Calculation

Suppose a Redis primary receives:

```text
GET:        8,000/s
SET:        1,500/s
HGET:         400/s
INCR:         100/s
-------------------
Total:     10,000 commands/s
```

If average bidirectional payload for this command mix is roughly 2 KiB, network payload traffic is ~19.5 MiB/s as in the earlier example.

However, **you cannot deduce CPU cores automatically** from 10,000 commands/s. Benchmark latency and CPU using the exact command mix and data.

A practical method:

1. Run a representative workload at 2,500 ops/s.
2. Record CPU, memory, throughput, and p95/p99.
3. Step up to 5,000, 10,000, and 15,000 ops/s.
4. Note where p99 or error rate breaches the SLO.
5. Repeat while `BGSAVE`/AOF rewrite runs.
6. Repeat during replica full resync or failover.
7. Set your operating target **below the saturation point** with clear headroom.

### 27.1. Do Not Scale Linearly by Assumption

If 5,000 ops/s uses 30% CPU, 20,000 ops/s will not necessarily use exactly 120% CPU because:

- Payloads and command mixes can change.
- Cache hit/miss rates and TTLs differ.
- Network/TLS overhead is non-linear.
- Disk persistence creates bursts.
- Queueing and scheduler effects accelerate near saturation.

Use CPU interpolation only as a rough guide, never in place of real load tests.

## 28. Sizing Application Resources from Redis Responses

A 2 KiB Redis response can expand into a much larger Java object graph after deserialization. When the app processes many commands concurrently:

```text
Number of in-flight responses
× average decoded object footprint
≈ application live memory from Redis results
```

This is one component of total JVM heap, not a complete heap model.

If a pipeline fetches 10,000 values, each 4 KiB on the wire:

```text
Response bytes roughly 40 MiB before overhead
```

Java objects, `List<Object>`, deserializer buffers, and application transformations can push peak heap usage much higher.

Smaller batches can save heap and cut GC p99 even when total command count stays the same.

### 28.1. Bound Batches and Concurrency Before Adding RAM

Tuning options:

- Paginate or range-query instead of loading entire Sets/Lists/Streams.
- Bound pipeline batch sizes.
- Cap Reactor `flatMap` concurrency.
- Use bounded queues for background tasks.
- Avoid materializing full response lists when incremental processing is possible.
- Monitor allocation rate and GC.
- Choose clean key/value serialization without bloated metadata payloads.

Increasing JVM heap is sometimes necessary, but eliminating unnecessary data footprint is usually cheaper and safer.

## 29. Minimum Metrics for a Capacity Plan

### 29.1. Redis Server

```redis
INFO memory
INFO clients
INFO stats
INFO commandstats
INFO cpu
INFO persistence
INFO replication
```

Metrics:

| Category | Metrics |
|---|---|
| Memory | `used_memory`, RSS, peak, allocator, fragmentation |
| Client | `connected_clients`, `blocked_clients`, `rejected_connections` |
| Commands | ops/s, per-command stats, slowlog |
| Network | input/output bytes/sec or equivalent |
| CPU | user/system CPU, host/container throttling |
| Persistence | `BGSAVE`/rewrite duration, fork latency, COW, delayed fsync |
| Replication | link status, offsets, full sync, replica count |
| Errors | OOM, `READONLY`, timeouts, connection errors, rejected connections |
| Keyspace | key count/TTL/expirations/evictions |
| Disk | free bytes, inodes, IOPS, write latency |

### 29.2. Spring Data Redis Client

- Redis command duration p50/p95/p99.
- Connect time/errors.
- Reconnect attempts.
- Pool active/idle/waiters/borrow time if pooling is enabled.
- Pending commands/queue depth if client instrumentation provides it.
- Timeouts/exceptions by operation type.
- Retry counts and jitter/backoff.
- Serialization/deserialization overhead.
- Thread/event-loop CPU and task queues.

Do not assume Spring Boot provides a built-in metric named `redis.pool.active` across all versions; verify what your client/Micrometer/JMX setup actually exposes.

### 29.3. Business/Application

- HTTP p95/p99 and success rate.
- Cache hit/miss/error/fallback rates.
- DB connection pool usage and DB latency.
- Session failures.
- Stream processing delay/pending count.
- Lock/idempotency errors.
- JVM heap/native memory/GC.
- Pod restarts/`OOMKilled`.
- Autoscaling events.

### 29.4. Monitor Per Node and Role

For Redis Cluster or primary+replica:

```text
redis_node
role: primary/replica
cluster/shard
environment
service owner
```

Never use user IDs or key values as Prometheus labels. Keep cardinality low and separate metrics per node so averages do not mask a hot shard.

## 30. Capacity Alerts: Actionable Warnings

Useful alerts:

| Signal | Risk | Action |
|---|---|---|
| Cgroup memory near limit + rising COW | OOM kill | Investigate write rate, persistence, headroom |
| Redis `used_memory` near `maxmemory` | Eviction or write rejection | Check TTLs, key counts, policy |
| Abnormal `evicted_keys` spike | Cache misses / session loss | Check whether stored data is evictable |
| Pool waiters rising + borrow timeouts | App pool saturation | Find blocking consumers or leaks |
| `rejected_connections` rising | `maxclients`/FD exhaustion or connection storm | Inspect pods, factories, rollouts |
| Command p99 rising + high Redis CPU | Server saturation | Inspect command mix / hot keys |
| Low free disk during rewrite | Persistence failure | Clean up per safe runbook / expand volume |
| High replication lag | RPO/failover risk | Check network and replica health |
| High Stream oldest pending age | Event SLA threatened | Check handlers, reclaim, DB load |
| Cache fallback rising + DB pool near full | Imminent user impact | Rate limit / coalesce / restore cache |

Do not page on every signal indiscriminately. Severity should tie to **SLOs, data criticality, and concrete actions**, not just an arbitrary 80% CPU threshold.

## 31. Benchmarking Redis and Spring Data Redis Applications

A capacity test must exercise **the real application** across representative workloads, not just blast raw Redis commands.

### 31.1. Layer-by-Layer Benchmarking

**Redis-only benchmark**

- Measures server capacity with a representative command mix.
- Isolates network/Java overhead to understand server bottlenecks.
- Do not mistake this for end-to-end app throughput.

**Spring Data Redis benchmark**

- Uses the exact Lettuce/Jedis version, serializer, and connection factory.
- Measures template/`ReactiveRedisTemplate` operations.
- Covers cache hits/misses, payload sizes, and blocking operations.
- Measures JVM heap/GC and driver queue/pool metrics.

**End-to-end benchmark**

- Executes user journeys through HTTP/workers.
- Includes databases, message handlers, and authentication.
- Measures p95/p99 business latency and errors.
- Evaluates fallback behavior when Redis is unavailable.

### 31.2. Scenarios to Test

| ID | Condition | Goal |
|---|---|---|
| CAP-01 | Read-heavy baseline | `GET`/`SET` latency |
| CAP-02 | Heavy write load | CPU, COW, AOF bandwidth |
| CAP-03 | Large dataset near forecast | RSS, `maxmemory`, eviction |
| CAP-04 | Cold cache after restart | DB fallback, warm-up burst |
| CAP-05 | `BGSAVE` in progress | Memory peak and fork latency |
| CAP-06 | `BGREWRITEAOF` | Disk pressure, fsync, COW |
| CAP-07 | Replica full resync | Network and memory headroom |
| CAP-08 | Primary failover | Client reconnect, RTO/RPO |
| CAP-09 | Multi-pod rolling deployment | Connection storm, warm-up |
| CAP-10 | Slow Redis / timeouts | Pending queues, retry amplification |
| CAP-11 | Cluster resharding | Hot shards, `MOVED`/`ASK`, routing |
| CAP-12 | Stream backlog | Blocking connections, handler capacity |
| CAP-13 | TLS enabled | CPU/network overhead |
| CAP-14 | Large responses / pipelines | JVM heap/native memory peak |

Not every test needs to run on every pull request; resilience/load suites can run periodically in isolated staging, and should definitely run before rollouts involving major data or topology changes.

### 31.3. Results Must Document Conditions

A report should capture:

```text
Redis version/distribution:
Redis topology:
Spring Boot / Spring Data Redis / Lettuce/Jedis versions:
Redis data type mix:
Key count / value size distribution:
HTTP RPS and Redis ops/s:
Cache hit ratio:
Client concurrency / pool config:
Persistence / TLS / replica config:
Pod CPU and memory requests/limits:
Network topology:
Dataset warm/cold:

p50/p95/p99 latency:
Error/timeout rate:
Redis CPU/memory/RSS peak:
Cgroup memory peak / OOM events:
Disk IOPS/latency:
Network throughput:
Connections/pool waiters:
Replica lag:
Degraded-mode behavior:
```

Without documented test conditions, a single high-throughput measurement is insufficient for production sizing.

## 32. Use `Testcontainers` to Verify Config, Not as a Capacity Benchmark

Testcontainers with real Redis is great for testing:

- Redis version and command behavior.
- Serializers/TTL/`CacheManager`.
- Lua scripts.
- Memory policies at moderate data sizes.
- Redis auth/ACL.
- Spring Data Redis reconnects at the integration level.

However, a small container test on a laptop does not prove Redis will handle millions of keys, hundreds of connections, and multi-GiB AOF rewrites.

Layering:

```text
Unit tests
   |
   v
Redis Testcontainers integration tests
   |
   v
Staging load/capacity tests
   |
   v
Failover/restore/chaos drills
```

Each layer answers a different question. Passing a single `SET`/`GET` in a Redis container does not mean capacity planning is done.

## 33. Application Autoscaling Does Not Automatically Scale Redis

In Kubernetes, HPA may scale Spring Boot pods from 8 to 20 when CPU or traffic spikes. Yet the Redis server remains a shared dependency.

```text
HPA scales out
    |
    v
More Spring pods
    |
    +-- More Redis connections
    +-- More cache GET/SET calls
    +-- More retries on failure
    +-- More DB fallback requests
    |
    v
Redis/DB saturation
```

Autoscaling can inadvertently amplify an incident if downstream systems cannot keep up.

### 33.1. Add Application-Layer Admission Controls

Options:

- Per-pod concurrency caps.
- Service-wide global traffic limits where appropriate coordination exists.
- Bounded executor queues.
- Retry budgets and exponential backoff.
- Circuit breakers/bulkheads.
- Work-queue backpressure.
- Scale-down/scale-up policies that avoid churn and reconnect storms.

Note: a semaphore placed per pod does not enforce a **global cap**. Sum across maximum pod counts and rollout surges.

### 33.2. Kubernetes Requests Do Not Equal SLOs

No pod OOMs, zero CPU throttling, and successful Redis `PING`s are not enough to conclude user journeys meet SLOs. Track business p95/p99, availability, and correctness alongside resource metrics.

## 34. Optimizing Cost Without Sacrificing Reliability

To reduce cloud spend, consider:

1. **Reduce redundant data**: use appropriate TTLs, avoid stale/unused keys, compress payloads where genuinely effective.
2. **Pick fitting data types**: use Hashes instead of many Strings per aggregate when sensible.
3. **Cut round trips**: pipeline/batch within driver limits, avoid duplicate `GET`s.
4. **Control key cardinality**: avoid namespaces that generate unbounded keys.
5. **Tier caches**: cache appropriate data in-app or at the CDN to reduce Redis traffic.
6. **Match eviction policies to data**: evictable caches vs. non-evictable critical state.
7. **Separate workloads**: keep cache evictions from wiping sessions or locks.
8. **Tune pools from measurements**: trim unnecessary idle sockets.
9. **Scale the actual bottleneck**: memory, CPU, network, storage, or hot shards.
10. **Match durability to need**: skip expensive persistence on purely rebuildable data when safe; never turn off durability for critical state.

### 34.1. Account Fully for HA Costs

A 16 GiB primary with two replicas does not cost the same as a single 16 GiB node. Include:

```text
Primary compute + memory
Replica compute + memory
Storage volumes / snapshots
Network replication traffic
Sentinel / Cluster management
Monitoring / logging
Backup retention
Cross-zone / cross-region transfer (if applicable)
```

Across multiple AZs, network charges and replication latency can be substantial. Do not choose a topology based solely on RAM/GB pricing.

## 35. Capacity Planning Worksheet Template

A worksheet (adaptable to an operational spreadsheet) with columns:

| Field | Sample Entry | Measurement Source |
|---|---|---|
| Redis role | `product-cache` | Architecture inventory |
| Data criticality | Rebuildable cache | Product owner |
| Current keys | 3,000,000 | `INFO keyspace`/sampling |
| Future keys | 4,500,000 | Growth forecast |
| Measured RAM/key | 1.4 KiB | Staging Redis sample |
| Projected `used_memory` | ~6 GiB | Calculation |
| RSS multiplier | 1.20 | Benchmark/`INFO` |
| COW peak | 2 GiB | `BGSAVE`/rewrite load test |
| Container memory target | 14–16 GiB (illustrative) | Envelope + testing |
| `maxmemory` | Per policy/benchmark | Redis config |
| Peak ops/s | 10,000 | Production traces |
| GET/SET ratio | 80/20 | Commandstats/app |
| Average payload | 2 KiB two-way | Sampling |
| Redis p99 target | Per service SLO | SLO |
| Replica count | 2 | HA design |
| AOF/RDB policy | Measured deployment config | Redis config |
| Disk peak | Per rewrite/backup test | Storage telemetry |
| Peak app pods | 15 including rollout | HPA/rollout |
| Client type | Lettuce | Spring config |
| Pool and connection cap | Per dedicated demand | Pool metrics |
| App heap/native RAM | Per load test | JVM/cgroup |
| DB fallback budget | Per cache outage drill | DB metrics |
| Failure headroom | Per failover simulation | Staging drill |

Never leave critical cells blank to be silently treated as 0. Explicitly mark `UNKNOWN`, assign an owner to measure it, and set a target date to update it.

## 36. Step-by-Step Implementation Playbook

### Step 1 — Lock Down the Workload

Gather existing production metrics; group cache/session/lock/Streams. Define 3-, 6-, and 12-month forecasts for key counts, payloads, and traffic aligned with business plans.

### Step 2 — Inspect the Data Model

Build a test dataset closely matching real data types. Use `MEMORY USAGE`, `INFO memory`, key cardinality, and TTL distributions to project dataset growth.

### Step 3 — Choose Topology and Failure Model

Standalone, Sentinel, or Cluster? How many replicas? Must it survive a node failure, an AZ failure, or more? What are RPO/RTO? Size resources for degraded states, not just normal operation.

### Step 4 — Budget CPU/RAM/Network/Disk

Create envelopes for each Redis data node, client/app pods, and network paths. Leave headroom for COW, full syncs, bursts, rollout surges, and disk rewrites.

### Step 5 — Configure the Driver

Choose Lettuce or Jedis. For Lettuce, separate shared connections from dedicated workloads; for Jedis, measure pool demand. Set connect/command/borrow timeouts and resource limits appropriately.

### Step 6 — Configure the Application

Bound concurrency, Reactor fan-out, batch sizes, thread/executor counts, and retry budgets. Never create Redis clients per request or hold connections across non-Redis I/O.

### Step 7 — Load Test in Staging

Run normal, peak, cold-cache, persistence, failover, and reconnect workloads. Measure end-to-end app/Redis/downstream p99 alongside cgroup memory.

### Step 8 — Tune Based on Measurements

If:

```text
Low Redis CPU, high pool wait -> check pool/dedicated connection contention.
High Redis CPU, low pool wait -> check command mix / scale Redis.
RSS/cgroup near limit during BGSAVE -> increase headroom or optimize job/IO.
DB overload on cache miss -> limit fallback fan-out or scale DB capacity.
```

Change one variable at a time so you know its effect.

### Step 9 — Set Alerts and Runbooks

Alert on business SLOs alongside near-saturation resource signals. Maintain playbooks for OOM, disk full, connection storms, failover, hot shards, and cache outages.

### Step 10 — Re-Verify After Changes

Whenever Redis version, Spring Boot/Lettuce/Jedis versions, serializers, TTL policies, pod counts, topology, or persistence policies change, resource capacity can shift. A capacity plan must be updated periodically—not treated as a one-time document.

## 37. Misconceptions That Cause Incidents

**“Redis uses 5 GiB of `used_memory`, so 5 GiB of container RAM is enough.”** False: RSS, COW, buffers, page cache, and other overhead can breach the limit.

**“`maxmemory` is a hard cap on process RAM.”** False: Redis `maxmemory` is not the same as a cgroup memory limit.

**“Snapshots run in the background, so they use no resources.”** False: fork/COW, CPU, and disk I/O still create pressure.

**“`BGSAVE` always requires double the RAM.”** Not true for every workload; COW depends on how many pages are modified while the child runs.

**“AOF `everysec` means at most exactly one second of writes is lost in any crash.”** There is no absolute guarantee of that.

**“Replicas need less RAM because they mostly handle reads.”** False: replicas hold full dataset copies and may have to become primaries after failover.

**“A 3-primary Cluster has exactly 3× the capacity.”** Not guaranteed: hot keys/slots, resharding, and networking can impose bottlenecks.

**“HTTP thread count must equal Redis connection count.”** Incorrect for Lettuce shared/multiplexed operations.

**“Lettuce pool `max-active=64` means every `GET` uses 64 sockets.”** Not by default when the factory shares a native connection for regular commands.

**“Jedis and Lettuce perform identically with the same pool config.”** False: their connection semantics differ.

**“Increasing pool size always makes Redis faster.”** It can just increase queueing, resource consumption, and server saturation.

**“Reactive Redis doesn't block threads, so concurrency is unlimited.”** False: command queues, buffers, network, and server capacity still constrain it.

**“`flatMap(concurrency=16)` caps the whole system at 16 commands.”** False: it bounds per subscription/operator; multiple requests and pods multiply total concurrency.

**“Good Redis command p99 means good HTTP p99.”** Not if app GC, serialization, DB fallbacks, or thread pools are slow.

**“If cache fails we have the DB, so no extra capacity is needed.”** False: fallbacks can amplify DB load dramatically.

**“Scaling Spring Boot pods scales Redis too.”** No: Redis is a separate downstream dependency.

**“Disk volume only needs to match the current RDB size.”** False: snapshots/rewrites, backups, and growth require additional space.

**“Passing one Redis Testcontainers test is enough for capacity planning.”** No: functional integration tests do not replace production-scale load/failure tests.

**“Low Redis `connected_clients` means few operations are in flight.”** Not necessarily: Lettuce multiplexes.

**“Empty `SLOWLOG` means Redis is not causing latency.”** No: pool waits, networking, client queues, and fork pauses may not show up in `SLOWLOG`.

**“All Redis keys can be safely evicted when memory runs out.”** False: sessions/locks/idempotency/state may not tolerate early loss.

**“Average payload size is sufficient.”** No: p99 value sizes, batch responses, and Stream retention can cause memory spikes.

## 38. Pre-Deployment Checklist

### 38.1. Redis Data and Memory

- [ ] Inventory of key types, TTLs, current key counts, and forecasts exists.
- [ ] RAM/key measured with the target Redis version and serializers.
- [ ] `used_memory`, RSS, and allocator behavior measured.
- [ ] COW peak measured during `BGSAVE`/AOF rewrite.
- [ ] `maxmemory` set below RAM limit with verified headroom.
- [ ] Eviction policy matches data criticality.
- [ ] No overlooked keys without TTL or unbounded Stream retention.

### 38.2. CPU, Disk, Network

- [ ] Command mix and peak throughput established.
- [ ] p95/p99 Redis latency and peak CPU measured.
- [ ] Bidirectional request/response payload throughput calculated.
- [ ] Network budget includes replication and failover.
- [ ] Disk space accounts for peak RDB/AOF and rewrites.
- [ ] fsync/disk throughput and restore times verified.
- [ ] Headroom reserved for full resyncs and resharding.

### 38.3. Redis Driver

- [ ] Confirmed whether Spring Data Redis uses Lettuce or Jedis.
- [ ] Verified shared native vs. dedicated/pooled connection behavior.
- [ ] Connection budget calculated across pods/factories/nodes.
- [ ] Blocking consumers and Pub/Sub subscriptions accounted for.
- [ ] Connect/command/borrow timeouts aligned with deadlines.
- [ ] Metrics enabled for pool waiters, rejected connections, and reconnects.
- [ ] No per-request driver/client creation.

### 38.4. Spring Boot Application

- [ ] JVM heap and native memory measured under peak load.
- [ ] `-Xmx` not set equal to total memory limit when non-heap/native memory exists.
- [ ] Concurrency/batch size limits enforced on reactive/batch workloads.
- [ ] HTTP/worker threads sized to downstream capacity.
- [ ] No blind retries of non-idempotent operations.
- [ ] Cache fallback / DB capacity plan in place.
- [ ] Cache stampede / cold-start protections enabled.
- [ ] Autoscaling accounts for connection surges.

### 38.5. Operations

- [ ] Production-like and degraded-mode load tests completed.
- [ ] Per-node metrics collected for Cluster/replicas.
- [ ] SLO/error-budget alerts and resource saturation alerts configured.
- [ ] Runbooks exist for OOM, disk full, failover, and high p99.
- [ ] Deployment rollback plan ready if latency or error rates degrade.
- [ ] Schedule established to update capacity forecasts with growth.

## 39. Conclusion

**Resource sizing for Redis, drivers, and applications** in Spring Data Redis is a multi-layer problem that must begin with **data and business behavior** before choosing node sizes or pool settings.

Key principles:

1. **Measure Redis RAM with real data**, since payload bytes omit object and allocator overhead.
2. **Separate `used_memory`, RSS, COW, and cgroup memory**; `maxmemory` is not a total process RAM limit.
3. **Account for persistence, replication, and failover**, as background forks, AOF rewrites, and full resyncs create resource peaks.
4. **Calculate network from payloads and topology**, not commands/sec alone.
5. **Measure CPU by command mix**, especially Lua, collection commands, TLS, and background jobs.
6. **Understand Lettuce/Jedis before tuning pools**; shared/multiplexed connections, dedicated connections, and blocking consumers have different demands.
7. **Compute connection budgets across the entire deployment**, including app pods, factories, listeners, Cluster nodes, and rolling surges.
8. **Size both JVM heap and native memory**, cap Reactor/worker concurrency, and avoid unbounded command queues.
9. **Test cold caches and fallbacks**, since a Redis outage can multiply database load many times over.
10. **Benchmark at peak and under failure scenarios**, then choose headroom based on SLOs rather than a generic multiplier.

A sound capacity plan is not a one-time CPU/RAM spreadsheet—it is **a model combining explicit assumptions, measured data, alert thresholds, failure mitigation, and re-verification procedures** as workloads, versions, and topologies evolve.
