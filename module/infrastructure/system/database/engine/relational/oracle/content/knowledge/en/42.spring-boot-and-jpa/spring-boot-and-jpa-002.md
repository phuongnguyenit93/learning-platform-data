# HikariCP, Oracle UCP, and Connection Management Boundaries

In a Spring Boot application using JPA with Oracle Database, JDBC connections are a finite resource. Creating a physical connection can involve a network handshake, authentication, session establishment, and Oracle state initialization. If an application opens and closes a connection for every SQL statement, this overhead grows rapidly and the database has to handle constant logins and logouts.

A connection pool maintains a set of pre-created JDBC connections. When a request needs database access, the application borrows a connection from the pool, uses it for the scope of its work, and returns it to the pool. Both HikariCP and Oracle Universal Connection Pool (UCP) provide this mechanism, though with different scopes of integration:

- **HikariCP** is a lightweight, fast JDBC connection pool widely used in Spring Boot. It suits applications that need standard JDBC connection lifecycle management.
- **Oracle UCP** is Oracle's pool, offering deeper integration with the Oracle ecosystem, including capabilities such as Fast Connection Failover (FCF), FAN, Runtime Load Balancing (RLB), connection labeling, and certain HA features depending on configuration/version.

A critical point to understand is that the pool only manages allocating and reclaiming connections. The Spring transaction manager manages transactions; the JPA EntityManager manages the persistence context; Hibernate manages SQL execution and object mapping. These layers collaborate, but they are not a single component.

## 1. Why Do We Need a Connection Pool?

Suppose an application handles 100 requests per second and each request queries Oracle multiple times. If every query creates a new TCP/JDBC connection, the system continuously pays the cost of:

1. Hostname resolution and establishing a network connection.
2. Oracle Net handshake.
3. User authentication.
4. Creating a database session and initializing session state.
5. Executing SQL.
6. Closing the connection and releasing the session.

A pool retains authenticated connections for reuse:

~~~text
HTTP request
    |
    v
Spring service / repository
    |
    v
JPA / Hibernate / JDBC
    |
    | borrow connection
    v
Connection pool
    |
    +---- JDBC connection 1 ---- Oracle session
    +---- JDBC connection 2 ---- Oracle session
    +---- JDBC connection 3 ---- Oracle session
    +---- ...
    |
    | return connection
    v
Connection pool
~~~

A pool helps:

- Reduce the number of physical connection creations.
- Limit how many sessions a single application instance can open.
- Reuse connections after work finishes.
- Detect or evict certain invalid connections.
- Throttle requests when all connections are busy.
- Centralize timeout and pool size configuration.

A pool does not make SQL queries inherently faster, replace index/query tuning, fix transaction bugs, or add processing capacity to the database. If the pool is too large, the application can open too many sessions and overload Oracle.

## 2. Distinguishing DataSource, Connection, EntityManager, and Transaction

These concepts are often conflated when configuring Spring Boot:

| Component | Responsibility |
|---|---|
| DataSource | Supplies JDBC connections; in a pooled app, it is typically a facade managing the pool |
| Connection | Represents a JDBC session currently borrowed from the DataSource |
| HikariCP or UCP | Manages the set of physical connections and borrow/return operations |
| EntityManagerFactory | Creates JPA EntityManagers |
| EntityManager | Manages the persistence context, entity states, and JPA operations |
| Hibernate Session | Hibernate's corresponding persistence context/implementation |
| Spring transaction manager | Starts, commits, rolls back, and synchronizes transaction resources |
| Oracle database session | Database-side session corresponding to an authenticated physical connection |

A Spring Boot application typically has a shared DataSource used by JPA, JdbcTemplate, and other JDBC components. When they use the same DataSource and an appropriate transaction manager, operations can participate in the same transaction.

### Resource Boundaries

- The pool manages **physical connections** and how long connections are borrowed.
- The transaction manager manages **commit/rollback boundaries**.
- The EntityManager manages the **persistence context** and entity state.
- The repository/service defines **business boundaries**.

Do not call Connection.close() to commit a transaction. Do not call EntityManager.close() on an EntityManager injected and managed by Spring. Do not store a connection in a static variable or share it across multiple threads.

## 3. What Is HikariCP?

HikariCP is a JDBC connection pool focused on performance, small footprint, and relatively straightforward behavior. Spring Boot typically selects HikariCP as the default implementation if it is on the classpath.

Common characteristics:

- maximumPoolSize: maximum number of connections in the pool.
- minimumIdle: target minimum number of idle connections.
- connectionTimeout: maximum time to wait to borrow a connection.
- idleTimeout: time after which idle connections may be retired when the pool exceeds minimumIdle.
- maxLifetime: maximum lifetime of a connection in the pool.
- keepaliveTime: interval to test/keep idle connections alive, if enabled.
- validationTimeout: timeout for connection validation checks.
- leakDetectionThreshold: threshold for logging when a connection is held too long.

HikariCP uses standard JDBC and works across many databases. It is not an Oracle-specific HA pool; specialized integrations like Oracle UCP's FAN/FCF and Runtime Load Balancing do not appear automatically just because the connection URL points to Oracle.

## 4. Configuring HikariCP in Spring Boot

When using spring-boot-starter-data-jpa or spring-boot-starter-jdbc, HikariCP is typically included on the classpath via Spring Boot dependency management.

Maven dependency example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>

<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
</dependency>
~~~

The JDBC driver version should be managed through a BOM or dependency management matching your JDK and Oracle Database version. Do not pick an arbitrary latest driver version without verifying compatibility.

### application.yml

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/APP_SERVICE
    username: app_runtime
    password: ${DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      pool-name: app-oracle-pool
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 120000
      leak-detection-threshold: 60000
~~~

These values are initial examples only, not a universal baseline for every application. Specifically:

- maximum-pool-size must be calculated based on total application instances and database capacity.
- minimum-idle can be set lower than maximum to let the pool scale, or left at the default equal to maximum for a fixed-size pool.
- connection-timeout is the wait time for a connection from the pool, not a SQL statement timeout.
- max-lifetime must be shorter than connection lifetime limits imposed by the database, firewall, load balancer, or network.
- auto-commit must align with the application's transaction management; when using Spring/JPA, configure the transaction manager explicitly.
- leak-detection-threshold only detects and logs long-held connections; it does not fix the root cause or guarantee connection closure.

### Explicitly Selecting HikariCP

If multiple pool implementations are on the classpath and you want to choose explicitly:

~~~yaml
spring:
  datasource:
    type: com.zaxxer.hikari.HikariDataSource
~~~

In a standard Spring Boot application, you usually do not need to declare a DataSource bean manually if there is only one datasource configured using standard prefixes.

## 5. Oracle JDBC URL and Service Name

With Oracle, applications usually connect using a service name:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/orders.example.com
~~~

This is an Easy Connect URL. A more complex connect descriptor can be used when multiple addresses, timeouts, or failover settings are needed:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=orders.example.com))
)
~~~

In RAC, connect using a service managed for the workload instead of hardcoding a single instance SID. Services allow the database to route sessions to appropriate instances according to cluster configuration.

Do not confuse service name with SID:

- SID identifies an instance.
- Service name identifies a logical service/workload.
- PDBs typically have dedicated application services so clients land in the right container.

## 6. What Is Oracle UCP?

Oracle Universal Connection Pool (UCP) is Oracle's connection pool for JDBC. UCP works with the Oracle JDBC driver and provides deeper Oracle-specific integrations than a general-purpose JDBC pool.

Commonly sought-after capabilities:

- Fast Connection Failover (FCF) with FAN events.
- Runtime Load Balancing (RLB) in supported environments.
- Connection labeling to classify connections by state/session context.
- Connection harvesting to manage connections under pool resource pressure.
- Connection validation and timeouts.
- Additional HA, replay, or integration features depending on driver, database, service, and version.

UCP is especially worth considering when running on Oracle RAC or needing integration with the Oracle HA stack. Simply enabling UCP does not automatically enable every HA feature; the service, ONS, driver, database, and cluster environment must be configured accordingly.

## 7. UCP Dependencies for Spring Boot

Maven dependencies example:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
</dependency>

<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ucp</artifactId>
</dependency>

<dependency>
    <groupId>com.oracle.database.ha</groupId>
    <artifactId>ons</artifactId>
</dependency>
~~~

ojdbc11 is an example driver for the corresponding Java environment. Choose artifacts and versions matching your JDK, Oracle Database, Spring Boot, and current Oracle JDBC/UCP guidance. The ONS dependency is typically required when using FAN/FCF with ONS configuration; not every UCP application needs FCF configured.

If using the Oracle JDBC BOM or an internal BOM for dependency management, let the BOM align compatible versions rather than manually mixing driver, UCP, and ONS versions.

## 8. Configuring UCP as a DataSource in Spring

UCP provides PoolDataSource and a factory to create pools. One clear approach is declaring a dedicated bean:

~~~java
import oracle.ucp.jdbc.PoolDataSource;
import oracle.ucp.jdbc.PoolDataSourceFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.env.Environment;

import java.sql.SQLException;

@Configuration
public class OracleUcpConfiguration {

    @Bean
    @Primary
    public PoolDataSource dataSource(Environment env) throws SQLException {
        PoolDataSource pool = PoolDataSourceFactory.getPoolDataSource();

        pool.setConnectionFactoryClassName(
            "oracle.jdbc.pool.OracleDataSource"
        );
        pool.setURL(env.getRequiredProperty("app.datasource.url"));
        pool.setUser(env.getRequiredProperty("app.datasource.username"));
        pool.setPassword(env.getRequiredProperty("app.datasource.password"));

        pool.setConnectionPoolName("app-oracle-ucp");
        pool.setInitialPoolSize(3);
        pool.setMinPoolSize(3);
        pool.setMaxPoolSize(20);
        pool.setConnectionWaitTimeout(30);
        pool.setValidateConnectionOnBorrow(true);

        return pool;
    }
}
~~~

This is a starting configuration example. Methods and properties must match your UCP version. Do not hardcode passwords; read secrets from environment variables, a secret manager, or platform security configuration.

Example application.yml:

~~~yaml
app:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/APP_SERVICE
    username: app_runtime
    password: ${DB_PASSWORD}
~~~

When creating a DataSource bean manually, ensure Spring Boot does not create another unintended pool. If the application has multiple DataSources, mark the default one with @Primary or use @Qualifier explicitly on the corresponding JPA/JdbcTemplate beans.

### Property-Based Configuration

Different Spring Boot versions may support binding UCP via specific prefixes or through a configured DataSourceBuilder/bean. If using Spring Boot's dedicated auto-configuration, verify property prefixes and UCP classes in the documentation for that exact Boot version. Do not copy prefixes from a different Boot version without verifying.

## 9. Configuring FCF, FAN, and ONS with UCP

In Oracle RAC, a node or instance can fail, and a service can relocate to another instance. If the pool is unaware of HA events, some pooled connections may still point to a dead instance and only fail when the application uses them.

Key concepts:

- **FAN (Fast Application Notification):** events notifying clients or middle tiers of service/instance/node state changes.
- **ONS (Oracle Notification Service):** infrastructure that transports FAN notifications.
- **FCF (Fast Connection Failover):** UCP uses FAN events to evict invalid connections and react faster to cluster changes.
- **RLB (Runtime Load Balancing):** uses service/load metrics to distribute connections appropriately in supported environments.

UCP configuration example:

~~~java
pool.setFastConnectionFailoverEnabled(true);
pool.setONSConfiguration(
    "nodes=racnode1.example.com:6200,racnode2.example.com:6200"
);
~~~

ONS addresses/ports must come from the actual Grid Infrastructure configuration. Do not guess ports or open firewalls based on examples. In some setups, clients may use remote ONS configuration or other discovery mechanisms depending on version.

For FCF to work properly:

1. The database runs in a supported Oracle HA configuration, such as RAC.
2. Services are configured appropriately for the workload.
3. FAN events are emitted and ONS is reachable.
4. UCP has FCF enabled and ONS properly configured.
5. Oracle JDBC driver and UCP versions are compatible.
6. The application handles interrupted transactions safely.

FCF helps the pool detect invalid connections; it cannot automatically complete an interrupted transaction according to business semantics. The application still needs controlled retries and idempotency when an operation might have committed on the server while the response was lost.

## 10. HikariCP vs. UCP: Where Do They Differ?

| Criterion | HikariCP | Oracle UCP |
|---|---|---|
| Scope | General-purpose JDBC pool | Oracle's JDBC pool |
| Spring Boot | Widely auto-configured, simple setup | Configurable via appropriate auto-config or bean declaration |
| Oracle RAC/FAN/FCF | No equivalent UCP-native integration | Supports FCF/FAN depending on config and version |
| Runtime Load Balancing | No native Oracle RLB integration | Can integrate RLB in supported environments |
| Connection labeling | Not a core feature equivalent to UCP | Supported |
| Connection harvesting | Not a signature Hikari mechanism | Supported with proper configuration |
| Simplicity | Usually simpler, minimal config | Additional Oracle-specific configuration |
| Best fit | Standard JDBC/JPA apps, single endpoint, or HA handled elsewhere | Apps needing Oracle RAC/ONS/FAN and UCP features |

HikariCP runs well with the Oracle JDBC driver. UCP is not automatically faster for every workload. The choice depends on HA requirements, topology, operations, driver requirements, and monitoring capabilities.

### When to Choose HikariCP?

HikariCP is usually the right choice when:

- The Spring Boot application only needs standard JDBC pooling.
- UCP-specific FAN/FCF/RLB is not required.
- HA is handled at another layer via services, network, driver, or retries.
- Simple configuration and predictable pool behavior are preferred.
- Connection labeling or UCP-specific features are not needed.

### When to Consider UCP?

UCP is worth considering when:

- The application runs against Oracle RAC and needs to react to FAN events.
- FCF is needed to evict connections to failed instances/services.
- RLB based on service metrics is needed.
- Connection labeling or connection harvesting is required.
- The architecture standardizes on Oracle UCP and the operations team can monitor it.

Do not pick UCP solely because the database is Oracle. For standalone databases and typical workloads, HikariCP works well.

## 11. Pool Size: Calculate Across the Entire System

maximumPoolSize is the maximum connection limit for a single pool in a single application process. When deploying multiple replicas, total potential connections equal the sum across all pools.

Example:

| Component | Count | Max pool per instance | Maximum total |
|---|---:|---:|---:|
| API deployment | 4 | 20 | 80 |
| Batch worker | 2 | 8 | 16 |
| Admin/reporting | 1 | 5 | 5 |
| **Total** | | | **101** |

Oracle must also serve other sessions: DBAs, monitoring, schedulers, replication, background services, and other applications. Therefore, never size a pool for one service in isolation while ignoring the rest of the database.

### Connection Budget Formula

\[
\text{Total max connections}
= \sum(\text{application instances} \times \text{max pool})
\]

Then compare against:

- PROCESSES/SESSIONS capacity and practical database limits.
- CPU, I/O, and concurrent transaction load.
- Other applications sharing the same database.
- Headroom for rolling deployments, autoscaling, and failovers.
- Non-pooled sessions.

If a Kubernetes autoscaler can scale from 4 to 12 pods, the budget must use the maximum possible pod count, not just normal replica count.

### More Connections Does Not Mean Faster

Every Oracle session consumes resources. Increasing pool size can:

- Increase concurrent sessions.
- Increase contention on CPU, buffer cache, latches, or locks.
- Increase the number of simultaneously running transactions.
- Overload the database and lengthen query times.
- Make the system slower even though the app has more connections.

Start with a small pool size, measure pool wait times, active/idle counts, DB CPU, I/O, and query latency, and adjust from there.

### One Pool or Multiple Pools?

Each DataSource typically owns its own pool. If an application creates one DataSource for JPA, another for JdbcTemplate, and another for batch jobs all pointing to Oracle, total connections equal the sum of all pools.

If there is no need to isolate transactions or workloads, sharing a DataSource simplifies connection budgeting. If workload isolation is needed, sum all pools and set per-workload limits.

## 12. HikariCP Timeouts and Connection Lifecycle

Timeouts have distinct meanings:

| Property | Meaning |
|---|---|
| connectionTimeout | Maximum time the app waits to borrow a connection from the pool |
| validationTimeout | Maximum time for connection validation |
| idleTimeout | Time after which idle connections may be retired when excess exists |
| maxLifetime | Maximum lifetime of a connection in the pool |
| keepaliveTime | Interval to check idle connections to prevent network device drops |
| Query timeout | Execution time limit for a SQL statement |
| Transaction timeout | Transaction time limit configured on the transaction manager |

Do not confuse connectionTimeout with query timeout. Once the pool grants a connection and SQL runs for 5 minutes, connectionTimeout does not stop that SQL statement.

### maxLifetime

Set maxLifetime lower than any connection lifetime limit enforced by firewalls, load balancers, database profiles, or network infrastructure. HikariCP will retire connections gracefully on its own schedule instead of letting middleboxes sever them unexpectedly.

Do not set maxLifetime too low, or the pool will constantly create and close connections, causing login storms and overhead. Do not set it higher than infrastructure limits if connections get dropped mid-use.

### keepaliveTime

Keepalive probes idle connections to reduce the risk of network devices dropping them for inactivity. It does not protect a connection currently running a long query and does not replace network or JDBC driver timeouts.

### Leak Detection

Example:

~~~yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 60000
~~~

If a connection is borrowed longer than the threshold, HikariCP logs the stack trace from where it was borrowed to aid investigation. When the connection is returned, logs may note that the leak was reclaimed. This is a suspicion-detection tool, not proof that every case is a leak; a valid long-running transaction can also exceed the threshold.

## 13. UCP Timeouts and Validation

UCP has similar properties, but with different names and semantics from HikariCP. Common properties include:

- initialPoolSize.
- minPoolSize.
- maxPoolSize.
- connectionWaitTimeout.
- inactiveConnectionTimeout.
- abandonedConnectionTimeout.
- validateConnectionOnBorrow.
- sqlForValidateConnection.
- fastConnectionFailoverEnabled.
- ONSConfiguration.

Example:

~~~java
pool.setInitialPoolSize(3);
pool.setMinPoolSize(3);
pool.setMaxPoolSize(20);
pool.setConnectionWaitTimeout(30);
pool.setValidateConnectionOnBorrow(true);
~~~

UCP time values may use seconds in the corresponding API, whereas many Hikari properties use milliseconds. Read the Javadoc for your exact version before porting settings between the two pools.

### Abandoned Connection Timeout

UCP provides a mechanism to detect connections held too long. Certain configurations can reclaim connections deemed abandoned. Be cautious because a valid long-running transaction or operation could be misidentified if the timeout is set too low.

Before enabling reclaim:

- Measure the longest valid transaction duration.
- Understand how UCP detects abandoned connections.
- Test logging and alerting.
- Validate in a staging environment.
- Never use timeouts to mask bugs where code fails to close connections.

### Connection Validation

Validation on borrow reduces the risk of handing a dead connection to the application, at the cost of a check on every borrow. Balance this against FAN/FCF and driver validation. Use Connection.isValid() or SQL validation per pool/driver recommendations; avoid heavy validation queries.

## 14. Transaction Boundaries with Spring JPA

In Spring, @Transactional typically defines transaction boundaries at the service layer:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final JdbcTemplate jdbcTemplate;

    public OrderService(
            OrderRepository orderRepository,
            JdbcTemplate jdbcTemplate) {
        this.orderRepository = orderRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void confirmOrder(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        order.confirm();

        jdbcTemplate.update(
            "insert into order_audit(order_id, event_type) values (?, ?)",
            orderId,
            "CONFIRMED"
        );
    }
}
~~~

When JPA and JdbcTemplate use the same DataSource and a properly configured transaction manager, entity changes and JDBC statements execute in the same transaction. If one operation throws an exception triggering rollback under Spring rules, both parts roll back together.

If each component uses a different DataSource or different transaction manager, do not assume they share a transaction. Explicit transaction coordination or an outbox/messaging pattern is required.

### When Is a Connection Borrowed?

JPA may defer acquiring a connection until SQL needs to be executed. Exact acquire/release timing depends on Hibernate connection handling mode, the transaction manager, OSIV, and actual operations.

Do not assume simply creating an EntityManager immediately holds a physical connection. Conversely, do not assume a connection is always returned immediately after each repository method if the transaction remains open.

In a typical transaction:

1. Spring starts the transaction.
2. An EntityManager/persistence context is bound to the transaction.
3. When SQL is needed, Hibernate acquires a JDBC connection via the DataSource.
4. SQL executes on the connection within the transaction.
5. Spring commits or rolls back.
6. The connection is returned to the pool per resource management rules.

## 15. EntityManager and Connection Pool Are Not the Same

An EntityManager is not a JDBC connection. A single EntityManager can perform many operations while Hibernate manages borrowing and returning connections underneath.

Example:

~~~java
@PersistenceContext
private EntityManager entityManager;
~~~

This is a context-managed EntityManager proxy handled by Spring. Do not call entityManager.close() inside a service when injected this way.

For manual JDBC:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement("select 1 from dual");
     ResultSet resultSet = statement.executeQuery()) {

    if (resultSet.next()) {
        // Use the result.
    }
}
~~~

With a pooled DataSource, connection.close() typically returns the connection to the pool rather than immediately closing the physical socket. try-with-resources is still required to guarantee the connection is returned when code completes or throws an exception.

If a connection is managed by the Spring transaction manager, let Spring coordinate its release. Avoid manually closing connections obtained through transaction-aware mechanisms.

## 16. @Transactional and Connection Hold Time

Long transactions hold connections longer, saturating the pool quickly. Bad example:

~~~java
@Transactional
public void processLargeFile() {
    List<Row> rows = readFileFromRemoteStorage();
    callExternalPaymentApi(rows);
    updateDatabase(rows);
}
~~~

If the method acquires a connection early and keeps the transaction open while reading files or calling slow APIs, the connection sits idle while the database does no work. Concurrent requests can exhaust the pool.

Split the work:

~~~java
public void processLargeFile() {
    List<Row> rows = readFileFromRemoteStorage();
    paymentClient.validate(rows);
    orderWriter.persist(rows);
}

@Transactional
public void persist(List<Row> rows) {
    // Keep only database work inside this transaction.
}
~~~

In practice, orderWriter should be a separate bean so the call goes through the Spring proxy; self-invoking a @Transactional method on the same object may bypass proxy-based transaction interception under default settings.

### Calling External APIs Inside a Transaction

Do not keep an Oracle transaction open while waiting on HTTP APIs unless there is a strict consistency requirement. External APIs can time out or stall, holding connections and locks for a long time.

If you need to guarantee both database updates and event emission:

- Use a transactional outbox.
- Commit business data and the outbox record in the same transaction.
- Have a separate worker read the outbox and send messages/API calls.
- Make consumers idempotent.

## 17. Open Session in View and the Pool

Spring Boot may enable Open EntityManager in View (OSIV) for web applications depending on configuration. OSIV keeps the persistence context open throughout the HTTP request so lazy associations can be accessed in the web/view layer.

OSIV does not necessarily mean a physical JDBC connection is held from start to finish of the request; acquire/release behavior depends on Hibernate connection handling. However, lazy queries during serialization/view rendering can trigger SQL outside service transactions, prolonging resource usage and making N+1 issues harder to control.

For REST APIs, consider disabling it:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

When disabling OSIV:

- Load required data inside the service transaction.
- Use fetch joins, entity graphs, or projections as appropriate.
- Map entities to DTOs before leaving the transaction.
- Do not let JSON serializers trigger lazy loading.

This is an architectural decision; test the application before disabling it if existing code relies on lazy loading outside services.

## 18. Pool Exhaustion and Warning Signs

Pool exhaustion occurs when all connections are borrowed and new requests must wait. If waiting exceeds connectionTimeout, HikariCP throws a connection acquisition timeout error. UCP reports a connection wait error according to its configured timeout.

Common causes:

- Pool too small for actual concurrency.
- Long-running transactions.
- Connection leaks or unclosed JDBC resources.
- Slow queries or lock waits.
- Calling remote APIs inside transactions.
- Slow or unreachable database.
- Total pool capacity growing too large across replicas.
- More DataSources/pools than anticipated.

Do not immediately raise max pool size when seeing timeouts. First inspect active/idle/pending metrics, query durations, transaction durations, database sessions, and pod counts.

### Signs from HikariCP

Logs can reveal:

- Connection timeouts.
- Pool active/idle/total counts.
- Threads waiting for connections.
- Leak detection warnings.
- Evicted connections or validation failures.

A pool consistently showing active equal to maximum with high pending counts indicates saturation. If active is low while requests are still slow, the bottleneck may be in the database, network, or application threads.

### Signs from Oracle

Check sessions:

~~~sql
SELECT username,
       service_name,
       machine,
       program,
       status,
       COUNT(*) AS session_count
  FROM v$session
 WHERE username IS NOT NULL
 GROUP BY username,
          service_name,
          machine,
          program,
          status
 ORDER BY session_count DESC;
~~~

Check sessions by service/module:

~~~sql
SELECT service_name,
       module,
       action,
       status,
       COUNT(*) AS session_count
  FROM v$session
 WHERE username = 'APP_RUNTIME'
 GROUP BY service_name, module, action, status
 ORDER BY session_count DESC;
~~~

V$ views require appropriate read privileges. In production, use a least-privilege monitoring account or DBA-published views.

## 19. Monitoring the Pool from Spring Boot

Spring Boot Actuator can expose DataSource and HikariCP metrics when appropriate dependencies/configuration are present. With Micrometer, metrics are typically prefixed with hikaricp and tagged by pool name, such as:

- Active connections.
- Idle connections.
- Pending threads.
- Maximum connections.
- Minimum connections.
- Connection usage/acquire time.

Exact metric names and exposure depend on the Spring Boot/Micrometer version. Check /actuator/metrics or your Prometheus scrape target rather than assuming metric names are identical across versions.

Example of enabling management endpoints in a controlled scope:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Never expose metrics, env, or config endpoints to the public Internet. Protect Actuator with authentication, network policies, and allowlists.

### What to Monitor

| Metric | Meaning |
|---|---|
| Active | Connections currently in use by the application |
| Idle | Connections ready to be borrowed |
| Pending | Threads waiting for a connection |
| Max | Pool limit |
| Acquire time | Time spent borrowing a connection |
| Usage time | Time a connection is held |
| Timeout count | Number of failed connection borrows due to timeout |

Correlate pool metrics with database CPU, session counts, wait events, SQL latency, and HTTP request latency. Looking at a single metric in isolation is insufficient to identify bottlenecks.

## 20. UCP Monitoring and Pool Management

UCP provides APIs/management interfaces and pool statistics to observe:

- Total/available/borrowed connection counts.
- Pool size and limits.
- Connection wait times.
- Connection validation.
- Connection labeling.
- FCF events and HA status per configuration.

Pool statistics can be retrieved through the version-appropriate UCP API. Conceptual example:

~~~java
int total = pool.getStatistics().getTotalConnectionsCount();
int available = pool.getStatistics().getAvailableConnectionsCount();
int borrowed = pool.getStatistics().getBorrowedConnectionsCount();
~~~

Method names may vary across UCP releases; check the Javadoc for your version. Do not write credentials or connection strings containing secrets into metrics/logs.

If using FCF, observe:

- FAN/ONS connectivity.
- Service/instance events.
- Invalidated/aborted connections.
- Pool stabilization time after failover.
- Transaction retries and application errors.

## 21. Connection Labeling and Session State

Oracle UCP supports connection labeling to categorize connections by session attributes. This helps when requests require different session states, such as NLS settings or specific business attributes.

The pool can pick a connection with a matching label or invoke a callback to reconfigure a connection when needed. However, session state can persist after a connection is returned to the pool.

If the application modifies:

- NLS_DATE_FORMAT.
- CURRENT_SCHEMA.
- CLIENT_IDENTIFIER.
- Module/action.
- Application context.
- Certain session parameters.

you must ensure the state is reset or managed via labeling/callbacks. Otherwise, the next request may inherit session state from the previous request.

HikariCP has no UCP-equivalent connection labeling mechanism. The application must manage session state carefully and reset it in a finally block or appropriate connection lifecycle hook.

Do not run arbitrary ALTER SESSION statements and return connections to the pool without resetting them. If setting module/action, use a clear set/reset mechanism so monitoring does not misattribute workloads.

## 22. Read-Only Transactions and Connection State

@Transactional(readOnly = true) is a hint to the transaction manager/provider. It is not an authorization mechanism and does not guarantee all SQL is read-only. It can help Hibernate optimize flush behavior or pass a read-only hint depending on configuration.

Example:

~~~java
@Transactional(readOnly = true)
public OrderDto findOrder(Long id) {
    return repository.findById(id)
        .map(OrderDto::from)
        .orElseThrow();
}
~~~

If the application uses multiple datasources or separate read/write services, configure routing and transaction managers explicitly. Do not route transactions to a read replica solely based on readOnly=true without a routing policy and consistency plan.

Because connection pools reuse connections after transactions, session-level state such as schema, NLS, isolation, or roles must be restored by design. Avoid letting requests mutate session state without resetting it.

## 23. Async, Schedulers, and Thread Boundaries

Spring transactions are typically bound to the executing thread. When an @Async method invokes another task, the new thread does not automatically inherit the original thread's transaction or JDBC connection.

Example:

~~~java
@Async
public CompletableFuture<Void> processAsync(Long orderId) {
    workerService.process(orderId);
    return CompletableFuture.completedFuture(null);
}

@Transactional
public void process(Long orderId) {
    // This worker thread starts its own transaction.
}
~~~

The worker's transaction must be started on the bean/service invoked on the new thread. Do not pass a Connection, EntityManager, or Hibernate Session from the old thread to the new thread.

Schedulers and batch workers also draw from connection pools. If running multiple jobs in parallel, include scheduler concurrency alongside API pools and any other pools.

## 24. Retries and Connection Failures

When a network glitch or RAC failover occurs, connections can become invalid. The pool can discard broken connections and supply fresh ones, but an in-flight transaction may have rolled back, committed, or entered an unknown state from the client's perspective.

Do not blindly retry write operations:

~~~java
@Retryable
public void chargeCardAndUpdateOrder(...) {
    // A retry may repeat a non-idempotent operation.
}
~~~

Before retrying:

- Determine whether the error occurred before or after the server received the request.
- Determine whether the transaction might already have committed.
- Use idempotency keys for business operations with side effects.
- Only retry well-defined transient errors.
- Enforce retry limits and backoff.
- Do not retry endlessly during a database outage.

UCP/FCF improves broken-connection detection in Oracle HA; it does not replace application-level retry policies.

## 25. Session Initialization and Connection Reset

Applications may need to set module/action so Oracle can identify workloads:

~~~java
try (Connection connection = dataSource.getConnection()) {
    try (CallableStatement statement = connection.prepareCall(
            "begin dbms_application_info.set_module(?, ?); end;")) {
        statement.setString(1, "orders-api");
        statement.setString(2, "confirm-order");
        statement.execute();
    }

    // Execute work using this connection.
}
~~~

This is illustrative. When the connection returns to the pool, module/action may persist on the session unless reset. You can set/reset it in a wrapper/interceptor or via an appropriate pool hook.

DBMS_APPLICATION_INFO helps DBAs track module/action in V$SESSION, but does not replace authorization. Never write sensitive data or PII into module/action.

## 26. Multi-Tenancy and Multiple DataSources

An application may connect to multiple PDBs or databases:

- OLTP database.
- Reporting database.
- Legacy database.
- Dedicated tenant databases.

Each DataSource typically maintains its own pool. If there are 3 DataSources with max pool 20 across 5 pods, maximum potential connections can reach:

\[
3 \times 20 \times 5 = 300
\]

Creating multiple pools increases total sessions and transaction complexity. If a transaction must span two databases, Spring @Transactional with a single transaction manager does not turn two DataSources into a distributed transaction. JTA/XA configuration or a saga/outbox design is needed depending on consistency requirements.

Do not share one DataSource bean across two different database URLs. Each DataSource must have its own pool, credentials, health check, and transaction configuration.

## 27. HikariCP and UCP in RAC Environments

In RAC, a service can run across multiple instances. Clients should use a Clusterware-managed service name. UCP can integrate with FAN/FCF and RLB when configured properly.

HikariCP can connect to a RAC service using a normal JDBC URL, though the pool lacks the same UCP-native integration for handling FAN events. During failover, HikariCP detects broken connections via validation or when the app uses the connection; behavior and recovery time depend on the driver, URL, network timeouts, and application.

### Factors Affecting HA

- Service placement and service role.
- SCAN listener/VIP.
- ONS/FAN configuration.
- Oracle JDBC driver version.
- Pool implementation.
- Connection validation.
- TCP connect/read timeouts.
- Transaction retries and idempotency.
- Application health checks.

Do not simply enable FCF and consider HA finished. Rehearse node failures, service relocations, network partitions, and database restarts in a test environment.

## 28. Sample Configurations for Choosing HikariCP or UCP

### Simple HikariCP

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/APP_SERVICE
    username: app_runtime
    password: $DB_PASSWORD
    hikari:
      pool-name: orders-hikari
      maximum-pool-size: 16
      minimum-idle: 4
      connection-timeout: 30000
      validation-timeout: 5000
      max-lifetime: 1740000
~~~

### UCP for Oracle HA

~~~java
PoolDataSource pool = PoolDataSourceFactory.getPoolDataSource();
pool.setConnectionFactoryClassName("oracle.jdbc.pool.OracleDataSource");
pool.setURL("jdbc:oracle:thin:@//rac-scan.example.com:1521/ORDERS_RW");
pool.setUser("app_runtime");
pool.setPassword(secretProvider.getSecret("oracle/app-runtime"));
pool.setInitialPoolSize(4);
pool.setMinPoolSize(4);
pool.setMaxPoolSize(16);
pool.setConnectionWaitTimeout(30);
pool.setValidateConnectionOnBorrow(true);
pool.setFastConnectionFailoverEnabled(true);
pool.setONSConfiguration(onsConfiguration);
~~~

These two configurations are starting points for comparison, not benchmarks. Measure pool wait times, connection creation, failover recovery, SQL latency, database load, and total sessions in your real topology.

## 29. Production Pool Design Checklist

- [ ] Identify maximum replica/pod count, not just normal replica count.
- [ ] Sum maximum connections across all DataSources and applications.
- [ ] Choose HikariCP or UCP based on actual requirements.
- [ ] Use the right Oracle service name and PDB.
- [ ] Manage passwords via a secret manager.
- [ ] Distinguish connection timeout from query/transaction timeouts.
- [ ] Set maxLifetime to fit network/database limits.
- [ ] Configure validation/keepalive per pool and driver.
- [ ] Limit transaction duration and avoid external API calls inside long transactions.
- [ ] Use the same DataSource/transaction manager when operations must share a transaction.
- [ ] Never share EntityManagers/Connections across threads.
- [ ] Measure active, idle, pending, acquire time, and usage time.
- [ ] Monitor session counts, SQL latency, and database waits.
- [ ] If using UCP FCF, verify FAN/ONS/service/driver compatibility.
- [ ] Rehearse RAC failover or network failures.
- [ ] Verify retries/idempotency and post-error transaction states.

## 30. Common Mistakes

**Pool too large:** each pod creates many sessions, exceeding Oracle's budget. Calculate across maximum replicas and all DataSources.

**Increasing pool size to fix slow queries:** more connections can overload the database. Inspect SQL, locks, I/O, and DB CPU first.

**Confusing connection timeout with query timeout:** pool wait timeouts do not stop running SQL. Configure statement/query timeouts separately.

**Holding transactions during HTTP calls:** connections and locks stay held. Move non-database work out of the transaction or use an outbox.

**Failing to close JDBC resources:** connections stay checked out and exhaust the pool. Use try-with-resources when managing JDBC manually.

**Manually closing Spring's EntityManager:** can break lifecycle and transactions. Let Spring manage EntityManagers injected via @PersistenceContext.

**Using Hikari while expecting UCP FCF:** Hikari does not natively integrate FAN/FCF the way UCP does. Choose UCP if Oracle-specific integration is required.

**Enabling UCP FCF without proper ONS/services:** the pool will not receive HA events as expected. Verify ONS, FAN, services, and drivers.

**Setting abandoned timeout too low:** connections running valid transactions can be reclaimed. Measure workloads and test beforehand.

**Using @Transactional(readOnly=true) as read-only security:** the annotation is a hint, not a security boundary.

**Passing connections to @Async:** JDBC connections and EntityManagers are not thread-safe that way; workers need their own transactions and connections.

**Retrying non-idempotent writes:** can create duplicates when a response is lost after commit. Use idempotency keys and retry policies.

## 31. Conclusion

Both HikariCP and Oracle UCP manage JDBC connection pools, serving different needs. HikariCP suits Spring Boot/JPA applications needing straightforward JDBC pooling. UCP is worth considering when Oracle-specific integrations such as FAN, FCF, RLB, connection labeling, or harvesting are needed in supported environments.

The pool manages physical connections and borrowing/returning; the Spring transaction manager handles commit/rollback; the JPA EntityManager manages the persistence context. Keep transactions short, avoid calling external systems inside long transactions, never share connections or EntityManagers across threads, and always return JDBC resources to the pool.

Pool size must be calculated across total pods/replicas, DataSources, and applications sharing the database. Monitor active/idle/pending counts, acquire time, usage time, Oracle sessions, and query latency before increasing pool sizes. If using UCP with RAC, verify FAN/ONS/service/driver compatibility and rehearse failover. No pool replaces proper transaction design, retries, idempotency, and capacity planning.
