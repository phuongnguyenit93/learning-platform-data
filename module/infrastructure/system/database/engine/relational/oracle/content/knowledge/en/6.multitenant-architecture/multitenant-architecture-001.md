# Multitenant Model and Relationships Between CDB Root, Seed, and PDBs in Oracle Database

Oracle Database supports the **multitenant** architecture so that one **container database (CDB)** contains multiple **pluggable databases (PDBs)**. Each PDB provides a relatively independent database environment for applications, while PDBs share the CDB's management infrastructure and resources. This is an important shift from the model where a single database is directly tied to a single set of application objects: one Oracle instance can serve multiple PDBs, and administrative operations must target the **correct container**.

A basic CDB consists of three types of containers: **CDB root** (`CDB$ROOT`), **PDB seed** (`PDB$SEED`), and **user-created PDBs**. They are closely related yet have distinct responsibilities. Understanding this relationship helps you connect to the right PDB, create schemas in the right place, understand how datafiles are separated, and avoid mistakenly operating in the root.

After this lesson, you will be able to:

- Distinguish **CDB**, **instance**, **CDB root**, **PDB seed**, **user-created PDB**, and **service name**.
- Explain what the root contains, how the seed is used to create PDBs, and why applications should work inside a PDB.
- Identify the current container using SQL*Plus, `SYS_CONTEXT`, and dynamic performance views.
- Distinguish **common** vs. **local** accounts, data dictionary scope, and application objects.
- Describe the PDB lifecycle at a conceptual level: creating, opening, closing, saving open state, cloning, and unplugging/plugging.
- Understand the impact of sharing an instance, memory, redo, control files, and physical resources.

> **Practice Scope:** The examples below use a hypothetical CDB named `ORCLCDB`, an application PDB `LABPDB`, and a listener accepting the `LABPDB` service. Actual names and states depend on the version, installation method, and machine configuration. Most commands are **read-only queries**; commands to create or open a PDB are reserved for a lab environment that you administer.

## 1. From Traditional Databases to the Multitenant Model

### 1.1. The Problem Multitenant Solves

Suppose an organization has three applications: sales, human resources, and reporting. Each application wants its own tables, users, privileges, configuration, and data lifecycle. A traditional deployment approach is to create three independent databases, each with its own instance and management structure. This provides stronger isolation at the process level, but introduces many components to start, monitor, and maintain.

In the multitenant model, a DBA can place the three application environments into three PDBs belonging to the same CDB:

~~~text
                         ORACLE INSTANCE
                    SGA + background processes
                              |
                              v
+------------------------------------------------------------------+
|                    CONTAINER DATABASE (CDB)                       |
|                                                                  |
|  +------------------+       +--------------------+                |
|  | CDB$ROOT         |       | PDB$SEED           |                |
|  | shared metadata  |       | read-only template |                |
|  | CDB admin        |       | for creating PDBs  |                |
|  +------------------+       +--------------------+                |
|                                                                  |
|  +------------------+  +------------------+  +------------------+ |
|  | SALES_PDB        |  | HR_PDB           |  | REPORT_PDB       | |
|  | sales users      |  | HR users         |  | report users     | |
|  | tables, indexes  |  | tables, indexes  |  | tables, indexes  | |
|  | own datafiles    |  | own datafiles    |  | own datafiles    | |
|  +------------------+  +------------------+  +------------------+ |
+------------------------------------------------------------------+
                   Shared CDB-level infrastructure
                  (for example, control/redo logging)
~~~

A PDB is not a single schema. **A single PDB can contain multiple schemas**, along with their corresponding tables, indexes, views, procedures, accounts, roles, and data. From the perspective of most applications, connecting to a PDB looks just like connecting to a regular database.

However, a PDB is also not an independent Oracle instance: in a single-instance CDB, multiple PDBs share the SGA memory and background processes. Therefore, multitenant provides **isolation at the database/container level**, rather than automatically guaranteeing that each application has dedicated hardware resources or separate OS processes.

### 1.2. Distinguishing Four Commonly Confused Concepts

| Concept | Example | Nature |
| --- | --- | --- |
| **Oracle instance** | Instance with SID `ORCLCDB` | The SGA together with the background processes serving the database |
| **CDB** | Database `ORCLCDB` | The physical database comprising root, seed, and PDBs; has CDB control files and online redo logs |
| **PDB** | `LABPDB` | A container holding its own data, schemas, and metadata serving one or more applications |
| **Database service** | `LABPDB`, or another service name created by the DBA | A name used by clients to connect and get routed to the target PDB/container |

The names of **SID**, **CDB**, **PDB**, and **service** sometimes coincide due to installation defaults, but their meanings are different. For example, `sqlplus / as sysdba` on the server host may connect locally to the instance and start in `CDB$ROOT`, whereas `sqlplus app_user@//db-host:1521/LABPDB` connects through the listener to the **PDB's service**. Setting `ORACLE_SID=LABPDB` does not turn a PDB into a separate instance.

## 2. Three Container Types and Their Relationships

| Characteristic | `CDB$ROOT` | `PDB$SEED` | User PDB, e.g. `LABPDB` |
| --- | --- | --- | --- |
| Role | Root of the CDB and place for administering shared information | Standard system template for creating new PDBs | Environment containing application data and objects |
| Default name | `CDB$ROOT` | `PDB$SEED` | Named by the DBA/creator |
| Typical `CON_ID` | `1` | `2` | `3` and above |
| Contains data dictionary? | Yes, including shared CDB metadata | Yes, template metadata base for cloning | Yes, PDB's own metadata and ability to reference shared metadata |
| Datafiles | Has root system files | Has seed system files | Has the PDB's own files (SYSTEM, SYSAUX, and data/tablespaces depending on configuration) |
| Contains application tables? | Typically **no** | **Not used** for creating application data | **Yes**, this is the appropriate place |
| Open mode | Root is open to serve the CDB | Maintained as read-only by design | Can be `MOUNTED`, `READ ONLY`, or `READ WRITE` depending on the moment |
| Common operations | Managing PDBs, common users, shared resources | Used by Oracle as a template when creating PDBs | DDL/DML, PDB-scoped backup/recovery, managing schemas and users |

Note on `CON_ID`: in many dynamic performance views, `CON_ID=0` indicates data applying to the **entire CDB** or the entire database depending on the view's context; `1` corresponds to root, `2` corresponds to seed. Do not interpret `CON_ID=0` as a fourth PDB.

### 2.1. `CDB$ROOT`: The Root Container and Shared Administration

The **CDB root** is the central container holding metadata and Oracle-managed components to coordinate PDBs. It includes:

- Common data dictionary objects, identifying information, and the structure of the CDB.
- Metadata about PDBs, resource management information, and common objects per Oracle mechanisms.
- Common users/roles and privileges declared at the appropriate scope.
- Infrastructure to execute CDB administration commands such as listing PDBs or opening/closing PDBs.

The root typically has its own system tablespaces such as `SYSTEM` and `SYSAUX`. The fact that a metadata object is shared **does not mean all data of all PDBs resides in the root**. Each PDB still has its own files and storage structures.

**Important rule:** Do not use `CDB$ROOT` as an application database. DBAs operate in the root to administer the CDB and PDBs; business tables, application schemas, and application users should be created in the designated PDB. Being in the wrong container when running DDL can create the wrong type of user, cause privilege errors, or operate on a broader scope than intended.

The root is not created from the seed like a user PDB. The root is a core component present from the moment the CDB is initialized, while the seed provides the starting point for **new PDBs**.

### 2.2. `PDB$SEED`: The Read-Only Template of the CDB

The **PDB seed** is a system-supplied PDB inside the CDB provided by Oracle to serve as a **template for creating PDBs**. The seed has the structural base and data dictionary required for a new PDB, allowing the PDB creation process to use a consistent starting point.

Typical relationship:

~~~text
                       CDB$ROOT
                          |
                    manages PDBs
                          |
         +----------------+--------------------+
         |                                     |
         v                                     v
  PDB$SEED (template)               Existing PDBs in the CDB
         |                                     ^
         | CREATE PLUGGABLE DATABASE           |
         +------> clone/create system files ---+
                       of the new PDB
~~~

The seed usually has the fixed name `PDB$SEED` and `CON_ID=2`. It is protected in **read-only** mode and is not meant for application connections or data modifications like a normal PDB. Do not create users, business tables, or manually modify seed datafiles to "set defaults" for all new PDBs.

When creating a PDB by default from the seed, Oracle creates copies/initializes the necessary files and metadata for the new PDB (the physical copy method may vary by storage type). From then on, the PDB has its **own identity, datafiles, and lifecycle**. Changes you make in the new PDB **do not propagate back to modify the seed**, and DML in this PDB does not automatically replicate to other PDBs.

The seed **is not**:

- A backup of the entire CDB or of running PDBs.
- A test database for trying out DML.
- A place to store all shared application data.
- A continuously synchronized replica of user PDBs.

### 2.3. User PDB: The Database Environment for Applications

A user PDB such as `LABPDB` contains:

- **Local** users, roles, and privileges; some common objects may be visible per Oracle mechanisms.
- Schema objects: tables, indexes, views, sequences, packages, procedures, triggers, and many other objects.
- Dedicated tablespaces and datafiles for the PDB's data; appropriate dedicated system files.
- Object metadata and settings applied at the PDB scope.
- Services for clients to connect; each PDB can have multiple configured services.

Example:

~~~text
CDB: ORCLCDB
 |
 +-- CDB$ROOT                (CDB administration)
 +-- PDB$SEED                (read-only template)
 +-- LABPDB                  (practice PDB)
 |    +-- LAB_USER schema
 |    |    +-- ORDERS
 |    |    +-- ORDER_ITEMS
 |    +-- AUDIT_USER schema
 |    +-- SYSTEM / SYSAUX / USERS tablespaces
 |
 +-- REPORTPDB               (separate reporting PDB)
      +-- REPORT_USER schema
      +-- REPORTS table
~~~

`LAB_USER` and `AUDIT_USER` are just examples of **schemas/users within one PDB**. Separating users into schemas **does not create additional PDBs**. Conversely, creating `REPORTPDB` creates a new container with its own metadata, users, and data scope.

## 3. Boundary Between Shared and Dedicated Components

### 3.1. Shared Instance, Container-Level Data Isolation

In a **single-instance** CDB, PDBs share:

- The SGA, background processes, and database processing infrastructure of the instance.
- The CDB's control files and CDB-level online redo log system.
- Administration, monitoring infrastructure, and many Oracle backup/recovery mechanisms.
- CPU, memory, I/O, and physical resources according to the environment's allocation policies.

Each PDB has:

- Datafiles, tablespaces, and object data/metadata tied to its container.
- Local users/schemas, objects, and corresponding privileges.
- Its own `OPEN`/`MOUNTED` state and connection services.
- Certain parameters that can be changed at the PDB scope within Oracle-allowed limits.

~~~text
                    SHARED INSTANCE / CDB
          +-------------------------------------+
          | SGA, LGWR, DBWR, SMON, PMON, ...   |
          | CDB control file, online redo logs  |
          +------------------+------------------+
                             |
          +------------------+------------------+
          |                  |                  |
          v                  v                  v
      CDB$ROOT           PDB: SALES        PDB: REPORT
     datafiles           datafiles          datafiles
     root metadata       user objects       user objects
~~~

Because redo is managed at the CDB level, a single online redo log can contain redo related to multiple PDBs. Business data still resides in the datafiles of the respective container. PDB storage architecture has additional details depending on version (for example, local undo versus shared undo); do not assume every internal structure has a single file per PDB.

**Operational consequence:** If the instance or a CDB-level component suffers a severe failure, multiple PDBs can be affected simultaneously. Logical isolation between PDBs does not replace backups, privilege separation, and system-level high-availability design.

### 3.2. Data Dictionary: Shared Yet Bounded

The Oracle data dictionary contains information about objects, users, privileges, tablespaces, the database, and other metadata. In multitenant:

- The root stores CDB-level shared objects and metadata.
- A PDB has its own metadata about its objects.
- Oracle uses **metadata links** and **data links** for certain common objects, avoiding unnecessary duplication and providing an appropriate view within each container.
- A PDB normally sees the data of the **current container** via `DBA_*`, `ALL_*`, and `USER_*` views; many `CDB_*` views in the root can aggregate data across multiple containers and provide the `CON_ID` column.

Do not assume that the root can view every business table with a simple `SELECT * FROM table` as if every schema resided in the root. Viewing metadata and data across PDBs must still obey view mechanics, privileges, PDB open status, and the account's container-data policies.

### 3.3. Security and Resource Isolation

PDBs help isolate users/schemas, configurations, and many management operations. However:

- A **common user** can have a scope spanning multiple containers if granted appropriate privileges.
- Common/system privileges must not be granted by default to application users.
- PDBs share an instance and can still impact each other's resources without Resource Manager and proper limits.
- Host permissions, filesystem permissions, and CDB administration are critical boundaries beyond SQL privileges inside a PDB.

Therefore, using PDBs is a way to organize multiple database environments within the same CDB, **not a guarantee that they are as completely independent as separate servers**.

## 4. Connecting: From Client to the Right PDB

### 4.1. Why Connect to a PDB via Service?

External clients do not need to know datafile names or the seed's location. They connect to the listener using an address and a **service name** registered by the database or configured by the DBA. The service identifies the target database environment.

~~~text
Client SQL*Plus
    |
    | user@//db-host.example.com:1521/LABPDB
    v
Oracle Net Listener
    |
    +--- service LABPDB ---> PDB LABPDB
    |
    +--- service REPORT_SVC ---> PDB REPORTPDB
~~~

In many installations, when a PDB is created, Oracle creates a default service matching the PDB name. Production systems may use DBA-defined services with names **different from the PDB name**, so always verify the correct service information instead of guessing.

Example connecting to a PDB via SQL*Plus:

~~~bash
# Run on a machine with SQL*Plus client; replace host, service, and user according to your system.
sqlplus lab_user@//db-host.example.com:1521/LABPDB
~~~

SQL*Plus will prompt for the password for `lab_user`; do not pass passwords directly in command arguments. The `lab_user` account must exist in the targeted container/service and have the appropriate `CREATE SESSION` privilege.

Upon successful connection:

~~~sql
SHOW CON_NAME;

SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

The expected result in the example is `CONTAINER_NAME = LABPDB` and `SESSION_USER = LAB_USER`. Checking the container is especially useful when you have multiple dev/test/prod environments using the same schema names.

### 4.2. Local Connection for DBAs

On the **database server** with the appropriate Oracle Home/SID and an OS account holding OSDBA privileges:

~~~bash
# Local connection; only for users with administrative privileges.
sqlplus / as sysdba
~~~

With a CDB, a local administrative session typically starts in `CDB$ROOT`:

~~~sql
SHOW CON_NAME;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

If the result is `CDB$ROOT`, you are in the **root**; do not run commands to create application tables, application users, or drop business objects as if you were inside a PDB. In remote environments or different authentication configurations, the initial container depends on how you connect; always verify instead of relying on the SID name.

### 4.3. Switching Containers for Administrative Accounts

A common administrative user with the necessary privileges can change the current container:

~~~sql
-- Only execute in an administrative session granted the required privileges.
SHOW CON_NAME;

ALTER SESSION SET CONTAINER = LABPDB;
SHOW CON_NAME;

-- Return to root if the account and privileges allow.
ALTER SESSION SET CONTAINER = CDB$ROOT;
SHOW CON_NAME;
~~~

`ALTER SESSION SET CONTAINER` is not a default privilege for a local user. Applications should **connect directly to the PDB service**, rather than switching containers via CDB administrative privileges. In a `SYSDBA` session, user/schema names and privileges have sensitive scope; do not use this type of session for regular application DML operations.

## 5. Inspecting CDB Structure with Read-Only Queries

The following examples are for SQL*Plus or a compatible SQL tool, usually requiring a DBA account or granted privileges to read `V$`/`CDB_*` views. If learning on a shared system, ask the DBA to provide equivalent outputs; do not grant `SYSDBA` to an application account just to read a few views.

### 5.1. Confirming This Is a CDB

~~~sql
SELECT name, cdb, open_mode
FROM v$database;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

In `V$DATABASE`, the `CDB` column typically returns `YES` for a container database. `OPEN_MODE` reflects the database state; the open state of **each PDB** must be checked separately. Legacy systems may have a non-CDB configuration; when `CDB=NO`, the root/seed/PDB concepts in this lesson do not apply in the same way.

### 5.2. Listing Root, Seed, and User PDBs

Execute in the root with appropriate privileges:

~~~sql
SELECT con_id, name, open_mode, restricted
FROM v$containers
ORDER BY con_id;

SHOW PDBS;
~~~

An **illustrative** output, not a required output on every machine:

~~~text
CON_ID  NAME       OPEN_MODE
------  ---------  ----------
1       CDB$ROOT   READ WRITE
2       PDB$SEED   READ ONLY
3       LABPDB     READ WRITE
4       REPORTPDB  MOUNTED
~~~

Key identifiers:

- `CON_ID=1`: root.
- `CON_ID=2`: seed; typically in `READ ONLY` state.
- `CON_ID>=3`: other PDBs, with IDs assigned by Oracle within the CDB.
- `OPEN_MODE=MOUNTED`: the PDB is not yet open to serve normal application queries.
- `OPEN_MODE=READ ONLY`: the PDB is open for reading.
- `OPEN_MODE=READ WRITE`: the PDB is open for performing DML/DDL if the user has privileges.

`CON_ID` is an identifier within the CDB context, **not a persistent business identifier when moving a PDB between CDBs**. Other identifiers such as PDB GUID are used in certain migration/recovery administrative tasks.

### 5.3. Listing PDBs and Open Times

~~~sql
SELECT con_id, name, open_mode, restricted, open_time
FROM v$pdbs
ORDER BY con_id;
~~~

`V$PDBS` is a view dedicated to PDBs; in a root administrative session, it lets you observe the PDB seed and existing user PDBs. If a PDB is `MOUNTED`, that is **not automatically an error**: the PDB may not have been opened after an instance restart or may have been intentionally closed by the DBA.

### 5.4. Checking Which Container Owns Which Datafiles

In the root, when you need to know which datafiles belong to root/seed/PDBs, you can use:

~~~sql
SELECT con_id, file#, name, status
FROM v$datafile
ORDER BY con_id, file#;
~~~

For example, rows with `CON_ID=1` belong to root; `CON_ID=2` belong to seed; `CON_ID=3` may belong to `LABPDB` if that PDB currently holds ID 3. File paths may be on the filesystem, Oracle Managed Files (OMF), or ASM (starting with `+DATA`…). **Do not move or delete files directly at the OS level** based on query results; Oracle manages the metadata and consistency of these files.

### 5.5. Identifying Metadata Scope in the Root

Many CDB dictionary views have a `CON_ID` column, helping administrators see which container a record belongs to. For example, if privileges and PDB state permit:

~~~sql
SELECT con_id, username, common
FROM cdb_users
WHERE username IN ('SYS', 'SYSTEM', 'LAB_USER')
ORDER BY con_id, username;
~~~

The same name `SYS` or `SYSTEM` can appear in multiple containers with different `CON_ID` values due to common/system account properties and metadata mechanisms. `LAB_USER`, if created locally in `LABPDB`, belongs only to that PDB's scope. Actual results also depend on query privileges, whether the PDB is open or closed, and related policies.

## 6. Common Users, Local Users, and Privilege Boundaries

### 6.1. Local Users

A **local user** belongs to a single PDB. For example, `LAB_USER` can own the `ORDERS` table in `LABPDB`. A local user does not become a user of the root or other PDBs simply because the containers reside in the same CDB.

A PDB administrator can be granted appropriate privileges to create local users, grant roles, and manage schemas within the PDB. When creating a user inside a PDB, the command takes effect **in the current PDB**; before every administrative operation, check `SHOW CON_NAME`.

### 6.2. Common Users

A **common user** is an account managed at the CDB scope and can exist across multiple containers, with operational capabilities depending on granted privileges and how they are granted. In the default configuration, common users created by a DBA in the CDB root usually must have a prefix such as `C##` (per `COMMON_USER_PREFIX`); Oracle provides its own common/system accounts.

This explains a common error when beginners log into `CDB$ROOT` and try to create a normal application user:

~~~sql
-- EXAMPLE NOT TO RUN: in root, creating a local user
-- may be rejected due to the common-user naming rule.
CREATE USER app_user IDENTIFIED BY "example_password";
~~~

On typical installations, `ORA-65096: invalid common user or role name` may appear because the user is being created in the root without a name matching common user rules. **The solution for application schemas is to switch to the right PDB via service or an administrative session, not to alter `COMMON_USER_PREFIX` to bypass the rule.**

`CONTAINER=ALL` and `CONTAINER=CURRENT` in certain common user/privilege operations are different administrative mechanisms; do not assume a privilege granted in the root automatically gives an application full privileges in every PDB. Common users should be granted least privilege, especially in environments holding data from multiple teams.

### 6.3. Local Roles and Common Roles

Like users, a role can be local or common depending on where it is created and its scope. Local roles are used within a PDB, while common roles are designed for use across multiple containers when properly administered. Looking at a role name alone is not enough to determine its scope; check the appropriate dictionary views and the `COMMON` column.

### 6.4. Checking the Container Before DDL

A safe habit:

~~~sql
SHOW CON_NAME;

SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;

-- Only run DDL after confirming the right PDB and privileges.
~~~

When operating multiple PDBs with identical schema/table names, checking the container name is part of data protection, not merely a convenience step.

## 7. Lifecycle of a PDB

### 7.1. Creating a PDB from Seed

A conceptual workflow to create a new user PDB is:

~~~text
CDB$ROOT
    |
    | CREATE PLUGGABLE DATABASE ...
    v
PDB$SEED as template
    |
    | Oracle creates datafiles and metadata for the new PDB
    v
New LABPDB (initially usually MOUNTED)
    |
    | ALTER PLUGGABLE DATABASE LABPDB OPEN
    v
LABPDB READ WRITE
    |
    +--> create local users, schemas, tablespaces, applications
~~~

A **PDB created from seed** is not a copy of another user PDB. When cloning from a source PDB, Oracle uses the source PDB's metadata/datafiles in its own workflow; when unplugging/plugging, a PDB is detached from/attached to a compatible CDB. All three can result in a PDB, but **the sources and operational requirements differ**.

In practice, creating a new PDB requires:

- A DBA account with administrative privileges in `CDB$ROOT`.
- An open CDB and properly configured file-creation environment (Oracle Managed Files, ASM, or file-name conversion rules).
- Storage capacity, version compatibility, and usage rights per system policy.
- A plan for provisioning services, admin users, backups, and resource limits upon use.

### 7.2. Example Commands to Create/Open a PDB in a Dedicated Lab

**Read this section only as an administrative operation template.** If granted privileges on an **independent lab CDB**, use real values and follow your installation's file management method. The example below assumes Oracle Managed Files is configured so Oracle determines where to create datafiles:

~~~sql
-- DBA session at CDB$ROOT on a dedicated lab.
SHOW CON_NAME;
SHOW PARAMETER db_create_file_dest;

-- Replace the sample password with a strong password and do not store it in shared logs/scripts.
CREATE PLUGGABLE DATABASE LABPDB
    ADMIN USER LAB_ADMIN IDENTIFIED BY "ReplaceWithStrongPassword_123";

-- After creation, the PDB usually needs to be opened.
ALTER PLUGGABLE DATABASE LABPDB OPEN READ WRITE;

-- Save the open state so Oracle can restore it after an instance restart.
ALTER PLUGGABLE DATABASE LABPDB SAVE STATE;
~~~

If `DB_CREATE_FILE_DEST` is not configured and Oracle lacks a suitable file-naming mechanism, the `CREATE PLUGGABLE DATABASE` template above may fail; filesystem-based environments may require `FILE_NAME_CONVERT` or another file-creation configuration. **Do not run commands just to test syntax in production**, because `CREATE PLUGGABLE DATABASE` actually creates a container and datafiles, while `OPEN`/`SAVE STATE` changes operational state.

The password in the example is an illustrative value that must be replaced before use. When designing a real environment, avoid putting plaintext passwords in shared documentation, command history, or logs; use an organization-supported secrets management process.

### 7.3. Opening and Closing a PDB

A PDB can be opened or closed by a DBA independently of other PDBs at the appropriate level:

~~~sql
-- Only for a DBA session in the root; do not run on a PDB actively serving users.
ALTER PLUGGABLE DATABASE LABPDB OPEN READ WRITE;

-- Close the PDB, interrupting sessions/applications currently using this PDB:
ALTER PLUGGABLE DATABASE LABPDB CLOSE IMMEDIATE;
~~~

Closing a PDB can interrupt running work and cause application errors. Do not perform this on a shared/production PDB without a plan. The primary impact is focused on the specified PDB, though the CDB and infrastructure components remain shared resources.

The `OPEN` state of the CDB **does not mean every PDB is open**. After an instance restart, a PDB may return to `MOUNTED` if there is no corresponding saved state or auto-open mechanism. `ALTER PLUGGABLE DATABASE ... SAVE STATE` is one way to persist the intended open state for a PDB; details depend on the configuration and instance management environment.

### 7.4. Clone, Unplug, and Plug at a Conceptual Level

| Operation | Source | Meaning |
| --- | --- | --- |
| **Create from seed** | `PDB$SEED` | Creates a new PDB with a clean system base, containing no application data |
| **Clone PDB** | A source PDB | Creates a new PDB based on the state/data of the source PDB, subject to clone conditions |
| **Unplug PDB** | Existing PDB | Prepares metadata and files for moving/plugging via supported procedures |
| **Plug PDB** | Unplugged PDB or compatible source | Attaches a PDB to another CDB or the same CDB under supported conditions |

Unplugging/plugging is not just copying datafile directories in a file explorer. Oracle requires descriptive metadata, compatibility checks, and database operation sequences; paths, services, character sets, versions, options, encryption, and storage configurations may all be prerequisites to handle. Always have a backup and an appropriate transition plan before operating on critical PDBs.

Beyond standard user PDBs, some versions/features also offer an **application container** with an application root, application seed, and application PDBs. This is a specialized organizational level for managing shared applications; do not confuse an application root/application seed with **`CDB$ROOT`/`PDB$SEED`**, which belong to the overall CDB.

## 8. Backup, Recovery, and Impact Across PDBs

Because multiple PDBs share CDB infrastructure, incident scope and recovery scope must be distinguished:

| Scenario | Typical Impact Scope | Meaning |
| --- | --- | --- |
| A user accidentally drops a table in `LABPDB` | Data/operations in the affected PDB | Recoverability depends on backups/recovery, privileges, and enabled features |
| A datafile of a PDB is lost | The corresponding PDB/tablespace may stop working | May require restoring/recovering the file or PDB depending on the incident |
| Instance crash | All PDBs served by that instance are interrupted | Oracle uses redo/control files and CDB-level instance recovery upon restart |
| Control file or critical online redo is corrupted | May affect the entire CDB | Individual PDBs cannot be treated as completely independent physical databases |
| Severe failure in root or CDB infrastructure | Multiple or all PDBs may be affected | Requires CDB-level protection/recovery strategy |

Oracle Recovery Manager (**RMAN**) can support backup/recovery operations at both CDB and PDB scope depending on version/configuration. Having a separate PDB **does not automatically mean having separate backups**. An operational design must consider datafile backups, control files, archived redo, retention, RPO/RTO, and restore testing.

In multitenant, online redo logs are managed at the CDB level; redo records can relate to multiple PDBs. Therefore, the ability to recover a PDB to a given point in time still depends on the redo infrastructure and Oracle-supported recovery conditions. Never delete archived redo just because "my PDB isn't using this file."

## 9. Hands-On Practice: Identifying Root, Seed, and PDB Relationships

This section prioritizes **reading and observing** and can be performed on an existing CDB. The exercise does not require creating a new PDB. If your account is not permitted to view administrative views, ask the DBA to run the corresponding queries and provide the outputs.

### Step 1 — Identify the Current Session's Container

Connect using SQL*Plus or a suitable SQL tool and run:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

If using SQL*Plus, you can also run `SHOW CON_NAME;`. When you see a PDB name such as `LABPDB`, note it down. If the result is `CDB$ROOT`, that is a root session, which is not suitable for practicing creating application tables.

### Step 2 — Observe All Containers from the Root

Under a sufficiently privileged administrative session:

~~~sql
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;
~~~

Identify the three groups: root (`1`), seed (`2`), and user PDBs (`3` and above). Count the existing user PDBs excluding root and seed. Do not assume this count is fixed across all environments.

### Step 3 — Observe the PDB Seed

From the `V$CONTAINERS` or `SHOW PDBS` output, confirm `PDB$SEED` is marked `READ ONLY` by design. Do not attempt to create tables or modify users in the seed; the exercise only requires explaining **why the seed should remain immutable** for business operations.

### Step 4 — Verify the Application PDB State

From the root:

~~~sql
SELECT name, open_mode, restricted
FROM v$pdbs
WHERE name = 'LABPDB';
~~~

If no rows are returned, `LABPDB` may not exist or may not be the PDB name on this system. Replace `LABPDB` with the actual name. If `OPEN_MODE=MOUNTED`, do not proceed with application connections until the DBA confirms the PDB is allowed to be opened.

### Step 5 — Connect to the PDB via Service

From the client machine:

~~~bash
sqlplus lab_user@//db-host.example.com:1521/LABPDB
~~~

After logging in and entering the password at the prompt:

~~~sql
SHOW CON_NAME;

SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    USER AS current_user
FROM dual;
~~~

Explain why `CON_NAME` and `CURRENT_USER` here differ from the DBA session in the root. If an application has multiple services pointing to the same PDB, `SERVICE_NAME` can be completely different from the PDB name while `CON_NAME` remains the expected container.

### Step 6 — Cross-Check Datafile Structure

In a privileged root session:

~~~sql
SELECT con_id, COUNT(*) AS datafile_count,
       ROUND(SUM(bytes) / 1024 / 1024) AS datafile_mb
FROM v$datafile
GROUP BY con_id
ORDER BY con_id;
~~~

The output shows that containers have separately managed groups of datafiles. The `DATAFILE_MB` figure is the total allocated size of the declared datafiles, **not the actual application data size** or free space remaining.

### Step 7 — Map Out the Architecture Model

Complete the diagram based on the data you just observed:

~~~text
Actual CDB: ________________________
Instance/SID: ______________________
Root: CDB$ROOT (CON_ID=1)
Seed: PDB$SEED (CON_ID=2)
User PDBs: _________________________
PDB used for practice: _____________
Service used to connect: ___________
CON_NAME of application session: ___
~~~

The instance identifier can be obtained via `V$INSTANCE` if permitted; **do not infer it from the service name**. The exercise is complete when you can explain why a single CDB and a single instance can still host multiple PDBs that are independent in schemas and data.

## 10. Common Misconceptions and Isolation Diagnostics

| Symptom | Possible Cause | Approach |
| --- | --- | --- |
| `ORA-65096` when creating a user like `APP_USER` | Currently in root and the username is invalid for a common user | `SHOW CON_NAME`; create a local user in the right PDB per privileges and procedures |
| `ORA-65011` | The specified PDB name does not exist in the CDB/context | Check `V$PDBS`/`V$CONTAINERS` and spelling of the PDB name |
| `ORA-65040` | Attempted an operation not permitted in the current PDB/container | Determine whether the command must run in root or PDB; use the appropriate account |
| `ORA-12514` when connecting via PDB service | Listener does not yet know the requested service | Verify service name, PDB open status, listener, and service registration |
| CDB is open but cannot connect to PDB | PDB is still `MOUNTED`, service is unavailable, or user is invalid | Check `V$PDBS.OPEN_MODE`; verify service and login credentials |
| Login succeeds but table is not visible | In a different PDB/schema or missing privileges | Check `CON_NAME`, `USER`, schema owner, and privileges |
| DBA created table in root, application PDB cannot see it | Ran DDL in the wrong container | Check `SHOW CON_NAME` before operating; reorganize objects per DBA procedures |
| After restart PDB returns to `MOUNTED` | Missing saved open state configuration or other management mechanism | DBA checks `SAVE STATE` and how the instance is started |

Some errors have multiple causes; error codes help narrow down the issue but are not enough to immediately confirm a specific configuration. Observe the container, service, and PDB state **before modifying parameters or running administrative commands**.

### 10.1. Misconception: "A PDB Is Just a Schema"

A PDB contains multiple schemas; a schema is a set of objects owned by a user. Switching schemas does not create a new PDB, whereas creating a new PDB creates a container boundary with separate files and metadata.

### 10.2. Misconception: "The Root Holds All Application Tables"

The root holds CDB-level shared metadata and objects. Business tables belong in a PDB. A CDB dictionary view in the root may display metadata across multiple PDBs depending on privileges, but that **does not turn the root into a shared schema for all PDBs**.

### 10.3. Misconception: "The Seed Updates Automatically When a PDB Changes"

The seed is an Oracle-managed template. Once created, each PDB has its own lifecycle and data; `INSERT/UPDATE` operations in one PDB do not modify the seed, the root, or other PDBs.

### 10.4. Misconception: "Each PDB Has Its Own Instance and Redo Logs"

In a single-instance CDB, PDBs share the SGA, background processes, control files, and online redo logs at the CDB level. A PDB has its own datafiles and metadata, but does not have an independent instance like a separately installed database on the OS.

### 10.5. Misconception: "A PDB Opens Automatically When the CDB Opens"

The CDB being `OPEN` does not mean every PDB is `READ WRITE`. Inspect `V$PDBS`/`V$CONTAINERS` and manage PDB states according to operational policies.

## 11. Review Questions

1. What types of containers make up a CDB? Why is `PDB$SEED` not used as an application database?
2. When `LABPDB` is created from seed, does `LABPDB`'s subsequent data write back into the seed?
3. A PDB contains two schemas, `APP_USER` and `REPORT_USER`. How many databases/instances are in that PDB?
4. How does `CDB$ROOT` differ from a user PDB in role, metadata, and where business tables should be placed?
5. Is `CON_ID=0` in some `V$` views the name of a PDB?
6. Why should a DBA check `SHOW CON_NAME` before running `CREATE USER` or `ALTER PLUGGABLE DATABASE`?
7. If both `SALES_PDB` and `REPORT_PDB` reside in the same CDB instance, which PDBs are affected by an instance crash?
8. How can an application connect directly to a PDB using a service instead of using `ALTER SESSION SET CONTAINER`?
9. Why can the same PDB have multiple service names, and why can a service name different from the PDB name still be valid?
10. Can a `MOUNTED` PDB serve normal application DML queries? Which state is appropriate?
11. Why can moving a PDB to another CDB not be treated simply as copying datafiles at the OS level?
12. A CDB has backups, but the user PDB has never been restore-tested. What risk still remains?

**Answer hints:** (1) root, seed, user PDB; seed is a read-only template; (2) no; (3) one PDB containing two schemas and using the CDB instance serving it; (4) root handles shared administration, user PDB holds business data; (5) no, it usually represents CDB-wide scope; (6) to avoid operating on the wrong scope; (7) all PDBs served by that instance may be interrupted; (8) use the connect string `user@//host:port/service`; (9) a service is a routing name configurable by the DBA; (10) no, the PDB must be opened appropriately, usually `READ WRITE` for DML; (11) metadata, compatibility, and plug-in procedures are required; (12) having a backup does not prove restore and recovery will succeed.

## Oracle References

- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): fundamentals of multitenant architecture, instances, and database components.
- [Oracle Multitenant Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/): managing CDB, root, seed, PDBs, common/local users, lifecycle, cloning, and unplug/plug.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): reference for `V$DATABASE`, `V$CONTAINERS`, `V$PDBS`, `V$DATAFILE`, and related parameters.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): syntax for `CREATE PLUGGABLE DATABASE`, `ALTER PLUGGABLE DATABASE`, and `ALTER SESSION`.
