# Simulating Pool Exhaustion, Timeouts, Deadlocks, and Controlled Recovery in Oracle Database

An application incident involving Oracle Database can surface as slow requests, connection acquisition failures, SQL timeouts, blocked sessions, or deadlocks. On the surface, these symptoms look quite similar: threads stall, the pool runs out of connections, and users receive errors. However, the root causes and recovery procedures differ.

This hands-on lab simulates four related scenarios:

1. **Connection pool exhaustion:** the application has no idle connections left to hand out to incoming requests.
2. **Timeouts:** requests exceed wait limits at the pool, connect, network, lock, or SQL statement layer.
3. **Deadlocks:** two or more transactions hold resources needed by each other, forming a wait cycle.
4. **Controlled recovery:** gathering evidence, shedding load, releasing resources within the proper scope, restoring the pool, and verifying stability across both application and database.

The lesson uses Oracle Database 19c, JDBC, and HikariCP as examples. You can swap HikariCP for another pool, provided you map each configuration property's semantics. Perform these exercises in a test schema and lab application; never intentionally exhaust pools, induce deadlocks, or kill connections in production.

## 1. Architecture and Layers Where Waits Can Occur

### 1.1. Request Flow to Oracle

A request traverses several layers before SQL executes:

~~~text
HTTP request / job
       |
       v
Application thread
       |
       v
Connection pool
       |
       | borrow idle connection
       v
JDBC connection
       |
       | TCP / Oracle Net / authentication
       v
Oracle listener -> service -> instance
       |
       v
Oracle session
       |
       | parse / execute / wait / fetch
       v
Transaction and data blocks
       |
       v
Commit / rollback -> return connection to pool
~~~

A request can stall at any layer:
- Thread waiting for the pool to hand out a connection.
- Driver waiting on the listener or authentication.
- SQL waiting on a row lock.
- SQL running but starved for CPU or I/O.
- Application holding a connection while calling an external API.
- Connection broken while the pool has not yet evicted it.
- Uncommitted transaction blocking other sessions.

Looking only at response latency or active connection count is not enough to pinpoint the stalling layer.

### 1.2. Distinguishing Pool Exhaustion from Database Session Exhaustion

**Application pool exhaustion** means the pool has leased out its maximum allowed connections and zero idle connections remain. New requests must wait or fail with an acquisition timeout. The database itself may still be healthy.

**Database session/process exhaustion** means Oracle cannot create additional sessions or processes within configured limits or available resources. The pool may fail when attempting to open new physical connections.

Both conditions can occur simultaneously, though they are not synonymous:
- The pool is exhausted because connections are held too long, while Oracle still has plenty of capacity.
- Oracle runs out of sessions, preventing the pool from opening new connections.
- SQL statements are blocked, connections stay checked out longer, and eventually the pool exhausts.
- Oversized pools across many replicas push Oracle to its session limit.

### 1.3. Distinguishing Blocking from Deadlocks

**Blocking** occurs when one session waits on a resource held by another session. The chain clears once the blocker commits or rolls back.

**Deadlock** is a wait cycle: transaction A holds a resource B needs while transaction B holds a resource A needs. Neither can progress without breaking the cycle. Oracle detects the cycle and raises `ORA-00060` on one participating statement.

Blocking can persist for a long time without being a deadlock. Deadlocks are detected automatically by Oracle; DBAs do not need to kill both sessions simply upon seeing `ORA-00060`.

### 1.4. Quick Diagnostic Decision Tree

~~~text
Slow / failing request
       |
       v
Pool has idle connection?
       |
   +---+---+
   |       |
  Yes      No
   |       |
   v       v
Acquired  Active = max?
connection?    |
   |        +--+--+
   |        |     |
   v        No   Yes
Check       |     |
SQL/wait    v     v
         Pool creating  Request
         new conn?      waiting on pool
              |             |
              v             v
         Connect/DB      Inspect
         timeout?       session/SQL
                            |
                            v
                      Lock wait or
                      query/resource?
                            |
                            v
                       Wait cycle?
                         |      |
                        Yes     No
                         |      |
                         v      v
                     ORA-00060 Blocking /
                     deadlock  slow workload
~~~

## 2. Preparing the Lab Environment

### 2.1. Prerequisites

You will need:
- Oracle Database 19c or a compatible test environment.
- A dedicated test user schema, e.g., `LAB_APP`.
- Privileges to create tables and sequences in that schema.
- A JDK-compatible Oracle JDBC driver.
- HikariCP in the Java project.
- At least two SQL sessions to simulate blocking and deadlocks.
- Read access to dynamic performance views if inspecting sessions from a DBA perspective.

No `DBA` role is needed for the basic lab if the user owns its schema objects. Querying `GV$`/`V$` and `DBA_*` views requires appropriate grants; ask a DBA for least-privilege read access or run monitoring queries from an operational account.

### 2.2. Confirming Database and Service

Connect using the service-name JDBC URL provided by your DBA:

~~~text
jdbc:oracle:thin:@//dbhost.example.com:1521/labpdb.example.com
~~~

After connecting, verify database, PDB, service, and user:

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME')       AS db_name,
    sys_context('USERENV', 'CON_NAME')      AS con_name,
    sys_context('USERENV', 'SERVICE_NAME')  AS service_name,
    sys_context('USERENV', 'SESSION_USER')  AS session_user,
    sys_context('USERENV', 'INSTANCE_NAME') AS instance_name
FROM dual;
~~~

Never run lab exercises against a production service simply because its URL is already saved in local config.

### 2.3. Creating Test Tables

Create an account table to test locks and deadlocks:

~~~sql
CREATE TABLE lab_account (
    account_id NUMBER(10) CONSTRAINT pk_lab_account PRIMARY KEY,
    balance    NUMBER(12,2) NOT NULL,
    note       VARCHAR2(100)
);

INSERT INTO lab_account(account_id, balance, note)
VALUES (1, 1000, 'account-1');

INSERT INTO lab_account(account_id, balance, note)
VALUES (2, 1000, 'account-2');

COMMIT;
~~~

Create a work table to test holding connections and running queries:

~~~sql
CREATE TABLE lab_work (
    work_id     NUMBER(10) CONSTRAINT pk_lab_work PRIMARY KEY,
    status      VARCHAR2(20) NOT NULL,
    amount      NUMBER(12,2),
    created_at  TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO lab_work(work_id, status, amount)
SELECT LEVEL,
       CASE WHEN MOD(LEVEL, 2) = 0 THEN 'READY' ELSE 'NEW' END,
       LEVEL * 10
FROM dual
CONNECT BY LEVEL <= 1000;

COMMIT;
~~~

### 2.4. Tagging Lab Sessions with MODULE and ACTION

When applications call `DBMS_APPLICATION_INFO`, DBAs can identify connections by module and action:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'OraclePoolLab',
        action_name => 'PoolExhaustion'
    );
END;
/
~~~

JDBC can also set module/action via Oracle JDBC APIs or callable statements. Setting module tags is especially helpful when multiple applications share a database service.

### 2.5. Recording a Baseline

Before each scenario, capture:
- Active concurrent requests/threads.
- Pool maximum, active, idle, and waiting counts.
- Connection acquisition wait time.
- Count of Oracle sessions belonging to the lab module.
- `SQL_ID` and wait events.
- CPU, memory, and I/O if available.
- Error counts and p50/p95/p99 latencies.

You cannot declare a lab successful just because an exception appeared. Prove the state of both the pool and the database before, during, and after the fault.

## 3. Connection Pool Configuration

### 3.1. What Does a Pool Manage?

A connection pool maintains a set of physical database connections and lends them to threads on demand. When application code calls `close` on a borrowed connection, the connection is returned to the pool rather than tearing down the TCP and database session immediately.

Pools typically manage:
- Maximum pool size.
- Minimum idle connections.
- Acquisition timeout.
- Validation timeout.
- Idle timeout.
- Maximum lifetime.
- Keepalive.
- Connection validation.
- Metrics and leak detection.

A pool does not manage business transactions on behalf of the application. The application must still commit, roll back, and close resources properly.

### 3.2. Spring Boot Example with HikariCP

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//dbhost.example.com:1521/labpdb.example.com
spring.datasource.username=LAB_APP
spring.datasource.password=SET_FROM_SECRET_STORE
spring.datasource.driver-class-name=oracle.jdbc.OracleDriver

spring.datasource.hikari.pool-name=OracleLabPool
spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.validation-timeout=1000
spring.datasource.hikari.idle-timeout=600000
spring.datasource.hikari.max-lifetime=1800000
spring.datasource.hikari.keepalive-time=120000
spring.datasource.hikari.leak-detection-threshold=10000
~~~

This is a lab configuration intended to surface timeouts clearly. Never copy these numbers into production without sizing for replica counts, database capacity, network timeouts, and SLAs.

### 3.3. HikariCP Parameter Meanings

| Parameter | Unit | Meaning |
| --- | --- | --- |
| `maximumPoolSize` | connections | Maximum physical connections in the pool |
| `minimumIdle` | connections | Target minimum idle connections |
| `connectionTimeout` | ms | Wait time to borrow a connection from the pool |
| `validationTimeout` | ms | Max time to validate a connection |
| `idleTimeout` | ms | Idle duration before excess connections may be retired |
| `maxLifetime` | ms | Maximum connection age before recycling |
| `keepaliveTime` | ms | Interval to probe/keep idle connections alive if configured |
| `leakDetectionThreshold` | ms | Threshold to log connections held beyond expected duration |

Key rules:
- `maximumPoolSize` caps database concurrency per pool, not maximum application requests.
- `connectionTimeout` is the pool borrow timeout; it does not replace Oracle JDBC's connect timeout.
- `leakDetectionThreshold` only warns when a connection stays checked out past the threshold. A legitimate long transaction can also trigger it.
- `maxLifetime` should be shorter than any lifetime limit enforced by the database, firewall, or network infrastructure.
- `validationTimeout` must be strictly less than `connectionTimeout` per HikariCP requirements.
- `keepaliveTime` must be less than `maxLifetime` and applies only to idle connections per pool semantics.

### 3.4. Sizing Pools System-Wide

Never size for a single JVM in isolation. With multiple replicas:

~~~text
Maximum total connections
= application replicas × maximumPoolSize
  + batch/worker pools
  + admin/monitoring
  + other clients
~~~

For example, 8 replicas each with `maximumPoolSize = 20`:

~~~text
8 × 20 = 160 maximum connections from the web application
~~~

Add batch jobs, schedulers, BI tools, monitoring, and DBA headroom. The sum must fit comfortably within database capacity.

Do not set pool size equal to web server thread count. An application with 200 worker threads rarely needs 200 Oracle connections; overly large pools increase DB contention and can reduce throughput.

### 3.5. Inspecting the Pool via MXBean

Hikari exposes `PoolMXBean` for runtime inspection:

~~~java
HikariPoolMXBean poolBean = dataSource.getHikariPoolMXBean();

int active = poolBean.getActiveConnections();
int idle = poolBean.getIdleConnections();
int total = poolBean.getTotalConnections();
int waiting = poolBean.getThreadsAwaitingConnection();
~~~

Key metrics:
- Active: connections currently borrowed by application threads.
- Idle: connections currently available.
- Total: total physical connections currently in the pool.
- Threads awaiting connection: threads blocked waiting to borrow.

If active stays pinned at maximum, idle sits at 0, and waiting climbs, the pool is saturated. Find out why connections are held so long before raising `maximumPoolSize`.

### 3.6. Observing from Oracle

DBAs can count sessions by service and module:

~~~sql
SELECT inst_id,
       service_name,
       module,
       status,
       COUNT(*) AS session_count
FROM   gv$session
WHERE  type = 'USER'
GROUP  BY inst_id, service_name, module, status
ORDER  BY inst_id, service_name, module, status;
~~~

If `MODULE` is unset, group by username, machine, program, and service. Compare database session counts with pool metrics. Discrepancies can stem from multiple data sources, pools, admin connections, or unclosed connections.

## 4. Lab A — Simulating Pool Exhaustion

### 4.1. Objective

Create a pool of max 3 connections and launch 8 concurrent workers. The first three workers borrow connections and hold them for several seconds; the remaining workers wait. With a short `connectionTimeout`, several workers will hit acquisition timeouts.

This is an intentional simulation. In production, never hold connections while sleeping, waiting on users, or calling external services.

### 4.2. Maven Dependencies

Example using approved HikariCP and Oracle JDBC driver versions:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.zaxxer</groupId>
        <artifactId>HikariCP</artifactId>
        <version>YOUR_APPROVED_HIKARI_VERSION</version>
    </dependency>
    <dependency>
        <groupId>com.oracle.database.jdbc</groupId>
        <artifactId>ojdbc11</artifactId>
        <version>YOUR_APPROVED_OJDBC_VERSION</version>
    </dependency>
</dependencies>
~~~

Select the JDBC artifact matching your JDK and Oracle driver compatibility matrix. Never put placeholder version strings directly into a real build.

### 4.3. Java Simulation Program

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class PoolExhaustionLab {
    public static void main(String[] args) throws Exception {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(System.getenv("LAB_JDBC_URL"));
        config.setUsername(System.getenv("LAB_DB_USER"));
        config.setPassword(System.getenv("LAB_DB_PASSWORD"));
        config.setPoolName("PoolExhaustionLab");
        config.setMaximumPoolSize(3);
        config.setMinimumIdle(3);
        config.setConnectionTimeout(1500);
        config.setValidationTimeout(1000);

        try (HikariDataSource dataSource = new HikariDataSource(config)) {
            int workers = 8;
            CountDownLatch start = new CountDownLatch(1);
            ExecutorService executor = Executors.newFixedThreadPool(workers);
            List<Future<?>> tasks = new ArrayList<>();

            for (int i = 0; i < workers; i++) {
                final int workerId = i;
                tasks.add(executor.submit(() -> {
                    try {
                        start.await();

                        try (Connection connection = dataSource.getConnection()) {
                            System.out.println(
                                "worker-" + workerId + " acquired connection"
                            );

                            // Used only to hold the connection in this lab.
                            Thread.sleep(5000);

                            System.out.println(
                                "worker-" + workerId + " returning connection"
                            );
                        }
                    } catch (SQLException e) {
                        System.out.println(
                            "worker-" + workerId + " failed: "
                            + e.getClass().getSimpleName() + ": "
                            + e.getMessage()
                        );
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }));
            }

            start.countDown();

            HikariPoolMXBean pool = dataSource.getHikariPoolMXBean();
            for (int i = 0; i < 6; i++) {
                Thread.sleep(500);
                System.out.printf(
                    "active=%d idle=%d total=%d waiting=%d%n",
                    pool.getActiveConnections(),
                    pool.getIdleConnections(),
                    pool.getTotalConnections(),
                    pool.getThreadsAwaitingConnection()
                );
            }

            for (Future<?> task : tasks) {
                task.get();
            }

            executor.shutdown();
        }
    }
}
~~~

Supply `LAB_JDBC_URL`, `LAB_DB_USER`, and `LAB_DB_PASSWORD` via secure lab environment variables. Run the program and observe both console logs and MXBean output.

### 4.4. Expected Observations

With a pool size of 3, you should observe:
- At most 3 workers hold connections simultaneously.
- Remaining workers increment the waiting thread count.
- Several workers fail with an acquisition timeout after roughly `connectionTimeout`.
- Once the initial workers return their connections, any still-waiting worker acquires a connection if it has not yet timed out.
- After all tasks finish, `active` returns to 0 and `idle` settles toward the configured minimum.

Exact worker success/failure order is non-deterministic due to thread scheduling and connection initialization timing.

### 4.5. Observing on Oracle

While the lab runs, execute:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       service_name,
       module,
       machine,
       event,
       sql_id,
       logon_time
FROM   gv$session
WHERE  username = 'LAB_APP'
ORDER  BY inst_id, sid;
~~~

If `module` is blank, the program has not set it or the driver has not sent it yet. Session counts may not match pool size at every instant due to pool startup, validation, and lifecycle churn.

### 4.6. Analyzing Root Causes

Pool exhaustion alone does not tell you *why* connections are held:
- Slow queries.
- Lock waits.
- Uncommitted transactions.
- Connection leaks.
- Threads waiting on external APIs inside transactions.
- Pool size smaller than legitimate concurrency.
- Slow database or network delaying connection return.

The next step is finding the connection owners and corresponding SQL/sessions, not immediately raising pool size.

## 5. Lab B — Simulating Connection Leaks and Long-Held Connections

### 5.1. True Leaks vs. Busy Connections

A **connection leak** happens when code borrows a connection and never returns it to the pool—for example, skipping `close()` on an exception path or storing a connection in a long-lived object.

A **long-held connection** may be a valid transaction or slow query occupying a pool slot for an extended duration. Leak detection can flag both; examine stack traces and actual durations to tell them apart.

### 5.2. Leak-Prone Code Example

~~~java
public void updateOrder(DataSource dataSource, long orderId)
        throws SQLException {
    Connection connection = dataSource.getConnection();

    PreparedStatement statement = connection.prepareStatement(
        "UPDATE lab_work SET status = 'DONE' WHERE work_id = ?"
    );
    statement.setLong(1, orderId);
    statement.executeUpdate();

    // If an exception occurs before close, resources may leak.
    statement.close();
    connection.close();
}
~~~

If `executeUpdate()` throws, the `close()` calls below are skipped. Use `try-with-resources` to guarantee closure:

~~~java
public void updateOrder(DataSource dataSource, long orderId)
        throws SQLException {
    String sql =
        "UPDATE lab_work SET status = 'DONE' WHERE work_id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.executeUpdate();
    }
}
~~~

In Spring-managed transactions, let the transaction manager control connection lifecycle. Never manually close a framework-managed connection inside an active transaction.

### 5.3. HikariCP Leak Detection

~~~properties
spring.datasource.hikari.leak-detection-threshold=20000
~~~

If a connection stays checked out longer than the threshold, Hikari logs the stack trace from where it was borrowed. When the connection is eventually returned, Hikari logs that the apparent leak recovered.

Set the threshold high enough to avoid false positives from valid long transactions. Leak detection is a diagnostic tool, not an automatic connection-reclamation mechanism.

### 5.4. Patterns That Hold Connections Too Long

- Starting a transaction before making HTTP service calls.
- Holding a connection while waiting for user input.
- Acquiring application-level `synchronized`/locks while inside an active transaction.
- Streaming a `ResultSet` slowly without closing it promptly.
- Failing to close `Statement` or `ResultSet` objects.
- Triggering unnecessary nested transactions/connections (`REQUIRES_NEW`).
- Processing huge batches inside a single transaction.
- Catching exceptions and skipping rollback.

Keep transactions short, hold connections strictly during database work, and close all resources according to lifecycle rules.

## 6. Timeouts: Identifying Which Layer Timed Out

### 6.1. Timeout Comparison Table

| Timeout | Layer | Typical Unit | Control |
| --- | --- | --- | --- |
| Request/deadline timeout | HTTP/RPC/application | ms or s | Framework/gateway/client |
| Pool acquisition timeout | Connection pool | ms | Hikari `connectionTimeout` |
| Login/connect timeout | JDBC/Oracle Net | driver-specific | JDBC/Oracle Net properties |
| Network read timeout | Socket/JDBC | ms | Oracle JDBC `ReadTimeout` or JDBC network timeout |
| Lock wait timeout | Oracle transaction | s | `DML_LOCK_TIMEOUT` or `SELECT FOR UPDATE WAIT` |
| Statement query timeout | JDBC statement | s | `Statement.setQueryTimeout` |
| Transaction timeout | Transaction manager | s | Spring/JTA/container |
| Validation timeout | Connection pool | ms | Hikari `validationTimeout` |

A timeout at one layer does not automatically cancel work at lower layers. For example, an HTTP deadline expiring makes the client stop waiting, while the JDBC statement keeps running unless the application cancels and rolls it back cleanly.

### 6.2. Pool Acquisition Timeout

Hikari:

~~~properties
spring.datasource.hikari.connection-timeout=3000
~~~

Requests wait up to roughly 3 seconds to borrow a connection from the pool. If the pool is exhausted and nothing returns in time, Hikari throws a connection acquisition exception.

This differs from listener or authentication failures. Inspect the exception cause, pool metrics, and physical connection creation logs to see whether threads waited on the pool or the driver stalled opening a socket.

### 6.3. JDBC Login Timeout

JDBC `DriverManager` supports a login timeout in seconds:

~~~java
DriverManager.setLoginTimeout(10);
~~~

Login timeout is a `DriverManager`-level setting and can affect connections opened via `DriverManager` within the JVM. With `DataSource`/connection pools, check how your driver and pool honor timeout properties. Never assume it replaces all Oracle Net timeouts.

### 6.4. Oracle Net Connect Timeout

Oracle Net provides timeout parameters for connecting to listeners/endpoints, such as `CONNECT_TIMEOUT` and `TRANSPORT_CONNECT_TIMEOUT` inside connect descriptors or Easy Connect Plus in supported versions.

Illustrative descriptor example:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=10)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=labpdb.example.com))
)
~~~

Units and scope depend on the specific parameter and driver. Verify Oracle JDBC and Oracle Net documentation for your version. These govern connection establishment, not query execution duration.

### 6.5. JDBC Network/Read Timeout

Oracle JDBC supports a driver-level network read timeout, commonly configured via `oracle.jdbc.ReadTimeout` in milliseconds.

Example `DataSource` property:

~~~java
Properties properties = new Properties();
properties.setProperty("oracle.jdbc.ReadTimeout", "30000");
~~~

How properties are passed varies between `DriverManager`, `OracleDataSource`, and connection pools. Check your exact pool and driver APIs.

JDBC 4.1 also provides `Connection.setNetworkTimeout(Executor, milliseconds)`. It caps the wait for a network response per JDBC specification; the driver must support it and an appropriate `Executor` must be provided.

~~~java
connection.setNetworkTimeout(networkExecutor, 30000);
~~~

A network timeout is not a query timeout. Once triggered, the connection may be marked unusable; the pool should evict it and establish a fresh connection.

### 6.6. Statement Query Timeout

JDBC:

~~~java
try (PreparedStatement statement =
         connection.prepareStatement(
             "SELECT work_id, status FROM lab_work WHERE work_id = ?")) {

    statement.setLong(1, 10L);
    statement.setQueryTimeout(5);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            System.out.println(resultSet.getLong("work_id"));
        }
    }
}
~~~

`setQueryTimeout` takes seconds. When expired, the driver attempts to cancel the running statement per JDBC semantics. Verify driver/database behavior and transaction state after cancellation.

### 6.7. Lock Wait Timeout

DML lock waits can be bounded at the session level:

~~~sql
ALTER SESSION SET DML_LOCK_TIMEOUT = 5;
~~~

DML needing a lock waits up to this limit before raising a resource-busy error if the lock is not released.

For `SELECT FOR UPDATE`, specify explicitly:

~~~sql
SELECT account_id, balance
FROM   lab_account
WHERE  account_id = 1
FOR UPDATE WAIT 5;
~~~

Or fail immediately without waiting:

~~~sql
SELECT account_id, balance
FROM   lab_account
WHERE  account_id = 1
FOR UPDATE NOWAIT;
~~~

Lock timeout is a lock-waiting policy. It does not replace deadlock detection; deadlock cycles are detected by Oracle and raise `ORA-00060`.

### 6.8. Aligning Timeouts to an End-to-End Deadline

Suppose a request has an 8-second deadline:
- Pool acquisition: at most 1 second.
- New physical connection if needed: at most 2 seconds.
- SQL statement execution: at most 4 seconds.
- Remaining budget for processing results and returning the response.

Never set every layer to 30 seconds while the HTTP gateway gives up after 5 seconds. When lower-layer timeouts exceed the request deadline, the application keeps doing wasted work long after the client has disconnected.

Likewise, do not set all timeouts identically; account for setup, retries, fetching, and cleanup.

## 7. Lab C — Simulating Lock Waits and Timeouts

### 7.1. Preparing Two SQL Sessions

Open Session A and Session B connected to the same `LAB_APP` schema.

Session A:

~~~sql
ALTER SESSION SET DML_LOCK_TIMEOUT = 30;

UPDATE lab_account
SET    balance = balance - 100
WHERE  account_id = 1;

-- Hold transaction open, do not COMMIT yet.
~~~

Session A holds the row lock on account 1.

Session B:

~~~sql
ALTER SESSION SET DML_LOCK_TIMEOUT = 5;

UPDATE lab_account
SET    balance = balance + 50
WHERE  account_id = 1;
~~~

Session B blocks on Session A's lock. After the configured timeout elapses, Session B receives a resource-busy error if the lock has not been released.

### 7.2. Observing Wait Events

From a DBA session:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       seconds_in_wait,
       blocking_instance,
       blocking_session,
       sql_id
FROM   gv$session
WHERE  username = 'LAB_APP'
ORDER  BY inst_id, sid;
~~~

Session B typically displays an enqueue/transaction-related wait event while waiting for the row lock. Exact wait event names depend on lock type and Oracle release.

### 7.3. Releasing the Lock

Session A:

~~~sql
ROLLBACK;
~~~

Once the rollback finishes, Session B proceeds if it has not yet timed out. If Session B already received a timeout error, its statement has failed; the application must decide whether to retry the transaction.

### 7.4. Comparing NOWAIT, WAIT, and DML_LOCK_TIMEOUT

- `NOWAIT`: do not wait; fail immediately if the lock is held.
- `WAIT n`: wait up to `n` seconds on `SELECT FOR UPDATE`.
- `DML_LOCK_TIMEOUT`: controls DML lock wait duration at supported session/system scopes.

Do not confuse this with `DDL_LOCK_TIMEOUT`, which governs DDL lock waits. Timeouts do not release blockers or fix application code that holds transactions open too long.

## 8. Lab D — Creating a Controlled Deadlock

### 8.1. Cause of Deadlocks

Deadlocks occur when transactions acquire locks on the same resources in conflicting orders.

Example:
- Transaction A locks account 1, then requests account 2.
- Transaction B locks account 2, then requests account 1.

Each holds one row lock while waiting for the other. Oracle detects the wait cycle and raises `ORA-00060` to one statement.

### 8.2. Resetting Test Data

~~~sql
UPDATE lab_account
SET balance = 1000
WHERE account_id IN (1, 2);

COMMIT;
~~~

### 8.3. Session A — Lock the First Row

~~~sql
UPDATE lab_account
SET balance = balance - 10
WHERE account_id = 1;

-- Do not COMMIT yet.
~~~

### 8.4. Session B — Lock the Second Row

~~~sql
UPDATE lab_account
SET balance = balance - 20
WHERE account_id = 2;

-- Do not COMMIT yet.
~~~

### 8.5. Session A — Request the Row Held by Session B

~~~sql
UPDATE lab_account
SET balance = balance + 20
WHERE account_id = 2;
~~~

Session A blocks waiting on Session B.

### 8.6. Session B — Complete the Deadlock Cycle

~~~sql
UPDATE lab_account
SET balance = balance + 10
WHERE account_id = 1;
~~~

Session B requests row 1, held by Session A. Oracle detects the deadlock and raises `ORA-00060` on one of the statements. Which session is chosen as the victim depends on runtime timing; never assume it is always Session B.

### 8.7. What Does Oracle Do Upon Detecting a Deadlock?

Oracle detects the cycle, rolls back the statement causing the deadlock in one transaction, and returns `ORA-00060` to that client. Rolling back that statement does *not* roll back the entire transaction.

Earlier statements in that transaction remain uncommitted and continue holding locks. The application should roll back the entire transaction whenever the business operation is atomic, and only then consider retrying from the beginning.

Never blindly commit a transaction after `ORA-00060`. Determine transaction state and business semantics first.

### 8.8. Cleaning Up the Lab and Restoring Data

In both sessions, check transaction state and explicitly roll back:

~~~sql
ROLLBACK;
~~~

Then verify data:

~~~sql
SELECT account_id, balance
FROM   lab_account
ORDER  BY account_id;
~~~

Reset balances to initial values if needed and commit in the lab. Do not treat post-deadlock balances as business outcomes; the lab's goal is observing lock cycles and Oracle's error reporting.

## 9. Analyzing ORA-00060 and Deadlock Graphs

### 9.1. Capturing Details from the Application

`ORA-00060` is usually wrapped in a `SQLException` or framework exception. Record:
- SQL operation and transaction boundary.
- `SQL_ID` if available.
- Request or correlation ID.
- Module, action, and client identifier.
- Instance and service.
- Error timestamp.
- Full exception chain.

Never log passwords, sensitive bind values, or personal data purely to investigate deadlocks.

### 9.2. Locating Trace Files

DBAs can locate trace and diagnostic directories:

~~~sql
SELECT name, value
FROM   v$diag_info
WHERE  name IN (
    'Diag Trace',
    'Diag Alert',
    'Default Trace File'
);
~~~

Deadlock graphs are normally written to trace/alert diagnostics. Their contents identify the objects, rows/resources, and transactions participating in the cycle. Exact formatting and paths depend on ADR configuration.

### 9.3. Finding Participating Sessions

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       sql_id,
       prev_sql_id,
       event,
       blocking_instance,
       blocking_session,
       module,
       action,
       client_identifier
FROM   gv$session
WHERE  username = 'LAB_APP'
ORDER  BY inst_id, sid;
~~~

The deadlock may have already cleared before a DBA runs this query, because Oracle detects and breaks cycles quickly. In that case, trace files and application logs provide better evidence than a live session snapshot.

### 9.4. Mapping Objects and SQL

Use `DBA_OBJECTS`/`ALL_OBJECTS` to look up object IDs from the deadlock graph:

~~~sql
SELECT owner,
       object_name,
       object_type,
       object_id
FROM   dba_objects
WHERE  object_id = :object_id;
~~~

If the graph includes a `ROWID`, you can inspect the row in an appropriate environment, though do not assume every lock type maps cleanly to a single row. Read the full graph and SQL trace.

### 9.5. Deadlocks vs. Lock Timeouts

| Situation | Typical Outcome | Resolution |
| --- | --- | --- |
| One session waits on blocker | Waits until blocker ends or timeout | Identify blocker, transaction, and wait policy |
| `SELECT FOR UPDATE NOWAIT` | Immediate error if row locked | Retry or return busy per business rules |
| `SELECT FOR UPDATE WAIT n` | Error after exceeding wait time | Tune wait policy and transaction duration |
| `DML_LOCK_TIMEOUT` expires | Resource busy / lock wait timeout | Resolve blocker and apply bounded retry |
| Deadlock cycle | `ORA-00060` | Roll back full transaction, fix lock ordering |

## 10. Preventing Deadlocks in Applications

### 10.1. Lock Rows in Consistent Order

If multiple transactions must update account 1 and account 2, always lock in ascending `account_id` order:

~~~sql
SELECT account_id, balance
FROM   lab_account
WHERE  account_id IN (:id1, :id2)
ORDER  BY account_id
FOR UPDATE;
~~~

Across separate `UPDATE` statements, ensure every code path follows the same deterministic order. Never rely on arbitrary input collection order or execution plan order when lock ordering matters.

### 10.2. Keep Transactions Short

Never keep a transaction open while:
- Making HTTP/REST calls.
- Waiting on message queues.
- Waiting for user input.
- Performing slow file I/O.
- Running large uncheckpointed batches.
- Waiting on external application locks.

Perform required reads and writes, commit or roll back promptly, and run external work outside the transaction.

### 10.3. Update as a Single Business Unit

If a funds transfer debits a source account and credits a destination account, execute both inside one transaction with consistent lock ordering. Enforce invariants with constraints and validation. Never commit between the two updates if business rules require atomicity.

### 10.4. Indexes and Foreign Keys

Proper indexes shorten row lookups and prevent certain forms of contention. For foreign keys, evaluate indexing child columns when parent rows are updated or deleted; missing child indexes can force wider locking during certain parent-key operations.

Do not blindly index every foreign key. Measure workload, cardinality, DML overhead, and execution plans.

### 10.5. Pessimistic vs. Optimistic Locking

Pessimistic locking uses `SELECT FOR UPDATE` to lock before modifying. Control lock order and hold duration carefully.

Optimistic locking uses a version column to detect concurrent updates. In JPA, `@Version` catches stale writes, though it does not eliminate all deadlocks if transactions still update multiple rows in conflicting orders.

### 10.6. Retrying Properly

`ORA-00060` can be transient, provided retries:
1. Roll back the entire transaction when the business unit must be atomic.
2. Return or evict the connection per driver/pool state.
3. Sleep with short backoff and jitter.
4. Start a fresh transaction.
5. Cap maximum attempts.
6. Emit metrics to expose recurring deadlocks.

Never retry an isolated statement when earlier statements already altered transaction state. Never retry infinitely, which risks a retry storm.

### 10.7. Idempotency and Commit Outcomes

Network timeouts can occur after Oracle commits but before the application receives the acknowledgment. The client cannot know for sure whether the transaction succeeded.

Use:
- Request IDs or idempotency keys.
- Unique constraints preventing duplicate records.
- Queryable business status.
- Clear transaction boundaries.
- Reconciliation workflows when commit outcomes are uncertain.

Retrying a payment or order creation without idempotency can create duplicate transactions.

## 11. Controlled Recovery from Pool Exhaustion

### 11.1. Capture State First

Record:
- Pool active, idle, total, and waiting counts.
- Acquisition timeout counts.
- Connection creation failures.
- Leak detection logs.
- Application thread dumps if needed.
- Sessions grouped by module and service.
- `SQL_ID`, wait events, and blockers.
- Queued requests and error rates.

Never restart the application before capturing evidence; restarting erases connection ownership clues and thread stacks.

### 11.2. Shed Load and Protect the System

While the pool is exhausted:
- Throttle concurrency on offending endpoints or jobs.
- Pause deferrable batch workloads.
- Apply bounded queues/backpressure or fail fast with controlled busy errors.
- Limit client-side retries.
- Reserve capacity for health checks or admin tasks if architecture requires.
- Never scale pool size past database capacity.

The goal is stopping new traffic from lengthening queues while clearing stuck connections.

### 11.3. Locate Held Connections

Correlate:
- Hikari active connections.
- Thread dumps and leak detection stack traces.
- `GV$SESSION` filtered by username, service, module, and machine.
- Current SQL and previous SQL.
- Transaction start time and undo usage.
- Wait events and blockers.

If active connections are waiting on row locks, resolve the blocker or transaction. If sessions are idle inside the database while marked active in the pool, check whether application code is holding connections without executing SQL.

### 11.4. Return Connections Cleanly

Prefer:
- Letting valid transactions finish.
- Fixing code paths missing `close()`.
- Rolling back abandoned transactions per owner/runbook.
- Cancelling runaway statements.
- Throttling pool-hogging workloads.
- Terminating clearly identified stale sessions.

Never kill all sessions belonging to the application user just to empty the pool. That breaks every in-flight request at once, triggers a reconnect storm, and causes massive rollbacks.

### 11.5. When to Recycle the Pool or Restart the App?

Recycling a datasource or process may be necessary if pool state is corrupted or connections are unrecoverable, but only after:
- Capturing pool metrics and thread dumps.
- Identifying affected transactions and sessions.
- Assessing in-flight requests.
- Draining incoming traffic.
- Confirming database capacity for the reconnect burst.
- Verifying fresh connections succeed.

Restarting the app frees client-side handles, though Oracle may not finish rolling back large transactions instantaneously. Database cleanup may still be in progress.

### 11.6. Avoiding Reconnect Storms

After a pool recycles, all replicas may attempt to open new connections simultaneously, creating an authentication and session-creation spike.

Mitigate using:
- Staggered restarts or rolling deployments.
- Moderate `minimumIdle` settings.
- Retry backoff with jitter.
- Connection creation rate limiting where supported.
- Database session and process headroom.
- Health checks gating traffic admission.

## 12. Recovering from Timeouts

### 12.1. Identify Which Timeout Fired

Record exception class, message, and originating layer:
- Hikari acquisition timeout.
- Driver connect/login timeout.
- Socket/read timeout.
- Statement query timeout.
- Lock wait timeout.
- HTTP/request deadline.
- Transaction timeout.

Never map every timeout to `ORA-00060` or a generic connection error. Inspect nested `SQLException`s along with `SQLState` and vendor error codes.

### 12.2. Cancelling Statements and Transactions Properly

On a query timeout:
- Verify whether the statement actually cancelled.
- Verify whether the connection remains usable.
- Roll back the transaction if the business operation is incomplete.
- Close `ResultSet` and `Statement`.
- Return the connection to the pool per API.
- Discard the connection if the driver flags it broken.

When an HTTP request times out, propagate cancellation down to JDBC where appropriate. A client disconnecting does not automatically cancel Oracle SQL execution.

### 12.3. Checking Commit Outcomes

If an error happens near `COMMIT` or the network drops silently:
- Never assume the transaction rolled back.
- Look up state using the request ID or business key.
- Verify whether the data committed.
- Use idempotency to retry safely.
- Reconcile operations whose outcomes remain ambiguous.

This is especially critical for payments, orders, and operations with external side effects.

### 12.4. Repeated Timeouts Signal Overload

If timeouts spike:
- Check pool waiting counts and active DB sessions.
- Inspect CPU, I/O, storage, and wait classes.
- Inspect SQL plans and bind values.
- Inspect lock chains.
- Inspect network and listener health.
- Check retry amplification and request concurrency.

Raising timeouts only makes requests stall longer. Growing pools only increases concurrency. Both can worsen database load when the root cause is resource saturation.

## 13. Deadlock Recovery Runbook

### 13.1. Preserve Evidence

Collect:
- `ORA-00060` stack trace.
- Deadlock graph and trace file.
- `SQL_ID` and SQL text per access policy.
- Module, action, and client identifier.
- Transaction boundaries and request ID.
- Objects, rows, and resources listed in the graph.
- Application retry logs.
- Timestamp and frequency of deadlocks.

### 13.2. Handle the Failed Transaction

Applications should roll back along the business transaction boundary. In raw JDBC:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        performBusinessOperation(connection);
        connection.commit();
    } catch (SQLException e) {
        connection.rollback();
        throw e;
    }
}
~~~

This simple example illustrates rollback on failure. With Spring `@Transactional`, let the transaction manager control commit/rollback; verify rollback rules, especially if exceptions are caught and not rethrown.

### 13.3. Bounded Retries

Pseudocode example:

~~~java
int maxAttempts = 3;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        executeWholeTransaction();
        break;
    } catch (SQLException e) {
        rollbackCurrentTransaction();

        if (!isOracleDeadlock(e) || attempt == maxAttempts) {
            throw e;
        }

        sleepWithExponentialBackoffAndJitter(attempt);
    }
}
~~~

`isOracleDeadlock` must check for vendor error code `60` across the `SQLException` chain, not merely match message strings. Each retry must start a fresh transaction and the operation must be safe to re-execute.

### 13.4. Fix Root Causes

From the deadlock graph:
- List involved objects and lock acquisition order.
- Locate code paths acquiring locks in opposite orders.
- Standardize lock ordering.
- Shorten transaction duration.
- Add indexes when supported by evidence.
- Split large batches.
- Evaluate `SELECT FOR UPDATE WAIT`/`NOWAIT`.
- Add idempotency and bounded retries.

Never kill sessions to fix a deadlock after Oracle has already raised `ORA-00060`; the cycle is already broken. Handle the affected transaction state and fix the underlying lock-order conflict.

## 14. Diagnostic Queries During Incidents

### 14.1. Sessions by Service and Module

~~~sql
SELECT inst_id,
       service_name,
       module,
       action,
       status,
       COUNT(*) AS sessions
FROM   gv$session
WHERE  type = 'USER'
GROUP  BY inst_id, service_name, module, action, status
ORDER  BY sessions DESC;
~~~

### 14.2. Waiting Sessions

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       seconds_in_wait,
       state,
       blocking_instance,
       blocking_session,
       module,
       action
FROM   gv$session
WHERE  state = 'WAITING'
  AND  wait_class <> 'Idle'
ORDER  BY seconds_in_wait DESC;
~~~

### 14.3. Long-Running Transactions

~~~sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.module,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM   gv$transaction t
JOIN   gv$session s
       ON s.inst_id = t.inst_id
      AND s.taddr = t.addr
ORDER  BY t.start_time;
~~~

### 14.4. Resource Limits

~~~sql
SELECT inst_id,
       resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM   gv$resource_limit
WHERE  resource_name IN ('sessions', 'processes')
ORDER  BY inst_id, resource_name;
~~~

Compare `current_utilization` and `max_utilization` with `limit_value`. Historical peaks can show workload bursts, though they do not by themselves identify application pool exhaustion.

### 14.5. Lock Waiters and Blockers

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       event,
       blocking_instance,
       blocking_session,
       final_blocking_instance,
       final_blocking_session,
       sql_id,
       module
FROM   gv$session
WHERE  blocking_session IS NOT NULL
   OR  final_blocking_session IS NOT NULL
ORDER  BY inst_id, sid;
~~~

### 14.6. Alert Log and Diagnostic Traces

~~~sql
SELECT name, value
FROM   v$diag_info
WHERE  name IN (
    'Diag Trace',
    'Diag Alert',
    'Default Trace File'
);
~~~

Use `ADRCI` or authorized monitoring tools to read deadlock traces and alert logs. Never delete trace or alert files to clear errors before saving evidence.

## 15. Post-Recovery Health Checks

### 15.1. Pool Metrics

After remediation:
- Active connections drop back to baseline.
- Idle connections repopulate per policy.
- Waiting threads drop to 0.
- Acquisition timeouts stop climbing.
- Connection creation failures stop repeating.
- Leak warnings cease recurring.

Monitor long enough to span a normal workload cycle, not just a single successful request.

### 15.2. Database Sessions

Verify:
- Session counts stabilize.
- No unexpected blockers remain.
- Old transactions have committed or rolled back.
- No lingering `KILLED` sessions persist abnormally.
- Services, PDBs, and instances are healthy.
- Resource limits maintain safe headroom.

### 15.3. Application Health

Verify:
- Request success rate.
- p95/p99 latency.
- HTTP 5xx and database exception rates.
- Queue depth.
- Retry counts.
- Thread pool saturation.
- Connection pool pending count.
- Business data consistency.

An endpoint returning HTTP 200 is not enough to prove business data integrity after timeouts or deadlocks.

### 15.4. Reconciling Lab Data

After completing the scenarios, check:

~~~sql
SELECT account_id, balance, note
FROM   lab_account
ORDER  BY account_id;

SELECT status, COUNT(*) AS row_count
FROM   lab_work
GROUP  BY status
ORDER  BY status;
~~~

Reset lab data back to its initial state if required by the exercise and commit intentionally.

## 16. Designing Timeouts and Pools for Production

### 16.1. One End-to-End Deadline

Establish an API request deadline and budget portions for:
- Pool acquisition.
- New connection establishment if needed.
- SQL execution.
- Fetch and serialization.
- Commit and cleanup.
- Response transmission.

Lower-layer timeouts should fit inside upper-layer deadlines so the application still has time to cancel, roll back, and return controlled errors.

### 16.2. Pool Sizing and Database Capacity

Sum pool sizes across all replicas, workers, schedulers, and clients. Reserve headroom for:
- DBA and admin tasks.
- Monitoring.
- Critical batch jobs.
- Failover when a RAC instance goes down.
- Rolling deployments that temporarily spike replica counts.
- Background and maintenance sessions.

If RAC services use preferred/available instances, evaluate worst-case connection distribution when an instance is unavailable.

### 16.3. Backpressure Instead of Infinite Pool Growth

When pools saturate:
- Cap concurrency per endpoint.
- Use bounded queues.
- Reject requests early that cannot finish within their deadline.
- Apply circuit breakers to slow dependencies.
- Never hold JDBC connections while waiting on external services.
- Bound retries.

Bigger pools do not guarantee higher throughput; they can increase contention for CPU, latches, buffers, and locks.

### 16.4. Metrics and Alerts

Track:
- Hikari active, idle, total, and pending counts.
- Acquisition timeouts.
- Connection creation and validation failures.
- Connection hold durations.
- Transaction durations.
- Oracle session counts by service and module.
- Wait events and blocking sessions.
- `ORA-00060` rate.
- SQL latency and DB time.
- Database process and session utilization.
- Application request latency and error rate.

Alert when pending/active connections climb steadily, acquisition timeouts appear, or deadlock rates exceed baseline—do not wait until the pool is completely exhausted.

## 17. Common Misconceptions

**"Pool exhaustion means Oracle ran out of sessions."** No. A pool can run out of connections while the database still has plenty of capacity.

**"Increasing `maximumPoolSize` always fixes pool exhaustion."** No. If connections are leaked, blocked on locks, or running slow SQL, a larger pool only delays failure and increases database load.

**"Hikari `connectionTimeout` is Oracle's connect timeout."** No. It limits how long threads wait to borrow from the pool; driver and Oracle Net timeouts are separate.

**"An HTTP timeout automatically cancels SQL."** No. Applications must propagate cancellation down to JDBC and clean up transaction state.

**"Statement query timeout always rolls back the whole transaction."** No. Verify driver, statement, and transaction behavior; roll back the business transaction explicitly when needed.

**"Inactive sessions never hold locks."** No. An `INACTIVE` session can still own an uncommitted transaction holding locks.

**"A deadlock is a session waiting too long."** No. A deadlock is a mutual wait cycle; single-direction blocking is not a deadlock.

**"`ORA-00060` rolls back the entire transaction."** No. Oracle rolls back the offending statement; remaining transaction state must be handled by the application along business boundaries.

**"Seeing `ORA-00060` means you must kill both sessions."** No. Oracle already broke the cycle. Roll back the affected transaction and fix lock ordering.

**"Retrying the failed statement alone is enough."** No. For atomic transactions, roll back and retry the entire unit in a fresh transaction.

**"Leak detection proves there is a code leak."** No. Valid long-running transactions can also trigger leak warnings; inspect stack traces and lifecycles.

**"Restarting the database solves all pool problems."** Restarts sever sessions, but do not fix connection leaks, retry storms, slow SQL, or poor transaction boundaries.

## 18. Integrated Practice Exercises

Execute these sequentially on a dedicated lab schema and lab application. Record inputs, before/during/after metrics, and expected outcomes.

### Exercise 1 — Pool Baseline

Configure a pool size of 5. Run a light workload and record active/idle/total/waiting counts alongside Oracle session counts.

### Exercise 2 — Pool Exhaustion

Run the Lab A Java program with 8 workers, pool size 3, and a short `connectionTimeout`. Capture timeout logs and MXBean snapshots.

### Exercise 3 — Connection Leak

Create a lab code path that intentionally omits closing a connection. Observe rising active counts and leak warnings. Fix with `try-with-resources` and retest.

### Exercise 4 — Long Transaction

Start a transaction updating a row and hold it uncommitted. Observe `INACTIVE`/`ACTIVE` session status, open transactions, and locks.

### Exercise 5 — Lock Timeout

Session A holds a row lock. Session B sets `DML_LOCK_TIMEOUT = 5` or uses `SELECT FOR UPDATE WAIT 5`. Record the error code and elapsed wait time.

### Exercise 6 — NOWAIT

Run `SELECT FOR UPDATE NOWAIT` against a locked row. Observe the immediate error and compare with `WAIT`.

### Exercise 7 — Deadlock

Execute the Session A/B sequence from Lab D to trigger `ORA-00060`. Collect the trace/deadlock graph if authorized.

### Exercise 8 — Transaction Rollback

After a deadlock, inspect changes made before the deadlocked statement. Roll back the full transaction and verify the data.

### Exercise 9 — Bounded Retry

Implement a retry loop capped at 3 attempts for an idempotent transaction. Add backoff/jitter and metrics; confirm retries are bounded.

### Exercise 10 — Statement Timeout

Use `PreparedStatement.setQueryTimeout` in the lab environment. Verify statement cancellation, connection usability, and transaction state.

### Exercise 11 — Pool After Timeouts

Force several connections to time out in a controlled test. Verify the pool evicts unusable connections and creates replacements.

### Exercise 12 — Recovery Runbook

Simulate rising pool wait queues, identify the offending session SQL/lock, shed load, release the transaction cleanly, and verify metric recovery.

### Exercise 13 — Multi-Replica Pool Budget

Calculate total `maximumPoolSize` for 6 replicas, 2 worker pools, and admin headroom. Compare against the test database's `sessions`/`processes` capacity.

### Exercise 14 — Incident Report

Write a report covering:
- Symptoms and timeline.
- Blast radius.
- Pool and database evidence.
- Root cause.
- Recovery actions.
- Transaction and data validation.
- Post-recovery metrics.
- Preventive changes.

## 19. Incident Runbook Template

### Initial State

- Incident ID:
- Timestamp:
- Database / DB unique name:
- Role / instance / service / PDB:
- Application version / replica count:
- Pool maximum / active / idle / waiting:
- Oracle sessions / processes:
- Error rate / p95 / p99:
- `SQL_ID` / wait event / blocker:
- Transaction start / undo:
- Alert/trace location:

### Incident Classification

- [ ] Pool acquisition timeout.
- [ ] Physical connection creation timeout.
- [ ] Network/read timeout.
- [ ] Statement/query timeout.
- [ ] Lock wait timeout.
- [ ] `ORA-00060` deadlock.
- [ ] Database session/process capacity.
- [ ] Connection leak or long-held connection.
- [ ] Other.

### Chosen Actions

- Action:
- Scope:
- Rationale and evidence:
- Approver / incident commander:
- Start time:
- Stop criteria:
- Rollback / forward-fix:

### Post-Recovery Verification

- Pool active/idle/waiting:
- Connection acquisition timeouts:
- Oracle sessions/transactions:
- Blocking/deadlocks:
- Application error rate:
- p95/p99 latency:
- Business data reconciliation:
- Preventive follow-ups:
- Verifier and timestamp:

## 20. References

- [Oracle Database 19c Concepts — Transactions and Data Concurrency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transactions, locks, and concurrency.
- [Oracle Database 19c Administrator's Guide — Managing Processes](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-processes.html): sessions, processes, and resource management.
- [Oracle Database 19c Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): session states, wait events, and blockers.
- [Oracle Database 19c Database Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html): enqueue locks.
- [Oracle Database 19c Database Reference — V$TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSACTION.html): active transactions and undo usage.
- [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `SELECT FOR UPDATE`, `WAIT`, and `NOWAIT`.
- [Oracle Database 19c SQL Language Reference — ALTER SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-SESSION.html): session parameters such as `DML_LOCK_TIMEOUT`.
- [Oracle Database JDBC Developer's Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): JDBC connections, timeouts, and statement behavior.
- [HikariCP Documentation](https://github.com/brettwooldridge/HikariCP): pool configuration, metrics, leak detection, and lifecycle.
- [JDBC API — Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): transactions, closing, and network timeouts.
- [JDBC API — Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html): query timeouts and cancellation.

Pool exhaustion, timeouts, and deadlocks can all cause requests to stall or fail, so they must be diagnosed at the proper layer. Pool exhaustion requires inspecting active/idle/waiting counts and connection hold times; timeouts require distinguishing pool, connect, network, lock, and statement layers; deadlocks require reading `ORA-00060`/deadlock graphs and handling transactions along business boundaries. **Safe recovery starts by preserving evidence, shedding admission, locating blocking sessions or transactions, releasing resources within the right scope, and verifying both the pool and business data once stability returns.**
