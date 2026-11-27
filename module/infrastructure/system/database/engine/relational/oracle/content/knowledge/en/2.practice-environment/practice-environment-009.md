# Checking Version, Database Status, PDB, and Listener

Before practicing SQL on Oracle, you need to know **which Oracle Database version** you are connecting to, whether the database is open, whether the **PDB** holding application data is ready, and whether the **listener** is accepting external connections. These four questions are related, yet they are verified at different layers.

This lab uses SQL*Plus or SQLcl for SQL commands and the `lsnrctl` utility for the listener. You can run it on a machine with Oracle installed directly, a virtual machine, or inside a container if you have a shell and appropriate permissions. Example database/PDB names like `FREE`, `FREEPDB1`, `XE`, and `XEPDB1` are simply common defaults in certain Oracle editions; **always read the actual names from your environment**.

## 1. Distinguishing What You Are About to Check

~~~mermaid
flowchart TD
    U["Application / SQL client"] -->|"host:port/service_name"| L["Listener (Oracle Net)"]
    L -->|"Routes connection request"| S["Service and server process"]
    S --> I["Oracle instance: SGA + background processes"]
    I --> C["CDB: container database"]
    C --> R["CDB$ROOT"]
    C --> P["Application PDB"]
    C --> Seed["PDB$SEED: template"]
    C --> F["Datafiles, control files, redo logs"]
~~~

| Component | Question to answer | Primary way to observe |
|---|---|---|
| SQL client | Which version of the client tool runs on this machine? | `sqlplus -v` or tool version command |
| Oracle Database engine | Which version is the database server running? | `V$VERSION`, `V$INSTANCE` |
| Instance | What state are Oracle processes and memory in? | `V$INSTANCE.STATUS` |
| Database | Is the database `OPEN` and accepting reads/writes? | `V$DATABASE.OPEN_MODE` |
| CDB / PDB | Which container are we in, and is the application PDB `READ WRITE`? | `SHOW CON_NAME`, `SHOW PDBS`, `V$PDBS` |
| Listener | Which address/port does the listener run on, and which services does it know? | `lsnrctl status`, `lsnrctl services` |
| Actual connection | Can the application account log into the right PDB? | Connect via `host:port/service_name` and run `SELECT` |

An **Oracle instance** is the running set of processes and memory. An **Oracle database** is the data organization managed by the instance. The **listener** is the component receiving Oracle Net connection requests. The **service name** routes a session to the right database/container; a service is not the listener's name. Starting in Oracle 12c, the multitenant model has a **CDB** (Container Database) containing `CDB$ROOT`, `PDB$SEED`, and **PDBs** (Pluggable Databases). Some deployments or legacy releases may be non-CDB; in that case, PDB checks do not apply.

## 2. Preparing a SQL Session and a Terminal

You need two places to run commands:

1. **SQL*Plus or SQLcl:** runs SQL statements, `SHOW ...` display commands, and queries against dynamic performance views.
2. **OS terminal:** runs `sqlplus -v`, `lsnrctl status`, and `lsnrctl services`. These commands are **not** typed at the `SQL>` prompt.

If you are on the Oracle host and your OS account has OSDBA administrative privileges, e.g., on Linux/Unix:

~~~sh
sqlplus / as sysdba
~~~

This connection relies on OS authentication on the Oracle server; it does not work by default from arbitrary workstations, arbitrary containers, or arbitrary accounts. On Windows, users also need the proper authentication/privilege setup. Never use `SYSDBA` as a routine application connection account.

To test the same connection path an application uses, connect with an account allowed to log into the **PDB service**, for example:

~~~sh
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

SQL*Plus prompts for a password if none is supplied. `-L` tells it to exit after one failed login instead of re-prompting repeatedly. Replace `db-host.example`, port `1521`, and `my_pdb_service` with real values; port 1521 is a common convention, not mandatory. Avoid passing passwords directly on the command line, as they can leak via shell history or process listings.

Once connected, you can adjust formatting for readability:

~~~sql
SET LINESIZE 200
SET PAGESIZE 100
COLUMN instance_name FORMAT A18
COLUMN status FORMAT A12
COLUMN database_status FORMAT A18
COLUMN name FORMAT A24
COLUMN open_mode FORMAT A20
~~~

Note: the `V$...` queries below generally require privileges to view system metadata. If an application account gets `ORA-00942` or `ORA-01031`, check privileges first; do not conclude the database is broken or the PDB is closed. An administrator can run the appropriate queries or grant minimal read access per environment policy.

## 3. Checking Versions: Client, Server, and Listener Differ

### 3.1 SQL*Plus client version on the local machine

In the **terminal**:

~~~sh
sqlplus -v
~~~

Illustrative example output:

~~~text
SQL*Plus: Release 23.0.0.0.0 - Production
Version 23.x.x.x.x
~~~

This command confirms the **SQL*Plus client version**, not the database engine version running on the server your app connects to. Client and server can run different versions within Oracle's support matrix; to know the server version, log in and ask the server itself.

### 3.2 Oracle Database engine version

In **SQL*Plus/SQLcl connected to Oracle**:

~~~sql
SELECT banner
FROM v$version;
~~~

One row typically describes Oracle Database; other rows may describe related components. You can also check:

~~~sql
SELECT instance_name, version
FROM v$instance;
~~~

In newer releases, `V$VERSION` also includes a `BANNER_FULL` column showing a more detailed release/patch string. For broader lab compatibility across releases, `BANNER` and `V$INSTANCE.VERSION` are useful starting points. Major version, release update level, and applied patches are not always fully captured in a single string; when investigating specific patches, consult the environment's patch inventory.

**What to record:** the Oracle version on the **server**, not just the SQL client version. If an application reports incompatibility, record the JDBC driver version, SQL client version (if used), and Oracle server version for analysis.

### 3.3 Listener version

In a terminal on a machine with Oracle Net tools:

~~~sh
lsnrctl version
~~~

The listener version identifies the Oracle Net toolset running on that host. It **does not replace** querying the database version: a host can have multiple Oracle Homes, multiple listeners, or multiple databases.

## 4. Checking Instance and Database Status

### 4.1 Instance status

In SQL*Plus with sufficient privileges:

~~~sql
SELECT instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM v$instance;
~~~

Example interpretation of two key columns:

| Column | Common value | Meaning |
|---|---|---|
| `STATUS` | `STARTED` | Instance started in NOMOUNT stage; database is not mounted yet |
| `STATUS` | `MOUNTED` | Instance mounted the database, not yet open for normal use |
| `STATUS` | `OPEN` | Instance opened the database |
| `DATABASE_STATUS` | `ACTIVE` | Database is active as reported by the instance |

`STATUS = OPEN` and `DATABASE_STATUS = ACTIVE` are positive signs, yet they **do not confirm the application PDB is open** or that external clients can connect. `STARTUP_TIME` helps spot a recently restarted instance; `HOST_NAME` prevents confusing one server with another.

Basic startup stages:

~~~mermaid
flowchart LR
    A["NOMOUNT: instance STARTED"] --> B["MOUNT: control files opened"]
    B --> C["OPEN: database opened"]
~~~

These state transitions are background knowledge for **interpreting query output**, not a prompt to run `STARTUP` or `ALTER DATABASE` during a verification check.

### 4.2 Database status

~~~sql
SELECT name,
       db_unique_name,
       cdb,
       open_mode,
       database_role,
       log_mode
FROM v$database;
~~~

Notable columns:

- `NAME`: database name, not necessarily equal to the service name clients use.
- `DB_UNIQUE_NAME`: unique database identifier in setups distinguishing multiple replicas or Data Guard configurations.
- `CDB`: `YES` if container database; `NO` if non-CDB.
- `OPEN_MODE`: e.g., `READ WRITE`, `READ ONLY`, or `MOUNTED`. A primary transactional database typically needs `READ WRITE`, whereas a reporting/standby database may intentionally be in another mode.
- `DATABASE_ROLE`: such as `PRIMARY` or `PHYSICAL STANDBY`; helps explain why a database is not open for writes.
- `LOG_MODE`: `ARCHIVELOG` or `NOARCHIVELOG`; reflects redo archiving mode for recovery, not whether a PDB is ready.

If an instance is still in **NOMOUNT**, querying `V$DATABASE` may fail because the database is not mounted yet. In that case, rely on `V$INSTANCE.STATUS` and operational logs; never infer from the query error that data is lost.

### 4.3 Two states that must be read together

| Observation | Appropriate conclusion |
|---|---|
| Instance `OPEN`, database `READ WRITE` | The main CDB/database is open for reads/writes |
| Instance `MOUNTED`, database `MOUNTED` | Database is mounted but not open for normal operations |
| Instance `STARTED` | Only the instance has started; database is not mounted |
| Database `READ ONLY` | Readable per configuration; do not treat as a business write target without verifying architecture |
| Instance `OPEN` yet app still cannot connect | Check PDB, service, listener, network path, and login privileges next |

In Oracle RAC, each instance has its own state and host; querying `GV$INSTANCE` when permitted can reveal multiple instances. Basic labs can start with `V$INSTANCE` on the connected session.

## 5. Checking Which CDB or PDB You Are In

In Oracle multitenant, an **OPEN CDB** can still hold a **MOUNTED PDB**. This is a common reason beginners see the database "running" while the application cannot reach its target PDB.

### 5.1 Identifying the current SQL session's container

In SQL*Plus:

~~~sql
SHOW CON_NAME
~~~

Or using a SQL query:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

The result may be `CDB$ROOT` if in the root container, or an application PDB name such as `FREEPDB1`. Every query against application tables must be interpreted within the connected container and schema context.

### 5.2 Checking whether multitenant CDB is enabled

~~~sql
SELECT name, cdb, open_mode
FROM v$database;
~~~

If `CDB = YES`, proceed to check PDBs. If `CDB = NO`, the environment is non-CDB and there is no need to force `SHOW PDBS`. Never assume every Oracle version or environment shares the same PDB name.

### 5.3 Listing PDBs and open modes

When connected with sufficient privileges to `CDB$ROOT`:

~~~sql
SHOW PDBS
~~~

Equivalent SQL selecting specific columns:

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
~~~

**Illustrative** example output, not actual machine data:

~~~text
CON_ID  NAME       OPEN_MODE   RESTRICTED
------  ---------  ----------  ----------
2       PDB$SEED   READ ONLY   NO
3       FREEPDB1   READ WRITE  NO
~~~

`PDB$SEED` is the seed template used to create new PDBs and is normally `READ ONLY`; this is expected, not an error. A PDB holding application schemas usually needs `READ WRITE` for DML exercises. `MOUNTED` means the PDB is not open; `READ ONLY` blocks normal writes; `RESTRICTED = YES` indicates restricted access. Whether connections succeed also depends on services, user privileges, and configuration.

You can also query:

~~~sql
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;
~~~

`V$CONTAINERS` shows containers visible to the current session; from root you can observe both root and PDBs. Inside a PDB, dynamic view output may be scoped to that container and your privileges. If you do not see the expected PDB, check **whether you are connected to root or a specific PDB** and whether you have query privileges before concluding the PDB does not exist.

### 5.4 Which PDB is the application's connection target?

PDB names and service names are often related, yet **must not be assumed identical**. One PDB can expose multiple services. From a privileged admin account, you can list:

~~~sql
SELECT name, con_id
FROM v$services
ORDER BY con_id, name;
~~~

Match `CON_ID` against the PDBs in `V$PDBS`, then verify whether the corresponding service is registered with the listener. Never use a service pointing to `CDB$ROOT` to run DDL/DML for application schemas when the target is a dedicated PDB.

## 6. Checking the Listener at the OS Level

An **active listener** is essential for remote Oracle Net connections, yet a running listener **does not mean** the database/PDB is `OPEN`. Conversely, a local admin session logging in via OS authentication can still work while the listener is stopped, so a successful local login does not prove external network access works.

### 6.1 Checking listener status

In a terminal on the Oracle host or inside a container with listener utilities installed:

~~~sh
lsnrctl status
~~~

If the listener does not use the default name `LISTENER`, specify its name:

~~~sh
lsnrctl status MY_LISTENER
~~~

Key sections to read in `lsnrctl status` output:

| Section | How to read it |
|---|---|
| `Alias` | Name of the listener being queried |
| `Start Date` and `Uptime` | When the listener started |
| `Listening Endpoints Summary` | Protocol/host/port the listener listens on; e.g., TCP port 1521 |
| `Services Summary` | Services known to the listener |
| `The command completed successfully` | The listener status command succeeded; not proof that an application account can log in |

**Abbreviated, illustrative** example:

~~~text
Alias                     LISTENER
Listening Endpoints Summary...
  (DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=db-host)(PORT=1521)))
Services Summary...
Service "my_pdb_service" has 1 instance(s).
  Instance "mycdb", status READY, has 1 handler(s) for this service...
The command completed successfully
~~~

Do not copy `HOST=db-host` or `PORT=1521` literally from this example into your application. When running in Docker/VMs, the address and port visible to external machines may go through port mapping or NAT and differ from the endpoint inside the Oracle environment.

### 6.2 Checking detailed services and handlers

~~~sh
lsnrctl services
~~~

This command reveals the services, instances, and handlers known to the listener for dispatching connection requests. With normal dynamic registration, a `READY` status for the instance/service indicates the listener can accept matching connections. `UNKNOWN` is common with static registration because the listener cannot verify instance state through that mechanism; **never conclude an instance is broken solely from `UNKNOWN`**.

If `lsnrctl status` shows the listener running but **the PDB service is missing**:

1. Verify whether the PDB is in `READ WRITE` or the expected open mode.
2. Check whether the service was configured/started for the PDB; do not guess the service solely from the database name.
3. Verify the listener query targeted the right host, Oracle Home, and port.
4. Check dynamic service registration and related admin settings such as `LOCAL_LISTENER`.

For instance, administrators sometimes run `ALTER SYSTEM REGISTER` to trigger service re-registration; this is a **state-changing command**, not part of read-only checks, and should only be run with proper authority and a clear diagnosis.

### 6.3 On client machines without `lsnrctl`

`lsnrctl` is an Oracle Net server/admin utility and is not necessarily installed on every application host. When testing from a client machine, test connecting to the target service with SQL*Plus/JDBC to confirm end-to-end reachability. A TCP-level port check only shows network reachability to the port; it **does not** prove the PDB service exists or credentials are valid.

On Windows PowerShell, an example TCP connectivity test:

~~~powershell
Test-NetConnection -ComputerName db-host.example -Port 1521
~~~

On Unix/Linux with `nc`:

~~~sh
nc -vz db-host.example 1521
~~~

Run these network checks from **a machine sharing the application's network path**, whereas `lsnrctl status` queries the listener on the database host. Results can differ due to firewalls, container networks, DNS, NAT, or load balancers.

## 7. Verifying with a Real Connection to the PDB

Once the database and PDB are open and the listener has registered the service, verify the **end-to-end** path from where the application will run.

~~~sh
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

After logging in successfully:

~~~sql
SELECT USER AS session_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'SERVER_HOST') AS server_host
FROM dual;
~~~

The output confirms the **user**, **container**, **service**, and host bound to the active session. A successful login where `CONTAINER_NAME` turns out to be `CDB$ROOT` or a different PDB than intended is still **the wrong business target**, even with zero network errors.

For Java JDBC Thin, the corresponding Easy Connect syntax is typically:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db-host.example:1521/my_pdb_service
spring.datasource.username=app_user
~~~

This illustrates only the URL and username for a Spring Boot application; passwords/secrets should be supplied through your environment's secure configuration mechanism. The `@//host:port/service` syntax denotes a **service name**; do not confuse it with legacy SID connection syntax. One service can route across multiple RAC instances and handlers without changing how clients specify the service.

## 8. Quick Check Script Suite in Proper Order

First in the **terminal** (targeting the listener on the database host):

~~~sh
sqlplus -v
lsnrctl version
lsnrctl status
lsnrctl services
~~~

Next in **SQL*Plus connected with an account permitted to inspect views**, ideally at CDB root when inspecting all PDBs:

~~~sql
SET LINESIZE 200
SET PAGESIZE 100

-- 1) Server version
SELECT banner FROM v$version;

-- 2) Instance
SELECT instance_name, host_name, status, database_status
FROM v$instance;

-- 3) Database and CDB flag
SELECT name, db_unique_name, cdb, open_mode, database_role
FROM v$database;

-- 4) Current container
SHOW CON_NAME

-- 5) Applicable only when CDB = YES and sufficiently privileged
SHOW PDBS

SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;

-- 6) Services known to the instance
SELECT name, con_id
FROM v$services
ORDER BY con_id, name;
~~~

Finally, from the application host, log in as `app_user@//host:port/service` and confirm `CON_NAME` and `SERVICE_NAME` via `SYS_CONTEXT`. **Never** use `SYS`/`SYSTEM` to verify `app_user`'s application privileges; an admin connection succeeding does not prove the application has the right permissions.

Sample log template for a lab session:

| Item | Result to record |
|---|---|
| Oracle server version | Version from `V$VERSION` / `V$INSTANCE` |
| Instance name/host/status | E.g., `mycdb` / `db-host` / `OPEN` |
| Database name/open mode | Real name / `READ WRITE` or actual state |
| CDB? | `YES` or `NO` |
| Current container | `CDB$ROOT` or specific PDB |
| Application PDB/open mode | Real PDB name / `READ WRITE` or actual state |
| Listener endpoint | Actual host/port from listener |
| PDB service | Service name and handler status |
| Application connection | Success/failure; confirmed service/container |

Never write passwords into result tables, lab notes, or terminal screenshots.

## 9. Reading Common Errors Layer by Layer

| Symptom / message | Layer to inspect first | Verification path |
|---|---|---|
| `sqlplus` or `lsnrctl` not recognized as a command | Tool host | Is the tool installed; are Oracle Home and `PATH` set properly? |
| `ORA-12541: TNS:no listener` or equivalent | Listener / host / port / network | Is the listener running on the right endpoint; can the client reach the port? |
| `ORA-12514`: listener does not know requested service | Service registration / PDB | Compare connect-string service with `lsnrctl services`; verify PDB open mode and service registration |
| `ORA-12505` listener does not recognize SID | Connect identifier style | Check whether SID was mistakenly used instead of service name |
| `ORA-01017`: invalid username/password | User/password/target PDB | Are username, password, and target PDB service all correct? |
| `ORA-28000`: account is locked | User status | Contact account administrator; do not alter user security policies arbitrarily |
| `ORA-01034`: Oracle not available | Instance / connection target | Check whether the instance is running and how far the database is mounted/open |
| `ORA-01109`: database not open | Database open mode | Inspect `V$INSTANCE` and `V$DATABASE` in an appropriate admin session |
| `ORA-00942` / `ORA-01031` querying `V$...` | Metadata read privileges | Use an authorized account or ask the DBA for appropriate view grants |
| Listener running, but PDB is `MOUNTED` | PDB state | Check `SHOW PDBS`; connections to the PDB service may not be ready yet |
| Login succeeds yet app tables are missing | Wrong PDB or schema/privileges | Check `CON_NAME`, `SESSION_USER`, schema, and object privileges |

The error codes above help **isolate** the fault, not form a rigid diagnosis in every environment. For instance, `ORA-12514` can also appear right after database startup before service registration finishes, when the client hits the wrong listener, or when a service was stopped. Always read the full message and walk through the verification steps.

### Isolating incidents with a question flow

~~~mermaid
flowchart TD
    A["Application cannot reach Oracle"] --> B{"Can client reach host/port?"}
    B -->|No| C["Check DNS, network, firewall, listener endpoint"]
    B -->|Yes| D{"Does listener see requested service?"}
    D -->|No| E["Check service, PDB OPEN state, registration"]
    D -->|Yes| F{"Does login via service succeed?"}
    F -->|No| G["Check auth error, privileges, session limits, logs"]
    F -->|Yes| H{"Are CON_NAME and schema right?"}
    H -->|No| I["Fix service target or schema context"]
    H -->|Yes| J["Check queries and application business logic"]
~~~

In practice, multiple faults can occur simultaneously. This diagram helps avoid fixing the wrong layer—such as restarting the listener over a wrong password or editing a JDBC URL when the PDB has not been opened yet.

## 10. Example Conclusions from Two Different Environments

**Environment A — Ready for data-writing exercises**

~~~text
V$INSTANCE.STATUS       = OPEN
V$DATABASE.OPEN_MODE    = READ WRITE
V$DATABASE.CDB          = YES
App PDB OPEN_MODE       = READ WRITE
lsnrctl services        = PDB service has a READY handler
app_user connection     = succeeded, CON_NAME matches target PDB
~~~

These observations indicate **favorable readiness signals**, not that every table privilege, storage quota, performance target, or HA setup has been verified. For an `INSERT` to succeed, the account still needs the required privileges and data must satisfy constraints.

**Environment B — CDB is open, yet application cannot reach the PDB**

~~~text
V$INSTANCE.STATUS       = OPEN
V$DATABASE.OPEN_MODE    = READ WRITE
V$DATABASE.CDB          = YES
App PDB OPEN_MODE       = MOUNTED
lsnrctl status          = listener is running
PDB service connection  = failed or service unavailable
~~~

There is no contradiction here: the `OPEN` state of the instance/CDB and the `MOUNTED` state of a PDB live at two different levels. Whoever administers the PDB must verify why it has not opened and apply the right operational procedure. A read-only practitioner can accurately log the symptoms and report the exact failing component.

## 11. Self-Check Lab Exercise

Run these checks against an Oracle environment you are authorized to access and answer using your **actual collected outputs**:

1. Does `sqlplus -v` match the server version in `V$VERSION`? If they differ, which component does each output represent?
2. What stage do `V$INSTANCE.STATUS` and `V$DATABASE.OPEN_MODE` indicate the database is in?
3. Is `V$DATABASE.CDB` `YES` or `NO`? If `YES`, does `SHOW CON_NAME` return root or a PDB?
4. Does `SHOW PDBS` show the application PDB as `MOUNTED`, `READ ONLY`, or `READ WRITE`? Why should `PDB$SEED = READ ONLY` not be treated as an error?
5. Which host and port is `lsnrctl status` listening on? Does `lsnrctl services` list the service name your client uses?
6. From the application machine, can you log in using the PDB service? What does `SYS_CONTEXT('USERENV','CON_NAME')` return?
7. If a local `/ as sysdba` login succeeds while the application connection fails with `ORA-12514`, which layer will you inspect next?

To complete this lab, you should be able to explain **why an `OPEN` database alone does not guarantee an application can connect and write data**: the PDB must be in the right open mode, the listener must know the requested service, the network must reach the listener, the session must land in the right container, and the account must hold the necessary privileges.

## 12. Remembering the Relationship Between the Four Checks

- **Version** answers "Which Oracle release am I running?"; distinguish the SQL client, listener, and database engine.
- **Instance/database state** answers "Has Oracle started and what stage is the database in?"; read `V$INSTANCE` alongside `V$DATABASE`.
- **PDB state** answers "Is the application's data container open in the right mode?"; check `CON_NAME` and `V$PDBS` in a CDB.
- **Listener/service** answers "Are client connection requests routed to the right service?"; inspect endpoints with `lsnrctl status`, services with `lsnrctl services`, and then test an actual login.

An effective inspection order is: **verify versions → check instance and database → identify CDB/PDB → check listener/services → test connection from the application host → confirm the active container**. Each step proves only one slice of the system; combining them gives a clear enough picture to begin the upcoming SQL lessons.
