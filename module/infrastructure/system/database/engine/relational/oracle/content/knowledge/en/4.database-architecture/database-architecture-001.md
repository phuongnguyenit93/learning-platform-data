# Distinguishing Physical Database, Instance, and Logical Objects

When working with Oracle Database, three concepts frequently appear together yet serve different roles:

- **Physical database** is the set of persistent files used to store data and the information required to recover and open the database.
- **Instance** is the active, running part of Oracle: memory areas and processes that handle queries, transactions, and data reads/writes.
- **Logical objects** are how Oracle organizes and presents data for users to operate on, such as *pluggable databases* (PDBs), schemas, tables, views, indexes, tablespaces, and segments.

For example, the statement `SELECT * FROM APP_ORDERS` references the **logical table** `APP_ORDERS`. The Oracle instance processes the statement and locates the required blocks in memory or in files. The records persist in a **datafile** even if the instance is shut down normally. Therefore, "the table", "the database on disk", and "the running database" are not the same entity.

## 1. Big Picture: How Do the Three Layers Work Together?

A common Oracle model can be visualized as follows:

```text
Application / SQL client (JDBC, SQLcl, SQL Developer)
                     |
               Host + Port + Service
                     |
             Listener / connection
                     |
        +------------v----------------+
        | ORACLE INSTANCE             |
        | - SGA (shared memory area)  |
        | - Background processes      |
        | - Server processes serving  |
        |   user sessions             |
        +------------+----------------+
                     | Read/write and manage
        +------------v----------------+
        | ORACLE DATABASE             |
        | - Datafiles                 |
        | - Control files             |
        | - Online redo log files     |
        +-----------------------------+

In a multitenant database (CDB):
  CDB$ROOT    : shared metadata and administration
  PDB$SEED    : template PDB used to create new PDBs
  APP_PDB     : application PDB
    Schema APP
      TABLE APP_ORDERS, INDEX, VIEW, PROCEDURE...
    Tablespaces -> segments -> extents -> data blocks
    Object data is stored in datafiles.
```

The diagram is simplified: **PDBs, schemas, tables, and tablespaces are logical views**, not separate processes running alongside the instance. PDBs have datafiles within their own scope, while sharing certain CDB-level physical components such as control files and online redo logs.

| Concept | Nature | Examples | Key Takeaway |
| --- | --- | --- | --- |
| Physical database | Set of persistent storage files | `system01.dbf`, control file, redo log | Persists after instance shutdown, unless files are deleted or corrupted |
| Instance | Running memory + processes | SGA, DBWn, LGWR | Created at startup; memory state is lost on shutdown |
| CDB / PDB | Database organizational boundaries in multitenant architecture | `CDB$ROOT`, `APP_PDB` | A PDB is **not automatically a separate instance** |
| Schema | Namespace containing objects owned by a database user | `APP`, `HR` | Schema is not synonymous with tablespace |
| SQL object | Object referenced by name by users | Table, view, index, sequence, package | Some have data segments; others only have definitions |
| Tablespace | Logical storage grouping mapped to files | `USERS`, `SYSTEM`, `TEMP` | Not an operating system directory |
| Segment / extent / block | Units of data space allocation | Table segment or index segment | Connects logical objects to blocks inside datafiles |

## 2. Physical Database: What Actually Resides on Disk

In the core architectural model, an Oracle database has three essential file types:

### 2.1. Datafiles — Files Containing Data Content

**Datafiles** contain Oracle data blocks for tablespaces: table data, indexes, dictionary data, undo, and other storage content depending on the tablespace type. Filenames commonly end in `.dbf`, though the filename is not what defines the file's nature. A single tablespace can use multiple datafiles; a single datafile belongs to one tablespace at a time.

An illustrative example of file layout (paths are for demonstration only):

```text
/u02/oradata/DEMO/system01.dbf   -> SYSTEM tablespace
/u02/oradata/DEMO/sysaux01.dbf   -> SYSAUX tablespace
/u02/oradata/DEMO/users01.dbf    -> USERS tablespace
/u02/oradata/DEMO/users02.dbf    -> can also belong to USERS
```

For a **PDB**, datafiles may reside in a directory structure managed separately by Oracle for that PDB; actual names and locations depend on the installation, Oracle Managed Files (OMF), ASM, or cloud storage. You should not infer file paths from schema names.

A **tempfile** is a physical file serving a temporary tablespace, such as for sorting, hash operations, or temporary SQL processing. Tempfiles have a different role and recovery behavior from datafiles storing persistent data; they are not where long-lived application tables are stored.

### 2.2. Control Files — Database Structure Control Information

The control file stores information Oracle needs to identify and manage the database, such as database identity, structure/datafiles, checkpoints, and metadata for recovery. When the database is in the **MOUNT** state, Oracle has opened the control file but has not yet opened the database for normal use.

Control files are commonly **multiplexed** into multiple copies across appropriate storage locations according to administrative configuration. Losing all control files can prevent mounting or opening the database even if the datafiles still exist.

### 2.3. Online Redo Log Files — Recording Changes for Recovery

Redo records change information used for recovery after a failure. Oracle writes redo from the redo log buffer to the **online redo log**; when a commit succeeds, the redo records needed for the transaction have been durably written according to Oracle's commit mechanism.

Key point: **it is not required for every modified data block to be written by DBWn to datafiles at the exact moment of commit**. If the instance fails, Oracle can use redo to perform *instance recovery*. Online redo logs are also typically configured in groups and members to protect against file loss.

In `ARCHIVELOG` mode, filled redo logs can be saved as **archived redo logs**, supporting backup strategies and media recovery. These are operationally critical files, though they do not replace datafiles or control files.

### 2.4. Supporting Files That Should Not Be Equated

| Component | Purpose | Distinction |
| --- | --- | --- |
| `SPFILE` / `PFILE` | Instance startup parameters | Not where application data rows are stored |
| Password file | Authenticates eligible privileged administrative connections | Not a schema or table |
| Archived redo logs | Saved redo supporting recovery | Distinct from active online redo logs |
| Tempfiles | Temporary space for SQL operations | Does not store persistent application data |
| Backup/RMAN pieces | Copies used for recovery | Output of a backup plan, not open datafiles |
| Alert/trace logs | Operational diagnostic information | Not copies of SQL tables |

Therefore, "backing up the database" requires a consistent recovery strategy, not simply copying an arbitrary `.dbf` file while the instance is running.

## 3. Instance: Oracle Running in RAM and Processes

An **Oracle instance** consists of a shared memory area called the **SGA (System Global Area)** and a set of **background processes**. When client sessions exist, Oracle also has *server processes* handling session requests according to the connection configuration. The instance opens and interacts with the physical database.

### 3.1. Memory Components

| Area | Typical Role |
| --- | --- |
| **Database buffer cache** (in SGA) | Holds copies of data blocks read from datafiles or modified in memory |
| **Shared pool** | Stores parsed SQL structures, execution plans, dictionary cache, and shared information |
| **Redo log buffer** | Holds redo information before LGWR writes it to the online redo log |
| **PGA (Program Global Area)** | Private memory bound to a process, serving processing state and private work areas; **not part of the SGA** |

Depending on configuration, Oracle also has other memory areas; you do not need to memorize every memory area name to distinguish **persistent data in files** from **active processing state in RAM**.

### 3.2. Representative Background Processes

| Process | Primary Responsibility |
| --- | --- |
| **DBWn** (Database Writer) | Writes modified data blocks from the buffer cache down to datafiles according to Oracle's mechanism |
| **LGWR** (Log Writer) | Writes redo from the redo log buffer to the online redo log |
| **CKPT** (Checkpoint) | Coordinates checkpoints and updates checkpoint information; **does not directly write all data blocks in place of DBWn** |
| **SMON** (System Monitor) | Performs system monitoring and recovery tasks according to the Oracle version's functionality |
| **PMON** (Process Monitor) | Monitors and cleans up failed resources/processes according to the active process architecture |
| **ARCn** (Archiver) | Saves redo into archived redo logs in `ARCHIVELOG` configurations |

### 3.3. Processing Flow of a Transaction

Suppose a program executes:

```sql
UPDATE app_orders
   SET amount = amount + 100
 WHERE order_id = 42;

COMMIT;
```

Conceptually:

1. The server process receives the SQL over the session connection, parses the statement, and locates the relevant blocks.
2. The blocks may already be in the **buffer cache** or be read from a **datafile** into the buffer cache.
3. Oracle updates the required data state in memory and generates **redo records** describing the change.
4. At `COMMIT`, the required redo is written by LGWR to the online redo log according to Oracle's durability rules; the application receives the commit result.
5. **DBWn may write the data blocks to the datafile at another time**. That does not mean a committed transaction will be lost during normal instance recovery: redo is used to restore a valid state.

This example shows that **the instance processes**, **files store persistently**, and **the table `APP_ORDERS` is the logical object name** being queried. Actual write steps involve optimizations, caching, undo, and concurrency mechanisms that are more complex; this is an explanatory model, not a strict order for every I/O.

## 4. Is There Always a 1–1 Mapping Between a Database and an Instance?

**No.** This is a common point of confusion when moving from a personal machine to enterprise systems.

### Single-Instance

In a configuration commonly seen in learning environments:

```text
Instance A (SGA + background processes)
            |
            v
Database A (datafiles + control files + redo logs)
```

One instance opens one database. If the instance is shut down cleanly, the database files remain on storage and can be opened again later.

### Oracle RAC (Real Application Clusters)

In an **Oracle RAC** system, multiple instances on different nodes can access **the same physical database** on shared storage:

```text
Node 1: Instance A ---------+
                            |
                            +---- Shared Database
                            |     (datafiles, control files...)
Node 2: Instance B ---------+
```

Each instance has its own SGA and background processes. RAC mechanisms coordinate block access and redo across instances; these details cannot be simulated by arbitrarily pointing two regular Oracle instances at the same datafile directory.

| Configuration | Instances | Physical Databases | Key Difference |
| --- | --- | --- | --- |
| Single-instance | Usually 1 | 1 | Common learning model |
| RAC | Multiple | 1 shared database | Requires appropriate RAC architecture and licensing |
| Multiple independent databases on one host | Each database has its own instance when running | Multiple | Not the same as one database with multiple schemas |

**A PDB is not a RAC instance.** A CDB with multiple PDBs is typically still served by one instance in a single-instance deployment; in a RAC deployment, multiple instances can open the same CDB.

## 5. CDB, PDB, Schema: Different Logical Boundaries

Modern Oracle releases use the **multitenant** architecture:

- **CDB (Container Database)** is the database containing containers, with CDB-level physical structure and files. It includes the **CDB root**, the **PDB seed**, and application **PDBs**.
- **`CDB$ROOT`** stores shared metadata and administrative components; it is not the default place to create business tables for individual applications.
- **`PDB$SEED`** is the template Oracle uses when creating a PDB, not an area for learners to create application data.
- **PDB (Pluggable Database)** is a relatively independent logical database environment inside a CDB, with its own metadata, schemas, and datafiles; users typically connect through a **PDB service**.
- **Schema** is the collection of objects owned by a database user within the corresponding container. Multiple schemas can exist inside a single PDB.

Example:

```text
CDB: TRAINING_CDB                     -> physical database + instance opening CDB
  CDB$ROOT                            -> root container
  PDB$SEED                            -> seed container
  PDB: SALES_PDB                      -> an application environment
    Schema SALES_APP                  -> user + user's objects
      SALES_APP.CUSTOMERS             -> table
      SALES_APP.ORDERS                -> table
      SALES_APP.IX_ORDERS_DATE        -> index
    Schema REPORT_APP                 -> another schema in the same PDB
      REPORT_APP.ORDER_REPORT         -> view
  PDB: TRAINING_PDB                   -> another PDB, not a new instance
    Schema LAB_STUDENT
      LAB_STUDENT.EXERCISE_01         -> table
```

A PDB can have its **own datafiles**, yet PDBs within the same CDB share CDB-level components and the instance. When accidentally connecting to `CDB$ROOT` instead of `SALES_PDB`, user/schema creation statements may behave differently or be rejected; when connecting to a different PDB, a table with the same name may not exist at all.

### Service Name, SID, and Schema Are Not the Same

| Name | What Does It Identify? | Where Is It Used? |
| --- | --- | --- |
| **Service name** | Database service handling connections, typically bound to a PDB or workload | JDBC URL / client connect string |
| **SID / instance name** | A specific instance in an Oracle environment | Instance configuration and diagnostics |
| **PDB name** | Logical container inside a CDB | Database separation for applications/labs |
| **Username / schema** | Owner of SQL objects | Authentication, privileges, and `SCHEMA.OBJECT` naming |

Example service-name-style JDBC URL:

```text
jdbc:oracle:thin:@//localhost:1521/SALES_PDB
```

This is only a **syntax example**; the service name must match the configuration registered with the listener, and should not be guessed by combining an instance name or schema name. A single PDB can be served by multiple different services.

## 6. Logical Objects: Namespaces and Storage Organization

The phrase "logical objects" is used across two related but **distinct** layers:

1. **SQL objects**: tables, views, indexes, sequences, triggers, procedures, packages, synonyms...
2. **Logical storage structures**: tablespaces, segments, extents, data blocks — the units Oracle uses to lay out data into files.

### 6.1. SQL Objects in a Schema

| Object | Used By Learners To | Has Its Own Data Segment Immediately? |
| --- | --- | --- |
| **Table** | Store rows and columns | Usually has a segment when space is allocated; initial allocation may be deferred |
| **Index** | Support retrieval and certain constraints | Usually has an index segment if data/definition requires it |
| **View** | Name a query | **Does not** store a copy of rows by default |
| **Materialized view** | Store materialized query results | **Has** separately managed storage for results |
| **Sequence** | Generate sequential numeric values | Has Oracle-managed metadata and state; not a typical user table segment |
| **Procedure / function / package** | Encapsulate PL/SQL code | Stores definition/metadata, not an application row table |
| **Synonym** | Define an alias referencing an object | Does not turn the target object into a physical copy |

**A schema is not a file.** For example, the table `SALES_APP.ORDERS` belongs to schema `SALES_APP`, yet the table's segment may reside in tablespace `APP_DATA`, and an index on that same table may reside in tablespace `APP_INDEX`. Multiple schemas can also share a single tablespace if granted appropriate privileges and quota.

### 6.2. Tablespace → Segment → Extent → Data Block

Oracle describes logical storage structures in terms of space allocation:

```text
TABLESPACE APP_DATA
  |-- manages one or more DATAFILEs on storage
  |
  |-- SEGMENT of table SALES_APP.ORDERS
  |      |-- EXTENT 1: multiple contiguous Oracle data blocks
  |      |-- EXTENT 2: multiple contiguous Oracle data blocks
  |      +-- ...
  |
  +-- SEGMENT of table SALES_APP.CUSTOMERS
         |-- EXTENT 1
         +-- ...
```

- **Tablespace** is the logical space management unit in a database/PDB. A permanent tablespace maps to **one or more datafiles**; a temporary tablespace uses **tempfiles**.
- **Segment** is the space allocated for a storage structure such as a table, index, LOB, or partition. Not every SQL object has a segment. A partitioned table can map to multiple segments, so there is no rule that "one table = one segment".
- **Extent** is a group of contiguous Oracle data blocks allocated to a segment inside a datafile. A segment can have multiple extents distributed across different datafiles belonging to the same tablespace when configuration permits.
- **Oracle data block** is the smallest logical storage unit Oracle uses to organize data I/O. Block size is determined by tablespace/database configuration and does not have to match the operating system block size.

Relationship to keep in mind:

```text
SQL object (table/index)
       |
       +--> segment(s) if the object requires materialized data storage
                   |
                   +--> extent(s)
                           |
                           +--> Oracle data blocks
                                       |
                                       +--> located inside a datafile
                                               |
                                               +--> belonging to a tablespace
```

**Tablespace and schema are two independent classification dimensions:** schema answers "**who owns the object?**"; tablespace answers "**which storage space is used?**". A table or index name does not immediately reveal the physical file location of all the blocks containing it.

### 6.3. Example of the Difference Between Object and Segment

Suppose in PDB `TRAINING_PDB`, user `LAB_STUDENT` has privileges to create objects and quota on the default tablespace. Run:

```sql
CREATE TABLE lab_orders (
    order_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    amount   NUMBER(12, 2) NOT NULL
);

INSERT INTO lab_orders (amount) VALUES (150.00);
COMMIT;

CREATE INDEX ix_lab_orders_amount ON lab_orders (amount);

CREATE VIEW v_lab_orders_positive AS
SELECT order_id, amount
  FROM lab_orders
 WHERE amount > 0;
```

Now inspect the **SQL objects** owned by the user:

```sql
SELECT object_name, object_type, status
  FROM user_objects
 WHERE object_name IN (
       'LAB_ORDERS',
       'IX_LAB_ORDERS_AMOUNT',
       'V_LAB_ORDERS_POSITIVE'
 )
 ORDER BY object_type, object_name;
```

The output will show the table, index, and view. Then inspect the **allocated segments**:

```sql
SELECT segment_name, segment_type, tablespace_name, bytes
  FROM user_segments
 WHERE segment_name IN (
       'LAB_ORDERS',
       'IX_LAB_ORDERS_AMOUNT',
       'V_LAB_ORDERS_POSITIVE'
 )
 ORDER BY segment_name;
```

Once data exists, the table and index typically have segments; **a regular view has no segment storing query results**, so it does not appear under the view name in `USER_SEGMENTS`. The primary key in this example may also cause Oracle to create **another index** to enforce the constraint. This illustrates that the count of SQL objects and the count of storage segments do not necessarily match.

To check which tablespace a table declares it uses:

```sql
SELECT table_name, tablespace_name
  FROM user_tables
 WHERE table_name = 'LAB_ORDERS';
```

The `USER_*` views allow users to inspect metadata for their own objects without typically needing DBA privileges. `DBA_*` and many `V$*` views have broader scope and are used only when granted appropriate privileges by an administrator.

## 7. Checking Which Database, Instance, and Container You Are In

In an SQL client connected to Oracle, a regular user can start with:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    USER                                     AS login_user
FROM dual;
```

Illustrative values might be:

```text
DATABASE_NAME | CONTAINER_NAME | CURRENT_SCHEMA | LOGIN_USER
--------------+----------------+----------------+-----------
TRAINING_CDB  | TRAINING_PDB   | LAB_STUDENT    | LAB_STUDENT
```

Actual names vary by installation. This query is especially helpful when a statement reports "table not found": sometimes the learner is connected to the **wrong PDB**, using a **different schema**, or missing read privileges on the object.

If granted read access to dynamic performance views, an administrator can inspect the database and instance:

```sql
-- Status of the instance currently connected to.
SELECT instance_name, status
FROM v$instance;

-- Database and database open mode.
SELECT name, open_mode, cdb
FROM v$database;

-- List of PDBs belonging to the CDB (visibility and scope depend on user privileges).
SELECT con_id, name, open_mode
FROM v$pdbs;
```

In RAC, administrators can use `GV$INSTANCE` to inspect multiple instances. Being unable to read `V$INSTANCE` due to insufficient privileges **does not prove the instance is down**; metadata authorization is a separate issue.

## 8. Startup States Help Distinguish Instance from Database

One of the clearest illustrations is Oracle's startup lifecycle:

| State | Instance | Physical Database | What Is Happening |
| --- | --- | --- | --- |
| **SHUTDOWN** | Inactive | Files remain on storage | No instance is opening the database |
| **NOMOUNT** | SGA and background processes initialized | Control file not yet mounted | An instance exists, but the database is not yet mounted |
| **MOUNT** | Active | Control file opened/read | Certain DBA/recovery operations are possible; database not yet open for regular SQL |
| **OPEN** | Active | Datafiles and online redo logs opened as required | Database is ready to serve authorized operations |

Illustration for a DBA using SQL*Plus (requires a privileged connection; do not run carelessly on a shared database):

```sql
STARTUP NOMOUNT;
ALTER DATABASE MOUNT;
ALTER DATABASE OPEN;
```

In a CDB, **opening the CDB does not mean every application PDB is OPEN**. A DBA may need to open PDBs with separate commands and save their open state appropriately. Thus, an instance in the `OPEN` state does not automatically guarantee that the service/PDB used by an application is ready.

Viewed through this lifecycle, the questions "does the database exist?" and "is the instance/database open to accept connections?" are two distinct questions. Files may remain intact while the instance is stopped; an instance may be running while the database is only at `NOMOUNT`.

## 9. Diagnosing Issues by the Right Architectural Layer

| Symptom | Layer to Check First | Direction for Root Cause |
| --- | --- | --- |
| Cannot connect via host/port, listener/service error such as `ORA-12514` | Network / listener / service / PDB | Host, port, service registration, whether the PDB is open |
| `ORA-01034: ORACLE not available` | Instance / database state | Whether the instance is running, environment configuration, and open state |
| Database fails to mount/open due to missing or damaged file, e.g. `ORA-01157` | Physical files / storage | Datafiles, filesystem/ASM permissions, disk mount, recovery |
| `ORA-00942: table or view does not exist` | PDB / schema / object / privileges | Current container, object owner, object name, `SELECT` privilege |
| Cannot create table due to missing quota, e.g. `ORA-01950` | Schema / tablespace / privileges | Default tablespace, granted quota, object creation privilege |
| Table created but view name not seen in `USER_SEGMENTS` | Logical object vs. physical segment | Regular views do not store results; view name has no table segment |
| Same database host, yet application A cannot see application B's tables | PDB / schema / privileges | Are A and B in the same PDB? Using schema prefix? Granted access? |

These are **classification guidelines**, not definitive diagnoses based on a single error code. Always read the full error message and relevant logs before making database changes.

## 10. Self-Check Practice Exercises

### Exercise 1 — Classify Components

Given the list:

```text
SGA, LGWR, datafile, control file, online redo log,
PDB SALES_PDB, schema SALES_APP, table ORDERS,
view V_ORDERS, tablespace APP_DATA, segment ORDERS,
extent, data block, SQLcl.
```

Divide the components into four groups: **instance**, **physical files**, **logical objects/structures**, and **client tool**. Explain why `SQLcl` is not the database and why a `PDB` is not synonymous with an `instance`.

### Exercise 2 — Observe Object vs. Segment Differences

In a practice schema, run the code creating `LAB_ORDERS`, `IX_LAB_ORDERS_AMOUNT`, and `V_LAB_ORDERS_POSITIVE` from section 6. Then:

1. Use `USER_OBJECTS` to record which objects exist.
2. Use `USER_SEGMENTS` to record which segments have been allocated and their corresponding tablespaces.
3. Explain why the view appears in the object list yet has no separate segment storing rows.
4. Use `SYS_CONTEXT` to check the session's database name, container name, and current schema.

### Exercise 3 — Explain an Operational Scenario

Suppose an administrator performs a controlled instance shutdown, while all datafiles, control files, and online redo logs remain on storage.

- Does application data automatically disappear? **No**: persistent data resides in files and does not depend on the SGA remaining in existence.
- Can users execute `SELECT` while the instance is stopped? **No** through that instance: the instance must be started and the appropriate database/PDB opened.
- Can copying a single datafile be considered a full database backup plan? **No**: backup/recovery requires the full set of files, redo, and consistency using an Oracle-supported method.
- When moving from single-instance to RAC, what increases? **The number of instances that can access the same database**, not necessarily the number of physical databases.

### Exercise 4 — Trace the Path of a Query

Draw arrows from a Java application, service, instance, object `SALES_APP.ORDERS`, segment, extent, and block to the datafile. Distinguish arrows for **connection**, **processing**, **logical organization**, and **physical storage**. Explain why a schema name cannot be treated as a path to a specific file.

## Architectural Conclusion

An application sees **logical objects** such as `SCHEMA.TABLE` inside the right **PDB**; the **instance** uses memory and processes to handle requests; persistent data along with information needed for operation and recovery resides in **database files**. Internally on storage, **tablespace → segment → extent → block** lets Oracle manage data placement and allocation without requiring developers to know the OS path of every row.

Understanding these three boundaries helps you read Oracle diagrams accurately, pick the right connection service, manage schema privileges, explain commit/redo behavior, troubleshoot errors, and avoid mistaking one database with multiple schemas/PDBs for multiple independent instances.

**Further reading:** [Oracle Database Concepts (official documentation, choose the exact release you use)](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/) — sections on *Oracle Database Architecture*, *Oracle Database Instance*, *Physical Storage Structures*, *Logical Storage Structures*, and *Multitenant Architecture*.
