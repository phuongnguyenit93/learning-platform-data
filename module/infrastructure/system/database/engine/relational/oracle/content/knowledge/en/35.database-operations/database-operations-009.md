# Monitoring Listener, Service, Database, and PDB Status

For an application to connect to Oracle Database, multiple components must work properly together: the listener must listen on the network endpoint, the database instance must be started and in an appropriate state, the pluggable database (PDB) must be open, the database service must be active and registered with the listener, and finally the client must use the correct connect descriptor and valid authentication credentials.

Therefore, checking that a single **lsnrctl status** command succeeds is not enough to conclude that applications can connect. The listener can be running while the database is closed; the database can be OPEN while the PDB containing the application schema is MOUNTED; the PDB can be OPEN while the application service has not been started or registered with the listener. A solid operational procedure must inspect each layer and clearly distinguish their states.

## 1. Four Layers to Monitor

| Component | Role | Verification Question |
|---|---|---|
| Listener | Receives Oracle Net connection requests and hands them off to the appropriate database service/handler | Is the process running, is the endpoint listening, and is the service registered? |
| Database instance/database | Manages memory, processes, and data; exposes OPEN/MOUNTED state | Has the instance started and is the database open for the expected operation? |
| PDB | Container holding the application's schema and data in multitenant architecture | Is the PDB OPEN in READ WRITE or the required mode? |
| Database service | Logical service name clients use to route connections to the database/PDB | Is the service active, advertised by the listener, and called by clients with the right name? |

The connection flow can be visualized as:

~~~text
Application / SQL*Plus
        |
        | host, port, service_name
        v
Oracle Net Listener
        |
        | select service and handler
        v
Database instance
        |
        v
PDB containing application schema
        |
        v
Database user / session
~~~

Each layer has its own state and inspection method. Identify the first failing layer before restarting or altering configurations.

## 2. What Is the Listener and How Does It Operate Independently?

Oracle Net Listener is the process that accepts incoming client connections. The listener listens on one or more protocol addresses, typically TCP with a host and port such as 1521. When a client requests a service, the listener locates an appropriate service handler and forwards the connection request to the database instance.

The listener is independent of the database instance:

- The listener can be running while the database is shut down.
- The database can be OPEN while the listener is not running.
- The listener can be running and showing the right endpoint without yet knowing about the database's service.
- One listener can serve multiple database services.
- A database can register services with a local listener or a listener on another host.

Therefore, the listener being up only confirms part of the connection path.

### Related Files and Components

- listener.ora: static listener configuration, listening addresses, and any static registration details if present.
- tnsnames.ora: connect identifiers/aliases on the client or server side.
- sqlnet.ora: Oracle Net settings such as naming methods and connection options.
- Listener log: records listener activity and connection requests per configuration.
- ADR: Automatic Diagnostic Repository, where Oracle stores logs and traces for multiple components.

Not every environment requires manually declaring database services in listener.ora. Databases normally register services dynamically with the listener.

## 3. Checking the Listener with lsnrctl

On hosts with Oracle Database or Oracle Grid Infrastructure installed, use the lsnrctl utility:

~~~text
lsnrctl status
~~~

If multiple listeners exist or the listener does not use the default name, specify the name:

~~~text
lsnrctl status LISTENER
~~~

The status command typically shows:

- Listener alias/name.
- Listener version.
- Start date.
- Listening endpoints, e.g., TCP host/port.
- Path to the listener parameter file.
- Path to the listener log.
- List of services known to the listener at the time of the check.

Illustrative sample output:

~~~text
Connecting to (DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=dbhost)(PORT=1521)))
STATUS of the LISTENER
------------------------
Alias                     LISTENER
Version                   ...
Start Date                ...
Uptime                    ...
Listening Endpoints Summary...
  (DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=dbhost)(PORT=1521)))
Services Summary...
  Service "orders.example.com" has 1 instance(s).
    Instance "ORCL", status READY, has 1 handler(s) for this service...
The command completed successfully
~~~

This is a formatting example, not fixed output. The number of endpoints, services, instances, and handlers depends on the actual configuration.

### Checking Services and Handlers

~~~text
lsnrctl services
~~~

Or:

~~~text
lsnrctl services LISTENER
~~~

This command shows deeper detail on services, instances, and handlers managed by the listener. Check:

- Does the service name match the application's connect descriptor?
- Which instance(s) are providing the service?
- Is the handler READY or BLOCKED?
- Is any handler overloaded or refusing connections?
- Does the listener know the application PDB's service or only other services?

A service may appear with status UNKNOWN when configured statically. That does not automatically mean the database is broken; check whether the service is statically or dynamically registered. With dynamic registration, the listener typically receives instance/handler status from the database.

### Common Listener Commands

| Command | Purpose |
|---|---|
| lsnrctl status | View status, endpoints, and service summary |
| lsnrctl services | View detailed services, instances, and handlers |
| lsnrctl start | Start the listener |
| lsnrctl stop | Stop the listener |
| lsnrctl reload | Reload listener configuration without a full stop/start |
| lsnrctl version | View listener version |
| lsnrctl help | View syntax and supported commands |

lsnrctl stop terminates the listener process and blocks new connections through that listener. Existing established database sessions generally continue running, but applications cannot use that listener to reconnect or fail over until the listener is running again. Do not run stop/start on production just to test. Before making changes, determine which listener serves the application, whether backup listeners exist, and whether a maintenance window is approved.

## 4. Listener Endpoints and listener.ora Configuration

A minimal TCP listener configuration may look like:

~~~ini
LISTENER =
  (DESCRIPTION_LIST =
    (DESCRIPTION =
      (ADDRESS =
        (PROTOCOL = TCP)
        (HOST = dbhost.example.com)
        (PORT = 1521)
      )
    )
  )
~~~

Listener name and addresses in the example must be replaced with your environment's configuration. HOST can be a hostname, IP address, or address matching the network design. In multi-homed environments, ensure the listener binds to the right interface permitted for client access.

After modifying listener.ora, verify and reload configuration per procedure:

~~~text
lsnrctl status LISTENER
lsnrctl reload LISTENER
lsnrctl status LISTENER
~~~

Reloading does not replace confirming that applications actually connect. Re-verify endpoints, services, and test connecting from a client machine.

### An Open Endpoint Does Not Mean the Firewall Is Open

A listener reporting that it is listening on port 1521 on the database host does not prove clients on every network can reach it. Firewalls, security lists, routes, DNS, NAT, and network ACLs can block the path.

Testing must be performed from the exact network zone used by the application. Testing only from localhost on the database server can miss firewall or DNS issues between the application server and database.

## 5. Dynamic Service Registration

The database usually registers service and instance information with the listener automatically via the LREG process. LREG sends registration updates so the listener knows which database services can accept connections.

Dynamic registration avoids statically declaring every service in the listener. Registration information can be affected by:

- Configured listener endpoints.
- LOCAL_LISTENER for local listeners.
- REMOTE_LISTENER in certain configurations, especially RAC/SCAN.
- Instance and service states.
- Status of the PDB associated with the service.
- Timing of LREG registration or re-registration.

Inspect related parameters:

~~~sql
SHOW PARAMETER local_listener;
SHOW PARAMETER remote_listener;
~~~

In some situations after fixing configuration or starting a listener, a DBA can instruct the database to re-register:

~~~sql
ALTER SYSTEM REGISTER;
~~~

This command requests the instance to register services with the configured listener(s). It does not start the database, open a PDB, or create a new service. If the service is not running or the listener endpoint is wrong, REGISTER will not fix the root cause on its own.

### LOCAL_LISTENER

LOCAL_LISTENER specifies the local listener address the instance uses for dynamic registration. The value can be a connect descriptor or an alias resolved via Oracle Net.

If LOCAL_LISTENER points to the wrong host/port, the listener may be running while the database fails to register services into the listener clients are actually connecting to.

### REMOTE_LISTENER

REMOTE_LISTENER commonly appears in RAC environments where instances register services with SCAN listeners or remote listeners per Grid Infrastructure configuration. Do not manually alter this parameter if the database is managed by Clusterware; use cluster management tools and follow release documentation.

### SERVICE_NAMES and Service Management

The SERVICE_NAMES parameter was historically used to specify service names for a database. Starting with Oracle Database 19c, Oracle deprecated customer use of this parameter for service management; for HA or clustered environments, manage services with SRVCTL/DBMS_SERVICE according to the supported model rather than relying on editing SERVICE_NAMES as a modern service administration method.

In RAC or Grid Infrastructure-managed environments, use SRVCTL to create, configure, start/stop, and inspect services. For standalone databases, DBAs can use DBMS_SERVICE per version documentation when managing application services.

## 6. Checking Database Instance Status

After verifying the listener, log in to the database with an account privileged to check status. On the database host, DBAs can use OS authentication if configured:

~~~text
sqlplus / as sysdba
~~~

Never use SYSDBA credentials in applications. This is a special administrative privilege reserved strictly for controlled DBA operations.

### Checking the Instance

~~~sql
SELECT instance_name,
       host_name,
       status,
       startup_time
  FROM v$instance;
~~~

Common instance statuses:

| STATUS | General Meaning |
|---|---|
| STARTED | Instance has started, but the database is not mounted yet |
| MOUNTED | Control file is mounted; database is not OPEN yet |
| OPEN | Instance has opened the database |

Certain statuses or details may vary during recovery, shutdown, or by version. If the instance returns no rows or cannot be connected to, inspect OS processes, the alert log, and startup state.

### Checking the Database

~~~sql
SELECT name,
       db_unique_name,
       open_mode,
       database_role
  FROM v$database;
~~~

OPEN_MODE shows the open mode of the database, such as READ WRITE, READ ONLY, or MOUNTED. DATABASE_ROLE shows the role such as PRIMARY or PHYSICAL STANDBY. You cannot look solely at instance STATUS and conclude the database is ready for writes.

Example:

| Instance status | Database open_mode | Interpretation |
|---|---|---|
| OPEN | READ WRITE | Database is open for read/write operations per privileges and configuration |
| OPEN | READ ONLY | Database is open read-only |
| MOUNTED | MOUNTED | Database is not OPEN yet |
| STARTED | No matching database result | Instance started, but database is not mounted |

If the database is a standby or undergoing switchover/failover, READ ONLY/READ WRITE must be interpreted according to database role and Data Guard state. Do not arbitrarily open a database in a mode incompatible with its operational role.

## 7. Checking PDBs in a CDB

In Oracle Multitenant, a CDB can contain multiple PDBs. A PDB can be closed while the CDB root remains OPEN. Therefore, an OPEN database does not automatically mean applications in every PDB can connect.

From SQL*Plus connected to the CDB root:

~~~sql
SHOW CON_NAME;
SHOW PDBS;
~~~

Or query:

~~~sql
SELECT name,
       open_mode,
       restricted
  FROM v$pdbs
 ORDER BY name;
~~~

Common statuses:

| OPEN_MODE | Meaning |
|---|---|
| MOUNTED | PDB is not open yet |
| READ WRITE | PDB is open for read/write |
| READ ONLY | PDB is read-only |

RESTRICTED indicates whether the PDB is in restricted mode. A PDB that is READ WRITE with RESTRICTED = YES may only allow sessions with specific privileges to connect. Regular application users may be unable to log in.

### Opening a PDB

If a PDB should be open and the DBA has confirmed the action is appropriate:

~~~sql
ALTER PLUGGABLE DATABASE salespdb OPEN;
~~~

Open all PDBs:

~~~sql
ALTER PLUGGABLE DATABASE ALL OPEN;
~~~

Do not run OPEN ALL mechanically across every environment. Some PDBs are designed to stay closed, read-only, serve standby roles, or open only during batch windows.

### Saving Open State Across Restarts

If you want Oracle to automatically restore PDB state after a CDB restart:

~~~sql
ALTER PLUGGABLE DATABASE salespdb SAVE STATE;
~~~

Or:

~~~sql
ALTER PLUGGABLE DATABASE ALL SAVE STATE;
~~~

SAVE STATE persists the current open state of the PDB to be restored on the next CDB startup per Oracle behavior. Identify which PDBs genuinely need to auto-open on startup; do not save state for temporary PDBs or those requiring manual control.

### Closing a PDB

~~~sql
ALTER PLUGGABLE DATABASE salespdb CLOSE IMMEDIATE;
~~~

Closing a PDB terminates/impacts application sessions inside that PDB. Perform only with maintenance planning, service checks, session handling, and confirmed business impact.

## 8. What Is a Database Service?

A database service is a logical name describing a workload or connection target requested by clients. Services decouple how applications connect from specific instance names or SIDs.

For example, a database might expose:

- orders_rw.example.com: service for the order read/write application.
- reports_ro.example.com: service for read-only reporting.
- batch.example.com: service for batch jobs.

These names are examples only. Services can be tied to databases/PDBs, workload attributes, database roles, or HA configurations by design.

### Service Name vs. SID

A SID identifies a single instance. A service name identifies the logical service a client wants to access. In multi-instance or RAC environments, clients should connect using an appropriate service name rather than depending on a fixed SID.

Example connect descriptor:

~~~text
ORDERS =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = dbhost.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = orders_rw.example.com)
    )
  )
~~~

Clients can connect using the ORDERS alias in tnsnames.ora or via EZCONNECT:

~~~text
sqlplus app_user@//dbhost.example.com:1521/orders_rw.example.com
~~~

The connect string must use the service name configured by the DBA and registered with the listener. Do not guess the service name from DB_NAME or SID.

### Services Bound to PDBs

In Multitenant, an application service is typically associated with a specific PDB. When a client connects with the right service, the session is routed into the corresponding PDB. If the service is bound to the wrong PDB or the PDB is closed, the application may fail to connect or access the wrong schema.

Oracle automatically creates a default service for each PDB. For production applications, use application-defined services managed under operational/HA policies instead of relying on the default PDB service for every workload.

## 9. Checking Services Inside the Database

### Viewing Services Known to the Database

~~~sql
SELECT name,
       network_name,
       con_id
  FROM v$services
 ORDER BY con_id, name;
~~~

V$SERVICES displays service information in the database. CON_ID identifies the associated container in Multitenant environments. Specific columns may change by release; if a column is missing in your version, check that release's data dictionary reference.

### Viewing Currently Active Services

~~~sql
SELECT name,
       network_name,
       con_id
  FROM v$active_services
 ORDER BY con_id, name;
~~~

V$ACTIVE_SERVICES reflects services currently active in the current instance. In RAC, query GV$ACTIVE_SERVICES or GV$SERVICES to aggregate across instances; pay attention to INST_ID and CON_ID.

### Viewing Which Service Sessions Are Using

~~~sql
SELECT username,
       service_name,
       module,
       machine,
       status,
       COUNT(*) AS session_count
  FROM v$session
 WHERE username IS NOT NULL
 GROUP BY username,
          service_name,
          module,
          machine,
          status
 ORDER BY service_name, session_count DESC;
~~~

This query reveals which services active sessions are using. It does not show configured services that currently have zero sessions.

### Checking Services in the Current PDB

When connected directly to a PDB:

~~~sql
SHOW CON_NAME;

SELECT name,
       network_name
  FROM v$services
 ORDER BY name;
~~~

Compare the service the application uses against the services of the target PDB. If connected to the wrong service, an application might log in successfully but operate on an unintended schema/database.

## 10. Managing Services with SRVCTL in RAC/Grid Infrastructure

In Oracle RAC or environments where services are managed by Clusterware, use SRVCTL to inspect and operate services. Do not manually manage cluster services by editing parameters or calling DBMS_SERVICE if the service is owned by Grid Infrastructure.

Example:

~~~text
srvctl status database -db ORCL
srvctl config database -db ORCL
srvctl status service -db ORCL
srvctl config service -db ORCL
~~~

Checking a specific service:

~~~text
srvctl status service -db ORCL -service orders_rw
srvctl config service -db ORCL -service orders_rw
~~~

Starting or stopping a service:

~~~text
srvctl start service -db ORCL -service orders_rw
srvctl stop service -db ORCL -service orders_rw
~~~

Database and service names must come from the actual configuration. Option syntax can differ across Grid Infrastructure versions; check srvctl -help or release documentation before executing.

### Why Use SRVCTL?

SRVCTL understands cluster topology, preferred/available instances, database roles, and service attributes. When a service is managed by Clusterware, SRVCTL keeps configuration consistent and allows Clusterware to monitor, restart, or relocate services according to policy.

Do not use lsnrctl stop as a substitute for stopping a database service. A listener may serve many other services and databases; stopping the listener has a much broader blast radius.

## 11. Managing Services in a Standalone Database

In standalone environments where services are not managed by Clusterware, Oracle provides DBMS_SERVICE to manage application services per version capabilities.

Illustrative example creating and starting a service in a suitable environment:

~~~sql
BEGIN
  DBMS_SERVICE.CREATE_SERVICE(
    service_name => 'orders_rw',
    network_name => 'orders_rw.example.com'
  );

  DBMS_SERVICE.START_SERVICE(
    service_name => 'orders_rw'
  );
END;
/
~~~

This is an API example, not a generic script for RAC or all releases. Verify privileges, database state, PDB context, and service management guidelines for your specific version. For Grid Infrastructure-managed services, use SRVCTL.

Services must be bound to the appropriate PDB and attributes if using Multitenant. Do not just verify that a service exists in DBA_SERVICES; verify that the service is active and the listener has received its registration.

## 12. Client-Side Checks: tnsping and Actual SQL Connection

### tnsping

~~~text
tnsping ORDERS
~~~

tnsping tests connect identifier resolution and reachability to the listener using the connect descriptor. It does not perform database authentication, validate usernames/passwords, or prove the PDB or service is ready to execute SQL.

Consequently:

- tnsping succeeds but SQL*Plus fails: the listener is reachable, but the service, database, PDB, or authentication has an issue.
- tnsping fails: check the alias, naming method, DNS, routing, firewall, host, and port.

### Testing an Actual Connection

~~~text
sqlplus -L app_user@//dbhost.example.com:1521/orders_rw.example.com
~~~

After connecting, run a lightweight query:

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
  SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

The output confirms the client landed in the expected database, PDB/container, service, and user. This check is far more meaningful than looking at listener status alone.

### Testing from the Right Host and Network Zone

A successful connection from the database server does not prove an application server can connect. Test from the host or network zone closest to the application, using the exact same DNS, port, service name, and authentication mechanism. If load balancers, SCAN, or VIPs are involved, test the exact endpoint used by the application.

## 13. Common Connection Errors Table

| Error Code | Common Meaning | First Check |
|---|---|---|
| ORA-12154 | Could not resolve the connect identifier | tnsnames.ora, naming method, alias, and TNS_ADMIN |
| ORA-12541 | No listener at the requested endpoint | Listener process, host, port, firewall, and endpoint |
| ORA-12514 | Listener does not currently know of the requested service name | SERVICE_NAME, dynamic registration, service/PDB status |
| ORA-12505 | Listener does not know of the requested SID | Whether connect descriptor uses SID or SERVICE_NAME; check SID only if truly required |
| ORA-12516 / ORA-12519 | Listener could not find an available handler or no appropriate handler available | Handler status, process/session limits, database load, and service registration |
| ORA-12545 | Connect failed because target host or object does not exist | DNS, hostname, routing, and network |
| ORA-01034 | Oracle instance not available | Instance status, startup/shutdown, and alert log |
| ORA-01033 | Oracle initialization or shutdown in progress | Startup/shutdown progress, alert log |
| ORA-01109 | Database not open | V$INSTANCE, V$DATABASE, and startup state |
| ORA-65019 | Pluggable database not open | V$PDBS, OPEN_MODE, and PDB status |
| ORA-01017 | Invalid username/password | Credentials, case sensitivity, authentication, and secret rotation |
| ORA-28000 | The account is locked | DBA_USERS, profiles, and account policy |

Error messages may appear alongside other root errors on the server/client. Do not modify the listener or open a database based solely on an error code; verify the connect descriptor and the state of each layer.

## 14. Layered Health Check Procedure

A connectivity verification runbook can follow this order:

### Step 1: Identify the Endpoint the Client Uses

Collect hostname, port, service name, alias, protocol, expected PDB, and actual service name from application configuration. Do not substitute SID for service name when the architecture requires a service.

### Step 2: Check Listener Process and Endpoints

~~~text
lsnrctl status LISTENER
lsnrctl services LISTENER
~~~

Confirm the right listener name, right host/port endpoints, and no obvious errors.

### Step 3: Check Instance and Database

~~~sql
SELECT instance_name, status, startup_time
  FROM v$instance;

SELECT name, db_unique_name, open_mode, database_role
  FROM v$database;
~~~

Determine whether the database is OPEN in the expected mode or MOUNTED/READ ONLY.

### Step 4: Check PDBs

~~~sql
SELECT name, open_mode, restricted
  FROM v$pdbs
 ORDER BY name;
~~~

Confirm the PDB hosting the application is open and not unexpectedly restricted.

### Step 5: Check Services

~~~sql
SELECT name, network_name, con_id
  FROM v$services
 ORDER BY con_id, name;

SELECT name, network_name, con_id
  FROM v$active_services
 ORDER BY con_id, name;
~~~

Compare configured services against active services. In RAC, check via SRVCTL and GV$ views as needed.

### Step 6: Test from Client

~~~text
tnsping ORDERS
sqlplus -L app_user@//dbhost.example.com:1521/orders_rw.example.com
~~~

Connect from the application host and run a query confirming DB/PDB/service/user.

### Step 7: Inspect Logs

If any layer fails, review the listener log, database alert log, Grid Infrastructure logs, and application logs around the same time. Record timestamps, timezones, host, service, SQL_ID, or session details when available.

## 15. Listener Log and Database Alert Log

### Listener Log

lsnrctl status usually prints the listener log path. Inside ADR, the listener log typically sits under:

~~~text
diag/tnslsnr/<host>/<listener_name>/trace/listener.log
~~~

The listener log helps investigate:

- Which client host originated the connection.
- Which service name was requested.
- Connection timestamps and Oracle Net errors.
- Endpoint details and listener state.

Logs can contain hostnames, IPs, service names, and connection metadata. Restrict read permissions and handle them according to log protection policies.

### Database Alert Log

The alert log records major events such as startup/shutdown, internal errors, state transitions, recovery, and warnings. Locate it via ADR or inspect it using ADRCI:

~~~text
adrci
show homes
set home diag/rdbms/<db_unique_name>/<instance_name>
show alert -tail 100
~~~

Home paths depend on DB name, instance, and ADR configuration. Before running ADRCI commands, select the exact home from show homes output.

If the database fails to OPEN, the alert log is usually one of the first places to look for startup, mount, or recovery errors.

## 16. Monitoring in RAC Environments

In RAC, instances can run on different nodes, and services can be distributed or relocated across instances per configuration. Distinguish:

- Local listener on each node.
- SCAN listeners.
- VIPs and public/private network addresses.
- Instances currently hosting the service.
- Service preferred/available instances.
- Database role and service role when Data Guard is integrated.

Common commands:

~~~text
srvctl status listener
srvctl status scan_listener
srvctl status database -db ORCL
srvctl status service -db ORCL
~~~

Check service configuration:

~~~text
srvctl config service -db ORCL -service orders_rw
~~~

Inside the database:

~~~sql
SELECT inst_id,
       name,
       network_name,
       con_id
  FROM gv$active_services
 ORDER BY name, inst_id;
~~~

INST_ID shows which instance(s) currently have the service active. A service may run on one or multiple instances depending on policy.

Do not run lsnrctl stop on a node as a way to stop an application service. For Clusterware-managed services, operate through SRVCTL and cluster operational procedures.

## 17. Monitoring Services in Data Guard Environments

If databases operate as primary/standby, application services can be configured to run only under the appropriate database role. During switchover or failover, services should start on the database that newly becomes primary per design.

When checking:

- Check DATABASE_ROLE in V$DATABASE.
- Check whether services are configured with role-based policies.
- Confirm the service is active on the database currently acting as primary.
- Confirm client connect descriptors, DNS, SCAN, or endpoints switched properly.
- Verify the PDB is open and services are attached to the PDB.
- Test connecting from the application network.

Do not start a read/write service on a standby just because the listener exposes an endpoint. Services must match the database role and Data Guard policy.

## 18. Continuous Monitoring and Alert Design

A monitoring system should separate multiple types of health checks:

| Check | Suggested Frequency | Alert When |
|---|---|---|
| Listener process/endpoint | Short interval aligned with SLA | Listener is not listening on required endpoints |
| Service registration | Periodic | Application service is not recognized by the listener |
| Database state | Periodic | Instance/database is not in the expected state |
| PDB state | Periodic | Application PDB is closed or unexpectedly restricted |
| Synthetic client login | Per application SLA | Real connection from the application network fails |
| Application query | Per SLA | Verification query or API health endpoint fails |
| Listener/database logs | Event-driven | Repeated or critical errors appear |

Frequency should balance SLA requirements, query cost, and monitoring system capacity. Avoid polling heavy views at overly aggressive intervals.

### What Should a Health Check Verify?

A good connectivity check should:

1. Use the exact endpoint and service name used by the application.
2. Use a least-privilege monitoring account.
3. Perform a real login instead of just tnsping.
4. Run a lightweight query confirming database, PDB, and service.
5. Enforce clear timeouts.
6. Never print passwords or tokens to logs.
7. Return unambiguous status so monitoring distinguishes listener, service, database, PDB, and authentication failures.

Example verification query after login:

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_UNIQUE_NAME') AS db_unique_name,
  SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb_name,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

If the monitoring account lacks privileges to query V$ views, SYS_CONTEXT can verify connection context without granting broad administrative privileges.

### Avoiding False Positives

A listener with no application services registered may be completely normal if the database is in scheduled maintenance shutdown. A READ ONLY PDB may be expected if it serves reporting. A service inactive on one node may be normal if policy runs it only on another node.

Monitoring must compare actual state against the expected state for each environment, database role, maintenance window, and service policy. Do not apply one blanket threshold to every PDB.

## 19. Common Operational Scenarios

### Listener Is Running, but Service Does Not Appear

Check:

1. Is the database instance OPEN?
2. Is the PDB hosting the service OPEN?
3. Does the service exist and is it active?
4. Do LOCAL_LISTENER/REMOTE_LISTENER point to the right endpoints?
5. Is the listener you are inspecting the same listener the database registers with?
6. Has LREG re-registered yet?

After confirming the configuration is correct, you can request re-registration:

~~~sql
ALTER SYSTEM REGISTER;
~~~

If it still does not appear, check the alert log, listener log, and service configuration rather than repeatedly running REGISTER.

### Listener Knows the Service, but Client Receives ORA-12514

The client may be connecting to a different listener, using the wrong service name, or the service may only be registered on another listener/endpoint. Compare the exact host, port, and service name in the connect descriptor against lsnrctl services on the endpoint the client is actually hitting.

### Database Is OPEN, but Application Cannot Connect

Check the PDB, service, handlers, account status, password, firewall, service name, and process/session limits. Do not restart the database when the actual issue is a locked account or an unstarted service.

### PDB Is Closed After a CDB Restart

Check PDB open mode and saved state. If the PDB should auto-open after restart, confirm its state was saved with SAVE STATE per design and verify the alert log shows no errors opening the PDB.

### Service Is Running on Another Node

In RAC, this may be expected behavior due to service placement or failover. Use SRVCTL and GV$ACTIVE_SERVICES to verify current placement rather than inferring from a single local listener.

## 20. Troubleshooting Order and Change Principles

When connections fail, troubleshoot from the outside in:

1. Connect descriptor and DNS/hostname.
2. Network routing, firewall, and TCP endpoint.
3. Listener process and listening endpoints.
4. Service registration and handlers.
5. Database instance and database open mode.
6. PDB open mode and restricted status.
7. Active service bound to the right PDB.
8. Authentication, account status, and privileges.
9. Application, connection pool, and transactions.

Never restart the entire database or listener as the first step. Restarts disrupt other services and can erase root-cause evidence. Collect timestamps, full error messages, listener logs, alert logs, instance/PDB/service states, and test connection output before making changes.

Commands such as ALTER PLUGGABLE DATABASE, SRVCTL start/stop service, lsnrctl stop/start, or shutdown/startup operations can impact users. Execute them only with proper authorization, confirmed scope, and approved change procedures.

## 21. Operational Checklist Template

- [ ] Identify hostname, port, service name, and PDB required by the application.
- [ ] Confirm the exact listener name and endpoints.
- [ ] Run lsnrctl status and lsnrctl services.
- [ ] Check the listener log if Oracle Net errors occur.
- [ ] Check V$INSTANCE and V$DATABASE.
- [ ] Check V$PDBS and restricted status.
- [ ] Check V$SERVICES and V$ACTIVE_SERVICES.
- [ ] For RAC, check SRVCTL and GV$ACTIVE_SERVICES.
- [ ] Verify LREG registration and LOCAL_LISTENER/REMOTE_LISTENER if the service is missing.
- [ ] Run tnsping from the client to check alias/endpoint resolution.
- [ ] Test an actual SQL login from the application network.
- [ ] Use SYS_CONTEXT to verify database, PDB, service, and user.
- [ ] Check account status, handlers, and process/session limits if login fails.
- [ ] Cross-reference listener log, database alert log, and application logs.
- [ ] Record results, timestamps, operator, and applied changes.

## 22. Conclusion

Monitoring the Oracle listener, services, database, and PDB must be executed as a multi-layered workflow. lsnrctl status confirms the listener and endpoints; lsnrctl services reveals the services/handlers known to the listener; V$INSTANCE and V$DATABASE reflect instance/database state; V$PDBS shows whether the PDB is open; V$SERVICES, V$ACTIVE_SERVICES, and SRVCTL verify active services and where they are hosted.

Finally, test a real connection from the application network using the exact service name and confirm context with SYS_CONTEXT. tnsping only verifies name resolution and listener reachability; it does not prove database login succeeds. When an incident occurs, identify the first failing layer, read the listener/database logs, and change a service, PDB, listener, or instance only after confirming the scope of impact. This disciplined approach pinpoints the true root cause and avoids unnecessary restarts.
