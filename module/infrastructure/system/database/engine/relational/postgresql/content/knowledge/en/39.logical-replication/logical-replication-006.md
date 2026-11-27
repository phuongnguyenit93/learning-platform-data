# DDL, Sequences, Large Objects, and Limitations Requiring Separate Handling in PostgreSQL

PostgreSQL logical backups store structure and data at the database-object level rather than directly copying data files. The primary tools are pg_dump, pg_restore, and pg_dumpall. This approach is flexible when migrating databases, restoring a schema/table, or upgrading across major versions.

However, a logical dump is not always a complete copy of everything an application needs. DDL has dependencies and execution ordering; sequences have independent state that does not follow MVCC; large objects are stored separately from regular rows; roles and tablespaces are global objects; extensions, foreign data, and OS-level configurations may require separate preparation.

~~~text
PostgreSQL database
       |
       +-------------------------------+
       |                               |
       v                               v
  Schema / DDL                    Data objects
  - schemas                       - table rows
  - types/domains                 - sequence values
  - functions                     - large objects
  - tables/views                  - data-only sections
  - indexes/constraints
  - triggers/policies
       |                               |
       +---------------+---------------+
                       |
                       v
                   pg_dump
                       |
             +---------+---------+
             |         |         |
             v         v         v
           Plain     Custom    Directory
           SQL       archive   archive
             |         |         |
           psql     pg_restore pg_restore
                       |
                       v
                Target database
                       |
          +------------+-------------+
          |            |             |
          v            v             v
       Roles       Extensions    External systems
       /tablespace  /libraries   /files /secrets
       globals      /versions    /remote data
~~~

This lesson belongs to the **Logical Replication** chapter of the *Database Engine Relational PostgreSQL* module, focusing on what to watch out for when dumping/restoring DDL, sequences, large objects, and the limitations of logical backups.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the scope of logical backups and the differences between pg_dump, pg_restore, and pg_dumpall.
2. Distinguish schema-only, data-only, and full logical dumps.
3. Choose plain, custom, directory, or tar format.
4. Understand pre-data, data, and post-data ordering during restore.
5. Analyze dependencies among schemas, types, functions, tables, sequences, indexes, and constraints.
6. Identify global objects excluded from a regular pg_dump.
7. Back up and restore roles and tablespaces using pg_dumpall --globals-only.
8. Understand why extensions require compatible packages/binaries on the target.
9. Explain sequence state, nextval, setval, and non-transactional behavior.
10. Synchronize sequences after loading data or importing a subset of tables.
11. Distinguish large objects from bytea and ordinary OIDs.
12. Ensure large objects are included in dumps when using selective options.
13. Identify orphan large objects and access permission issues.
14. Understand pg_dump limitations by database, table/schema, and dependencies.
15. Handle foreign tables, FDWs, credentials, and data residing outside PostgreSQL.
16. Choose compatible client/server versions when dumping and restoring.
17. Use pg_restore to inspect archive contents and control restore order/objects.
18. Verify logical backups by test-restoring and validating data.
19. Design migration procedures with clear downtime, consistency, and rollback plans.
20. Identify limitations that must be handled separately before treating a logical dump as a complete backup.

## 2. What Is a Logical Backup?

A logical backup represents a database as SQL statements and/or a structured archive containing object definitions and data. During restore, PostgreSQL recreates objects and loads data into the target database.

### 2.1. Logical Objects

A database contains many kinds of objects:

- Schemas and namespaces.
- Tables, partitioned tables, views, and materialized views.
- Sequences and identity columns.
- Types, domains, enums, and composite types.
- Functions, procedures, operators, and aggregates.
- Indexes, constraints, triggers, and rules.
- Policies and grants.
- Large objects.
- Extension declarations and certain database-level settings.

### 2.2. Logical Dump

pg_dump connects to a single database and creates a dump of that database. You can select the whole database, schemas, tables, sections, or objects via options.

### 2.3. Logical Restore

Plain SQL dumps are executed using psql. Custom, directory, and tar archives are processed using pg_restore.

### 2.4. Logical Backups Do Not Copy Raw PGDATA

A dump is not a physical copy of the data directory. It recreates objects via DDL and loads data through logical mechanisms.

### 2.5. Portability

Logical dumps are generally more portable than physical backups when moving data across environments or major versions, though SQL, extensions, collations, and new features may still be incompatible with older targets.

## 3. pg_dump, pg_restore, and pg_dumpall

| Tool | Responsibility | Input/Output |
| --- | --- | --- |
| pg_dump | Dump a single database | Server → dump file |
| pg_restore | Restore or list non-plain archives | Archive → target server or SQL |
| pg_dumpall | Dump entire cluster at logical level | Server → SQL script |
| psql | Execute plain SQL dump | SQL script → database |
| pg_verifybackup | Verify physical backup manifest | Physical backup directory |

### 3.1. pg_dump

Use when backing up a specific database:

~~~bash
pg_dump -h db.example.internal -U backup_user \
  -d appdb -Fc -f appdb.dump
~~~

### 3.2. pg_restore

Use with custom, directory, and tar archives:

~~~bash
pg_restore -h target.example.internal -U restore_user \
  -d appdb --verbose appdb.dump
~~~

### 3.3. pg_dumpall

Dump multiple databases and global objects:

~~~bash
pg_dumpall -h db.example.internal -U backup_user \
  -f cluster.sql
~~~

### 3.4. Global Objects

A regular pg_dump does not back up cluster-level roles and tablespaces. Use:

~~~bash
pg_dumpall --globals-only -h db.example.internal \
  -U backup_user -f globals.sql
~~~

### 3.5. Dump Roles Only

~~~bash
pg_dumpall --roles-only -h db.example.internal \
  -U backup_user -f roles.sql
~~~

Exact options may vary by version. Check pg_dumpall --help on your installed client.

### 3.6. Backing Up Databases and Globals as Separate Artifacts

In operations, you can store each database dump alongside a globals dump. This gives better control over restore order and permissions, while keeping them together as one backup set.

## 4. Plain SQL and Archive Formats

pg_dump supports several output formats.

### 4.1. Plain Format

~~~bash
pg_dump -d appdb -Fp -f appdb.sql
~~~

Plain format is a human-readable SQL script. Restore with psql:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb -f appdb.sql
~~~

### 4.2. Custom Format

~~~bash
pg_dump -d appdb -Fc -f appdb.dump
~~~

Custom format stores PostgreSQL's proprietary archive. You can inspect contents, select objects, and restore in parallel with pg_restore.

### 4.3. Directory Format

~~~bash
pg_dump -d appdb -Fd -j 4 -f appdb_dir
~~~

Directory format creates multiple files inside a directory and supports parallel dumps. It is useful for large databases or increasing throughput.

### 4.4. Tar Format

~~~bash
pg_dump -d appdb -Ft -f appdb.tar
~~~

Tar format packages dump components into a tar archive. Restore with pg_restore.

### 4.5. Comparison

| Format | Human-readable | Selective object restore | Parallel dump | Parallel restore |
| --- | --- | --- | --- | --- |
| Plain | Yes | Via editing/scripting | No | Not via pg_restore |
| Custom | No | Yes | No | Yes |
| Directory | No | Yes | Yes | Yes |
| Tar | No | Yes | No | No parallel restore like custom/directory |

### 4.6. Choosing a Format

- Plain suits readable SQL scripts that can be edited and stored in migration workflows.
- Custom suits general-purpose backups requiring object selection or parallel restore.
- Directory suits large databases needing parallel dump and restore.
- Tar suits workflows requiring tar archives or compatible storage pipelines.

### 4.7. Do Not Use psql for Custom Archives

Custom/directory/tar files are not plain SQL scripts. Use pg_restore to read and restore those formats properly.

## 5. Snapshot Consistency of pg_dump

A key strength of pg_dump is producing consistent dumps while the database continues serving reads and writes.

### 5.1. MVCC Snapshot

pg_dump uses a snapshot to read data in a consistent state. Changes committed after the snapshot do not appear in table data for that dump.

### 5.2. Writes Continue

Applications can continue running INSERT/UPDATE/DELETE while the dump runs. pg_dump does not require stopping all writes for a normal database dump.

### 5.3. Concurrent DDL

pg_dump acquires appropriate locks to protect objects being dumped. Concurrent DDL may wait on locks or cause the dump to fail if objects are altered/dropped mid-run. Avoid deploying major DDL simultaneously with backups.

### 5.4. Parallel Dump

Directory format with -j uses synchronized snapshots so workers read the exact same data state. The server must support the corresponding synchronized snapshot mechanism.

### 5.5. Sequences Are an Important Exception

Sequence state does not follow MVCC snapshots like table rows. Sequence values can advance during the dump. Therefore, a consistent table-data dump does not guarantee every sequence value reflects the exact same instant.

### 5.6. pg_dumpall Is Not a Single Cluster-Wide Snapshot

pg_dumpall invokes dump operations per database. Databases can be dumped at different instants. If applications maintain cross-database invariants, quiesce writes or choose another suitable backup strategy.

## 6. Dumping an Entire Database, Schema, or Table

### 6.1. Full Database Dump

~~~bash
pg_dump -Fc -d appdb -f appdb.dump
~~~

This is the simplest way to capture objects and data in a single database.

### 6.2. Schema-Only

~~~bash
pg_dump -s -d appdb -f appdb_schema.sql
~~~

Dumps definitions only, without table data or sequence current values as a data backup.

### 6.3. Data-Only

~~~bash
pg_dump -a -d appdb -Fc -f appdb_data.dump
~~~

Dumps data only. The target must already have a compatible schema or have the schema restored beforehand.

### 6.4. Dump One Schema

~~~bash
pg_dump -n app -Fc -d appdb -f app_schema.dump
~~~

### 6.5. Dump One Table

~~~bash
pg_dump -t 'app.orders' -Fc -d appdb -f orders.dump
~~~

### 6.6. Multiple Tables

You can repeat -t for desired tables. Use exact patterns and verify the object list before executing.

### 6.7. Table Selection Does Not Pull All Dependencies

Dumping a table does not automatically guarantee inclusion of every type, function, sequence, schema, or object that the table depends on. Identify dependencies and dump/restore them separately.

### 6.8. Schema Selection Has Limits

Selecting one schema does not automatically include external objects referenced by objects inside that schema—for instance, a function using a type in another schema or a foreign server in another cluster.

## 7. DDL and Object Creation Order

DDL describes database structure. Objects frequently depend on one another, so restore requires proper ordering.

### 7.1. Dependency Graph

Example where an orders table depends on a schema, enum type, sequence, function, and extension:

~~~text
Extension / Type / Schema
          |
          v
      Sequence
          |
          v
        Table
          |
     +----+-----+
     |          |
     v          v
   Index     Constraint
     |          |
     +-----+----+
           |
           v
        Trigger
           |
           v
        Application
~~~

### 7.2. Schemas

Schemas are namespaces containing objects. Create schemas before creating objects inside them.

### 7.3. Types and Domains

Table columns can use enums, domains, composite types, or range types. Types must exist before creating dependent tables.

### 7.4. Functions and Procedures

Default expressions, generated expressions, triggers, and views can invoke functions. Restores need functions in place before referencing objects when dependencies require them.

### 7.5. Tables and Partitions

Create tables/partitioned tables before loading data. Partition attachments and constraints may belong in the post-data phase.

### 7.6. Indexes and Constraints

Indexes and certain constraints are typically created after loading data to reduce restore cost. PostgreSQL archives divide components into sections to support ordering.

### 7.7. Triggers and Rules

Triggers can fire while data is loaded. Restore tooling manages appropriate ordering; when writing manual migrations, account for trigger behavior and side effects.

## 8. Archive Sections

pg_dump/pg_restore divide an archive into three logical sections:

| Section | Typical contents |
| --- | --- |
| pre-data | Schemas, types, functions, tables, and object definitions needed before data |
| data | Table data, large objects, and sequence values |
| post-data | Indexes, triggers, rules, and constraints created after data |

### 8.1. Pre-data

~~~bash
pg_dump -Fc -d appdb --section=pre-data -f pre.dump
~~~

This section holds definitions required before loading data.

### 8.2. Data

~~~bash
pg_dump -Fc -d appdb --section=data -f data.dump
~~~

The data section holds table data and data items such as sequence values/large objects within the dump scope.

### 8.3. Post-data

~~~bash
pg_dump -Fc -d appdb --section=post-data -f post.dump
~~~

This section typically holds indexes, triggers, and constraints added after data loading.

### 8.4. Inspecting the TOC

~~~bash
pg_restore --list appdb.dump
~~~

The TOC (table of contents) lists archive entries. You can save it to a file, edit the restore list, or use -L to restore only selected entries.

### 8.5. Do Not Arbitrarily Reorder

If restoring sections manually, preserve dependencies. Loading data before creating types/tables or restoring constraints before data satisfies them will cause errors.

## 9. Restoring with pg_restore

### 9.1. Restore into an Existing Database

~~~bash
createdb -h target.example.internal -U admin appdb_restore

pg_restore -h target.example.internal -U restore_user \
  -d appdb_restore --verbose appdb.dump
~~~

### 9.2. Create the Database from the Archive

~~~bash
pg_restore -h target.example.internal -U admin \
  -C -d postgres appdb.dump
~~~

-C instructs pg_restore to create the database per archive metadata. Connecting to -d postgres provides the initial database where CREATE DATABASE executes.

### 9.3. Clean Before Restoring

~~~bash
pg_restore --clean --if-exists \
  -d appdb_restore appdb.dump
~~~

--clean drops objects to be restored before recreating them. This can destroy existing data; use only on confirmed target databases.

### 9.4. Parallel Restore

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

Parallel restore supports custom and directory archives. It accelerates restores, though it requires CPU, I/O, and connection headroom.

### 9.5. Exit on Error

~~~bash
pg_restore --exit-on-error -d appdb_restore appdb.dump
~~~

Stops immediately on error instead of silently continuing into a partially restored state.

### 9.6. Plain SQL Restore

~~~bash
psql -X -v ON_ERROR_STOP=1 \
  -h target.example.internal -U restore_user \
  -d appdb_restore -f appdb.sql
~~~

-X prevents personal psqlrc files from altering script behavior; ON_ERROR_STOP makes psql fail when a SQL statement errors.

### 9.7. Single Transaction

For small restores, you can use the appropriate single-transaction mode of pg_restore or psql. Not all options are compatible with parallel restore; check --help for your version.

## 10. Ownership, Privileges, and Global Objects

A logical dump can contain owners and ACLs, provided the corresponding roles exist on the target.

### 10.1. Owner

During restore, ALTER OWNER statements can fail if the role does not exist.

### 10.2. ACL

GRANT/REVOKE statements reference roles and objects. If roles are missing, restore can fail in the privileges section.

### 10.3. Globals

Use pg_dumpall --globals-only to dump roles and tablespaces:

~~~bash
pg_dumpall --globals-only -h db.example.internal \
  -U backup_user -f globals.sql
~~~

### 10.4. Restore Globals First

Typically, create roles and tablespaces before restoring a database containing owners, grants, or objects placed in those tablespaces.

~~~bash
psql -X -v ON_ERROR_STOP=1 -d postgres -f globals.sql
~~~

Execute using an appropriately privileged account and review globals contents before applying.

### 10.5. Omitting Owner

If the target uses a different role mapping, you can restore with:

~~~bash
pg_restore --no-owner -d appdb_restore appdb.dump
~~~

When omitting owner, objects are generally created under the role executing the restore. Assign target ownership afterward.

### 10.6. Omitting Privileges

~~~bash
pg_restore --no-acl -d appdb_restore appdb.dump
~~~

Use only when permissions will be re-applied via another process. Do not omit ACLs and forget to restore the security model.

### 10.7. Password Hashes

Globals dumps can contain role definitions and password hashes depending on privileges/configuration. Protect these files as secrets; never post them in chats/logs or public repositories.

## 11. What Is a Sequence?

A sequence is an object that generates numeric sequences on demand, commonly used for primary keys or identifiers.

~~~sql
CREATE SEQUENCE app.orders_id_seq
    AS bigint
    START WITH 1
    INCREMENT BY 1
    CACHE 20;
~~~

Fetch a value:

~~~sql
SELECT nextval('app.orders_id_seq');
~~~

### 11.1. Serial

A serial column is shorthand that creates an integer column, a sequence, and a default calling nextval, while linking sequence ownership to the column.

### 11.2. Identity

An identity column uses an internal sequence with SQL-standard syntax:

~~~sql
CREATE TABLE app.orders (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description text
);
~~~

### 11.3. Standalone Sequence

A sequence can be shared across multiple tables or used independently, rather than owned by a single column.

### 11.4. nextval

nextval() issues a new value atomically across concurrent sessions.

### 11.5. currval

currval() returns the most recent sequence value obtained via nextval in the current session.

### 11.6. setval

setval() sets sequence state. It is commonly used after importing data or when synchronizing sequences with loaded IDs.

## 12. Why Do Sequences Need Special Handling During Backup?

Sequences do not behave like ordinary tables.

### 12.1. Sequences Do Not Follow MVCC Snapshots

Sequence advances are not rolled back with transactions like table updates and do not follow snapshot isolation in the same way. A pg_dump has a consistent snapshot for table data, yet a sequence may have advanced during the dump.

### 12.2. Sequences Can Have Gaps

Issued values may go unused due to transaction rollbacks, crashes, or caching. Sequences do not guarantee gapless consecutive numbers.

### 12.3. Cache

Sequences can cache multiple values per session. last_value does not necessarily equal the highest committed ID in the table.

### 12.4. Data Dumps and Sequence State

pg_dump stores sequence definitions in schema and sequence values in the data section when dumping data. A schema-only dump does not save current sequence state.

### 12.5. Data-Only Dumps

A data-only dump can record sequence values to synchronize after loading table rows, depending on selected objects.

### 12.6. Dumping a Single Table

If you dump only a table without including its associated sequence, data can be restored while the sequence is not automatically positioned properly. Identify sequences used by columns and include them in your backup/migration.

## 13. Inspecting Sequences and Column Relationships

### 13.1. Finding the Sequence Attached to Serial/Identity

~~~sql
SELECT pg_get_serial_sequence('app.orders', 'id');
~~~

This function returns the name of the sequence owned by the column, including serial/identity when ownership exists.

### 13.2. Listing Sequences

~~~sql
SELECT
    schemaname,
    sequencename,
    data_type,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    cache_size,
    last_value
FROM pg_sequences
WHERE schemaname = 'app'
ORDER BY sequencename;
~~~

Some fields may be null if the role lacks privileges or the sequence has not been used yet. Columns and view details may vary by version.

### 13.3. Inspecting Identity Columns

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    is_identity,
    identity_generation,
    column_default
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'orders';
~~~

### 13.4. Verifying Sequences in Schema Dumps

Use pg_restore --list or inspect plain SQL dumps to verify whether sequence definitions and setval entries are included.

### 13.5. Do Not Infer Sequence State from MAX(id) Under Active Workloads

MAX(id) reflects only committed rows currently visible in the table; a sequence may already have issued higher values to uncommitted transactions or discarded IDs. Check both sequence state and workload.

## 14. Synchronizing Sequences After Data Import

When importing a subset of tables or merging data, a sequence can fall behind the highest ID in the table.

### 14.1. Duplicate Key Error Example

Suppose a table has IDs up to 5000 while the sequence is still at 4200. A new insert calling nextval can generate an already-existing ID and raise a unique violation.

### 14.2. Retrieving the Sequence Name

~~~sql
SELECT pg_get_serial_sequence('app.orders', 'id');
~~~

### 14.3. Synchronizing to MAX(id)

For a sequence owned by the id column:

~~~sql
SELECT setval(
    pg_get_serial_sequence('app.orders', 'id')::regclass,
    COALESCE(MAX(id), 1),
    COUNT(*) > 0
)
FROM app.orders;
~~~

Meaning:
- If the table has rows, set the sequence to MAX(id) with is_called = true; the next nextval will return the subsequent value per increment.
- If the table is empty, set it to 1 with is_called = false; the next nextval returns the start value in this simple example.

### 14.4. Non-Default Sequence Start/Increment

If a sequence has a start value or increment other than 1, use actual metadata to compute the right value. Do not assume every sequence increments from 1.

### 14.5. Block Writes While Synchronizing

Perform sequence resync only after stopping or locking relevant writers. If applications continue calling nextval concurrently, the value can advance immediately after resync.

### 14.6. Identity Columns

pg_get_serial_sequence can also locate sequences attached to identity columns. Verify exact table/column names and privileges before calling setval.

### 14.7. Do Not Use MAX(id) as a Gapless Policy

Sequences generate identifiers, not gapless business counters. Never try to fill gaps by resetting sequences while applications are live.

## 15. Sequences and Transaction Semantics

### 15.1. nextval Does Not Roll Back

~~~sql
BEGIN;
SELECT nextval('app.orders_id_seq');
ROLLBACK;
~~~

An issued value is not returned merely because the transaction rolled back.

### 15.2. setval Does Not Roll Back Normally

Sequence state changes via setval take effect immediately and are not undone like table rows when a transaction aborts.

### 15.3. Concurrent Sessions

Multiple sessions calling nextval receive distinct values atomically. Do not use sequences as a gapless sequential counter.

### 15.4. Dumping While Writes Continue

Table rows in a dump reflect the snapshot; sequence values are read at a different moment in the process. Upon restore, sequence values may be higher than some rows in the snapshot, creating valid gaps.

### 15.5. Importing into an Active Database

When loading rows into a database that already receives writes, decide how IDs and sequence states merge. Never blindly restore old sequence states from a dump over an active target, as that can move the sequence backward below already-issued target IDs.

## 16. Sequences in Serial and Identity

### 16.1. Serial

Example:

~~~sql
CREATE TABLE app.invoice (
    id bigserial PRIMARY KEY,
    invoice_no text NOT NULL
);
~~~

PostgreSQL creates a sequence and default nextval. pg_dump usually records both the sequence relationship and current value in a full data dump.

### 16.2. Identity

~~~sql
CREATE TABLE app.invoice (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_no text NOT NULL
);
~~~

Identity is a column property with a sequence managed alongside the column. Dump/restore must preserve generation mode and state.

### 16.3. GENERATED ALWAYS

When loading explicit IDs into an ALWAYS identity column, appropriate syntax/options such as OVERRIDING SYSTEM VALUE in SQL or corresponding restore options may be needed. pg_dump/pg_restore handle standard dumps, while manual data imports require attention.

### 16.4. GENERATED BY DEFAULT

Allows explicit values during INSERT, which is helpful in some migration workflows. Always verify sequence state after import.

### 16.5. Ownership Dependency

Sequence ownership ensures DROP TABLE/COLUMN properly handles the associated sequence. A standalone unowned sequence has its own lifecycle and requires separate backup consideration.

## 17. What Is a Large Object?

A large object (LO) is a PostgreSQL mechanism for storing large binary content outside regular rows, referenced by an OID.

### 17.1. OID Reference

A table can store an OID referencing a large object:

~~~sql
CREATE TABLE app.documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_oid oid,
    file_name text
);
~~~

### 17.2. Large Object Storage

Large object contents are split into pages/chunks and stored in dedicated system catalogs such as pg_largeobject; metadata/owner/ACLs reside in related catalogs.

### 17.3. Large Object API

Applications can use the large object API to open, read, write, seek, truncate, or unlink objects. Language drivers often provide wrappers.

### 17.4. An OID Is Not the Content

Dumping a table containing OID values in a column does not mean large object contents were dumped. If LOs are omitted from the archive, OIDs in rows may point to nonexistent objects on the target.

### 17.5. Large Objects Differ from bytea

bytea is a binary data type stored as a column value, TOASTed when large. A large object is an independent object accessed via OID and API. The two storage approaches have different lifecycles, permissions, and backup behaviors.

## 18. Large Objects vs. bytea: Which to Choose?

| Criterion | bytea | Large object |
| --- | --- | --- |
| Reference method | Column value | OID |
| Storage | Inside row/TOAST | Separate large object catalog |
| SQL access | Readable/writable as a value | Typically uses LO API |
| Streaming | Driver may stream value depending on API | LO API supports chunked read/write |
| Permissions | Table/column privileges | LO ownership/ACL and API privileges |
| Logical dump | Table data | Must ensure LO objects are included |
| Lifecycle | Tied to the row | Can exist independently of referencing rows |
| Orphan risk | No separate LO orphans | Orphan LOs possible if rows are deleted without unlinking |

### 18.1. When to Choose bytea

Use when binary data is a natural part of the row and size/workload suits your driver, queries, and storage design.

### 18.2. When to Choose Large Objects

Use when streaming/chunked access to large content is needed or the application already relies on the large object API.

### 18.3. Do Not Convert Arbitrarily

Converting large object OIDs to bytea requires reading each LO's content and writing it into a column. Copying only the OID number does not transfer the content.

## 19. pg_dump and Large Objects

For a full-database dump, pg_dump normally includes large objects by default. However, certain schema/table-selection or schema-only options alter this default. When applications use LOs, check and explicitly specify -b/--blobs if needed.

### 19.1. Full Database Dump with LOs

~~~bash
pg_dump -Fc -b -d appdb -f appdb_with_blobs.dump
~~~

### 19.2. --no-blobs

~~~bash
pg_dump -Fc --no-blobs -d appdb -f appdb_without_blobs.dump
~~~

Do not use --no-blobs if the application needs large object contents to function.

### 19.3. Schema-Only Dump

Schema-only does not store large object contents as a data backup. It may preserve table definitions/OID columns without LO bytes.

### 19.4. Selective Table Dump

~~~bash
pg_dump -Fc -t 'app.documents' -b \
  -d appdb -f documents.dump
~~~

When using table selection, actively ensure large objects are included. -b can include large objects across the database in the archive; it is not necessarily limited to OIDs referenced by the selected rows.

### 19.5. Do Not Assume Dependencies Are Automatically Included

pg_dump is not a general dependency-closure tool for arbitrary table subsets. If dumping a table with OID references, verify LO data is in the archive and restorable.

### 19.6. Inspecting the TOC

~~~bash
pg_restore --list documents.dump
~~~

Look for entries related to large objects/blobs and match them against your dump scope.

## 20. Restoring Large Objects

### 20.1. Full Archive Restore

~~~bash
pg_restore -d appdb_restore --verbose appdb_with_blobs.dump
~~~

If the archive contains large objects, pg_restore loads them along with other entries per TOC/dependencies.

### 20.2. Restoring Selected Entries

You can use pg_restore --list to generate a TOC list and select entries with -L. When selecting individual tables or LOs, keep all dependencies required by the application.

### 20.3. Large Object Permissions

Large objects have their own owners and ACLs. Check target roles and LO read/write permissions after restore, not just SELECT privilege on the table storing the OID.

### 20.4. LO API

Applications using the large object API need appropriate permissions and transaction context per API rules. Test with the actual driver after restore.

### 20.5. Orphan Large Objects

If an application deletes a referencing row without unlinking the LO, the object can remain with no row pointing to it. A full database dump may still carry those orphan LOs.

### 20.6. Controlled Cleanup

Identify unreferenced LOs before deleting. Never run bulk unlinks without understanding the schema/application reference model; multiple rows can share one LO.

## 21. Inspecting Large Object Inventory

You can inspect large object metadata:

~~~sql
SELECT
    loid,
    pageno,
    length(data) AS chunk_bytes
FROM pg_largeobject
ORDER BY loid, pageno
LIMIT 50;
~~~

The pg_largeobject catalog stores chunks; direct access requires appropriate privileges and should not be treated as a normal application API.

### 21.1. Metadata

~~~sql
SELECT *
FROM pg_largeobject_metadata
ORDER BY oid
LIMIT 50;
~~~

### 21.2. Counting LOs

~~~sql
SELECT count(*) AS large_object_count
FROM pg_largeobject_metadata;
~~~

### 21.3. Storage Size

You can estimate byte volume by summing chunk lengths:

~~~sql
SELECT
    count(DISTINCT loid) AS object_count,
    sum(length(data)) AS stored_chunk_bytes
FROM pg_largeobject;
~~~

This estimates stored chunk content bytes, not exact total disk usage since it excludes catalog/index/page overhead and bloat.

### 21.4. Access Privileges

Large object metadata stores owners/ACLs. Verify application access after restore; table grants do not automatically substitute for LO privileges.

### 21.5. OID Reference Audit

To find orphan objects, you must know which OID columns actually represent LO references. Not every oid column is a large object reference. Write checks according to the schema/application model.

## 22. DDL Dependencies Requiring Separate Handling

A full-database logical dump can order many dependencies for standard restores. However, when selecting specific objects, moving across environments, or splitting schemas, check out-of-scope dependencies.

### 22.1. Schemas and search_path

Objects can be referenced by schema-qualified names or depend on search_path. Restoring into a database with a different schema layout or search_path can make functions/views behave incorrectly.

### 22.2. Types and Domains

Enum/domain/composite types must exist before creating columns/functions that use them. Types in other schemas must be included in the migration set.

### 22.3. Functions and Procedures

Views, triggers, generated expressions, and defaults can call functions. Preserve language, function body, owner, volatility, security definer, and grants.

### 22.4. Collations

Collations depend on locale/ICU/OS versions. Restoring onto a target missing a collation or using a different collation version can affect sorting/index semantics.

### 22.5. Extensions

Dumps normally record CREATE EXTENSION and related metadata, but do not package shared libraries or extension source code. The target must have compatible extension packages installed.

### 22.6. Operators and Operator Classes

Index definitions can reference operator classes or extension-specific access methods. Matching packages/objects must be present before restoring indexes.

### 22.7. Triggers and Rules

Triggers can call functions or write to other tables. During data loads, restore tooling usually controls order; manual imports must account for trigger side effects.

### 22.8. Constraints

Foreign keys, unique/check constraints, and exclusion constraints can be created in post-data. Target data must satisfy constraints when they are added.

### 22.9. Views and Materialized Views

Views depend on tables/functions/types. Materialized views may need refreshing after restore depending on dump method and data availability; verify data and actual state.

### 22.10. Row-Level Security

Policies and role memberships affect what data applications see. Restoring schemas without roles/grants/policies can produce behavior different from production.

## 23. Extensions, FDWs, and Data Outside the Database

Logical dumps do not package every dependency outside PostgreSQL.

### 23.1. Extension Packages

Extensions such as PostGIS, pgcrypto, or internal extensions must be installed on the target with compatible versions. CREATE EXTENSION in a dump merely references an installed package.

### 23.2. Shared Libraries

C-language functions or extensions using shared libraries require binaries compatible with the OS, PostgreSQL major version, and architecture.

### 23.3. Foreign Data Wrappers

Dumps can contain foreign server/foreign table definitions within supported limits, but actual data residing on remote sources is not automatically copied like local table data.

### 23.4. User Mappings and Secrets

Connection details/credentials to external services must be checked separately. Do not assume all secrets were dumped or can be safely restored from SQL files.

### 23.5. External Files

Files on filesystems, object storage, application servers, or external services are not inside a logical database dump. Back them up on their own lifecycle.

### 23.6. Sequences/IDs in External Systems

If an application uses sequences to issue IDs across multiple systems or syncs to message brokers, restoring a database may not automatically restore external state. Reconciliation is needed.

## 24. Global Objects and Database-Level Settings

### 24.1. Roles

Roles are cluster-wide objects. A database dump may contain owner/ACL references without creating full role definitions.

### 24.2. Tablespaces

Tablespace definitions are global objects. Restoring to another server requires preparing tablespace names, locations, and filesystem paths.

### 24.3. Database Settings

Some database-level settings are dumped with the database, while server-wide configurations like postgresql.conf, pg_hba.conf, and SSL files must be backed up separately.

### 24.4. Replication Slots

Physical/logical replication slots and their runtime state are not part of a normal logical dump. Recreate replication setups using dedicated runbooks.

### 24.5. Server Configuration

Parameters such as shared_buffers, max_connections, archive_command, wal_level, logging, listen_addresses, and authentication rules sit outside logical database data.

### 24.6. Database Encoding and Locale

When creating the target database, choose the proper encoding, locale provider, collation, and template. Not every difference can be fixed after database creation.

## 25. pg_dumpall and Cross-Database Consistency

pg_dumpall creates a SQL dump of multiple databases plus globals, yet it does not turn the whole cluster into a single MVCC snapshot.

### 25.1. Each Database Is Dumped Individually

Each database has its own snapshot point. A transaction workflow spanning two databases may be observed at different states across two dumps.

### 25.2. Cross-Database Invariants

PostgreSQL does not support regular transactions across multiple databases. However, applications may maintain business workflows spanning multiple databases. If a shared consistent point is required, quiesce writers or use a physical backup strategy.

### 25.3. Dumping Globals Concurrently

Roles/tablespaces changing while databases are dumping can cause mismatches if globals dumps and database dumps are uncoordinated.

### 25.4. Restore Order

Usually restore globals first, then create/restore databases. Verify tablespaces exist before restoring objects placed in them.

### 25.5. Partial Outcomes

pg_dumpall can continue/log errors depending on scripts and versions. Check exit status, stderr, and confirm every database has a complete dump.

## 26. Client and Server Versions

### 26.1. Using a Compatible pg_dump

pg_dump cannot dump from a server major version newer than the client's own major version. Use a client of the same or newer major version than the server per support rules.

### 26.2. Restoring to a Newer Version

Logical dumps are commonly used to move data to a newer major version. Even so, check syntax, extension, collation, and feature compatibility.

### 26.3. Restoring to an Older Version

Dumps from a newer server may contain syntax/objects an older server cannot parse. Never assume logical dumps support downgrades.

### 26.4. pg_restore Version

Use a pg_restore compatible with the archive format/version that created the dump; in practice, use the same version as the pg_dump that produced the file or newer per support guidelines.

### 26.5. Extension Compatibility

Check extension versions on source and target, upgrade scripts, and binary dependencies.

### 26.6. Collation Drift

Different libc/ICU/OS versions can change collation behavior. After restore, check collation versions and reindex per PostgreSQL guidance when necessary.

## 27. Logical Backups Do Not Protect Everything

| Component | Standard pg_dump of a database |
| --- | --- |
| Table data | Yes |
| DDL inside the database | Yes |
| Sequence definitions/state | Yes in full dump; schema-only does not save current state |
| Large objects | Usually included by default in full dump; check when filtering or using --no-blobs |
| Roles | Not dumped completely as globals |
| Tablespace definitions | Not dumped completely as globals |
| postgresql.conf | No |
| pg_hba.conf | No |
| SSL keys/certificates | No |
| Extension binaries | No |
| Remote foreign data | No |
| External files/object storage | No |
| Replication slot runtime state | No |
| OS packages/config | No |
| Data across all databases in cluster | Only when dumping each DB/pg_dumpall |

### 27.1. Distinguishing Data and Environment

A logical dump recreates database objects/data. It does not automatically recreate the entire server environment needed for applications to run.

### 27.2. Backup Runbook

Separately record: PostgreSQL version, extension list, config files, TLS, secrets, FDW endpoints, roles, tablespaces, and application deployment dependencies.

### 27.3. Do Not Call a Dump Full Disaster Recovery If Dependencies Are Missing

If applications rely on external files, extension binaries, or remote services without backups, a logical dump is only one piece of the recovery plan.

## 28. Securing Dump Files

Plain SQL dumps can contain full sensitive data and role definitions.

### 28.1. File Permissions

Grant read permissions only to necessary backup/restore operators and service identities.

### 28.2. Encryption

Encrypt in transit and at rest. Manage keys independently from where dumps are stored.

### 28.3. Password Handling

Use .pgpass with proper permissions or a secret manager. Avoid placing passwords directly in shell history, command logs, or repositories.

### 28.4. SQL Injection in Restore Context

Dumps are executable SQL. Restore only from trusted artifacts and review externally supplied files.

### 28.5. Role Passwords

Globals dumps may contain password hashes. Protect them as sensitive authentication material and restrict access.

### 28.6. Retention and Deletion

Apply retention, encryption, auditing, and secure deletion per organizational data policies.

## 29. Migration Using Logical Dumps

Logical dumps are frequently used when moving databases to new hosts/versions.

### 29.1. Preflight

- Confirm target PostgreSQL version.
- Check extensions, locale/collation, and encoding.
- Check roles, tablespaces, and owners.
- Identify large objects and sequence dependencies.
- Estimate storage size and restore duration.

### 29.2. Schema Freeze

Avoid deploying DDL during a dump/restore migration unless the migration plan accounts for that change.

### 29.3. Initial Dump

Create a full dump or schema/table dump. For large databases, consider directory/custom formats and parallelism.

### 29.4. Delta Changes

pg_dump is a snapshot dump; it does not automatically capture writes occurring after the snapshot. To minimize downtime, implement a separate delta sync strategy such as logical replication or a write freeze/cutover.

### 29.5. Cutover

Pause writes, synchronize final deltas, verify sequence state, and switch the application to the target.

### 29.6. Rollback

Keep the old source recoverable for a defined rollback window. Once the target accepts new writes, rolling back may require reverse replication or reconciliation; merely switching the connection string does not sync new data backward.

## 30. Verifying Dumps and Restores

### 30.1. Check Exit Status

Automation should mark a backup successful only when pg_dump exits with code 0.

### 30.2. Check File Integrity

Confirm the artifact exists, size is reasonable, checksum is recorded, and file is readable.

### 30.3. Check Archive TOC

~~~bash
pg_restore --list appdb.dump
~~~

If the TOC cannot be read, the file may be corrupted or not in the expected archive format.

### 30.4. Restore into a Separate Database

Never test backups by overwriting production. Use an isolated target database/instance.

### 30.5. Verify DDL

Verify schemas, types, functions, triggers, indexes, constraints, policies, and owners were created properly.

### 30.6. Verify Data

Compare row counts, key ranges, aggregate totals, and business invariants. For large objects, check OID references and test reading contents.

### 30.7. Verify Sequences

After import, verify nextval does not generate duplicate IDs and sequence states align with loaded data.

### 30.8. Verify Applications

Run smoke tests, representative transactions, and queries dependent on extensions/FDWs.

## 31. Limitations When Dumping Part of a Database

### 31.1. Table Selection Does Not Automatically Include Dependencies

A table may use an enum in another schema, a function in a default expression, a sequence, a trigger function, or an extension. Dumping a table alone does not guarantee dependencies are included.

### 31.2. Cross-Schema References

Views/functions may reference objects outside the selected schema. Restores can fail, or objects may be created yet fail at runtime.

### 31.3. Large Objects

A table with OID references does not guarantee LO content is included in a selective dump. Check --blobs and archive TOC.

### 31.4. Sequences

A table dump may omit associated sequences or current values needed for migration. Identify sequences and synchronize after import.

### 31.5. Foreign Keys

Dumping a single table can omit referenced tables. When restoring constraints, the target needs matching tables/keys or a plan to separate constraints.

### 31.6. Triggers

Trigger functions and auxiliary tables may lie outside the selection. During manual imports, triggers can fail or cause side effects.

### 31.7. Views/Materialized Views

Views depend on multiple tables/functions/types. Selecting a view without its dependencies can cause restore failures.

### 31.8. Select Objects by Dependency Closure

Before dumping a subset, inventory source and target objects, dependencies, roles, extensions, sequences, LOs, and external resources. Test-restore before cutover.

## 32. Large Object Lifecycle and Orphan Objects

A large object can exist independently of the row referencing its OID.

### 32.1. Creating an LO

Applications create LOs via the large object API or appropriate helper functions.

### 32.2. Storing the OID in a Row

A table stores the OID as a reference. PostgreSQL does not automatically treat every OID column as a foreign key relationship to a large object.

### 32.3. Deleting a Row

DELETEing a row containing an OID does not necessarily delete the large object's content automatically.

### 32.4. Orphan Growth

If applications fail to call unlink when an object is no longer needed, pg_largeobject can grow even as application row counts shrink.

### 32.5. Dumps Can Still Carry Orphans

A full database dump preserves existing LOs, including LOs no longer referenced by any row. They remain part of the actual database data.

### 32.6. Cleanup Policy

Build reference-checking logic per schema/application, identify unused LOs, review first, and delete using proper transactions/tooling. Never assume every LO has only one owning row.

## 33. Sequences and Large Objects in Partial Restores

When restoring only a group of tables, these two object types require dedicated verification.

### 33.1. Sequence Checklist

- Is the sequence definition in the dump?
- Are owner/OWNED BY correct?
- Do defaults/identity columns reference the right sequence?
- Was the current value dumped?
- Are new writes occurring on the target during import?
- After import, could nextval generate duplicates?

### 33.2. Large Object Checklist

- Does the table have OID references to LOs?
- Did the dump include blob data?
- Does the TOC contain large object entries?
- Are OID references preserved upon restore?
- Are LO owners/ACLs correct?
- Are there orphan objects or shared LOs?
- Can the application read LOs via driver/API?

### 33.3. Do Not Check Row Counts Alone

Row counts can match while sequences are wrong or LO contents are missing. Verify each object type appropriately.

## 34. Common Errors and How to Resolve Them

### Error 1. Restore Reports role does not exist

Globals dump has not been restored or target role mapping was not prepared. Restore roles first or use --no-owner per plan.

### Error 2. Tablespace Location Does Not Exist

Tablespace globals or filesystem paths have not been created. Prepare mounts/directories and tablespaces before database restore.

### Error 3. Extension is not available

Install the extension package/binary at the matching version before restoring CREATE EXTENSION.

### Error 4. Function/type does not exist

Subset dump omitted dependencies or restore order is wrong. Inspect TOC and add dependent objects.

### Error 5. Duplicate Key After Restore

Sequence state is lower than loaded data or the target already contained old data. Stop writes, locate sequences, and synchronize in a controlled way.

### Error 6. Large Object Missing

Selective dump/schema-only/no-blobs omitted LO content. Create a dump with blobs from a complete source and restore LO entries.

### Error 7. OID Exists, Yet Content Is Unreadable

The table row was restored, but the large object is absent or ACLs are wrong. Check pg_largeobject_metadata and LO privileges.

### Error 8. Restoring Plain Format with pg_restore

Plain SQL requires psql. Use pg_restore for custom/directory/tar archives.

### Error 9. Archive Version Mismatch

Use a pg_restore compatible with or newer than the archive format. Check binary versions and regenerate the dump if needed.

### Error 10. SQL Syntax Unsupported on Target

A dump from a newer server may contain syntax/objects an older target cannot parse. Choose a compatible target version or run a conversion migration.

### Error 11. Parallel Restore Runs Out of Connections

Reduce -j, increase connection capacity appropriately, or restore by sections.

### Error 12. Parallel Dump Unsupported for Format

Parallel dump requires directory format. Use -Fd -j or dump sequentially with another format.

### Error 13. pg_dumpall Missing a Database

Check exit codes/logs per database, connection privileges, and output disk space. Never mark a cluster backup successful if one database failed.

### Error 14. Sequence Moves Backward During Migration

Never restore old sequence state over a target already accepting writes. Stop writes and reconcile state against issued IDs.

### Error 15. Foreign Table Has No Data

Foreign table definitions do not mean remote data was dumped. Back up remote sources using their own tools.

### Error 16. Collation Mismatch

Check locale provider/version and reindex per PostgreSQL guidance after switching environments.

### Error 17. Role Passwords Exposed in Dump

Restrict file permissions, encrypt, audit access, and rotate credentials if artifacts were exposed.

### Error 18. Dump Inconsistent Across Databases

pg_dumpall dumps each database separately. Quiesce applications or use a backup method providing appropriate consistency if cross-DB invariants exist.

### Error 19. Trigger Side Effects During Manual Import

Restore data via standard workflows or plan triggers/constraints explicitly. Never disable triggers arbitrarily without understanding integrity requirements.

### Error 20. Restore Succeeds, Yet Application Fails

Check role memberships, grants, extensions, FDWs, secrets, sequences, LOs, collations, and external dependencies.

## 35. Recommended Logical Backup Workflow

~~~text
Scheduler
   |
   v
Preflight
   |-- source/version
   |-- roles/tablespaces
   |-- extension inventory
   |-- sequence/LO inventory
   |-- disk and credentials
   |
   v
pg_dump / pg_dumpall
   |-- chosen format
   |-- explicit blob policy
   |-- logs and exit code
   |
   v
Artifact verification
   |-- file size/checksum
   |-- archive TOC
   |-- metadata
   |
   v
Offsite encrypted storage
   |
   v
Restore drill
   |-- globals first
   |-- extensions/tablespaces
   |-- database restore
   |-- sequence/LO checks
   |-- application validation
~~~

### 35.1. Pre-Backup Inventory

Record PostgreSQL version, database list, roles, tablespaces, extensions, sequences, large objects, FDWs, and external dependencies.

### 35.2. Choose Format

Choose custom/directory for archive workflows needing selective/parallel restore, or plain for SQL scripts.

### 35.3. Explicit Blobs

If applications use large objects, specify -b in dump workflows that need them and check the TOC.

### 35.4. Save Globals

Dump roles/tablespaces alongside the backup set.

### 35.5. Artifact Integrity

Record checksums, file sizes, timestamps, source cluster, and command options.

### 35.6. Restore Drill

Restore into an isolated target, verify sequences/LOs and application behavior. Mark a backup usable only after required checks pass.

## 36. Recommended Logical Migration Workflow

1. Verify source/target major versions and extension compatibility.
2. Inventory DDL, roles, tablespaces, sequences, LOs, and external systems.
3. Prepare target server, roles, tablespaces, extensions, and database settings.
4. Create initial logical dump.
5. Restore and verify schemas/data on target.
6. Plan synchronization for writes occurring after the snapshot.
7. At cutover, pause writers or finalize delta replication.
8. Synchronize sequence states and large objects.
9. Verify constraints, indexes, triggers, ownership, and ACLs.
10. Run application smoke tests and business reconciliation.
11. Switch traffic to target.
12. Monitor errors and keep a rollback plan.
13. Do not delete source or backups until the agreed rollback window closes.

## 37. Practice Exercises

Exercises use an isolated lab database and dump artifacts containing no sensitive production data.

### Exercise 1. Logical Backup

At what level does a logical backup store a database?

### Exercise 2. Tools

Distinguish the roles of pg_dump, pg_restore, and pg_dumpall.

### Exercise 3. Plain Format

Which tool restores a plain SQL dump?

### Exercise 4. Custom Format

Why do custom archives use pg_restore?

### Exercise 5. Directory Format

Which format supports parallel dump?

### Exercise 6. Schema-Only

Which option creates a schema-only dump, and is current sequence state saved?

### Exercise 7. Data-Only

When should a data-only dump be used?

### Exercise 8. Snapshot

Why can pg_dump produce a consistent snapshot while writes continue?

### Exercise 9. DDL

List three types of dependencies that can cause a single-table restore to fail.

### Exercise 10. Sections

What do the three sections pre-data, data, and post-data contain?

### Exercise 11. TOC

Write the command to list archive contents.

### Exercise 12. Globals

Which command dumps roles and tablespaces?

### Exercise 13. Owner

Which option omits owner commands during restore?

### Exercise 14. ACL

Which option omits privilege commands during restore?

### Exercise 15. Sequence

Why do sequences not follow MVCC snapshots like table rows?

### Exercise 16. nextval

Why can nextval produce gaps?

### Exercise 17. setval

Write an example synchronizing a sequence to MAX(id) after import.

### Exercise 18. Concurrent Writes

Why should sequences not be resynced while writers remain active?

### Exercise 19. Identity

How does an identity column differ from serial in SQL definition?

### Exercise 20. Large Object

By what data type are large objects usually referenced in tables?

### Exercise 21. bytea

State one difference between bytea and large objects.

### Exercise 22. Blob Option

Which option includes large objects in pg_dump?

### Exercise 23. no-blobs

When should --no-blobs not be used?

### Exercise 24. Selective Dump

Why does dumping a table containing OIDs not guarantee large object contents are present?

### Exercise 25. Orphan LO

What is an orphan large object?

### Exercise 26. LO Permissions

Why might table SELECT privilege not suffice to read a large object?

### Exercise 27. Extension

Why is CREATE EXTENSION in a dump insufficient by itself to install an extension on the target?

### Exercise 28. FDW

Why does dumping a foreign table not back up remote data?

### Exercise 29. Version

Can a pg_dump client older than the server major version dump from a newer server?

### Exercise 30. pg_dumpall Consistency

Why does pg_dumpall not produce a single snapshot across all databases?

### Exercise 31. Collation

What issue can collation version differences cause after restore?

### Exercise 32. Global Configuration

Name four components excluded from a standard logical dump.

### Exercise 33. Parallel Restore

Which formats support parallel restore via pg_restore?

### Exercise 34. Exit on Error

Which option stops pg_restore upon encountering an error?

### Exercise 35. Security

Why must a globals dump be protected as a secret?

### Exercise 36. Migration

Why does an initial pg_dump not automatically sync writes occurring after its snapshot?

### Exercise 37. Sequence Restore

Why must sequences be checked after restoring a subset of tables?

### Exercise 38. LO Restore

List four checks needed after restoring large objects.

### Exercise 39. Validation

List five validation layers for a logical backup.

### Exercise 40. Design

Propose a backup/migration workflow covering DDL, sequences, large objects, and external dependencies.

## 38. Reference Solutions

### Exercises 1–5. Tools and Formats

Logical backups store schemas/data at the object level. pg_dump dumps one database; pg_restore reads custom/directory/tar archives; pg_dumpall dumps multiple databases and global objects. Plain SQL uses psql. Directory format supports parallel dump.

### Exercises 6–10. Snapshots and DDL

-s creates schema-only dumps and does not store current sequence state like a data dump. Data-only is used when schemas already exist and data must be loaded. pg_dump uses MVCC snapshots to read table data consistently. Dependency examples: enums/types, sequences/defaults, functions/triggers, extensions, schemas, and foreign keys. Pre-data holds definitions needed before data; data holds rows/LOs/sequence values; post-data holds indexes/triggers/constraints per archive organization.

### Exercises 11–14. Archives and Globals

~~~bash
pg_restore --list appdb.dump
~~~

~~~bash
pg_dumpall --globals-only -f globals.sql
~~~

--no-owner skips owner commands; --no-acl skips privilege commands. Alternative workflows are needed to assign roles/owners/privileges.

### Exercises 15–19. Sequences

Sequence state does not follow MVCC snapshots and nextval/setval do not roll back like table rows. Gaps occur due to rollbacks, caching, or unused allocated values. Sync example:

~~~sql
SELECT setval(
    pg_get_serial_sequence('app.orders', 'id')::regclass,
    COALESCE(MAX(id), 1),
    COUNT(*) > 0
)
FROM app.orders;
~~~

Writers must be paused during resync to prevent races. Identity uses GENERATED ... AS IDENTITY syntax, whereas serial is shorthand creating sequence/default/ownership.

### Exercises 20–26. Large Objects

Large objects are typically referenced by OID. bytea is a column value; LO is an independent object using the LO API. -b/--blobs includes LOs. Do not use --no-blobs if the application needs LO content. Selective dumps can preserve OID columns while omitting LO data unless blobs are included. An orphan LO is an object no longer referenced by any row/application. LOs have their own ACLs, so table SELECT does not automatically grant read permission on LOs.

### Exercises 27–32. Dependencies and Limitations

CREATE EXTENSION creates the extension only if the package/binary is already installed on the target. Foreign table definitions do not copy data on remote servers. An older pg_dump client cannot dump from a newer major server version. pg_dumpall dumps each database separately, so there is no single cluster-wide snapshot. Collation drift can affect sort/index semantics and require reindexing per guidance. Components outside dumps include global roles/tablespaces, server configs, TLS files, extension binaries, external data/files, replication slots, and OS packages.

### Exercises 33–36. Restore and Migration

Custom and directory archives support parallel restore. --exit-on-error stops pg_restore on error. Globals dumps may contain password hashes and must be protected. Initial pg_dump captures only its snapshot point; post-snapshot writes must be synced via a delta mechanism or write freeze/cutover.

### Exercises 37–40. Validation and Workflow

After partial table restores, check sequence definitions/states/nextval and duplicate IDs. For LOs, check OID references, object counts/content readability, owners/ACLs, and orphan lifecycles. Logical backup validation covers exit status, artifact/checksum, TOC/manifest metadata, restore drills, and application/business checks. A complete pipeline inventories DDL/dependencies, roles/tablespaces, sequences and LOs, extensions/FDWs/external systems, dumps with blobs when needed, restores in dependency order, resyncs sequences, validates, and cuts over with delta/rollback plans.

## 39. Quick Reference Table

| Need | Tool/Option |
| --- | --- |
| Dump one database | pg_dump |
| Logical dump of entire cluster | pg_dumpall |
| Dump roles/tablespaces | pg_dumpall --globals-only |
| Restore plain SQL | psql |
| Restore archive | pg_restore |
| Plain output | -Fp |
| Custom archive | -Fc |
| Directory archive | -Fd |
| Tar archive | -Ft |
| Schema-only | -s / --schema-only |
| Data-only | -a / --data-only |
| Include large objects | -b / --blobs |
| Exclude large objects | --no-blobs |
| Select schema | -n |
| Select table | -t |
| Parallel dump | -Fd -j |
| Parallel restore | pg_restore -j |
| View archive TOC | pg_restore --list |
| Select TOC entries | pg_restore -L |
| Create database on restore | pg_restore -C |
| Clean existing objects | pg_restore --clean |
| Stop restore on error | pg_restore --exit-on-error |
| Skip owner commands | --no-owner |
| Skip ACL commands | --no-acl |
| Find owned sequence | pg_get_serial_sequence() |
| Read sequence metadata | pg_sequences |
| Set sequence state | setval() |
| Get next sequence value | nextval() |
| Inspect LO metadata | pg_largeobject_metadata |
| Inspect LO chunks | pg_largeobject |

## 40. DDL, Sequence, and Large Object Checklist

1. Select the exact database/schema/table scope for the dump.
2. Record client/server PostgreSQL major versions.
3. Choose the right plain/custom/directory/tar format.
4. Check dump exit status and artifact integrity.
5. Store TOC/metadata alongside backups.
6. Inventory schemas, types, domains, and collations.
7. Inventory functions, procedures, triggers, and rules.
8. Inventory tables, partitions, indexes, and constraints.
9. Identify dependencies outside selected schemas/tables.
10. Dump roles and tablespaces via globals workflow.
11. Protect globals dumps because they may contain password hashes.
12. Prepare extension packages and shared libraries on the target.
13. Check FDW servers, user mappings, and external credentials.
14. Back up server configurations, TLS files, and secrets separately.
15. Check sequence definitions and ownership.
16. Identify serial/identity columns and sequence names.
17. Ensure data dumps include sequence values when needed.
18. Resync sequences after partial imports or ID merges.
19. Stop writers during sequence resync.
20. Verify nextval does not generate duplicate IDs.
21. Inventory large objects and OID references.
22. Use --blobs when workflows need large objects included.
23. Avoid --no-blobs if applications require LO content.
24. Verify selective dumps retain LO entries.
25. Check LO owners and ACLs after restore.
26. Check orphan LOs per the application reference model.
27. Restore in proper dependency order.
28. Restore globals/roles/tablespaces before databases when required.
29. Use psql for plain dumps and pg_restore for archives.
30. Verify DDL, data, sequences, LOs, and application behavior after restore.
31. Manage cross-database consistency if using pg_dumpall.
32. Plan delta/cutover strategies for migrations with ongoing writes.
33. Keep source/rollback plans during the migration window.
34. Mark a backup usable only after passing restore drills.

## 41. Summary

Logical backups use pg_dump/pg_dumpall to store database objects and data as SQL/archives. This approach is flexible for migrations, selective restores, and major-version upgrades, yet several components are not automatically included in a single database dump: roles, tablespaces, server configurations, extension binaries, remote data, external files, and replication runtime state.

DDL must be restored in dependency order. A full-database dump lets PostgreSQL archives manage most object ordering, whereas selective schema/table dumps can omit type, function, sequence, trigger, extension, or foreign-key dependencies. Inspect the TOC and test-restore before using artifacts for migration.

Sequences require care because nextval/setval lack transactional rollback behavior like table rows and sequence state does not follow MVCC snapshots. After partial imports or ID merges, pause writers, locate the right sequences, and synchronize state in a controlled way. Large objects also need dedicated checks: a table containing OID references does not mean LO content was dumped. Use --blobs when needed, inspect the TOC, and verify ownership, ACLs, and content readability after restore.

A logical backup is only valuable when the target has all required DDL dependencies, roles, extensions, sequences, large objects, and external configurations. Inventory before backing up, protect artifacts, run test restores in isolated environments, verify business invariants, and measure recovery times. For migrations with ongoing writes, design delta synchronization and cutover plans; pg_dump alone does not capture changes committed after its snapshot.
