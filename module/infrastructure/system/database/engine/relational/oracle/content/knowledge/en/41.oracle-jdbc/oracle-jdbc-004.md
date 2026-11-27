# OracleDataSource, Connection Properties, and Secret Management

## 1. OracleDataSource in JDBC architecture

JDBC provides the standard javax.sql.DataSource interface for applications to obtain database connections. Oracle implements this interface with the **oracle.jdbc.pool.OracleDataSource** class.

OracleDataSource consolidates connection configuration into a single object:

- Database URL or separate host, port, and service name components.
- Driver type.
- Database username.
- Password or an alternative authentication mechanism.
- Oracle JDBC connection properties.
- Login timeout and log writer.

Applications call getConnection() to create a JDBC Connection. A DataSource can also be bound into JNDI so an application server or framework can provide it to applications by logical name.

What must be distinguished immediately:

- **OracleDataSource** is a DataSource that creates physical connections; by itself, it is not a general-purpose connection pool.
- **Universal Connection Pool (UCP)** provides a pool-enabled DataSource for borrowing/returning connections and managing the pool lifecycle.
- **JNDI** is a naming/lookup mechanism for an already configured DataSource, typically managed by an application server or container.

In small applications or short-lived tasks, OracleDataSource may suffice. For web applications or services handling many requests, use UCP or an application-server-managed connection pool to reuse connections, bound session counts, and handle broken connections.

## 2. Important classes and interfaces

| Class/interface | Role |
| --- | --- |
| javax.sql.DataSource | Standard JDBC interface for obtaining a Connection |
| oracle.jdbc.pool.OracleDataSource | Oracle implementation of DataSource |
| oracle.jdbc.OracleConnection | JDBC Connection extending Oracle-specific features |
| oracle.ucp.jdbc.PoolDataSource | UCP DataSource used to borrow connections from a pool |
| oracle.ucp.jdbc.PoolDataSourceFactory | Factory that creates PoolDataSource |
| oracle.jdbc.xa.client.OracleXADataSource | Oracle XA connection factory |
| javax.naming.Context | JNDI naming context |

Typical imports:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import oracle.jdbc.pool.OracleDataSource;
~~~

The Oracle JDBC driver JAR must be on the runtime classpath/module path. If using UCP, add a UCP JAR compatible with the Oracle JDBC driver and the running JDK.

### 2.1. OracleDataSource does not replace JDBC Connection

DataSource is a factory. Each call to getConnection() obtains a Connection to execute SQL:

~~~java
OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc");
dataSource.setUser("APP_RUNTIME");
dataSource.setPassword(passwordFromSecretStore);

try (Connection connection = dataSource.getConnection()) {
    // Perform JDBC work.
}
~~~

In the example, passwordFromSecretStore is a value retrieved from a secret source at runtime. Never put real passwords in source code or commit configuration files containing passwords.

### 2.2. Why is DataSource recommended?

DataSource:

- Separates connection configuration from query logic.
- Can be configured using JavaBeans setters.
- Can be bound/looked up via JNDI.
- Supports pooling configuration via a pool-enabled DataSource.
- Reduces direct dependency on DriverManager inside business code.

DriverManager still exists and can still be used, but DataSource is more convenient for enterprise applications, dependency injection, and container-managed resources.

## 3. Creating OracleDataSource and opening connections

### 3.1. Configuring with URL and setters

JDBC Thin example:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import oracle.jdbc.pool.OracleDataSource;

public final class OracleConnectionFactory {
    private OracleConnectionFactory() {
    }

    public static Connection open(
            String username,
            String password) throws SQLException {

        OracleDataSource dataSource = new OracleDataSource();
        dataSource.setURL(
            "jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc"
        );
        dataSource.setUser(username);
        dataSource.setPassword(password);

        return dataSource.getConnection();
    }
}
~~~

In real applications, do not instantiate a new OracleDataSource for every request. Configure the DataSource once at application startup, then share the DataSource or let the container manage it.

### 3.2. Configuring with host/port/service properties

OracleDataSource exposes setters:

~~~java
OracleDataSource dataSource = new OracleDataSource();
dataSource.setDriverType("thin");
dataSource.setServerName("dbhost.example.com");
dataSource.setPortNumber(1521);
dataSource.setServiceName("appsvc.example.com");
dataSource.setUser("APP_RUNTIME");
dataSource.setPassword(passwordFromSecretStore);

try (Connection connection = dataSource.getConnection()) {
    // JDBC work.
}
~~~

This approach uses discrete properties. Once a URL is set, Oracle JDBC ignores serverName, portNumber, networkProtocol, databaseName, driverType, and tnsEntry according to DataSource precedence rules. Do not configure both a URL and a conflicting set of discrete properties expecting the driver to merge them.

### 3.3. Configuring with Properties

OracleDataSource supports setConnectionProperties(Properties) to pass Oracle JDBC connection properties:

~~~java
import java.sql.Connection;
import java.util.Properties;
import oracle.jdbc.pool.OracleDataSource;

Properties properties = new Properties();
properties.setProperty("user", "APP_RUNTIME");
properties.setProperty("password", passwordFromSecretStore);
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "5");
properties.setProperty("oracle.net.OUTBOUND_CONNECT_TIMEOUT", "10");
properties.setProperty("oracle.jdbc.ReadTimeout", "30000");

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc");
dataSource.setConnectionProperties(properties);

try (Connection connection = dataSource.getConnection()) {
    // JDBC work.
}
~~~

Property names, units, and support depend on driver type and version. Do not copy JDBC Thin properties to OCI or another driver version without checking the Oracle JDBC API Reference.

### 3.4. Using getConnection(username, password)

DataSource provides an overload:

~~~java
Connection connection = dataSource.getConnection(
    runtimeUsername,
    runtimePassword
);
~~~

The username/password passed to getConnection takes precedence over username/password properties already set on the DataSource. This is useful when the same DataSource factory needs to open connections with different credentials, though you must consider connection pooling and credential isolation.

Do not share a single pool across multiple end users unless the pool is designed to isolate identity, privileges, and session state per credential.

## 4. OracleDataSource properties

### 4.1. Standard properties

Common properties per Oracle JDBC 19c:

| Property | Type | Meaning |
| --- | --- | --- |
| databaseName | String | Database name under the discrete property model |
| dataSourceName | String | Underlying data source name |
| description | String | DataSource description |
| networkProtocol | String | Network protocol; primarily applicable to OCI |
| password | String | Password for the connecting user |
| portNumber | int | Listener port |
| serverName | String | Host/server |
| user | String | Database username |
| loginTimeout | int | Maximum time to wait to create a connection, in seconds |
| logWriter | PrintWriter | Output target for DataSource logs |

For security reasons, OracleDataSource does not provide getPassword(). Do not attempt to read the password back from the object after configuration.

### 4.2. Oracle extension properties

Some common extension properties:

| Property | Meaning |
| --- | --- |
| driverType | thin, oci, or kprb |
| url | JDBC URL |
| serviceName | Oracle database service name |
| tnsEntry | TNS alias in tnsnames.ora |
| connectionProperties | Properties for connections |
| connectionCachingEnabled | Configuration for legacy implicit connection cache |
| connectionCacheName | Name of legacy implicit cache |
| fastConnectionFailoverEnabled | Fast Connection Failover for the corresponding cache/pool mechanism |
| ONSConfiguration | ONS/FAN notification configuration |
| maxStatements | Statement cache property in the corresponding mechanism |

Properties related to the legacy implicit connection cache should not be chosen as the foundation for a new pool design. For applications requiring pooling, evaluate UCP or an application-server-managed pool.

### 4.3. setConnectionProperties and setConnectionCacheProperties

The two methods serve different purposes:

- setConnectionProperties: configures properties for connections created by the factory.
- setConnectionCacheProperties: configures the legacy OracleDataSource cache in corresponding legacy models.

Do not place pool sizing settings like minPoolSize/maxPoolSize inside OracleDataSource's connectionProperties. Pool sizing is the responsibility of UCP or the application server.

## 5. JDBC URLs: service name, SID, and TNS alias

### 5.1. Easy Connect with SERVICE_NAME

Common format:

~~~text
jdbc:oracle:thin:@//host:port/service_name
~~~

Example:

~~~text
jdbc:oracle:thin:@//dbhost.example.com:1521/sales.example.com
~~~

This format suits service-based connections, PDB services, and many RAC architectures.

### 5.2. TNS alias

~~~text
jdbc:oracle:thin:@APPDB
~~~

In tnsnames.ora:

~~~text
APPDB =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = dbhost.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = appsvc.example.com)
    )
  )
~~~

To let the driver locate tnsnames.ora, configure the Oracle Net admin directory:

~~~java
Properties properties = new Properties();
properties.setProperty(
    "oracle.net.tns_admin",
    "/opt/app/oracle/network/admin"
);

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@APPDB");
dataSource.setConnectionProperties(properties);
~~~

The path must exist on the host/container running the application. Do not assume Oracle JDBC will read the right TNS directory merely because the DBA workstation has ORACLE_HOME.

### 5.3. Full connect descriptor

When multiple addresses, retries, or Oracle Net options are required:

~~~text
jdbc:oracle:thin:@
(DESCRIPTION =
  (CONNECT_TIMEOUT = 10)
  (TRANSPORT_CONNECT_TIMEOUT = 5)
  (RETRY_COUNT = 3)
  (ADDRESS_LIST =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = dbnode1.example.com)
      (PORT = 1521)
    )
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = dbnode2.example.com)
      (PORT = 1521)
    )
  )
  (CONNECT_DATA =
    (SERVICE_NAME = appsvc.example.com)
  )
)
~~~

Connect descriptors let you declare multiple endpoints and timeouts/retries at the Oracle Net layer. Ensure the addresses genuinely serve the same service or are configured appropriately for load balancing/failover.

### 5.4. Legacy SID syntax

Some legacy connections use:

~~~text
jdbc:oracle:thin:@host:1521:ORCL
~~~

The trailing segment is a SID, not a service name. For RAC, PDBs, or applications needing service-based routing, use SERVICE_NAME rather than hardcoding a SID/instance.

### 5.5. Service name and SID are not the same

| Concept | Meaning |
| --- | --- |
| SID | Oracle instance identifier |
| SERVICE_NAME | Database service requested by the client |
| TNS alias | Logical name pointing to a connect descriptor |
| Host/port | Listener network endpoint |

In a RAC environment, a service can run across multiple instances and be relocated. If an application hardcodes a SID, its ability to leverage service management, load balancing, and failover is reduced.

### 5.6. URLs should not contain credentials

Do not write:

~~~text
jdbc:oracle:thin:APP_RUNTIME/password@//dbhost:1521/appsvc
~~~

URLs can appear in logs, exceptions, metrics, process lists, configuration dumps, or monitoring tools. Keep only the endpoint/service in the URL; pass credentials via a secret provider, wallet, or appropriate authentication mechanism.

## 6. Driver types: Thin, OCI, and KPRB

| Driver type | Characteristics | When to use |
| --- | --- | --- |
| Thin | Pure Java driver, connects directly via Oracle Net | Common choice for Java applications |
| OCI | Uses Oracle Client/native OCI libraries | When features or environments depend on OCI |
| KPRB | Internal server-side driver for internal connections | Java running inside the Oracle Database JVM |

For Java applications running outside the database, JDBC Thin is usually simplest because it requires no Oracle Client installation on the application host.

OCI requires native libraries and matching Oracle Client configuration. If choosing OCI, verify ORACLE_HOME, PATH/LD_LIBRARY_PATH, bitness, native library versions, and Oracle Net configuration.

KPRB is an internal driver; normal connection properties may be ignored. Do not use KPRB as a substitute for Thin in applications running on an application server.

## 7. Property precedence and conflicts

This is a common reason applications connect as the wrong user or to the wrong database.

### 7.1. User/password in the URL

If the URL contains username/password, those values may override user/password configured separately on the DataSource.

Do not put credentials in the URL to avoid discrete settings being silently ignored and to prevent secret exposure.

### 7.2. getConnection(username, password)

Credentials passed to the getConnection(username, password) overload take precedence over username/password properties already set on the DataSource.

### 7.3. URL overrides discrete properties

When the url property is set, tnsEntry, driverType, portNumber, networkProtocol, serverName, and databaseName are ignored according to Oracle JDBC rules.

When tnsEntry is set and URL is not set, databaseName, serverName, portNumber, and networkProtocol are ignored.

### 7.4. KPRB

If driverType is kprb, other property settings are ignored because the driver uses an implicit internal connection.

### 7.5. Easy-to-control configuration rules

Pick one clear configuration style:

1. One complete URL, without credentials.
2. One separate credential source.
3. One intentional group of connection properties.
4. Never declare two different values for the same endpoint detail.

After configuring, verify the session:

~~~sql
SELECT USER AS database_user,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

## 8. Important connection properties

Not every property needs to be configured. Add one only when there is a measurable requirement verified against your Oracle JDBC version.

### 8.1. Timeouts during connection creation

| Property | Unit | Scope |
| --- | --- | --- |
| DataSource loginTimeout | Seconds | Maximum time DataSource waits to open a connection |
| oracle.net.CONNECT_TIMEOUT | Seconds | Time to establish socket connection to the listener |
| oracle.net.OUTBOUND_CONNECT_TIMEOUT | Seconds | Time for session setup/network negotiation with the service |
| UCP connectionWaitTimeout | Seconds | Time waiting for a connection to be returned to the pool |

CONNECT_TIMEOUT succeeding only means the listener accepted the socket connection; it does not prove the database service is ready or authentication completed.

OUTBOUND_CONNECT_TIMEOUT covers connection and session negotiation per Oracle Net, excluding every stage of authentication.

UCP connectionWaitTimeout is the time spent waiting to borrow a connection when the pool is at max size and none are free. It differs from the listener connect timeout.

### 8.2. Read timeout

The Thin driver supports:

~~~java
properties.setProperty("oracle.jdbc.ReadTimeout", "30000");
~~~

The value is in milliseconds. Read timeout limits socket read waiting time. It is not a statement execution timeout in the sense that the database will always halt SQL exactly on schedule.

Oracle JDBC notes that ReadTimeout and Connection.setNetworkTimeout may interact with legacy Dead Connection Detection settings. Verify DCD/Oracle Net and test in your exact environment.

### 8.3. Statement query timeout

JDBC provides:

~~~java
try (var statement = connection.createStatement()) {
    statement.setQueryTimeout(30);
    statement.executeQuery("SELECT 1 FROM dual");
}
~~~

setQueryTimeout sets a statement duration; the driver typically uses a cancel mechanism to ask the server to stop. If the network or database server hangs, cancel may not immediately release the thread right at the timeout mark.

Do not conflate:

- Login timeout.
- Socket connect timeout.
- Session negotiation timeout.
- Socket read timeout.
- Statement query timeout.
- Pool borrow timeout.
- Application HTTP request timeout.

Timeouts must be coordinated under a unified time budget.

### 8.4. Timeout configuration example

~~~java
Properties properties = new Properties();
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "5");
properties.setProperty("oracle.net.OUTBOUND_CONNECT_TIMEOUT", "10");
properties.setProperty("oracle.jdbc.ReadTimeout", "30000");

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc");
dataSource.setLoginTimeout(15);
dataSource.setConnectionProperties(properties);
~~~

Numbers are illustrative only. If the connect descriptor specifies CONNECT_TIMEOUT or TRANSPORT_CONNECT_TIMEOUT, values in the URL/descriptor may take precedence over the corresponding property.

### 8.5. TNS_ADMIN

Property:

~~~java
properties.setProperty(
    "oracle.net.tns_admin",
    "/opt/app/oracle/network/admin"
);
~~~

Points to the directory containing tnsnames.ora, sqlnet.ora, and required Oracle Net files. Do not hardcode this path in the repository if each environment has a different filesystem layout; supply it via deployment configuration.

### 8.6. Row prefetch and batching

Oracle JDBC includes extension properties such as defaultRowPrefetch and defaultBatchValue. They can affect how much data the driver prefetches or batching behavior.

~~~java
properties.setProperty("defaultRowPrefetch", "100");
~~~

Do not increase prefetch arbitrarily. Large ResultSets, LOBs/streaming, WAN links, and heap limits can cause overly high values to increase memory pressure. Measure round trips, heap usage, response size, and latency before changing it.

### 8.7. Network compression

Oracle JDBC Thin since 12.2 supports network data compression:

~~~java
properties.setProperty("oracle.net.networkCompression", "on");
properties.setProperty("oracle.net.networkCompressionThreshold", "1024");
~~~

Compression can help over WANs with large payloads, but it incurs CPU cost and does not apply to streamed data per Oracle documentation. Benchmark before enabling it for all workloads.

## 9. Managing connection secrets

Database passwords are high-value secrets. If an application account's password leaks, an attacker can access data or perform actions within that account's privileges.

Principles:

- Do not hardcode passwords in Java source.
- Do not commit passwords to Git.
- Do not embed passwords in JDBC URLs.
- Do not log passwords, tokens, or wallet passwords.
- Do not print Properties objects containing credentials to the console.
- Do not store secrets in unencrypted .properties files on shared filesystems.
- Use a dedicated account per application or service.
- Grant least privilege to runtime accounts.
- Have rotation, revocation, and incident response processes for leaked secrets.

### 9.1. Recommended secret sources

Preferred by architecture:

1. Oracle Secure External Password Store (client-side wallet).
2. Cloud or deployment platform secret manager.
3. Secret store managed by the application server/container.
4. Organization-managed credential provider with ACL controls and rotation.

Environment variables can be used to inject configuration in some environments, but understand that they can still leak via process inspection, crash dumps, diagnostics, or deployment configurations. Do not treat environment variables as an automatically secure vault.

### 9.2. Do not put passwords in plain config files

Avoid:

~~~properties
db.url=jdbc:oracle:thin:@//dbhost:1521/appsvc
db.user=APP_RUNTIME
db.password=VerySecretPassword
~~~

The file can be read by OS users, backup agents, CI logs, or committed by mistake.

Separate endpoint and username from the password:

~~~properties
db.url=jdbc:oracle:thin:@//dbhost:1521/appsvc
db.user=APP_RUNTIME
db.secretRef=prod/oracle/app-runtime
~~~

The application reads secretRef from the secret provider at startup or via the platform's rotation mechanism.

### 9.3. Passing passwords via runtime variables

~~~java
String username = configuration.get("db.user");
String password = secretProvider.read("prod/oracle/app-runtime");

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL(configuration.get("db.url"));
dataSource.setUser(username);
dataSource.setPassword(password);
~~~

Here secretProvider is an application abstraction. Do not log the password and limit the lifetime of copies in memory where possible. Java Strings cannot be zeroed out directly; if tighter buffer control is needed, use secret provider APIs supporting char[]/credential objects and manage their lifecycle.

## 10. Oracle Wallet and Secure External Password Store

### 10.1. Two purposes of a wallet

An Oracle wallet can hold:

- Username/password credentials for Secure External Password Store.
- Certificates and private keys for TLS/mTLS.

Credential store and PKI store are two distinct purposes, even though both can reside in one wallet container depending on setup. Distinguish a wallet used for password-based database login from a wallet used for certificate verification.

### 10.2. Why use Secure External Password Store?

Secure External Password Store stores credentials in a client-side Oracle wallet. The JDBC driver can retrieve username/password from the wallet instead of requiring applications to embed credentials in source code, batch jobs, or scripts.

Benefits:

- No need to store passwords in Java source.
- Credentials in the wallet can be rotated without modifying application code.
- Supports centralized credential management for batch/application clients.
- Wallet files can be restricted to owner-only read permissions.

A wallet is still a secret. If an auto-login wallet is stolen and an attacker can use it in the right environment, credentials can be abused. Protect files, directories, backups, and OS permissions.

### 10.3. Creating a wallet

Example on a client host:

~~~text
mkstore -wrl /opt/app/oracle/wallet -create
~~~

mkstore prompts for the wallet password. Do not pass the wallet password as a command-line argument that could be captured in shell history or process lists.

### 10.4. Creating credentials for a database service

~~~text
mkstore -wrl /opt/app/oracle/wallet
  -createCredential APPDB APP_RUNTIME
~~~

The command prompts for the database password. APPDB must be a connect identifier/TNS alias/service string matching the name used when connecting.

List credentials:

~~~text
mkstore -wrl /opt/app/oracle/wallet -listCredential
~~~

The list shows aliases and usernames, without displaying passwords.

### 10.5. Configuring a wallet for JDBC

Oracle JDBC 19c supports the connection property:

~~~text
oracle.net.wallet_location
~~~

Example:

~~~java
Properties properties = new Properties();
properties.setProperty(
    "oracle.net.wallet_location",
    "(SOURCE=(METHOD=FILE)(METHOD_DATA=(DIRECTORY=/opt/app/oracle/wallet)))"
);

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@APPDB");
dataSource.setConnectionProperties(properties);

try (Connection connection = dataSource.getConnection()) {
    // Driver retrieves the credential from the wallet.
}
~~~

In the example, user/password are not set in the URL or Properties. Oracle JDBC looks for credentials in Properties first, then the URL, and only then the wallet. Thus, if a password is still declared directly, the wallet may not be used.

Wallet location can be specified as a file URI or an Oracle Net descriptor. Verify syntax with your exact JDBC driver.

### 10.6. PKCS12 and auto-login wallets

An auto-login wallet typically has a cwallet.sso file. A PKCS12 wallet may require the wallet password via the oracle.net.wallet_password property if auto-login is not enabled.

Do not store wallet passwords in source code. When using an auto-login wallet, strictly control the cwallet.sso file and directory permissions.

### 10.7. Credential rotation in a wallet

High-level workflow:

1. DBA changes the database password per schedule.
2. Update the corresponding credential in the wallet using mkstore.
3. Verify the application can open new connections.
4. Drain/refresh the pool to remove connections that need replacement.
5. Verify no authentication errors appear in logs.
6. Revoke/remove the old credential per policy.

Credentials already used by the pool when physical connections were created may remain in the pool. Updating the password in the wallet does not automatically turn existing connections into new ones.

## 11. TLS and TCPS

### 11.1. TCP and TCPS

- TCP is standard transport, which can be combined with Oracle Native Network Encryption/Integrity.
- TCPS is the Oracle Net protocol using TLS to protect the network channel and authenticate server/client per configuration.

Connect descriptor example:

~~~text
jdbc:oracle:thin:@
(DESCRIPTION =
  (ADDRESS =
    (PROTOCOL = TCPS)
    (HOST = db.example.com)
    (PORT = 2484)
  )
  (CONNECT_DATA =
    (SERVICE_NAME = appsvc.example.com)
  )
  (SECURITY =
    (TLS_SERVER_DN_MATCH = TRUE)
  )
)
~~~

Port 2484 is just an example; use the actual TCPS listener port.

### 11.2. Server DN matching

DN matching helps the client verify that the certificate belongs to the expected server. If you only validate the certificate chain without checking server identity, the client could mistakenly trust an endpoint with a valid certificate that is not the intended database.

Oracle recommends enabling TLS_SERVER_DN_MATCH and configuring host/DN to match the certificate. For full DN matching, use TLS_SERVER_CERT_DN per Oracle documentation. From Oracle Database 19c Release 2 onward, partial DN matching behavior has been tightened; do not assume SERVICE_NAME is always used in place of hostname.

### 11.3. One-way TLS and mutual TLS

| Type | Description |
| --- | --- |
| One-way TLS | Client verifies the server's certificate |
| Mutual TLS (mTLS) | Client and server verify each other's certificates |

One-way TLS typically only requires trusting the server certificate. mTLS requires a client certificate/private key, and the server must be configured to require or allow client authentication.

### 11.4. Wallets for TLS

Oracle JDBC Thin uses JSSE and can use an Oracle wallet as a truststore/keystore depending on configuration. With TCPS, the wallet can hold CA certificates and client certificates if using mTLS.

Do not disable certificate validation just to make a connection succeed. If the TLS handshake fails:

1. Check the certificate chain.
2. Check hostname/DN.
3. Check expiry and system clock.
4. Check wallet location/permissions.
5. Verify the listener uses TCPS on the right port.
6. Check client/server TLS version and cipher policy.

## 12. Connection pooling with UCP

### 12.1. Why is a pool needed?

Creating a new database connection incurs network handshake, authentication, session initialization, and resource allocation overhead. For web applications, creating a new connection per request increases latency and session churn.

A pool maintains a set of physical connections and lends connection handles to requests. When the application closes the handle, the connection is typically returned to the pool for reuse by other requests.

Oracle Universal Connection Pool provides a pool-enabled DataSource:

- oracle.ucp.jdbc.PoolDataSource.
- oracle.ucp.jdbc.PoolDataSourceFactory.

UCP uses OracleDataSource as its connection factory to create physical connections.

### 12.2. UCP configuration example

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import oracle.ucp.jdbc.PoolDataSource;
import oracle.ucp.jdbc.PoolDataSourceFactory;

public final class UcpFactory {
    private UcpFactory() {
    }

    public static PoolDataSource create(
            String username,
            String password) throws SQLException {

        PoolDataSource pool =
            PoolDataSourceFactory.getPoolDataSource();

        pool.setConnectionFactoryClassName(
            "oracle.jdbc.pool.OracleDataSource"
        );
        pool.setURL(
            "jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc"
        );
        pool.setUser(username);
        pool.setPassword(password);

        pool.setConnectionPoolName("APP_POOL");
        pool.setInitialPoolSize(2);
        pool.setMinPoolSize(2);
        pool.setMaxPoolSize(20);
        pool.setConnectionWaitTimeout(10);

        return pool;
    }
}
~~~

Min/max values are illustrative only. Sum the maximum connections across all application replicas, batch workers, and services before setting maxPoolSize.

### 12.3. Borrowing and returning connections

~~~java
try (Connection connection = pool.getConnection()) {
    // Execute SQL and finish the transaction.
}
~~~

With UCP, closing the connection handle returns the connection to the pool. Do not keep connections in static fields or share the same Connection concurrently across multiple threads.

### 12.4. Commonly used pool properties

| Property | Meaning |
| --- | --- |
| initialPoolSize | Initial number of connections |
| minPoolSize | Minimum number of connections |
| maxPoolSize | Maximum number of connections |
| connectionWaitTimeout | Time to wait for a connection to be returned to the pool |
| inactiveConnectionTimeout | Time an idle connection can stay in the pool before being closed |
| abandonedConnectionTimeout | Time a borrowed connection stays inactive before being considered abandoned |
| validateConnectionOnBorrow | Validate connection upon borrowing |
| SQLForValidateConnection | SQL used to validate when validate on borrow is enabled |
| timeToLiveConnectionTimeout | Maximum age a connection may stay in the borrowed state |
| maxConnectionReuseTime | Maximum time a connection is reused per configuration |

Do not enable every timeout simultaneously without understanding interactions. An abandoned connection timeout that is too low can reclaim a connection from a valid long-running request.

### 12.5. Validating connections

Example:

~~~java
pool.setValidateConnectionOnBorrow(true);
pool.setSQLForValidateConnection("SELECT 1 FROM DUAL");
~~~

Validation helps detect stale connections before handing them to a request. However, validating on every borrow incurs round-trip overhead. UCP offers validation and stale-connection handling mechanisms; choose settings based on network/firewall/HA requirements.

### 12.6. Pool sizing

Suppose:

- 4 application replicas.
- Each replica has maxPoolSize = 30.
- 2 batch workers, each with max 5 connections.

Potential total:

~~~text
4 × 30 + 2 × 5 = 130 connections
~~~

The database must have enough processes/sessions/resources for the combined load from all clients, not just a single application instance. Consider services, RAC instance distribution, background sessions, DBA sessions, and other applications.

### 12.7. Do not use legacy implicit cache for new pools

OracleDataSource has legacy cache properties. For new designs, use UCP or an application server pool with clear lifecycle/metrics/validation rather than building a custom pool or relying on old cache APIs.

## 13. JNDI and application servers

### 13.1. JNDI logical names

JNDI lets applications look up a DataSource by logical name:

~~~java
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.sql.DataSource;
import java.sql.Connection;

Context context = new InitialContext();
DataSource dataSource =
    (DataSource) context.lookup("java:comp/env/jdbc/AppDB");

try (Connection connection = dataSource.getConnection()) {
    // JDBC work.
}
~~~

The JNDI name is declared in the application server/container. The application does not need to hardcode host, port, password, or pool sizing in code.

### 13.2. Container-managed DataSource

In an enterprise environment:

1. DBA/platform admin creates the database service and account.
2. Application server configures the JDBC DataSource/UCP pool.
3. Credentials are stored in a credential store/encrypted configuration.
4. Application injects or looks up the DataSource via JNDI.
5. Container manages pool lifecycle, monitoring, and connection validation.

This is usually easier to operate than having every web request create its own OracleDataSource.

### 13.3. JNDI does not automatically encrypt passwords

Binding a DataSource into JNDI does not automatically secure passwords. If the application server serializes or saves DataSource configuration to files, use the server's credential store/encryption mechanism and restrict file read permissions.

Do not place plaintext passwords in deployment descriptors or XML files when the platform provides a secret/credential store.

## 14. Credential rotation and lifecycle

### 14.1. Password rotation

When a database password changes:

1. Identify applications and pools using that account.
2. Prepare the new credential in the secret manager/wallet.
3. Execute the password change via database procedure.
4. Update the secret reference/credential store.
5. Refresh or drain the pool so new connections use the new credential.
6. Verify new connection creation and authentication.
7. Monitor for ORA-01017 or related login failures.

If you change the password on the database before updating the secret, new connections may fail during the transition window. Design rotation with a grace/transition window if supported by the system.

### 14.2. Old connections and new connections

Passwords are only used during authentication when creating a new session. Already-authenticated connections may continue working after a password change, depending on session state and policy. Therefore, rotating the secret does not mean every physical connection in the pool has been replaced.

### 14.3. Separate accounts per application

Do not share a single schema owner or SYS across multiple applications. Create dedicated runtime accounts, grant only needed privileges, and ensure you can lock/rotate one application's credential without impacting all other clients.

### 14.4. Do not use SYS in application runtime

SYS/SYSDBA holds special administrative privileges. Never configure a SYS password in a business application's OracleDataSource. When administrative operations are needed, use a dedicated admin account, privileged workflows, and auditing.

## 15. Network, service, and HA

### 15.1. Connecting by service

A service is the logical routing point for a workload. Services can be configured with:

- Preferred/available instances.
- Load balancing.
- Failover.
- FAN/ONS notifications.
- Draining for planned maintenance.
- Application Continuity/TAC if configured.

Applications should use a stable service name rather than a specific instance's SID.

### 15.2. FAN and UCP

UCP can receive FAN events to react when services/instances change. For RAC/HA, configure ONS/FAN and Fast Connection Failover aligned with the database/service topology.

Do not simply enable fastConnectionFailoverEnabled while ignoring ONS, service configuration, and pool support.

### 15.3. Retrying connections is not retrying transactions

Retrying new connection creation can make sense when a listener or network temporarily fails. Retrying a transaction after losing a COMMIT response is another matter: the client may not know whether the transaction committed.

Do not write blind retry loops for every SQLException. Classify errors, transaction outcomes, idempotency, and Application Continuity/Transaction Guard if supported by the system.

## 16. Data protection and application account privileges

### 16.1. Least privilege

Runtime accounts should only have:

- CREATE SESSION.
- Necessary object privileges.
- EXECUTE on business packages/APIs.
- Required sequence or type privileges if used by the app.

Do not grant DBA, SELECT ANY TABLE, or broad DDL privileges to a runtime account just to bypass insufficient privilege errors.

### 16.2. Use package APIs instead of broad DML grants

If an application needs to invoke a set of business operations, you can grant EXECUTE on a package and restrict direct UPDATE/DELETE on sensitive tables. Design definer-rights/invoker-rights appropriately and issue direct grants for stored code when Oracle requires them.

### 16.3. Database auditing

Tag MODULE, ACTION, and CLIENT_IDENTIFIER to trace workloads:

~~~java
try (var statement = connection.createStatement()) {
    statement.execute(
        "BEGIN DBMS_APPLICATION_INFO.SET_MODULE(" +
        "'orders-api', 'create-order'); END;"
    );
}
~~~

CLIENT_IDENTIFIER can be set via DBMS_SESSION.SET_IDENTIFIER to correlate a database session with a logical request/user. Never write passwords, access tokens, or sensitive data into MODULE/ACTION/CLIENT_IDENTIFIER.

## 17. Handling SQLException and diagnosing connections

### 17.1. SQLException

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Work.
} catch (SQLException exception) {
    int errorCode = exception.getErrorCode();
    String sqlState = exception.getSQLState();

    logger.error(
        "Oracle JDBC connection failed. errorCode={}, sqlState={}",
        errorCode,
        sqlState
    );
    throw exception;
}
~~~

Do not log passwords, URLs with embedded credentials, wallet passwords, or Properties containing secrets. You can log a controlled service alias, correlation ID, error code, and SQLState.

### 17.2. Common errors

| Error | Possible cause | Where to check |
| --- | --- | --- |
| ORA-01017 | Invalid username/password | Secret source, username casing, wallet alias, and password rotation |
| ORA-28000 | Account is locked | DBA checks account status and login policy |
| ORA-28001 | Password expired | Password rotation/expiry workflow |
| ORA-12154 | Could not resolve TNS alias | TNS_ADMIN, tnsnames.ora, alias spelling |
| ORA-12514 | Listener does not know requested service | SERVICE_NAME, service registration, listener status |
| ORA-12541 | No listener at endpoint | Host/port, listener, and network |
| ORA-12545 | Host/address does not resolve or exist | DNS, connect descriptor, and network route |
| ORA-29024 | Certificate validation failure | Trust chain, wallet, certificate expiry, and DN match |
| ORA-17002 | I/O/network adapter error | Firewall, socket timeout, listener, database availability |
| ORA-01031 | Insufficient privileges | Direct grants/roles and account permissions |
| SQLRecoverableException | Connection may be lost or unusable | Discard broken connection, resolve transaction outcome, acquire new connection |

An error code alone is insufficient to conclude root cause. Inspect the SQLException chain, Oracle error code, alert log, listener log, and client trace as needed.

### 17.3. Testing the service after connecting

~~~sql
SELECT USER,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

This query helps catch applications connecting to the wrong service, PDB, or instance.

## 18. Configuration examples by scenario

### 18.1. Small application without a pool

~~~java
OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@//dbhost:1521/appsvc");
dataSource.setUser(runtimeUser);
dataSource.setPassword(runtimePassword);
dataSource.setLoginTimeout(15);

try (Connection connection = dataSource.getConnection()) {
    // Run one short task.
}
~~~

Suitable for command-line jobs or low-connection tasks if lifecycle is controlled.

### 18.2. Production application using UCP

~~~java
PoolDataSource pool = PoolDataSourceFactory.getPoolDataSource();
pool.setConnectionFactoryClassName(
    "oracle.jdbc.pool.OracleDataSource"
);
pool.setURL("jdbc:oracle:thin:@//dbhost:1521/appsvc");
pool.setUser(runtimeUser);
pool.setPassword(runtimePassword);
pool.setMinPoolSize(4);
pool.setInitialPoolSize(4);
pool.setMaxPoolSize(24);
pool.setConnectionWaitTimeout(10);
pool.setValidateConnectionOnBorrow(true);
pool.setSQLForValidateConnection("SELECT 1 FROM DUAL");
~~~

Pool sizing must be calculated alongside replica count, batch jobs, background workers, and database session/process limits.

### 18.3. TNS alias and wallet

~~~java
Properties properties = new Properties();
properties.setProperty(
    "oracle.net.tns_admin",
    "/opt/app/oracle/network/admin"
);
properties.setProperty(
    "oracle.net.wallet_location",
    "(SOURCE=(METHOD=FILE)(METHOD_DATA=(DIRECTORY=/opt/app/oracle/wallet)))"
);

OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL("jdbc:oracle:thin:@APPDB");
dataSource.setConnectionProperties(properties);

try (Connection connection = dataSource.getConnection()) {
    // Credentials are obtained from the external password store.
}
~~~

The credential entry in the wallet must use the exact connect identifier APPDB. Do not declare user/password in the URL or Properties if you want the driver to retrieve them from the wallet.

### 18.4. TCPS and DN matching

~~~java
OracleDataSource dataSource = new OracleDataSource();
dataSource.setURL(
    "jdbc:oracle:thin:@(DESCRIPTION=" +
    "(ADDRESS=(PROTOCOL=TCPS)(HOST=db.example.com)(PORT=2484))" +
    "(CONNECT_DATA=(SERVICE_NAME=appsvc.example.com))" +
    "(SECURITY=(TLS_SERVER_DN_MATCH=TRUE)))"
);
dataSource.setUser(runtimeUser);
dataSource.setPassword(runtimePassword);
~~~

Wallet/truststore and server certificates must be configured consistently. If using mTLS, a client certificate/private key is required per server policy.

## 19. Anti-patterns to avoid

| Anti-pattern | Risk | Better approach |
| --- | --- | --- |
| Hardcoding passwords in source | Exposed via Git, source archives, or code review | Secret manager or Oracle wallet |
| Passwords in JDBC URLs | Exposed via logs, process args, or diagnostics | Keep only endpoint/service in URL |
| Creating a DataSource per request | Higher connection overhead and session churn | Singleton/container-managed DataSource |
| Using OracleDataSource as a pool | No general-purpose pool lifecycle | Use UCP/application server pool |
| Hardcoding SID in RAC | Hard to relocate/load-balance services | Use SERVICE_NAME |
| Conflicting URL and host/port properties | Some properties get silently ignored | Choose one explicit configuration style |
| Using SYS for application runtime | Overly broad privileges | Dedicated runtime account, least privilege |
| Logging full Properties | May leak passwords/tokens/wallet paths | Log allowlisted fields only |
| Sharing one Connection across threads | Race conditions and mixed session state | Borrow a separate connection per unit of work |
| Failing to close Connections | Leaks pool slots or server sessions | try-with-resources |
| Uncoordinated timeouts | Requests hang long or time out prematurely | Unified timeout budget |
| Enabling validation on every borrow unmeasured | Adds round trips on borrow | Choose validation based on network/pool behavior |
| Rotating secrets without refreshing pool | Existing/pooled connections keep old state | Controlled pool drain/recycle |
| Blindly retrying after COMMIT error | Transaction may execute twice | Transaction Guard/idempotency |
| Disabling TLS/DN validation to silence errors | Risk of connecting to wrong server | Fix certificates, trust chain, and hostname |

## 20. OracleDataSource deployment checklist

1. **Right driver?** Choose Thin/OCI/KPRB based on runtime location and requirements.
2. **URL using service name?** Prefer services for RAC/PDB/workload routing.
3. **TNS_ADMIN accurate?** Confirm alias files are readable from the runtime host/container.
4. **No credentials in URL?** Separate endpoint from secrets.
5. **Precedence clear?** Avoid conflicting URL and discrete properties.
6. **Connection properties necessary?** Enable only properties with a clear reason.
7. **Timeouts distinguished?** Login, connect, outbound, read, statement, and pool wait.
8. **Secret source appropriate?** Wallet, secret manager, or container credential store.
9. **Wallet permissions restricted?** Readable only by the runtime identity.
10. **TLS/DN matching enabled?** Verify server identity and certificate chain.
11. **Pooling in place?** Production services typically require UCP or container pools.
12. **Total pool size calculated?** Sum all replicas and workers.
13. **Validation/stale connection policy suitable?** Consider firewalls and HA.
14. **Credential rotation workflow defined?** Update secret and refresh pool.
15. **Runtime account follows least privilege?** Never use SYS/DBA.
16. **Connections closed properly?** Use try-with-resources.
17. **Logs free of secret leaks?** Never dump URLs/Properties/credentials.
18. **Service/PDB verified?** Confirm via SYS_CONTEXT.
19. **Tested network/TLS/authentication failures?** Don't test only happy-path connections.
20. **Monitoring pool and database sessions?** Borrow wait, active/available, failures, session count.

## 21. Self-check questions

**Question 1.** What is OracleDataSource?

**Question 2.** Which package contains OracleDataSource?

**Question 3.** How does DataSource differ from Connection?

**Question 4.** Is OracleDataSource a connection pool?

**Question 5.** How does UCP use OracleDataSource?

**Question 6.** How does SERVICE_NAME differ from SID?

**Question 7.** When URL is set, which discrete host/port properties are ignored?

**Question 8.** What precedence does getConnection(username, password) have?

**Question 9.** Why should passwords not be embedded in a JDBC URL?

**Question 10.** What is setConnectionProperties used for?

**Question 11.** How does loginTimeout differ from oracle.net.CONNECT_TIMEOUT?

**Question 12.** What unit does oracle.jdbc.ReadTimeout use?

**Question 13.** Why is ReadTimeout not equivalent to Statement.setQueryTimeout?

**Question 14.** What is TNS_ADMIN used for?

**Question 15.** What problem does Secure External Password Store solve?

**Question 16.** Why does an auto-login wallet still require file protection?

**Question 17.** How can an Oracle wallet be used for both password credentials and TLS?

**Question 18.** Why is TLS_SERVER_DN_MATCH needed?

**Question 19.** How does UCP connectionWaitTimeout differ from connect timeout?

**Question 20.** Why might rotating a password in a secret store not immediately replace every connection in the pool?

<details>
<summary>Suggested answers</summary>

1. Oracle's implementation of JDBC DataSource for configuring and creating database connections.
2. oracle.jdbc.pool.
3. DataSource is a factory; Connection is a JDBC session used to execute SQL.
4. No. It creates physical connections; UCP or an application server pool manages reuse.
5. UCP uses OracleDataSource as its connection factory to create physical connections.
6. SID identifies an instance; SERVICE_NAME identifies a database service.
7. tnsEntry, driverType, portNumber, networkProtocol, serverName, and databaseName.
8. Credentials passed to getConnection take precedence over properties on the DataSource.
9. URLs can appear in logs, process lists, diagnostics, or configuration dumps.
10. Passing Oracle JDBC connection properties.
11. loginTimeout is the DataSource wait time; CONNECT_TIMEOUT is the socket connection time to the listener.
12. Milliseconds.
13. ReadTimeout limits socket reads; query timeout requests statement cancellation and can be affected by network/cancel behavior.
14. Specifies the Oracle Net directory containing tnsnames.ora/sqlnet.ora and related files.
15. Stores username/password in a client wallet instead of embedding them in source code/scripts.
16. Anyone able to read the wallet can use its credentials; ACLs and filesystem protection are required.
17. The password store provides username/password; the PKI wallet holds trust/certificates/private keys for TLS/mTLS.
18. Verifies that the server certificate belongs to the intended endpoint.
19. connectionWaitTimeout waits for a free connection in the pool; connect timeout connects to the listener/service.
20. Already-authenticated physical connections can remain in the pool; draining/refreshing is required to create new connections.

</details>

## 22. Official Oracle documentation

1. [Oracle Database 19c JDBC Developer's Guide — Data Sources and URLs](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/data-sources-and-URLs.html): OracleDataSource, standard/extended properties, JNDI, URLs, and precedence.
2. [Oracle Database 19c JDBC Java API Reference — OracleConnection](https://docs.oracle.com/en/database/oracle/oracle-database/19/jajdb/oracle/jdbc/OracleConnection.html): connection properties, wallets, timeouts, and Oracle JDBC extensions.
3. [Oracle Database 19c JDBC Developer's Guide — JDBC Client-Side Security Features](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/client-side-security.html): wallets, authentication, network encryption, TLS, and Secure External Password Store.
4. [Oracle Database 19c Security Guide — Managing the Secure External Password Store](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-secure-external-password-store-password-credentials.html): creating wallets, managing credentials with mkstore, and client configuration.
5. [Oracle Database 19c Universal Connection Pool Developer's Guide — Borrowing Connections](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjucp/borrowing-ucp-connections.html): PoolDataSource, connection factory, and connection properties.
6. [Oracle Database 19c Universal Connection Pool Developer's Guide — Setting UCP Properties](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjucp/setting-ucp-properties.html): min/max pool size and pool configuration.
7. [Oracle Database 19c JDBC Troubleshooting](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/JDBC-troubleshooting.html): read timeout, firewalls, network failures, and resource cleanup.
8. [Oracle Database 19c Security Guide — About Configuring TLS](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/about-configuring-tls-oracle-database.html): TCPS, wallets, TLS client authentication, and DN matching.
9. [Oracle Database 19c Security Guide — TLS Features](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/tls-and-oracle-database.html): one-way TLS, mTLS, and certificate validation.

**Principle to remember:** OracleDataSource is a factory that creates JDBC Connections; UCP or an application server pool manages borrowing/returning and reusing connections. Use SERVICE_NAME, control URL/property precedence explicitly, distinguish timeout types, and verify the session after connecting. Passwords must come from a wallet, secret manager, or protected credential store; never embed them in source code, URLs, or logs. In production, combine least privilege, TLS/DN matching, pool sizing, credential rotation, and monitoring to manage the connection lifecycle securely.
