# ORA-12154, ORA-12514, ORA-12541, and Oracle Net Diagnostics

When an application connects to Oracle Database, connection errors often appear before the first SQL statement is executed. Three common Oracle Net errors are **ORA-12154**, **ORA-12541**, and **ORA-12514**. They have similar-looking codes but occur at different layers:

- **ORA-12154 — Could not resolve the connect identifier specified:** the client cannot resolve the alias/connect identifier into a connect descriptor. Usually related to tnsnames.ora, sqlnet.ora, TNS_ADMIN, naming method, or the connect string.
- **ORA-12541 — No listener:** the client has a target address but cannot reach a listener at the specified host/port or IPC key. Usually related to a stopped listener, wrong host/port, DNS, firewall, or network path.
- **ORA-12514 — Listener does not currently know of service requested:** the client reached the listener, but the listener does not know the requested service name. Usually related to an incorrect SERVICE_NAME, a stopped database/PDB/service, or incomplete dynamic service registration.

Effective diagnosis must follow the proper order: **name resolution → host/port resolution → listener check → service registration check → database session authentication → application check**. Skipping this order easily leads DBAs to edit listener.ora unnecessarily, change service names, or restart the database when the issue lies on the client machine or network.

This lesson belongs to the **Troubleshooting** group of Database Engine Relational Oracle. It focuses on Oracle Net architecture, naming methods, connect descriptors, the three errors ORA-12154/12514/12541, listener/service registration, PDB/RAC, JDBC connection strings, listener logs, ADR, tracing, and a client-to-database diagnostic runbook.

After this lesson, you will be able to:

- Distinguish connect identifier, net service name, connect descriptor, SID, and SERVICE_NAME.
- Understand the roles of the Oracle Net client, listener, LREG, and database service.
- Locate the exact tnsnames.ora and sqlnet.ora files actually used by the client.
- Read and fix structural errors in tnsnames.ora.
- Use Easy Connect to isolate alias errors from listener/service errors.
- Distinguish ORA-12154 from ORA-12541 and ORA-12514.
- Check the listener using lsnrctl status and lsnrctl services.
- Check TCP ports using operating system tools.
- Check service registration via LREG, LOCAL_LISTENER, and REMOTE_LISTENER.
- Re-register services with ALTER SYSTEM REGISTER when appropriate.
- Handle services for PDBs and Oracle RAC.
- Diagnose connections from SQL*Plus, JDBC Thin Driver, connection pools, and database links.
- Read listener logs, SQL*Net logs, ADR, and trace files.
- Distinguish tnsping from an actual database login.
- Build a runbook and collect evidence before making configuration changes.

> **Example scope:** Content is primarily based on Oracle Database 19c. Hosts, services, ports, and paths in examples are illustrative. Replace them with values from your actual environment. Do not expose passwords, wallets, connect descriptors containing sensitive information, or unredacted traces/logs.

## 1. Oracle Net in a Connection Attempt

Oracle Net Services provides naming, addressing, listener, and connectivity mechanisms between clients and Oracle Database.

### 1.1. Components

| Component | Role |
| --- | --- |
| Oracle client | Application or tool sending the connection request |
| Connect identifier | Name or connection string supplied by the client |
| Naming method | Method used to resolve the connect identifier |
| tnsnames.ora | Local repository containing net service names |
| sqlnet.ora | Oracle Net client/server configuration, naming order, timeouts, security, and diagnostics |
| Connect descriptor | Protocol, host, port, and connect data details |
| Listener | Process receiving initial connection requests on the database server |
| LREG | Background process that registers services/instances with the listener |
| Database service | Logical endpoint name requested by the client |
| Database instance | Instance executing the database workload |
| PDB service | Service used to connect to the appropriate pluggable database |

### 1.2. General Connection Flow

~~~text
Java / SQL*Plus / SQL Developer
             |
             v
       Connect identifier
             |
             v
        Naming method
    (TNSNAMES / EZCONNECT / LDAP)
             |
             v
       Connect descriptor
       HOST + PORT + SERVICE
             |
             v
      DNS / Network / TCP
             |
             v
       Oracle Net Listener
             |
             v
     Registered service handler
             |
             v
      Database instance / PDB
             |
             v
       Authentication / Session
~~~

Common errors can be pinpointed along this flow:

- ORA-12154: failure at the naming method step, before the client obtains a valid connect descriptor.
- ORA-12541: unable to reach the listener address in the descriptor.
- ORA-12514: the listener received the request, but the service name in connect data is not yet known to the listener.

### 1.3. The Listener Is Not the Database Instance

The listener is a separate process running on the database server host. It receives incoming requests and hands off connections to the appropriate service handler. A database instance may be running while the listener is stopped; in that case, remote clients still encounter ORA-12541.

Conversely, the listener may be running normally while the database service has not yet registered; in that case, clients encounter ORA-12514.

### 1.4. A Service Is Not a SID

A service name is the logical identifier that applications should use to connect. A SID typically identifies an Oracle instance. For modern databases, especially RAC and Multitenant, prefer service names instead of relying on SIDs.

Example:

~~~text
(CONNECT_DATA =
  (SERVICE_NAME = sales.example.com)
)
~~~

SERVICE_NAME must be a service known to the listener. Do not guess a service name from DB_NAME, SID, PDB name, or host name.

## 2. Connect Identifier, Connect Descriptor, and Net Service Name

These three concepts are often loosely called a TNS name, but they have distinct roles.

### 2.1. Connect Identifier

The connect identifier is the value the client provides in the connect command.

Example:

~~~text
sqlplus app_user@SALES_PROD
~~~

In this example, SALES_PROD is the connect identifier. It can be an alias in tnsnames.ora, an LDAP name, or an Easy Connect string.

### 2.2. Net Service Name

A net service name is the name defined in a naming repository, for example:

~~~text
SALES_PROD =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = db-sales.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = sales.example.com)
    )
  )
~~~

SALES_PROD is the alias; the DESCRIPTION block is the connect descriptor.

### 2.3. Connect Descriptor

The descriptor specifies how to connect:

- Protocol: TCP, TCPS, or IPC.
- Host or listener address.
- Port or IPC key.
- Service name or other connect data details.
- Optionally failover/load-balancing/address lists and additional options.

### 2.4. SID and SERVICE_NAME

Example descriptor using a service:

~~~text
(CONNECT_DATA =
  (SERVICE_NAME = sales.example.com)
)
~~~

Example descriptor using a SID:

~~~text
(CONNECT_DATA =
  (SID = SALES)
)
~~~

Do not replace SERVICE_NAME with SID just as a random trial. Check the listener services output and the details provided by the DBA.

## 3. Naming Methods

Oracle Net supports multiple methods to resolve a connect identifier.

### 3.1. Local Naming — TNSNAMES

Local naming looks up aliases in the tnsnames.ora file.

Example:

~~~text
SALES_PROD =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = db-sales.example.com)(PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = sales.example.com))
  )
~~~

Connect:

~~~text
sqlplus app_user@SALES_PROD
~~~

### 3.2. Easy Connect

Easy Connect lets you specify host, port, and service directly without an alias in tnsnames.ora.

Common syntax:

~~~text
//host:port/service_name
~~~

Example:

~~~text
sqlplus app_user@//db-sales.example.com:1521/sales.example.com
~~~

Easy Connect helps quickly test whether the problem lies in the TNS alias. If the alias fails with ORA-12154 while Easy Connect succeeds, focus on checking the naming configuration.

### 3.3. Directory Naming — LDAP

The connect identifier is resolved via a directory server. Check:

- ldap.ora.
- DIRECTORY_SERVERS.
- DEFAULT_ADMIN_CONTEXT.
- LDAP server host/port and DNS.
- Whether the net service name exists in the Oracle Context.

If the LDAP server is unreachable or the default context is wrong, the alias may fail to resolve even if tnsnames.ora has no errors.

### 3.4. External Naming

Some environments use external naming adapters such as NIS. Identify the naming method actually configured rather than assuming all clients use TNSNAMES.

### 3.5. NAMES.DIRECTORY_PATH

In sqlnet.ora, the NAMES.DIRECTORY_PATH parameter determines the order in which naming methods are tried.

Example:

~~~text
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT, LDAP)
~~~

If the application uses an alias in tnsnames.ora but TNSNAMES is not in the list, Oracle Net may not try local naming.

If the application uses Easy Connect but EZCONNECT is not configured in the list, the connect string may not resolve as expected.

Do not alter the entire production naming path just to fix a single client. Check policy and which naming methods other applications rely on.

## 4. ORA-12154 — Could not resolve the connect identifier specified

### 4.1. Meaning

ORA-12154 occurs when Oracle Net cannot translate the connect identifier into a connect descriptor using the configured naming methods.

Example:

~~~text
ORA-12154: TNS:could not resolve the connect identifier specified
~~~

This error typically occurs before connecting to the listener. Therefore, restarting the listener or database usually does not resolve the cause.

### 4.2. Common Causes

- The alias is misspelled or does not exist.
- tnsnames.ora is not located in the directory the Oracle client is using.
- The TNS_ADMIN environment variable points to a different directory.
- Multiple Oracle Homes exist and the client is using the wrong home.
- NAMES.DIRECTORY_PATH is missing TNSNAMES or EZCONNECT.
- The tnsnames.ora file has unbalanced parentheses or stray characters.
- The alias has a domain suffix that does not match the connect string.
- NAMES.DEFAULT_DOMAIN causes a domain to be appended unexpectedly.
- LDAP naming is unreachable or the default context is wrong.
- JDBC Thin Driver is not configured with the appropriate TNS_ADMIN.
- A database link is executed from the database server, but the server-side Oracle Net config is missing the alias.

### 4.3. Step 1 — Identify Which Client Is Failing

First determine:

- Is the application running on a developer workstation, application server, container, or database server?
- Does the tool use Oracle Client, Instant Client, or JDBC Thin Driver?
- Does the error occur when running SQL*Plus, SQL Developer, a Java application, or a database link?
- Can other applications on the same machine connect?

If SQL*Plus on the DBA's machine connects while a Java app on a server fails, never assume both clients use the same Oracle Net configuration.

### 4.4. Step 2 — Locate the Oracle Client and TNS_ADMIN

On Windows PowerShell:

~~~powershell
Get-Command sqlplus -ErrorAction SilentlyContinue
Get-Command tnsping -ErrorAction SilentlyContinue
where.exe sqlplus
where.exe tnsping
$env:ORACLE_HOME
$env:TNS_ADMIN
~~~

On Linux/Unix:

~~~bash
which sqlplus
which tnsping
echo "$ORACLE_HOME"
echo "$TNS_ADMIN"
~~~

Check the paths:

- If TNS_ADMIN is set, Oracle Net uses the specified configuration directory for that client/environment.
- If not set, the client typically searches the Oracle Home network admin directory.
- Instant Client can also use TNS_ADMIN to point to a dedicated configuration directory.

Do not set an environment variable in one terminal and assume a Windows service, application server, or container inherits that value. Each process has its own environment.

### 4.5. Step 3 — Inspect tnsnames.ora

Example:

~~~text
SALES_PROD =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = db-sales.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = sales.example.com)
    )
  )
~~~

Check:

- Does the SALES_PROD alias exist with exact spelling?
- Is there an = sign after the alias?
- Are all parentheses balanced?
- Does ADDRESS include PROTOCOL, HOST, and PORT?
- Does CONNECT_DATA have the correct SERVICE_NAME?
- Are there smart quotes pasted from documentation?
- Are there stray characters or truncated configuration lines?
- Are there duplicate aliases across different TNSNAMES files?

Oracle Net may treat an entire TNSNAMES file as invalid if part of its structure is malformed. Check entries adjacent to the alias being used as well.

### 4.6. Step 4 — Inspect sqlnet.ora

Example:

~~~text
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
~~~

If using TNSNAMES, ensure TNSNAMES is in the directory path. If using Easy Connect, ensure EZCONNECT is configured appropriately for the client.

Also check:

~~~text
NAMES.DEFAULT_DOMAIN = example.com
~~~

When this parameter is configured, simple names may have the domain appended. For example, the connect identifier SALES_PROD may resolve as SALES_PROD.EXAMPLE.COM. Verify whether the alias in the file uses the fully-qualified name.

Do not add NAMES.DEFAULT_DOMAIN just to make one alias work without understanding its impact on other aliases.

### 4.7. Step 5 — Try Easy Connect

Instead of:

~~~text
sqlplus app_user@SALES_PROD
~~~

Try:

~~~text
sqlplus app_user@//db-sales.example.com:1521/sales.example.com
~~~

Enter the password when SQL*Plus prompts.

Results:

- Easy Connect works, alias fails: prioritize checking TNSNAMES, TNS_ADMIN, NAMES.DIRECTORY_PATH, and alias/domain.
- Both fail with ORA-12541: move on to checking the listener/network.
- Both fail with ORA-12514: check service registration/service name.

### 4.8. Step 6 — Check LDAP Naming

If the environment uses LDAP:

- Locate the right ldap.ora.
- Check TNS_ADMIN and LDAP_ADMIN.
- Check directory server host/port.
- Check DNS.
- Check Oracle Context and default context.
- Use an appropriate directory tool to confirm the service entry exists.

Do not create a local TNS alias to bypass LDAP if organizational policy mandates centralized naming.

### 4.9. Step 7 — Database Link Cases

If the error occurs when running:

~~~sql
SELECT *
FROM remote_table@sales_link;
~~~

ORA-12154 may be raised by the Oracle Database server executing the database link, not the DBA's laptop.

Check:

- Does the database server have the proper Oracle Net naming configuration?
- Does the database process's TNS_ADMIN point to the right directory?
- Does the alias used by the database link exist on the database server?
- Is the remote connect descriptor configured in the database link dictionary?
- Is there a difference between client-side and server-side Oracle Homes?

Inspect database link metadata with appropriate privileges, avoiding printing passwords:

~~~sql
SELECT
    owner,
    db_link,
    username,
    host
FROM dba_db_links
WHERE db_link LIKE 'SALES_LINK%';
~~~

Do not export or share secrets if administrative tools expose sensitive data.

### 4.10. ORA-12154 Checklist

- [ ] Identified the exact process/client raising the error.
- [ ] Identified the Oracle Home or JDBC Thin configuration.
- [ ] Checked TNS_ADMIN.
- [ ] Located the correct tnsnames.ora.
- [ ] Verified the alias exists and is accurate.
- [ ] Verified descriptor syntax is valid.
- [ ] Verified NAMES.DIRECTORY_PATH includes the required naming method.
- [ ] Reviewed NAMES.DEFAULT_DOMAIN.
- [ ] Tested Easy Connect to isolate naming issues.
- [ ] If using a database link, checked server-side Oracle Net.

## 5. ORA-12541 — TNS: no listener

### 5.1. Meaning

ORA-12541 means the client cannot reach a listener at the specified address.

Example:

~~~text
ORA-12541: TNS:no listener
~~~

Or:

~~~text
ORA-12541: Cannot connect. No listener at host db-sales.example.com port 1521
~~~

This error indicates a problem with listener address/reachability. It does not mean SERVICE_NAME is wrong; the request never reached the listener for it to evaluate the service.

### 5.2. Common Causes

- The listener has not been started.
- The listener is running on a different port.
- The client points to the wrong host or port.
- DNS resolves the hostname incorrectly.
- A firewall/security group blocks TCP.
- The listener binds only to a different address.
- The listener is running from a different Oracle Home.
- The Windows listener service has not started.
- Network routing/VPN/NAT is misconfigured.
- The client connects via SCAN, proxy, or Connection Manager, and that endpoint is failing.
- The listener process stopped or the host lost connectivity.

### 5.3. Step 1 — Check Hostname and Port in the Descriptor

Example:

~~~text
(ADDRESS =
  (PROTOCOL = TCP)
  (HOST = db-sales.example.com)
  (PORT = 1521)
)
~~~

Compare this with the actual listener configuration on the database server. Never assume the port is always 1521.

### 5.4. Step 2 — Check DNS/Host Resolution

Windows:

~~~powershell
Resolve-DnsName db-sales.example.com
nslookup db-sales.example.com
~~~

Linux:

~~~bash
getent hosts db-sales.example.com
nslookup db-sales.example.com
~~~

Verify that the returned IP matches the expected host/VIP/SCAN IP. If the hostname returns multiple IPs, determine which address the client is trying and whether each address has a listener.

### 5.5. Step 3 — Test the TCP Port

Windows:

~~~powershell
Test-NetConnection db-sales.example.com -Port 1521
~~~

Linux:

~~~bash
nc -vz db-sales.example.com 1521
~~~

TcpTestSucceeded = True only proves a TCP connection to the port can be established. It does not confirm that the Oracle service name, authentication, or database session works.

If TCP fails:

- Check client/server/network firewalls.
- Check security groups or network ACLs.
- Check VPN, routes, and NAT.
- Check whether the listener is listening on that port.

### 5.6. Step 4 — Check the Listener on the Database Server

Log in to the database host with an appropriate administrative account:

~~~text
lsnrctl status
~~~

If the listener is named:

~~~text
lsnrctl status LISTENER_SALES
~~~

The output typically reports:

- Listener alias.
- Listener version.
- Start time.
- Listening Endpoints Summary.
- Protocol/host/port.
- Services Summary.
- Listener log file path.

Compare the listening endpoint with the host/port in the connect descriptor.

### 5.7. Step 5 — Start the Listener When Truly Stopped

If confirmed that the listener should be running and starting it is authorized:

~~~text
lsnrctl start
~~~

Or:

~~~text
lsnrctl start LISTENER_SALES
~~~

Then verify:

~~~text
lsnrctl status LISTENER_SALES
lsnrctl services LISTENER_SALES
~~~

Do not start a new listener under the default name if the system uses a listener managed by Grid Infrastructure. In RAC, use SRVCTL/Clusterware as configured instead of managing listeners manually.

### 5.8. Step 6 — Check the Windows Service

On a Windows database server:

~~~powershell
Get-Service *Oracle*Listener*
~~~

Or open Services and inspect the service matching the Oracle Home/listener. Service names vary by version and Oracle Home.

If the listener service is stopped, start only the right service per server administration procedures.

### 5.9. Step 7 — Check Which Address the Listener Is Bound To

A listener may be listening on:

- A hostname.
- A specific IP.
- A VIP.
- A non-1521 port.
- TCPS instead of TCP.

Use `lsnrctl status` output to check the actual endpoint. If needed, check OS sockets:

Linux:

~~~bash
ss -ltnp
~~~

Windows:

~~~powershell
Get-NetTCPConnection -State Listen |
    Where-Object { $_.LocalPort -eq 1521 }
~~~

Do not arbitrarily change HOST in listener.ora to 0.0.0.0 or another IP without evaluating security and topology.

### 5.10. Step 8 — Check the Firewall

If the listener is listening on the right port but clients cannot reach it:

- Check the inbound firewall on the database host.
- Check outbound policy on the client network.
- Check intermediate firewalls.
- Check cloud security lists/security groups.
- Check VPN or subnet routing.
- Verify the exact destination IP if DNS returns multiple records.

Open ports only for the correct endpoint with proper approval. Never disable the host firewall entirely to test.

### 5.11. Step 9 — Check RAC/SCAN

In RAC, clients typically connect to a SCAN listener and are then redirected to the local listener of an appropriate instance.

Check:

~~~text
srvctl status scan
srvctl status scan_listener
srvctl status listener
~~~

Depending on configuration and privileges, you can also check:

~~~text
srvctl config scan
srvctl config scan_listener
~~~

If the client receives ORA-12541 after redirect, the final address in the error may be the VIP/local listener rather than the initial SCAN listener. Check the endpoint reported in the error message and listener logs.

### 5.12. ORA-12541 Checklist

- [ ] Host and port in the descriptor are correct.
- [ ] DNS resolves to the right IP.
- [ ] TCP port is reachable from the exact client.
- [ ] Listener is running.
- [ ] Listener is listening on the correct endpoint.
- [ ] Windows service/Clusterware listener is active.
- [ ] Firewall/routing permits the connection.
- [ ] SCAN/VIP/redirect endpoints work if using RAC.
- [ ] Listener status and logs have been reviewed.

## 6. ORA-12514 — Listener does not currently know of service requested

### 6.1. Meaning

ORA-12514 occurs when the listener receives a connection request but does not recognize the service name specified in the connect descriptor.

Example:

~~~text
ORA-12514: TNS:listener does not currently know of service requested in connect descriptor
~~~

This indicates the listener received the request. Therefore, testing the TCP port is usually not the primary fix. Determine whether the service name is correct and registered with the listener.

### 6.2. Common Causes

- SERVICE_NAME in tnsnames.ora is wrong.
- JDBC URL specifies the wrong service.
- The PDB is closed.
- The database instance is not open or is still starting up.
- The listener was just started and LREG has not registered the service yet.
- LOCAL_LISTENER points to the wrong listener.
- REMOTE_LISTENER is misconfigured in RAC.
- The service has not been created or started.
- The service was stopped after maintenance/failover.
- The client is connecting to a different listener/port than the one holding the service.
- Service registration is blocked by listener configuration.

### 6.3. Step 1 — View Services Known to the Listener

On the database server:

~~~text
lsnrctl services
~~~

Or:

~~~text
lsnrctl services LISTENER_SALES
~~~

Example output:

~~~text
Services Summary...
Service "sales.example.com" has 1 instance(s).
  Instance "sales", status READY, has 1 handler(s) for this service...
    Handler(s):
      "DEDICATED" established: 10 refused: 0 state: ready
~~~

Check:

- Does the service name appear?
- Which instance is registering the service?
- Is the instance status READY?
- Is the handler state READY?
- Is the right service registered only on a different listener?

### 6.4. Step 2 — Compare SERVICE_NAME on the Client

In TNSNAMES:

~~~text
SALES_PROD =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = db-sales.example.com)(PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = sales.example.com)
    )
  )
~~~

Compare `sales.example.com` exactly against the `lsnrctl services` output.

Do not use DB_NAME or INSTANCE_NAME in place of SERVICE_NAME unless the descriptor and listener are explicitly designed for that connection type.

### 6.5. Step 3 — Check Services from the Database

Connect locally to the database using an appropriate administrative method:

~~~sql
SELECT
    name,
    network_name,
    pdb,
    con_id
FROM v$services
ORDER BY name;
~~~

V$SERVICES shows the services recognized by the database instance. Compare them with the services the listener reports as registered.

### 6.6. Step 4 — Check Instance and PDB

~~~sql
SELECT
    instance_name,
    status,
    database_status
FROM v$instance;

SELECT
    name,
    open_mode
FROM v$pdbs
ORDER BY name;
~~~

If the service belongs to a PDB that is MOUNTED/CLOSED, applications cannot connect to that service.

Open the PDB per procedure:

~~~sql
ALTER PLUGGABLE DATABASE salespdb OPEN;
~~~

Ensure the open state persists across restarts if required:

~~~sql
ALTER PLUGGABLE DATABASE salespdb SAVE STATE;
~~~

Run the PDB open command only after confirming the right PDB, the right CDB, and proper authorization/approval.

### 6.7. Step 5 — Check Dynamic Service Registration

Oracle Database uses the LREG background process to register service and instance information with the listener.

After a listener starts, registration may not occur immediately. LREG runs discovery periodically; you can force immediate registration:

~~~sql
ALTER SYSTEM REGISTER;
~~~

Then re-check:

~~~text
lsnrctl services LISTENER_SALES
~~~

ALTER SYSTEM REGISTER is only helpful when the instance/service is ready and the listener is reachable. It will not fix a wrong service name, wrong listener port, or broken network.

### 6.8. Step 6 — Check LOCAL_LISTENER

~~~sql
SHOW PARAMETER local_listener;
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name IN ('local_listener', 'remote_listener');
~~~

LOCAL_LISTENER identifies the local listener where LREG should register. If the listener runs on a non-1521 port while LOCAL_LISTENER still uses the default or an unresolvable alias, the service may not register with the listener clients are calling.

Example of a custom listener running on port 1522:

~~~sql
ALTER SYSTEM SET LOCAL_LISTENER =
  '(ADDRESS=(PROTOCOL=TCP)(HOST=db-sales.example.com)(PORT=1522))'
  SCOPE=BOTH;

ALTER SYSTEM REGISTER;
~~~

This example is illustrative only. In production, verify the SPFILE/PFILE, RAC setup, listener aliases, and current configuration before changing parameters.

### 6.9. Step 7 — Check REMOTE_LISTENER in RAC

In RAC, service registration typically involves SCAN listeners via REMOTE_LISTENER.

~~~sql
SHOW PARAMETER remote_listener;
~~~

Check:

- SCAN hostname resolves properly.
- SCAN listeners are running.
- REMOTE_LISTENER points to the right SCAN address.
- Local listeners/VIPs are operational.
- The service is configured for the right database/instances.

Do not set REMOTE_LISTENER to a local listener address just as a workaround. Use the SCAN configuration managed by Grid Infrastructure.

### 6.10. Step 8 — Managing Services in Oracle 19c

Starting in Oracle Database 19c, customer management of the SERVICE_NAMES parameter is deprecated. Oracle recommends using SRVCTL, GDSCTL, or DBMS_SERVICE to manage services.

In a RAC/Clusterware environment, inspect services:

~~~text
srvctl config service -db SALESDB
srvctl status service -db SALESDB
~~~

If the service is managed by Clusterware, use SRVCTL to start/stop it according to configuration and HA policy:

~~~text
srvctl start service -db SALESDB -service sales_app
~~~

Do not manually add SERVICE_NAMES to the SPFILE as a default fix for ORA-12514 on 19c. First determine whether the service is managed by SRVCTL, DBMS_SERVICE, GDS, or a cloud control plane.

### 6.11. Step 9 — Verify the Service on the Right Listener

A database service might appear on one listener while the client connects to another:

- The client uses port 1521 while the listener service only registers on port 1522.
- The local listener differs from the SCAN listener.
- Multiple Oracle Homes/listeners exist on the same host.
- Service registration goes to a listener that does not match the endpoint the client is calling.

Compare `lsnrctl status` and `lsnrctl services` for the exact listener name, host, and port.

### 6.12. ORA-12514 Checklist

- [ ] SERVICE_NAME in the connect descriptor is correct.
- [ ] The listener on the right host/port received the request.
- [ ] `lsnrctl services` lists the requested service.
- [ ] The service handler state is READY.
- [ ] The instance is running and appropriate.
- [ ] The PDB is OPEN if the service belongs to a PDB.
- [ ] LREG has registered the service.
- [ ] LOCAL_LISTENER is accurate.
- [ ] REMOTE_LISTENER/SCAN is accurate if RAC.
- [ ] The service is properly managed via SRVCTL/DBMS_SERVICE/GDS.
- [ ] The listener log has no related registration errors.

## 7. Quick Comparison of the Three Errors

| Criterion | ORA-12154 | ORA-12541 | ORA-12514 |
| --- | --- | --- | --- |
| Phase | Naming resolution | Listener address/connectivity | Service selection |
| Valid descriptor obtained? | Failed to resolve | Has an address to attempt | Yes |
| Reached listener? | Not necessarily; usually no | No | Yes |
| Check host/port? | After resolving the name | Yes, primary focus | Yes, though listener already received request |
| Check service name? | Not first step since descriptor unresolved | Not yet at service selection | Yes, primary focus |
| Commonly involved files/config | tnsnames.ora, sqlnet.ora, TNS_ADMIN, LDAP | listener.ora, OS/network/firewall | LOCAL_LISTENER, REMOTE_LISTENER, service/PDB, listener registration |
| Key commands | Check files, Easy Connect, naming path | lsnrctl status, TCP test | lsnrctl services, V$SERVICES, ALTER SYSTEM REGISTER |

## 8. TNSPING: Using It Properly

tnsping is a diagnostic utility for testing an Oracle Net connect identifier and connectivity information.

Example:

~~~text
tnsping SALES_PROD
~~~

Output typically shows:

- Alias used.
- Resolved connect descriptor.
- Attempt latency.
- TNS-125xx error if it fails.

### 8.1. TNSPING Is Not a Database Login

TNSPING does not authenticate a username/password and does not prove:

- That the database service can create a session.
- That the database instance is open.
- That the PDB is open.
- That a handler is ready to accept connections.
- That user/password credentials are valid.
- That the application has privileges on objects.
- That a SQL statement can execute successfully.

Oracle Database 19c Troubleshooting Oracle Net Services documentation recommends testing an actual connection with SQL*Plus rather than using TNSPING as proof that the Oracle Net foundation layer is fully functional.

### 8.2. End-to-End Check with SQL*Plus

~~~text
sqlplus -L app_user@SALES_PROD
~~~

Enter the password at the prompt. If login succeeds:

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME') AS db_name,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

This query confirms which database, service, and container the session is connected to.

### 8.3. TCP Tests Do Not Replace SQL*Plus

Test-NetConnection or nc -vz only verifies that the TCP port is reachable. A successful TCP connection does not prove Oracle listener, service, or authentication functionality.

Use all three checks according to their purpose:

| Tool | What Is Tested |
| --- | --- |
| DNS lookup | Which address the hostname resolves to |
| TCP port test | Whether TCP can connect to the host/port |
| SQL*Plus login | Whether an Oracle database session can actually be established |

## 9. Checking Client Configuration by Environment

### 9.1. SQL*Plus on Windows

~~~powershell
where.exe sqlplus
where.exe tnsping
$env:ORACLE_HOME
$env:TNS_ADMIN

Get-ChildItem Env: |
    Where-Object { $_.Name -match 'ORACLE|TNS' }
~~~

If multiple Oracle Homes are installed, identify the exact executable invoked. Each Oracle Home can have its own network/admin directory.

### 9.2. SQL*Plus on Linux

~~~bash
which sqlplus
which tnsping
echo "$ORACLE_HOME"
echo "$TNS_ADMIN"
env | grep -E 'ORACLE|TNS'
~~~

Check file read permissions:

~~~bash
ls -l "$TNS_ADMIN/tnsnames.ora"
ls -l "$TNS_ADMIN/sqlnet.ora"
~~~

### 9.3. Oracle Instant Client

Instant Client can use TNS_ADMIN to locate Oracle Net configuration. Do not assume configuration inside an Oracle Database Home is automatically used by Instant Client.

### 9.4. SQL Developer

SQL Developer can use:

- Basic connection: hostname, port, and service name/SID entered directly.
- TNS connection: alias read from the TNS admin directory configured in Preferences.

If SQL*Plus works while SQL Developer fails with ORA-12154, check the TNS admin directory in SQL Developer and the tool's JDK/runtime configuration.

### 9.5. JDBC Thin Driver

JDBC Thin Driver can connect using Easy Connect:

~~~java
String url =
    "jdbc:oracle:thin:@//db-sales.example.com:1521/sales.example.com";
~~~

Or using a TNS alias when the driver is configured to locate Oracle Net config:

~~~java
String url = "jdbc:oracle:thin:@SALES_PROD";
~~~

With a TNS alias, configure oracle.net.tns_admin or the TNS admin mechanism appropriate for the Oracle JDBC driver/version.

Example JVM property:

~~~text
-Doracle.net.tns_admin=/opt/app/oracle/network/admin
~~~

On Windows, use the corresponding directory path.

### 9.6. Spring Boot Application

Example JDBC URL configuration:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-sales.example.com:1521/sales.example.com
    username: app_user
    password: INJECT_FROM_SECRET_STORE
    driver-class-name: oracle.jdbc.OracleDriver
~~~

If using an alias:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@SALES_PROD
~~~

Ensure the JVM/app process sees the right TNS_ADMIN. Never place real passwords in source control or logs.

### 9.7. Container/Kubernetes

If the app runs inside a container:

- TNSNAMES files on the host do not automatically appear in the container.
- TNS_ADMIN must point to a path inside the container.
- ConfigMap/secret volumes must be mounted properly.
- Container DNS and network policies may differ from the host.
- Egress policies must permit the Oracle port.
- Roll out restarts when environment/config needs to be reloaded per procedure.

Do not inspect tnsnames.ora on a laptop and conclude a pod has the same configuration.

## 10. Listener and Service Registration

### 10.1. Listener Configuration

Listener configuration typically resides in listener.ora, containing:

- Listener name.
- Protocol addresses.
- Host/IP.
- Port.
- Runtime parameters.

The default listener is usually named LISTENER on TCP port 1521, though environments may use different names/ports.

### 10.2. Dynamic Service Registration

The database registers services with the listener through LREG. Dynamic registration does not require declaring every service in listener.ora.

LREG sends service, instance, and workload information to the listener. The listener uses this data to select a service handler for connection requests.

### 10.3. Listener Started Before Database

If the listener starts before the instance, LREG may not register services immediately. Once the instance is ready, registration happens on the discovery cycle. You can force registration:

~~~sql
ALTER SYSTEM REGISTER;
~~~

### 10.4. LOCAL_LISTENER

LOCAL_LISTENER specifies the local listener where LREG registers services. The value can be an alias or an address.

~~~sql
SHOW PARAMETER local_listener;
~~~

Example with a direct address:

~~~sql
ALTER SYSTEM SET LOCAL_LISTENER =
  '(ADDRESS=(PROTOCOL=TCP)(HOST=db-sales.example.com)(PORT=1522))'
  SCOPE=BOTH;
~~~

After making changes, verify the parameter and listener registration. In RAC, Clusterware and network configuration must be reviewed together.

### 10.5. REMOTE_LISTENER

REMOTE_LISTENER is commonly used to register services with remote/SCAN listeners in RAC.

~~~sql
SHOW PARAMETER remote_listener;
~~~

If REMOTE_LISTENER points to the wrong target, the service may not appear on the SCAN listener that clients are calling.

### 10.6. SERVICE_NAMES in 19c

In Oracle Database 19c, customer use of the SERVICE_NAMES parameter is deprecated. Oracle recommends managing services with SRVCTL, GDSCTL, or DBMS_SERVICE.

Therefore, do not run commands like:

~~~sql
ALTER SYSTEM SET SERVICE_NAMES = 'sales.example.com';
~~~

as a default fix for every ORA-12514 on 19c. First determine which tool created and manages the service.

### 10.7. Checking Listener Services

~~~text
lsnrctl services LISTENER
~~~

Inspect:

- Service name.
- Instance name.
- Instance status.
- Handler type.
- Established/refused/current/max.
- Handler state.

State READY means the handler can accept connections. BLOCKED means the handler is not accepting new connections. UNKNOWN is commonly associated with static registration.

## 11. PDB Services and ORA-12514

In Multitenant architectures, services are typically how clients connect to a PDB.

### 11.1. View PDBs

~~~sql
SHOW PDBS;
~~~

Or:

~~~sql
SELECT name, open_mode
FROM v$pdbs;
~~~

### 11.2. View Services

~~~sql
SELECT
    name,
    network_name,
    pdb,
    con_id
FROM v$services
ORDER BY name;
~~~

### 11.3. PDB Service Not Ready

If the PDB is closed or the service is not started, the listener will not know the service requested by the client.

Check:

1. Is the CDB instance running?
2. Is the PDB OPEN?
3. Does the service exist?
4. Is the service started?
5. Is the service registered with the listener?
6. Is the client using the right service name?

### 11.4. Do Not Use SID to Connect to a PDB

For applications connecting to a PDB, use the PDB's service name. A SID generally identifies only the instance, not a logical route to a PDB.

### 11.5. Saving PDB State

If policy requires a PDB to reopen automatically after a database restart:

~~~sql
ALTER PLUGGABLE DATABASE salespdb SAVE STATE;
~~~

Re-check after restart and verify service registration.

## 12. Oracle RAC, SCAN, and Local Listener

RAC introduces additional endpoints into the connection flow.

### 12.1. RAC Connection Flow

~~~text
Client
  |
  v
SCAN name / SCAN IP
  |
  v
SCAN Listener
  |
  v
Redirect to Node VIP / Local Listener
  |
  v
Database Instance / Service Handler
~~~

### 12.2. SCAN Listener vs. Local Listener

- SCAN listener receives connections via the SCAN address and distributes them to an appropriate node.
- Local listener on each node manages service handlers for instances on that node.
- A service may run on one or more instances according to preferred/available configuration.

### 12.3. Checking SCAN and Listeners

~~~text
srvctl status scan
srvctl status scan_listener
srvctl status listener
srvctl status service -db SALESDB
~~~

Inspect configuration:

~~~text
srvctl config scan
srvctl config scan_listener
srvctl config service -db SALESDB
~~~

### 12.4. ORA-12541 After Redirect

A client may reach the SCAN listener successfully but fail to connect to the local listener/VIP after redirect. The error may include the final endpoint. Read CONNECTION_ID, listener logs, and the final hostname/IP rather than testing only the SCAN hostname.

### 12.5. ORA-12514 in RAC

The service may not be running on the instance handled by the listener, or the client may be requesting the wrong service. Check service configuration, preferred/available instances, service status, and `srvctl status service` output.

### 12.6. Do Not Arbitrarily Restart Listeners

In RAC, listeners are managed by Grid Infrastructure. Use SRVCTL and Clusterware procedures. Manually restarting listeners can lose state or disrupt connections for other workloads.

## 13. JDBC and Connection Pools

An Oracle Net error can appear in a Java application even when a DBA can connect from a terminal.

### 13.1. Thin vs. OCI

JDBC Thin Driver uses a pure Java implementation of Oracle Net and does not require Oracle Client native libraries the way OCI does.

JDBC OCI depends on the Oracle Client/OCI installation and Oracle Net configuration on the host.

When comparing results, use the same driver type and runtime configuration.

### 13.2. JDBC Easy Connect URL

~~~java
String url =
    "jdbc:oracle:thin:@//db-sales.example.com:1521/sales.example.com";

try (Connection connection =
         DriverManager.getConnection(url, username, password)) {
    // session created if no exception
}
~~~

### 13.3. JDBC TNS Alias URL

~~~java
String url = "jdbc:oracle:thin:@SALES_PROD";
~~~

The alias must resolve within the JVM runtime. If TNS_ADMIN is set only in the DBA's shell and not passed to the service/application process, the Java app will encounter ORA-12154.

### 13.4. Connection Pools Holding Stale Connections

If a listener/service was just fixed, the pool may still hold stale connections or retry on its own timeouts. Check:

- Pool initialization failure.
- Connection validation query.
- Maximum lifetime.
- Connection timeout.
- Retry/backoff.
- DNS cache.
- Pod/application restart and environment variables.

Do not restart the entire application just to mask a configuration error. First confirm whether the error reproduces with a fresh connection from the same runtime.

### 13.5. Spring Boot Datasource

Check effective configuration:

- Final JDBC URL.
- Driver class/version.
- TNS_ADMIN or JVM properties.
- Secret/environment injection.
- Host/port/service in the active config profile.
- Whether HikariCP or another pool is using the right DataSource.

Do not log passwords or full connection properties if they contain secrets.

### 13.6. Verify Session After Connecting

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME') AS db_name,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'INSTANCE_NAME') AS instance_name,
    sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

This confirms the app not only connected, but landed in the right database, service, and PDB.

## 14. Listener Logs, SQL*Net Logs, and ADR

When errors persist after basic checks, logs help determine which layer the request reached.

### 14.1. Listener Log

The listener log records connection requests, service registration events, direct hand-offs, and related events.

Run:

~~~text
lsnrctl status LISTENER
~~~

The output contains a Listener Log File line showing the actual path.

In ADR, the listener home typically follows:

~~~text
<ADR_BASE>/diag/tnslsnr/<host>/<listener_name>/
~~~

Common subdirectories:

- alert: XML alert log.
- trace: listener trace and text log.
- incident: incident dumps if any.

Do not hard-code a single path for all hosts. Get the ADR home from `lsnrctl status` output or ADRCI.

### 14.2. SQL*Net Client/Server Logs

Oracle Net can write sqlnet.log and trace files in client/server ADR homes.

For ORA-12154, client-side diagnostics are usually critical because naming resolution happens on the client.

For ORA-12541/12514, the listener log typically reveals whether the listener received the request or whether service registration occurred.

### 14.3. ADRCI

Start ADRCI:

~~~text
adrci
~~~

List homes:

~~~text
ADRCI> SHOW HOMES
~~~

Select the right listener home:

~~~text
ADRCI> SET HOME diag/tnslsnr/db-sales/listener
~~~

View the alert log:

~~~text
ADRCI> SHOW ALERT -TAIL 100
~~~

The SET HOME path must match an actual home listed by SHOW HOMES.

### 14.4. Reading the Error Stack

Oracle Net logs may contain multiple error layers:

- NI: Network Interface.
- NS: Network Session.
- NA: Network Authentication.
- NT: Network Transport/OS.

The final message displayed by the application may only be the outer layer. In the log, start from the bottom of the error stack and locate the first meaningful non-zero error to identify the root cause.

### 14.5. Listener Log and CONNECTION_ID

Newer Oracle error outputs can provide a CONNECTION_ID. Use this value to correlate requests across listener, client, and server traces. Record:

- Exact timestamp and timezone.
- Client host/source.
- Destination host/port.
- Service name.
- CONNECTION_ID.
- Full error code.

Do not copy just a single ORA-12514 line while omitting the descriptor and timestamp.

## 15. Enabling Controlled Oracle Net Tracing

Tracing logs detailed internal communication steps and can generate large amounts of data.

### 15.1. When Is Tracing Needed?

- The error happens only on certain clients.
- The error is intermittent or occurs only after redirect.
- DNS/network behavior is hard to reproduce.
- The listener receives the request, but it is unclear why no handler was chosen.
- You need to inspect naming resolution or network protocol negotiation.

### 15.2. Client Tracing

Example temporary configuration in sqlnet.ora:

~~~text
TRACE_LEVEL_CLIENT = ADMIN
TRACE_UNIQUE_CLIENT = ON
~~~

Trace file names and locations depend on ADR configuration and Oracle Net version. Once enabled, reproduce the failure once, save the trace, and disable tracing.

### 15.3. Listener Tracing

Listener tracing is configured in listener.ora per listener name. Example:

~~~text
TRACE_LEVEL_LISTENER = ADMIN
TRACE_TIMESTAMP_LISTENER = ON
~~~

Exact parameter names depend on the listener alias and release. Consult the Oracle Net Services Reference before modifying.

### 15.4. Trace Levels

Common levels:

- OFF: disabled.
- USER: basic user-level information.
- ADMIN: more detailed administrative info.
- SUPPORT: highly detailed, intended for Oracle Support.

Do not leave SUPPORT tracing enabled for long periods in production. Tracing can increase disk usage and impact performance.

### 15.5. Disable Tracing After Collection

Restore the original configuration, verify trace files stop growing continuously, and ensure logs/traces are stored appropriately per retention policy.

### 15.6. Redacting Sensitive Data

Traces can contain:

- Hostnames/IPs.
- Usernames.
- Connect descriptors.
- Service names.
- Authentication/network metadata.
- SQL text or application data depending on trace type.

Before sending externally, review and redact sensitive information.

## 16. Layered Diagnostic Procedure

A good runbook never starts with restarting the database. Follow verifiable steps.

### Step 1 — Capture Exact Error Details

Collect:

- Full error code, including TNS-xxxxx if present.
- Timestamp and timezone.
- Client host/application.
- Redacted connect identifier or JDBC URL.
- Protocol, host, port, and service.
- Is only one client failing or all clients?
- When did the error start?
- Were there any recent DNS, firewall, listener, service, PDB, or deployment changes?

### Step 2 — Identify Client Configuration

- Locate Oracle Home/driver.
- Identify TNS_ADMIN.
- Identify naming method.
- Inspect TNSNAMES or LDAP.
- For JDBC, check URL and JVM properties.

### Step 3 — Resolve Name

If using an alias:

- Check TNSNAMES.
- Check NAMES.DIRECTORY_PATH.
- Check NAMES.DEFAULT_DOMAIN.

Try Easy Connect to isolate naming errors.

### Step 4 — Check Host/Port

- Resolve DNS.
- Verify IP.
- Test TCP port.
- Identify firewall/network path.

### Step 5 — Check Listener

~~~text
lsnrctl status LISTENER
~~~

Compare the actual endpoint with the descriptor.

### Step 6 — Check Service Registration

~~~text
lsnrctl services LISTENER
~~~

If the service is missing, check:

- V$SERVICES.
- V$INSTANCE.
- V$PDBS.
- LOCAL_LISTENER.
- REMOTE_LISTENER.
- Service status via SRVCTL/DBMS_SERVICE.

### Step 7 — Attempt Actual Login

~~~text
sqlplus -L app_user@SALES_PROD
~~~

If login succeeds, run a query confirming DB/service/PDB.

### Step 8 — Check Application Runtime

- From the exact application server/container.
- Using the exact JDBC driver.
- Using the exact effective URL.
- Using the exact TNS_ADMIN.
- Check connection pool and DNS cache.

### Step 9 — Inspect Logs/Traces

Correlate client, listener, and database timestamps/connection IDs.

### Step 10 — Change Only the Right Layer

Change one evidence-backed variable at a time, record before/after values, and re-test from the same client.

## 17. Error Matrix and Troubleshooting Direction

| Symptom | Priority Layer | First Check |
| --- | --- | --- |
| ORA-12154 | Naming | TNS_ADMIN, TNSNAMES, NAMES.DIRECTORY_PATH |
| ORA-12541 | Listener/network | Host, port, TCP test, lsnrctl status |
| ORA-12514 | Service registration | SERVICE_NAME, lsnrctl services, V$SERVICES |
| ORA-12505 | Instance/SID | SID in descriptor and listener |
| ORA-12521 | Instance registration | INSTANCE_NAME and service registration |
| ORA-12520 | Handler availability/type | Handler status, server=, instance state |
| ORA-12516 | Handler capacity/protocol | Service handler, dispatcher/dedicated capacity |
| ORA-12170 | Timeout | Network delay, timeout parameters, listener/client trace |
| ORA-12525 | Listener inbound timeout | Client completion time, listener log, network |
| ORA-12500 | Server process startup | PROCESSES, OS limits, permissions, listener log |
| ORA-12560 | Protocol adapter | OS/client protocol configuration |
| ORA-03113 | Session/communication loss | Database alert log, server process, network |

Do not treat the errors in this table with a single generic fix. Identify the error stack and originating layer first.

## 18. Related Oracle Net Errors

### 18.1. ORA-12505 — Listener Does Not Know of SID

ORA-12505 differs from ORA-12514:

- ORA-12505: descriptor specifies a SID that the listener does not recognize.
- ORA-12514: descriptor specifies a service name that the listener does not recognize.

If the application should connect by service, use the right SERVICE_NAME rather than changing SIDs randomly.

### 18.2. ORA-12521 — Listener Does Not Know of Instance

The requested instance name is incorrect or has not registered with the listener. Check INSTANCE_NAME, the database instance, and listener services.

### 18.3. ORA-12520 — Unable to Find Suitable Handler

The listener may know the service but lack a suitable handler for the requested server type, or the instance has not registered properly. Check `lsnrctl services`, handler state, server mode, and instance status.

### 18.4. ORA-12516 — No Available Handler

The listener cannot find a service handler with a matching protocol stack. Check handler capacity, dispatcher/shared server configuration, process/session limits, and the listener log.

### 18.5. ORA-12170 — Connect Timeout

Timeouts can be caused by:

- Slow DNS/network.
- Firewall silently dropping packets.
- Overloaded server.
- Client failing to complete connect/authentication within configured time.
- Packet loss or retransmissions on the network path.

Do not immediately increase timeouts before knowing where it is waiting. Tracing helps identify which phase the client/server is waiting on.

### 18.6. ORA-03113 — End-of-File on Communication Channel

This error usually appears after a session has been established or during communication, and can relate to the database process, instance failure, network, or server-side errors. Check the database alert log and traces instead of checking only TNSNAMES.

## 19. Real-World Scenarios

### 19.1. SQL Developer Connects but Java App Fails with ORA-12154

Possibilities:

- SQL Developer uses its own TNS admin directory.
- The JVM lacks TNS_ADMIN.
- The app uses a JDBC Thin alias, but Oracle Net config is not mounted.
- The app is running under a different profile.

Troubleshooting steps:

1. Retrieve the actual JDBC URL.
2. Check JVM system properties.
3. Check TNS_ADMIN in the process.
4. Try Easy Connect.
5. Verify driver version and runtime.

### 19.2. SQL*Plus Works on Laptop but Server App Fails with ORA-12541

Possibilities:

- The server does not resolve the same IP.
- Firewall between the application subnet and DB subnet.
- The app uses a different port.
- DNS cache or proxy/redirect endpoint differs.

Run a TCP test from the exact application host/container.

### 19.3. Listener Is Running but Returns ORA-12514

Possibilities:

- Wrong service name.
- Service is not started.
- PDB is closed.
- LREG has not registered yet.
- Client is calling a listener that does not hold the service.

Use `lsnrctl services`, V$SERVICES, V$PDBS, and inspect LREG registration.

### 19.4. After Reboot, ORA-12514 Appears for a Few Minutes Then Clears

The listener may have started before the database, or LREG had not yet registered the service. Observe listener services over time and database startup logs. If confirmed to be a registration delay, you can run `ALTER SYSTEM REGISTER` once the instance/service is ready, or adjust startup dependencies per system administration standards.

### 19.5. Newly Created PDB Cannot Be Reached by App

Check:

1. PDB exists.
2. PDB is OPEN.
3. Service is created and started.
4. Service appears in V$SERVICES.
5. Listener received the service.
6. JDBC URL uses the exact service name.

### 19.6. Only One RAC Node Fails with ORA-12541

Check VIP, local listener, SCAN redirect, and firewalls between nodes. Clients may be redirected to an inactive node even when the SCAN listener is healthy.

### 19.7. Database Link Fails with ORA-12154

Check the alias/connect descriptor from the Oracle database server executing the database link. The TNSNAMES file on the machine running SQL*Plus does not govern naming configuration for the database server process.

## 20. Sample DBA Runbook

### 20.1. Gather Information

~~~text
ERROR_CODE:
TIMESTAMP:
CLIENT_HOST:
APPLICATION:
ORACLE_CLIENT_OR_DRIVER:
CONNECT_IDENTIFIER:
HOST:
PORT:
SERVICE_NAME:
DATABASE_NAME:
PDB:
RAC_OR_SINGLE_INSTANCE:
RECENT_CHANGE:
~~~

### 20.2. Check Client

~~~text
where.exe sqlplus
where.exe tnsping
echo %TNS_ADMIN%
~~~

If using PowerShell:

~~~powershell
Get-Command sqlplus -ErrorAction SilentlyContinue
$env:TNS_ADMIN
~~~

### 20.3. Check Naming

- Verify alias.
- Read TNSNAMES.
- Read SQLNET.
- Check naming order.
- Try Easy Connect.

### 20.4. Check Network

~~~powershell
Resolve-DnsName db-sales.example.com
Test-NetConnection db-sales.example.com -Port 1521
~~~

### 20.5. Check Listener

~~~text
lsnrctl status LISTENER
lsnrctl services LISTENER
~~~

### 20.6. Check Database/Service

~~~sql
SELECT
    instance_name,
    status,
    database_status
FROM v$instance;

SELECT
    name,
    network_name,
    pdb
FROM v$services
ORDER BY name;

SELECT
    name,
    open_mode
FROM v$pdbs
ORDER BY name;

SHOW PARAMETER local_listener;
SHOW PARAMETER remote_listener;
~~~

### 20.7. Re-Register Service if Appropriate

~~~sql
ALTER SYSTEM REGISTER;
~~~

Then:

~~~text
lsnrctl services LISTENER
~~~

### 20.8. Verify End-to-End

~~~text
sqlplus -L app_user@SALES_PROD
~~~

After login:

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME') AS db_name,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'INSTANCE_NAME') AS instance_name,
    sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

### 20.9. Post-Fix Documentation

Record:

- Root cause.
- Changed configuration.
- Before/after values.
- Commands executed.
- Listener/service state.
- Clients tested.
- Recovery time.
- Whether post-change monitoring is needed.

## 21. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| ORA-12154 means the listener is down | It is a connect identifier resolution error |
| ORA-12541 means the service name is wrong | It is an error reaching the listener address |
| ORA-12514 means the port is blocked by a firewall | The listener received the request but does not know the service |
| Running listener means database service is ready | The listener may not have the service registered yet |
| PING succeeding means Oracle can connect | Ping only tests IP reachability at the ICMP level |
| Open TCP port means database login works | TCP tests do not verify Oracle services or authentication |
| TNSPING succeeding means database sessions work | Actual SQL*Plus/JDBC login is required |
| TNSNAMES on laptop is the same as the Java app's TNSNAMES | Each runtime may use a different Oracle Home/TNS_ADMIN |
| Restarting the database always fixes ORA-12514 | Service registration and PDB/service states must be checked |
| SERVICE_NAME always equals DB_NAME | Not necessarily; a service is a logical connect endpoint |
| SID and SERVICE_NAME can be swapped freely | They have different semantics |
| Just add SERVICE_NAMES to SPFILE for 19c | Customer management of SERVICE_NAMES is deprecated; use SRVCTL/GDSCTL/DBMS_SERVICE |
| ALTER SYSTEM REGISTER fixes all ORA-12514 errors | It only asks LREG to re-register; it does not fix wrong services or listeners |
| ORA-12154 in a database link must be fixed on the laptop | Naming resolution can occur on the database server |
| No request in listener log means the listener is broken | The client may not have reached the listener or may be calling another endpoint |
| Increasing timeouts fixes all connection errors | Timeouts do not fix naming, listeners, or service registration |
| Opening the firewall network-wide is a quick test | Only test and open exact source/destination/port per policy |

## 22. Pre-Change Configuration Checklist

**Naming**

- Is the exact client process identified?
- Is TNS_ADMIN correct?
- Are multiple Oracle Homes present?
- Does TNSNAMES contain the right alias?
- Is NAMES.DIRECTORY_PATH right?
- Does Easy Connect work?

**Network**

- Does the hostname resolve to the right IP?
- Is the listener port open from the right subnet?
- Is there NAT, firewall, VPN, or SCAN redirect involved?
- Is the final endpoint in the error identified?

**Listener**

- Is the listener running?
- Is the listener listening on the right port?
- Is the listener name right?
- Is the listener receiving requests?
- Does the listener log have corresponding entries?

**Service**

- Is SERVICE_NAME exact?
- Does `lsnrctl services` show that service?
- Is the handler READY?
- Are the instance and PDB ready?
- Are LOCAL_LISTENER/REMOTE_LISTENER correct?
- Is the service managed via SRVCTL/DBMS_SERVICE/GDS?

**Application**

- Is the JDBC URL right?
- Does the driver/runtime use the right TNS_ADMIN?
- Does the connection pool hold stale connections?
- Is the app running in a different container/network namespace?
- Has it been tested from the exact app host with SQL*Plus or an equivalent client?

## 23. Self-Check Questions

1. What role does Oracle Net fulfill?
2. How does a connect identifier differ from a connect descriptor?
3. What is a net service name?
4. How do SID and SERVICE_NAME differ?
5. At which layer does ORA-12154 occur?
6. What does ORA-12541 indicate?
7. What does ORA-12514 indicate?
8. Why does restarting the listener usually not fix ORA-12154?
9. What is TNS_ADMIN used for?
10. What does NAMES.DIRECTORY_PATH control?
11. How does NAMES.DEFAULT_DOMAIN affect aliases?
12. How is Easy Connect useful during troubleshooting?
13. Why can ORA-12154 in a database link be caused by server-side config?
14. What does `lsnrctl status` show?
15. How does `lsnrctl services` differ from `status`?
16. What does LREG do?
17. When is `ALTER SYSTEM REGISTER` used?
18. What is LOCAL_LISTENER used for?
19. What role does REMOTE_LISTENER typically play in RAC?
20. Why should you not manually change SERVICE_NAMES in Oracle 19c?
21. Why can a closed PDB cause ORA-12514?
22. What is `srvctl status service` used to check?
23. Does TNSPING prove a database login will succeed?
24. What does `Test-NetConnection` prove?
25. Why is it necessary to test from the exact application server?
26. How do listener logs and client traces help distinguish error layers?
27. What is ADR?
28. Why should tracing not be left enabled for long periods?
29. How does ORA-12505 differ from ORA-12514?
30. When should SCAN/local listeners be checked in RAC?
31. What configuration is required when JDBC Thin Driver uses a TNS alias?
32. Why might SQL Developer work while a Java app fails with ORA-12154?
33. What details should be recorded during an Oracle Net incident?
34. Why should you not increase timeouts or open firewalls before identifying the failing layer?
35. What test should conclude an end-to-end runbook?

**Answer hints:**

1. Provides naming, addressing, listener, and client/server communication.
2. Identifier is the name/string supplied by the client; descriptor is the resolved protocol/host/port/connect data.
3. An alias name in a naming repository.
4. SID identifies an instance; SERVICE_NAME logically routes to a service.
5. Naming resolution.
6. Cannot reach a listener at the specified address.
7. Listener received the request but does not know the service name.
8. Because the error occurs before the client has a valid descriptor.
9. Specifies the Oracle Net config directory used by the client/process.
10. Order of naming methods.
11. It can append a domain to simple connect identifiers.
12. Isolates alias/TNSNAMES errors from host/port/service errors.
13. The database server process has its own Oracle Net configuration.
14. Listener endpoints, status, services summary, and log path.
15. SERVICES provides details on services, instances, and handlers.
16. Registers service/instance information with the listener.
17. When the instance/service is ready and immediate registration is needed.
18. Specifies the local listener LREG registers with.
19. Registers with remote/SCAN listeners.
20. Because customer use is deprecated; manage services via SRVCTL/GDSCTL/DBMS_SERVICE.
21. A PDB service cannot accept connections if the PDB/service is not ready.
22. Status of services managed by Clusterware.
23. No; an actual SQL*Plus/JDBC login is required.
24. Ability to open TCP to the host/port.
25. Because DNS, firewalls, TNS_ADMIN, JVM, and network namespaces may differ.
26. Listener logs show requests/service registration; client traces show client-side naming and connection steps.
27. Automatic Diagnostic Repository, storing logs/traces/incident data.
28. Tracing can generate large volumes of data and affect performance.
29. ORA-12505 is an unknown SID; ORA-12514 is an unknown service name.
30. When using RAC/SCAN, redirects, or errors isolated to a single node.
31. Corresponding TNS_ADMIN or oracle.net.tns_admin.
32. The two runtimes may use different TNS admin directories or Oracle Net configs.
33. Error code, timestamp, client, redacted descriptor, host/port/service, CONNECTION_ID, and recent changes.
34. Because they do not fix naming/service/listener root causes and can introduce security risks.
35. An actual login and a query verifying database/service/PDB.

## Oracle References

- [Oracle Database 19c Net Services Administrator's Guide — Troubleshooting Oracle Net Services](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/troubleshooting-oracle-net-services.html): diagnostic procedures, ORA-12154, ORA-12514, ORA-12541, logging, and tracing.
- [Oracle Database 19c Net Services Administrator's Guide — Configuring and Administering Oracle Net Listener](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/configuring-and-administering-oracle-net-listener.html): listener, LREG, dynamic registration, LOCAL_LISTENER, REMOTE_LISTENER, and SERVICES.
- [Oracle Database Error Help — ORA-12154](https://docs.oracle.com/en/error-help/db/ora-12154/): naming resolution causes and remedies.
- [Oracle Database Error Help — ORA-12514](https://docs.oracle.com/en/error-help/db/ora-12514/): unregistered service or service not recognized by listener.
- [Oracle Database Error Help — ORA-12541](https://docs.oracle.com/en/error-help/db/ora-12541/): listener not running or host/port unreachable.
- [Oracle Database 19c Quick Start to Oracle Net Services](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/quick-start-oracle-net-services.html): testing connections and service registration.
- [Oracle Database 19c Real Application Clusters Administration and Deployment Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/index.html): SCAN, local listeners, and managing services with SRVCTL.

**Principle to remember:** ORA-12154 is a name resolution error; ORA-12541 is a listener reachability error; ORA-12514 means the listener does not know the service. Identify the exact client and connect descriptor first, then inspect DNS/TCP, the listener, and service registration layer by layer. tnsping and TCP tests are only supporting checks; always perform an actual SQL*Plus or JDBC login from the exact runtime to confirm end-to-end connectivity. On Oracle 19c, inspect LREG, LOCAL_LISTENER, REMOTE_LISTENER, and manage services via SRVCTL/GDSCTL/DBMS_SERVICE instead of modifying SERVICE_NAMES manually. Collect listener logs/ADR/traces in a controlled manner, and only alter configuration once you have evidence of the root cause.
