# Parameter and Metadata Scope in CDB vs. PDB in Oracle Database

## 1. Why Can the Same SQL Statement Return Different Results in Root and a PDB?

Suppose an Oracle Database system has a **CDB** named `CDB01` and two **PDBs** named `SALES_PDB` and `HR_PDB`. A DBA connects to `CDB$ROOT`, inspects the `STATISTICS_LEVEL` parameter, and lists tables using `DBA_TABLES`. An application connects to `SALES_PDB`, runs seemingly identical queries, and sees a different parameter value or table list. Meanwhile, a monitoring account in the root querying `CDB_TABLES` may see information from both PDBs, whereas the application account sees only one PDB's scope.

This is by design in **Oracle Multitenant**, not necessarily lost data or misconfigured parameters. In a CDB, some settings apply at the database/instance level; some are **inherited from the root but overridable at the PDB level**; and metadata objects are displayed based on **current container, access privileges, and view type**.

This lesson focuses on two questions:

1. **Parameter scope:** When reading or changing an initialization parameter, does that value belong to the root, an individual PDB, an instance, a session, or is it inherited? Does it persist across closing/reopening a PDB?
2. **Metadata scope:** When reading `USER_*`, `ALL_*`, `DBA_*`, `CDB_*`, and `V$`/`GV$`, which container's data is the query seeing? Why does prefixing `CDB_` not guarantee seeing every PDB?

> Examples use Oracle Database 19c syntax; concepts apply to newer releases when cross-checked against the corresponding documentation. Container names, services, and configuration values are illustrative. The `ALTER SYSTEM` and `ALTER SESSION SET CONTAINER` commands in the hands-on section have different impacts; run modification steps only in a lab environment with granted privileges.

## 2. Understanding the CDB Structure Before Discussing Scope

```text
                      Oracle Database CDB01
                 (instance, SGA, background process)
                                │
        ┌───────────────────────┼────────────────────────┐
        │                       │                        │
        ▼                       ▼                        ▼
   CDB$ROOT                 PDB$SEED                  User PDBs
   CON_ID = 1              CON_ID = 2             ┌───────────────┐
        │                       │                 │ SALES_PDB     │
        │                       │                 │ CON_ID = 3    │
        │                       │                 │ Tables/users  │
        │                       │                 ├───────────────┤
        │                       │                 │ HR_PDB        │
        │                       │                 │ CON_ID = 4    │
        │                       │                 │ Tables/users  │
        │                       │                 └───────────────┘
        │                       │                        │
        ├── Shared metadata     └─ Template PDB          │
        │   and resources                                │
        │                                                │
        └───── PDBs inherit eligible parameters ─────────┘
               (some PDBs have dedicated overrides)
```

| Component | Role | Typical Scope |
| --- | --- | --- |
| **CDB** | Multi-container database; physical/instance infrastructure and shared resources | Entire CDB, potentially including application PDBs |
| **`CDB$ROOT`** | Root container holding metadata, common users, and CDB admin config | Place to run CDB-wide operations and query cross-PDB metadata when sufficiently privileged |
| **`PDB$SEED`** | Template PDB used by Oracle when creating new PDBs | Not an application PDB for creating business tables |
| **User PDB** | Dedicated container holding schemas, data, and a subset of configuration | One PDB independent in namespace, many privileges, and schema objects |
| **Application root / application PDB** | Application tier in an application container (if used) | Has similar inheritance and metadata/data link mechanisms, plus an application root layer |

In the multitenant architecture, **each PDB does not have its own dedicated instance and redo logs**. A CDB has one or more instances depending on topology; PDBs share many infrastructure components. However, each PDB has its own logical schema and data space, with separate datafiles for its tablespaces.

### 2.1. Three Distinct Scope Concepts

| Scope | Example | Key Distinction |
| --- | --- | --- |
| **Instance scope** | Instance memory/process parameters, some `GV$` views | Can differ across RAC instances, but does not mean each PDB has its own instance |
| **Container scope** | Schema objects of `SALES_PDB`, PDB-overridable parameters | Same object/parameter name can exist across containers with different metadata/values |
| **Session scope** | `ALTER SESSION`, current schema, and session-modifiable parameters | Two sessions in the same PDB can see/apply different session settings |

Always clarify whether you are referring to **instance, container, or session** before changing configurations or interpreting output.

## 3. Identifying the Current Container Immediately Upon Login

Every Oracle session has a **current container**. When an application logs in via a PDB's service, the current container is usually the PDB pointed to by that service. When a DBA logs into the root, normal SQL runs in the root context.

**Read-only** commands to check your context:

```sql
-- SQL*Plus / SQLcl
SHOW CON_NAME;
SHOW CON_ID;

-- Standard Oracle SQL, usable in query execution tools:
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'CON_ID')   AS con_id,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM   dual;
```

Example:

```text
CON_NAME   CON_ID  SERVICE_NAME
---------  ------  ------------------------
SALES_PDB  3       sales_app.example.com
```

If an account/common user holds appropriate privileges, a DBA can switch the current container:

```sql
-- Session context-switching command: only for accounts with SET CONTAINER privilege.
ALTER SESSION SET CONTAINER = SALES_PDB;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name FROM dual;

-- When returning to root if authorized:
ALTER SESSION SET CONTAINER = CDB$ROOT;
```

Switching containers does not automatically grant privileges to view data or perform administrative tasks in the target PDB. `SET CONTAINER`, `CREATE SESSION`, and object privileges must still be granted in the appropriate context. For applications, connect directly to the **PDB's service** instead of starting in the root and switching containers.

### 3.1. Observing the Container List from Root

```sql
-- Run from CDB$ROOT with appropriate view-reading privileges.
SELECT con_id, name, open_mode, restricted
FROM   v$containers
ORDER BY con_id;

-- For PDBs specifically, from root you can view PDB$SEED and user PDBs:
SELECT con_id, name, open_mode, restricted
FROM   v$pdbs
ORDER BY con_id;
```

`V$CONTAINERS` provides metadata about containers, including the root. `V$PDBS` lists PDBs associated with the **current instance**; when queried inside a PDB, `V$PDBS` shows only the current PDB rather than all PDBs. In RAC, also check the instance or use the corresponding `GV$` view when a multi-instance view is needed.

Do not equate `OPEN_MODE='READ WRITE'` with a user having permission to read every object. Visibility is still governed by privileges, current container, and object-specific policies.

## 4. Initialization Parameters: Default in Root, Selectively Overridable in PDBs

### 4.1. Inheritance Principle

Oracle uses a **parameter inheritance** model:

- **The root holds parameter values** applicable CDB-wide or to instance operations.
- **PDBs inherit by default** the corresponding value from the root when no dedicated setting exists.
- **Only a subset of parameters are allowed to be changed in a PDB.** Other parameters must inherit from the root and cannot arbitrarily take separate values per PDB.
- When a PDB is allowed to override and the DBA sets a value for it, **the PDB uses its own value** instead of continuing to inherit from the root, until inheritance is restored/reset using the proper syntax.

Illustration:

```text
                         Root: PARAM_X = A
                                │
                   ┌────────────┴─────────────┐
                   ▼                          ▼
       SALES_PDB: inherit=true         HR_PDB: inherit=false
       effective PARAM_X = A           explicit PARAM_X = B
                   │                          │
                   └────────────┬─────────────┘
                                ▼
                   Root sets PARAM_X = C

       SALES_PDB sees C if it receives the change per scope/timing rules
       HR_PDB keeps using B while the override remains in effect
```

**Key takeaway:** A DBA modifying a parameter from the root does not automatically wipe out every PDB's override. The effect depends on `CONTAINER=CURRENT` vs. `CONTAINER=ALL`, PDB overridability, `SCOPE`, and startup/open state.

### 4.2. Do Not Guess from Parameter Names; Check `ISPDB_MODIFIABLE`

Oracle Database Reference defines `V$SYSTEM_PARAMETER.ISPDB_MODIFIABLE`:

- **`TRUE`**: the parameter can be configured individually for a PDB.
- **`FALSE`**: the parameter cannot be modified from inside a PDB, so the PDB must use the configuration from the higher administrative level.

```sql
-- Read-only: determine which parameters can be set individually in a PDB.
SELECT name,
       display_value,
       ispdb_modifiable,
       issys_modifiable,
       isses_modifiable
FROM   v$system_parameter
WHERE  name IN (
           'statistics_level',
           'optimizer_mode',
           'open_cursors',
           'db_name',
           'processes',
           'sga_target'
       )
ORDER BY name;
```

The parameter names here are just **inspection inputs**; the `ISPDB_MODIFIABLE` column result on your **actual release and environment** is the basis for deciding PDB-level changes. A parameter may belong to infrastructure limits and disallow PDB overrides, whereas a query-behavior parameter may be modifiable in a PDB.

To retrieve the full list from a running database:

```sql
SELECT name,
       display_value,
       issys_modifiable,
       isses_modifiable
FROM   v$system_parameter
WHERE  ispdb_modifiable = 'TRUE'
ORDER BY name;
```

**Distinguish the three columns:**

| Column | Question Answered | Common Values |
| --- | --- | --- |
| `ISPDB_MODIFIABLE` | Can it be set individually inside a PDB? | `TRUE`, `FALSE` |
| `ISSYS_MODIFIABLE` | Can it be changed via `ALTER SYSTEM` while running, and when does it take effect? | `IMMEDIATE`, `DEFERRED`, `FALSE` |
| `ISSES_MODIFIABLE` | Can a session change it via `ALTER SESSION`? | `TRUE`, `FALSE` |

A parameter with `ISSES_MODIFIABLE='TRUE'` does not mean you can run `ALTER SYSTEM` for it in a PDB. Nor does `ISSYS_MODIFIABLE='IMMEDIATE'` **automatically mean `ISPDB_MODIFIABLE='TRUE'`**. Each column controls a different scope dimension.

### 4.3. Examples of Parameter Groups by Purpose

| Group | Examples | Scope to Consider |
| --- | --- | --- |
| Database/instance structure | `DB_NAME`, `CONTROL_FILES`, `PROCESSES` | CDB/instance infrastructure; PDBs do not own separate control files or process pools |
| Memory and resource management | `SGA_TARGET`, `PGA_AGGREGATE_TARGET`, certain PDB memory limits depending on release | Distinguish shared instance memory from supported PDB-level resource limits |
| Optimizer/session behavior | `OPTIMIZER_MODE`, `STATISTICS_LEVEL`, other optimizer behavior parameters | May support PDB-level or session-level configuration depending on parameter/release |
| Connection/session limits | `OPEN_CURSORS`, `SESSIONS`, and related limits | Read metadata to verify which parameters allow PDB overrides and local limits |
| Storage/PDB attributes | Default tablespace, storage limits, open mode, services | Many attributes are PDB metadata/properties or `ALTER PLUGGABLE DATABASE` operations, not initialization parameters |

Do not "automatically split" the SGA into a separate SGA per PDB. PDBs have resource control/limiting capabilities in certain releases and offerings, yet still live within shared instance infrastructure. Only conclude a parameter can be set per PDB when Oracle reports `ISPDB_MODIFIABLE='TRUE'` and the manual confirms applicable conditions.

## 5. `CONTAINER=CURRENT` vs. `CONTAINER=ALL` When Changing Parameters

`ALTER SYSTEM SET` in a CDB allows specifying `CONTAINER` to control the scope of a parameter change. **The current container must be confirmed first.**

| Execution Location | `CONTAINER` | Meaningful Scope | Impact on Inheritance |
| --- | --- | --- | --- |
| `CDB$ROOT` | `CURRENT` or omitted | Root value; inheriting PDBs may receive the new root value per effective rules | Does **not** actively remove existing PDB overrides |
| `CDB$ROOT` | `ALL` | Root and all PDBs in the CDB | **Resets inheritance to true** for that parameter across PDBs, potentially replacing prior overrides |
| A PDB | `CURRENT` or omitted | Current PDB only, when the parameter supports `ISPDB_MODIFIABLE=TRUE` | PDB can create/adjust its own override |
| A PDB | `ALL` | Not valid for CDB-wide changes from inside a regular PDB | Cannot widen scope to other PDBs this way |

**Illustrative syntax; do not execute in production without change approval:**

```sql
-- Run in CDB$ROOT: updates only root and PDBs still inheriting.
ALTER SYSTEM SET STATISTICS_LEVEL = TYPICAL
  SCOPE = BOTH CONTAINER = CURRENT;

-- Run in SALES_PDB: sets specifically for the current PDB (if supported).
ALTER SYSTEM SET STATISTICS_LEVEL = ALL
  SCOPE = BOTH CONTAINER = CURRENT;

-- Run in CDB$ROOT: CDB-wide scope,
-- and also reverts PDBs back to inheriting that parameter.
ALTER SYSTEM SET STATISTICS_LEVEL = TYPICAL
  SCOPE = BOTH CONTAINER = ALL;
```

**Note three different meanings of the word `ALL`:**

1. `STATISTICS_LEVEL = ALL`: this is the **parameter value**.
2. `CONTAINER = ALL`: this is the **change scope**.
3. `SCOPE = BOTH`: this is **when and where the change is saved**, not container scope.

`CONTAINER=ALL` can wipe out custom configurations across multiple PDBs. In a CDB running multiple applications, this is a major change requiring an inventory of current overrides and a rollback plan beforehand.

### 5.1. Step-by-Step Illustration Across Two PDBs

Suppose parameter X has `ISPDB_MODIFIABLE=TRUE`:

| Point in Time | Root | `SALES_PDB` | `HR_PDB` |
| --- | --- | --- | --- |
| Initial | `A` | `A` (inherit) | `A` (inherit) |
| Set `HR_PDB` specifically to `B` | `A` | `A` (inherit) | `B` (override) |
| Root sets `C`, `CONTAINER=CURRENT` | `C` | `C` (inherit) | `B` (override) |
| Root sets `D`, `CONTAINER=ALL` | `D` | `D` (inherit) | `D` (inherit, override replaced) |

The table shows the **effective value after the change takes effect per `SCOPE`/dynamic behavior**. If `SCOPE=SPFILE`, the newly saved value is not necessarily visible immediately in running sessions.

### 5.2. Do Not Confuse `CONTAINER=ALL` in Other Statement Types

`CONTAINER` also appears in `CREATE USER`, `CREATE ROLE`, `GRANT`, `REVOKE`, etc., but the exact semantics and privilege requirements **are not identical to `ALTER SYSTEM`**. For example, `GRANT CREATE SESSION ... CONTAINER=ALL` for a common user is a **common grant**, not a parameter change. Always read the specification for the statement being used.

## 6. `SCOPE=MEMORY`, `SPFILE`, `BOTH`, and Persistence Across PDB Reopen

It is not enough to know **which container is targeted**; you must also know whether the change takes **immediate effect** and **persists**.

| `SCOPE` | For a Dynamic Parameter in a PDB | Upon Closing/Reopening PDB or Restarting CDB |
| --- | --- | --- |
| `MEMORY` | Changes the running value in the PDB within the applicable scope | Not persisted as a durable PDB setting; value may revert to root/startup value |
| `SPFILE` | Writes a durable PDB setting without necessarily changing runtime value immediately | Takes effect after next PDB reopen / CDB restart |
| `BOTH` | Changes runtime value in the PDB and writes a durable setting | Persists across PDB close/open or CDB restart |

**Conditions:** Actual semantics also depend on whether the parameter is dynamic or static, whether Oracle Home uses an SPFILE or PFILE, and release-specific rules. For a **static parameter**, `SCOPE=SPFILE` is the appropriate choice to take effect at the next startup; do not force `MEMORY/BOTH` if the parameter does not allow runtime modification.

### 6.1. A PDB Does Not Have a Standalone PFILE Like a Dedicated Instance

Oracle stores PDB initialization parameter settings when using `SCOPE=SPFILE`/`BOTH` via persistent PDB parameter settings. **A text PFILE cannot hold PDB-specific initialization parameter values**. If a PDB is unplugged, persistently set PDB parameters are included in the PDB's **XML metadata** so they can be restored when plugged into another CDB per Oracle documentation.

This does not mean every PDB parameter value is stored in a file like `initSALES_PDB.ora` on the filesystem. A PDB does not own an independent instance startup process like a legacy non-CDB.

### 6.2. How to Return a PDB to Inheritance

When a parameter has been overridden in a PDB and you want to remove the dedicated setting, a DBA can use `ALTER SYSTEM RESET` in the PDB. Per 19c documentation, the effect depends on `SCOPE`:

| `ALTER SYSTEM RESET` in PDB | Effect to Understand |
| --- | --- |
| `SCOPE=SPFILE` | Removes the durable PDB setting; PDB inherits from root when reopened |
| `SCOPE=MEMORY` | Restores the in-memory value per startup/inheritance rules; if a persistent override remains, reopening the PDB may reapply it |
| `SCOPE=BOTH` | Removes the persistent override and returns the PDB to inheriting from root per Oracle rules |

```sql
-- ILLUSTRATIVE ONLY: configuration change in lab after confirming PDB context.
-- DBA must verify parameter support and potential application impact.
ALTER SYSTEM RESET STATISTICS_LEVEL
  SCOPE = BOTH CONTAINER = CURRENT;
```

Do not substitute reset with `ALTER SYSTEM SET parameter = <current root value>` if the goal is to **restore inheritance**. Setting a value equal to root inside a PDB can still create a **dedicated override**, so the next time root changes, the PDB keeps the old value. Verify the exact `RESET` semantics for your version before using it.

## 7. Three Parameter Views You Must Distinguish

| View | Primary Question | Characteristics |
| --- | --- | --- |
| **`V$PARAMETER`** | What parameter value is currently in effect for the **current session**? | Reflects `ALTER SESSION` if the session modified that parameter |
| **`V$SYSTEM_PARAMETER`** | What is the system/instance-level parameter value for the current container? | Used to check `ISPDB_MODIFIABLE` and the default configuration for new sessions |
| **`V$SPPARAMETER`** | Which parameters have been recorded in the **server parameter file/persistent settings**? | Includes `ISSPECIFIED`; does not necessarily reflect the immediate runtime value at query time |

### 7.1. Comparing Session Value and System Value

```sql
-- Read-only, from the exact container under investigation.
SELECT name,
       display_value,
       isses_modifiable,
       ispdb_modifiable
FROM   v$parameter
WHERE  name IN ('optimizer_mode', 'statistics_level')
ORDER BY name;

SELECT name,
       display_value,
       issys_modifiable,
       ispdb_modifiable
FROM   v$system_parameter
WHERE  name IN ('optimizer_mode', 'statistics_level')
ORDER BY name;
```

If a session has run `ALTER SESSION SET OPTIMIZER_MODE=FIRST_ROWS`, `V$PARAMETER` can differ from `V$SYSTEM_PARAMETER` **even within the same container**. Therefore, when comparing parameters between two applications, lock down the container first, then check for session overrides.

### 7.2. Persistent Settings and `ISSPECIFIED`

```sql
-- Read-only; this view describes the contents of the server parameter file.
SELECT con_id, sid, name, display_value, isspecified
FROM   v$spparameter
WHERE  name IN ('optimizer_mode', 'statistics_level')
ORDER BY con_id, sid, name;
```

`V$SPPARAMETER` shows settings declared persistently, but **do not use a single query against it to immediately infer the effective value for every PDB**. A PDB may be inheriting from root; a `SCOPE=SPFILE` change may not yet be active at runtime; or a PDB might not appear in the data object scope visible to the querying user. Query `V$SYSTEM_PARAMETER` inside the specific PDB being compared and verify persistent config sources per documentation.

### 7.3. `ISDEFAULT` and `ISMODIFIED` Are Not Inheritance Verification Labels

`ISDEFAULT` and `ISMODIFIED` have specific meanings regarding default values and parameters declared/modified at runtime. **You cannot rely solely on `ISDEFAULT='TRUE'` to conclude a PDB is currently inheriting from root**, nor use `ISMODIFIED` as sufficient proof that a PDB has a persistent override. Cross-check where `ALTER SYSTEM` was run, `SCOPE`, saved settings, and actual values inside the PDB.

### 7.4. RAC: One `CON_ID` Can Appear Across Multiple Instances

In RAC, parameters also have an **instance** dimension: some must be uniform, while others can vary per instance if `ISINSTANCE_MODIFIABLE` allows. When hunting for anomalies across RAC, consult `GV$SYSTEM_PARAMETER` and filter by both `INST_ID` **and** `CON_ID`, within permitted privilege scope.

```sql
-- Read-only; results depend on container context and visibility privileges.
SELECT inst_id, con_id, name, display_value
FROM   gv$system_parameter
WHERE  name = 'statistics_level'
ORDER BY inst_id, con_id;
```

In `GV$`, `INST_ID` identifies the instance while `CON_ID` identifies the container. **`INST_ID=2` is not `CON_ID=2`**; `CON_ID=2` represents `PDB$SEED` in the CDB.

## 8. Metadata and Data Dictionary: Same View Definitions, Container-Scoped Data

### 8.1. Which Metadata Lives in Root vs. in a PDB?

Oracle stores the **metadata definitions of Oracle-supplied data dictionary tables/views** primarily in the root, using internal linking mechanisms so PDBs see the appropriate dictionary. However, **records describing business objects** of a PDB reside within that PDB's scope.

For example:

```text
CDB$ROOT
  ├── Oracle-supplied metadata for dictionary views
  ├── CDB-wide common definitions/objects
  └── DBA_TABLES in root: objects belonging to root

SALES_PDB
  ├── APP.ORDERS
  ├── APP.ORDER_ITEMS
  └── DBA_TABLES in SALES_PDB: metadata of tables visible in the PDB

HR_PDB
  ├── HR.EMPLOYEES
  ├── HR.DEPARTMENTS
  └── DBA_TABLES in HR_PDB: metadata belonging to HR_PDB
```

Consequently, `SELECT ... FROM DBA_TABLES` when **current container = root** does not automatically merge metadata from `SALES_PDB` and `HR_PDB`. An application table created in `SALES_PDB` appears in `SALES_PDB`'s `DBA_TABLES` but has no corresponding row in `CDB$ROOT`'s `DBA_TABLES`.

### 8.2. Metadata Link, Data Link, Extended Data Link

Oracle Multitenant distinguishes several dictionary/common object linking mechanisms:

- **Metadata link**: an object in a PDB references metadata maintained in root/application root, while the data can belong to the PDB. With application common objects, multiple application PDBs can share one definition while holding separate data.
- **Data link**: the PDB references shared metadata **and data** stored in root/application root, per object rules.
- **Extended data link**: combines data from the application root and application PDBs within an application container when supported by the object type.

Do not confuse these mechanisms with a **database link (`DBLINK`)** used to query remote databases. Multitenant metadata/data links are internal linking mechanisms for sharing definitions and/or content across containers.

For eligible objects, the `SHARING` column in views such as `DBA_OBJECTS`/`CDB_OBJECTS` helps distinguish normal objects from shared link types:

```sql
SELECT owner, object_name, object_type, sharing
FROM   dba_objects
WHERE  owner = 'APP'
ORDER BY object_name;
```

This is a **metadata query in the current container**; to inventory across PDBs, inspect `CDB_OBJECTS` from the root with appropriate privileges and visibility.

## 9. `USER_*`, `ALL_*`, `DBA_*`, `CDB_*`: Four Layers of Dictionary Views

| View Group | Semantic Visibility Scope | Examples |
| --- | --- | --- |
| **`USER_*`** | Objects/metadata related to the current user's schema, in the current container | `USER_TABLES`, `USER_OBJECTS` |
| **`ALL_*`** | Objects the user has access to / is permitted to see, in the current container | `ALL_TABLES`, `ALL_OBJECTS` |
| **`DBA_*`** | Administrative metadata in the current container, if the account holds dictionary read privileges | `DBA_TABLES`, `DBA_USERS`, `DBA_OBJECTS` |
| **`CDB_*`** | Container data objects with a `CON_ID` column; from root can return metadata across containers per privileges and `CONTAINER_DATA` | `CDB_TABLES`, `CDB_USERS`, `CDB_OBJECTS` |

**Key takeaway:** `DBA_` means metadata breadth per **privileges in the current container**, not "the entire CDB." `CDB_` is the **multi-container** viewing mechanism, but only when queried from root with appropriate dictionary privileges and container visibility.

### 9.1. Same Table Name, Different PDBs

Suppose each PDB has a table `APP.CONFIG`:

```text
SALES_PDB.APP.CONFIG    ← metadata and rows dedicated to SALES
HR_PDB.APP.CONFIG       ← metadata and rows dedicated to HR
```

From `SALES_PDB`:

```sql
-- Reads only local metadata of the current PDB.
SELECT owner, table_name, tablespace_name
FROM   dba_tables
WHERE  owner = 'APP' AND table_name = 'CONFIG';
```

From `CDB$ROOT` with appropriate privileges and container visibility:

```sql
SELECT con_id, owner, table_name, tablespace_name
FROM   cdb_tables
WHERE  owner = 'APP' AND table_name = 'CONFIG'
ORDER BY con_id;
```

Illustrative output:

```text
CON_ID OWNER TABLE_NAME TABLESPACE_NAME
------ ----- ---------- ---------------
3      APP   CONFIG     APP_DATA
4      APP   CONFIG     HR_DATA
```

These two rows are **not an erroneously duplicated table**: they are two objects in two containers, sharing the same owner/table name while having separate namespaces and storage.

### 9.2. Querying `CDB_*` While Inside a PDB

Oracle 19c specifies that when the current container **is not root**, `CDB_*` views show only objects visible through the corresponding `DBA_*` view in the **current PDB**. Therefore, choosing `CDB_TABLES` while in `SALES_PDB` **does not grant visibility into `HR_PDB`**. To aggregate across multiple PDBs, use an appropriate administrative account from root or an explicitly authorized mechanism.

### 9.3. Do Not Use Metadata Views to Read Business Data

`CDB_TABLES` lists **metadata about tables**; it does not merge rows of `APP.ORDERS` from multiple PDBs. When cross-container application data queries are needed, dedicated mechanisms exist such as **`CONTAINERS()`** with strict object/schema/grant requirements, typically used by common users with objects prepared to exist in the relevant PDBs. Do not treat `SELECT * FROM CDB_TABLES` as equivalent to `SELECT * FROM APP.ORDERS` across the whole CDB.

## 10. The `CON_ID` Column: Container Identifier in Aggregated Results

In many `CDB_*` views and container data objects such as `V$`/`GV$`, the **`CON_ID`** column indicates which scope a row belongs to.

| `CON_ID` | Common Meaning in a CDB |
| --- | --- |
| **0** | **CDB-wide** information or non-CDB case; not the name of a PDB called `0` |
| **1** | `CDB$ROOT` |
| **2** | `PDB$SEED` |
| **3 and above** | User PDB, application root, application PDB, or other assigned container |

**Do not discard `CON_ID=0` as a data error.** In performance views, it typically denotes a summary row for the entire CDB/instance. Nor should you assume `CON_ID=3` is always `SALES_PDB`: container IDs vary by CDB, unplug/plug history, and observation time.

### 10.1. Joining Container Names from IDs

```sql
-- Run in CDB$ROOT with corresponding metadata privileges.
SELECT con_id, name, open_mode
FROM   v$containers
ORDER BY con_id;

-- Example joining container names with table metadata (requires privileges + container visibility).
SELECT c.name AS container_name,
       t.con_id,
       t.owner,
       t.table_name
FROM   cdb_tables t
JOIN   v$containers c ON c.con_id = t.con_id
WHERE  t.owner = 'APP'
ORDER BY t.con_id, t.table_name;
```

Joining by `CON_ID` is only valid within the **same CDB at the same point in time**. Do not use `CON_ID` as a durable global identifier across CDBs. If you need to track a PDB across unplug/plug operations, consider `GUID`, `DBID`, incarnation info, and PDB history as appropriate for your goal.

### 10.2. `INST_ID` Is Different from `CON_ID`

`GV$` views usually add `INST_ID` to identify the RAC instance; `CON_ID` identifies the container. An aggregated query may need both:

```sql
-- Example reading multi-instance/container info if provided by the view and permitted.
SELECT inst_id, con_id, name, open_mode
FROM   gv$containers
ORDER BY inst_id, con_id;
```

If a PDB is open on two RAC instances, it can appear as two rows with the **same `CON_ID` but different `INST_ID`**. Counting rows without distinct over the proper key can yield the wrong logical PDB count.

## 11. Why Does Querying `CDB_*` in Root Not Return All PDBs?

This is a very common situation in inventorying, monitoring, and DBA authorization.

### 11.1. `CONTAINER_DATA` Controls Which Container Rows Are Visible

`CDB_*` views are **container data objects**. For a common user querying from the root, row scope across containers is controlled by the **`CONTAINER_DATA`** attribute at the user level and optionally per object. Oracle Database Reference notes that by default a user connected to the root may see only root data. Therefore:

```sql
-- From CDB$ROOT, using a common user with CDB_USERS read privilege:
SELECT con_id, username, common
FROM   cdb_users
WHERE  username LIKE 'APP%'
ORDER BY con_id, username;
```

If no row appears for a PDB, **that is insufficient to conclude the PDB has no `APP...` users**. Verify: does the executing account have dictionary privileges, does `CONTAINER_DATA` include that PDB, is the PDB open, and is the query filtering rows?

An authorized DBA can inspect this attribute via `CDB_CONTAINER_DATA`/`DBA_CONTAINER_DATA` per the Oracle Security Guide. **Do not widen `CONTAINER_DATA` to all PDBs just to get more rows on a dashboard** unless cross-tenant data access has been formally approved.

### 11.2. Closed or `RESTRICTED` PDBs Affect Results

Per Oracle Database Reference 19c, `CDB_*` views aggregate from **open PDBs** and have restrictions for PDBs opened in `RESTRICTED` mode; PDB state and RAC instances can affect the result set. A `MOUNTED` PDB still has metadata in PDB management views, yet `CDB_TABLES` may **not return that PDB's table list** while it is closed.

```sql
-- Check container states to know the scope from which metadata can be collected.
SELECT con_id, name, open_mode, restricted
FROM   v$pdbs
ORDER BY con_id;
```

Never open a production PDB just to make a metadata query return complete rows. If an inventory is needed, align scope, timing, and authorization with the responsible DBA.

### 11.3. Dictionary Privileges and Tenant Scope Are Two Separate Conditions

A common user may hold `SELECT` on a container data object yet not be permitted to see all containers under `CONTAINER_DATA`. Conversely, `CONTAINER_DATA` allowing container scope **does not automatically grant `SELECT` on every view/table**. Both control layers must be satisfied independently:

```text
      Object/view read privilege?
                 │
         ┌───────┴────────┐
         │                │
        NO               YES
         │                │
       Error/             ▼
      blocked     Which PDBs does CONTAINER_DATA allow?
                          │
                 ┌────────┴─────────┐
                 ▼                  ▼
             Permitted         Not permitted
                 │                  │
            May see            No rows from that
            valid rows         PDB in results
```

Therefore, do not diagnose a "broken view" simply because the root receives fewer rows than expected.

## 12. Watch Out for `V$`/`GV$` Views with Special Semantics

Not every performance view displays one row per PDB. Some views provide **instance-level metrics**, using `CON_ID=0` when queried from root; others are container data objects capable of providing per-PDB breakdown rows.

For example, the Oracle 19c Multitenant Administrator's Guide highlights the distinction:

| Metric | System-Level View | Corresponding Container-Scoped View |
| --- | --- | --- |
| System statistics | `[G]V$SYSSTAT` | `[G]V$CON_SYSSTAT` |
| Time model | `[G]V$SYS_TIME_MODEL` | `[G]V$CON_SYS_TIME_MODEL` |
| System event | `[G]V$SYSTEM_EVENT` | `[G]V$CON_SYSTEM_EVENT` |
| Wait class | `[G]V$SYSTEM_WAIT_CLASS` | `[G]V$CON_SYSTEM_WAIT_CLASS` |

Example:

```sql
-- Observe per-container statistics in root, if sufficiently privileged.
SELECT con_id, name, value
FROM   v$con_sysstat
WHERE  name = 'execute count'
ORDER BY con_id;
```

If querying `V$SYSSTAT` in the root returns a row with `CON_ID=0`, that is the intended summary meaning by design, not SQL "dropping" all PDB `CON_ID`s. Likewise, some `GV$` views also require `INST_ID` to aggregate properly in RAC.

**Do not apply a universal rule that "adding `CON_ID` splits metrics by PDB."** Before building monitoring, read the definition of the exact view you are using and determine whether the metric is instance-wide or PDB-specific.

## 13. Common Users, Local Users, and Privilege Scope Are Also Metadata

Parameters are one kind of administrative metadata; **users, roles, privileges, profiles, objects, and grants** also have container scope. Separate:

- **Common user**: an identity defined to exist across containers within the root scope; user-created common usernames in CDB root typically have the default prefix `C##`, depending on configuration.
- **Local user**: belongs only to one PDB; two different PDBs can have the same username as two independent users.
- **Common privilege/grant**: privilege granted with `CONTAINER=ALL` scope per Oracle rules, available across the corresponding PDBs.
- **Local privilege/grant**: privilege granted with `CONTAINER=CURRENT`, effective only in the container where it was granted.

### 13.1. Checking Which Container a User Belongs To

```sql
-- From a PDB: sees only user metadata in the current PDB.
SELECT username, common, oracle_maintained
FROM   dba_users
ORDER BY username;

-- From CDB$ROOT: can see multiple PDBs when permitted.
SELECT con_id, username, common, oracle_maintained
FROM   cdb_users
ORDER BY con_id, username;
```

`COMMON='YES'` means the user is a common user; **it does not mean** that user has been granted all privileges on all tables in all PDBs. A common user can hold common privileges for some functions alongside dedicated **local grants** inside a specific PDB.

### 13.2. Example Effect of Common Grants vs. Local Grants

```text
CDB$ROOT: C##REPORT has common roles/privileges in granted scope

SALES_PDB: C##REPORT also has local SELECT on APP.DAILY_SALES
HR_PDB:    Does not have local SELECT on HR.SALARY

Result:
  C##REPORT can use common privileges when connected appropriately,
  but cannot use its local privilege in SALES_PDB to read HR.SALARY.
```

`CONTAINER=ALL` in a `GRANT` is a cross-tenant authorization decision with security risk. Do not use it to work around missing rows in a metadata query before clarifying requirements and privilege boundaries.

## 14. Distinguishing Structural Metadata from PDB Operational Metadata

| Administrative Question | Typical View | Notes |
| --- | --- | --- |
| Is the current CDB multitenant? | `V$DATABASE.CDB` | Value `YES/NO` |
| Container names/IDs/open modes? | `V$CONTAINERS`, `V$PDBS` | Distinguishes root/seed/PDB, shows `RESTRICTED` |
| PDB inventory and lifecycle status? | `DBA_PDBS`, `CDB_PDBS` in root | Metadata about PDBs, not all tables inside PDBs |
| Which tables exist in the current PDB? | `DBA_TABLES` or `USER_TABLES`/`ALL_TABLES` | Affected by object privileges and current container |
| Which PDBs contain a table name? | `CDB_TABLES` in root | Complete only when PDBs are open and privileges/`CONTAINER_DATA` allow |
| Is a user local or common? | `DBA_USERS.COMMON`, `CDB_USERS.COMMON` | Local/common differs from grant scope |
| Which PDB does a service belong to? | `V$SERVICES`, `CDB_SERVICES` (if supported) | Service is an entry point to a PDB; not a schema/table |
| Can a parameter be overridden in a PDB? | `V$SYSTEM_PARAMETER.ISPDB_MODIFIABLE` | Combine with `ISSYS_MODIFIABLE`, `SCOPE`, `CONTAINER` |
| Which parameters are saved persistently? | `V$SPPARAMETER`, corresponding config metadata | Cross-check against runtime values in the PDB |

### 14.1. Example: `DBA_PDBS` vs. `DBA_TABLES`

```sql
-- From root, with appropriate privileges: metadata about PDB existence.
SELECT pdb_id, pdb_name, status
FROM   dba_pdbs
ORDER BY pdb_id;

-- From root: DBA_TABLES is table metadata in the root.
SELECT owner, table_name
FROM   dba_tables
WHERE  owner = 'APP'
ORDER BY table_name;

-- From root: CDB_TABLES can return table metadata in visible PDBs.
SELECT con_id, owner, table_name
FROM   cdb_tables
WHERE  owner = 'APP'
ORDER BY con_id, table_name;
```

A PDB can appear in `DBA_PDBS` even when `MOUNTED`; that does not guarantee `CDB_TABLES` returns full schema details for that PDB.

## 15. Procedure for Reading Metadata Before Changing a Parameter

This procedure should be applied in design reviews and change requests.

**Step 1 — Lock down CDB/release/instance/container.** Record login service, `SYS_CONTEXT` output, PDB name, and open mode. In RAC, explicitly record instance/session.

**Step 2 — Select the parameter.** Get its exact name and purpose; inspect `V$SYSTEM_PARAMETER.ISPDB_MODIFIABLE`, `ISSYS_MODIFIABLE`, `ISSES_MODIFIABLE`, and release conditions.

**Step 3 — Read root and individual PDBs separately.** Inspect `V$SYSTEM_PARAMETER` in root, then in each affected PDB; check session overrides via `V$PARAMETER` and persistent settings via `V$SPPARAMETER` where appropriate.

**Step 4 — Determine inheritance/override status.** Do not rely solely on `ISDEFAULT`; use configuration/DDL change history and inspect runtime/persistent values to see which PDBs have custom settings.

**Step 5 — Assess blast radius.** For `CONTAINER=CURRENT` in root, identify inheriting PDBs. For `CONTAINER=ALL`, identify overrides that may be erased. For `SCOPE=SPFILE`, plan PDB/CDB reopens during an appropriate maintenance window.

**Step 6 — Approve, execute, verify.** Only an authorized DBA runs `ALTER SYSTEM`. Afterward, inspect the right view in the right container, including after reopen if persistence verification is required.

**Step 7 — Record state.** Save parameter name, before/after values in root and PDB, `SCOPE`, `CONTAINER`, approving owner, and review date.

### 15.1. Sample Parameter Change Form

| Field | Example |
| --- | --- |
| CDB / version | `CDB01`, appropriate Oracle 19c RU |
| Instance | `cdb01_1`, in RAC list all instances |
| Target PDB | `SALES_PDB` |
| Parameter | `STATISTICS_LEVEL` |
| `ISPDB_MODIFIABLE` | Value **read directly** in the environment |
| Current root value | `TYPICAL` |
| Current PDB value | `TYPICAL` or existing override |
| Target value | `ALL` |
| `SCOPE`/`CONTAINER` | `BOTH` / `CURRENT` in `SALES_PDB` |
| User impact | Changes statistics/overhead related to the PDB workload |
| Post-change verification | Query `V$SYSTEM_PARAMETER` in `SALES_PDB` and other PDBs if relevant |
| Rollback | Documented and verified `RESET`/restore plan |

## 16. Read-Only Hands-On Lab: Comparing Root with a PDB

> This lab does not require creating/stopping PDBs, changing parameters, or reading user data. If your account only has privileges inside a PDB, perform the PDB portion; the root portion requires a DBA with appropriate privileges.

### Step A — Identify the CDB and Current Container

```sql
SELECT cdb, name, dbid
FROM   v$database;

SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV','CON_ID')   AS current_con_id
FROM   dual;
```

`V$DATABASE.CDB` indicates whether the database is a CDB; the name/DBID relates to the database, not an application PDB's schema.

### Step B — In `CDB$ROOT`, Record PDB Metadata

```sql
SELECT con_id, name, open_mode, restricted
FROM   v$pdbs
ORDER BY con_id;

SELECT name, display_value, ispdb_modifiable,
       issys_modifiable, isses_modifiable
FROM   v$system_parameter
WHERE  name IN ('statistics_level','optimizer_mode','open_cursors')
ORDER BY name;
```

Record the root values; do not assume they are also the effective values for every PDB.

### Step C — Connect Directly to `SALES_PDB`

Connect using a **PDB service** provided by the DBA (e.g., `sales_app.example.com`), then run:

```sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container
FROM   dual;

SELECT name, display_value, ispdb_modifiable,
       issys_modifiable, isses_modifiable
FROM   v$system_parameter
WHERE  name IN ('statistics_level','optimizer_mode','open_cursors')
ORDER BY name;
```

If the account has sufficient privileges:

```sql
SELECT owner, table_name
FROM   dba_tables
WHERE  owner = 'APP'
ORDER BY table_name;
```

If lacking `DBA_TABLES` privilege, substitute `ALL_TABLES` or `USER_TABLES` to observe the objects the account is permitted to see. The results of these three views differ by **privileges**, even in the same PDB.

### Step D — Return to Root and Inventory Multi-Container Metadata

```sql
SELECT con_id, owner, table_name
FROM   cdb_tables
WHERE  owner = 'APP'
ORDER BY con_id, table_name;
```

Cross-check against `V$PDBS` and `CONTAINER_DATA` scope. If `SALES_PDB` does not appear, do not conclude tables are missing before checking privileges, open status, and the actual container.

### Step E — Explain the Results

Record at least four observations:

1. What is the current container of each query?
2. Which parameters does `V$SYSTEM_PARAMETER` show as configurable in a PDB?
3. Why does `DBA_TABLES` differ between root and the PDB?
4. Which `CON_ID`s appear in `CDB_TABLES`, and is the query authorized to view all PDBs?

## 17. Troubleshooting Scenarios

### Scenario 1 — DBA Changes a Parameter in Root, Yet One PDB Keeps the Old Value

**Observation:** `STATISTICS_LEVEL` in root became `TYPICAL`, yet `HR_PDB` continues showing `ALL`.

**Possible explanation:** `HR_PDB` had a dedicated override. If root changed with `CONTAINER=CURRENT`, inheriting PDBs receive the root value per applicable rules, while PDBs with overrides keep their own values. Also check whether the new setting is only in `SPFILE` and not yet active at runtime, or whether a session override exists.

**Resolution:** verify `ISPDB_MODIFIABLE`, inspect runtime and persistent settings in root/PDB, and check change records. Only `RESET` the override if you genuinely want the PDB to revert to inheriting.

### Scenario 2 — Root Query on `DBA_TABLES` Does Not See App Tables Even Though App Runs Normally

**Observation:** `SALES_PDB.APP.ORDERS` exists and the application queries it, yet a DBA checking `DBA_TABLES` in `CDB$ROOT` does not see `APP.ORDERS`.

**Explanation:** `DBA_TABLES` in root describes root metadata; application tables were created in the PDB. Use `DBA_TABLES` **inside SALES_PDB** or `CDB_TABLES` **from root** when sufficiently privileged.

### Scenario 3 — Common User Query on `CDB_USERS` Only Sees `CON_ID=1`

**Observation:** The view runs without ORA errors, yet no PDB user rows appear.

**Explanation:** Default/configured `CONTAINER_DATA` may allow seeing only root. The account also needs appropriate dictionary privileges and PDBs must be in a state supporting metadata queries. Do not assume PDB users do not exist.

### Scenario 4 — A PDB Has a Row in `DBA_PDBS` But No Tables in `CDB_TABLES`

**Observation:** `HR_PDB` is `MOUNTED` in `V$PDBS`, while `DBA_PDBS` still lists that PDB.

**Explanation:** PDB management views provide lifecycle metadata from root; `CDB_TABLES` queries metadata of open PDBs and depends on visibility. A closed PDB does not mean its tables were dropped.

### Scenario 5 — Monitoring Double-Counts PDBs in RAC

**Observation:** A query on `GV$CONTAINERS` returns two rows for `SALES_PDB`.

**Explanation:** The same PDB may be open on two instances with different `INST_ID`s. Use `(INST_ID, CON_ID)` to inspect per-instance state; use distinct container identity when counting logical PDBs in a CDB.

### Scenario 6 — PDB Uses `SCOPE=MEMORY` and Loses Configuration After Reopen

**Observation:** A DBA changes a parameter to `ALL` in `SALES_PDB`, initially sees it take effect, and after maintenance the PDB reverts to the root value.

**Explanation:** `SCOPE=MEMORY` applies only at runtime; it does not persist across reopen per Oracle rules. If a persistent override is required, plan `SCOPE=BOTH` or `SPFILE` depending on parameter mutability and change procedures.

### Scenario 7 — After Unplug/Plug, PDB Configuration Still Differs from the New Root

**Observation:** `HR_PDB` is moved to another CDB; several parameters still follow old overrides even though the new root differs.

**Explanation:** Oracle can carry persistently set PDB parameter values (`SPFILE`/`BOTH`) in the PDB's XML metadata during unplug/plug. Review the target PDB configuration, limits/compatibility, and post-migration plug-in checks; do not assume all parameters automatically inherit from the new root.

## 18. Common Misconceptions

1. **"A PDB is a mini-instance."** False: a PDB is a logical container sharing many CDB instance resources.
2. **"`ALTER SYSTEM` in root always changes all PDBs."** Not necessarily: check whether PDBs have overrides, `CONTAINER`, `SCOPE`, and when it takes effect.
3. **"`CONTAINER=ALL` does not erase custom configurations."** False for `ALTER SYSTEM SET`: it can reset inheritance across PDBs.
4. **"`ISPDB_MODIFIABLE=TRUE` means the parameter can be changed immediately without restart."** False: also check `ISSYS_MODIFIABLE` and `SCOPE`.
5. **"`V$PARAMETER` and `V$SYSTEM_PARAMETER` are always identical."** False if the session has overrides or scope differs.
6. **"`SCOPE=MEMORY` persists after reopening a PDB."** Normally no; use a supported persistent mechanism if durability is needed.
7. **"`ISDEFAULT='TRUE'` definitely means the PDB is inheriting from root."** Insufficient evidence.
8. **"`DBA_TABLES` in root lists tables of every PDB."** False: root is its own current container.
9. **"Changing `DBA_TABLES` to `CDB_TABLES` shows all tenants."** False if dictionary privileges, `CONTAINER_DATA`, or PDB states do not permit it.
10. **"`CON_ID=0` is a broken PDB."** False: it typically represents CDB-wide/instance-wide scope.
11. **"`CON_ID=3` means SALES in every CDB."** False: the ID is local to a CDB and point in time.
12. **"A common user can access every table in every PDB."** False: container-level and object-level privileges still apply.
13. **"Every `V$` view has a per-PDB breakdown."** False: some views are instance-level; use the corresponding `V$CON_*` view when available.
14. **"When a PDB is closed, its metadata disappears."** False: distinguish between the existence of PDB metadata and the ability to query schema metadata when the PDB is open.
15. **"A `CDB_*` query returning fewer rows means data was lost."** Never conclude this before checking privileges, open mode, restricted mode, and query filters.

## 19. Review Questions

**Question 1.** A parameter has `ISSYS_MODIFIABLE=IMMEDIATE` and `ISPDB_MODIFIABLE=FALSE`. Can `ALTER SYSTEM SET` be used inside `SALES_PDB` to set a dedicated value? Why?

**Question 2.** Root sets `PARAM_X=C` with `CONTAINER=CURRENT`; `HR_PDB` previously overrode `PARAM_X=B`. What is `HR_PDB`'s value after the change takes effect?

**Question 3.** When root runs `ALTER SYSTEM SET ... CONTAINER=ALL`, what can happen to parameter inheritance across PDBs?

**Question 4.** A common user's `CDB_USERS` query in root shows only `CON_ID=1`, while `V$PDBS` shows `SALES_PDB` and `HR_PDB` are open. Name two things to check before concluding there are no local users.

**Question 5.** Why can `SELECT ... FROM DBA_TABLES` in `CDB$ROOT` and `SALES_PDB` return different results even for the same admin user?

**Question 6.** `V$SYSSTAT` in root shows `CON_ID=0`. To inspect per-PDB breakdown, which view should you investigate?

**Question 7.** A DBA runs `ALTER SYSTEM SET ... SCOPE=SPFILE` in a PDB. Must `V$SYSTEM_PARAMETER` immediately show the new value?

**Question 8.** After running `ALTER SESSION` in one session, why can `V$PARAMETER` differ from `V$SYSTEM_PARAMETER` in the same container?

<details>
<summary>Answer Hints</summary>

1. **No.** `ISPDB_MODIFIABLE=FALSE` disallows PDB overrides; runtime mutability does not determine PDB scope.
2. **B**, if the override remains, because a root change with `CONTAINER=CURRENT` does not reset PDB inheritance.
3. The operation can **reset the parameter's inheritance to true** across the CDB, replacing per-PDB overrides; blast radius must be reviewed.
4. Check **`CONTAINER_DATA`** and dictionary/view privileges, as well as PDB open/restricted state and SQL filter conditions.
5. Because `DBA_TABLES` describes metadata in the **current container**, and PDBs have their own schemas and objects.
6. Check **`V$CON_SYSSTAT`** or `GV$CON_SYSSTAT` by instance and `CON_ID`.
7. **Not necessarily.** `SPFILE` is a persistent setting for the next appropriate PDB reopen/restart; runtime may not have changed yet.
8. `V$PARAMETER` reflects session values after `ALTER SESSION`, while `V$SYSTEM_PARAMETER` holds the system value serving current/new sessions.

</details>

## 20. Official Oracle Documentation for Cross-Reference

Concepts and syntax must be cross-checked against your actual release, especially when deploying Oracle Database 19c, 21c, or Oracle AI Database 26ai:

1. [Oracle Database 19c Multitenant Administrator's Guide — Administering PDBs](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/administering-pdbs-with-sql-plus.html): `ISPDB_MODIFIABLE`, PDB parameters, `SCOPE`, `ALTER SYSTEM`, metadata on unplug/plug.
2. [Oracle Database 19c Multitenant Administrator's Guide — Administering a CDB](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/administering-a-cdb-with-sql-plus.html): inheritance in root, `CONTAINER=CURRENT`/`ALL`, statement scope, and common/local security.
3. [Oracle Database 19c SQL Language Reference — ALTER SYSTEM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-SYSTEM.html): official semantics of `SCOPE`, `CONTAINER`, and privilege requirements.
4. [Oracle Database 19c Administrator's Guide — Creating and Configuring an Oracle Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/creating-and-configuring-an-oracle-database.html): SPFILE, PFILE, parameter persistence, and `ALTER SYSTEM RESET`.
5. [Oracle Database 19c Multitenant Administrator's Guide — Monitoring CDBs and PDBs](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/viewing-information-about-cdbs-and-pdbs-with-sql-plus.html): `V$CONTAINERS`, `V$PDBS`, `CDB_*`, `DBA_*`, container data objects, and `CON_ID`.
6. [Oracle Database 19c Database Reference — CDB_* Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/cdb_-views.html): metadata limitations, privileges and `CONTAINER_DATA`, behavior with open/closed PDBs.
7. [Oracle Database 19c Database Reference — V$PARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-PARAMETER.html), [V$SYSTEM_PARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSTEM_PARAMETER.html), [V$SPPARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SPPARAMETER.html): session/system/persistent parameter metadata.
8. [Oracle Database 19c Multitenant Administrator's Guide — Overview of the Multitenant Architecture](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/overview-of-the-multitenant-architecture.html): data dictionary architecture, metadata/data links, and common/local objects.
9. [Oracle Database 19c Security Guide — Managing Commonly and Locally Granted Privileges](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-commonly-and-locally-granted-privileges.html): common/local grants, `CONTAINER_DATA`, and tenant boundaries.
10. [Oracle AI Database 26ai — Data Dictionary and Dynamic Performance Views](https://docs.oracle.com/en/database/oracle/oracle-database/26/cncpt/data-dictionary-and-dynamic-performance-views.html): architecture documentation in newer releases for comparing changes.

**Consistent mental checklist:** To understand an Oracle Multitenant result, identify **current container → view/parameter type → instance/session/root/PDB scope → privileges and `CONTAINER_DATA` → PDB state → `SCOPE`/`CONTAINER` if making a configuration change**. The same parameter or view name does not guarantee the same value or row set between `CDB$ROOT` and PDBs.
