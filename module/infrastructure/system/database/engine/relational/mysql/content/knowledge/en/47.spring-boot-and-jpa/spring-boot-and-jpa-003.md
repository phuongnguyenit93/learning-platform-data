# maxLifetime, keepalive, wait_timeout, and Connection Lifecycle

In a Spring Boot application using JPA with MySQL, a request typically does not open a new TCP connection for every SQL statement. Instead, the application borrows a connection from a connection pool, executes a transaction or query, and returns the connection to the pool for another request to reuse. This reduces connection setup overhead, while creating a connection lifecycle controlled simultaneously by HikariCP, MySQL Server, the JDBC driver, and intermediate network components.

Three frequently confused settings are **HikariCP maxLifetime**, **HikariCP keepaliveTime**, and **MySQL wait_timeout**. They measure different durations and act on different connection states. Misconfiguration can cause errors such as "Communications link failure", "MySQL server has gone away", failures when borrowing a connection, or unexpected transaction rollbacks.

This lesson explains the connection lifecycle in Spring Boot/JPA, how these timers interact, how to pick safe values, and how to investigate when connections are closed by MySQL or network infrastructure.

Within **DATABASE_MYSQL**, application connectivity is the bridge to all MySQL fundamentals: table design, data types, keys, SQL queries, indexes, transactions, and concurrency control. Operating a pool also requires reading execution plans, query tuning, access control, backups, and relational database troubleshooting. The **Spring Boot and JPA** chapter places those principles into the Java application connection lifecycle.

## 1. Connection Lifecycle Model

### 1.1. Participating Components

A JDBC connection to MySQL typically traverses several layers:

~~~mermaid
flowchart LR
    REQ[HTTP request / Job] --> TX[Spring Transaction / JPA]
    TX --> POOL[HikariCP connection pool]
    POOL --> JDBC[MySQL Connector/J]
    JDBC --> NET[TCP / Proxy / Firewall]
    NET --> DB[MySQL session]
~~~

- **Spring Transaction / JPA:** determines transaction scope and when a connection is needed.
- **HikariCP:** creates, manages, validates, lends, and retires physical connections.
- **MySQL Connector/J:** implements JDBC, sends statements, and receives results from the server.
- **TCP, proxy, firewall, or load balancer:** may close connections due to idle timeouts or their own connection age limits.
- **MySQL Server:** maintains sessions and enforces limits such as **wait_timeout**.

The connection that code receives from **DataSource.getConnection()** is typically a wrapper managed by HikariCP. Calling **close()** on the wrapper normally returns the connection to the pool; it does not necessarily close the underlying physical TCP connection immediately.

### 1.2. Primary States

A physical connection typically moves through these states:

1. **Created:** HikariCP opens a connection through Connector/J and MySQL creates a session.
2. **Borrowed (active/borrowed):** a request or transaction is actively using the connection.
3. **Returned to pool:** the application calls **close()** after finishing work.
4. **Idle in pool:** the connection is not currently borrowed by another request.
5. **Keepalive check:** HikariCP temporarily checks out an idle connection from the pool, verifies liveness, and returns it.
6. **Retired:** HikariCP removes a connection that reached its maximum lifetime or is no longer needed.
7. **Closed by server/infrastructure:** MySQL or a network element closes the socket; the pool must detect and evict the broken connection.

Simplified state diagram:

~~~mermaid
stateDiagram-v2
    [*] --> Creating
    Creating --> Borrowed: Connection succeeds
    Borrowed --> Idle: close() returns to pool
    Idle --> Borrowed: Request borrows
    Idle --> Keepalive: Scheduled check due
    Keepalive --> Idle: Ping succeeds
    Keepalive --> Retired: Ping fails
    Idle --> Retired: maxLifetime / idleTimeout
    Borrowed --> Retired: Returned after maxLifetime elapsed
    Retired --> [*]
~~~

Key takeaway: a borrowed connection is not an idle connection in the pool. **keepaliveTime** primarily checks idle connections; **maxLifetime** does not forcibly sever a connection actively in use by the application.

## 2. Three Timers to Distinguish

| Setting | Component | Unit | What It Measures | Primary Effect |
|---|---|---:|---|---|
| **maxLifetime** | HikariCP | Milliseconds | Maximum age of a physical connection since creation | Marks connection for removal from the pool upon expiration |
| **keepaliveTime** | HikariCP | Milliseconds | Interval between liveness checks on idle connections | Pings idle connections to detect or prevent idle-timeout closure |
| **wait_timeout** | MySQL Server | Seconds | Time the server waits for activity on a non-interactive session before closing it | Closes sessions that have been idle too long |
| **idleTimeout** | HikariCP | Milliseconds | Time an excess connection sits idle in the pool | Evicts excess idle connections when the pool can shrink |
| **connectionTimeout** | HikariCP | Milliseconds | Time a request waits to borrow a connection from the pool | Throws an error if a connection cannot be borrowed in time |

Never compare values directly without converting units first. For example, **wait_timeout=1800** is 1,800 seconds (30 minutes); **maxLifetime=1500000** is 1,500,000 milliseconds (25 minutes).

## 3. MySQL wait_timeout

### 3.1. Meaning of wait_timeout

**wait_timeout** is the number of seconds MySQL waits for activity on a non-interactive connection before closing the session. Standard JDBC connections are non-interactive connections, so the session **wait_timeout** is usually initialized from the global **wait_timeout** when the connection is established.

MySQL's default is often 28,800 seconds (8 hours), but actual settings can be much lower as configured by administrators, managed database services, or infrastructure policies. Always inspect the running value rather than relying on defaults.

**wait_timeout** is an **idle time** limit, not a total connection age limit:

- A query currently executing on MySQL is not an idle waiting session.
- Once the statement completes and the session sends no further commands, the idle timer begins counting.
- A connection returned to the pool and sitting idle can be closed once it exceeds **wait_timeout**.
- A transaction holding a connection without sending statements for a long period also leaves the session in Sleep state; the server may close that session, rolling back the uncommitted transaction.

That last point is especially important with JPA: do not keep a transaction open while waiting on users, calling external APIs, or executing long non-database tasks.

### 3.2. wait_timeout vs. interactive_timeout

MySQL has two related variables:

- **wait_timeout:** used for non-interactive sessions.
- **interactive_timeout:** used to initialize the timeout for sessions connected with the interactive client flag.

When a new session starts, MySQL initializes the session **wait_timeout** based on the client type. JDBC normally does not set the interactive flag, so Spring Boot applications should pay attention to **wait_timeout**.

Check global and session values:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW SESSION VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'interactive_timeout';

SELECT
  CONNECTION_ID() AS connection_id,
  @@GLOBAL.wait_timeout AS global_wait_timeout,
  @@SESSION.wait_timeout AS session_wait_timeout;
~~~

Global and session values can differ. The current session retains its own value initialized at connection time or changed directly within the session.

### 3.3. Changing wait_timeout

Change global setting:

~~~sql
SET GLOBAL wait_timeout = 1800;
~~~

This applies to new sessions created afterward; existing sessions in HikariCP do not automatically pick up the new value.

Change current session:

~~~sql
SET SESSION wait_timeout = 1800;
~~~

This command affects only the session executing it. If you need to set a session value for every new physical connection created by HikariCP, you can use **connectionInitSql** when there is a clear operational reason. The initialization SQL runs only when creating a physical connection, not every time a request borrows a connection.

Do not lower **wait_timeout** to a few seconds to "clean up connections" without evaluating pools and workloads. An overly low value can close connections while the application holds a transaction or borrows an idle connection, causing hard-to-reproduce failures.

## 4. HikariCP maxLifetime

### 4.1. Maximum Age of a Physical Connection

**maxLifetime** is the maximum lifetime HikariCP allows a physical connection to remain in the pool, measured from when the connection was created. Upon expiration, the pool marks the connection for retirement and replaces it with a new connection as needed.

Key characteristics:

- Measured in milliseconds.
- Limits total connection age, not idle duration.
- A connection currently borrowed will not be forcibly closed by HikariCP solely because it exceeded **maxLifetime**.
- When an expired connection is returned to the pool, HikariCP retires it instead of reusing it.
- Should be set lower than any hard connection age limit imposed by a database proxy, cloud service, or network infrastructure, with a safe margin.

For example, if a proxy imposes a 60-minute physical connection lifetime limit, set **maxLifetime** lower than that limit, such as 55 minutes. Exact values should be based on service policy and empirical testing.

### 4.2. maxLifetime Is Not the Same as wait_timeout

**maxLifetime** and **wait_timeout** do not replace each other:

- **maxLifetime** counts connection age from creation, even when the connection is actively used.
- **wait_timeout** counts how long a session has had no activity.
- A connection can live for many hours if kept continuously active and not capped by infrastructure age limits.
- A connection created only minutes ago can still be closed by MySQL if it sits idle beyond **wait_timeout**.
- HikariCP does not close a borrowed connection the moment **maxLifetime** expires.

You can set **maxLifetime** lower than **wait_timeout** as a conservative policy so the pool regularly cycles connections before the server's idle threshold. Semantically, however, **wait_timeout** is an idle timeout; if **keepaliveTime** already keeps idle connections alive in the pool and there is no other hard age limit, **maxLifetime** does not strictly have to be smaller than **wait_timeout**.

### 4.3. Choosing maxLifetime

Before choosing a value, identify connection age limits across every infrastructure layer: MySQL managed service, proxy, load balancer, firewall, NAT, and service mesh if present.

Examples:

- Database or proxy closes all connections after 60 minutes regardless of activity: set **maxLifetime** shorter than 60 minutes.
- Infrastructure closes connections only after 10 minutes idle: examine **keepaliveTime** and connection state; **maxLifetime** addresses total age, not directly keepalive.
- No known hard age limit: HikariCP's default can serve as a starting point, then evaluate based on version and observed behavior.

Never set **maxLifetime** equal to the exact limit of the proxy or database. Closure timing may not be exact; leave a safety margin so the pool proactively retires connections first.

## 5. HikariCP keepaliveTime

### 5.1. What Does Keepalive Do?

**keepaliveTime** specifies the interval between liveness checks on an idle connection in the pool. When scheduled, HikariCP temporarily takes the connection out of the pool, sends a liveness check via JDBC, and returns it if healthy.

Keepalive is useful when:

- MySQL **wait_timeout** is short.
- A firewall, NAT, or load balancer closes idle TCP connections.
- A database proxy enforces an idle timeout.
- The application keeps idle connections in the pool ready for incoming requests.

HikariCP can use JDBC **Connection.isValid()** to check liveness. With JDBC4-compliant drivers, configuring **connectionTestQuery** manually is usually unnecessary.

### 5.2. Keepalive Applies Only to Idle Connections in the Pool

Keepalive does not ping connections currently borrowed by the application. Consequently:

- Idle connections in the pool can be checked periodically.
- Borrowed connections actively running queries do not need keepalive.
- Borrowed connections left idle inside an open transaction can still be closed by MySQL or a proxy.
- Keepalive cannot rescue a connection already severed by the network while in use.

If an application holds a connection in a transaction while waiting 20 minutes on an external API, setting **keepaliveTime=2 minutes** does not mean HikariCP will ping that connection during those 20 minutes. The proper fix is shortening transactions and not holding connections when database access is not needed.

### 5.3. Choosing keepaliveTime

**keepaliveTime** must be smaller than **maxLifetime**. In current HikariCP versions, values below the library's minimum threshold are rejected/ignored; check the documentation for your specific version.

To prevent the server or network from closing connections before a ping occurs, set keepalive lower than the **smallest idle timeout** along the entire path, with a substantial margin.

Example:

- MySQL **wait_timeout** is 30 minutes.
- A proxy closes idle TCP connections after 10 minutes.
- HikariCP needs to ping before the 10-minute mark; you might start testing with **keepaliveTime=5 minutes**.
- If the pool does not need to keep idle connections warm, you can lower **minimumIdle** or let the pool shrink via **idleTimeout** instead of pinging excessive connections.

Never set keepalive equal to the proxy timeout. Scheduler jitter, system load, and network latency can delay pings.

## 6. idleTimeout, connectionTimeout, and Related Timeouts

### 6.1. idleTimeout

**idleTimeout** is the duration an excess connection can sit idle in the pool before HikariCP removes it. It allows the pool to shrink when demand drops.

**idleTimeout** only shrinks the pool when **minimumIdle** is smaller than **maximumPoolSize**. If the pool is configured as fixed-size with **minimumIdle** equal to **maximumPoolSize**, HikariCP maintains that count and **idleTimeout** does not shrink the pool.

Do not confuse **idleTimeout** with MySQL **wait_timeout**:

- **idleTimeout:** the pool decides whether to close its own excess idle connections.
- **wait_timeout:** MySQL decides to close inactive sessions.
- **keepaliveTime:** the pool checks idle connections to detect or prevent closure by external layers.

### 6.2. connectionTimeout

**connectionTimeout** is the maximum time a thread waits to borrow a connection from the pool. It is not:

- How long MySQL allows a session to remain idle.
- The maximum execution time for a SQL statement.
- TCP connect timeout.
- Socket read timeout.

If the pool has no free connections and all are borrowed, new requests wait up to **connectionTimeout** and then receive an exception from HikariCP.

Other timeouts may live in the JDBC URL or transaction configuration:

| Timeout | Component | Purpose |
|---|---|---|
| Hikari **connectionTimeout** | HikariCP | Waiting to borrow a connection |
| Connector/J **connectTimeout** | JDBC driver | Waiting to establish the TCP socket |
| Connector/J **socketTimeout** | JDBC driver | Limiting wait time reading data from the socket |
| Hikari **validationTimeout** | HikariCP | Limiting connection validation duration |
| Hikari **idleTimeout** | HikariCP | Reclaiming excess idle connections |
| Hikari **maxLifetime** | HikariCP | Limiting total connection age |
| MySQL **wait_timeout** | MySQL Server | Closing idle non-interactive sessions |
| Query/transaction timeout | JDBC/Spring/database | Limiting query execution or transaction duration via respective mechanisms |

Setting a low **connectionTimeout** does not make slow queries run faster. If the pool runs dry, investigate connection hold duration, slow queries, long transactions, and pool size.

## 7. Configuring Spring Boot with HikariCP

### 7.1. application.yml Example

Suppose a system has the following limits:

- MySQL **wait_timeout** is configured at 1,800 seconds (30 minutes).
- A network proxy closes idle connections after 10 minutes.
- The system wants to proactively cycle connections after roughly 25 minutes.
- The pool keeps a minimum of 5 connections and a maximum of 20 connections per application instance.

A starting configuration for testing:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://mysql.internal:3306/appdb?sslMode=VERIFY_IDENTITY&serverTimezone=UTC
    username: app_user
    password: ${DB_PASSWORD}
    hikari:
      pool-name: app-mysql-pool
      maximum-pool-size: 20
      minimum-idle: 5
      max-lifetime: 1500000
      keepalive-time: 300000
      idle-timeout: 600000
      connection-timeout: 30000
      validation-timeout: 5000
~~~

Explanation:

- **max-lifetime: 1500000** is 25 minutes.
- **keepalive-time: 300000** is 5 minutes, below the 10-minute proxy idle timeout and 30-minute MySQL wait timeout.
- **idle-timeout: 600000** is 10 minutes; the pool can reclaim excess idle connections as long as **minimum-idle** is less than **maximum-pool-size**.
- **connection-timeout: 30000** lets requests wait up to 30 seconds to borrow a connection.
- **validation-timeout: 5000** bounds connection validation time.

This example reflects specific assumptions, not a one-size-fits-all set of values for every environment. Verify the actual limits of your managed database service, proxy, firewall, and the HikariCP version resolved by Spring Boot.

Do not commit real passwords into YAML. Use secrets or environment variables. If the application manually defines multiple **DataSource** beans, ensure Hikari settings are bound to the proper pool rather than only configuring **spring.datasource.hikari** for a default datasource.

### 7.2. Verifying Effective Configuration

After startup, inspect HikariCP initialization logs and effective pool configuration. Do not assume a property took effect just because it appears in YAML; profiles, environment variables, external configuration, or custom beans can override it.

If global **wait_timeout** changes, previously created physical connections retain their old session value. The pool needs to gradually replace old connections or be drained/recycled in a controlled manner so new connections receive the updated session setting.

### 7.3. Do Not Configure connectionTestQuery Mechanically

HikariCP prefers JDBC4 **Connection.isValid()** when supported by the driver. With modern MySQL Connector/J, you normally do not need to set:

~~~yaml
spring:
  datasource:
    hikari:
      connection-test-query: SELECT 1
~~~

Only configure **connection-test-query** if the driver or environment does not support JDBC4 validation as required. A custom test query alone does not fix timeouts or transactions holding connections too long.

## 8. Calculating Relationships Between Timeouts

### 8.1. Find the Shortest Timeout Along the Connection Path

A connection can be closed by multiple components. Check:

- MySQL **wait_timeout** for idle sessions.
- Idle timeouts of proxies or load balancers.
- TCP idle timeouts of firewalls/NAT.
- Hard connection age limits of database services or proxies.
- Connection recycling policies of the connection pool.

Set **keepaliveTime** lower than the smallest idle timeout that keepalive can address, with margin. Set **maxLifetime** lower than any hard connection age limit. For MySQL **wait_timeout**, remember it is an idle timeout, not a total age limit.

### 8.2. Unit Conversion Example

| Value | Original Unit | Converted |
|---|---:|---:|
| MySQL **wait_timeout=1800** | 1,800 seconds | 30 minutes |
| Proxy idle timeout | 600 seconds | 10 minutes |
| Hikari **keepaliveTime=300000** | 300,000 ms | 5 minutes |
| Hikari **maxLifetime=1500000** | 1,500,000 ms | 25 minutes |
| Hikari **idleTimeout=600000** | 600,000 ms | 10 minutes |

In this example, a 5-minute keepalive pings idle connections in the pool before the proxy closes them at minute 10. A 25-minute **maxLifetime** proactively rotates connections by age. If a connection is borrowed, neither keepalive nor maxLifetime expiration guarantees immediate closure at that instant; MySQL or the network can still close an idle borrowed session under their own rules.

### 8.3. Pool Size Also Affects Lifecycle

An oversized pool increases MySQL session counts and may hold unnecessary idle connections. An undersized pool forces requests to wait for connections even when the database has spare capacity.

Calculate maximum total connections across all application instances:

**Total application connections = instance count × maximumPoolSize per instance**

Add workers, batch jobs, migration tools, monitoring, and admin connections. This sum must stay below **max_connections** with headroom for failovers, rolling deployments, and operational tasks.

For example, 4 instances with **maximumPoolSize=20** can open up to 80 connections. If a rolling deployment temporarily runs both old and new groups simultaneously, connections can nearly double. Do not calculate only for steady-state pod counts.

## 9. How Long Can Spring Transactions and JPA Hold a Connection?

### 9.1. Transactions Govern Connection Hold Duration

In a typical flow:

1. Spring begins a transaction.
2. JPA/Hibernate needs database access and borrows a connection from the DataSource.
3. SQL statements are sent via Connector/J.
4. Spring commits or rolls back the transaction.
5. The connection is returned to the pool.

The exact moment a connection is acquired can depend on Hibernate configuration, the transaction manager, and lazy connection handling. Nevertheless, long transactions typically hold connections longer and reduce availability for other requests.

### 9.2. Do Not Hold a Transaction While Calling External Services

Bad example:

~~~java
@Transactional
public void checkout(Long orderId) {
    Order order = orderRepository.findById(orderId).orElseThrow();

    paymentClient.charge(order); // External network call while transaction is open

    order.markPaid();
}
~~~

The payment call may take several seconds or time out. Throughout that time, the transaction can hold a connection, locks, and database resources. If no SQL activity occurs longer than **wait_timeout**, MySQL may close the session.

A better design keeps transactions short around database operations, calls external services outside the transaction, and uses outbox/saga patterns or intermediate states when business consistency is required. Design details depend on payment processing requirements; simply moving an annotation is not enough.

### 9.3. maxLifetime Is Not a Transaction Timeout

If a request holds a connection for 40 minutes and **maxLifetime** is 25 minutes, HikariCP does not forcibly sever that connection at minute 25. The connection is retired upon return to the pool. However, MySQL **wait_timeout** or a proxy may still close the session while the application holds the connection without sending commands.

Use transaction timeouts, query timeouts, and business processing limits according to your requirements. Never use **maxLifetime** as a substitute for a transaction timeout.

## 10. Diagnosing Connection Errors

### 10.1. Inspecting MySQL

Run on a new session and check existing sessions:

~~~sql
SELECT
  CONNECTION_ID(),
  @@GLOBAL.wait_timeout,
  @@SESSION.wait_timeout,
  @@SESSION.interactive_timeout;

SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Aborted_clients';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';

SHOW PROCESSLIST;
~~~

- **Threads_connected** shows the current number of connections.
- Increasing **Aborted_clients** may indicate improper client disconnects or abnormal connection closures; correlate with logs.
- **Aborted_connects** reflects failed connection attempts.
- **SHOW PROCESSLIST** helps identify sleeping sessions, long-running queries, or abnormal states.

Counters are cumulative since server startup or status reset; analyze trends over time rather than drawing conclusions from a single reading.

### 10.2. Inspecting HikariCP

Monitor pool metrics if the application has Actuator/Micrometer:

- **hikaricp.connections.active:** currently borrowed connections.
- **hikaricp.connections.idle:** connections idle in the pool.
- **hikaricp.connections.pending:** threads waiting for a connection.
- **hikaricp.connections.max** and **min:** pool bounds.
- **hikaricp.connections.timeout:** number of connection acquisition timeouts.

If **active** frequently hits **max** and **pending** climbs, investigate slow queries, long transactions, leaks, or an undersized pool. Increasing **maximumPoolSize** will not automatically help if MySQL is near its connection limit or CPU/I/O is saturated.

Only expose Actuator metrics endpoints to authorized people or systems. Metrics and logs can reveal pool names, system topology, or operational details.

### 10.3. Common Symptoms and Causes

| Symptom | Possible Cause | Where to Investigate |
|---|---|---|
| Errors occur after a fairly consistent idle period | **wait_timeout** or proxy idle timeout | Compare session timeout with error interval; check proxy logs |
| Errors when a request borrows a connection from the pool | Idle connection in the pool was closed by the server | Check keepalive, pool validation, and MySQL error log |
| Errors during a long-running transaction | Borrowed connection closed by server/proxy due to idle or another timeout | Check duration with no SQL sent, transaction, and proxy |
| Hikari reports connection acquisition timeout | Pool exhausted, connections held too long, or new connection creation failing | Check active/idle/pending, slow queries, and connection logs |
| **Too many connections** | Total pools across multiple instances exceed server capacity | Sum maximumPoolSize across fleet and check **max_connections** |
| Errors appear only after deploy or global timeout change | Old pool still holds physical connections with old session values | Check **@@SESSION.wait_timeout**, perform controlled pool recycle |
| Errors occur during a long query | Socket timeout, proxy query timeout, server restart, or network interruption | Cross-check Connector/J, proxy, and MySQL error logs |

Do not attribute every "MySQL server has gone away" error to **wait_timeout**. Causes can also include server restarts, oversized packets, network resets, proxy timeouts, socket timeouts, or resource exhaustion.

## 11. Procedure When Connections Close Unexpectedly

1. Record the timestamp, request ID, thread, connection pool name, and root exception.
2. Identify whether the failure occurred while borrowing a connection, executing SQL, committing, or returning the connection.
3. Check **@@SESSION.wait_timeout** on the corresponding session if still accessible.
4. Correlate the failure timestamp with the MySQL error log, proxy/firewall logs, and restart/failover events.
5. Inspect Hikari active/idle/pending metrics and connection creation/validation errors.
6. Verify whether a transaction was held open while waiting on I/O or business logic.
7. Identify the smallest idle timeout and hard lifetime at each infrastructure layer.
8. Adjust **keepaliveTime**, **maxLifetime**, **idleTimeout**, or transaction boundaries based on the root cause.
9. Test in staging with timeouts closely matching production.
10. Monitor metrics and error rates after deployment.

If a transaction loses its connection before commit, the application must treat the transaction outcome as failed or indeterminate depending on when the error occurred. Do not blindly retry every write statement: a client may lose the connection after the server committed but before receiving the response. Use idempotency keys or business-state lookups for safe retries.

## 12. Configuration and Operations Checklist

### Before Setting Timeouts

- [ ] Identify the exact HikariCP version resolved by Spring Boot.
- [ ] Read both global and session **wait_timeout**.
- [ ] Check idle timeouts on proxies, firewalls, NAT, and load balancers.
- [ ] Determine hard connection lifetimes if enforced by your service.
- [ ] Convert all values to the same unit before comparing.

### When Configuring HikariCP

- [ ] Set **keepaliveTime** smaller than the smallest idle timeout the pool must survive, with margin.
- [ ] Ensure **keepaliveTime** is smaller than **maxLifetime**.
- [ ] Set **maxLifetime** lower than any infrastructure hard connection lifetime.
- [ ] Choose **minimumIdle**, **maximumPoolSize**, and **idleTimeout** based on workload.
- [ ] Set **connectionTimeout** according to acceptable application pool wait time.
- [ ] Use JDBC4 validation if supported by the driver; avoid unnecessary test queries.
- [ ] Sum connections across all instances and jobs before increasing pool size.

### When Operating Spring/JPA

- [ ] Never hold transactions open while calling external APIs or waiting on users.
- [ ] Bound transaction and query durations according to business requirements.
- [ ] Monitor Hikari active, idle, pending, and timeout metrics.
- [ ] Check **@@SESSION.wait_timeout** on new connections after changing global settings.
- [ ] Drain/recycle connection pools in a controlled way when new session settings must take effect.
- [ ] Test rolling deployments, failovers, and network interruptions.
- [ ] Retry transactions only when idempotent or backed by commit-status verification.

## 13. Self-Check

**Scenario 1:** MySQL **wait_timeout** is 600 seconds, and Hikari **keepaliveTime** is 900,000 ms. What can happen to idle connections in the pool?

**Hint:** A 900,000 ms keepalive is 900 seconds, longer than 600 seconds. MySQL may close the session before the next ping; keepalive must be set lower than the timeout with margin.

**Scenario 2:** Hikari **maxLifetime** is 20 minutes, but a transaction holds a connection for 35 minutes. Does Hikari forcibly close the connection at minute 20?

**Hint:** No. Hikari marks the connection for retirement and evicts it when returned to the pool. However, MySQL or a proxy may still close the session if it goes idle or violates their own limits.

**Scenario 3:** **keepaliveTime** is 2 minutes, but the application holds a connection inside a transaction while waiting 15 minutes for a payment service. Does keepalive protect that connection?

**Hint:** No. The connection is borrowed, so it is not an idle connection in the pool. Design short transactions and avoid holding connections during external network waits.

**Scenario 4:** A DBA runs **SET GLOBAL wait_timeout=900**, yet an existing connection still reports **@@SESSION.wait_timeout=28800**. Is this a bug?

**Hint:** No. The global value initializes new sessions; existing sessions retain their own value. Check new connections or recycle the pool in a controlled manner.

**Scenario 5:** Hikari reports connection timeouts even though MySQL has fewer connections than **max_connections**. What should you check?

**Hint:** Check **active**, **idle**, **pending**, connection hold times, long transactions, slow queries, and connection creation/validation errors. **connectionTimeout** is the pool wait time, not MySQL's connection limit.

## 14. Key Takeaways

- HikariCP manages physical connection lifecycles; JPA/Spring borrows connections according to transaction needs.
- **maxLifetime** limits total connection age and retires connections when they return to the pool.
- **keepaliveTime** pings idle connections in the pool; it does not protect connections actively borrowed by the application.
- MySQL **wait_timeout** is an idle timeout for non-interactive sessions, not a total age limit.
- Session **wait_timeout** is initialized from global at connection creation; changing global does not modify existing sessions.
- **idleTimeout** lets the pool shrink; **connectionTimeout** bounds how long threads wait to borrow a connection.
- Set keepalive lower than the smallest idle timeout and maxLifetime lower than any hard connection lifetime, with margin.
- Do not hold transactions open while calling external services; borrowed connections can still be closed by MySQL or proxies.
- The sum of maximum pool sizes across all instances must fit within the **max_connections** budget.
- Investigate errors using timestamps, MySQL sessions, Hikari metrics, and proxy/network logs; do not assume every connection error is caused by wait_timeout.

## References

- [HikariCP: Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby) — maxLifetime, keepaliveTime, idleTimeout, pool sizing, and validation.
- [Spring Boot Reference: SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html) — configuring DataSource and HikariCP in Spring Boot.
- [MySQL 8.4 Reference Manual: Server System Variables](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_wait_timeout) — wait_timeout and interactive_timeout.
- [MySQL Connector/J: Configuration Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-configuration-properties.html) — connectTimeout, socketTimeout, TLS, and JDBC configuration.
- [Spring Boot Reference: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — collecting and observing application metrics.
