# REMAP_SCHEMA, REMAP_TABLESPACE, and Handling Existing Objects

Oracle Data Pump Import (impdp) can bring schemas, tables, and metadata from a source database to a target database. When switching environments, renaming schemas, or reorganizing tablespaces, dump files typically retain the original schema and tablespace names. Data Pump provides remap parameters to change ownership and segment storage locations during import.

Three key parameters to understand clearly are:

- **REMAP_SCHEMA**: transfers objects belonging to a source schema to a target schema during import.
- **REMAP_TABLESPACE**: moves object segments from a source tablespace to a target tablespace.
- **TABLE_EXISTS_ACTION**: determines how data is loaded when a target table already exists.

These parameters solve different problems. REMAP_SCHEMA does not automatically rewrite every schema-name string inside PL/SQL source code; REMAP_TABLESPACE does not automatically allocate storage or alter all user default configurations; TABLE_EXISTS_ACTION only controls handling of existing tables when loading data. To import safely, prepare users, tablespaces, privileges, table structures, and existing data before running.

## 1. Data Pump Import and the Remapping Context

Data Pump is Oracle Database's toolset for exporting and importing data and metadata. Export is performed with expdp; import with impdp. A dump file can contain metadata, data, or both depending on how it was exported.

A typical schema migration workflow looks like:

1. Export the schema from the source database into a dump file.
2. Transfer the dump file to a location accessible by an Oracle DIRECTORY on the target database.
3. Prepare the target schema, tablespaces, quotas, and privileges.
4. Run impdp with remap parameters.
5. Inspect logs, objects, data, grants, synonyms, jobs, and dependencies.
6. Test the application before switching traffic.

Example: the source database has schema SALES residing in tablespaces SALES_DATA and SALES_INDEX. The test environment needs schema SALES_TEST, with data in APP_DATA and indexes in APP_INDEX.

    Source database                        Target database
    +-------------------+                  +-------------------+
    | Schema SALES      |                  | Schema SALES_TEST |
    |                   |                  |                   |
    | SALES_DATA        |   Data Pump      | APP_DATA          |
    | SALES_INDEX       |  ------------>   | APP_INDEX         |
    |                   |                  |                   |
    +-------------------+                  +-------------------+
            |                                      ^
            | expdp                                | impdp
            v                                      |
       dump file  ---------------------------------+

In this example:

- REMAP_SCHEMA=SALES:SALES_TEST changes the owner of imported objects.
- REMAP_TABLESPACE=SALES_DATA:APP_DATA moves segments belonging to tablespace SALES_DATA to APP_DATA.
- REMAP_TABLESPACE=SALES_INDEX:APP_INDEX moves segments belonging to SALES_INDEX to APP_INDEX.
- TABLE_EXISTS_ACTION determines how each table is handled if the corresponding table already exists on the target.

Remapping takes place during import. The source dump file is not modified.

## 2. REMAP_SCHEMA: Changing Object Ownership

Syntax:

    REMAP_SCHEMA=source_schema:target_schema

Example:

    REMAP_SCHEMA=SALES:SALES_TEST

During import, Data Pump transfers objects belonging to schema SALES in the dump to owner SALES_TEST. You can use this parameter to:

- Create a schema copy for testing.
- Rename a schema when moving an application to a new database.
- Import data from multiple source schemas into planned target schemas.
- Keep source and target databases using different owner names.

### 2.1. Importing a schema into a differently named schema

Example export:

    expdp system@SOURCE
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_export.log
      SCHEMAS=SALES
      PARALLEL=4
      FILESIZE=10G

The command above is formatted across multiple lines for readability. When running in a shell, place the parameters on a single line or use a parameter file.

Import:

    impdp system@TARGET
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_to_test.log
      SCHEMAS=SALES
      REMAP_SCHEMA=SALES:SALES_TEST

As a result, the selected objects from SALES are created under owner SALES_TEST, within the metadata scope in the dump and the import filters.

If multiple schemas need renaming, you can specify multiple REMAP_SCHEMA pairs in the same job. Specify source and target clearly for each pair; do not use an ambiguous mapping for schemas sharing names across different databases.

### 2.2. Preparing the target schema

Operationally, the easiest way to maintain control is to pre-create the target user with appropriate default tablespace, temporary tablespace, and quotas:

    CREATE USER sales_test
      IDENTIFIED BY "replace-with-managed-secret"
      DEFAULT TABLESPACE app_data
      TEMPORARY TABLESPACE temp
      QUOTA 5G ON app_data
      QUOTA 2G ON app_index;

    GRANT CREATE SESSION TO sales_test;

This is an illustrative example. The import user needs additional privileges matching the objects to be created and how Data Pump is run. Do not grant broader privileges than actually required. If the dump contains user-creation metadata and the job runs with sufficient privileges, Data Pump can process user metadata from the dump; however, pre-creating the target schema lets the DBA control passwords, quotas, profiles, tablespaces, and security policies.

Items to verify:

- Whether the target user already exists.
- Whether the default tablespace and temporary tablespace are correct.
- Whether quotas are sufficient for tables, indexes, LOBs, and partitions.
- Whether the user has object creation privileges or the import account has appropriate privileges.
- Whether profile, password policy, roles, and system privileges are appropriate.
- Whether the target schema already holds objects from a prior import or data from another application.

REMAP_SCHEMA changes the owner of imported objects. It does not replace proper account and login privilege design for the application.

### 2.3. Schema references inside objects

Do not treat REMAP_SCHEMA as a global find-and-replace for every schema-name string in the dump.

For example, a procedure in SALES might contain an explicit reference:

    SELECT *
    FROM COMMON_CONFIG.CURRENCY_RATE;

When the object is moved to SALES_TEST, the reference to COMMON_CONFIG may still point to schema COMMON_CONFIG. This may be desirable if the shared schema exists, or it could cause a test application to access the wrong database objects or production data.

Locations to audit after remapping:

- PL/SQL procedures, functions, packages, and triggers with hardcoded schema qualifiers.
- Views and materialized views referencing objects in other schemas.
- Synonyms pointing to old owners or database links.
- Database links, jobs, scheduler programs, and credentials.
- Dynamic SQL concatenating schema names from strings.
- Grants, roles, ACLs, and cross-schema dependencies.
- Application configurations, connection strings, and migration scripts containing old owner names.

You can search for schema references in source code after import by querying the data dictionary, for example:

    SELECT owner, name, type, line, text
    FROM dba_source
    WHERE owner = 'SALES_TEST'
      AND UPPER(text) LIKE '%SALES.%'
    ORDER BY name, type, line;

The string query above is only an initial scan. It can miss dynamic SQL built across multiple lines or yield false positives on column names and string literals. Inspect the actual source code and recompile objects.

### 2.4. Multiple schemas and dependencies

If schema SALES references MASTER_DATA, importing SALES alone may create its objects, yet external dependencies still must exist in the target database.

    SALES_TEST.ORDERS
           |
           +----> MASTER_DATA.CUSTOMERS
           |
           +----> MASTER_DATA.PRODUCTS
           |
           +----> COMMON_CONFIG.CURRENCY_RATE

Before remapping, identify which schemas hold application-specific data and which hold shared data. You can import dependent schemas first, or keep the owner of shared schemas unchanged. Avoid mechanically remapping everything so objects do not end up pointing to the wrong copy.

## 3. REMAP_TABLESPACE: Moving Segment Storage Locations

Syntax:

    REMAP_TABLESPACE=source_tablespace:target_tablespace

Example:

    REMAP_TABLESPACE=SALES_DATA:APP_DATA
    REMAP_TABLESPACE=SALES_INDEX:APP_INDEX

This parameter instructs Data Pump to place segments imported from the source tablespace into the corresponding target tablespace.

It is useful when:

- Moving a database to a new storage layout.
- Separating tables and indexes into dedicated tablespaces.
- Moving production data into smaller tablespaces for a test environment.
- Standardizing tablespace names across environments.
- Moving a schema off an old tablespace scheduled for retirement.

### 3.1. Single mapping and multiple mappings

Single mapping:

    REMAP_TABLESPACE=SALES_DATA:APP_DATA

Multiple mappings:

    REMAP_TABLESPACE=SALES_DATA:APP_DATA
    REMAP_TABLESPACE=SALES_INDEX:APP_INDEX
    REMAP_TABLESPACE=SALES_LOB:APP_LOB

In a parameter file, you can repeat parameters according to Data Pump syntax. Check parameter-passing rules for your version and shell; parameter files are generally easier to read and less prone to quoting errors than long command lines.

### 3.2. Creating target tablespaces before import

REMAP_TABLESPACE is not a storage allocation command. Target tablespaces must exist with appropriate datafiles or tempfiles before import creates segments.

Example:

    CREATE TABLESPACE app_data
      DATAFILE '/u02/oradata/target/app_data01.dbf'
      SIZE 2G
      AUTOEXTEND ON NEXT 256M MAXSIZE 20G;

    CREATE TABLESPACE app_index
      DATAFILE '/u03/oradata/target/app_index01.dbf'
      SIZE 1G
      AUTOEXTEND ON NEXT 128M MAXSIZE 10G;

Paths and sizes are illustrative only. With ASM, Oracle Managed Files, or cloud storage, file creation syntax can differ. The DBA must verify storage pools, quotas, encryption, block size, autoextend, and operational limits.

### 3.3. Target tablespaces and user quotas

Having a tablespace is not enough for a user to create segments. Grant quotas to the target schema or apply an appropriate privilege policy:

    ALTER USER sales_test QUOTA 5G ON app_data;
    ALTER USER sales_test QUOTA 2G ON app_index;

If quotas are insufficient, import can fail when creating tables, indexes, or LOB segments. When calculating quotas, do not sum only table data size. Indexes, LOBs, partitions, nested tables, and auxiliary segments also consume space.

You can check quotas:

    SELECT
        username,
        tablespace_name,
        bytes,
        max_bytes
    FROM dba_ts_quotas
    WHERE username = 'SALES_TEST'
    ORDER BY tablespace_name;

### 3.4. Tablespace mapping does not change a user's default tablespace

REMAP_TABLESPACE affects where segments imported from source tablespaces are placed. It should not be relied on as the sole way to configure the target user's default tablespace.

Set the default tablespace explicitly:

    ALTER USER sales_test DEFAULT TABLESPACE app_data;

After import, check whether any objects landed in unexpected tablespaces. Some objects may be created using the default tablespace or affected by metadata and applied transforms. Do not assume one mapping covers every object and every user configuration.

### 3.5. Tables, indexes, LOBs, and partitions

A table can have multiple segments: table segments, index segments, LOB segments, and partitions/subpartitions. Some segments can reside in different tablespaces from the main table.

Example:

    SALES.ORDERS
      +-- Table partitions       -> SALES_DATA
      +-- Primary key index     -> SALES_INDEX
      +-- ORDER_DOCUMENT LOB    -> SALES_LOB

If you only remap SALES_DATA to APP_DATA, indexes or LOBs may still be created according to other mappings or metadata. List all tablespaces actually containing source objects and define corresponding mappings.

You can inspect source schema segments:

    SELECT
        segment_type,
        tablespace_name,
        COUNT(*) AS segment_count,
        ROUND(SUM(bytes) / 1024 / 1024) AS size_mb
    FROM dba_segments
    WHERE owner = 'SALES'
    GROUP BY segment_type, tablespace_name
    ORDER BY tablespace_name, segment_type;

After import, run the same query for owner SALES_TEST to compare. For partitioned tables, also inspect DBA_TAB_PARTITIONS and DBA_IND_PARTITIONS to confirm individual partition placement.

### 3.6. What REMAP_TABLESPACE does not solve

REMAP_TABLESPACE primarily controls storage metadata of imported objects. It does not:

- Create or extend physical storage.
- Grant user quotas.
- Automatically rewrite PL/SQL statements containing hardcoded tablespace names.
- Move datafiles already existing on the target database.
- Guarantee every object across every import mode supports remapping identically.
- Replace dedicated procedures for transportable tablespaces or specialized movement methods.

Transportable tablespaces, network imports, and special modes have their own parameter limitations. When using these modes, consult the documentation for your exact Oracle version before designing mappings.

## 4. Combining REMAP_SCHEMA and REMAP_TABLESPACE

Many projects require changing both owner and tablespaces. Example:

- Source schema: SALES.
- Target schema: SALES_TEST.
- Source table tablespace: SALES_DATA.
- Target table tablespace: APP_DATA.
- Source index tablespace: SALES_INDEX.
- Target index tablespace: APP_INDEX.

The parameter file can be written as:

    DIRECTORY=DP_DIR
    DUMPFILE=sales_%U.dmp
    LOGFILE=sales_test_import.log
    SCHEMAS=SALES
    REMAP_SCHEMA=SALES:SALES_TEST
    REMAP_TABLESPACE=SALES_DATA:APP_DATA
    REMAP_TABLESPACE=SALES_INDEX:APP_INDEX
    LOGTIME=ALL
    METRICS=YES

Run import:

    impdp system@TARGET PARFILE=sales_test_import.par

A parameter file saves the import configuration so it can be reviewed, version-controlled, and reused. Do not store production passwords in parameter files committed to a repository.

Before running, confirm:

- The dump file belongs to the right source database and schema.
- The DIRECTORY object points to the right folder on the database server.
- The import user has privileges to read dumps and write logs.
- User SALES_TEST is prepared with quotas and tablespaces.
- APP_DATA and APP_INDEX exist and have enough free space.
- Dependent schemas are prepared.
- No critical data in the target schema will be unexpectedly overwritten.

## 5. TABLE_EXISTS_ACTION: When the Target Table Already Exists

During import, table metadata or table data may target a table that already exists in the target database. The TABLE_EXISTS_ACTION parameter determines how that table is handled.

Options:

| Value | Behavior | When to consider using |
|---|---|---|
| SKIP | Skips the existing table and does not load its data | Preserve existing table and data untouched |
| APPEND | Inserts rows from the dump into the existing table | Add data into a compatible table |
| TRUNCATE | Deletes existing data via truncate and loads data from the dump | Replace all table data while keeping existing structure |
| REPLACE | Drops the existing table, recreates it from dump metadata, and loads data | Replace both table structure and contents with the dump version |

Example:

    TABLE_EXISTS_ACTION=APPEND

This parameter matters most when importing data into existing tables. Specify it explicitly rather than relying on job defaults, especially for data-only imports or retries after failure.

### 5.1. SKIP

SKIP keeps the target table intact and skips loading that table. Existing data is neither deleted nor appended.

Example: the target database already has a separately managed table SALES_TEST.COUNTRIES, and you do not want the source dump to alter its data. SKIP can be appropriate if the goal is preserving the table.

Note: SKIP does not mean every dependent object is skipped. The import job can still process other objects per metadata and filters. Read the log to see exactly which objects were created, skipped, or errored.

### 5.2. APPEND

APPEND keeps existing data and adds rows from the dump to the target table. The target table must have a structure compatible with the imported data.

Example:

    CONTENT=DATA_ONLY
    SCHEMAS=SALES
    REMAP_SCHEMA=SALES:SALES_TEST
    TABLE_EXISTS_ACTION=APPEND

APPEND can create business duplicates if the dump contains rows that already exist. Unique constraints may cause rows to fail; without appropriate constraints, duplicate data may be inserted. Do not rerun APPEND repeatedly without a duplicate-control strategy.

### 5.3. TRUNCATE

TRUNCATE deletes data in the existing table before loading data from the dump. It preserves the target table definition, so it does not automatically replace the structure with the dump's definition.

Example:

    CONTENT=DATA_ONLY
    TABLE_EXISTS_ACTION=TRUNCATE

TRUNCATE is suitable when the target table already has the right prepared structure and you want to replace all its data with the dump snapshot. Check foreign keys, constraints, triggers, and inter-table relationships; certain referential conditions can prevent truncate.

When importing multiple parent/child tables, plan load order and constraint handling appropriately. Do not assume Data Pump will automatically handle every business constraint as desired.

### 5.4. REPLACE

REPLACE drops the existing target table, recreates it from the dump metadata, and then loads data. This is the highest-impact option of the four.

Example:

    CONTENT=ALL
    TABLE_EXISTS_ACTION=REPLACE

Use REPLACE only after confirming the old table can be discarded. Dropping and recreating can affect indexes, constraints, triggers, grants, and dependent objects. Which objects Data Pump reprocesses depends on metadata scope, filters, and import mode.

Do not use REPLACE as a blanket fix for object-already-exists errors. TABLE_EXISTS_ACTION only controls behavior for existing tables; it is not a command to replace an entire schema or all object types.

### 5.5. Comparison by goal

| Goal | Usually appropriate approach |
|---|---|
| Keep the target table untouched | SKIP |
| Add new rows into the table | APPEND |
| Replace data while keeping target table structure | TRUNCATE |
| Replace both table definition and data from the dump | REPLACE |
| Create metadata only without loading data | CONTENT=METADATA_ONLY |
| Load data only into a prepared structure | CONTENT=DATA_ONLY |

The final choice must be based on data synchronization requirements and structural compatibility. No single TABLE_EXISTS_ACTION value fits every import.

## 6. TABLE_EXISTS_ACTION Does Not Handle All Existing Objects

A schema contains more than tables. It also has indexes, sequences, views, synonyms, procedures, packages, triggers, types, constraints, materialized views, and more.

If import encounters an existing object, Data Pump may report notices or errors such as object already exists, depending on object type and import behavior. TABLE_EXISTS_ACTION does not apply universally to all objects.

Examples:

- A sequence with the same name already exists.
- A package was previously created by a newer release.
- A synonym points to an old owner.
- A type is referenced by multiple tables.
- A view has a dependency that does not exist yet.
- An index already exists with a different definition.
- A grant or role was configured specifically on the target.

Classify object conflicts before deciding how to handle them.

### 6.1. Listing existing objects

You can check objects in the target schema:

    SELECT
        object_type,
        status,
        COUNT(*) AS object_count
    FROM dba_objects
    WHERE owner = 'SALES_TEST'
    GROUP BY object_type, status
    ORDER BY object_type, status;

Search for specific object names:

    SELECT owner, object_name, object_type, status
    FROM dba_objects
    WHERE owner = 'SALES_TEST'
      AND object_name IN (
          'ORDERS',
          'ORDER_SEQ',
          'PKG_ORDER'
      )
    ORDER BY object_type, object_name;

Compare against dump metadata by generating an SQL preview or reading logs from a test export/import. Do not drop an object merely because its name collides; that object may belong to an active release or running application.

### 6.2. Using SQLFILE to inspect DDL before import

The SQLFILE parameter instructs Data Pump to write the DDL that would be executed into an SQL file instead of executing that DDL. It is useful for reviewing metadata, owners, tablespaces, storage clauses, and objects to be created.

Example:

    impdp system@TARGET
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_preview.log
      SCHEMAS=SALES
      REMAP_SCHEMA=SALES:SALES_TEST
      REMAP_TABLESPACE=SALES_DATA:APP_DATA
      SQLFILE=sales_preview.sql

SQLFILE is written in the physical folder pointed to by the DIRECTORY object on the database server. This file is a DDL preview, not proof that the actual import will succeed. Table data is not loaded by a preview operation.

Review the preview file to detect:

- Owners still retaining the source schema name.
- Tablespaces not yet remapped.
- DDL that may conflict with target objects.
- Objects depending on other schemas.
- Unsuitable storage clauses, partitions, and LOB clauses.
- Objects you do not want created in the target environment.

### 6.3. Using INCLUDE and EXCLUDE deliberately

Data Pump supports INCLUDE and EXCLUDE to restrict object types or specific objects imported. They help split metadata into phases or avoid importing certain separately managed objects.

Example excluding optimizer statistics from import:

    EXCLUDE=STATISTICS

Or importing only specific required object types using INCLUDE. Object type names, object paths, and filter rules depend on import mode; consult Data Pump documentation for your exact version.

Do not use EXCLUDE arbitrarily. Skipping constraints, triggers, grants, or types can leave data loaded while the application behaves incorrectly. Document why objects are excluded and plan to recreate them if needed.

## 7. Splitting Import into Phases

For large schemas or target schemas where part of the structure is already deployed, split the import into controllable phases.

### 7.1. Metadata-only

Create objects and metadata first without loading data:

    SCHEMAS=SALES
    REMAP_SCHEMA=SALES:SALES_TEST
    REMAP_TABLESPACE=SALES_DATA:APP_DATA
    REMAP_TABLESPACE=SALES_INDEX:APP_INDEX
    CONTENT=METADATA_ONLY

Before running, review SQLFILE and prepare object dependencies. Some objects may need to be created in order or adjusted separately.

### 7.2. Data-only

Once the structure exists and has been verified, load the data:

    SCHEMAS=SALES
    REMAP_SCHEMA=SALES:SALES_TEST
    CONTENT=DATA_ONLY
    TABLE_EXISTS_ACTION=APPEND

APPEND is only an example. If you want to replace data in existing tables, consider TRUNCATE after checking constraints; if preserving existing tables, use SKIP; if structure must change, return to a controlled metadata import plan.

Separating metadata and data enables clearer review, but adds synchronization responsibility: the structure must remain compatible with the dump and must not change between phases in a way that breaks column mappings.

### 7.3. Checking logs after each phase

Data Pump generates logs recording processed objects, rows loaded, and errors. Check:

- Whether the job completed or stopped in an error state.
- Which objects were created, skipped, or failed.
- Row counts loaded for each table.
- Quota, tablespace, privilege, constraint, or dependency errors.
- Warnings caused by existing objects.
- INVALID objects after import.

Do not conclude an import succeeded simply because the impdp process exited. Verify exit status, logs, and data.

## 8. Handling Common Errors

### 8.1. Target tablespace does not exist

Cause: a mapping points to a tablespace that has not been created yet or is misspelled.

Resolution:

1. Verify the mapping in the parameter file.
2. Check DBA_TABLESPACES on the target database.
3. Create the tablespace with appropriate storage.
4. Check quotas and physical space.
5. Re-run import after determining where the previous job stopped.

Do not arbitrarily create tablespaces on filesystems lacking capacity.

### 8.2. Target user lacks quota

Import may create some objects and then fail when allocating the next segment.

Check:

    SELECT username, tablespace_name, bytes, max_bytes
    FROM dba_ts_quotas
    WHERE username = 'SALES_TEST';

Adjust quotas after estimating table, index, LOB, and partition sizes. Do not grant UNLIMITED TABLESPACE to applications just to bypass errors without evaluating capacity.

### 8.3. Object already exists

If the log reports an object already exists, identify the object type first. If it is a table, TABLE_EXISTS_ACTION can control data loading. If it is a sequence, package, type, view, or another object, handle it via metadata import/filters or planned target schema cleanup.

Do not rerun import with REPLACE just to clear object-already-exists errors; doing so can destroy data or metadata actively used by the application.

### 8.4. APPEND creates duplicate data or unique constraint errors

APPEND does not deduplicate automatically. If the dump contains rows that already exist, the outcome depends on constraints and table structure. Duplicate key errors may occur, or duplicate rows may be inserted if appropriate constraints are absent.

Before rerunning the job:

- Determine how many rows the previous import loaded.
- Compare business keys and primary keys.
- Decide whether to append only missing rows, truncate and reload, or build a clean schema.
- Verify transactions and job state to prevent duplicate data.

### 8.5. TRUNCATE cannot execute

Referential constraints and table conditions can block truncate. Check foreign keys, constraints, and table relationships. If needed, design load ordering and constraint handling via a tested procedure.

Do not disable all constraints in production just to push an import through. Re-enabling constraints requires ensuring the data satisfies those conditions.

### 8.6. Objects import as INVALID

A package, procedure, view, or trigger can be created yet fail to compile due to missing dependencies, renamed owners, or insufficient privileges.

Check:

    SELECT owner, object_name, object_type, status
    FROM dba_objects
    WHERE owner = 'SALES_TEST'
      AND status = 'INVALID'
    ORDER BY object_type, object_name;

Inspect compilation errors:

    SELECT owner, name, type, line, position, text
    FROM dba_errors
    WHERE owner = 'SALES_TEST'
    ORDER BY name, sequence;

Resolve dependencies, grants, and schema references; then recompile objects. Do not ignore INVALID errors if the application relies on those objects.

## 9. Sample Workflow: Moving a Schema to a Test Environment

Suppose you need to move SALES from source to SALES_TEST in a target database while changing tablespaces.

### Step 1: Survey the source

Check objects, segments, and dependencies:

    SELECT object_type, COUNT(*)
    FROM dba_objects
    WHERE owner = 'SALES'
    GROUP BY object_type
    ORDER BY object_type;

    SELECT tablespace_name,
           ROUND(SUM(bytes) / 1024 / 1024) AS size_mb
    FROM dba_segments
    WHERE owner = 'SALES'
    GROUP BY tablespace_name
    ORDER BY tablespace_name;

Record row counts of key tables, sequences, grants, synonyms, jobs, and cross-schema dependencies.

### Step 2: Export

    expdp system@SOURCE
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_export.log
      SCHEMAS=SALES
      PARALLEL=4

Confirm the dump completes and files are readable in the target environment.

### Step 3: Prepare the target

Create APP_DATA, APP_INDEX, user SALES_TEST, default tablespace, temporary tablespace, and quotas. Check whether the target schema contains old objects.

### Step 4: Preview DDL

    impdp system@TARGET
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_preview.log
      SCHEMAS=SALES
      REMAP_SCHEMA=SALES:SALES_TEST
      REMAP_TABLESPACE=SALES_DATA:APP_DATA
      REMAP_TABLESPACE=SALES_INDEX:APP_INDEX
      SQLFILE=sales_preview.sql

Review the generated SQL file on the database server and check mappings/dependencies.

### Step 5: Import

    impdp system@TARGET
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_import.log
      SCHEMAS=SALES
      REMAP_SCHEMA=SALES:SALES_TEST
      REMAP_TABLESPACE=SALES_DATA:APP_DATA
      REMAP_TABLESPACE=SALES_INDEX:APP_INDEX
      LOGTIME=ALL
      METRICS=YES

If the target schema already has tables, add TABLE_EXISTS_ACTION per the agreed objective. For an initial import into a clean schema, do not set REPLACE to force overwrites.

### Step 6: Post-import reconciliation

Check object counts and statuses:

    SELECT object_type, status, COUNT(*)
    FROM dba_objects
    WHERE owner = 'SALES_TEST'
    GROUP BY object_type, status
    ORDER BY object_type, status;

Check segments:

    SELECT segment_type, tablespace_name,
           ROUND(SUM(bytes) / 1024 / 1024) AS size_mb
    FROM dba_segments
    WHERE owner = 'SALES_TEST'
    GROUP BY segment_type, tablespace_name
    ORDER BY tablespace_name, segment_type;

Reconcile row counts of key tables, sequence values, constraints, indexes, grants, and dependencies. Test business flows in the test environment before letting the application use it.

## 10. Ensuring Consistency and Safety When Rerunning

Imports can be interrupted by storage, network, quota, or process errors. A failed import does not mean every change was rolled back completely. A Data Pump job may retain state to attach and continue, or partially created objects may require cleanup.

Before rerunning:

1. Read the previous job's log and identify completed objects.
2. Check Data Pump job status and decide whether to attach/continue if appropriate.
3. Check which tables already have data and how many rows were loaded.
4. Reconfirm TABLE_EXISTS_ACTION for each data category.
5. Consider recreating a clean target schema if the environment allows and the goal is a consistent copy.
6. Do not rerun APPEND repeatedly without knowing where the previous run stopped.

If a point-in-time consistent copy is required, coordinate export timing, transaction consistency, and data changes during the transfer. A dump taken while the application continues writing data may require an additional synchronization strategy depending on cutover requirements.

## 11. Pre- and Post-Import Checklist

### Before import

- Confirm source database, target database, DBID, and schemas to move.
- Confirm dump files and DIRECTORY object.
- Check target schema, privileges, profile, quotas, and default tablespace.
- Create target tablespaces and check datafiles and storage.
- List schema/tablespace mappings for tables, indexes, LOBs, and partitions.
- Check existing objects in the target schema.
- Preview DDL using SQLFILE if changing owners/tablespaces or if the target schema is not clean.
- Select CONTENT and TABLE_EXISTS_ACTION to match the objective.
- Protect dumps, logs, and credentials; do not put passwords into shared files.

### After import

- Check exit status and the entire log.
- Check created, skipped, and INVALID objects.
- Reconcile row counts of critical tables.
- Verify segments reside in the intended tablespaces.
- Verify quotas, grants, roles, synonyms, sequences, and dependencies.
- Recompile PL/SQL and views if needed.
- Test the application with the target connection string and owner.
- Retain logs, sanitized parameter files, and reconciliation records.

## 12. Principles to Remember

- REMAP_SCHEMA changes the owner of imported objects from source schema to target schema; it does not replace every schema-name string in source code.
- REMAP_TABLESPACE changes the storage location of imported segments from source tablespace to target tablespace; target tablespaces and quotas must be prepared.
- TABLE_EXISTS_ACTION handles existing tables, not every object type in a schema.
- SKIP keeps existing tables; APPEND adds rows; TRUNCATE deletes existing rows and loads; REPLACE drops and recreates tables from dump metadata.
- APPEND can cause duplicate data if rerun; TRUNCATE and REPLACE destroy existing data.
- SQLFILE helps review DDL before import, but does not prove data loading will succeed.
- INCLUDE and EXCLUDE must be used with appropriate object paths and import modes; omitting objects can break dependencies.
- Always check logs, INVALID objects, row counts, tablespaces, quotas, and the application after import.

A safe schema migration combines remapping with target environment preparation, control over existing objects, and post-import reconciliation. Treat each parameter as a distinct decision: which owner will own the objects, where segments will reside, and whether existing table data will be kept, appended to, truncated, or replaced.
