# JDBC URLs, DataSource, and Connection Properties

## Objectives

After this lesson, you will be able to:

- Read and construct syntactically valid JDBC URLs for MySQL Connector/J.
- Distinguish connecting via DriverManager, DataSource, and a connection pool.
- Configure a MySQL DataSource in Java or an application-managed environment.
- Choose appropriate connection properties for TLS, timeouts, timezones, character sets, and performance.
- Securely manage credentials, Connection lifecycles, and JDBC resources.
- Diagnose common connection errors and verify the driver's actual runtime configuration.

## 1. MySQL Connector/J in JDBC Architecture

MySQL Connector/J is the JDBC driver that enables Java applications to communicate with MySQL Server through the JDBC API. The application calls standard interfaces such as Connection, PreparedStatement, ResultSet, and DataSource; Connector/J translates those operations into the protocol understood by MySQL Server.

Basic connection flow:

~~~mermaid
flowchart LR
    APP[Java Application] --> JDBC[JDBC API]
    JDBC --> CJ[MySQL Connector/J]
    CJ --> TCP[TCP + TLS if enabled]
    TCP --> MYSQL[MySQL Server]
~~~

Connector/J provides the driver for DriverManager, DataSource classes, and advanced connection mechanisms. The driver is not a database server, nor does it automatically create a connection pool for the application when using DriverManager or a standard MysqlDataSource.

In a real-world application, distinguish between:

- **JDBC URL:** describes the host, port, database, and connection properties.
- **DriverManager:** a simple API for obtaining a Connection from a JDBC URL.
- **DataSource:** a standard abstraction for providing connections, configurable in code, JNDI, or an application server.
- **Connection pool:** manages and reuses physical connections to avoid opening a new TCP connection for every operation.

Choosing the right approach keeps configuration manageable, strengthens security, and reduces errors across multi-environment deployments.

## 2. Adding Connector/J to a Java Project

With Maven, the MySQL Connector/J dependency coordinates are:

~~~xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <version>${mysql.connector.version}</version>
</dependency>
~~~

Manage the version via a property or dependency management so all modules use the same driver version. Choose a Connector/J version compatible with your Java runtime and deployed MySQL Server; do not copy an old version simply because an online example uses it.

The modern driver class is:

~~~text
com.mysql.cj.jdbc.Driver
~~~

With JDBC 4 and later, the driver is automatically discovered when the JAR contains valid service provider metadata and is on the classpath/module path. Typical applications do not need to call Class.forName to load the driver. Class.forName is only useful in some legacy environments or when manually verifying driver loading.

If you encounter a No suitable driver error, verify that the dependency is actually included in the runtime artifact/container, that the URL uses the correct jdbc:mysql: prefix, and that the driver is compatible with the Java runtime.

## 3. JDBC URL Structure

Common connection syntax:

~~~text
jdbc:mysql://host[:port]/database?property1=value1&property2=value2
~~~

Where:

- jdbc:mysql: identifies the JDBC driver type.
- host is the hostname or IP address of the MySQL Server.
- port is the TCP port; MySQL's default port is typically 3306.
- database is the default schema for the connection; this part can be omitted if the application selects a database after connecting.
- The part after the question mark is the property list, separated by &.

Minimal example:

~~~text
jdbc:mysql://db.internal.example:3306/sales_app
~~~

Example with properties:

~~~text
jdbc:mysql://db.internal.example:3306/sales_app?sslMode=VERIFY_IDENTITY&connectTimeout=5000&socketTimeout=30000&connectionTimeZone=UTC
~~~

The values in these examples are illustrative; replace hostname, database, certificates, and timeouts according to your actual environment.

### 3.1. Host, Port, and Database

Some examples:

| Purpose | JDBC URL |
|---|---|
| Local host, default port | jdbc:mysql://localhost/sales_app |
| Specific host and port | jdbc:mysql://10.20.0.15:3307/sales_app |
| No default database selected | jdbc:mysql://db.internal.example:3306/ |
| IPv6 host | jdbc:mysql://[2001:db8::15]:3306/sales_app |

IPv6 addresses must be enclosed in square brackets to distinguish colons in the address from the colon separating the port.

The database in the URL is the default schema for the connection. You can change the active schema using Connection.setCatalog or an appropriate SQL statement, but it is best to explicitly configure the database the application needs to access to reduce the risk of querying the wrong schema.

### 3.2. Multiple Properties in the URL

The first property starts after the question mark, and subsequent properties are joined with &:

~~~text
jdbc:mysql://db.internal.example:3306/sales_app?sslMode=VERIFY_IDENTITY&connectTimeout=5000&socketTimeout=30000
~~~

Do not chain multiple question marks for multiple properties. Special characters such as &, =, or ? in values may be misinterpreted by the parser as delimiters. When values are complex, configure them using Properties or DataSource setters instead of concatenating URL strings.

Do not place passwords directly in the JDBC URL, committed configuration files, or startup logs. URLs frequently appear in logs, exceptions, dashboards, or diagnostic output; credentials should be passed separately.

## 4. Connecting with DriverManager

DriverManager is suitable for small programs, command-line tools, lab exercises, or applications with low concurrency.

Example:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Properties;

public class JdbcExample {
    public static void main(String[] args) throws Exception {
        String url =
            "jdbc:mysql://db.internal.example:3306/sales_app"
            + "?sslMode=VERIFY_IDENTITY"
            + "&connectTimeout=5000"
            + "&socketTimeout=30000"
            + "&connectionTimeZone=UTC";

        Properties properties = new Properties();
        properties.setProperty("user", System.getenv("DB_USER"));
        properties.setProperty("password", System.getenv("DB_PASSWORD"));

        String sql =
            "SELECT order_id, total_amount "
            + "FROM orders WHERE customer_id = ?";

        try (Connection connection =
                 DriverManager.getConnection(url, properties);
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, 501L);

            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    long orderId = resultSet.getLong("order_id");
                    java.math.BigDecimal amount =
                        resultSet.getBigDecimal("total_amount");

                    System.out.println(orderId + " " + amount);
                }
            }
        }
    }
}
~~~

The example uses environment variables to demonstrate separating credentials from source code. In production environments, secrets can be retrieved from a secret manager or the platform's credential provisioning mechanism. Always verify that environment variables exist and are non-empty before opening a connection.

Try-with-resources automatically closes ResultSet, PreparedStatement, and Connection in reverse order when exiting the block. This ensures JDBC resources are released even when statements throw exceptions.

DriverManager opens a new connection when getConnection is called. Do not call it for every query in a high-traffic web application without a connection reuse strategy.

## 5. What Is a DataSource?

DataSource is an interface in the javax.sql package that provides a standard way to obtain a Connection. Compared to DriverManager, DataSource supports separating configuration from code and can be managed by an application server, JNDI, or a connection pool library.

A DataSource is not necessarily a pool. There are three common concepts:

| Type | Role |
|---|---|
| Basic DataSource | Provides a Connection per configuration; may open a new physical connection on each call |
| ConnectionPoolDataSource | Low-level API for a pool manager to manage PooledConnections |
| Pooled DataSource | DataSource provided by a pool library; getConnection borrows a logical connection from the pool and close returns it to the pool |

MySQL Connector/J includes the MysqlDataSource class in the com.mysql.cj.jdbc package. This class is a basic DataSource. Using MysqlDataSource directly does not mean you have pooling.

## 6. Configuring MysqlDataSource in Java

Example of configuring a DataSource in code:

~~~java
import com.mysql.cj.jdbc.MysqlDataSource;
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class DataSourceExample {
    public static void main(String[] args) throws Exception {
        MysqlDataSource mysql = new MysqlDataSource();

        mysql.setURL(
            "jdbc:mysql://db.internal.example:3306/sales_app"
            + "?sslMode=VERIFY_IDENTITY"
            + "&connectTimeout=5000"
            + "&socketTimeout=30000"
            + "&connectionTimeZone=UTC"
        );
        mysql.setUser(System.getenv("DB_USER"));
        mysql.setPassword(System.getenv("DB_PASSWORD"));

        DataSource dataSource = mysql;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                 "SELECT COUNT(*) FROM orders");
             ResultSet resultSet = statement.executeQuery()) {

            if (resultSet.next()) {
                System.out.println("Order count: " + resultSet.getLong(1));
            }
        }
    }
}
~~~

You can configure DataSource using individual setters such as server name, port, database, user, and password. Using setURL is concise when you already have a complete URL. Avoid configuring the same property in multiple places without clearly defining the primary configuration source.

In large applications, create the DataSource once during application startup and reuse it. Do not instantiate a new MysqlDataSource for every request. If pooling is needed, place this DataSource behind a pool manager or use a DataSource provided by a pooling library.

## 7. DataSource in Application Servers and JNDI

In Jakarta EE or an application server, administrators can create a DataSource at the server level and register it under a JNDI name. The application looks up the DataSource by name and obtains a Connection.

Conceptual example:

~~~java
import javax.naming.InitialContext;
import javax.sql.DataSource;
import java.sql.Connection;

InitialContext context = new InitialContext();
DataSource dataSource =
    (DataSource) context.lookup("java:comp/env/jdbc/SalesDB");

try (Connection connection = dataSource.getConnection()) {
    // Perform JDBC operations within the unit of work.
}
~~~

The JNDI name and resource declaration depend on the application server. A server-managed DataSource can integrate connection pooling, a transaction manager, a credential store, monitoring, and connection limits. In that case, the application should not create another pool of its own for the same database without a clear architectural reason.

One benefit of JNDI is that changes to hostname, port, credentials, or pool size can be made via deployment configuration without modifying source code. However, server configuration and application configuration must agree on resource names, transaction policies, and access permissions.

## 8. Connection Pools and HikariCP

Establishing a TCP/TLS connection, authenticating, and initializing a MySQL session carry overhead. In web applications, creating a new connection for every request increases latency and opens many concurrent connections. A connection pool maintains a set of physical connections, lending them to the application briefly and taking them back afterward.

Usage flow:

1. The application calls DataSource.getConnection.
2. The pool assigns a logical connection backed by an idle physical connection.
3. The application executes queries or transactions.
4. The application calls close.
5. The pool resets necessary state and returns the connection to the available list.

With a pool, close typically returns the connection to the pool rather than immediately closing the physical TCP connection. Therefore, always close Connections using try-with-resources so connections are not held unintentionally.

### 8.1. HikariCP Example

HikariCP is a popular connection pool. You can configure the JDBC URL and credentials as follows:

If using Maven, add the HikariCP dependency alongside Connector/J:

~~~xml
<dependency>
    <groupId>com.zaxxer</groupId>
    <artifactId>HikariCP</artifactId>
    <version>${hikari.version}</version>
</dependency>
~~~

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class PooledJdbcExample {
    public static void main(String[] args) throws Exception {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(
            "jdbc:mysql://db.internal.example:3306/sales_app"
            + "?sslMode=VERIFY_IDENTITY"
            + "&connectTimeout=5000"
            + "&socketTimeout=30000"
            + "&connectionTimeZone=UTC"
        );
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASSWORD"));
        config.setPoolName("sales-app-pool");
        config.setMaximumPoolSize(12);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(3000);
        config.setValidationTimeout(1000);
        config.setMaxLifetime(1500000);

        try (HikariDataSource dataSource =
                 new HikariDataSource(config)) {
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement statement =
                     connection.prepareStatement("SELECT 1");
                 ResultSet resultSet = statement.executeQuery()) {
                resultSet.next();
                System.out.println(resultSet.getInt(1));
            }
        }
    }
}
~~~

The example uses illustrative configuration values. The pool is closed when the application exits; in server applications, the DataSource lifecycle is typically managed by a dependency injection container or lifecycle manager.

Choose maxLifetime to be shorter than the connection lifetime limit imposed by the database, proxy, or network. The value in the example is 25 minutes and is appropriate only if infrastructure limits allow it.

### 8.2. Distinguishing Pool Timeouts and Driver Timeouts

Properties with similar names handle different stages:

| Property | Component | Meaning |
|---|---|---|
| connectTimeout | Connector/J | Wait time to establish the network connection to MySQL |
| socketTimeout | Connector/J | Wait time for socket operations before timing out |
| connectionTimeout | HikariCP | Maximum wait time to borrow a connection from the pool |
| validationTimeout | HikariCP | Maximum time for connection validation |
| maxLifetime | HikariCP | Maximum age of a connection in the pool before lifecycle eviction |

HikariCP's connectionTimeout does not replace Connector/J's connectTimeout. If the pool is full and no idle connection is available, the application may wait on the pool even when MySQL is healthy. Conversely, if the pool is opening a new connection and TCP connect hangs, connectTimeout governs the network connection wait time.

### 8.3. Sizing the Pool

Do not set maximumPoolSize arbitrarily high just to avoid waiting. Every connection consumes resources on MySQL: session memory, threads, sockets, and processing capacity. Total connections must be calculated across all application instances, workers, cron jobs, and admin tools.

For example, 10 application instances with a max pool size of 20 can open up to 200 connections, excluding other services. Compare this total against max_connections, actual workload, and database concurrency capacity.

A practical approach:

- Measure query duration and how long connections are borrowed.
- Estimate required concurrency from throughput and connection hold time.
- Start with a small pool and increase only when metrics prove it is necessary.
- Set a system-wide total connection cap, not just per-instance limits.
- Monitor active, idle, pending borrowers, timeouts, and connection creation rate.
- Keep transactions short and avoid making HTTP calls or waiting for user input while holding a connection.

## 9. Important Connection Properties

Connector/J supports many connection properties. They can be specified in the JDBC URL, in Properties, or via corresponding DataSource setters. Enable a property only when you understand its impact and have tested it with your Connector/J version.

### 9.1. Network and Timeout Group

| Property | Meaning | Recommendation |
|---|---|---|
| connectTimeout | Timeout when establishing the socket connection | Set an appropriate limit so the application does not wait indefinitely when a host is unresponsive |
| socketTimeout | Timeout for socket read operations | Choose based on valid query duration; too short may interrupt legitimate slow queries |
| tcpKeepAlive | Enables TCP keepalive on the socket | Can help detect dead connections according to OS policy |
| localSocketAddress | Local address used when binding the socket | Configure only when network infrastructure specifically requires it |

Timeout values are in milliseconds in Connector/J. A value of 0 usually means no timeout at that property level. Do not use low timeouts as a fix for slow queries; optimize SQL, indexes, and server load instead.

### 9.2. TLS and Security Group

The most important property for choosing TLS mode is sslMode. Common values:

| Value | Behavior |
|---|---|
| DISABLED | Do not use TLS |
| PREFERRED | Prefer TLS, but fall back to an unencrypted connection if the server does not support it |
| REQUIRED | Require TLS, without full CA and hostname verification |
| VERIFY_CA | Require TLS and verify the certificate chain against a trusted CA |
| VERIFY_IDENTITY | Verify both the CA and that the server hostname matches the certificate |

For connections over untrusted networks, the strict choice is typically VERIFY_IDENTITY, paired with a properly managed trust store/CA. The server certificate must have a Subject Alternative Name matching the hostname in the JDBC URL. If connecting by IP, the certificate must include the corresponding IP or the application should use a valid hostname.

Example:

~~~text
jdbc:mysql://mysql.prod.example:3306/sales_app?sslMode=VERIFY_IDENTITY&connectTimeout=5000
~~~

useSSL is a legacy property; in new configurations, use sslMode to express the exact verification level. Do not disable certificate verification just to bypass TLS errors in production.

Some MySQL authentication flows may require public key retrieval when TLS is not used. Connector/J provides the allowPublicKeyRetrieval property, which is typically disabled by default. Do not enable it arbitrarily on untrusted networks; prefer configuring TLS with proper certificate verification.

Do not place truststore passwords, client keystore passwords, or private keys in JDBC URLs or repositories. Supply them via a secret manager or runtime security configuration.

### 9.3. Timezone and Temporal Data Group

The application, JDBC driver, and MySQL session can use different timezones. This is especially important when working with TIMESTAMP, DATETIME, java.time, and data written from multiple geographic regions.

Modern Connector/J provides the connectionTimeZone property. Example:

~~~text
jdbc:mysql://db.internal.example:3306/sales_app?connectionTimeZone=UTC
~~~

connectionTimeZone controls the timezone the driver uses when converting temporal values; this property is available in modern Connector/J versions (since 8.0.23). If you need to synchronize the MySQL session timezone, also evaluate forceConnectionTimeZoneToSession according to your semantics and Connector/J version. These two concepts are related but not identical.

The serverTimezone property appears in older configurations; in new configurations, prefer connectionTimeZone as documented for your deployed Connector/J version.

Do not assume all temporal columns are converted identically:

- MySQL TIMESTAMP stores a point in time in UTC and converts between session timezones on write/read.
- MySQL DATETIME stores date and time components without automatically attaching a timezone.
- Java Instant represents an absolute point in time.
- LocalDateTime does not carry a timezone.

Define business rules for each data type, use appropriate Java types, and test across DST transitions when local timezones are involved.

### 9.4. Character Set Group

For multilingual applications, ensure Java, Connector/J, MySQL database, tables, and connections agree on encoding. Modern MySQL typically uses utf8mb4 for full Unicode support, including emoji and characters outside the BMP.

You can inspect the session:

~~~sql
SHOW SESSION VARIABLES LIKE 'character_set_%';
SHOW SESSION VARIABLES LIKE 'collation_%';
~~~

If explicit encoding configuration is needed, consult the characterEncoding property and how Connector/J maps Java charsets to MySQL charsets in the version you are using. Do not confuse connection charset with column collation: charset governs character encoding, while collation governs comparison and sorting rules.

Do not use legacy charsets merely to silence character errors. If data exhibits mojibake, locate where encoding is wrong across the entire pipeline rather than changing connection charsets at random.

### 9.5. Statement and Performance Group

Several properties can affect how Connector/J sends statements:

| Property | Effect |
|---|---|
| useServerPrepStmts | Allows using server-side prepared statements when appropriate |
| cachePrepStmts | Enables prepared statement caching on the driver side |
| prepStmtCacheSize | Size of the prepared statement cache |
| prepStmtCacheSqlLimit | Maximum SQL length eligible for caching |
| rewriteBatchedStatements | Allows the driver to rewrite certain batch statements to reduce round trips |
| allowMultiQueries | Allows multiple SQL statements per send; enable only when the application truly needs it |

These properties do not always improve performance. Effectiveness depends on workload pattern, repetitive SQL counts, batch size, server version, and how the application uses PreparedStatement. Measure with benchmarks close to your actual workload.

Do not enable allowMultiQueries simply for convenience when concatenating SQL strings. Use PreparedStatement with parameter binding to mitigate SQL injection and validate input data.

### 9.6. Avoid Auto-Reconnect Properties as a General Solution

Do not rely on a reconnect property to automatically recover failing connections as if nothing happened. When a TCP connection drops, a transaction may be in an uncertain commit state. Automatically resending statements can create duplicate transactions or corrupt business logic.

Let the pool evict broken connections, obtain a fresh connection, and let the application handle errors at transaction boundaries. Retry operations only when idempotency can be guaranteed or when an idempotency key/transaction identifier prevents duplicate execution.

## 10. Configuring with Properties Instead of Long URLs

When there are many properties, Properties separates configuration from the URL string:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.Properties;

String url = "jdbc:mysql://db.internal.example:3306/sales_app";

Properties properties = new Properties();
properties.setProperty("user", System.getenv("DB_USER"));
properties.setProperty("password", System.getenv("DB_PASSWORD"));
properties.setProperty("sslMode", "VERIFY_IDENTITY");
properties.setProperty("connectTimeout", "5000");
properties.setProperty("socketTimeout", "30000");
properties.setProperty("connectionTimeZone", "UTC");

try (Connection connection =
         DriverManager.getConnection(url, properties)) {
    // Use the connection within the unit of work.
}
~~~

This keeps credentials out of the URL string and makes per-environment configuration easier. Properties must still be protected; never print the entire object to logs because it may contain passwords or sensitive information.

## 11. Multiple Hosts and Advanced URLs

Connector/J supports several multi-host URL formats. Choose the right type for your connection goal and understand the driver's failover or routing behavior.

### 11.1. Host Lists

Example URL with multiple hosts:

~~~text
jdbc:mysql://mysql-a.internal:3306,mysql-b.internal:3306/sales_app
~~~

A host list allows Connector/J to try other hosts according to the failover mechanism of the URL type and associated properties. This does not automatically guarantee safe failover for every topology. Hosts must serve the same logical database with compatible permissions and schemas; the application must still handle dropped connections and transactions with unknown outcomes.

### 11.2. Load Balancing URLs

Connector/J provides a load balancing URL format:

~~~text
jdbc:mysql:loadbalance://mysql-a.internal:3306,mysql-b.internal:3306/sales_app
~~~

This format distributes connections across hosts using the driver's load balancing mechanism. It does not automatically understand all application read/write rules and does not replace MySQL InnoDB Cluster architecture, MySQL Router, or an organization's endpoint coordinator.

### 11.3. Replication URLs

Connector/J also provides a replication URL format:

~~~text
jdbc:mysql:replication://mysql-source.internal:3306,mysql-replica.internal:3306/sales_app
~~~

This URL format represents source and replica hosts for replication-aware connections. Switching connections between source and replica depends on the API, configuration, and how the application controls read-only mode. Do not assume every SELECT query automatically routes to a replica in all scenarios.

With a replication-aware connection, applications typically use Connection.setReadOnly(true) for read work and switch back to setReadOnly(false) for write work per driver guidelines. Set the mode before starting a transaction; do not switch modes in the middle of an open transaction.

For production HA, prefer endpoints managed by MySQL infrastructure—such as MySQL Router for InnoDB Cluster—when that is your system architecture. The router routes based on topology state; Connector/J remains responsible for creating JDBC connections, and the application still must handle reconnects/retries.

## 12. Connection and Transaction Management

A Connection is a stateful session. It holds transactions, autocommit, isolation level, current schema, session variables, and other settings. When using a pool, connections are reused, so applications must properly finish transactions and close resources.

Transaction example:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement debit = connection.prepareStatement(
                 "UPDATE accounts SET balance = balance - ? "
                 + "WHERE account_id = ?");
             PreparedStatement credit = connection.prepareStatement(
                 "UPDATE accounts SET balance = balance + ? "
                 + "WHERE account_id = ?")) {

            debit.setBigDecimal(1, amount);
            debit.setLong(2, fromAccountId);
            int debitRows = debit.executeUpdate();

            credit.setBigDecimal(1, amount);
            credit.setLong(2, toAccountId);
            int creditRows = credit.executeUpdate();

            if (debitRows != 1 || creditRows != 1) {
                throw new IllegalStateException(
                    "Account was not found or not updated");
            }
        }

        connection.commit();
    } catch (Exception exception) {
        try {
            connection.rollback();
        } catch (Exception rollbackException) {
            exception.addSuppressed(rollbackException);
        }
        throw exception;
    }
}
~~~

This example illustrates transaction boundaries. In real applications, also enforce non-negative balances, row locking, deadlock handling, and idempotency rules. Do not hold a Connection longer than necessary.

When using a pool, never store a Connection reference in a static field to share across threads. A JDBC Connection is not designed for arbitrary concurrent operations by multiple threads. Each unit of work should borrow its own connection and return it upon completion.

## 13. Inspecting Configuration and Driver Metadata

At startup or in diagnostic tools, you can retrieve information from JDBC:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;

try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println("Driver: " + metadata.getDriverName());
    System.out.println("Driver version: "
        + metadata.getDriverVersion());
    System.out.println("Database: " + metadata.getDatabaseProductName());
    System.out.println("Server version: "
        + metadata.getDatabaseProductVersion());
    System.out.println("URL: " + metadata.getURL());
}
~~~

Do not log the metadata URL if the URL might contain sensitive configuration details. With modern drivers, metadata can confirm that the runtime loaded the expected Connector/J version and connected to the expected server version.

Inspect the MySQL session:

~~~sql
SELECT
  @@hostname AS server_host,
  @@port AS server_port,
  @@version AS server_version,
  @@session.time_zone AS session_time_zone,
  @@character_set_connection AS connection_charset,
  @@collation_connection AS connection_collation;
~~~

Compare the output against expected configuration. If the URL sets timezone UTC but session time_zone is not UTC, review connectionTimeZone, forceConnectionTimeZoneToSession, session initialization, and server configuration.

## 14. Diagnosing Common Connection Errors

| Error | Possible causes | How to check |
|---|---|---|
| No suitable driver | Connector/J missing at runtime, wrong URL prefix, or invisible to classloader | Verify runtime dependencies and jdbc:mysql: URL |
| Communications link failure | DNS, firewall, routing, server down, timeout, or connection closed mid-flight | Check hostname, TCP port, server logs, network, and timeouts |
| Access denied for user | Wrong password, user@host mismatch, or missing privileges | Check account, host matching, secrets, and GRANTs |
| Unknown database | Schema in URL does not exist or name is misspelled | Check database existence and access privileges |
| TLS handshake/certificate error | Untrusted CA, expired certificate, or hostname mismatch | Check trust store, SAN, chain, and sslMode |
| Public Key Retrieval is not allowed | Authentication requires public key retrieval under current config | Prefer TLS; consider retrieval only in trusted environments per security policy |
| Unrecognized timezone | Driver/server timezone mismatch or legacy configuration | Check connectionTimeZone, session time_zone, and versions |
| Too many connections | Total connections from applications exceed server capacity | Sum pool sizes, check connection leaks, and check max_connections |
| Pool connection timeout | Pool out of idle connections or connections held too long | Inspect active/idle/pending counts, borrow duration, and transactions |
| Socket timeout during query | Slow query, unstable network, or timeout set too low | Inspect slow queries, execution plans, server load, and socketTimeout |

### 14.1. Distinguishing Network Errors and SQL Errors

A connection error can occur before MySQL receives the SQL statement, during execution, or while returning results to the client. If a connection drops during COMMIT, the application may not know whether the transaction committed successfully.

Do not blindly retry a write operation after a Communications link failure error. First determine the nature of the operation, and use an idempotency key or query business state to verify the outcome. For pure read operations, retrying is usually simpler, though retry counts and backoff limits are still required.

### 14.2. Useful Exception Logging

When handling SQLException, record these fields:

- getSQLState() — standard SQL error classification code.
- getErrorCode() — MySQL vendor error code.
- getMessage() — diagnostic message, with secrets stripped.
- getNextException() — subsequent JDBC exception chain, if any.

Do not log passwords, tokens, full URLs containing secrets, or personal data inside SQL statements. If enabling JDBC logging for investigation, restrict its duration and log access permissions.

## 15. Configuration Mistakes to Avoid

- Embedding usernames/passwords in URLs or source code.
- Using sslMode=DISABLED on untrusted production networks.
- Using PREFERRED when policy mandates TLS and server identity verification.
- Enabling allowPublicKeyRetrieval to bypass certificate issues without assessing risk.
- Creating a new DataSource or connection pool on every request.
- Setting very large pool sizes per instance without calculating system-wide total connections.
- Holding a Connection indefinitely in a cache, static field, or thread-local.
- Failing to close ResultSet, Statement, or Connection.
- Setting timeouts too low, causing valid queries to be aborted.
- Enabling multi-query or performance properties without genuine need and testing.
- Using a multi-host URL and assuming it replaces a router, quorum, or topology failover mechanism.
- Retrying non-idempotent transactions after connection loss without verifying commit status.

## 16. Pre-Production Configuration Checklist

### Driver and URL

- [ ] Connector/J is included in the runtime artifact and compatible with Java.
- [ ] JDBC URL uses the correct hostname, port, database, and URL type.
- [ ] Properties are specified clearly without duplicates or conflicts.
- [ ] Special characters in property values do not break the URL parser.

### Security

- [ ] Credentials are retrieved from a secret manager or approved provisioning mechanism.
- [ ] TLS is enabled per policy; CA and hostname are verified as required.
- [ ] Trust store/client certificates are managed and have a rotation plan.
- [ ] Secrets are never written to logs or exception reports.

### Connections and Pooling

- [ ] Selected DriverManager, DataSource, or pooled DataSource according to workload.
- [ ] DataSource is created once with a clear lifecycle.
- [ ] Pool size is calculated across all instances and workers.
- [ ] connectTimeout, socketTimeout, and pool connectionTimeout are appropriate.
- [ ] Connections are closed after every unit of work.
- [ ] Transactions are short and handle uncertain commit errors.

### Data and Operations

- [ ] Timezone and character set are verified at the session level.
- [ ] PreparedStatement is used for input parameters.
- [ ] Batch/prepared statement settings are benchmarked if enabled.
- [ ] Pool metrics, timeouts, connection creation, and SQL latency are monitored.
- [ ] Runbooks exist for DNS, TLS, authentication, connection leaks, and database failover.

## 17. Hands-On Exercise

You are tasked with connecting a Java retail application to MySQL production and staging. The two environments use different hostnames, credentials, certificates, and databases. The application runs 6 API instances and 3 workers, and requires connection pooling.

Perform the following in a lab environment:

1. Add a MySQL Connector/J dependency compatible with your Java runtime.
2. Write separate JDBC URLs for staging and production using TLS with hostname verification.
3. Create a MysqlDataSource, passing user/password separately via a secret manager or environment variables.
4. Execute a SELECT using PreparedStatement and close all resources with try-with-resources.
5. Integrate HikariCP, set a small initial pool size, and configure separate timeouts for the pool and driver.
6. Run concurrent requests and observe active/idle/pending connections and MySQL Threads_connected.
7. Stop MySQL or block TCP in the lab and observe connect timeout and pool timeout.
8. Test a certificate with a mismatched hostname and confirm VERIFY_IDENTITY rejects the connection.
9. Verify timezone, charset, and current database using session variables.
10. Document driver version, server version, timeout settings, and expected maximum connections when all 9 processes run concurrently.

**Self-check questions:**

1. How does a JDBC URL differ in role from a DataSource?
2. Why does MysqlDataSource not equate to a connection pool?
3. How does connectTimeout differ from HikariCP's connectionTimeout?
4. Why is sslMode=VERIFY_IDENTITY stronger than merely requiring TLS?
5. Why should passwords not be placed in a JDBC URL?
6. Does connectionTimeZone always change session time_zone?
7. Why is the total pool size across all instances more important than a single instance's pool size?
8. When a connection drops during COMMIT, why can't every statement be retried automatically?
9. When should you use a JNDI DataSource managed by an application server?
10. When should a multi-host URL be replaced by an endpoint managed by MySQL Router?

## Conclusion

A JDBC URL describes the connection target and Connector/J properties; DataSource provides a standard abstraction for applications to obtain Connections; a connection pool manages reuse of physical connections. A secure MySQL configuration separates credentials, enables appropriate TLS, sets timeouts at the proper layer, aligns timezones/charsets, and bounds pools by total load. Always verify actual configuration from JDBC metadata and the MySQL session, and handle connection errors at transaction boundaries to avoid executing write transactions multiple times.

## References

- [MySQL Connector/J Developer Guide — Driver/Datasource Class Names](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-driver-name.html)
- [MySQL Connector/J Developer Guide — Connecting to MySQL Using JDBC](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-connect-drivermanager.html)
- [MySQL Connector/J Developer Guide — Configuration Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-configuration-properties.html)
- [MySQL Connector/J Developer Guide — Using JDBC Data Sources](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-j2ee-concepts-datasource.html)
- [MySQL Connector/J Developer Guide — Connection Pooling](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-j2ee-concepts-connection-pooling.html)
- [MySQL Connector/J Developer Guide — TLS/SSL Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-security.html)
