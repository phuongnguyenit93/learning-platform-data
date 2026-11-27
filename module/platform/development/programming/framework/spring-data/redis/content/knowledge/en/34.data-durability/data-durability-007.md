# Designing Backup, Restore, and Copy Verification in Spring Data Redis

Redis is well known for reading and writing data in memory, yet a real-world system may still need **data recovery capability** after server crashes, human errors, software bugs, availability-zone loss, or prolonged operational incidents. If Redis holds only rebuildable cache, wiping everything and repopulating may be sensible. If Redis stores sessions, queues, business state, or data persisted nowhere else, losing that data has completely different consequences.

In a Spring Data Redis application, using `RedisTemplate` or `ReactiveRedisTemplate` does not provide backups on its own. **Data durability is an end-to-end design spanning Redis persistence, external storage, restore planning, access control, integrity verification, and operational readiness.** A `dump.rdb` file sitting on disk is not enough to prove the system can recover.

This lesson covers choosing between RDB and AOF, scheduling backups, verifying backup artifacts, practicing restores across Standalone/Sentinel/Cluster, defining RPO/RTO, and validating data from Spring Data Redis. Commands that touch files, stop Redis, or alter configurations apply solely to **isolated test/restore environments or approved production runbooks**.

## 1. Distinguishing persistence, replication, backups, and disaster recovery

These four concepts are frequently conflated:

| Mechanism | Purpose | What it cannot replace |
|---|---|---|
| **Persistence** | Writes a single Redis instance's data to disk, typically via RDB/AOF | Offsite backups, recovering state before an accidental delete |
| **Replication** | Copies state from master to replicas to increase availability | Multi-version history, independent backups |
| **Backup** | Retains copies at defined points in time, outside normal runtime paths | Instant automatic failover |
| **Disaster recovery (DR)** | Procedures to restore service after major outages, covering infra, configs, and data | Generating valid backup files if none were planned beforehand |

Example:

```text
                  Spring application
                          |
                          v
                       Redis M
                       /     \
             replication     persistence
                    /           \
                Redis R        RDB/AOF on disk
                                  |
                            backup job
                                  |
                            encrypted archive
                                  |
                         offsite/object storage
                                  |
                          restore drill / DR
```

If an application accidentally sends `FLUSHALL`, the deletion can **replicate** to replicas, and the post-deletion state can overwrite new AOF/snapshot files. A replica sharing the same logic bug is not an independent copy to roll back to yesterday. You need **versioned backups with retention**.

### 1.1. Example data classification before planning

| Redis data | Rebuildable? | Approach |
|---|---|---|
| Query result cache from PostgreSQL | Usually yes | Can skip backups, but budget for warm-up cost |
| Login sessions | Recoverable by re-login, though impacts UX | Define acceptable RPO and downtime |
| Redis Streams with unprocessed jobs | Not necessarily | Persistence, backups, retention, and consumer group recovery |
| Inventory count cache | Authoritative DB exists | Ensure rebuild from DB and avoid trusting stale cache as truth |
| Counters or business state living solely in Redis | Potentially no | Strict durability design or move source of truth to proper storage |
| Short-lived rate limiters | Usually needs no history | Rebuildable; weigh impact of counter resets |

**Do not assume all Redis data needs the same backup policy.** Data semantics dictate backup frequency and post-restore checks.

## 2. RPO and RTO: start from business requirements

Two key targets:

- **RPO (Recovery Point Objective):** the maximum time-equivalent data loss acceptable.
- **RTO (Recovery Time Objective):** the maximum acceptable time to restore required functionality after an outage.

```text
                         Incident
                            |
       Last backup          |                 Service restored
               |            |                         |
---------------+------------+-------------------------+----> time
               <--- RPO --->|<---------- RTO -------->|
```

Example system using Redis for intermediate events:

| Service tier (example) | RPO | RTO | Design options to consider |
|---|---|---|---|
| Rebuildable cache | Total cache loss | 15–60 minutes to warm up | No cache backups needed; have a rebuild plan |
| Sessions tolerating re-login | 1 hour | 30 minutes | Periodic RDB, automated restore |
| Critical job streams | Seconds/minutes per SLA | 15 minutes | AOF + RDB + off-host backups, test replay/idempotency |
| Zero-loss financial data | Near 0 per business | Strict | Do not rely solely on Redis async replication; choose an authoritative store with suitable commit guarantees |

These are **design examples**, not actual RPO/RTO promises made by Redis. RPO is meaningful only when measured as the age of the **completed, safely transferred, and verified** backup. A job running every 5 minutes whose uploads have failed for 8 hours straight does not achieve a 5-minute RPO.

### 2.1. Formula for planning backup schedules

Suppose:

```text
Snapshot frequency: 15 minutes
Snapshot creation time: 2 minutes
Copy/upload time: 3 minutes
Job failure detection time: 5 minutes
```

You cannot simply declare RPO is 15 minutes. Account for the age of **the last protected recovery point** at incident time, backup pipeline latency, and the risk of a missed run. RTO similarly includes incident detection, fetching artifacts, provisioning hosts, loading data, verifying correctness, and shifting traffic.

Validate these numbers with **real restore drills**, not paper estimates.

## 3. Redis persistence: RDB, AOF, combined, or disabled

Redis offers four main options:

### 3.1. RDB: point-in-time state snapshot

Redis writes a binary snapshot, typically `dump.rdb`. Snapshots can be configured on schedules or requested via `BGSAVE`.

Pros:

- A relatively compact single file, easy to retain multiple timestamped versions.
- Typically fast to reload on restart for large datasets compared to replaying a long AOF.
- Well suited for offsite backups and staging restores.

Limitations:

- Changes after the latest snapshot can be lost if the process or host fails.
- `BGSAVE` requires `fork`/copy-on-write and disk I/O, raising RAM, CPU, and storage pressure.
- If a new snapshot fails, an old RDB file may linger; **file presence does not mean the latest backup succeeded**.

### 3.2. AOF: logging data-mutating operations

AOF (Append Only File) logs state-mutating commands so Redis can rebuild the dataset on startup. `appendfsync` policies:

| Value | Principle | Trade-off |
|---|---|---|
| `always` | Frequently syncs write batches to storage | Safer against crashes, yet raises latency and reduces throughput |
| `everysec` | Fsyncs roughly once per second | Balances performance with risk of losing writes right before a crash |
| `no` | Lets the OS decide when to flush | Potentially much larger data loss on host failure |

Never interpret `appendfsync everysec` as "a strict 1-second guarantee across all failure types". OS, filesystem, storage controller, volume/zone loss, and replication each carry distinct failure models.

### 3.3. RDB + AOF

Redis can enable both:

```conf
appendonly yes
appendfsync everysec
save 900 1
save 300 10
save 60 10000
```

Those `save` lines are **example snapshot rules**, not mandatory for every workload. When both RDB and AOF are enabled, Redis normally **prioritizes AOF to reload the dataset on startup** because AOF can hold newer state than RDB.

This is crucial in restore runbooks: **merely copying a `dump.rdb` into the data directory of an instance with an active AOF enabled does not guarantee Redis loads your RDB**. Always specify which artifact will load and prepare compatible configuration.

### 3.4. No persistence

If Redis stores only completely rebuildable cache, persistence can be intentionally turned off:

```conf
save ""
appendonly no
```

This fits when the system can warm up or degrade gracefully; it also means Redis data can vanish on restart. Never apply this to critical Redis Streams or queues merely because Redis is commonly labeled a cache.

### 3.5. Quick comparison table

| Criterion | RDB | AOF | RDB + AOF |
|---|---|---|---|
| Recovery point | Snapshot timestamp | Per log/fsync | Both snapshot and log |
| Artifact size | Typically compact | Can grow larger | Storage needed for both |
| Offsite copy | Fairly easy with complete RDB | Must ensure consistent AOF set | Must manage both types |
| Load duration | Often faster | Can be long due to replay | AOF usually prioritized on restart |
| Risk of losing recent changes | Depends on snapshot schedule | Depends on fsync/storage | Not zero |
| Restore to historical point | Easy if multiple historical RDBs kept | Requires AOF at target point or log process | More options |

## 4. What else must be backed up besides Redis data

A backup containing **only the dataset** is rarely enough to rebuild a service.

| Component | Example | Automatically inside RDB/AOF? |
|---|---|---|
| Redis keys/values and TTLs | Strings/Hashes/Sets/Streams | Yes, per format and snapshot time |
| Redis settings | `maxmemory`, `appendonly`, `save`, `dir` | Do not assume data backups carry full `redis.conf` |
| ACLs/credentials/TLS | ACL files, certificates, secrets | Back up and manage separately and securely |
| Redis modules | Search/JSON/TimeSeries per deployment | Must install compatible versions and test artifacts |
| Infrastructure & storage | Disks, PVCs, hostnames, firewalls | Belongs in IaC/DR runbooks |
| Sentinel topology | Master name, sentinels, auth | Cannot be rebuilt from an RDB alone |
| Cluster topology | Slot ownership, node roles, `nodes.conf` metadata | Needs procedures to recreate Cluster and map shards properly |
| Spring configuration | Redis nodes, serializers, namespaces, prefixes, key mappings | Stored in app config / secret manager |
| Backup manifest | Timestamp, version, checksums, source | Generated explicitly by the backup pipeline |

In Redis Cluster, `nodes.conf` is managed by Redis itself; **never hand-edit it to "match" an arbitrary set of RDB files**. Cluster restores require shard-, slot-, metadata-, and membership-aware procedures.

## 5. Checking state before backing up

On a test Redis or via an authorized operational account:

```bash
redis-cli -h 127.0.0.1 -p 6379 INFO server
redis-cli -h 127.0.0.1 -p 6379 INFO replication
redis-cli -h 127.0.0.1 -p 6379 INFO persistence
redis-cli -h 127.0.0.1 -p 6379 INFO memory

redis-cli -h 127.0.0.1 -p 6379 CONFIG GET dir
redis-cli -h 127.0.0.1 -p 6379 CONFIG GET dbfilename
redis-cli -h 127.0.0.1 -p 6379 CONFIG GET appendonly
redis-cli -h 127.0.0.1 -p 6379 CONFIG GET appenddirname
```

Common fields to inspect in `INFO persistence`:

```text
rdb_bgsave_in_progress
rdb_last_bgsave_status
rdb_last_save_time
rdb_last_bgsave_time_sec
aof_enabled
aof_rewrite_in_progress
aof_last_bgrewrite_status
aof_last_write_status
```

Field names and presence vary by Redis version; parse according to your deployed version.

**Avoid putting passwords directly in command history** whenever possible. Use secret managers, ACLs, TLS, and secure environment variables; example commands assume an unauthenticated test Redis.

### 5.1. Checking whether a snapshot is running or finished

`BGSAVE` runs asynchronously. Receiving confirmation that the request was accepted **does not mean the snapshot has finished writing**.

Consider a snapshot complete only when:

- `rdb_bgsave_in_progress` is no longer active.
- `rdb_last_bgsave_status` indicates success.
- `rdb_last_save_time` / `LASTSAVE` increased appropriately compared to before the request.
- The target file exists and can be copied/verified.

If busy with another background task, `BGSAVE` may not start immediately or may return an error; backup jobs must verify actual status rather than assuming success.

### 5.2. Monitoring disk and memory

RDB saves and AOF rewrites spawn background processes and trigger copy-on-write. Heavy writes during a snapshot raise RAM usage. Monitor free disk space, latency, memory, child process status, and upload throughput before scheduling frequent snapshots.

A completed snapshot cannot save you if the backup disk fills up, the offsite target is unreachable, or the backup job keeps only a single version and overwrites it.

## 6. Backing up RDB while Redis is running

Redis writes RDB to a **temporary file**, then atomically swaps the target file upon completion. A completed RDB stays immutable until the next snapshot replaces it. Copying the existing `dump.rdb` while Redis runs is therefore Redis's recommended backup method, **provided you verify the exact snapshot version and data age**.

### 6.1. Standard procedure

1. Identify the Redis instance and its master/replica role.
2. Check `CONFIG GET dir`, `dbfilename`, `INFO persistence`, and `LASTSAVE`.
3. If a fresh snapshot is needed, trigger `BGSAVE` with an operational account; avoid routine blocking `SAVE` in production.
4. Wait for `BGSAVE` to succeed and the snapshot timestamp to advance.
5. Copy the completed RDB to a **separate staging path, never reusing the live Redis filename**.
6. Compute a SHA-256 checksum, write a manifest, and upload to independent storage.
7. Verify destination checksums, retention policies, access controls, and alerts.
8. Run periodic restore drills into an isolated Redis instance.

Redis CLI example:

```bash
# Before snapshot:
redis-cli -h 127.0.0.1 -p 6379 LASTSAVE
redis-cli -h 127.0.0.1 -p 6379 INFO persistence

# Run on test infra or under a controlled runbook:
redis-cli -h 127.0.0.1 -p 6379 BGSAVE

# Poll until complete:
redis-cli -h 127.0.0.1 -p 6379 INFO persistence
redis-cli -h 127.0.0.1 -p 6379 LASTSAVE
```

### 6.2. External artifact staging pattern

Suppose the completed RDB sits at `/var/lib/redis/dump.rdb` on a Linux test machine and the backup directory already exists:

```bash
cp /var/lib/redis/dump.rdb \
   /srv/redis-backups/staging/redis-standalone-20261113T030000Z.rdb

sha256sum \
   /srv/redis-backups/staging/redis-standalone-20261113T030000Z.rdb
```

The filename in the example illustrates a UTC timestamp only. Operational jobs must compute the real UTC timestamp, node ID, and run ID. Verify `BGSAVE` succeeded **before copying** if the runbook requires a fresh snapshot for that run.

Never delete the last valid snapshot just because a newer snapshot failed. Prune old versions only after verifying replacement copies meet retention and offsite safety.

### 6.3. Why retain multiple point-in-time backups?

```text
00:00  backup-A (before application bug)
01:00  backup-B
02:00  application accidentally deletes critical keys
03:00  backup-C (already contains broken state)
04:00  incident detected
```

Keeping only backup-C **cannot restore data from before the deletion**. Multi-version retention lets you pick backup-A or backup-B, while recognizing newer valid writes after that point may be lost. Blindly restoring the entire dataset can cause business drift, so evaluate **restore scope** and compensating replay/reconciliation.

## 7. Backing up AOF: special care for Redis 7 and later

Redis 7.0+ uses **multi-part AOF**: one base AOF (in RDB or AOF format), multiple incremental AOFs, and a manifest describing valid files.

Illustrative layout:

```text
/var/lib/redis/
  appendonlydir/
    appendonly.aof.manifest
    appendonly.aof.12.base.rdb
    appendonly.aof.12.incr.aof
    appendonly.aof.13.incr.aof
```

Filenames and sequence numbers depend on server and configuration. **Never assume copying a single `appendonly.aof` file like older Redis versions suffices.** A manifest missing its base or an incremental file is not a complete recoverable backup.

### 7.1. Why copying AOF during a rewrite can corrupt the backup

During `BGREWRITEAOF`, Redis generates a new base and incremental files, then updates the manifest. If a backup script copies one file before and another file after a generation switch, the copy can end up with:

- A new-generation manifest missing the base or increment it references.
- A mix of old-generation and new-generation files.
- Files already pruned by Redis mid-copy.

**Never run an uncontrolled `cp -r appendonlydir` while a rewrite is active** and call it a consistent backup.

### 7.2. Common AOF backup procedure per Redis documentation

For Redis 7+:

1. Read and **save the original value** of `auto-aof-rewrite-percentage`.
2. Temporarily disable auto-rewrites with `CONFIG SET auto-aof-rewrite-percentage 0`.
3. Do not trigger manual `BGREWRITEAOF` during the backup window.
4. Wait until `INFO persistence` reports `aof_rewrite_in_progress:0`.
5. Copy **all files in `appenddirname`**, including the manifest and active base/incremental files, to staging.
6. Restore the original auto-rewrite percentage **even if copying/uploading fails**, via cleanup/`finally` logic.
7. Compute checksums per file, write the backup manifest, and test restoring from the copy.

Illustrative commands:

```bash
redis-cli -h 127.0.0.1 -p 6379 \
  CONFIG GET auto-aof-rewrite-percentage

# Run only inside an authorized backup runbook:
redis-cli -h 127.0.0.1 -p 6379 \
  CONFIG SET auto-aof-rewrite-percentage 0

redis-cli -h 127.0.0.1 -p 6379 INFO persistence

# Once copying completes and auto-rewrite no longer needs pausing:
# Restore the exact value read in step 1.
redis-cli -h 127.0.0.1 -p 6379 \
  CONFIG SET auto-aof-rewrite-percentage 100
```

**The trailing `100` is purely an example**; never blindly overwrite the originally configured value. Backup automation must capture the prior value and guarantee restoration via cleanup handlers even on errors.

If copying takes long, consider OS/filesystem snapshots or hard-link workflows as supported to shorten the rewrite-pause window. Never improvise hard-link scripts casually because active incremental AOFs may still receive appends; packaging and copy timing must follow your Redis version's contract.

### 7.3. Do not enable AOF on a running Redis by editing the config file and restarting blindly

When switching from RDB to AOF, follow Redis's **online** conversion procedure, monitor initial AOF generation to completion, and persist the updated config. Simply changing `appendonly no` to `appendonly yes` in a config file and restarting can make Redis load the wrong/empty artifact and even lose data.

This is a persistence-mode migration; do not bundle it into routine backup scripts without a migration and rollback plan.

## 8. Modern Redis: version-specific online BACKUP commands

In **Redis Open Source 8.10.0 and later**, Redis documentation introduces the `BACKUP` command group for creating stamped, restorable online backups, separating start and seal phases:

```text
BACKUP START
     |
     v
Create BASE snapshot
     |
     +--> BACKUP LIST: shows pinned files
     |
     v
BACKUP SEAL
     |
     +--> freeze INCR + manifest
     |
     v
Copy files from BACKUP LIST to independent storage
     |
     v
BACKUP CLEANUP
```

`BACKUP STATUS` reports progress; `BACKUP ABORT` cleans up an unsealed backup. The file set comprises BASE, INCR, and manifest—not just a single `dump.rdb`. On supporting versions, Redis provides the startup option `preload-file`, shown here illustratively:

```conf
preload-file aof:/tmp/restore-backup/appendonly.aof.manifest
```

**Do not use these commands on Redis 6/7/8.0 if your server does not support them.** Always check `INFO server`/`redis_version` and version-specific Redis docs. This newer mechanism simplifies several AOF backup steps without replacing offsite verification, retention, and application restore testing.

## 9. Storing backups: 3-2-1, encryption, and access control

A backup architecture might look like:

```text
Redis data nodes
     |
     | complete snapshot / consistent AOF set
     v
Backup staging (with checksums)
     |
     +--> Local backup store (fast recovery)
     |
     +--> Offsite object storage / region B
                |
                +--> Versioning / immutable retention
                +--> Encryption at rest
                +--> Integrity metadata
                +--> Access logs / alerts
```

The **3-2-1** principle serves as a design guideline: retain multiple copies across appropriate media/tiers, including an independent offsite copy outside the primary operating domain. Exact details must fit RPO, RTO, data sensitivity, and budget.

### 9.1. Security principles

- Encrypt backups in transit and at rest, managing keys via KMS/secret managers.
- Separate **read backup**, **create backup**, **delete backup**, and **restore** permissions; never let application credentials delete all backups.
- Use versioning, object lock, or immutable retention to defend against ransomware and accidental deletion.
- Retain access logs and audit who downloads or restores sensitive data.
- Never print session payloads, tokens, or sensitive keys into backup manifests or logs.
- Verify decryption key availability from redundant locations; encrypted backups with lost keys cannot be restored.

Redis backups can hold personal data, session tokens, refresh tokens, or Stream message payloads. Protect them at production security standards—even copies resting in "test" buckets.

### 9.2. Retention tiers

Example:

| Backup tier | Frequency | Illustrative retention |
|---|---|---|
| Recent RDB | Hourly | 48 hours |
| Historical RDB | Daily | 30 days |
| Long-term RDB | Weekly | 12 weeks |
| AOF backups for tight recovery | Per separate policy | Based on RPO/storage |

Do not treat this table as mandatory law. For data subject to legal obligations or right-to-erasure rules, review PII retention and deletion workflows in backups per corporate policy.

## 10. Manifests: describing backups for reliable recovery

Every backup should carry metadata alongside its files:

```yaml
backupId: "redis-prod-20261113T030000Z-run45"
environment: "production"
redisVersion: "8.x-example"
topology: "standalone"
nodeId: "redis-prod-01"
roleAtCapture: "master"
snapshotType: "rdb"
captureRequestedAtUtc: "2026-11-13T03:00:00Z"
snapshotCompletedAtUtc: "2026-11-13T03:01:16Z"
uploadedAtUtc: "2026-11-13T03:02:03Z"
sourcePersistence:
  appendonly: true
  appendfsync: everysec
files:
  - name: "redis-prod-01-20261113T030000Z.rdb"
    bytes: 123456789
    sha256: "<SHA256 computed over actual bytes>"
verification:
  checksumAtDestination: passed
  restoreDrill: pending
schemaVersion: 1
```

All values are illustrative, not from a real backup. In Cluster deployments, include shard IDs, slot sets, master/replica ownership, cluster generation/topology snapshots, and **per-node** artifact lists.

**Checksums verify copy integrity, not that the contents represent the desired data point.** If the source RDB was stale yet copied accurately, SHA-256 matches while RPO fails.

### 10.1. Verify checksums on both sides

Example on Linux:

```bash
sha256sum /srv/redis-backups/staging/backup.rdb
sha256sum /srv/redis-backups/downloaded/backup.rdb
```

Compare checksums, file sizes, and artifact metadata. When uploading to object storage, understand provider checksum/ETag semantics: **ETag is not always a whole-file MD5**, especially with multipart uploads or encryption. Prefer computing and verifying SHA-256 explicitly in your backup pipeline after download.

## 11. Restoring RDB in an isolated environment

**Rule number one:** restore drills must run on an **empty, independent** Redis instance with dedicated port, data directory, network, and credentials. Never overwrite a running production Redis with backup files.

### 11.1. Standard steps

1. Select a backup ID matching target RPO and pre-incident time.
2. Download artifacts and manifest from independent storage; verify checksums.
3. Provision a restore Redis instance with compatible version, required modules, and its own data directory.
4. **Stop the restore Redis instance** before placing data files.
5. Place `dump.rdb` into `dir` under the expected `dbfilename`.
6. Ensure the restore instance's AOF config **does not accidentally prioritize an old AOF**; to load RDB via traditional startup, use a test config with RDB enabled and AOF off, or use `preload-file` on supporting versions.
7. Start the restore Redis instance, inspect startup loading logs and `INFO persistence`.
8. Check sample keys, data types, TTLs, Stream groups, and app metrics.
9. Record elapsed time from start until the application confirms readiness.

Example configuration **strictly for a test restore Redis**:

```conf
bind 127.0.0.1
protected-mode yes
port 6385
dir /srv/redis-restore-lab
dbfilename dump.rdb
appendonly no
save ""
```

After copying the RDB to `/srv/redis-restore-lab/dump.rdb`, start a separate Redis process with that config and run:

```bash
redis-cli -h 127.0.0.1 -p 6385 PING
redis-cli -h 127.0.0.1 -p 6385 INFO persistence
redis-cli -h 127.0.0.1 -p 6385 DBSIZE
```

`DBSIZE` reports current key count only; **it is insufficient to prove all values are accurate**. It can also differ from the key count at capture time because keys expire during storage and restore.

### 11.2. Why test on an empty instance?

Restoring into a Redis already holding other keys can mix old and new data or overwrite state unpredictably. In production recovery, the goal is usually standing up **a dataset with clean provenance** rather than ad-hoc merging via scattered `RESTORE`/`SET` scripts.

When you only need to recover specific accidentally deleted keys, first restore the full backup into an isolated environment, verify the target keys, and build a controlled migration script into production. Restoring individual keys requires checking TTLs, key types, serializers, concurrent updates, and consistency with origin systems.

## 12. Restoring AOF and missing-component risks

For Redis 7+ multi-part AOF:

1. Download **the complete set of base, incremental, and manifest files** Redis expects.
2. Verify SHA-256 checksums and sizes for every file.
3. Place files in the `appenddirname` layout the restore Redis reads.
4. Start with a compatible Redis version/config, **never mixing a new manifest with AOF files from another generation**.
5. Inspect startup logs, replay duration, and load status.
6. Run business data and expiration checks.

If an AOF is corrupted, Redis provides `redis-check-aof`, yet never run `--fix` directly on **your only backup copy**. Repairing can truncate logs after the error offset, losing data; instead:

- Make an immutable copy of the corrupted artifact.
- Record original checksums and error logs before fixing.
- Test repairs on a separate copy and document lost entries.
- Reconcile against other backups and authoritative data sources.

Similarly for RDB, use `redis-check-rdb` to inspect file structure before restoring:

```bash
redis-check-rdb /srv/redis-backups/downloaded/dump.rdb
```

Tools require matching Redis versions and read permissions. **Passing a structural parser check does not prove keys or business data are accurate or recent enough.** Restores and integration checks remain mandatory.

### 12.1. Distinguishing AOF files, AOF rewrites, and backup points

`BGREWRITEAOF` compacts logs for faster startup. It **is not a multi-version backup history command**; after a rewrite, obsolete files may be deleted. Keeping only the live AOF does not let you pick an arbitrary historical point prior to a bad write.

Therefore, multi-version RDB snapshots and offsite storage remain valuable even when AOF is enabled.

## 13. TTL after restore: do not expect deadlines to "freeze"

A very common misconception:

```text
00:00   Write session:user-42 with 30-minute TTL
00:05   Take RDB snapshot
02:00   Restore RDB into new Redis
```

At restore time, that old session is likely **already expired**, rather than receiving 25 remaining minutes. Redis stores expiration as absolute timestamps in its persistence format; once loaded, keys past their expiration are treated as expired.

Consequences:

- Post-restore key counts can be **smaller** than key counts when the snapshot ran.
- `DBSIZE` can differ even when the file is 100% intact.
- Sessions, rate limits, and caches should not be verified by "exact key-for-key count match" when TTLs are used.
- Storing a backup for days does not keep short-lived sessions alive forever.
- System clocks on restore hosts must be accurate; major clock skew causes premature or delayed expiration.

### 13.1. Sensible TTL verification

Example checks on a restored Redis:

```redis
TYPE product:100
TTL product:100
PTTL session:user-42
GET product:100
```

Interpreting `TTL` output:

| Result | Meaning |
|---|---|
| Non-negative integer | Remaining lifetime in seconds |
| `-1` | Key exists with no expiration |
| `-2` | Key does not exist (may have expired) |

For keys expected to persist indefinitely, `-1` is valid. For keys required to expire, `-1` warrants investigation. Document **expected policies** per namespace instead of assuming every key has a TTL.

## 14. Sentinel: backing up a replica does not guarantee the newest data

With Redis Sentinel:

```text
                Sentinel quorum
                      |
            Redis master M1
                 |
        asynchronous replication
                 |
            Redis replica R1
                 |
         create/copy RDB from replica
```

Taking backups from a replica often offloads snapshot pressure from the master. However, asynchronous replication means the replica **may lack the most recent writes**.

When backing up from a replica:

1. Confirm it is replicating from the right master.
2. Inspect `INFO replication`: role, link status, and offset/lag.
3. Measure replica lag and establish the true recovery point.
4. Capture only after confirming the replica meets RPO lag thresholds.
5. Guard against failover occurring between node selection and backup completion.
6. Record node ID, role, master group, timestamp, and replication state in the manifest.

Never treat a replica backup as linearizable with every master-acknowledged write. If a write returned OK on the master before replicating to R1, R1's backup can lack it.

### 14.1. Failover occurring mid-backup

If the master changes while a backup runs:

- The source node may switch roles between master and replica.
- Replication offsets and captured state may not reflect the intended point.
- Spring Data Redis clients may route to a new master while the backup runs on the old node.

Runbooks should record topology **before and after** the backup. If recovery-point validity cannot be proven, mark that run **suspect/quarantine** rather than listing it as a "valid backup".

## 15. Redis Cluster: every shard must be protected

Redis Cluster partitions keys across 16,384 hash slots managed by multiple masters. **An RDB from one master is not a backup of the whole Cluster.**

```text
                         Redis Cluster
                       16,384 hash slots
                              |
               +--------------+--------------+
               |              |              |
          Master A         Master B        Master C
          slots A          slots B         slots C
               |              |              |
             RDB-A          RDB-B          RDB-C
               |              |              |
               +--------------+--------------+
                              |
                    Backup set + manifest
                              |
                       Offsite storage
```

To restore the entire logical dataset, you need snapshots/datasets for **every shard**. If resharding, failover, or replica migration occurs during backups, record topology at backup time and enforce checks for missing or overlapping slots.

### 15.1. No global atomic snapshot by default

Suppose:

```text
10:00:00  Back up shard A
10:00:30  Application updates A then B
10:01:00  Back up shard B
```

Combining A from 10:00 with B from 10:01 may represent a Cluster-wide state that never actually existed at any single point in time. Cross-shard workflows can end up inconsistent in that backup.

Options depending on requirements:

- If Redis is solely a cache: independent per-shard backups can suffice; reload from authoritative sources post-restore.
- If data is tightly coupled: establish an **application-level consistency point**, pause writes in a controlled window, or use changelogs/outbox to resynchronize.
- If writes cannot pause: rely on dedicated snapshot/changelog mechanisms and business-ordered replay; do not assume independent RDBs yield global transactions.
- With Redis 8.10+ `BACKUP START/SEAL`, per-node backup windows are cleaner to manage, yet **still do not automatically produce a multi-shard atomic snapshot**.

### 15.2. What else belongs in a Cluster manifest?

```yaml
backupId: cluster-20261113T030000Z
topology: cluster
clusterState: ok
expectedSlots: 16384
shards:
  - shardId: "shard-A"
    roleAtCapture: master
    nodeId: "node-a"
    slotRanges: ["0-5460"]
    artifact: "node-a.rdb"
    sha256: "<computed>"
  - shardId: "shard-B"
    roleAtCapture: master
    nodeId: "node-b"
    slotRanges: ["5461-10922"]
    artifact: "node-b.rdb"
    sha256: "<computed>"
  - shardId: "shard-C"
    roleAtCapture: master
    nodeId: "node-c"
    slotRanges: ["10923-16383"]
    artifact: "node-c.rdb"
    sha256: "<computed>"
```

Slot ranges merely illustrate a three-master split. In real operations, query `CLUSTER SHARDS` or `CLUSTER SLOTS` from the live Cluster rather than hardcoding slot ownership like the example.

### 15.3. Checks before certifying a Cluster backup set

- Are artifacts present for every master/shard requiring protection?
- Do assigned slot ranges cover all slots without gaps or improper overlaps at capture time?
- Was the backing-up node a master or replica of each shard?
- Was replication lag within RPO?
- Did resharding or failover happen during the capture window?
- Can an empty Cluster be stood up matching the topology and each shard loaded via a tested runbook?

Never dump all master RDBs onto a single Standalone Redis hoping it merges data and preserves cluster keyspaces/slots.

## 16. Restoring a Cluster: two different paths

### 16.1. Full Cluster disaster recovery

General workflow:

1. Identify a **complete-shard** backup set and manifest.
2. Provision new Redis Cluster infrastructure in the restore target: nodes, networking, disks, accounts, TLS, matching versions.
3. Recreate topology and slot assignments per your Redis version's runbook.
4. Load each shard/node's artifact or use supported restore/cluster migration tools.
5. Confirm `CLUSTER INFO` reports full slot coverage and all masters/replicas healthy.
6. Validate data across namespaces/slots and from the Spring application.
7. Shift traffic only after read/write smoke tests, health checks, and business reconciliation pass.

Exact steps for node addresses, cluster state, and data import depend on Redis version, orchestrator, and backup tooling. **You cannot simply run `redis-cli --cluster create` and drop random RDB files onto production nodes** without aligning slot mappings.

### 16.2. Restoring a subset of accidentally deleted keys

Restoring an entire Cluster to an earlier point can wipe valid writes created afterward. If only specific keys were lost:

1. Restore the backup into an **isolated** environment.
2. Identify target keys via business records—avoid `KEYS *` on large production instances.
3. Verify data types, TTLs, values, index dependencies, and idempotency.
4. Copy/migrate selected keys into production using controlled APIs.
5. Protect newer data that may have been created under the same key names since the incident.

Redis `DUMP`/`RESTORE` can transfer individual key representations, though direct use must consider encoding versions, expirations, existing keys, and `REPLACE` semantics. Never turn a historical recovery script into an unconditional overwrite against production.

## 17. Three-tier backup verification

A trustworthy backup policy needs **three verification tiers**—none replaces the others:

### Tier 1 — File and transfer integrity

Verify:

- All files/artifacts and the manifest exist.
- File sizes match, and SHA-256 matches between source and destination.
- Storage returns the expected object version/backup ID.
- No multipart upload errors or truncated files occurred.
- Lifecycle policies did not purge the backup prematurely.

### Tier 2 — Redis can load the files

Verify:

- `redis-check-rdb` or version-matched AOF tools report zero structural errors.
- A test Redis instance starts and loads the data cleanly.
- Startup logs show no checksum errors, invalid AOFs, or missing modules.
- Load time stays within projected RTO bounds.
- `INFO persistence` reports healthy post-restore status.

### Tier 3 — Data is valid per business rules

Verify:

- Critical keys and structures are accessible.
- Redis types (String, Hash, Stream, ZSet...) match expectations.
- Keys with TTLs follow expected expiration rules.
- Spring Data Redis schemas/serializers decode the data cleanly.
- Consumer groups, Stream recovery, and secondary indexes function properly.
- Business totals reconcile with authoritative sources or consistency markers.

**A backup whose SHA-256 matches yet fails to load in Redis is a failure. A backup that loads in Redis yet holds corrupted business state is also unfit for recovery.**

## 18. Designing canary and integrity markers

To verify a recovery point, you can write a dedicated **test marker** key that never collides with customer data. For example, right before a backup job triggers an RDB snapshot:

```redis
HSET backup:canary:run45 id run45 expectedValue "ok" createdAt "2026-11-13T03:00:00Z"
```

Include this marker in snapshot expectations only if the write completed **before Redis actually captured the snapshot**. A marker written after `BGSAVE` forked **is not guaranteed to appear in that snapshot**.

After restore:

```redis
HGETALL backup:canary:run45
TYPE backup:canary:run45
```

A surviving marker provides strong evidence for a single point in time, yet does not prove the entire dataset is intact. Combine it with:

- Representative keys with known values across key namespaces.
- Keys holding Hashes/ZSets/Streams with specific checkable fields and members.
- Record counts aligned with origin systems.
- Dataset digests/checksums computed at consistent checkpoints.

### 18.1. Avoid verifying by scanning the entire keyspace during live production writes

On a running Redis, `SCAN` does not produce an atomic snapshot of the keyspace. If keys mutate during scanning, the output is not a consistent list at one timestamp.

In Redis Cluster, `SCAN` on **one node** covers only keys served by that node; full inventory requires scanning every master/slot range. For large datasets, run full key/value checksums against an **isolated restore instance** or rely on app metadata anchored to a consistent snapshot point.

## 19. Verification from a Spring Data Redis application

Once the restore Redis instance is running, a Spring Boot verification test can connect using dedicated endpoints and credentials. Never allow a test verifier to accidentally use production connection factories.

Example test-profile config:

```yaml
spring:
  data:
    redis:
      host: 127.0.0.1
      port: 6385
      timeout: 3s
```

### 19.1. Checking invariants with StringRedisTemplate

Suppose the backup is expected to contain:

```text
backup:canary:run45 (Hash)
catalog:version      (String, no TTL)
session:test-42      (String, with TTL; may have expired if restored late)
```

A verification service:

```java
import java.util.Map;
import org.springframework.data.redis.connection.DataType;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisRestoreVerifier {

    private final StringRedisTemplate redis;

    public RedisRestoreVerifier(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void verifyCanary(String backupRunId) {
        String key = "backup:canary:" + backupRunId;

        DataType type = redis.type(key);
        if (type != DataType.HASH) {
            throw new IllegalStateException(
                    "Canary key missing or wrong type: " + type);
        }

        Map<Object, Object> fields =
                redis.opsForHash().entries(key);

        if (!backupRunId.equals(fields.get("id"))) {
            throw new IllegalStateException(
                    "Canary backup run ID does not match");
        }

        if (!"ok".equals(fields.get("expectedValue"))) {
            throw new IllegalStateException(
                    "Canary payload is invalid");
        }
    }
}
```

This is a **read-only** check against a canary written before the snapshot. It never injects fresh markers into the restored copy, avoiding masking backup bugs. If your app uses JSON/JDK serializers, use the matching `RedisTemplate`/`RedisSerializationContext` rather than reading every value blindly as a String.

### 19.2. Checking TTLs with Spring Data Redis

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public void checkExpiringKey(
        StringRedisTemplate redis,
        String key) {

    Duration ttl = redis.getExpire(key);

    if (ttl == null) {
        throw new IllegalStateException(
                "Cannot determine TTL of " + key);
    }

    // Spring may represent Redis -1/-2 as negative Durations.
    // Compare only with full knowledge of the key's policy.
    if (!ttl.isNegative() && ttl.isZero()) {
        // Key is about to expire or already expired; do not assume backup failed.
    }
}
```

For keys with TTLs, results depend on restore timing. Verification should check rules like "key may have expired because the backup is old" or "by policy this key must have no TTL", instead of asserting the exact second count from capture time.

### 19.3. Verifying Redis Streams

When Redis Streams hold critical jobs, also check:

```redis
TYPE orders:events
XLEN orders:events
XINFO STREAM orders:events
XINFO GROUPS orders:events
XPENDING orders:events billing-workers
```

Verify:

- Are message IDs/cursors intact?
- Do consumer groups and pending entries match the recovery point?
- Must un-`XACK`ed messages be reprocessed?
- Is idempotency in place to prevent duplicate side effects post-restore?
- Do messages newer than the backup yet already processed elsewhere need reconciliation?

Restoring Streams neither rolls back side effects already committed outside Redis nor guarantees consumer groups resume cleanly if application logic skips the PEL.

## 20. RPO/RTO differ across Spring Cache, Repositories, and Streams

Because Spring Data Redis serves multiple patterns, restore plans must distinguish:

### 20.1. Spring Cache

Caches backed by `@Cacheable` can usually rebuild from a database. Restoring a **very stale** cache can be worse than starting empty if stale keys remain with long or infinite TTLs.

Example:

```java
@Cacheable(cacheNames = "productDetails", key = "#id")
public ProductView getProduct(String id) {
    return repository.load(id);
}
```

Post-restore, consider:

- Selectively flushing/clearing caches known to be rebuildable.
- Versioning namespaces such as `app:v2:...` when cache schemas change.
- Controlled warm-ups to prevent cache stampedes hitting the database.
- Never restoring stale price/inventory caches and treating them as transactional truth.

### 20.2. Redis Repositories

With `@RedisHash` and auxiliary entity/index keys:

- Do not just check that the entity key exists; verify indexes, ID sets, TTLs, and schemas/serializers.
- Indexes can drift after data rollbacks or application version changes.
- Never copy entities into a new backup while omitting Spring-managed auxiliary structures.

After staging restores, execute the actual Repository queries your application uses—not just raw byte `GET`s.

### 20.3. Redis Streams

Streams track delivery progress and pending state. Restoring to an earlier point means:

- An event ACKed after the backup point may reappear as un-ACKed.
- An event written after the backup may vanish from the restored dataset.
- Side effects in external SQL databases or APIs may still exist.

Hence, **idempotency and reconciliation** are mandatory parts of any DR plan for stream processing.

## 21. Periodic restore drills: measure against the clock

A drill runbook might follow:

```text
T0  Receive signal "primary Redis environment unavailable"
 |
 +-- Assess impact and select backup ID
 |
 +-- Download manifest + artifacts into restore environment
 |
 +-- Verify SHA-256 and completeness
 |
 +-- Provision matching Redis version infrastructure
 |
 +-- Load RDB/AOF and wait for Redis readiness
 |
 +-- Run CLI checks + business canary
 |
 +-- Boot Spring app with restore profile
 |
 +-- Smoke test read/write flows and reconciliation
 |
 +-- Record results and elapsed timings
 v
T1  Restore accepted / drill completed
```

Elapsed time **T1 − T0** provides real evidence for RTO, while clearly noting scope: "Redis ready" differs from "application serving customers normally".

### 21.1. Drills to include

| Scenario | Objective |
|---|---|
| Restore latest RDB | Validate artifact integrity and fastest recovery path |
| Restore RDB older than 24 hours | Validate retention, version selection, and TTL handling |
| Restore multi-part AOF set | Verify complete base/increment/manifest handling and replay time |
| Simulate one missing artifact | Confirm pipeline detects corruption and rejects incomplete set |
| Restore with missing module or old serializer | Assess compatibility and migration runbooks |
| Restore Redis Streams | Validate consumer groups, pending entries, and idempotency |
| Restore Sentinel topology | Test master discovery config, ACLs, and TLS |
| Restore Redis Cluster | Verify complete shards/slots and cross-shard consistency |
| Recover when primary bucket is unavailable | Validate secondary offsite backup copy |

A pipeline reporting `backup_success=1` after upload without ever running a restore drill is **unproven for recovery**.

## 22. Automated backup verification pipeline

A backup pipeline can follow:

```text
TRIGGER
   |
   v
Detect topology and capture policy
   |
   v
Create snapshot / sealed AOF set
   |
   v
Await completion + inspect Redis status
   |
   v
Copy artifacts to staging + compute SHA-256
   |
   v
Upload offsite + verify destination checksums
   |
   v
Write manifest and mark VERIFIED_TRANSFER
   |
   v
Restore drill (on sampling schedule)
   |
   v
Verify Redis load + app business checks
   |
   v
Mark VERIFIED_RESTORE / ALERT on failure
```

### 22.1. Distinguishing backup statuses

| Status | Meaning |
|---|---|
| `CAPTURING` | Redis is creating the copy |
| `CAPTURED` | Artifacts present in staging, upload not yet verified |
| `TRANSFERRED` | Artifacts uploaded to external storage |
| `VERIFIED_TRANSFER` | Checksums, file counts, and destination metadata valid |
| `VERIFIED_RESTORE` | Restore tested and passed smoke/integrity checks |
| `FAILED` | Error occurred; do not use as a default recovery point |
| `SUSPECT` | Consistency or data age could not be proven |

Never wipe failure records from prior backups when retrying. Give each run a unique `runId` for traceability.

### 22.2. Do not let backup jobs become a cause of data loss

Backup tooling should operate under **least privilege**:

- Does not need `FLUSHALL`/`FLUSHDB` permissions.
- Must not alter Redis config arbitrarily without guaranteed cleanup.
- Must never overwrite production Redis during "restore tests".
- Must never log plaintext credentials.
- Upload credentials should not necessarily hold permission to delete all history.

When backups fail, systems should **alert and preserve the last known good backup**, never attempting to "repair" live AOF/RDB files or delete active Redis files.

## 23. Monitoring and alerting

| Metric or alert | Meaning |
|---|---|
| Age of **last verified offsite backup** | Tracks whether RPO is protected |
| `rdb_last_bgsave_status` | Snapshot errors |
| `rdb_last_save_time` | Timestamp of last captured RDB |
| `aof_last_write_status` | AOF write health |
| `aof_rewrite_in_progress` and duration | Prolonged or stuck rewrites |
| Available disk and I/O latency | Risk of full disk or slow snapshots |
| Upload failures / checksum mismatches | Corrupted or incomplete offsite copy |
| Replica lag / role changes | Risk of stale replica backup |
| Cluster slots covered | Detects backup sets missing shards or broken topology |
| Restore drill elapsed time | Measures real RTO |
| Business verification failures | Backup loads yet holds invalid business data |
| Encryption/key access failures | Backups cannot be decrypted when needed |

Exact metric names can be defined by your backup pipeline or monitoring stack. Redis `INFO` only reflects live server state; it has no idea whether backups were encrypted and uploaded safely to a bucket.

### 23.1. A meaningful RPO alert rule

Example:

```text
Target RPO: 30 minutes
Now: 04:00 UTC
Latest VERIFIED_TRANSFER snapshot completed: 02:45 UTC
Age: 75 minutes
=> Target RPO is currently unprotected
```

If a snapshot at 03:50 only sits on the same disk as Redis and has not uploaded offsite, it **cannot** be counted as protecting recovery if that host/disk fails completely.

## 24. Common failures and diagnostics

| Symptom | Causes to check | Remediation |
|---|---|---|
| `dump.rdb` exists yet lacks recent data | Old snapshot, `BGSAVE` failing | Inspect `LASTSAVE` and `INFO persistence` |
| Backup job reports OK right after `BGSAVE` | Didn't wait for background snapshot completion | Certify only after status/timestamp confirmation |
| RDB checksum matches yet Redis fails to load | Incompatible file format/module/version | Run restore tests and inspect startup logs |
| Restored RDB yet data looks unchanged | Redis loaded enabled AOF instead | Use a clean restore instance, check startup precedence |
| Restored sessions missing en masse | TTL expired while backup was stored | Account for absolute expiration and session design |
| Redis 7+ AOF backup missing files | Copied only one `.aof` or omitted manifest | Copy complete matching base/increment/manifest set |
| Inconsistent AOF backup | Copied mid-`BGREWRITEAOF` | Pause rewrites during copy or use supported `BACKUP` commands |
| Uploaded file cannot be downloaded | Broken ACLs/bucket/KMS/lifecycle rules | Run restore drills in backup account/DR region |
| All replicas lost the same data | Accidental delete replicated | Restore from independent historical backup |
| Replica backup has fewer records than master | Replication lag | Record role/offset/lag, verify against RPO |
| Cluster restore missing many keys | Backed up only one shard or wrong slot map | Maintain full per-master/shard manifests and Cluster restore drills |
| Cross-shard dataset inconsistent | Nodes snapshotted at different times | Quiescence/app reconciliation or synchronized snapshots |
| Spring fails to deserialize values | Serializer/schema/class/module changed | Deploy compatible build/schema or run migration |
| Redis Streams re-runs already processed tasks | Old backup holds older pending/cursor state | Idempotency, outbox/reconciliation |
| `DBSIZE` mismatch | Expiration or different snapshot times | Compare sample keys and TTL policies, not raw counts alone |
| Restore exceeds SLA | Long AOF replay, huge dataset, slow disk | Drill regularly, consider RDB + AOF and faster infra |
| Backups deleted right after creation | Over-aggressive lifecycle or broad delete permissions | Enable versioning/immutability and monitor retention |

## 25. Integrated lab exercises

These exercises require a test Redis with a dedicated data directory and must never disrupt production.

### Exercise 1 — Capturing and restoring RDB

1. Start a test Redis with RDB persistence enabled.
2. Write a String, a Hash, a Set, and a key with a TTL.
3. Write canary `backup:canary:lab1`.
4. Run `BGSAVE`, wait for `rdb_last_bgsave_status:ok` and `LASTSAVE` to advance.
5. Copy `dump.rdb` to a staging folder and compute SHA-256.
6. Start another Redis instance on a separate port and load the RDB.
7. Verify keys, values, types, TTLs, canary, and restore duration.

### Exercise 2 — Safely backing up Redis 7+ AOF

1. Enable AOF on a test Redis with a separate data directory.
2. Check `CONFIG GET appenddirname` and `INFO persistence`.
3. Identify active base, incremental, and manifest files.
4. Temporarily pause auto-rewrites per procedure and wait for rewrites to go idle.
5. Back up **the entire AOF file set** and restore the config setting.
6. Restore onto a test instance using that exact AOF set, checking load logs and data.
7. Remove one manifest-referenced file **in the lab copy** and confirm your verification pipeline rejects it as invalid.

### Exercise 3 — TTL after an older backup

1. `SET lab:ttl value EX 10`.
2. Capture an RDB immediately after writing.
3. Wait more than 10 seconds.
4. Restore the RDB into an isolated instance.
5. Run `GET lab:ttl` and `TTL lab:ttl`; explain why the key may be gone despite an intact snapshot.

### Exercise 4 — Redis Streams and idempotency

1. Create a test Stream and consumer group.
2. Read one message into the PEL without ACKing.
3. Take an RDB snapshot, then process and ACK the message on the original instance.
4. Restore the snapshot onto a test instance.
5. Inspect the PEL and discuss why external database side effects may already have committed.
6. Design `eventId`/idempotency to handle redelivery safely.

### Exercise 5 — Redis Cluster backup set

1. On a multi-master test Cluster, run `CLUSTER SHARDS`.
2. Write keys with hash tags mapping to slots owned by different masters.
3. List per-shard artifacts separately.
4. Write a manifest capturing slot ranges, nodes, roles, timestamps, and checksums.
5. Verify the backup covers all 16,384 slots per capture-time topology.
6. Practice restoring per your environment's Cluster procedure and verify keys across all masters.

### Exercise 6 — Measuring RTO

1. Start a timer when simulating an outage notification.
2. Select backup, download files, create restore instance, and load data.
3. Boot Spring Boot with the restore profile.
4. Verify health, canary, basic Redis commands, and sample business flows.
5. Record per-step timings, the slowest bottleneck, and actual end-to-end RTO.

### Exercise 7 — Detecting bad data despite a valid checksum

1. Create a backup snapshot **after** intentionally changing a test value from valid to invalid.
2. Copy and verify SHA-256: the copy is transfer-valid.
3. Restore and run your business verifier: it must detect the invalid value.
4. Explain why checksums do not replace application-level validation.

## 26. Pre-deployment runbook checklist

**Data architecture**

1. Are Redis keys classified into rebuildable cache vs. authoritative data?
2. Are business-approved RPO/RTO targets defined for each dataset?
3. Are RDB/AOF and fsync/save policies chosen around an explicit failure model?
4. If Redis holds Streams, are idempotency and consumer-group recovery in place?

**Backup pipeline**

5. Do RDB backups wait for `BGSAVE` completion and verify `LASTSAVE`?
6. Do Redis 7+ AOF backups capture full base/increment/manifest sets without rewrite races?
7. Are manifests and SHA-256 checksums recorded for every file and shard?
8. Are backups encrypted, uploaded offsite, and retained across multiple versions?
9. Do alerts fire when the last verified offsite backup ages beyond target?
10. Are permissions and backup deletion strictly controlled?

**Restore**

11. Is an isolated staging instance available for restores without overwriting production?
12. Is it verified whether RDB or AOF takes precedence on startup per configuration?
13. Are matching Redis versions, modules, ACL/TLS, serializers, and app builds prepared?
14. Are TTLs, key types, canaries, Stream groups, and business data verified?
15. For Sentinel/Cluster, do runbooks rebuild topology and cover all shards?
16. Have failovers, missing files, stale backups, and checksum failures been rehearsed?
17. Is real RTO measured up to **usable application state**, not merely Redis `PING`?
18. Are owners, drill schedules, and completion evidence documented?

## 27. Conclusion

Effective Redis backup design goes far beyond enabling `save` or `appendonly yes`. **Persistence** helps Redis restart after certain local faults; **replication** improves availability; **multi-version backups stored outside the operational domain** enable recovery from accidental deletions, corruption, or total infrastructure loss; and **restore drills** actually prove backups work.

For RDB, verify snapshot completion before copying, record timestamps/checksums, and retain historical points. For AOF—especially Redis 7+—manage **the entire consistent base/increment/manifest set** without rewrite races. Redis 8.10+ adds the `BACKUP` command suite, whose support must be verified against your server version. With Sentinel, track replication lag and role changes; with Cluster, back up **every shard** and never assume a global atomic snapshot.

Finally, **checksums only verify byte integrity**, whereas a successful restore combined with business-level verification proves true recoverability. Design RPO/RTO, protect copies offsite, validate TTLs/Streams/serializers, and rehearse restores from arbitrary older backups before claiming the system has disaster recovery.

## References

- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/): RDB/AOF, Redis 7+ multi-part AOF, backup/restore procedures, and new Redis BACKUP commands.
- [Redis — BGSAVE](https://redis.io/docs/latest/commands/bgsave/): asynchronous snapshotting and behavior during background operations.
- [Redis — LASTSAVE](https://redis.io/docs/latest/commands/lastsave/): checking latest completed RDB snapshot timestamp.
- [Redis — INFO](https://redis.io/docs/latest/commands/info/): persistence/replication/role and operational metrics.
- [Redis — CONFIG GET](https://redis.io/docs/latest/commands/config-get/): reading active server configuration.
- [Redis — AOF rewrite](https://redis.io/docs/latest/commands/bgrewriteaof/): AOF compaction process.
- [Redis — Backup START](https://redis.io/docs/latest/commands/backup-start/): online backup workflow in supporting versions.
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/): asynchronous replication and limitations.
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/): failover, master discovery, and topology.
- [Redis — Cluster scaling](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/): shards, slots, failover, and Cluster operations.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): key expiration states.
- [Redis — Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/): Stream structures and consumer groups.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): accessing and verifying data with Spring Data Redis.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): mappings/indexes/TTLs when using Repositories.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): Stream operations and consumer group state.
