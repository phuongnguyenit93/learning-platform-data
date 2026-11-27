# Oracle Terminology Map: Database, Instance, Service, Schema, CDB, and PDB

When starting with Oracle Database, you quickly hear phrases like "connect to the database," "restart the instance," "create a schema," "open the PDB," or "switch services." These describe **different components** of the same system. Confusing them can lead to connecting to the wrong environment, granting privileges in the wrong place, or troubleshooting the wrong root cause.

This lesson places six key terms on a single map: **database**, **instance**, **service**, **schema**, **CDB**, and **PDB**. The goal is to understand what question each term answers, how they relate to one another, and how to identify them when connecting or running SQL.

## 1. The Big Picture

In Oracle architecture, these concepts fall into three layers:

1. **Storage and runtime:** a *database* is the collection of data and files serving storage, while an *instance* is the memory and processes operating the database.
2. **Connectivity and objects:** a *service* is the logical name applications use to reach a workload/database or PDB; a *schema* is the namespace of objects owned by a user.
3. **Multitenant organization:** a *CDB* (Container Database) is a database holding containers; a *PDB* (Pluggable Database) is a container with its own data, schemas, and application environment inside the CDB.

| Term | Question It Answers | Illustrative Example | Should Not Be Equated With |
|---|---|---|---|
| **Database** | Where does Oracle data physically reside, and how is it organized and persisted? | Database `CORPDB` with datafiles, control files, and redo logs | A running instance |
| **Instance** | Which component uses memory and processes to open and access the database? | Instance `corp1` | The entire database or a PDB |
| **Service** | Which name does an application call to be routed to the right data service? | `sales_rw.example.com` | SID, schema name, or PDB name |
| **Schema** | Which owner do tables, views, sequences, packages, etc. belong to? | Schema `SALES_APP`, containing `ORDERS` | A separate database or PDB |
| **CDB** | How does this database organize multiple containers/PDBs? | CDB `CORPDB` | A schema |
| **PDB** | Which logical data unit inside the CDB is the application operating in? | PDB `SALES_PDB` | A separate instance or a schema |

> **Orientation rule:** "What name do I connect with?" usually asks about the **service**; "Which data region am I in?" asks about the **PDB**; "Whose tables am I using?" asks about the **schema**; "Which server runtime is processing queries?" asks about the **instance**.

## 2. Database: The Persistent Data Collection

In architectural terms, an **Oracle database** is the set of physical files storing data and the metadata required to manage and recover it. Typical components include:

- **Datafiles:** store table contents, indexes, and other persistent objects via tablespaces.
- **Control files:** contain database identity and structure, datafile locations, checkpoints, and management/recovery metadata.
- **Online redo logs:** record changes to support recovery when needed.

The database is the **durable** part: an instance can be shut down, yet the database files remain on storage. Upon restart, an instance can open the database from those files.

In casual conversation, "Oracle Database" sometimes refers to the entire product/system comprising the database, instance, and services. When reading architecture diagrams or diagnosing failures, separate the physical meaning of **database** from **instance**.

### How Do Database and Tablespace Differ?

A **tablespace** is a logical storage unit inside a database, implemented by one or more datafiles. A **schema** organizes objects by *owner*; a **tablespace** organizes storage by *storage location/structure*. One schema can have objects across multiple tablespaces, and one tablespace can store objects belonging to multiple schemas.

## 3. Instance: Memory and Processes Running the Database

An **Oracle instance** primarily consists of:

- **SGA (System Global Area):** shared memory regions, such as the database buffer cache and shared pool.
- **Background processes:** background tasks handling data writes, redo writes, recovery, monitoring, and coordination—such as DBWn, LGWR, and CKPT.

**Server processes** handle SQL requests from client sessions interacting with the instance; they are usually described separately rather than as the core defining components of the instance itself.

You can picture it as:

~~~text
Database files on storage
    ├── Datafiles
    ├── Control files
    └── Redo logs
             ▲
             │ opens and accesses
             │
Running instance
    ├── SGA (shared memory)
    └── Background processes
~~~

Several important points:

- **Single-instance:** normally one running instance opens one database.
- **Oracle RAC (Real Application Clusters):** multiple instances across different machines/nodes can concurrently open the **same database**. Each instance has its own SGA and processes, coordinating access to the shared data.
- **SID (System Identifier):** identifies an instance in SID-style configuration/connection contexts. In RAC, each instance has its own SID. A SID is **not a service name**.
- **Startup states:** startup typically progresses through `NOMOUNT` (instance started), `MOUNT` (control files attached), and `OPEN` (database opened for normal operations). Therefore, "the instance is running" does not automatically mean users can query data.

For example, a CDB named `CORPDB` can be opened by instance `corp1`. In a RAC deployment, that same CDB/database can also be opened by instance `corp2`. That gives **one database, multiple instances**.

## 4. CDB and PDB: How Oracle Organizes Multiple Data Environments

Oracle's **multitenant** architecture uses two tiers:

- **CDB (Container Database):** an Oracle database structured to hold containers, including root and PDBs. The CDB owns the shared database infrastructure and is operated by one or more instances.
- **PDB (Pluggable Database):** a logical database inside a CDB with its own schemas, application objects, data, and local metadata. Applications typically connect to the appropriate **PDB** via a service.

Example of a CDB:

~~~text
Oracle CDB: CORPDB
│
├── CDB$ROOT                  Root container, shared metadata and administration
├── PDB$SEED                  Read-only template for creating new PDBs
│
├── SALES_PDB                 PDB dedicated to the sales system
│   ├── schema SALES_APP
│   ├── schema REPORT_APP
│   └── tables, views, packages, data...
│
└── HR_PDB                    PDB dedicated to human resources
    ├── schema HR_APP
    └── tables, views, packages, data...

Instance corp1
    └── SGA and background processes operating the CDB above
~~~

### What Roles Do the Containers Play?

| Container | Role | Common Practice |
|---|---|---|
| `CDB$ROOT` | Root managing shared CDB metadata, components, and common users | DBAs configure and administer the CDB; avoid placing ordinary application tables in root |
| `PDB$SEED` | System template for provisioning new PDBs | Do not use as an application PDB or modify arbitrarily |
| User PDB, e.g., `SALES_PDB` | Holds application data and schemas | Create local users, tables, views; connect applications and run business workloads |

A PDB can contain **multiple schemas**. Different PDBs can even contain schemas with the same name such as `APP_USER`, yet those are separate accounts/schemas in **different containers** with their own objects and privileges. PDBs can be opened/closed, cloned, or unplugged/moved using Oracle's administration capabilities, while PDBs inside the same CDB share the common instance/database infrastructure.

**A PDB is not equivalent to a separate server or separate instance.** Separation by PDB is logical data and administrative isolation; physical resources can still be shared, and resource isolation depends on system configuration.

### Does Every Oracle Database Have PDBs?

Not necessarily. Some legacy Oracle systems operate in **non-CDB** architecture, without PDBs. The concepts of database, instance, service, and schema still exist. In multitenant environments, the two CDB/PDB tiers are needed to know exactly which container an application is working in.

## 5. Schema: Namespace of Objects Owned by a User

In Oracle, a **schema** is the set of database objects owned by a **database user**: tables, views, indexes, sequences, procedures, functions, packages, triggers, and other objects. The user and schema share the **same name** within the corresponding container; you log in as the user, and objects are qualified by the schema name.

For example, inside `SALES_PDB`:

~~~sql
-- The ORDERS table belongs to schema SALES_APP.
SELECT order_id, status
FROM sales_app.orders;
~~~

Here:

- `SALES_PDB` is the **PDB** the SQL session is connected to.
- `SALES_APP` is the **schema** that owns the table.
- `ORDERS` is the **object** within that schema.
- The user executing `SELECT` may be `SALES_APP` or another user granted appropriate privileges.

Oracle does not treat a schema as an independent sub-database in the sense of a PDB. A schema **does not** have its own instance, its own listener, or an independent open/close lifecycle. One PDB can contain many schemas; a schema does not replace PDB boundaries.

### Login User, Owning Schema, and Access Privileges

If you log in as `REPORT_USER`, your queries are not limited to `REPORT_USER`'s objects. Once granted privileges, this user can query `SALES_APP.ORDERS`. Access depends on having the appropriate **privileges/roles**, not simply on two schemas being in the "same database" or "same PDB."

Statement:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = SALES_APP;

-- You can omit the schema prefix on table names,
-- provided the logged-in user actually has SELECT privilege on the table.
SELECT order_id, status
FROM orders;
~~~

`CURRENT_SCHEMA` only changes the default schema used for **object name resolution**. It **does not change** `SESSION_USER` (login identity) and **does not grant any extra privileges**.

## 6. Service: The Logical Name Applications Connect With

A **database service** is a logical name representing a data access service or workload. Applications typically provide **host + port + service name** so Oracle routes the connection to the right target.

In a multitenant environment, a service can be **bound to a specific PDB**. A PDB can have multiple services serving different applications or workloads. In RAC, a service can be offered by one or more instances to support routing, load balancing, and high availability. Hence **a service has no mandatory one-to-one relationship with an instance**.

Example JDBC Thin connection string:

~~~text
jdbc:oracle:thin:@//db.example.internal:1521/sales_rw.example.com
~~~

Components of the connection string:

| Component | Meaning |
|---|---|
| `db.example.internal` | Host or address the client contacts |
| `1521` | Listener port (common example port; may differ) |
| `sales_rw.example.com` | Requested **service name** |
| `SALES_PDB` | The PDB this service is configured to serve; **not necessarily visible in the string** |
| `SALES_APP` | User/schema subsequently used to authenticate and access objects |

Simplified connection flow:

~~~text
Application
   |
   | host:port / service_name
   v
Oracle Net Listener
   |
   | locate service and forward connection request
   v
Instance / server process
   |
   | session bound to the service's container
   v
PDB: SALES_PDB
   |
   | authenticate USER, check privileges, run SQL
   v
Schemas SALES_APP, REPORT_APP, ...
~~~

**Listener is not the service**: the listener is the network component accepting connection requests; the service is the logical name the listener/Oracle uses to identify the destination and workload. **Service is not user/schema**: choosing the right service lands you in the right PDB, while username/password and privileges determine which objects you can access.

### Service Name and SID

A common mistake is putting a SID into the `SERVICE_NAME` field, or vice versa:

- **SID:** identifies an **instance**, such as `corp1`.
- **SERVICE_NAME:** identifies a **logical service**, such as `sales_rw.example.com`.

For modern applications—especially when using PDBs or RAC—**connecting by service name** is usually the right choice. The `host:port:SID` format is the older SID connection style and does not substitute for service semantics.

## 7. Putting All Six Terms Together in a Concrete Scenario

Suppose an organization runs Oracle as follows:

~~~text
                                      ┌───────────────────────┐
                                      │ Client: Sales app     │
                                      └───────────┬───────────┘
                                                  │
                             //dbhost:1521/sales_rw.example.com
                                                  │
                                                  ▼
                                          Listener / service
                                                  │
                                                  ▼
                      CDB / DATABASE: CORPDB
              ┌──────────────────────────────────────────────┐
              │ Instance corp1: SGA + background processes   │
              │                                              │
              │ CDB$ROOT          PDB$SEED                   │
              │                                              │
              │ ┌───────────────┐      ┌───────────────────┐ │
              │ │ SALES_PDB     │      │ HR_PDB            │ │
              │ │ Schema        │      │ Schema            │ │
              │ │ SALES_APP     │      │ HR_APP            │ │
              │ │ ORDERS        │      │ EMPLOYEES         │ │
              │ └───────────────┘      └───────────────────┘ │
              └──────────────────────────────────────────────┘
                      Database files on storage
~~~

Here are the matching names and functions:

| Question | Answer |
|---|---|
| Which physical database holds the data? | `CORPDB` |
| Which instance is processing requests? | `corp1` (additional instances may exist under RAC) |
| Which service does the Sales app request? | `sales_rw.example.com` |
| Which PDB does the Sales service route to? | `SALES_PDB` per this example configuration |
| Which schema owns the business table? | `SALES_APP` |
| Which structure contains both the Sales and HR PDBs? | The same **CDB** `CORPDB` |

If the HR application connects using a service bound to `HR_PDB`, it operates in a **different container**, even though it may share the same host, listener, instance, and physical database with Sales.

> **Distinguish names from relationships:** a service may share the same name as a default PDB, yet that does not make them the same object. To know which PDB a service routes to, inspect the configuration or query the actual container of the logged-in session.

## 8. Self-Identifying Inside an Oracle Session Using SQL

The SQL query below is most useful when you are **already logged in** and want to see which database/PDB/service/schema you are in. `SYS_CONTEXT` calls do not require querying administrative views.

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'INSTANCE_NAME')  AS instance_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Suppose it returns:

~~~text
DATABASE_NAME  INSTANCE_NAME  CONTAINER_NAME  SERVICE_NAME          SESSION_USER  CURRENT_SCHEMA
-------------  -------------  --------------  --------------------  ------------  --------------
CORPDB         corp1          SALES_PDB       sales_rw.example.com  REPORT_USER   REPORT_USER
~~~

We know this session is inside **PDB `SALES_PDB`** of database **`CORPDB`**, using service **`sales_rw.example.com`**, running via instance **`corp1`**, and logged in as user **`REPORT_USER`**. Whether querying `SALES_APP.ORDERS` is allowed still depends on `REPORT_USER`'s privileges.

### Inspecting CDB/PDB Structure (Requires Appropriate Privileges)

The queries below are primarily for administrators or accounts granted access to dynamic performance views. Depending on privileges and the current container, results may be scoped or restricted.

~~~sql
-- Is the currently open database a CDB?
SELECT name, cdb, open_mode
FROM v$database;

-- Current instance
SELECT instance_name, host_name, status
FROM v$instance;

-- Containers in the CDB, including root, seed, and PDBs
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;

-- Services currently registered with Oracle and their associated PDBs
SELECT name, network_name, pdb
FROM v$services
ORDER BY name;
~~~

In SQL*Plus or SQLcl, `SHOW CON_NAME` is a shorthand way to check the current container; it is a **client** command, not a standard SQL statement.

### Checking Which Schema Owns an Object

~~~sql
-- Objects visible to the current session
-- where owner is SALES_APP
SELECT owner, object_name, object_type
FROM all_objects
WHERE owner = 'SALES_APP'
  AND object_name = 'ORDERS';
~~~

`ALL_OBJECTS` lists objects visible to the current user in the connected container context. Finding zero rows is **not enough** to conclude the table does not exist anywhere in the CDB: you might be in a different PDB, have a typo in the name, or lack privileges to see the object.

## 9. Diagnosing Incidents at the Right Conceptual Layer

When an application encounters an error, identify **which layer** has the problem before changing configuration:

| Symptom | What to Check First | Why |
|---|---|---|
| Client reports requested service is unrecognized, e.g., `ORA-12514` | Service name, listener, PDB open state, service registration | The listener may not know the requested service yet, or the PDB/service is not ready |
| Connection reaches Oracle, but app sees "wrong environment" data | `CON_NAME`, `SERVICE_NAME`, connection string | The service may route to a different PDB |
| User logs in successfully, but gets `ORA-00942` when querying a table | Schema owner, object name, access privileges, current PDB | The table may belong to another schema/PDB or privileges are missing |
| Creating an app user in CDB root fails with common-user naming error, e.g., `ORA-65096` | Current container and intent (local vs. common user) | Application **local users** are normally created inside a PDB |
| "Restarted instance" yet data files remain | Instance and database state | The instance is the running runtime; the database sits on storage |
| App uses SID instead of service name and lands in the wrong PDB | Connection string format and target configuration | SID identifies an instance; service selects a workload/PDB |

For example, when investigating "logged in fine, but `ORDERS` table not found": first run the `SYS_CONTEXT` query above to verify the **PDB**, next verify the owning **schema**, and finally check the current user's **privileges**. Connecting to the right host or instance still does not guarantee landing in the right PDB or schema.

## 10. Misconceptions to Avoid

1. **"Every PDB has its own separate instance."** False. PDBs in a CDB typically share an instance; under RAC, a CDB can be opened by multiple instances.
2. **"Schema means database."** False in Oracle terminology. A schema is a user's collection of objects inside a container; a PDB is a larger logical data unit holding multiple schemas.
3. **"Service name is always identical to the PDB name."** Not mandatory. A PDB can have multiple services, and administrators can choose service names freely.
4. **"Connected to CORPDB means I am definitely in SALES_PDB."** False. The database name is typically the CDB name; check `CON_NAME`.
5. **"Changing CURRENT_SCHEMA logs in as a different user."** False. It changes default object-name resolution, not identity or privileges.
6. **"Listener, instance, and service are all the same thing."** False. The listener accepts network connections; the service identifies the logical target; the instance provides memory and processes.
7. **"CDB and PDB are two completely independent physical databases."** False. A PDB has its own data/metadata, yet lives inside the CDB structure with shared infrastructure components.

## 11. Self-Check Exercises

**Scenario A.** Two applications both connect to `db.example.internal:1521`. App A uses service `sales_app` and lands in `SALES_PDB`; App B uses `hr_app` and lands in `HR_PDB`. Must they be in two separate physical databases or two separate instances?

**Answer:** No. They can share the same CDB and the same instance while residing in two separate PDBs routed by their respective services.

**Scenario B.** Inside `SALES_PDB`, user `REPORT_USER` successfully queries `SALES_APP.ORDERS`. Which schema owns the table? Who is the session user?

**Answer:** The table belongs to schema `SALES_APP`; the logged-in user is `REPORT_USER`. It succeeds because the session holds the required access privileges.

**Scenario C.** A DBA shuts down instance `corp1`, then restarts it and opens database `CORPDB`. Do the datafiles of `SALES_PDB` vanish when the instance stops?

**Answer:** No. Datafiles are persistent storage; stopping the instance only shuts down memory/processes and serving availability. Whether the PDB is ready for access after restart also depends on its open state and service registration.

**Scenario D.** A session runs `ALTER SESSION SET CURRENT_SCHEMA = SALES_APP`. Can we conclude the session switched PDBs or elevated its privileges to `SALES_APP`?

**Answer:** No. Both the PDB and the logged-in user stay unchanged; only the default schema for resolving object names changes.

## Remembering Through One Connection Story

An application sends a request to the **listener** using a **service name**. The service is configured to serve a **PDB** (or the database in a non-CDB setup); the PDB is part of a **CDB/database**. An **instance** with memory and processes executes work against that database. After authenticating as a **user**, queries operate on objects belonging to one or more **schemas** that the user is permitted to access.

Always answer six questions separately: **which database, which instance, which service, which PDB, which user/schema, and which privileges**. This is the foundational map for reading Oracle architectures, configuring connections, and diagnosing errors accurately.
