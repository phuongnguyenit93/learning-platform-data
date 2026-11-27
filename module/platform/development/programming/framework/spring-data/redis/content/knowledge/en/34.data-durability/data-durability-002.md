# RDB Snapshots and the Data-Loss Window in Spring Data Redis

## 1. Context: Redis is very fast, but a successful write is not guaranteed to be on disk

Spring Data Redis enables Java applications to write and read data from Redis via `RedisTemplate`, `StringRedisTemplate`, Reactive Redis, Repositories, or Spring Cache. Those APIs normally operate against **the state Redis is serving at the moment the command is processed**. However, if Redis loses power, its process is killed, or the server fails, a different question arises:

> How much of the written state can Redis reconstruct when starting up from durable data on disk?

One of Redis's persistence mechanisms is the **RDB snapshot** (*Redis Database snapshot*). RDB saves a point-in-time snapshot of the dataset into a binary file, commonly named `dump.rdb`. When Redis restarts, a valid RDB file can be loaded to restore the previously saved state.

However, RDB is a **point-in-time snapshot**, not a log recording every individual command. With RDB alone, changes occurring **after the point reflected by the last snapshot** can disappear when Redis must recover from that snapshot.

Example:

```text
10:00:00  Snapshot starts, state has 1,000 orders
10:00:12  Snapshot finishes and is saved to disk
10:00:15  Order o-1001 is written to Redis
10:00:20  Order o-1002 has its status updated
10:00:25  Redis crashes, RAM data is lost
10:01:00  Redis restarts from the 10:00:00 snapshot

Possible outcomes:
  - o-1001 is missing from the recovered data
  - o-1002 reverts to its state at 10:00:00
```

You must distinguish **when the snapshot starts**, **when the snapshot file finishes**, **when Redis reports a successful write**, and **when data is recovered**. This is the root of many misunderstandings about acceptable data loss when using RDB.

This lesson explains the RDB mechanism, the *data-loss window*, factors affecting RPO/RTO, how to observe Redis, and how to choose appropriate Spring Data Redis application designs.

### Learning objectives

After this lesson, you can:

1. Explain what an RDB snapshot saves and what it does not save.
2. Distinguish `SAVE`, `BGSAVE`, automatic `save` rules, and snapshot timestamps.
3. Understand the `fork` and **copy-on-write (COW)** mechanisms during background snapshotting.
4. Predict changes at risk of loss after an outage, including updates and deletions.
5. Explain why snapshot schedules are not a hard RPO guarantee.
6. Read `INFO persistence` metrics, `LASTSAVE`, and `BGSAVE` status.
7. Compare RDB with AOF, replication, failover, and independent backups.
8. Design failure tests, backup/restore workflows, monitoring, and retention policies.
9. Understand the limits of Spring Data Redis: a `SET` returning success does not mean RDB was just updated.
10. Choose appropriate durability levels for caches, sessions, queues, counters, and critical business data.

## 2. What is RDB?

**RDB (Redis Database)** is Redis's binary snapshot format. A snapshot describes Redis's dataset state at a logical point in time, including the various data types Redis holds and necessary metadata such as key expiration deadlines.

RDB is created by Redis to:

- Restart from a saved state.
- Create data copies for backups or environment migration.
- Support certain replication/full synchronization workflows per Redis mechanics.
- Reduce storage costs compared to replaying an entire command history in certain workloads.
- Recover relatively efficiently when data size and I/O speed permit.

RDB is **not**:

- An event log containing every `SET`/`DEL` command after the last snapshot.
- An application transaction log.
- An ACK system proving business state is durably persisted across all failures.
- A safe backup if only a single file sits on the same disk as Redis.
- A self-protection mechanism against the application writing/deleting bad data and then snapshotting it.
- A transaction synchronization mechanism between Redis and PostgreSQL, MySQL, or external services.

### 2.1. A snapshot is not a per-request copy

Suppose the application executes:

```redis
SET cart:101:status OPEN
SET cart:101:status CHECKED_OUT
```

If the snapshot occurs between the two commands, RDB may store `OPEN`; if after the second command, it may store `CHECKED_OUT`.

RDB stores **the state at the snapshot point** and does not need to store both commands in the file. If a command runs after the snapshot point, it does not automatically appear in RDB before the next snapshot is created.

### 2.2. RDB is usually named dump.rdb

Relevant configuration parameters:

```conf
dbfilename dump.rdb
dir /var/lib/redis
```

The file is written in the configured Redis directory. Actual filenames and paths depend on the container image, Redis distribution, managed service, and environment configuration.

Redis may also have another persistence mode like AOF active alongside it. Never assume `dump.rdb` is the sole recovery source just because the file exists.

## 3. Which point in time does an RDB snapshot reflect?

At the core of RDB is a **consistent snapshot at a logical point in time**. When Redis runs `BGSAVE`, it typically spawns a child process via `fork` (on supported operating systems) so the child writes the snapshot while the parent continues serving client commands.

```text
Timeline
-------------------------------------------------------------------->

t0                    t1                  t2                t3
|                     |                   |                 |
BGSAVE starts         SET key=A           BGSAVE finishes   crash
snapshot fork         SET key=B           new RDB file      RAM lost
|                                         |
+------------------- child writes RDB ----+
|
+------------------- parent keeps serving commands ------------------->

RDB reflects the logical state at t0,
and does not automatically append SET commands from t1.
```

The subtle trap: **`LASTSAVE` typically reflects the time of the successful save**, which is not necessarily the exact time the dataset state in RDB was captured. If `BGSAVE` takes many seconds, there is a gap between when it started and when the file finished writing.

Concrete example:

```text
10:00:00  Parent forks child for BGSAVE.
10:00:08  Application writes inventory:42 = 90.
10:00:19  Child finishes RDB, Redis reports save succeeded.
10:00:21  Redis crashes, RAM is lost.
10:01:00  Recovery from RDB.

LASTSAVE may reflect around 10:00:19.
Yet the RDB data was captured around 10:00:00.

The write at 10:00:08 may not be contained in that RDB.
```

This is why **you must not interpret `now - LASTSAVE` as a strict upper bound on data that could be lost**. A snapshot in progress or just completed can represent a state older than the file completion timestamp.

### 3.1. Do changes during BGSAVE disappear from a running Redis?

No. The parent continues accepting and applying commands in RAM normally, subject to available resources. For example:

```redis
SET cart:101:state CHECKED_OUT
GET cart:101:state
```

`GET` can return `CHECKED_OUT` right after `SET` succeeds. However, the child is writing the snapshot based on the state at fork time; that newer version is not guaranteed to be in the RDB file currently being written.

Keep these separate:

```text
Live state that clients are reading
    differs from
Snapshot state currently being written
```

### 3.2. RDB does not continuously catch up to the latest state

The child process does not continuously append every new mutation occurring in the parent into the same snapshot. Redis uses a single logical snapshot point to ensure snapshot consistency. Subsequent writes require another snapshot or an additional persistence mechanism to survive a crash.

## 4. BGSAVE works via fork and copy-on-write

Visualizing the background mechanism:

```text
Redis parent (serving clients)
         |
         | BGSAVE
         v
      fork()
         |
   +-----+----------------------------------+
   |                                        |
   v                                        v
Child process                           Parent process
writes RDB based on                     continues SET, GET,
logical snapshot t0                     DEL, INCR, ...
   |                                        |
   | reads memory pages                     | writes mutations
   | to flush to disk                       v
   |                                  Copy-on-write pages
   |                                        |
   +--> Temp RDB file --> complete --> publish RDB file
```

When `fork` creates the child, parent and child can initially share many memory pages under OS memory management. When the parent modifies a page after the fork, **copy-on-write** forces the OS to preserve the old page for the child and allocate/keep a new page for the parent.

Thanks to this, Redis continues serving clients while the child generates the snapshot. In exchange, `BGSAVE` consumes additional CPU, I/O, page tables, and can increase memory usage.

### 4.1. Why can BGSAVE increase RAM usage?

A write-heavy workload while a snapshot is running can touch many memory pages. Modified pages require copy-on-write, increasing physical memory usage.

Example:

```text
Redis data before BGSAVE         : 8 GiB
BGSAVE running                   : child needs t0 snapshot
Parent receives heavy writes     : many pages are modified
Copy-on-write memory             : increases significantly
```

There is no simple formula like "COW is always 10% of RAM" or "BGSAVE always needs double RAM". The increase depends on write patterns, dataset size, `BGSAVE` duration, allocator, OS, and other dynamics.

Memory headroom is essential, especially in containers or servers using Redis as an important data store.

### 4.2. Fork can introduce brief latency on the parent

Creating a child via `fork` on a large dataset can take noticeable time and cause a temporary pause on the Redis parent. Redis does not need to block all traffic for the entire time the child writes the snapshot, but **the fork moment itself** still has overhead.

The risk is higher when:

- The dataset is large.
- The machine lacks RAM or memory overcommit settings are misconfigured.
- There are millions of keys.
- Disk is too slow, making snapshots run long.
- CPU faces contention with other workloads.
- Redis runs in a virtualized/containerized environment with tight resource limits.

`BGSAVE` reduces blocking compared to `SAVE`, yet **it is by no means completely free**.

### 4.3. How does the child write RDB?

In the standard model, Redis writes RDB to a temporary file and replaces the target snapshot file only after successful creation, preventing an incomplete file from immediately overwriting the previous valid RDB.

However, that is no reason to skip:

- Verifying the RDB file after backup.
- Checking disk space.
- Persistence directory write permissions.
- Filesystem health.
- An independent off-host backup plan.
- Crash scenarios during disk/OS-level steps.

Reliable recovery requires real backup and restore testing, not merely trusting that a `BGSAVE` command returned success.

## 5. How do SAVE and BGSAVE differ?

Redis provides two key commands:

```redis
SAVE
BGSAVE
```

| Aspect | `SAVE` | `BGSAVE` |
|---|---|---|
| Execution mode | Saves snapshot synchronously | Spawns child/background save |
| Impact on command handling | Can block the server while executing | Parent typically continues serving commands |
| Fork mechanism | No standard BGSAVE child model | Relies on fork/COW in typical deployments |
| Latency impact | Can be very long with large datasets | Has fork, COW, and I/O overhead |
| Operational suitability | Only in intentional cases where blocking is understood | Standard approach for runtime snapshots |
| Return semantics | Returns when save completes/errors | Typically confirms background save started, not that child finished |
| Post-command monitoring | File/restore status | `INFO persistence`, `LASTSAVE`, BGSAVE logs |

### 5.1. Why should SAVE not be run routinely in production?

`SAVE` can block Redis while the dataset is written out. In systems with high request volume and low latency requirements, this impact can be severe.

Avoid using `SAVE` as a way to "guarantee data is persisted" for individual Java requests. When a runtime snapshot is needed, normally use `BGSAVE` paired with completion monitoring.

### 5.2. BGSAVE returning OK does not mean the file is updated yet

When calling:

```redis
BGSAVE
```

Redis may respond that the background save task has started. You must follow up by checking:

```redis
INFO persistence
LASTSAVE
```

or Redis logs to know whether the operation succeeded or failed.

An application must not call `BGSAVE` and immediately declare all recent writes safe against power loss, because:

1. The snapshot may not be finished yet.
2. The snapshot reflects fork time and does not automatically contain writes after that point.
3. Recovery still depends on file integrity and the storage system.
4. If AOF is also enabled, recovery rules may differ from RDB-only.

### 5.3. Calling BGSAVE while another is already running

Redis does not spawn unlimited parallel snapshot children for every request. When a background save is already in progress, commands or schedulers must respect Redis execution constraints and related options.

Therefore, **do not turn every business request into a `BGSAVE` call**. Doing so does not provide instant durability, and easily causes fork/disk overhead, memory contention, and tangled snapshot states.

## 6. Automatic `save` rules in redis.conf

Redis supports configuring RDB creation based on elapsed time and number of data changes.

Example:

```conf
save 900 1
save 300 10
save 60 10000
```

How to read this:

- After roughly **900 seconds**, if at least **1** data change has occurred per save tracking, Redis may initiate a snapshot.
- After roughly **300 seconds**, if at least **10** changes occurred, Redis may initiate a snapshot.
- After roughly **60 seconds**, if at least **10,000** changes occurred, Redis may initiate a snapshot.

These lines are **independent trigger conditions**; satisfying any one condition when Redis can execute background work can trigger a snapshot. These values are **illustrative** and should not be assumed as universal defaults across every Redis version.

### 6.1. The setting does not mean "snapshot strictly every 60 seconds"

Suppose only this rule is configured:

```conf
save 60 10000
```

If over 10 minutes the system only sees 9,999 changes since the relevant baseline, the 10,000-change threshold is not met. Nothing in this rule forces Redis to take a snapshot strictly every 60 seconds.

Conversely, if the system sees 100,000 writes/s, the 10,000-change threshold can be reached very quickly, yet timing, an already running background save, scheduling, resource availability, and failures still apply.

**`save <seconds> <changes>` is a combined time-and-mutation trigger condition, not a hard real-time snapshot interval.**

### 6.2. Completion time does not match trigger-satisfaction time

Even once a condition triggers `BGSAVE`, Redis still must fork and write the entire snapshot to disk. With a large dataset, this can take a long time.

The data-loss window upon crash depends not only on configured intervals, but also on:

```text
- Logical timestamp of the last restorable snapshot
- Changes occurring after that snapshot point
- File write duration and I/O
- Whether a newer snapshot is running or failed
- Whether trigger conditions have been met yet
```

### 6.3. Viewing the active configuration

In an environment with permissions:

```redis
CONFIG GET save
CONFIG GET dbfilename
CONFIG GET dir
```

`CONFIG GET save` output reflects the active runtime rules, which can differ from the startup config file if an administrator altered them at runtime.

Any changes must follow production change management. A `CONFIG SET` change may not persist across restarts unless persisted as supported by the environment.

### 6.4. Disabling automatic RDB

A setting like:

```conf
save ""
```

disables automatic RDB snapshot rules in typical configurations. It **does not mean data has become safer**.

Without AOF or another backup, disabling RDB can cause Redis to restart without recovering prior RAM data. In some pure-cache systems this is acceptable; in systems holding critical state, it is very dangerous.

Disabling auto-save also does not necessarily stop manual RDB creation or replication-related RDB behavior. Always verify the overall persistence configuration.

## 7. The data-loss window: what is RPO?

**Recovery Point Objective (RPO)** describes the time-equivalent amount of data a system targets as acceptable to lose during an incident.

If a system allows an RPO of 5 minutes, the architecture must be designed and verified so that in-scope failure scenarios do not lose more data than that target allows.

For RDB-only Redis, **actual RPO depends on the last restorable snapshot and its capture timestamp**. A `save` rule does not automatically become a hard RPO guarantee.

### 7.1. Mental formula

Let:

```text
T_snapshot = logical point in time reflected by the recovered RDB
T_failure  = time when Redis lost volatile state
```

Then changes missing from RDB can lie in:

```text
(T_snapshot, T_failure]
```

Window length:

```text
LossWindow ≈ T_failure - T_snapshot
```

This is an intuitive model for RDB data. It should not be taken as exact across all scenarios involving AOF, replication, failover, clock skew, shutdown saves, or storage failures.

The strength of this model is forcing you to identify the **actual snapshot capture point**, rather than looking only at when the file finished writing.

### 7.2. Timeline RPO example

```text
10:00:00  BGSAVE #1 forks
10:00:20  BGSAVE #1 completes successfully
10:00:30  SET user:1 updated
10:01:15  DEL key:old
10:02:00  INCR counter:orders
10:03:00  Redis crashes; only RDB #1 is valid
```

When restarting from RDB #1:

- `user:1` may revert to its 10:00:00 version.
- `key:old` may **reappear** if it existed in the snapshot before being `DEL`eted.
- `counter:orders` may **decrease** compared to the last value observed by users.
- Keys created after 10:00:00 may not exist.
- TTL changes after 10:00:00 may not be preserved.

Because the snapshot reflects state around 10:00:00, the logical loss window can be roughly 3 minutes, **not merely 2 minutes and 40 seconds since BGSAVE finished**.

### 7.3. RPO must account for writes, updates, and deletes

Many people picture "data loss" only as losing newly created keys. In reality, restoring an older snapshot can cause:

| Operation after snapshot | Possible state observed after restore |
|---|---|
| `SET new:key value` | New key disappears |
| `SET existing:key newValue` | Value reverts to old version |
| `HSET user:1 status ACTIVE` | Hash field reverts to old state |
| `INCR counter` | Counter rolls backward |
| `LPUSH queue item` | New item is missing |
| `XADD stream * ...` | New stream entry disappears |
| `DEL sensitive:key` | Deleted key **may reappear** |
| `EXPIRE session:key 300` | Post-snapshot TTL changes are not preserved |
| `PERSIST key` | Old expiration deadline may return |
| `SADD membership item` | New member may disappear |
| `SREM membership item` | Removed member may return |

In particular, **delete rollback** is critical for tokens, sessions, access rights, and revocation lists. If the application treats Redis as the sole source confirming a token was revoked, restoring an old snapshot can resurrect state the business believed was deleted.

### 7.4. No hard bound from `save` alone

Even if you configure:

```conf
save 60 1
```

you must not claim "at most 60 seconds of data can ever be lost in any failure" because:

- Snapshot start and completion times differ.
- Redis may already be running another background save.
- Forking or writing RDB can fail.
- Disk can run out of space or error.
- The process can crash mid-snapshot.
- The new snapshot may not survive a storage/system failure.
- `save` settings are trigger conditions, not a client commit protocol.
- Persistence/replication/restore behavior can alter the actual recovery point.

A **target RPO** must be backed by fault-injection testing, monitoring, a backup strategy, and storage guarantees.

## 8. RPO and RTO are two different objectives

**RTO (Recovery Time Objective)** is the target time to restore service operation after an outage.

RDB affects both:

- **RPO:** how old is the state reflected by the snapshot?
- **RTO:** how long does it take to locate the snapshot, load the file, start Redis, warm caches, and resume application traffic?

Example:

```text
Last snapshot reflects data from 10:00.
Redis crashes at 10:04.
Redis restarts and serves requests at 10:07.
```

Conceptual summary:

```text
Potential data-loss window ≈ 4 minutes  (actual incident RPO)
Service downtime           ≈ 3 minutes  (actual recovery time)
```

These are two distinct quantities. Very frequent snapshots may reduce unsaved changes, yet if the file is huge and loading is slow, RTO can still be long.

### 8.1. Does Redis recover from RAM, RDB, or elsewhere?

Once a process crashes, its RAM is no longer a durable source. On restart, Redis may:

- Load RDB if enabled and an appropriate file exists.
- Load AOF if AOF is enabled and chosen by Redis as the recovery source.
- Start with an empty dataset if no valid persistence exists.
- Sync data from a primary if the instance starts as a replica and performs replication sync.
- Be replaced by another replica via Sentinel/Cluster failover.

Accurately measuring RPO/RTO requires identifying the **actual recovery path of your deployment**, not just a filename on the filesystem.

## 9. Common RDB configuration

An illustrative Redis configuration:

```conf
# Create RDB when save conditions are met.
save 900 1
save 300 10
save 60 10000

# Persistence filename and directory.
dbfilename dump.rdb
dir /var/lib/redis

# Compress RDB when appropriate.
rdbcompression yes

# Verify checksum for RDB.
rdbchecksum yes

# How to react when background save fails.
stop-writes-on-bgsave-error yes
```

This is an example configuration, not a mandatory template and not a claim that these exact values are defaults in every Redis version/distribution.

### 9.1. `rdbcompression`

RDB can use compression to reduce file size. This trades CPU for disk space and I/O. Actual impact depends on data types, data compressibility, payload sizes, and storage hardware.

Do not assume RDB is always smaller than RAM data by a fixed ratio. Measure snapshot size on your real workload.

### 9.2. `rdbchecksum`

Checksums help detect certain file corruption errors during verification/reading. Checksums do not replace:

- Off-host backups.
- Storage redundancy.
- Disk monitoring.
- Restore testing.
- Access controls and encryption of sensitive data.
- Protection against ransomware or human error.

A file with a valid checksum can still contain **stale state that is completely valid structurally**.

### 9.3. `stop-writes-on-bgsave-error`

When a background save fails and Redis is configured to protect data integrity, the server can reject write commands instead of continuing to accept writes without reliable snapshotting.

Scenario:

```text
BGSAVE fails due to disk full.
    |
    +--> Redis logs persistence error.
    |
    +--> If stop-writes-on-bgsave-error is enabled:
             some write commands may be rejected
             instead of silently continuing to accept data.
```

This is an **operational detection/protection mechanism**, not a guarantee that un-snapshotted data is saved. When the application receives write errors, treat them as real failures; never assume `SET` always succeeds just because Redis still answers `PING`.

Disabling this option can make sense in systems that accept data loss and prioritize availability, but it must be a deliberate operational decision made with clear understanding of RPO, not a way to "fix" a full disk.

### 9.4. Disk space and directory write permissions

If Redis cannot write to `dir`:

- `BGSAVE` can fail.
- No new RDB is created.
- `LASTSAVE` stops advancing.
- Some write commands may be rejected depending on config.
- Spring applications may see exceptions from Redis commands.
- On restart, the system can only fall back to an older snapshot or have no valid snapshot.

Therefore, monitor **snapshot success status**, not just Redis RAM usage.

## 10. Observing RDB status with redis-cli

Commonly used commands:

```redis
INFO persistence
LASTSAVE
CONFIG GET save
CONFIG GET dbfilename
CONFIG GET dir
```

To inspect persistence metrics, you can run:

```bash
redis-cli INFO persistence
```

Common fields in `INFO persistence`:

| Field | How to interpret it |
|---|---|
| `rdb_bgsave_in_progress` | Whether a background RDB save is currently running |
| `rdb_last_save_time` | Unix timestamp of the most recent successful RDB save per Redis |
| `rdb_changes_since_last_save` | Number of tracked changes since the last save per Redis |
| `rdb_last_bgsave_status` | Result of the latest background save, e.g., `ok` or `err` |
| `rdb_last_bgsave_time_sec` | Duration of the previous `BGSAVE` in seconds |
| `rdb_current_bgsave_time_sec` | Elapsed seconds of the active `BGSAVE`, when running |
| `rdb_last_cow_size` | Estimated/recorded copy-on-write size for the latest `BGSAVE` |
| `rdb_saves` | Number of RDB saves recorded in supported versions |
| AOF fields | Reflect AOF status if enabled |

Field names can vary across Redis versions and metric exporters. Inspect the actual output from your Redis deployment.

### 10.1. Interpretation example

Suppose:

```text
rdb_bgsave_in_progress:0
rdb_last_bgsave_status:ok
rdb_last_save_time:1893456000
rdb_changes_since_last_save:15230
```

What you can conclude:

- No `BGSAVE` is currently running at the moment of observation.
- The most recently recorded `BGSAVE` succeeded.
- A successful save timestamp is present.
- Redis tracked a number of changes since that save point.

However, **you cannot conclude with certainty**:

- Every write before `rdb_last_save_time` is inside the snapshot.
- No writes can be lost if a crash happens right now.
- The RDB file has been backed up off-host.
- The file on disk is free of corruption.
- 15,230 changes equal 15,230 keys or 15,230 business transactions.

`rdb_changes_since_last_save` is an operational persistence metric; it is not an exact count of business records at risk.

### 10.2. Using LASTSAVE

```redis
LASTSAVE
```

Returns a Unix timestamp representing the most recent successful save time according to Redis.

Example:

```text
1893456000
```

You can convert the timestamp into human-readable time in the appropriate timezone. Remember:

> **LASTSAVE is the save completion/success timestamp, not necessarily the logical data timestamp at `BGSAVE` fork time.**

When calculating the data-loss window, using `LASTSAVE` alone without knowing when the snapshot started introduces error. Combine Redis logs, `BGSAVE` duration history, and metrics for a grounded estimate.

### 10.3. Monitoring snapshot progress

Example:

```redis
BGSAVE
INFO persistence
```

If `rdb_bgsave_in_progress:1`, the snapshot is still running. Wait for completion and check `rdb_last_bgsave_status`. Do not set up tight polling loops or repeatedly invoke `BGSAVE` in production.

In environments requiring point-in-time backups, procedures must handle cases where `BGSAVE` fails to start or errors out.

## 11. What happens if a crash occurs mid-BGSAVE?

Suppose:

```text
T0: RDB #1 already exists and is valid.
T1: Redis starts BGSAVE #2.
T2: Parent writes lots of new data.
T3: Server crashes before BGSAVE #2 finishes.
```

Normally, an incomplete RDB #2 does not become a completed snapshot for recovery. Redis may have to recover from **RDB #1**, making the data-loss window longer than estimated from when `BGSAVE #2` started.

Illustration:

```text
10:00   RDB #1 finishes, capturing state around 09:59:45
10:05   BGSAVE #2 starts
10:05+  Thousands of writes succeed in RAM
10:06   Redis crashes before BGSAVE #2 finishes
10:07   Redis restores from RDB #1
```

Data modified after #1's snapshot point can be lost, **not merely changes after 10:05**.

### 11.1. If BGSAVE fails repeatedly

Suppose the disk is full from 10:00 to 11:00. Even with:

```conf
save 60 1
```

no new snapshot can be created. If the application continues writing because configuration allows it, the unsaved data window can grow very long.

Monitoring should therefore alert on:

```text
Time since last successful save is growing.
rdb_last_bgsave_status = err.
Low free disk space.
Redis write traffic continues.
```

In an RDB-only system with tight RPO, this is a high-severity alert, not merely an informational log.

### 11.2. Storage failure vs. process crash

A Redis process crash where the disk still retains the RDB file is one class of failure. Total disk/host loss, filesystem errors, or corruption is another.

If backups reside only on the same failed disk, there is no snapshot left to recover from. Hence, **RDB persistence** and **independent backups** must be clearly distinguished.

## 12. Data loss scenarios involving deleted keys

This is a notable risk when using Redis for security-sensitive data or business state.

Suppose a snapshot stores:

```text
session:token-42 = ACTIVE
```

Later the application invalidates the session:

```redis
DEL session:token-42
```

Redis returns success and subsequent `GET` calls on the live instance return `nil`. However, if no new snapshot has occurred and Redis crashes:

```text
Restore from old RDB
    |
    v
session:token-42 = ACTIVE
```

The key can **come back**.

### 12.1. Why is this not just a cache bug?

If Redis is a cache over a database and authentication always checks session revocation against a durable source, a stale key may not cause a severe security breach if validation layers are properly designed.

However, if Redis is the sole source determining whether a token remains valid, losing a `DEL` command can resurrect a revoked session after a restart.

For logouts, permissions, resource locks, balances, or consequential entitlements, choose an appropriate storage and consistency strategy. RDB-only with spaced snapshots is not sufficient on its own.

### 12.2. Does TTL completely solve this problem?

RDB stores key expiration deadlines per Redis mechanics. On restore, Redis evaluates deadlines against current time; keys past their deadline can be discarded on load or access via expiration.

Yet a key `DEL`eted after a snapshot **may still have a future deadline** in the older RDB file, so restoring can still bring it back until that deadline expires.

TTL limits lifetime, **it does not guarantee the latest deletion was snapshotted**.

## 13. RDB and TTL on restore

Do not treat a Redis snapshot as "freezing TTL time" so that keys resume living with their full remaining TTL from the restore moment.

Example:

```text
10:00  SET otp:123 value EX 300
10:01  Snapshot captures valid OTP
10:15  Redis restarts from 10:01 RDB
```

By 10:15, the 5-minute deadline from 10:00 has passed. The OTP key should not be granted another 5 minutes just because Redis restarted. Redis stores expiration metadata as deadlines, so keys already expired by current wall-clock time can be skipped/evicted during loading or when checked.

Keep in mind:

- Restoring a snapshot does not reset all TTLs to their initial values.
- Keys past their deadline may not be present after restore.
- If the application changed a TTL after the snapshot, that change may be lost.
- System clock skew can affect expiration behavior.
- A `PERSIST` issued after the snapshot can be lost, bringing the old deadline back.
- A key `DEL`eted after the snapshot can return if the prior snapshot contained it and its deadline has not yet passed.

### 13.1. How does the system clock affect data?

Redis expiration relies on timestamps. Severe clock skew or abnormal clock settings when moving snapshots between hosts can make data expire earlier or later than expected.

Keep operational clocks synchronized, especially when backing up/restoring across environments or using deadlines for tokens, sessions, or leases.

### 13.2. Spring Data Redis @TimeToLive

A Redis Repository can use `@TimeToLive` or `@RedisHash(timeToLive = ...)` to attach a TTL to an entity. RDB stores the key data and expiry metadata just like any other Redis keys.

However, `@TimeToLive` **does not increase snapshot frequency** and does not guarantee `repository.save(...)` has been durably written to disk. It only controls TTL within Spring Data Redis Repository capabilities.

## 14. RDB and Spring Data Redis: what a successful SET means

Example simple service:

```java
package com.example.session;

import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionCache {

    private final StringRedisTemplate redis;

    public SessionCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String sessionId, String userId) {
        redis.opsForValue().set(
            "session:" + sessionId,
            userId,
            Duration.ofMinutes(30)
        );
    }

    public String get(String sessionId) {
        return redis.opsForValue().get(
            "session:" + sessionId
        );
    }
}
```

When `save` returns normally, the application knows the Redis API call completed without error on that call path. This **does not prove**:

- Redis just finished a new RDB.
- The RDB currently contains this key.
- The file was backed up independently.
- Another replica definitely received the command.
- A related database transaction committed.
- The data cannot be lost in a crash or failover.

`StringRedisTemplate` is only a client interacting with Redis. Durability depends on Redis configuration and persistence infrastructure.

### 14.1. Reactive Redis has the same limits

Example:

```java
public Mono<Boolean> save(String key, String value) {
    return reactiveStringRedisTemplate
        .opsForValue()
        .set(key, value, Duration.ofMinutes(5));
}
```

When the `Mono` emits success, the Redis command has completed per the client contract. Yet a successful `Mono` **is not proof that a new RDB snapshot contains that write**.

Reactive vs. blocking is an I/O model decision, **not a durability guarantee level**.

### 14.2. `@Cacheable` does not make a cache more durable

Example:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto findProduct(String productId) {
    return repository.findProduct(productId);
}
```

Spring Cache can use `RedisCacheManager`. If Redis crashes and recovers from an older snapshot, the cache may lose newer entries or resurrect old ones. This is usually acceptable because the cache is rebuilt from the source of truth.

However, if the application **writes exclusive business data into the cache** with no other durable store, using cache annotations with RDB-only creates hard-to-control data loss risks.

### 14.3. RDB and serializers are two separate concerns

`RedisTemplate` can write Java Strings, JSON, or binary objects. RDB stores Redis data in Redis internal structures plus needed metadata; it does not understand your application's Java classes.

If you change serializers between before and after a restore:

```text
Before crash: Spring writes JSON using serializer A
After restore: Spring reads using serializer B
```

the application may fail to decode values even though RDB restored the Redis data intact.

Therefore, **successfully restarting the Redis process** does not guarantee **the application can read the business data**. Verify serializers, schemas, and Spring Data Redis application versions too.

## 15. Choosing durability by data type

Not every Redis key needs the same level of protection.

| Data type | If post-snapshot writes are lost | Typical tolerance |
|---|---|---|
| Cache of PostgreSQL data | Cache miss, must reload | Often acceptable if source of truth is intact |
| Cache of expensive API results | Higher latency/origin load after restart | Depends on rebuild cost |
| Ephemeral sessions | Users may have to log in again | Depends on product and security requirements |
| Short-lived OTPs | Newly issued OTP may be lost; user requests another | Must enforce sound verification policies |
| Rate limit counters | Counters may roll back after restore | Risk of abuse if sole defense layer |
| Inventory reservations | Reservations may be lost or resurrected | Usually needs a durable transactional store |
| Payment ledger | Lost or reverted balances/transactions | RDB-only is generally unsuitable as sole source |
| Redis Stream queues | New entries or ACK states may roll back | Must evaluate durability/replication/idempotency |
| Feature flags | New flags may be lost, old flags return | Depends on operational workflow |
| Distributed locks | Locks may vanish or reappear after restore | Do not rely on RDB as proof of lock safety |
| Token revocations | Revocations may be lost | Security risk; requires additional safeguards |

This table describes design risks and does not replace real SLA and security requirement analysis.

### 15.1. When Redis is only a cache

When Redis can lose its entire dataset and the application still behaves correctly by reloading from the source, RDB may be chosen to:

- Speed up warmup after restarts.
- Reduce the wave of cache misses after an outage.
- Reduce database load during recovery.
- Avoid logging every mutation for a rebuildable cache.

Even then, plan for **cache stampedes** for keys missing from the snapshot, especially after a full cluster restart.

### 15.2. When Redis is the source of truth

When data exists only in Redis, evaluate:

- Maximum acceptable data loss.
- Whether writes must be confirmed on storage before returning success.
- Extent of replication/failover support.
- Off-host snapshot backups.
- Whether AOF or another persistence mode is needed.
- Whether recovering from an old snapshot can violate business invariants.
- Impact of missing, rolled-back, and resurrected keys.
- Audit, legal, accounting, and security requirements.

Never assume "RDB is enabled" means Redis qualifies as a system of record for every business workload.

## 16. RDB and AOF: two different persistence approaches

Redis also provides **AOF (Append Only File)** to log data-mutating operations under Redis persistence mechanics.

Conceptually:

```text
RDB:
    t0 snapshot  -> [full image of state at t0]
    t1 writes    -> not in t0 RDB
    t2 crash     -> restore state t0

AOF:
    SET a 1      -> appended per AOF mechanics
    INCR b       -> appended
    DEL c        -> appended
    ...
    crash        -> replay recoverable AOF data
```

### 16.1. Comparing RDB and AOF

| Criterion | RDB | AOF |
|---|---|---|
| Data written | State snapshot at a logical point | Log/representation of mutations for replay |
| Trigger | `save` rules, `BGSAVE`, admin action | Driven by write operations and AOF config |
| Typical expected RPO | Can lose changes after last snapshot | Can narrow loss window depending on `appendfsync` |
| Size/overhead | Snapshots are often compact for many workloads | Has append and rewrite overhead |
| Recovery | Load snapshot image | Load/replay AOF per structure and version |
| Performance impact | Fork/COW and I/O during snapshots | Continuous I/O, fsync, and rewrite |
| Key settings | `save`, `dbfilename`, `dir` | `appendonly`, `appendfsync`, rewrite |
| Meaning of a successful write | Does not mean snapshot includes write | Depends on flush/fsync policy and storage |
| Typical use cases | Backups, fast snapshot restarts, caches | When limiting the data-loss window matters |

This table is conceptual. Redis can use both RDB and AOF; exact writing/restoring behavior depends on Redis version.

### 16.2. appendfsync always, everysec, and no

Example configuration:

```conf
appendonly yes
appendfsync everysec
```

Key AOF options:

- `always`: attempts to sync data to storage much more frequently, at higher latency/throughput cost.
- `everysec`: commonly used to balance performance and durability; can lose roughly one second of data in some failure scenarios, **not a hard cap of strictly one second in all cases**.
- `no`: relies more on OS flush schedules, potentially enlarging the data-loss window.

Do not turn the common saying "everysec loses at most about 1 second" into a legal/accounting SLA without testing hardware, OS, Redis version, and failover/restore procedures.

### 16.3. Enabling both RDB and AOF

Redis can have both RDB snapshots and AOF enabled. When both are active, Redis normally prioritizes the valid AOF recovery source because it may reflect newer data than RDB, though exact behavior depends on version and persistence state.

Redis 7 uses a multi-part AOF model with rewrite/manifest configurations; do not assume a single flat `appendonly.aof` file in every deployment.

Thus, to evaluate the real data-loss window, ask:

```text
Is RDB enabled?
Is AOF enabled?
Which appendfsync policy is set?
Are replicas/failover configured?
What storage holds the persistence files?
Which source did startup actually load?
```

**Do not infer from the mere presence of `dump.rdb` that the system is restoring from RDB.**

## 17. RDB and replication/failover

**Persistence** and **replication** address different risks:

- Persistence attempts to preserve data across instance restarts.
- Replication copies state/operations from a primary to replicas for multiple copies.
- Sentinel/Redis Cluster can automatically promote a replica to replace a failed primary.
- Backups maintain independent copies for recovery after data errors or total system loss.

Redis replication is normally **asynchronous**. A primary can return write success to the client before every replica receives that command.

Example:

```text
t0: Primary processes SET counter 100.
t1: Primary returns OK to Spring client.
t2: Primary dies before replica receives that write.
t3: Replica lacking the write is promoted.

Result: the last value observed by the client may be missing on the new primary.
```

This can happen regardless of how RDB/AOF is configured. You must analyze the topology and guarantees of the whole system.

### 17.1. WAIT is not disk fsync by default

Redis offers `WAIT` to wait for a specified number of replicas to acknowledge receipt of prior writes per replication mechanics.

However, `WAIT` **does not turn Redis into a consensus system with exactly-once commits**, nor does it prove writes are durably fsynced on every replica.

Some Redis versions offer `WAITAOF` for conditional AOF persistence waiting; check version, configuration, and actual guarantees. Never treat an auxiliary command like `WAIT` as an absolute promise that data cannot be lost.

### 17.2. Can a replica have a newer RDB than the old primary?

In replicated setups, each node has its own persistence process and syncs data via replication state. During failover or restart, the recovery path may involve a replica holding state newer than an old snapshot on a primary.

Still, this is not a guarantee that all client-acknowledged writes exist. Partitions, async replication lag, and failover timing can still lose writes that appeared to succeed.

### 17.3. Redis Cluster has multiple sets of RDB files

Redis Cluster splits keys across primaries responsible for different hash slots. One node's RDB backup **is not a snapshot of the entire cluster**.

If the application updates keys across different slots, each node may snapshot at a different time:

```text
Primary A: RDB at T1
Primary B: RDB at T2
Primary C: RDB at T3
```

Restoring from those three snapshots can yield a combined system representing **multiple logical points in time**. Redis Cluster does not automatically create a globally transactionally consistent snapshot simply by enabling RDB per node.

If the business requires consistent point-in-time recovery across shards, design a dedicated backup/restore and source-of-truth architecture.

## 18. Are Redis Streams and pending state affected when restoring RDB?

Yes. Redis Streams are Redis data; Stream entries, consumer groups, and pending state are represented in restored data per Redis version capabilities.

Suppose:

```text
10:00 Snapshot has Stream entry E1, group received E1 (pending).
10:01 Worker processes E1 successfully and calls XACK.
10:02 Redis crashes.
10:03 Restore 10:00 snapshot.
```

After restore, state may show E1 **still pending** per the old snapshot, even though external business processing already finished before the crash.

A recovery worker may claim and reprocess E1. This is a form of ACK-state rollback caused by an older RDB.

Reverse scenario:

```text
10:00 Snapshot has Stream up to E1.
10:01 Producer runs XADD E2.
10:02 Worker processes E2 and writes to database.
10:03 Redis crashes.
10:04 Restore 10:00 snapshot.
```

E2 may be missing from the Redis Stream even though the database already has E2's result. Depending on the system, you need a durable source or outbox/reconciliation to resolve this drift.

### 18.1. XACK does not mean the data has been snapshotted

`XACK` clears pending status for the group in live Redis. If Redis only has an older RDB, recovery can revert the PEL back to before the ACK.

Therefore, idempotent consumers are essential not only because crashes occur **between business commit and ACK**, but also because of **persistence rollback** when Redis recovers from an earlier point.

### 18.2. RDB-only does not replace message broker durability

If Redis Streams serve as a critical task delivery system, design for:

- Appropriate persistence, potentially combined with AOF.
- Replication and failover with clear understanding of async semantics.
- Transactional outbox at the business data source when needed.
- Idempotency keys.
- Sufficiently long retention.
- Pending recovery.
- DLQs and reconciliation.

Never assume "having a Stream ID and XACK" guarantees every acknowledged message survives total RAM loss if persistence is inadequate.

## 19. RDB and distributed locks

A Redis lock typically uses:

```redis
SET lock:resource:42 unique-token NX PX 30000
```

Redis returns success when the lock is acquired on the live instance, but if Redis loses RAM and restores from an older snapshot, lock state can:

- **Disappear:** a lock created after the snapshot is gone.
- **Reappear:** a lock released after the snapshot still existed in the old RDB, if its deadline has not passed.
- **Have an outdated deadline:** because TTL metadata was restored from the earlier point.

In some cases, losing lock state can allow two workers to believe they both hold exclusive rights to a resource.

If a lock protects an external resource and correctness depends on exclusivity, consider leases, token ownership, fencing/versioning, and checks at the resource-owning system rather than relying solely on Redis RDB.

A Redis TTL lock can be useful for best-effort coordination, but **RDB does not provide linearizability guarantees across failovers**.

## 20. RDB backup is not the same as simply enabling RDB persistence

A Redis instance may write `dump.rdb` on the same disk used to run the service. That helps across some restarts, yet fails to protect against:

- Disk/host loss.
- Ransomware.
- Accidental directory deletion by an operator.
- Filesystem corruption.
- Overwriting snapshots with logically corrupted data from application bugs.
- Container replacement without a persistent volume.
- Disaster recovery requiring a restore in another region.

A real backup policy needs copies **independent** of the primary Redis.

### 20.1. Creating snapshots for backup

A controlled approach:

1. Request `BGSAVE` if environment and policy permit.
2. Monitor until `BGSAVE` succeeds.
3. Identify the stable, version-matched RDB file.
4. Copy the file to a backup staging area.
5. Record metadata: request time, start time, completion time, node, Redis version, checksum.
6. Store the copy off-host/off-volume or in a suitable backup service.
7. Verify integrity.
8. Periodically restore onto a test Redis instance and run application checks.

Do not simply run `cp dump.rdb backup.rdb` at a random moment without knowing whether Redis is swapping the file and which version the backup tool sees.

In some setups, `redis-cli --rdb <path>` can fetch an RDB via replication sync. When using it, still account for generated load, permissions, topology, and capture point; never rely solely on CLI completion without restore testing.

### 20.2. Example file check using Redis tools

On a copy of the backup file, you can run:

```bash
redis-check-rdb /secure/backup/dump.rdb
```

This tool is useful for validating format and catching some RDB errors for the corresponding version. However, **a file passing format checks does not guarantee business data is correct or up to date**.

The stronger validation step is **restoring into an isolated environment** and checking representative keys and business metadata.

### 20.3. Backups also have a point in time

When creating a backup from RDB, metadata should record:

- Backed-up node/instance.
- Fork/capture timestamp if determinable.
- File completion timestamp.
- Copy and upload completion timestamps.
- Redis server version.
- Storage location/checksum.
- Accompanying RDB/AOF configuration.
- Cluster/shard name and slot ownership at backup time if applicable.

Do not name a file `backup-10h00.rdb` and assume it contains every write before exactly 10:00:00 if the fork happened earlier and copying occurred afterward.

## 21. Restoring from RDB: process and limitations

A restore test workflow might look like:

1. Stop a test Redis instance or start a fresh Redis instance isolated from production.
2. Place the valid RDB file into the test instance's persistence directory.
3. Configure `dir`, `dbfilename`, and AOF settings as needed so startup reads the intended file.
4. Start Redis.
5. Inspect logs and `INFO persistence`.
6. Check key counts, data types, TTLs, and sample records.
7. Run integration checks via Spring Data Redis to verify serializers and schemas.
8. Measure total time from restore start until the application is ready to serve.
9. Note which new keys or post-snapshot deletions were lost per the test scenario.
10. Never use test restore outputs to overwrite production without an approved procedure.

Example command to start an isolated Redis instance:

```bash
redis-server \
  --port 6380 \
  --dir /path/to/isolated-restore \
  --dbfilename dump.rdb \
  --appendonly no
```

The file `/path/to/isolated-restore/dump.rdb` must be in place before starting. `--appendonly no` in the example focuses the test environment on RDB; never blindly apply it to a production deployment relying on AOF.

### 21.1. Verifying actual results

In the test environment:

```redis
DBSIZE
GET cart:101:state
TTL session:token-42
TYPE orders:events
XLEN orders:events
```

Commands are valid only for matching keys/types. `DBSIZE` is the key count of the current logical DB, not proof that all business transactions were recovered.

Check:

- Important objects remain valid.
- No unexpected stale keys exist.
- TTLs match expected deadlines.
- Stream/group offsets match snapshot expectations.
- Spring Data Redis can deserialize the data.
- Secondary indexes/metadata remain consistent with primary keys.
- Message-driven jobs do not duplicate or drop work.

### 21.2. Restoring is not a safe business rollback

Using an old RDB to roll back production can revert operations already recorded by external systems.

Example:

```text
10:00  RDB has order status=PENDING
10:03  Payment database records order=PAID
10:04  Redis status=PAID
10:05  Redis crashes and restores 10:00 RDB
```

Redis may report `PENDING`, while the payment database records `PAID`. The application must reconcile against authoritative sources rather than treating a Redis snapshot as the final word on payment state.

For caches, it is often safer to **flush stale cache and rebuild from the database** instead of restoring potentially stale cache entries.

## 22. Impact on Redis Repositories, indexes, and TTLs

Spring Data Redis Repositories can store:

```text
Entity Hash
Secondary index Sets
Expiration metadata
Shadow/phantom copies for expiry events
```

If RDB is restored to an earlier time, not only the entity Hash but also index state and expiration metadata revert to that snapshot's state.

Possible effects:

- Entities updated after the snapshot revert to old values.
- Entities created after the snapshot vanish.
- Entities deleted after the snapshot reappear.
- Index entries updated after the snapshot disappear.
- TTLs reset after the snapshot revert to old deadlines.
- Expiration listeners do not replay all events that occurred while Redis was offline.

**Do not use keyspace expiration notifications as a durable event delivery system to reconcile post-restore drift.** Pub/Sub notifications lack default ACK/replay logs.

If indexes and entities are business-critical, you need a data source capable of rebuilding indexes or a post-incident reconciliation process.

### 22.1. Shadow copies do not save un-snapshotted writes

Shadow copies in Redis Repositories can carry entity payloads when the primary key expires, depending on configuration. However, if both the primary key and shadow copy were created after the last snapshot, restoring an old RDB will lack both.

Shadow copies solve an **expiration event payload** problem, not a WAL mechanism for shrinking RPO.

## 23. Calculating the data-loss window across three scenarios

### Scenario A — Pure cache, RDB triggered on changes when eligible

```text
09:00  Snapshot contains 50,000 product cache entries.
09:15  Cache receives 5,000 new keys.
09:20  Redis crashes.
09:22  Redis restores 09:00 snapshot.
```

New keys can be lost, causing cache misses. If source products remain in the database/API, the application can rebuild the cache. The primary risks are origin load spikes, latency, and database overload.

Mitigations:

- Rate limits/bulkheads for cache loaders.
- Prewarming hot keys.
- Cache stampede protection.
- Monitoring miss rates after restart.
- Never making cache data the sole source of business updates.

### Scenario B — Session store, lost revocation command

```text
12:00  Snapshot: session:s-7 = ACTIVE, long remaining TTL.
12:04  User logs out -> DEL session:s-7 succeeds.
12:06  Redis crashes.
12:07  Restore 12:00 snapshot.
```

The session can revert to `ACTIVE` if its deadline has not yet elapsed. This is a bigger risk than "users need to log in again".

Mitigations:

- Base authentication on durable state/epochs/versions where appropriate.
- Treat Redis session state as a cache where possible.
- Do not rely solely on RDB-only Redis for strict-security token revocation.
- Test authentication system behavior after rollback.

### Scenario C — Counters or queues

```text
13:00  Snapshot: counter:orders = 120.
13:01  50 INCR requests succeed, live counter = 170.
13:02  Redis crashes.
13:03  Restore 13:00 snapshot -> counter = 120.
```

If the counter issues strictly monotonic unique business IDs, rolling back can cause severe collisions. If it is only a recomputable metric, the loss may be tolerable.

Mitigations:

- Do not use RDB-only Redis as the sole generator for unique/monotonic IDs across crashes.
- Use an appropriately guaranteed ID/sequence source.
- If data is recomputable, maintain a recompute workflow.
- For queues, consider ACKs, idempotency, stronger persistence, and source records.

## 24. Limits of forcing a snapshot immediately after every write

A common misconception:

```java
redis.opsForValue().set("order:101", "PAID");
// After every request, call Redis BGSAVE to be "safe".
```

This approach has severe flaws:

- `BGSAVE` has high fork/I/O overhead.
- Concurrent requests cannot spawn unlimited useful snapshots.
- `BGSAVE` returns when started, not after waiting for file completion.
- Commands arriving after fork are omitted from the in-progress snapshot.
- Snapshots can fail due to disk/memory limits.
- Redis latency and throughput degrade dramatically.
- It does not provide atomicity with another database.

If a write must be durably persisted before returning success, choose **an appropriate persistence model and transactional storage**. Periodic RDB snapshots are not designed for per-request durable commits.

### 24.1. Define requirements before choosing Redis

Ask:

```text
Can the data be rebuilt from another source?
How many seconds/minutes of writes can be lost?
Can a DELeted key be allowed to reappear?
Does every mutation need an audit trail?
Are exactly-once side effects required?
Is Redis a cache or the primary database?
During failover, is reading an older version acceptable?
What is the RTO?
```

If the answers show transactional state cannot be lost or resurrected, revisit the entire data architecture rather than simply shortening `save` intervals.

## 25. Optimizing BGSAVE for operations

Key operational areas to monitor:

### 25.1. Dataset size and disk throughput

The larger the dataset, the longer a snapshot takes to write. Low-throughput or high-latency disks prolong `BGSAVE`, extending COW lifetime and impacting other I/O.

Measure:

```text
RDB file size
BGSAVE duration
Disk throughput / latency
Remaining disk space
CoW memory size
Fork latency
Redis command latency
```

### 25.2. Memory headroom

If Redis runs near RAM limits, a write-heavy `BGSAVE` can trigger memory pressure. Plan headroom for fork and COW; `maxmemory` does not account for all OS memory consumed by the process.

In containers, memory limits and OS OOM kills of child or parent processes can disrupt snapshotting.

### 25.3. Do not arbitrarily use Redis RDB as an online export tool

Creating large snapshots adds load to Redis. If frequent backups are needed while a production primary handles heavy writes, consider taking backups from an appropriate replica, while accounting for replication lag and replica snapshot state.

Backing up from a replica can offload the primary in some setups, yet the replica may **lag behind** the primary; the resulting backup can be older than writes already acknowledged to clients.

### 25.4. Optimization does not mean raising frequency endlessly

More frequent snapshots narrow the window of un-snapshotted data, but increase:

- Fork frequency.
- Disk I/O.
- COW memory.
- CPU usage.
- Overlapping or failed background saves.
- Impact on Redis command latency.

Balance RPO, RTO, throughput, dataset size, and operational cost. Very write-heavy workloads may fit AOF or another persistence strategy better than forcing frequent RDB saves.

## 26. Redis Cloud/managed services can alter backup behavior

When using managed Redis, the provider may:

- Enforce proprietary snapshot/backup schedules.
- Restrict `CONFIG SET`, `BGSAVE`, or `SAVE`.
- Vary persistence defaults across service tiers or topologies.
- Offer custom point-in-time restore or backup schedulers.
- Use managed storage and replication layers.
- Impose distinct maintenance/failover behaviors.

Do not assume `dump.rdb` sits on a filesystem accessible to your application, or that `redis-cli --rdb` is always permitted.

When evaluating durability, clarify:

```text
Who controls backup frequency?
Are snapshots taken from primary or replica?
Which RDB/AOF settings are active in this service tier?
To which points in time can we restore?
How does the provider's SLA distinguish failover from disaster recovery?
Is application data verified after restore?
```

A dashboard showing "backup completed" does not prove business RPO without a tested restore procedure.

## 27. Monitoring and alerting RDB in production

Monitoring should answer at least four groups of questions.

**(1) Are snapshots running on schedule and succeeding?**

- `rdb_bgsave_in_progress`.
- `rdb_last_bgsave_status`.
- `rdb_last_save_time` and logs.
- Consecutive failure count.

**(2) Are snapshots causing resource pressure?**

- `rdb_last_bgsave_time_sec`.
- `rdb_current_bgsave_time_sec`.
- `rdb_last_cow_size`.
- CPU, RSS, memory limits, disk I/O.

**(3) Is the unsaved data window growing past targets?**

- Time elapsed since the last observed snapshot point.
- Changes accumulated since the last save.
- `BGSAVE` duration.
- Fork/disk/permission errors.
- Complementary AOF/replication backups.

**(4) Are backups/restores actually usable?**

- Timestamp of the last off-host backup.
- Checksum status.
- Most recent restore test.
- Measured RTO.
- Data verification with Spring Data Redis post-restore.

### 27.1. Example alert thresholds per internal policy

Suppose operations **sets a target** that RDB backups for a critical cache be no older than 15 minutes:

```text
WARNING:
    No completed snapshot newer than 15 minutes.

CRITICAL:
    Multiple BGSAVE failures or disk nearly full.

CRITICAL:
    No recent off-host backup.

INVESTIGATE:
    Abnormal spike in BGSAVE duration, COW, or fork latency.
```

Thresholds are illustrative. If a snapshot runs for 4 minutes, a file finishing now may still reflect state from when it started, so snapshot-age alerts must account for that lag.

### 27.2. Do not rely solely on LASTSAVE

A dashboard displaying only:

```text
Time since last save = now - LASTSAVE
```

helps show when Redis last reported a successful save. Yet it can **underestimate** the logical data age of the snapshot if `BGSAVE` takes a long time.

Combine duration/logs or backup process metadata when evaluating actual RPO.

## 28. Planning backups by environment

An example plan:

| Environment / Data type | Characteristics | RDB direction |
|---|---|---|
| Local dev | Easily reproducible data | Simple snapshots or intentionally disabled persistence |
| Integration testing | Needs repeatable state for tests | Seeded snapshots and restore verification |
| Production cache | Backed by another durable source | RDB supports warm restarts if benefits outweigh cost |
| Redis sessions | UX and security risks | Evaluate persistence, auth source, reset policy |
| Critical queues/Streams | Cannot lose events and ACKs | RDB-only may be insufficient; add suitable persistence/backup/recovery |
| Financial/ledger state | Cannot roll back acknowledged entries | Usually needs a durable transactional source beyond RDB-only |

This table is a guide; actual SLAs depend on business requirements and system risk.

### 28.1. Multi-version snapshot retention policy

Keeping a single snapshot may suffice for a recent restart, yet fails if data was accidentally deleted and a newer snapshot overwrote the old state.

For backup requirements:

- Retain multiple snapshot generations.
- Store off-host or in another failure domain.
- Attach timestamps and metadata.
- Verify checksums/integrity.
- Restrict access permissions.
- Enforce sensible retention periods.
- Practice restoring both older and newer versions.
- Distinguish operational recovery backups from archival backups.

### 28.2. Securing RDB data

RDB files can contain sensitive data from Redis:

```text
Tokens, sessions, user information,
counters, cached API responses, feature flags...
```

Even when Redis key TTLs are short, an older snapshot can hold data that was valid at capture time. Apply encryption at rest, restrict read permissions, protect storage, and enforce backup disposal policies.

Never post production RDB files containing sensitive data in chat channels, logs, or public debugging threads. Use synthetic data or controlled sanitized copies when sharing for analysis.

## 29. Lab 1 — Observing BGSAVE and LASTSAVE

**Objective:** distinguish requesting a snapshot from snapshot completion.

On a test Redis instance:

```redis
CONFIG GET save
INFO persistence
LASTSAVE
```

Create some sample data:

```redis
SET lab:profile:1 Alice
SET lab:profile:2 Bob
HSET lab:cart:1 total 120000 status OPEN
```

If the environment permits:

```redis
BGSAVE
```

Then observe:

```redis
INFO persistence
LASTSAVE
```

Record:

- Time `BGSAVE` was requested.
- Value of `rdb_bgsave_in_progress`.
- Time `BGSAVE` finished.
- `rdb_last_bgsave_status`.
- `rdb_last_save_time`.
- `rdb_last_bgsave_time_sec`.

Explain why `BGSAVE` returning success for starting differs from confirming the snapshot file has finished saving.

Never run persistence-altering operations on production Redis without authorization.

## 30. Lab 2 — Losing keys created after a snapshot

Use a test Redis with an RDB volume, and disable AOF for this lab to observe true RDB-only behavior:

```conf
appendonly no
save ""
dbfilename dump.rdb
dir /path/to/lab-data
```

These values are for an isolated lab only. With `save ""`, snapshots must be triggered manually as needed.

Steps:

1. Write `SET lab:before 1`.
2. Run `BGSAVE`, wait for success.
3. Write `SET lab:after 2`.
4. Stop Redis using a controlled test scenario **that does not create a new snapshot**.
5. Restart from RDB.
6. Check `lab:before` and `lab:after`.

Predict that `lab:after` may be missing because it was created after the snapshot point. This scenario is safe only in a lab without important data.

**Note:** a graceful shutdown may save data depending on configuration. When testing crash data-loss windows, clearly distinguish shutdowns that save from failures with no save opportunity. Never use `SHUTDOWN SAVE` to simulate power loss.

## 31. Lab 3 — Delete rollback and token revocation

In a test Redis:

```redis
SET lab:token:42 ACTIVE EX 3600
BGSAVE
```

After `BGSAVE` completes:

```redis
DEL lab:token:42
GET lab:token:42
```

Live, `GET` returns nil. Then simulate restoring **from the pre-DEL RDB** in an isolated environment.

Check whether the key reappears, as long as its deadline remains valid.

Answer:

- Why can restoring an old snapshot undo a `DEL` command?
- If the token were a real authentication credential, what is the security risk?
- What durable sources or version/revocation checks must be added?
- Why does TTL not completely solve the issue?

## 32. Lab 4 — BGSAVE while data is changing

In the lab:

1. Prepare a dataset large enough to observe a `BGSAVE` taking non-trivial duration.
2. Before calling `BGSAVE`, write `lab:marker = BEFORE`.
3. Call `BGSAVE`.
4. While `BGSAVE` is running, write `lab:marker = AFTER`.
5. After `BGSAVE` finishes, do not trigger a new snapshot.
6. Copy/restore that RDB onto another test Redis instance.
7. Read `lab:marker` on the restored instance.

Explain why the RDB can contain `BEFORE` even though the `AFTER` write was acknowledged by live Redis **before the `LASTSAVE` timestamp of that `BGSAVE`**.

On a tiny dataset, `BGSAVE` may finish before you write `AFTER`, failing to reproduce the timing gap. That is an observation timing artifact, not a counterexample to the snapshot mechanism.

## 33. Lab 5 — Calculating the data-loss window

Given the hypothetical timeline:

```text
14:00:00 BGSAVE #1 starts.
14:00:15 BGSAVE #1 finishes.
14:00:20 SET A = 1.
14:01:00 DEL B.
14:02:00 BGSAVE #2 starts.
14:02:10 SET C = 3.
14:02:30 Redis crashes, BGSAVE #2 has not finished.
```

Answer:

1. Which snapshot is likely the latest completed one?
2. Around what time does that snapshot's logical data point sit?
3. Which changes among `SET A`, `DEL B`, and `SET C` could be lost?
4. Why can the loss window not be computed simply as `14:02:30 - 14:00:15` without knowing the fork timestamp?
5. If `BGSAVE #2` finished at `14:02:25`, would `SET C` at 14:02:10 necessarily be in RDB #2?

The last question is crucial: **no**, because `BGSAVE #2` represents the state at start time around 14:02:00.

## 34. Lab 6 — Comparing RDB-only and AOF

Use two test Redis instances:

```text
Instance A: RDB enabled, AOF disabled.
Instance B: AOF enabled per selected policy.
```

Apply the same set of writes after the last snapshot point. In a controlled test environment, recover each instance after a pre-designed failure scenario.

Record:

- Which data survived?
- Which data was lost?
- Restart/restore duration.
- Disk footprint.
- Write latency.
- CPU/I/O cost.
- Reliability of pre-incident writes.

Do not generalize from a single benchmark that RDB or AOF is always faster for every workload; dataset size, fsync config, disk, and Redis version greatly influence results.

## 35. Lab 7 — Spring Data Redis and the gap between command ACK and persistence

Create a service:

```java
@Service
public class CounterService {

    private final StringRedisTemplate redis;

    public CounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment() {
        return redis.opsForValue().increment(
            "lab:counter"
        );
    }

    public String read() {
        return redis.opsForValue().get(
            "lab:counter"
        );
    }
}
```

Steps:

1. Create a snapshot containing `lab:counter = 10`.
2. Call `increment` multiple times until the live value reaches `20`.
3. Observe that Java received confirmations for every increment.
4. Restore a test Redis from the older RDB.
5. Compare `lab:counter` before and after restore.

Answer:

- Did the Java method lie when returning success on those `increment` calls?
- Why did the Redis commands succeed yet post-restore state rolled back?
- If the counter generates strictly monotonic business IDs, how should the source of truth be designed?

## 36. Lab 8 — Designing backup/restore

You operate Redis storing product cache and temporary cart info.

Build a runbook:

1. Define RPO/RTO policies for each key category.
2. Select snapshot mechanics and off-host backup methods.
3. Verify `BGSAVE` completion.
4. Copy files and metadata.
5. Verify checksums/format.
6. Restore into a test Redis.
7. Confirm Spring Data Redis deserializes sample keys.
8. Check TTLs and previously deleted keys.
9. Measure time until service readiness.
10. Define application behavior when restored cache data is stale.

A good runbook also covers failed backups, failed restores, and operational rollback procedures.

## 37. Lab 9 — Redis Cluster and non-simultaneous backups

Suppose a Redis Cluster has two primaries:

```text
Primary A: keys order:{o-101}:...
Primary B: keys inventory:{sku-42}:...
```

A's RDB reflects T1, B's reflects T2. Between T1 and T2, checkout updates inventory and order in two separate steps.

Do the following:

- Describe inconsistent states that can arise when restoring two snapshots from different points in time.
- Explain why same-slot hash tags solve atomicity within **one aggregate** but do not make the entire cluster a single transaction.
- Propose using database transactions/outbox or reconciliation when checkout is business-critical.
- Contrast per-shard RDB restore with failing over to a replica holding newer state.

## 38. Lab 10 — Observing BGSAVE errors

In a controlled lab environment containing no important data, simulate an inability to write snapshots (for example, a read-only test filesystem or a controlled low-disk test setup).

Observe:

```redis
INFO persistence
CONFIG GET stop-writes-on-bgsave-error
```

Note: adjusting permissions or disk limits must be done safely; never affect production Redis or real data.

Questions:

1. What does `rdb_last_bgsave_status` report?
2. Does `LASTSAVE` continue advancing?
3. Can the application still write data?
4. How does `stop-writes-on-bgsave-error` impact availability?
5. If the failure persists, why can RPO greatly exceed intervals in `save` rules?
6. At what thresholds should monitoring fire alerts?

## 39. Common pitfalls and misconceptions

### 39.1. "Enabling save 60 1 means at most one minute of loss"

There is no hard guarantee. Save conditions depend on snapshot startup/completion, resource availability, and persistence errors. Logical data reflects fork time, not necessarily `LASTSAVE` time.

### 39.2. "BGSAVE returning OK means all current data is on disk"

Incorrect. The command usually confirms the background save started; you must monitor completion. Writes after fork are not part of that snapshot.

### 39.3. "LASTSAVE is when all prior writes became durable"

Incorrect. With `BGSAVE`, the logical state point precedes completion time, sometimes by seconds or minutes for large snapshots.

### 39.4. "Data loss only means losing new keys"

Incorrect. Updates can revert, deletes can be undone, counters can drop, and TTLs can revert to older deadlines.

### 39.5. "Once DEL succeeds, the key can never return"

Incorrect if restoring a snapshot containing that key whose deadline has not passed. This is especially risky for revocation data.

### 39.6. "Redis has replicas, so writes cannot be lost"

Replication is typically asynchronous, and failover may promote a replica missing the latest writes. Never infer absolute durability from replicas.

### 39.7. "WAIT means fsync on every replica"

No. `WAIT` pertains to replication acknowledgment; it does not provide storage durability guarantees or turn Redis into a consensus system.

### 39.8. "Enabling AOF makes RDB pointless"

Not necessarily. RDB can still assist backups, startup, full syncs, or other operational tasks. When both are enabled, know which source recovery actually uses.

### 39.9. "Using ReactiveRedisTemplate makes writes safer"

Reactive APIs govern Java I/O execution; they do not alter Redis's snapshot/disk mechanisms.

### 39.10. "Spring Cache/Redis Repository writes another durable copy"

No. They may create Redis keys or secondary indexes per their mapping, but if stored on the same instance after the last snapshot, those can also be lost on crash.

### 39.11. "Keeping dump.rdb on a volume is enough for backup"

Persistent volumes help restarts, yet do not protect against volume loss, corruption, or accidental deletion. Independent backups and restore tests remain necessary.

### 39.12. "If an RDB file passes redis-check-rdb, the data is definitely up to date"

Format verification is not freshness or business correctness verification. A completely valid old snapshot can still miss recent writes.

### 39.13. "Restoring RDB automatically recovers lost Pub/Sub events"

No. Pub/Sub events lack replay logs like Streams. Restoring RDB does not recreate notifications emitted while subscribers were absent.

### 39.14. "RDB can take an atomic snapshot across an entire Redis Cluster"

Each primary manages its own slot range and persistence process; there is no automatic global simultaneous snapshot across nodes.

### 39.15. "Once snapshotted, we can delete the external data source"

If Redis was only a cache expecting rebuilds from the origin, deleting the source of truth completely changes the risk profile. You must re-evaluate Redis as primary storage with new durability requirements rather than assuming RDB suffices.

## 40. Design and operations checklist

Before choosing RDB-only, confirm:

- [ ] Does Redis hold a rebuildable cache or unique state?
- [ ] Is target RPO stated as **acceptable data loss**, not just `save` rules?
- [ ] Has RTO been measured via real restore drills?
- [ ] Are `BGSAVE` start time and completion time clearly distinguished?
- [ ] Are `INFO persistence` and `BGSAVE` errors monitored?
- [ ] Are disk space, RAM headroom, COW, and fork latency tracked?
- [ ] Do off-host/off-volume backups and multi-version retention exist?
- [ ] Are backups verified for integrity and periodically restore-tested?
- [ ] Are AOF, replication, and failover fully understood without conflating guarantees?
- [ ] When restoring an old snapshot, how does the app handle stale/rolled-back keys?
- [ ] Do token revocations, sessions, counters, and queues have dedicated consistency designs?
- [ ] Are Redis Repository serializers, schemas, and TTLs tested after restore?
- [ ] Are Redis Cluster backups evaluated per shard and for global consistency?
- [ ] Are runbooks ready for disk full, `BGSAVE` failure, timeouts, corruption, and data loss?
- [ ] Are idempotency/reconciliation mechanisms in place for non-repeatable side effects?
- [ ] Are crash experiments strictly isolated from production?

This checklist is an implementation guide; the ultimate goal is a **battle-tested recovery process**, not just a config line.

## 41. Self-assessment questions

1. At what points in time does RDB capture Redis state?
2. Why does `SET` returning OK not prove the key is in `dump.rdb`?
3. How does `BGSAVE` differ from `SAVE`?
4. Why does `BGSAVE` incur fork/COW overhead?
5. If Redis writes data while `BGSAVE` is running, must the snapshot contain those writes?
6. Why is `LASTSAVE` not necessarily the logical timestamp of the RDB data?
7. Does `save 300 10` mean Redis guarantees a snapshot strictly every 5 minutes?
8. What data can be lost when crashing between two snapshots?
9. How can a `DEL` command be undone after restore?
10. Why do keys with TTL not "revive" for their full original duration starting from restore time?
11. When is RDB-only suitable for caches?
12. Why might RDB-only be unsuitable as a payment ledger?
13. What do `rdb_last_bgsave_status` and `rdb_bgsave_in_progress` help observe?
14. If background saves fail repeatedly, how can RPO change?
15. How does `stop-writes-on-bgsave-error` affect availability?
16. How should `SAVE` be treated on latency-sensitive systems?
17. How do RPO and RTO differ?
18. How does AOF differ from RDB in writing and recovery?
19. Is `WAIT` proof of disk fsync?
20. Do replicas/failover eliminate all possibilities of write loss?
21. Why does a Redis Cluster require a backup strategy covering multiple primaries?
22. Does RDB guarantee a consumer group will never reprocess an event?
23. Why can a backup file with a valid checksum still contain stale state?
24. If a key was `DEL`eted after a snapshot and its deadline has not arrived, what can happen on restore?
25. What would you verify to prove an RDB backup truly restores cleanly with Spring Data Redis?

## 42. Key takeaways

- **RDB is a snapshot of Redis state at a logical point in time**, not a log of every write after that point.
- `BGSAVE` typically uses fork and copy-on-write to write snapshots in the background. The parent keeps serving commands, yet writes after fork **are not automatically included in the active snapshot**.
- **`LASTSAVE` time can reflect when `BGSAVE` completed**, while RDB data reflects when `BGSAVE` started. Do not use `now - LASTSAVE` as a hard upper bound on data loss.
- `save <seconds> <changes>` lines define **trigger conditions**, not a hard snapshot schedule or absolute RPO guarantee.
- Crashes can lose **new keys, updates, deletes, counter increments, Stream entries, ACK state, and TTL changes** after the snapshot. A successful `DEL` can be reverted when restoring an older snapshot.
- `SAVE` can block the server; `BGSAVE` is usually preferred at runtime, though it brings fork, I/O, COW RAM, and failure risks.
- Monitor `INFO persistence`, `LASTSAVE`, logs, disk, and COW. When `BGSAVE` fails, the unsaved data window can grow well beyond `save` thresholds.
- **RPO** measures tolerable data loss; **RTO** measures recovery time. Both must be measured via real restore exercises.
- **AOF, replication, failover, and independent backups** are distinct mechanisms from RDB; each mitigates a class of risk without automatically yielding exactly-once or cross-system transactions.
- With Spring Data Redis, success from `StringRedisTemplate`, `ReactiveRedisTemplate`, Spring Cache, or Repositories **does not mean a snapshot now holds the write**.
- Redis caches can tolerate data loss if rebuildable, whereas financial data, revocations, locks, queues, or critical counters need dedicated durability and idempotency designs.
- **A reliable backup is one that can be restored and verified**, not merely a `dump.rdb` file sitting on the same machine.
- Choose persistence configurations from **real business data-loss requirements**, not just numbers of seconds in `redis.conf`.

### Official references

- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis — Redis configuration](https://redis.io/docs/latest/operate/oss_and_stack/management/config/)
- [Redis — SAVE](https://redis.io/docs/latest/commands/save/)
- [Redis — BGSAVE](https://redis.io/docs/latest/commands/bgsave/)
- [Redis — LASTSAVE](https://redis.io/docs/latest/commands/lastsave/)
- [Redis — INFO](https://redis.io/docs/latest/commands/info/)
- [Redis — CONFIG GET](https://redis.io/docs/latest/commands/config-get/)
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis — PERSIST](https://redis.io/docs/latest/commands/persist/)
- [Redis — WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis — WAITAOF](https://redis.io/docs/latest/commands/waitaof/)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis — Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
