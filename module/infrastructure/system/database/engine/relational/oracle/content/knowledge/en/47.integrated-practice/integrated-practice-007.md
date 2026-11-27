# Java/Spring Boot Connectivity, Transaction Management, and Data Type Mapping

## 1. The Big Picture

A Java application connecting to Oracle Database typically flows through the following layers:

```text
REST Controller / Message Consumer
              |
              v
       Service Layer
       @Transactional
              |
       +------+------+
       |             |
       v             v
 Spring Data JPA   JdbcTemplate
       |             |
       v             v
 Hibernate ORM   Spring JDBC
       |             |
       +------+------+
              |
              v
         DataSource
       (HikariCP/UCP)
              |
              v
       Oracle JDBC Driver
              |
              v
        Oracle Database
```

Each component has a distinct responsibility:

- **Oracle JDBC driver** handles JDBC communication with Oracle, sends SQL, binds parameters, and marshals results back to Java.
- **DataSource/connection pool** manages physical connections for reuse, caps total connections, and enforces wait timeouts.
- **Hibernate/JPA** maps entities, generates SQL, and manages the persistence context.
- **Spring transaction manager** coordinates transaction boundaries across JPA/JDBC.
- **Service layer** defines which database changes belong to a business operation and when to commit or roll back.

When working with a single Oracle Database, a local transaction on a single JDBC connection is usually sufficient. JTA/XA is only required when one business operation must atomically commit or roll back across multiple independent resource managers, such as Oracle and an XA-capable JMS broker.

## 2. Preparing Oracle Database and Connection Details

### 2.1. Creating the Application User and Schema

Applications should run under a dedicated database account with least-privilege access to required objects. Never use `SYS`, `SYSTEM`, or a `DBA` account as the runtime account.

Example DBA setup of tablespace and user:

```sql
CREATE TABLESPACE app_data
  DATAFILE '/u02/oradata/DB/app_data01.dbf'
  SIZE 1G
  AUTOEXTEND ON NEXT 256M MAXSIZE 10G;

CREATE USER app_user IDENTIFIED BY "replace-with-secret"
  DEFAULT TABLESPACE app_data
  TEMPORARY TABLESPACE temp
  QUOTA 2G ON app_data;

GRANT CREATE SESSION TO app_user;
```

Paths and sizes above are filesystem examples; ASM or OMF environments use different syntax. In production, manage passwords via a secret manager or platform credential store—never commit real passwords in scripts.

If schemas are created by Flyway or Liquibase, the migration account may need broader DDL privileges than the runtime account. Separate the migration/deployment account from the runtime data read/write account.

### 2.2. Service Name and SID in the JDBC URL

The Oracle Thin driver connects over TCP without requiring an Oracle Client installation. Standard URLs use a service name:

```text
jdbc:oracle:thin:@//db-host.example.com:1521/app_service
```

Where:

- `db-host.example.com`: database hostname or address.
- `1521`: listener port, which may vary by environment.
- `app_service`: service registered with the listener, typically mapped to a database, PDB, or workload service.

A legacy URL format uses a SID:

```text
jdbc:oracle:thin:@db-host.example.com:1521:ORCL
```

Do not swap a service name for a SID casually. In multitenant environments, applications normally connect through a PDB service. Your DBA supplies the service name and configures appropriate failover/load balancing.

### 2.3. Verifying Connectivity from SQL*Plus

Before troubleshooting Spring Boot, verify the database service is reachable using an Oracle tool if available:

```bash
sqlplus app_user@//db-host.example.com:1521/app_service
```

After connecting:

```sql
SELECT sys_context('USERENV', 'DB_NAME') AS db_name,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name,
       sys_context('USERENV', 'CON_NAME') AS container_name
FROM dual;
```

If SQL*Plus also fails to connect, investigate DNS/network, listener, service registration, firewall, wallet/TLS, and credentials before altering Java code.

## 3. Oracle JDBC Driver in Maven and Gradle

### 3.1. Maven Dependency

Example using `ojdbc11`:

```xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>${oracle.jdbc.version}</version>
    <scope>runtime</scope>
</dependency>
```

Declare the property under `properties` or manage versions via the project BOM:

```xml
<properties>
    <oracle.jdbc.version>use-a-supported-version</oracle.jdbc.version>
</properties>
```

`use-a-supported-version` is a placeholder that must be replaced with an exact version verified against the Oracle JDBC support matrix. Never leave this placeholder in production builds.

### 3.2. Gradle Dependency

```kotlin
dependencies {
    runtimeOnly("com.oracle.database.jdbc:ojdbc11:$oracleJdbcVersion")
}
```

If the project uses Spring Boot dependency management, verify the resolved driver version. Avoid bundling multiple `ojdbc` artifacts on the runtime classpath, which can cause class-loading conflicts.

### 3.3. Selecting the Driver by Java and Oracle Release

Do not pick a driver solely by matching the Oracle Database version number. Verify:

- The JDK running the application.
- The Oracle Database release/RU.
- The Spring Boot / Hibernate version.
- The application server, if deploying to a container.
- Required features: JDBC, LOB, JSON, TLS, XA, UCP, or wallets.

`ojdbc8` and `ojdbc11` target different Java generations, and each specific driver release has its own Oracle Database compatibility matrix. The driver version number does not need to match the database release number, but it must fall within Oracle's supported matrix.

The Thin driver normally self-registers with `DriverManager`, and Spring Boot can infer the driver from the JDBC URL. Declaring `driver-class-name: oracle.jdbc.OracleDriver` makes configuration explicit, though it is not always mandatory.

## 4. Configuring Spring Boot DataSource

### 4.1. Basic application.yml

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-host.example.com:1521/app_service
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      pool-name: app-oracle-pool
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
      auto-commit: true

  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
```

Pool values above are illustrative starting points, not universal recommendations. Size `maximum-pool-size` according to total replicas, number of services, database workload, and Oracle capacity. Inject credentials via environment variables or a secret store; never commit credentials to source control.

### 4.2. HikariCP Property Meanings

| Property | Meaning |
|---|---|
| `maximum-pool-size` | Maximum number of physical connections in the pool |
| `minimum-idle` | Minimum number of idle connections the pool tries to maintain |
| `connection-timeout` | Max wait time in milliseconds to borrow a connection before failing |
| `validation-timeout` | Max wait time to validate whether a connection is alive |
| `idle-timeout` | Duration an idle connection may remain before eviction when above `minimum-idle` |
| `max-lifetime` | Maximum lifetime of a physical connection before replacement |
| `auto-commit` | Default auto-commit state when connections are outside pool-managed transactions |

Do not set timeouts so low that requests fail during brief database slowdowns, nor so high that requests hold threads and resources indefinitely. Set `max-lifetime` shorter than any network, load balancer, or database idle-connection termination timeout.

### 4.3. Calculating Total Connections Across the System

`maximum-pool-size` applies per pool per application instance. With multiple replicas:

\[
Total\ possible\ connections = \sum_{i=1}^{n}(replicas_i \times maxPool_i)
\]

For example, 4 replicas with a max pool of 20 connections each allow a single service to open up to 80 physical connections. Add other services, batch jobs, reporting tools, monitoring agents, and DBA sessions before comparing against Oracle `PROCESSES`/`SESSIONS`.

Larger pools do not automatically make the database faster. Excessive concurrent SQL increases CPU, I/O, lock contention, and latency. Measure throughput and connection hold times when sizing pools.

### 4.4. HikariCP vs. Oracle UCP?

HikariCP is a widely used, lightweight pool integrated cleanly into Spring Boot applications. Oracle Universal Connection Pool (UCP) offers Oracle-specific integrations such as runtime load balancing, Fast Connection Failover, or DRCP depending on configuration and version.

Choose a pool based on operational requirements. Whether using HikariCP or UCP, the application still requires proper Oracle JDBC driver configuration, timeouts, connection validation, pool sizing, and transaction management.

## 5. Configuring JPA/Hibernate

### 5.1. Letting Hibernate Auto-Detect Oracle

With Hibernate 6/7, if JDBC metadata works properly, you usually do not need to set the dialect manually. Example:

```yaml
spring:
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        format_sql: true
```

Modern Hibernate 5.x typically uses `org.hibernate.dialect.Oracle12cDialect` for Oracle 12c/18c/19c. Hibernate 6/7 uses `org.hibernate.dialect.OracleDialect`. Verify the class in your exact artifact and prefer auto-detection unless explicit configuration is required.

### 5.2. Use Schema Migrations Instead of Auto-Modifying the Schema

In production, use Flyway or Liquibase to manage versioned DDL. Hibernate is typically configured with:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
```

Common settings:

| Value | Behavior |
|---|---|
| `none` | Performs no schema management |
| `validate` | Validates entity mappings against the existing schema without creating or altering objects |
| `update` | Attempts to alter the schema to match mappings; unsuitable for controlled production migrations |
| `create` | Creates schema on startup, potentially destroying existing data |
| `create-drop` | Creates schema on startup and drops it when the context closes |

Never use `create`, `create-drop`, or `update` in production just to bypass mapping errors. Oracle DDL performs implicit commits and may acquire locks; migrations must be tested and executed under a controlled release plan.

### 5.3. Do Not Leave Open Session in View Enabled Unintentionally

`spring.jpa.open-in-view` may default to enabled in some Spring Boot setups. For APIs and services, consider disabling it to avoid lazy queries firing outside transactions during serialization. Fetch required associations inside the service or repository using fetch joins, entity graphs, or DTO projections.

## 6. Managing Transactions with Spring

### 6.1. Transaction Boundaries at the Service Layer

A business action often spans multiple database operations. Place `@Transactional` on the service method encompassing all changes that must be atomic:

```java
@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        inventoryRepository.reserve(
                command.productId(), command.quantity());

        Order order = new Order(
                command.customerId(),
                command.productId(),
                command.quantity());

        return orderRepository.save(order).getId();
    }
}
```

If `reserve` fails with a matching exception, the transaction manager rolls back all changes made by the method. Never commit manually inside a repository when Spring manages the transaction.

### 6.2. How @Transactional Works

Spring typically enforces `@Transactional` via proxies/interceptors:

1. The caller invokes the method through a Spring proxy.
2. The transaction manager starts a new transaction or joins an existing one.
3. Repositories/JPA/JDBC use the connection bound to that transaction.
4. If the method completes normally, the transaction manager commits.
5. If an exception matches the rollback rules, the transaction manager rolls back.

Because of proxying, self-invocation bypasses transaction advice:

```java
public void outer() {
    inner(); // internal call on the same object may bypass the proxy
}

@Transactional
public void inner() {
    // Does not automatically start a new transaction just because of the annotation.
}
```

Place transaction boundaries on methods invoked through a Spring bean proxy, or refactor so calls go through a separate bean. Never rely on `@Transactional` on a private method to establish an independent transaction.

### 6.3. Default Rollback Rules

By default, Spring rolls back on `RuntimeException` and `Error`; checked exceptions do not trigger rollback automatically under default rules.

If checked exceptions must also trigger rollback:

```java
@Transactional(rollbackFor = Exception.class)
public void importOrders() throws Exception {
    // Multiple database writes
}
```

Do not catch and swallow an exception if you expect a rollback:

```java
@Transactional
public void process() {
    try {
        repository.save(...);
    } catch (DataAccessException ex) {
        log.error("Database operation failed", ex);
        throw ex; // rethrow so the transaction manager rolls back
    }
}
```

If you catch an exception without rethrowing it, Spring considers the method successful and commits remaining changes. If you want to handle an error while committing other work, design explicit transaction boundaries or compensating actions.

### 6.4. Propagation

Common propagation modes:

| Propagation | Behavior |
|---|---|
| `REQUIRED` | Joins the current transaction; creates a new one if none exists |
| `REQUIRES_NEW` | Suspends the current transaction and starts an independent transaction |
| `SUPPORTS` | Joins a transaction if active; otherwise executes non-transactionally |
| `MANDATORY` | Requires the caller to already have an active transaction |
| `NOT_SUPPORTED` | Suspends any active transaction while the method runs |
| `NEVER` | Throws an error if a transaction is active |
| `NESTED` | Uses nested transactions/savepoints if supported by transaction manager and resource |

`REQUIRES_NEW` can require an additional connection while the outer transaction still holds its connection and locks. Overuse can exhaust the connection pool or cause connection-pool deadlocks. `NESTED` depends on transaction manager and JDBC savepoint support; do not assume every JPA transaction manager supports it fully.

### 6.5. Oracle Isolation Levels

Oracle defaults to `READ COMMITTED`. Each statement reads data committed as of statement start via multiversion read consistency; Oracle does not permit dirty reads in the traditional sense.

Spring can request a specific isolation level:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void readOrders() {
    // Oracle default isolation
}
```

Or:

```java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void calculateAndUpdate() {
    // Must be tested for serialization conflicts
}
```

Oracle supports `READ COMMITTED` and `SERIALIZABLE` under Oracle semantics; it does not support true `READ UNCOMMITTED`. `SERIALIZABLE` can throw `ORA-08177` under concurrent modifications. Raise isolation only when business rules demand it and concurrency has been tested.

### 6.6. readOnly and timeout

```java
@Transactional(readOnly = true, timeout = 10)
public List<OrderSummary> findRecentOrders() {
    return orderRepository.findRecentSummaries();
}
```

`readOnly = true` is a hint to the transaction manager and persistence provider that may optimize flushing; it does not guarantee the database rejects all DML. `timeout` is specified in seconds in Spring's annotation, though actual enforcement depends on the transaction manager, driver, and provider.

Distinguish transaction timeout from query timeout, lock timeout, network timeout, and connection acquisition timeout. Each protects a different stage and none replaces the others.

## 7. Mixing JPA and JDBC in the Same Transaction

### 7.1. Prefer JdbcTemplate When Direct SQL Is Needed

If an application uses JPA and needs an Oracle-specific JDBC query, `JdbcTemplate` can participate in the active Spring transaction when wired to the same `DataSource` and compatible transaction manager:

```java
@Service
public class ReconciliationService {
    private final OrderRepository orderRepository;
    private final JdbcTemplate jdbcTemplate;

    @Transactional
    public void reconcile(Long orderId) {
        Order order = orderRepository.findById(orderId).orElseThrow();

        jdbcTemplate.update(
                "UPDATE order_audit SET status = ? WHERE order_id = ?",
                order.getStatus(), orderId);
    }
}
```

Crucially, JPA and `JdbcTemplate` must share the exact same `DataSource` and a transaction manager capable of coordinating that connection. Spring Boot typically auto-configures `JpaTransactionManager` for a single `EntityManagerFactory`/`DataSource`; verify wiring whenever multiple data sources exist.

### 7.2. Never Fetch Connections Outside the Transaction-Bound Context

If you call `dataSource.getConnection()` manually inside a JPA transaction, do not assume the returned connection is the same physical connection managed by the transaction. Use `JdbcTemplate` or `DataSourceUtils.getConnection(dataSource)` to obtain the Spring transaction-bound connection.

Never call `commit()` or `rollback()` directly on a Spring-managed connection, and never manually close a transaction-bound connection; let Spring/`JdbcTemplate` manage its lifecycle. If using raw JDBC outside any transaction, manage `try-with-resources`, commit/rollback, and cleanup yourself.

### 7.3. Multiple DataSources

If an application accesses two Oracle databases, or Oracle plus another database, two separate local transaction managers do not create a joint atomic transaction. Consider:

- JTA/XA with XA-capable data sources and a unified transaction manager.
- Transactional outbox or Saga patterns when XA is unnecessary or unavailable.
- Reconciliation and idempotency workflows when eventual consistency is acceptable.

Never put a single `@Transactional` annotation on a method assuming multiple data sources will commit atomically together.

## 8. Mapping Oracle Data Types to Java/JPA

### 8.1. NUMBER and BigDecimal

Oracle `NUMBER(p,s)` typically maps to `BigDecimal` when exact decimal precision is required:

```sql
amount NUMBER(18, 2) NOT NULL
```

Entity:

```java
@Column(name = "AMOUNT", precision = 18, scale = 2, nullable = false)
private BigDecimal amount;
```

Never use `double` or `float` for currency or values requiring exact decimal arithmetic, as binary floating-point rounding can introduce discrepancies.

Common mappings:

| Oracle | Typical Java/JDBC Type | Notes |
|---|---|---|
| `NUMBER(p,0)` with small range | `Integer` | Verify `p` bounds and range |
| `NUMBER(19,0)` | `Long` or `BigDecimal` | `NUMBER` can hold values beyond `Long`; verify domain range |
| `NUMBER(p,s)` | `BigDecimal` | Declare matching precision and scale |
| `BINARY_FLOAT` | `Float` | Floating-point only, never currency |
| `BINARY_DOUBLE` | `Double` | Use only when binary floating point is acceptable |

Never infer the Java type solely from the word `NUMBER`. Unconstrained Oracle `NUMBER` allows arbitrary precision/scale unlike fixed `NUMBER(p,s)` columns; inspect the DDL and actual values.

### 8.2. VARCHAR2, NVARCHAR2, and CHAR

```sql
customer_code VARCHAR2(50 CHAR),
display_name  NVARCHAR2(200),
country_code  CHAR(2)
```

Typically mapped to `String`:

```java
@Column(name = "CUSTOMER_CODE", length = 50)
private String customerCode;

@Column(name = "DISPLAY_NAME", length = 200)
private String displayName;

@Column(name = "COUNTRY_CODE", length = 2)
private String countryCode;
```

`VARCHAR2` limits can use `BYTE` or `CHAR` semantics; check `NLS_LENGTH_SEMANTICS` and actual DDL. `NVARCHAR2` uses the national character set. `CHAR` is fixed-length and blank-padded; verify comparison and trimming behavior when mapping.

Never assume `@Column(length = ...)` fully captures Oracle byte vs. character semantics. Migration DDL should remain the source of truth for lengths and character sets.

### 8.3. DATE Does Not Store Date Only

Oracle `DATE` stores year, month, day, hour, minute, and second, without fractional seconds or timezone. It is not identical to a date-only `java.sql.Date`.

Choose the Java type by semantics:

- `LocalDate` if the application intentionally stores dates only and consistently normalizes the time component.
- `LocalDateTime` if both date and time down to seconds are needed.

Example:

```java
@Column(name = "ORDER_DATE", nullable = false)
private LocalDateTime orderDate;
```

If an Oracle `DATE` column represents a pure calendar date, standardize setting the time component to midnight and test round-trip behavior. Never let one application map the same column as `LocalDate` while another interprets it as `LocalDateTime`.

### 8.4. TIMESTAMP and Timezones

| Oracle Type | Typical Java Type | Characteristics |
|---|---|---|
| `TIMESTAMP(n)` | `LocalDateTime` | Fractional seconds, no timezone |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` or provider-supported type | Retains timezone/offset per Oracle/JDBC semantics |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Typically `OffsetDateTime`/`LocalDateTime` per design and provider | Normalized to database timezone and displayed in session timezone |

Example:

```java
@Column(name = "CREATED_AT", nullable = false)
private LocalDateTime createdAt;

@Column(name = "EVENT_TIME")
private OffsetDateTime eventTime;
```

`TIMESTAMP WITH LOCAL TIME ZONE` does not preserve the original offset the way `TIMESTAMP WITH TIME ZONE` does; values are normalized to the database timezone and converted to the session timezone on retrieval. Choose Java types and session timezone configuration based on business requirements rather than column names alone.

For systems recording global instants, standardize on UTC or an explicit timezone convention, and test across JVMs in different timezones as well as differing session/database timezones.

### 8.5. CLOB, NCLOB, and BLOB

Oracle LOBs store large payloads:

- `CLOB`: characters in the database character set.
- `NCLOB`: characters in the national character set.
- `BLOB`: binary data.

JPA can map them using `@Lob`:

```java
@Lob
@Column(name = "DESCRIPTION")
private String description;

@Lob
@Column(name = "DOCUMENT_CONTENT")
private byte[] documentContent;
```

`String` and `byte[]` are convenient for small or medium payloads, though they materialize the entire value onto the JVM heap. For large LOBs, consider JDBC `Clob`/`Blob`, streams, or provider streaming APIs. Close streams and LOB locators properly and keep connections open while streaming.

Do not add `@Lob` to small text fields simply out of habit; mappings must match DDL and usage patterns.

### 8.6. RAW and UUID

Oracle `RAW(n)` typically maps to `byte[]`. When storing UUIDs, you can use `RAW(16)` with a converter or supported Hibernate mapping:

```java
@Converter(autoApply = false)
public class UuidRawConverter
        implements AttributeConverter<UUID, byte[]> {

    @Override
    public byte[] convertToDatabaseColumn(UUID value) {
        if (value == null) return null;
        ByteBuffer buffer = ByteBuffer.allocate(16);
        buffer.putLong(value.getMostSignificantBits());
        buffer.putLong(value.getLeastSignificantBits());
        return buffer.array();
    }

    @Override
    public UUID convertToEntityAttribute(byte[] value) {
        if (value == null) return null;
        if (value.length != 16) {
            throw new IllegalArgumentException("Expected 16-byte UUID");
        }
        ByteBuffer buffer = ByteBuffer.wrap(value);
        return new UUID(buffer.getLong(), buffer.getLong());
    }
}
```

This converter defines byte ordering via the two `long` components of `UUID`; all services reading or writing the column must follow the same byte order. Using `VARCHAR2(36)` to store text UUIDs is easier to inspect in SQL tools, though it consumes more bytes than `RAW(16)`. Pick one standard and never mix encodings across systems.

### 8.7. Booleans in Oracle

Oracle Database prior to 23c/23ai lacks a standard SQL `BOOLEAN` column type like PostgreSQL. Schemas commonly represent booleans using:

- `NUMBER(1)` with `0`/`1`.
- `CHAR(1)` or `VARCHAR2(1)` with `Y`/`N` or `T`/`F`.

Example converter:

```java
@Converter
public class BooleanYnConverter
        implements AttributeConverter<Boolean, String> {

    @Override
    public String convertToDatabaseColumn(Boolean value) {
        if (value == null) return null;
        return value ? "Y" : "N";
    }

    @Override
    public Boolean convertToEntityAttribute(String value) {
        if (value == null) return null;
        return switch (value) {
            case "Y" -> true;
            case "N" -> false;
            default -> throw new IllegalArgumentException(
                    "Unexpected boolean value: " + value);
        };
    }
}
```

Apply the converter on the field:

```java
@Convert(converter = BooleanYnConverter.class)
@Column(name = "ACTIVE_FLAG", length = 1)
private Boolean active;
```

Oracle Database 23c/23ai introduces a native SQL `BOOLEAN` type; direct usage depends on JDBC driver, Hibernate version, and schema compatibility. Do not use native SQL `BOOLEAN` columns in 19c environments.

### 8.8. Enums

For business enums, persisting enum names via `EnumType.STRING` is usually preferred:

```java
@Enumerated(EnumType.STRING)
@Column(name = "ORDER_STATUS", length = 30)
private OrderStatus status;
```

`EnumType.ORDINAL` stores numeric positions. Reordering or inserting enum constants in Java silently shifts how historical rows are interpreted. `STRING` is readable, though renaming enum constants still requires a data migration.

## 9. Mapping Primary Keys and Oracle Sequences

### 9.1. Creating a Sequence

```sql
CREATE SEQUENCE order_seq
  START WITH 1
  INCREMENT BY 50
  CACHE 100
  NOCYCLE;
```

`CACHE` improves sequence generation throughput; sequences do not guarantee gapless values. Instance restarts or cache evictions can leave gaps. Never use sequences for gapless invoice numbers when regulations prohibit gaps.

### 9.2. Entity Using GenerationType.SEQUENCE

```java
@Entity
@Table(name = "ORDERS")
public class Order {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_seq_generator")
    @SequenceGenerator(
        name = "order_seq_generator",
        sequenceName = "ORDER_SEQ",
        allocationSize = 50)
    @Column(name = "ORDER_ID")
    private Long id;

    // Other fields
}
```

`allocationSize` and the sequence's `INCREMENT BY` must align with Hibernate's ID optimizer. With pooled optimizers, Hibernate allocates a block of IDs per sequence fetch. Mismatched increments can cause large ID jumps, validation errors, or ID collisions depending on configuration. Verify DDL, Hibernate version, and generator logs.

### 9.3. Identity Columns

Oracle 12c and later support identity columns:

```sql
CREATE TABLE audit_event (
    event_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_type VARCHAR2(50) NOT NULL,
    created_at TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL
);
```

Entities can use `GenerationType.IDENTITY` if the database, Hibernate, and JDBC driver support the generated-key mechanism properly. Identity columns can limit JDBC insert batching; for high-volume inserts, sequence-based IDs usually give Hibernate greater batching flexibility.

## 10. A Complete Oracle Entity Example

DDL:

```sql
CREATE TABLE customers (
    customer_id   NUMBER(19) PRIMARY KEY,
    customer_code VARCHAR2(40 CHAR) NOT NULL,
    display_name  VARCHAR2(200 CHAR) NOT NULL,
    credit_limit  NUMBER(16, 2) DEFAULT 0 NOT NULL,
    active_flag   CHAR(1) DEFAULT 'Y' NOT NULL,
    created_at    TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL,
    version_no    NUMBER(19) DEFAULT 0 NOT NULL,
    CONSTRAINT customers_code_uk UNIQUE (customer_code),
    CONSTRAINT customers_active_ck CHECK (active_flag IN ('Y', 'N'))
);

CREATE SEQUENCE customer_seq START WITH 1 INCREMENT BY 1 CACHE 100;
```

Entity:

```java
@Entity
@Table(name = "CUSTOMERS")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE,
                    generator = "customer_seq_gen")
    @SequenceGenerator(name = "customer_seq_gen",
                       sequenceName = "CUSTOMER_SEQ",
                       allocationSize = 1)
    @Column(name = "CUSTOMER_ID")
    private Long id;

    @Column(name = "CUSTOMER_CODE", nullable = false, length = 40)
    private String customerCode;

    @Column(name = "DISPLAY_NAME", nullable = false, length = 200)
    private String displayName;

    @Column(name = "CREDIT_LIMIT", precision = 16, scale = 2, nullable = false)
    private BigDecimal creditLimit;

    @Convert(converter = BooleanYnConverter.class)
    @Column(name = "ACTIVE_FLAG", length = 1, nullable = false)
    private Boolean active;

    @Column(name = "CREATED_AT", nullable = false)
    private LocalDateTime createdAt;

    @Version
    @Column(name = "VERSION_NO", nullable = false)
    private Long version;

    protected Customer() {}

    public Customer(String customerCode, String displayName,
                    BigDecimal creditLimit) {
        this.customerCode = customerCode;
        this.displayName = displayName;
        this.creditLimit = creditLimit;
        this.active = true;
        this.createdAt = LocalDateTime.now();
    }

    // Getters and domain methods omitted for brevity.
}
```

This example uses `allocationSize = 1` to match `INCREMENT BY 1` without delving into pooled optimizers. In high-throughput systems, a larger allocation size can be chosen provided DDL and Hibernate's optimizer remain synchronized.

## 11. End-to-End Repository and Service

### 11.1. Spring Data Repository

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByCustomerCode(String customerCode);

    boolean existsByCustomerCode(String customerCode);
}
```

Spring Data generates implementations based on entity mappings. Property names in derived query methods match Java field names, not necessarily Oracle column names.

### 11.2. DTO Command and Service Transaction

```java
public record CreateCustomerCommand(
        String customerCode,
        String displayName,
        BigDecimal creditLimit) {}

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long create(CreateCustomerCommand command) {
        if (repository.existsByCustomerCode(command.customerCode())) {
            throw new IllegalArgumentException("Customer code already exists");
        }

        Customer customer = new Customer(
                command.customerCode(),
                command.displayName(),
                command.creditLimit());

        return repository.save(customer).getId();
    }

    @Transactional(readOnly = true)
    public Customer findByCode(String code) {
        return repository.findByCustomerCode(code).orElseThrow();
    }
}
```

Checking `existsByCustomerCode` improves user-facing error messages but does not replace a unique constraint. Two concurrent requests can both pass the check; Oracle's unique constraint is the final safeguard. Handle `DataIntegrityViolationException`/constraint violations to return an appropriate error.

### 11.3. Never Call External APIs Inside Long-Lived Transactions

If a `@Transactional` method calls HTTP services, sends emails, or awaits a message broker, database connections and locks remain held throughout the external wait. Move external calls outside the transaction or use an outbox/event-driven pattern. Database transactions should stay brief and include only changes requiring atomicity.

## 12. Testing Connectivity, Mapping, and Transactions

### 12.1. Testing DataSource Connectivity

A smoke test can borrow a connection and inspect metadata:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();
    assertTrue(metadata.getDatabaseProductName().contains("Oracle"));
    assertTrue(connection.isValid(5));
}
```

Never run this check by opening a new connection on every production request. Use Spring Boot Actuator health indicators or standard monitoring instead.

### 12.2. Testing Data Type Round-Trips

Write tests that insert and read back fields to verify:

- `BigDecimal` retains exact scale and precision.
- `LocalDate`/`LocalDateTime` does not shift days or drop time unexpectedly.
- `OffsetDateTime`/timezones are preserved per chosen semantics.
- Unicode/`NVARCHAR2` values persist and read accurately.
- Large LOBs stream completely.
- `UUID`/`RAW(16)` uses consistent byte ordering.
- Boolean converters handle nulls and invalid values properly.
- String enums remain compatible with existing rows.

Tests must run against an Oracle release and driver close to production; in-memory databases like H2 do not reproduce Oracle `DATE`, `NUMBER`, sequence, LOB, locking, or SQL dialect semantics.

### 12.3. Testing Rollbacks

A test service method can throw an exception after an initial write:

```java
@Transactional
public void createThenFail() {
    repository.save(new Customer(...));
    throw new IllegalStateException("force rollback for test");
}
```

After the method fails, query using a fresh transaction/connection to confirm the row does not exist. Do not read from the same rolled-back persistence context to infer database state.

### 12.4. Testing Concurrency

Open two independent connections/transactions and test:

- Unique constraints when two requests insert the same business key.
- Optimistic locking with `@Version`.
- Pessimistic locking with `SELECT FOR UPDATE`.
- Lock timeouts and deadlocks.
- `READ COMMITTED`/`SERIALIZABLE` behavior if used.

Each thread requires its own transaction and persistence context; `EntityManager` is not thread-safe. Use barriers or latches to coordinate timing rather than fixed sleeps.

## 13. Diagnosing Common Errors

| Error/Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| `ORA-12154` | Could not resolve connect identifier / TNS alias | Check JDBC URL, TNS config, service name, and name resolution |
| `ORA-12514` | Listener does not know requested service | Verify service name, listener registration, and PDB service |
| `ORA-12541` | No listener at host/port | Check listener process, port, firewall, and DNS |
| `ORA-01017` | Invalid username/password | Check secret, account, case-sensitive password, target PDB/service |
| `ORA-28000` | Account is locked | DBA checks account status and profile policy |
| Pool acquisition timeout | Unable to borrow connection within configured wait | Inspect active/idle/pending pool counts, leaks, slow queries/transactions, DB capacity |
| `ORA-00020`/`ORA-00018` | Process/session limit reached | Check `V$RESOURCE_LIMIT`, sessions per user/service, and sum of replica pools |
| `ORA-00904` | Invalid identifier | Check schema migrations, column names, naming strategy, quoted identifiers |
| `ORA-01400` | Inserting `NULL` into `NOT NULL` column | Check mappings, defaults, insert statements, and DDL |
| `ORA-12899` | Value too large for column | Check `BYTE`/`CHAR` semantics, length annotations, and multibyte Unicode |
| `ORA-01438` | Value larger than specified `NUMBER` precision | Check `BigDecimal`, precision/scale, and DDL |
| `ORA-00001` | Unique/primary key violation | Check business keys, sequence/identity sync, and concurrency |
| `ORA-00060` | Deadlock | Inspect transaction order, lock graph, and transaction duration |
| `ORA-08177` | Cannot serialize access for this transaction | Review `SERIALIZABLE` isolation and retry in a fresh transaction |

When troubleshooting, extract the root JDBC/Oracle error code. Spring often wraps exceptions in `DataAccessException`; do not rely solely on the top-level exception class at the REST layer.

### 13.1. Inspecting Sessions from Oracle

```sql
SELECT sid,
       serial#,
       username,
       status,
       machine,
       program,
       module,
       action,
       service_name,
       sql_id,
       event
FROM v$session
WHERE username = 'APP_USER'
ORDER BY logon_time;
```

To correlate sessions with requests, applications can call `DBMS_APPLICATION_INFO.SET_MODULE` and `DBMS_SESSION.SET_IDENTIFIER` on the active connection. When pooling connections, reset session-specific attributes before returning connections to the pool so subsequent requests do not inherit stale metadata or state.

### 13.2. Inspecting Open Transactions

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
WHERE s.username = 'APP_USER'
ORDER BY t.start_time;
```

Long-lived transactions may indicate missing commit/rollback calls, external calls inside transaction boundaries, or leaked connections. Identify the owner and impact before terminating a session.

## 14. Security and Production Operations

### 14.1. Credentials and TLS

- Retrieve username and password from a secret store or platform secret injection.
- Use a least-privilege runtime account.
- Enforce TLS/TCPS or Oracle Native Network Encryption per security policy.
- Never log JDBC URLs if they contain credentials or tokens.
- Rotate credentials smoothly and verify pools reconnect cleanly after rotation.

### 14.2. Avoid Broad SQL/Bind Logging in Production

`org.hibernate.SQL=DEBUG` is useful in dev/test environments. Bind-parameter `TRACE` logging can expose customer data, tokens, or sensitive values. Enable only briefly with narrow scope and protected logs.

### 14.3. Monitoring Pool and Database Health

Monitor:

- Pool active, idle, pending threads, and acquisition timeouts.
- Connection creation/close rates and leak detection alerts.
- Transaction durations, rollback rates, and query latencies.
- Oracle session/process utilization and wait events.
- `SQL_ID`, module/action, top SQL, and lock contention.
- Error rates by `ORA` code and service/PDB.

Do not blindly increase pool size when pending borrowers rise. If the database is already CPU- or lock-saturated, a larger pool can worsen contention.

### 14.4. Session State and Connection Pooling

Connection pools reuse physical sessions. Avoid letting requests alter `CURRENT_SCHEMA`, NLS settings, session timezone, application context, or package state without resetting them. If session state is needed, initialize and clean it up deterministically—even on exceptions. Leaked session state can cause subsequent requests to hit the wrong schema or tenant.

## 15. Practical Implementation Workflow

1. DBA provides host, port, service name/PDB, runtime account, and TLS/wallet requirements.
2. Verify connectivity using an Oracle CLI tool; confirm database, service, and container.
3. Choose the Oracle JDBC driver matching JDK, database release, and support matrix; pin the version in the build.
4. Configure the `DataSource`/connection pool using secrets, timeouts, and a capacity-budgeted pool size.
5. Align Spring Boot/Hibernate versions; let Hibernate auto-detect the Oracle dialect when appropriate.
6. Manage schemas with Flyway/Liquibase; set `ddl-auto: validate` in production.
7. Design entity mappings matching Oracle DDL: `NUMBER`, `VARCHAR2`, `DATE`/`TIMESTAMP`, LOB, `RAW`, Booleans, and sequences.
8. Define transaction boundaries at service methods; configure rollback rules, propagation, isolation, and timeouts.
9. Use `JdbcTemplate`/`DataSourceUtils` when mixing JDBC into JPA transactions; never manually commit Spring-managed connections.
10. Test type round-trips, rollbacks, concurrency, locking, generated IDs, and unique constraint violations on real Oracle or a compatible environment.
11. Observe pool metrics, transactions, SQL, and Oracle sessions in staging under production-like load.
12. Deploy with runbooks, dashboards, alerts, and application/schema rollback plans.

## 16. Pre-Production Checklist

| Area | Questions to Confirm |
|---|---|
| Connection | Does the URL target the right service/PDB? Are listener and network/TLS working? |
| Driver | Is `ojdbc` compatible with the JDK, Oracle release, and application server? |
| Credentials | Are secrets externalized from source code? Does the runtime user have least privilege? |
| Pool | Does total max connections across all replicas fit within DB capacity? Are timeouts tuned? |
| Hibernate | Is the dialect compatible with the major version? Does metadata auto-detection work? |
| Schema | Does Flyway/Liquibase manage DDL? Is `ddl-auto` safe against modifying schema? |
| Mapping | Are `NUMBER` precision/scale, `DATE`/`TIMESTAMP`/timezone, LOB, `RAW`, Boolean, and enum mappings tested? |
| Identifiers | Do sequence/identity settings and `allocationSize` match DDL? |
| Transactions | Are service boundaries clear? Are rollback rules and propagation accurate? |
| Isolation/Locking | Have lost updates, lock timeouts, deadlocks, and serialization conflicts been tested? |
| JDBC/JPA Mix | Same `DataSource`/transaction manager? No manual commits or closes on transaction-bound connections? |
| Observability | Are pool metrics, `SQL_ID`, module/action, `ORA` codes, and transaction durations captured? |
| Recovery | Are backups, schema migration rollbacks, and operational runbooks ready? |

## 17. Key Principles to Remember

- The JDBC driver, `DataSource` pool, Hibernate, and transaction manager are distinct layers; pinpoint issues at the proper layer.
- Use a JDBC Thin URL with the DBA-provided service name/PDB; verify connectivity independently before debugging the ORM.
- Select `ojdbc` based on JDK, Oracle release, and the support matrix; never match driver versions mechanically to database numbers.
- Use bounded connection pools; sum potential connections across all replicas, services, and background workloads.
- Place Spring `@Transactional` at service boundaries; self-invocation bypasses proxies and checked exceptions do not roll back by default.
- Oracle defaults to `READ COMMITTED`; `SERIALIZABLE` can raise `ORA-08177` and requires retrying in a new transaction.
- When mixing JPA and JDBC, share the same `DataSource`/transaction manager; use `JdbcTemplate` or `DataSourceUtils` to enlist in the active transaction.
- `NUMBER(p,s)` typically maps to `BigDecimal`; Oracle `DATE` includes hours through seconds; distinguish `TIMESTAMP` variants and timezone behavior.
- Stream large LOBs; standardize conventions for `UUID`/`RAW`, Booleans, and enums.
- Sequence `allocationSize` must match DDL; sequences do not guarantee gapless values.
- Use Flyway/Liquibase with `ddl-auto: validate`; never let Hibernate alter production schemas unguarded.
- Test round-trips, rollbacks, concurrency, and pool behavior against an Oracle release and driver matching production.

## Oracle, Spring, and Java Reference Documentation

- [Oracle JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/)
- [Oracle Database 19c SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html)
- [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html)
- [Oracle Database 19c SQL Language Reference — CREATE SEQUENCE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SEQUENCE.html)
- [Spring Boot Reference — SQL Databases and DataSource](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/)
- [Hibernate ORM User Guide — Basic Types](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#basic)
- [Hibernate ORM User Guide — Identifiers](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#identifiers)
- [Java SE API — JDBC](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/package-summary.html)
