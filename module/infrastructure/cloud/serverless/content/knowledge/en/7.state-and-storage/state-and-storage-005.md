# Connection Pooling, Database Proxies, and Serverless Data Services

In the **State and Storage** chapter, one of the major operational challenges in serverless applications is managing database connections. An application running on long-lived servers usually has a relatively stable process count, allowing teams to size a connection pool predictably. With FaaS, the number of execution environments can rise rapidly with traffic. If every function invocation opens a new connection on its own, the database can exhaust its connection limit even before actual query volume becomes large.

Connection pooling, database proxies, and serverless data services solve different parts of this problem. A pool reuses connections within a process or execution environment. A proxy manages connections across multiple clients and the database. Serverless data services provide platform-managed access models and scaling. Choosing the right combination helps Java functions handle durable state, control access, reduce cold starts, and keep costs bounded.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying serverless applications—specifically Java functions triggered by HTTP, messages, or events. Because functions can be initialized, reused, or scaled out with load, connection design must account for instance lifecycles, concurrency, timeouts, retries, and data system limits.

## 1. Why are database connections problematic in serverless?

A relational database connection is typically a stateful session. Establishing a connection may require DNS lookup, opening a TCP socket, TLS negotiation, authentication, session setup, and driver initialization. These steps consume both time and resources.

In a serverless application, a traffic surge can cause the platform to spin up many execution environments simultaneously. If each invocation opens its own connection, connection count scales with concurrent invocations. Even when a function executes quickly, connections can outlive processing due to pooling, timeouts, or kept-warm execution environments.

For example, suppose an API receives 600 concurrent requests. If each execution environment opens 3 connections and the platform creates 600 environments, the system could demand up to 1,800 potential client connections. The database may permit only a fraction of that figure. Common consequences include:

- The database rejects new connections because `max_connections` is reached.
- Connection establishment times increase due to authentication and TLS handshakes.
- Connection storms cause sudden spikes in database CPU and memory.
- Functions wait too long to acquire a connection, causing cascading timeouts.
- Retries amplify traffic right when the database is already overloaded.
- Idle connections consume resources even with zero active queries.

The issue is not solely total query volume. Concurrent session count, session hold duration, and how connections are distributed across functions matter just as much.

## 2. Distinguishing connections, connection pools, and database proxies

Three components are often mentioned together yet serve distinct roles:

| Component | What does it manage? | Operating scope | Purpose |
|---|---|---|---|
| Database connection | One communication session between client and database | One specific connection | Send queries, transactions, and receive results |
| Connection pool | Set of reusable connections | Within one process or execution environment | Avoid opening a new connection for every operation |
| Database proxy | Client connections from apps and backend connections to DB | Between multiple clients and the database | Centralize, cap, and distribute backend connections |

A pool in Java is commonly created by a library such as HikariCP. Each execution environment can have its own pool. When the platform creates additional environments, the total number of pools grows alongside them.

A proxy sits between the application and the database. Many clients can connect to the proxy while the proxy manages a set of backend connections to the database. Depending on the engine and session state, the proxy can reuse one backend connection across different clients at appropriate points.

~~~mermaid
flowchart TB
    subgraph FaaS["Java function execution environments"]
      F1["Function A<br/>Pool A"]
      F2["Function B<br/>Pool B"]
      F3["Function C<br/>Pool C"]
    end
    F1 --> P["Database Proxy"]
    F2 --> P
    F3 --> P
    P --> BP["Backend connection pool"]
    BP --> DB[("Relational database")]
~~~

Application-side pooling reduces how often functions open connections to the proxy or database. A proxy coordinates backend connections and relieves pressure on the database. Both layers can complement each other, but must be configured holistically; creating large pools in every function and simply adding a proxy does not automatically make the system safe.

## 3. Connection pooling in Java

### 3.1. How does a pool work?

When the application needs to query the database, instead of opening a new connection, it asks the pool for an idle connection. Afterward, the application closes the `Connection` object to return it to the pool. Calling `close` in this case typically returns the connection to the pool rather than immediately closing the physical socket.

Basic flow:

1. Application initializes the pool with connection bounds.
2. Business code calls `getConnection`.
3. Pool returns an idle connection or waits until one is available.
4. Application executes queries or transactions.
5. Application closes `Connection` to return it to the pool.
6. Pool retains the connection for reuse or evicts it according to timeout and lifecycle policies.

Pools typically manage:

- Maximum number of connections.
- Minimum or target idle connections.
- Wait timeout when the pool has no available connections.
- Maximum lifetime of a connection.
- Connection validity checks.
- Eviction of broken or expired connections.

### 3.2. Benefits

Pooling reduces the overhead of repeatedly establishing connections. For Java, this is especially valuable when JDBC drivers and TLS handshakes carry significant cost.

A pool also caps the connections a single process can open. If pool size is 2, one execution environment has at most 2 connections managed by that pool. Concurrent requests inside that environment share those two connections or wait to acquire one.

Pooling does not automatically reduce total system-wide connections. If there are 300 environments each with a pool size of 10, the total limit can still reach 3,000 connections. You must calculate totals across the entire fleet.

### 3.3. Pool limitations in FaaS

A pool is typically an in-memory process resource. It is not shared across distinct execution environments. When the platform scales from 10 to 100 environments, the system may have 100 independent pools.

A pool created at environment startup can be reused across multiple invocations while the environment stays alive. However, there is no guarantee how long an environment will survive. The platform can shut down an instance at any time.

Therefore:

- Do not use a pool to store business state.
- Do not assume the pool survives past the current invocation.
- Do not create a new pool on every handler invocation.
- Do not open an oversized pool hoping to reduce wait times.
- Handle connections closed by the database or network after an environment sleeps for a long time.

## 4. Reusing a pool in Java functions

### 4.1. Creating the pool once per execution environment

In FaaS, a common pattern is keeping the `DataSource` at static or singleton scope so invocations within the same execution environment reuse the pool.

HikariCP example:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DatabaseResources {
    private static final HikariDataSource DATA_SOURCE = createDataSource();

    private DatabaseResources() {
    }

    private static HikariDataSource createDataSource() {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(System.getenv("DB_JDBC_URL"));
        config.setUsername(System.getenv("DB_USERNAME"));
        config.setPassword(System.getenv("DB_PASSWORD"));

        config.setMaximumPoolSize(2);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(3000);
        config.setValidationTimeout(1000);
        config.setIdleTimeout(60000);
        config.setMaxLifetime(300000);

        return new HikariDataSource(config);
    }

    public static HikariDataSource dataSource() {
        return DATA_SOURCE;
    }
}
~~~

The function borrows a connection while handling a request:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public final class CustomerRepository {
    public String findName(String customerId) throws Exception {
        String sql = "SELECT name FROM customers WHERE customer_id = ?";

        try (Connection connection =
                     DatabaseResources.dataSource().getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setString(1, customerId);

            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next() ? resultSet.getString("name") : null;
            }
        }
    }
}
~~~

In this example, try-with-resources closes `ResultSet`, `PreparedStatement`, and `Connection`. The connection returns to the pool after use. The `DataSource` stays alive for subsequent invocations in the same environment.

The configuration values are illustrative only. URL, username, and password must be retrieved from the platform's secure configuration, such as a secret manager or identity provider mechanism. Never log or commit credentials into source code.

### 4.2. Lazy initialization and cold starts

Initializing a pool in a static initializer can increase cold start time. HikariCP generally creates connections on demand, yet instantiating objects, reading configuration, and initializing the driver still carry overhead. If `minimumIdle` is set greater than 0, the pool may open idle connections right at startup.

For infrequently invoked functions, `minimumIdle` of 0 can avoid unnecessary connections. For steady-load functions, measure whether keeping a few idle connections reduces latency.

A lazy holder can initialize the `DataSource` only on first access:

~~~java
public final class LazyDatabaseResources {
    private LazyDatabaseResources() {
    }

    private static class Holder {
        private static final HikariDataSource DATA_SOURCE =
                DatabaseResourcesFactory.create();
    }

    public static HikariDataSource dataSource() {
        return Holder.DATA_SOURCE;
    }
}
~~~

This is a safe initialization pattern using Java's class initialization semantics. Even so, the first call still pays the cost of creating the `DataSource` and potentially opening the first physical connection. Measure real cold start and latency rather than merely shifting when initialization runs.

### 4.3. Do not close the DataSource after each invocation

Closing the `DataSource` after every request forces subsequent invocations in the same environment to recreate the pool. That defeats reuse and increases handshake overhead.

Normally, the handler closes only `Connection`, `Statement`, and `ResultSet`. The `DataSource` lives for the environment's lifetime. Do not rely on a shutdown hook to guarantee the pool closes cleanly when FaaS terminates, as the platform may stop the environment without giving the application reliable cleanup time.

## 5. Sizing the pool and bounding total connections

### 5.1. Estimation formula

To estimate maximum connections, use the formula:

\[
C_{total} \approx E \times P + B
\]

Where:

- `E` is the number of execution environments that can process concurrently.
- `P` is the maximum pool size per environment.
- `B` is the number of connections reserved for other applications, migrations, admin tasks, monitoring, and background jobs.

For example, if the function's concurrency limit is 120 environments and each environment has a pool size of 2, maximum client connections from the function can reach roughly 240. If the database reserves 300 connections for applications, headroom must still remain for other workloads.

This is a conservative estimate. Actual connection counts also depend on concurrent invocations per environment, how the pool initializes connections, and activity levels. However, never rely on pools staying partially unfilled to ignore connection limits.

### 5.2. Choosing pool size

In FaaS, a small pool is usually a sensible starting point. Many functions process only one request or one batch at a time inside an environment, so a large pool brings little benefit.

Choose pool size based on:

- Concurrent database operations within a single invocation.
- Concurrency allowed within the same execution environment.
- Maximum environments allowed by concurrency limits.
- Connection limits of the database or proxy.
- Query throughput and database CPU/I/O limits.
- Other applications sharing the database.

If each invocation executes only one sequential transaction, a pool size of 1 or 2 may suffice. If a function executes multiple tasks in parallel inside one invocation, calculate concurrent connections needed and bound worker pool concurrency.

### 5.3. Bounding function concurrency

Pool size and function concurrency must be designed together. Lowering max concurrency protects the database from overload, at the cost of increased message queue wait times or throttled requests. Raising concurrency can improve function throughput, but helps nothing once the database hits its limits.

Allocate explicit connection budgets per function or workload group. For example:

| Workload | Max concurrency | Pool per environment | Estimated max connections |
|---|---:|---:|---:|
| Customer read API | 80 | 1 | 80 |
| Order processing consumer | 40 | 2 | 80 |
| Reconciliation function | 5 | 2 | 10 |
| Migrations/monitoring and other apps | — | — | 30 |
| Projected total | | | 200 |

These figures are examples to illustrate budgeting. Verify real limits from your platform and database configuration.

## 6. Timeouts and connection lifecycle

A sound pool configuration coordinates multiple timeout settings:

| Timeout | Meaning | When too short | When too long |
|---|---|---|---|
| Connection timeout | Wait time to borrow a connection from pool | Requests fail early when pool is busy | Requests stall and risk exceeding function timeout |
| Validation timeout | Time allowed to validate a connection | Healthy connections may be marked bad when slow | Slow detection of broken connections |
| Idle timeout | Duration to keep idle connections before eviction | Frequent connection churn | Retaining unnecessary connections |
| Max lifetime | Maximum age of a connection in the pool | Increases connection recreation overhead | Old connections may be closed first by proxy or DB |
| Function timeout | Maximum invocation duration | Requests cut off before work finishes | Holds resources and connections too long |

Connection timeout should be shorter than the remaining invocation time. If a function times out after 10 seconds, letting the pool wait 10 seconds just to borrow a connection leaves zero time to run the query.

Max lifetime should generally be shorter than the maximum connection lifetime enforced by the proxy or database, with a safety buffer. There is no single magic number for all platforms; base settings on actual timeouts and service documentation.

After an environment sits unused for a while, firewalls, NAT, proxies, or the database may close idle connections. The pool must detect and evict invalid connections. Keepalive settings can help in some cases, though they add traffic and do not replace connection error handling.

## 7. What is a database proxy?

A database proxy is an intermediary layer that accepts connections from applications and manages connections to the database. Functions connect to the proxy endpoint instead of directly to the database.

A proxy can provide:

- Centralized backend connections and connection reuse.
- Caps on the number of connections opened to the database.
- Connection distribution across many clients.
- Connection health monitoring and handling of certain failover cases.
- Managed or integrated authentication depending on platform capabilities.
- Mitigation of connection storms hitting the database.

A proxy is not a query cache and does not automatically optimize SQL statements. If the database is slow due to heavy queries, missing indexes, or lock contention, a proxy will not fix those root causes.

### 7.1. Frontend and backend connections

Two connection groups can be distinguished:

- **Client/frontend connections:** from Java functions to the proxy.
- **Backend/database connections:** from the proxy to the database.

Many frontend connections can be served by the proxy over a smaller set of backend connections, provided session state allows. The proxy helps cap backend connections and prevents every execution environment from opening a dedicated physical session directly into the database.

However, frontend connection counts can still be large. Proxies also have limits on clients, memory, throughput, and backend connections. Monitor both sides.

### 7.2. Multiplexing

Multiplexing is the ability to reuse one backend connection across multiple clients at suitable points. A backend connection can be returned to the proxy pool after a transaction ends, then serve a different transaction.

Multiplexing efficiency depends on the engine, proxy, and session state. When a client holds a long transaction, alters session state, or uses features requiring session affinity, the proxy may have to bind a backend connection to that client for an extended period.

In that case, the connection becomes pinned, reducing pooling efficiency. Thus, a proxy does not guarantee every client connection is shared optimally.

### 7.3. Session pinning

Certain operations prevent a proxy from safely reassigning a backend connection to another client, for example:

- Long-running or unclosed transactions.
- Modifying session variables or session settings.
- Using temporary tables.
- Holding cursors or specialized session state.
- Certain prepared statements or connection-state-dependent commands, depending on proxy and database engine.

The exact list varies by service. Check the documentation of your proxy and monitor pinning metrics. To maximize multiplexing, keep transactions short, close statements and result sets promptly, and avoid global session state unless necessary.

## 8. When should you use a database proxy?

A proxy is especially helpful when:

- Many function environments connect to a relational database.
- Traffic has sudden spikes causing connection storms.
- The database connection limit is lower than total potential clients.
- Centralized backend connection management is needed.
- You want to reduce failover or endpoint-change impact according to service capabilities.
- Multiple applications or functions share one database.

A proxy may be unnecessary when:

- The workload is small and steady, and direct connections are already well-bounded.
- The data service uses an HTTP API or SDK instead of long-lived JDBC sessions.
- The proxy does not support the database engine or features the application needs.
- Added cost and latency outweigh the benefits.
- The application relies heavily on session pinning, making multiplexing ineffective.

A proxy is also an infrastructure component requiring configuration, monitoring, security, and budget. Do not add a proxy merely because the architecture is serverless; measure connection counts and load characteristics to decide.

## 9. Combining connection pools and database proxies

A common architecture uses Java functions with small pools connecting to a proxy, while the proxy manages a backend pool to the database.

~~~mermaid
flowchart LR
    A["Java Function A<br/>Small pool"] --> P["Database Proxy"]
    B["Java Function B<br/>Small pool"] --> P
    C["Java Function C<br/>Small pool"] --> P
    P --> D["Backend connection pool"]
    D --> DB[("Database")]
~~~

Each layer enforces its own limit:

- Application pools limit connections per environment.
- Concurrency limits cap active environments.
- The proxy caps and coordinates backend connections.
- The database limits sessions, CPU, memory, and throughput.

For example, 200 environments might open 400 total frontend connections to the proxy if each pool has size 2. The proxy might maintain only 50 backend connections if transactions are short and multiplexing is effective. If many sessions become pinned, required backend connections can climb close to active frontend connections.

Therefore, do not monitor only database connection counts. Also track:

- Client connections to the proxy.
- Active and idle backend connections.
- Connection multiplexing ratio.
- Pinned session count and pinning duration.
- Wait time to acquire a backend connection.
- Connection errors, timeouts, and failovers.
- Transaction duration and open transaction count.

## 10. Serverless data services and access models

Not every serverless data service needs a JDBC connection pool. Choose an access model suited to the data type and workload.

### 10.1. Serverless-capable relational databases

Some relational services manage compute and capacity on demand, such as serverless databases or auto-scaling capacity clusters. They may still use standard relational protocols like PostgreSQL or MySQL.

Characteristics:

- Support SQL, transactions, and relational integrity.
- Fit when business logic needs joins, constraints, or multi-record transactions.
- Still have connection, CPU, memory, and throughput limits.
- May still need pools or proxies when client counts grow high.
- Elastic capacity does not mean unlimited connections or queries.

Serverless at the compute tier does not automatically eliminate connection management.

### 10.2. Data APIs or HTTP database endpoints

Some relational services offer a Data API over HTTPS. Instead of opening long-lived JDBC sessions, functions send HTTP requests containing statements or data operations.

Advantages:

- No need to manage JDBC connections to the database.
- Well-suited to short-lived functions and environments with frequent cold starts.
- Can leverage service-managed authentication and connection management.
- HTTP clients can reuse keep-alive connections to reduce handshakes.

Limitations:

- APIs enforce quotas, payload limits, timeouts, and request rate limits.
- Transaction and batch semantics may differ from JDBC.
- Every request carries serialization and HTTP overhead.
- Not all SQL features or driver capabilities are available.
- Engine and regional availability must be verified.

A Data API reduces application-level database connection management, yet does not remove database capacity limits or API limits.

### 10.3. Managed or serverless NoSQL

Managed NoSQL services are typically accessed via SDKs or HTTP APIs rather than a JDBC connection per function. Examples include key-value stores or document databases that scale by requests, throughput, or provisioned capacity.

Best suited when:

- Queries rely primarily on keys or well-defined access patterns.
- Data has flexible structure.
- Independent scaling by partition or throughput is needed.
- Complex relational joins are not required.
- The consistency and transaction model fits business requirements.

SDK clients should generally be reused within an execution environment to leverage HTTP connection pooling, credential providers, and retry configuration. Do not instantiate a new SDK client for every operation without reason.

### 10.4. Object storage and caches

Object storage suits files, images, documents, log archives, and large data not needing direct relational querying. Functions can read/write via SDKs or HTTP APIs.

Caches suit read-heavy data that can accept TTLs or explicit invalidation policies. A cache does not replace the primary data source and should not become the sole store for critical business state unless the service provides appropriate guarantees.

### 10.5. Comparing options

| Service type | Common access method | Needs JDBC pool? | Best suited when |
|---|---|---|---|
| Managed/serverless relational DB | JDBC or native driver | Usually helpful when many ops use sessions | SQL, transactions, joins, constraints |
| Relational DB with Data API | HTTPS requests | No JDBC pool needed; reuse HTTP client | Short-lived functions, few long sessions |
| Managed/serverless NoSQL | SDK or HTTP API | No JDBC pool; SDK may manage HTTP pool | Key-value, document, clear access patterns |
| Object storage | SDK or HTTP | No | Files, objects, and unstructured data |
| Managed cache | Client protocol or API | Protocol-dependent; may need own pool | Read-heavy data with TTL |

Do not pick a database solely for a "serverless" label. Start from access patterns, consistency, transactions, data size, query capabilities, throughput, and cost.

## 11. Java SDK clients and HTTP connection reuse

For services accessed over an SDK or HTTP, no JDBC pool is needed, yet client reuse still matters. HTTP clients commonly manage connection pools, keep-alive, TLS sessions, and retries.

Example with Java `HttpClient`:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

public final class HttpClients {
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .version(HttpClient.Version.HTTP_2)
            .build();

    private HttpClients() {
    }

    public static HttpClient shared() {
        return CLIENT;
    }
}
~~~

Functions can reuse this client across invocations within the same environment. Reusing the client reduces socket creation and TLS handshake overhead. However, configure per-request timeouts, enforce appropriate concurrency limits, and respect API quotas.

With cloud SDKs, initialize one client per environment and reuse credential providers and HTTP transports as recommended by the SDK. Never create a new client for every record in a batch if the client is thread-safe across calls.

## 12. Transactions, session state, and safe usage

Connection pools and proxies support transactions, yet a transaction remains state bound to a connection or session during execution.

In JDBC:

- Start a transaction by disabling auto-commit.
- Execute operations requiring atomicity.
- Commit when all operations succeed.
- Roll back on error.
- Close `Connection` to return it to the pool.

Example:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(
            String fromAccount,
            String toAccount,
            long amount) throws Exception {

        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                debit(connection, fromAccount, amount);
                credit(connection, toAccount, amount);
                connection.commit();
            } catch (Exception failure) {
                connection.rollback();
                throw failure;
            }
        }
    }

    private void debit(
            Connection connection,
            String accountId,
            long amount) throws Exception {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE accounts SET balance = balance - ? WHERE account_id = ?")) {
            statement.setLong(1, amount);
            statement.setString(2, accountId);

            if (statement.executeUpdate() != 1) {
                throw new IllegalStateException("Debit failed");
            }
        }
    }

    private void credit(
            Connection connection,
            String accountId,
            long amount) throws Exception {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE accounts SET balance = balance + ? WHERE account_id = ?")) {
            statement.setLong(1, amount);
            statement.setString(2, accountId);

            if (statement.executeUpdate() != 1) {
                throw new IllegalStateException("Credit failed");
            }
        }
    }
}
~~~

This is an illustrative example. In production systems, validate non-negative balances, apply locking or conditional updates to prevent race conditions, handle deadlocks, and enforce account constraints. Never hold a transaction open while calling external HTTP services, as that ties up connections and reduces proxy multiplexing efficiency.

In serverless, an invocation can time out or terminate mid-transaction. Databases usually roll back uncommitted transactions when a connection closes, but you should not rely on that to manage multi-step processes. Operations spanning multiple invocations require durable state and an orchestration or Saga model.

## 13. Retries, idempotency, and connection failures

Connection errors can occur during function cold starts, proxy failovers, database capacity scaling, transient network blips, or expired pool connections.

Classify them carefully:

| Failure type | Example | Remediation direction |
|---|---|---|
| Transient failure before sending query | Connection timeout, socket reset | Retry with backoff and jitter if time remains |
| Dead connection | Database closed session while environment slept | Evict connection from pool and acquire a new one |
| Query timeout | Query runs too long or hits locks | Investigate query, cap timeouts, consider bounded retry |
| Unknown transaction outcome | Connection lost during commit | Look up business state before resending |
| Data or constraint error | Unique key violation, invalid schema | Do not retry infinitely; handle per business rules |

In particular, if a connection drops right at commit time, the client may not know whether the transaction committed. Retrying the entire operation can create duplicates. For critical writes, use idempotency keys, unique constraints, or transaction records to verify outcomes before retrying.

Do not blindly retry every SQL error. Retries must be bounded, with exponential backoff and jitter. If a function has little time remaining before timeout, extra retries may cause the invocation to fail and trigger message redelivery.

## 14. Connection security and credential management

Database connections often carry direct access to critical data. Each function should have least-privilege permissions matching its responsibilities.

Principles to apply:

- Use TLS when connecting to the database or proxy.
- Fetch credentials from a secret manager or platform identity mechanism.
- Rotate passwords or tokens according to policy.
- Separate database users for read and write workloads where needed.
- Grant permissions only on the schemas, tables, and operations the function requires.
- Never write passwords, tokens, JDBC URLs containing secrets, or sensitive data to logs.
- Control network access across functions, proxies, and databases.
- Use IAM authentication or short-lived tokens if supported by the service and driver.

If a proxy integrates with a secret manager or IAM authentication, configure both client-to-proxy and proxy-to-database permissions. Successful authentication on one hop does not mean the next hop is properly authorized.

Never share a single administrative database account across all functions. If one function is compromised or a credential leaks, least privilege limits the blast radius.

## 15. Observability and measurement

You cannot tune pools or proxies merely by checking current connection counts. Measure over time and correlate with concurrency, latency, and errors.

Metrics to track:

- Active and idle connections in the pool.
- Pending threads or requests waiting for connections.
- Connection acquisition time.
- Connection timeouts and validation failures.
- Client connections to the proxy.
- Active and idle backend connections.
- Session pinning or multiplexing ratio if exposed by the service.
- Database max connection utilization.
- Query latency, transaction duration, and lock waits.
- Function concurrency, cold starts, and invocation duration.
- Retry rates, timeouts, and database errors.

Logs should carry a correlation ID or request ID to link an invocation with its queries and errors. Avoid logging full SQL statements containing sensitive data or bound parameter values unless permitted.

Alert before the database hits its connection limit rather than waiting until functions start timing out. A useful signal is connection utilization combined with requests waiting on the pool and request wait age.

## 16. Common design mistakes

**Creating a pool per invocation:** Every request creates a new `DataSource`, spiking connections and losing reuse benefits. Create the pool once per environment and reuse it.

**Oversized pool size:** A large pool per environment can multiply into thousands of connections. Calculate the fleet-wide budget before setting max pool size.

**Using a pool without capping concurrency:** A pool caps connections per process, not the total number of processes. Set concurrency caps and evaluate a proxy.

**Assuming a proxy removes all limits:** Proxies still have client, backend, throughput, and session pinning limits. Monitor both frontend and backend connections.

**Holding transactions open too long:** Calling external APIs inside transactions or waiting on slow steps ties up connections and impairs multiplexing. Keep transactions short and wrap only data operations requiring atomicity.

**Ignoring stale connections:** Environments can sleep long enough for the network or database to close connections. Configure validation, lifetimes, and error handling so pools replace bad connections.

**Closing the DataSource after every request:** This destroys the pool and forces the next invocation to reinitialize it. Close only `Connection`/`Statement`/`ResultSet` at the operation scope.

**Misaligned timeouts:** The pool waits longer than the function timeout, or the proxy closes connections before the pool expects. Coordinate connection timeout, query timeout, max lifetime, and function timeout.

**Using JDBC for every data type:** NoSQL, object storage, or Data APIs may fit certain access patterns far better. Choose based on queries, transactions, and consistency.

**Unprotected retries on ambiguous commits:** Resending writes can duplicate data. Use idempotency keys and check state before retrying.

## 17. Connection design workflow for a Java function

Use the following workflow when taking a data-connected function to production:

1. **Identify access patterns:** Does the function read or write, how many queries per invocation, are transactions long, and is relational SQL needed?
2. **Select data service type:** Relational, Data API, NoSQL, object storage, or cache based on business requirements.
3. **Estimate concurrency:** Determine max concurrent environments and parallel database operations per environment.
4. **Calculate connection budget:** Pick a small pool size, add connections from other workloads, and reserve headroom.
5. **Decide on a proxy:** Weigh connection storms, session pinning, backend limits, and proxy cost.
6. **Configure pools and timeouts:** Set appropriate connection timeout, idle timeout, max lifetime, validation, and query timeouts.
7. **Manage lifecycles:** Reuse `DataSource` or SDK clients per environment; close per-operation resources promptly.
8. **Design error handling:** Distinguish transient errors, data errors, and ambiguous commit outcomes; use bounded retries.
9. **Secure access:** Enforce TLS, short-lived credentials or secret manager, least privilege, and network policies.
10. **Measure and tune:** Monitor connections, latency, concurrency, retries, and costs under representative load.

## 18. Pre-deployment checklist

- [ ] Function data types and access patterns have been identified.
- [ ] Appropriate relational DB, Data API, NoSQL, object storage, or cache has been selected.
- [ ] If using JDBC, `DataSource` is reused within the same execution environment.
- [ ] Pools are never recreated on every invocation.
- [ ] Pool sizes and concurrency are budgeted across the entire fleet.
- [ ] Connection budget accounts for migrations, monitoring, and other applications.
- [ ] Database proxy necessity and session pinning risks have been evaluated.
- [ ] Connection timeout is shorter than remaining function execution time.
- [ ] Max lifetime is compatible with proxy/database timeouts.
- [ ] `Connection`, `Statement`, and `ResultSet` are closed properly.
- [ ] Transactions are short and never hold connections while waiting on external services.
- [ ] Idempotency protects write operations that may be retried.
- [ ] Credentials are securely managed, TLS is enabled, and database privileges are least privilege.
- [ ] Metrics cover pool waits, active/idle connections, proxy, and database utilization.
- [ ] Cold starts, burst concurrency, failovers, and connection timeouts have been tested.
- [ ] Costs of pools, proxies, database capacity, and API requests have been estimated.

## Conclusion

Connection pooling lets Java reuse connections within one execution environment, yet each environment maintains its own pool so total connections still scale with concurrency. A database proxy coordinates backend connections and can relieve pressure on the database, though effectiveness depends on transactions, session state, and multiplexing behavior. Serverless data services or Data APIs can reduce session management overhead, while still carrying their own quotas, throughput limits, and costs.

Good design begins with access patterns and resource budgets. Keep pools small, cap concurrency, coordinate timeouts, manage credentials securely, keep transactions short, and make writes resilient to retries. Then measure connections, latency, and errors under realistic load to decide whether a proxy or a different data service model is warranted.
