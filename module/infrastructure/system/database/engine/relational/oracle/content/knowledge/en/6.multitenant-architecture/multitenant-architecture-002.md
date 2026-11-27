# Current Container, CON_ID, and Switching Containers with the Right Scope

In Oracle Database using the **multitenant** architecture, a successful connection is not enough to confirm that a SQL statement is running in the right place. The same instance can serve the **CDB root** and multiple **PDBs**; each PDB contains schemas, objects, and application data within its own scope. Before creating tables, reading data, granting privileges, or performing administrative operations, three questions must be answered:

1. **Which container is the session currently in?**
2. **What does the CON_ID of that container mean, and how does it differ from the CON_ID values seen in views?**
3. **To work with another PDB, how do you connect or switch containers, and with what privileges?**

This lesson uses SQL*Plus/SQLcl and read-only SQL queries to determine context; the container-switching section includes an `ALTER SESSION SET CONTAINER` example for an **authorized administrative/common user account**. All PDB/service names in the examples are hypothetical and must be replaced with actual values.

## 1. Why Is the Container Part of the SQL Execution Context?

Suppose a system has a CDB `SALESDB` with two PDBs:

~~~mermaid
flowchart TD
    C["Oracle CDB: SALESDB"] --> R["CDB$ROOT (CON_ID = 1)"]
    C --> S["PDB$SEED (typically CON_ID = 2)"]
    C --> A["SALES_PDB (e.g., CON_ID = 3)"]
    C --> B["REPORT_PDB (e.g., CON_ID = 4)"]
    A --> A1["Schema SALES_APP"]
    A1 --> A2["ORDERS, PRODUCTS..."]
    B --> B1["Schema REPORT_APP"]
    B1 --> B2["Reporting tables and views"]
~~~

The **CDB** (*Container Database*) provides the infrastructure and shared components. **`CDB$ROOT`** is the root container for managing the CDB and shared components. **`PDB$SEED`** is the template PDB used to create other PDBs; it is normally open `READ ONLY`. An **application PDB** is where application users and business tables normally reside.

Within the same CDB, identical table names can appear in two different PDBs while holding different data. For example, running:

~~~sql
SELECT COUNT(*) FROM orders;
~~~

does not mean Oracle automatically searches for an `ORDERS` table across all PDBs. Oracle resolves object names based on the **current session's container, schema, and privileges**. Therefore, an `ORA-00942` error or an unexpected row count may stem from connecting to the wrong PDB rather than the table having been dropped.

| Concept | Role | Is it the "current container"? |
|---|---|---|
| Database/CDB name | Overall database name, e.g. `SALESDB` | No: the CDB name does not tell whether the session is in root or a PDB |
| Instance name | Name of the instance running memory/processes, e.g. `sales1` | No: one instance can serve multiple containers |
| Service name | Service name clients use to route connections | A service can point to a PDB, but the actual container still needs verification |
| Container name | `CDB$ROOT` or a PDB name such as `SALES_PDB` | **Yes**: this is the current scope of the session |
| `CON_ID` | Numeric identifier of a container within a CDB | **Can be mapped** to the container name in the same database |
| Schema/current schema | Namespace for looking up tables, views, packages... inside a container | No: changing schema is not changing PDB |

A normal session has **one current container at a time**. Changing the container via an allowed mechanism affects the object-resolution context; it does not mean renaming the database, switching instances, or physically moving data between PDBs.

## 2. Identifying the Current Container Immediately After Login

In SQL*Plus or SQLcl, two quick commands:

~~~sql
SHOW CON_NAME
SHOW CON_ID
~~~

**Illustrative** example output:

~~~text
CON_NAME
------------------------------
SALES_PDB

CON_ID
------------------------------
3
~~~

`SHOW CON_NAME` and `SHOW CON_ID` are **SQL*Plus/SQLcl client commands**, not standard SQL syntax to send over JDBC. In SQL Developer, they can be run in script mode or by using the `SELECT` query below; many SQL GUI clients only partially support `SHOW` commands.

### 2.1 Query That Works in Most SQL Tools

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV', 'CON_ID') AS current_con_id
FROM dual;
~~~

`SYS_CONTEXT('USERENV', ...)` returns environment information **for the exact session executing the SQL statement**. Specifically:

- `CON_NAME` is the current container name (for example `CDB$ROOT` or `SALES_PDB`).
- `CON_ID` is the corresponding container identifier, which can be converted to a number when comparison is needed.

The strength of this approach: **there is no need to assume you are in the root** and no need to guess the PDB name from a URL. You can run it immediately after logging in with an application account.

An additional query helps determine the complete session context:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'CON_ID') AS container_id,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

| Value | Question It Answers |
|---|---|
| `SESSION_USER` | Which database user logged in? |
| `CURRENT_SCHEMA` | If you write `SELECT * FROM orders`, which schema does Oracle look in first? |
| `CON_NAME` | Is the session in root or which PDB? |
| `CON_ID` | What is the container ID number in this CDB? |
| `SERVICE_NAME` | What service name is currently recorded for the session? |

**Do not rely solely on `CURRENT_SCHEMA` or `SERVICE_NAME` to determine the container.** A session can use a schema different from the login user; a service handles connection routing and does not always match the PDB name verbatim. `CON_NAME` and `CON_ID` are more direct evidence of the current container.

### 2.2 Example Reading the Output

~~~text
LOGIN_USER   CURRENT_SCHEMA   CONTAINER_NAME   CONTAINER_ID   SERVICE_NAME
-----------  ---------------  ---------------  -------------  --------------
SALES_APP    SALES_APP        SALES_PDB        3              sales_service
~~~

Correct conclusion: the session is logged in as `SALES_APP`, resolves unqualified names under `SALES_APP`, and is in container `SALES_PDB`. `CONTAINER_ID = 3` is meaningful within the currently connected CDB. The value `sales_service` is the service the session used, not the physical name of a datafile, instance, or schema.

## 3. Understanding CON_ID = 0, 1, 2, and Other Values

`CON_ID` appears in many dynamic performance views (`V$...`), multitenant data dictionary views (`CDB_...`), and related metadata. It helps distinguish **which container a row of data belongs to** within the **database being observed**.

| `CON_ID` Value | Common Interpretation |
|---|---|
| `0` | Data applies CDB-wide, is not tied to a specific container, or appears in a non-CDB context; exact meaning depends on the view |
| `1` | `CDB$ROOT` in a CDB |
| `2` | Typically `PDB$SEED` |
| `3` and above | PDBs or other container types with their own identifiers; must look up the actual name |

**`CON_ID = 0` is not "PDB number 0".** In some statistical views, it represents CDB-wide scope. If you sum a `CON_ID = 0` summary row together with per-PDB `CON_ID` rows, you may **double-count**. Likewise, the number `3` is not a fixed convention for `SALES_PDB` across environments: PDB creation order, cloning, dropping/recreating, or a different CDB can produce a different number.

The `CON_ID` value is a **technical identifier in the database context**, not a permanent business key to store in APIs or data tables.

### 3.1 Mapping CON_ID to Container Name

When authorized to query system views, from an administrative session at `CDB$ROOT`:

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$containers
ORDER BY con_id;
~~~

Example:

~~~text
CON_ID  NAME          OPEN_MODE   RESTRICTED
------  ------------  ----------  ----------
1       CDB$ROOT      READ WRITE  NO
2       PDB$SEED      READ ONLY   NO
3       SALES_PDB     READ WRITE  NO
4       REPORT_PDB    MOUNTED     NO
~~~

Here `CON_ID = 4` is `REPORT_PDB` in **the exact CDB being observed**, currently `MOUNTED`. Do not assume you can run application SQL in this PDB simply because it appears in the list.

To view only the PDBs:

~~~sql
SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;
~~~

`V$CONTAINERS` and `V$PDBS` usually require system observation privileges; visible rows depend on the session and container scope. If the query runs from a PDB or a restricted account, the output may **not include the entire CDB**. To map the full CDB, use an authorized account at the root.

### 3.2 Checking the Session's Own CON_ID via SQL

~~~sql
SELECT TO_NUMBER(SYS_CONTEXT('USERENV', 'CON_ID')) AS my_con_id,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS my_con_name
FROM dual;
~~~

When permitted to view `V$CONTAINERS`, you can cross-check:

~~~sql
SELECT c.con_id, c.name, c.open_mode
FROM v$containers c
WHERE c.con_id = TO_NUMBER(SYS_CONTEXT('USERENV', 'CON_ID'));
~~~

The second query filters only **the row corresponding to the current container**, not the full PDB list. Do not use numbers from a screenshot of another database for comparison: the same `CON_ID` can refer to a different container in another CDB.

### 3.3 If the Environment Is Non-CDB

Older Oracle versions or architectures may be non-CDB. When sufficiently privileged:

~~~sql
SELECT name, cdb, open_mode
FROM v$database;
~~~

If `CDB = NO`, distinguishing root/PDB and `ALTER SESSION SET CONTAINER` **do not apply in the same model**. Not every tool is expected to return a PDB list in an environment that does not support multitenant. To practice CDB/PDB concepts, you must use a database with the multitenant architecture.

## 4. Right Container Does Not Mean Right Schema

Consider two sessions both in `SALES_PDB`:

~~~text
Session A: SESSION_USER = SALES_APP, CURRENT_SCHEMA = SALES_APP
Session B: SESSION_USER = AUDITOR,   CURRENT_SCHEMA = SALES_APP
CON_NAME of both: SALES_PDB
~~~

If user `AUDITOR` has been granted privileges, Session B can reference `SALES_APP`'s objects using the qualified name `SALES_APP.ORDERS` or by changing the default schema:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = SALES_APP;
~~~

After this statement, observe:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

`CURRENT_SCHEMA` can change, while `SESSION_USER` and `CON_NAME` **do not automatically change**. This statement also **does not grant extra privileges**: if `AUDITOR` lacks privileges on `SALES_APP.ORDERS`, the query will still fail. `ALTER SESSION SET CURRENT_SCHEMA` and `ALTER SESSION SET CONTAINER` solve two different problems.

To avoid confusion in multi-PDB exercises, prefer recording **schema and container** together. Writing `SALES_APP.ORDERS` specifies the schema within the **current container**; that syntax does not jump to `SALES_PDB` if the session is in `REPORT_PDB`.

## 5. The Standard Way into the Right PDB: Connecting via Service

For applications, local user accounts, and most everyday tools, the clearest approach is to **establish a connection to the desired PDB's service**.

~~~mermaid
flowchart TD
    U["SQL*Plus / JDBC / application"] -->|"//db-host:1521/sales_service"| L["Listener"]
    L --> S["Service of SALES_PDB"]
    S --> P["Session in SALES_PDB"]
    P --> V["SYS_CONTEXT: CON_NAME = SALES_PDB"]
~~~

SQL*Plus/SQLcl example from a terminal:

~~~sh
sqlplus -L sales_app@//db-host.example:1521/sales_service
~~~

SQL*Plus will prompt for a password if one is not provided. Replace host/port/service/user with actual values; do not write passwords directly on the command line or in shell history.

After logging in:

~~~sql
SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV','CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV','CON_ID') AS container_id,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
FROM dual;
~~~

If `CONTAINER_NAME` returns `SALES_PDB`, the session is in the expected container. **Verify with a query**, because a service name is not required to match the PDB name and a system can bind multiple services to the same PDB.

Java JDBC Thin applications typically use this URL syntax:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db-host.example:1521/sales_service
spring.datasource.username=sales_app
~~~

Keep passwords in an appropriate secrets configuration system. Connection pools normally manage physical connections for a specific service configuration; applications serving multiple PDBs should design explicit DataSource/connection separation per PDB rather than inadvertently changing the container of a reused connection.

**Distinction to keep in mind:** the listener receives connection requests and the service routes them to the database/PDB; `ALTER SESSION SET CONTAINER` is a scope-switching operation **inside an already connected session**, used for specially authorized situations. Connecting to the PDB service is easier to verify for routine application workloads.

## 6. Switching Containers with ALTER SESSION: Who Can Use It?

Oracle supports the command:

~~~sql
ALTER SESSION SET CONTAINER = SALES_PDB;
~~~

This is a **conditional operation**, not a default capability of every database user. In the CDB architecture, switching containers between root and PDBs normally requires a **common user** (for example, an authorized common administrative account) with the appropriate `SET CONTAINER` privilege on the target. Specific administrative privileges and account types also depend on database configuration and security policies.

A **local user** created specifically inside one PDB for application use cannot by default switch to another PDB using `ALTER SESSION SET CONTAINER`. Even if the SQL syntax is valid, Oracle checks privileges, PDB state, and session conditions.

### 6.1 Distinguishing Local Users and Common Users

| Account Type | Scope | How to Work with Another PDB |
|---|---|---|
| **Local user** | Belongs to a specific PDB, e.g. `SALES_APP` | Log in via the service of the PDB where the user exists; use appropriate account/authorization in the other PDB |
| **Common user** | Has a shared identity across containers within the common user's scope, e.g. a CDB admin account | Can switch containers **if granted `SET CONTAINER` on the target and other conditions are met** |
| **Application common user** | Application container / application PDB scope, if this architecture is deployed | Privileges and container-switching paths must be evaluated per the application container, not treated as a CDB-wide common user |

In standard CDBs, administrator-created common user names typically have a `C##` prefix under the default configuration; **a prefix in the name does not prove the account holds the required privileges**. Do not rely on a username starting with `C##` to skip privilege checks.

### 6.2 Illustrative Container-Switching Workflow for an Authorized Common User

Suppose an administrative session starts in `CDB$ROOT`, account `C##OBSERVER` has been granted `SET CONTAINER` appropriately, and PDB `SALES_PDB` is open:

~~~sql
-- 1. Confirm initial scope
SHOW CON_NAME
SHOW CON_ID

-- 2. Locate exact target PDB name and state
SELECT con_id, name, open_mode, restricted
FROM v$pdbs
WHERE name = 'SALES_PDB';

-- 3. Switch to the confirmed PDB
ALTER SESSION SET CONTAINER = SALES_PDB;

-- 4. Re-verify immediately after switching
SHOW CON_NAME
SHOW CON_ID

SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV','CON_ID') AS current_con_id
FROM dual;
~~~

If the output returns `SALES_PDB` and the matching CON_ID from the list, you can confirm **the session has switched to the right PDB**. Do not proceed to DDL/DML statements before this verification.

When returning to the root, if the account holds the corresponding privileges:

~~~sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV','CON_ID') AS current_con_id
FROM dual;
~~~

The expected output is `CDB$ROOT` and `1`. In tools that do not support `SHOW CON_NAME`, the `SYS_CONTEXT` queries remain the verification method. Only run this container-switching sequence in a dedicated authorized session on an environment you are permitted to administer.

### 6.3 Preconditions Before Switching

Before `ALTER SESSION SET CONTAINER`, the operator needs to verify:

1. **The environment is actually a CDB.** For non-CDB, this workflow does not apply.
2. **Valid account and privileges.** A common user must hold `SET CONTAINER` in the right scope; a local user cannot elevate itself to a common user by running the statement.
3. **Target container has the right name and is in a state that supports the intended task.** For example, a PDB needing write data access usually requires `READ WRITE`; `PDB$SEED` is normally read-only and is not a target for application schemas.
4. **The session is not in the middle of a transaction that needs to be preserved.** Do not attempt to switch containers while a transaction is active; complete an intentional `COMMIT` or `ROLLBACK` in the current scope per procedure.
5. **No session state should be blindly assumed preserved.** After switching, re-check the container/schema/privileges and critical session settings before continuing.

An `ALTER SESSION SET CONTAINER` statement **does not copy tables**, **does not move data between two PDBs**, **does not convert a local user into a common user**, and **does not grant privileges to read tables in the target PDB**. It is solely a mechanism to change the current container scope for an eligible session.

### 6.4 Why Should ALTER SESSION Not Be Used Arbitrarily in a Connection Pool?

Suppose an application borrows a JDBC connection from a pool, switches it to `REPORT_PDB`, returns it to the pool without ensuring proper state restoration, and a subsequent request reuses that connection assuming it is in `SALES_PDB`. Subsequent SQL statements may read the wrong data, report missing tables, or perform DML in the wrong scope.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant P as Connection pool
    participant O as Oracle session
    participant B as Request B
    A->>P: Borrow connection
    P->>O: Session initially in SALES_PDB
    A->>O: ALTER SESSION SET CONTAINER = REPORT_PDB
    A->>P: Return connection without verifying state
    B->>P: Borrow connection again
    B->>O: SELECT from default schema
    O-->>B: May mistakenly access REPORT_PDB
~~~

Therefore, for multi-PDB applications, organizing separate connection pools per service/target and verifying the container upon connection initialization is usually clearer and less error-prone. If a system has a specialized requirement for dynamic container switching, transaction boundaries and session state must be strictly controlled; do not perform it as a side effect inside an ordinary repository method.

## 7. Distinguishing Query Scope in Root vs. in a PDB

A common user connected to `CDB$ROOT` **does not mean every normal `SELECT` automatically runs across all PDBs**. Depending on the view type, Oracle provides different observation scopes:

- **Normal application tables/schemas:** `SELECT` looks at objects in the **current container** according to privileges/schema; it does not automatically scan all PDBs.
- **`DBA_*` views:** reflect the data dictionary within the session/container scope, subject to privileges.
- **`CDB_*` views:** can provide data from multiple containers from the root when the account has privileges and appropriate container-data configuration; the `CON_ID` column helps distinguish sources.
- **`V$*`/`GV$*` views:** reflect runtime state; the meaning of `CON_ID` and visible rows depend on the specific view, instance, session, and privileges.

For example, with appropriate privileges, from the root:

~~~sql
SELECT con_id, username, common
FROM cdb_users
WHERE username IN ('SALES_APP', 'REPORT_APP')
ORDER BY con_id, username;
~~~

If `CDB_USERS` returns two rows with different `CON_ID` values, that is user metadata across different containers. **Do not** interpret the output as proof that the root session is simultaneously "in both PDBs" or has privileges to query every table of both users. Row visibility also depends on the account/common user's privileges and container data visibility settings.

### 7.1 When You Need to Read from the Right Schema in the Right PDB

Suppose you want to count orders in `SALES_PDB`. Two clear approaches:

**Standard approach for applications:** log a session into `SALES_PDB`'s service with an authorized user and run:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS con_name
FROM dual;

SELECT COUNT(*) AS order_count
FROM sales_app.orders;
~~~

**Approach for an authorized common user:** from the root, identify the PDB and its status, switch to the right container, confirm `CON_NAME`, and only query the table when the current user has privileges on that object. Switching containers and table read privileges are **two separate checks**.

If using the unqualified table name `orders`, Oracle also depends on `CURRENT_SCHEMA`. To reproduce a situation accurately, record `SESSION_USER`, `CURRENT_SCHEMA`, and `CON_NAME` together.

### 7.2 What Does CON_ID in V$SESSION Show?

An account permitted to observe sessions can query:

~~~sql
SELECT sid, serial#, username, con_id, service_name, status
FROM v$session
WHERE type = 'USER'
ORDER BY con_id, sid;
~~~

`V$SESSION.CON_ID` associates a session with a container within the view's scope at observation time; `SERVICE_NAME` shows the service the session uses. A broad-privilege query in the root can see sessions across multiple containers; a PDB account typically observes only what it is permitted to see. **Do not confuse the `CON_ID` of other session rows with the `CON_ID` of the session running the query**. To confirm your own session, `SYS_CONTEXT('USERENV','CON_ID')` is the direct way.

## 8. Common Pitfalls When Managing Containers

| Observation or Action | Correct Conclusion / Next Step |
|---|---|
| `SHOW CON_NAME` returns `CDB$ROOT` | The session is in root; not yet in an application PDB |
| `SHOW PDBS` shows `SALES_PDB READ WRITE` | The PDB is ready in terms of open mode; continue checking service, user, and privileges |
| `SHOW PDBS` shows `PDB$SEED READ ONLY` | Usually the normal state of the template PDB; do not use seed for business data |
| `V$CONTAINERS` has `CON_ID = 0` | Check the view's semantics; do not assume it is a PDB named "0" |
| JDBC URL uses `sales_service` | That is a service name, not absolute proof of container; verify `CON_NAME` after login |
| `CURRENT_SCHEMA` changed from `AUDITOR` to `SALES_APP` | Only changes object-resolution context; `CON_NAME` does not change automatically |
| `ALTER SESSION SET CONTAINER` reports insufficient privileges | Check user type and `SET CONTAINER` privilege; do not over-grant privileges due to a command error |
| Root sees PDB user metadata via `CDB_USERS` | Has privileges to view some metadata; does not guarantee access to read application tables inside the PDB |
| Two CDBs both have `CON_ID = 3` | Does not guarantee they are the same PDB; verify name and database |
| SQL connection succeeds but `ORA-00942` when querying a table | Check PDB, schema, object name, and privileges before concluding the table does not exist |
| Connecting to service fails before entering a session | Check listener/service/PDB open mode; before connecting, you cannot run `SHOW CON_NAME` in that session |

### 8.1 Container-Related Error Messages

**`ORA-01031: insufficient privileges`** can occur when a container switch lacks appropriate privileges. **`ORA-65011`** indicates the specified PDB does not exist in the current management context; first re-query the PDB name and connected CDB. **`ORA-01109: database not open`** can appear when trying to query objects in a database/PDB that is not open as required. These error codes are clues to narrow down the cause, not a complete diagnosis: compare the actual state, privileges, and full SQL statement.

If the session has an active transaction or uses a specialized session mechanism, Oracle may refuse the switch; do not resolve this by blindly issuing `COMMIT` on a transaction whose contents are unknown. Complete the transaction according to business intent first, then perform the switch in a safe administrative session.

## 9. Hands-On Command Sets by Role

### 9.1 Application Developer: Verifying PDB Connection Without Admin Privileges

In the terminal:

~~~sh
sqlplus -L sales_app@//db-host.example:1521/sales_service
~~~

In the SQL session:

~~~sql
-- Observe account, schema, container, and service
SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV','CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV','CON_ID') AS container_id,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
FROM dual;

-- Run a read-only query on an authorized schema table
SELECT COUNT(*) AS order_count
FROM sales_app.orders;
~~~

`sales_app.orders` is just an illustrative table; if the actual schema does not have this table, replace it with an authorized practice table. If `SYS_CONTEXT` returns a different container than expected, check the connect string/service before running update SQL.

If you need to work with `REPORT_PDB` using a different local user, **open a new connection to REPORT_PDB's service** with the appropriate account credentials. Do not try to use container switching as a way to bypass privileges.

### 9.2 Administrator / Authorized Common User: Controlled Observation and Scope Switching

In `CDB$ROOT`:

~~~sql
-- Step 1: Verify it is a CDB and check the database name
SELECT name, cdb, open_mode
FROM v$database;

-- Step 2: Check this session's own container
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS before_name,
       SYS_CONTEXT('USERENV','CON_ID') AS before_id
FROM dual;

-- Step 3: Verify target PDB and open mode
SELECT con_id, name, open_mode, restricted
FROM v$pdbs
WHERE name = 'SALES_PDB';

-- Step 4: Switch only when the account is authorized and the session is ready
ALTER SESSION SET CONTAINER = SALES_PDB;

-- Step 5: Verify target immediately
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS after_name,
       SYS_CONTEXT('USERENV','CON_ID') AS after_id,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

This sequence **contains a session scope-change operation** in Step 4; the remaining steps are read-only. Do not put this administrative sequence into an automated production script without controls on privileges, target, and transaction boundaries. When finished practicing, if continuing to use the administrative session for root work, switch back to root with appropriate privileges and **re-verify**:

~~~sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

SELECT SYS_CONTEXT('USERENV','CON_NAME') AS final_container
FROM dual;
~~~

## 10. Decision Diagram: New Connection or Switch Container?

~~~mermaid
flowchart TD
    A["Need to operate in a PDB"] --> B{"Already have a session in the right PDB?"}
    B -->|Yes| C["Check schema and privileges, then run SQL"]
    B -->|No| D{"Is it a common user with valid SET CONTAINER?"}
    D -->|No| E["Log in via the PDB's service with the appropriate account"]
    D -->|Yes| F{"Need to switch within the same admin session?"}
    F -->|No| E
    F -->|Yes| G["Check transaction, PDB name, OPEN_MODE"]
    G --> H["ALTER SESSION SET CONTAINER = PDB"]
    H --> I["Verify CON_NAME, CON_ID, CURRENT_SCHEMA"]
    E --> I
    I --> C
~~~

For learners and most applications, the standard path is **logging in via the target PDB's service and then confirming the container**. `ALTER SESSION SET CONTAINER` primarily serves authorized common-user work, under strict privilege and session-state conditions.

## 11. Self-Check Exercises

**Exercise 1 — Identify the container.** Open a SQL connection to your practice PDB, run `SHOW CON_NAME` (if supported by the tool), and query `SYS_CONTEXT`. Record `SESSION_USER`, `CURRENT_SCHEMA`, `CON_NAME`, `CON_ID`, and `SERVICE_NAME`. Explain why `SERVICE_NAME` does not necessarily match `CON_NAME`.

**Exercise 2 — Map CON_IDs.** With an authorized account in CDB root, run `SELECT CON_ID, NAME, OPEN_MODE FROM V$CONTAINERS ORDER BY CON_ID`. Label root, seed, and each PDB. Explain why you cannot carry a CON_ID number from CDB A to CDB B to infer a PDB name.

**Exercise 3 — User and schema scope.** Inside your practice PDB, inspect `SESSION_USER` and `CURRENT_SCHEMA` before and after changing `CURRENT_SCHEMA` to a schema you are permitted to reference. Confirm `CON_NAME` does not change and explain why another schema still requires object access privileges.

**Exercise 4 — Authorized container switching.** If an administrator grants you a common user with `SET CONTAINER` in a permitted test environment, switch from root to an open PDB, read `CON_NAME` and `CON_ID` again, and return to root. If you do not have that privilege, **do not try to force the switch command**: describe why a local user should open a new connection via service.

**Exercise 5 — Scenario analysis.** A user reports "I can log into Oracle, but I don't see the `ORDERS` table." Present the checklist order: which service was connected, what `CON_NAME` is, what `CURRENT_SCHEMA` is, which schema owns the table, and whether the account has privileges. State why immediately recreating the table is an inappropriate reaction.

**Exercise 6 — View scope.** From root, a `CDB_USERS` query returns users across multiple CON_IDs. Explain the difference between "a session can view metadata from multiple containers" and "a session is executing a business `SELECT` inside a specific container."

## 12. Takeaways for Operating in the Right Scope

| What You Need to Know | Command or Principle |
|---|---|
| Where is the session? | `SHOW CON_NAME` / `SYS_CONTEXT('USERENV','CON_NAME')` |
| What is the current CON_ID? | `SHOW CON_ID` / `SYS_CONTEXT('USERENV','CON_ID')` |
| Which PDB matches a CON_ID? | From root, query `V$CONTAINERS` or `V$PDBS` when authorized |
| Is the database a CDB? | `SELECT CDB FROM V$DATABASE` |
| Is the PDB open for writes? | Check `OPEN_MODE`; `READ WRITE` is usually needed for DML |
| How do user and schema differ? | `SESSION_USER` is the user; `CURRENT_SCHEMA` is where object names resolve |
| How do apps enter a PDB? | Connect via the **PDB's service**, then verify `CON_NAME` |
| Who can use `ALTER SESSION SET CONTAINER`? | A common user with valid `SET CONTAINER` privilege when session/target meet conditions |
| Does switching containers elevate privileges? | **No**: object privileges and security rules are still enforced |
| Can CON_ID be used as a system-wide ID? | **No**: this identifier requires the CDB and view context |

The most important practical rule is **identify the container first, operate second**. In Oracle multitenant, connecting to the right database server but the wrong PDB can still lead to wrong data, wrong privileges, or creating objects in the wrong place. Checking `CON_NAME`, `CON_ID`, `CURRENT_SCHEMA`, and the session's service puts every SQL statement in the right scope; when switching containers is required, use the right account type, proper privileges, and re-verify the context immediately afterward.
