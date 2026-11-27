# Transportable Tablespaces and Full Transportable Under Compatibility Conditions

## 1. Overview

**Transportable Tablespaces (TTS)** is an Oracle data movement method that transfers metadata via Data Pump and moves tablespace datafiles directly to the target database. Instead of reading and rewriting every row like traditional export/import, Oracle can attach the transported datafiles to the target database after verifying metadata and compatibility conditions.

This method is particularly useful when:

- Moving a large set of tablespaces between two databases.
- Transferring data between systems with different storage or platforms.
- Reducing downtime compared to row-level export/import for large data volumes.
- Separating a group of schemas/tablespaces from a source database.
- Moving data from a legacy system to a new database as part of an upgrade plan.

**Full Transportable Export/Import** extends this method nearly to full-database scope. User tablespaces are transported via datafiles; metadata and data residing in non-transportable tablespaces (notably SYSTEM and SYSAUX) are processed through Data Pump.

Neither method is a backup. Copied datafiles on the target must be consistent, metadata must match the datafiles, and dependencies must be verified before bringing the target database into service.

## 2. How Do Transportable Tablespaces Work?

A transportable tablespace set consists of:

1. Datafiles of the selected tablespaces.
2. Metadata describing objects inside those tablespaces, exported via Data Pump.
3. Required dependencies so the tablespace set can be attached to the target database.

Basic flow:

~~~text
SOURCE DATABASE
      |
      | 1. Check transport set self-containment
      v
DBMS_TTS.TRANSPORT_SET_CHECK
      |
      | 2. Put tablespaces into READ ONLY
      v
ALTER TABLESPACE ... READ ONLY
      |
      | 3. Export metadata
      v
Data Pump expdp
      |
      +--------------------------+
      |                          |
      v                          v
Metadata dump file          Tablespace datafiles
      |                          |
      +------------+-------------+
                   |
                   | 4. Copy to target
                   v
             TARGET DATABASE
                   |
                   | 5. impdp + TRANSPORT_DATAFILES
                   v
             Attach/import metadata
                   |
                   | 6. Verify objects and dependencies
                   v
             READ WRITE / Application
~~~

Key differences:

- A TTS dump file primarily contains metadata.
- Table data resides inside separately copied datafiles.
- Datafiles must be in a consistent state when transported.
- The target must understand the metadata, block format, platform, and associated datafile attributes.

## 3. Transport Set Scope and Requirements

### 3.1. Select the right tablespaces

Transportable tablespaces operate at the tablespace level, not solely the schema level. One schema can own objects across multiple tablespaces; one tablespace can also hold objects from multiple schemas.

Before selecting the transport set, check:

~~~sql
SELECT owner,
       segment_type,
       segment_name,
       partition_name,
       tablespace_name
FROM dba_segments
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX')
ORDER BY owner, segment_type, segment_name;
~~~

For partitioned tables or partitioned indexes, partitions/subpartitions can span multiple tablespaces. Identify every tablespace containing portions to be transported.

### 3.2. Transport set must be self-contained

A transport set is **self-contained** when required dependencies do not cross outside the selected set of tablespaces according to Oracle's validation rules.

Example:

- A table in APP_DATA has a foreign key referencing a table in APP_REFERENCE.
- If only APP_DATA is transported, the referential dependency lies outside the set.
- You may need to include APP_REFERENCE in the transport set or handle the dependency via a supported design.

Check using the DBMS_TTS package:

~~~sql
EXEC DBMS_TTS.TRANSPORT_SET_CHECK(
    ts_list          => 'APP_DATA,APP_INDEX,APP_REFERENCE',
    incl_constraints => TRUE,
    full_check       => TRUE
);
~~~

View violations:

~~~sql
SELECT *
FROM transport_set_violations;
~~~

If the query returns rows, resolve each violation before exporting. Never ignore warnings just to push an expdp command through.

### 3.3. Why also check constraints?

Foreign keys or constraints can link objects across different tablespaces. During a partial transport, the target might lack a referenced table or lack the metadata required to rebuild the dependency.

Use FULL_CHECK to request a thorough dependency check within DBMS_TTS scope. Verify indexes, partitions, LOB segments, and related objects in the data dictionary as well.

### 3.4. Tablespaces not transported like regular application tablespaces

Do not include system tablespaces such as SYSTEM, SYSAUX, UNDO, or TEMP in a transportable application tablespace set. They serve internal database roles and are created/managed by the target database architecture.

With full transportable, SYSTEM and SYSAUX still belong to the target database; user data residing in these tablespaces is handled via Data Pump rather than copying raw system datafiles.

### 3.5. Inspecting tablespaces and datafiles

~~~sql
SELECT tablespace_name,
       status,
       contents,
       block_size,
       bigfile
FROM dba_tablespaces
ORDER BY tablespace_name;

SELECT tablespace_name,
       file_id,
       file_name,
       bytes,
       autoextensible
FROM dba_data_files
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX', 'APP_REFERENCE')
ORDER BY tablespace_name, file_id;
~~~

Ensure every datafile is identified accurately, including files belonging to multi-datafile or bigfile tablespaces.

## 4. Compatibility Requirements Between Source and Target

TTS is not simply copying a DBF file to another machine. Datafiles carry platform, endian format, block size, database compatibility, and database-dependent metadata. Build a compatibility matrix before executing.

### 4.1. Platform and endian format

Oracle provides the list of platforms eligible for transport:

~~~sql
SELECT platform_id,
       platform_name,
       endian_format
FROM v$transportable_platform
ORDER BY platform_name;
~~~

Check the current database platform:

~~~sql
SELECT platform_name
FROM v$database;
~~~

If source and target share the same endian format, datafiles typically do not need endian conversion. If endian formats differ, convert datafiles using RMAN CONVERT or another Oracle-supported method.

Endian examples:

| Platform family | Typical endianness |
| --- | --- |
| Linux x86/x86-64 | Little endian |
| Windows x86/x86-64 | Little endian |
| Solaris SPARC | Big endian |
| AIX POWER | Big endian |

Do not guess from the OS name alone; retrieve ENDIAN_FORMAT from V$TRANSPORTABLE_PLATFORM for both the exact source and target platforms.

### 4.2. Endian conversion with RMAN

Illustrative example converting a tablespace to the target platform:

~~~text
RMAN> CONVERT TABLESPACE app_data
      TO PLATFORM 'Linux x86 64-bit'
      FORMAT '/stage/tts/%U';
~~~

The platform name must match PLATFORM_NAME in V$TRANSPORTABLE_PLATFORM. FORMAT specifies the output location on the host running conversion.

Conversion can run on source or target depending on workflow, network, and staging storage. Whichever host is chosen, datafiles must be in a consistent state as required by RMAN and TTS. Perform conversion before importing/attaching datafiles on the target.

Example checking/converting a staged datafile:

~~~text
RMAN> CONVERT DATAFILE '/stage/tts/app_data01.dbf'
      TO PLATFORM 'Linux x86 64-bit'
      FORMAT '/target/stage/app_data01.dbf';
~~~

This is illustrative syntax; files already converted on the source must not be converted again. Never convert datafiles actively being written by the source database.

### 4.3. Database version and COMPATIBLE

Data Pump dump files carry metadata versions, and the target must be able to read that metadata. The general rule is moving from source to a same-version or newer target; do not assume you can transport backward from a newer database to an older one.

Check:

~~~sql
SELECT banner_full
FROM v$version
WHERE banner_full LIKE 'Oracle Database%';

SHOW PARAMETER compatible;
~~~

Verify:

- Release and Release Update of source/target.
- Data Pump export/import versions.
- COMPATIBLE initialization parameter.
- Features or data types unique to the source version.
- Downgrade/upgrade rules in the Oracle Database Upgrade Guide.

Never lower COMPATIBLE just to force transportable compatibility. Changing COMPATIBLE can affect features and downgrade eligibility.

### 4.4. Block size

Tablespaces can use a block size different from the database's standard block size. The target must configure matching buffer caches to support nonstandard block sizes.

Check:

~~~sql
SELECT tablespace_name,
       block_size
FROM dba_tablespaces
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX');

SHOW PARAMETER db_block_size;
SHOW PARAMETER db_2k_cache_size;
SHOW PARAMETER db_4k_cache_size;
SHOW PARAMETER db_8k_cache_size;
SHOW PARAMETER db_16k_cache_size;
SHOW PARAMETER db_32k_cache_size;
~~~

These cache parameters are examples by block size. Configure only the caches required on the target and ensure SGA has enough capacity.

### 4.5. Character set and national character set

Because table data travels inside datafiles, do not assume Data Pump converts every byte inside a datafile as in conventional export/import.

Before transport, compare:

~~~sql
SELECT parameter,
       value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
~~~

For traditional transportable tablespaces, treat character set compatibility between source and target as a mandatory gate to verify per release/platform. If character sets differ, do not proceed merely because metadata export/import runs; evaluate an Oracle-supported conversion approach, such as conventional Data Pump migration or a dedicated database conversion procedure.

Full transportable can handle data inside non-transportable tablespaces via Data Pump, yet transportable datafiles must still satisfy transportable data compatibility rules. Do not use full transportable as an automatic converter for arbitrary character sets.

### 4.6. Time zone file version

If tablespaces contain TIMESTAMP WITH TIME ZONE columns, check the timezone file version:

~~~sql
SELECT filename,
       version
FROM v$timezone_file;
~~~

Timezone file differences can affect how timestamp data is interpreted and import/upgrade eligibility. Identify the target timezone file version, check Oracle Data Pump/TTS requirements, and perform a DBMS_DST upgrade if needed via a dedicated procedure. Never manually patch bytes inside datafiles to handle timezones.

### 4.7. TDE and encrypted tablespaces

If the transport set contains encrypted tablespaces or TDE-dependent data:

- Identify the active keystore/wallet.
- Verify the keystore is backed up and openable.
- Ensure the target has the required keys or follows the proper key export/import procedure.
- Transfer keys over secure channels; never leave secrets in command history or logs.
- Verify encryption mode, algorithm, and key versions after import.

Encrypted datafiles cannot be read simply by copying files to the target if the target lacks the matching keys. For encrypted tablespaces, follow the exact release's TDE transportable tablespace procedure.

### 4.8. Other conditions

Also verify:

- Target database is created and open in the proper mode.
- Target tablespace names do not collide.
- Schema owners/users and quotas exist or are imported properly.
- Target has enough space for all datafiles.
- Data Pump directory objects exist with proper read/write permissions.
- Filesystem file permissions/ownership are correct.
- ASM disk groups or OMF paths are properly configured.
- Tablespace encryption, compression, SecureFiles, and data types are supported.
- No dependencies exist outside the transport set.

## 5. Traditional Transportable Tablespaces Workflow

Example transporting APP_DATA and APP_INDEX from source to target. Assume both tablespaces passed compatibility checks and the target has prepared required schemas/metadata.

### Step 1. Check the source

~~~sql
SELECT name,
       open_mode,
       database_role,
       platform_name
FROM v$database;

SELECT tablespace_name,
       status,
       contents,
       block_size
FROM dba_tablespaces
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX');
~~~

Inspect all objects and datafiles belonging to both tablespaces. Run DBMS_TTS.TRANSPORT_SET_CHECK with FULL_CHECK before moving.

### Step 2. Confirm the transport set is self-contained

~~~sql
EXEC DBMS_TTS.TRANSPORT_SET_CHECK(
    ts_list          => 'APP_DATA,APP_INDEX',
    incl_constraints => TRUE,
    full_check       => TRUE
);

SELECT *
FROM transport_set_violations;
~~~

Zero violations must remain. If violations appear, expand the transport set or resolve dependencies before continuing.

### Step 3. Set tablespaces to READ ONLY

~~~sql
ALTER TABLESPACE app_data READ ONLY;
ALTER TABLESPACE app_index READ ONLY;
~~~

READ ONLY ensures datafiles do not change while metadata is exported and files are copied. Applications cannot write to these tablespaces during the cutover window.

### Step 4. Export metadata with Data Pump

Create a directory object if not already present:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_dir AS '/u02/dpump';
GRANT READ, WRITE ON DIRECTORY dpump_dir TO system;
~~~

Run expdp:

~~~text
expdp system@source_db DIRECTORY=DPUMP_DIR
  DUMPFILE=app_tts.dmp
  LOGFILE=app_tts_export.log
  TRANSPORT_TABLESPACES=APP_DATA,APP_INDEX
  TRANSPORT_FULL_CHECK=Y
~~~

Transportable export focuses on metadata for objects inside the tablespaces; row data stays inside the datafiles. Protect dump files and logs per operational policy.

### Step 5. Copy datafiles and dump file

Copy all datafiles belonging to APP_DATA and APP_INDEX to staging/target. Copy dump file `app_tts.dmp` to a directory readable by Data Pump import.

If source and target differ in endianness, run RMAN conversion to the target platform before importing. If endianness matches, datafiles can be copied directly when other conditions are satisfied.

Never miss a datafile or copy only one file from a multi-datafile tablespace.

### Step 6. Import metadata and attach datafiles

On the target:

~~~text
impdp system@target_db DIRECTORY=DPUMP_DIR
  DUMPFILE=app_tts.dmp
  LOGFILE=app_tts_import.log
  TRANSPORT_DATAFILES='/u03/oradata/target/app_data01.dbf',
                     '/u03/oradata/target/app_index01.dbf'
~~~

Paths in TRANSPORT_DATAFILES must be accessible on the target. With ASM/OMF, use paths and syntax matching the target storage architecture.

### Step 7. Verify the target

~~~sql
SELECT tablespace_name,
       status,
       contents,
       block_size
FROM dba_tablespaces
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX');

SELECT owner,
       object_type,
       COUNT(*) AS object_count
FROM dba_objects
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX')
GROUP BY owner, object_type
ORDER BY owner, object_type;
~~~

DBA_OBJECTS does not expose TABLESPACE_NAME for every object type; use DBA_SEGMENTS to check segment placement:

~~~sql
SELECT owner,
       segment_type,
       COUNT(*) AS segment_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM dba_segments
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX')
GROUP BY owner, segment_type
ORDER BY owner, segment_type;
~~~

Check invalid objects, constraints, indexes, grants, and run application smoke tests before opening traffic.

### Step 8. Switch tablespaces to READ WRITE

On the target, after verifying import and file status:

~~~sql
ALTER TABLESPACE app_data READ WRITE;
ALTER TABLESPACE app_index READ WRITE;
~~~

On the source, once cutover is complete and keeping source READ ONLY is no longer required:

~~~sql
ALTER TABLESPACE app_data READ WRITE;
ALTER TABLESPACE app_index READ WRITE;
~~~

Never open writes concurrently on both source and target without a designed data-synchronization mechanism. After cutover, designate clearly which system is the primary writer.

## 6. Full Transportable Export/Import

### 6.1. What is full transportable?

Full transportable combines transportable tablespaces with Data Pump full export/import to move nearly an entire database:

- User data in transportable tablespaces is moved via datafiles.
- Database metadata is exported/imported via Data Pump.
- Data residing in non-transportable tablespaces is transferred via Data Pump instead of copying raw datafiles.
- SYSTEM and SYSAUX on the target database remain created and managed by the target database.

This reduces the number of rows passing through dump files compared to full conventional export/import, especially when most business data resides in large user tablespaces.

### 6.2. Supported sources and targets

Full transportable was introduced to support moving from Oracle Database 11g Release 2 (11.2.0.3 or later) to Oracle Database 12c Release 1 (12.1) or newer per the support matrix. The target must support the metadata and transportable format generated by the source.

Always verify:

- Source and target versions.
- Data Pump compatibility and the VERSION parameter.
- COMPATIBLE.
- Platform/endianness.
- Database character set.
- Time zone file.
- Block sizes and features in use.

Do not cite the 11.2.0.3-to-12.1 example as proof that every source/target version pair is compatible.

### 6.3. SYSTEM and SYSAUX in full transportable

SYSTEM and SYSAUX are not transferred by attaching source datafiles to the target. They belong to the target database's internal structure.

If user objects reside in SYSTEM or SYSAUX, Data Pump moves their metadata and data via appropriate export/import mechanisms. Consequently, full transportable still requires dump files with enough capacity and time for data residing in non-transportable tablespaces.

### 6.4. Preparing the source

Check tablespaces:

~~~sql
SELECT tablespace_name,
       contents,
       status,
       block_size
FROM dba_tablespaces
ORDER BY tablespace_name;
~~~

Identify user tablespaces to be transported. Set these tablespaces to READ ONLY per the cutover procedure and verify self-contained/full transport dependencies.

### 6.5. Full transportable export

Example:

~~~text
expdp system@source_db DIRECTORY=DPUMP_DIR
  FULL=Y
  TRANSPORTABLE=ALWAYS
  TRANSPORT_FULL_CHECK=Y
  DUMPFILE=full_tts_%U.dmp
  FILESIZE=20G
  LOGFILE=full_tts_export.log
~~~

FULL=Y requests full-database metadata export. TRANSPORTABLE=ALWAYS instructs Data Pump to use the transportable method for eligible tablespaces. TRANSPORT_FULL_CHECK=Y requests full dependency checks.

Data Pump exports data in non-transportable tablespaces into dump files. Datafiles for transportable user tablespaces still must be copied separately.

### 6.6. Copying datafiles

Copy all datafiles of the transported user tablespaces to the target. If endianness differs, use RMAN CONVERT. Keep source tablespaces READ ONLY until datafile snapshotting/copying/conversion completes.

### 6.7. Full transportable import

Example:

~~~text
impdp system@target_db DIRECTORY=DPUMP_DIR
  FULL=Y
  DUMPFILE=full_tts_%U.dmp
  TRANSPORT_DATAFILES='/u03/oradata/target/app_data01.dbf',
                     '/u03/oradata/target/app_index01.dbf'
  LOGFILE=full_tts_import.log
~~~

The TRANSPORT_DATAFILES list must match every transportable datafile recorded in the dump metadata. Data from non-transportable tablespaces is loaded from the dump files.

### 6.8. After import

Check:

- Database users, roles, profiles, and grants.
- Tablespace/datafile status.
- Object counts, segment sizes, and invalid objects.
- Public/private synonyms, database links, and directories.
- External tables, scheduler jobs, credentials, and network ACLs.
- TDE keystore and encrypted tablespaces.
- Database links, services, and application configuration.
- Character set/timezone and version-dependent features.

Full transportable does not automatically migrate external configurations outside the database, such as listeners, wallet files, OS credentials, external files, backup policies, service registrations, or middle-tier applications.

## 7. Comparing TTS, Full Transportable, and Conventional Data Pump

| Criterion | Transportable tablespaces | Full transportable | Conventional Data Pump |
| --- | --- | --- | --- |
| Scope | One or a group of tablespaces | Nearly the entire database | Schema/table/full export |
| User tablespace data | Copy datafiles | Copy datafiles | Read/write through dump files |
| Metadata | Data Pump | Full Data Pump | Data Pump |
| Data in SYSTEM/SYSAUX | Not part of normal transport set | Transferred via dump file when needed | Transferred via dump file |
| Self-contained check | Required for transport set | Full dependency check | Not required as transport set |
| Downtime | READ ONLY/cutover of selected tablespaces | READ ONLY/cutover for transportable user tablespaces and exporting remainder | Depends on export/import, consistency, and downtime plan |
| Cross-endian | RMAN conversion if endian differs | RMAN conversion for transportable datafiles if endian differs | Data Pump processes data logically |
| Use case | Moving large datasets by tablespace | Moving nearly an entire database | Moving schemas/tables, filtering, or restructuring data |

### 7.1. When to choose TTS?

Choose TTS when you only need a large group of tablespaces, dependencies are clear, and a compatible target database already exists.

### 7.2. When to choose full transportable?

Choose full transportable when migrating nearly an entire database, most data resides in transportable user tablespaces, and compatibility requirements are met.

### 7.3. When to choose conventional Data Pump?

Choose conventional Data Pump when you need to:

- Move specific schemas/tables.
- Filter rows or objects.
- Change structure/schemas/tables.
- Convert data logically.
- Source/target fail TTS prerequisites.

Conventional Data Pump may be slower for very large volumes, but it is far more flexible for logical transformations.

## 8. Cross-Platform Transport and RMAN CONVERT

### 8.1. Same endianness

If source and target share the same endian format, no endian conversion is needed. You still must verify platform compatibility, version, block size, character set, timezone, and TDE.

### 8.2. Different endianness

If endianness differs:

1. Switch tablespaces to READ ONLY.
2. Run RMAN CONVERT TABLESPACE or CONVERT DATAFILE to the target platform.
3. Verify output files and locations.
4. Copy converted files and the metadata dump.
5. Import on the target.
6. Verify datafiles/tablespaces.

Never copy big-endian datafiles to a little-endian host and attach them directly without conversion.

### 8.3. Checking target platform

~~~sql
SELECT platform_name,
       endian_format
FROM v$transportable_platform
WHERE platform_name IN (
    'Linux x86 64-bit',
    'Microsoft Windows x86 64-bit'
);
~~~

Exact names must be queried from the view on the database; do not hardcode platform strings from examples if releases differ.

### 8.4. Conversion on source or target?

RMAN can run conversion on either source or target. Choose based on:

- Host CPU and I/O capacity.
- Network bandwidth.
- Staging capacity.
- Whether the source can tolerate conversion workload.
- Security boundaries and datafile read permissions.

If converting on the target, transfer original files to staging first and ensure the target host can read them. If converting on the source, copy only the converted output files.

### 8.5. Do not use custom OS byte-swapping

Oracle datafiles have internal headers, block structures, and metadata. Never write custom scripts to swap byte order or patch headers using OS tools. Use RMAN CONVERT or an Oracle-supported method.

## 9. Reducing Downtime with Incremental Transportable Tablespaces

For very large tablespaces, keeping them READ ONLY while copying full datafiles can take too long. Oracle offers cross-platform incremental transportable tablespaces (XTTS) using RMAN incremental backups to apply changes while the source continues writing during eligible phases.

General flow:

1. Prepare source/target and the transport set.
2. Create baseline datafile backups.
3. Copy the baseline to the target.
4. Take incremental backups on the source.
5. Transfer incremental backups to the target and apply them to datafile copies.
6. Repeat until the delta is small.
7. Switch tablespaces to READ ONLY during the cutover window.
8. Apply the final incremental.
9. Export metadata, import/attach, and open tablespaces on the target.
10. Cut over the application to the target.

XTTS has its own procedures depending on version, platform, block size, and RMAN support. Never substitute it by manually copying active datafiles while writes occur. Follow Oracle XTTS documentation and supported scripts for your exact release.

## 10. Filenames, OMF, and ASM on the Target

Source datafile paths usually do not exist on the target. Determine how files will be named:

- TRANSPORT_DATAFILES specifies target files.
- OMF can auto-generate names via DB_CREATE_FILE_DEST.
- ASM requires appropriate disk group paths and access permissions.
- Data Pump parameters such as REMAP_DATAFILE can be used in supported scenarios.

Filesystem example:

~~~text
TRANSPORT_DATAFILES='/u03/oradata/target/app_data01.dbf'
~~~

ASM example:

~~~text
TRANSPORT_DATAFILES='+DATA/DBTARGET/DATAFILE/app_data.123.123456789'
~~~

The ASM path above is illustrative; actual filenames may be OMF-generated. Never alter filenames in metadata by renaming files outside the database without updating via Oracle procedures.

## 11. Users, Schemas, Grants, and Dependencies

### 11.1. TTS does not mean moving the entire application environment

Transportable tablespaces move objects and metadata associated with tablespaces. Database-level configurations or items outside tablespaces may need separate migration:

- Users, roles, and profiles.
- System privileges and role grants.
- Tablespace quotas.
- Public synonyms.
- Database links.
- Directory objects and OS directories.
- Scheduler jobs, credentials, and external jobs.
- Network ACLs.
- Contexts, services, and application configurations.
- TDE wallets/keystores.

Full transportable has broader metadata coverage due to FULL=Y, yet external elements and environment-dependent configurations still require verification.

### 11.2. Schema owners and quotas

Check users:

~~~sql
SELECT username,
       default_tablespace,
       temporary_tablespace,
       account_status
FROM dba_users
WHERE username IN ('APP_OWNER', 'APP_READ');
~~~

Check quotas:

~~~sql
SELECT username,
       tablespace_name,
       bytes,
       max_bytes
FROM dba_ts_quotas
WHERE username = 'APP_OWNER';
~~~

Ensure users have appropriate default tablespaces and quotas. Do not grant UNLIMITED TABLESPACE mechanically.

### 11.3. Object grants

Check grants:

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
FROM dba_tab_privs
WHERE owner = 'APP_OWNER'
ORDER BY table_name, grantee, privilege;
~~~

After import, confirm grantees exist, roles are granted, and effective privileges match. Do not assume all external grants automatically appear merely because datafiles were attached.

### 11.4. Dependencies outside tablespaces

Inspect views, procedures, packages, and synonyms referencing transported objects. An object in another schema or tablespace may depend on a moved table. After import, compile invalid objects and run application smoke tests.

## 12. CDB/PDB and Transportable Tablespaces

In multitenant architectures, distinguish among:

- Transport within the same CDB/PDB.
- Transport between two PDBs.
- Transport between a non-CDB and a PDB.
- Moving an entire PDB via unplug/plug.

If the goal is moving a whole PDB, unplug/plug or PDB cloning may suit better than transportable tablespaces. If moving only a group of tablespaces into a target PDB, check multitenant TTS rules and source/target PDB compatibility.

Check the current container:

~~~sql
SHOW CON_NAME;

SELECT con_id,
       name,
       open_mode
FROM v$pdbs
ORDER BY con_id;
~~~

Ensure expdp/impdp connects to the exact PDB service. Never run import into the CDB root if objects belong inside an application PDB.

## 13. Post-Import Verification and Cutover

### 13.1. Tablespaces/datafiles

~~~sql
SELECT tablespace_name,
       status,
       contents,
       block_size
FROM dba_tablespaces
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX');

SELECT file_name,
       tablespace_name,
       status,
       bytes
FROM dba_data_files
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX');
~~~

### 13.2. Segments and objects

~~~sql
SELECT owner,
       segment_type,
       COUNT(*) AS segment_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM dba_segments
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX')
GROUP BY owner, segment_type
ORDER BY owner, segment_type;
~~~

### 13.3. Invalid objects

~~~sql
SELECT owner,
       object_type,
       object_name,
       status
FROM dba_objects
WHERE status = 'INVALID'
  AND owner IN ('APP_OWNER', 'APP_API')
ORDER BY owner, object_type, object_name;
~~~

### 13.4. Constraints and indexes

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated
FROM dba_constraints
WHERE owner = 'APP_OWNER'
ORDER BY table_name, constraint_name;

SELECT owner,
       index_name,
       table_name,
       status
FROM dba_indexes
WHERE owner = 'APP_OWNER'
ORDER BY table_name, index_name;
~~~

### 13.5. Row counts and application checks

Do not compare file sizes alone. Pick critical business tables and verify row counts, financial totals, min/max business keys, partition counts, and business invariants.

If possible, generate reconciliation reports on source and target before cutover. Note that the source may change after the snapshot point; compare at the same SCN/snapshot or keep the source READ ONLY during reconciliation.

### 13.6. Application smoke tests

Verify:

- Connecting via the target service.
- SELECT/INSERT/UPDATE inside a test transaction.
- Critical packages/procedures.
- Database links and external integrations.
- Jobs, schedulers, and queues.
- Application account privileges.
- Query latency and critical execution plans.
- Target backup/recovery policy.

## 14. Common Errors

| Symptom/error | Possible cause | Resolution |
| --- | --- | --- |
| Transport set violations | Dependency lies outside selected tablespaces | Expand transport set or resolve dependencies |
| ORA-399xx during TTS check | Transport set not self-contained or violates conditions | Inspect TRANSPORT_SET_VIOLATIONS and fix each dependency |
| ORA-29345 / endian mismatch | Datafile endianness differs from target | RMAN CONVERT to target platform |
| Data Pump reports version incompatibility | Dump metadata incompatible with target | Check source/target releases, VERSION, and Data Pump compatibility |
| ORA-01122 / ORA-01110 attaching datafile | Datafile header/metadata mismatch or invalid file | Verify exact file, conversion, DBID/incarnation, and datafile state |
| ORA-01119 / ORA-270xx | Target cannot create/read file due to path, permissions, or storage | Check filesystem/ASM, permissions, and capacity |
| ORA-01536 quota exceeded | Schema owner lacks sufficient quota on target | Adjust quotas per policy |
| ORA-01031 insufficient privileges | User running Data Pump/DDL lacks privileges | Grant proper privileges or run with an authorized admin account |
| Invalid objects after import | Differences in dependencies, users/grants, or version | Check dependencies, recompile, and verify grants |
| Encrypted tablespace cannot open | Target lacks TDE key or keystore is closed | Prepare and import keys per TDE procedure |
| TSTZ data issues | Incompatible time zone file version | Check V$TIMEZONE_FILE and DBMS_DST |
| Missing datafile | Not all datafiles of the transport set were copied | Reconcile DBA_DATA_FILES and TRANSPORT_DATAFILES |
| Target attaches file yet objects are missing | Missing metadata dump or imported into wrong PDB/schema | Check expdp/impdp logs, service, and dump files |
| Long downtime | Full datafile copy occurring inside the READ ONLY window | Evaluate XTTS/incremental transportable or boost throughput |

Exact error codes depend on release and operation. Always read the Data Pump log, alert log, and complete error stack.

## 15. Choosing a Migration Method

~~~text
Moving only a few large tablespaces?
        |
        +-- YES --> Check self-containment and compatibility
        |               |
        |               +-- Pass --> Transportable Tablespaces
        |               |
        |               +-- Fail --> Conventional Data Pump
        |
        +-- NO --> Moving nearly the entire database?
                        |
                        +-- YES --> Full transportable compatible?
                        |               |
                        |               +-- Pass --> Full transportable
                        |               |
                        |               +-- Fail --> Full Data Pump / other upgrade path
                        |
                        +-- NO --> Moving schemas/tables, filtering data?
                                        |
                                        +--> Conventional Data Pump
~~~

If moving an entire PDB, evaluate unplug/plug or PDB cloning before choosing TTS. If datafile copy downtime is too long, evaluate incremental XTTS.

## 16. Pre-Cutover Checklist

1. **Is the scope right?** TTS for a group of tablespaces; full transportable for nearly the whole database.
2. **Is the transport set self-contained?** DBMS_TTS.TRANSPORT_SET_CHECK shows zero violations.
3. **Are all partition/index tablespaces included?** Do not leave critical dependencies outside the set.
4. **Are source and target versions compatible?** Verify releases, Data Pump version, and COMPATIBLE.
5. **Are platform/endianness confirmed?** Use V$TRANSPORTABLE_PLATFORM.
6. **Converted if endianness differs?** RMAN CONVERT, never custom OS byte-swapping.
7. **Is block size supported?** Target has caches for nonstandard block sizes.
8. **Are character sets compatible?** Never assume copied datafiles are converted by Data Pump.
9. **Do timezone file versions match?** Especially for TIMESTAMP WITH TIME ZONE.
10. **Are TDE keys ready?** Target can open the keystore and holds required keys.
11. **Are all datafiles complete?** Copy every datafile of every selected tablespace.
12. **Were tablespaces set READ ONLY at the right time?** Snapshot did not change during copying.
13. **Are dump files and directories ready?** Valid privileges, capacity, and paths.
14. **Are users, roles, quotas, and grants handled?** Especially for traditional TTS.
15. **Importing into the right database/PDB?** Use the exact service.
16. **Are target datafile names right?** Verify filesystem/ASM/OMF.
17. **Verified objects/dependencies on target?** Invalids, constraints, indexes, synonyms, jobs.
18. **Reconciled data?** Row counts and business invariants.
19. **Is a rollback plan ready?** Keep source and backups until the target is accepted.
20. **Is a post-cutover target backup configured?** Establish the new backup policy.

## 17. Self-Check Questions

**Question 1.** How do transportable tablespaces differ from conventional Data Pump in how row data is moved?

**Question 2.** What does a self-contained transport set mean?

**Question 3.** What is DBMS_TTS.TRANSPORT_SET_CHECK used for?

**Question 4.** Why must tablespaces be set to READ ONLY before copying datafiles?

**Question 5.** What does a transportable tablespace dump file typically contain?

**Question 6.** Why must every datafile of a tablespace be copied?

**Question 7.** What information does V$TRANSPORTABLE_PLATFORM provide?

**Question 8.** When is RMAN CONVERT required?

**Question 9.** Why must you never byte-swap datafiles with custom scripts?

**Question 10.** Do DB_RECOVERY_FILE_DEST or ASM paths replace TRANSPORT_DATAFILES?

**Question 11.** How does full transportable differ from standard TTS?

**Question 12.** Why are SYSTEM and SYSAUX not copied as raw datafiles to the target in full transportable?

**Question 13.** Why can full transportable still require a potentially large dump file?

**Question 14.** Why must database version and COMPATIBLE be verified?

**Question 15.** Why can character sets not be assumed to convert automatically when copying datafiles?

**Question 16.** How does a TDE keystore affect encrypted transportable tablespaces?

**Question 17.** Why must users, roles, quotas, and grants be verified after TTS?

**Question 18.** When does XTTS help reduce downtime?

**Question 19.** When the goal is moving an entire PDB, which methods should be evaluated?

**Question 20.** Why reconcile business invariants instead of comparing datafile sizes alone?

<details>
<summary>Answer hints</summary>

1. TTS copies datafiles and imports metadata; conventional Data Pump reads/writes data through dump files.
2. Required dependencies stay inside the transport set per Oracle rules.
3. Checks dependencies and self-containment of a set of tablespaces.
4. So datafiles do not change while exporting metadata and copying files.
5. Primarily object/tablespace metadata, not all row data inside the datafiles.
6. A tablespace can span multiple datafiles; missing one file leaves the set incomplete.
7. Platform ID/name and endian format.
8. When source and target have different endian formats.
9. Datafiles contain internal blocks/headers/metadata; conversion must use RMAN or an Oracle-supported method.
10. No. TRANSPORT_DATAFILES specifies target datafile paths; storage destinations must be configured separately.
11. Full transportable moves nearly the whole database, using datafiles for user tablespaces and Data Pump for non-transportable tablespace data/metadata.
12. SYSTEM/SYSAUX belong to the target database's internal structure and are managed by the target.
13. Data residing inside non-transportable tablespaces is still exported into the dump file.
14. Metadata and features must be supported by the target; COMPATIBLE governs database format/features.
15. Row data sits in datafiles already encoded in the database character set; it does not pass through logical conversion like conventional Data Pump.
16. The target must possess the matching keys/keystore to read encrypted datafiles.
17. Traditional TTS does not automatically migrate all database/user/security settings and application environment configuration.
18. When tablespaces are large and copying full datafiles inside a READ ONLY window takes too long.
19. Unplug/plug or PDB clone.
20. File sizes do not prove business data is complete and consistent.

</details>

## 18. Official Oracle Documentation

1. [Oracle Database 19c Administrator's Guide — Transporting Tablespaces Between Databases](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/transporting-tablespaces-between-databases.html): TTS workflow, self-contained sets, and transportable restrictions.
2. [Oracle Database 19c Database Utilities — Transportable Tablespaces](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html): Data Pump transportable export.
3. [Oracle Database 19c Database Utilities — Oracle Data Pump Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-import-utility.html): TRANSPORT_DATAFILES and metadata import.
4. [Oracle Database 19c Backup and Recovery Reference — CONVERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/CONVERT.html): RMAN cross-platform conversion.
5. [Oracle Database 19c Reference — V$TRANSPORTABLE_PLATFORM](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSPORTABLE_PLATFORM.html): platforms and endian formats.
6. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_TTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_TTS.html): transport set checks.
7. [Oracle Database 19c Database Utilities — Full Transportable Export/Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-overview.html): full transportable and Data Pump.
8. [Oracle Database 19c Security Guide — Transparent Data Encryption](https://docs.oracle.com/en/database/oracle/oracle-database/19/asoag/): TDE keystores and encrypted tablespaces.
9. [Oracle Database 19c Upgrade Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/upgrd/): version compatibility and database upgrade paths.

**Key principle to remember:** TTS transports metadata with Data Pump and data with datafiles; full transportable combines this approach with full Data Pump for non-transportable parts. Before moving, verify transport set self-containment, READ ONLY consistency, version, platform/endianness, block size, character set, timezone, and TDE. Cross-endian moves must use RMAN conversion. After import, verify objects, dependencies, privileges, business data, and target backups before cutover.
