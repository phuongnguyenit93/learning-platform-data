# Creating Tablespaces, Configuring AUTOEXTEND, and Controlling MAXSIZE in Oracle Database

In Oracle Database, when needing to store additional application tables, indexes, or data, administrators must often decide **which tablespace will hold the data**, **the initial datafile size**, and **the maximum permitted growth**. The two options `AUTOEXTEND` and `MAXSIZE` help control file expansion, yet they do not guarantee that the server always has enough physical storage capacity remaining.

For example, suppose a datafile is created at **2 GiB**, with `AUTOEXTEND ON NEXT 256M MAXSIZE 10G`. The file can grow when Oracle needs more extents, subject to applicable conditions, yet **cannot exceed 10 GiB** due to configuration. If space runs out on the filesystem/ASM disk group or another limit is hit, growth can fail before reaching 10 GiB.

This lesson guides you through creating and managing tablespaces in **Oracle Relational Database Engine**, from basic SQL syntax to practical capacity management and operational scenarios.

> Commands that create, grow, shrink, and add datafiles **alter storage structure**. Practice on a test database, use valid server paths, hold appropriate privileges, and check backup/monitoring procedures before applying to a live environment.

## 1. What Is a Tablespace?

A **tablespace** is a **logical storage** unit of Oracle Database. A tablespace can contain **segments**, such as table segments and index segments; segments are organized into extents and data blocks. Physical data of a permanent tablespace is stored in one or more **datafiles**.

```text
                    ORACLE DATABASE
                          |
                     Tablespace
                    APP_DATA (logical)
                          |
             +------------+------------+
             |                         |
      Datafile 01                  Datafile 02
      app_data01.dbf               app_data02.dbf
      size 2 GiB                   size 2 GiB
      max  10 GiB                  max  10 GiB
             |                         |
             +------------+------------+
                          |
                 Segments / Extents
                 Tables, Indexes, ...
```

A tablespace is **not** an operating system directory. The create tablespace statement specifies how Oracle manages the logical storage unit and underlying physical files.

### 1.1. Distinguishing Capacity Layers

| Layer | Example | Unit and Meaning |
|---|---|---|
| Database | `ORCL` or a PDB | Includes multiple tablespaces serving system and application data |
| Tablespace | `APP_DATA` | Logical grouping containing segments |
| Datafile | `app_data01.dbf` | Physical file with current size and growth limit |
| Segment | Table `ORDERS`, index `IDX_ORDERS` | Object consuming extents in the tablespace |
| Extent | A set of Oracle blocks | Unit Oracle allocates when a segment needs more space |
| Oracle block | e.g., 8 KiB block | Fundamental logical storage/I/O unit inside the database |

An **allocated datafile** differs from **used data in segments**: a 2 GiB file may still have many free extents for Oracle to allocate without needing to increase the file size yet.

### 1.2. Three Common Tablespace Types

| Type | Related File | What Is It Used For? | Notes on Expansion |
|---|---|---|---|
| **Permanent** | `DATAFILE` | Tables, indexes, materialized views, and persistent segments | Can use `ADD DATAFILE` in smallfile tablespaces |
| **Temporary** | `TEMPFILE` | Temporary space for sorts, hashes, and tasks needing TEMP | Uses `TEMPFILE` syntax; monitor TEMP capacity separately |
| **Undo** | Typically `DATAFILE` | Stores undo for rollback, read consistency, and recovery | Must account for undo retention, workload, and undo configuration |

Do not create a permanent tablespace and use it as a substitute for a temporary tablespace. File and space management mechanisms differ.

### 1.3. Smallfile vs. Bigfile

Oracle distinguishes two tablespace structural types:

- **Smallfile tablespace**: the standard type; can contain **multiple datafiles**. When individual files exhaust their growth headroom, you can add new datafiles if limits and infrastructure allow.
- **Bigfile tablespace**: designed to contain **a single very large datafile** (or a single tempfile for a bigfile temporary tablespace, per its corresponding type). Resize operations focus on that single file; you cannot resolve space exhaustion by adding a second datafile like a smallfile.

File size limits depend on the **Oracle block size** and tablespace type. Architecturally, smallfiles typically have a ceiling around **2²² blocks/file**, whereas bigfiles have around **2³² blocks/file**; with an 8 KiB block, the theoretical ceilings are roughly **32 GiB** and **32 TiB**, respectively. Exact limits also depend on version, operating system, storage, and database capabilities, so do not treat those figures as default quotas for every system.

## 2. Preparation Before Creating a Tablespace

Before running `CREATE TABLESPACE`, determine:

1. **Right target database/PDB**: in a CDB/PDB architecture, regular application tablespaces should be created **inside the PDB** holding the application's data.
2. **Tablespace type**: permanent, temporary, undo; smallfile or bigfile.
3. **Datafile location**: filesystem path, ASM, or Oracle Managed Files (OMF).
4. **Initial size**: `SIZE` should meet initial demand without over-allocating.
5. **Growth increment**: `NEXT` sized appropriately for the workload and remaining capacity.
6. **Growth ceiling**: `MAXSIZE` per file; calculate the total potential growth across the tablespace.
7. **Operational conditions**: DBA privileges, real storage space, monitoring, backups, and schema quota policy.

### 2.1. Checking Container and Baseline Parameters

With SQL*Plus/SQLcl:

```sql
SHOW CON_NAME;

-- May require privileges to query administrative views.
SELECT name, open_mode
FROM   v$pdbs
ORDER  BY name;

SHOW PARAMETER db_block_size;
SHOW PARAMETER db_create_file_dest;
```

To switch to a specific PDB, the account must hold appropriate privileges:

```sql
-- Example only for an administrative account with appropriate privileges.
ALTER SESSION SET CONTAINER = APPPDB;

SHOW CON_NAME;
```

The name `APPPDB` is only an example. Running `CREATE TABLESPACE` in `CDB$ROOT` places the tablespace in root under that context; it does not automatically become a PDB application tablespace.

### 2.2. Choosing How Filenames Are Managed

An **explicit path** works well when the DBA explicitly manages datafile locations:

```text
/u02/oradata/ORCL/app_data01.dbf
```

That path must exist / its parent directory must be writable by Oracle Database on the **database server**; it is not a folder on the laptop running SQL Developer.

With **Oracle Managed Files (OMF)**, Oracle automatically generates filenames and manages files under a configured destination (such as `DB_CREATE_FILE_DEST`). Example when OMF is configured:

```sql
SELECT name, value
FROM   v$parameter
WHERE  name = 'db_create_file_dest';
```

You can then use `DATAFILE SIZE ...` without specifying an explicit path. If using **ASM**, syntax and physical placement depend on the disk group and Oracle/ASM file management mechanisms; never guess and enter a regular filesystem path for ASM.

## 3. Creating a Permanent Tablespace with SIZE, AUTOEXTEND, and MAXSIZE

### 3.1. Smallfile Example with Explicit Path

Assume the database uses a filesystem and a valid path has been prepared. Create a tablespace for application data:

```sql
CREATE SMALLFILE TABLESPACE app_data
    DATAFILE '/u02/oradata/ORCL/app_data01.dbf'
        SIZE 2G
        AUTOEXTEND ON
        NEXT 256M
        MAXSIZE 10G
    EXTENT MANAGEMENT LOCAL
    SEGMENT SPACE MANAGEMENT AUTO;
```

**Meaning of each clause:**

| Component | Meaning |
|---|---|
| `CREATE SMALLFILE TABLESPACE app_data` | Creates a permanent smallfile tablespace named `APP_DATA` |
| `DATAFILE '...app_data01.dbf'` | Specifies the first physical file |
| `SIZE 2G` | Initial file size is 2 GiB as interpreted by Oracle units |
| `AUTOEXTEND ON` | Allows the file to grow automatically when Oracle needs to allocate more space |
| `NEXT 256M` | Configured growth increment is 256 MiB |
| `MAXSIZE 10G` | Maximum size limit for **this datafile**, not all files in the tablespace |
| `EXTENT MANAGEMENT LOCAL` | Locally manages extents using tablespace metadata |
| `SEGMENT SPACE MANAGEMENT AUTO` | Uses Automatic Segment Space Management, standard for permanent locally managed tablespaces |

The example above does not need a separate `ALTER DATABASE DATAFILE` statement to enable autoextend because it is configured right at creation time.

**Note:** `AUTOEXTEND ON` only enables growth capability when conditions permit. It **does not force the file to jump immediately to `MAXSIZE`** and does not guarantee every extension request will succeed.

### 3.2. Declaring Multiple Datafiles at Creation Time

A smallfile tablespace can be created with multiple files:

```sql
CREATE SMALLFILE TABLESPACE app_report
    DATAFILE
        '/u02/oradata/ORCL/app_report01.dbf'
            SIZE 1G AUTOEXTEND ON NEXT 128M MAXSIZE 6G,
        '/u03/oradata/ORCL/app_report02.dbf'
            SIZE 1G AUTOEXTEND ON NEXT 128M MAXSIZE 6G
    EXTENT MANAGEMENT LOCAL
    SEGMENT SPACE MANAGEMENT AUTO;
```

This configuration has **two files**, each starting at 1 GiB with a 6 GiB max. The combined ceiling across both files can reach about **12 GiB** if storage, database limits, and allocation conditions allow.

Never conclude that `MAXSIZE 6G` means **the entire tablespace** is capped at 6 GiB: this option belongs to the specification of **each individual datafile**.

### 3.3. Creating a Tablespace with OMF

If `DB_CREATE_FILE_DEST` is validly configured, you can let Oracle name the datafile:

```sql
CREATE TABLESPACE app_index
    DATAFILE SIZE 1G
        AUTOEXTEND ON NEXT 128M MAXSIZE 6G
    EXTENT MANAGEMENT LOCAL
    SEGMENT SPACE MANAGEMENT AUTO;
```

Oracle chooses the filename in the configured OMF destination. This approach helps avoid manual naming/path errors and fits many ASM/cloud environments.

Do not omit `DATAFILE` or an important parameter just because the system uses OMF without verifying the syntax and defaults of your exact Oracle release.

### 3.4. Creating a Bigfile Tablespace

Example with OMF configured:

```sql
CREATE BIGFILE TABLESPACE analytics_data
    DATAFILE SIZE 8G
        AUTOEXTEND ON NEXT 1G MAXSIZE 100G
    EXTENT MANAGEMENT LOCAL
    SEGMENT SPACE MANAGEMENT AUTO;
```

This is **one file** with an initial size of 8 GiB and a configured ceiling of 100 GiB. With a bigfile tablespace, you do not use `ALTER TABLESPACE ... ADD DATAFILE` to add a second file. Instead, when needed, you increase the size/limit of the existing file using supported syntax.

Choose bigfile based on capacity administration requirements, storage system, and architectural limits; never assume "bigfile" automatically makes every SQL query faster.

## 4. How Does AUTOEXTEND Work?

### 4.1. Distinguishing Extent Allocation from File Growth

When a table or index needs more room, Oracle attempts to allocate a new **extent** from existing free space inside the tablespace. If no suitable extents are available to satisfy the request, Oracle can extend a datafile that has `AUTOEXTEND` enabled within its configured limit.

```text
Object needs a new extent
          |
          v
Does tablespace have suitable free extents?
     |                         |
    Yes                       No
     |                         |
     v                         v
Allocate extent         Does datafile have AUTOEXTEND ON?
                              |             |
                             Yes           No
                              |             |
                              v             v
                      Still under MAXSIZE?  Out-of-extent error
                      Storage sufficient?   may occur
                          |       |
                         Yes     No
                          |       |
                          v       v
                    Grow file  Extension error
                          |
                          v
                    Allocate extent
```

In practice, allocation also depends on extent size, tablespace policy, storage infrastructure, quotas, and other limits. The diagram depicts the basic processing path.

### 4.2. SIZE, NEXT, and MAXSIZE Do Not Replace Each Other

Suppose:

```text
Datafile:       app_data01.dbf
SIZE:           2 GiB
AUTOEXTEND:     ON
NEXT:           256 MiB
MAXSIZE:        10 GiB
```

There are three numbers to distinguish:

- **2 GiB**: file size allocated by Oracle at creation time.
- **256 MiB**: `NEXT` increment configured when Oracle must extend the file; actual sizing must still obey allocation conditions and limits.
- **10 GiB**: ceiling of the file. `MAXSIZE` is not the space immediately occupied on disk upon creation.

If the file is currently 2 GiB, the configured remaining growth headroom before the ceiling is **8 GiB**. However, if the filesystem/ASM only has 3 GiB available, you cannot automatically expect the file to reach 10 GiB.

### 4.3. AUTOEXTEND ON vs. OFF

You can create a fixed-size datafile by omitting autoextend or setting it explicitly:

```sql
CREATE TABLESPACE audit_fixed
    DATAFILE '/u02/oradata/ORCL/audit_fixed01.dbf'
        SIZE 2G
        AUTOEXTEND OFF;
```

In this case, when allocatable space runs out, Oracle **does not automatically grow the file**. A DBA can manually resize the file or add a new datafile to a smallfile tablespace if allowed.

**Benefit of AUTOEXTEND ON:** reduces the risk of manual intervention each time data grows.  
**Risk if configured without control:** files grow unexpectedly, filling shared storage and potentially impacting other databases/applications.

There is no single optimal setting for every environment; combining `AUTOEXTEND ON` with an appropriate `MAXSIZE` and storage capacity alerts is usually best.

### 4.4. Is MAXSIZE UNLIMITED Truly Unlimited?

Syntax example:

```sql
CREATE TABLESPACE growth_test
    DATAFILE '/u02/oradata/ORCL/growth_test01.dbf'
        SIZE 1G
        AUTOEXTEND ON NEXT 128M MAXSIZE UNLIMITED;
```

`UNLIMITED` **does not mean infinite capacity**. Oracle remains bound by architectural limits on blocks per file, bigfile/smallfile type, operating system, filesystem/ASM disk group, quota policies, allocation mechanisms, and remaining free resources.

Some systems also use **thin provisioning**: logical capacity metrics or virtual limits may exceed available physical storage. Therefore, `MAXSIZE UNLIMITED` is not a capacity management plan.

### 4.5. MAXSIZE Is a Property of Each Datafile

Given this configuration:

```text
APP_DATA:
  app_data01.dbf   SIZE 2G  MAXSIZE 10G  AUTOEXTEND ON
  app_data02.dbf   SIZE 3G  MAXSIZE 12G  AUTOEXTEND ON

Current total file size: 5 GiB
Combined configured ceiling of 2 files: 22 GiB
Configured remaining growth headroom: 17 GiB
```

**These are sums across the listed files**, not an absolute ceiling guaranteed for the entire tablespace under every circumstance. Tablespace, database, PDB, OS, and storage constraints still apply.

Adding a new datafile with its own `MAXSIZE` to a smallfile tablespace raises the combined configured ceiling by the new file's limit.

## 5. Modifying AUTOEXTEND, NEXT, and MAXSIZE After Creation

### 5.1. Enabling Autoextend or Adjusting the Ceiling

Use `ALTER DATABASE DATAFILE` on an existing permanent/undo datafile:

```sql
ALTER DATABASE DATAFILE
    '/u02/oradata/ORCL/app_data01.dbf'
    AUTOEXTEND ON NEXT 256M MAXSIZE 16G;
```

Meaning: allows the file to grow in configured 256 MiB increments up to a new maximum of 16 GiB, **if file-type and environmental limits permit**.

This command **does not immediately change the current size to 16 GiB**. `MAXSIZE` is an upper limit, not a `RESIZE` operation.

### 5.2. Disabling Autoextend

```sql
ALTER DATABASE DATAFILE
    '/u02/oradata/ORCL/app_data01.dbf'
    AUTOEXTEND OFF;
```

Disabling autoextend **does not shrink the file**. The datafile keeps its current size; Oracle simply stops automatically extending the file via the autoextend mechanism.

If growth is needed after disabling it, the DBA must allocate more space manually or adjust the configuration.

### 5.3. Changing the Current File Size Immediately with RESIZE

Unlike setting MAXSIZE, `RESIZE` changes the **current size**:

```sql
ALTER DATABASE DATAFILE
    '/u02/oradata/ORCL/app_data01.dbf'
    RESIZE 4G;
```

If the file is currently 2 GiB and storage permits, the statement attempts to grow it to 4 GiB immediately. If the file is larger than 4 GiB, this is a **shrink** request, which succeeds only if used blocks/extents allow shrinking down to that size.

Errors during shrinking commonly happen because allocated data sits near the end of the file. `DBA_FREE_SPACE` reporting free space does not mean the tail end of the file is empty and can be `RESIZE`d arbitrarily.

### 5.4. Adding a Datafile to a Smallfile Tablespace

```sql
ALTER TABLESPACE app_data
    ADD DATAFILE '/u03/oradata/ORCL/app_data02.dbf'
        SIZE 2G
        AUTOEXTEND ON NEXT 256M MAXSIZE 12G;
```

This operation increases the tablespace's current size with a new datafile and sets a separate growth ceiling for that file. For a bigfile tablespace, adding a second **ADD DATAFILE** is not supported: you must modify the existing large file.

### 5.5. Choosing Commands When Approaching Capacity

| Situation | Common Action | What to Check |
|---|---|---|
| Storage available, file near `MAXSIZE`, smallfile TS | Raise file `MAXSIZE` if limits allow, or add a datafile | Smallfile type, file limits, space on storage |
| File has `AUTOEXTEND OFF` but needs growth | `RESIZE` or `AUTOEXTEND ON ... MAXSIZE` | Capacity plan and execution privileges |
| Bigfile TS near current ceiling | Raise `MAXSIZE` or `RESIZE` the single file if supported | Block size and physical/architectural limits |
| Tablespace has room but schema cannot create objects | Check **user quota**, privileges, and objects | Do not assume every error is a datafile issue |
| Storage is running low | Address physical capacity, cleanup, migration, or planned storage expansion | Raising `MAXSIZE` does not create physical disk space |
| TEMP out of space | Analyze TEMP workload and **tempfiles** | Do not alter permanent datafiles to fix TEMP errors |

## 6. Creating and Managing Temporary Tablespaces

Temporary tablespaces use **tempfiles** and serve temporary needs, such as sort/hash operations whose data spills beyond working memory.

Example with a filesystem:

```sql
CREATE TEMPORARY TABLESPACE app_temp
    TEMPFILE '/u02/oradata/ORCL/app_temp01.dbf'
        SIZE 1G
        AUTOEXTEND ON NEXT 128M MAXSIZE 8G
    EXTENT MANAGEMENT LOCAL;
```

A corresponding configuration can use OMF if set up in the environment. When modifying autoextend settings for a tempfile, use **`ALTER DATABASE TEMPFILE`**, for example:

```sql
ALTER DATABASE TEMPFILE
    '/u02/oradata/ORCL/app_temp01.dbf'
    AUTOEXTEND ON NEXT 256M MAXSIZE 12G;
```

For tempfiles, query `DBA_TEMP_FILES`. Do not rely only on `DBA_DATA_FILES`, as that view covers **datafiles**, while tempfiles are tracked separately.

### 6.1. Why Can TEMP Still Run Out of Space?

A query with `ORDER BY`, `GROUP BY`, hash join, or similar operations can require substantial TEMP when data spills out of work-area memory. Many concurrent queries also increase aggregate demand.

Even with `AUTOEXTEND ON`, TEMP can still fill up if:

- tempfiles reach `MAXSIZE`;
- filesystem/ASM runs out of space;
- concurrent TEMP usage is too high;
- PDB configuration or platform limits prevent further growth.

Never simply set `MAXSIZE UNLIMITED` on TEMP to resolve every incident: identify the queries consuming TEMP and the root cause.

## 7. Inspecting Configuration with Data Dictionary Views

The following SQL examples are **read-only**. They require appropriate access to DBA views and should be run in the right target PDB/container.

### 7.1. Viewing Created Tablespaces and File Type

```sql
SELECT tablespace_name,
       contents,
       status,
       bigfile,
       block_size
FROM   dba_tablespaces
WHERE  tablespace_name IN (
           'APP_DATA',
           'APP_REPORT',
           'APP_INDEX',
           'ANALYTICS_DATA',
           'APP_TEMP'
       )
ORDER  BY tablespace_name;
```

Interpretation:

- `CONTENTS`: `PERMANENT`, `TEMPORARY`, or `UNDO` by type.
- `BIGFILE`: indicates whether the tablespace is a bigfile tablespace.
- `BLOCK_SIZE`: block size of the tablespace, needed when converting block counts to size.
- `STATUS`: tablespace status, such as online/offline depending on state.

### 7.2. Checking AUTOEXTEND and MAXSIZE of Datafiles

```sql
SELECT df.tablespace_name,
       df.file_id,
       df.file_name,
       ROUND(df.bytes / 1024 / 1024, 1) AS allocated_mb,
       df.autoextensible,
       ROUND(df.maxbytes / 1024 / 1024, 1) AS max_mb,
       ROUND(df.increment_by * ts.block_size / 1024 / 1024, 1) AS next_mb
FROM   dba_data_files df
JOIN   dba_tablespaces ts
       ON ts.tablespace_name = df.tablespace_name
WHERE  df.tablespace_name = 'APP_DATA'
ORDER  BY df.file_id;
```

Key columns:

| Column | Meaning |
|---|---|
| `BYTES` | Current file size in Oracle |
| `AUTOEXTENSIBLE` | `YES` or `NO`, whether the file can autoextend |
| `MAXBYTES` | Expansion ceiling reported by Oracle, **not current size** |
| `INCREMENT_BY` | Growth step measured in **Oracle blocks**, not MiB |
| `BLOCK_SIZE` | Block size used to convert `INCREMENT_BY` into bytes |

If a file has `AUTOEXTENSIBLE='NO'`, do not treat `MAXBYTES` as usable growth capacity while ignoring that flag. When calculating **achievable file size under the current configuration**, non-autoextensible files should be capped at their **current `BYTES`** (unless a DBA alters settings or adds files).

The query below roughly totals current size and configured ceilings across datafiles:

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / POWER(1024, 3), 2) AS allocated_gib,
       ROUND(
         SUM(
           CASE
             WHEN autoextensible = 'YES' THEN maxbytes
             ELSE bytes
           END
         ) / POWER(1024, 3), 2
       ) AS potential_file_limit_gib
FROM   dba_data_files
WHERE  tablespace_name = 'APP_DATA'
GROUP  BY tablespace_name;
```

`POTENTIAL_FILE_LIMIT_GIB` is **not the actual free space immediately available**, because it only sums file ceilings without accounting for already-allocated segments or real storage limits.

### 7.3. Viewing Free Extents Inside Current Datafiles

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / POWER(1024, 3), 2) AS free_gib
FROM   dba_free_space
WHERE  tablespace_name = 'APP_DATA'
GROUP  BY tablespace_name;
```

`DBA_FREE_SPACE` shows free extent space inside already-allocated datafiles as reported by the view. It **does not include potential future growth** from `AUTOEXTEND`, nor does it mean the filesystem has that much free capacity.

When a tablespace has no free extents at all and the view returns no rows, the query above may return zero rows. For more reliable reporting, combine files and free space using `LEFT JOIN`/`NVL` and cross-check tablespace status.

### 7.4. Monitoring Aggregate Tablespace Usage

A helpful view is `DBA_TABLESPACE_USAGE_METRICS`:

```sql
SELECT tablespace_name,
       used_space,
       tablespace_size,
       used_percent
FROM   dba_tablespace_usage_metrics
WHERE  tablespace_name = 'APP_DATA';
```

Size values in this view are measured in blocks using Oracle's capacity calculation logic; `TABLESPACE_SIZE`/`USED_PERCENT` may factor in autoextend capability and storage limits per the view/version mechanism. Do not infer directly from this percentage alone how many GiB remain on an OS volume.

Concluding sufficient capacity requires **combining**: free extents, current file sizes, autoextend ceilings, filesystem/ASM free space, workload growth, and administrative constraints.

### 7.5. Checking Tempfiles

```sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 1)    AS allocated_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 1) AS max_mb
FROM   dba_temp_files
WHERE  tablespace_name = 'APP_TEMP'
ORDER  BY file_id;
```

This shows TEMP file configuration, not fully **which SQL is currently consuming TEMP**. When deeper investigation is needed, a DBA can check TEMP statistics views such as `V$TEMP_SPACE_HEADER`, `V$TEMPSEG_USAGE`, or applicable views for the running release.

### 7.6. In CDB/PDB: Querying the Right Container

When working inside a **PDB**, standard DBA views reflect objects in the current container per privileges and query context. If a DBA in `CDB$ROOT` wants to inspect across the entire CDB, they can use the corresponding **`CDB_`** views with the `CON_ID` column per version/privileges:

```sql
-- Run in root using an account with appropriate privileges.
SELECT con_id,
       tablespace_name,
       file_name,
       ROUND(bytes / 1024 / 1024, 1) AS allocated_mb
FROM   cdb_data_files
WHERE  tablespace_name = 'APP_DATA'
ORDER  BY con_id, file_name;
```

Different PDBs can have **tablespaces with the same name**. Therefore, when calculating capacity across a CDB, differentiate by `CON_ID` rather than blindly summing all rows named `APP_DATA`.

## 8. User Quota Differs from Datafile MAXSIZE

A tablespace may still have free capacity, yet a schema cannot allocate extents because it lacks a **quota** or has exceeded the quota granted to that user.

Example (assuming user `APP_USER` already exists in the PDB and the operator has privileges):

```sql
ALTER USER app_user
    QUOTA 1G ON app_data;
```

This sets the **user's tablespace usage quota** to 1 GiB. It **does not change file size**, does not change `MAXSIZE`, and does not guarantee that the schema actually has 1 GiB of free physical disk space.

Three limits to verify independently:

```text
Database user quota
        |
        v
Free space in tablespace / datafiles
        |
        v
AUTOEXTEND + MAXSIZE of each datafile
        |
        v
Actual capacity on filesystem / ASM / storage
```

If you encounter an error like `ORA-01950: no privileges on tablespace`, check quotas/privileges. If you encounter an unable-to-extend-extent error, check free extents, file status, autoextend, maxsize, and physical storage.

Never raise quotas or `MAXSIZE` blindly without identifying which limit layer was hit.

## 9. Capacity Planning by Example

Suppose an application has a permanent smallfile tablespace `APP_DATA` with two datafiles:

| Datafile | Current Size | AUTOEXTEND | NEXT | MAXSIZE |
|---|---:|---|---:|---:|
| `app_data01.dbf` | 2 GiB | ON | 256 MiB | 10 GiB |
| `app_data02.dbf` | 3 GiB | ON | 256 MiB | 12 GiB |
| **Total** | **5 GiB** | | | **22 GiB** |

Preliminary calculation:

- **Allocated at file level:** 5 GiB.
- **Configured ceiling of the two files:** 10 + 12 = 22 GiB.
- **Configured file growth headroom:** 22 − 5 = 17 GiB.

However, to forecast **how long until full**, you need to know:

- Space actually used by segments and free extents inside the current 5 GiB.
- Average daily/weekly growth rate, batch events, and seasonal fluctuations.
- Remaining physical storage space and ability to expand storage.
- Large objects (LOBs, partitions, indexes) and sudden creation/rebuild spikes.
- Schema quotas, datafile limits, and architectural ceilings.

### 9.1. Time Estimation with Illustrative Numbers

Assume measurements report:

```text
Free extents in current files:           1 GiB
Remaining configured autoextend margin: 17 GiB
Real allocatable storage remaining:      9 GiB
Effective data growth rate:              0.25 GiB/day
```

Assuming steady workload, all other limits permitting, and that the 9 GiB of available storage can be dedicated to these files, growth headroom from measurement time is roughly **1 + min(17, 9) = 10 GiB**, corresponding to roughly **40 days** at 0.25 GiB/day.

This is purely a mathematical illustration, **not a guarantee of 40 days of runway**. Extent step sizes, sudden data spikes, autoextend granularity, file allocation overhead, shared storage, and other workloads can exhaust resources sooner. In monitoring, set early warning thresholds to leave time for remediation.

### 9.2. Metrics to Monitor

| Metric | Reason |
|---|---|
| Current datafile `BYTES` | Storage already allocated to files |
| Datafile `AUTOEXTENSIBLE`, `MAXBYTES` | Growth headroom Oracle may permit |
| Free extents and tablespace utilization | Logical space available for segment allocation |
| Filesystem/ASM free capacity | Actual physical expansion capability |
| Growth rate over time | Forecast date when warning thresholds are hit |
| Connection counts, batch jobs, index rebuilds | Explain sudden growth spikes |
| User quotas and PDB limits | Can block allocation even before files hit their ceilings |
| Recovery time, backups, and monitoring | Ensure operational readiness when a capacity incident occurs |

Monitor at **both the tablespace and storage levels**, because a tablespace may still have room to autoextend while shared underlying storage is nearly full.

## 10. Troubleshooting Common Out-of-Space Errors

### 10.1. ORA-01653 and ORA-01654

Common errors:

- **`ORA-01653`**: unable to extend table segment in tablespace.
- **`ORA-01654`**: unable to extend index segment in tablespace.

A structured diagnostic flow:

1. Identify the **tablespace** and **segment** named in the error.
2. Check free extents and datafile settings using `DBA_FREE_SPACE` and `DBA_DATA_FILES`.
3. Check whether files have hit `MAXSIZE` and whether `AUTOEXTENSIBLE` is enabled.
4. Check filesystem/ASM capacity and other limits.
5. Choose a fix: raise `MAXSIZE`, add a datafile (smallfile), expand storage, reclaim/reorganize data if appropriate, or fix quota if that is the cause.

Never assume every `ORA-01653` is solved by a single `MAXSIZE UNLIMITED` command.

### 10.2. ORA-01652 Related to Temporary Segments

`ORA-01652` reports an inability to extend a temporary segment in the indicated context. First check the **tablespace named in the error**, as temporary segments can arise in multiple operations, and sort/hash queries typically involve TEMP.

How to handle:

- Inspect tempfiles and `MAXSIZE` via `DBA_TEMP_FILES`.
- Check TEMP consumption by session/SQL when authorized.
- Evaluate execution plans, parallelism, and concurrency levels.
- Grow or adjust tempfiles if storage and policy allow.

Growing `APP_DATA` permanent datafiles will not necessarily resolve an error occurring in `TEMP`.

### 10.3. Hitting File or Storage Limits

When a datafile cannot grow, the root cause may lie in:

- `MAXSIZE` ceiling reached;
- blocks-per-file ceiling for smallfile/bigfile;
- out of disk space, quota, or write permissions on storage;
- database/PDB limits;
- I/O errors or a file not in an extensible state.

Oracle emits different error codes depending on cause and operation phase (for instance, a `RESIZE` exceeding file limits); read the **full error code and trace/alert log** before selecting a fix.

### 10.4. Why Does ALTER RESIZE to Shrink a File Fail?

A datafile is not an arbitrary byte stream you can truncate without checking where used extents sit. If blocks near the end of the file still belong to a segment, shrinking the file below that point is disallowed. Even if the tablespace has plenty of free extents in the middle, **the end of the file might not be free**.

Reclaiming storage requires evaluating extent placement, segment move/shrink options, lock/redo impact, and maintenance policies. Never run guesswork shrink/resize operations on production data.

## 11. Step-by-Step Practice in a Test Environment

Assume practice in PDB `APPPDB`, where the operator has privileges to create/alter tablespaces and provisioned storage.

### Step 1 — Confirm the Right Environment

```sql
SHOW CON_NAME;
SHOW PARAMETER db_create_file_dest;
```

If OMF is validly configured, you can choose the example without an explicit physical path.

### Step 2 — Create a Tablespace with a Specific Ceiling

```sql
CREATE TABLESPACE lab_data
    DATAFILE SIZE 512M
        AUTOEXTEND ON NEXT 64M MAXSIZE 2G
    EXTENT MANAGEMENT LOCAL
    SEGMENT SPACE MANAGEMENT AUTO;
```

`LAB_DATA` starts at 512 MiB, configured to grow in 64 MiB increments up to a 2 GiB file ceiling (subject to permitted conditions). If the environment does not use OMF, replace `DATAFILE SIZE ...` with `DATAFILE '<valid_path>' SIZE ...`.

### Step 3 — Observe the Actual Metadata

```sql
SELECT file_name,
       ROUND(bytes / 1024 / 1024) AS current_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024) AS max_mb,
       increment_by
FROM   dba_data_files
WHERE  tablespace_name = 'LAB_DATA';
```

Save the `FILE_NAME` Oracle created. With OMF, the actual filename is generated by Oracle, not a fixed string from documentation.

### Step 4 — Adjust the Ceiling

Once you know the real `FILE_NAME` from Step 3, in a test environment you can modify it with:

```sql
-- Replace with the actual FILE_NAME value from Step 3.
ALTER DATABASE DATAFILE
    '<actual_datafile_name>'
    AUTOEXTEND ON NEXT 128M MAXSIZE 4G;
```

`<actual_datafile_name>` is just a **placeholder**—do not run it literally. The current size does not jump to 4 GiB just because `MAXSIZE` changed.

### Step 5 — Observe After the Change

```sql
SELECT file_name,
       ROUND(bytes / 1024 / 1024) AS current_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024) AS max_mb
FROM   dba_data_files
WHERE  tablespace_name = 'LAB_DATA';
```

Compare `CURRENT_MB` and `MAX_MB` to see the difference between **allocated space** and **configured growth capacity**.

### Step 6 — Clean Up the Practice Exercise (Only When Data Need Not Be Kept)

If this is truly a test tablespace confirmed to contain no data needing retention, a DBA can clean up per standard procedure:

```sql
-- DESTRUCTIVE OPERATION: use only on LAB_DATA created specifically for this lab.
DROP TABLESPACE lab_data INCLUDING CONTENTS AND DATAFILES;
```

The command above drops both objects belonging to the tablespace and the corresponding datafiles per Oracle's mechanism; **never run on tablespaces holding production data**. In organization-managed environments, cleanup must follow procedures and ownership verification.

## 12. Misconceptions to Avoid

**"`MAXSIZE 10G` means Oracle immediately reserves 10 GiB."**  
No. `SIZE` is the initial size; `MAXSIZE` is the file's upper limit if autoextend is enabled.

**"`AUTOEXTEND ON` guarantees we will never run out of space."**  
No. The datafile can hit `MAXSIZE`, or physical storage can fill up.

**"`MAXSIZE` is the limit for the entire tablespace."**  
Not directly. `MAXSIZE` is set per **datafile/tempfile**; a smallfile tablespace can contain multiple files.

**"`AUTOEXTEND ON` makes the file bigger right away."**  
No. Growth typically happens when additional allocation is needed; use `RESIZE` if the goal is changing the current size immediately.

**"Disabling AUTOEXTEND returns allocated storage space."**  
No. `AUTOEXTEND OFF` only stops automatic growth; current size does not shrink on its own.

**"If there are free extents in the tablespace, OS storage also has free space."**  
No. Free extents are space **inside already-allocated datafiles**, whereas free filesystem/ASM space is external to the database; they are two different metrics.

**"When a datafile fills up, you must raise MAXSIZE to UNLIMITED."**  
Not necessarily. Depending on root cause, you might add a file to a smallfile tablespace, optimize data, expand storage, adjust quotas, or review segment design.

**"In a PDB, you don't need to care about the container when creating a tablespace."**  
False. A tablespace created in a container is scoped to that container. Always verify `SHOW CON_NAME`.

## 13. Self-Check Questions

1. A datafile has `SIZE 1G`, `AUTOEXTEND ON NEXT 128M MAXSIZE 8G`. From this configuration alone, can you state the file currently occupies 8 GiB on the filesystem?
2. A smallfile tablespace contains 3 datafiles, each `MAXSIZE 5G`. Should you describe this as "a tablespace capped at 5 GiB"?
3. File `APP_DATA01.DBF` is currently 6 GiB with `AUTOEXTEND OFF`. Does running `ALTER DATABASE DATAFILE ... AUTOEXTEND OFF` again free up 2 GiB?
4. Why can `DBA_FREE_SPACE` report remaining free extents while OS storage alerts are still high?
5. A table throws an error saying it cannot extend an extent. Why must you check all three: `DBA_DATA_FILES`, `DBA_FREE_SPACE`, and filesystem/ASM?
6. When needing to expand a **bigfile tablespace**, can you use `ALTER TABLESPACE ... ADD DATAFILE` like a smallfile?
7. When `RESIZE` of a file from 10 GiB down to 6 GiB fails, why can you not conclude the tablespace has zero free space anywhere?
8. Why does changing a datafile's `MAXSIZE` not substitute for granting quota to a schema?

**Answer Hints:**

1. No; initial `SIZE` is 1 GiB, while `MAXSIZE` is only a growth ceiling.
2. No; each file has its own limit, so the combined configured ceiling across three files can be 15 GiB if conditions permit.
3. No; disabling autoextend does not shrink a file.
4. Free extents are logical space **inside files already occupying storage**, not free capacity outside Oracle.
5. To distinguish existing free space, file auto-growth capability, configured ceilings, and actual underlying storage availability.
6. No; a bigfile tablespace centers on a single large file and must be adjusted through supported mechanisms on that file.
7. There may be free extents in the middle of the file while the tail end of the file is still occupied by a segment.
8. Quota limits by **database user**, whereas `MAXSIZE` limits by **file**—two different management layers.

## 14. Recommended Oracle Documentation

- [Oracle Database SQL Language Reference — CREATE TABLESPACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLESPACE.html): syntax for creating permanent, temporary, smallfile, and bigfile tablespaces.
- [Oracle Database SQL Language Reference — ALTER TABLESPACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLESPACE.html): modifying tablespace attributes and adding datafiles.
- [Oracle Database SQL Language Reference — ALTER DATABASE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-DATABASE.html): `DATAFILE`/`TEMPFILE` and `RESIZE`/`AUTOEXTEND` clauses.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): managing tablespaces, datafiles, tempfiles, Oracle Managed Files, and space.
- [Oracle Database Reference — DBA_DATA_FILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DATA_FILES.html): `BYTES`, `MAXBYTES`, `AUTOEXTENSIBLE`, `INCREMENT_BY`.
- [Oracle Database Reference — DBA_TEMP_FILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TEMP_FILES.html): corresponding attributes for tempfiles.
- [Oracle Database Reference — DBA_TABLESPACE_USAGE_METRICS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TABLESPACE_USAGE_METRICS.html): tablespace usage and capacity metrics.
- [Oracle Database Reference — DBA_FREE_SPACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_FREE_SPACE.html): free extents by tablespace/file.

When creating and operating tablespaces, manage **current file size (`SIZE`/`BYTES`)**, **growth increment (`NEXT`)**, **file ceiling (`MAXSIZE`)**, **free space inside the tablespace**, and **actually available underlying storage** together. Only by reading these together do you know how much further the database can grow and when to intervene before the system runs out of space.
