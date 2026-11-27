# Connecting Spring Boot to Oracle Database and UCP

## 1. Objectives and OCI Deployment Context

In the **Java and Spring Boot Deployment** chapter of the **CLOUD_PROVIDERS_ORACLE** module, database connectivity sits at the intersection of application code, OCI networking, identity, secrets, and Oracle Database capacity. An application starting successfully does not prove it connected to the right database, service, or account.

This lesson builds a Spring Boot configuration using Oracle JDBC Thin and **Universal Connection Pool — UCP**. The same configuration can serve applications running on OCI Compute or Oracle Kubernetes Engine (OKE), with connection details supplied per environment.

After completing this lesson, you will be able to:

- Distinguish the JDBC driver, `DataSource`, UCP, database service, and database user.
- Connect to Oracle Database using a service name or TNS alias; understand Autonomous Database cases using TLS or mTLS.
- Force Spring Boot to use UCP and verify the active pool.
- Execute parameterized queries and Spring-managed transactions.
- Configure pool limits, timeouts, health checks, and credential rotation strategies suited for OCI deployments.
- Isolate errors across networking, TLS, authentication, authorization, and pool usage layers.

**Example scope:** Java 21, a Maven project using the Spring Boot **3.5.x** parent or BOM, BOM-managed Oracle JDBC/UCP **23.x**, and a compatible Oracle Database. This is an illustrative baseline, not a claim of the latest versions. When adopting in practice, pin patch versions in your project and check Oracle's JDK–driver–database compatibility matrix; never infer compatibility solely from the name `ojdbc11`.

The `pom.xml`, `application.yml`, SQL, and Java snippets below are meant to be added to **your own lab project**. Hostnames, services, and wallet paths are examples to replace with your environment's values.

## 2. Path of a Database Access

```mermaid
flowchart LR
    Request["HTTP request or background job"]
    Spring["Spring service / transaction"]
    JDBC["JdbcTemplate or JPA"]
    UCP["UCP DataSource in each JVM"]
    Driver["Oracle JDBC Thin"]
    Network["DNS, route, NSG, TLS"]
    Service["Oracle Database service"]
    Schema["Database user and schema privileges"]

    Request --> Spring --> JDBC --> UCP --> Driver
    Driver --> Network --> Service --> Schema
```

| Component | Responsibility | Common Misconception |
| --- | --- | --- |
| Oracle JDBC Thin | Implements JDBC communication to Oracle Database in Java | Assuming adding the driver already provides pooling |
| `javax.sql.DataSource` | Interface for obtaining connections | Treating the interface as a specific pooling mechanism |
| UCP `PoolDataSourceImpl` | Manages, lends, reclaims, and evicts connections | Creating a new pool per HTTP request |
| `oracle.jdbc.pool.OracleDataSource` | Connection factory creating physical connections for UCP | Putting this factory name in `driver-class-name` |
| Database service | Logical access point and workload serving policy | Confusing service name with SID or schema name |
| Database user | Authenticates and holds SQL privileges | Confusing with OCI IAM users or policies |

A pool holds physical connections to the database. The application borrows a connection handle to perform work and then returns it. Under normal conditions, calling `Connection.close()` on a borrowed handle returns the connection to the pool; the physical connection can continue to be reused.

UCP lives **inside each JVM process**. If an application has four replicas, there are four independent pools, even if all replicas share the same pool name. A name like `orders-ucp` only identifies the pool; it does not create a cluster-wide shared pool.

Spring Boot 3 uses Jakarta for many application APIs, but JDBC continues to use `java.sql.*` and `javax.sql.DataSource`. Do not change imports to `jakarta.sql.DataSource`.

## 3. Preparing Connectivity and Layer-Specific Identities

### 3.1. Gathering Target Database Details

Before writing configuration, determine:

1. Which service hosts the database: Base Database Service, Exadata, or Autonomous Database.
2. Whether the endpoint is private or public, and whether the app has a network path to it.
3. Hostname, port, **service name**, or **TNS alias** to use.
4. Transport security mechanism: TCP in a lab, TCPS/TLS, or mTLS.
5. Application database account and per-object privileges.
6. Connection limits, workload service, and resource budget allocated to the app.

Easy Connect example using a service name:

```text
jdbc:oracle:thin:@//db.internal.example:1521/orderspdb.example
```

In this example:

- `db.internal.example` is a hostname resolvable from where the app runs.
- `1521` is the illustrative environment's listener port.
- `orderspdb.example` is the **service name**, not a username.

Legacy SID syntax looks different:

```text
jdbc:oracle:thin:@db.internal.example:1521:ORCL
```

Do not switch arbitrarily between the two forms. For PDBs and cloud services, use the exact service string provided by your administrator or the OCI Console.

### 3.2. Private Connectivity in OCI

For databases with private endpoints, the application must be able to resolve DNS and route to the endpoint's private IP. Compute inside the same VCN typically follows a different path than a laptop outside OCI; succeeding from an admin workstation does not guarantee connectivity from an application pod.

Check DNS, routes, and ingress/egress rules in order on both source and destination. Permit only required application sources to reach the database port. For Autonomous Database, the port depends on the connection string and TLS/mTLS mode; do not hardcode `1521` or `1522` for all cases. Oracle documents private endpoint rules in [Configure Network Access with Private Endpoints](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/private-endpoints-autonomous.html).

You can test TCP on Windows from a host **on an equivalent network path**:

```powershell
Resolve-DnsName db.internal.example
Test-NetConnection db.internal.example -Port 1521
```

A successful TCP check only proves a socket connection can open to that port. It does not verify the service name, TLS, account, or SQL privileges. In OKE, test from a pod environment or diagnostic tool sharing the pod's network conditions rather than testing only from a laptop.

### 3.3. Distinguishing OCI IAM From SQL Privileges

OCI IAM governs permissions on OCI resources and APIs, such as reading a secret or managing a database resource. With the username/password setup in this lesson, SQL permissions remain governed by the database user and `GRANT` statements inside the database.

An instance principal permitted to read a secret does not automatically gain `SELECT` access on business tables. Likewise, downloading a wallet does not grant rights across every schema.

Separate two roles:

- **Schema owner or migration account:** creates and alters tables and manages schema versions.
- **Runtime account:** connects and executes only the exact SQL statements the application requires.

The lab example uses `APP_OWNER` to own tables and `APP_RUNTIME` to run the application. The DBA prepares both accounts, tablespace/quotas, and owner object-creation rights per target database. Object grant steps appear in the hands-on section; the application never uses `ADMIN`, `SYSTEM`, `SYS`, or the `DBA` role.

## 4. Declaring Dependencies and Selecting the Right Pool

### 4.1. Minimal Dependency Set

Add the following dependencies to a project whose versions are already managed by Spring Boot 3.5.x:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
        <exclusions>
            <exclusion>
                <groupId>com.zaxxer</groupId>
                <artifactId>HikariCP</artifactId>
            </exclusion>
        </exclusions>
    </dependency>

    <dependency>
        <groupId>com.oracle.database.jdbc</groupId>
        <artifactId>ojdbc11</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>com.oracle.database.jdbc</groupId>
        <artifactId>ucp</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

Omit `<version>` on each dependency here because versions come from the parent/BOM. Spring Boot's [Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html) lists Oracle JDBC, UCP, and related libraries.

`ucp` uses compile scope because diagnostic code below imports UCP APIs; `ojdbc11` is only needed at runtime when application code uses standard JDBC. Never place multiple versions or variants of the driver or UCP on the same classpath.

The JDBC starter normally pulls in HikariCP. Excluding Hikari here keeps the lab's dependencies explicit; `spring.datasource.type` below is still needed to declare the UCP choice. If using multiple starters, check whether another starter transitively brings Hikari back.

In your lab project, verify with:

```bash
mvn dependency:tree -Dincludes=com.oracle.database.jdbc,com.oracle.database.security,com.zaxxer
```

### 4.2. When Using Oracle Wallet

With the Oracle 23.x library suite using Oracle Wallet, add the matching PKI provider:

```xml
<dependency>
    <groupId>com.oracle.database.security</groupId>
    <artifactId>oraclepki</artifactId>
    <scope>runtime</scope>
</dependency>
```

Guides for 19.x/21.x drivers may still mention `osdt_core` and `osdt_cert`. Packaging changed in 23.x, so read documentation matching your pinned driver line instead of mixing JARs across generations. Oracle details artifacts and these changes in the [Developers Guide for Maven Central](https://www.oracle.com/database/technologies/maven-central-guide.html).

Projects using a dedicated Oracle starter may also receive dependencies and auto-configuration from that starter. This lesson uses Spring Boot's native datasource mechanism only; do not layer a second `DataSource` creation mechanism on top.

## 5. Configuring Spring Boot to Use UCP

### 5.1. Baseline Configuration

Contents of `application.yml` in the lab project:

```yaml
spring:
  application:
    name: orders-service
  datasource:
    type: oracle.ucp.jdbc.PoolDataSourceImpl
    driver-class-name: oracle.jdbc.OracleDriver
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    oracleucp:
      connection-factory-class-name: oracle.jdbc.pool.OracleDataSource
      connection-pool-name: orders-ucp
      initial-pool-size: 2
      min-pool-size: 2
      max-pool-size: 10
      connection-wait-duration: 5s
      validate-connection-on-borrow: true
      connection-validation-timeout: 2
      seconds-to-trust-idle-connection: 0
      inactive-connection-timeout: 120
      timeout-check-interval: 30
      connection-properties:
        "[oracle.net.CONNECT_TIMEOUT]": "3000"
        "[oracle.jdbc.ReadTimeout]": "10000"
        "[oracle.net.ssl_server_dn_match]": "true"
  jdbc:
    template:
      query-timeout: 5s
  sql:
    init:
      mode: never

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
```

These values are starting points for a small lab. Tune them according to actual query durations, request budgets, network latency, and database limits.

Spring Boot binds general properties from `spring.datasource.*` and pool properties from `spring.datasource.oracleucp.*`. Setting `type` selects the UCP implementation instead of Spring Boot's pool auto-selection algorithm; see [SQL Databases — Spring Boot](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html).

| Property | Meaning in the Example |
| --- | --- |
| `type` | Pool datasource class instantiated by Spring Boot |
| `driver-class-name` | JDBC driver class, not the pool class |
| `connection-factory-class-name` | Factory creating physical connections inside UCP |
| `initial-pool-size` | Connections created when the pool initializes |
| `min-pool-size` | Minimum pool size target |
| `max-pool-size` | Pool connection ceiling within a single JVM |
| `connection-wait-duration` | Wait limit when borrowing a connection via UCP's Duration API |
| `connection-properties` | Properties passed down to Oracle JDBC, distinct from pool management properties |

JDBC keys containing dots and uppercase letters are quoted as `"[...]"`, alongside proper YAML indentation. This syntax preserves exact key names during map/properties binding; do not alter `ReadTimeout` to a guessed lowercase name.

With older UCP versions, you may encounter `connection-wait-timeout: 5` in seconds. The baseline configuration here uses `connection-wait-duration: 5s` per Spring Boot 3.5 / UCP 23.x properties. Never copy both properties simultaneously or assume every timeout accepts an `s` suffix. Check [Spring Boot 3.5 Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html) when changing versions.

### 5.2. Supplying Environment Variables

PowerShell example for a lab session using Easy Connect:

```powershell
$env:DB_URL = 'jdbc:oracle:thin:@//db.internal.example:1521/orderspdb.example'
$env:DB_USERNAME = 'APP_RUNTIME'

$secureDbPassword = Read-Host 'Database password' -AsSecureString
$env:DB_PASSWORD = [System.Net.NetworkCredential]::new('', $secureDbPassword).Password

try {
    java -jar .\target\orders-service.jar --spring.profiles.active=db-probe
}
finally {
    Remove-Item Env:DB_PASSWORD -ErrorAction SilentlyContinue
}
```

The JAR name depends on your project's build config. Prompting interactively avoids writing the password into command history; environment variables are still passed as strings to child processes and are not a secret store.

On Compute or OKE, use a deployment workflow that fetches secrets from a managed source such as OCI Vault and delivers them via an appropriate mechanism. Reading a secret requires scoped IAM policies; placing `${DB_PASSWORD}` in YAML does not call Vault on its own.

`spring.sql.init.mode: never` explicitly decouples table creation from application startup. In production, run migrations in a controlled step; the runtime account does not need DDL privileges just to run the application.

### 5.3. Avoiding Duplicate DataSources

Do not define an extra `@Bean DataSource` merely duplicating the configuration above. Once an application defines its own datasource bean, several Spring Boot auto-configuration branches step back, and properties you expect to apply may no longer bind to that bean.

If a system requires multiple databases, design distinct datasources, templates/entity managers, and transaction managers explicitly. A single-datasource setup in this lesson does not solve distributed transactions.

## 6. Connecting to Autonomous Database With mTLS or TLS

### 6.1. Wallets, TNS Aliases, and Runtime Paths

For mTLS, download the database client credentials and place the required files in a protected directory. A wallet bundle typically includes `tnsnames.ora`, `sqlnet.ora`, `ojdbc.properties`, and wallet/keystore files. Required files depend on the security configuration, so do not arbitrarily delete files that look redundant.

Example URL for a process running inside a Linux container:

```text
jdbc:oracle:thin:@orders_tp?TNS_ADMIN=/run/secrets/adb-wallet
```

`orders_tp` must be an alias present in `tnsnames.ora`. `TNS_ADMIN` points to the **directory**, not an unextracted ZIP file. Oracle documents aliases and this parameter in [JDBC Thin Connections with a Wallet (mTLS)](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-jdbc-thin-wallet.html).

On Windows, an example directory path is `H:/secrets/adb-wallet`. Never copy a Windows path from a build machine unchanged into a Linux container.

When deploying, verify from the perspective of the account running the JVM:

- Is the directory mounted into the right container or VM?
- Does the process have read permission on the required files?
- Does the alias match the target database and environment?
- Do `sqlnet.ora` or `ojdbc.properties` contain hardcoded paths needing runtime adjustment?
- Do the URL, JDBC properties, and system properties accidentally point to different wallet directories?

Never commit wallets to Git or bake them into shared images. Mount read-only where possible and scope file permissions to the application account. Wallets contain sensitive cryptographic material; treat them with the same rigor as other credentials.

### 6.2. Selecting the Right Service and TLS Mode

Alias names may carry suffixes such as `_tp`, `_low`, `_medium`, or `_high` depending on the Autonomous Database type. Not every database has the same alias set. Obtain aliases from target configuration and pick according to workload; `high` does not mean every application runs faster.

In environments allowing TLS without client certificates, a compatible JDBC Thin driver can connect **without a wallet**. mTLS adds client-certificate authentication; with the username/password login shown here, you still supply the database username and password. TLS requirements and endpoint choices are explained in [About Connecting to an Autonomous Database Instance](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-introduction.html).

Whether choosing TLS or mTLS:

- Obtain the connection string from the target database, preserving server certificate verification and hostname/DN matching.
- Never set `ssl_server_dn_match` to `false` to bypass certificate errors.
- Never downgrade a `tcps` URL to `tcp` just to force a connection to succeed.
- Keep the service-issued hostname; substituting an IP address can break server identity verification.

The TCP URL in the lab sections only illustrates Easy Connect structure in an authorized lab environment. For real data, transport encryption choices must follow environment security policy.

## 7. Verifying That Connections Actually Use UCP

Create the following class in a package scanned by the Spring Boot application. The `db-probe` profile turns this into an intentional diagnostic step rather than running a probe query on every normal startup.

```java
package example.orders;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;

import oracle.ucp.jdbc.PoolDataSource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("db-probe")
public class DatabaseProbe {

    private static final Logger log =
            LoggerFactory.getLogger(DatabaseProbe.class);

    @Bean
    ApplicationRunner verifyOracleConnection(DataSource dataSource) {
        return args -> {
            if (!(dataSource instanceof PoolDataSource pool)) {
                throw new IllegalStateException(
                        "Expected UCP, found "
                                + dataSource.getClass().getName());
            }

            log.info("Datasource={}, pool={}, maxPoolSize={}",
                    dataSource.getClass().getName(),
                    pool.getConnectionPoolName(),
                    pool.getMaxPoolSize());

            String sql = """
                    select sys_context('USERENV', 'SESSION_USER'),
                           sys_context('USERENV', 'SERVICE_NAME')
                    from dual
                    """;

            try (Connection connection = dataSource.getConnection();
                 PreparedStatement statement =
                         connection.prepareStatement(sql)) {

                statement.setQueryTimeout(5);

                try (ResultSet result = statement.executeQuery()) {
                    if (!result.next()) {
                        throw new IllegalStateException(
                                "Oracle probe returned no row");
                    }

                    log.info("Connected as user={} to service={}",
                            result.getString(1),
                            result.getString(2));
                }
            }
        };
    }
}
```

In projects wrapping datasources with proxies for tracing or routing, the outer bean type may be a wrapper. In that case, use proper unwrapping instead of the direct type check above. With simple auto-configuration in this lesson, the bean is expected to be the UCP implementation.

Checks to verify:

1. The datasource is UCP and `maxPoolSize` matches configuration.
2. A connection can be borrowed and the SQL query executes.
3. `SESSION_USER` is the expected runtime account.
4. `SERVICE_NAME` belongs to the environment's target database/service.

The HTTP server may already have opened its port before the runner completes; treat the probe as successful only when logs confirm the query completed and the process does not exit from runner errors. Never log passwords, wallet contents, or full security configs. After diagnosing, disable this profile and retain appropriate health checks.

Try-with-resources closes `ResultSet`, `PreparedStatement`, and the connection handle even when exceptions occur. Never store a `Connection` in a static field shared across requests.

## 8. Practicing Table Access and Transactions

### 8.1. Preparing the Schema With Appropriate Accounts

The DBA or an authorized administrative tool grants login rights to the runtime user:

```sql
GRANT CREATE SESSION TO APP_RUNTIME;
```

Then log in as **APP_OWNER** and create tables in the owner schema:

```sql
CREATE TABLE ORDER_RECORD (
    ORDER_ID VARCHAR2(36 CHAR) PRIMARY KEY,
    CUSTOMER_NAME VARCHAR2(100 CHAR) NOT NULL,
    AMOUNT NUMBER(12, 2) NOT NULL,
    CREATED_AT TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT CK_ORDER_AMOUNT CHECK (AMOUNT > 0)
);

CREATE TABLE ORDER_AUDIT (
    ORDER_ID VARCHAR2(36 CHAR) PRIMARY KEY,
    EVENT_TYPE VARCHAR2(30 CHAR) NOT NULL,
    CREATED_AT TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT FK_ORDER_AUDIT_ORDER
        FOREIGN KEY (ORDER_ID) REFERENCES ORDER_RECORD (ORDER_ID)
);

GRANT SELECT, INSERT ON ORDER_RECORD TO APP_RUNTIME;
GRANT SELECT, INSERT ON ORDER_AUDIT TO APP_RUNTIME;
```

These statements assume the owner user already has required privileges and quota in the target PDB. Never run them in the root container merely for login convenience.

The runtime user only needs to read and insert rows in this lab, so it is not granted `UPDATE`, `DELETE`, or `CREATE TABLE`. Application SQL uses qualified names like `APP_OWNER.ORDER_RECORD`, avoiding synonyms or altering `CURRENT_SCHEMA`.

### 8.2. Service Using JdbcTemplate

Place the service in a component-scanned package:

```java
package example.orders;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(timeout = 10)
    public String createOrder(String customerName, BigDecimal amount) {
        String customer = customerName == null
                ? "" : customerName.strip();

        if (customer.isEmpty()
                || customer.codePointCount(0, customer.length()) > 100) {
            throw new IllegalArgumentException(
                    "Customer name must have 1 to 100 characters");
        }

        if (amount == null) {
            throw new IllegalArgumentException("Amount is required");
        }

        BigDecimal normalized;
        try {
            normalized = amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Amount must have at most two decimal places", ex);
        }

        if (normalized.signum() <= 0
                || normalized.compareTo(
                        new BigDecimal("9999999999.99")) > 0) {
            throw new IllegalArgumentException("Amount is out of range");
        }

        String orderId = UUID.randomUUID().toString();

        jdbc.update("""
                insert into APP_OWNER.ORDER_RECORD
                    (ORDER_ID, CUSTOMER_NAME, AMOUNT)
                values (?, ?, ?)
                """, orderId, customer, normalized);

        jdbc.update("""
                insert into APP_OWNER.ORDER_AUDIT
                    (ORDER_ID, EVENT_TYPE)
                values (?, ?)
                """, orderId, "CREATED");

        return orderId;
    }

    @Transactional(readOnly = true, timeout = 5)
    public BigDecimal findAmount(String orderId) {
        return jdbc.queryForObject("""
                select AMOUNT
                from APP_OWNER.ORDER_RECORD
                where ORDER_ID = ?
                """, BigDecimal.class, orderId);
    }
}
```

The `?` markers are bind parameters. Never concatenate `customerName` or `orderId` directly into SQL strings. `BigDecimal` represents monetary amounts accurately at two decimal places in this example; avoid converting through `double`.

When `createOrder` is invoked from another bean through the Spring proxy, both `INSERT` statements share the same datasource transaction. If the audit insert fails with a Spring-translated runtime exception, let the exception propagate so the transaction rolls back. Never swallow the error and return success.

`JdbcTemplate` uses Spring's connection management and participates in the active transaction; see [Controlling Database Connections — Spring Framework](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/connections.html). Therefore, inside this service, do not call manual `commit()`, `rollback()`, or `getConnection()` to create parallel access paths.

Important boundaries to keep in mind:

- Calling an annotated method from another method on the same object bypasses standard Spring proxy transaction interception.
- `readOnly = true` is a hint to the transaction infrastructure, not a replacement for database `GRANT` privileges.
- Transaction timeouts are not a hard watchdog capable of interrupting every Java operation or network call.
- Never keep a transaction open while making external HTTP calls or waiting for user input.
- `findAmount` throws an exception if no row is found; the API layer must translate that into appropriate behavior, such as HTTP 404.

### 8.3. Dedicated Lab Write Runner

Invoke the service from an independent bean to ensure calls go through the Spring proxy:

```java
package example.orders;

import java.math.BigDecimal;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("lab-write")
public class OrderLabRunner implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(OrderLabRunner.class);

    private final OrderService orders;

    public OrderLabRunner(OrderService orders) {
        this.orders = orders;
    }

    @Override
    public void run(ApplicationArguments args) {
        String id = orders.createOrder(
                "Lab customer", new BigDecimal("125000.00"));

        log.info("Created lab order={}, amount={}",
                id, orders.findAmount(id));
    }
}
```

Running with the `lab-write` profile **inserts a new order on every startup**. Enable it only against a prepared lab database, record the `orderId`, and disable the profile after practice. This runner provides no business API idempotency.

Log in as the runtime user and verify both rows for the logged ID:

```sql
SELECT ORDER_ID, CUSTOMER_NAME, AMOUNT
FROM APP_OWNER.ORDER_RECORD
WHERE ORDER_ID = :order_id;

SELECT ORDER_ID, EVENT_TYPE
FROM APP_OWNER.ORDER_AUDIT
WHERE ORDER_ID = :order_id;
```

`:order_id` is a SQL tool bind variable to set to the logged ID. After the lab, the owner account or an authorized cleanup tool deletes the audit row first and then the order row by that ID; do not grant `DELETE` to the runtime account just for lab cleanup convenience.

## 9. If the Application Uses Spring Data JPA

JPA/Hibernate sits above the datasource; it can still use the configured UCP pool. Replace the JDBC starter with `spring-boot-starter-data-jpa` when JPA is needed, handle the Hikari exclusion accordingly, and retain Oracle JDBC/UCP. There is no need to stand up a separate pool for Hibernate.

Example additional configuration:

```yaml
spring:
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
```

Merge this into the existing config rather than creating two top-level `spring:` keys in the same YAML document.

`ddl-auto: validate` requires the schema to be created by migrations and match entity mappings. Avoid automatic `create`, `create-drop`, or `update` against production databases. Do not copy an old dialect from another guide when Hibernate can determine the right dialect from metadata.

`spring.jdbc.template.query-timeout` only configures Boot-managed `JdbcTemplate`, not all JPA queries automatically. For JPA, configure query timeouts via the Hibernate/Jakarta Persistence APIs and properties for your version.

## 10. Sizing the Pool System-Wide

### 10.1. Connection Budget Across Multiple Replicas

Suppose each replica uses one datasource and the database allocates connection budget `B` to the application. Preliminary design condition:

```text
R_peak × P_max + C_other + C_reserve <= B
```

Where:

- `R_peak`: maximum concurrent replicas, including surge replicas during rolling deployments.
- `P_max`: `max-pool-size` per replica.
- `C_other`: connections from migrations, batch jobs, and related clients outside this pool.
- `C_reserve`: agreed safety headroom.
- `B`: workload connection budget, not automatically the database's entire session limit.

Example assuming `B = 80`, up to six replicas during rolling deployments, other clients using up to eight connections, and twelve reserved:

```text
6 × P_max + 8 + 12 <= 80
P_max <= 10
```

Thus, `max-pool-size: 10` fits this **assumed budget**. If autoscaling raises the ceiling to ten replicas, recalculate. These figures are learning examples, not Oracle service limits.

### 10.2. Estimating Actual Demand

Estimate using **connection hold time**, not just HTTP request duration:

```text
Average borrowed connections
≈ borrows per second × average hold time (seconds)
```

For instance, one replica borrowing 120 times/second with an average hold time of 0.04 seconds averages roughly 4.8 borrowed connections. This excludes tail distributions, bursts, lock waits, or batch jobs; measure real load before choosing a ceiling.

Enlarging the pool can cause more concurrent queries to contend for CPU, I/O, and locks, lengthening hold times and worsening overload. Measure borrowed/available counts, wait times, SQL latency, and database capacity before increasing pool size. Oracle likewise emphasizes keeping pools small and matched to database capacity in [UCP Best Practices](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjucp/UCP-best-practices.html).

A large `min-pool-size` across many replicas also creates many idle sessions. Under rapid scale-out, a large `initial-pool-size` can trigger a simultaneous logon storm. Set both values based on baseline load and pace replica startup.

## 11. Distinguishing Timeout Types

| Setting | Layer Affected | Unit in Example | What It Does Not Guarantee |
| --- | --- | --- | --- |
| `connection-wait-duration: 5s` | UCP: waiting to borrow a connection | Duration | Does not bound the whole HTTP request |
| `connection-validation-timeout: 2` | UCP: validating a connection | Seconds | Not a business SQL query timeout |
| `oracle.net.CONNECT_TIMEOUT: "3000"` in connection properties | JDBC: opening socket connection | Milliseconds | Does not replace an end-to-end budget across retries/addresses |
| `oracle.jdbc.ReadTimeout: "10000"` | JDBC: socket read | Milliseconds | Not total transaction duration |
| `spring.jdbc.template.query-timeout: 5s` | JDBC statements created by template | Duration passed to statement | Does not cover all JPA queries or every network operation |
| `@Transactional(timeout = 10)` | Spring-managed transaction | Seconds | Does not forcibly interrupt arbitrary JVM work |
| `inactive-connection-timeout: 120` | UCP: reclaiming idle connections per pool cycle | Seconds | Does not fix leaks where connections stay borrowed |

JDBC properties follow their own unit rules; in particular, units in a URL or connect descriptor may differ from connection properties. Check the API docs for your pinned driver, such as [OracleConnection — JDBC API](https://docs.oracle.com/en/database/oracle/oracle-database/21/jajdb/oracle/jdbc/OracleConnection.html), instead of assuming one unit everywhere.

The baseline config sets independent values to clarify each layer. In operations, design a time budget along the real execution path:

```text
Wait for connection + execute SQL + bounded retry + return response
must fit within the request deadline and gateway/client timeouts.
```

If a gateway times out before a transaction finishes, the client may see an error even though the write commits afterward. Such cases call for idempotency and transaction-status lookup rather than merely raising timeouts.

Do not interpret a `5s` pool wait and `5s` query timeout as a guarantee that every request finishes in 10 seconds. A transaction executing multiple statements, calling multiple endpoints, or retrying follows a different total path.

## 12. Validation, Stale Connections, and Leaked Resources

### 12.1. Validation on Borrow

The baseline enables:

```yaml
validate-connection-on-borrow: true
connection-validation-timeout: 2
seconds-to-trust-idle-connection: 0
```

With Oracle JDBC, UCP uses an internal lightweight ping, so you do not need `SQLForValidateConnection` just to run `SELECT 1 FROM DUAL` on every borrow. A positive `seconds-to-trust-idle-connection` reduces checks on recently used/validated connections while introducing a trust window to weigh carefully. See [Overview of Validating Connections in UCP](https://docs.oracle.com/en/database/oracle/oracle-database/21/jjucp/validating-ucp-connections.html).

Validation prevents lending connections already detected as broken at check time. It does not guarantee the network or database cannot fail immediately afterward; the business layer must still handle exceptions.

### 12.2. Shrinking the Pool and Detecting Long-Held Connections

`inactive-connection-timeout` targets idle connections sitting in the pool. It is not a substitute for closing connections. Timeout enforcement also depends on the pool's check interval, so do not treat 120 seconds as millisecond-exact.

`max-connection-reuse-time`, `abandoned-connection-timeout`, and `time-to-live-connection-timeout` address different scenarios. The latter two can reclaim connections that are currently borrowed, so setting them too low can abort valid transactions. Distinguish their behaviors in [Stale Connections in UCP](https://docs.oracle.com/en/database/oracle/oracle-database/21/jjucp/stale-ucp-connections.html).

Before enabling forced reclamation, find why connections are held:

- `ResultSet`/statement/connection left unclosed on an exception branch.
- Transaction spanning a slow external HTTP call.
- Query waiting on locks or a bad execution plan.
- Batch job reading a large dataset and processing rows too slowly inside one transaction.
- Application thread blocked while still holding a transaction.

An application can exhaust its pool even with low JVM CPU. What matters is where connections are held and for how long.

## 13. Monitoring the Pool and Designing Health Checks

### 13.1. What to Observe

Monitor both sides simultaneously:

| Application Side | Database Side |
| --- | --- |
| Borrowed and available connection counts | Sessions by user/service |
| Borrow wait counts and wait durations | Active SQL, wait events, and locks |
| Connection creation and validation errors | Service/listener state and resource health |
| Transaction latency and retry counts | CPU, I/O, and workload limits |
| Replica count and pool sizes | Aggregate load from other applications |

UCP exposes APIs such as `getBorrowedConnectionsCount()`, `getAvailableConnectionsCount()`, and pool statistics; refer to [PoolDataSource API](https://docs.oracle.com/en/database/oracle/oracle-database/21/jjuar/oracle/ucp/jdbc/PoolDataSource.html). When building dashboards, integrate these metrics into your app's metrics framework, confirm metrics actually appear, and use bounded-cardinality labels.

Never assume UCP-specific metrics appear automatically just because Actuator was added. Expose metrics/Prometheus endpoints only after configuring an exporter and locking down access. Never use order IDs or customer usernames as metric labels.

### 13.2. Liveness and Readiness

If the application runs as a web service on OKE and the database is mandatory to serve requests, you can **add** the following configuration:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

Merge into the existing YAML tree. With a standard datasource, Boot typically registers a `db` health contributor; verify the exact contributor name in your application before adding it to the readiness group.

Liveness here reflects only the application's own vitality. Putting the database into liveness can restart every pod during a temporary database disconnect. Readiness can reflect the database dependency when the app has no degraded serving mode. Spring Boot describes these choices in [Actuator Endpoints — Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).

Consider probe frequency and timeouts: a fleet of hundreds of pods querying the database too aggressively creates self-inflicted load. When a pool is full, the database health check can fail simply because it cannot borrow a connection; inspect pool metrics alongside it to distinguish pool exhaustion from a database outage.

For batch applications without a web server, use job status, logs, and controlled connectivity checks rather than expecting an HTTP endpoint.

## 14. Maintenance, Failover, and Retries

UCP can participate in Oracle HA capabilities such as Fast Connection Failover (FCF), using FAN/ONS events when appropriately configured. FCF reacts to service events and evicts unusable connections; it does not magically make every in-flight transaction succeed. Prerequisites are detailed in [About Fast Connection Failover](https://docs.oracle.com/en-us/database/oracle/oracle-database/21/jjucp/fast-connection-failover.html).

Do not simply enable `fast-connection-failover-enabled` and assume infrastructure is HA. Verify database topology, service type, required notification libraries, and corresponding network paths. With Autonomous Database, follow that service's own client and service instructions rather than copying ONS settings from a different RAC example.

Application Continuity and Transparent Application Continuity form a separate capability tier depending on service config, datasource/replay driver, versions, and replay limits. This lesson uses the basic factory and does not claim transaction replay is enabled.

Business-tier retry policies should have these properties:

1. Classify likely transient errors; never endlessly retry invalid passwords or missing privileges.
2. Each transaction retry must enter a fresh transaction boundary and acquire a valid connection.
3. Cap attempts and total duration, adding backoff and jitter to avoid reconnect storms.
4. For write operations, use idempotency keys, unique constraints, and result lookup.
5. On disconnect during commit, handle uncertain commit outcomes before resending.

The order runner in this lesson generates a new UUID per call and has no client idempotency contract. Never wrap it in automatic write retries expecting zero duplicate orders.

## 15. Troubleshooting by Symptom

| Symptom | First Layer to Check | Resolution Direction |
| --- | --- | --- |
| `oracle.jdbc.OracleDriver` not found | Dependencies / runtime classpath | Verify the driver is inside the deployed artifact, not only in the IDE |
| Cannot load `PoolDataSourceImpl` | UCP dependency | Check UCP artifact/version and remove duplicate conflicting JARs |
| Probe shows Hikari or another datasource | Auto-configuration / beans | Check `spring.datasource.type`, active profiles, and custom beans |
| Unknown host or socket timeout | DNS, routes, NSGs, endpoint | Test from the actual runtime before changing database accounts |
| `ORA-12154` | Connect identifier resolution | Verify TNS alias, `TNS_ADMIN`, and target config files |
| `ORA-12514` | Service known to the listener | Match service name/PDB and verify service registration |
| `ORA-01017` | Database authentication | Check active secret, username, and target database |
| `ORA-28000` | Account lock status | Stop bad-password retry loops, unlock account, and fix credential source |
| `ORA-00942` or insufficient SQL privileges | Schema / object privileges | Check owner, table name, and runtime `GRANT`s; never grant DBA as a shortcut |
| TLS handshake, wallet, or certificate error | TLS/mTLS bundle | Check files, read permissions, PKI dependency, truststore, and hostname |
| Connection wait timeout | Pool or slow DB | Compare borrowed vs. max, queries holding connections, and total load |
| Errors after long idle period | Stale connections, intermediate firewalls | Check validation and idle/max-lifetime settings |
| Errors during rollout or scale-out | Total connection budget | Account for surge replicas, jobs, and per-JVM initial pool sizes |

Never conclude a root cause from a single outer exception line. Preserve Oracle error codes, causal chains, and timestamps while redacting secrets from shared logs.

A useful troubleshooting sequence is:

```text
Right artifact and profile
→ DNS/route/port
→ TLS or wallet
→ right service
→ login
→ object privileges
→ borrow/return connection and transaction
→ database resources and load.
```

## 16. Repeatable Practice Workflow

Execute in a lab environment:

1. **Prepare:** confirm target database, service, network path, and runtime account.
2. **Package:** use a compatible JDBC/UCP set; inspect the dependency tree and deployed artifact.
3. **Configure:** supply URL, username, and password; mount the wallet properly if using mTLS.
4. **Read probe:** enable `db-probe`, verify UCP, user, and service; disable the profile once verified.
5. **Prepare schema:** use the owner/migration account to create both tables and grant specific runtime rights.
6. **Transactional write:** enable `lab-write` once, record the ID, and verify both order and audit rows exist.
7. **Observe pool:** apply bounded load, monitor borrowed counts, hold times, and slow SQL.
8. **Controlled recovery test:** in an authorized lab, simulate an appropriate connectivity disruption and observe errors, readiness, and reconnection; avoid impacting shared databases.
9. **Multi-replica rollout:** recalculate the connection budget using peak replica count during rolling deployment.
10. **Wrap up:** disable the write profile, clean up lab data using an authorized account, and revoke temporary resources/secrets.

For OCI Compute/OKE, automate non-sensitive URLs, secret references, wallet mount paths, pool limits, and environment profiles in a repeatable deployment pipeline. Cost and availability tie directly to replica counts, pool sizing, and database capacity; adding resources only helps once the actual bottleneck is identified.

The expected outcome is an application reaching the intended Oracle Database using a least-privilege account, verified to use UCP, closing resources cleanly, and backed by metrics explaining behavior under rising load or connectivity disruption.
