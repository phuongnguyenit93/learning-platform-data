# Setting Acceptable Data-Loss and Recovery-Time Objectives in Spring Data Redis

## 1. Why set data durability objectives before configuring Redis?

Redis is commonly introduced as a low-latency store, yet a Spring Data Redis application may use Redis for many different kinds of data: product caches, login sessions, shopping carts, temporary processing state, rate-limiting counters, Redis Streams, or business data capable of triggering external side effects. **Not every type of data needs the same durability or recovery speed.**

Suppose an application uses Redis for three purposes:

- Product catalog cache: losing all keys can still be reloaded from the primary database.
- Shopping carts not yet synced elsewhere: losing keys can discard users' work.
- Stream holding unprocessed order-creation commands: losing an entry can drop an order.

From the exact same Redis primary outage, the business impact differs completely.

Therefore, before choosing Redis RDB, AOF, replication, Sentinel, Cluster, or backups, answer two questions:

1. **How much data loss is acceptable at most?** This is the **RPO – Recovery Point Objective**.
2. **How much time is acceptable to restore service?** This is the **RTO – Recovery Time Objective**.

Setting RPO and RTO around **business impact**—rather than just Redis's default behavior—avoids two opposite mistakes: over-engineering complex solutions for rebuildable caches, or running cache-grade configs for data where losing a few seconds causes severe harm.

This lesson shows how to define RPO/RTO, translate them into persistence and Redis architecture choices, organize recovery drills, and align outage handling in Spring Data Redis.

---

## 2. What is RPO?

**RPO (Recovery Point Objective)** is the maximum amount of recent mutations an organization can tolerate losing when recovering from an outage. It can be expressed as **time** measured backward from the failure instant to the acceptable recovery point.

Example system with:

```text
Target RPO = 5 minutes

10:00  Guaranteed recovery point per target
10:01  New data written
10:02  New data written
10:03  New data written
10:04  New data written
10:05  Incident

Goal: recovered data must not be older than 10:00
(at most roughly 5 minutes of latest changes lost).
```

**RPO is not the time needed to recover.** It is the maximum acceptable age of recovered data relative to the incident time.

Examples:

| Data type | Possible RPO choices | Meaning |
|---|---|---|
| Rebuildable product cache | No cache retention required | Entire cache may be lost if origin source stays accurate |
| Temporary real-time statistics | 5–15 minutes | A slice of recent metrics must be recomputed |
| Carts living solely in Redis | 30–60 seconds or tighter | Losing carts disrupts user experience |
| Unreplicated business Streams | Near 0, or needs a more durable source | Dropping events can omit operations |
| Confirmed payment statuses | Usually zero transaction loss allowed | Must not rely solely on a Redis setup risking write loss |

Numbers in the table are **examples for business discussions**, not universal product standards.

### 2.1. What does RPO = 0 mean?

RPO of 0 means **zero tolerance for losing any successfully acknowledged change**. This is a very strong requirement.

Redis with persistence and replicas **does not automatically guarantee RPO = 0 across all failure types**. For example:

- Redis primary replied OK to a write command, yet data had not durably fsynced to disk.
- Primary and replica use async replication; primary dies before the new record reaches the replica.
- Disk or backups holding the new record fail simultaneously with the node.
- The application timed out after sending the command and does not know whether it executed.

If the business genuinely cannot lose committed data, design appropriate storage, write acknowledgment, fault tolerance, recovery, and verification; for certain transactions, keep a durable database as the source of truth and use Redis as a speed or derived layer.

### 2.2. Target RPO vs. actual RPO

**Target RPO** is what the business accepts. **Achieved RPO** can only be assessed from architecture, failure modes, and test evidence.

A backup taken every hour does not prove a one-hour RPO in every scenario:

- A backup may not have finished or may have errored.
- The backup may not have transferred to safe storage yet.
- The latest backup may be unreadable.
- If restoring only from backup while a newer AOF still exists, actual RPO depends on which recovery source is chosen.

You must therefore identify the **guaranteed recovery point** per failure scenario.

---

## 3. What is RTO?

**RTO (Recovery Time Objective)** is the maximum allowed time to restore a service or business capability after disruption.

Example:

```text
Target RTO = 10 minutes

14:00  Redis primary stops serving
14:01  Monitoring detects failure
14:03  Replica promoted to primary
14:04  Spring Boot reconnects
14:06  Core APIs stabilize
14:07  System verifies recovery

Observed recovery time ≈ 7 minutes
=> within the 10-minute target in this example.
```

RTO is more than Redis process startup time:

- Must **detect** the incident.
- Must **fail over** or **restore** Redis.
- Must **re-establish connections** from Spring Boot services.
- May need to **reload data** from RDB/AOF or canonical sources.
- May need to **warm caches** or recover consumer states.
- Must **verify business flows** before declaring service restored.

### 3.1. Differences from related terms

| Term | Interpretation |
|---|---|
| RPO | Maximum acceptable data loss |
| RTO | Maximum acceptable downtime |
| MTTD (Mean Time To Detect) | Average time to detect an incident |
| MTTR (Mean Time To Recover/Repair) | Average time to recover/repair, as defined by the organization |
| Availability SLO | Desired uptime within a measurement window |
| Actual recovery time | Elapsed time measured in a real incident or drill |

MTTR is a **statistical average** and does not guarantee every incident meets RTO. A system with a 2-minute MTTR can still hit a 60-minute outage and violate a 10-minute RTO.

### 3.2. When should the RTO clock start?

In recovery docs, state explicitly:

```text
Start: when the service stops meeting agreed serving criteria.
End:   when mandatory business flows operate again
       and pass recovery verification checks.
```

If you start measuring only when operators begin restarting Redis—ignoring 10 minutes spent undetected—the metric fails to reflect customer impact.

---

## 4. RPO and RTO must not be conflated

They are independent objectives.

A system can have:

- **Short RTO, loose RPO:** replica promotes fast, yet loses the last writes due to replication lag.
- **Tight RPO, long RTO:** latest writes sit safely in AOF, yet reloading a massive dataset takes a long time.
- **Both relaxed:** rebuildable cache accepting restarts and multi-hour repopulation.
- **Both strict:** requires higher-cost infrastructure, operations, and data modeling.

Example matrix:

| | RTO 1 minute | RTO 1 hour |
|---|---|---|
| **RPO 0–1 second** | Needs both fast failover and very tight write-loss controls; must test in practice | Data must almost never be lost, though longer recovery time is tolerable |
| **RPO 15 minutes** | Prioritizes availability, tolerating loss of some recent data | Simpler backups/snapshots may suffice if business allows |

**Never take `appendfsync everysec` and infer the app automatically gets RPO = 1 second and RTO = 1 second.** Fsync cadence, replication lag, and restore duration are separate mechanisms, alongside multi-node failure modes.

---

## 5. Classifying Spring Data Redis data before setting targets

A single Redis cluster may serve multiple use cases. For each dataset, answer **is Redis the final source of truth?**

### 5.1. Redis is only a cache

Example:

```java
@Cacheable(cacheNames = "productView", key = "#p0")
public ProductView getProduct(String sku) {
    return productRepository.findBySku(sku)
            .orElseThrow();
}
```

If Redis cache is wiped completely, the app reloads data from the canonical database. **Losing cache is not losing business data.**

The cache's RPO can be stated as "retaining cached entries is not required". Yet the **product read service's** RTO still matters: does the database have enough capacity when every request misses cache?

There are thus two separate concerns:

- Restoring the Redis cache service.
- Keeping the API available while cache data is missing.

An app configured to bypass cache when Redis fails can stay up while Redis recovers, provided the canonical source handles the load and cache errors are handled properly.

### 5.2. Redis holds sessions or shopping carts

If login sessions live solely in Redis, losing keys logs users out. If carts live solely in Redis, losing data drops users' selected items.

Discuss RPO around user experience:

- Is forcing all users to log in again acceptable when Redis fails?
- Is losing the last 30 seconds of cart edits acceptable?
- Does the database store a copy of the cart?
- Can carts be reconstructed from user activity logs?

**TTL is not a backup mechanism.** A session expiring per TTL rules is normal lifecycle behavior, not a data-loss incident. Conversely, losing a disk and dropping live non-expired sessions is a durability failure.

### 5.3. Redis holds Streams or job queues

A Stream can hold events not yet processed by consumers. If events are lost in a node crash before replication or persistence finishes, consumers cannot recover them from offsets/PELs alone.

Determine:

- Are events persisted in another durable store?
- Can producers replay events?
- Can consumers safely handle duplicates?
- Does reconciliation detect missing events?
- Is Redis Stream the source of truth or a transient transport channel?

When messages must never be lost, using Redis Streams with AOF/replication **must be evaluated against explicit failure models**; in some designs, a transactional outbox in the primary database guarantees event intent is never lost.

### 5.4. Redis stores money- or permission-related state

If Redis holds payment states, paid-tier entitlements, spent quotas, or idempotency records, losing records can trigger duplicate transactions or incorrect access grants.

In many architectures, keep **durable business ledgers** in a store with strong consistency and constraints, using Redis for fast reads, load shedding, or coordination.

RPO must start from "does losing one acknowledged write corrupt money, permissions, or compliance?"—not "is AOF enabled on Redis?".

---

## 6. Building a per-capability target table

A useful RPO/RTO document ties targets to **user capabilities**, not just node names.

Example discussion table:

| Capability | Role of Redis | Example RPO | Example RTO | Behavior when Redis fails |
|---|---|---|---|---|
| Catalog page | Rebuildable cache | Cache retention unnecessary | API stays up within 2 minutes | Bypass cache, rate-limit DB load |
| Sessions | Temporary session store | 1 minute | 5 minutes | Prompt re-login or temporary error |
| Shopping cart | Unsynced state | 30 seconds | 10 minutes | Load alternate saved state if available |
| Rate-limit counters | Load control | Few seconds loss tolerable per risk | 1 minute | Fail-closed or backup limiter |
| Non-critical notification Stream | Rebuildable transport | 5 minutes | 15 minutes | Producer can replay |
| Sole-source order Stream | Critical events | Near 0, requires extra design | 5 minutes | Reject new intake if durable write unguaranteed |

**These figures are illustrative**, not Redis engineering promises. Real adoption requires business-owner sign-off, impact analysis, data sizing, and verification plans.

A system may span multiple layers:

- **Application layer:** which APIs may serve degraded results?
- **Data layer:** which records must survive failover/disaster?
- **Redis layer:** which persistence and replication modes fit?
- **Operations layer:** who recovers it, how long it takes, and how it is proven?

---

## 7. Redis stores data primarily in memory: distinguish two recovery types

Redis executes most commands against in-memory data. During an incident, recovery depends on where surviving data lives.

### 7.1. Same-node restart with intact disk

If the Redis process stops or the server restarts with persistence files intact on disk, Redis loads RDB/AOF to restore state.

Recovery time covers process startup, reading disk files, rebuilding in-memory state, health verification, and client reconnection.

### 7.2. Loss of node or disk

If the primary's disk is completely destroyed, local persistence files are gone too. Recover from:

- A replica holding suitable state.
- An off-node backup.
- A copy in another storage zone.
- Business data sources capable of repopulating Redis.

These two scenarios can have vastly different RPO/RTO. Setting `appendonly yes` on a local disk does not turn that disk into an offsite backup.

### 7.3. Loss of an entire cluster or zone

A datacenter or availability-zone outage can wipe out primary, replicas, and backups simultaneously if all copies sit in the same fault zone.

**Disaster recovery** RPO/RTO must account for:

- Replicas/backups placed in separate failure domains.
- Whether data replicated to the standby zone prior to the outage.
- Whether networking, DNS, secrets, configs, and Spring Boot infra can spin up in the standby zone.
- Safeguards preventing split-brain concurrent writes to two primaries across zones.

**Replication, persistence, and backups are three complementary layers—none replaces the others.**

---

## 8. RDB snapshots and their impact on RPO

**RDB (Redis Database)** saves a point-in-time snapshot of the Redis dataset. Snapshots run on schedules or on demand.

Example self-managed `redis.conf`:

```conf
save 900 1
save 300 10
save 60 10000

dbfilename dump.rdb
dir /var/lib/redis
```

Meaning of `save` lines:

- After ~900 seconds with at least 1 mutation, Redis may create a snapshot.
- After ~300 seconds with at least 10 mutations, Redis may create a snapshot.
- After ~60 seconds with at least 10,000 mutations, Redis may create a snapshot.

These conditions are **snapshot trigger rules**, not guarantees that a new completed RDB file exists exactly at those marks.

### 8.1. RPO with RDB-only

Suppose a snapshot completes at 10:00, Redis keeps taking writes, and the process/disk fails at 10:04. If only the 10:00 snapshot is recoverable, writes after 10:00 risk being lost.

```text
10:00  RDB snapshot completes
10:01  Write A
10:02  Write B
10:03  Write C
10:04  Redis loses disk

Restore from 10:00 RDB
=> A, B, C do not exist in the restored copy.
```

If required RPO is tighter than the snapshot interval, periodic RDB alone falls short.

**RDB fits when:**

- Data can be rebuilt from another source.
- Losing changes since the last snapshot is acceptable.
- Portable snapshot backups are desired.
- Fast restarts from a pre-built dataset image are helpful.

### 8.2. Snapshot overhead

Redis creates background snapshots via `BGSAVE`. During snapshotting, fork/copy-on-write creates resource pressure, especially on large datasets with high write rates.

Budget for:

- Does RAM have headroom for copy-on-write?
- Does disk have sufficient space and I/O throughput?
- How long does the snapshot take to complete?
- Could it fail from full disk or permissions?
- Does snapshotting push latency beyond SLO?

A rule like "snapshot every 60 seconds" helps nothing if snapshots keep failing.

### 8.3. Observing RDB state

Useful Redis commands in authorized environments:

```redis
INFO persistence
LASTSAVE
```

Fields such as last successful save time, `rdb_bgsave_in_progress`, and previous save status reveal protection gaps.

Never use `LASTSAVE` alone as system-wide RPO proof: it does not tell you whether the backup transferred offsite, and an old snapshot omits writes occurring after capture.

---

## 9. AOF and its impact on RPO

**AOF (Append Only File)** logs data-mutating operations so Redis can replay them on startup. Appropriately configured, AOF narrows the data-loss window relative to periodic snapshots alone.

Example:

```conf
appendonly yes
appendfsync everysec
```

### 9.1. appendfsync modes

| Setting | General behavior | Trade-off |
|---|---|---|
| `appendfsync always` | Requests fsync per write/write group per execution rules | Shrinks write-loss window on process/OS crashes, at higher disk I/O and latency cost |
| `appendfsync everysec` | Redis typically fsyncs roughly once per second | Common balance of performance and durability, yet retains an un-persisted window |
| `appendfsync no` | Leaves fsync timing to the OS | Less control over how much data is lost on crash |

**Never interpret `everysec` as an absolute 1-second RPO guarantee.** Real fsync timing varies with disk performance, OS scheduling, load, AOF rewrites, crash mode, and storage hardware. Even `always` does not protect against total disk loss or multi-node outages.

### 9.2. AOF rewrite and restarts

If every write appended indefinitely, AOF files would grow massive. Redis supports **AOF rewrite** to produce a compact representation of current state while retaining recoverability per Redis version rules.

Common tuning parameters:

```conf
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
```

These parameters do not directly set RPO; they control rewrite triggers to cap log growth. Huge AOF files lengthen startup replay time, hurting RTO.

In newer Redis versions, AOF can span multiple files and a **manifest**. When backing up or restoring, never blindly copy a single file named `appendonly.aof` while ignoring the actual AOF layout of your running version.

### 9.3. Enabling RDB and AOF simultaneously

Redis can run both RDB and AOF. In typical setups, when AOF is enabled and valid, Redis prioritizes AOF on recovery because it likely contains more recent changes than RDB.

Still, **source precedence** does not replace integrity checks, backups, or data verification. If AOF becomes corrupted, have a recovery plan grounded in backups and version-specific Redis docs.

### 9.4. Does AOF meet your RPO?

Follow this sequence:

1. Determine maximum acceptable business RPO.
2. Identify in-scope failure modes: process crash, OS crash, disk loss, node loss, zone loss.
3. Evaluate fsync modes and real storage hardware.
4. Evaluate replication and independent backups.
5. Measure recovered results in drills, including writes right before the failure.
6. Document remaining unprotected gaps.

Never pick `appendfsync always` simply by comparing seconds while ignoring throughput limits, disk latency, and topology.

---

## 10. Replication: improves availability, does not guarantee every write

Redis replication is normally **asynchronous**. The primary executes writes, replies, and streams changes to replicas. A replica may not yet have received the newest writes when the primary fails.

Example:

```text
Client          Primary            Replica
  | SET A -------->|                  |
  |<------ OK ------|                  |
  |                 | ---- replicate A -->  (not yet arrived)
  |                 X Primary dies
  |
  |                     Replica promoted
  |                     but lacks A
```

Result: the application received `OK` for `SET A`, yet the post-failover primary lacks A. That is an RPO risk from **replication lag**.

### 10.1. Redis Sentinel and Redis Cluster

- **Sentinel** monitors primaries/replicas and orchestrates failover for appropriate deployments. It does not make replication strictly synchronous.
- **Redis Cluster** distributes hash slots and performs cluster-managed failover. Within each shard, promoting a replica still risks losing un-replicated writes.
- **Managed Redis** may offer automatic failover, backups, and operational tooling. Check actual deployment policies and SLAs rather than assuming guarantees from product branding.

### 10.2. WAIT does not equal on-disk fsync

Redis provides `WAIT` to wait for a number of replicas to confirm receipt of prior replication data from the current connection:

```redis
SET demo:critical-key value
WAIT 1 1000
```

General meaning: after writing, wait up to ~1,000 ms for at least one replica to acknowledge matching replication progress. The return value reports how many replicas met the threshold.

**Important:**

- `WAIT` does not guarantee data fsynced durably onto replica disks.
- Check `WAIT`'s return value; if fewer replicas respond than requested, the app must handle that case.
- `WAIT` does not turn Redis replication into a consensus system with strong consistency across all failovers.
- With connection pooling or pipelining, enforce **same client connection** semantics between write and `WAIT`, rather than calling `WAIT` on an unrelated connection and assuming the prior write is protected.

In supporting Redis versions, `WAITAOF` adds waiting for AOF fsync acknowledgments per parameters; verify version docs and failure models before treating it as a complete RPO answer.

### 10.3. min-replicas-to-write and min-replicas-max-lag

Redis offers settings so a primary **rejects writes** when too few replicas meet count and responsiveness thresholds:

```conf
min-replicas-to-write 1
min-replicas-max-lag 10
```

This example requires at least one replica considered close enough (lag within 10 seconds) for the primary to accept writes.

Yet this **is not synchronous replication**: it does not prove **each acknowledged write** was confirmed by a specific replica before replying. It shifts part of the risk into **reduced write availability** when replicas have issues.

Decide explicitly whether rejecting writes is preferable to risking un-replicated writes.

---

## 11. How do backups differ from replication?

Replicas keep service running when a primary fails, yet fail to protect against undesirable valid mutations:

```text
Operator accidentally runs FLUSHDB
            |
            v
Primary deletes keys
            |
            v
Replica receives same deletion
            |
            v
Neither node has the data left
```

Without separately stored backups, replication cannot roll back to before the accidental deletion.

Backups enable recovery from a **historical point in time** and guard against logic/operator errors. When designing Redis backups, specify:

- **What** to back up: RDB, consistent AOF sets, or provider snapshots.
- **When** and how frequently.
- Whether backups **survive node/region loss**.
- Whether backups are **readable** and restorable within target timelines.
- Whether backups are **encrypted** and access-controlled.
- How long backups are retained and who can delete them.
- Whether multi-shard datasets require globally consistent checkpoints.

### 11.1. Never copy actively changing persistence files haphazardly

While Redis snapshots, rewrites AOF, or writes logs, uncoordinated file copying can yield inconsistent or incomplete copies.

Use Redis/managed-service supported backup mechanisms or verified storage-level consistent snapshots; for multi-part AOF, preserve the entire required structure.

Never stop or move live production persistence files merely to test backups without a plan.

### 11.2. Backups also have their own RPO and RTO

Example:

```text
RDB backup every 15 minutes
Cross-zone storage transfer takes up to 5 extra minutes
Restoring 80 GB takes 25 minutes
App restart and verification takes 5 minutes
```

If all nodes fail and only cross-zone backups survive, safe data can **trail the outage by many minutes**. RTO must include downloading backups, restoring Redis, and verifying APIs.

"Backups every 15 minutes" does not yield a 15-minute RPO if backups finish late, transfers fail, or artifacts are corrupted.

### 11.3. Test actual restores, not just file existence

A backup logged as created does not prove it can be restored. Test by:

1. Picking an existing backup.
2. Restoring into an **isolated environment**, never overwriting production.
3. Booting Redis with matching config, secrets, and version.
4. Reading sample keys and checking business invariants.
5. Measuring elapsed time until ready to serve.
6. Documenting errors, data age, and required manual steps.

---

## 12. Building a failure model for Redis

For RPO/RTO to mean anything, specify which failures they cover.

| Scenario | Potential data loss? | Primary recovery mechanism | What to measure |
|---|---|---|---|
| Redis process crash, disk intact | Un-persisted writes may be lost | Restart and load RDB/AOF | Data age, restart/replay duration |
| OS/kernel crash or power loss | Depends on fsync/disk | Restart from persistence | Last surviving write, integrity |
| Primary dies, replica survives | Un-replicated writes may be lost | Sentinel/Cluster failover | Replication lag, failover duration |
| Primary disk destroyed | Local files lost | Promote replica or restore backup | Replica gap, restore duration |
| Accidental key delete / `FLUSHDB` | Replicas also affected | Restore backup or origin source | Usable point-in-time backups |
| Out of memory / eviction | Keys dropped per policy | Capacity relief, restore/rebuild | Eviction rate, recoverability |
| Network partition | Clients may fail reads/writes; split behavior | Failover, write fencing, reconnect | Error duration, write-loss exposure |
| Entire zone lost | Primary/replicas in zone may vanish | Cross-zone replicas/backups | Cross-zone RPO/RTO |
| Entire region lost | Requires cross-region copy | Disaster recovery site | DR activation time, data skew |
| App misconfiguration / bad serializer | Data unreadable or written corrupt | Code/schema rollback, restore | Rollback and migration plans |

**Never set a single RPO/RTO covering only process crashes if the business requires surviving regional outages.** Define targets per scenario, then design to meet the strictest required tier.

---

## 13. Translating business goals into Redis choices

A reference design matrix:

| Target level | Example need | Common options considered | Caveat |
|---|---|---|---|
| No cache retention required | Rebuildable from DB | No or minimal persistence, cache TTLs, fallback path | API RTO depends on DB capacity |
| Can lose several minutes | Temporary/analytics data | RDB snapshots and matching backups | Snapshot interval is not an RPO guarantee |
| Reduce write loss near crash | Sessions/carts more important than cache | AOF `everysec`, replicas, backups | Never market as strict 1-second RPO |
| Minimize per-node write-loss window | Critical data, latency budget allows | AOF `always`, replicas, appropriate wait controls | Measure latency, disk, and failover exposure |
| Near-zero transaction loss | Mandatory ledgers / side effects | Durable transactional source; Redis as cache/coordination | Do not rely solely on Redis persistence + async replicas |
| Low second/minute RTO | Critical APIs | Auto failover, monitoring, client reconnect, warm standby | Fast failover can still drop un-replicated writes |
| Multi-hour RTO | Internal tools | Restore from backups, manual runbooks | Must rehearse real restores |

This is not a mechanical lookup table. **A persistence choice suitable for one failure scenario may fall short in another**; weigh cost, targets, and failure domains together.

### Decisions to lock down in design

1. Is Redis the source of truth or a derived copy?
2. When is a write considered "successful to the user"?
3. If that write is lost, can it be replayed idempotently?
4. Which failures must survive: process, disk, node, zone, or region?
5. Who owns recovery and holds required permissions?
6. Does multi-shard data require globally consistent snapshots?
7. Is there recent drill evidence?

---

## 14. RTO includes both infrastructure recovery and Spring application recovery

A Spring Boot system can remain unavailable longer than the Redis server because of connection pools, retry backoff, or unready startup paths.

Example:

```text
Redis failure begins                         00:00
Monitoring detects                           00:25
System triggers failover                     00:55
Replica promoted                             01:20
Spring Boot discovers new primary            01:45
App clears timeout/retry backlog             02:05
Cache warms gradually, API meets latency SLO 03:15
Read/write verified, alerts close            03:35

Observed recovery time: roughly 3 minutes 35 seconds
```

If target RTO is 2 minutes, even though the new primary served at 1:20, the overall service breached its target. Improve every stage:

- Faster failure detection.
- Automated failover and proper Sentinel/Cluster/managed Redis settings.
- Appropriate client topology discovery and reconnection.
- Request-budget-aligned timeouts.
- Readiness/health checks reflecting true business capability.
- Cache warmups or fallbacks so APIs meet SLAs once Redis returns.

### 14.1. Distinguishing readiness and liveness

If Redis is temporarily down:

- Endpoints that **only work with Redis up** may need readiness to report unavailable.
- Endpoints that **can bypass cache** do not necessarily need the instance pulled from load balancers.
- Liveness should not restart application pods endlessly merely because Redis blips for a few seconds.

Never rely solely on Redis `PING` to claim business recovery: a server may answer `PING` while slowly loading persistence, missing needed keys, pointing to the wrong cluster, or rejecting writes.

### 14.2. Never configure unbounded retries

During failover, bounded retries smooth over transient errors. Yet infinite retries with short fixed delays unleash a **retry storm** onto the recovering Redis.

Prefer:

- Timeouts fitting the request budget.
- Backoff with jitter.
- Bounded retry counts.
- Caps on in-flight / concurrent commands.
- Data-appropriate fail-open/fail-closed policies.
- Idempotency whenever writes may have executed before client timeout.

**A timeout does not mean Redis never received the write.** Commands like `INCR` or `XADD` may have executed right before connection drop. Automatic retries can double-count or duplicate events, breaking post-recovery correctness.

---

## 15. Designing fail-open / fail-closed into the RTO plan

When Redis fails, not every endpoint has to go down together.

Example:

| Feature | Role of Redis | Policy on failure | RTO impact |
|---|---|---|---|
| Product search | Cache | Fail-open with DB rate limits | API achieves low RTO even before Redis recovers |
| Login sessions | Session store | Temporary error / re-login per security | RTO tied to session store recovery |
| Login rate limiting | Security control | Fail-closed or backup limiter | Prevents Redis outage from bypassing protection |
| Checkout | Temporary price cache | Fetch canonical price before commit | Can continue if canonical source is healthy |
| Payment-command Stream | Critical intake | Reject new intake if durability unguaranteed | Intake RTO depends on durable intake recovery |

A blanket rule like "Redis down returns HTTP 500 everywhere" stretches business RTO needlessly. Conversely, swallowing all Redis errors so APIs always return 200 hides lost data, broken idempotency, or skipped security checks.

**RTO is not improved by pretending features are healthy when required data is untrustworthy.** Anchor recovery criteria to correct business behavior.

---

## 16. Integrating with Spring Data Redis: connectivity does not equal durability

Spring Data Redis provides abstractions including:

- `StringRedisTemplate` and `RedisTemplate` for imperative Redis operations.
- `ReactiveRedisTemplate` for reactive operations with supporting drivers.
- Redis Repositories for entity hashes and TTLs within repository scope.
- Redis Streams, Pub/Sub, and specialized APIs.

These APIs **do not pick RPO/RTO automatically**. Actual durability depends on Redis server configuration, topology, storage, write confirmation, and business recovery logic.

Simple example:

```java
@Service
public class CartStateService {

    private final StringRedisTemplate redis;

    public CartStateService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveCart(String userId, String serializedCart) {
        redis.opsForValue().set(
                "cart:v1:" + userId,
                serializedCart,
                Duration.ofDays(7)
        );
    }

    public String loadCart(String userId) {
        return redis.opsForValue().get("cart:v1:" + userId);
    }
}
```

Corresponding imports:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
```

This code writes a value and a TTL, yet **does not guarantee**:

- AOF has fsynced.
- A replica received the write.
- The latest backup includes the write.
- The cart survives failover.
- Restoring all carts takes under 5 minutes.

If `saveCart` must guarantee "saved carts are never lost", build appropriate architecture and confirmation mechanisms—not just `try/catch` around `set`.

### 16.1. Redis transactions do not solve RPO alone

`MULTI`/`EXEC` groups Redis commands to execute sequentially, without making writes durable across all crash modes. Likewise, Spring's `@Transactional` does not commit Redis and SQL atomically together.

When an entity spans both Redis and a database:

```text
1. SQL commit succeeds.
2. App writes Redis cache.
3. Redis failover drops the latest write.
```

If Redis is purely a cache, rebuild it. If Redis holds unique business state, use a more durable mechanism or reconciliation.

### 16.2. Note TTL behavior after restore

Expiring keys restored from snapshots or AOF preserve expiration semantics. Redis stores deadlines using timestamps suited to the persistence format. Upon recovery, already-expired keys may not be restored as live keys.

Thus, post-restore key counts can be smaller than pre-incident counts even when backups are uncorrupted. Distinguish:

- Data **lost unintentionally** due to an older recovery point.
- Data **expired legitimately** per TTL.
- Data **evicted** prior to the snapshot.
- Data **trimmed/deleted** by application logic.

For sessions or tokens, never extend expiration windows merely to hit recovery aesthetics: security lifetimes must be respected.

---

## 17. Designing checkpoints and replayability for Redis Streams

When using Redis Streams for business events, RPO covers not only what stays on the server, but also knowing **which events have already been processed**.

Example:

```text
Producer emits OrderCreated
    |
    v
XADD orders:events *
    |
    v
Consumer reads event
    |
    v
Writes to orders database
    |
    v
XACK after successful processing
```

Risks:

1. Redis loses an event after `XADD` succeeded before durable persistence per failure model.
2. Consumer finishes processing yet crashes before `XACK` → event may be reprocessed.
3. Unprocessed events get trimmed prematurely by `XTRIM` → gone from the Stream.
4. Backup captures an older Stream state while the database holds newer side effects.
5. Producer times out and retries `XADD` → can emit duplicate events.

Design requirements:

- **Idempotent consumers:** reprocessing the same event never causes bad side effects.
- **Proper checkpointing/ACK:** never ACK before business logic succeeds.
- **Retention:** retain events long enough for slow consumers to catch up.
- **Replay:** have an event replay source if Redis Stream drops or trims data.
- **Reconciliation:** compare canonical source state against event consumption state.

For very critical transactions, a **transactional outbox** in the origin database eliminates the "business commit succeeded, event dispatch to Redis lost" gap. The outbox commits atomically with business data, and workers relay until completed.

Never equate Redis Streams with permanent archival logs; Streams can be trimmed/deleted and share the same persistence/replication risks as other Redis keys.

---

## 18. Building a backup/restore plan around RPO and RTO

A recovery plan must specify **recovery point**, **recovery source**, **actions**, and **success criteria**.

### 18.1. Defining the scenario

Example:

```text
Failure: loss of entire Redis primary VM and disk.
Remaining: replica in zone B, off-zone backup.
Targets:
  RPO <= 60 seconds for session store.
  RTO <= 10 minutes for login API.

Planned strategy:
  Prefer failing over to an eligible replica.
  If replica is also unavailable, restore from backup.
  Measure last protected write and time to resume serving.
```

These targets are **illustrative hypotheses**—unverified until replication lag, failover behavior, and backup restores are measured.

### 18.2. What belongs in a runbook?

An actionable runbook states:

1. **Trigger conditions:** which metrics/alerts confirm a real outage?
2. **Owners:** who handles Redis, who handles Spring Boot, who authorizes failover?
3. **Safe inspection commands:** checking Redis health, persistence, replication, topology.
4. **Failover mechanics:** automatic via Sentinel/Cluster/managed service or manual steps?
5. **Recovery source selection:** which replica is newest, which backup is valid?
6. **Preventing split-brain writes to old primary:** avoiding dual writers during partitions.
7. **Restoring client connectivity:** endpoints, DNS, credentials, TLS, driver reconnect.
8. **Post-recovery verification:** test reads/writes, check TTLs, sample keys, event backlog, latency.
9. **Data reconciliation:** identify business operations potentially lost or duplicated.
10. **Timestamps and findings:** log detection time, recovery start, service resumption, and verification completion.

Never embed Redis passwords, backup access keys, or sensitive payloads directly in public runbooks. Use secret managers and restricted access.

### 18.3. Non-destructive inspection commands

On a Redis with appropriate read permissions:

```redis
PING
INFO server
INFO persistence
INFO replication
INFO memory
INFO stats
ROLE
```

These inspect server, replication, persistence, and memory state at check time. In Redis Cluster, also verify slot ownership and topology per deployment.

**Never run** `FLUSHALL`, `FLUSHDB`, `DEBUG SEGFAULT`, `SHUTDOWN NOSAVE`, or crash production Redis to "test RPO" without an isolated environment and an approved plan. Conduct drills in staging simulating failure modes with controlled infrastructure tooling.

---

## 19. How to measure actual RPO during drills?

RPO is hard to measure merely by checking whether Redis is running. You need **evidence of the order/timestamps of acknowledged writes** and verify them after recovery.

A safe method in a test environment:

1. Generate a write workload of probe records with monotonic IDs and trusted timestamps.
2. Record **outside Redis** which IDs the application received success acknowledgments for.
3. Inject a controlled failure in the test environment.
4. Recover using the exact procedure planned for real incidents.
5. Read Redis data post-recovery.
6. Identify the newest preserved ID and which IDs/writes were lost.
7. Compare the timestamp of the earliest missing write against the incident time using agreed measurement rules.
8. Record results per failure mode, not just an average.

Example:

```text
Incident begins        : 12:10:00
Last acknowledged write: 12:09:59.900
Newest surviving write : 12:09:58.700

Estimated loss window ≈ 1.2 seconds
(for this probe stream and drill conditions).
```

Never take one 1.2-second trial and advertise Redis as "guaranteeing 1.2-second RPO". Repeat across varied loads, failure modes, disk/network profiles, and versions, tracking worst-case results relevant to business goals.

### 19.1. Last surviving writes may have gaps

Under concurrent writes from multiple clients, acknowledgment order and persistence order do not match a clean linear counter. Probes should use reconcilable IDs distinguishing **sent commands**, **Redis-executed commands**, and **app-acknowledged commands**.

Timed-out requests may still have executed, so never treat every HTTP 500 as proof that Redis did not write.

---

## 20. How to measure actual RTO during drills?

RTO must measure from outage onset until **the defined capability is serving again**.

A complete measurement:

```text
T0  Redis primary stops serving per requirements.
T1  Alert fires.
T2  Ops / automation starts action.
T3  New Redis primary or restored instance is up.
T4  Spring Boot reconnects and reads/writes succeed.
T5  Target business flows work correctly within latency SLO.
T6  Recovery verification completes.

Observed RTO = T6 - T0  (per target definition).
```

Break down intervals:

- **Detection time = T1 − T0**.
- **Response time = T2 − T1**.
- **Infrastructure recovery = T3 − T2**.
- **Application recovery = T5 − T3**.
- **Validation time = T6 − T5**.

If 80% of elapsed time is application recovery, speeding up Redis snapshots barely improves RTO. Conversely, if replaying a 100 GB AOF dominates, look at replay speed, disk throughput, and warm-standby architectures.

### 20.1. Does cache warmup count toward RTO?

Depends on business definition. If the API returns correct data yet latency jumps to 10 seconds for 20 minutes on an empty Redis while the latency SLO is under 1 second, calling the system "recovered" the instant `PING` succeeds is misleading.

State exit criteria explicitly:

```text
95% of requests served within target latency,
no severe data errors,
critical APIs verified,
error rate below agreed threshold.
```

If the application can serve from the origin store, you can restore core operation first and warm cache progressively, while protecting the origin against cache stampedes.

---

## 21. Estimating recovery time and data size

RTO hits a hard physical limit: **larger data requires more I/O and processing to recover**.

Suppose a dataset requires downloading 40 GiB from backup. Assuming an average effective transfer throughput of 200 MiB/s, theoretical transfer time alone is:

\[
40 \times 1024 / 200 \approx 204.8\text{ seconds}
\]

This is merely a **transfer-step estimate** at assumed throughput. Real RTO also includes:

- Selecting/fetching backup metadata.
- Integrity checks and decryption.
- Parsing/loading data into memory.
- Process startup and config application.
- Client reconnection.
- Verification and cache warming.
- Delays from IOPS, CPU, network, and backup-source limits.

You therefore cannot promise a 2-minute RTO for huge datasets just because "backups exist". Measure the full end-to-end process on production-like infrastructure.

### 21.1. Large AOFs can hurt RTO

AOF logging protects recent writes, yet recovery may replay many commands or load rewritten AOF structures depending on Redis version.

Tighter RPO often raises runtime or recovery I/O costs. Balance:

- Normal write latency.
- CPU/disk for snapshots and rewrites.
- Storage and backup footprint.
- Startup reload speed.
- Failover to a warm replica vs. cold restore.

**Low RPO does not automatically yield low RTO**; design and measure both.

---

## 22. Architectural options to improve RTO

### 22.1. Ready replicas for failover

A replica kept reasonably close to the primary avoids reading full backups from slow storage when one node dies. Properly failed over, RTO drops dramatically.

However, replication remains asynchronous, so RPO worsens if the replica lacks the newest writes.

### 22.2. Isolating failure domains

Placing primary and replicas in separate availability zones prevents a single physical failure from taking down both.

Weigh trade-offs:

- Network latency and data-transfer costs.
- Risk of network partitions splitting the cluster.
- Automatic replica promotion rules.
- Ensuring only a valid primary accepts writes.
- Placing backups outside shared fault zones.

### 22.3. Restorable backups and regular drills

An offsite backup matters only if you can actually restore it. Test throughput and time to spin up a fresh instance, load data, and validate correctness.

### 22.4. Rebuildable caches

When Redis is a cache, cache-aside patterns with origin load controls let APIs maintain very low RTO even before Redis fully recovers.

Keep cache warmups from overloading the database using bulkheads, concurrency limits, or prioritized preloading of hot keys.

### 22.5. Separating workloads with different RPO/RTO

Avoid needlessly mixing:

```text
disposable cache that can be wiped anytime
+
critical event streams
+
unsynced sessions
```

on one Redis instance sharing one persistence, eviction, backup, and failover policy, unless all trade-offs are explicitly accepted.

Separating Redis deployments or namespaces by criticality lets you:

- Prevent caches from pushing memory pressure onto critical Streams.
- Give caches appropriate eviction policies.
- Give critical data stricter persistence and backups.
- Maintain dedicated runbooks and recovery targets.
- Shrink blast radius from configuration or operational errors.

---

## 23. Avoid confusing eviction, TTL, and outage data loss

In Redis, a key can vanish for multiple reasons:

| Cause | Scenario | Assessment |
|---|---|---|
| TTL expiration | Session expires after 30 minutes per policy | Normal lifecycle |
| Redis eviction | `maxmemory-policy` removes keys | Normal for caches, dangerous for state |
| `DEL` / `UNLINK` | Application deletes explicitly | Intended or business bug |
| `FLUSHDB` / `FLUSHALL` | Bulk wipe | Operational hazard |
| `XTRIM` | Stream capped in length | Retention behavior |
| Restore from old snapshot | Missing writes newer than snapshot | Data loss from missed RPO |
| Failover to lagging replica | Missing un-replicated writes | Data loss from replication gap |
| Serializer/schema mismatch | Key exists, yet app cannot read it | Accessibility issue, not necessarily lost key |

Counting every missing key as an RPO incident skews metrics. Conversely, blaming every lost key on "TTL" hides durability bugs.

For Redis storing business data that must be retained, `maxmemory-policy` is critical. Depending on the policy, eviction can drop keys before TTL expires—violating durability if no external copy exists. Such workloads need capacity planning, suitable memory policies, and alerts.

---

## 24. RPO when using Redis as a distributed lock or idempotency store

Not all critical state looks like traditional data records. Consider Redis storing:

- Distributed locks.
- Deduplication / idempotency tokens.
- Rate limits and temporary quotas.
- In-flight transaction states.
- Worker cursors/checkpoints.

### 24.1. Distributed locks

If Redis loses lock state across failover, two workers can simultaneously believe they hold permission to mutate the same resource.

For critical operations, use **fencing tokens** or validation at the final target store—never rely solely on a Redis lock key surviving failover.

### 24.2. Idempotency tokens

If an API processed a payment and stored the idempotency key solely in Redis, losing that key in a crash can let a retried request execute again.

For critical idempotency, store unique transaction IDs and completion status in a durable database with unique constraints, using Redis purely to speed up lookups.

### 24.3. Rate limits

Losing Redis counters can reset quotas and let extra requests through. Acceptable on low-risk endpoints, whereas login/OTP limits need failover evaluation and fallback limiters.

### 24.4. Worker checkpoints

Losing checkpoints can cause massive event replays or skipped events if the app defaults to the latest offset. Checkpoints need persistence, retry, and recovery policies matching the event source and consumer idempotency.

**Common thread:** evaluate RPO by **the consequence of losing state**, not key size or TTL.

---

## 25. Monitoring RPO/RTO signals

A durability dashboard needs more than `Redis UP`. Track at least:

| Group | Signals | Relevance |
|---|---|---|
| Persistence | Latest RDB save time, save status, AOF fsync/rewrite health | RPO, write-loss risk |
| Replication | Primary/replica roles, link status, replication lag/offset | Failover RPO |
| Memory | Used memory, evictions, fragmentation, key count | Unintended key loss and capacity |
| Disk | Free space, IOPS, latency, write errors | RPO and restart speed |
| Backup | Latest successful backup time, age, offsite transfer results | Recoverability |
| Restore drills | Backup download time, data load time, app verification | Actual RTO |
| Redis client | Timeouts, reconnects, command errors, pool saturation | Application RTO |
| API | Error rates, latency, fallbacks, cache stampedes | Business RTO |
| Streams | Pending counts, consumer lag, trim/retention, replay health | Lost or duplicated events |
| Operations | MTTD, failover duration, drill cadence | Ability to meet RTO |

### 25.1. Tie alerts to targets

For instance, if target RPO for a feature is 60 seconds, rising replication lag or repeated AOF fsync errors must trigger alerts even while Redis still answers `PING`.

If backups are required every 15 minutes yet the latest successful copy is 3 hours old, dashboards must never look green merely because "Backup job is running".

### 25.2. Verify monitoring quality

A good alert drives clear action:

- Who receives the alert?
- What threshold is warning vs. incident?
- Are planned Redis restarts suppressed appropriately?
- Which non-destructive inspection commands should run?
- When must critical write capabilities be halted?
- Is there a customer and service-status communication plan?

Monitoring does not replace drills; yet drills without monitoring fail to detect real incidents early enough to meet RTO.

---

## 26. RPO/RTO specification template for a Redis workload

An architecture decision record might look like:

```yaml
workload: cart-session-store
owner: checkout-team
redisRole: primary-temporary-state
sourceOfTruth: redis-with-periodic-database-sync
businessImpact:
  dataLoss: "Users may lose unsynced cart changes"
  downtime: "Cannot view or edit shopping cart"
objectives:
  rpo: "60s"
  rto: "10m"
failureScenarios:
  - process-crash
  - primary-node-loss
  - zone-loss
persistence:
  rdb: enabled
  aof: enabled
  appendfsync: everysec
availability:
  replication: enabled
  failover: automatic
backup:
  offNode: required
  restoreTest: quarterly
applicationBehavior:
  whenRedisUnavailable: "Display temporary error / use safe fallback"
  retryPolicy: "Bounded retry with backoff"
verification:
  dataProbe: "Compare acknowledged-write IDs with restored IDs"
  serviceReady: "Cart reads/writes and latency target verified"
openRisks:
  - "Async replica can miss latest acknowledged write"
  - "Backup restore alone may exceed 10-minute RTO"
```

**This is a template document, not a config to load into Redis or proof targets are met.** Fields like `rpo`, `rto`, and `appendfsync` must be validated by testing on your real topology.

For a pure-cache workload, `sourceOfTruth` should point to the canonical database/API, and cache RPO can state "retention not required".

### Pre-production sign-off conditions

The business owner should confirm:

- RPO/RTO are official targets.
- Covered failure modes are explicitly listed.
- Implementation and operations owners are assigned.
- Drill metrics or assessment evidence exist.
- Remaining residual risks/limits are accepted.
- A regular re-test cadence and post-change review schedule exist.

---

## 27. Scenario analysis

### Scenario A — Product cache completely wiped

Redis product cache loses all keys, yet PostgreSQL remains intact and the API reads PostgreSQL on cache misses.

**Analysis:** product data is not lost. **Cache** RPO is not a major issue, yet read-feature RTO and PostgreSQL overload risk from cold-cache stampedes must be managed. Use bounded preloading or throttled warmups.

### Scenario B — AOF everysec, yet primary and replica fail together

The app uses AOF `everysec` with one replica in the same zone. A zone outage wipes out both nodes; the newest offsite backup is 20 minutes old.

**Analysis:** disaster RPO is not 1 second. For zone loss, recovery falls back to the cross-zone backup, and exposed data loss matches that backup's age and reliability.

### Scenario C — Failover takes 20 seconds, yet Redis drops the last write

Primary replies OK to an `XADD` event and dies before the replica receives it. Replica promotes in 20 seconds without the event.

**Analysis:** RTO is fast, while RPO fails if that event cannot be lost. Add write-loss mitigations, replay/reconciliation, or a stronger durable source.

### Scenario D — AOF intact, yet restore takes too long

AOF and backups retain all data with zero lost writes in testing. Still, Redis needs 45 minutes to load the dataset against a 10-minute business RTO.

**Analysis:** RPO passes, while RTO fails. Evaluate warm standbys, restore speed, dataset size, persistence rewrites, and application fallback paths.

### Scenario E — Replica caught up, yet data was accidentally deleted

An operator runs `FLUSHDB` on the primary, and the delete replicates to replicas.

**Analysis:** replication reflects valid Redis mutations—including business mistakes. Returning to prior state requires backups/restores or another canonical source.

### Scenario F — Redis UP, yet checkout still fails

Redis promoted a new primary, yet Spring Boot retains stale endpoints or times out before reconnecting. Checkout keeps returning 503.

**Analysis:** business RTO is not over. Count client reconnection and business verification time—never stop the stopwatch at Redis `PING`.

### Scenario G — Carts expire right after restore

The backup captured many cart keys with active TTLs. After restoring later, several keys have already expired.

**Analysis:** separate legitimate policy expirations from lost data due to stale backups. Never extend expired carts or security sessions artificially just to inflate restored key counts.

### Scenario H — Application retries write after timeout

Client sends `INCR`, hits a network timeout waiting for the reply, and retries. After recovery, the counter incremented twice.

**Analysis:** storage durability does not solve network idempotency. Design around request IDs, conditional operations, or reconciliation.

### Scenario I — Redis Stream kept data, yet consumers lag badly

Redis lost zero records, yet consumers process 50 events/s while producers emit 500 events/s. After restart, clearing the backlog takes hours.

**Analysis:** this is a **business capacity recovery time** problem even though persistence saved the data. RTO must cover backlog drain if business flows remain degraded until caught up.

---

## 28. Common mistakes and fixes

| Mistake | Why it is wrong | Fix |
|---|---|---|
| "AOF everysec guarantees 1-second RPO" | Fsync and failure modes lack strict 1s bounds | Define scenarios, measure, document limits |
| "Having replicas means zero lost writes" | Replication is usually async | Measure lag, consider wait checks, add replay |
| "Sentinel/Cluster guarantees RPO 0" | Fast failover does not ensure newest writes replicated | Evaluate RPO independently of RTO |
| "Having backups guarantees low RTO" | Restoring huge datasets can take very long | Drill full end-to-end restores |
| "RDB snapshot every 60s means backups at most 60s old" | Snapshots can fail/lag or remain un-transferred | Monitor successful backups and offsite age |
| "Replicas replace backups" | Logic errors and deletes replicate | Keep versioned backups outside failure domains |
| "PING succeeding means recovered" | App may still fail reads/writes, hit high latency, or miss data | Verify business flows and latency |
| "Losing cache equals losing enterprise data" | Caches rebuild from canonical sources | Classify sources of truth |
| "Redis is just a cache, so RTO doesn't matter" | Cache loss can crush DBs and stall APIs | Set RTO per business capability, not just node |
| "TTL is backup" | TTL is automatic expiration | Separate lifecycle from persistence/backups |
| "Keep Redis up by ignoring all errors" | Can violate permissions, finances, idempotency | Choose fail-open/closed per domain |
| "WAIT proves all replicas fsynced" | WAIT checks replication progress, not disk sync | Understand command semantics and limits |
| "min-replicas-to-write is synchronous replication" | Only gates writes on replica health | Never promises every write ACKed on replicas |
| "RTO excludes detection time" | Users already suffer outage before alerts fire | Measure from incident onset to business recovery |
| "One passing drill is enough" | Load, data size, topology, and failure modes evolve | Drill periodically and after major changes |
| "Timeout means the command didn't execute" | Redis may have processed it before disconnect | Use idempotency and reconciliation |
| "RPO=0 comes solely from Redis server settings" | Disks, replication, failover, apps, and zones all matter | Design end-to-end and use proper canonical stores |

---

## 29. A 10-step process to set and verify objectives

A Spring Data Redis team can follow this process:

1. **Inventory Redis workloads.** Caches, sessions, carts, streams, locks, rate limiters, business state.
2. **Identify sources of truth.** Mark what is rebuildable vs. what causes irreversible harm if lost.
3. **Estimate impact.** What breaks if 1 second, 1 minute, or 1 hour of data vanishes? What if down for 1 minute, 10 minutes, or 1 hour?
4. **Set owned RPO and RTO.** Use measurable numbers and explicit start/end definitions.
5. **Select failure models.** Process crash, disk loss, node loss, zone loss, operator error, region loss.
6. **Design protection layers.** RDB, AOF, replication, failover, backups, zone isolation, replay.
7. **Design application behavior.** Timeouts, reconnects, retries/idempotency, cache fallbacks, Stream checkpoints, fail-open/closed.
8. **Write runbooks.** Backup locations, promote/restore steps, secrets, owners, post-recovery checks.
9. **Drill and measure.** Use externally logged acknowledged probes to measure lost writes; time until business stability.
10. **Monitor and refresh.** Configure alerts; re-drill as data grows, Redis upgrades, topology shifts, or traffic changes.

After each drill, record:

```text
Drill date:
Workload and Redis version:
Failure mode:
Dataset size and write rate:
Last acknowledged write ID:
Newest recovered write ID:
Measured RPO:
Outage start timestamp:
Business resumption timestamp:
Measured RTO:
Manual actions required:
Open unresolved risks:
Approver:
```

These records turn RPO/RTO from architectural slogans into evidence-backed decisions.

---

## 30. Summary

In Spring Data Redis, **RPO** answers *how much recent data loss is acceptable at most*, while **RTO** answers *how long restoring functionality can take at most*. Both targets must stem from business impact and be verified per failure scenario.

- **RDB** protects via snapshots; RPO depends on snapshot intervals and the reliability of the actually restorable point.
- **AOF** narrows write-loss windows in certain failures; `appendfsync always/everysec/no` trade durability against performance rather than guaranteeing absolute RPO.
- **Replication, Sentinel, and Cluster** boost availability, yet async replication can still drop latest writes on failover.
- **Off-failure-domain backups** cover disk loss, zone loss, and accidental deletions; only restore-tested backups provide real confidence.
- **Spring Data Redis clients** must reconnect, handle timeouts/retries/idempotency, and recover processing flows—otherwise app RTO exceeds Redis server RTO.
- **Redis as pure cache** can tolerate losing all keys; **Redis holding unique business state** needs far stricter targets and protections.
- **Achieved RPO/RTO** must be measured via drills checking acknowledged writes, end-to-end recovery time, and business readiness criteria.

A dependable setup is not the one with the most Redis flags enabled, but the one **with business-approved objectives, clearly understood limits, and proven recoverability under realistic conditions**.

### References

- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis — High Availability with Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Redis — Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis — WAITAOF](https://redis.io/docs/latest/commands/waitaof/)
- [Redis — CONFIG SET](https://redis.io/docs/latest/commands/config-set/)
- [Redis — INFO](https://redis.io/docs/latest/commands/info/)
- [Redis — BGSAVE](https://redis.io/docs/latest/commands/bgsave/)
- [Spring Data Redis — Reference Documentation](https://docs.spring.io/spring-data/redis/reference/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
