# Monitoring Capacity, Growth Trends, and Disk-Full Alerts in Oracle Database

An Oracle Database can run smoothly for months and then suddenly fail when a table cannot extend, a query needs more TEMP, UNDO runs out of space, or the system cannot write archived redo logs. The issue is not merely total free gigabytes: **Oracle manages space across multiple layers**, and one layer having free space does not guarantee underlying layers can still allocate.

For example, a datafile may have `AUTOEXTEND` enabled up to 100 GB while the filesystem only has 2 GB free. On a tablespace monitoring dashboard, configured growth capacity looks ample; on the operating system, running out of disk is imminent. Conversely, a filesystem may have hundreds of free GB while the datafile hits `MAXSIZE` or the tablespace has no allocatable extents left, causing `INSERT` statements to fail anyway.

This lesson explains how to **observe current usage, record history to compute growth rates, design alerts, and handle early signs of space exhaustion** in Oracle Database. The focus is on reading and assessment, not hastily resizing files.

After this lesson, you will be able to:

- Distinguish **tablespace**, **datafile**, **segment**, **TEMP/UNDO**, **filesystem or ASM**, and **Fast Recovery Area (FRA)** capacity.
- Read `USED_SPACE`, `TABLESPACE_SIZE`, `USED_PERCENT`, `BYTES`, `MAXBYTES`, and `AUTOEXTENSIBLE` accurately in context.
- Write SQL queries to find filling tablespaces, extensible datafiles, and top space-consuming objects.
- Track history rather than looking at a single snapshot, and conditionally estimate growth rates and **days to full**.
- Build multi-tier alerting rules with thresholds on usage percentage, reserve headroom, and forecasted runway.
- Establish a safe diagnostic workflow when out-of-space errors or nearly full archive/FRA alerts occur.

> These `SELECT` statements query Oracle dictionary/dynamic performance views, which may require `SELECT` privileges on those views or an appropriate administrative account. Some views and calculations vary by version, CDB/PDB container, storage backend, and autoextend settings. When lacking privileges, ask an administrator for the metrics; never grant full `DBA` privileges to an application account merely to view capacity.

## 1. "Disk Full" Can Happen at Multiple Layers

Oracle's basic storage path:

```text
Application INSERT / UPDATE / CREATE INDEX / SORT / COMMIT
                         │
                         ▼
             Segment / Extent / Block
                         │
                         ▼
             Oracle Tablespace
               │            │
          Datafile       Tempfile
               │            │
               └─────┬──────┘
                     ▼
           Filesystem or ASM
                     │
                     ▼
         Disk / volume / storage device

         Other write streams:
         LGWR → online redo logs
         ARCn / RMAN / flashback → FRA or separate destination
```

A system can run out of space at any point along this chain:

| Layer | Question to Answer | Incident Example |
|---|---|---|
| **Segment** | Which table, index, LOB, or partition is occupying and growing space? | A log table grows rapidly due to an inappropriate retention policy |
| **Tablespace** | Can extents still be allocated to segments? | Tablespace reaches limit; `ORA-01653` when extending a table |
| **Datafile** | What are current size, `AUTOEXTEND`, `MAXBYTES`, and remaining growth margin? | File hits `MAXSIZE` even though underlying disk still has space |
| **TEMP** | How much temporary space do sort/hash queries or index operations need? | `ORA-01652` when unable to allocate additional temporary segments |
| **UNDO** | Are undo extents sufficient for transactions and consistent reads? | `ORA-30036` when unable to allocate additional undo |
| **Filesystem** | How many bytes/inodes remain on volumes holding datafiles, redo, backups, or archives? | Datafile tries to extend while underlying storage device is out of space |
| **ASM disk group** | How much real usable space remains after redundancy? | `USABLE_FILE_MB` is low even though some `FREE_MB` remains |
| **FRA / archive** | Do archived redo, flashback logs, and backups still fit inside the FRA limit? | `ORA-19809` or archiver error; transactions may stall |
| **VM/container/host** | Can virtual disks, Docker volumes, and physical drives still grow? | Container reports file write errors because host or virtual disk is out of space |

**No single "% disk used" column accurately describes all of the layers above.** Good monitoring must cross-check Oracle data against storage metrics outside the database.

### 1.1. Units and Terminology

- **Block:** Oracle's unit for managing database data; block sizes can differ across tablespaces.
- **Extent:** group of blocks allocated to a segment. Space allocated to a segment does not necessarily equal active business data bytes.
- **Segment:** storage region belonging to a table, index, LOB, partition, or other object type.
- **Datafile:** physical file storing data in a permanent/undo tablespace.
- **Tempfile:** file belonging to a temporary tablespace; must be monitored differently from regular datafiles.
- **Allocated size:** size of files or extents currently allocated by Oracle.
- **Potential/configured maximum:** maximum expansion limit per configuration; **not synonymous** with guaranteed available physical disk.
- **Free extents:** space not yet assigned to segments inside a datafile; distinct from "empty rows" inside a table.

In the SQL examples, `POWER(1024, 2)` converts bytes to MiB and `POWER(1024, 3)` converts bytes to GiB. Common `MB/GB` labels in tools may use rounded display units; align units carefully when comparing Oracle figures with storage monitoring.

## 2. Three Numbers to View Together

Consider a tablespace with illustrative metrics:

| Metric | Example | Meaning |
|---|---:|---|
| Currently allocated size of datafiles | 80 GiB | Current file size |
| Extents allocated to segments | 72 GiB | Space already assigned to objects |
| Free extents inside current datafiles | 8 GiB | Empty space inside existing files |
| Combined configured ceiling if autoextending | 120 GiB | Theoretical limit per `MAXBYTES` |
| Remaining free space on underlying filesystem | 6 GiB | Disk remaining for files to grow, shared with other files |

Looking only at configured limits, the tablespace appears to have 48 GiB between 72 GiB used extents and the 120 GiB ceiling. Yet **the physical disk only has 6 GiB free**; you must not forecast 48 GiB as actually usable. Assuming the filesystem only serves these resources, file growth hits a ceiling at 6 GiB first. Meanwhile, 8 GiB of free extents still exist inside existing datafiles.

Therefore, at least three perspectives are required:

1. **How much is used/allocated at the Oracle level?**
2. **Can it grow further under Oracle's configuration?**
3. **Does physical storage actually have enough space to back that growth?**

When collecting metrics, clearly separate **current size**, **configured ceiling**, and **real available ceiling**. An alert relying solely on `AUTOEXTEND=YES` is incomplete.

## 3. Viewing Tablespace Usage with SQL

### 3.1. Overview via `DBA_TABLESPACE_USAGE_METRICS`

Oracle provides `DBA_TABLESPACE_USAGE_METRICS` with key columns:

- `TABLESPACE_NAME`: tablespace name.
- `USED_SPACE`: used space in blocks.
- `TABLESPACE_SIZE`: tablespace size evaluated by the view's calculation, in blocks; may reflect extension ceilings and storage factors depending on configuration/version.
- `USED_PERCENT`: ratio of `USED_SPACE` to `TABLESPACE_SIZE` per the view's definition.

Join with `DBA_TABLESPACES.BLOCK_SIZE` to convert blocks into bytes:

```sql
SELECT
    m.tablespace_name,
    t.contents,
    t.bigfile,
    ROUND(m.used_space * t.block_size / POWER(1024, 3), 2) AS used_gib,
    ROUND(m.tablespace_size * t.block_size / POWER(1024, 3), 2)
        AS capacity_gib,
    ROUND(m.used_percent, 2) AS used_percent,
    ROUND((m.tablespace_size - m.used_space) * t.block_size
          / POWER(1024, 3), 2) AS remaining_gib
FROM dba_tablespace_usage_metrics m
JOIN dba_tablespaces t
  ON t.tablespace_name = m.tablespace_name
ORDER BY m.used_percent DESC;
```

Illustrative output:

| TABLESPACE_NAME | CONTENTS | USED_GIB | CAPACITY_GIB | USED_PERCENT |
|---|---|---:|---:|---:|
| APP_DATA | PERMANENT | 76.0 | 90.0 | 84.44 |
| APP_INDEX | PERMANENT | 18.0 | 30.0 | 60.00 |
| UNDOTBS1 | UNDO | 10.0 | 16.0 | 62.50 |

**How to read accurately:** this percentage relies on the view's `TABLESPACE_SIZE` definition, which can differ from `used / allocated-current-files`. Do not label `USED_PERCENT` as "filesystem fill percentage." If the numbers appear to conflict with `df`/ASM, inspect datafiles, autoextend, and real storage before drawing conclusions.

For CDB/PDB, `DBA_...` views generally show the scope of the currently connected container; an account in CDB root does not automatically produce one consolidated accurate view across every PDB without using matching container views/scoping. Multi-PDB monitoring should store **container identity** (`CON_NAME`/`CON_ID`) and run with clearly scoped privileges.

### 3.2. Checking Individual Datafiles and Autoextend Settings

`DBA_DATA_FILES` reflects current sizes and expansion settings of datafiles. `DBA_FREE_SPACE` shows free extents in permanent tablespaces; aggregate by `FILE_ID` before joining with datafiles:

```sql
WITH free_per_file AS (
    SELECT file_id, SUM(bytes) AS free_bytes
    FROM dba_free_space
    GROUP BY file_id
)
SELECT
    df.tablespace_name,
    df.file_name,
    df.autoextensible,
    ROUND(df.bytes / POWER(1024, 3), 2) AS allocated_gib,
    ROUND(NVL(f.free_bytes, 0) / POWER(1024, 3), 2)
        AS free_extent_gib,
    ROUND((df.bytes - NVL(f.free_bytes, 0))
          / POWER(1024, 3), 2) AS nonfree_extent_gib,
    ROUND(
        CASE WHEN df.autoextensible = 'YES'
             THEN df.maxbytes ELSE df.bytes END
        / POWER(1024, 3), 2
    ) AS configured_file_max_gib
FROM dba_data_files df
LEFT JOIN free_per_file f
  ON f.file_id = df.file_id
ORDER BY df.tablespace_name, df.file_name;
```

Interpretation:

- `ALLOCATED_GIB`: Oracle file's current size.
- `FREE_EXTENT_GIB`: extents Oracle has not yet assigned to segments inside the file.
- `NONFREE_EXTENT_GIB`: remainder not in free extents under that simple subtraction; **not actual business data payload bytes**. Datafiles include metadata, and segments can hold blocks without live rows.
- `CONFIGURED_FILE_MAX_GIB`: configured ceiling derived from `MAXBYTES` if autoextend is on; does not guarantee filesystem/ASM still has room.

In locally managed tablespaces, `DBA_FREE_SPACE` may omit rows for files with zero free extents; `LEFT JOIN` and `NVL` keep those files in the report. Tablespaces/files in special states such as offline or encrypted may require specific privileges/conditions to read metadata; missing dictionary rows must not automatically be read as "0 bytes used." **Tempfiles are tracked via separate views**—never substitute this output for a TEMP report.

### 3.3. Finding Which Segments Consume the Most Space

When a permanent tablespace grows rapidly, inspect segment sizes:

```sql
SELECT
    owner,
    segment_name,
    segment_type,
    ROUND(SUM(bytes) / POWER(1024, 3), 2) AS allocated_gib
FROM dba_segments
WHERE tablespace_name = :tablespace_name
GROUP BY owner, segment_name, segment_type
ORDER BY SUM(bytes) DESC
FETCH FIRST 20 ROWS ONLY;
```

Set bind parameter `:tablespace_name` in your SQL client, e.g., `APP_DATA`. When analyzing partitioned tables/indexes, sum the related segments/partitions. LOBs typically sit in separate segments; the base table may be tiny while its LOB segment is huge.

**`DBA_SEGMENTS.BYTES` is allocated extent space**, not useful payload or row count multiplied by average row length. Deleting rows may leave a table segment holding extents without returning them to the tablespace; analysis must consider the high water mark, in-segment free space, and appropriate reclamation policies.

To know which segments **are growing**, store snapshots of `DBA_SEGMENTS` over time or compare against suitable historical stats. A single `ORDER BY bytes DESC` run only identifies large segments, not necessarily recent growth culprits.

## 4. Monitoring TEMP and UNDO by Their Own Characteristics

### 4.1. Temporary Tablespaces: Allocated vs. Actively Used

Temporary tablespaces serve sorts, hash joins, intermediate processing, and certain other tasks. Temporary extents can stay cached for reuse after queries finish, so **allocated TEMP does not mean all of it is currently held by active sessions**.

Overview query:

```sql
SELECT
    tablespace_name,
    ROUND(tablespace_size / POWER(1024, 3), 2) AS size_gib,
    ROUND(allocated_space / POWER(1024, 3), 2) AS allocated_gib,
    ROUND(free_space / POWER(1024, 3), 2) AS free_gib
FROM dba_temp_free_space
ORDER BY tablespace_name;
```

In `DBA_TEMP_FREE_SPACE`, `FREE_SPACE` may include both allocated-but-unused space and unallocated space; therefore, do not treat `TABLESPACE_SIZE - ALLOCATED_SPACE` as "TEMP currently used by sessions" without checking exact column definitions.

Check which sessions **currently hold temporary segments**:

```sql
SELECT
    username,
    tablespace,
    segtype,
    SUM(blocks) AS used_blocks
FROM v$tempseg_usage
GROUP BY username, tablespace, segtype
ORDER BY used_blocks DESC;
```

`BLOCKS` here is in blocks, not bytes; multiply by the corresponding block size to convert. When many sessions share one username, include session/SQL identifiers and timestamps to pinpoint the exact SQL consuming TEMP.

When TEMP fills up, do not jump to "not enough disk space": an inefficient sort/hash query, abnormal batch job, or index build may be consuming far more TEMP than expected.

### 4.2. Undo Tablespaces: Active, Unexpired, and Expired

Undo stores info for rollback and read consistency. Undo extents can be:

- `ACTIVE`: needed by currently running transactions.
- `UNEXPIRED`: no longer active, yet still within the undo retention window.
- `EXPIRED`: eligible for reuse per Oracle's rules.

Inspect by status:

```sql
SELECT
    tablespace_name,
    status,
    ROUND(SUM(bytes) / POWER(1024, 3), 2) AS allocated_gib
FROM dba_undo_extents
GROUP BY tablespace_name, status
ORDER BY tablespace_name, status;
```

`UNEXPIRED` does not strictly mean "never reusable"; undo retention also depends on retention settings, guarantee mode, space pressure, and configuration. Long-running queries or long-open transactions increase undo demand. Views like `V$UNDOSTAT` help track undo generation rates and retention issues over intervals.

When `ORA-30036` occurs, examine undo capacity, autoextend settings, long transactions, DML rate, and storage limits before deciding to expand undo.

## 5. Monitoring Storage Below Oracle

### 5.1. Filesystems on Linux

When Oracle stores datafiles, redo logs, or archived redo logs on filesystems, administrators should measure directly on the host or VM:

```bash
df -h
df -i
lsblk -f
```

- `df -h`: used and available space on mounted filesystems.
- `df -i`: used/free inodes; on some filesystems, running out of inodes makes file creation fail even when free bytes remain.
- `lsblk -f`: inspects block devices, filesystems, and mountpoints on Linux.

Checking a specific mountpoint:

```bash
df -h /u02/oradata
```

`/u02/oradata` is an illustrative path. Replace it with the actual directory holding datafiles or archives/backups. If Oracle spans multiple mountpoints, monitor **every mountpoint**. Filesystem limits where datafiles live do not necessarily match where archived logs live.

Filesystem measurements must also account for quotas, thin provisioning, or available capacity on the storage array. With thin-provisioned storage, OS readings inside a VM may differ from real remaining space on underlying infrastructure.

### 5.2. ASM: `FREE_MB` Differs from `USABLE_FILE_MB`

If Oracle uses **Automatic Storage Management (ASM)**, datafiles/redo may reside in disk groups (such as `+DATA`, `+RECO`). Running `df -h` inside a Linux guest does not replace inspecting ASM capacity.

In the **ASM instance** with proper privileges, run:

```sql
SELECT
    name,
    total_mb,
    free_mb,
    required_mirror_free_mb,
    usable_file_mb
FROM v$asm_diskgroup_stat
ORDER BY name;
```

Meaning:

- `TOTAL_MB`: total disk group capacity reported by ASM.
- `FREE_MB`: raw free space at the disk group level before accounting for redundancy mirror copies.
- `REQUIRED_MIRROR_FREE_MB`: space ASM reserves to restore redundancy after a failure per redundancy policy.
- `USABLE_FILE_MB`: useful remaining space available for files after factoring in those mirroring/reserve requirements.

With mirrored redundancy, **`FREE_MB` cannot be read as MB of new single-copy data you can add**. `USABLE_FILE_MB` can be much lower, or even negative indicating severe reserve pressure. Also monitor individual disk groups, balance state, and disk health appropriately.

### 5.3. Docker, VMs, and Physical Hosts

When Oracle runs inside a container, space can face layered limits:

```text
Oracle datafile
   → Docker named volume / bind mount
   → filesystem of Docker host or Linux VM/WSL
   → physical disk / backing storage
```

Commands to inspect general Docker usage:

```powershell
docker system df
docker volume ls
docker volume inspect oracle-lab-data
```

Replace `oracle-lab-data` with the real volume name. `docker system df` mainly reports images/containers/volumes per Docker's accounting—**it is not a substitute for `DBA_DATA_FILES` or Oracle metrics**. On Docker Desktop/WSL, also check the virtual disk size and the host drive containing that virtual disk.

**Never delete volumes, Oracle files, or run full Docker prune commands just to free space.** Such actions can wipe your practice database or break recovery. Before cleaning storage, verify exact objects and data ownership.

### 5.4. On Windows

If datafiles/VM/Docker storage live on Windows drives, inspect volumes with PowerShell:

```powershell
Get-Volume | Select-Object DriveLetter, FileSystemLabel, Size, SizeRemaining
```

Know the exact path of files/virtual disks to match the right volume. If Oracle runs inside a Linux VM/WSL, both Windows host and Linux guest metrics matter: the guest can hit its virtual disk limit before the host drive fills up, or vice versa.

## 6. FRA, Archived Redo Logs, and Risk of Database Stalls

The **Fast Recovery Area (FRA)** is a recovery storage area capable of holding archived redo logs, flashback logs, backup pieces, and related files per configuration. The FRA has an **Oracle-managed size limit** alongside the physical limits of the underlying filesystem or ASM disk group.

If the FRA hits its limit, Oracle may be unable to create new recovery files; archiving failures can severely disrupt database write operations. Therefore, **the FRA requires its own independent alert**, never lumped naively into data tablespace fill percentages.

### 6.1. Checking FRA Limit and Usage

With appropriate privileges:

```sql
SELECT
    name,
    ROUND(space_limit / POWER(1024, 3), 2) AS limit_gib,
    ROUND(space_used / POWER(1024, 3), 2) AS used_gib,
    ROUND(space_reclaimable / POWER(1024, 3), 2) AS reclaimable_gib,
    number_of_files
FROM v$recovery_file_dest;
```

If FRA is not configured, output may lack expected values. Never assume every database stores archived redo logs in the FRA; some systems use separate archive destinations.

Inspect file categories consuming the FRA:

```sql
SELECT
    file_type,
    percent_space_used,
    percent_space_reclaimable,
    number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
```

`SPACE_RECLAIMABLE` indicates space Oracle can reclaim under management policies, **not bytes already freed back to disk**. Actual reclamation depends on retention, backup status, archivelog deletion policy, flashback, and other conditions.

Check archive mode:

```sql
SELECT log_mode FROM v$database;
```

`ARCHIVELOG` databases must monitor archived redo generation rates and approved backup/deletion cycles. On databases with Data Guard or backup dependencies, never manually delete archived logs because standbys/recovery may still need them.

### 6.2. Why Can the FRA Fill Up Very Quickly?

- A large `INSERT/UPDATE/DELETE` batch generating far more redo than usual.
- Archive logs not being backed up or purged per policy.
- Retention of flashback logs/restore points or recovery requirements holding space.
- `DB_RECOVERY_FILE_DEST_SIZE` undersized relative to redo rate and required retention window.
- Underlying physical storage beneath the FRA running out of space before Oracle reaches the configured FRA ceiling.

**Never use `rm`, `del`, or manual deletion on online/archived redo logs in Oracle directories as a "quick fix."** Assess recovery status, backups, and deletion policies, then use approved administrative tools/procedures like RMAN with proper authorization. Deleting the wrong file can break recoverability or halt the database.

## 7. Periodic Capacity "Snapshots" to Reveal Trends

Seeing `USED_PERCENT=78%` once does not tell you how urgent it is:

- A tablespace growing **0.1 GiB/day** with 20 GiB left may last a long time.
- A tablespace growing **5 GiB/day** with 20 GiB left could fill in just a few days.
- Usage can also jump suddenly during batch runs, data loads, or post-maintenance.

Thus you must collect a **time series**. Sample consistently at steady intervals, storing at least:

| Field | Purpose |
|---|---|
| Sample timestamp and timezone | Correlate samples with operational events |
| Database/instance and PDB/container | Avoid mixing metrics across different databases or PDBs |
| Tablespace or ASM disk group/FRA/filesystem name | Identify the exact storage target |
| Used bytes and allocated bytes | See both consumption and allocated space |
| Configured maximum and physical available | Understand both logical and physical expansion limits |
| Used percent | Percentage-based alerting |
| Autoextend status and storage health | Explain sudden shifts |

Sampling frequency depends on the environment. A quiet lab might sample daily; fast-growing production should sample hourly or even more frequently for critical FRA, TEMP, and filesystems. **Sampling once a day can miss a 10-minute TEMP spike or a one-hour archive surge.**

### 7.1. Example Storing Tablespace History in a Management Table

The example below illustrates storing time-series snapshots in **an appropriately privileged monitoring schema**. This is sample table DDL to learn the mechanism, not a recommendation to add schemas to production without clear ownership and retention policies.

```sql
CREATE TABLE ts_usage_history (
    sampled_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    container_name  VARCHAR2(128) NOT NULL,
    tablespace_name VARCHAR2(128) NOT NULL,
    used_bytes      NUMBER NOT NULL,
    capacity_bytes  NUMBER NOT NULL,
    used_percent    NUMBER NOT NULL
);

CREATE INDEX idx_ts_usage_history
    ON ts_usage_history (
        container_name,
        tablespace_name,
        sampled_at
    );
```

Each sampling run:

```sql
INSERT INTO ts_usage_history (
    sampled_at,
    container_name,
    tablespace_name,
    used_bytes,
    capacity_bytes,
    used_percent
)
SELECT
    SYSTIMESTAMP,
    SYS_CONTEXT('USERENV', 'CON_NAME'),
    m.tablespace_name,
    m.used_space * t.block_size,
    m.tablespace_size * t.block_size,
    m.used_percent
FROM dba_tablespace_usage_metrics m
JOIN dba_tablespaces t
  ON t.tablespace_name = m.tablespace_name;

COMMIT;
```

This captures a **snapshot for the running session's container**. When monitoring multiple databases/PDBs, production systems need a database identifier such as `DB_UNIQUE_NAME` or source ID, scoping each PDB cleanly without duplicates. Never schedule unbounded continuous sampling jobs or create history tables without a retention cleanup plan.

Scheduling can be handled by an external monitoring platform, Oracle Scheduler, or existing operations tooling. In production, prefer your organization's existing observability stack rather than adding ad-hoc jobs inside the database just to experiment.

### 7.2. Reading Change Between Start and End of a Window

Once multiple samples are collected in `TS_USAGE_HISTORY`:

```sql
WITH endpoints AS (
    SELECT
        container_name,
        tablespace_name,
        MIN(sampled_at) AS first_at,
        MAX(sampled_at) AS last_at,
        MAX(used_bytes) KEEP (
            DENSE_RANK FIRST ORDER BY sampled_at
        ) AS first_used,
        MAX(used_bytes) KEEP (
            DENSE_RANK LAST ORDER BY sampled_at
        ) AS last_used,
        MAX(capacity_bytes) KEEP (
            DENSE_RANK LAST ORDER BY sampled_at
        ) AS last_capacity
    FROM ts_usage_history
    WHERE sampled_at >= SYSTIMESTAMP - INTERVAL '14' DAY
    GROUP BY container_name, tablespace_name
)
SELECT
    container_name,
    tablespace_name,
    ROUND((last_used - first_used) / POWER(1024, 3), 2)
        AS net_growth_gib,
    ROUND(
        (last_used - first_used)
        / POWER(1024, 3)
        / NULLIF(
            CAST(last_at AS DATE) - CAST(first_at AS DATE), 0
          ), 2
    ) AS growth_gib_per_day,
    ROUND((last_capacity - last_used) / POWER(1024, 3), 2)
        AS remaining_gib
FROM endpoints
ORDER BY growth_gib_per_day DESC NULLS LAST;
```

This computes **net growth between window endpoints**. It can be negative after cleanup/reclaim shrinks usage; that does not mean writes during the window consumed zero storage. The query uses the end-of-window capacity from the chosen view, **not yet factoring in physical filesystem/ASM limits or FRA growth**.

Do not compute a daily rate from two samples spaced minutes apart and treat it as authoritative. Use many data points, compare weekdays vs. weekends, and account for batch schedules and heavy load days to establish reliable trends.

## 8. Calculating Growth and "Days to Full"

A simple forecast calculation:

```text
growth_per_day = (used_at_end - used_at_start) / number_of_days

headroom = effective_capacity - current_used

days_to_full = headroom / growth_per_day
               (only when growth_per_day > 0)
```

Where:

- `effective_capacity` must consider both **Oracle ceilings** and **real storage expansion headroom**. Without storage metrics, state explicitly "per observed logical limits" rather than treating it as a guaranteed physical forecast.
- `current_used` must follow the exact same definition as historical samples.
- When `growth_per_day <= 0`, **never confidently declare days to full as infinity**; simply conclude there is no evidence of sustained upward growth in that measurement window.
- For event-driven, seasonal/batch, or bulk-loaded workloads, a linear trend is only one reference scenario.

### 8.1. Manual Calculation Example

Suppose tablespace `APP_DATA` has:

| Metric | Value |
|---|---:|
| Used at start of week | 62 GiB |
| Used at end of week | 76 GiB |
| Elapsed time between samples | 7 days |
| Usable capacity per measured metric | 100 GiB |

Then:

```text
Net growth      = 76 - 62 = 14 GiB
Daily average   = 14 / 7 = 2 GiB/day
Remaining per measured capacity = 100 - 76 = 24 GiB
Days to full ≈ 24 / 2 = 12 days
```

A dashboard showing only "76%" might look safe if the warning threshold is 80%; yet with **12 days to full**, operations already needs advance notice to prepare storage or curb data growth.

If the configured autoextend ceiling is 150 GiB while the filesystem only has 6 GiB left outside existing datafiles, do not use `150 - 76 = 74 GiB` as physical headroom. Sum existing free extents plus **actual available expansion headroom**, while accounting for space other files on the same filesystem will consume.

### 8.2. Forecasts Should Include an Uncertainty Range

With a month of data, also examine:

- Average growth rate vs. **peak-day** growth rate.
- 7-day vs. 30-day trends, and backup/ETL/batch schedules.
- Configuration changes such as adding datafiles or raising `MAXSIZE` that cause capacity jumps.
- Growth per segment group, not only tablespace totals.
- Real storage metrics: FRA, filesystems/ASM may be shared by other systems.

For example, suppose average growth is 1 GiB/day while peak days hit 8 GiB/day. With 12 GiB of headroom left, announcing "12 days guaranteed" is unsafe. Present a **forecast range of 1.5–12 days** across both illustrative scenarios, stating assumptions and observed data clearly.

## 9. Designing Alerts Before the Database Actually Fills Up

Alerting solely on "over 90% full" often triggers too late on fast-growing systems. Combine **fill level**, **actual expansion capability**, and **growth rate**.

Sample policy template, to adjust per each environment's SLAs and growth patterns:

| Level | Suggested Condition | Action |
|---|---|---|
| **Info** | Growing faster than baseline even if not yet near full | Log trend, cross-check recent batches/segments |
| **Warning** | Tablespace ≥ 80% or forecast ≤ 14 days | Verify growth, autoextend, and storage source; open capacity planning ticket |
| **Critical** | Tablespace ≥ 90%, or forecast ≤ 7 days, or storage/FRA below safe reserve | Page on-call, immediately assess allocation headroom and service impact |
| **Emergency** | Database writes/archiving failing or physical storage can no longer allocate | Trigger incident runbook, protect data and recovery capability |

Thresholds like 80/90% and 14/7 days are **examples**, not mandatory Oracle standards. A 10 TiB tablespace with 5% free differs vastly from a 10 GiB tablespace with 5% free. To avoid noisy alerts, also factor in **absolute GiB remaining** and workload-specific rules.

### 9.1. Example SQL to Detect Tablespaces Crossing Thresholds

```sql
SELECT
    tablespace_name,
    ROUND(used_percent, 2) AS used_percent,
    CASE
        WHEN used_percent >= 90 THEN 'CRITICAL'
        WHEN used_percent >= 80 THEN 'WARNING'
        ELSE 'OK'
    END AS severity
FROM dba_tablespace_usage_metrics
WHERE used_percent >= 80
ORDER BY used_percent DESC;
```

This output is **raw alert input**, not a notification system. Real deployments use your organization's monitoring stack, Oracle Enterprise Manager, or server-generated alerts matching your version/privileges, with dedicated management of recipients, channels, thresholds, and operational permissions.

### 9.2. Layer-Specific Alerting Rules

| Target | Metrics to Monitor | Why Different? |
|---|---|---|
| Permanent tablespace | `USED_PERCENT`, free extents, datafile max/autoextend | Detects extent exhaustion and datafile ceilings |
| Temporary tablespace | Free TEMP and TEMP actively held by sessions | Query-driven peaks can be very brief |
| Undo | Undo extent statuses, undo generation rate, autoextend headroom | Long transactions / undo retention can create pressure |
| Filesystem | Free bytes, free %, inodes, growth rate | Oracle autoextend cannot exceed physical disk |
| ASM | `USABLE_FILE_MB`, disk group health, free space, redundancy | `FREE_MB` alone does not reflect usable capacity |
| FRA | Used/limit, reclaimable, archived redo rate, archiver status | FRA has its own cap and can stall writes/archiving |
| Datafile | Current size, maxsize, autoextend, growth rate | One file may hit max before others |
| Segment | Size snapshots by owner/object/partition | Pinpoints the exact growth source |

For example, even if a tablespace is only 65% full, if **the filesystem has under 10 GiB left** and archive/backup rates surge, host-level storage alerts may be far more urgent than tablespace percentages.

### 9.3. Reducing Alert Noise

An effective alerting system typically needs:

1. **Clear source labeling:** database, PDB, tablespace/mountpoint/disk group, environment, timestamp, and severity.
2. **Consecutive-sample confirmation** for oscillating trend or percentage alerts; real write errors must alert immediately per policy.
3. **Hysteresis:** e.g., fire warning at 80%, auto-resolve only after usage drops below 75%, if policy permits.
4. **Deduplication:** avoid sending identical alerts every minute when nothing significant changed.
5. **Attached runbooks and owners:** responders must know which Oracle views, filesystems/ASM, and FRA checks to run.
6. **Recovery context:** when usage drops, distinguish real space reclamation, capacity expansion, or monitoring changes.

Never equate "no data collected" with "0% used." If a monitoring agent stops or loses view privileges, alert on **monitoring unavailable/stale** to avoid false green status.

## 10. When Out-of-Space Errors Occur: Diagnose in Order

### 10.1. Common Messages

| Message | First Diagnostic Direction |
|---|---|
| `ORA-01653: unable to extend table ... in tablespace ...` | Permanent tablespace/datafile cannot allocate another extent for the table |
| `ORA-01654: unable to extend index ...` | Index segment or the index's tablespace cannot extend |
| `ORA-01652: unable to extend temp segment ...` | TEMP or a temp-segment operation hit a limit; inspect workload and storage |
| `ORA-30036: unable to extend segment ... in undo tablespace` | Undo lacks extent allocation capacity; inspect transactions/retention/autoextend |
| `ORA-19809: limit exceeded for recovery files` | FRA reached configured limit; inspect file types and reclaim policy |
| `ORA-00257: archiver error` | Archiving problem, possibly full archive destination/FRA or storage error |
| I/O error or OS file extension failure | Filesystem/ASM/quota/device cannot accept writes |

These are **investigation leads**, not definitive root causes. Examine the full error stack, alert log, timestamp, and state of every storage layer.

### 10.2. Observation and Isolation Runbook

**Step 1 — Define impact scope.** Did the error hit a table/index, TEMP, UNDO, FRA, or filesystem? Which applications are affected? Are transactions blocked or unusual batches running? Record timestamp, database/PDB, table/segment, and exact message.

**Step 2 — Locate physical storage.** For segment errors, trace tablespace then datafiles. For redo/archive, trace archive destination/FRA. For VMs/containers, trace the actual mountpoint/volume. Never just run `df -h` on an arbitrary mountpoint.

**Step 3 — Read current size, free extents, and autoextend.** Cross-check `DBA_TABLESPACE_USAGE_METRICS`, `DBA_DATA_FILES`, `DBA_FREE_SPACE`, or the corresponding TEMP/UNDO views. If Oracle shows datafiles can still autoextend, inspect underlying storage next.

**Step 4 — Check storage limits.** Inspect `df` or ASM disk groups, FRA status, quotas/thin provisioning, and storage error messages. If the backend is out of space, raising `MAXSIZE` inside Oracle alone will not solve it.

**Step 5 — Identify growth source.** Compare `DBA_SEGMENTS` snapshots, archived redo rate, batch imports, new partitions, long transactions, or heavy TEMP queries. Determine whether growth is expected or abnormal.

**Step 6 — Choose a controlled remediation.** Depending on cause and policy, this may mean adding storage, adjusting datafile limits, adding datafiles for supported tablespace types, tuning queries, applying partitioning/data retention, or cleaning up files via valid backup/recovery procedures. Ensure recoverability and execution by authorized personnel.

**Step 7 — Verify post-remediation.** Confirm both Oracle and storage metrics reflect expected changes; verify workload recovery and close alerts with fresh evidence. Update growth forecasts so the incident does not recur.

### 10.3. What Never to Do When Approaching Full Disk

- **Never delete datafiles, control files, online redo logs, or archived redo logs directly** using OS commands as a general fix.
- **Never raise `AUTOEXTEND MAXSIZE` without checking real filesystem/ASM space.** That only raises a config ceiling without creating capacity.
- **Never set every datafile to unlimited.** One runaway file can consume all shared disk and take down other services.
- **Never assume `DELETE FROM table` immediately frees filesystem space.** Extents and file sizes have separate lifecycles; reclaim/shrink needs case-by-case evaluation.
- **Never delete backups/archives just because they look "old"** without checking retention, standbys, recovery windows, and backup tooling.
- **Never assume adding a datafile is always valid.** Bigfile tablespaces and certain file-management setups follow different rules from smallfile tablespaces; never run sample commands out of context.
- **Never confuse TEMP exhaustion from a runaway query with permanent tablespace exhaustion.** Adding table datafiles will not help a sort query starving for TEMP.

## 11. Sample Scenarios

### Scenario A — Autoextend Enabled Yet INSERT Still Fails

`APP_DATA` has a 40 GiB datafile with `AUTOEXTENSIBLE=YES` and `MAXBYTES=80 GiB`. `DBA_FREE_SPACE` reports near 0 GiB, and the filesystem has only 500 MiB left. An `INSERT` needing a large extent fails.

**Reasoning:** Autoextend only describes permission to request file growth up to the ceiling; physical storage is insufficient. Verify the exact error and address mountpoint/ASM capacity, or apply controlled data management. Enabling autoextend again does nothing.

### Scenario B — Tablespace at 70% Yet Could Fill in 3 Days

A tablespace uses 70 GiB out of 100 GiB usable capacity, growing net 10 GiB/day due to an import wave. The remaining 30 GiB gives roughly 3 days if that rate continues.

**Reasoning:** An 80% threshold alert has not fired yet, whereas a **days to full ≤ 7** alert catches this early. Confirm whether the import is ongoing or a one-time spike before provisioning permanent storage.

### Scenario C — Data Tablespace Has Room Yet Applications Cannot Write

`APP_DATA` still has 30 GiB free, while `V$RECOVERY_FILE_DEST` shows the FRA near its limit and the alert log shows archiver errors.

**Reasoning:** This is not necessarily an `APP_DATA` issue. Oracle must write redo and archive per configuration; if archiving stalls, transactions can be impacted. Inspect FRA/archived redo/backup policies instead of expanding the application tablespace.

### Scenario D — TEMP Spikes Sharply at 02:00

During the day, TEMP sits nearly idle. At 02:00, a reporting job runs large hash joins/sorts, fills TEMP, and returns TEMP to reusable state once the job finishes.

**Reasoning:** Sampling once daily at 09:00 misses the spike completely. Monitor `V$TEMPSEG_USAGE` while the job runs and sample at minute/hour granularity; then inspect plans, statistics, query patterns, and capacity needs.

### Scenario E — ASM Has `FREE_MB` Left Yet Lacks Usable Capacity

A mirrored disk group shows positive `FREE_MB` while `USABLE_FILE_MB` is low. A report plotting only `FREE_MB/TOTAL_MB` assumes the disk group is healthy.

**Reasoning:** Read `USABLE_FILE_MB` and redundancy rules rather than applying simple filesystem math to ASM. When adding capacity, also inspect disk group state and rebalancing capability.

### Scenario F — Large Table No Longer Growing

A historical table occupies 80 GiB yet barely changed over the last 30 days. A smaller log table is only 8 GiB yet grows 3 GiB/day.

**Reasoning:** A "top 10 largest segments" list shows where space currently sits, whereas **per-object growth snapshots** reveal where upcoming exhaustion risk actually originates.

## 12. Hands-On Practice: Building a Capacity and Alert Forecast Report

You can run this exercise on an Oracle Database lab, or read and calculate manually if you lack dictionary view privileges. Do not delete data or change configurations.

### Part A — Record Current State

1. Query `DBA_TABLESPACE_USAGE_METRICS` to list the tablespaces with the highest `USED_PERCENT`.
2. Pick one permanent tablespace; inspect `DBA_DATA_FILES` and free extents to distinguish **current file size**, **free extents**, and **configured max**.
3. Identify whether the backend is filesystem or ASM. Locate the matching mountpoint or disk group.
4. If permitted, read FRA status to see if archives/backups pose a separate risk.
5. Write a conditional conclusion: which tablespace nears its *logical* limit, which storage nears its *physical* limit, and where more metrics are needed.

Report template:

| Time | Object | Used | Capacity/Limit | Headroom | Growth/Day | Days to Full | Status |
|---|---|---:|---:|---:|---:|---:|---|
| 09:00 | APP_DATA | 76 GiB | 100 GiB | 24 GiB | 2 GiB | ≈12 days | Warning by forecast |
| 09:00 | APP_INDEX | 18 GiB | 50 GiB | 32 GiB | 0.2 GiB | ≈160 days | Monitor |
| 09:00 | FRA | 45 GiB | 50 GiB | 5 GiB | variable | calculate separately | Critical by percentage |

The numbers in this table are **illustrative only**; they do not represent a live instance. For the FRA, also factor in reclaim/retention and archive generation rates for a sound forecast.

### Part B — Calculate Growth Rate

Suppose you have 5 practice samples:

| Day | APP_DATA Used |
|---|---:|
| Day 1 | 50 GiB |
| Day 2 | 52 GiB |
| Day 3 | 56 GiB |
| Day 4 | 57 GiB |
| Day 5 | 62 GiB |

Net growth over 4 days is `62 - 50 = 12 GiB`, averaging `12 / 4 = 3 GiB/day`. If usable capacity is 80 GiB, measured headroom is 18 GiB, giving a linear forecast of roughly `18 / 3 = 6 days`. Explain why this table has an **uneven** growth rate and why days jumping by 4–5 GiB/day must be tracked when designing alerts.

### Part C — Write Alert Rules

From the data above, build rules with two conditions:

- Warning if usage ≥ 80% **or** forecasted time to limit ≤ 14 days.
- Critical if usage ≥ 90% **or** forecasted time ≤ 7 days.

For `APP_DATA` at 62/80 GiB, usage is 77.5%; the 6-day forecast must escalate severity to **Critical per the example policy** even though current usage is under 80%. Note explicitly that the calculation assumes physical capacity is truly available and the growth rate remains constant.

### Part D — Write a Short Runbook

Write a brief guide for an on-call engineer: when `APP_DATA` triggers Critical, which dictionary views, storage paths, growing segments, batch vs. query growth sources to inspect in order, and when to escalate to storage/backup administrators.

The goal is to make alerts **actionable**, not merely a red number on a screen.

## 13. Remembering the Oracle Capacity Monitoring Workflow

```text
Observe properly across layers
        │
        ├── Tablespace / Datafile / Segment
        ├── TEMP / UNDO
        ├── Filesystem or ASM
        └── FRA / Archived redo / Backup
        │
        ▼
Store timestamped history with exact database/PDB
        │
        ▼
Measure growth by workload and time window
        │
        ▼
Estimate real headroom and time to limit
        │
        ▼
Alert on % + remaining GiB + days to full
        │
        ▼
Investigate root cause, remediate safely, re-measure
```

To avoid out-of-space incidents, do not wait until Oracle reports an inability to allocate extents. A sound monitoring model tracks **current usage, growth rate, and real storage limits**, while independently watching high-risk areas like TEMP and FRA. Knowing all involved layers and maintaining historical data lets you plan capacity proactively and isolate incidents faster without risking data.
