# PDB Services and Application Connection Routing in Oracle

When working with Oracle Database using the **multitenant** architecture, applications usually do not connect directly using an instance name or a datafile directory. Applications request a connection to a **service**; Oracle Net uses this service to find where the connection can be served and places the session into the appropriate **PDB**. If the service is misconfigured, the program can connect to the wrong container, see a different schema, or fail even while the database and listener are still running.

This lesson explains the relationships among **CDB**, **PDB**, **service**, **listener**, **instance**, and **client**; how connections are routed from Java/JDBC; how to create, start, and verify services; and a methodology for diagnosing when a service is unreachable.

## 1. From CDB to PDB: What Does an Application Actually Connect To?

In the Oracle multitenant architecture:

- **CDB (Container Database)** is the database containing the root, seed, and PDBs. The CDB is opened and operated by one or more Oracle instances.
- **CDB$ROOT** is the root container serving shared information and administration. It is normally not the business access target for applications.
- **PDB$SEED** is the template used to create PDBs; it is not a normal application access target.
- **PDB (Pluggable Database)** is a logical container holding application schemas, objects, and data. One CDB can contain multiple PDBs.
- **Schema/user** is the object owner and access identity inside a container; multiple users/schemas can coexist within one PDB.
- **Service** is a logical name requested by clients to be routed to a data service, typically associated with a specific PDB.

Example:

~~~text
                           CDB: CORPDB
                    ┌──────────────────────────┐
                    │ CDB$ROOT                 │
                    │ PDB$SEED                 │
                    │                          │
                    │ ┌──────────────────────┐ │
                    │ │ SALES_PDB            │ │
                    │ │ SALES_APP, REPORT_APP│ │
                    │ │ ORDERS, CUSTOMERS... │ │
                    │ └──────────────────────┘ │
                    │                          │
                    │ ┌──────────────────────┐ │
                    │ │ HR_PDB               │ │
                    │ │ HR_APP, EMPLOYEES... │ │
                    │ └──────────────────────┘ │
                    └──────────────────────────┘
                             ▲          ▲
                             │          │
          sales_app.example.com          hr_app.example.com
                (service)                     (service)
                             ▲          ▲
                             └────┬─────┘
                                  │
                   Client / Listener / Instance
~~~

In this example, two applications can use the **same host and port**, while requesting **different service names** to connect to two PDBs. Once a client enters `SALES_PDB`, the user `SALES_APP` or `REPORT_APP` determines the identity and available privileges; a service does not turn two users into one.

> **Guiding questions:** *Which service did it connect to?* identifies the logical target. *Which PDB is the session actually in?* confirms the data location. *Which user logged in?* determines the default schema and privileges. These are three separate questions.

## 2. What Is a Service and How Does It Relate to a PDB?

A **database service** is a logical name provided by Oracle for clients to connect to a workload or data service. In a CDB, an application service is typically **associated with one PDB**; connections through that service are established in the target container.

Core relationships:

| Concept Pair | Correct Relationship | Example |
|---|---|---|
| **CDB – PDB** | One CDB contains multiple PDBs | `CORPDB` contains `SALES_PDB` and `HR_PDB` |
| **PDB – service** | One PDB can have **multiple services** | `SALES_PDB` serves `sales_app.example.com` and `sales_report.example.com` |
| **Service – instance** | One service can be provided by one or more instances, depending on deployment | In RAC, the Sales service runs on managed instances |
| **Service – listener** | The listener receives Oracle Net requests and identifies a handler for the registered service | The listener knows where `sales_app.example.com` can be served |
| **Service – schema** | The service selects the connection target; schema/user is the identity and objects inside the PDB | `sales_app.example.com` leads to `SALES_PDB`, user `SALES_APP` logs in |
| **Service – SID** | Service is a logical target; SID identifies an instance | `sales_app.example.com` is distinct from `corp1` |

A **service is not a data copy**. Two services both pointing to `SALES_PDB` do not create two datasets, two transaction logs, or two schemas. You can split services by application or workload class, yet privilege isolation must rely on **users, roles, privileges**, and appropriate controls.

### Must the Service Name Match the PDB Name?

**No.** When creating a PDB, Oracle typically provides a **default service** associated with the PDB; this default name is usually based on the PDB name and the database domain identifier. However, administrators can create **dedicated application services** with network names like `sales_app.example.com`.

For example:

~~~text
PDB: SALES_PDB
    ├── Default PDB service (serves basic connections)
    ├── sales_app.example.com       ── Transactional application
    ├── sales_report.example.com    ── Reporting application
    └── sales_batch.example.com     ── Batch jobs
~~~

The three services above can all lead to the **same SALES_PDB**. Naming a service with suffixes like `_ro`, `_rw`, or `_batch` merely describes its purpose: a `_ro` name **does not automatically make the PDB read-only**. If updates must be restricted, configure appropriate privileges or deploy the workload on a target/role enforcing that policy.

## 3. Connection Routing Flow from Application to PDB

Suppose a Java application uses:

~~~text
jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com
~~~

The processing flow typically works as follows:

1. **The client resolves the address** `db.example.internal` via DNS or network configuration, then opens an Oracle Net connection to the host and port `1521`.
2. **The listener accepts the request** with connect data containing `SERVICE_NAME=sales_app.example.com`. The listener is a connection-listening process, **not** the PDB or the service itself.
3. **The service has registered with the listener** along with serving instance/handler details. The listener chooses how to forward or hand off the request to the appropriate process/instance side.
4. **The Oracle server creates a session** for the connection request, binding the session to the container corresponding to the service—in this example, `SALES_PDB`.
5. **Oracle authenticates the user** and establishes the session context. From then on, SQL is resolved within the session's PDB, schema, and privileges.
6. **The connection pool holds open connections** for application reuse; the service is requested when establishing a new physical connection, not on every individual SQL statement.

~~~text
Java Application
    |
    | Oracle JDBC URL
    | db.example.internal:1521 / sales_app.example.com
    v
DNS / Oracle Net connect descriptor
    |
    v
Oracle Listener :1521
    |  requests SERVICE_NAME
    |  finds registered handler
    v
Instance/server process serving the service
    |
    v
CDB CORPDB
    |
    └── PDB SALES_PDB
         |
         ├── Authenticates SALES_APP
         ├── Applies SALES_APP privileges
         └── Queries SALES_APP.ORDERS
~~~

This is the **logical** diagram for a connection. In Oracle RAC or a load-balanced setup, a listener can redirect the client to another listener/instance; actual connection mechanics depend on the driver and Oracle Net design. Resolving the service name selects the logical target, whereas choosing the instance/handler is the physical routing step.

### Role of the Listener and Service Registration

The listener knows which services can accept connections through **service registration**. On modern Oracle systems, a registration process such as **LREG** supplies service/instance information to the listener; `LOCAL_LISTENER` and, in RAC environments, `REMOTE_LISTENER` determine where registration occurs.

Important points:

- **The listener running** does not guarantee **the service is known to the listener**.
- **The instance running** does not guarantee **the PDB is open**.
- **The PDB being open** does not guarantee **a custom service has been started**.
- **The service being registered** does not guarantee **the username/password is right** or the application has privileges on the schema.

Therefore, when a connection fails, inspect each link in the chain instead of blindly restarting the whole database.

## 4. SERVICE_NAME, SID, PDB Name, DB_NAME, and TNS Alias

The following names often appear together yet play different roles:

| Name | Represents | Where Is It Used? |
|---|---|---|
| **`DB_NAME`** | Database name per Oracle configuration | Identifying the database/CDB at the administrative level |
| **`INSTANCE_NAME` / SID** | Running Oracle instance | Instance administration, some legacy connection styles |
| **`PDB name`** | Logical container name | PDB administration, checking `CON_NAME` |
| **`SERVICE_NAME`** | Logical target requested by clients | JDBC URL, Oracle Net connect descriptor |
| **TNS alias** | Client-side alias for a connect descriptor | `tnsnames.ora` or Oracle Net configuration |
| **Schema/user** | Identity or object owner | Login and SQL statements, e.g., `SALES_APP.ORDERS` |

For example, all values can easily be distinct:

~~~text
DB_NAME       = CORPDB
INSTANCE_NAME = corp1
PDB_NAME      = SALES_PDB
SERVICE_NAME  = sales_app.example.com
TNS_ALIAS     = SALES_PROD
SESSION_USER  = SALES_APP
~~~

In an application that needs to select a **PDB**, prefer connecting via the appropriate **service name**. A `host:port:SID` string targets an instance rather than clearly specifying the destination PDB; it is especially error-prone in CDB/PDB or RAC environments.

### Easy Connect, TNS Alias, and Connect Descriptor

The following three forms can represent the exact same logical target:

**Easy Connect / JDBC Thin URL:**

~~~text
//db.example.internal:1521/sales_app.example.com

jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com
~~~

**An entry in `tnsnames.ora` on the client machine:**

~~~text
SALES_PROD =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)
               (HOST = db.example.internal)
               (PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = sales_app.example.com)))
~~~

**Client using the alias when Oracle Net is configured appropriately:**

~~~text
sqlplus SALES_APP@SALES_PROD
~~~

SQL*Plus will prompt for a password if not provided on the command line. `SALES_PROD` is only a **client alias**, not necessarily a service registered on the database. The alias entry can point to multiple hosts or include retry/timeout settings, while `SERVICE_NAME` inside the descriptor specifies the Oracle Net service to locate.

## 5. Default PDB Service vs. Application Service

Once a PDB is created, Oracle normally provides a default service tied to the PDB name for basic connectivity. However, for long-lived applications, a **dedicated service per application or workload** is usually easier to manage.

| Criterion | Default PDB Service | Dedicated Application Service |
|---|---|---|
| Purpose | Ensures the PDB has a basic connection endpoint | Identifies app/workload independently of the PDB name |
| Name | Usually tied to the PDB name | Chosen by architecture/DBA per naming standards |
| Lifecycle | Tied to the PDB and open mode | Requires managing start/stop state and appropriate configuration |
| Workload/HA configurability | More limited depending on platform/mechanism | Better suited for management via tools such as SRVCTL in RAC |
| Underlying changes | App may become coupled to the PDB name | Application-facing name remains more stable during controlled deployment changes |

Reasons to use an application service:

- **Decouples application config from physical names** of the database/instance.
- **Controls where workloads run** in multi-instance configurations.
- **Proactive operations:** an application's service can be stopped for maintenance without shutting down the entire CDB.
- **Classifies connections** for operations and monitoring; in supported environments, services also integrate with availability and workload management features.

Applications need a stable service name in their configuration. If tomorrow the system moves to another instance or the host topology changes, the DBA can adjust Oracle Net/services and address lists, minimizing the need to change SID names in Java code.

## 6. Creating and Operating a Service in a Single-Instance Environment

Illustrative example: CDB `CORPDB` contains `SALES_PDB`, and we want to create a service:

~~~text
Internal service: sales_app_svc
Network name:     sales_app.example.com
Target PDB:       SALES_PDB
~~~

**Prerequisites:** you have the required administrative privileges, the PDB exists, and it can be opened. `DBMS_SERVICE` syntax/capabilities depend on Oracle version and environment type; if the database is managed by Oracle Restart/RAC/Clusterware, manage services with the corresponding tool rather than creating competing services via other APIs.

### Step 1 — Check the PDB Before Configuring

From an administrative session in CDB root:

~~~sql
SHOW CON_NAME

SELECT name, open_mode
FROM v$pdbs
WHERE name = 'SALES_PDB';
~~~

If the PDB is not yet open, once verified as aligned with operational procedures:

~~~sql
ALTER PLUGGABLE DATABASE SALES_PDB OPEN READ WRITE;
~~~

In environments where the PDB open state should persist across CDB restarts, saved state can be configured:

~~~sql
ALTER PLUGGABLE DATABASE SALES_PDB SAVE STATE;
~~~

`SAVE STATE` records the desired open state of the PDB for future startups; it **does not guarantee** every service auto-starts across all deployment types. Services still need to be managed with an appropriate startup policy.

### Step 2 — Switch to the Right PDB

~~~sql
ALTER SESSION SET CONTAINER = SALES_PDB;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

Expected output is `SALES_PDB`. Creating the service in the **right PDB context** avoids configuring a service that does not belong to the intended container.

### Step 3 — Create and Start the Application Service

In a single-instance environment not using Clusterware service management, an example is:

~~~sql
BEGIN
  DBMS_SERVICE.CREATE_SERVICE(
    service_name => 'sales_app_svc',
    network_name => 'sales_app.example.com'
  );
END;
/

BEGIN
  DBMS_SERVICE.START_SERVICE(
    service_name => 'sales_app_svc'
  );
END;
/
~~~

Here:

- `service_name` is the internal administrative name of the service passed to the package.
- `network_name` is the name Oracle Net clients can request.
- Because the example runs **inside `SALES_PDB`**, the service is created for that PDB according to the context and version-supported mechanism.
- `START_SERVICE` makes the service available at runtime; creating metadata alone does not ensure the service is ready to accept connections.

If the service already exists, do not blindly re-run `CREATE_SERVICE`. Check existing services, registration status, and management policy before making changes.

### Step 4 — Confirm Registration with the Listener

On the Oracle server host, from the OS and when using the default listener:

~~~bash
lsnrctl status
lsnrctl services
~~~

`lsnrctl services` lists the services, instances, and handlers currently known to the listener. If the system uses a non-default listener or RAC/SCAN setup, inspect the **listener serving the client endpoint**, not just any arbitrary listener on the host.

Docker/VM images often have non-default listener names and ports; check according to the actual setup. There may be a brief delay between service startup and listener registration. If the service does not appear, inspect the PDB status, service status, and listener registration.

### Step 5 — Verify from a Real Client Session

Log in using a user **that already exists in `SALES_PDB`**:

~~~bash
sqlplus SALES_APP@//db.example.internal:1521/sales_app.example.com
~~~

SQL*Plus will prompt for the password. After logging in, run the container/service verification query shown in the next section.

### Stopping a Service for Maintenance

In an environment managing services via `DBMS_SERVICE`, the package can stop a service:

~~~sql
BEGIN
  DBMS_SERVICE.STOP_SERVICE(
    service_name => 'sales_app_svc'
  );
END;
/
~~~

Stopping a service affects **the ability to accept new connections** through that service; how existing sessions are handled depends on operational options and management tools. Do not assume `STOP_SERVICE` immediately terminates all application transactions. During maintenance, coordinate connection pools, drain traffic, wait for in-flight transactions, and use appropriate drain/service relocation mechanisms if supported by the platform.

## 7. Managing Services with Oracle RAC or Oracle Restart

In **Oracle RAC**, multiple instances can open the same CDB/database. A PDB can be accessed by applications via a service running on one or more instances. To manage lifecycle, placement, auto-start policy, and HA, Oracle uses **Oracle Clusterware/SRVCTL** in supported environments.

~~~text
                      Application
                          |
                          v
                   SCAN / Oracle Net
                          |
                    Service: SALES_APP
                          |
             +------------+------------+
             |                         |
             v                         v
        Instance corp1            Instance corp2
             |                         |
             +------------+------------+
                          |
                     CDB CORPDB
                          |
                     SALES_PDB
~~~

Here, two instances can serve **the same PDB** over **the same CDB dataset**. There are not two independent copies of `SALES_PDB` simply because there are two instances.

Illustrative RAC administrative commands:

~~~bash
# Descriptive example - replace DB_UNIQUE_NAME/instances per actual configuration.
srvctl add service -db CORPDB -service sales_app -pdb SALES_PDB -preferred corp1,corp2

srvctl start service -db CORPDB -service sales_app

srvctl status service -db CORPDB -service sales_app
~~~

Depending on Oracle version, service policy, database management mode, and RAC topology, `srvctl` options may differ; in practice DBAs must use the official syntax matching the deployment. This example highlights the core concept: **the service is bound to a PDB and managed by Clusterware across instances**.

### SCAN, Listeners, and Services in RAC

**SCAN (Single Client Access Name)** provides a stable access point for RAC; clients connect to the SCAN name/port, and the listener routes requests to an instance providing the service. Services can relocate across instances within configuration rules. Therefore:

- **Do not hard-code a single node's SID** as the sole target if the application needs redirection when that node stops serving.
- **Do not treat SCAN as the service**: SCAN is the network name/address; the service identifies the workload.
- **Do not treat a service as a fixed IP**: a service can be served by multiple instances or change placement.

Features such as **FAN**, **Fast Connection Failover**, **Application Continuity**, **Transaction Guard**, or load-balanced connections can enhance availability depending on version, driver/pool type, and service configuration. Naming a service alone does not activate all those features; applications must configure clients and test failure behavior.

## 8. Configuring Oracle JDBC for Java Applications

With JDBC Thin, the common Easy Connect format is:

~~~text
jdbc:oracle:thin:@//host:port/service_name
~~~

Example:

~~~text
jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com
~~~

When Java runs on the host machine, the hostname is one reachable by the client. When the application and Oracle run in **two containers on the same Docker Compose network**, the hostname can be the **Compose service name**, e.g., `db`; `localhost` inside the Java container is **not** the Oracle container:

~~~text
Java running on host:       jdbc:oracle:thin:@//localhost:1521/SALES_PDB
Java on Compose network:    jdbc:oracle:thin:@//db:1521/SALES_PDB
Enterprise environment:     jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com
~~~

These three examples use different network endpoints. `SALES_PDB` in the two lab examples is a valid service name **only if** Oracle has provisioned/registered that service; always verify the actual name instead of assuming every system uses that exact string.

### Plain JDBC with `DriverManager`

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

public class OraclePdbServiceDemo {
    public static void main(String[] args) throws Exception {
        String url =
            "jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com";
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password);
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(
                 "SELECT " +
                 "SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb_name, " +
                 "SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name, " +
                 "SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name " +
                 "FROM dual")) {

            if (result.next()) {
                System.out.println("PDB      = " + result.getString("PDB_NAME"));
                System.out.println("Service  = " + result.getString("SERVICE_NAME"));
                System.out.println("Instance = " + result.getString("INSTANCE_NAME"));
            }
        }
    }
}
~~~

This example assumes a compatible Oracle JDBC driver is on the classpath and environment variables are set for user/password. Never put passwords in the JDBC URL or commit them to a repository.

### Configuration in Spring Boot

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}
spring.datasource.driver-class-name=oracle.jdbc.OracleDriver
~~~

This is an example `application.properties` configuration. In real deployments, supply `DB_USER` and `DB_PASSWORD` via a secrets manager or appropriate environment-variable mechanism. The application must use a driver and pool compatible with the Oracle version.

If connections have already been created in a pool, changing the URL/service in config **does not necessarily** change the target of live physical connections. Plan a pool refresh/rolling deployment process, combined with verifying that the new service is registered and accepting connections.

## 9. Checking Service, PDB, and Instance via SQL

### 9.1. Checking from Any Logged-In Session

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_NAME')       AS database_name,
  SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
  SYS_CONTEXT('USERENV', 'CON_NAME')      AS container_name,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME')  AS service_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER')  AS session_user,
  SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Example output:

~~~text
DATABASE_NAME INSTANCE_NAME CONTAINER_NAME SERVICE_NAME           SESSION_USER CURRENT_SCHEMA
------------- ------------- -------------- ---------------------- ------------ --------------
CORPDB        corp1         SALES_PDB      sales_app.example.com  SALES_APP    SALES_APP
~~~

This is direct proof that **the current session** is in `SALES_PDB`, established via the corresponding service, running on instance `corp1`, and logged in as `SALES_APP`. When troubleshooting "connected successfully but wrong data," this query is usually far more helpful than just inspecting the URL in a config file.

### 9.2. Checking PDBs and Open State (Requires Appropriate Privileges)

From CDB root with administrative privileges:

~~~sql
SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;
~~~

If `SALES_PDB` is `MOUNTED` or not ready, the listener knowing the service name does not guarantee applications can log in. To have the PDB auto-open in its saved state on future startups, the DBA can use `SAVE STATE` as covered in the administration section.

### 9.3. Viewing Configured and Active Services

Example from a session permitted to read dynamic performance views:

~~~sql
SELECT name, network_name, pdb
FROM v$services
ORDER BY name;
~~~

~~~sql
SELECT name, network_name, pdb
FROM v$active_services
ORDER BY name;
~~~

`V$SERVICES` displays service metadata; `V$ACTIVE_SERVICES` shows services active within the instance/view scope. Depending on container, privileges, and version, displayed rows can vary. In RAC, `GV$` views and Clusterware status may be needed to see which instances are running a service.

Do not conclude a service is reachable by **external clients** solely because a database query returns its name. You must also verify it is registered with the listener on the right endpoint, DNS/networking works, and the client authenticates successfully.

### 9.4. Checking from the OS

~~~bash
lsnrctl status
lsnrctl services
~~~

These two commands run on a machine/container with Oracle Net tools; they are not SQL statements. They confirm what services and handlers the listener actually sees. In RAC you may need to check the right SCAN listener or node listener; in Docker pay attention to host port mappings.

## 10. Diagnostic Workflow When an Application Cannot Connect

Suppose Java configures `jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com` and reports an error. Trace in order from network to service, PDB, and privileges:

~~~text
Application cannot connect
          |
          v
Can host/port reach the listener?
     | no                     | yes
     v                        v
DNS, network, firewall       Has the listener registered the service?
                                | no               | yes
                                v                  v
                           Is service started?   Is PDB OPEN?
                           Is PDB open?             | no          | yes
                           LREG/registration?       v             v
                                                 Open PDB      User/password,
                                                               privilege,
                                                               connection pool
~~~

| Error or Symptom | Common Possibility | First Checks |
|---|---|---|
| `ORA-12541: TNS:no listener` | Cannot reach listener at requested host/port | DNS, host, port, firewall, is listener running |
| `ORA-12514` | Listener does not know the requested service | Verify `SERVICE_NAME`, `lsnrctl services`, service active, and PDB open |
| `ORA-12505` | Requested SID is not recognized by listener | Does connect string use SID or service; switch to appropriate service name |
| `ORA-12516` | Listener cannot find an available/suitable handler | Instance resources, session/process limits, handler/service state |
| `ORA-01017` | Credentials rejected | Username/password, target container, whether user exists in the PDB |
| `ORA-01033` or startup/shutdown message | Database/PDB not ready to serve | Open mode, startup logs, service status |
| Connection succeeds but `ORA-00942` on table query | Wrong PDB/schema or missing privilege | `CON_NAME`, `CURRENT_SCHEMA`, table owner name, grants |
| Right URL yet routed to another instance | Service may span multiple instances or relocated | `INSTANCE_NAME`, RAC policy, listener/SCAN |
| Changed service yet pool still connects to old target | Connection pool reuses open physical sessions | Planned switchover, refresh/drain pool, verify new sessions |

### Example Investigation of `ORA-12514`

1. Read the URL and identify the exact `SERVICE_NAME` requested by the application, such as `sales_app.example.com`.
2. On the target listener endpoint, run `lsnrctl services` to see if that service is registered.
3. If missing, check `V$ACTIVE_SERVICES` and `SALES_PDB` status inside the database; a custom service may not have been started.
4. Inspect listener registration mechanisms and related parameters if the service is active yet absent from the listener.
5. Once the listener knows the service and the PDB is open, test a **new** client connection and read `SYS_CONTEXT` to verify the actual PDB.

Avoid fixing this by randomly replacing `SERVICE_NAME` with `SID` or the CDB name. Doing so may route you elsewhere without solving proper registration of the application service.

### Example "Connected Successfully, Yet Wrong Data"

Within one CDB, `HR_PDB` and `SALES_PDB` might both have an `EMPLOYEES` table or identically named users. If a URL points to the wrong service, SQL may still run while reading a different dataset. Check:

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user
FROM dual;
~~~

Once `PDB` and `SERVICE` are confirmed right, then inspect the schema owner and object privileges. **Same host, same port, or same CDB is not enough to prove the right PDB.**

## 11. Services and Availability: What Does Routing Mean for Applications?

A service provides a **logical naming endpoint** for a workload, decoupling how applications call the database from the physical identity of an instance. However, failover capability does not appear automatically just because a URL has a service name.

### Single-Instance Case

If a CDB runs on a single instance and that instance stops, the service has nowhere to be served until the instance/database/PDB comes back up. Using a service does not turn a single instance into an HA system.

### Multi-Instance RAC Case

A service can be managed across multiple instances or relocated to an available instance per policy. Connection pools/drivers may need proper configuration to **receive state-change notifications** and recreate connections. In-flight transactions obey the semantics of the driver, database, and configured HA features; you cannot assume every running SQL statement continues seamlessly.

### Read-Write and Read-Only

Naming services `sales_rw` and `sales_ro` can serve architectural clarity, yet **the name does not enforce read-only**. To provide a dedicated read target, the DBA must design the proper environment and privileges (such as a PDB opened read-only in supported contexts, or an appropriate reporting/standby solution). Those policies must be coordinated with connection, transaction, and data-consistency requirements.

### Client-Side Timeout and Retry Management

Applications should configure connection establishment timeouts and sensible retry policies at the Oracle Net/connection pool layer. Aggressive or unbounded retries can cause a connection storm when the database recovers. Timeouts and retries cannot fix a wrong service name, wrong user, or closed PDB; distinguish configuration errors from transient outages.

## 12. Lab: Two PDBs, Two Services, and an Application

Assume:

~~~text
CDB: CORPDB
  ├── SALES_PDB
  │     service: sales_app.example.com
  │     local user: SALES_APP
  └── HR_PDB
        service: hr_app.example.com
        local user: HR_APP

Listener endpoint: db.example.internal:1521
~~~

Assume the services and users were created properly by the DBA. Learners do not need to recreate the CDB just to observe routing.

### Step 1 — Test Connecting to Sales

~~~bash
sqlplus SALES_APP@//db.example.internal:1521/sales_app.example.com
~~~

After entering the password:

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb_name,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Expected output:

~~~text
PDB_NAME   SERVICE_NAME           SESSION_USER
---------- ---------------------- ------------
SALES_PDB  sales_app.example.com  SALES_APP
~~~

### Step 2 — Test Connecting to HR

~~~bash
sqlplus HR_APP@//db.example.internal:1521/hr_app.example.com
~~~

Run the same `SYS_CONTEXT` SQL:

~~~text
PDB_NAME SERVICE_NAME         SESSION_USER
-------- -------------------- ------------
HR_PDB   hr_app.example.com   HR_APP
~~~

Host/port stayed the same; **service** changed, so the target PDB differs. The login user also changed to match each PDB's local account.

### Step 3 — If an Additional Service Exists on SALES_PDB

Suppose the DBA creates `sales_report.example.com` also bound to `SALES_PDB`. Connect to the new service with an appropriately privileged user, then check `CON_NAME`:

~~~text
SERVICE_NAME               CON_NAME
-------------------------- ---------
sales_app.example.com      SALES_PDB
sales_report.example.com   SALES_PDB
~~~

Two services point to one PDB yet can be managed as two separate workloads. **Do not** infer that `sales_report` is read-only solely from the service name; verify via access privileges and configured policies without performing arbitrary writes on important data.

### Step 4 — Wire Into a Java Application

Place the JDBC URL into the application's configuration variable. After establishing a connection, run SQL to read `CON_NAME` and `SERVICE_NAME` as in the JDBC section. If you change the service in config, refresh the connection pool to confirm new physical connections actually use the newly chosen service.

### Step 5 — Observe Impact When a PDB Closes (Only in an Approved Lab)

The DBA can stop accepting connections for the PDB/service in a test environment and use a client to open a **new connection** to observe the error. Then the DBA reopens the PDB and starts/registers the service per environment procedure. When doing this, understand that existing connections, open transactions, and new connection attempts can behave differently. Never close a shared PDB just for practice.

## 13. Common Misconceptions

1. **"A service is the PDB."** No. A service is a logical name for connections; a PDB is a container holding schemas and data. One PDB can have multiple services.
2. **"A service must equal the PDB name."** No. The default service usually relates to the PDB name, while application services can have custom names.
3. **"SID and SERVICE_NAME are interchangeable."** No. SID identifies an instance; service identifies a workload/logical target, which is critical for PDBs and RAC.
4. **"Reaching the right listener guarantees entering the right PDB."** No. A listener can know many services; the client must request the right service.
5. **"Once the PDB is open, every application service runs automatically."** Never assume this. Verify the start/registration status of the service and actual management policies.
6. **"Just changing the service URL immediately moves existing pooled connections to the other PDB."** No. Already-open physical connections keep their current session; manage pool/connection lifecycles properly.
7. **"A service named read_only blocks UPDATE statements by itself."** No. Enforcement relies on database/standby state, privileges, and actual policies.
8. **"A service guarantees failover for every transaction."** No. Behavior depends on HA architecture, driver, pool, and enabled availability features.
9. **"ORA-12514 only happens because of a wrong username/password."** No. It usually means the listener does not recognize the requested service; authentication fails at a later step.
10. **"Connecting successfully proves I am in the right environment."** No. Always verify `CON_NAME` and `SERVICE_NAME` when there is any doubt about the PDB.

## 14. Self-Check Questions

**Question 1.** Two applications use the same host and port `db.example.internal:1521`, but different services. Can they connect to two different PDBs?

**Answer:** Yes. The listener selects the target based on registered services; two services can bind to two different PDBs in the same CDB.

**Question 2.** `SALES_PDB` has services `sales_app.example.com` and `sales_report.example.com`. Do they necessarily hold two independent datasets?

**Answer:** No. If both services bind to the same `SALES_PDB`, they serve the same data container; privileges and workload configuration may differ.

**Question 3.** A client receives `ORA-12514` when connecting to service `sales_app.example.com`. Should you immediately change the connect string to `:corp1` (SID)?

**Answer:** No. First check the service name, service status, PDB status, and listener registration; SID is merely an instance identifier and does not replace service/PDB semantics.

**Question 4.** The DBA has opened `SALES_PDB` but has not started the custom-created application service. Is the application guaranteed to connect via that service?

**Answer:** No. PDB open state and service active/registered status are separate conditions. Check `V$ACTIVE_SERVICES` and the corresponding listener.

**Question 5.** A service is served by instance `corp2` instead of `corp1` in RAC. Does the application need to change the PDB name in its SQL?

**Answer:** No. The service still identifies the workload/PDB; the physical instance can change per configuration. The client/connection pool must support reconnecting according to the HA policy.

**Question 6.** A JDBC connection to the Sales service is borrowed from the pool and runs `SELECT` for several minutes. The DBA changes the service mapping for **new** connections. Does the running session automatically switch PDBs?

**Answer:** No. An already-connected session retains its current container context. Service changes affect new connection establishment per the updated configuration; manage old sessions and pool drain/refresh timing.

## 15. Final Summary Diagram

~~~text
             APPLICATION / CONNECTION POOL
                        |
                        | host + port + SERVICE_NAME
                        v
                  ORACLE NET / LISTENER
                        |
                        | service registration
                        v
                INSTANCE / SERVER PROCESS
                        |
                        | session bound to service's PDB
                        v
                      CDB
                        |
                        v
                       PDB
                        |
                        | user + password + privileges
                        v
                   SCHEMA / DATA
~~~

To route Oracle connections accurately, **use a dedicated application service name**, confirm the service is **registered and active**, verify the **PDB is open**, and once logged in read `SYS_CONTEXT('USERENV', 'CON_NAME')` alongside `SERVICE_NAME` to confirm the actual target. In RAC or JDBC pools, the service is also the central point for organizing workloads and redirecting connections, while failover policies, security, and connection lifecycle management still require dedicated configuration.
