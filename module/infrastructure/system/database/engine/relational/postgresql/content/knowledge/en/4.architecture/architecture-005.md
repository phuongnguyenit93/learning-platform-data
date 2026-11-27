# Database Cluster, PGDATA, Tablespaces, and Relation Files in PostgreSQL

## 1. From an SQL Table to Files on Disk

When you run the statement:

```sql
CREATE TABLE public.orders (
    order_id bigint PRIMARY KEY,
    amount numeric(12, 2) NOT NULL
);
```

PostgreSQL creates a **logical object** named `public.orders`. However, the table's data does not live in an "`orders.sql` file" or a folder named `public`. PostgreSQL uses a **database cluster**, a **`PGDATA` data directory**, **tablespaces**, **relation files**, and multiple internal files to store data and recover from crashes.

Picture two perspectives of the same system.

**Logical SQL perspective:**

```text
PostgreSQL instance
└── Database cluster
    ├── Database: postgres
    ├── Database: shop_db
    │   ├── Schema: public
    │   │   └── Table: orders
    │   │       ├── Row: order_id = 1001
    │   │       └── Row: order_id = 1002
    │   └── Schema: audit
    │       └── Table: events
    └── Database: analytics_db
        └── Schema: reporting
            └── Table: daily_sales
```

**Typical physical perspective with the default tablespace:**

```text
PGDATA/
├── PG_VERSION
├── base/
│   ├── <OID of shop_db>/
│   │   ├── <relfilenode of orders table>
│   │   ├── <relfilenode of index>
│   │   ├── <relfilenode>_fsm
│   │   └── ...
│   └── <OID of analytics_db>/
├── global/
├── pg_tblspc/
├── pg_wal/
├── pg_xact/
├── pg_multixact/
└── ... other administrative files and directories
```

Placeholders such as `<OID of shop_db>` and `<relfilenode>` in the diagram are **descriptive labels**, not literal filenames. On disk, PostgreSQL uses numeric identifiers and an internal directory layout. Never manually edit or rename these files.

This lesson answers five questions:

1. What is a **database cluster**, and how does it differ from a multi-machine PostgreSQL cluster?
2. What does **`PGDATA`** contain, and why does it matter?
3. How do **tablespaces** determine where objects are stored?
4. How do **relation files** represent tables, indexes, TOAST, and forks/segments?
5. How can you inspect storage architecture using **safe SQL**, without touching internal files?

## 2. Database Cluster: A Collection of Databases Managed Together

### 2.1. Technical meaning of "database cluster"

In PostgreSQL terminology, a **database cluster** is **the collection of databases managed by a single PostgreSQL server instance**. A cluster encompasses the databases' data, shared system catalogs, and internal state required for the server to operate.

Example:

```text
One PostgreSQL database cluster
├── Role: application_login
├── Role: readonly_user
├── Tablespace: pg_default
├── Tablespace: pg_global
├── Database: postgres
├── Database: shop_db
└── Database: reporting_db
```

Key points to remember:

- One cluster contains **multiple databases**.
- Each database contains **multiple schemas** and objects.
- **Roles** and tablespace definitions are **cluster-wide** concepts, not scoped to a single schema.
- A PostgreSQL server instance opens and manages **one data directory/cluster** to serve connections.
- A single physical machine or VM can run **multiple independent PostgreSQL instances**, provided each has its own data directory and resource configuration.

A cluster is **initialized** with the `initdb` system utility, not with `CREATE DATABASE`.

```sh
# Illustrative command to initialize a NEW cluster in a test environment.
# Run only if the path contains no data yet and with appropriate permissions.
initdb -D /path/to/new/pgdata
```

This command creates the initial structure of a data directory. It is not something you repeat every time an application needs another database.

By contrast:

```sql
CREATE DATABASE shop_db;
```

creates **one database inside the existing cluster**. It does not initialize a new database cluster or server instance.

### 2.2. A database cluster does not mean an HA cluster

The phrase "PostgreSQL cluster" is commonly used in two different senses:

| Term | Nature | Requires multiple machines? |
|---|---|---|
| **Database cluster per `initdb`** | Set of databases and data managed by one PostgreSQL instance | **No** |
| **HA cluster / primary–standby topology** | Multiple PostgreSQL instances cooperating for high availability | Usually multiple instances/nodes |
| **Replication setup** | Mechanism transmitting/applying changes across PostgreSQL instances | Multiple instances, without necessarily automatic failover |
| **Cluster orchestrator** | Management layer handling primary election, failover, fencing... | Depends on solution |

A laptop running PostgreSQL with just the `postgres` database still has a **database cluster** in technical terms. It does not automatically have failover or standby replicas.

In streaming replication, each standby has its **own separate data directory** and syncs changes through PostgreSQL replication; never point two running instances to write to the same `PGDATA`. Having a primary and standby with matching data **does not turn two data directories into one shared directory**.

### 2.3. Which objects belong to the cluster, and which belong to a database?

| Object | Primary scope |
|---|---|
| List of roles, role memberships | Cluster |
| List of databases | Cluster |
| List of tablespaces | Cluster |
| Schemas such as `public`, `sales` | One database |
| Tables such as `sales.orders` | One schema within one database |
| Indexes, sequences, views | Belong to their respective database and schema |
| Table rows | Specific table |
| Instance WAL | Storage/recovery mechanism for the entire instance, not a single table |

This boundary explains why one role can connect to multiple databases, yet a normal `SELECT` works only within **the database the session is currently connected to**.

## 3. What Is `PGDATA`?

### 3.1. `PGDATA` and `data_directory`

**`PGDATA`** commonly refers to PostgreSQL's **data directory**: the root directory holding the database cluster's data and system files needed for the instance to operate.

In some installations, `PGDATA` is an **environment variable** pointing to the data directory:

```sh
# Example environment variable on a self-managed system:
PGDATA=/var/lib/postgresql/data
```

This is an example path only. Not every OS, Linux distribution, or container image uses the same path, and an environment variable in your terminal **does not prove** the running server uses that directory.

PostgreSQL also has a `data_directory` configuration parameter and can accept a directory path at startup (e.g., via `-D`). Depending on packaging, configuration files may also live **outside the data directory**.

To check the actual data directory of **the connected server**, an administrator or appropriately privileged role can run:

```sql
SHOW data_directory;
```

Access to this parameter may be restricted for ordinary accounts; do not grant broad admin privileges just to see a filesystem path. In managed PostgreSQL services, users may **not even have access** to the underlying filesystem.

### 3.2. Why is PGDATA critical?

`PGDATA` is fundamental because it stores, or links to, the data and metadata PostgreSQL requires to:

- Identify the major version and cluster layout.
- Locate database data stored in the default tablespace.
- Access shared system catalogs.
- Persist transactions and perform crash recovery via WAL.
- Track transaction statuses, replication metadata, and other internal state.

**Never treat PGDATA like an application documents folder where individual files can be copied or deleted at will.** PostgreSQL maintains tight invariants across table data, catalogs, transaction status, WAL, and relation files. Modifying a single file while the server is running can corrupt data consistency.

### 3.3. Map of key directories inside PGDATA

The exact layout can vary by PostgreSQL version, configuration, and packaging. Common entries include:

| Path inside PGDATA | Role |
|---|---|
| `PG_VERSION` | Records the major version number of the cluster layout |
| `base/` | Data for databases stored in the **default tablespace** `pg_default` |
| `global/` | Shared system catalogs and cluster-wide shared data |
| `pg_tblspc/` | Links from the cluster to locations of **user-created tablespaces** |
| `pg_wal/` | Write-Ahead Log for durability, crash recovery, replication, and PITR |
| `pg_xact/` | Commit/abort status records for transactions |
| `pg_multixact/` | Status data for multi-transaction IDs supporting concurrent row locking |
| `pg_subtrans/` | Metadata about subtransactions |
| `pg_twophase/` | State for prepared transactions / two-phase commit when used |
| `pg_replslot/` | Replication slot state |
| `pg_logical/` | Metadata related to logical decoding and replication |
| `pg_stat/` | Persistent statistics data per version mechanisms |
| `postgresql.auto.conf` | Configuration settings persisted via mechanisms like `ALTER SYSTEM` |
| `postmaster.pid` | Lock/control info for the running instance, present while active |

**Do not treat this table as a checklist required across every PostgreSQL version.** PostgreSQL adds, renames, or reorganizes internal directories across releases, and packaging choices affect where configs, logs, and data reside.

For example, Linux distro packages often place `postgresql.conf` and `pg_hba.conf` in a separate config directory rather than inside `PGDATA`. Always verify via the running instance's settings and packaging conventions.

### 3.4. How do `base/` and `global/` differ?

**`base/`** holds subdirectories named by **database OID** for databases using the default tablespace.

Illustrative layout:

```text
PGDATA/base/
├── 1/
├── 4/
├── 5/
└── 16384/
    ├── 16390
    ├── 16391
    ├── 16391_fsm
    └── 16391_vm
```

These numbers are examples only. `16384` in the path is a database OID; the numeric filenames inside are **relation file identifiers**, not row IDs from a table.

**`global/`** stores cluster-wide shared relations and catalogs, such as database and role metadata per PostgreSQL's storage design. That does not mean every system catalog lives in `global/`; many system catalogs are per-database and reside inside each database's storage directory.

## 4. Database OID: The Bridge Between Database Name and Storage Directory

### 4.1. What is an OID?

PostgreSQL assigns an **Object Identifier (OID)** to many internal objects. Every database has an **OID** recorded in `pg_database`.

Safe inspection query:

```sql
SELECT
    oid AS database_oid,
    datname AS database_name,
    pg_get_userbyid(datdba) AS owner_name
FROM pg_database
ORDER BY datname;
```

If `shop_db` has OID `16384` and uses tablespace `pg_default`, its relation files typically live under the relative path:

```text
base/16384/
```

Never guess an OID from a database name, and never assume an example OID stays identical across machines.

### 4.2. Checking the OID of the connected database

```sql
SELECT
    current_database() AS database_name,
    d.oid AS database_oid
FROM pg_database AS d
WHERE d.datname = current_database();
```

This connects **logical** SQL info to the database's directory inside the default tablespace.

However, not every relation in that database lives under `base/<database_oid>`: if a table or index is placed in a **custom tablespace**, its files may live outside `PGDATA`, referenced via `pg_tblspc`.

### 4.3. Database name vs. schema name vs. file name

Suppose:

```text
Database: shop_db
Schema: sales
Table: orders
```

From SQL's perspective inside the connected database, the qualified table name is:

```sql
SELECT * FROM sales.orders;
```

On the filesystem, however, there is no path like:

```text
PGDATA/shop_db/sales/orders.csv
```

Instead, PostgreSQL resolves files via database OID, tablespace, and **relfilenode**. A schema is a logical namespace managed in system catalogs; it does not map to a physical directory of the same name.

## 5. Tablespaces: Choosing Physical Storage Locations for Objects

### 5.1. What is a tablespace?

A **tablespace** lets PostgreSQL place relation objects at a specific **managed storage location**. It is not a new database, not a new schema, and not a separate PostgreSQL server.

Example:

```text
PostgreSQL instance / PGDATA
├── pg_default  -> PGDATA/base/
├── pg_global   -> PGDATA/global/
└── admin-created tablespace
    └── fast_ts -> /srv/postgres/tablespaces/fast_ts/
```

Paths shown here are illustrative only. The two default tablespaces are:

- **`pg_default`**: where user objects are stored unless another tablespace is chosen, corresponding to `base/`.
- **`pg_global`**: used for cluster-wide shared storage objects, corresponding to `global/`.

An administrator-created tablespace can reside on a different disk/volume to meet capacity, operational, or performance requirements in self-managed environments.

### 5.2. Listing tablespaces with SQL

```sql
SELECT
    oid AS tablespace_oid,
    spcname AS tablespace_name,
    pg_get_userbyid(spcowner) AS owner_name
FROM pg_tablespace
ORDER BY spcname;
```

In `psql`, you can also use the meta-command:

```text
\db
```

`\db` is specific to `psql`; it is not an SQL command sent through a JDBC driver.

To inspect the default tablespace of the **current database**:

```sql
SELECT
    d.datname AS database_name,
    t.spcname AS default_tablespace
FROM pg_database AS d
JOIN pg_tablespace AS t
  ON t.oid = d.dattablespace
WHERE d.datname = current_database();
```

For an uncustomized database, `default_tablespace` is `pg_default`.

### 5.3. Actual location of a custom tablespace

On self-managed PostgreSQL using a POSIX filesystem, creating a tablespace outside `PGDATA` typically creates a **symbolic link** inside `PGDATA/pg_tblspc/` pointing to that external location.

Diagram:

```text
PGDATA/
└── pg_tblspc/
    └── 24576   -> /srv/postgres/tablespaces/fast_ts

/srv/postgres/tablespaces/fast_ts/
└── PG_<version>_<catalog_version>/
    └── <database_oid>/
        ├── <relfilenode>
        ├── <relfilenode>_fsm
        └── ...
```

On Windows, filesystem links/junctions differ in OS implementation. The `PG_<version>_<catalog_version>` component is an internal version-specific directory format, not a fixed directory name to hard-code in applications.

You can query tablespace paths using:

```sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace
ORDER BY spcname;
```

For built-in tablespaces like `pg_default` or `pg_global`, the location field returns an empty string per how the function represents internal locations; that does not mean those tablespaces hold no data.

### 5.4. Creating a tablespace requires admin privileges and a valid directory

Example **intended only for administrators on a self-managed test instance**:

```sql
CREATE TABLESPACE fast_ts
LOCATION '/srv/postgres/tablespaces/fast_ts';
```

To be valid, in principle:

1. The path on the PostgreSQL server host must already exist.
2. The directory must meet PostgreSQL's emptiness, ownership, and permission requirements; it is normally created at the OS level and owned by the OS user running PostgreSQL.
3. The role executing `CREATE TABLESPACE` normally requires **superuser** privileges.
4. The tablespace must sit on storage with suitable durability, permissions, and backup coverage.
5. `CREATE TABLESPACE` must obey PostgreSQL transaction rules and cannot run inside `BEGIN ... COMMIT`.

**Never run this snippet in production or copy paths blindly without administrator approval.** In managed PostgreSQL services, custom tablespace creation may be disabled entirely.

You can grant permission to create objects in a tablespace to another role if required by design:

```sql
-- Example after fast_ts already exists; run by a role with GRANT privileges.
GRANT CREATE ON TABLESPACE fast_ts TO app_owner;
```

This allows placing objects in the tablespace within granted bounds, **without granting superuser** to `app_owner`. The role still needs schema/database privileges to create relations.

### 5.5. Choosing a tablespace when creating a table or index

Assuming `fast_ts` was prepared by an admin in a lab and the role has sufficient privileges:

```sql
CREATE TABLE storage_lab.archive_events (
    event_id bigint PRIMARY KEY,
    payload text NOT NULL
) TABLESPACE fast_ts;
```

`archive_events` still lives in **schema `storage_lab` of the current database**; only its physical storage location is overridden via the tablespace. You do not switch databases to query it:

```sql
SELECT *
FROM storage_lab.archive_events;
```

Indexes can specify their own tablespace:

```sql
CREATE INDEX idx_archive_events_payload_prefix
ON storage_lab.archive_events ((left(payload, 20)))
TABLESPACE fast_ts;
```

This demonstrates setting storage placement. **Do not create an index on `left(payload, 20)` just to practice tablespaces and keep it in an application** if no query needs it.

### 5.6. A tablespace is not a data authorization mechanism

A table in `fast_ts` is still governed by `SELECT/INSERT/UPDATE/DELETE` privileges, ownership, and security policies identically to tables in `pg_default`. Placing it on a separate disk **does not encrypt data**, enforce tenant security isolation, or isolate transactions.

Tablespaces also do not automatically make queries faster. Performance depends on underlying storage hardware, workload, indexes, caching, latency, concurrency, and placement of WAL/indexes/data. If multiple tablespaces sit on the exact same physical device, I/O separation benefits are minimal.

## 6. Relation: The Concept Between an SQL Table and Physical Files

### 6.1. "Relation" does not mean "one file = one table"

PostgreSQL uses the term **relation** for many catalog-managed objects, including:

- Ordinary tables.
- Indexes.
- Materialized views.
- Sequences and certain other physical objects.
- Partitioned tables and partitioned indexes as logical parent objects.
- Views and foreign tables at the metadata level, even without local heap storage like ordinary tables.

In `pg_class`, relations use `relkind` to distinguish object types. One ordinary table can have:

- **One heap relation** holding row data.
- **One or more index relations** holding index structures.
- **One TOAST relation** and its index if oversized values require out-of-line storage.
- Associated **forks** and **segments** belonging to those relations.

Thus, creating a single table with a primary key and a couple of indexes typically produces **multiple physical files**, not a single file named after the table.

### 6.2. Relation OID and `relfilenode`

Every relation has a catalog identity represented by its **OID**. When a relation has physical storage, PostgreSQL also tracks a **filenode**: a number identifying the physical storage files for that relation.

These two identifiers serve different roles:

| Attribute | Role |
|---|---|
| Relation OID | Catalog identity of the object |
| `relfilenode` / file node | Physical storage file identifier where applicable |
| Database OID | Identifies the database, usually reflected in a directory level |
| Tablespace OID | Identifies the storage area / tablespace |
| Schema name | Logical namespace, not a literal physical directory |
| Table name | Logical name, not a literal filename |

A relation can **keep its logical OID** while receiving a **new filenode** after a table-rewriting operation such as `VACUUM FULL`, `CLUSTER`, or certain structural alterations. Therefore, never store `relfilenode` in application config as a permanent table identifier.

Some shared/core system catalogs also use **relation mapping** rather than storing a regular filenode directly in `pg_class.relfilenode`. To find actual storage paths, **PostgreSQL's built-in helper functions** are far more reliable than stitching catalog numbers together manually.

### 6.3. Inspecting relations with SQL

After creating `storage_lab.orders` in the practice section, you can run:

```sql
SELECT
    c.oid AS relation_oid,
    c.relname,
    c.relkind,
    c.relfilenode,
    c.reltablespace
FROM pg_class AS c
WHERE c.oid = 'storage_lab.orders'::regclass;
```

For ordinary tables, `relfilenode` is normally non-zero. When `reltablespace = 0`, it indicates the relation uses **the database's default tablespace**, not a tablespace named "0".

Functions to locate a relation's path:

```sql
SELECT
    pg_relation_filenode('storage_lab.orders'::regclass)
        AS physical_filenode,
    pg_relation_filepath('storage_lab.orders'::regclass)
        AS relative_relation_path;
```

The path returned by `pg_relation_filepath()` is **relative to the data directory** in PostgreSQL's storage representation. For example:

```text
base/16384/16410
```

For relations in a custom tablespace, paths typically start with `pg_tblspc/...`. This information is for observation and diagnostics—**never an invitation to open that file in a text editor**.

### 6.4. Not every relation has local files

An ordinary **view** stores a query definition rather than a heap of result rows. A **foreign table** accesses external data through a foreign data wrapper without standard local heap storage. A **partitioned table parent** defines partitioning metadata and normally has no heap storage of its own; each leaf partition holds its own physical storage.

Hence `pg_relation_filepath()` can return `NULL` for objects lacking physical storage. Do not assume filesystem corruption simply because it returns `NULL` for a view or partitioned parent.

## 7. Relation Filenames: Main Fork, FSM, VM, and Init Fork

### 7.1. Main fork: the primary data file

An ordinary table has a **main fork** storing the table's heap pages. If its filenode is `16410`, you may see:

```text
16410
```

That is the first segment of the main fork. This number is an example, not a permanent filename.

Indexes also have their own main forks. If `orders` has a primary key and an index on status, separate relation files exist for:

```text
Heap of orders        -> relfilenode A
Primary key index     -> relfilenode B
Status/date index     -> relfilenode C
```

These files may live in the same or different tablespaces depending on configuration. Querying a table may read both index and heap files, or satisfy the query from the index alone in certain plans.

### 7.2. Free Space Map (FSM)

The **FSM fork** tracks where pages have available free space for inserting or updating tuples.

Example filename:

```text
16410_fsm
```

Purpose:

- Helps PostgreSQL locate pages with enough room when inserting or updating rows.
- FSM is space-management metadata, **not a substitute table file holding business rows**.
- Whether an FSM file exists and its size depend on relation activity; a brand-new relation might not immediately have a non-zero FSM file.

### 7.3. Visibility Map (VM)

The **VM fork** tracks page-level visibility flags such as **all-visible** and **all-frozen**, enabling key optimizations:

- **Index-only scans** can skip heap visibility checks when pages are marked all-visible.
- **VACUUM** uses the visibility map to skip pages that need no cleanup.
- All-frozen bits help optimize transaction ID wraparound maintenance and vacuuming.

Example file:

```text
16410_vm
```

VM does not store pre-computed `SELECT` results. It is metadata tracking MVCC tuple visibility. All-visible bits are cleared whenever a page is modified; they are not permanent properties of data.

### 7.4. Initialization fork for unlogged relations

**Unlogged relations** can have an **init fork**, indicated by the suffix:

```text
16410_init
```

This fork enables PostgreSQL to reset the unlogged relation to an empty initial state during crash recovery.

Do not assume every table has `_init`. Normal **logged** tables do not use an init fork in this way.

An **`UNLOGGED` table** skips WAL logging for data modifications to reduce write overhead, at a major trade-off: its data lacks standard crash durability and is not replicated as normal table data over physical WAL streaming replication. Never choose `UNLOGGED` just for "faster reads/writes" while ignoring durability requirements.

### 7.5. Fork summary

| Fork | Filename suffix | Role |
|---|---|---|
| **Main** | No suffix | Primary heap or index data pages |
| **FSM** | `_fsm` | Tracks free space per page |
| **VM** | `_vm` | All-visible / all-frozen metadata for vacuum and index-only scans |
| **Init** | `_init` | Reinitializes unlogged relations during recovery |

Not every relation type uses all four forks. Presence of files depends on object type and activity.

## 8. Relation Segments: Why Does a Large Table Have Multiple Files?

PostgreSQL splits a relation's storage into **segments**. In standard builds, each segment has a maximum size of about **1 GiB**. This limit can differ if PostgreSQL was compiled with custom build options.

Example main fork of a large relation:

```text
16410          -- first segment
16410.1        -- next segment
16410.2        -- subsequent segment
```

Secondary forks can also split into segments with appropriate suffixes, for example:

```text
16410_fsm
16410_fsm.1
16410_vm
```

Avoid these misconceptions:

- `16410.1` is a **new table**.
- `16410.1` is **row 1** of the table.
- The filename number equals a primary key value.
- A table always maps to exactly one file on disk.

All segments of a given fork are pieces of **one relation's storage**.

### 8.1. Pages/blocks are the unit inside a file

PostgreSQL divides relation files into **pages**, also called **blocks**. The standard default page size is **8 KiB**, though that is a compile-time build setting rather than a universal constant across custom builds.

Diagram:

```text
Relation main fork
├── Segment 0: 16410
│   ├── Page 0
│   ├── Page 1
│   ├── Page 2
│   └── ...
├── Segment 1: 16410.1
│   ├── Page ...
│   └── ...
└── Segment 2: 16410.2
    └── ...
```

Inside a heap page sit a page header, line pointers / item identifiers, tuple data, and free space. PostgreSQL manages pages in binary engine structures; applications should never assume they can read a page directly as plain text or CSV.

### 8.2. A row is not a file

At the SQL layer, a **row** is a logical record. At the storage layer, PostgreSQL stores **tuple versions** in heap pages under **MVCC**.

Example:

```sql
UPDATE storage_lab.orders
SET status = 'PAID'
WHERE order_no = 'ARCH58-001';
```

After an `UPDATE`, PostgreSQL creates a new tuple version while retaining the older version temporarily for active transactions reading earlier snapshots. One logical row can therefore correspond to multiple physical tuple versions concurrently.

Consequently:

- Counting files in a directory **never** tells you the row count.
- Relation size **never** equals just the sum of current column byte lengths.
- Tuple versions, page headers, free space, indexes, and TOAST all contribute to storage size.
- `ctid` represents the physical location of a tuple version; it is **not** a stable primary key for applications.

## 9. TOAST: How Are Large Values Stored?

### 9.1. Why is TOAST needed?

A row may contain `text`, `jsonb`, or other values larger than comfortably fit inside an 8 KiB heap page. PostgreSQL uses **TOAST** (*The Oversized-Attribute Storage Technique*) to compress and/or move oversized attribute values out-of-line when needed and supported by the data type and column storage strategy.

Example table:

```sql
CREATE TABLE storage_lab.documents (
    document_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    body text NOT NULL
);
```

When `body` is long, PostgreSQL can:

1. Store the value inline inside the heap tuple if small enough.
2. Compress the value using a supported compression algorithm/setting.
3. Store oversized chunks in the relation's **TOAST table** and keep a compact TOAST pointer in the main heap tuple.

TOAST does not trigger for every `text` value; short strings remain inline in the heap. Long strings that compress well may also behave differently from incompressible strings.

### 9.2. TOAST tables also have relation files

An ordinary table can link to a **TOAST relation** inside the `pg_toast` system schema, and that TOAST relation has its own index to look up chunks.

Diagram:

```text
storage_lab.documents
    ├── Heap relation
    │      └── body may hold inline data or reference
    ├── Index relation (PRIMARY KEY)
    └── TOAST relation if needed
           ├── TOAST heap
           └── TOAST index
```

You can inspect TOAST linkage in the catalog:

```sql
SELECT
    c.oid::regclass AS table_name,
    c.reltoastrelid,
    CASE
        WHEN c.reltoastrelid <> 0
        THEN c.reltoastrelid::regclass::text
        ELSE NULL
    END AS toast_relation
FROM pg_class AS c
WHERE c.oid = 'storage_lab.documents'::regclass;
```

A non-zero `reltoastrelid` shows the table has an associated TOAST relation. It **does not prove** the table currently contains out-of-line TOASTed values; PostgreSQL creates the TOAST table infrastructure up front whenever a table has toastable columns.

**Never read or modify TOAST files directly** to alter `text` content. Standard `INSERT`, `UPDATE`, and `SELECT` statements let PostgreSQL handle TOAST transparently.

### 9.3. Why can table size exceed main heap size?

If a table holds large values, total storage includes:

- Heap main fork.
- Secondary heap forks (FSM, VM).
- TOAST heap and its forks.
- TOAST index.
- Regular table indexes, when measuring total relation footprint.

This explains the differences between `pg_relation_size`, `pg_table_size`, and `pg_total_relation_size` covered below.

## 10. WAL and the Role of `pg_wal/` in Architecture

### 10.1. WAL differs from relation files

**WAL (Write-Ahead Logging)** is PostgreSQL's mechanism for recovering transactions and data modifications after a crash. When modifying pages, PostgreSQL writes WAL records according to write-ahead rules before modified dirty data pages can safely be written out to storage.

Put simply:

```text
Transaction modifies data
     |
     +--> WAL records -> pg_wal / WAL storage
     |
     +--> Heap/index pages updated in buffer
                          |
                          v
                    Dirty pages written to data files
```

WAL is **not** a per-table file. It serves all relations and all databases across the entire instance.

On some deployments, WAL can be placed on a dedicated volume through configuration; `PGDATA/pg_wal` remains logically part of the cluster layout even when mapped to a separate physical mount.

### 10.2. What does WAL enable?

- **Crash recovery:** replays WAL records to restore consistency when restarting after an unclean shutdown.
- **Physical streaming replication:** streams WAL to standbys to replay data-page changes.
- **Point-in-time recovery (PITR):** combines a consistent base backup with archived WAL segments to restore to a chosen timestamp.
- **Logical decoding / replication:** extracts logical changes from WAL when configured.

Crucial rule: **WAL alone does not replace a base backup**. Without a valid starting base backup or if required WAL segments are missing, recovery cannot complete. Keeping only a copy of `pg_wal` cannot rebuild a database.

### 10.3. Do not treat pg_wal as user file storage

Never place application files inside `PGDATA/pg_wal`, never manually delete WAL segments to "free disk space," and never edit WAL metadata with a text editor. If WAL storage grows unexpectedly, diagnose the cause—such as inactive replication slots, failing `archive_command`, long transactions, or retention settings—and resolve it with proper PostgreSQL administrative commands.

A dangerous command often misunderstood is resetting WAL to force startup. Low-level WAL reset utilities are strictly a last resort for administrators who understand the consequences and hold backups; they are **not** routine application maintenance.

## 11. Practice: Creating a Schema, Table, and Inspecting Relation Paths via SQL

This section runs inside a **dedicated lab database** without requiring filesystem access. You need `CREATE` privileges on the lab database/schema; superuser is not needed for basic inspection queries.

### Step 1. Identify the current database

In `psql` or another SQL client:

```sql
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    current_schema() AS active_schema;
```

In `psql`, you can also run:

```text
\conninfo
```

Verify you are connected to your **lab database**, never production.

### Step 2. Create a schema

```sql
CREATE SCHEMA IF NOT EXISTS storage_lab;
```

This schema is purely a namespace inside the current database; it does not create a physical `storage_lab` folder under `PGDATA`.

### Step 3. Create a table and index

```sql
CREATE TABLE storage_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_no text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'NEW',
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT orders_status_check
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE INDEX idx_orders_status_created
ON storage_lab.orders (status, created_at);
```

This table has one heap relation plus indexes:

- Primary key index for `order_id`.
- Unique index backing the `order_no` constraint.
- Index `idx_orders_status_created` supporting status/time queries.

That creates multiple **physical storage relations** even though you created **one table** in the schema.

### Step 4. Insert sample rows

```sql
INSERT INTO storage_lab.orders
    (order_no, status, amount, note)
VALUES
    ('ARCH58-001', 'NEW', 125000.00, 'Test order A'),
    ('ARCH58-002', 'PAID', 89000.00, 'Test order B'),
    ('ARCH58-003', 'NEW', 175000.00, 'Test order C')
RETURNING order_id, order_no, status, amount;
```

Verify:

```sql
SELECT order_id, order_no, status, amount, created_at
FROM storage_lab.orders
ORDER BY order_id;
```

If you need to re-run the exercise from scratch, use a **fresh lab database/schema** or a controlled reset script. Never run `DROP SCHEMA ... CASCADE` on a schema holding data whose ownership and dependencies you haven't verified.

### Step 5. Inspect database OID and default tablespace

```sql
SELECT
    d.oid AS database_oid,
    d.datname AS database_name,
    t.spcname AS default_tablespace
FROM pg_database AS d
JOIN pg_tablespace AS t ON t.oid = d.dattablespace
WHERE d.datname = current_database();
```

The output reveals your database's OID and default tablespace.

### Step 6. Inspect OID, filenode, and filepath of the table

```sql
SELECT
    'storage_lab.orders'::regclass AS relation_name,
    pg_relation_filenode('storage_lab.orders'::regclass)
        AS relation_filenode,
    pg_relation_filepath('storage_lab.orders'::regclass)
        AS relative_path;
```

Example **illustrative output only**:

```text
relation_name       | relation_filenode | relative_path
--------------------+-------------------+------------------
storage_lab.orders  | 16410             | base/16384/16410
```

Actual numbers are assigned dynamically by your running PostgreSQL instance. To check an index:

```sql
SELECT
    pg_relation_filenode('storage_lab.idx_orders_status_created'::regclass)
        AS index_filenode,
    pg_relation_filepath('storage_lab.idx_orders_status_created'::regclass)
        AS index_path;
```

The index has its own file, and the path shows where PostgreSQL stores that relation. There is no path mirroring SQL names like `storage_lab/orders/rows`.

### Step 7. Inspect the catalog for all relations in the schema

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind,
    c.oid AS relation_oid,
    c.relfilenode,
    c.reltablespace,
    pg_relation_filepath(c.oid) AS relative_path
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'storage_lab'
ORDER BY c.relkind, c.relname;
```

Common `relkind` values:

| `relkind` | Relation type |
|---|---|
| `r` | Ordinary table |
| `i` | Ordinary index |
| `S` | Sequence |
| `v` | View (no ordinary row heap) |
| `m` | Materialized view (physically stored results) |
| `p` | Partitioned table parent |
| `I` | Partitioned index parent |

An identity column creates an associated sequence appearing in the catalog. The sequence's existence does not mean every row is a file; the sequence is a generator object tracking counter state.

### Step 8. Inspect storage sizes

```sql
SELECT
    pg_relation_size('storage_lab.orders'::regclass)
        AS heap_main_bytes,
    pg_table_size('storage_lab.orders'::regclass)
        AS table_with_toast_bytes,
    pg_indexes_size('storage_lab.orders'::regclass)
        AS indexes_bytes,
    pg_total_relation_size('storage_lab.orders'::regclass)
        AS total_bytes;
```

These columns measure distinct scopes, not four ways of computing the same number. Each function is explained in the next section.

For human-readable formatting:

```sql
SELECT
    pg_size_pretty(
        pg_total_relation_size('storage_lab.orders'::regclass)
    ) AS total_pretty_size;
```

### Step 9. Try an UPDATE and re-check sizes

```sql
UPDATE storage_lab.orders
SET status = 'PAID'
WHERE order_no = 'ARCH58-001'
RETURNING order_no, status;

SELECT
    pg_relation_size('storage_lab.orders'::regclass) AS main_bytes,
    pg_total_relation_size('storage_lab.orders'::regclass) AS total_bytes;
```

Do not expect every tiny `UPDATE` to increase byte counts by a fixed amount immediately. PostgreSQL reuses existing free space in pages, and sizes grow in page increments. One logical change does not create a new file.

**Note:** these SQL commands create and modify objects inside the lab database without touching the server filesystem directly. Do not use `COPY ... TO '/server/path'` or privileged file operations in this exercise.

## 12. Distinguishing PostgreSQL Size Functions

### 12.1. `pg_relation_size()`: size of one relation or fork

```sql
SELECT
    pg_relation_size('storage_lab.orders'::regclass) AS main_bytes;
```

By default, it measures the **main fork** of the specified relation. It does **not** automatically include the table's indexes.

You can specify a fork explicitly:

```sql
SELECT
    pg_relation_size('storage_lab.orders'::regclass, 'main')
        AS main_bytes,
    pg_relation_size('storage_lab.orders'::regclass, 'fsm')
        AS fsm_bytes,
    pg_relation_size('storage_lab.orders'::regclass, 'vm')
        AS vm_bytes;
```

A fork without a file or data yet returns `0` under supported behavior. Never force FSM/VM creation solely to see files on disk.

### 12.2. `pg_table_size()`: table size excluding regular indexes

```sql
SELECT pg_table_size('storage_lab.orders'::regclass);
```

This measures **table storage**, including the heap, secondary forks, and TOAST table / TOAST index if present; it **excludes** the table's regular indexes.

Hence `pg_table_size` can exceed `pg_relation_size(table)`.

### 12.3. `pg_indexes_size()`: total size of a table's indexes

```sql
SELECT pg_indexes_size('storage_lab.orders'::regclass);
```

This reports total storage of all indexes attached to the table, including their forks and segments per PostgreSQL semantics.

A table with a primary key and several secondary indexes can easily spend more disk space on indexes than on the heap if keys are wide or numerous.

### 12.4. `pg_total_relation_size()`: total size of table plus related objects

```sql
SELECT pg_total_relation_size('storage_lab.orders'::regclass);
```

This reports the table's total footprint, combining table storage and attached indexes (including TOAST).

A helpful conceptual equation:

```text
Total relation size
    ≈ Table size (heap/forks/TOAST)
      + Indexes size (regular indexes)
```

The `≈` conveys general understanding; do not rely on it to deduce every file type across all relation kinds and versions without checking the exact function definitions.

### 12.5. `pg_database_size()` and `pg_tablespace_size()`

To check larger scopes:

```sql
SELECT
    current_database() AS database_name,
    pg_size_pretty(pg_database_size(current_database()))
        AS database_size;
```

And with appropriate privileges:

```sql
SELECT
    spcname,
    pg_size_pretty(pg_tablespace_size(oid)) AS tablespace_size
FROM pg_tablespace
ORDER BY spcname;
```

Viewing tablespace sizes may require specific permissions; if a query reports permission denied, ask an administrator rather than granting superuser to an application role.

Each function measures a **different scope**:

| Function | Scope |
|---|---|
| `pg_relation_size(relation)` | Main fork of one relation by default |
| `pg_relation_size(relation, 'fsm')` | FSM fork of that relation |
| `pg_table_size(table)` | Table storage including TOAST and forks, excluding regular table indexes |
| `pg_indexes_size(table)` | Regular indexes attached to the table |
| `pg_total_relation_size(table)` | Table plus its attached indexes |
| `pg_database_size(database)` | Total disk space used by a database |
| `pg_tablespace_size(tablespace)` | Total disk space used in a tablespace |

**Size differences alone do not prove corruption or bloat.** Results depend on free space inside pages, tuple versions, indexes, TOAST, forks, and relation characteristics.

## 13. MVCC, VACUUM, and Physical File Changes

### 13.1. An UPDATE can create a new tuple version

PostgreSQL implements **MVCC** to support concurrent reads and writes. Different transactions can see different versions of a row based on their snapshots and isolation levels.

Simplified diagram:

```text
Logical row: order_no = ARCH58-001
    |
    ├── Old version: status = NEW
    │      └── May still be needed for old snapshots
    └── New version: status = PAID
           └── Version visible after commit
```

Some updates qualify for the **HOT (Heap-Only Tuple)** optimization when indexed columns are untouched and the same heap page has free space. In our example updating `status`, because `status` is indexed, do not assume HOT applies.

Querying final column values in SQL does not show all tuple versions currently sitting in heap pages.

### 13.2. What does VACUUM do?

Once no active snapshot or transaction needs dead tuple versions, PostgreSQL reclaims their space for reuse via **VACUUM**. The **autovacuum** system automates most of this maintenance.

A table owner or appropriately privileged role can run in the lab:

```sql
VACUUM (ANALYZE) storage_lab.orders;
```

- `VACUUM` cleans up obsolete row versions and maintains visibility/wraparound metadata.
- `ANALYZE` updates planner statistics for better query plans.
- Ordinary `VACUUM` makes free space reusable **inside** existing files, rather than immediately shrinking files down to live-data size.

Never conclude `VACUUM` failed merely because file size on disk did not drop afterward.

### 13.3. `VACUUM FULL` and relation rewrites

`VACUUM FULL` compacts a table by **rewriting the relation** to reclaim physical disk space aggressively, at the cost of heavy I/O, extra temporary disk space during execution, and an **`ACCESS EXCLUSIVE`** lock blocking reads and writes.

Syntax example—**not recommended on live production tables serving traffic**:

```sql
VACUUM FULL storage_lab.orders;
```

During a rewrite, PostgreSQL assigns a **new `relfilenode`**. Thus `pg_relation_filepath()` can change even though the SQL name `storage_lab.orders` stays identical.

Operations like `CLUSTER`, `TRUNCATE`, or certain `REINDEX` commands can also replace storage files. **Filenames and `relfilenode`s are not a stable API for applications to bind business logic to.**

### 13.4. Inspecting dead tuple metrics

A query for estimated counts:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_all_tables
WHERE schemaname = 'storage_lab'
  AND relname = 'orders';
```

`n_live_tup` and `n_dead_tup` are **statistical estimates**, not exact real-time counters. In a tiny lab table with a few rows, values may not shift immediately. Investigating real bloat requires additional tools and workload context beyond a single column.

## 14. Moving a Table or Index to Another Tablespace

### 14.1. Moving alters physical file location

If an administrator has created tablespace `fast_ts` and the role has sufficient privileges, table storage can be moved:

```sql
ALTER TABLE storage_lab.orders
SET TABLESPACE fast_ts;
```

This is an **illustrative command with heavy physical impact**. It can copy/rewrite huge amounts of data while holding locks that block applications; **never run it in production without a migration plan and downtime/lock budget**.

Afterward, verify:

```sql
SELECT
    pg_relation_filepath('storage_lab.orders'::regclass)
        AS new_relative_path;
```

When the tablespace sits outside `PGDATA`, the path changes from:

```text
base/<database_oid>/<filenode>
```

to:

```text
pg_tblspc/<tablespace_oid>/PG_<version>_<catalog_version>/<database_oid>/<filenode>
```

### 14.2. Do indexes move automatically with the table?

**Never assume `ALTER TABLE ... SET TABLESPACE` moves all attached indexes.** PostgreSQL manages table storage and index storage locations independently; moving indexes requires explicit planning and commands.

Example syntax:

```sql
ALTER INDEX storage_lab.idx_orders_status_created
SET TABLESPACE fast_ts;
```

Other indexes such as the primary key or unique indexes must also be addressed if your goal is moving the entire storage footprint. Running commands one by one does not mean PostgreSQL moves all objects atomically without locks.

### 14.3. Why choose a custom tablespace?

Valid operational reasons include:

- The default volume is nearing capacity and objects must be distributed per policy.
- Very large tables or indexes need storage hardware with specific I/O characteristics.
- Filesystem/volume administrative requirements mandate placing data separately.
- Specific maintenance or physical storage workflows require clear volume separation.

However, tablespaces have strict limitations:

- They do not create read replicas.
- They do not create separate transaction boundaries.
- They do not replace replication, backups, or restore testing.
- They do not automatically encrypt data in ways applications can blindly rely on.
- They do not establish automatic role, schema, or security boundaries.
- They do not speed up queries if the underlying physical storage device is the same.

In managed PostgreSQL or abstracted cloud storage, custom tablespaces may not be supported; use your platform's official storage management features instead.

## 15. Relations That Do Not Behave Like Ordinary Tables

### 15.1. Views and materialized views

```sql
CREATE VIEW storage_lab.paid_orders AS
SELECT order_id, order_no, amount
FROM storage_lab.orders
WHERE status = 'PAID';
```

An **ordinary view** primarily stores a query definition. It does not maintain a separate heap pre-storing all current rows.

By contrast:

```sql
CREATE MATERIALIZED VIEW storage_lab.paid_orders_snapshot AS
SELECT order_id, order_no, amount
FROM storage_lab.orders
WHERE status = 'PAID';
```

A **materialized view** persists query results in physical relation storage; when source data changes, its contents **do not update automatically in real time**. You must run an appropriate refresh workflow when fresher results are required.

Thus, two objects can look identical to `SELECT` while managing relation files completely differently.

### 15.2. Partitioned tables

A partitioned parent table defines the partitioning scheme, while individual **partitions** store the actual rows.

Example:

```sql
CREATE TABLE storage_lab.logs (
    log_id bigint NOT NULL,
    created_at date NOT NULL,
    message text NOT NULL
) PARTITION BY RANGE (created_at);

CREATE TABLE storage_lab.logs_2026_11
PARTITION OF storage_lab.logs
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
```

When you run:

```sql
SELECT pg_relation_filepath('storage_lab.logs'::regclass);
```

the partitioned parent returns `NULL` because **it has no heap storage of its own**. Partition `storage_lab.logs_2026_11` holds the physical data and has a relation filepath.

Do not interpret "the parent has no file" as meaning data queried through the parent vanished. PostgreSQL routes reads and writes across the underlying partitions.

### 15.3. Temporary tables

Temporary tables have lifecycles bound to a session or transaction as configured; PostgreSQL manages temporary files and workspace using dedicated mechanisms, optionally guided by `temp_tablespaces`.

```sql
CREATE TEMP TABLE tmp_ids (
    id bigint
) ON COMMIT DROP;
```

Such a temporary table exists within the matching transaction/session scope and is dropped per `ON COMMIT DROP`. Never try to predict temporary filenames or use `pg_relation_filepath()` to share temp data across sessions.

### 15.4. Sequences and identity columns

The column:

```sql
order_id bigint GENERATED ALWAYS AS IDENTITY
```

uses a PostgreSQL-managed sequence. A sequence is a separate object with its own state; generated values **do not** correspond to physical row offsets in the table's main fork. Sequences can have gaps due to transaction rollbacks or insert errors and must never be used to count rows.

## 16. Protecting PGDATA and Tablespaces in Backup and Restore

### 16.1. Logical backup vs. physical backup

A **logical backup** such as `pg_dump` exports SQL-level definitions and data. Upon restore, PostgreSQL recreates tables and indexes with **new OIDs, relfilenodes, and physical paths**.

A **physical backup** such as `pg_basebackup` copies cluster files to produce a physically consistent snapshot per PostgreSQL mechanics. When a cluster uses custom tablespaces, physical backup/restore workflows must handle **all tablespace locations outside `PGDATA`**, not just `base/`.

Comparison:

| Criterion | Logical backup | Physical / base backup |
|---|---|---|
| Primary content unit | Schemas, tables, objects, and SQL-level data | Physical cluster files eligible for backup |
| Preserves relfilenodes? | Do not expect it | Captures physical files per backup procedure, with specific restore requirements |
| Restoring a single table | Usually more convenient | Not the primary goal of a raw physical restore |
| Role of WAL | Depends on strategy; logical dumps alone do not provide full PITR | Critical for physical consistency and PITR |
| Custom tablespaces | Handled via DDL/location mapping during restore | Must account for tablespace files and path mappings |
| Roles and global privileges | May require backing up global objects separately | Included in cluster state depending on backup method |

Never assume copying files from `PGDATA/base/<db_oid>` with OS commands while PostgreSQL is running produces a **consistent backup**. While the server writes data, pages, WAL, and metadata are out of sync unless you use a PostgreSQL-supported backup method.

### 16.2. WAL archiving and point-in-time recovery

To recover to an exact point in time after a base backup, the architecture generally requires:

1. A consistent base backup.
2. Archived/retained WAL covering the recovery window.
3. Appropriate recovery target settings.
4. A tested WAL replay and post-restore verification procedure.

**Replication does not replace backups**: an accidental `DROP TABLE` on the primary replays onto standbys. Independent backups give you a path back to before the mistake.

### 16.3. Protecting physical paths

Mandatory operational rules:

- Never open, edit, copy haphazardly, or delete relation files inside `PGDATA`.
- Never "move a tablespace" by moving files at the OS level while PostgreSQL is running.
- Never place PostgreSQL data directories or tablespaces on unverified filesystems that fail PostgreSQL's durability/semantics requirements.
- Preserve ownership and permissions for the OS user running PostgreSQL.
- Never manually delete WAL files when disk fills up.
- Maintain backups, restore drills, and free-disk monitoring across **every storage volume**: `PGDATA`, external tablespaces, and WAL volumes if separate.
- In containers, distinguish **ephemeral container filesystems**, mounted volumes, and host paths. Deleting containers or volumes carelessly can permanently destroy data.

Physical recovery should always prioritize **supported PostgreSQL tools** and a tested recovery plan.

## 17. Operational Errors Related to PGDATA and Relation Files

### 17.1. Server fails to start because PGDATA cannot be accessed

Symptoms typically point to a wrong path, filesystem permissions, or an uninitialized data directory.

Troubleshooting steps:

- Verify the exact instance, `PGDATA` path, and OS owner.
- Check PostgreSQL logs and service manager/container logs.
- Confirm volumes are mounted properly and paths did not shift unexpectedly.
- Never run `initdb` on an existing cluster directory to "fix" startup.

`initdb` is for **initializing a new cluster**, not repairing existing data.

### 17.2. `No space left on device`

PostgreSQL can exhaust space on:

- The `PGDATA` volume holding `base/`.
- The WAL volume.
- External tablespace volumes.
- Temporary file storage.

Identify **which volume** is full before taking action. If WAL grew, check archiving, replication slots, and retention; if a table grew huge, inspect tables, indexes, TOAST, and workload. Never free space by deleting arbitrary relation or WAL files.

### 17.3. `could not open file "base/...": No such file or directory`

This error demands serious investigation: it can stem from external file tampering outside PostgreSQL, mount/volume issues, I/O errors, or storage corruption.

Never create an empty dummy file matching the logged name just to "silence the error." Identify the relation in catalogs, assess instance state, review logs, and plan recovery from a consistent backup.

### 17.4. Missing tablespace path

If `pg_tblspc/<oid>` points to an unmounted volume or invalid path, relations in that tablespace become inaccessible even though their schemas and tables still appear in system catalogs.

Inspect storage mounts, permissions, and filesystem health; never repoint a symlink to an empty or unrelated directory.

### 17.5. Cannot find a table's file on disk

If:

```sql
SELECT pg_relation_filepath('storage_lab.orders'::regclass);
```

returns a different path than yesterday, that is not automatically an error. Rewrites, moves, or reindexes can change `relfilenode`, and tables can change tablespaces. Always query **catalogs and PostgreSQL functions at the moment of inspection**, never searching for an outdated filenode.

### 17.6. Why are there still files when a table is empty?

An empty table still exists in catalogs and can retain relation storage. Indexes, sequences, and forks may still exist depending on state. PostgreSQL does not map file count to row count. Even after deleting all rows with `DELETE`, allocated pages often remain available inside the relation for reuse.

### 17.7. Missing permissions to inspect PGDATA

Application roles typically lack privileges to view `data_directory` or read the server filesystem. That is a sound security boundary. Use permitted catalog/statistics functions, or ask an administrator/monitoring role with appropriate access. **Never grant superuser to an application just to read filenames.**

## 18. Key Misconceptions

**"One database equals one PostgreSQL instance."** No. One PostgreSQL database cluster can contain many databases, all served by one instance.

**"A PostgreSQL database cluster means at least two machines."** False. A cluster initialized by `initdb` is a collection of databases managed together, even on a single host.

**"`PGDATA` only holds individual table files."** No. It also holds WAL, transaction status, global catalogs, tablespace links, and internal metadata.

**"`base/` stores every table regardless of tablespace."** False. `base/` holds data for databases in the default tablespace; external tablespaces store files in their configured locations.

**"Schema `sales` maps to a `sales/` directory."** No. Schemas are logical namespaces stored in catalogs. File paths use database OID, tablespace, and filenode.

**"Filename `16410` is always the `orders` table."** No. Filenodes are assigned dynamically, change after rewrites, and are not identical across instances.

**"One table equals one file."** No. A table can have main/FSM/VM forks, multiple segments, TOAST relations, indexes, and auxiliary structures.

**"`16410.1` is row 1 of the table."** False. It is the next segment of a relation's main fork.

**"`pg_relation_size(table)` includes all indexes of the table."** False. It measures one relation/fork, defaulting to the main fork. Use `pg_table_size`, `pg_indexes_size`, or `pg_total_relation_size` for broader scopes.

**"Running `VACUUM` must shrink files immediately."** Not necessarily. Normal `VACUUM` frees space inside files for reuse; `VACUUM FULL` rewrites the relation to shrink physical files, with heavy locks and I/O.

**"A new tablespace automatically makes queries faster."** No. Speed depends on real storage hardware, workload, and I/O layout; placing two tablespaces on the same disk gives no hardware separation.

**"WAL alone is enough to restore all of PostgreSQL."** No. PITR requires a consistent base backup plus the full required WAL chain and a restore procedure.

**"A view having no filepath means data was lost."** No. Ordinary views have no local heap storing results; partitioned parents and other logical objects likewise lack separate heap files.

## 19. Self-Practice Exercises with Solutions

### Exercise 1. Distinguishing cluster and database

You run `initdb` once on a test machine, then create `sales_db` and `analytics_db`.

**Question:** how many database clusters and how many new user databases were created?

**Solution:** one database cluster was initialized by `initdb`; two new user databases were created inside that cluster (alongside built-in system databases). You do not create a second cluster just to add another database.

### Exercise 2. Interpreting a path from `pg_relation_filepath`

Suppose:

```text
current_database() = shop_db
OID of shop_db = 16384
pg_relation_filepath('sales.orders') = base/16384/16410
```

**Question:** what do `16384` and `16410` represent?

**Solution:** in this default-tablespace path, `16384` is the database OID, and `16410` is the relation's current filenode. Neither is a row count or an order primary key.

### Exercise 3. Why are there no schema directories?

You have `sales.orders` and `audit.events` in the same database, yet `PGDATA/base/<db_oid>` only shows numeric filenames.

**Solution:** `sales` and `audit` are logical schemas recorded in system catalogs; PostgreSQL stores relation files by numeric identifiers and tablespaces. Physical directories named after schemas are not used.

### Exercise 4. Distinguishing forks

Given these files:

```text
16410
16410_fsm
16410_vm
16410.1
```

**Question:** which holds the main fork, which tracks free space, which stores visibility metadata, and which is the next segment?

**Solution:**

- `16410`: main fork, first segment.
- `16410_fsm`: free space map.
- `16410_vm`: visibility map.
- `16410.1`: next segment of the main fork.

### Exercise 5. Main fork size vs. total size

Illustrative output:

```text
pg_relation_size(orders)       = 80 MB
pg_table_size(orders)          = 105 MB
pg_indexes_size(orders)        = 45 MB
pg_total_relation_size(orders) = 150 MB
```

**Question:** why are these four values different?

**Solution:** the main fork is only the primary heap; `pg_table_size` adds secondary forks and TOAST; indexes occupy their own space; `pg_total_relation_size` sums the table and its attached indexes. Total size exceeding main fork size is completely normal.

### Exercise 6. Why does `pg_relation_filepath` return `NULL`?

You call the function on a view or a partitioned table parent and receive `NULL`.

**Solution:** those objects do not own local heap storage like ordinary tables. Views store query definitions; partitioned parents route across partitions. Inspect the underlying relation that actually stores rows, such as leaf partitions or a materialized view, before looking for files.

### Exercise 7. Relation files changing after maintenance

You recorded a table's filenode as `16410`. After `VACUUM FULL`, the function returns a different filenode, yet `SELECT` still works.

**Solution:** PostgreSQL rewrote the relation and assigned a new filenode; the table's logical name and catalog OID persist. Never hard-code filenode numbers in application logic or backup scripts.

### Exercise 8. A tablespace is not a schema

A table is created as:

```sql
CREATE TABLE storage_lab.archive_events (
    event_id bigint PRIMARY KEY,
    payload text
) TABLESPACE fast_ts;
```

**Question:** is the table's qualified SQL name `fast_ts.archive_events`?

**Solution:** no. Its SQL name remains `storage_lab.archive_events` in the connected database. `fast_ts` is the tablespace controlling storage placement, not the schema containing the table.

### Exercise 9. Role of WAL

You hold a copy of `pg_wal` alone, with no base backup or data files.

**Question:** is that enough to restore all tables?

**Solution:** no. WAL replays changes against a matching baseline state; you need a consistent base backup along with the full WAL sequence and restore procedure. Never treat `pg_wal` alone as a backup.

### Exercise 10. A tablespace's disk fills up

Table `archive_events` resides in `fast_ts`, while the main `PGDATA` volume still has plenty of free space.

**Question:** can writes to that table still fail?

**Solution:** yes. Relation storage depends on the volume backing `fast_ts`; if that volume fills up or fails, writes to that table or its indexes can fail even while `PGDATA` has free space. Monitor every storage volume, not just the root `PGDATA` directory.

## 20. PostgreSQL Storage Architecture Quick Reference

| Term | Question to answer | Useful way to inspect |
|---|---|---|
| Database cluster | Which set of databases is managed by this instance? | `pg_database`, admin connection, instance configuration |
| PGDATA / data directory | Where does the cluster's foundational data live? | `SHOW data_directory` with appropriate privileges |
| Database OID | Which numeric ID maps to an SQL database? | `SELECT oid, datname FROM pg_database` |
| Tablespace | Which storage area holds a relation? | `pg_tablespace`, `pg_database.dattablespace` |
| Relation | Which table, index, or object is being inspected? | `pg_class`, `pg_namespace` |
| Filenode | What identifier names the current storage file? | `pg_relation_filenode()` |
| Relative filepath | Where does PostgreSQL currently locate the relation's file? | `pg_relation_filepath()` |
| Main fork | Where do the primary data pages live? | `pg_relation_size(relation)` |
| FSM | Free-space tracking per page | `pg_relation_size(relation, 'fsm')` |
| VM | Page all-visible / all-frozen metadata | `pg_relation_size(relation, 'vm')` |
| Segments | Why is a large relation split into numbered files? | Numeric suffixes like `.1`, per internal storage layout |
| TOAST | How are oversized values compressed or stored out-of-line? | `pg_class.reltoastrelid`, `pg_table_size()` |
| WAL | How are transactions recovered and changes streamed? | WAL config/monitoring, backup and replication workflows |
| Total size | How much space do a table and its indexes use? | `pg_total_relation_size()` |
| MVCC / VACUUM | Why do old tuple versions exist and get reclaimed? | `pg_stat_all_tables`, VACUUM/autovacuum |

**Core takeaway:** A **database cluster** is a PostgreSQL instance's managed dataset; **`PGDATA`** is its root data directory; **tablespaces** choose physical storage locations; and **relation files** store heaps, indexes, TOAST, and auxiliary structures across forks, segments, and pages. An SQL table is a **logical object**, not a permanent filename. Always use catalogs and PostgreSQL functions like `pg_relation_filepath()`, `pg_relation_size()`, and `pg_total_relation_size()` to inspect storage rather than touching physical files manually.
