# Full-Page Writes, Checksums, and Integrity Protection in PostgreSQL

PostgreSQL stores data in pages (blocks) on disk and uses **Write-Ahead Logging (WAL)** to ensure recoverability after failures. However, writing a page from shared buffers to storage is not necessarily an atomic operation. If the server loses power mid-write, a page may be only partially written: the first half holds new contents while the rest still holds old contents. This phenomenon is a **torn page write**.

PostgreSQL provides two critical mechanisms to protect data page integrity:

- **Full-page writes (FPW):** writes a full image of a page to WAL the first time that page is modified after a checkpoint. If the on-disk page is partially written during a crash, recovery can pull the full-page image (FPI) from WAL to restore the page before replaying subsequent changes.
- **Data checksums:** stores a checksum inside each data page and verifies it whenever the page is read. This detects various forms of page corruption, including errors arising outside normal crash recovery.

The two mechanisms complement each other, but do not replace one another. **Full-page writes help recover a page after a torn write; checksums help detect altered or corrupted page bytes.** A checksum cannot repair a page on its own, and an FPI is not a tool for detecting long-term corruption.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain pages/blocks, shared buffers, dirty pages, and write-back to storage.
2. Describe torn page writes and why row-level WAL changes alone may be insufficient.
3. Explain the write-ahead rule and checkpoints in the crash recovery cycle.
4. Distinguish between checkpoint, WAL flush, data page flush, and commit acknowledgement.
5. Describe full-page images (FPIs) and when PostgreSQL writes an FPI.
6. Explain why an FPI is typically needed only on the first modification of each page after a checkpoint.
7. Inspect and configure `full_page_writes`, `wal_log_hints`, and `wal_compression`.
8. Understand the trade-offs among checkpoint frequency, WAL volume, CPU, I/O, and crash recovery time.
9. Distinguish data page checksums from WAL record CRCs.
10. Check checksum status via `SHOW data_checksums`.
11. Understand how to enable checksums using `initdb --data-checksums` or the `pg_checksums` utility.
12. Know that `pg_checksums` requires a clean cluster shutdown and operates cluster-wide.
13. Understand the protection scope and limitations of checksums.
14. Distinguish corruption detection, recovery via WAL/FPI, and restoring from backups.
15. Read checksum errors, page corruption, and WAL CRC errors in logs.
16. Design verification workflows for backups, standbys, storage, and hardware error monitoring.

## 2. Pages and the Data Path

### 2.1. PostgreSQL Stores Data in Pages

PostgreSQL organizes heap tables and indexes into fixed-size pages determined at build time, typically 8 KB. Each relation is stored as one or more segment files; each segment contains many blocks/pages.

A heap page contains:

- Page header;
- Line pointers (item identifiers);
- Tuple data;
- Free space between line pointers and tuple data;
- Related metadata.

Pages are read and written through the buffer manager; queries do not need direct filesystem access for each row.

### 2.2. Shared Buffers

PostgreSQL maintains a page cache in **shared buffers**. When a backend reads a row, the corresponding page can be loaded into shared buffers. When UPDATE/INSERT/DELETE modifies a page, the buffer becomes a **dirty page**.

A dirty page is a page in memory that has changed relative to its on-disk copy. It must be written out to storage at an appropriate time, such as by the background writer, checkpointer, or a backend process in certain situations.

### 2.3. WAL and Data Files Are Two Separate Write Streams

A transaction modifying a page typically creates WAL records describing the change. PostgreSQL must ensure the associated WAL is durably written before the data page holding that change is considered safe to write to data files.

~~~text
SQL UPDATE
   |
   v
Backend modifies page in shared buffers
   |
   +----> Creates WAL record in WAL buffers
   |             |
   |             v
   |        WAL file is flushed as required
   |
   v
Dirty data page is written to data file later
~~~

This is the **write-ahead logging** principle: WAL must come before the data page. If the system crashes, PostgreSQL can replay WAL to bring data files back to a consistent state.

### 2.4. Commit Does Not Require Flushing Every Data Page to Disk

Under normal durability settings, when a transaction commits, PostgreSQL must flush the WAL commit record per durability requirements. Modified data pages can remain dirty in shared buffers and be written to storage later.

This makes commits faster, since there is no need to wait for all modified data pages of the transaction to be written to disk. Crash recovery uses WAL to replay changes missing from data files.

### 2.5. WAL Flush vs. Data Page Flush

The two operations carry distinct meanings:

| Operation | Meaning |
| --- | --- |
| WAL flush | Pushes required WAL records to storage per the durability contract |
| Data page flush | Writes modified pages from shared buffers to relation files |
| Checkpoint | Establishes a recovery starting point and drives writing dirty pages per checkpoint procedure |
| Crash recovery | Replays WAL from a checkpoint to restore a consistent state |

**Flushed WAL does not mean all data pages have been flushed.** This is a core part of PostgreSQL's design.

## 3. What Is a Torn Page Write?

### 3.1. A Page Can Be Partially Written

Suppose a page is 8 KB. The storage stack may execute one page write as multiple smaller operations depending on filesystem, kernel, controller, device, and alignment. If power is lost or the kernel crashes between operations, the page on disk can end up mixing old and new contents.

~~~text
Page in shared buffers:
+----------------------------------+
|            NEW PAGE              |
+----------------------------------+

Page on disk after a torn write:
+----------------------------------+
|       NEW       |      OLD       |
+----------------------------------+
~~~

This is a conceptual illustration. A torn write can take many shapes and does not necessarily split a page cleanly in half.

### 3.2. Why Can a WAL Delta Be Insufficient?

Suppose WAL stores only a small delta: "change tuple X's status from pending to paid." On disk, the portion holding the tuple header or line pointer may have been partially overwritten. When recovery replays the delta, the underlying page structure may no longer be valid or match the state the WAL record expects.

A WAL record describing a small delta does not necessarily contain enough bytes to rebuild an entire torn page.

### 3.3. Crash Scenario

~~~text
T0: Page P has contents A on disk
T1: Transaction modifies P to B in memory
T2: WAL record for the change is written
T3: Checkpointer/background writer starts writing P
T4: Power loss occurs mid-page write
T5: Disk holds page P mixing bytes from A and B
T6: PostgreSQL starts up and replays WAL
~~~

Without full-page image protection, recovery may lack enough information to repair a partially written page.

### 3.4. Sector Atomicity Does Not Equal PostgreSQL Page Atomicity

A storage device may guarantee atomic writes at a particular sector size, yet a PostgreSQL page is usually larger than a sector. Even when a device has atomicity for a smaller unit, that does not automatically make an entire 8 KB page write atomic.

Do not assume:

- "Modern SSDs don't have torn writes";
- "A RAID controller with a battery cache always makes pages atomic";
- "Filesystem journaling protects the entire contents of PostgreSQL pages";
- "Because WAL exists, full_page_writes isn't needed."

Guarantees depend on the exact storage stack. PostgreSQL defaults to conservative protection.

### 3.5. Torn Page vs. Silent Corruption

Torn pages typically stem from partial writes during a crash or power loss. Silent corruption can come from:

- Faulty RAM;
- Controller/firmware bugs;
- Media degradation over time;
- Firmware writing incorrect bytes;
- Storage/network layers returning wrong data;
- Software bugs corrupting pages.

Full-page writes focus on recovering from torn writes. Data checksums detect many cases of corrupted pages on read, even outside a recent crash.

## 4. WAL and Checkpoints

### 4.1. WAL Record

WAL (Write-Ahead Log) is a sequence of records describing the changes needed to replay database state. WAL is organized by segment files and Log Sequence Numbers (LSNs).

An LSN is an increasing position in the WAL stream, usually displayed as `HEX/HEX`, e.g. `0/16B6C50`. It helps locate records and page states in WAL.

### 4.2. Page LSN

A data page has an LSN field in its page header indicating the WAL position associated with the most recent update to that page. During recovery, PostgreSQL uses this LSN and redo rules to decide which records need to be replayed.

A page LSN is not a checksum and does not automatically detect all corruption. It is metadata for recovery/redo.

### 4.3. What Is a Checkpoint?

A checkpoint establishes a point in WAL from which PostgreSQL can begin crash recovery. The checkpoint process:

1. Determines the redo point;
2. Writes required dirty buffers to data files per procedure;
3. Ensures required WAL has been flushed prior to corresponding data pages;
4. Writes the checkpoint record and updates control information;
5. Enables recovery to start from the latest valid checkpoint.

A checkpoint **is not a backup** and does not produce a complete, independently restorable database copy.

### 4.4. Redo Point

The redo point is the WAL position from which recovery may need to replay. On startup after a crash, PostgreSQL reads checkpoint metadata, finds the redo start, and applies subsequent WAL records.

### 4.5. Checkpoints Too Frequent

Checkpoints flush dirty pages. If they happen too frequently:

- Many data pages must be written to disk repeatedly;
- Storage write load can rise;
- After each checkpoint, many pages experience a new "first modification" requiring an FPI;
- WAL volume can grow due to full-page images;
- I/O bursts can degrade latency.

### 4.6. Checkpoints Too Infrequent

Less frequent checkpoints can reduce FPI frequency and write bursts, but:

- Crash recovery may need to replay a larger amount of WAL;
- Dirty pages stay in memory longer before checkpointing;
- WAL retention and storage needs can grow;
- Recovery duration must be verified against SLAs.

### 4.7. Checkpoint Timeout and max_wal_size

~~~sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW min_wal_size;
SHOW checkpoint_completion_target;
~~~

- `checkpoint_timeout`: maximum configured time between automatic checkpoints.
- `max_wal_size`: soft WAL volume threshold that can trigger earlier checkpoints; not an absolute hard limit.
- `min_wal_size`: minimum WAL volume kept/reused by segment management.
- `checkpoint_completion_target`: target for spreading checkpoint write work across the interval between checkpoints.

Defaults vary by major version and workload. Do not apply numbers from a blog post without measuring your own system.

### 4.8. Manual CHECKPOINT

~~~sql
CHECKPOINT;
~~~

This command requests an immediate checkpoint. It can generate significant I/O and shifts when pages require FPIs in the next cycle. Do not run CHECKPOINT repeatedly as a way to "flush the database clean" in production.

## 5. Full-Page Writes (FPW)

### 5.1. Core Mechanism

When `full_page_writes` is enabled, PostgreSQL writes the **entire contents of a page** into WAL the first time that page is modified after a checkpoint.

Example:

~~~text
Checkpoint C1
   |
   v
Page P modified for the first time
   |
   +--> WAL contains full-page image of P
   |
Page P modified a second, third time...
   |
   +--> WAL writes normal changes (no repeated FPI needed for P)
   |
Checkpoint C2
   |
   v
Next modification of P can emit a new FPI
~~~

### 5.2. Why Is an FPI Only Needed the First Time After a Checkpoint?

Crash recovery starts from a valid checkpoint. If page P is partially written after a checkpoint, the first FPI in WAL can restore page P to an intact state before subsequent WAL records are replayed.

Once the FPI is in WAL, later modifications can be recovered using the corresponding redo records. A new checkpoint starts a new cycle where the next first modification of the page requires an FPI again.

### 5.3. What Does an FPI Contain?

An FPI is a complete image of the page at the moment it is logged to WAL. It includes the page contents needed to restore the page, not just a small row delta. During replay, PostgreSQL can overwrite the damaged/torn page with the image and then continue redoing.

An FPI can be compressed inside WAL if `wal_compression` is enabled with a supported compression method.

### 5.4. Default full_page_writes

~~~sql
SHOW full_page_writes;
~~~

PostgreSQL's default is `on`. This is a critical durability protection setting. Turning it off may speed up normal operation in some cases, yet risks unrecoverable or silent data corruption after a system failure.

### 5.5. Do Not Disable FPW Arbitrarily to Reduce WAL

Disabling `full_page_writes` is not a harmless optimization. If the storage stack does not guarantee atomic page writes, a crash can leave torn pages that WAL deltas cannot fully recover.

Consider changing it only with concrete proof/guarantees of atomic writes across the entire storage stack and explicit risk acceptance on par with other hazardous durability settings. For typical production systems, keep it `on`.

### 5.6. An FPI Is Not a Backup

An FPI is a WAL component supporting crash recovery/redo, not a full backup:

- It is logged only for pages modified under FPW rules;
- It does not capture all relation pages at a single point in time;
- It does not replace a base backup;
- It does not replace WAL archiving/PITR;
- It cannot ensure recovery if the WAL chain or storage is lost.

### 5.7. FPIs and Base Backups

In applicable backup and WAL logging modes, PostgreSQL can emit relevant FPIs to guarantee page consistency while a backup runs. Details depend on the backup API/protocol and version; never build backups by copying live data files outside PostgreSQL's backup procedures.

## 6. wal_log_hints and Hint Bits

### 6.1. What Are Hint Bits?

Tuple headers contain transaction visibility metadata. PostgreSQL can update certain **hint bits** to record that the creating or deleting transaction committed or aborted, making future visibility checks faster.

Hint bits are derivable from transaction status under certain conditions; they are not like an ordinary business UPDATE.

### 6.2. Why Do Hint Bits Relate to Full-Page Writes?

If a page is modified only by a hint-bit update and then written to disk, a torn write could still damage the page. When `wal_log_hints=on`, PostgreSQL writes a full-page image on the first modification after a checkpoint even for otherwise non-critical hint-bit changes.

### 6.3. Configuration

~~~sql
SHOW wal_log_hints;
~~~

`wal_log_hints` defaults to `off` and can only be set at server start (server-start parameter). Enabling it increases WAL logging due to FPIs for hint-bit modifications.

### 6.4. Data Checksums Change the Need for wal_log_hints

When data checksums are enabled, hint-bit updates are WAL-logged as required; `wal_log_hints` is no longer needed for that purpose and is ignored per PostgreSQL documentation. When checksums are off, `wal_log_hints=on` can also be used to test the approximate WAL overhead of enabling data checksums.

### 6.5. pg_rewind

`pg_rewind` needs enough information to synchronize changed pages between two data directories. One prerequisite is that either data checksums are enabled or `wal_log_hints=on` (depending on version/tool requirements). Before planning failover/rewind, read the `pg_rewind` documentation for your running major version and configure it beforehand.

### 6.6. Do Not Confuse wal_log_hints with full_page_writes

| Parameter | Role |
| --- | --- |
| `full_page_writes` | FPI on the first page modification after a checkpoint to protect against torn writes |
| `wal_log_hints` | Adds WAL/FPI logging for hint-bit changes when checksums are disabled |
| Data checksums | Verifies data page integrity on read/verify |

`wal_log_hints=on` is not a reason to turn off `full_page_writes`.

## 7. wal_compression and the Cost of Full-Page Images

### 7.1. Why Do FPIs Increase WAL Volume?

A normal WAL record may contain only info about a small change. An FPI contains nearly an entire page image, usually much larger than a delta record. For workloads modifying many pages right after a checkpoint, WAL volume can climb sharply.

Illustrative example:

| Component | Hypothetical WAL bytes |
| --- | ---: |
| One delta record | 100 bytes |
| One full-page image | 8,192 bytes before compression |

These numbers only illustrate proportions, not exact record sizes. WAL records also include headers, alignment, block references, and other metadata.

### 7.2. wal_compression

~~~sql
SHOW wal_compression;
~~~

`wal_compression` enables compressing full-page images written to WAL. During recovery replay, PostgreSQL decompresses the image before applying it.

### 7.3. Compression Methods

In modern versions, supported methods can include:

- `pglz`;
- `lz4` if PostgreSQL was built with LZ4 support;
- `zstd` if PostgreSQL was built with Zstandard support.

Supported methods and configuration syntax depend on major version and build options. The value `on` is a historical alias for `pglz` in versions that moved to an enum.

### 7.4. Trade-Offs

Compressing FPIs can reduce WAL bytes, network transfer, and archive storage, while spending CPU to compress on WAL write and decompress on replay. The best method depends on:

- How compressible page contents are;
- CPU headroom;
- WAL generation rate;
- Network/archive throughput;
- Recovery time objective;
- Whether the compression method is supported by the build.

### 7.5. Not All WAL Is Compressed

`wal_compression` primarily compresses full-page images. It is not general compression for all WAL records, nor does it compress data files.

### 7.6. Measure Instead of Guessing

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    stats_reset
FROM pg_stat_wal;
~~~

`wal_fpi` counts full-page images and `wal_bytes` is cumulative WAL bytes per cluster statistics. Counters reset on statistics reset. Record baselines before and after changes across comparable workload windows.

### 7.7. FPI Ratio

~~~sql
SELECT
    wal_records,
    wal_fpi,
    round(
        100.0 * wal_fpi / NULLIF(wal_records, 0),
        2
    ) AS fpi_per_100_records,
    pg_size_pretty(wal_bytes) AS wal_written
FROM pg_stat_wal;
~~~

This is the ratio of FPI count to WAL record count, not byte share. One FPI can be far larger than a delta record; do not use this ratio in place of analyzing `wal_bytes`.

## 8. How Do Data Checksums Protect Pages?

### 8.1. Checksums on Data Pages

When checksums are enabled, each data page carries a checksum computed when the page is written and verified when the page is read. PostgreSQL can detect when page bytes no longer match the stored checksum.

The checksum incorporates the page/block number, helping detect cases where a page was misplaced or its contents no longer match. This is an integrity check, not an encryption mechanism.

### 8.2. What Can Checksums Detect?

Examples:

- Certain media/storage errors altering bytes;
- Pages partially written or damaged after being written;
- Controllers/firmware returning wrong data;
- Certain transmission or read/write errors causing page contents to mismatch the checksum.

A checksum does not pinpoint which hardware device or software layer caused the corruption. It reports that the page failed verification.

### 8.3. Checksums Do Not Repair Data

On a checksum mismatch, PostgreSQL flags the bad page and typically raises an error on read. It **cannot reconstruct the correct bytes from the checksum alone**. Recovery from WAL/FPI if possible, restoring from backup, or a formal data recovery procedure is required.

### 8.4. Scope of Protection

Data checksums protect **data pages**. They do not cover every file or byte in the data directory. Per PostgreSQL documentation:

- Relation data pages are checksummed;
- Internal data structures such as certain transaction status/state files are not directly protected by data page checksums;
- Temporary files used for sorting, materialization, or intermediate query data are not checksummed by this mechanism;
- Other structures may have their own WAL/CRC mechanisms.

Thus, enabling checksums does not mean "every file on the server is checksummed."

### 8.5. Checksums Are Not Cryptographic Hashes

Data page checksums are designed to detect accidental data corruption, not defend against an attacker deliberately modifying pages. They do not replace HMACs, digital signatures, encryption, or access controls.

### 8.6. Miss Probability

Checksums have finite bit width. Certain error combinations can collide and go undetected. Therefore, checksums reduce silent corruption risk, but cannot guarantee every possible corruption is caught.

### 8.7. Overhead

Computing checksums on write and checking them on read consumes CPU. Performance impact is usually small, though it varies by workload and hardware. Starting in PostgreSQL 18, data checksums are enabled by default at initdb unless explicitly disabled.

## 9. Data Page Checksums vs. WAL CRCs

PostgreSQL protects multiple data layers using different mechanisms.

### 9.1. WAL Record CRC-32C

Every WAL record is protected by a 32-bit CRC-32C. PostgreSQL computes the CRC when writing the WAL record and checks it during crash recovery, archive recovery, and replication reads.

If a WAL record is corrupted, the CRC detects that the record contents are no longer valid.

### 9.2. Data Page Checksums

Data page checksums protect page contents when pages are written and read. It is a separate mechanism from WAL record CRCs.

### 9.3. Full-Page Images Are Also Protected in WAL

Full-page images are stored inside WAL records, and the WAL record CRC protects the record carrying the image. Thus an FPI in WAL is not an unchecked blob.

### 9.4. Comparison Table

| Mechanism | Target | Goal | Self-Repairs Data? |
| --- | --- | --- | --- |
| Full-page write / FPI | Data page image in WAL | Recover torn pages during crash recovery | Can restore page if WAL is intact and valid |
| Data page checksum | Data pages | Detect page corruption on read/verify | No |
| WAL CRC-32C | WAL records | Detect WAL record corruption | No |
| Backup manifest checksums | Backup files | Verify backup files match manifest | No |

### 9.5. Why Are Multiple Layers Needed?

A page may be partially written during a crash; FPIs enable recovery. A page may silently degrade days later due to media issues; checksums detect it on read or verification scan. A WAL segment may suffer corruption in storage or transit; WAL CRCs detect record corruption.

No single mechanism covers every failure mode.

## 10. Enabling Data Checksums at Cluster Creation

### 10.1. initdb --data-checksums

When creating a new cluster, you can specify:

~~~bash
initdb -D /var/lib/postgresql/data --data-checksums
~~~

This option enables checksums for data pages cluster-wide.

### 10.2. Defaults by Major Version

Note this important difference:

| PostgreSQL version | Default data checksums at initdb |
| --- | --- |
| PostgreSQL 17 and earlier majors | Off by default; enable with `--data-checksums` |
| PostgreSQL 18 and later | On by default; use `--no-data-checksums` to disable |

Because the default changed in PostgreSQL 18, **never guess a cluster's state from version alone**. Check directly:

~~~sql
SHOW data_checksums;
~~~

### 10.3. initdb --no-data-checksums

On versions where checksums default to on, you can disable them at initialization:

~~~bash
initdb -D /var/lib/postgresql/data --no-data-checksums
~~~

Use this only with a clear operational rationale and understanding of the trade-off. For new production deployments, checksums provide a valuable layer of protection.

### 10.4. Cannot Enable Checksums per Database or Table

Data checksums are a **cluster-wide** setting. You cannot enable them individually for database A, schema B, or table C within the same cluster.

### 10.5. Cannot Be Set in postgresql.conf

`data_checksums` is read-only state, not a GUC you can toggle via:

~~~conf
data_checksums = on
~~~

Changing checksum state on an existing cluster requires the offline `pg_checksums` tool and a clean server shutdown.

## 11. Checking Checksum Status

### 11.1. SHOW data_checksums

~~~sql
SHOW data_checksums;
~~~

Output:

- `on`: the cluster has data page checksums enabled;
- `off`: the cluster does not have them enabled.

This is the quickest way to inspect the current state from SQL.

### 11.2. Checking via pg_controldata

~~~bash
pg_controldata -D /var/lib/postgresql/data
~~~

The output includes a checksum version field (e.g., `Data page checksum version`). Exact values and display depend on major version. `pg_controldata` is useful when inspecting an offline cluster or from a host with read access to the data directory.

### 11.3. pg_checksums --check

With the cluster cleanly shut down:

~~~bash
pg_checksums --check -D /var/lib/postgresql/data --progress
~~~

This scans eligible files/blocks across the cluster to verify checksums. Exit status:

- `0`: no checksum errors detected;
- non-`0`: at least one checksum failure occurred or the check failed.

Distinguish checksum mismatches from command/permission/path errors; read stdout and stderr in full.

### 11.4. The Server Must Be Cleanly Shut Down

`pg_checksums` does not run against a live cluster. The server must be cleanly shut down before checking, enabling, or disabling. Never run it concurrently with the PostgreSQL server or any other process writing to the data directory.

### 11.5. Checksum Scanning Is Heavy I/O

On multi-terabyte clusters, `pg_checksums --check` must read a large volume of relation files. Plan for duration, storage throughput, and maintenance windows. Checking on a replica or copy can help if your workflow and consistency requirements allow.

### 11.6. pg_checksums --filenode

Some versions offer an option to check a specific relation by filenode:

~~~bash
pg_checksums --check --filenode=12345 -D /var/lib/postgresql/data
~~~

A filenode is a physical relation identifier that can change after a rewrite, REINDEX, or DDL. Do not store an old filenode and reuse it long-term like a table name. Run `pg_checksums --help` for your version to confirm supported flags.

### 11.7. Tool Name Across Versions

Older PostgreSQL versions named this utility `pg_verify_checksums`. Current versions use `pg_checksums`. Always use the binary from the matching major version and verify via:

~~~bash
pg_checksums --version
pg_checksums --help
~~~

## 12. Enabling or Disabling Checksums on an Existing Cluster

### 12.1. pg_checksums --enable

If an existing cluster does not have checksums enabled, you can enable them offline:

~~~bash
pg_checksums --enable -D /var/lib/postgresql/data --progress
~~~

During enabling, the tool computes checksums and rewrites all applicable relation file blocks. On large clusters, this operation can take considerable time and generate heavy I/O.

### 12.2. Safe Procedure

1. Verify the exact data directory and binary major version.
2. Verify the latest backup and its restorability.
3. Schedule a maintenance window and announce downtime.
4. Shut down PostgreSQL **cleanly**.
5. Ensure no other process is writing to the data directory, tablespaces, or WAL directory.
6. Run `pg_checksums --enable` with the matching version binary.
7. Wait for the command to finish and sync data to storage.
8. Start the server.
9. Confirm `SHOW data_checksums;` returns `on`.
10. Monitor logs, checksum statistics, and replication health.

### 12.3. Do Not Use --no-sync in Production

By default, `pg_checksums` waits for files to be safely synced to disk. The `--no-sync` option skips waiting for sync, running faster at the risk of leaving the cluster corrupt if the OS crashes afterward. It is meant primarily for testing; never use it in production.

### 12.4. Disabling Checksums

Technically possible via:

~~~bash
pg_checksums --disable -D /var/lib/postgresql/data
~~~

However, disabling checksums removes page corruption detection. Never disable them as a workaround for checksum errors or to chase performance without risk assessment and operational approval.

### 12.5. Cluster-Wide Operation

Checksum state applies to the entire cluster, not one database. Every database, shared relation, and associated tablespace is covered by the operation.

### 12.6. Replication Topology

With a primary/standby setup or tools like `pg_rewind` that copy relation blocks directly, mismatched checksum states across nodes can produce pages with incompatible checksum versions.

Per PostgreSQL documentation, when changing checksum state in a replication setup, shut down all clusters and convert them together; another safe option is removing standbys, converting the primary, and rebuilding standbys from scratch. In practice, follow your product or managed service runbook.

### 12.7. If pg_checksums Is Interrupted Mid-Run

PostgreSQL documentation notes that if the tool is aborted or killed while enabling/disabling, the cluster's checksum configuration remains in its original state and the command can be re-run to perform the same operation. Even so, never intentionally kill the process. Read the exit status/logs, keep the cluster offline, and follow version documentation.

### 12.8. Never Run a Different Version's Binary Against PGDATA

Always use `pg_checksums` from the matching major version installation. Never run a PostgreSQL 18 binary against a PostgreSQL 16 data directory or vice versa.

## 13. Monitoring Checksum Failures

### 13.1. pg_stat_database

On supported versions, `pg_stat_database` includes:

- `checksum_failures`: number of data page checksum failures detected;
- `checksum_last_failure`: timestamp of the most recent detection.

~~~sql
SELECT
    datname,
    checksum_failures,
    checksum_last_failure,
    stats_reset
FROM pg_stat_database
ORDER BY checksum_failures DESC NULLS LAST;
~~~

If checksums are off, related columns may be NULL. These are cumulative counters since the last statistics reset; take snapshots and compare over time.

### 13.2. Checksum Failures Do Not Equal Distinct Corrupt Pages

A single corrupt page can be read repeatedly, incrementing the failure counter each time it is detected. Each increment does not necessarily correspond to a distinct physical page.

### 13.3. Inspecting Current Configuration

~~~sql
SELECT
    current_setting('data_checksums') AS data_checksums,
    current_setting('full_page_writes') AS full_page_writes,
    current_setting('wal_log_hints') AS wal_log_hints,
    current_setting('wal_compression') AS wal_compression,
    current_setting('fsync') AS fsync;
~~~

These are the settings visible in the current session; some parameters can only be changed at server configuration/startup. On managed services, cross-check effective settings and modification permissions.

### 13.4. Monitoring WAL/FPI

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

This view provides WAL records, full-page images, WAL bytes, and write/sync counters. Columns vary by version; consult documentation for your major version and compare across equal time windows.

### 13.5. Monitoring Checkpoints

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

On major versions providing this view, inspect timed/requested checkpoints, buffers written, and write/sync times. On older versions, checkpoint counters reside in `pg_stat_bgwriter`. Inspect catalog views on your actual server.

### 13.6. Logging Checkpoints

~~~sql
SHOW log_checkpoints;
~~~

With appropriate logging enabled, checkpoint logs show checkpoint triggers, buffers written, and durations. Use logs to catch overly frequent checkpoints or abnormal I/O.

### 13.7. Checksum Error Logs

When PostgreSQL detects a checksum mismatch, logs typically include the database, relation/block, or expected vs. calculated checksum depending on context and version. Record:

- Timestamp and server/node;
- Database, relation, and block if provided;
- Expected checksum and calculated checksum;
- Query/session that read the page;
- Storage, OS, kernel, and controller logs from the same time;
- Replication and backup state.

Never just wipe logs or reset counters after detecting an error.

## 14. Distinguishing Checksum Errors, WAL CRCs, and Page Structure Errors

### 14.1. Data Page Checksum Failure

A page is read, and its recomputed checksum does not match the checksum stored in the page. This indicates page contents were altered or corrupted.

### 14.2. WAL CRC Failure

A WAL record fails CRC-32C validation during recovery, replication, or archive processing. This is corruption in the WAL stream, distinct from a data page checksum failure.

### 14.3. Invalid Page Header

PostgreSQL may report an invalid page header, page size/version mismatch, or structurally invalid page. This does not always produce the same message as a checksum mismatch; a page header can be too damaged for normal checksum verification to run.

### 14.4. OS/Storage Errors

Messages reporting I/O errors, read failures, write failures, device resets, or filesystem errors can point to the root cause. PostgreSQL logs alone usually cannot pinpoint the exact failing hardware component.

### 14.5. Classification Table

| Symptom | Layer Potentially Affected | First Step |
| --- | --- | --- |
| Data page checksum mismatch | Relation data page / storage | Record relation/block, preserve data, investigate storage |
| WAL CRC mismatch | WAL record / segment / archive | Protect WAL chain, inspect archive/replication/storage |
| Invalid page header | Data page structure | Identify page, avoid overwriting, prepare restore plan |
| OS I/O error | Kernel / filesystem / device / controller | Check system logs, device health, and storage path |
| Backup manifest checksum mismatch | Backup artifact / transfer / storage | Quarantine backup, verify source/destination and alternate backups |

## 15. ignore_checksum_failure and Handling Corrupt Pages

### 15.1. Default Behavior Is Raising an Error

When a data checksum mismatch occurs during a read, PostgreSQL normally raises an error and aborts the active transaction. This is protective behavior: applications should not keep processing data the server has flagged as untrustworthy.

### 15.2. ignore_checksum_failure

~~~sql
SHOW ignore_checksum_failure;
~~~

This parameter defaults to `off`. When enabled, PostgreSQL may ignore checksum failures after still emitting a warning and proceed in certain cases if the page header remains valid enough.

### 15.3. This Is Not a Repair Tool

> Enabling `ignore_checksum_failure` can lead to crashes, propagation or masking of corruption, and severe consequences. It is useful only in emergencies to attempt reading intact tuples from a damaged page when you understand the risks and are executing recovery.

Never leave it enabled permanently, never use it to make monitoring "green," and never treat data read under it as trustworthy.

### 15.4. zero_damaged_pages

PostgreSQL provides a special recovery option `zero_damaged_pages` to bypass certain damaged pages by replacing them with zeroed pages. This can wipe out all rows stored on those pages. It is a selective salvage measure, not lossless repair.

### 15.5. Initial Response Steps

1. Record the error along with page, relation, and block;
2. Restrict writes that might worsen the state if needed per runbook;
3. Check storage, kernel, filesystem, and hardware logs;
4. Check checksum failure counters, WAL/archive integrity, and standby state;
5. Determine whether the page can be recovered via WAL/FPI during recovery or requires restore;
6. Protect existing backups before attempting destructive operations;
7. Recover on an appropriate copy, standby, or backup and verify results.

### 15.6. Never Manually Edit Bytes in Relation Files

Never use a hex editor, `dd`, custom scripts writing bytes, or copy a page from another node into a live relation file. Page formats carry metadata, LSNs, and visibility state tied to transaction history. Direct writes can destroy data or render the cluster unrecoverable.

## 16. FPIs in Crash Recovery

### 16.1. Recovery Starts from a Checkpoint

When PostgreSQL starts after a crash, it reads control metadata and the latest valid checkpoint, then replays WAL from the redo point. Records already reflected in data files may be skipped based on page LSN/redo logic; missing changes are replayed.

### 16.2. How FPIs Handle a Partially Written Page

Suppose:

1. Checkpoint C completes;
2. Page P is modified for the first time after C, and WAL logs P's FPI;
3. P is written to disk, resulting in a torn write;
4. The server crashes;
5. Recovery begins from C;
6. PostgreSQL replays WAL and uses the FPI to restore P to an intact page image;
7. Subsequent WAL changes after the FPI are redone in order.

That is how FPIs protect pages from torn writes during crash recovery.

### 16.3. What If the WAL Holding the FPI Is Also Corrupt?

WAL records carry CRC-32C. If the record holding the FPI is corrupted, CRC validation detects the problem. When a required WAL chain or segment is no longer intact, recovery may fail to complete. Inspect WAL archives, base backups, and standbys per your recovery plan.

### 16.4. FPIs Do Not Automatically Repair Post-Recovery Corruption

If a page degrades due to media failure hours after the cluster started and ran normally, PostgreSQL does not automatically rewind from an old checkpoint simply upon hitting a checksum mismatch. You must restore the page or cluster from backups and WAL, or follow a verified recovery procedure.

### 16.5. WAL Must Be Retained Long Enough

Crash recovery uses WAL remaining in the cluster. PITR requires a base backup and a continuous WAL chain from that backup to the target time. FPIs cannot help if required WAL segments were deleted or archive gaps exist.

## 17. Full-Page Writes, fsync, and Durability Settings

### 17.1. full_page_writes Does Not Replace fsync

`full_page_writes` protects pages from torn writes using FPIs. `fsync` asks the OS to synchronize data and WAL to storage per the durability contract.

If `fsync=off`, PostgreSQL cannot guarantee WAL or data was durably persisted before reporting success. FPW cannot compensate for a storage stack that ignores flush requests or loses acknowledged WAL.

### 17.2. Inspecting fsync

~~~sql
SHOW fsync;
SHOW synchronous_commit;
SHOW wal_sync_method;
SHOW full_page_writes;
~~~

For production systems requiring standard durability, keep `fsync` enabled. Never disable it to work around slow I/O without understanding the risk of losing or corrupting the database.

### 17.3. synchronous_commit Differs from full_page_writes

`synchronous_commit` controls when a transaction commit is acknowledged relative to WAL flush (and synchronous replication acknowledgement if configured). Setting `synchronous_commit=off` can lose recently acknowledged transactions on crash, which is a different latency/durability trade-off than disabling FPW.

Do not confuse:

- `synchronous_commit`: durability of commit acknowledgement;
- `fsync`: syncing data to storage;
- `full_page_writes`: FPIs protecting pages against torn writes;
- `data_checksums`: detecting page corruption.

### 17.4. Storage Caches Must Honestly Honor Flushes

PostgreSQL issues sync requests according to `wal_sync_method`/OS. If a controller or drive reports flush success while data still sits in volatile cache, power loss can discard WAL or data considered durable.

Administrators must verify:

- Whether controller write caches have battery/flash-backed protection;
- Whether SSDs/drives honor cache flush and FUA properly;
- Whether the filesystem/storage stack preserves ordering and flush semantics;
- Whether firmware, kernel, and multipath have known bugs;
- Whether cloud/block storage provides an appropriate durability contract.

### 17.5. ECC RAM and Hardware Monitoring

PostgreSQL cannot catch every RAM error before corrupted bytes get written into an otherwise valid-looking page or WAL record. Use ECC RAM or equivalent protection, and monitor machine-check events, SMART/device health, and controller logs.

### 17.6. Full-Page Writes Are Not Anti-Malware

FPW and checksums do not protect against authorized users modifying/deleting data, ransomware, application logic bugs, SQL injection, or accidental deletes. You still need authentication, least privilege, isolated/immutable backups, and disaster recovery.

## 18. Checksums, Backups, and PITR

### 18.1. Base Backups Remain Essential

Data checksums detect bad pages and WAL replays changes, yet if relation files are severely corrupted or required WAL is gone, you still need a valid base backup to recover.

### 18.2. PITR

Point-in-time recovery typically requires:

- A valid base backup;
- Continuous WAL from the backup's required start point to the target recovery time;
- Working archive and restore commands;
- Appropriate recovery target configuration;
- Sufficient storage and capacity for the restore.

FPIs inside WAL make replaying page changes safer during recovery; they do not replace a base backup.

### 18.3. pg_verifybackup

`pg_verifybackup` validates a backup directory against its manifest and verifies supported consistency/WAL details depending on version options. It differs from `pg_checksums`:

- `pg_checksums`: verifies page checksums on an offline cluster;
- `pg_verifybackup`: verifies backup integrity against the backup manifest and supported checks.

Never assume a backup is restorable solely because a checksum scan succeeded. Run **restore tests** regularly.

### 18.4. Backups Should Not Share a Failure Domain

If backups, WAL archives, and the primary sit in the same storage failure domain, a controller/volume failure or accidental deletion can wipe out all of them. Isolate backups per DR architecture with retention, access controls, and restore testing.

### 18.5. Periodic Backup Verification

A verification schedule should include:

1. Confirming backup job completion;
2. Verifying backup manifests and checksums;
3. Checking WAL archive continuity;
4. Restoring into an isolated environment;
5. Confirming the server starts and finishes recovery;
6. Running validation queries and application smoke tests;
7. Recording actual RPO and RTO.

### 18.6. Page Checksums Are Not Backup Checksums

Page checksums live in page headers and verify pages. Backup manifest checksums protect backup files during storage and transfer. The two checksums have different goals and scopes.

## 19. FPIs and Checkpoint Tuning

### 19.1. Increasing Checkpoint Interval Can Reduce FPI Frequency

Because each page normally needs an FPI only on its first modification after a checkpoint, more frequent checkpoints force more pages to log FPIs more often. Raising `checkpoint_timeout` or `max_wal_size` can reduce checkpoint counts and FPI volume in some workloads.

### 19.2. Trade-Off: Crash Recovery Can Take Longer

Less frequent checkpoints can enlarge redo distance. After a crash, PostgreSQL may have to replay more WAL records before becoming fully available.

### 19.3. Checkpoint Completion Target

`checkpoint_completion_target` spreads writing dirty buffers across the checkpoint interval. Its goal is avoiding write bursts, not directly reducing FPI counts on its own.

### 19.4. max_wal_size Is Not a Hard Cap

WAL can exceed `max_wal_size` under high load, archive failures, or replication retention. Do not treat this setting as a hard cap on `pg_wal` disk usage.

### 19.5. WAL Retention and Replication Slots

Replication slots and archiving can retain WAL segments longer than normal checkpoint/recycle policies. Monitor slot lag, archive failures, and disk headroom; never delete WAL files manually.

### 19.6. Measure Checkpoints and FPIs Before Tuning

Record:

- Checkpoint counts over time;
- Timed vs. requested checkpoints;
- `wal_fpi` and `wal_bytes`;
- Checkpoint write/sync times;
- Disk write latency/IOPS;
- Recovery duration in tests;
- Replication/archive throughput.

Change one parameter at a time in staging or a controlled window and compare under equivalent workloads. Never raise `checkpoint_timeout` solely to trim WAL while ignoring recovery SLAs.

### 19.7. Do Not Disable full_page_writes to Fix Checkpoint Pressure

If FPIs inflate WAL, inspect checkpoint intervals, `wal_compression`, storage throughput, and workload first. Disabling FPW strips away torn-page protection and is not a safe default fix.

## 20. Lab: Observing FPIs and WAL in a Test Environment

This lab uses an isolated database/schema and only observes WAL statistics. Never intentionally corrupt relation files, disable fsync, or disable full_page_writes to induce a crash. Simulating torn writes requires specialized storage/fault-injection environments and is inappropriate on hosts holding real data.

### 20.1. Check Initial Configuration

~~~sql
SHOW server_version;
SHOW full_page_writes;
SHOW wal_log_hints;
SHOW wal_compression;
SHOW fsync;
SHOW data_checksums;
~~~

Record the outputs and version. `data_checksums` is read-only; its default depends on major version and how the cluster was initialized.

### 20.2. View Baseline WAL Stats

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
~~~

Save the result with a timestamp. On a shared lab where others run queries, counters include cluster-wide activity.

### 20.3. Create the Lab Table

~~~sql
CREATE SCHEMA copy448;

CREATE TABLE copy448.fpw_demo (
    id integer PRIMARY KEY,
    payload text NOT NULL
);

INSERT INTO copy448.fpw_demo(id, payload)
SELECT g, repeat('x', 100)
FROM generate_series(1, 10000) AS g;
~~~

### 20.4. Run a Checkpoint in the Lab

~~~sql
CHECKPOINT;
~~~

CHECKPOINT requires appropriate privileges and can generate I/O. Run it only in a lab without critical workloads; never call it repeatedly in production to "force" FPIs.

### 20.5. Update Some Rows

~~~sql
UPDATE copy448.fpw_demo
SET payload = payload || '-updated'
WHERE id BETWEEN 1 AND 100;
~~~

The UPDATE modifies heap pages containing the rows. With `full_page_writes=on`, the first modification to each page after the checkpoint can generate an FPI.

### 20.6. Read WAL Stats After the UPDATE

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
~~~

Compare against baseline. `wal_fpi` may rise; the exact increase depends on page layout, checkpoints, indexes, concurrent activity, and WAL record types.

### 20.7. Update the Same Page Region Again

~~~sql
UPDATE copy448.fpw_demo
SET payload = payload || '-again'
WHERE id BETWEEN 1 AND 100;
~~~

Within the same checkpoint cycle, the same pages generally do not need a new FPI per UPDATE. Still, do not expect FPI delta to be zero: other pages may be modified for the first time, and background cluster activity also generates FPIs.

### 20.8. Trigger Another Checkpoint

~~~sql
CHECKPOINT;
~~~

After the checkpoint, the next first modification to each page can generate new FPIs again.

### 20.9. Never Reset Shared Statistics in Production

In a private lab you can reset WAL stats if you have privileges and want a clean measurement:

~~~sql
SELECT pg_stat_reset_shared('wal');
~~~

Never reset shared statistics in production just to make a clean chart. Resetting erases cumulative baselines relied upon by other dashboards and monitors.

### 20.10. Check Data Checksum State

~~~sql
SHOW data_checksums;

SELECT
    datname,
    checksum_failures,
    checksum_last_failure
FROM pg_stat_database;
~~~

When checksums are enabled, there should normally be no failures and `checksum_failures` should be 0. Never fabricate a checksum mismatch by editing relation file bytes.

### 20.11. Offline pg_checksums Lab

On a lab machine with a dedicated PostgreSQL installation and data directory, initialize a cluster without checksums using the syntax for your major version, stop the server cleanly, and run:

~~~bash
pg_checksums --enable -D /path/to/lab-data --progress
pg_checksums --check -D /path/to/lab-data --progress
~~~

After enabling, start the cluster and verify `SHOW data_checksums;` returns `on`. Run only on an **offline lab cluster**; never point it at a running production PGDATA.

### 20.12. Never Simulate Corruption on Real Files

Never use `dd`, a hex editor, or scripts writing random bytes into relation files to test checksums on a live cluster. To test corruption detection, use a disposable cluster, an expendable copy, and a DBA-approved fault-injection procedure.

### 20.13. Clean Up the Lab Schema

~~~sql
DROP SCHEMA copy448 CASCADE;
~~~

Run only if the schema is strictly the test schema and holds no data you need to keep.

## 21. Operational Procedures and Integrity Verification

### 21.1. When Creating a New Cluster

1. Choose a supported major version.
2. Check that version's default data checksum behavior.
3. Enable data checksums per policy (PG18 defaults to on).
4. Keep `full_page_writes=on`.
5. Keep `fsync=on`.
6. Ensure WAL and data sit on storage with honest flush semantics.
7. Design base backups, WAL archiving, and restore tests.
8. Record checksum state and durability settings in inventory.

### 21.2. When Upgrading Major Versions

Do not assume checksum state automatically switches to the new major version's default. An upgraded cluster retains its existing checksum state depending on the upgrade method; verify `SHOW data_checksums` post-upgrade and follow documentation for the upgrade tool used.

### 21.3. When Cloning or Restoring a Cluster

Verify:

- Checksum state of the backup source;
- Whether restore/copy tools preserve exact page bytes and control metadata;
- Whether standbys and the new primary have consistent checksum state;
- `pg_rewind` prerequisites;
- WAL archive and backup manifest integrity;
- `SHOW data_checksums` after startup.

### 21.4. When a Checksum Failure Occurs

- Record the error along with relation and block;
- Never enable `ignore_checksum_failure` permanently;
- Inspect OS, storage, and hardware logs;
- Verify backups, WAL, and standbys;
- Run offline checksum verification on an appropriate copy;
- Choose restore/PITR or salvage per runbook;
- Open an incident with your storage provider if hardware error evidence appears;
- Post-recovery, run verification checks and continue monitoring.

### 21.5. When a WAL CRC Error Occurs

- Preserve the affected WAL segment and logs;
- Check archive copies and replica copies;
- Determine whether corruption occurred on the primary, standby, archive store, or in transit;
- Never delete or rename WAL files to force the server to start;
- Use a valid base backup and intact WAL chain to restore if required.

### 21.6. When Changing full_page_writes or wal_compression

Document:

- Reason for change;
- Current value and target value;
- Version support;
- WAL FPIs and bytes before/after;
- CPU, I/O, and replication/archive throughput;
- Crash recovery test duration;
- Rollback plan.

Avoid changing multiple durability parameters simultaneously without clear justification and isolated measurements.

### 21.7. Periodic Verification

An operational schedule might include:

- Daily: checksum failure counters, database logs, disk/controller alerts;
- Weekly: WAL generation, checkpoint frequency, archive/replication health;
- Per backup schedule: `pg_verifybackup`, restore tests, and PITR drills;
- Per maintenance window: offline `pg_checksums --check` when appropriate;
- After firmware/storage changes: flush/durability tests and error monitoring.

Actual cadence depends on data size, SLAs, downtime cost, and organizational policy.

## 22. Troubleshooting: Common Scenarios

### 22.1. pg_checksums Reports Server Is Running

Cause: the cluster was not shut down or another PostgreSQL process is still accessing the data directory.

Action:

1. Confirm the right PGDATA and instance;
2. Shut down cleanly via the service manager or `pg_ctl`;
3. Verify no server processes remain;
4. Ensure no other tool is writing to tablespaces or the WAL directory;
5. Re-run using the matching major version binary.

Never `kill -9` the server just to make the tool run.

### 22.2. pg_checksums Reports a Checksum Failure

This is evidence that a block failed checksum verification. Record the file/relation/filenode/block and full output. Preserve the data directory, backups, and logs; inspect the storage path and restore plan. Never disable checksums just to get exit code 0.

### 22.3. SHOW data_checksums Returns off

This can happen if the cluster was initialized on PG17 or earlier without `--data-checksums`, initialized on PG18+ with `--no-data-checksums`, or disabled offline. Do not jump to conclusions; review policy, cluster creation/upgrade history, and evaluate enabling offline.

### 22.4. Newly Created PostgreSQL 18 Cluster Has Unexpected Checksum State

PG18 enables checksums by default, yet an installer or provisioning script may have passed `--no-data-checksums`. Always verify with `SHOW data_checksums` rather than assuming from version alone.

### 22.5. FPIs Surge After a Checkpoint

This can be normal when many pages are modified for the first time after a checkpoint. Compare `wal_fpi`, `wal_bytes`, checkpoint frequency, and workload. Check for overly frequent requested checkpoints, base backups, or bulk page-modifying operations.

### 22.6. WAL Volume Increases After Enabling wal_log_hints

`wal_log_hints=on` can cause hint-bit page modifications to emit FPIs. Compare before and after on comparable workloads. If data checksums are already enabled, hint-bit updates are already WAL-logged and this setting is ignored per documented semantics.

### 22.7. wal_compression Rejects lz4 or zstd

The server build may lack support for that codec, or the major version does not support that option. Inspect `SHOW wal_compression`, `pg_settings`, and build/version docs; do not force a config copied from another server.

### 22.8. pg_stat_database checksum_failures Is NULL

NULL can indicate data checksums are disabled, rather than a zero counter. Confirm with `SHOW data_checksums`.

### 22.9. Checksum Failure Reported Earlier, Yet pg_checksums --check Passes

The page's state may have changed, the relation may have been rewritten, the error may be transient, or the scan path differed from where the original failure occurred. Keep original logs and cross-check filenode/block, host/node, and timestamp. One clean scan does not erase a recorded incident.

### 22.10. WAL CRC Error While Page Checksums Are Enabled

These are two separate layers of checking. Data page checksums do not validate WAL segments. Preserve the WAL segment/archive and inspect CRCs, transfer paths, filesystem/storage, backups, and replication links.

### 22.11. Checksum Failures After Restoring or Copying a Standby

Check:

- Whether nodes share the same checksum state/version;
- Whether the copy tool transferred relation blocks and control files intact;
- Whether checksum state was altered while a standby remained active;
- Whether restore/copy finished and synced files properly;
- Whether binary/tool versions match.

### 22.12. pg_rewind Fails to Run

Verify prerequisites for your version, including data checksums or `wal_log_hints` if needed, WAL availability, timeline/history, and permissions. Do not turn on `wal_log_hints` after divergence has already happened and assume old WAL contains what is needed.

### 22.13. FPIs Rise Despite Few UPDATEs

Other operations such as VACUUM, hint-bit changes (depending on checksums/`wal_log_hints`), index maintenance, bulk operations, or base backups can raise WAL and FPIs. Use `pg_stat_wal`, checkpoint logs, and workload tracing to identify the source.

### 22.14. Disabling FPW Cut WAL, but Recovery Is Unsafe

This is a dangerous trade-off. Re-enable `full_page_writes` in server configuration, verify storage atomic-write guarantees, and run crash/recovery tests on staging. Never make lower WAL bytes your sole optimization goal.

### 22.15. Disk Fills Up While pg_checksums --enable Runs

Do not start the cluster or continue writing if the operation's state is unclear. Inspect exit status, logs, and version docs; protect backups/copies, confirm checksum config state, resolve disk capacity, and re-run following the offline procedure. Never delete relation or WAL files to free space.

## 23. Practice Exercises: WAL, FPIs, and Checksums

These exercises use an isolated PostgreSQL lab. Questions about corruption require reasoning or describing a recovery plan only; **never edit bytes in data files on a real database**. Some questions require checking docs for your major version.

### Exercise 1 — Pages and Blocks

Explain what a page/block is in PostgreSQL, its typical size, and what components a heap page contains.

### Exercise 2 — Dirty Page

After an UPDATE, a page in shared buffers changes. Why is it called a dirty page? Which processes can write it out to a data file?

### Exercise 3 — WAL Before Data Page

Describe the write-ahead rule. What can happen if a data page is durably written before its required WAL records?

### Exercise 4 — Commit Without Flushing Every Data Page

A transaction commits successfully while several dirty pages remain in shared buffers. Why does this not violate durability when WAL is properly flushed?

### Exercise 5 — Torn Page Write

An 8 KB page is written using multiple sector writes. The server loses power after only some sectors are written. Describe what state the page on disk can end up in.

### Exercise 6 — WAL Delta Is Insufficient

WAL records only a single tuple change, yet the underlying page on disk is torn. Explain why replaying the delta may fail to restore the page structure.

### Exercise 7 — FPI

Define a full-page image. When is an FPI written to WAL when `full_page_writes=on`?

**Answer:** on the first modification to each page after a checkpoint.

### Exercise 8 — FPI After Checkpoint

A page is modified 5 times after checkpoint C1, then checkpoint C2 runs. Can the first modification after C2 emit a new FPI? Explain.

### Exercise 9 — Why Not Emit an FPI on Every UPDATE?

Analyze the WAL cost if PostgreSQL logged a full page image for every small change instead of only the first modification after a checkpoint.

### Exercise 10 — Checkpoint

Explain what a checkpoint does and why a checkpoint is not a backup.

### Exercise 11 — Redo Point

What is a redo point? How does PostgreSQL use it during crash recovery?

### Exercise 12 — Page LSN

What is page LSN used for? Why is it not a checksum?

### Exercise 13 — Checkpoints Too Frequent

A server checkpoints every minute and FPIs surge. Explain the relationship between checkpoint interval and WAL full-page images.

### Exercise 14 — Checkpoints Too Infrequent

A DBA sets `checkpoint_timeout` very high to reduce WAL. List at least three trade-offs that must be evaluated.

### Exercise 15 — max_wal_size

Explain why `max_wal_size` is a soft limit rather than a hard cap on `pg_wal`.

### Exercise 16 — Manual CHECKPOINT

Why should `CHECKPOINT` not be run repeatedly in production to force writing data pages?

### Exercise 17 — full_page_writes

Inspect via `SHOW full_page_writes`. What is the default? What can happen if it is disabled when storage does not guarantee atomic page writes?

### Exercise 18 — FPIs and Backups

Explain why FPIs in WAL do not replace base backups and WAL archiving/PITR.

### Exercise 19 — wal_log_hints

What are hint bits? How does `wal_log_hints=on` affect WAL?

### Exercise 20 — Data Checksums and wal_log_hints

When data checksums are enabled, why is `wal_log_hints` no longer needed for hint-bit WAL logging?

### Exercise 21 — pg_rewind

Explain why a system preparing to use pg_rewind needs to verify data checksums or `wal_log_hints` ahead of time.

### Exercise 22 — wal_compression

State what data `wal_compression` compresses, which codecs may be supported, and the CPU trade-off.

### Exercise 23 — WAL Stats

Write a query reading `wal_records`, `wal_fpi`, and `wal_bytes` from `pg_stat_wal`. Why must comparisons use equivalent workload windows?

### Exercise 24 — FPI Ratio

A dashboard displays FPI/records = 20%. Can you conclude 20% of WAL bytes are FPIs? Explain.

### Exercise 25 — Page Checksum

When is a data page checksum computed, and when is it checked? What types of errors does it detect?

### Exercise 26 — Checksums Do Not Self-Repair

A page hits a checksum mismatch. Why can PostgreSQL not recover the correct bytes from the checksum alone?

### Exercise 27 — Page Checksum vs. WAL CRC

Compare the goal, target, and bit width of data page checksums versus WAL record CRC-32C.

### Exercise 28 — FPI Checksum

Why are full-page images written into WAL also protected by the WAL record CRC?

### Exercise 29 — Checksums Are Not Cryptographic Hashes

Explain why a page checksum cannot stop an attacker who has permission to directly alter bytes.

### Exercise 30 — Checksum Scope

Give examples of internal structures and temporary files not directly protected by data page checksums.

### Exercise 31 — PostgreSQL 17 vs. 18

State the difference in default data checksums at initdb between PostgreSQL 17 and PostgreSQL 18. Why must you run `SHOW data_checksums` instead of guessing from version?

### Exercise 32 — initdb

Write the initdb command to enable data checksums when creating a new cluster. What scope does this flag apply to?

### Exercise 33 — Existing Cluster

Can you change `data_checksums` by adding it to postgresql.conf and reloading? Why or why not?

### Exercise 34 — Offline pg_checksums

Describe the mandatory precondition before running `pg_checksums --check`, `--enable`, or `--disable`.

### Exercise 35 — pg_checksums Exit Status

Explain exit code 0 vs. non-zero when running `pg_checksums --check`. Why must you read logs/output as well?

### Exercise 36 — Enabling Checksums

Order the steps to enable checksums on a large cluster: backup, shutdown, scan/enable, sync, restart, verify.

### Exercise 37 — Replication

Primary and standby end up with mismatched checksum states after an offline operation. State the risk to tools that copy pages directly and outline a safe remediation.

### Exercise 38 — pg_stat_database

Write a query reading `checksum_failures` and `checksum_last_failure`. If the value is NULL, what can be inferred?

### Exercise 39 — Repeated Checksum Failures

A page checksum failure increments multiple times. Why does the counter not necessarily equal the count of distinct physical pages?

### Exercise 40 — pg_checksums Scan

An 8 TB cluster requires `pg_checksums --check`. Plan for duration, I/O, downtime, and where to store results.

### Exercise 41 — ignore_checksum_failure

Explain the effect and risks of `ignore_checksum_failure`. Why should it never be left on permanently?

### Exercise 42 — zero_damaged_pages

Why can this option help salvage partial data while also discarding rows? When should it be considered?

### Exercise 43 — WAL CRC Error

Distinguish a WAL CRC error from a data page checksum failure. List the locations to inspect: primary, archive, standby, and transit.

### Exercise 44 — Storage Cache

A controller has a write-back cache without battery/flash protection. Why can PostgreSQL receive flush-complete signals yet still lose data on power failure?

### Exercise 45 — fsync

Why can `full_page_writes` not compensate for `fsync=off`? Distinguish between the two parameters.

### Exercise 46 — synchronous_commit

Distinguish `synchronous_commit=off` from `full_page_writes=off`. One relates to commit acknowledgement; what does the other protect?

### Exercise 47 — Backup Verification

Compare the roles of `pg_checksums`, `pg_verifybackup`, and an actual restore test.

### Exercise 48 — PITR

A base backup is valid, but the WAL archive is missing an intermediate segment. Can PITR recover to a timestamp after the missing segment? Explain.

### Exercise 49 — Checksum Incident

Design a runbook when production detects a checksum mismatch: preserve evidence, inspect hardware, check backups/WAL/standbys, salvage, and restore.

### Exercise 50 — Capstone: Designing Durability for PostgreSQL

A payment system requires high durability with 3 TB of data, primary/standby, WAL archiving, and daily backups. The team wants to cut WAL because archive storage is costly.

**Requirements:**

1. Trace an UPDATE from shared buffers through WAL to data files.
2. Explain torn page writes and the role of FPIs.
3. Define `full_page_writes`, `fsync`, and checksum policies.
4. Identify checksum defaults by major version and how to verify state.
5. Propose `wal_compression` using a build-supported codec.
6. Measure `wal_fpi`, `wal_bytes`, checkpoint frequency, and recovery time before/after.
7. Optimize checkpoint intervals while keeping crash recovery within SLA.
8. Define the offline checksum enabling/verification procedure for the cluster and standbys.
9. Build monitoring for checksum failures, WAL CRC errors, archive lag, and storage health.
10. Establish backup manifest verification and restore/PITR drills.
11. Write an incident runbook for checksum mismatches and WAL corruption.
12. Explicitly state actions never to run directly on production without a backup/maintenance plan.

**Passing criteria:** learners must distinguish mechanisms for **preventing/recovering torn pages**, **detecting corruption**, and **restoring from backups/WAL**, while proving durability does not rest on a single parameter.

## 24. Integrity Protection Checklist

### 24.1. At Cluster Initialization

- [ ] Verified major version and that version's default data checksum behavior.
- [ ] Checked `SHOW data_checksums` after initialization.
- [ ] Kept `full_page_writes=on` per durability policy.
- [ ] Kept `fsync=on` for standard production durability.
- [ ] Verified storage/controller/drive honors flushes properly.
- [ ] Designed WAL archiving, base backups, and restore tests.
- [ ] Tested restores in an isolated environment.
- [ ] Documented checksum/WAL configuration in inventory/runbooks.

### 24.2. During Daily Operations

- [ ] Monitor checksum failures and last failure timestamps.
- [ ] Monitor WAL bytes, FPI counts, and checkpoint frequency.
- [ ] Monitor WAL archive failures and replication lag.
- [ ] Monitor disk capacity, I/O latency, and controller/device alerts.
- [ ] Monitor logs for checksum mismatches, WAL CRCs, and OS I/O errors.
- [ ] Keep backups isolated from the primary failure domain.
- [ ] Never delete WAL files manually.
- [ ] Never disable autovacuum, fsync, or full_page_writes to mask symptoms.

### 24.3. When Enabling/Disabling Checksums

- [ ] Use `pg_checksums` matching the major version.
- [ ] Cluster is cleanly shut down.
- [ ] No other process writes to data directory, tablespaces, or WAL directory.
- [ ] Valid backup and restore plan exist.
- [ ] Accounted for scan/rewrite duration and I/O.
- [ ] Never use `--no-sync` in production.
- [ ] Have a consistency plan across primary, standbys, and pg_rewind.
- [ ] Start after completion and verify `SHOW data_checksums`.
- [ ] Run appropriate checksum verification.

### 24.4. When Tuning Checkpoints/FPIs

- [ ] Baseline `wal_fpi`, `wal_bytes`, and checkpoint counts captured.
- [ ] Understand how checkpoint intervals affect FPI frequency.
- [ ] Understand that sparser checkpoints can lengthen recovery time.
- [ ] Measured `wal_compression` against CPU, WAL, and archive throughput.
- [ ] Never turn off `full_page_writes` just to reduce WAL.
- [ ] Tested crash recovery in an appropriate environment.
- [ ] Monitored replication/archive lag after changes.

### 24.5. When Corruption Is Detected

- [ ] Preserve logs, WAL, backups, and related copies.
- [ ] Record relation, block, node, time, and error message.
- [ ] Distinguish data checksums, WAL CRCs, and OS I/O errors.
- [ ] Inspect hardware, firmware, filesystem, kernel, and storage paths.
- [ ] Never manually edit or write bytes into relation files.
- [ ] Never leave `ignore_checksum_failure` enabled permanently.
- [ ] Have a restore/PITR plan and post-recovery verification.
- [ ] File an incident report and track root cause.

## 25. Frequently Asked Questions

### 25.1. Are full-page writes enabled by default?

Yes. PostgreSQL enables `full_page_writes` by default. This writes a full-page image on the first modification to each page after a checkpoint to support torn-page recovery.

### 25.2. Why is an FPI written only once after a checkpoint?

Because crash recovery starts from a checkpoint. The first FPI restores the intact page; subsequent WAL changes are replayed sequentially. After the next checkpoint, the page may need a new FPI on its next first modification.

### 25.3. Do FPIs replace backups?

No. FPIs are simply part of WAL for crash recovery. Backup/PITR requires a base backup and a valid WAL chain.

### 25.4. Do data checksums repair corrupt pages?

No. They detect pages that mismatch their checksum and normally raise an error. Recovery requires appropriate WAL/FPIs, backups/PITR, or a salvage procedure.

### 25.5. How do checksums differ from WAL CRCs?

Data page checksums verify page contents. WAL CRC-32C verifies each WAL record. The two mechanisms protect different layers of data.

### 25.6. Are checksums enabled by default?

PostgreSQL 18 and later enable them by default at initdb. PostgreSQL 17 and earlier major versions default to off. Existing clusters can vary; check with `SHOW data_checksums`.

### 25.7. Can checksums be enabled with zero downtime?

`pg_checksums` requires a clean server shutdown and operates offline across the entire cluster. Schedule a maintenance window or use a platform-appropriate migration/switchover procedure.

### 25.8. Can pg_checksums --check run while the server is running?

No. The server must be cleanly shut down before running the tool.

### 25.9. Does pg_checksums check WAL CRCs?

No. It verifies data page checksums. WAL record CRCs are checked during WAL reads/replay and by related WAL tools.

### 25.10. Does pg_checksums scan the whole cluster?

Check mode scans eligible files across the cluster to verify checksums per supported format. This is heavy I/O; plan accordingly for large clusters.

### 25.11. Do data checksums protect temporary files?

No. Temporary files used during query execution are not protected by data page checksums under this mechanism.

### 25.12. Does WAL compression compress all WAL?

No. It compresses full-page images written into WAL, rather than acting as general compression for all WAL records.

### 25.13. Is increasing checkpoint_timeout always better?

No. It can reduce FPIs/checkpoints and write bursts, yet crash recovery may need to replay more WAL. You must balance WAL, I/O, and RTO.

### 25.14. Should full_page_writes be disabled on ZFS?

Some filesystems prevent partial page writes, but the decision depends on filesystem, storage stack, version, and real guarantees. PostgreSQL defaults FPW on; disable only after verifying end-to-end atomic-write guarantees and accepting the risk.

### 25.15. Does a battery-backed controller make FPW unnecessary?

Not automatically. The controller must guarantee full page writes are atomic or provide equivalent protection. A BBU keeping cache alive across power loss does not inherently mean every 8 KB page write is atomic.

### 25.16. What if a checksum failure appears once and then disappears?

It is still an incident requiring investigation. The page may have been rewritten/restored or the fault may be intermittent. Preserve logs and check storage/hardware/backups before assuming the issue is gone.

### 25.17. Can ignore_checksum_failure be used to keep queries running?

Potentially during emergency salvage, but it is very risky: bad data can propagate, backends can crash, or corruption gets hidden. Never use it permanently and never trust salvaged reads blindly.

### 25.18. Does synchronous_commit=off cause torn pages?

It primarily changes commit confirmation timing relative to WAL flush, risking loss of recently confirmed commits on crash. It is not the same as `full_page_writes=off`, which reduces torn-page protection.

### 25.19. Can pg_verifybackup replace pg_checksums?

No. `pg_verifybackup` validates backup artifacts/manifests within its scope; `pg_checksums` checks data page checksums on an offline cluster. Restore tests remain essential.

### 25.20. Do checksums stop an attacker from modifying data?

No. Page checksums detect accidental errors, not cryptographic tampering. You need access controls, auditing, protected backups, and other security controls.

## 26. Official PostgreSQL Documentation

The following links point to current PostgreSQL documentation. Some defaults changed across major versions, notably default data checksums in PostgreSQL 18; consult the documentation matching your server version:

- [Write Ahead Log (WAL)](https://www.postgresql.org/docs/current/wal-intro.html): WAL overview, crash recovery, and the write-ahead principle.
- [Reliability](https://www.postgresql.org/docs/current/wal-reliability.html): storage caches, partial page writes, full-page images, WAL CRCs, and data checksums.
- [Write Ahead Log Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): `full_page_writes`, `wal_log_hints`, `wal_compression`, `fsync`, `wal_sync_method`, and checkpoint-related parameters.
- [WAL Configuration](https://www.postgresql.org/docs/current/wal-configuration.html): checkpoint frequency, `checkpoint_timeout`, `max_wal_size`, checkpoint completion, and FPI trade-offs.
- [Data Checksums](https://www.postgresql.org/docs/current/checksums.html): protection scope, checksum state, and offline enable/disable.
- [pg_checksums](https://www.postgresql.org/docs/current/app-pgchecksums.html): checking, enabling/disabling checksums, options, and clean shutdown requirements.
- [initdb](https://www.postgresql.org/docs/current/app-initdb.html): `--data-checksums` and `--no-data-checksums`, version defaults.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_wal`, `pg_stat_database`, `pg_stat_checkpointer`, and checksum failure counters.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html): prerequisites and the role of data checksums/`wal_log_hints`.
- [Backup Manifest](https://www.postgresql.org/docs/current/backup-manifest-format.html): backup manifest checksums and metadata.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): validating a backup directory against its manifest.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backups, WAL archives, and PITR.
- [Reliability and the Write-Ahead Log](https://www.postgresql.org/docs/current/wal.html): comprehensive chapter on reliability and WAL.

## 27. Summary

**Full-page writes, data checksums, and WAL CRCs protect different layers of PostgreSQL.**

| Mechanism | Protects | Core Behavior |
| --- | --- | --- |
| `full_page_writes` | Torn data pages on crash | Writes an FPI in WAL on the first page modification after a checkpoint |
| `data_checksums` | Data page corruption | Checks checksum when pages are read/verified |
| WAL CRC-32C | WAL record corruption | Verifies CRC on every WAL record |
| `fsync` and storage flush | Write durability | Requests data/WAL sync to non-volatile storage |
| Base backup + WAL archive | Database recovery/PITR | Provides starting point and replay chain to target time |

To protect integrity:

1. Keep `full_page_writes` and `fsync` enabled per durability policy.
2. Enable data checksums for clusters; note PG18 switched the default to on.
3. Understand `wal_log_hints` and `wal_compression` before tuning them.
4. Monitor FPIs, WAL bytes, checkpoints, and checksum failures.
5. Run the matching version of `pg_checksums` on a cleanly shut-down cluster.
6. Protect WAL archives, backups, and replication topology.
7. Verify hardware/storage flush behavior.
8. Maintain restore/PITR drills and incident runbooks.

No single parameter can substitute for an entire durability architecture. **FPIs enable recovery after torn writes; checksums detect page corruption; WAL CRCs detect record corruption; backups and WAL archives restore data when files are no longer usable.** Combining these layers properly with regular recovery drills creates a reliable foundation for data protection.
