# Migrating Schemas with Data Pump and Verifying Data and Objects

## 1. Objectives and Scope

Oracle Data Pump is a logical data movement toolset. Export reads metadata and row data from a source database to produce dump files; Import reads dump files to recreate objects and load data into a target database.

A schema migration is not complete merely because `expdp` and `impdp` exited cleanly. You must verify that the exact schemas and object sets were moved; data is consistent at a defined point; tables, partitions, LOBs, indexes, constraints, and triggers work properly; sequences, views, packages, synonyms, and dependencies are resolved; users, roles, grants, quotas, and default tablespaces are configured; out-of-schema components are migrated separately; and the application connects to the right service/PDB and passes business workflows.

The approach in this lesson uses schema-mode Data Pump. It fits moving one or more schemas between two databases—such as from a legacy system to a new database, between two PDBs, or from on-premises to cloud.

Data Pump is a logical migration, not a physical database clone. Dump files do not replace RMAN backups, do not automatically migrate system listeners or services, and do not guarantee every out-of-schema component moves automatically.

## 2. Export/Import Architecture

~~~text
SOURCE DATABASE
      |
      | 1. Inventory schemas, dependencies, tablespaces, privileges
      v
Select consistent SCN and prepare export
      |
      | 2. expdp SCHEMAS=...
      v
Dump files + export log
      |
      | 3. Copy/transfer and verify files
      v
TARGET DATABASE
      |
      | 4. Prepare users, roles, tablespaces, quotas
      | 5. impdp REMAP_SCHEMA / REMAP_TABLESPACE
      v
Create objects + load data
      |
      | 6. Verify data, objects, grants, and dependencies
      v
Application testing + cutover
~~~

| Component | Role |
| --- | --- |
| `expdp` | Exports metadata/data from source |
| `impdp` | Imports metadata/data into target |
| `DIRECTORY` object | Maps a logical name to a directory on the database server |
| Dump file | Stores exported contents in Data Pump format |
| Log file | Records processed objects, warnings, and errors |
| `SCHEMAS` | Selects schemas to export/import |
| `REMAP_SCHEMA` | Changes schema ownership during import |
| `REMAP_TABLESPACE` | Remaps segment target tablespaces |
| `FLASHBACK_SCN` | Keeps exported data consistent as of an SCN when supported |

## 3. Distinguishing Data Pump Modes

| Mode | Parameter | Scope |
| --- | --- | --- |
| Full | `FULL=Y` | Database-wide per privileges and filters |
| Schema | `SCHEMAS=APP_OWNER` | One or more schemas |
| Table | `TABLES=APP_OWNER.ORDERS` | One or more tables/partitions |
| Tablespace | `TABLESPACES=APP_DATA` | Objects in selected tablespaces |
| Transportable | `TRANSPORTABLE` | Moves datafiles with metadata per TTS rules |

Schema mode fits the scenario in this lesson. Never use `FULL=Y` just to migrate one schema without appropriate justification and privileges.

`INCLUDE` and `EXCLUDE` filter object types or specific objects. Filtering carelessly can break dependencies. Before excluding an object type, confirm whether the application depends on it.

## 4. Inventorying the Source Before Export

### 4.1. Verifying Database, Service, and Container

~~~sql
SELECT name,
       dbid,
       open_mode,
       database_role,
       platform_name
FROM v$database;

SHOW CON_NAME;

SELECT sys_context('USERENV', 'SERVICE_NAME') AS service_name,
       sys_context('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

In a CDB environment, Data Pump must connect to the exact PDB service if the schema resides in a PDB. Never export accidentally from CDB$ROOT or another PDB sharing the same schema name.

### 4.2. Schema Metadata

~~~sql
SELECT username,
       account_status,
       default_tablespace,
       temporary_tablespace,
       profile,
       created
FROM dba_users
WHERE username = 'APP_OWNER';
~~~

Check whether the schema is locked, has an expired password, uses a custom profile, or references a default tablespace missing on the target.

### 4.3. Counting Objects by Type and Status

~~~sql
SELECT owner,
       object_type,
       status,
       COUNT(*) AS object_count
FROM dba_objects
WHERE owner = 'APP_OWNER'
GROUP BY owner, object_type, status
ORDER BY object_type, status;
~~~

Capture a pre-export baseline, especially counts of `TABLE`, `TABLE PARTITION`, `TABLE SUBPARTITION`, `INDEX`, `INDEX PARTITION`, `VIEW`, `MATERIALIZED VIEW`, `SEQUENCE`, `PROCEDURE`, `FUNCTION`, `PACKAGE`, `PACKAGE BODY`, `TRIGGER`, `TYPE`, `SYNONYM`, and `DATABASE LINK`.

Some object types or metadata follow special export rules. Object counts in `DBA_OBJECTS` serve as a comparison baseline, not a guarantee that every single row appears under the exact same object type after import.

### 4.4. Inspecting Segments and Sizes

~~~sql
SELECT tablespace_name,
       segment_type,
       COUNT(*) AS segment_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM dba_segments
WHERE owner = 'APP_OWNER'
GROUP BY tablespace_name, segment_type
ORDER BY tablespace_name, segment_type;
~~~

Inspect largest segments:

~~~sql
SELECT segment_name,
       partition_name,
       segment_type,
       tablespace_name,
       ROUND(bytes / 1024 / 1024, 2) AS size_mb
FROM dba_segments
WHERE owner = 'APP_OWNER'
ORDER BY bytes DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Segment size does not equal dump file size. Compression, data types, LOBs, and repetitive values can make dump files noticeably larger or smaller. The target needs sufficient capacity for datafiles, `TEMP`, `UNDO`, redo, archive logs, and dump staging.

### 4.5. Inspecting Tablespaces and Quotas

~~~sql
SELECT tablespace_name,
       status,
       contents,
       block_size,
       bigfile
FROM dba_tablespaces
ORDER BY tablespace_name;

SELECT username,
       tablespace_name,
       bytes,
       max_bytes,
       blocks,
       max_blocks
FROM dba_ts_quotas
WHERE username = 'APP_OWNER'
ORDER BY tablespace_name;

SELECT DISTINCT tablespace_name
FROM dba_segments
WHERE owner = 'APP_OWNER'
ORDER BY tablespace_name;
~~~

Build a source-to-target tablespace mapping table. Never assume the target has identical tablespace names, block sizes, or capacity.

### 4.6. Checking Pre-Existing Invalid Objects

~~~sql
SELECT object_type,
       object_name,
       status
FROM dba_objects
WHERE owner = 'APP_OWNER'
  AND status <> 'VALID'
ORDER BY object_type, object_name;

SELECT name,
       type,
       line,
       position,
       text
FROM dba_errors
WHERE owner = 'APP_OWNER'
ORDER BY name, sequence;
~~~

Record invalid objects already present prior to migration. Post-import, distinguish newly introduced errors from pre-existing source issues.

### 4.7. Cross-Schema Dependencies

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM dba_dependencies
WHERE owner = 'APP_OWNER'
  AND referenced_owner <> 'APP_OWNER'
ORDER BY referenced_owner, referenced_name, name;
~~~

If `APP_OWNER` invokes packages or queries tables in another schema, schema mode does not automatically pull in those external schemas. Either migrate the referenced schemas too, verify equivalent objects exist on target, recreate synonyms/grants/database links, or update application configuration.

### 4.8. Inspecting Privileges

System privileges:

~~~sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee = 'APP_OWNER'
ORDER BY privilege;
~~~

Role grants:

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
FROM dba_role_privs
WHERE grantee = 'APP_OWNER'
ORDER BY granted_role;
~~~

Object grants issued by the schema to other users:

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM dba_tab_privs
WHERE owner = 'APP_OWNER'
ORDER BY table_name, grantee, privilege;
~~~

Record grants to external roles and users. When exporting only a single schema, never assume every role, system privilege, public synonym, ACL, or external grant moves completely.

## 5. Out-of-Schema Components to Inventory Separately

Schema exports move schema-owned metadata and data within Data Pump's scope, while applications frequently depend on database-wide or OS-level resources.

| Component | Why Check Separately |
| --- | --- |
| Database users, profiles, authentication | User/security policies may need recreation or adjustment |
| Roles and system privileges | Roles may be managed centrally outside the schema |
| Tablespaces and quotas | Target storage layout may differ |
| Public synonyms | Database-level objects |
| `DIRECTORY` objects | Point to server filesystems; do not copy OS directories or files |
| External tables and files | Data files reside outside the database |
| Database links | Endpoints, credentials, and network access must be verified |
| Network ACLs | Govern `UTL_HTTP`/`UTL_TCP` and outbound network access |
| Scheduler credentials | External secrets/credentials require separate management |
| External jobs | Depend on OS executables, OS users, and hosts |
| Services/listeners/`tnsnames` | Connection configuration, not schema data |
| TDE wallets/keystores | Encryption keys needed to read encrypted data |
| Application configuration | JDBC URLs, secrets, endpoints, feature flags |
| Backup/monitoring policies | Must be configured on the target database |

Check directory objects:

~~~sql
SELECT owner,
       directory_name,
       directory_path
FROM dba_directories
ORDER BY owner, directory_name;
~~~

Check database links:

~~~sql
SELECT owner,
       db_link,
       username,
       host
FROM dba_db_links
WHERE owner IN ('APP_OWNER', 'PUBLIC')
ORDER BY owner, db_link;
~~~

Never attempt to extract database link passwords from dictionary views. When recreating links, retrieve credentials from an approved secret source and verify the remote service exists.

Check scheduler jobs:

~~~sql
SELECT owner,
       job_name,
       enabled,
       state,
       job_type,
       program_name,
       schedule_name
FROM dba_scheduler_jobs
WHERE owner = 'APP_OWNER'
ORDER BY job_name;
~~~

Check synonyms:

~~~sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM dba_synonyms
WHERE owner IN ('APP_OWNER', 'PUBLIC')
ORDER BY owner, synonym_name;
~~~

## 6. Preparing the Target Database

### 6.1. Checking Version and Character Set

~~~sql
SELECT banner_full
FROM v$version
WHERE banner_full LIKE 'Oracle Database%';

SELECT parameter,
       value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;

SELECT filename,
       version
FROM v$timezone_file;
~~~

The target must support the metadata and features generated by the source export. Compare source/target releases, Data Pump versions, `COMPATIBLE`, character sets, national character sets, timezone files, and used data types/features.

Data Pump can perform character-set conversion under Oracle rules during logical loads, though never assume every conversion is lossless. Verify character coverage, column lengths, `BYTE`/`CHAR` semantics, and actual data values.

### 6.2. Creating Target Tablespaces

~~~sql
CREATE TABLESPACE APP_DATA
DATAFILE '/u02/oradata/DBTARGET/app_data01.dbf'
SIZE 8G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 64G;

CREATE TABLESPACE APP_INDEX
DATAFILE '/u02/oradata/DBTARGET/app_index01.dbf'
SIZE 4G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 32G;
~~~

Paths and sizes are illustrative. For ASM or OMF, use corresponding storage destinations. Confirm filesystem or disk group capacity and enforce bounded autoextend.

### 6.3. Creating the Target User and Quotas

If remapping the schema owner, create the target user with appropriate default tablespace, temporary tablespace, profile, and quotas:

~~~sql
CREATE USER APP_RUNTIME
IDENTIFIED BY "<password-from-approved-secret-process>"
DEFAULT TABLESPACE APP_DATA
TEMPORARY TABLESPACE TEMP
QUOTA 20G ON APP_DATA
QUOTA 10G ON APP_INDEX;

GRANT CREATE SESSION TO APP_RUNTIME;
~~~

This is a lab example. In production, never hardcode real passwords in committed scripts or logs; grant approved quotas; assign least-privilege grants; consider separating schema owner from runtime account; and verify profile, password policy, and account status.

Data Pump can import user/grant metadata under certain export/import scopes and privileges. Nonetheless, pre-creating users, roles, quotas, and security policies avoids relying on implicit user creation or default settings. When pre-creating users, preview DDL with `SQLFILE` and adjust import filters to avoid unintended overwrites.

### 6.4. Creating the DIRECTORY Object for Data Pump

A `DIRECTORY` object points to a directory on the database server, not on the client machine running `expdp`/`impdp`:

~~~sql
CREATE OR REPLACE DIRECTORY DPUMP_STAGE AS '/u03/dpump';
GRANT READ, WRITE ON DIRECTORY DPUMP_STAGE TO SYSTEM;
~~~

The directory `/u03/dpump` must exist on the database host and the Oracle Database OS process must hold OS read/write permissions. The user running Data Pump needs `READ` and `WRITE` privileges on the `DIRECTORY` object. A `DIRECTORY` object does not grant OS filesystem permissions automatically.

Never grant `READ` or `WRITE` to `PUBLIC`. Choose an appropriate operational account and protect dump files, as they may contain complete business datasets.

### 6.5. Pre-Import Target Verification

~~~sql
SELECT tablespace_name,
       status,
       contents
FROM dba_tablespaces
ORDER BY tablespace_name;

SELECT username,
       account_status,
       default_tablespace,
       temporary_tablespace
FROM dba_users
WHERE username IN ('APP_OWNER', 'APP_RUNTIME');
~~~

Verify the target connection points to the right PDB, users and tablespaces exist, storage suffices, directories are valid, and services accept connections.

## 7. Choosing a Consistent SCN for Export

### 7.1. Why Is Consistency Required?

Schemas can continue changing during an export. If tables are read at different instants, related data can become inconsistent. For instance, if `ORDERS` is exported before a transaction commits while `ORDER_LINES` is exported after commit, the target receives mismatched states unless a consistent snapshot is enforced.

Data Pump supports Flashback Query via `FLASHBACK_SCN` or `FLASHBACK_TIME` where supported. For migrations requiring data reconciliation, record an agreed SCN and export as of that SCN.

### 7.2. Obtaining the SCN

~~~sql
SELECT current_scn
FROM v$database;
~~~

Record the SCN in the change ticket and pass it to `expdp`. Requires appropriate view privileges.

### 7.3. FLASHBACK_SCN

~~~text
expdp system@SOURCE_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_owner_export.log
  SCHEMAS=APP_OWNER
  FLASHBACK_SCN=123456789012
  PARALLEL=4
  FILESIZE=10G
  LOGTIME=ALL
  METRICS=YES
~~~

The SCN above is a placeholder. Replace it with the actual SCN captured right before export.

`FLASHBACK_SCN` requires Oracle to retain enough undo to read as of that SCN throughout the export. If the export outlasts undo retention, Data Pump can hit `ORA-01555`. Check export duration, undo generation rate, `UNDO_RETENTION`, and undo tablespace sizing beforehand.

### 7.4. FLASHBACK_TIME

You can specify a timestamp:

~~~text
FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 10:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Data Pump maps the timestamp to the closest matching SCN. Use one method per plan; never specify both `FLASHBACK_SCN` and `FLASHBACK_TIME` in the same job.

### 7.5. When Undo Cannot Be Retained Long Enough

If exports are long and the source handles heavy DML:

- Optimize export speed and storage throughput.
- Use multi-piece dump files and appropriate parallelism.
- Size undo capacity and verify retention.
- Schedule exports during low-write maintenance windows.
- Pause writers or put the app into read-only mode during cutover.
- Evaluate Data Pump `NETWORK_LINK` or alternative migration methods if appropriate.

Never disable undo or blindly crank up `UNDO_RETENTION` without backing storage capacity.

## 8. Exporting the Schema with expdp

### 8.1. Creating a Parameter File

Use a `parfile` for reviewability and reproducible configuration:

~~~text
DIRECTORY=DPUMP_STAGE
DUMPFILE=app_owner_%U.dmp
LOGFILE=app_owner_export.log
SCHEMAS=APP_OWNER
FLASHBACK_SCN=123456789012
PARALLEL=4
FILESIZE=10G
COMPRESSION=ALL
LOGTIME=ALL
METRICS=YES
REUSE_DUMPFILES=NO
~~~

Run:

~~~text
expdp system@SOURCE_PDB PARFILE=app_owner_export.par
~~~

Keep configuration in the parfile without plaintext passwords. Use Oracle Secure External Password Store, interactive prompts, or an approved credential mechanism. Protect parfiles and logs, as they reveal system topology.

### 8.2. Parameter Meanings

| Parameter | Role |
| --- | --- |
| `DIRECTORY` | Directory object holding dumps and logs |
| `DUMPFILE` | Dump file pattern; `%U` generates numbered pieces |
| `LOGFILE` | Export log file |
| `SCHEMAS` | Schema list |
| `FLASHBACK_SCN` | Snapshot SCN for export |
| `PARALLEL` | Number of parallel workers |
| `FILESIZE` | Maximum size per dump file piece |
| `COMPRESSION` | Compresses metadata/data per supported level |
| `LOGTIME` | Stamps log lines with timestamps |
| `METRICS` | Logs object counts and timing metrics |
| `REUSE_DUMPFILES` | Controls overwriting existing dump files |

`PARALLEL` does not parallelize every object equally. Excessive parallelism increases CPU/I/O load, undo/redo pressure, and file count. Size it based on storage throughput, CPU, and edition/feature limits.

### 8.3. Reviewing the Export Log

After export, verify:

- Job completed cleanly.
- Zero unhandled `ORA-`, `UDE-`, or `LRM-` errors.
- Exported object and row counts look reasonable.
- No unexpected skipped objects.
- All dump pieces exist with expected sizes.
- SCN and schema in the log match the change record.

Never rely solely on the shell exit code. The Data Pump log is essential evidence.

### 8.4. Metadata-Only Export for Reconnaissance

~~~text
expdp system@SOURCE_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_metadata.dmp
  LOGFILE=app_metadata.log
  SCHEMAS=APP_OWNER
  CONTENT=METADATA_ONLY
~~~

Metadata-only exports are useful for inspecting DDL and dependencies before moving data. They do not replace a full export.

## 9. Importing and Remapping Schemas and Tablespaces

### 9.1. Importing with the Same Schema Name

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_owner_import.log
  SCHEMAS=APP_OWNER
  PARALLEL=4
~~~

Prepare the target schema/user per policy. If target objects with matching names already exist, explicitly plan `TABLE_EXISTS_ACTION` and conflict handling before importing.

### 9.2. Changing Schema Ownership with REMAP_SCHEMA

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_runtime_import.log
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
  PARALLEL=4
~~~

`REMAP_SCHEMA` changes object ownership during import. It does not rewrite every hardcoded schema name embedded inside source code, dynamic SQL, config files, or external integrations. Audit views, procedures, packages, triggers, synonyms, database links, and application code for legacy schema references.

### 9.3. Changing Tablespaces with REMAP_TABLESPACE

~~~text
REMAP_TABLESPACE=APP_DATA:APP_DATA_NEW
REMAP_TABLESPACE=APP_INDEX:APP_INDEX_NEW
~~~

Multiple mappings may be specified. Target tablespaces must exist or be provisioned beforehand. Check partitions, LOBs, indexes, and segments with explicit tablespace overrides. Without remapping, Data Pump attempts to reuse old tablespace names in DDL.

### 9.4. Combining Remaps

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_runtime_import.log
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
  REMAP_TABLESPACE=APP_DATA:APP_DATA_NEW
  REMAP_TABLESPACE=APP_INDEX:APP_INDEX_NEW
  PARALLEL=4
  LOGTIME=ALL
  METRICS=YES
~~~

This is an example. In a parfile, place each `REMAP_TABLESPACE` on its own line per Data Pump syntax. Preview target DDL using `SQLFILE` before running production imports.

### 9.5. TABLE_EXISTS_ACTION

When a table already exists on the target, `TABLE_EXISTS_ACTION` controls behavior:

| Value | Behavior |
| --- | --- |
| `SKIP` | Skips existing tables |
| `APPEND` | Appends rows into existing tables |
| `TRUNCATE` | Truncates existing rows, then loads new rows |
| `REPLACE` | Drops existing tables and recreates them from the dump |

The default for existing tables is normally `SKIP`. Never use `APPEND` or `TRUNCATE` casually, as they risk duplicate data or wiping target data. `REPLACE` can destroy grants, constraints, triggers, or dependent objects if unmanaged.

For initial migrations, start with a clean or cleanly staged target schema. Never import over a schema serving live traffic.

## 10. Previewing DDL with SQLFILE

`SQLFILE` instructs Data Pump to write all DDL statements to a SQL script instead of executing the import. It is invaluable for reviewing schema remaps, tablespaces, users, grants, storage clauses, and object definitions.

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  SQLFILE=app_owner_preview.sql
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
  REMAP_TABLESPACE=APP_DATA:APP_DATA_NEW
~~~

`SQLFILE` is written to the server's `DIRECTORY`. Review owners, tablespaces, drop/replace statements, references to old schemas, grants to nonexistent users/roles, and objects requiring external files/directories/credentials.

`SQLFILE` is a DDL preview, not a data check. Some sensitive values may be masked or omitted by export behavior; never treat `SQLFILE` as a credential source.

## 11. Object Filtering Options

### 11.1. INCLUDE and EXCLUDE

Example importing only tables and sequences:

~~~text
INCLUDE=TABLE
INCLUDE=SEQUENCE
~~~

Example excluding statistics so they can be gathered fresh on target:

~~~text
EXCLUDE=STATISTICS
~~~

Do not apply these filters on a full migration without verifying whether views, packages, triggers, types, synonyms, grants, materialized views, and dependencies are needed.

Data Pump uses specific object path and filter syntax. Consult `DATABASE_EXPORT_OBJECTS` or `SCHEMA_EXPORT_OBJECTS` for valid object paths rather than guessing.

### 11.2. CONTENT

- `CONTENT=DATA_ONLY`: loads row data only into existing objects.
- `CONTENT=METADATA_ONLY`: creates metadata/DDL only, loading zero rows.
- Omit `CONTENT`: exports/imports both metadata and data per mode.

With `DATA_ONLY`, target table shapes must match and constraints/triggers may affect loading. Never drop objects casually without a recovery plan.

## 12. The NETWORK_LINK Option

Data Pump can stream data from a source database across a database link in supported workflows:

- `expdp` with `NETWORK_LINK` reads the remote source and writes dump files locally where the export job runs.
- `impdp` with `NETWORK_LINK` reads the remote source and loads directly into the target where supported.

Conceptual direct-import example:

~~~text
impdp system@TARGET_PDB
  NETWORK_LINK=SOURCE_LINK
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
  LOGFILE=network_import.log
~~~

`SOURCE_LINK` is a database link on the target pointing to the source. Check link privileges, network bandwidth/connectivity, version compatibility, supported data types, and Data Pump restrictions.

The advantage is avoiding intermediate dump file staging. Limitations include dependence on network throughput/latency, database link credentials and privileges, lack of an auditable dump artifact, and workflow-specific restrictions on versions, object types, and parallelism.

Choose dump files when you need an artifact that can be checksummed, archived, scanned, staged, or re-imported. Choose `NETWORK_LINK` when topology and policy allow it and load tests prove acceptable performance.

## 13. Dump File Encryption and Data Protection

Dump files may hold sensitive business data. Protect filesystem ACLs, Oracle OS process ownership, `DIRECTORY` privileges, transfer channels, staging/backup retention, and encryption.

Data Pump supports encryption parameters depending on version, edition, and configuration:

~~~text
ENCRYPTION=ALL
ENCRYPTION_MODE=PASSWORD
ENCRYPTION_PASSWORD=<supplied-securely>
~~~

This example is illustrative. Never store encryption passwords in parfiles committed to Git, shell history, or tickets. Supply via prompts or approved secret mechanisms and verify the target can decrypt the dump. Some encryption modes require TDE/keystore or carry edition/version prerequisites.

If a dump file is password-encrypted, store that password in a secret manager and transfer it over a secure channel. Losing the encryption password can render the dump un-importable.

## 14. Post-Import Data Verification

A clean import log does not prove business data accuracy. Compare source and target at the exact same snapshot or during a write-frozen window.

### 14.1. Table Counts

~~~sql
SELECT COUNT(*) AS table_count
FROM dba_tables
WHERE owner = 'APP_RUNTIME'
  AND nested = 'NO';
~~~

Compare source and target table counts using identical filters. Never compare total object counts while overlooking partitions, subpartitions, or nested tables.

### 14.2. Exact Row Counts

`DBA_TABLES.NUM_ROWS` is an optimizer statistic, not necessarily an exact live row count. After import, stats may be stale or missing. For critical tables, run `COUNT(*)` on both source and target:

~~~sql
SELECT COUNT(*) AS row_count
FROM APP_OWNER.ORDERS;
~~~

If remapped:

~~~sql
SELECT COUNT(*) AS row_count
FROM APP_RUNTIME.ORDERS;
~~~

Across many tables, generate a verified table list and run `COUNT(*)` per table. Never build dynamic SQL from untrusted input; quote schema/table identifiers strictly per Oracle rules.

### 14.3. Consistent Snapshots During Comparison

If the source continues taking writes while the target is imported, `COUNT(*)` at two different times will diverge even when export succeeded. Compare as of the exact same SCN using Flashback Query (while undo suffices), pause writers during cutover comparison, or use CDC/replication to catch up deltas before cutover.

Never compare live post-migration source counts against a target imported from an older SCN without accounting for transactions committed after that SCN.

### 14.4. Business-Level Data Comparisons

Row counts are necessary but insufficient. For key business tables, compare sum of amounts/quantities, `MIN`/`MAX` business keys, counts grouped by status, `NULL` counts in mandatory columns, row totals by date/month/partition, duplicate business keys, and orphan rows.

Example:

~~~sql
SELECT status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS amount_sum,
       MIN(order_id) AS min_order_id,
       MAX(order_id) AS max_order_id
FROM APP_RUNTIME.ORDERS
GROUP BY status
ORDER BY status;
~~~

Run the identical query on the source at the matching snapshot and compare. If data types or rounding differ, define explicit business tolerances rather than comparing formatted strings.

### 14.5. Data Hashes and Checksums

For critical tables, generate digests by key range or partition to compare. Hashes must be computed over ordered columns with strict canonical representation; naive string concatenation can suffer logical collisions from nulls, delimiters, timezones, number formatting, and character encodings.

Conceptual example:

~~~sql
SELECT STANDARD_HASH(
           TO_CHAR(order_id) || '|' ||
           NVL(status, '<NULL>') || '|' ||
           TO_CHAR(total_amount, 'FM9999999999990D00',
                   'NLS_NUMERIC_CHARACTERS=.,'),
           'SHA256'
       ) AS row_hash
FROM APP_RUNTIME.ORDERS
WHERE order_id BETWEEN 1 AND 100000
ORDER BY order_id;
~~~

This is an illustrative snippet. Design canonical encodings for every data type; for `CLOB`/`BLOB`, `TIMESTAMP WITH TIME ZONE`, and large payloads, build dedicated digest routines. Hashing complements—never replaces—row counts, constraints, and business checks.

### 14.6. Partitions and LOBs

~~~sql
SELECT table_name,
       partition_name,
       num_rows,
       tablespace_name
FROM dba_tab_partitions
WHERE table_owner = 'APP_RUNTIME'
ORDER BY table_name, partition_position;

SELECT owner,
       table_name,
       column_name,
       segment_name,
       tablespace_name,
       securefile
FROM dba_lobs
WHERE owner = 'APP_RUNTIME'
ORDER BY table_name, column_name;
~~~

Verify partitions, subpartitions, and LOB segments. A table with a matching total row count could still miss empty partitions or have wrong tablespace or LOB storage attributes.

## 15. Post-Import Object Verification

### 15.1. Object Counts by Type and Status

~~~sql
SELECT object_type,
       status,
       COUNT(*) AS object_count
FROM dba_objects
WHERE owner = 'APP_RUNTIME'
GROUP BY object_type, status
ORDER BY object_type, status;
~~~

Compare against the source baseline after accounting for owner remapping. Investigate any missing, extra, or `INVALID` objects.

### 15.2. Invalid Objects and Compile Errors

~~~sql
SELECT object_type,
       object_name,
       status
FROM dba_objects
WHERE owner = 'APP_RUNTIME'
  AND status <> 'VALID'
ORDER BY object_type, object_name;

SELECT name,
       type,
       line,
       position,
       text
FROM dba_errors
WHERE owner = 'APP_RUNTIME'
ORDER BY name, sequence;
~~~

If objects are invalid because dependencies were created later during import, recompile after import finishes:

~~~sql
BEGIN
    DBMS_UTILITY.COMPILE_SCHEMA(
        schema      => 'APP_RUNTIME',
        compile_all => FALSE
    );
END;
/
~~~

For multiple schemas or complex invalidations, run an appropriate compilation pass and re-check `DBA_ERRORS`. Never gloss over invalid objects by merely running compile without reading error messages.

### 15.3. Indexes

~~~sql
SELECT index_name,
       table_name,
       index_type,
       uniqueness,
       status,
       tablespace_name
FROM dba_indexes
WHERE owner = 'APP_RUNTIME'
ORDER BY table_name, index_name;

SELECT index_name,
       partition_name,
       status,
       tablespace_name
FROM dba_ind_partitions
WHERE index_owner = 'APP_RUNTIME'
ORDER BY index_name, partition_position;
~~~

Check for `UNUSABLE` indexes, unusable index partitions, skipped indexes, or index creation failures caused by quota or tablespace limits.

### 15.4. Constraints

~~~sql
SELECT table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred
FROM dba_constraints
WHERE owner = 'APP_RUNTIME'
ORDER BY table_name, constraint_name;
~~~

Check key attributes: `ENABLED`/`DISABLED`, `VALIDATED`/`NOT VALIDATED`, `DEFERRABLE`/`NOT DEFERRABLE`, foreign key states, and unique/primary keys. Verify both counts and statuses.

### 15.5. Triggers

~~~sql
SELECT trigger_name,
       table_name,
       status,
       triggering_event,
       trigger_type
FROM dba_triggers
WHERE owner = 'APP_RUNTIME'
ORDER BY table_name, trigger_name;
~~~

Triggers can mutate data during application testing. During validation, avoid running test DML on production schemas without understanding trigger side effects.

### 15.6. Views and Materialized Views

~~~sql
SELECT object_name,
       status
FROM dba_objects
WHERE owner = 'APP_RUNTIME'
  AND object_type IN ('VIEW', 'MATERIALIZED VIEW')
ORDER BY object_type, object_name;
~~~

For materialized views, verify refresh modes, refresh groups/jobs, materialized view logs, and dependencies. Importing the object does not guarantee materialized view contents were refreshed at cutover time.

### 15.7. Sequences and Identity Columns

~~~sql
SELECT sequence_name,
       min_value,
       max_value,
       increment_by,
       cycle_flag,
       order_flag,
       cache_size,
       last_number
FROM dba_sequences
WHERE sequence_owner = 'APP_RUNTIME'
ORDER BY sequence_name;
~~~

`LAST_NUMBER` reflects cached/high-water allocation boundaries rather than necessarily the exact next `NEXTVAL`. Comparing sequences solely by `LAST_NUMBER` can mislead.

When migrations must preserve monotonic ID issuance:

1. Stop writers or lock ID generation on the source.
2. Record high-water marks via a tested procedure.
3. Import sequence definitions.
4. Verify target `NEXTVAL` is never below IDs already issued on the source.
5. Adjust sequences if needed while respecting `INCREMENT`/`CACHE`/`CYCLE`.
6. Open target writers only after verification.

For identity columns, check identity metadata and post-import generated values using a rollback-safe transaction test or scratch table. Never reset sequences or identities blindly, which risks primary key collisions.

### 15.8. Grants and Quotas

~~~sql
SELECT grantee,
       table_name,
       privilege,
       grantable
FROM dba_tab_privs
WHERE owner = 'APP_RUNTIME'
ORDER BY grantee, table_name, privilege;

SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee = 'APP_RUNTIME'
ORDER BY privilege;

SELECT grantee,
       granted_role,
       admin_option,
       default_role
FROM dba_role_privs
WHERE grantee = 'APP_RUNTIME'
ORDER BY granted_role;

SELECT username,
       tablespace_name,
       bytes,
       max_bytes
FROM dba_ts_quotas
WHERE username = 'APP_RUNTIME'
ORDER BY tablespace_name;
~~~

If schema ownership changed, legacy object grants may need to be reissued for target users and roles. Confirm the application uses the intended runtime account with active privileges.

## 16. Verifying Dependencies and Application Components

### 16.1. Intra-Schema and Cross-Schema Dependencies

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM dba_dependencies
WHERE owner = 'APP_RUNTIME'
ORDER BY name, referenced_owner, referenced_name;
~~~

Locate dependencies still pointing to the legacy schema:

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM dba_dependencies
WHERE owner = 'APP_RUNTIME'
  AND referenced_owner = 'APP_OWNER'
ORDER BY name;
~~~

Flag these for investigation, though not every reference is wrong: the new schema might intentionally query an old schema or use a database link.

### 16.2. Dynamic SQL

`DBA_DEPENDENCIES` cannot detect schema names concatenated inside dynamic SQL, stored strings, Java code, configuration files, or scheduler commands. Search source repositories/configurations and run end-to-end functional tests.

### 16.3. Scheduler Jobs

~~~sql
SELECT owner,
       job_name,
       enabled,
       state,
       job_type,
       job_action,
       schedule_name
FROM dba_scheduler_jobs
WHERE owner = 'APP_RUNTIME'
ORDER BY job_name;
~~~

Jobs may import enabled or disabled; keep them disabled prior to cutover so they do not run simultaneously on both source and target. Enable on the target only when operational ownership transfers.

### 16.4. Database Links and Network ACLs

Verify DB link hosts, services, and credentials. Create or update Network ACLs for the target host and user. Test `UTL_HTTP`/`UTL_TCP` against approved test endpoints.

### 16.5. External Tables and Files

External tables rely on files stored on OS filesystems or object storage. Data Pump does not copy external data files. Transfer files, verify `DIRECTORY` objects, OS permissions, and credentials/ACLs on the target.

### 16.6. Public Synonyms and Public Grants

Public synonyms and public grants are database-scoped. If the application depends on them, recreate them via dedicated change scripts after confirming zero naming collisions and correct target ownership.

## 17. Systematic Source-to-Target Comparison

### 17.1. Building a Migration Manifest

Before export, record a manifest containing:

- Source DB/PDB/service and target DB/PDB/service.
- Source and target schemas.
- Export SCN.
- Source-to-target tablespace mapping.
- Object counts by type and status.
- Segment sizes by tablespace and type.
- Row counts and business aggregates for core tables.
- Sequence/identity high-water notes.
- Out-of-schema grants, roles, quotas, and dependencies.
- Dump file list, sizes, and checksums.
- Export/import log paths and timestamps.

The manifest serves as the verification baseline. Never store passwords, tokens, or encryption passwords inside the manifest.

### 17.2. File Checksums

After copying dump files to the target, compute checksums using OS utilities:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'D:\dpump\app_owner_01.dmp'
~~~

Compare source and target hashes for every piece. Checksums prove file integrity during transfer; they do not prove logical dump contents are valid or that all objects imported cleanly.

### 17.3. Validation Matrix

| Group | Source Baseline | Target Check | Acceptance Criteria |
| --- | --- | --- | --- |
| Database/PDB | DB name, service, SCN | Target service/PDB matches | Connected to intended target |
| Schema | Owner, status, default TS | Target owner, quota, status | User and privileges valid |
| Tables | Table/partition counts | `DBA_TABLES`/`DBA_TAB_PARTITIONS` | Zero unplanned missing objects |
| Data | Exact counts/aggregates at SCN | Exact counts/aggregates | Matches snapshot |
| Indexes | Count/status/partitions | `DBA_INDEXES`/`DBA_IND_PARTITIONS` | Zero unplanned `UNUSABLE` indexes |
| Constraints | Type/status/validated | `DBA_CONSTRAINTS` | Semantics preserved |
| Program units | Object status/errors | `DBA_OBJECTS`/`DBA_ERRORS` | `VALID` or approved exception |
| Sequences | Definition/high-water | `DBA_SEQUENCES` and `NEXTVAL` test | Zero duplicate ID generation |
| Grants | System/role/object grants | `DBA_*_PRIVS` | Sufficient least-privilege access |
| Dependencies | Cross-schema refs | `DBA_DEPENDENCIES` and app tests | Zero unintended legacy refs |
| External | Jobs, links, files, ACLs | Checked individually | Recreated and secured |
| Application | Business smoke tests | Executed on target | All business flows pass |

## 18. Cutover Plan

### 18.1. Pre-Cutover

1. Complete full staging rehearsal.
2. Finalize maintenance window and owners.
3. Verify source and target backups.
4. Confirm dump files and checksums are ready.
5. Verify target capacity, services, accounts, and monitoring.
6. Disable or pause schedulers/jobs that could double-execute.
7. Stage application configuration pointing to the target.
8. Define rollback procedures and rollback trigger criteria.

### 18.2. Cutover with Downtime

~~~text
1. Stop application writers
2. Stop/pause background jobs and integrations
3. Record final SCN or freeze source writes
4. Run final expdp (or final delta method)
5. Transfer and verify dump files
6. Run impdp on target
7. Validate row counts, objects, grants and dependencies
8. Enable target jobs and integrations deliberately
9. Point application to target service
10. Run smoke tests and monitor
11. Declare target primary for writes
~~~

If an earlier full export ran while the source kept taking writes after its SCN, the dump lacks post-SCN changes. Run a final export or delta/CDC catch-up. Simply repointing the JDBC URL without capturing deltas will lose transactions committed after the snapshot.

### 18.3. Low-Downtime Cutover

You can perform an initial export/import and synchronize trailing changes via replication/CDC or a supported delta strategy. Data Pump is not a continuous CDC tool. You must define how to capture `INSERT`/`UPDATE`/`DELETE` after the initial SCN, preserve transaction order, handle DDL, sync sequences and schedulers, drain writers, apply the final delta, and verify source/target convergence.

Never stitch multiple exports together with `APPEND` without explicit deduplication and ordering logic.

## 19. Rollback Plan

Design rollback before shifting traffic:

- Keep the source database and schema intact and recoverable for an agreed window.
- Retain dump files, logs, manifest, and checksums.
- Do not drop the source schema right after cutover.
- Record the exact timestamp when the target begins accepting writes.
- Once the target accepts writes, never just point URLs back to source, because source will miss new transactions.
- Define reverse-sync or data reconciliation steps if falling back after writes.
- Keep jobs/integrations disabled on the inactive side to prevent duplicate events or double batch runs.
- Check sequences/identities when rolling back.

Before the target accepts writes, rollback can be as simple as repointing the application back to source. Once the target accepts writes, rollback becomes a bidirectional data sync or log/CDC recovery problem—not a simple connection-string flip.

## 20. Common Data Pump Errors

| Error / Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `ORA-39002` invalid operation | Invalid parameters/job or incompatible mode | Read accompanying errors and check parfile |
| `ORA-39070` unable to open log file | `DIRECTORY`/path/OS permission issue | Check `DIRECTORY` object, path, and Oracle OS permissions |
| `ORA-39087` directory name invalid | `DIRECTORY` object missing or misspelled | Create/verify `DIRECTORY` and privileges |
| `ORA-31655` no data or metadata objects selected | Filter/schema mismatch or lacking visibility privileges | Verify `SCHEMAS`, `INCLUDE`/`EXCLUDE`, and privileges |
| `ORA-39151` table exists | Table exists on target and action is `SKIP` | Clean target or choose `TABLE_EXISTS_ACTION` carefully |
| `ORA-31684` object already exists | Metadata object already present | Decide which objects to keep or recreate |
| `ORA-01918` user does not exist | Target owner missing or user metadata not imported as planned | Pre-create user / configure remap and inspect `SQLFILE` |
| `ORA-00959` tablespace does not exist | Source tablespace lacks target mapping | Create target TS or use `REMAP_TABLESPACE` |
| `ORA-01653` unable to extend table | Target tablespace out of space/quota | Check datafiles, autoextend, quotas, and storage |
| `ORA-01031` insufficient privileges | Account running Data Pump lacks privileges | Grant required privileges or use approved admin account |
| `ORA-01555` during export | Insufficient undo to retain export snapshot | Shorten export, size undo properly, pick quieter window |
| `ORA-39126` worker unexpected fatal error | Worker hit error on specific object/metadata | Read full stack/log and isolate offending object |
| `ORA-39083` object creation failed | Specific object DDL failed (dependency, privilege, syntax) | Read failing SQL in log/`SQLFILE` and fix root cause |
| Invalid objects after import | Missing dependencies, grants, or version differences | Restore dependencies, recompile, check `DBA_ERRORS` |
| Row count mismatch | Differing SCNs, missing objects, filters, or load failures | Reconcile snapshot, logs, filters, and affected tables |

Never ignore object errors just to get a completed job status. An import with warnings may be acceptable if every error is understood, handled separately, and documented in the manifest; any unexplained error must block cutover.

## 21. Lab: Migrating Schema APP_OWNER to APP_RUNTIME

Run this lab across two test databases or PDBs. Never use production schemas or real passwords.

### 21.1. Creating the Source Schema and Tables

~~~sql
CREATE USER APP_OWNER
IDENTIFIED BY "LabOnlyPassword"
DEFAULT TABLESPACE USERS
QUOTA UNLIMITED ON USERS;

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW,
      CREATE SEQUENCE, CREATE PROCEDURE, CREATE TRIGGER
TO APP_OWNER;
~~~

Connect as `APP_OWNER`:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE SEQUENCE customers_seq START WITH 1001 INCREMENT BY 1;

CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    total_amount NUMBER(12,2) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT orders_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

INSERT INTO customers(customer_id, customer_name)
VALUES (1, 'Customer A');

INSERT INTO customers(customer_id, customer_name)
VALUES (2, 'Customer B');

INSERT INTO orders(order_id, customer_id, status, total_amount)
VALUES (101, 1, 'NEW', 120.50);

INSERT INTO orders(order_id, customer_id, status, total_amount)
VALUES (102, 2, 'PAID', 350.00);

COMMIT;
~~~

### 21.2. Recording Baseline

~~~sql
SELECT COUNT(*) AS customer_count FROM customers;
SELECT COUNT(*) AS order_count FROM orders;

SELECT status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders
GROUP BY status
ORDER BY status;
~~~

Record object lists, schema name, tablespaces, and source SCN.

### 21.3. Export

Create the `DIRECTORY` object and parfile for your lab environment. Run:

~~~text
expdp system@SOURCE_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_owner_export.log
  SCHEMAS=APP_OWNER
  FLASHBACK_SCN=<SCN_FROM_SOURCE>
  PARALLEL=2
  LOGTIME=ALL
  METRICS=YES
~~~

Replace the SCN placeholder with the captured SCN. Inspect the log and generated files.

### 21.4. Creating the Target User

~~~sql
CREATE USER APP_RUNTIME
IDENTIFIED BY "AnotherLabPassword"
DEFAULT TABLESPACE USERS
QUOTA UNLIMITED ON USERS;

GRANT CREATE SESSION TO APP_RUNTIME;
~~~

In the lab, `USERS` can hold all objects. In production, provision dedicated tablespaces and explicit quotas.

### 21.5. Previewing SQLFILE

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  SQLFILE=app_preview.sql
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
~~~

Review the generated DDL before importing.

### 21.6. Import

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_runtime_import.log
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
  PARALLEL=2
  LOGTIME=ALL
  METRICS=YES
~~~

### 21.7. Reconciling Data

On the target:

~~~sql
SELECT COUNT(*) AS customer_count
FROM APP_RUNTIME.CUSTOMERS;

SELECT COUNT(*) AS order_count
FROM APP_RUNTIME.ORDERS;

SELECT status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM APP_RUNTIME.ORDERS
GROUP BY status
ORDER BY status;
~~~

Compare against the source baseline. Verify constraints, sequences, object statuses, and grants.

### 21.8. Application Testing

Log in using the runtime account, query customers/orders, insert an order inside a test transaction and roll back, and verify foreign keys, sequence/ID generation, and any procedures/views created in the lab.

Do not verify row counts alone; confirm the application can execute real workflows under runtime privileges.

## 22. Pre-Sign-Off Migration Checklist

1. **Correct source?** Database, PDB, service, and schema owner.
2. **Correct target?** Database/PDB/service and version compatibility.
3. **Baseline captured?** SCN, object counts, row counts, aggregates, and grants.
4. **Out-of-schema dependencies identified?** Cross-schema references, links, ACLs, directories, and jobs.
5. **Tablespace mappings clear?** Segments, LOBs, partitions, and quotas.
6. **Enough undo for `FLASHBACK_SCN`?** Export duration and undo workload assessed.
7. **Complete dump files?** All pieces, checksums, and storage verified.
8. **Clean export log?** Every warning/error classified.
9. **`SQLFILE` reviewed?** Owners, tablespaces, DDL, and grants.
10. **Import log inspected?** Zero ignored object creation failures.
11. **Schemas/users/roles ready?** Profiles, quotas, grants, and secrets.
12. **Data reconciled?** Exact counts and business aggregates at matching snapshot.
13. **Objects checked?** Invalids, indexes, constraints, triggers, views, packages.
14. **Sequences/identities checked?** Zero risk of duplicate ID generation.
15. **Schedulers and integrations controlled?** No duplicate jobs running in both places.
16. **External files/directories migrated?** Filesystem paths and ACLs verified.
17. **Application smoke tests passed?** Right service/PDB and runtime privileges.
18. **Cutover window and rollback clear?** Source writers, target writers, and delta handling.
19. **Target backups/monitoring ready?** Operable immediately after cutover.
20. **Business owner sign-off obtained?** Data and workflows formally accepted.

## 23. Self-Check Questions

**Question 1.** Is Data Pump a logical or physical migration?

**Question 2.** How does `SCHEMAS` differ from `FULL=Y`?

**Question 3.** Where does a `DIRECTORY` object point?

**Question 4.** Why must you inventory out-of-schema dependencies?

**Question 5.** What does `FLASHBACK_SCN` guarantee during export?

**Question 6.** Why can an export with `FLASHBACK_SCN` encounter `ORA-01555`?

**Question 7.** What does `REMAP_SCHEMA` do, and what does it not do?

**Question 8.** What is `REMAP_TABLESPACE` used for?

**Question 9.** What risks come with `TABLE_EXISTS_ACTION=REPLACE`?

**Question 10.** At which step is `SQLFILE` useful?

**Question 11.** Why is `DBA_TABLES.NUM_ROWS` not an exact row count?

**Question 12.** Why must source and target be compared at the same SCN or during a write freeze?

**Question 13.** Why is `DBA_SEQUENCES.LAST_NUMBER` not necessarily the exact next `NEXTVAL`?

**Question 14.** Which components do not automatically move in schema mode alone?

**Question 15.** Why must scheduler jobs be controlled during cutover?

**Question 16.** What does a dump file checksum prove?

**Question 17.** Why must invalid objects be compared against the source baseline?

**Question 18.** Are two local transactions on two databases automatically atomic together?

**Question 19.** Why is rollback harder after the target has accepted writes than before cutover?

**Question 20.** What conditions must be met before switching application traffic?

<details>
<summary>Suggested Answers</summary>

1. Logical migration: Data Pump exports and imports metadata and row data.
2. `SCHEMAS` selects one or more schemas; `FULL` targets database-wide scope.
3. A directory on the database server where the Oracle process has OS read/write permissions.
4. Schemas may reference objects, roles, links, or resources owned by other schemas or the database.
5. Exports data as of the chosen snapshot SCN where supported by Flashback Query.
6. Undo needed to reconstruct the snapshot may be overwritten before export finishes.
7. Changes object ownership during import; does not automatically rewrite hardcoded schema names in code or external configs.
8. Maps source tablespaces to target tablespaces.
9. Drops and recreates existing tables, risking target data, grants, and dependencies.
10. Previewing import DDL to review remaps, tablespaces, users, and objects.
11. It is an optimizer statistic that may be stale or ungathered.
12. Avoids comparing two datasets captured at different points in time.
13. Sequence caching and allocation mean `LAST_NUMBER` can reflect cache boundaries.
14. Listeners/services, external files, OS directories, ACLs, wallets, app configs, and certain public/database-level metadata.
15. Prevents the same job from firing on both source and target, avoiding duplicate events or batches.
16. Confirms the file was not corrupted during transfer; does not prove logical contents are valid.
17. Distinguishes pre-existing invalids from newly introduced migration failures.
18. No; requires JTA/XA or distributed patterns such as Saga/outbox.
19. The target holds new transactions absent from the source; simply switching URLs back drops or splits data.
20. Data, objects, grants, dependencies, sequences, app smoke tests, and rollback plans are all verified and approved.

</details>

## 24. Official Oracle Documentation

1. [Oracle Database 19c Database Utilities — Oracle Data Pump Overview](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-overview.html): architecture, export/import modes, and jobs.
2. [Oracle Database 19c Database Utilities — Data Pump Export](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html): `expdp`, schema mode, Flashback, and dump parameters.
3. [Oracle Database 19c Database Utilities — Data Pump Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-import-utility.html): `impdp`, `REMAP_SCHEMA`, `REMAP_TABLESPACE`, `TABLE_EXISTS_ACTION`, and `SQLFILE`.
4. [Oracle Database 19c Database Utilities — Data Pump Export Parameters](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html): filters, parallelism, compression, and consistency parameters.
5. [Oracle Database 19c Database Utilities — Data Pump Import Parameters](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-import-utility.html): import filters, remapping, and network links.
6. [Oracle Database 19c Administrator's Guide — Managing Users and Security](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): users, roles, privileges, and secure credential management.
7. [Oracle Database 19c Reference — DBA_OBJECTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_OBJECTS.html): object inventory and status.
8. [Oracle Database 19c Reference — DBA_DEPENDENCIES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DEPENDENCIES.html): dependencies across database objects.
9. [Oracle Database 19c SQL Language Reference — STANDARD_HASH](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/STANDARD_HASH.html): computing hashes for data reconciliation.

**Key Principle to Remember:** Schema migration with Data Pump starts with a thorough inventory and a consistent snapshot, followed by controlled export/import with explicit remapping. Verify row counts, business aggregates, object statuses, indexes, constraints, sequences, grants, and dependencies; handle directories, external files, database links, ACLs, schedulers, wallets, and application configs separately. Cut over only after data reconciles at the same snapshot, the application runs cleanly on the target, and the rollback plan is crystal clear.
