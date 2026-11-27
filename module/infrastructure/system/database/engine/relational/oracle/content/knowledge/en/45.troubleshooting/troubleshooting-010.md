# ORA-01652, ORA-01653, and Insufficient Temporary or Storage Space Errors

## 1. Distinguishing TEMP Space Errors from Data Tablespace Errors

Oracle requires storage space for both persistent data and intermediate operations. Two common errors have distinct meanings:

- **ORA-01652**: Oracle cannot extend a temporary segment in the named tablespace. Commonly triggered by large sorts, hash joins, hash aggregations, index builds, temporary tables, or operations spilling intermediate data to `TEMP`.
- **ORA-01653**: Oracle cannot extend a table segment in the named tablespace. This usually indicates running out of space in the permanent tablespace holding the table.

Example error messages:

```text
ORA-01652: unable to extend temp segment by 128 in tablespace TEMP
ORA-01653: unable to extend table APP.ORDERS by 8192 in tablespace APP_DATA
```

The numbers `128` or `8192` in the message represent the number of blocks Oracle tried to allocate for the segment at failure time—not MB or GB. To convert to capacity, you need the tablespace's block size.

Do not handle both errors with the same action. If the error occurs in `TEMP`, adding a datafile to the table's permanent tablespace will not fix it. Conversely, if a table cannot extend in `APP_DATA`, expanding `TEMP` will not give the permanent segment more room.

## 2. TEMP Tablespaces and Temporary Segments

### 2.1. When Is TEMP Used?

Oracle uses temporary tablespaces to store intermediate data that exceeds the working memory allocated to an operation. Common scenarios:

- `ORDER BY`, `GROUP BY`, `DISTINCT` requiring large sorts.
- Hash joins or hash aggregations on large datasets spilling to `TEMP`.
- Creating or rebuilding indexes.
- Certain table creations, partition operations, materialized views, or intermediate processing.
- Global temporary tables or operations explicitly using temporary segments.

A SQL statement may fit entirely in PGA when memory is sufficient, but when workareas are insufficient, Oracle spills part or all intermediate data to `TEMP`. Therefore, `TEMP` usage depends on SQL, execution plans, data volume, concurrency, and PGA/workarea configuration.

### 2.2. TEMP vs. PGA

PGA is server-process private memory used for sorts, hashes, and workarea operations. `TEMP` is disk storage holding intermediate data that cannot fit in memory. These two components are related but not interchangeable.

| Component | Role | Investigation Signals |
|---|---|---|
| PGA/workarea | Processes sorts/hashes in memory | PGA pressure, multipass workareas, memory allocation errors |
| TEMP tablespace | Stores spilled sort/hash/temp segments on disk | ORA-01652, rising `TEMP` usage, tempfile unable to extend |
| Permanent tablespace | Stores persistent table/index/LOB segments | ORA-01653, ORA-01654, ORA-01691 |
| Undo tablespace | Stores undo records for rollback/read consistency | ORA-30036, undo space pressure |

If `ORA-04030` occurs, that is a failure to allocate process PGA memory, distinct from `ORA-01652` (lack of temporary segment space). If `ORA-30036` occurs, investigate the undo tablespace instead of merely expanding `TEMP`.

### 2.3. When Are Temporary Segments Freed?

A temporary segment can remain allocated as long as the operation or transaction needs it. Once the SQL/transaction finishes, Oracle can reuse the allocated extents in `TEMP`; therefore, seeing a tempfile with allocated space does not mean all of that space is actively held by one session.

`TEMP` tempfiles normally retain their allocated OS/storage file size for future reuse. Distinguish between allocated tempfile size, actively used space, and remaining extensible headroom.

## 3. Permanent Tablespaces and Segment Extension

### 3.1. Which Objects Relate to ORA-01653?

`ORA-01653` explicitly identifies a table unable to extend in its tablespace. The segment may need a new extent due to:

- Inserting new data.
- Updates lengthening rows and requiring additional blocks/extents.
- Partition or subpartition growth.
- Data-generation operations expanding the table segment.

Related errors help identify the segment type:

| Error Code | Common Object / Scenario |
|---|---|
| `ORA-01652` | Temporary segment unable to extend in `TEMP` or named tablespace |
| `ORA-01653` | Table segment unable to extend |
| `ORA-01654` | Index segment unable to extend |
| `ORA-01658` | Unable to create initial extent for segment in tablespace |
| `ORA-01691` | LOB segment unable to extend |
| `ORA-01950` | User lacks sufficient quota on tablespace |
| `ORA-30036` | Undo segment unable to extend in undo tablespace |

The error message is your first clue. Identify the exact object, owner, tablespace, files, and root cause before adding capacity.

### 3.2. Tablespace Shows Free Space Yet Still Fails to Extend

Total free space alone does not always explain the failure. Check:

- Whether datafiles have reached `MAXSIZE`.
- Whether `AUTOEXTEND` is enabled.
- Whether underlying filesystem/ASM storage has enough free space.
- Whether datafile size hit block-size/platform limits.
- Whether the tablespace uses uniform extents or autoallocate, and whether the requested extent fits the allocation policy.
- Whether the user has sufficient quota.
- Whether the PDB has an enforced storage limit.

With locally managed tablespaces, avoid thinking in terms of contiguous free space as in legacy fragmentation models. Oracle manages extents via bitmaps; nevertheless, extent sizes, file capacity, and underlying storage must still be checked.

## 4. Initial Diagnostic Procedure

### 4.1. Capture Exact Error Details

Record the entire error stack, not just the final line:

- Full ORA code and text.
- `SQL_ID`, SQL text, module/action, and client identifier if available.
- Timestamp, service, container/PDB, and instance where the error occurred.
- User/schema, target object, and tablespace named in the error.
- Operation type: `SELECT`, `INSERT`, `UPDATE`, `CREATE INDEX`, CTAS, batch, or maintenance job.
- Data volume and number of concurrent sessions.

If the error originates from an application, preserve the correlation ID to match against `V$SESSION` and the alert log. Never log passwords, sensitive bind values, or LOB payloads just to diagnose storage issues.

### 4.2. Identify Container and Tablespace

In SQL*Plus:

```sql
SHOW CON_NAME;

SELECT name, cdb, open_mode
FROM v$database;
```

In a CDB, pinpoint the exact PDB where the SQL executed. `DBA_*` queries inside a PDB reflect that PDB's metadata; from `CDB$ROOT`, query `CDB_*` views and keep `CON_ID` to separate containers. Never compare figures across PDBs while ignoring `CON_ID`.

### 4.3. Check Tablespace Types

```sql
SELECT tablespace_name,
       contents,
       status,
       bigfile,
       extent_management,
       allocation_type,
       block_size
FROM dba_tablespaces
ORDER BY tablespace_name;
```

`CONTENTS` shows `PERMANENT`, `TEMPORARY`, or `UNDO`; `BIGFILE` shows whether the tablespace has a single large datafile/tempfile or multiple smaller files; `BLOCK_SIZE` lets you convert block counts in error messages to bytes.

## 5. Diagnosing ORA-01652: Insufficient TEMP

### 5.1. Check Used and Free TEMP Space

`V$TEMP_SPACE_HEADER` reports metrics per tempfile:

```sql
SELECT tablespace_name,
       file_id,
       ROUND(bytes_used / 1024 / 1024, 2) AS used_mb,
       ROUND(bytes_free / 1024 / 1024, 2) AS free_mb,
       ROUND((bytes_used + bytes_free) / 1024 / 1024, 2) AS file_mb
FROM v$temp_space_header
ORDER BY tablespace_name, file_id;
```

Aggregate by `TEMP` tablespace:

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes_used) / 1024 / 1024, 2) AS used_mb,
       ROUND(SUM(bytes_free) / 1024 / 1024, 2) AS free_mb,
       ROUND(SUM(bytes_used + bytes_free) / 1024 / 1024, 2) AS allocated_mb
FROM v$temp_space_header
GROUP BY tablespace_name
ORDER BY tablespace_name;
```

These figures reflect allocated tempfile capacity and current used/free space inside existing files. They do not show how far tempfiles can autoextend; cross-check `DBA_TEMP_FILES`, `MAXBYTES`, and underlying storage.

### 5.2. Inspect Tempfiles, AUTOEXTEND, and MAXSIZE

```sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 2) AS current_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 2) AS max_mb,
       increment_by
FROM dba_temp_files
ORDER BY tablespace_name, file_id;
```

Key columns:

- `BYTES`: current tempfile size.
- `AUTOEXTENSIBLE`: `YES` if the file can grow automatically.
- `MAXBYTES`: configured maximum size when autoextend is enabled.
- `INCREMENT_BY`: number of blocks added per autoextend step.

If `AUTOEXTENSIBLE='NO'`, the tempfile will not grow automatically. If it has already reached `MAXBYTES`, enabling autoextend alone will not add space. Verify filesystem/ASM capacity and file limits before changing settings.

### 5.3. Find Sessions Consuming TEMP

```sql
SELECT u.username,
       s.sid,
       s.serial#,
       s.status,
       s.sql_id,
       s.module,
       s.action,
       u.tablespace,
       u.segtype,
       u.extents,
       u.blocks,
       ROUND(u.blocks * t.block_size / 1024 / 1024, 2) AS temp_mb
FROM v$tempseg_usage u
JOIN v$session s
  ON s.saddr = u.session_addr
 AND s.serial# = u.session_num
JOIN dba_tablespaces t
  ON t.tablespace_name = u.tablespace
ORDER BY u.blocks DESC;
```

`SEGTYPE` identifies temporary segment types such as sort, hash, or temporary table. `SQL_ID`, `MODULE`, and `ACTION` pinpoint the SQL/application consuming `TEMP`. A single session can hold multiple segment rows; aggregate by session or `SQL_ID` when reporting total consumption.

In RAC, use `GV$TEMPSEG_USAGE` and `GV$SESSION`, joining on `INST_ID`:

```sql
SELECT u.inst_id,
       u.username,
       s.sid,
       s.serial#,
       s.sql_id,
       s.module,
       u.tablespace,
       u.segtype,
       ROUND(SUM(u.blocks * t.block_size) / 1024 / 1024, 2) AS temp_mb
FROM gv$tempseg_usage u
JOIN gv$session s
  ON s.inst_id = u.inst_id
 AND s.saddr = u.session_addr
 AND s.serial# = u.session_num
JOIN dba_tablespaces t
  ON t.tablespace_name = u.tablespace
GROUP BY u.inst_id, u.username, s.sid, s.serial#, s.sql_id,
         s.module, u.tablespace, u.segtype
ORDER BY temp_mb DESC;
```

Verify column names and view privileges for your release and environment. In CDB/RAC, include container/instance context so sessions with identical SIDs are never confused.

### 5.4. Inspect Sort Segment Activity

```sql
SELECT tablespace_name,
       current_users,
       total_extents,
       used_extents,
       free_extents,
       max_used_size
FROM v$sort_segment
ORDER BY tablespace_name;
```

This view shows sort segment status at the tablespace level. `TEMP` extents are reusable; therefore, do not rely solely on `USED_EXTENTS` at one instant to conclude that a specific query filled `TEMP`.

### 5.5. Identify a User's Default TEMP Tablespace

```sql
SELECT username, temporary_tablespace
FROM dba_users
WHERE username = 'APP_USER';
```

A user may be assigned a different `TEMP` tablespace than the DBA assumed. Furthermore, the database may use a temporary tablespace group. Verify the actual mapping and session configuration before adding files to an unrelated tablespace.

## 6. Diagnosing ORA-01653: Insufficient Permanent Tablespace

### 6.1. Inspect Datafile Sizes and Growth Headroom

```sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 2) AS current_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 2) AS max_mb,
       increment_by
FROM dba_data_files
ORDER BY tablespace_name, file_id;
```

If a file has reached `MAXBYTES`, autoextend can no longer grow it. If `AUTOEXTENSIBLE='NO'`, the file remains fixed in size. Also verify storage capacity; configuring a larger `MAXSIZE` does not create physical disk space.

### 6.2. Total Allocated and Configured Maximum Space

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS allocated_mb,
       ROUND(SUM(CASE
                   WHEN autoextensible = 'YES' THEN maxbytes
                   ELSE bytes
                 END) / 1024 / 1024, 2) AS configured_max_mb,
       ROUND(SUM(CASE
                   WHEN autoextensible = 'YES'
                   THEN GREATEST(maxbytes - bytes, 0)
                   ELSE 0
                 END) / 1024 / 1024, 2) AS potential_growth_mb
FROM dba_data_files
GROUP BY tablespace_name
ORDER BY tablespace_name;
```

`POTENTIAL_GROWTH_MB` is the remaining configured file headroom, not a guarantee that physical storage has enough space. If the filesystem/ASM runs out of space, autoextend will fail before reaching `MAXBYTES`.

### 6.3. Inspect Free Extents and Largest Free Extent

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS free_mb,
       ROUND(MAX(bytes) / 1024 / 1024, 2) AS largest_free_extent_mb,
       COUNT(*) AS free_extent_count
FROM dba_free_space
GROUP BY tablespace_name
ORDER BY tablespace_name;
```

For locally managed tablespaces, total free space, allocation policy, and file extensibility are the key factors. If the error requests an extent larger than the largest available free extent, check the tablespace allocation type, file growth, and file limits. Do not immediately run `COALESCE`/rebuilds just because free space spans multiple extents; with locally managed tablespaces, Oracle manages extents and does not require all free space to be contiguous as in older models.

### 6.4. Find the Largest Segments in the Tablespace

```sql
SELECT owner,
       segment_name,
       partition_name,
       segment_type,
       tablespace_name,
       ROUND(bytes / 1024 / 1024, 2) AS size_mb
FROM dba_segments
WHERE tablespace_name = 'APP_DATA'
ORDER BY bytes DESC
FETCH FIRST 30 ROWS ONLY;
```

Replace `APP_DATA` with the actual tablespace. The output identifies tables, indexes, LOBs, and partitions consuming the most space. The largest segment is not always the sole cause; correlate growth rate, failure timestamp, and the object named in the error stack.

### 6.5. Check User Quotas

```sql
SELECT username,
       tablespace_name,
       bytes,
       max_bytes
FROM dba_ts_quotas
WHERE username = 'APP_USER'
ORDER BY tablespace_name;
```

If the error is `ORA-01950`, the user ran out of quota even though the tablespace has free space. Grant additional quota in a controlled manner:

```sql
ALTER USER app_user QUOTA 5G ON app_data;
```

Use `UNLIMITED` only when security policy and capacity planning allow it. User quota is a separate limit from datafile/tablespace capacity.

## 7. Checking Underlying Storage: Filesystem, ASM, and File Limits

### 7.1. Filesystem

For datafiles/tempfiles on a filesystem, inspect the mount point hosting the files:

```bash
df -h /u02/oradata
df -i /u02/oradata
```

`df -h` checks block capacity; `df -i` checks inodes. A filesystem can run out of inodes even with free bytes remaining. Also check OS quotas, read-only mounts, owner/group permissions, and storage alerts.

The path above is illustrative only. Use the actual mount point from `DBA_DATA_FILES` or `DBA_TEMP_FILES`.

### 7.2. ASM Disk Group

If files reside in ASM, check disk groups from the ASM instance or an authorized view:

```sql
SELECT name,
       state,
       type,
       total_mb,
       free_mb,
       usable_file_mb
FROM v$asm_diskgroup
ORDER BY name;
```

`USABLE_FILE_MB` is critical when ASM uses redundancy because allocatable file space depends on mirroring/redundancy and disk group state. `FREE_MB` does not necessarily equal safely allocatable space.

If an ASM disk group is nearing capacity, handle storage via ASM procedures, such as adding disks or rebalancing per design. Never delete ASM files manually with OS tools.

### 7.3. Datafile Limits and Bigfile Tablespaces

Each datafile has a maximum size limit depending on block size, platform, and Oracle release. When one file cannot grow further, add another datafile if the tablespace is smallfile and storage permits.

A bigfile tablespace contains only a single large datafile. You cannot add multiple datafiles as with smallfile; resize or enable autoextend on the existing file within supported limits. Check the `BIGFILE` column in `DBA_TABLESPACES` before choosing a command.

### 7.4. PDB Storage Limits

In a CDB, a PDB can have an administrative storage limit. Identify which PDB raised the error and have the CDB DBA inspect storage limits/container quotas if overall file capacity appears sufficient yet the PDB cannot extend. Never raise a PDB limit without confirming resource allocation policy.

## 8. Resolving ORA-01652

### 8.1. Enable Extensibility on Existing TEMP

If a tempfile lacks autoextend and storage has headroom, enable autoextend with an explicit increment and cap:

```sql
ALTER DATABASE TEMPFILE '/u02/oradata/DB/temp01.dbf'
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

Path and sizes are examples. `MAXSIZE` must stay within file, filesystem/ASM, and capacity-plan limits. Avoid `MAXSIZE UNLIMITED` without storage monitoring in place.

### 8.2. Resize a Tempfile

```sql
ALTER DATABASE TEMPFILE '/u02/oradata/DB/temp01.dbf'
  RESIZE 20G;
```

Growing a file requires physical storage. Shrinking can fail if the tail of the file holds active extents; never shrink `TEMP` while sessions are actively using it.

### 8.3. Add a Tempfile to a Smallfile Temporary Tablespace

```sql
ALTER TABLESPACE temp
  ADD TEMPFILE '/u02/oradata/DB/temp02.dbf'
  SIZE 10G
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

When using Oracle Managed Files or ASM, specify the `DB_CREATE_FILE_DEST`/ASM disk group per configuration:

```sql
ALTER TABLESPACE temp
  ADD TEMPFILE '+DATA'
  SIZE 10G
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

Adding files increases total `TEMP` capacity but does not fix SQL generating excessive temporary data. If workload continually outgrows capacity, tune SQL or redesign data processing.

### 8.4. Bigfile TEMP Tablespaces

A bigfile tablespace has only one tempfile. Do not attempt to add a second tempfile as in the smallfile example; check file limits, storage, and resize/autoextend the existing tempfile within release limits.

### 8.5. Reduce TEMP Demand

Investigate the `SQL_ID` consuming large amounts of `TEMP`:

- Inspect the execution plan and actual row counts.
- Inspect sort/hash operations, join cardinality, and statistics.
- Eliminate unnecessary `SELECT DISTINCT` or `ORDER BY` clauses.
- Ensure predicates filter early and join keys are appropriate.
- Check indexes and partition pruning where applicable.
- Check whether faulty join cardinality generates huge intermediate results.
- For batch jobs, chunk data by key range/partition instead of processing one massive set.

Do not arbitrarily raise `PGA_AGGREGATE_TARGET` or `PGA_AGGREGATE_LIMIT`. Larger PGA can reduce spills in some cases, depending on total memory, concurrent sessions, and system limits. Measure workarea usage before changing parameters.

## 9. Resolving ORA-01653

### 9.1. Enable Autoextend on a Datafile

```sql
ALTER DATABASE DATAFILE '/u02/oradata/DB/app_data01.dbf'
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

Enable only when underlying storage has sufficient capacity and the maximum cap is approved. Autoextend keeps applications running, yet without caps and monitoring it can fill the filesystem or ASM disk group.

### 9.2. Resize an Existing Datafile

```sql
ALTER DATABASE DATAFILE '/u02/oradata/DB/app_data01.dbf'
  RESIZE 20G;
```

Growing a file requires physical storage. With bigfile tablespaces, the existing file can be resized up to Oracle/platform limits. With smallfile tablespaces, adding a new datafile is more appropriate if the current file nears its maximum size limit.

### 9.3. Add a Datafile to a Smallfile Tablespace

```sql
ALTER TABLESPACE app_data
  ADD DATAFILE '/u02/oradata/DB/app_data02.dbf'
  SIZE 10G
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

With ASM:

```sql
ALTER TABLESPACE app_data
  ADD DATAFILE '+DATA'
  SIZE 10G
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

If using OMF with `DB_CREATE_FILE_DEST` configured, the filename can be omitted per supported Oracle syntax. Verify storage conventions and file paths before executing; never use example paths in production.

### 9.4. Bigfile Tablespaces

With a bigfile tablespace, do not add a second datafile. Resize the existing datafile or configure autoextend within valid limits. Check `DBA_TABLESPACES.BIGFILE` and block/file limits beforehand.

### 9.5. Handle Quotas or Abnormal Segment Growth

If the actual error is `ORA-01950`, grant appropriate quota to the user instead of adding files to the tablespace. If a segment is growing abnormally, determine the data or job cause:

- Log/audit tables growing without retention policies.
- Batch inserts running repeatedly or producing duplicate rows.
- Index/LOB growth driven by workload or application changes.
- New partitions not created or placed in the right tablespace.
- Index rebuilds or table moves temporarily needing extra space.

Never drop tables/indexes or purge data solely because of large size. Obtain owner confirmation on retention, dependencies, and recovery requirements.

## 10. Reclaiming Space Safely

### 10.1. TEMP Usage by Active Queries

If an active query consumes excessive `TEMP`, first identify `SQL_ID`, session, module, and runtime. Inspect the execution plan, SQL Monitor (if licensed/authorized), and workareas. Ask the application owner whether the query can be safely canceled.

Never kill a session solely because it tops the `TEMP` usage list. It may be a legitimate batch job; killing it can trigger rollbacks, retry storms, or cascading application failures. Terminate only with operational approval and clear understanding of impact.

### 10.2. Unneeded Data Segments

For permanent tablespaces, delete or archive data only per approved retention policies. Bulk deletes generate undo/redo and do not immediately return segment space to the tablespace. Shrinking, moving, or rebuilding objects may be required depending on object type and Oracle rules—and those operations themselves require additional `TEMP` or permanent free space.

### 10.3. Recycle Bin

Dropped objects may remain in the recycle bin and continue occupying space until purged. Check:

```sql
SELECT owner,
       original_name,
       object_name,
       type,
       droptime,
       space
FROM dba_recyclebin
ORDER BY droptime;
```

Purge only after the owner/DBA confirms flashback drop or object recovery is unnecessary. `PURGE DBA_RECYCLEBIN` has broad scope; prefer purging specific objects or tablespaces with approval and full awareness of lost recoverability.

### 10.4. Never Delete Tempfiles via OS Commands

Tempfiles must be managed through SQL/Oracle. Never use `rm`, PowerShell `Remove-Item`, or OS tools to delete files managed by Oracle. When a tempfile must be dropped, use the appropriate Oracle SQL command and verify the file is no longer in use.

## 11. TEMP Tablespace Groups and User Assignment

Oracle can configure temporary tablespace groups to distribute `TEMP` demand across multiple temporary tablespaces. Check:

```sql
SELECT tablespace_name, group_name
FROM dba_tablespace_groups
ORDER BY group_name, tablespace_name;

SELECT username, temporary_tablespace
FROM dba_users
ORDER BY username;
```

If a user is assigned a tablespace group, adding a tempfile to one member increases group capacity, though you still need to check storage, load distribution, and status across all members. Never change the database-wide default temporary tablespace just to fix one user's error without evaluating other sessions.

## 12. Monitoring in CDB and RAC

### 12.1. CDB/PDB

In a CDB, the same tablespace name can exist across multiple containers. From root, query `CDB_*` views with `CON_ID` to see which PDB owns each file:

```sql
SELECT con_id,
       tablespace_name,
       file_id,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM cdb_temp_files
ORDER BY con_id, tablespace_name, file_id;
```

For permanent datafiles:

```sql
SELECT con_id,
       tablespace_name,
       file_id,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM cdb_data_files
ORDER BY con_id, tablespace_name, file_id;
```

Inspect the exact PDB raising the error and its PDB storage limit. Never add files to root or another PDB simply because they share the same tablespace name.

### 12.2. RAC

In RAC, instances may share `TEMP` tablespaces/datafiles while sessions and `TEMP` usage are tracked per instance. Use `GV$SESSION`, `GV$TEMPSEG_USAGE`, and `INST_ID` to locate which node hosts each session. Avoid diagnosing or killing a session with a matching SID on the wrong instance.

### 12.3. Setting Up Alerts

Monitor:

- `TEMP` used/free and peak-hour growth rate.
- Datafile allocated/current/max bytes and autoextend status.
- Filesystem/ASM usable capacity.
- Tablespace growth and top segments by owner/object.
- `TEMP` usage by `SQL_ID`, module, and session.
- Undo usage and long-running transactions if undo errors occur.
- PDB storage limits and space distribution across PDBs.

Alert well before capacity hits 100%, setting thresholds based on real headroom and lead time needed to provision storage. Do not alert solely on percentages; a rapidly growing tablespace may require alerting even while utilization percentage is still moderate.

## 13. Sample Troubleshooting Workflows

### 13.1. Example: ORA-01652 in a Large Report

1. Retrieve `SQL_ID` from application logs or `V$SESSION`.
2. Query `V$TEMPSEG_USAGE` to identify the session/`SQL_ID` consuming `TEMP`.
3. Inspect `V$TEMP_SPACE_HEADER` and `DBA_TEMP_FILES` for free space, autoextend, and max size.
4. Check filesystem/ASM capacity and PDB limits.
5. Inspect the execution plan, sort/hash operations, cardinality estimates, and query result size.
6. If immediate service recovery is required, expand `TEMP` in a controlled way after confirming storage capacity.
7. Afterward, tune the SQL, reduce intermediate datasets, or chunk batches; monitor `TEMP` usage post-deployment.

### 13.2. Example: ORA-01653 During Insert into Orders Table

1. Read the full error to identify owner/table/tablespace.
2. Confirm the PDB and verify the tablespace is permanent.
3. Inspect `DBA_DATA_FILES`, `AUTOEXTENSIBLE`, `MAXBYTES`, and free extents.
4. Check user quota, ASM/filesystem capacity, and PDB storage limit.
5. Inspect segment/partition growth, top objects, and data growth rate.
6. If capacity is needed, resize or add a datafile for smallfile; for bigfile, resize/autoextend the existing file.
7. Confirm inserts succeed and set up alerts/retention policies to prevent recurrence.

## 14. Pre-Capacity-Change Checklist

| Question | What to Verify |
|---|---|
| Is the error ORA-01652 or ORA-01653? | Determine whether it is `TEMP` or a permanent segment |
| Which PDB owns the tablespace? | Avoid altering the wrong container |
| Is the tablespace TEMP, PERMANENT, or UNDO? | Choose datafile vs. tempfile appropriately |
| Is AUTOEXTEND enabled? | Check per file, not just at the tablespace level |
| Has MAXBYTES or a file limit been reached? | Determine remaining growth capacity under config |
| Do ASM/filesystems have enough space? | Confirm physical storage and usable capacity |
| Is the tablespace BIGFILE? | Choose resize vs. add file appropriately |
| Does the user have quota? | Distinguish ORA-01950 from full tablespaces |
| Which SQL/session is using TEMP? | Identify cause and owner before canceling queries |
| Is growth from valid or abnormal data? | Verify retention, partitions, batches, and jobs |
| Is monitoring configured? | Set alert thresholds and headroom post-change |

## 15. Key Principles to Remember

- ORA-01652 relates to temporary segments/`TEMP`; ORA-01653 relates to table segments in permanent tablespaces.
- Active `TEMP` usage, allocated tempfile size, and free disk storage are three distinct metrics.
- `V$TEMPSEG_USAGE`, `V$TEMP_SPACE_HEADER`, and `DBA_TEMP_FILES` diagnose `TEMP`; `DBA_DATA_FILES`, `DBA_FREE_SPACE`, and `DBA_SEGMENTS` diagnose permanent tablespaces.
- `AUTOEXTEND` operates only within `MAXSIZE`, file/platform limits, and underlying storage limits.
- Bigfile tablespaces cannot add a second datafile like smallfile; resize or autoextend the existing file instead.
- Check ASM `USABLE_FILE_MB`, filesystem space/inodes, and PDB storage limits before growing files.
- `ORA-01950` is a quota error; `ORA-30036` is an undo error; `ORA-04030` is a PGA error—never confuse them with `TEMP`.
- Find the SQL/session consuming `TEMP` and tune sorts/hashes/cardinality; expanding `TEMP` adds capacity without removing the SQL cause.
- Never kill sessions, drop objects, purge the recycle bin, or delete OS files without assessing impact and obtaining approval.
- Track capacity, growth rate, headroom, and alerts so you act before tablespaces run dry.

## Oracle References

- [Oracle Database 19c Error Messages — ORA-01652](https://docs.oracle.com/en/error-help/db/ora-01652/)
- [Oracle Database 19c Error Messages — ORA-01653](https://docs.oracle.com/en/error-help/db/ora-01653/)
- [Oracle Database 19c Administrator's Guide — Managing Tablespaces](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tablespaces.html)
- [Oracle Database 19c Administrator's Guide — Managing Temporary Tablespaces](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tablespaces.html)
- [Oracle Database 19c Reference — DBA_DATA_FILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DATA_FILES.html)
- [Oracle Database 19c Reference — DBA_TEMP_FILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TEMP_FILES.html)
- [Oracle Database 19c Reference — V$TEMPSEG_USAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TEMPSEG_USAGE.html)
- [Oracle Database 19c Reference — V$TEMP_SPACE_HEADER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TEMP_SPACE_HEADER.html)
- [Oracle Database 19c Reference — DBA_FREE_SPACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_FREE_SPACE.html)
- [Oracle Database 19c Reference — DBA_SEGMENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SEGMENTS.html)
