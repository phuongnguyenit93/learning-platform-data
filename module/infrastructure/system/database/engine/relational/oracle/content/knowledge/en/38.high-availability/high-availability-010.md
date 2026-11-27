# FAN, Fast Connection Failover, and Connection Pool Coordination in Oracle Database

In an Oracle RAC or Oracle Data Guard environment, an instance, node, or database service can stop due to an unexpected failure or be relocated for maintenance. On the application side, already-open connections in a connection pool can become stale: the pool still holds a connection object, but the database endpoint it points to is no longer serving requests.

If an application discovers a broken connection only when submitting the next SQL statement, requests can hang waiting on network timeouts or fail late. Oracle provides **Fast Application Notification (FAN)** so the database rapidly notifies clients of service/instance/node state changes. **Fast Connection Failover (FCF)** is the client/pool mechanism that consumes FAN events to identify and handle affected connections.

FCF coordinates with the connection pool to:

- Evict stale connections from the pool during unplanned outages.
- Drain connections at safe boundaries during planned maintenance.
- Detect newly available services/instances and open connections to surviving targets.
- Support runtime load balancing when services and pools are properly configured.

An exact distinction must be understood: FCF manages physical connection lifecycles and surfaces failures to the application. FCF by itself does not replay in-flight SQL or transactions. During an unplanned outage, uncommitted transactions on lost connections are rolled back by the database and the application receives an exception. If you need outage masking and request replay, configure Application Continuity/Transparent Application Continuity; if you need commit outcome verification to prevent double submission, use Transaction Guard.

This document covers FAN, FCF, and connection pool coordination, focusing on Oracle UCP/JDBC and principles applicable to third-party pools.

## 1. FAN and FCF Architecture

### 1.1 What Is FAN?

Fast Application Notification is an event-broadcasting mechanism from Oracle Clusterware/database services to subscribed clients. FAN reports resource state changes such as:

- A database service starting or stopping.
- A service member on an instance going down or up.
- An instance or node going down.
- A new instance joining and offering a service.
- Runtime Load Balancing Advisory changing recommended load distribution.

FAN enables clients to learn of state changes proactively rather than discovering errors only on the next SQL execution.

### 1.2 What Is FCF?

Fast Connection Failover is a FAN client integrated into a connection pool. The pool receives FAN events, identifies connections tied to the affected service/instance, and handles them based on event type.

In Oracle Universal Connection Pool (UCP), FCF manages connections across the service lifecycle. The Oracle JDBC driver also supports FAN events for third-party pools starting in JDBC 12.2.0.1, though UCP offers deeper integration and fuller support for Oracle FAN capabilities.

### 1.3 General Event Flow

~~~text
Oracle RAC / Data Guard service
          |
          |  FAN event: UP / DOWN / Load Advisory
          v
Oracle Notification Service (ONS)
          |
          |  publish / subscribe notification
          v
JDBC driver / FAN client in JVM
          |
          v
Fast Connection Failover in connection pool
          |
          +--> identify connections by service/instance
          |
          +--> purge stale idle connections
          |
          +--> mark borrowed connections for draining
          |
          +--> create new connections to active instances
          |
          v
Application continues requests or handles exception/retry
~~~

### 1.4 Distinguishing Components

| Component | Role |
|---|---|
| Oracle RAC service | Defines workloads and logical connection endpoints for applications |
| FAN | Notifies of service/instance/node state changes and load advisories |
| ONS | Delivers FAN notifications to client subscribers |
| JDBC FAN support | Receives and processes FAN events in the JDBC driver |
| FCF | Integrates FAN with the connection pool to clean up/recreate connections |
| Connection pool | Manages physical connections, logical handles, borrow/return, and validation |
| Application Continuity | Can replay eligible database requests after recoverable outages |
| Transaction Guard | Provides commit outcome of the last transaction after an outage |

FAN and ONS form the notification layer; FCF forms the connection management layer; Application Continuity/Transaction Guard address request and transaction recovery.

## 2. Key FAN Event Types

FAN events carry metadata about event type, status, service, instance, node, and reason for the change.

### 2.1 Service UP

An UP event announces a service or service member is newly available. The connection pool can open new connections to the joining instance or newly started service.

Examples:

- A RAC instance restarts after maintenance.
- A service relocates back to its original node.
- A new instance joins the cluster and begins offering the service.

The pool gradually allocates new connections toward the newly UP instance per load balancing advisories.

### 2.2 Unplanned Service DOWN

Unplanned DOWN occurs due to:

- Instance crash.
- Node loss.
- Service failure or unavailability.
- Network/storage failure rendering the service unable to serve.

FCF identifies connections tied to the failed service/instance, aborts the network sockets of stale connections, and evicts them from the pool. Both idle connections and currently borrowed connections can be affected. For in-use connections, the application receives an exception when operating on the connection or once the driver reports it closed.

Open uncommitted transactions on the lost session are rolled back by the database. The application must handle the error, acquire a fresh connection, and decide whether retrying the request/transaction is safe.

### 2.3 Planned DOWN

Planned DOWN is emitted when a DBA intentionally stops or relocates a service/instance for maintenance. The event carries a down status and a reason indicating a planned stop; in many RAC events, the reason appears as `user`.

FCF handles planned DOWN differently from unplanned DOWN:

- Idle connections in the pool are purged immediately since no request is using them.
- Borrowed connections are marked for draining and closed only once work finishes, the connection returns to the pool, or it reaches an appropriate safe-draining point.
- In-flight requests get a chance to finish normally.

This enables rolling maintenance without disrupting actively executing requests.

### 2.4 Node DOWN and Instance DOWN

Node DOWN signals a node is no longer available. Instance DOWN signals a database instance stopped or ceased hosting services. These events can affect multiple services and many connections simultaneously.

Pools should rely on FAN metadata to pinpoint affected connections rather than concluding an entire cluster is down from a single connection's failed health check.

### 2.5 Load Balancing Advisory

Runtime Load Balancing Advisory (RLB) delivers recommended work distribution ratios across instances hosting a service. Events can include load distribution percentages or affinity hints.

UCP uses advisories to pick instances when creating new connections and to route requests when borrowing connections. Advisories adapt dynamically to real load, service goals, and instance state.

RLB does not replace initial connection load balancing. The two mechanisms complement each other:

- Connection Load Balancing (CLB): listeners distribute new connections across instances.
- Runtime Load Balancing (RLB): pools use FAN advisories to pick optimal targets for connections/requests at runtime.

## 3. How Planned Outages Differ from Unplanned Outages

This is the most critical distinction when operating FCF.

| Scenario | Idle Connections in Pool | Borrowed Connections | In-Flight Transactions |
|---|---|---|---|
| Planned DOWN | Evicted from pool | Marked for drain; closed at check-in/safe point | Given opportunity to complete |
| Unplanned DOWN | Evicted immediately | Aborted and purged from pool | May receive exceptions; uncommitted transactions rolled back |
| Service UP | Pool can open new connections | Existing connections need not close solely on UP | Requests continue on valid existing connections |

### 3.1 Why Can Planned Outages Cause Zero Request Errors?

Applications borrow a connection only for the duration of a single database request and then return it to the pool. When FAN announces a planned DOWN, the pool stops handing out connections belonging to the draining instance while letting active requests finish. Once the application calls `close()` on the logical connection, the pool closes the drain-marked physical connection instead of returning it to the idle list.

If the service has already relocated to another instance, the pool opens fresh connections on surviving instances for subsequent requests.

### 3.2 Why Do Unplanned Outages Still Raise Exceptions?

When an instance or node vanishes unexpectedly, server-side sessions can no longer execute requests. The pool can evict stale connections quickly, yet it cannot pretend an interrupted transaction succeeded. Applications must catch the exception and resolve transaction state.

Do not assume FCF automatically re-runs all SQL statements. FCF only detects, evicts, and manages connections; replay is the responsibility of Application Continuity or application logic.

### 3.3 Do Not Manually Roll Back Connections Closed by FCF

During certain unplanned failures, the database has already rolled back the local transaction when the session died. Oracle recommends applications do not attempt calling `rollback()` on a closed connection as a recovery step. Instead:

1. Discard the failed connection.
2. Borrow a fresh connection from the pool.
3. Determine the commit outcome if the request may have issued `COMMIT`.
4. Retry the request only when business logic and transaction state permit.

## 4. How Connection Pools Participate in HA

A connection pool maintains a set of physical database connections and lends logical connection handles to threads/requests.

### 4.1 Borrow/Return Lifecycle

~~~text
Pool holds idle connections
          |
          v
Application calls getConnection()
          |
          v
Pool lends logical connection
          |
          v
Application executes database request
          |
          v
Application calls close()
          |
          v
Pool reclaims logical handle
          |
          +--> valid physical connection: return to idle
          |
          +--> connection marked for drain by FAN: close and remove
          |
          v
Connection ready for next request or pool creates replacement connection
~~~

In JDBC pools, `Connection.close()` normally returns the logical handle to the pool; it does not necessarily close the physical database session. This lets the pool reuse connections and drain cleanly at request boundaries.

### 4.2 Holding Connections Too Long Degrades Draining

If an application borrows a connection and holds it across unrelated operations, user think time, or an entire user session, the pool cannot reclaim it to idle for draining. Planned maintenance must wait until the connection returns or the drain timeout expires.

Best practices:

- Borrow a connection immediately before database work is needed.
- Execute a single request/database unit of work.
- Commit or roll back cleanly at the transaction boundary.
- Close the logical connection immediately upon completion.
- Never store a `Connection` in a singleton field or share it across threads.

### 4.3 Request Boundaries

Request boundaries define the start and end of a logical request. When the pool or driver knows these boundaries, the database can pick safe moments to drain or replay.

In UCP, borrowing a connection from `PoolDataSource` starts request usage; `close()` returns the connection to the pool. With frameworks/pools exposing `requestBegin`/`requestEnd` APIs, use the matching lifecycle hooks.

## 5. Fast Connection Failover with Oracle UCP

UCP is Oracle's Java connection pool with built-in FAN/FCF integration. It is Oracle's recommended choice for Java workloads seeking full RAC FAN capabilities.

### 5.1 Basic Prerequisites

Per UCP 19c guidance, FCF with RAC requires:

- Using Oracle Universal Connection Pool.
- Connecting with a service name; never use a SID/instance identifier in place of a service name.
- A database running RAC 12.1+ or properly configured Data Guard.
- ONS configured and reachable in the JDBC runtime environment.
- JVM configured with `oracle.ons.oraclehome` pointing to `ORACLE_HOME` when required by the UCP environment.
- Compatible driver/JAR and ONS components.

If FAN events cannot reach the client, FCF cannot react to connection failovers.

### 5.2 FCF Is Disabled by Default in UCP 19c

In UCP 19c, the FCF pool property is disabled by default. Applications must explicitly enable it:

~~~java
pds.setFastConnectionFailoverEnabled(true);
~~~

Status can be checked via:

~~~java
boolean enabled = pds.getFastConnectionFailoverEnabled();
~~~

In newer UCP/JDBC releases, default behavior can differ. Oracle documents that UCP and JDBC 23ai or later auto-enable FCF when connecting to Oracle RAC in supported configurations. Do not apply that assumption to UCP 19c apps; verify your exact driver, pool version, and release documentation.

### 5.3 UCP Configuration Example

~~~java
import java.sql.Connection;
import java.sql.SQLException;

import oracle.ucp.jdbc.PoolDataSource;
import oracle.ucp.jdbc.PoolDataSourceFactory;

public class RacPoolExample {

    public static PoolDataSource createPool() throws SQLException {
        PoolDataSource pds =
            PoolDataSourceFactory.getPoolDataSource();

        pds.setConnectionPoolName("OrdersPool");
        pds.setConnectionFactoryClassName(
            "oracle.jdbc.pool.OracleDataSource"
        );

        pds.setURL(
            "jdbc:oracle:thin:@//rac-scan.example.com:1521/orders_svc"
        );
        pds.setUser("APP_USER");
        pds.setPassword("read-from-secret-store");

        pds.setInitialPoolSize(5);
        pds.setMinPoolSize(5);
        pds.setMaxPoolSize(40);

        pds.setFastConnectionFailoverEnabled(true);

        return pds;
    }

    public static void runRequest(PoolDataSource pds)
            throws SQLException {
        try (Connection connection = pds.getConnection()) {
            // Execute a short database request.
            // Close returns logical connection to UCP.
        }
    }
}
~~~

The password in the example is merely a placeholder. Production code should retrieve credentials from a secret manager or wallet/credential provider rather than hardcoding them in source code.

The URL specifies the service name `orders_svc`. With RAC, use SCAN/service connect descriptors so listeners distribute connections across instances serving the service.

### 5.4 Remote ONS Configuration

UCP can accept ONS configuration via property:

~~~java
pds.setONSConfiguration(
    "nodes=racnode1.example.com:6200," +
    "racnode2.example.com:6200"
);
~~~

If ONS requires SSL, configure a wallet per environment instructions:

~~~java
pds.setONSConfiguration(
    "nodes=racnode1.example.com:6200," +
    "racnode2.example.com:6200\n" +
    "walletfile=/secure/ons-wallet"
);
~~~

Remote ONS configuration is Oracle's recommended approach for standalone UCP clients. Hosts and ports must match the remote ONS endpoints supplied by DBAs; do not guess ports or open firewall rules arbitrarily.

For certain UCP/RAC combinations 12.1+ without wallets/keystores, UCP can auto-configure ONS without calling `setONSConfiguration`. Verify release behavior and security requirements before omitting explicit configuration.

### 5.5 ONS JARs and Library Versions

For UCP/JDBC, the classpath needs matching components such as:

- `ojdbcXXX.jar`: Oracle JDBC driver.
- `ons.jar`: Oracle Notification Service client.
- `simplefan.jar`: FAN client support.

Use JARs from the exact same compatible release bundle. Never mix a driver from one release with ONS/SimpleFAN from another unless explicitly certified by Oracle.

In JDBC FAN deployments with third-party pools, Oracle also requires `simplefan.jar` and `ons.jar` to be loadable alongside the driver. If either JAR is missing or fails to load, FAN support is silently disabled.

### 5.6 Remote ONS Configuration vs. Client-Side Daemon

Two ways to configure ONS:

| Approach | Description | When Appropriate |
|---|---|---|
| Remote configuration | UCP/JDBC clients connect directly to declared ONS endpoints | Typically recommended by Oracle for standalone Java clients |
| Client-side ONS daemon | Run an ONS daemon on the middle tier and configure `ons.config` | Application server environments or architectures needing a local daemon |

Remote configuration typically uses a `nodes=host:port` list. When using a wallet, all involved ONS peers must have matching SSL/certificate configurations.

### 5.7 PlannedDrainingPeriod

UCP supports the system property:

~~~text
oracle.ucp.PlannedDrainingPeriod
~~~

This property takes a duration in seconds as a grace period for UCP to gradually drain borrowed connections affected by a planned shutdown. Draining starts once the same service is available on another instance.

If unset or set to 0, UCP closes affected connections as soon as they return to the pool. Setting a grace period lets the pool spread connection eviction over the configured window, avoiding logon storms and load spikes on surviving instances.

JVM example:

~~~bash
java -Doracle.ucp.PlannedDrainingPeriod=120 -jar orders-service.jar
~~~

The 120-second value is illustrative. Choose the drain period based on actual request durations and service drain timeouts; this property does not replace server-side drain configuration.

## 6. FAN with Third-Party Connection Pools

Starting with Oracle JDBC 12.2.0.1, the JDBC driver supports FAN events for planned and unplanned outages. Consequently, Java applications using third-party pools do not necessarily have to migrate entirely to UCP to obtain basic FAN benefits.

However, Oracle UCP offers fuller FAN integration. With third-party pools, verify that the pool validates connections on borrow/return and discards connections when the driver flags them closed.

### 6.1 Key Prerequisites

- Use an Oracle JDBC driver supporting FAN events (12.2.0.1 or newer).
- Include `simplefan.jar` and `ons.jar` from the matching compatible release.
- Use `OracleDataSource` or `OracleDriver` as the connection factory per Oracle guidance.
- Pool must support validating connections on checkout or check-in.
- Configure ONS so clients receive FAN notifications.
- Use a service name and RAC-compatible connect descriptor.

### 6.2 Safe-Draining APIs

For planned maintenance, the JDBC driver needs a safe checkpoint where a connection can be closed without interrupting in-flight work. APIs supported by JDBC FAN include:

- `java.sql.Connection.isValid(int timeout)`
- `oracle.jdbc.OracleConnection.pingDatabase()`
- `oracle.jdbc.OracleConnection.pingDatabase(int timeout)`
- `oracle.jdbc.OracleConnection.endRequest()`
- `EXECUTE***` calls on `Statement`, `PreparedStatement`, and `CallableStatement` if the validation SQL carries the `CLIENT_CONNECTION_VALIDATION` hint in the exact required position.

Example connection validation SQL:

~~~sql
/*+ CLIENT_CONNECTION_VALIDATION */ SELECT 1 FROM DUAL
~~~

The hint must be the first token after the comment opener in the SQL string per JDBC FAN requirements. Third-party pools typically invoke validation APIs or SQL at borrow or return time. When the driver reports the connection invalid, the pool must close and evict it.

Never use a single session's failed connection test to conclude an entire instance is down. Validation reflects only the tested connection.

### 6.3 Configuration Examples by Pool Type

Property names depend on product and version. The Oracle JDBC Developer's Guide lists examples such as:

| Pool | Example Validation Options |
|---|---|
| WebLogic Generic/MDS data source | `TestConnectionsOnReserve`, `TestConnectionsOnRelease`, `TestConnectionsOnCreate` |
| IBM WebSphere | `PreTest Connection` |
| JBoss | `check-valid-connection-sql` |
| Apache Tomcat | `testOnBorrow`, `testOnReturn` |

These are product-specific option names; consult documentation for your exact version. Never copy a property name from one pool product to another.

### 6.4 UCP vs. Third-Party Pools?

| Criterion | UCP | Third-Party Pool + JDBC FAN |
|---|---|---|
| FAN/FCF integration | Native direct integration | Depends on JDBC driver and pool validation |
| Planned draining | Built-in pool draining and grace period | Requires safe-draining API/validation and pool config |
| Runtime Load Balancing | Native RLB support | Depends on pool/client capabilities |
| Connection management | Oracle manages full lifecycle | Pool vendor manages lifecycle |
| Configuration | UCP properties and ONS | Driver/JAR/ONS plus pool-specific properties |

If a Java application needs deep RAC HA integration and is not tied to another pool, UCP is the natural fit. If retaining a third-party pool, verify FAN support, driver versions, validation hooks, and planned-draining behavior before production deployment.

## 7. Configuring Oracle RAC Services for FAN and Load Balancing

FAN binds to services, so applications should connect through an explicitly managed service rather than the default database service or a hardcoded SID.

### 7.1 Service Name

A service name represents a workload. DBAs can configure a service across one or more instances, setting preferred/available instances, notifications, and load balancing goals.

When a service relocates, FAN tells pools exactly which connections are affected. Connecting directly to a fixed instance SID or host endpoint bypasses service-level placement and failover routing.

### 7.2 Enabling FAN Notifications and Load Balancing Goals

Example RAC service configuration:

~~~bash
srvctl modify service -db salesdb \
  -service orders_svc \
  -notification TRUE \
  -clbgoal SHORT \
  -rlbgoal SERVICE_TIME
~~~

Parameters:

- `notification TRUE`: enables FAN notifications for the service.
- `clbgoal SHORT`: fits short-request workloads and runtime load balancing / integrated connection pools.
- `rlbgoal SERVICE_TIME`: advises distributing connections by response time.

If a workload optimizes aggregate throughput, use `rlbgoal THROUGHPUT`. For long-lived batch connections balanced by session count, `clbgoal LONG` may be more suitable. Choose goals based on workload traits rather than applying identical settings to every service.

### 7.3 Planned Service Stop or Relocate

When maintaining an instance, relocate or stop services with draining:

~~~bash
srvctl relocate service -db salesdb \
  -service orders_svc \
  -oldinst sales1 \
  -newinst sales2 \
  -drain_timeout 300 \
  -stopoption TRANSACTIONAL
~~~

Or stop the service:

~~~bash
srvctl stop service -db salesdb \
  -service orders_svc \
  -drain_timeout 300 \
  -stopoption TRANSACTIONAL
~~~

These are RAC examples whose syntax may vary by release and options. Verify with `srvctl` help and your cluster runbooks before executing.

### 7.4 DRAIN_TIMEOUT and STOP_OPTION

Two attributes governing planned maintenance:

| Attribute | Meaning |
|---|---|
| `DRAIN_TIMEOUT` | Seconds allowed for requests/sessions to drain before applying the stop option |
| `STOP_OPTION` | How remaining sessions are handled once drain timeout expires |

For services, common stop options are `TRANSACTIONAL` or `IMMEDIATE`:

- `TRANSACTIONAL`: waits for active transactions to finish before terminating sessions per service stop semantics.
- `IMMEDIATE`: terminates remaining sessions immediately once the drain timeout expires.

Pick drain timeouts from observed request duration distributions rather than an arbitrary constant. Too short a timeout cuts off long requests; too long a timeout drags out maintenance windows.

### 7.5 Service UP After Maintenance

After an instance/service restarts, a FAN UP event notifies pools they can open new connections to the instance. Pools gradually rebalance connections across healthy instances per load balancing advisories.

You do not need to restart application servers to refresh pools when FAN/FCF is properly configured and running.

## 8. Runtime Load Balancing and Connection Load Balancing

FAN/FCF also distributes workloads across appropriate instances.

### 8.1 Connection Load Balancing

CLB runs when a client establishes a new connection. Listeners distribute connections based on service goals and instance state. With integrated pools, `CLB` goal `SHORT` is commonly paired with short requests and frequent borrow/return cycles.

### 8.2 Runtime Load Balancing

RLB uses periodic Load Balancing Advisory events. The pool receives database advisories indicating which instance is best suited for the next request.

Two common service goals:

| RLB Goal | Objective | Example Workload |
|---|---|---|
| `SERVICE_TIME` | Balances by response time and serving capacity | OLTP, web shopping, interactive requests |
| `THROUGHPUT` | Balances by throughput | Batch or high-volume processing workloads |

### 8.3 Connection Affinity

Connection affinity keeps related requests on the same instance when beneficial, such as workloads benefiting from cache or service-state locality. Use affinity strictly when semantically justified; do not force affinity if it skews load or pins sessions too long.

In UCP, FCF must be enabled to use runtime connection load balancing and connection affinity per 19c guidance.

### 8.4 Inspecting Service Goals

~~~sql
SELECT name,
       network_name,
       goal,
       clb_goal,
       aq_ha_notification
FROM v$services
ORDER BY name;
~~~

In RAC, query `GV$SERVICES` to inspect services per instance and retain `INST_ID`. Specific column names or outputs may vary by release.

## 9. FCF, TAF, Application Continuity, and Transaction Guard

These features complement one another while solving distinct problems.

| Feature | Scope | Behavior |
|---|---|---|
| FAN | Notification | Reports service/instance/node state changes and load advisories |
| FCF | Connection pool | Detects, evicts, or drains affected connections |
| TAF | Session failover for certain clients/ops | Can reconnect sessions and support SELECT failover per config; no general transaction replay |
| Application Continuity | Request/session replay | Rebuilds sessions and replays eligible database calls after recoverable outages |
| Transparent Application Continuity | Built-in service/client replay | Automates replay for eligible requests |
| Transaction Guard | Commit outcome | Determines whether the last transaction committed to prevent duplicate execution |

### 9.1 FCF Is Not Transaction Replay

FCF closes broken connections and raises exceptions promptly to the application. However, it does not understand full business logic to decide whether re-running a request is safe.

For example, an application executes:

1. `INSERT` an order.
2. `UPDATE` inventory.
3. `COMMIT`.
4. Connection drops before the client receives commit confirmation.

The application cannot simply catch the exception and re-submit the entire transaction. The commit may have already succeeded on the server while the response was lost; re-submitting would create a duplicate order.

### 9.2 Transaction Guard

Transaction Guard uses a Logical Transaction ID (LTXID) to determine the outcome of the last transaction on a failed session. The application discovers whether the transaction committed and can decide safely whether to retry.

Transaction Guard fits applications managing their own retries that require idempotency guarantees. Application Continuity relies on Transaction Guard internally to enable safe replay.

### 9.3 Application Continuity

Application Continuity can:

- Establish a fresh connection/session after a recoverable outage.
- Verify commit outcome using Transaction Guard.
- Restore configured session state.
- Replay eligible database calls.
- Return results to the application as a request that continued after a brief delay.

Replay has limits. Operations with external side effects, external time dependencies, sending emails, HTTP calls, or independent session synchronization may need custom handling. Not every request is safe to replay.

### 9.4 When to Combine Features?

- Only need stale connection eviction with application-managed retries: FAN + FCF.
- Need graceful connection draining during rolling maintenance: FAN + FCF + pool request boundaries + service drain timeouts.
- Need automatic replay of eligible requests: FAN/FCF combined with Application Continuity/TAC.
- Need to verify commit outcomes when writing custom retry logic: Transaction Guard.

## 10. Managing Connection Lifecycles in Applications

FCF works best when applications maintain short, clean connection lifecycles.

### 10.1 Use try-with-resources

~~~java
public Order findOrder(PoolDataSource pool, long orderId)
        throws SQLException {
    String sql =
        "SELECT order_id, status " +
        "FROM orders WHERE order_id = ?";

    try (Connection connection = pool.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, orderId);

        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return null;
            }

            return new Order(
                rs.getLong("order_id"),
                rs.getString("status")
            );
        }
    }
}
~~~

`Connection.close()` returns the logical connection to the pool. `Statement` and `ResultSet` also close cleanly, preventing resource leaks across request boundaries.

### 10.2 Never Share Connections Across Threads

A single JDBC `Connection` should never be shared concurrently by independent threads. Each request/thread should borrow its own connection from the pool and return it immediately afterward.

### 10.3 Never Hold Transactions Across User Think Time

Never open a transaction while rendering a form and hold the connection while a user deliberates. Complete each database unit of work, commit or roll back, and return the connection to the pool.

### 10.4 Managing Session State

Applications may set NLS settings, schemas, client identifiers, package state, or application contexts on a session. When a connection is reused by another request, ensure session state is properly reset or restored.

FCF manages connections only; it does not understand business state or custom session variables. With Application Continuity, session state must be configured to support restoration/replay as required.

## 11. Monitoring FAN, Services, and Connection Pools

FCF must be monitored across the database, ONS, and application pools. Observing that an application still serves requests is not enough to prove FAN/FCF works; inspect event delivery and pool behavior.

### 11.1 Checking Services in the Database

~~~sql
SELECT inst_id,
       name,
       network_name,
       goal,
       clb_goal,
       aq_ha_notifications
FROM gv$services
ORDER BY inst_id, name;
~~~

Columns show service name, network name, runtime load balancing goal, connection load balancing goal, and HA notification settings. Exact names/columns depend on release and privileges.

### 11.2 Viewing Sessions by Service and Instance

~~~sql
SELECT inst_id,
       service_name,
       status,
       COUNT(*) AS session_count
FROM gv$session
WHERE type = 'USER'
GROUP BY inst_id, service_name, status
ORDER BY service_name, inst_id, status;
~~~

This query reveals how service sessions spread across instances. During planned relocation, sessions on the draining instance drop as connections drain while surviving instances accept new connections.

### 11.3 Viewing Clients, Modules, and Pools

~~~sql
SELECT inst_id,
       service_name,
       machine,
       program,
       module,
       COUNT(*) AS session_count
FROM gv$session
WHERE type = 'USER'
GROUP BY inst_id, service_name, machine, program, module
ORDER BY service_name, inst_id, session_count DESC;
~~~

`MODULE`, `PROGRAM`, and `MACHINE` distinguish connections from each application server/pool. Applications should set `MODULE`/`ACTION` and `CLIENT_IDENTIFIER` so DBAs can identify workloads.

### 11.4 Checking Service Status with SRVCTL

~~~bash
srvctl status service -db salesdb -service orders_svc
srvctl config service -db salesdb -service orders_svc
~~~

`STATUS` shows which instances run the service. `CONFIG` confirms notification, preferred/available instances, CLB/RLB goals, and configured service properties.

### 11.5 Checking Client-Side ONS

For client-side ONS daemons, run `onsctl` from the client `ORACLE_HOME`:

~~~bash
onsctl ping
onsctl detailed
~~~

`ping` confirms the daemon is running; `detailed` displays connection/topology status. For remote ONS, inspect client logs and connectivity to configured remote hosts/ports.

ONS logs expose SSL wallet errors, authentication issues, host resolution problems, firewall blocks, or event delivery failures. Secure logs since they contain infrastructure details.

### 11.6 Monitoring Connection Pools

Track pool-exposed metrics such as:

- Total physical connections.
- Available/idle connections.
- Borrowed/in-use connections.
- Connections closed or evicted from the pool.
- Connections newly opened after FAN UP.
- Borrow wait times, timeouts, and pool exhaustion.
- Validation failures.
- Connection creation/reconnection rates.

In UCP, use pool statistics/JMX or version-appropriate management APIs. With third-party pools, inspect vendor metrics and MBeans. Measure both open connection counts and borrow/return rates plus connection churn.

## 12. FAN/FCF Testing Procedure

Execute tests in staging or a dedicated RAC HA test environment. Never arbitrarily stop or kill production instances solely to verify FCF.

### 12.1 Pre-Test Checks

1. Verify service names and instance placement.
2. Verify ONS nodes, ports, wallets, and network routes.
3. Verify compatible driver, UCP, ONS, and SimpleFAN JARs.
4. Verify FCF is enabled.
5. Verify the pool returns connections after every request.
6. Verify application exception/retry semantics.
7. Record baseline session counts, pool metrics, and request latencies.

### 12.2 Testing Planned Relocation

1. Run a workload mixing short and long requests.
2. Confirm connections distribute across the service.
3. Run `srvctl relocate service` to another instance with an appropriate drain timeout.
4. Monitor FAN planned DOWN, idle pool cleanup, and borrowed connection draining.
5. Confirm in-flight requests have a chance to finish.
6. Confirm returned connections tied to the old instance close cleanly.
7. Confirm new requests receive connections to the target instance.
8. Relocate the service back to its original placement and observe FAN UP/rebalancing.

Success criteria: zero unexpected request errors during the drain window, pool stops issuing new connections to the draining instance, and subsequent requests run on surviving instances.

### 12.3 Testing Unplanned Outage

In staging, simulate instance/node/service failure per the HA runbook:

1. Maintain a workload holding both idle and borrowed connections.
2. Trigger an unplanned outage on the chosen instance/service.
3. Confirm FAN DOWN reaches the client.
4. Confirm the pool aborts and evicts stale connections.
5. Confirm active requests receive exceptions as designed.
6. Confirm the application acquires fresh connections and retries only when safe.
7. Confirm uncommitted transactions are not partially applied.
8. Restore the instance/service and observe FAN UP.

Success criteria do not mean "zero exceptions ever." Under an unplanned outage, exceptions on active requests are expected behavior. Success means stale connections purge rapidly, the pool recovers, and the application resolves transactions accurately.

### 12.4 Testing Commit Outcomes

Create a test case where connectivity drops right around `COMMIT`. Verify the application does not blindly resubmit the transaction. When exactly-once transaction outcomes are required, test Transaction Guard or Application Continuity per service configuration.

### 12.5 Testing Scale-Out and Service UP

Add or start a new instance providing the service. Confirm:

- FAN UP arrives.
- Pool opens new connections to the new instance.
- RLB distributes requests per service goals.
- Pool avoids connection storms overloading the newly started instance.

## 13. Common Error Diagnostics

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Pool retains dead connections after node failure | FCF disabled, ONS disconnected, or FAN events not reaching client | Check UCP properties, ONS topology, firewalls, JARs, and service notification |
| FCF inactive despite code enabling it | Using SID instead of service name, database/client missing prerequisites, or ONS unready | Switch to service name and verify release/HA prerequisites |
| UCP not receiving FAN events | Missing `ons.jar`/`simplefan.jar` or version mismatch | Deploy matching JAR bundle and verify classpath |
| Planned maintenance still breaks requests | Pool holds connections past request boundaries, safe-draining API unused, or DBA force-stopped | Fix lifecycle, validation/drain settings, and stop procedure |
| Long requests aborted during planned outage | Drain timeout too short or stop option kills sessions after timeout | Measure request durations and raise drain interval accordingly |
| New connections not created on surviving instances | Service not running on target, bad connect descriptor, or pool missed UP | Check SRVCTL status, service name, and ONS |
| After node returns, pool does not rebalance | FAN UP/RLB disabled or mismatched service goal | Check notifications, CLB/RLB goals, and FCF |
| `ORA-17008 Closed Connection` appears | Connection closed due to unplanned outage or pool validation caught stale connection | Discard failed connection, borrow fresh one, handle retry |
| Transaction executes twice after retry | Application blindly retried without knowing commit outcome | Use Transaction Guard/AC or design idempotency keys |
| Pool triggers logon storm after relocation | All connections recreated simultaneously or pool skips gradual drain | Configure planned draining period, drain timeout, and sensible pool limits |
| ONS SSL/authentication failure | Wallet/certificate mismatch between client and cluster | Synchronize trust/wallets per security runbook |
| Third-party pool fails to drain borrowed connections | Pool does not call safe-draining API or validates at wrong point | Configure pool validation and JDBC FAN integration |
| Connection validation adds latency | Validation SQL runs too often or timeout too long | Tune pool validation policy and use FAN events instead of aggressive polling |

## 14. Application Design Mistakes That Undermine FCF

### 14.1 Holding Connections in Long-Lived Objects

If a service class stores a `Connection` in an instance field for its entire lifetime, the pool cannot drain it at request boundaries. Borrow connections strictly within database operation scopes and close them immediately.

### 14.2 Sharing One Pool Across Dissimilar Services

A pool binds to a URL/service and specific HA settings. Avoid sharing a single pool across workloads with differing service policies, credentials, tenants, or availability needs without explicit design justification.

### 14.3 Connecting via Fixed SID or Instance Host

Pinning connections to one instance bypasses service-level placement, service relocation, and runtime load balancing. Use workload-appropriate service names.

### 14.4 Retrying Every SQLException

Not every `SQLException` stems from an outage. Constraint violations, invalid data, deadlocks, or business errors must not be retried automatically like connection failures.

Retries must:

- Classify recoverable connection errors.
- Enforce retry limits and backoff.
- Acquire a fresh connection.
- Avoid repeating committed transactions.
- Ensure idempotent requests or use Transaction Guard/AC where required.

### 14.5 Oversized Pools

Huge pool sizes do not automatically make an application more highly available. Excessive physical connections inflate session counts, memory, CPU scheduling, and post-failover logon storms. Size min/max pools from true concurrency and surviving-node capacity when one node is offline.

### 14.6 Failing to Plan Capacity for Node Loss

If a RAC cluster has N instances and the workload only survives when all N are up, a single node failover overloads the remaining nodes. Capacity planning must ensure surviving instances carry the load when one or more instances go offline.

## 15. Release and Client-Type Notes

### 15.1 UCP 19c

- FCF is disabled by default; enable via `setFastConnectionFailoverEnabled(true)`.
- ONS must be configured and can use remote configuration.
- UCP supports `PlannedDrainingPeriod` starting in 12.1.0.2.
- Requires service names and compatible RAC/Data Guard topology.

### 15.2 JDBC 12.2+ with Third-Party Pools

- Oracle JDBC supports FAN events for planned/unplanned outages starting in 12.2.0.1.
- Requires `simplefan.jar` and `ons.jar`.
- Planned draining requires safe-draining APIs and pool connection validation.
- UCP retains more comprehensive native FAN integration.

### 15.3 UCP/JDBC 23ai and Newer

Current Oracle HA documentation notes that UCP and JDBC 23ai+ auto-enable FCF when connecting to Oracle RAC in supported configurations. Verify your actual driver, pool, and server versions; never assume UCP 19c behaves like newer defaults.

### 15.4 Other Client Types

Oracle provides FAN/FCF integration across many clients and pools, including OCI Session Pool, ODP.NET, Tuxedo, WebLogic Active GridLink, Python, and Node.js drivers. Configuration syntax, notification transport, and pool properties vary by client. Never apply Java ONS/JAR settings to OCI or ODP.NET.

For each client stack, consult the exact version's Developer's Guide and confirm:

- Supported FAN notification mechanism.
- Whether the client subscribes to events.
- How the pool handles idle vs. borrowed connections.
- Whether planned draining is supported.
- Which feature handles retries, transaction outcomes, and request replay.

## 16. FAN/FCF Implementation Checklist

### Database and Services

1. Does the application connect using a user-defined service name?
2. Does the service span multiple instances or have a suitable failover target?
3. Are FAN notifications enabled on the service?
4. Do CLB and RLB goals match the workload?
5. Does the service configure drain timeout and stop options for planned maintenance?
6. Is remaining capacity sufficient when one instance is removed?

### Client and Connection Pool

1. Are driver, UCP, ONS, and SimpleFAN JARs from the same compatible release?
2. Is FCF enabled appropriately for your release?
3. Is remote/local ONS configuration accurate?
4. Have firewalls, routing, DNS, and wallets/certificates been verified?
5. Can the pool validate and evict stale connections?
6. Does the application return connections to the pool after each request?
7. Are connections ever held in threads/objects too long?
8. Is pool sizing aligned with RAC capacity?

### Application and Recovery

1. Does the application distinguish planned vs. unplanned outages?
2. Are Closed Connection / `SQLRecoverableException` handled properly?
3. Are broken connections discarded before retrying?
4. Are retries idempotent and bounded?
5. Is Transaction Guard used where commit outcomes must be verified?
6. Is Application Continuity/TAC configured if request replay is required?
7. Can session state be reset/restored when connections are replaced?

### Testing and Operations

1. Has planned service relocation been tested?
2. Has unplanned instance/node failure been tested?
3. Has Service UP after recovery been tested?
4. Have transactions failing mid-`COMMIT` been tested?
5. Are FAN/ONS logs and pool metrics actively monitored?
6. Have request latencies and pool exhaustion been measured during failover?
7. Does a runbook exist to roll back/restore services if relocation fails?

## 17. Summary

FAN and FCF work together so connection pools react rapidly to Oracle RAC/Data Guard topology changes:

- FAN broadcasts UP/DOWN state changes and load balancing advisories.
- ONS delivers events to subscribed clients.
- FCF uses events to purge stale connections, drain planned-down connections, and open new connections on surviving service instances.
- Planned DOWN lets borrowed connections finish and closes them at check-in/safe points; unplanned DOWN aborts even active connections and causes uncommitted transactions to roll back.
- UCP offers full FAN/FCF integration; third-party Java pools can leverage JDBC FAN from 12.2 onward with ONS/SimpleFAN and proper safe-draining/validation.
- Applications must return connections at request boundaries and avoid holding connections longer than actual database work.
- FCF does not automatically replay transactions. Application Continuity/Transparent Application Continuity recovers eligible requests; Transaction Guard determines commit outcomes.
- Service names, ONS connectivity, driver/pool versions, drain timeouts, pool sizing, and retry semantics are all integral parts of a complete HA design.

An FCF deployment is trustworthy only after testing both planned maintenance and unplanned outages. Observe FAN events, service states, pool metrics, and transaction outcomes together to prove the application continues serving without duplicate work or overloading surviving instances.

## 18. Oracle Documentation References

- Oracle Database 19c Universal Connection Pool Developer's Guide, "About Fast Connection Failover": https://docs.oracle.com/en/database/oracle/oracle-database/19/jjucp/fast-connection-failover.html
- Oracle Database 19c JDBC Developer's Guide, "Oracle JDBC Support for FAN Events": https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/JDBC-support-Oracle-FAN.html
- Oracle Database 19c High Availability Overview and Best Practices, "Configuring Level 2: Prepare Applications for Planned Maintenance": https://docs.oracle.com/en/database/oracle/oracle-database/19/haovw/configuring-level-2-prepare-applications-planned-maintenance.html
- Oracle Database 19c Real Application Clusters Administration and Deployment Guide, "Ensuring Application Continuity": https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/ensuring-application-continuity.html
- Oracle Database 19c Real Application Clusters Administration and Deployment Guide, "Workload Management with Dynamic Database Services": https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/workload-management-with-dynamic-database-services.html
- Oracle Database 19c Server Control Utility Reference, "srvctl service options": https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/server-control-utility-reference.html
- Oracle Database 19c SQL Processing for Application Developers, "Transaction Guard": https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/sql-processing-for-application-developers.html
- Oracle Database 26ai Real Application Clusters Administration and Deployment Guide, "Managing Planned Maintenance": https://docs.oracle.com/en/database/oracle/oracle-database/26/racad/ensuring-application-continuity/managing-planned-maintenance.html
