# Configuring Oracle DataSource in Spring Boot by Environment

## 1. Role of DataSource in Spring Boot

In a Spring Boot application using JDBC or Spring Data JPA, the DataSource is the entry point for the application to obtain connections to the database. Spring Boot can auto-configure a DataSource when a JDBC/JPA starter and appropriate connection information are present in the application configuration.

With Oracle Database, the DataSource typically uses the Oracle JDBC Thin Driver to connect to a database service. The application should not create a new Connection using DriverManager inside individual repository or service methods. Instead, Spring manages a shared DataSource; the connection pool issues a connection for each unit of work and returns it to the pool upon completion.

Key components:

- **Oracle JDBC driver:** communicates over Oracle Net with the listener and database.
- **DataSource:** factory that creates JDBC Connections.
- **Connection pool:** manages physical connections, session limits, connection validation, and reuse.
- **Spring transaction manager:** binds connections to Spring transactions.
- **JPA EntityManager/Hibernate:** uses the DataSource to execute SQL when the application chooses JPA.
- **Profiles and externalized configuration:** selects endpoints, pool settings, and secrets per environment.

Spring Boot typically chooses HikariCP when Hikari is on the classpath and no other DataSource bean/type is specified. The JDBC/JPA starters usually pull in HikariCP as a default dependency. OracleDataSource is a JDBC DataSource factory; it is not a connection pool itself. If UCP is needed, UCP must be configured as a separate pool implementation.

## 2. Adding the Oracle JDBC Dependency

### 2.1. Maven

Example using the Oracle JDBC 11 driver for applications running on JDK 11 and above:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>com.oracle.database.jdbc</groupId>
        <artifactId>ojdbc11</artifactId>
        <version>${oracle.jdbc.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Set oracle.jdbc.version in dependency management or a project property according to the verified driver version:

~~~xml
<properties>
    <oracle.jdbc.version>23.6.0.24.10</oracle.jdbc.version>
</properties>
~~~

The version above is an illustrative example only; choose a JDBC version compatible with your JDK, Oracle Database release, Spring Boot version, and organizational patching policy. Do not assume the latest version is always suitable for every database.

If only using JdbcTemplate/JDBC, use spring-boot-starter-jdbc instead of spring-boot-starter-data-jpa. There is no need to pull in Hibernate if the application does not use ORM.

### 2.2. Gradle

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    runtimeOnly("com.oracle.database.jdbc:ojdbc11:$oracleJdbcVersion")
}
~~~

Declare oracleJdbcVersion in a version catalog or Gradle property for centralized management. Do not declare multiple ojdbc versions simultaneously across modules.

### 2.3. Choosing the Right JDBC Artifact

| Artifact | Use Case |
| --- | --- |
| ojdbc11 | Driver for Java 11+ |
| ojdbc8 | Driver for Java 8 and compatible environments |
| ucp | Oracle Universal Connection Pool |
| ons | Oracle Notification Service client when using features requiring ONS |
| oraclepki, osdt_core, osdt_cert | Certain wallet/TLS/TDE configurations depending on driver and Oracle guidance |

Do not add every artifact to every application. Only add UCP, ONS, and security artifacts when required by the features and driver version.

### 2.4. Verifying the Runtime Driver

Spring Boot typically auto-detects the driver from the JDBC URL and driver JAR. For Oracle JDBC Thin, the driver class is:

~~~text
oracle.jdbc.OracleDriver
~~~

You can configure spring.datasource.driver-class-name, though it is usually unnecessary if the driver is on the classpath and the URL is valid.

If you encounter a driver-not-found error, check the runtime dependency tree and whether the artifact is packaged inside the executable JAR/container image. Do not solve it by manually adding JARs to production machines without updating the build.

## 3. JDBC URL for Oracle

### 3.1. Prefer SERVICE_NAME

Common URL format:

~~~text
jdbc:oracle:thin:@//host:port/service_name
~~~

Example:

~~~text
jdbc:oracle:thin:@//db-dev.example.com:1521/devapp.example.com
~~~

SERVICE_NAME is the database service requested by the application. This is the appropriate connection method for PDBs, RAC, and services that can relocate across instances.

### 3.2. TNS Alias

If the environment already manages connect descriptors in tnsnames.ora:

~~~text
jdbc:oracle:thin:@APPDB
~~~

Example entry:

~~~text
APPDB =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = db-prod.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = appsvc.example.com)
    )
  )
~~~

The JDBC process must be able to read the correct Oracle Net directory. You can configure TNS_ADMIN via an environment variable or the oracle.net.tns_admin connection property. Do not assume a Spring Boot container can read tnsnames.ora on a DBA workstation.

### 3.3. SID Syntax

Legacy URLs may use:

~~~text
jdbc:oracle:thin:@host:1521:ORCL
~~~

This is the SID format. SID identifies an instance; SERVICE_NAME identifies a service. With RAC or PDBs, prefer SERVICE_NAME so Oracle routes to the appropriate instance.

### 3.4. Do Not Embed Username/Password in the URL

Do not use:

~~~text
jdbc:oracle:thin:APP_USER/password@//dbhost:1521/appsvc
~~~

Credentials can leak in logs, exceptions, metrics, process diagnostics, configuration files, or deployment metadata. The URL should only contain the endpoint/service; username/password should come from a secret provider.

## 4. Basic DataSource Configuration

### 4.1. application.yml

Spring Boot can automatically create a DataSource from standard properties:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//localhost:1521/XEPDB1
    username: APP_RUNTIME
    password: ${ORACLE_DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
~~~

ORACLE_DB_PASSWORD must be supplied by the runtime environment or secret store. Do not write real passwords into application.yml.

With HikariCP, Spring Boot detects the pool on the classpath and configures it from the spring.datasource.hikari group:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: app-pool
      minimum-idle: 2
      maximum-pool-size: 12
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1740000
~~~

The values above are illustrative only. Choose pool size and timeouts based on load, number of application instances, Oracle session limits, request duration, and load balancer/firewall timeouts.

### 4.2. Minimal Driver Class Configuration

If the Oracle driver is on the runtime classpath, a minimal configuration can be:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc
    username: ${ORACLE_DB_USERNAME}
    password: ${ORACLE_DB_PASSWORD}
~~~

Spring Boot and the JDBC driver can infer the driver class from the URL. Declare driver-class-name explicitly when you need to avoid ambiguity or when using a custom DataSource type.

### 4.3. DataSourceProperties and Hikari

Spring Boot uses DataSourceProperties to translate standard configuration into a DataSource. When Hikari is selected, the url property is mapped to jdbcUrl per the Hikari API.

If you create a HikariDataSource manually with @ConfigurationProperties directly, remember that Hikari uses jdbcUrl rather than the url property. A common approach is to bind DataSourceProperties and call initializeDataSourceBuilder(), letting Spring perform the proper mapping.

## 5. Per-Environment Configuration with Profiles

An application typically runs in local/dev, test, staging, and production. Each environment has different endpoints, accounts, pool sizes, TLS policies, and secrets. You should not bundle multiple passwords into one file and select among them in code.

### 5.1. File Structure

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

The application.yml file holds shared configuration; application-{profile}.yml files hold environment-specific differences. Spring Boot automatically loads the corresponding profile file when a profile is active; there is no need to place spring.config.activate.on-profile inside application-dev.yml or application-prod.yml.

### 5.2. application.yml: Shared Configuration

~~~yaml
spring:
  application:
    name: orders-api

  datasource:
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      pool-name: orders-pool
      minimum-idle: 2
      maximum-pool-size: 12
      connection-timeout: 30000
      validation-timeout: 5000
      max-lifetime: 1740000

  jpa:
    open-in-view: false
    properties:
      hibernate:
        jdbc:
          time_zone: UTC

logging:
  level:
    com.zaxxer.hikari: INFO
~~~

Do not place default production credentials in the shared file. Each profile/environment provides its own URL and secrets.

### 5.3. application-dev.yml

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//localhost:1521/XEPDB1
    username: ${ORACLE_DB_USERNAME:APP_DEV}
    password: ${ORACLE_DB_PASSWORD}
    hikari:
      minimum-idle: 1
      maximum-pool-size: 4

  jpa:
    hibernate:
      ddl-auto: update
    show-sql: true

logging:
  level:
    org.hibernate.SQL: DEBUG
~~~

DDL_AUTO update and show_sql are only suitable for controlled development environments. Do not carry this configuration over to production.

### 5.4. application-test.yml

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//oracle-test.example.com:1521/testsvc
    username: ${ORACLE_DB_USERNAME}
    password: ${ORACLE_DB_PASSWORD}
    hikari:
      minimum-idle: 1
      maximum-pool-size: 3

  jpa:
    hibernate:
      ddl-auto: validate
~~~

Integration tests need a real Oracle database/schema or an organization-approved Oracle-compatible environment. Do not assume H2 can fully emulate Oracle SQL, sequences, PL/SQL, locking, and data types.

### 5.5. application-staging.yml

~~~yaml
spring:
  datasource:
    url: ${ORACLE_DB_URL}
    username: ${ORACLE_DB_USERNAME}
    password: ${ORACLE_DB_PASSWORD}
    hikari:
      minimum-idle: 2
      maximum-pool-size: 8

  jpa:
    hibernate:
      ddl-auto: validate
~~~

Staging should mirror production as closely as possible in database release, service routing, TLS, runtime privileges, and pool policy.

### 5.6. application-prod.yml

~~~yaml
spring:
  datasource:
    url: ${ORACLE_DB_URL}
    username: ${ORACLE_DB_USERNAME}
    password: ${ORACLE_DB_PASSWORD}
    hikari:
      minimum-idle: 5
      maximum-pool-size: 20
      connection-timeout: 30000
      validation-timeout: 5000
      max-lifetime: 1740000
      keepalive-time: 300000

  jpa:
    hibernate:
      ddl-auto: validate
    show-sql: false

logging:
  level:
    org.hibernate.SQL: WARN
    com.zaxxer.hikari: INFO
~~~

Pool numbers are only starting points, not fixed sizing recommendations. Production should manage schema with a migration tool such as Flyway/Liquibase or a DBA process; Hibernate should not auto-create/modify the schema on every application startup.

### 5.7. Activating Profiles

You can activate a profile via an environment variable:

~~~text
SPRING_PROFILES_ACTIVE=dev
~~~

In production:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Or pass a command-line argument at runtime:

~~~text
java -jar orders-api.jar --spring.profiles.active=prod
~~~

Environment variables work well with containers/orchestrators. Do not hardcode the production profile in source code because the same artifact should be deployable across multiple environments.

### 5.8. Configuration Precedence

Spring Boot has multiple externalized configuration sources. Higher-precedence sources can override application.yml, for example:

- Command-line arguments.
- SPRING_APPLICATION_JSON.
- Java system properties.
- OS environment variables.
- Config data files.
- Default properties.

Exact precedence details depend on the source and the Config Data mechanism of the Spring Boot version. When investigating misconfigurations, inspect environment variables, command line, mounted config, and active profiles—not just application.yml.

## 6. Injecting Secrets per Environment

### 6.1. Environment Variables

Spring Boot relaxed binding maps:

| Spring property | Environment variable |
| --- | --- |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| spring.datasource.username | SPRING_DATASOURCE_USERNAME |
| spring.datasource.password | SPRING_DATASOURCE_PASSWORD |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |
| spring.datasource.hikari.maximum-pool-size | SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE |

Example:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL=jdbc:oracle:thin:@//db-prod.example.com:1521/ordersvc
SPRING_DATASOURCE_USERNAME=ORDERS_RUNTIME
SPRING_DATASOURCE_PASSWORD=<injected-secret>
~~~

Do not record real secrets in shell history, Dockerfiles, compose files committed to Git, or pipeline logs.

### 6.2. Config Tree for Secrets Mounted as Files

Spring Boot supports config trees, which fit well when Kubernetes/secret managers mount each key as a file.

Configuration example:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

The directory can contain:

~~~text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
  spring.datasource.url
~~~

The filename becomes the property key; the file content becomes the value. If using a config tree for username/password, do not simultaneously declare different values in a profile without understanding precedence.

### 6.3. Secret Managers

In cloud or enterprise platforms, you can use:

- HashiCorp Vault.
- AWS Secrets Manager.
- Azure Key Vault.
- Google Secret Manager.
- Kubernetes/platform secret store.
- Application server credential store.

Spring Boot core does not natively integrate with every secret manager. You need an appropriate starter/provider, an identity/role granted permission to read the secret, and the provider's cache/rotation policy.

### 6.4. Never Log Configurations Containing Secrets

Avoid:

~~~java
log.info("Datasource properties: {}", properties);
log.info("Database password: {}", password);
~~~

Do not dump the entire Environment or DataSource bean if logs could contain passwords, tokens, wallet passwords, or sensitive URLs.

Only log allowlisted information, such as profile, service alias, pool name, and database product version; never log secrets.

### 6.5. Credential Rotation

A rotation workflow should include:

1. Create/change credentials according to database policy.
2. Update the secret store or wallet.
3. Ensure the application can read the new secret.
4. Refresh/restart/drain the pool in a controlled manner so new physical connections use the new credentials.
5. Verify authentication and new connection counts.
6. Revoke old credentials at an agreed-upon time.
7. Monitor for ORA-01017, ORA-28000, and login failures.

Changing a password in the secret store does not automatically update credentials already used to create physical connections currently sitting in the pool.

## 7. Pool Configuration and Sizing

### 7.1. HikariCP as the Common Default

Spring Boot prefers HikariCP when it is on the classpath. Basic configuration:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-pool
      minimum-idle: 4
      maximum-pool-size: 20
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 300000
~~~

Meaning:

| Property | Meaning |
| --- | --- |
| pool-name | Pool name used for logs/metrics |
| minimum-idle | Minimum number of idle connections |
| maximum-pool-size | Maximum total connections in the pool |
| connection-timeout | Wait time to borrow a connection, in milliseconds |
| validation-timeout | Validation wait time, in milliseconds |
| idle-timeout | Time a connection can sit idle before being eligible for removal, in milliseconds |
| max-lifetime | Maximum lifetime of a physical connection, in milliseconds |
| keepalive-time | Interval to test/keep idle connections alive, in milliseconds |
| leak-detection-threshold | Threshold for warning about a connection held too long, in milliseconds |

Hikari connectionTimeout is not the Oracle listener connect timeout. It is the time a request waits for a free connection in the pool.

### 7.2. Calculating System-Wide Total Connections

Suppose:

- 4 application pods.
- Each pod has maximumPoolSize = 20.
- 2 batch workers, each with a max pool size of 5.

Potential total connections:

~~~text
4 × 20 + 2 × 5 = 90 connections
~~~

The database must sustain this number of connections alongside DBA sessions, monitoring, schedulers, other applications, and background processes. With RAC, review service distribution and per-instance limits.

Do not set maximumPoolSize very high just to avoid pool waits. If the database cannot handle that concurrency, queueing at the pool can protect the database better.

### 7.3. Coordinating Timeouts

A single request can be subject to multiple timeouts:

| Timeout | Common Unit | Meaning |
| --- | --- | --- |
| Hikari connectionTimeout | ms | Waiting to borrow a connection from the pool |
| Oracle Net CONNECT_TIMEOUT in descriptor | seconds | Time to connect to the endpoint |
| Oracle JDBC ReadTimeout | ms | Waiting to read data from the socket |
| JDBC Statement query timeout | seconds | Statement execution time per JDBC |
| HTTP/load balancer timeout | Platform-dependent | Time the client/proxy waits for a response |

Units and support for Oracle JDBC properties depend on the driver/release. Check documentation for the exact version; do not copy values between timeouts with different units.

A timeout budget should follow a sensible order: pool wait must not exceed request SLA; connect/read timeouts must not let requests hang indefinitely; upstream timeouts must be large enough for the service to finish or return a controlled error.

### 7.4. maxLifetime and Firewalls/Load Balancers

If a firewall or network appliance closes idle connections after a period of time, maxLifetime/keepalive should be tuned to match that policy. Hikari should retire a connection before infrastructure silently closes it.

Do not set the same maxLifetime across all environments if network policies differ. Inspect Hikari logs, Oracle listener logs, and firewall idle timeouts.

### 7.5. Validation

Hikari uses JDBC4 Connection.isValid() when supported by the driver. There is no need to configure connectionTestQuery for modern Oracle JDBC drivers if isValid works properly.

Only set connection-test-query when required by the driver/connection implementation or confirmed necessary:

~~~yaml
spring:
  datasource:
    hikari:
      connection-test-query: SELECT 1 FROM DUAL
~~~

A validation query incurs a round trip and can increase load. Measure before enabling.

## 8. Oracle JDBC Connection Properties via Hikari

Hikari allows passing driver-specific properties:

~~~yaml
spring:
  datasource:
    hikari:
      data-source-properties:
        oracle.net.CONNECT_TIMEOUT: 10000
        oracle.net.OUTBOUND_CONNECT_TIMEOUT: 10000
        oracle.jdbc.ReadTimeout: 30000
~~~

Illustrative values must have their units and behavior verified against your Oracle JDBC version. Timeouts can be configured in the Oracle Net connect descriptor instead of passing properties, for example:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=10)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=appsvc.example.com))
)
~~~

Do not configure the same timeout at multiple layers with conflicting values. When investigating slow connections, separate pool wait time, DNS, TCP, listener, authentication, and query execution.

### 8.1. TNS_ADMIN

You can supply the Oracle Net admin path via a driver property:

~~~yaml
spring:
  datasource:
    hikari:
      data-source-properties:
        oracle.net.tns_admin: /run/secrets/oracle-net
~~~

The path must exist inside the container/pod and the account running the application must have read permission. If using tnsnames.ora, verify that the alias has the correct entry and the service is registered with the listener.

## 9. TLS/TCPS and Wallets per Environment

### 9.1. TCPS URL

Connect descriptor example:

~~~yaml
spring:
  datasource:
    url: >-
      jdbc:oracle:thin:@(DESCRIPTION=
      (ADDRESS=(PROTOCOL=TCPS)(HOST=db-prod.example.com)(PORT=2484))
      (CONNECT_DATA=(SERVICE_NAME=ordersvc.example.com))
      (SECURITY=(TLS_SERVER_DN_MATCH=TRUE)))
~~~

Port 2484 is an example only. Use your environment's actual TCPS listener port and certificate.

### 9.2. Wallet/Oracle Net Configuration

A wallet can provide trust certificates for TLS or credentials for Secure External Password Store. Distinguish carefully:

- Truststore/PKI wallet verifies the server certificate.
- Client wallet contains certificates/private keys for mutual TLS.
- Secure External Password Store holds database usernames/passwords.

These purposes can share the same wallet system depending on configuration, but one wallet file does not automatically contain every credential/key needed.

Example of supplying the Oracle Net admin directory via environment variable:

~~~text
TNS_ADMIN=/run/secrets/oracle-net
~~~

The directory may contain sqlnet.ora, tnsnames.ora, and wallet files depending on configuration. Do not copy wallets into immutable images or commit them to repositories. Mount secrets read-only and restrict filesystem permissions.

### 9.3. Server DN Matching

TLS_SERVER_DN_MATCH helps the client verify that the certificate belongs to the intended database endpoint. Do not disable DN matching or certificate validation just to get past a handshake error.

When TLS fails, check:

1. The listener is serving TCPS.
2. The certificate chain is still valid.
3. Hostname/DN matches the certificate.
4. The trust wallet is correct.
5. Client/server system clocks.
6. Supported TLS protocols/ciphers.
7. Wallet path and permissions.

### 9.4. Secret Wallet for JDBC Thin

Oracle JDBC Thin can use Secure External Password Store. When configured, the driver retrieves credentials by connect identifier from the wallet instead of needing a password in application properties.

With Spring Boot/Hikari, wallet/Oracle Net properties must be compatible with how Hikari creates physical connections and the driver version. Do not simultaneously set username/password directly if you want to verify cleanly that credentials are fetched from the wallet. Test with the exact ojdbc JAR, wallet, and container image before deployment.

## 10. Configuring JPA/Hibernate with Oracle

### 10.1. Dialect

Modern Hibernate can auto-detect the Oracle dialect from JDBC metadata. Usually you do not need to hardcode a dialect if connectivity and metadata work.

If explicit configuration is required, choose a dialect matching your Hibernate version. Do not copy Oracle12cDialect from old Hibernate examples into Hibernate 6 without checking deprecations and dialect classes.

### 10.2. DDL Auto

Production example:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Common options:

| Value | Behavior |
| --- | --- |
| none | Hibernate does not manage the schema |
| validate | Checks that mappings and schema are compatible |
| update | Attempts to alter the schema to match mappings |
| create | Creates a new schema on startup |
| create-drop | Creates schema on start, drops on shutdown |

For production, typically use none or validate and manage DDL via Flyway/Liquibase/DBA migrations. Never use create-drop on a database containing business data.

### 10.3. Open Session in View

For REST APIs, you can disable it:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

This forces the application service to define clear transaction/fetch boundaries, preventing unexpected queries during response serialization.

### 10.4. Transaction Management

Spring Boot auto-configures the corresponding transaction manager when JPA or JDBC is present. Use @Transactional at the service layer to define transaction boundaries.

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Order create(Order order) {
        return repository.save(order);
    }
}
~~~

Do not open a Connection manually outside a Spring transaction and expect the JPA transaction to participate automatically unless using the proper DataSource/transaction manager.

## 11. Multiple Oracle DataSources in One Application

An application sometimes needs to connect to two databases, such as OLTP and reporting. Each DataSource requires its own configuration, its own transaction manager, and its own persistence unit if using JPA.

### 11.1. Two Configuration Groups

~~~yaml
app:
  datasource:
    orders:
      url: ${ORDERS_DB_URL}
      username: ${ORDERS_DB_USERNAME}
      password: ${ORDERS_DB_PASSWORD}
      configuration:
        maximum-pool-size: 20
    reporting:
      url: ${REPORTING_DB_URL}
      username: ${REPORTING_DB_USERNAME}
      password: ${REPORTING_DB_PASSWORD}
      configuration:
        maximum-pool-size: 8
~~~

With custom configuration, use DataSourceProperties to map url to jdbcUrl:

~~~java
@Configuration
public class DataSourceConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders")
    public DataSourceProperties ordersProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders.configuration")
    public HikariDataSource ordersDataSource(
            @Qualifier("ordersProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
    }

    @Bean
    @ConfigurationProperties("app.datasource.reporting")
    public DataSourceProperties reportingProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.reporting.configuration")
    public HikariDataSource reportingDataSource(
            @Qualifier("reportingProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
    }
}
~~~

The example requires importing HikariDataSource, DataSourceProperties, ConfigurationProperties, Bean, Configuration, Primary, and Qualifier. In a real project, verify binding prefixes and bean naming; each DataSource must be injected using the appropriate qualifier.

### 11.2. Transaction Manager

If using JDBC transactions:

~~~java
@Bean
@Primary
public PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
~~~

If using JPA, each DataSource typically needs its own EntityManagerFactory and JpaTransactionManager. Select the corresponding repository packages, persistence unit, and transaction manager; do not mix transactions from two databases as if they were a single local transaction.

### 11.3. No Automatic Atomic Transactions Across Two Databases

Two local transaction managers on two DataSources do not automatically create a distributed transaction. If atomic commits across multiple databases/resources are required, you must design for JTA/XA or a saga/outbox pattern. Do not invoke two repositories and assume both databases commit or roll back together.

## 12. UCP Instead of HikariCP for Oracle-Specific Requirements

### 12.1. When to Consider UCP?

UCP can be suitable when an application needs deep integration with Oracle Database HA:

- Fast Connection Failover/FAN.
- Runtime connection load balancing.
- Application Continuity/TAC integration per driver/service support.
- Oracle-specific pool metrics and connection labeling.
- HA capabilities of the Oracle client stack.

If HikariCP meets your needs, there is no reason to add UCP solely because the database is Oracle.

### 12.2. Dependencies

Maven example:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>${oracle.jdbc.version}</version>
    <scope>runtime</scope>
</dependency>

<dependency>
    <groupId>com.oracle.database.ha</groupId>
    <artifactId>ucp</artifactId>
    <version>${oracle.jdbc.version}</version>
</dependency>
~~~

Ensure the UCP and JDBC driver versions are compatible; do not mix a newer UCP with an older driver unless supported by Oracle.

### 12.3. Configuring UCP via a DataSource Bean

When using UCP, you can declare the pool explicitly so Spring Boot uses that DataSource bean:

~~~java
@Configuration
public class OracleUcpConfiguration {

    @Bean
    @Primary
    public PoolDataSource dataSource(Environment environment)
            throws SQLException {

        String url = environment.getRequiredProperty("spring.datasource.url");
        String username = environment.getRequiredProperty("spring.datasource.username");
        String password = environment.getRequiredProperty("spring.datasource.password");

        PoolDataSource pool =
            PoolDataSourceFactory.getPoolDataSource();

        pool.setConnectionFactoryClassName(
            "oracle.jdbc.pool.OracleDataSource"
        );
        pool.setURL(url);
        pool.setUser(username);
        pool.setPassword(password);
        pool.setConnectionPoolName("orders-ucp");
        pool.setInitialPoolSize(2);
        pool.setMinPoolSize(2);
        pool.setMaxPoolSize(20);
        pool.setConnectionWaitTimeout(10);
        pool.setValidateConnectionOnBorrow(true);

        return pool;
    }
}
~~~

The example requires importing PoolDataSource, PoolDataSourceFactory, Environment, Bean, Configuration, Primary, and SQLException. For secret rotation, do not read the password once at startup and expect the pool to update automatically; a refresh/drain procedure is needed.

### 12.4. Do Not Configure Both Pools Simultaneously

If both Hikari and UCP are on the classpath, Spring Boot auto-configuration generally prioritizes Hikari. When intentionally using UCP, declare the DataSource bean/type explicitly and inspect startup logs to confirm only the intended pool is active.

Do not wrap a UCP pool inside a Hikari pool or vice versa without a deliberate special design; nested pools obscure connection lifecycle and sizing.

## 13. Schema Migration and Startup Ordering

### 13.1. Flyway/Liquibase

Database schema migrations should run in a controlled manner before the application receives traffic. Across multiple environments:

- Each profile points to the right database.
- Migration credentials may differ from runtime credentials.
- The runtime account does not need CREATE TABLE/ALTER TABLE if it does not run migrations.
- Migration history must be backed up/audited.
- Do not let multiple replicas run migrations concurrently without control if the tool/config does not handle locking properly.

### 13.2. Separating Migration and Runtime Accounts

Example:

- APP_MIGRATOR: granted required DDL privileges during the deployment window.
- APP_RUNTIME: granted only required DML/EXECUTE privileges.

Do not use a single DBA account for both migration and runtime.

### 13.3. Readiness and Liveness

Readiness checks should reflect the instance's ability to serve requests and may test a DataSource connection with a short, bounded timeout. Liveness checks should not continuously open heavy database connections in a way that causes a database outage to send all pods into a restart loop.

Distinguish between:

- Liveness: is the process alive and able to self-recover?
- Readiness: is the instance ready to receive traffic?
- Startup probe: has the application finished starting up?

Do not turn every transient database error into a liveness failure; this can trigger a restart storm during an outage.

## 14. Observability and Diagnostics

### 14.1. Spring Boot Actuator

If using Actuator, DataSource and Hikari metrics can be exposed via Micrometer. Protect metrics/health endpoints with appropriate network policies and authentication.

Monitor:

- Active connections.
- Idle connections.
- Pending threads.
- Max pool size.
- Min idle.
- Connection acquisition time.
- Connection usage duration.
- Timeout/failure count.

### 14.2. Hikari Logs

Pool logs help diagnose:

- Pool initialization.
- Connection creation failures.
- Pool starvation.
- Connection leak warnings.
- Pool shutdown/refresh.

Do not leave overly broad DEBUG logging enabled long-term in production; logs can grow rapidly and expose endpoints/configuration.

### 14.3. Checking Database Sessions

DBAs can inspect sessions from the database:

~~~sql
SELECT username,
       service_name,
       machine,
       program,
       status,
       COUNT(*) AS session_count
FROM v$session
WHERE username = 'APP_RUNTIME'
GROUP BY username, service_name, machine, program, status
ORDER BY machine, status;
~~~

Compare session counts against the total pool size across all pods/workers. Access to V$SESSION or an appropriate view is required.

### 14.4. Confirming Service/PDB

After opening a connection:

~~~sql
SELECT USER AS database_user,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

This query is useful when local/staging/prod have multiple services or PDBs.

### 14.5. Do Not Log JDBC URLs Containing Sensitive Information

URLs may contain internal hosts, services, wallet paths, or connect descriptors. Not every URL is strictly a secret, but evaluate topology information before writing it to public logs/traces.

## 15. Testing Configuration per Environment

### 15.1. Startup Verification

Verify:

1. The right profile is active.
2. The Oracle JDBC driver is loaded.
3. The DataSource is created with the expected type.
4. The pool initializes with the expected min/max.
5. The secret provider returns valid credentials.
6. The service name resolves.
7. TLS/wallet loads if enabled.

### 15.2. Integration Tests

An integration test should:

- Open a connection from the Spring-managed DataSource.
- Verify database user/service/PDB.
- Execute a transactional insert/update and roll back.
- Verify sequences/identities and critical Oracle data types.
- Verify migration/schema version.
- Verify runtime account privileges.

Do not test the DataSource solely with SELECT 1 FROM DUAL and conclude that all JPA mappings and transactions work.

### 15.3. Testing Pool Behavior

Test behavior under:

- Increased concurrency.
- Temporary database unavailability.
- Listener/service restarts in a test environment.
- Credential rotation.
- Idle connections closed by a firewall.
- Pool reaching maximumPoolSize.
- Queries running longer than read/statement timeouts.

Observe pending threads, borrow timeouts, stale connections, pool refill, and recovery time.

### 15.4. Do Not Use H2 as Proof of Oracle Compatibility

H2 is useful for testing simple logic, but does not replace Oracle integration tests when the application uses:

- PL/SQL packages.
- Oracle sequences.
- MERGE, hierarchical queries, or specialized analytic SQL.
- Oracle DATE/TIMESTAMP/TIMESTAMP WITH TIME ZONE.
- CLOB/BLOB and LOB streaming.
- Locking/isolation semantics.
- Oracle-specific functions/indexes/constraints.

## 16. Common Errors

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Failed to determine a suitable driver class | Missing ojdbc runtime dependency or invalid URL | Check dependency tree, driver JAR, and URL |
| ORA-01017 | Wrong username/password or stale secret | Check secret provider, rotation, and wallet alias |
| ORA-28000 | Account locked | Check account status and DBA policy |
| ORA-28001 | Password expired | Rotate credentials following procedure |
| ORA-12154 | Unable to resolve TNS alias | Check TNS_ADMIN and tnsnames.ora |
| ORA-12514 | Listener does not know SERVICE_NAME | Check service registration and URL |
| ORA-12541 | No listener at host/port | Check listener, DNS, and firewall |
| ORA-29024 | TLS certificate validation failed | Check trust chain, DN matching, and wallet |
| Hikari pool initialization fails | Database unreachable, bad secret, or pool config error | Check root SQLException and connection properties |
| Connection is not available, request timed out | Pool exhausted or connections held too long | Check active/pending, leaks, max pool, and query time |
| Too many sessions | Total pool size exceeds database limit | Sum all pods/workers and check service limits |
| Connection reset/broken pipe | Firewall/network closed socket or DB failover | Check timeouts, keepalive, FAN, and stale connection handling |
| Wrong database/PDB | Wrong URL/service profile | Check SYS_CONTEXT and SPRING_PROFILES_ACTIVE |
| Schema validation failed | Hibernate mapping and schema mismatch | Run matching migration version; check data types/sequences |
| DDL unexpectedly changes production | ddl-auto update/create | Use validate/none and a migration tool |
| Password changed but new logins still fail | Pool/secret provider still using old credentials | Refresh secret cache and drain/recreate pool |
| Hikari property ignored | Wrong prefix or property name | Check spring.datasource.hikari and configuration metadata |
| UCP not selected | Hikari still wins auto-configuration | Declare DataSource type/bean explicitly and check startup logs |

## 17. Per-Environment Deployment Flow

~~~text
Build a single artifact
       |
       v
Select deployment environment
       |
       +---- dev
       |       - local Oracle/PDB
       |       - dev secret
       |       - small pool
       |       - log SQL when needed
       |
       +---- test/staging
       |       - test/staging service
       |       - dedicated secret
       |       - schema validate
       |       - TLS and pool near production
       |
       +---- prod
               - production Oracle service
               - secret manager/wallet
               - TLS/TCPS per policy
               - pool sizing by total load
               - dedicated schema migration
               - monitoring/alerting
       |
       v
Validate configuration and readiness
       |
       v
Route traffic
~~~

A single artifact can run across multiple environments; profiles and secrets are injected at deploy time. Do not build a separate JAR just to change a password or database host.

## 18. Oracle DataSource Configuration Checklist

1. **Right driver?** ojdbc version matches JDK, database, and Spring Boot.
2. **URL uses SERVICE_NAME?** Avoid hardcoding SID/instance with RAC/PDB.
3. **Right profile selected?** Verify SPRING_PROFILES_ACTIVE.
4. **URL/user/password come from the right source?** Check precedence among config files, environment, and config tree.
5. **No secrets in Git/logs?** Passwords must come from a secret store.
6. **Need explicit driver class?** Only set when auto-detection is insufficient.
7. **Right pool implementation?** Default Hikari or UCP as needed.
8. **Pool size summed across pods/workers?** Compare against database session/process limits.
9. **Timeouts coordinated?** Pool wait, connect, read, statement, and HTTP.
10. **Network/TNS config correct?** TNS_ADMIN, DNS, listener, service.
11. **TLS/DN matching enabled when required?** Do not skip certificate validation.
12. **Wallet/keystore mounted securely?** Read-only, ACLs, and rotation.
13. **Credential rotation tested?** Ensure the pool refreshes.
14. **JPA DDL policy correct?** Production typically uses validate/none.
15. **Migration account separated from runtime account?** Least privilege.
16. **Transaction boundaries correct?** Use Spring @Transactional and the appropriate transaction manager.
17. **Health checks free of restart storms?** Separate readiness and liveness.
18. **Actuator/metrics protected?** Do not expose management endpoints publicly.
19. **Service/PDB verified via SQL?** Confirm the right target.
20. **Integration tested against Oracle?** H2 is no substitute for Oracle compatibility.

## 19. Self-Check Questions

**Question 1.** What is the role of DataSource in Spring Boot?

**Question 2.** Why is OracleDataSource not synonymous with a connection pool?

**Question 3.** When does Spring Boot typically select HikariCP?

**Question 4.** Which Java runtime is the ojdbc11 artifact suitable for?

**Question 5.** How does SERVICE_NAME differ from SID?

**Question 6.** Why should a single artifact be configured via profiles/external config rather than built separately per environment?

**Question 7.** Which property does SPRING_DATASOURCE_URL map to?

**Question 8.** What problem does config tree solve?

**Question 9.** Why should passwords never be committed in application-prod.yml?

**Question 10.** How does Hikari connectionTimeout differ from Oracle CONNECT_TIMEOUT?

**Question 11.** Why must maximumPoolSize be calculated across all pods and workers?

**Question 12.** Which infrastructure timeout does maxLifetime relate to?

**Question 13.** When should Oracle UCP be considered?

**Question 14.** Why should you not wrap UCP inside Hikari?

**Question 15.** Why does production typically avoid ddl-auto update?

**Question 16.** Why do multiple DataSources require separate transaction managers?

**Question 17.** Do two local transaction managers automatically create a distributed transaction?

**Question 18.** How can a wallet be used for credentials and TLS?

**Question 19.** Why should readiness and liveness be separated?

**Question 20.** Why are integration tests needed on real Oracle or a supported Oracle environment?

<details>
<summary>Suggested Answers</summary>

1. Provides JDBC Connections to JDBC/JPA and the transaction manager.
2. OracleDataSource creates physical connections; a pool manages reuse, sizing, and lifecycle.
3. When HikariCP is on the classpath and no other DataSource bean/type is specified.
4. Java 11 and later per artifact naming/support matrix; still verify the driver version.
5. SID identifies an instance; SERVICE_NAME identifies a database service.
6. The same artifact is deployed to multiple environments, reducing drift and keeping secrets/endpoints out of the binary.
7. spring.datasource.url.
8. Loads properties from mounted files, fitting secret/config injection.
9. Risk of exposure via Git, backups, reviews, and build artifacts.
10. Hikari waits for a free connection in the pool; Oracle CONNECT_TIMEOUT limits network connection establishment to the endpoint.
11. The database bears the total connections of all replicas/workers, not just a single pod.
12. Firewall/load balancer idle timeouts and database connection lifecycles.
13. When Oracle-specific HA, FAN, FCF, RLB, or AC/TAC integration is needed.
14. Nested pools create two layers of connection management, complicating sizing and lifecycle.
15. It can make unintended schema changes; production should use controlled migrations.
16. Each DataSource has its own connection/transaction resource.
17. No. JTA/XA or saga/outbox is required depending on requirements.
18. A credential store holds usernames/passwords; a PKI wallet holds trust/certificates/private keys.
19. A database outage should not cause processes to restart continuously; readiness stops traffic, while liveness only checks the process.
20. H2 does not fully emulate Oracle SQL, PL/SQL, data types, locking, and driver behavior.

</details>

## 20. Official Documentation

1. [Spring Boot Reference — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource auto-configuration, JDBC, connection pools, and SQL initialization.
2. [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): profiles, property sources, environment variables, and config trees.
3. [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): profile-based configuration.
4. [Spring Boot Reference — Data Access](https://docs.spring.io/spring-boot/reference/data/index.html): JDBC/JPA and transaction integration.
5. [Oracle JDBC Developer's Guide — Data Sources and URLs](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/data-sources-and-URLs.html): OracleDataSource, URLs, service names, and connection properties.
6. [Oracle JDBC Developer's Guide — JDBC Client-Side Security Features](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/client-side-security.html): wallets, credential stores, and TLS.
7. [Oracle Universal Connection Pool Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjucp/): UCP configuration, pooling, and connection lifecycle.
8. [HikariCP Configuration](https://github.com/brettwooldridge/HikariCP): pool sizing, timeouts, and connection lifecycle properties.
9. [Oracle Database Security Guide — Secure External Password Store](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-secure-external-password-store-password-credentials.html): wallets and credential management.

**Key takeaway:** Spring Boot should manage a shared DataSource and an appropriate connection pool. Use JDBC Thin with SERVICE_NAME, separate shared configuration from environment profiles, and inject passwords from a secret manager, config tree, or wallet. HikariCP is the common default; choose UCP for specific Oracle HA requirements. Pool sizing must account for all replicas/workers, timeouts must be distinguished by layer, and production requires controlled schema migrations, TLS where required, least privilege, credential rotation, and integration testing against Oracle.
