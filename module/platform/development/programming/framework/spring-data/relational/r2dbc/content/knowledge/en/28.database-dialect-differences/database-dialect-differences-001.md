# Evaluating R2DBC Support of Database Engines and Drivers

When choosing a database for a Spring Data R2DBC application, you cannot simply ask whether the database engine supports R2DBC. R2DBC is an SPI on the Java application side; the database engine still communicates over its own protocol and capabilities, while the R2DBC driver is responsible for implementing the SPI and translating operations into commands the database understands. Spring Data R2DBC further relies on the driver, metadata, and dialect to map entities, generate SQL, and handle data types.

Therefore, actual support is the result of multiple components working together compatibly: the database server version, R2DBC driver, R2DBC SPI, Spring Framework, Spring Data Relational/R2DBC, Spring Boot, and Java. A driver may connect successfully yet still not fully support the data types, generated values, transactions, cancellation, pooling, or SQL features the application needs.

A proper evaluation must start from business requirements down to database and driver capabilities, and then be confirmed with integration tests on the exact combination of versions planned for deployment. This lesson explains how to build a compatibility matrix, identify limitations at each layer, design tests, and make evidence-based technical decisions.

## 1. What Is R2DBC and Which Component Is Responsible?

R2DBC (Reactive Relational Database Connectivity) defines an SPI for Java applications to access relational databases reactively. The SPI provides abstractions such as `ConnectionFactory`, `Connection`, `Statement`, `Result`, `Row`, and `RowMetadata`. A specific driver implements these abstractions for a corresponding database engine and protocol.

A database engine does not necessarily implement R2DBC directly. Typically, the driver runs inside the application, talks to the database over its native protocol or a vendor-provided protocol, and exposes the R2DBC API to Java code.

```text
Spring application
       |
       v
Spring Data R2DBC
  - Repository
  - R2dbcEntityTemplate
  - Mapping / dialect
       |
       v
R2DBC SPI
  - ConnectionFactory
  - Connection / Statement
  - Result / Row
       |
       v
Vendor R2DBC driver
  - protocol handling
  - type conversion
  - parameter binding
  - transaction integration
       |
       v
Database server
  - SQL engine
  - data types
  - constraints / indexes
  - transactions / isolation
```

Different layers have different responsibilities:

- **Database server:** determines SQL syntax, data types, transactions, isolation, constraints, generated columns, locking, and engine-specific features.
- **R2DBC driver:** implements the SPI, manages the protocol, converts types, binds parameters, reads results, handles errors, and interacts with the server.
- **R2DBC SPI:** defines the common API contract so applications can use drivers consistently.
- **Spring Data R2DBC:** provides repositories, entity mapping, conversion, dialects, and query abstractions built on the SPI.
- **Spring Boot:** provides auto-configuration, dependency management, `ConnectionFactory` configuration, pooling, and related components.

A failure can originate at any layer. For example, the server supports JSONB, but the driver does not convert that type conveniently; the driver supports transactions, but the Spring Data dialect does not yet represent a specific syntax; or Spring Boot manages a driver version that is incompatible with the running server version.

## 2. Evaluate by Version Combination, Not Product Name

Do not record simplistic conclusions such as "Database X supports R2DBC". Conclusions must be tied to a specific combination of versions.

A compatibility matrix should include at least these components:

| Component | Information to Record | Why It Matters |
|---|---|---|
| Database product | Product name and server version | Determines SQL, data types, transactions, and available features |
| R2DBC driver | Artifact, version, vendor/publisher | Determines connectivity and SPI implementation |
| R2DBC SPI | API version implemented by the driver | Determines the contract between application and driver |
| Spring Boot | BOM/parent version | Manages dependencies and auto-configuration |
| Spring Framework | Version | Affects `DatabaseClient`, transactions, and reactive integration |
| Spring Data Relational | Version | Affects mapping, dialect, repositories, and conversion |
| Java runtime | JDK version | Affects bytecode, TLS, drivers, and dependent libraries |
| Pool implementation | R2DBC Pool and version if used | Affects acquisition, validation, lifecycle, and metrics |

Example of an environment record file:

```yaml
database:
  product: PostgreSQL
  server-version: "<version-tested>"
driver:
  artifact: "io.r2dbc:r2dbc-postgresql"
  version: "<version-tested>"
framework:
  spring-boot: "<version-tested>"
  spring-data-relational: "<managed-version>"
  r2dbc-spi: "<resolved-version>"
runtime:
  java: "<jdk-version>"
pool:
  artifact: "io.r2dbc:r2dbc-pool"
  version: "<resolved-version>"
```

Placeholders must be replaced with actual versions from the dependency lock/BOM and deployment environment. Do not independently pick the latest driver version without checking the Spring Boot BOM; review dependency management and release notes for each component.

### 2.1. Spring Boot BOM and Dependency Convergence

Spring Boot typically manages compatible versions of Spring Framework, Spring Data, and integration libraries. When adding a driver, start with the version recommended for the project's Boot version. If overriding a version, have a clear reason and inspect the full dependency tree.

Common problems when versions drift out of alignment:

- The driver is compiled against an SPI version different from the API provided at runtime.
- A mapping feature in Spring Data requires an API not present in an older driver.
- The pool and driver have incompatible lifecycle behavior.
- Upgrading the driver changes conversion or exception mapping.
- The JDK or TLS provider does not meet driver/server requirements.

Save the dependency resolution output in build artifacts or an SBOM so the tested combination can be reproduced.

### 2.2. Separate Documented Capabilities from Verified Capabilities

Driver documentation states what features are designed to be supported; integration tests verify the behavior of the exact versions and configuration in use. Classify each item in the matrix:

- **Documented:** driver/server documentation claims support.
- **Tested:** automated tests have passed on the specific version combination.
- **Limited:** supported with known conditions or constraints.
- **Unsupported:** not supported or does not meet requirements.
- **Unknown:** insufficient reliable evidence.

Do not turn `Unknown` into `Supported` just because a single simple query runs.

## 3. Verifying That the Driver Implements R2DBC SPI Appropriately

### 3.1. ConnectionFactory and Metadata

Applications typically create connections through `ConnectionFactory`. You can inspect metadata to verify the driver name and database name exposed by the driver:

```java
ConnectionFactory connectionFactory = ...;

ConnectionFactoryMetadata metadata = connectionFactory.getMetadata();
log.info("R2DBC driver: {}", metadata.getName());
```

This metadata is useful for recording the environment and helping Spring Data resolve the dialect. However, driver name or metadata is not proof that every feature works. It is only identification information at the SPI level.

### 3.2. Verifying Connection Creation and Statement Execution

A smoke test should verify:

1. `ConnectionFactory` is created with the correct URL, credentials, and TLS settings.
2. A connection can be acquired.
3. A statement can be created and parameters bound.
4. The statement can be executed and `Result` read.
5. The connection is properly closed/released on completion or error.

Simple check example:

```java
Mono<Long> databaseCheck(ConnectionFactory factory) {
    return Mono.usingWhen(
            Mono.from(factory.create()),
            connection -> Mono.from(connection
                            .createStatement("SELECT 1").execute())
                    .flatMap(result -> Mono.from(result.map(
                            (row, metadata) -> row.get(0, Long.class)))),
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close()));
}
```

`Mono.usingWhen` manages closing the connection when the publisher completes, emits an error, or is cancelled. In normal Spring Data applications, prefer letting `DatabaseClient`, `R2dbcEntityTemplate`, or Repositories manage connections rather than acquiring them directly.

### 3.3. Verifying Cancellation

Reactive APIs must respond properly when a subscriber cancels a subscription. Verify whether cancelling a running query releases or returns the connection to a valid state, whether the driver sends a cancel request to the server, and whether the server continues executing the statement in the background.

Cancellation does not always stop server-side work immediately; behavior depends on the driver and database protocol. For long queries or large result streams, confirm that resources are reclaimed and connections are not left stuck after client disconnect.

## 4. Verifying the Spring Data R2DBC Dialect

Spring Data R2DBC uses `R2dbcDialect` to handle differences between database engines, such as bind marker generation, supported data types, and SQL details needed for mapping.

The dialect is usually resolved from `ConnectionFactory`:

```java
R2dbcDialect dialect = DialectResolver.getDialect(connectionFactory);
```

Successful resolution indicates that Spring Data recognizes a matching dialect. It does not guarantee that every database-specific feature is abstracted away.

### 4.1. What to Check in the Dialect

- Bind markers are generated appropriately for the driver, such as positional or named markers after framework expansion.
- Scalar data types and default conversions are suitable.
- Generated IDs are handled properly by the dialect/driver.
- SQL generated by the template has syntax compatible with the database.
- Paging, limit/offset, and update/delete operations are supported.
- Custom types or custom mappings do not conflict with default conversions.

### 4.2. A Dialect Is Not a Universal SQL Translator

A dialect does not convert every SQL statement from database A into equivalent SQL for database B. If the application uses JSON operators, vendor-specific CTEs, full-text search, array functions, stored procedures, or engine-specific hints, that SQL can still depend on the specific database engine.

When portability is required, prefer operations commonly supported by Spring Data and isolate engine-specific SQL in a dedicated query layer. When leveraging engine-specific features, document the target database and add tests for that dialect.

## 5. Evaluating Data Type Support

Data type mapping is one of the biggest differences between drivers. Do not just check that Java and SQL types share similar names; verify binding, reading, nulls, precision, timezones, and boundary values.

### 5.1. Type Groups to Check

| Group | SQL Examples | Common Java Types | Questions to Confirm |
|---|---|---|---|
| Integers | `SMALLINT`, `INTEGER`, `BIGINT` | `Short`, `Integer`, `Long` | Is there overflow or implicit type conversion? |
| Decimals | `NUMERIC`, `DECIMAL` | `BigDecimal` | Are precision and scale preserved? |
| Boolean | `BOOLEAN`, equivalent types | `Boolean` | Are there differences for true/false and null? |
| Strings | `VARCHAR`, `CHAR`, `TEXT` | `String` | Unicode, collation, and length limits? |
| Binary | `BLOB`, `BYTEA`, `VARBINARY` | `byte[]`, `ByteBuffer`, or driver type | Is everything loaded into memory or is streaming supported? |
| Date | `DATE` | `LocalDate` | Is any timezone conversion applied? |
| Time | `TIME`, `TIMESTAMP` | `LocalTime`, `LocalDateTime` | Are precision and timezone preserved? |
| Timestamp with timezone | `TIMESTAMPTZ` or equivalent | `Instant`, `OffsetDateTime` | How does the driver normalize offsets? |
| UUID | `UUID` or native type | `UUID` | Is a converter required? |
| JSON | `JSON`, `JSONB`, or text | `String`, `Json`, driver-specific object | Does it bind natively and read accurately? |
| Array | SQL array | array/collection or driver type | Are binding, reading, and null elements supported? |
| Native enum | custom enum type | Java enum or `String` | Mapped by name, label, or ordinal? |
| Spatial | geometry/geography | driver type or specialized library | SRID, binary format, and operators? |

Not every driver supports all of these groups in the same way. For specialized types, check driver documentation and write Spring Data converters if necessary.

### 5.2. Testing Precision and Scale

For `DECIMAL(19, 4)`, test these values:

- Minimum and maximum values within the allowed precision.
- Values with full decimal digits.
- Values with more digits than the scale.
- Negative numbers, zero, and very small values.
- Null values if the column is nullable.

Confirm that the driver does not convert `BigDecimal` through `double` and lose precision. If the database rounds or rejects scales exceeding the limit, document that rule in domain validation.

### 5.3. Testing Timezone and Timestamp Precision

Verify how the database and driver handle `Instant`, `OffsetDateTime`, and `LocalDateTime`:

- Is the point in time stored and read back as the exact same instant?
- Is the offset preserved or normalized to UTC?
- Does the database store microseconds, milliseconds, or another precision?
- Do DST and session timezone affect results?
- Which Java type does the driver return when reading the column?

Do not use `LocalDateTime` as an absolute instant if the business requires identifying a global point in time. Define timezone conventions clearly across schema, session, and application.

### 5.4. Testing JSON, Arrays, and Native Enums

These types often vary significantly across databases:

- JSON may be stored as text, native JSON, or binary JSON.
- Arrays may support multiple dimensions, null elements, or only a subset of element types.
- Native enums may require special bind types and label-based mapping.

Test both write and read paths, query predicates on the data type, nulls, legacy data, and schema migrations. If using `R2dbcCustomConversions`, verify that converters apply in Repositories/Templates and do not assume they automatically apply to every manual `DatabaseClient` bind.

## 6. Parameter Binding and Null Data Types

The driver must translate bind markers and Java values into server-compatible parameters. Verify:

- Are named parameters expanded properly by the framework into the driver's markers?
- Does positional binding preserve order?
- Does `bindNull` require an explicit Java type?
- Are collections/arrays expanded or bound as native types?
- Do custom types require converters or custom codecs?
- Do large values exceed protocol or parameter count limits?

Example using `DatabaseClient`:

```java
return databaseClient.sql("""
        SELECT id, email
        FROM customers
        WHERE status = :status
          AND deleted_at IS NULL
        """)
        .bind("status", status)
        .map((row, metadata) -> new CustomerSummary(
                row.get("id", Long.class),
                row.get("email", String.class)))
        .all();
```

For null parameters, use the typed null-binding API:

```java
spec.bindNull("optionalCode", String.class);
```

Do not call `bind(name, null)` if the API requires `bindNull`. The target type matters because the server needs to know the parameter type when no data value is present.

### 6.1. SQL Injection and Identifiers

Bind parameters are for values, not for table names, column names, or SQL keywords. If sort fields or filter columns can be chosen dynamically, use an enum/whitelist. Never concatenate request data directly into SQL.

### 6.2. Placeholder Expansion for Collections

Some Spring APIs support expanding a collection into multiple bind markers inside an `IN` clause; details depend on the API and version. Check how empty lists, very large lists, and database parameter count limits are handled. If the driver has a native array type and suitable query syntax, you can use driver-specific array binding; do not assume every database engine shares the same syntax.

## 7. Transactions, Isolation, and Savepoints

A driver may connect and run `SELECT` queries successfully while still differing in transaction behavior. Evaluate scenarios critical to business logic.

### 7.1. Commit and Rollback

Verify that the transaction manager can:

- Begin a transaction.
- Execute multiple statements on the same transaction connection.
- Commit when the publisher completes successfully.
- Roll back when the publisher emits an error.
- Return the connection to the pool in a valid state after commit/rollback.

Spring reactive transaction example:

```java
@Transactional
public Mono<OrderEntity> createOrder(OrderEntity order) {
    return inventoryRepository.reserve(order)
            .then(orderRepository.save(order));
}
```

Integration tests must confirm that if `reserve` succeeds and `save` fails, inventory changes are rolled back with the transaction.

### 7.2. Isolation Levels

Verify that the database and driver support the isolation levels required by the application, such as `READ_COMMITTED`, `REPEATABLE_READ`, or `SERIALIZABLE`. Actual names and behavior can vary across products. Confirm dirty reads, non-repeatable reads, phantom reads, and serialization failures for the specific database.

Do not assume isolation levels with the same name behave identically across all engines. Check product documentation and write concurrency tests for critical workflows.

### 7.3. Savepoints and Nested Transactions

If the application needs savepoints or nested transaction semantics, check whether the driver and database support the corresponding API/syntax. Do not infer nested transaction support merely because `@Transactional` works.

### 7.4. Concurrent Statements on a Single Connection

In a reactive transaction, multiple repository calls may participate in the same transaction and share a connection. Some drivers do not allow concurrent statement execution on the same connection. If ordering is needed, use `concatMap` or chain publishers sequentially; if parallelism is needed, evaluate separating transactions/connections and the atomicity implications.

## 8. Generated Values, Identity, and RETURNING

Applications often need database-generated IDs or values after insert. This capability depends on SQL dialect, driver, and server.

Test:

- Is the returned identity/sequence key of the expected Java type?
- Can multiple generated values be retrieved at once?
- Do triggers modify values before returning results?
- Do generated/computed columns appear in results?
- Does the driver support `RETURNING` or an equivalent generated-values mechanism?
- Does `save` return an entity containing the new values, or is a follow-up select needed?

For example, PostgreSQL can use:

```sql
INSERT INTO customers (email)
VALUES (:email)
RETURNING id, email, created_at;
```

`RETURNING` is a database-specific feature/syntax, not guaranteed to be portable across all engines. If the application supports multiple databases, use a dedicated abstraction or dialect-specific query implementation. If you only need a generated ID, check Spring Data R2DBC's built-in support before writing custom SQL.

## 9. CLOB/BLOB, Streaming, and Large Data

For large data such as files, documents, or binary payloads, do not only check whether reading/writing works. You need to know whether the driver loads all data into memory or provides streaming, size limits, cancellation behavior, and connection hold duration.

Questions to answer:

- Are database LOB types supported?
- Is data represented as `byte[]`, `ByteBuffer`, `Blob`, `Clob`, or a custom type?
- Can it stream in chunks or must it materialize completely?
- When a subscriber cancels mid-stream, are LOB resources and connections released?
- Are there parameter/result size limits?
- What is the trade-off between storing binary data directly versus external object storage?

If the driver only supports materializing large data, enforce size limits and evaluate memory footprint. Do not hold a database connection open while slowly streaming a file to an HTTP client if reading/streaming can be decoupled or dedicated storage can be used.

## 10. Connection Pools, TLS, and Operations

A driver that works locally may not meet production operational requirements. Verify:

- Proper connection creation and closure.
- Acquire timeout and connection validation.
- Idle/lifetime eviction.
- Reaction when the database restarts or the network drops.
- TLS mode, certificate validation, and hostname verification.
- Authentication methods, secret rotation, and credential refresh.
- Metrics for active, idle, pending connections, and acquire latency.
- Logging/observability without exposing credentials or sensitive query parameters.
- Failover, DNS changes, or regional endpoint switching if required by architecture.

### 10.1. A Pool Cannot Fix an Unstable Driver

A pool manages connections, but it cannot fix protocol bugs, resource leaks in the driver, or incorrect type mappings. If connections are frequently marked invalid, examine driver logs, server errors, and release notes before increasing pool size.

### 10.2. Failover and Reconnect

When the database fails over or a connection drops, the driver/pool must emit understandable errors and never hand a broken connection to another request. Test behavior during:

- Server restart.
- Network timeout or reset.
- Connections idle longer than server timeout.
- DNS/endpoint changes.
- Expired or rotated credentials.

Do not retry all errors unconditionally. For write operations, handle cases where the client loses connection after the database has committed but before receiving acknowledgement; idempotency keys or status checks may be necessary.

## 11. SQL Capabilities and Engine-Specific Features

The R2DBC SPI provides a common way to execute statements, but SQL remains database-dependent. List the features the application actually uses:

- `LIMIT/OFFSET` or equivalent pagination syntax.
- CTEs and recursive CTEs.
- Window functions.
- `RETURNING` or generated values.
- `INSERT ... ON CONFLICT`, `MERGE`, or equivalent upsert.
- JSON/JSONB operators.
- Arrays, native enums, and spatial types.
- Full-text search.
- Stored procedures/functions.
- Advisory locks, row locks, and locking clauses.
- Partial indexes, expression indexes, and generated columns.

Evaluate both the server and the driver. A server may support a syntax, yet the driver still needs to support binding/reading the associated result types. The Spring Data dialect may not abstract that feature; custom SQL can still be used, though it increases coupling to the specific database.

### 11.1. Repository Derivation Does Not Cover All SQL

Derived query methods fit property-based queries and common predicates. When CTEs, window functions, or engine-specific operators are needed, use `@Query`, `DatabaseClient`, or a custom repository. This is a boundary of the query abstraction, not necessarily a driver limitation.

### 11.2. Evaluating Upsert

There is no single upsert syntax supported by every database. If business logic relies on atomic upsert, choose a dialect-specific implementation and test concurrency. Avoid the `SELECT`-then-`INSERT` pattern because two requests can pass the existence check simultaneously; unique constraints are still essential.

## 12. Exception Mapping and Observability

The driver translates server/protocol errors into exceptions at the R2DBC layer; Spring may translate certain errors into appropriate `DataAccessException` types. Check these error groups:

- Unique/primary key violations.
- Foreign key violations.
- Not-null/check constraint violations.
- Deadlocks and lock timeouts.
- Serialization failures.
- Connection refused, reset, or timeout.
- Authentication/TLS failures.
- Cancelled queries.
- Conversion or unsupported data types.

Evaluate whether exceptions preserve SQL state/vendor codes and causes, because services may need to distinguish duplicate keys from other integrity errors. Do not write business logic based on driver message strings when more stable error codes exist.

Metrics and tracing should provide visibility into:

- Query latency by query group.
- Connection acquire latency and pending borrowers.
- Error counts by category.
- Timeout/cancellation counts.
- Transaction duration and rollbacks.
- Row counts returned and payload sizes if needed.

## 13. Support Verification Test Matrix

A matrix can be organized by feature and evidence:

| Group | Minimum Test | Results to Record |
|---|---|---|
| Connectivity | Acquire, execute `SELECT 1`, close | Pass/fail, latency, driver metadata |
| CRUD | Insert, select, update, delete | Mapping and affected row counts |
| Bind parameters | String, number, null, collection | Bind types and limits |
| Generated ID | Insert without providing ID | Returned ID and Java type |
| Defaults | Omit column, explicit null, `DEFAULT` | Actual stored value |
| Data types | Decimal, temporal, UUID, JSON, array, binary | Round-trip and precision |
| Transactions | Commit, rollback, multi-statement | Final state in database |
| Isolation | Two concurrent read/write transactions | Observed anomalies/behavior |
| Concurrency | Multiple queries and multiple requests | Pool, latency, throughput |
| Cancellation | Cancel query/stream mid-flight | Resource cleanup and server behavior |
| Large results | Read many rows/LOBs | Memory, backpressure, connection duration |
| Error mapping | Constraint, timeout, disconnect | Exception type, SQL state, cause |
| Failover | Restart/network reset | Recovery, errors, and retry behavior |
| Security | TLS, auth, secret rotation | Handshake, certificates, reconnect |
| Spring mapping | Repository, Template, converters | Entity mapping and generated values |

Each row must record the database, driver, Spring Boot/Data, and JDK versions, along with configuration and test environment. If a test only runs on H2 while production uses a different database, it does not prove the production driver supports that feature.

## 14. Building Environment-Accurate Integration Tests

### 14.1. Use the Database Matching Production

In-memory database tests are useful for certain logic, but do not replace integration tests against the actual database engine. Differences can appear in SQL syntax, data types, generated keys, transaction isolation, collation, and exception mapping.

Database containers can be used in CI to create repeatable environments. Container images should be version-pinned; avoid mutable tags when reproducible results are needed.

### 14.2. Test Through Spring Data and Through the SPI

Maintain two testing layers:

- **Driver/SPI tests:** verify lowest-level behavior such as connections, binding, results, cancellation, and transactions.
- **Spring Data integration tests:** verify repositories, `R2dbcEntityTemplate`, dialects, custom conversions, auditing, generated values, and entity mapping.

If SPI tests pass but repository mapping fails, the issue may lie in the Spring Data dialect or entity metadata. If SPI tests already fail, focus on the driver, server, or configuration first.

### 14.3. Reactive Repository Test Example

```java
@DataR2dbcTest
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void insertsAndReadsCustomer() {
        CustomerEntity customer = new CustomerEntity(
                null, "an@example.com", "An");

        StepVerifier.create(repository.save(customer)
                .flatMap(saved -> repository.findById(saved.id())))
                .assertNext(found -> {
                    assertThat(found.id()).isNotNull();
                    assertThat(found.email()).isEqualTo("an@example.com");
                })
                .verifyComplete();
    }
}
```

This is a structural test example; provide schema, `ConnectionFactory`, and test configuration matching the target database. With multiple databases, you can run the same contract test suite across each driver via profiles or separate CI pipelines.

### 14.4. Testing Concurrency and Transactions

Important tests should use two or more real connections/transactions to simulate contention. Do not use a mock repository to conclude that database isolation or optimistic locking works properly.

Verify the final data state, not just exceptions. An operation that emits an error while partial data was committed outside the transaction can still cause business defects.

## 15. Process for Evaluating a New Database or Driver

You can follow these steps:

1. List the SQL features and data types the application actually uses.
2. Identify the specific database product/version and R2DBC driver.
3. Review driver documentation, release notes, SPI version, and compatibility matrix with Spring Boot/Spring Data.
4. Lock dependencies via BOM or version catalog; record the dependency tree.
5. Create `ConnectionFactory`, inspect metadata, and run a smoke test.
6. Verify that Spring Data resolves the dialect correctly.
7. Test CRUD, parameter binding, nulls, and custom conversions.
8. Test identity, defaults, generated columns, triggers, and returned values.
9. Test transactions, rollbacks, isolation, and concurrency.
10. Test cancellation, large results, LOBs, and pool saturation if required by the workload.
11. Test TLS, authentication, reconnect, failover, and observability.
12. Run integration tests against the exact server version in CI.
13. Mark each feature as Documented, Tested, Limited, Unsupported, or Unknown.
14. Decide to accept, conditionally accept, or reject based on mandatory requirements and remaining risks.

## 16. Decision Criteria

A driver may be suitable for standard CRUD applications yet unsuitable for LOB streaming, native JSON, or complex transaction workloads. Do not rate "good support" with a single overall score without considering the importance of each feature.

Criteria can be categorized as:

### Mandatory

- Stable connectivity with the target database version.
- Spring Boot/Spring Data recognizes the driver and dialect.
- CRUD, parameter binding, core data types, and required transactions work correctly.
- Pooling, timeouts, TLS, and authentication meet production requirements.
- Critical concurrency and rollback tests pass.

### Important With Possible Workarounds

- JSON/arrays/native enums.
- Generated values other than ID.
- CTEs/window functions or engine-specific features.
- Streaming LOBs and cancellation.
- Detailed metrics or advanced failover.

If an important feature is missing but can be replaced by custom SQL, converters, or a separate service, document the cost and limitations. If a mandatory feature such as transaction behavior or core data type support is missing, do not accept the driver merely because smoke tests pass.

### Operations and Support Lifecycle

Evaluate patch release speed, driver project activity, security reporting processes, release cadence, documentation, examples, and production support options. A feature-rich driver that is no longer maintained presents a long-term risk.

## 17. Common Misconceptions

### A Database With a Native Protocol Automatically Has R2DBC

R2DBC is typically implemented by a Java-side driver. The server does not necessarily implement the SPI. Choose an appropriate driver for the database.

### Being Able to Connect Means Every Feature Is Supported

Connecting and running `SELECT 1` only verifies basic connectivity. It does not test transactions, data types, cancellation, generated values, or pool behavior.

### Having an R2DBC Driver Means Spring Data Supports Everything

The driver implements the SPI; Spring Data also needs an appropriate dialect and mapping. Vendor-specific SQL may still require `DatabaseClient` or custom repositories.

### Reactive Drivers Make the Database Resource-Unlimited

Non-blocking I/O reduces thread blocking while waiting on I/O, but the database still has connection, CPU, I/O, lock, and memory limits. Concurrency limits and query optimization are still necessary.

### Passing H2 Tests Proves PostgreSQL/MySQL/SQL Server Behave the Same

Each database has a different SQL dialect, type system, transaction semantics, and driver. Test the production dialect on the target database.

### Spring Data Dialects Automatically Translate All Custom SQL

Dialects handle the differences the framework knows about. Hand-written SQL still depends on the target database's syntax and features.

### Every Generated Value Appears in the Entity Returned by save

The driver/dialect may return only the ID or a subset of values. Verify the actual result; re-read the entity if needed.

### Retries Solve All Connection Errors

Retries cannot fix schema errors, mapping bugs, authentication failures, or non-idempotent writes. Classify errors and bound retries.

## 18. Evaluation Checklist

- [ ] Recorded exact database product and server version.
- [ ] Recorded driver artifact/version and R2DBC SPI version.
- [ ] Spring Boot, Spring Framework, Spring Data, and Java runtime are in a verified combination.
- [ ] Dependency tree has no unexpected SPI/driver version conflicts.
- [ ] `ConnectionFactory` initializes and metadata is recognized properly.
- [ ] Spring Data resolves the correct dialect.
- [ ] CRUD and parameter binding work on the target database.
- [ ] Nulls, collections, decimals, temporals, UUID, JSON/arrays, and binaries are tested as needed.
- [ ] Generated IDs, defaults, triggers, and computed columns are tested.
- [ ] Transaction commit/rollback and isolation meet business requirements.
- [ ] Cancellation, streaming, and LOBs are tested if required by the workload.
- [ ] Pooling, timeouts, TLS, authentication, and reconnect meet operational requirements.
- [ ] Exception mapping preserves sufficient details for handling and diagnostics.
- [ ] Engine-specific SQL and portability limits are documented.
- [ ] Integration tests run against the exact database/driver versions in CI.
- [ ] Each feature is marked Documented, Tested, Limited, Unsupported, or Unknown.

## 19. Technical Conclusion

Evaluating R2DBC support requires treating the database, driver, SPI, Spring Data dialect, and operational configuration as a single integrated stack. A driver can provide reactive connectivity while still having limitations around data types, generated values, cancellation, transactions, or database-specific features. Conversely, an available server feature is not necessarily mapped conveniently by the driver or Spring Data.

Start from the workload and the features your application requires, build a version matrix, review driver documentation, and then verify with integration tests on the real database. Document supported capabilities, limitations, and unverified areas. This evidence-based evaluation helps select the right driver, avoid confusing server capabilities with framework abstractions, and reduce risk when upgrading or switching database engines.
