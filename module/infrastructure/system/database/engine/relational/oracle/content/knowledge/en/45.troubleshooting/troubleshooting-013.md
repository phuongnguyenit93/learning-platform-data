# ORA-03113, ORA-03135, ORA-17002, and Application Connection Drops

When a Spring Boot application or Java service connects to Oracle Database, connection-loss errors appear in several forms: ORA-03113, ORA-03135, ORA-17002, `Socket read timed out`, `Connection reset`, or `The Network Adapter could not establish the connection`. These messages are related, yet they are not synonymous and do not point to a single cause.

To troubleshoot properly, first determine **whether a connection was never established, dropped mid-operation, or died in the pool after an idle interval**. Then follow the JDBC exception chain and correlate the error timestamp with application logs, network paths, Oracle Listener, server processes, and the database alert log.

| Code/Error | Where Commonly Seen | General Meaning |
|---|---|---|
| ORA-03113 | Oracle Net/client or server log | Communication channel ended unexpectedly |
| ORA-03135 | Oracle Net/client or server log | Lost contact with peer on an established session |
| ORA-17002 | Oracle JDBC driver | JDBC I/O error wrapper; read root cause in exception chain |
| Socket read timed out | Java/network layer | No data received within the read timeout |
| Connection reset / Broken pipe | TCP/OS/network layer | Socket closed or reset by a peer or intermediary device |

Never conclude the database crashed solely from ORA-03113; nor conclude a firewall caused it solely from ORA-03135. A JDBC error can wrap an Oracle Net error, and an Oracle Net error can stem from server processes, listeners, networks, proxies, or client timeouts.

## 1. Classifying Incidents by Timing

### 1.1. Failure Immediately When Opening a Connection

The application cannot acquire a new connection from Oracle. Common errors:

- ORA-17002 with `The Network Adapter could not establish the connection`.
- ORA-12541: `TNS:no listener`.
- ORA-12514: `listener does not currently know of service requested`.
- ORA-12543: `destination host unreachable`.
- `Connection timed out` or `Connection refused`.
- TLS handshake/certificate errors when using TCPS.

Priority investigation steps:

1. DNS/hostname and target address.
2. TCP reachability to host/port.
3. Whether the listener is running and listening on the right interface/port.
4. Whether the service name is registered with the listener.
5. JDBC URL, wallet/TLS, and authentication.
6. Network policies, firewalls, NAT, or load balancers.

If a TCP connection cannot even reach the listener, checking SQL inside the database is not the first step.

### 1.2. Active Connection Dropped Mid-Use

The application logged in and executed queries/DML, then the socket closed. You may see:

- ORA-03113: `end-of-file on communication channel`.
- ORA-03135: `connection lost contact`.
- ORA-17002 with `Socket read timed out`, `Connection reset`, or `Socket closed`.
- `SQLRecoverableException` or `SQLException` with matching vendor codes.

Investigation focus:

- Alert log and server process trace at the exact timestamp.
- Listener log if failure coincides with session creation/reconnection.
- OS logs, process termination, memory pressure, and database instance events.
- Firewall/NAT/proxy idle timeouts or network interruptions.
- JDBC read timeouts and application cancellations.
- RAC node/service failovers or Data Guard role transitions.

### 1.3. Failures Occurring Only After an Idle Interval

If queries run fine yet pooled connections fail after 15, 30, or 60 minutes of inactivity, suspect idle timeouts:

- Firewalls or NAT devices clearing TCP state.
- Load balancers/proxies closing idle connections.
- Database profiles or Resource Manager terminating idle sessions.
- Server/client TCP keepalive not configured appropriately.
- Pool keeping connections alive longer than infrastructure allows.

Check whether the time elapsed before failure repeats consistently. A nearly fixed interval is a strong clue pointing to an intermediary device timeout.

### 1.4. Failure Isolated to One Instance or Network Zone

If only one pod, VM, subnet, or application node sees errors, prioritize comparing:

- DNS resolution.
- Routing, firewall policies, and NAT paths.
- JDBC driver/configuration.
- Connection pool state.
- Host clock and TLS truststore.
- Network interface and OS resources.

If all application nodes fail at the exact same timestamp, check the database instance, listener, shared network path, storage/OS events, and concurrent operational changes.

## 2. ORA-03113: end-of-file on communication channel

### 2.1. Meaning

ORA-03113 means the client stopped receiving expected data over the communication channel; the peer closed the connection or communication ended abruptly. This is a communication-layer symptom, not a self-explanatory root cause.

### 2.2. Common Causes

- The Oracle server process crashed or was terminated.
- The database instance was shut down/aborted or restarted.
- Internal errors such as ORA-00600, ORA-07445, or process memory errors.
- OS killed the process via OOM killer, resource limits, or admin action.
- A network device reset/closed the TCP connection.
- The client process closed the socket or the application restarted.
- Listener/service failover terminated old sessions.
- Storage/I/O errors prevented the server process from continuing.

### 2.3. Information to Capture

Record:

- Exact timestamp and timezone of the application host.
- Host, pod, process ID, and thread name.
- Redacted JDBC URL/service name.
- Oracle error code and all nested causes.
- Executing operation, SQL operation type, and transaction phase.
- Database service, instance, and session if still identifiable.
- Request/correlation ID and related business keys.

### 2.4. Check the Database Alert Log

On the database, retrieve ADR paths:

§§§sql
SELECT name, value
FROM v$diag_info
ORDER BY name;
§§§

Key entries include `ADR Base`, `ADR Home`, `Diag Trace`, `Diag Alert`, and `Default Trace File` depending on context. The alert log typically records instance restarts, process deaths, ORA-00600, ORA-07445, ORA-04030, ORA-04031, or I/O errors near when clients disconnected.

You can use ADRCI on the database host:

§§§text
adrci
show homes
set home <ADR_HOME>
show alert -tail 100
show alert -tail -f
§§§

Choose syntax and ADR home for the actual database instance. Do not search only for the string `ORA-03113`; look for server-side errors occurring before or at the exact timestamp.

### 2.5. Inspect Trace Files

If the alert log names a process ID, incident, or trace file, collect the corresponding trace. Inspect:

- Oracle process ID / session ID.
- Running SQL and final wait event.
- Call stack if an incident was raised.
- ORA-00600/ORA-07445 and incident packages.
- Signs of process termination or resource exhaustion.

Never delete traces/incidents before preserving evidence. For Oracle internal errors, preserve alert logs, traces, and incident packages for DBA/Oracle Support analysis.

### 2.6. Check Whether the Instance Restarted

§§§sql
SELECT instance_name,
       host_name,
       startup_time,
       status,
       database_status
FROM v$instance;
§§§

If `startup_time` changed near the failure time, the instance restarted. Verify why via the alert log and OS logs. If the database stayed open while one specific session disconnected, do not assume an instance restart.

## 3. ORA-03135: connection lost contact

### 3.1. Meaning

ORA-03135 indicates Oracle Net lost contact with the remote peer. It commonly appears on established sessions, especially after prolonged idleness or when a TCP path closes. However, it can also stem from process, server, or network failures; always verify with evidence.

### 3.2. Idle Timeouts

Firewalls, NAT gateways, proxies, VPNs, or load balancers can drop idle TCP connections after a timeout. Both database and application may still believe the connection is open; when the pool reuses the socket, the next operation discovers the peer is gone.

Example:

1. HikariCP opens a connection at 09:00.
2. The connection sits unused.
3. A network firewall drops TCP state at 09:30.
4. The pool still holds the connection object.
5. The application borrows the connection at 09:45.
6. The first query fails with ORA-03135 or ORA-17002 / `Connection reset`.

This is an illustrative timeline. Actual durations depend on infrastructure timeout settings.

### 3.3. SQLNET.EXPIRE_TIME

`SQLNET.EXPIRE_TIME` in `sqlnet.ora` configures probes to verify connection liveness. Values are typically in minutes; a value greater than 0 helps detect dead connections and shorten how long broken connections linger.

Illustrative example:

§§§text
SQLNET.EXPIRE_TIME = 10
§§§

This is neither a query keepalive nor a SQL statement timeout. Choose the value based on Oracle release, network idle timeouts, and system load. Probing too frequently adds unnecessary traffic, and this setting cannot fix every network error.

After editing `sqlnet.ora`, verify which components need reloading/restarting per configuration and release. Server-side changes may apply to new connections or follow Oracle Net rules; do not assume every existing session updates instantaneously.

### 3.4. TCP Keepalive

TCP keepalive is an OS/network stack mechanism that probes peer liveness. It differs from Oracle Net probes and Hikari keepalive. OS values are usually managed by system administrators; verify on the actual Windows/Linux hosts and container network namespaces.

Keepalive helps only if probes fire before intermediary devices expire state and probes are allowed across the network path. It does not replace proper read timeouts or pool validation.

### 3.5. Profile IDLE_TIME and Resource Policies

Inspect the database user's profile:

§§§sql
SELECT username, profile
FROM dba_users
WHERE username = 'APP_RUNTIME';

SELECT profile, resource_name, limit
FROM dba_profiles
WHERE profile = (
    SELECT profile
    FROM dba_users
    WHERE username = 'APP_RUNTIME'
)
AND resource_name IN (
    'IDLE_TIME',
    'CONNECT_TIME',
    'SESSIONS_PER_USER'
);
§§§

Resource limits take effect per `RESOURCE_LIMIT` and active policies. `IDLE_TIME` can terminate sessions after idle periods; this differs from firewall TCP idle timeouts. Inspect alert, audit, and application logs to determine whether Oracle terminated the session or the network closed the socket.

### 3.6. Idle Sessions and Transactions

Never leave transactions open for long intervals waiting on users or external calls. Idle transactions hold locks, undo, and session resources; dropping a connection mid-transaction leaves business outcomes ambiguous on the client.

## 4. ORA-17002 in Oracle JDBC

### 4.1. This Is a JDBC Driver Code

ORA-17002 is the Oracle JDBC driver's code for an I/O error. It is not a single-cause Oracle Database server error. Messages usually include extra detail such as:

- `The Network Adapter could not establish the connection`.
- `Socket read timed out`.
- `Connection reset`.
- `Socket closed`.
- `Broken pipe`.
- `Connection aborted`.

Read the full message and nested exceptions. Recording only ORA-17002 in an incident report is insufficient to isolate the cause.

### 4.2. Connect-Time Failures vs. Mid-Session Failures

If ORA-17002 happens while creating a connection, check DNS, TCP ports, listener, service name, connect timeout, and TLS.

If it happens during a query or commit, check read timeout, network resets, server processes, instance restarts, and transaction outcomes.

If it happens when borrowing an existing connection from a pool, check idle timeouts, keepalive, `maxLifetime`, and validation.

### 4.3. Exception Chains in Java

JDBC can nest errors in `SQLException.getCause()`, `SQLException.getNextException()`, or framework wrappers. Capture:

- Exception class name.
- Message.
- SQLState.
- Vendor error code.
- Cause chain.
- Next-exception chain.
- Thread, request ID, and timestamp.

Example chain-logging helper:

§§§java
import java.sql.SQLException;

public final class JdbcErrorLogger {

    private JdbcErrorLogger() {
    }

    public static void logChain(SQLException exception) {
        SQLException current = exception;
        int index = 0;

        while (current != null) {
            System.err.printf(
                "JDBC[%d] type=%s code=%d state=%s message=%s%n",
                index,
                current.getClass().getName(),
                current.getErrorCode(),
                current.getSQLState(),
                current.getMessage()
            );
            current = current.getNextException();
            index++;
        }

        Throwable cause = exception.getCause();
        while (cause != null) {
            System.err.printf(
                "CAUSE type=%s message=%s%n",
                cause.getClass().getName(),
                cause.getMessage()
            );
            cause = cause.getCause();
        }
    }
}
§§§

This is an illustrative example. In production, use a structured logger instead of `System.err`, bound message lengths, and never log passwords, access tokens, wallet secrets, or personal data.

### 4.4. SQLRecoverableException

Some connection errors are surfaced by the JDBC driver as `SQLRecoverableException` or another `SQLException`. The exception type helps frameworks classify failures, yet does not prove a transaction is safe to retry.

After a connection drop during commit, the client cannot tell whether the server committed. Verify the transaction outcome using a business key, idempotency key, or reconciliation mechanism before re-submitting non-idempotent operations.

### 4.5. Spring Exception Translation

Spring wraps `SQLException` inside `DataAccessException`. When investigating, unwrap down to the root cause and SQL exception chain. Do not log only the outer exception class, which usually only reports that a repository/JPA call failed.

## 5. Path of an Oracle Connection

A connection from Spring Boot to Oracle typically traverses:

§§§text
Spring service / transaction
        |
HikariCP connection pool
        |
Oracle JDBC Thin driver
        |
DNS / route / firewall / NAT / proxy
        |
TCP listener endpoint (host:port)
        |
Oracle Listener
        |
Database service / PDB / instance
        |
Oracle server process
        |
SQL execution / transaction
§§§

Connection drops can occur at any hop. The listener participates primarily in connection establishment and handoff; established sessions communicate directly with the server process, so listener logs will not necessarily record mid-session drops.

### 5.1. DNS

Hostnames can resolve to wrong IPs, stale IPs, or multiple addresses where some are unreachable. Compare DNS resolution directly from the application host/container, not just from the DBA's laptop.

### 5.2. TCP

The listener port is commonly 1521 but may differ. Test TCP connectivity from the exact same network namespace as the application.

### 5.3. Listener

The listener may be down, bound to the wrong interface/port, or unaware of the requested service. Service registration may be delayed or `LOCAL_LISTENER`/`REMOTE_LISTENER` misconfigured.

### 5.4. Database Service

A service name can map to a specific PDB, workload, or role. When a PDB closes, a service unregisters, or Data Guard switches roles, clients fail to connect even though the listener process stays up.

### 5.5. Server Process

A server process can terminate due to internal errors, OS kills, resource exhaustion, or instance shutdown. Alert logs and traces are more informative than listener logs here.

### 5.6. Connection Pool

The pool keeps physical JDBC connections open for reuse. If the network path closed the socket without the pool noticing, the application borrows a stale connection and fails on the first query.

## 6. Checking from the Application Host

### 6.1. Check DNS

Windows PowerShell:

§§§powershell
Resolve-DnsName dbhost.example.internal
§§§

Linux:

§§§bash
getent hosts dbhost.example.internal
nslookup dbhost.example.internal
§§§

Inspect all returned IPs and compare against network/service configuration. For RAC SCAN, hostnames often resolve to multiple IPs; verify every returned address is reachable.

### 6.2. Check TCP Port

Windows:

§§§powershell
Test-NetConnection -ComputerName dbhost.example.internal -Port 1521
§§§

Linux:

§§§bash
nc -vz dbhost.example.internal 1521
§§§

A passing TCP check only proves a TCP handshake reached the endpoint; it does not prove the listener knows the service, the database is open, or the user can log in.

### 6.3. Check TNS Alias

§§§text
tnsping APPDB
§§§

`tnsping` tests alias resolution and Oracle Net listener responsiveness at a basic level. It does not perform a database login, verify passwords, check schema privileges, or prove SQL can execute.

### 6.4. Check the Listener

On the database host:

§§§text
lsnrctl status
lsnrctl services
§§§

Verify:

- Listener name.
- Listening endpoints and ports.
- Registered service names.
- Instance handler status.
- Whether the service maps to the right PDB/role.

If a service is missing, inspect the listener alert log, service configuration, and dynamic registration rather than reflexively restarting the listener.

### 6.5. Test with SQL*Plus or SQLcl

If an Oracle client is installed, test connecting with the exact host/service/user from the application host:

§§§text
sqlplus APP_RUNTIME@//dbhost.example.internal:1521/APP_SERVICE
§§§

Never pass passwords on the command line or in shell history. Succeeding in SQL*Plus does not prove JDBC driver, TLS settings, connection pool, or application timeouts match; it simply isolates layers.

### 6.6. Compare from the Exact Environment

If the app runs in Kubernetes, run tests from a pod or ephemeral diagnostic container sharing the same namespace and network policy. If it runs in a VM, test from that exact VM. A laptop may traverse a VPN or different route.

## 7. Checking Oracle Listener and Services

### 7.1. Listener Status

§§§text
lsnrctl status LISTENER
lsnrctl services LISTENER
§§§

Listener names can differ from the default `LISTENER`. Use actual output to identify endpoints.

### 7.2. Service Registration

Inside the database:

§§§sql
SELECT name,
       network_name,
       pdb
FROM v$services
ORDER BY name;
§§§

Verify the service requested in the JDBC URL is present and maps to the right PDB. A service can exist without being active or registered with the listener.

### 7.3. Instance Status

§§§sql
SELECT inst_id,
       instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM gv$instance
ORDER BY inst_id;
§§§

In non-RAC environments, `V$INSTANCE` can be used. `GV$` views require appropriate privileges and are essential in RAC.

### 7.4. Listener Log

The listener log helps identify:

- Incoming connection requests to endpoints.
- Unrecognized service names.
- Client IP addresses.
- Listener restarts or accept failures.
- Connections dropped during handoff.

The absence of an entry does not prove the network is healthy; packets may not have reached the listener, or the session may have already been handed off earlier.

### 7.5. Do Not Blindly Restart the Listener

Restarting the listener can disrupt new connection setup or alter service registration timing. It rarely fixes broken sockets between an application and existing database server processes. Capture listener status and logs before making changes.

## 8. Checking Database Sessions and Resources

### 8.1. Application User Sessions

§§§sql
SELECT inst_id,
       sid,
       serial#,
       username,
       machine,
       program,
       module,
       service_name,
       status,
       logon_time,
       event
FROM gv$session
WHERE username = 'APP_RUNTIME'
ORDER BY inst_id, logon_time;
§§§

If the application uses a proxy user, different schema owner, or pool switching usernames, adjust the predicate. Setting `MODULE`/`ACTION` via `DBMS_APPLICATION_INFO` links database sessions to application requests/services.

### 8.2. Resource Limits

§§§sql
SELECT inst_id,
       resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM gv$resource_limit
WHERE resource_name IN (
    'processes',
    'sessions',
    'transactions'
)
ORDER BY inst_id, resource_name;
§§§

If near `processes`/`sessions` limits, the database rejects new connections. Check the alert log for accompanying ORA-00018/ORA-00020 errors.

### 8.3. Process and Session Mapping

§§§sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.machine,
       s.program,
       p.spid
FROM gv$session s
JOIN gv$process p
  ON p.inst_id = s.inst_id
 AND p.addr = s.paddr
WHERE s.username = 'APP_RUNTIME';
§§§

This mapping lets DBAs identify the corresponding OS server process when traces/logs report a process ID. Access to `GV$` views requires appropriate privileges.

### 8.4. Sessions That Have Vanished

After a connection drops, the session may already be cleaned up or the server process terminated. Not seeing the session now does not prove the connection never existed. Use the alert log, listener log, audits, and application timestamps to reconstruct history.

### 8.5. Resource Manager and Profiles

Check profile `IDLE_TIME`/`CONNECT_TIME`, Resource Manager consumer groups, session kills, and session governance policies. Distinguish intentional database termination from network socket closures.

## 9. JDBC URLs and Oracle Net Descriptors

### 9.1. Easy Connect Service Name

Example:

§§§text
jdbc:oracle:thin:@//dbhost.example.internal:1521/APP_SERVICE
§§§

The segment after the slash is the service name. In multitenant environments, the service typically maps to a PDB.

### 9.2. TNS Alias

§§§text
jdbc:oracle:thin:@APPDB
§§§

The driver must find the alias in the corresponding Oracle Net configuration. In containers, verify `TNS_ADMIN` and `tnsnames.ora` are properly mounted and configured.

### 9.3. Full Descriptor

§§§text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=10)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (RETRY_COUNT=3)
  (RETRY_DELAY=2)
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.internal)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=APP_SERVICE))
)
§§§

These parameters are examples only. Semantics, units, and support depend on Oracle JDBC and Oracle Net versions. Pick timeouts aligned with latency and RTO; connect retries do not replace transactional retry logic.

### 9.4. SID vs. SERVICE_NAME

Legacy URLs may use a SID:

§§§text
jdbc:oracle:thin:@dbhost.example.internal:1521:ORCL
§§§

Service name:

§§§text
jdbc:oracle:thin:@//dbhost.example.internal:1521/APP_SERVICE
§§§

Never swap SID for service name or vice versa by guesswork. Confirm descriptors, listener services, and database service configuration.

### 9.5. Multi-Address Connection Strings

Oracle Net descriptors can include `ADDRESS_LIST` or multiple `ADDRESS` blocks for RAC/HA. Verify `LOAD_BALANCE`, `FAILOVER`, `RETRY_COUNT`, `RETRY_DELAY`, `CONNECT_TIMEOUT`, and service goals match the topology. One unreachable address in the list can inflate connect times if retry settings are poorly tuned.

### 9.6. SCAN and RAC

With RAC, applications typically connect through the SCAN listener and a service. Never hard-code a single node VIP when the design requires service-aware load balancing and failover. Verify SCAN DNS, all IPs, listeners, and service placement.

## 10. Timeouts: Distinguishing Each Layer

Timeouts serve distinct goals. Setting a single timeout cannot cover the entire connection lifecycle.

| Timeout | Layer | Controls |
|---|---|---|
| DNS timeout | Resolver/network | Time to resolve hostname |
| TCP connect timeout | JDBC/OS | TCP handshake time to endpoint |
| Oracle Net `CONNECT_TIMEOUT` | Oracle Net | Descriptor-level connection establishment time |
| Pool `connectionTimeout` | HikariCP | Time waiting to borrow a connection from pool |
| JDBC `ReadTimeout` | Oracle JDBC socket | Time waiting for data returned on socket |
| `SQLNET.RECV_TIMEOUT` | Oracle Net server/client | Configured receive wait timeout |
| `SQLNET.SEND_TIMEOUT` | Oracle Net | Configured send wait timeout |
| `SQLNET.EXPIRE_TIME` | Oracle Net probe | Periodic liveness probe interval |
| Firewall idle timeout | Network device | Idle TCP state retention duration |
| Hikari `maxLifetime` | Connection pool | Maximum lifetime of a physical pooled connection |
| Hikari `keepaliveTime` | Connection pool | Periodic validation/keepalive for idle connections |
| Query/statement timeout | JDBC/JPA/application | Statement execution or wait limit |

### 10.1. Connect Timeout

Bounds socket opening and Oracle Net session setup. If too low, valid connections over higher-latency links fail; if too high, request threads block when endpoints are unreachable.

### 10.2. Read Timeout

Bounds socket read waits in the JDBC driver. If too low, legitimate long queries hit client timeouts. Client timeouts close the socket while the server may still be working; verify server-side outcomes afterward.

### 10.3. SQLNET.RECV_TIMEOUT and SEND_TIMEOUT

These Oracle Net parameters govern receive/send waits per configuration. They are not equivalent to statement timeouts. Apply them deliberately and test both client and server behavior.

### 10.4. SQLNET.EXPIRE_TIME

This is a periodic probe to detect dead peers, not a query timeout or connect timeout.

### 10.5. Pool connectionTimeout

HikariCP `connectionTimeout` is how long a thread waits to borrow a connection from the pool. If the pool is exhausted because all connections are busy or stuck, requests time out even though the database listener is healthy.

### 10.6. maxLifetime and Firewall Timeouts

Set Hikari `maxLifetime` shorter than any connection lifetime enforced by databases, proxies, or firewalls so the pool proactively retires connections before infrastructure drops them. Hikari cannot detect every network timeout without traffic or keepalive.

### 10.7. Never Set Every Timeout to One Second

Overly aggressive timeouts turn normal load spikes or valid queries into false failures. Overly high timeouts tie up request threads, pool slots, and transactions. Tune to SLOs, latency percentiles, transaction profiles, and failure-detection targets.

## 11. Configuring HikariCP in Spring Boot

### 11.1. Example Configuration

§§§yaml
spring:
  datasource:
    hikari:
      pool-name: OracleAppPool
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 300000
§§§

These values are illustrative milliseconds. Recalculate them based on database limits, firewalls, replica counts, and Oracle capacity. Never copy them verbatim into production.

### 11.2. maxLifetime

HikariCP proactively retires physical connections upon reaching `maxLifetime`; connections currently in use are not killed mid-transaction merely for hitting max lifetime. Set `maxLifetime` below any fixed infrastructure limit.

### 11.3. keepaliveTime

Hikari keepalive applies only to idle pooled connections and must be shorter than `maxLifetime`. It borrows a connection, tests liveness, and returns it to the pool. It does not keep busy connections alive and does not replace TCP keepalive or `SQLNET.EXPIRE_TIME`.

### 11.4. validationTimeout

`validationTimeout` caps connection validation time. It must be less than `connectionTimeout`. An overly long validation timeout delays callers waiting for connections.

### 11.5. connectionTestQuery

With JDBC4 drivers supporting `Connection.isValid()`, HikariCP uses JDBC validation without a custom test query. Configure `connectionTestQuery` only when driver compatibility requires it. If used, ensure the query has no side effects and negligible cost.

### 11.6. maximumPoolSize

Raising pool size does not fix network drops. With 10 application replicas at pool size 20 each, the database can receive up to 200 physical connections plus other clients. Calculate connection budgets across the entire deployment, not one pod.

### 11.7. Leak Detection

Hikari `leakDetectionThreshold` logs warnings when connections are held beyond a threshold; it is a diagnostic tool, not an automatic killer for hung transactions. Pick a sensible threshold and do not confuse leak warnings with network disconnects.

## 12. JDBC Drivers and TLS/TCPS

### 12.1. Driver Version

Verify the actual resolved Oracle JDBC driver version and compatibility with your JDK, Oracle Database release, and Spring Boot/Hibernate stack. Dependency management may resolve a different driver version than directly declared.

### 12.2. Driver Mismatches

Older drivers may lack fixes for TLS, networking, protocols, or database features. Newer drivers must also match the JDK and environment. Collect:

- JDBC driver class and version.
- JDK vendor and version.
- Oracle Database release and patch level.
- Thin vs. OCI mode.
- Connection URL and properties with secrets redacted.

### 12.3. TCPS

When using TCPS, verify:

- Wallets/truststores are mounted properly on all pods.
- Certificate chains are complete.
- Certificates are unexpired and hostnames/SANs match.
- TLS protocols and ciphers are compatible.
- `TNS_ADMIN` and wallet locations are accurate.
- Passwords/keystore secrets are supplied properly.

TLS handshake failures produce distinct exception chains; never resolve them by disabling certificate validation in production.

### 12.4. Connection Resets After Certificate Rotation

When rotating certificates or wallets, application instances may hold open TLS connections from before rotation while new connections use updated trust material. Plan pool reloads/restarts, overlap certificates where needed, and verify reconnects across all replicas.

## 13. RAC, Data Guard, and HA Events

### 13.1. RAC Node Failure

If a RAC instance/node fails, sessions on that node drop. Services relocate or restart on surviving nodes; applications must reconnect and handle in-flight transaction outcomes.

### 13.2. FAN and Fast Connection Failover

Oracle Fast Application Notification (FAN) and Fast Connection Failover (FCF) notify application pools of service/instance events. UCP and Oracle integrations support HA events; HikariCP does not natively provide full FCF behavior like UCP.

If advanced RAC HA is required, evaluate UCP/Oracle JDBC HA integration, service configuration, and FAN/ONS per release instead of assuming all JDBC pools behave identically.

### 13.3. Data Guard Role Transitions

During a Data Guard switchover/failover, services relocate or start on the new primary. Applications must connect using role-aware services, refresh pooled connections, and verify database role before writing.

### 13.4. In-Flight Transactions During Failover

Losing a session during failover does not mean transactions replay automatically and safely. Transaction Guard and Application Continuity support outcome determination and replay in supported topologies, drivers, and services. Verify configuration and eligibility limits before relying on them.

### 13.5. UCP and Application Continuity

Oracle Universal Connection Pool (UCP) integrates with Oracle HA features such as FAN/FCF and can participate in Application Continuity/Transaction Guard when properly configured. These features impose requirements on the database, services, drivers, replay eligibility, and application behavior; not every statement replays safely.

## 14. Retries and Transaction Safety

### 14.1. Never Blindly Retry Every SQLException

When a connection drops mid-transaction, the client may not know whether the server executed or committed the statement. Example:

1. The application sends `COMMIT`.
2. Oracle commits successfully.
3. The network drops before the acknowledgment reaches the application.
4. The application receives ORA-03113/ORA-17002.

If the application blindly retries the entire request, it can create a duplicate transaction even though the first one already committed.

### 14.2. Distinguish Connect Retries from Transaction Retries

- Retrying a new connection before sending business work is usually safe.
- Retrying read-only queries is safe when semantics and snapshot consistency allow.
- Retrying write transactions requires knowing the outcome or using idempotency.
- Retrying after an ambiguous commit outcome must rely on transaction outcome tracking or business reconciliation.

### 14.3. Idempotency Keys

For payment/order creation requests, attach a unique idempotency key per business operation. Enforce a unique constraint on that key in the database so retries cannot create duplicate records.

Example:

§§§sql
CREATE TABLE APP.PAYMENT_REQUEST (
    REQUEST_KEY VARCHAR2(100 CHAR) NOT NULL,
    PAYMENT_ID NUMBER(19),
    STATUS VARCHAR2(20 CHAR) NOT NULL,
    CONSTRAINT PK_PAYMENT_REQUEST PRIMARY KEY (REQUEST_KEY)
);
§§§

Applications must handle duplicate request keys by reading the existing record and returning a consistent response—never merely catching ORA-00001 and assuming everything succeeded.

### 14.4. Exponential Backoff and Jitter

When retrying connections, use increasing backoff with random jitter so multiple application instances do not stampede the database after an outage.

Illustrative policy: 0.5s, 1s, 2s, 4s, 8s with jitter and a total time cap. Actual timings must match SLOs and incident policies.

### 14.5. Circuit Breakers

When a database endpoint fails repeatedly, a circuit breaker pauses new requests to protect thread pools and the database. In half-open state, allow only a few probe requests. Circuit breakers complement, rather than replace, pool validation and HA services.

### 14.6. Evict Broken Connections

Connections hitting I/O errors must not return to the pool for reuse. Frameworks/pools recognize certain `SQLRecoverableException` subclasses and evict them; verify behavior for your driver/pool version and never cache failed connections in application code.

### 14.7. Never Retry Business Errors

Do not retry constraint violations, invalid SQL, authentication failures, or schema errors under the same policy as network drops. Classify errors by SQLState, vendor code, and root cause.

## 15. Logging and Observability in Applications

### 15.1. Fields to Log

- Timestamp with timezone.
- Service name, pod/host, and deployment version.
- Request/correlation ID.
- Redacted database service/endpoint.
- JDBC driver version.
- SQLState, Oracle vendor code, and exception class.
- Root cause and nested exceptions.
- Operation/transaction phase.
- Connection acquisition wait time.
- Query/commit duration if measured.

### 15.2. Never Log Secrets

Never log passwords, secret-bearing wallet paths, tokens, private keys, PII bind values, or credential-bearing connection strings. Mask host/service details if required by security policy.

### 15.3. Pool Metrics

Track:

- Active connections.
- Idle connections.
- Total connections.
- Threads awaiting connections.
- Connection acquisition latency.
- Connection creation failures.
- Timeout counts.
- Connection usage duration.

If `active == max pool size` while pending threads rise, suspect pool exhaustion or transactions holding connections too long—a very different symptom from a downed listener.

### 15.4. Database Observability

Track session counts, process counts, resource limits, service availability, listener logs, alert logs, wait events, CPU, I/O, FRA, and network errors. Synchronize NTP/timezones across app hosts, database hosts, and network appliances for accurate timestamp correlation.

### 15.5. Correlation

Use request IDs in application logs alongside `DBMS_APPLICATION_INFO` `MODULE`/`ACTION`/`CLIENT_IDENTIFIER` to correlate requests with database sessions. Relying on username alone is insufficient when multiple services share one schema user.

## 16. Incident Handling Procedure

### Step 1 — Determine Scope

- One pod or the entire application?
- One service or multiple database services?
- New connects only or active connections too?
- When did errors start, and do they repeat on an idle interval?
- Were there recent deployments, patches, firewall, DNS, certificate, or role changes?

### Step 2 — Capture Complete Exceptions

Collect ORA codes, messages, SQLState, vendor codes, nested causes, and timestamps. Separate ORA-03113/03135 in the cause chain from the outer ORA-17002 wrapper.

### Step 3 — Inspect Application Pool

- Active/idle/total/pending counts.
- Connection acquisition timeouts.
- Connection age and idle duration.
- Hikari `keepaliveTime`/`maxLifetime`.
- Driver version.
- Pool eviction behavior.

### Step 4 — Check Network from the Exact Host

- DNS resolution.
- TCP connect to listener port.
- Routing/firewall/NAT/proxy.
- Idle timeouts.
- TLS/TCPS handshake.
- Compare healthy nodes against failing nodes.

### Step 5 — Check Listener and Services

- `lsnrctl status`/`services`.
- Listener log.
- Service registration.
- PDB open mode and database role.
- SCAN/service placement in RAC.

### Step 6 — Check Database

- `V$DIAG_INFO` and alert log.
- Traces/incidents.
- Instance startup time/status.
- Session/process/resource limits.
- OS logs, OOM events, process kills, storage/network events.

### Step 7 — Verify Transaction Outcomes

If the failure occurred during DML/commit:

- Locate the business key / idempotency key.
- Check whether the record already exists.
- Check audit/outbox/ledger tables.
- Confirm commit outcome before retrying.

### Step 8 — Controlled Recovery

- If listener/service is down: fix the exact component and verify service.
- If pooled connections are stale: evict/recycle cleanly and tune timeouts.
- If instance crashed: resolve the database/OS root cause before reopening traffic.
- If firewall timeout: coordinate with network team on policy/keepalive.
- If TLS: fix certificates, wallets, or trust chains.
- If resources exhausted: address session leaks, connection storms, and capacity.

### Step 9 — Verify

Test connectivity using the runtime user, run a read-only query, run a controlled transaction test, check pool metrics, and monitor long enough to span past the idle interval that triggered the failure.

### Step 10 — Write the RCA

Document root cause, timeline, affected requests/transactions, data impact, fix, preventive actions, and evidence. Never close an incident simply because restarting the app or listener made errors disappear.

## 17. Diagnostic Decision Tree

§§§text
Connection error
|
|-- Cannot open a new connection?
|   |
|   |-- DNS/TCP cannot reach host: DNS, route, firewall, port
|   |
|   |-- TCP succeeds but listener/service fails: listener, service, PDB
|   |
|   |-- TLS handshake fails: wallet, certificate, protocol
|
|-- Connection opened first, then dropped?
|   |
|   |-- Instance/process failure: alert log, trace, OS logs
|   |
|   |-- Only after idle interval: firewall/NAT, keepalive, pool lifetime
|   |
|   |-- During long query: read timeout, network reset, server wait/health
|   |
|   |-- During RAC/role transition: service, FAN/FCF, reconnect behavior
|
|-- Fails only when borrowing from pool?
|   |
|   |-- Pool exhausted: active/pending, leak, long transaction
|   |
|   |-- Stale connection: validation, keepalive, maxLifetime
|
|-- Error occurred during COMMIT?
    |
    |-- Outcome unknown: do not retry blindly; check idempotency/reconciliation
§§§

## 18. Case Studies

### 18.1. ORA-03135 After 30 Minutes Idle

Symptom: all queries work normally, yet the first request after a fixed idle period fails with ORA-03135.

Investigation:

1. Compare idle duration against firewall/NAT timeouts.
2. Check Hikari `keepaliveTime` and `maxLifetime`.
3. Check `SQLNET.EXPIRE_TIME` and OS TCP keepalive.
4. Confirm whether the pool handed out an old connection after the firewall dropped TCP state.
5. Test one configuration adjustment in staging and wait past the idle interval.

Fixes may involve adjusting pool lifetime/keepalive, network idle policies, or Oracle Net probes. Choose per architecture and verify with repeated tests.

### 18.2. Mass ORA-03113 During Database Restart

Symptom: many pods receive ORA-03113 within the same minute.

Investigation:

1. Compare timestamps against `V$INSTANCE.STARTUP_TIME`.
2. Read the alert log for shutdown/startup and preceding errors.
3. Inspect OS logs and maintenance events.
4. Check listener/service registration after restart.
5. Identify in-flight transactions and outcomes.
6. Evict dead connections and reconnect with backoff.

The root cause is a database/OS event; raising pool timeouts will not fix an instance crash.

### 18.3. ORA-17002: Network Adapter Could Not Establish Connection

Symptom: newly deployed app cannot connect while SQL*Plus from the DBA's laptop connects fine.

Investigation:

1. Check hostname resolution inside the pod.
2. Test TCP port from the pod.
3. Compare `TNS_ADMIN`/JDBC URL between app and laptop.
4. Check network policies/security groups.
5. Check service name and listener registration.
6. Check TCPS wallets if the app uses TLS while the laptop uses TCP.

Never use success from a laptop to conclude the network path from a pod works.

### 18.4. ORA-17002 During Commit

Symptom: application writes a payment and receives an I/O error during `COMMIT`; the client does not know whether the commit succeeded.

Handling:

1. Do not immediately retry the payment request.
2. Look up by idempotency key / business request key.
3. Inspect the payment ledger/outbox or gateway state.
4. Determine whether the transaction committed.
5. Re-execute only if the outcome and idempotency rules allow.

### 18.5. One Pod Fails While Other Pods Work Normally

Symptom: only pods on one node receive `Connection reset`.

Investigation:

- DNS cache and resolved IPs.
- Node routing, NAT, and security policies.
- Container network namespace.
- Different driver or config secrets.
- TLS truststore mounts.
- Pool metrics and connection ages.

Fix the failing node or path; never restart the entire database when only one application node is affected.

## 19. Prevention

### 19.1. Connection Design

- Use stable service names instead of hard-coding instance hosts when topology requires HA.
- Use connection descriptors with sensible timeouts and retries.
- Manage JDBC driver versions consistently.
- Synchronize TLS/wallets across all application instances.
- Budget total connections system-wide.

### 19.2. Pool Management

- Set `maxLifetime` shorter than network/database connection lifetimes.
- Use keepalive for idle connections where appropriate.
- Keep `validationTimeout` smaller than `connectionTimeout`.
- Monitor active/idle/pending counts and acquisition latency.
- Close connections, statements, and result sets properly.
- Never hold transactions across network calls or user interactions.

### 19.3. Database / Oracle Net

- Monitor alert logs and listener logs.
- Configure `SQLNET.EXPIRE_TIME` aligned with network policies when needed.
- Monitor process/session limits.
- Monitor instance/node/service availability.
- Preserve ADR/traces and OS logs.

### 19.4. Network

- Align idle timeouts with pool settings and keepalives.
- Audit DNS, routing, NAT, and firewall rules.
- Ensure all RAC SCAN IPs and service endpoints are reachable.
- Monitor packet loss, resets, and connection tracking pressure.
- Synchronize clocks for log correlation.

### 19.5. Application Resilience

- Separate connect retries from transaction retries.
- Enforce idempotency on write requests.
- Use backoff and jitter.
- Use bounded circuit breakers.
- Evict broken connections.
- Implement reconciliation for unknown outcomes.

## 20. Incident Checklist

- [ ] Recorded timestamp with timezone and correlation ID.
- [ ] Captured the full exception chain, SQLState, and vendor codes.
- [ ] Classified whether failure happened on connect, during query/commit, or after idle.
- [ ] Identified affected pods/nodes/services.
- [ ] Tested DNS from the application host/container.
- [ ] Tested TCP port over the exact network path.
- [ ] Checked JDBC URL, service name, and `TNS_ADMIN`.
- [ ] Checked listener status/services and listener logs.
- [ ] Checked database role, PDB, and instance status.
- [ ] Inspected alert logs and traces at the exact failure time.
- [ ] Checked OS/OOM/process kills/storage/network events.
- [ ] Checked `SQLNET.EXPIRE_TIME` and profile idle policies.
- [ ] Checked firewall/NAT/proxy idle timeouts.
- [ ] Checked Hikari active/idle/pending, `maxLifetime`, and `keepaliveTime`.
- [ ] Checked JDBC driver, JDK, and TLS wallets.
- [ ] Checked session/process resource limits.
- [ ] Verified transaction outcomes before retrying DML/COMMIT.
- [ ] Checked idempotency/business keys and external side effects.
- [ ] Verified using the exact runtime user and application path.
- [ ] Documented root cause, data impact, and preventive actions.

## 21. Self-Check Questions

1. What does ORA-03113 describe at the communication channel?
2. Why does ORA-03113 alone not prove the database instance crashed?
3. How does ORA-03135 differ from ORA-03113 in general meaning?
4. Which layer emits ORA-17002?
5. Why must you inspect nested causes and `SQLException.getNextException()`?
6. How do you distinguish a new-connection error from a mid-session drop?
7. What causes ORA-03135 after a fixed idle interval?
8. What is `SQLNET.EXPIRE_TIME` used for?
9. How does `SQLNET.EXPIRE_TIME` differ from TCP keepalive and Hikari keepalive?
10. Why does a successful `tnsping` not prove an application can log in and query?
11. What does `Test-NetConnection` or `nc` verify, and what does it not verify?
12. Which components do ORA-12514 and ORA-12541 point you to check?
13. Which diagnostic paths does `V$DIAG_INFO` help locate?
14. When ORA-03113 occurs, which server-side errors should you look for in the alert log?
15. What does `V$INSTANCE.STARTUP_TIME` help confirm?
16. Why might the listener log not record mid-session drops of established sessions?
17. How does Hikari `connectionTimeout` differ from JDBC `ReadTimeout`?
18. How should `maxLifetime` and `keepaliveTime` align with network idle timeouts?
19. Why can raising `maximumPoolSize` overload the database?
20. What wallet and certificate checks are needed for TCPS connections?
21. Why does one pod failing while others succeed suggest a node-specific network path or config issue?
22. How does RAC service failover impact active sessions?
23. How do FAN/FCF and UCP support high availability?
24. Why does `SQLRecoverableException` not automatically prove a transaction retry is safe?
25. What can happen if the network drops immediately after Oracle commits?
26. How do idempotency keys prevent duplicate business operations?
27. Why do retries need exponential backoff and jitter?
28. Which pool metrics reveal pool exhaustion?
29. When should you inspect `DBA_PROFILES` and `RESOURCE_LIMIT`?
30. What evidence is required before closing an ORA-03113/03135/17002 incident?

**Principle to remember:** Classify errors by timing: connect, active use, or idle. ORA-03113 is an unexpected end of the communication channel; ORA-03135 is lost contact; ORA-17002 is a JDBC I/O wrapper whose root cause must be read. Correlate application exceptions, pool metrics, DNS/TCP, listener/service state, alert logs, traces, and OS/network events at the same timestamp. Align pool lifetime/keepalive with firewall timeouts without confusing them with query timeouts. When drops happen during DML or `COMMIT`, never retry blindly: verify transaction outcomes or rely on idempotency and reconciliation before re-executing.
