# Choosing the Oracle Dialect by Hibernate and Database Version

## 1. What Is an Oracle Dialect in Hibernate?

Hibernate is an ORM responsible for translating Java/JPA operations into SQL and mapping SQL results back to entities. The same operation—such as pagination, key generation, row locking, or DDL generation—may require different SQL between Oracle and other RDBMSs. Even within Oracle, syntax and capabilities change across database versions.

A **Dialect** is the Hibernate component that describes the SQL and specific characteristics of a database engine. The Oracle dialect tells Hibernate about:

- Pagination and row-limiting syntax.
- How to use sequences, identity columns, and key generation.
- JDBC/SQL data types and Java type mappings.
- `FOR UPDATE` syntax, locking, and database-specific SQL expressions.
- SQL functions, DDL, large data types, and Oracle-supported capabilities.
- Version-dependent limits/features such as identifier length or newer syntax.

Choosing the right dialect lets Hibernate generate SQL suited to the database. Choosing a dialect that is too old can prevent Hibernate from using newer Oracle capabilities or cause it to emit legacy syntax. Choosing a dialect newer than the database's capabilities can trigger SQL syntax errors or use features the server does not yet support.

A dialect is not a JDBC driver. The JDBC driver opens connections, sends SQL, and marshals data between Java and Oracle. The dialect governs how Hibernate generates SQL and interprets database capabilities. The two must be compatible, but they solve distinct tasks.

## 2. Relationship Between Hibernate Version, Oracle Version, and JDBC Driver

When configuring Spring Boot/JPA, consider at least three versions simultaneously:

1. **Hibernate ORM version:** determines which dialect classes exist and which dialect APIs are supported.
2. **Oracle Database version:** determines which syntax the server understands and which features it supports.
3. **Oracle JDBC driver version:** determines JDK compatibility, reported database metadata, and supported JDBC/XA protocols.

Other factors include the Spring Boot version, Java version, Jakarta Persistence version, and Oracle's `COMPATIBLE` parameter.

```text
Spring Boot dependency management
            |
            v
      Hibernate ORM version
            |
            v
   Oracle Dialect implementation
            |
            +------ JDBC DatabaseMetaData
            |                  |
            |                  v
            |          Oracle DB product/version
            v
       Generated SQL
            |
            v
    Oracle JDBC driver
            |
            v
      Oracle Database
```

You cannot choose a dialect simply by looking at the Oracle Database name. First determine whether the application uses Hibernate 5, 6, or 7, because class names and how Hibernate detects database versions have changed across major releases.

## 3. Choosing a Dialect by Hibernate Major Version

### 3.1. Hibernate ORM 5.x

In Hibernate 5.x, Oracle dialects follow database generations. In modern Hibernate 5.x releases such as 5.4/5.6, `Oracle12cDialect` is typically used for Oracle 12c and later, including 18c and 19c:

```properties
spring.jpa.database-platform=org.hibernate.dialect.Oracle12cDialect
```

Or configure the Hibernate property directly:

```properties
spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.Oracle12cDialect
```

`Oracle12cDialect` is a class in Hibernate 5.x's dialect API. There is no reason to invent a class name like `Oracle19cDialect` if your Hibernate version does not ship one. For Oracle 19c on Hibernate 5.6, the Oracle 12c dialect is typically the right choice because it already models capabilities of the Oracle 12c+ family.

For older databases, Hibernate 5 releases may still ship classes like `Oracle10gDialect` or corresponding legacy dialects. Pick them only when both the actual Oracle release and Hibernate version are within the support scope. Do not grab an older class merely because its name resembles the database version; inspect the dialect list in the exact Hibernate artifact.

### 3.2. Hibernate ORM 6.x

Hibernate 6 standardizes the dialect system and uses:

```text
org.hibernate.dialect.OracleDialect
```

In most setups, Hibernate 6 reads `DatabaseMetaData` from the JDBC connection to detect Oracle and its server version, then selects appropriate behavior automatically. Thus, manually setting `hibernate.dialect` is usually unnecessary.

If you must declare the dialect explicitly due to deployment constraints or restricted metadata access, use the class provided in the exact Hibernate 6 version you run:

```properties
spring.jpa.database-platform=org.hibernate.dialect.OracleDialect
```

Hibernate 5's version-specific Oracle dialects were removed, consolidated, or moved to legacy/deprecated status depending on the major/minor release. Do not copy an `Oracle12cDialect` configuration from a Hibernate 5 project into Hibernate 6 if that class no longer exists in the artifact.

### 3.3. Hibernate ORM 7.x

Hibernate 7 continues using the unified Oracle dialect:

```text
org.hibernate.dialect.OracleDialect
```

Prefer letting Hibernate auto-detect the database version from JDBC metadata unless there is a clear technical reason to configure the dialect explicitly or use a custom dialect. Support for a new Oracle feature also depends on the exact Hibernate minor release; just because the database has a feature does not mean your Hibernate version knows how to generate SQL for it.

### 3.4. Quick Reference Table

| Hibernate ORM | Common Oracle dialect | Notes |
|---|---|---|
| Modern Hibernate 5.x | `org.hibernate.dialect.Oracle12cDialect` for Oracle 12c/18c/19c | Check classes in the exact 5.x release; older DBs may require another legacy dialect |
| Hibernate 6.x | `org.hibernate.dialect.OracleDialect` | Old versioned dialects were consolidated/removed; prefer auto-detection |
| Hibernate 7.x | `org.hibernate.dialect.OracleDialect` | Check feature support per minor release and JDBC driver |

This table is a major-version guide, not a replacement for the official compatibility matrices of Hibernate, Spring Boot, Oracle JDBC, and Oracle Database. If a project uses Hibernate 5.0/5.1 or a very old database, consult documentation for that exact minor release rather than applying Hibernate 5.6 settings.

## 4. How Does Spring Boot Select the Hibernate Version?

### 4.1. Spring Boot Dependency Management

Spring Boot manages the Hibernate version via dependency management/BOM. As a result, the Spring Boot major/minor version usually dictates the default Hibernate version pulled into the application.

General mapping:

| Spring Boot generation | Typical bundled Hibernate generation | JPA namespace |
|---|---|---|
| Spring Boot 2.x | Hibernate 5.x | `javax.persistence` |
| Spring Boot 3.x | Hibernate 6.x | `jakarta.persistence` |
| Spring Boot 4.x | Hibernate 7.x per managed dependency line | `jakarta.persistence` |

Do not infer the exact Hibernate minor version from the Spring Boot major version alone. Spring Boot minor/patch releases can upgrade Hibernate within the same major line. Inspect the project's resolved dependencies before setting a dialect.

### 4.2. Checking Hibernate Version with Maven

```bash
mvn dependency:tree -Dincludes=org.hibernate.orm:hibernate-core,org.hibernate:hibernate-core
```

In Hibernate 5, the artifact typically uses coordinates `org.hibernate:hibernate-core`; starting in Hibernate 6, the primary coordinates are `org.hibernate.orm:hibernate-core`. The command above includes both so neither is missed.

### 4.3. Checking Hibernate Version with Gradle

```bash
./gradlew dependencyInsight \
  --dependency hibernate-core \
  --configuration runtimeClasspath
```

On Windows, use `gradlew.bat` instead of `./gradlew`. `dependencyInsight` shows the resolved version and which dependency brought it into the graph.

### 4.4. Do Not Arbitrarily Override Hibernate

If the Spring Boot BOM already selects a compatible Hibernate version, do not override `hibernate-core` alone just to use a dialect class or new feature. Overriding can introduce version skew across Hibernate core, community dialects, integration modules, JPA providers, and Spring libraries.

If upgrading Hibernate outside the BOM is genuinely necessary, check migration guides, Jakarta Persistence compatibility, Java baseline, Spring integration, and drivers before deploying.

## 5. Configuring the Dialect in Spring Boot

### 5.1. Recommended Setup: Auto-Detection

With Hibernate 6/7 and an Oracle JDBC driver providing proper metadata, configuration usually needs only the datasource:

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-host.example.com:1521/app_service
    username: app_user
    password: ${DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver

  jpa:
    hibernate:
      ddl-auto: validate
```

There is no need to set `spring.jpa.database-platform` if Hibernate already detects Oracle and the database version. This reduces the risk of leaving an invalid dialect class configured after upgrading Spring Boot/Hibernate.

In the example, the password comes from an environment variable/secret store; never commit credentials to source control. `ddl-auto: validate` only asks Hibernate to verify mappings against the schema, without creating or altering objects.

### 5.2. Explicit Dialect Configuration for Hibernate 5.x

Example Spring Boot 2.x application using Hibernate 5.6 and Oracle 19c:

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-host.example.com:1521/app_service
    username: app_user
    password: ${DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver

  jpa:
    database-platform: org.hibernate.dialect.Oracle12cDialect
    hibernate:
      ddl-auto: validate
```

Verify that `Oracle12cDialect` exists in the project's actual Hibernate 5.x version. When upgrading to Hibernate 6, remove or update the setting per the new dialect API.

### 5.3. Explicit Dialect Configuration for Hibernate 6/7

If explicit configuration is needed:

```yaml
spring:
  jpa:
    database-platform: org.hibernate.dialect.OracleDialect
```

In most cases, auto-detection is sufficient. Configure it explicitly only when strict control is desired or metadata issues occur. If using a custom dialect, the class must be compatible with the Hibernate major version and present on the classpath.

### 5.4. Configure in Only One Place

Two common ways to configure it:

```properties
spring.jpa.database-platform=org.hibernate.dialect.OracleDialect
```

and:

```properties
spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.OracleDialect
```

`spring.jpa.database-platform` is the Spring Boot property for setting the database platform/dialect. `spring.jpa.properties.*` passes the corresponding property directly to Hibernate. Never declare both with conflicting values; duplicate settings obscure the effective value and cause confusion during upgrades.

## 6. How Does Hibernate Detect the Oracle Version?

### 6.1. JDBC DatabaseMetaData

When initializing SessionFactory/EntityManagerFactory, Hibernate can inspect metadata from a JDBC connection:

- Database product name, e.g., `Oracle`.
- Database product version, e.g., the running Oracle release.
- JDBC driver name and version.
- JDBC capabilities reported by the driver.

An application can inspect metadata independently:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductName());
    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());
}
```

If metadata reports inaccurate information or is inaccessible, Hibernate may fail to detect the database version and dialect capabilities as expected. Check the driver, URL, connection privileges, and startup logs before hardcoding a dialect.

### 6.2. Checking Version Directly in Oracle

```sql
SELECT banner
FROM v$version
ORDER BY banner;
```

Or if the account has privileges to query the appropriate view:

```sql
SELECT version
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
```

Version views may require data dictionary privileges. Runtime application accounts should not be granted administrative privileges solely to read versions; DBAs can provide version details from the target environment.

### 6.3. Database Version Differs from COMPATIBLE

The Oracle database release and the `COMPATIBLE` parameter are two separate pieces of information:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
```

A database may run Oracle 19c binaries while keeping `COMPATIBLE` at an older level during an upgrade window. Dialect detection usually relies on JDBC metadata/database version; `COMPATIBLE` controls which on-disk formats and database capabilities are permitted. When relying on new features such as new data types or DDL syntax, check both the release and `COMPATIBLE` along with actual configuration.

Do not force an old dialect just because `COMPATIBLE` is lower than the binary release, nor assume new features work just because `V$VERSION` shows a newer release.

## 7. Oracle Capabilities Affected by the Dialect

### 7.1. Pagination

Different Oracle releases use different pagination syntax. Oracle 12c and later support the row limiting clause:

```sql
SELECT order_id, order_date
FROM orders
ORDER BY order_date, order_id
OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY;
```

Older Oracle releases typically required `ROWNUM`-based queries or nested subqueries. The Hibernate dialect chooses the appropriate pagination strategy. If the dialect assumes the database is too old, Hibernate may emit legacy SQL even when the database supports newer syntax; if the dialect assumes the database is newer than reality, the SQL may fail.

### 7.2. Sequences and Identity Columns

Oracle has long supported sequences; identity columns were added in Oracle 12c. For an entity using a sequence:

```java
@Entity
@Table(name = "ORDERS")
public class OrderEntity {
    @Id
    @SequenceGenerator(
        name = "order_seq_gen",
        sequenceName = "ORDER_SEQ",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_seq_gen"
    )
    private Long id;
}
```

Hibernate can use sequences with allocation/optimizer mechanisms to reduce sequence round trips. The `allocationSize` setting must match the actual sequence increment and the Hibernate optimizer in use. When the database schema is managed by Flyway/Liquibase, keep sequence increments synchronized with entity mappings.

For identity columns:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Use this only when the database release/schema supports identity columns and the Hibernate dialect/driver supports retrieving generated keys. With Oracle, sequence-based generation remains a popular and explicitly controllable choice.

### 7.3. Identifier Length and Naming

Oracle's identifier length limit depends on release and `COMPATIBLE` level. Older databases had shorter limits than Oracle 12.2 and later. Hibernate can use dialect limits when generating table, column, index, or constraint names.

Names generated by a naming strategy that exceed limits can fail during schema creation or migration. Do not shorten names by tweaking the dialect alone; check actual Oracle limits and your project's naming strategy.

### 7.4. Data Types and SQL Expressions

The dialect participates in choosing SQL types for Java/JDBC types such as:

- `String`, `BigDecimal`, `Long`, `Boolean`.
- `LocalDate`, `LocalDateTime`, `OffsetDateTime`.
- Binary data, `BLOB`, `CLOB`, `NCLOB`.
- JSON or specialized data types where supported by Hibernate version and Oracle release.

Not every Java type maps to a single Oracle type. For example, `BigDecimal` may map to `NUMBER`; long strings may need `CLOB`; time-zoned timestamps have distinct semantics. Verify actual schemas, mapping annotations, and the JDBC types selected by Hibernate.

### 7.5. Locking and Database-Specific SQL

JPA operations such as `LockModeType.PESSIMISTIC_WRITE` can generate `SELECT ... FOR UPDATE` with appropriate syntax/options. Oracle has specific rules for `NOWAIT`, `WAIT`, `SKIP LOCKED`, and locking across joins/views. The dialect helps Hibernate generate valid SQL, while the application must still design proper transaction boundaries and timeouts.

## 8. Choosing a Dialect When Upgrading Spring Boot/Hibernate

### 8.1. From Spring Boot 2/Hibernate 5 to Spring Boot 3/Hibernate 6

This is a major transition because Hibernate 6 moves from `javax.persistence` to `jakarta.persistence` and overhauls the dialect system.

Steps required:

1. Check the actual Hibernate version after bumping the BOM.
2. Search for all `Oracle12cDialect`, `Oracle10gDialect`, or legacy dialect settings in properties/YAML/XML.
3. For Hibernate 6, use `OracleDialect` or remove the setting for auto-detection.
4. Migrate JPA imports from `javax.persistence.*` to `jakarta.persistence.*` as required by Spring Boot 3.
5. Audit custom dialects, custom types, naming strategies, and Hibernate extensions, as Hibernate 6 APIs changed.
6. Run tests covering SQL generation, pagination, sequences, identity columns, locking, and schema validation.

Do not merely rename the dialect and consider the upgrade finished. Other Hibernate 6 changes can affect SQL, type mappings, and query behavior.

### 8.2. From Hibernate 6 to Hibernate 7

Follow the same principle: use the unified Oracle dialect provided by Hibernate 7 and prefer metadata auto-detection. Read the migration guide for the exact minor release, and audit custom dialects and extensions. Never carry a custom dialect compiled against Hibernate 5/6 into Hibernate 7 without rebuilding and retesting.

### 8.3. Do Not Pick a Dialect Mechanically from the Spring Boot Version

Spring Boot only manages dependencies. If a project overrides Hibernate or uses custom starters, the effective version may differ from the default. Inspect the dependency tree/runtime classpath and Hibernate bootstrap logs before configuring.

## 9. Custom Oracle Dialects

### 9.1. When Is a Custom Dialect Needed?

Only create a custom dialect when there is a genuine need, such as:

- An application-specific data type or SQL function not yet supported by the standard dialect.
- Registering additional functions or types using your Hibernate version's API.
- Handling a deployment discrepancy that cannot be solved through standard mapping/configuration.

Never create a custom dialect just to tweak a single SQL query when JPQL, native queries, or standard function registration would suffice.

### 9.2. Custom Dialect Skeleton for Hibernate 6/7

Conceptual example:

```java
package com.example.persistence;

import org.hibernate.dialect.OracleDialect;

public class ApplicationOracleDialect extends OracleDialect {
    public ApplicationOracleDialect() {
        super();
        // Register application-specific behavior using the API
        // supported by the exact Hibernate major/minor version.
    }
}
```

Registration:

```properties
spring.jpa.database-platform=com.example.persistence.ApplicationOracleDialect
```

This is an illustrative skeleton only; function/type registration APIs change across Hibernate major versions. Do not copy method overrides from Hibernate 5 into Hibernate 6/7 because class and method signatures may have changed.

### 9.3. Avoid Overriding Standard Behavior Unnecessarily

When a custom dialect overrides pagination, sequences, type mappings, or locking, it can inadvertently disable improvements Hibernate provides for newer Oracle releases. Override only what is necessary, write integration tests against real Oracle or a compatible environment, and document why the custom behavior exists.

## 10. JDBC Driver and Compatibility

### 10.1. Choosing ojdbc by Java Runtime

Oracle distributes multiple JDBC driver artifacts. Common examples:

| Artifact | Target Java environment | Notes |
|---|---|---|
| `ojdbc8` | Java 8 and later per the corresponding driver matrix | Use when runtime needs a Java 8-compatible driver |
| `ojdbc11` | Java 11 and later per the corresponding driver matrix | Commonly used for apps running on Java 11+ |

Do not pick a driver based solely on the Oracle Database version. Check the Oracle JDBC download/support matrix to select a driver compatible with your JDK, Oracle Database release, application server, and required features. Newer drivers can connect to older databases within Oracle's support matrix; there is no rule that the driver version number must match the database release number.

### 10.2. Illustrative Maven Dependency

```xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>${oracle.jdbc.version}</version>
    <scope>runtime</scope>
</dependency>
```

Set the version according to your organization's support matrix and dependency management. Do not leave undefined version placeholders in a project; this example illustrates dependency structure.

### 10.3. Illustrative Gradle Dependency

```kotlin
runtimeOnly("com.oracle.database.jdbc:ojdbc11:$oracleJdbcVersion")
```

When using Spring Boot dependency management, verify the BOM and any intentional overrides. Avoid putting multiple `ojdbc` versions on the runtime classpath because class loading may pick the wrong driver.

### 10.4. Driver Version and Dialect Version Do Not Need to Match

For example, Oracle 19c can be accessed using `ojdbc11` suited for JDK 17 and Hibernate 6. There is no requirement for the dialect to be named `Oracle19cDialect` or for the driver version to be `19`.

Hibernate identifies the database via JDBC metadata and uses the dialect implementation to generate SQL. The driver handles communication. Select each component according to its own compatibility matrix.

## 11. Verifying Which Dialect Is in Use

### 11.1. Inspecting Bootstrap Logs

When Hibernate starts, enable appropriate logging to observe dialect and database metadata details. Logger names and messages vary by Hibernate version; look for:

- Database product/version reported by JDBC metadata.
- Resolved Hibernate dialect class.
- JDBC driver name/version.
- Warnings about deprecated, nonexistent, or unsupported dialect classes for the database version.

Do not enable TRACE-level bind parameter logging in production without data sanitization controls; logs can record parameter values containing PII or secrets.

### 11.2. Inspecting Generated SQL

In development/test environments:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
```

In Hibernate 6, the bind parameter logger is typically `org.hibernate.orm.jdbc.bind`; Hibernate 5 uses different loggers, such as `org.hibernate.type.descriptor.sql.BasicBinder`. Enable only when investigating and avoid logging sensitive data.

Check critical SQL statements:

- Does pagination use appropriate Oracle syntax?
- Are sequences/identity columns invoked correctly?
- Do DDL and identifiers stay within Oracle limits?
- Are `TIMESTAMP`, `NUMBER`, `CLOB`/`BLOB` mapped correctly?
- Do `FOR UPDATE`, generated keys, and batch inserts behave as expected?

### 11.3. Checking Schema with validate

When schemas are managed by Flyway/Liquibase, configure:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
```

Hibernate validates mappings against the existing schema within its capabilities; it does not replace migration testing or verify all business constraints. Never run `ddl-auto: create` or `update` in production just to test a dialect.

## 12. Common Errors from Choosing the Wrong Dialect

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `ClassNotFoundException`/cannot resolve dialect | Configured class belongs to another Hibernate major version or is absent from artifact | Check Hibernate version and dialect classes inside runtime JARs |
| SQL syntax error near `FETCH FIRST`/`OFFSET` | Dialect generates syntax incompatible with release or `COMPATIBLE` | Verify Oracle version, metadata, and dialect resolution |
| Hibernate uses legacy pagination | Dialect/metadata sees DB as too old or legacy dialect configured | Check metadata logs and actual dialect class |
| Identity/generated key error | Database/dialect/driver disagree on identity support | Check Oracle release, mapping, and driver generated-key support |
| Sequence allocation mismatch | `allocationSize` out of sync with sequence increment/optimizer | Check sequence DDL and generator mapping |
| Identifier too long | Naming strategy produces names exceeding database/`COMPATIBLE` limit | Check Oracle limits and naming strategy |
| Data type altered or fails validation | Hibernate dialect/type mapping differs by version or schema mismatch | Check JDBC types, column definitions, and migrations |
| Deprecated dialect class warning | Legacy class configured in newer Hibernate | Remove setting to auto-detect or switch to current dialect |
| Unable to read metadata | Issue with JDBC driver, connection, or metadata access privileges | Inspect driver, datasource, and bootstrap config |

Never fix errors by randomly swapping dialects. Read the SQL exception, Hibernate logs, database version, and generated SQL to find the exact mismatch.

## 13. Process for Selecting an Oracle Dialect for New Projects or Upgrades

1. Identify the actual Oracle Database release via `V$VERSION` or DBA-provided environment details.
2. Check `COMPATIBLE` and the features the application relies on.
3. Identify the Spring Boot version and Hibernate ORM version resolved on the runtime classpath.
4. Check the JDK version and pick a compatible Oracle JDBC driver from the support matrix.
5. For modern Hibernate 5.x and Oracle 12c/18c/19c, verify `Oracle12cDialect` exists in the artifact and use it if configuring manually.
6. For Hibernate 6/7, prefer auto-detection; if explicit configuration is needed, use `org.hibernate.dialect.OracleDialect`.
7. Never declare two conflicting dialect properties; never invent `Oracle19cDialect` if Hibernate does not provide it.
8. Run integration tests against the target Oracle release: pagination, sequences, identity columns, DDL, type mapping, locking, batching, and generated keys.
9. Use `ddl-auto: validate` and a migration tool to control schema; never rely on schema auto-update in production.
10. Inspect dialect/metadata logs, watch for warnings, and record the verified stack of Boot, Hibernate, JDK, ojdbc, Oracle release/RU, and `COMPATIBLE`.

## 14. Key Principles to Remember

- A dialect describes how Hibernate generates SQL for a database; the JDBC driver handles JDBC communication.
- Choose the dialect by Hibernate major version first, then cross-check the Oracle Database release and driver capabilities.
- Modern Hibernate 5.x typically uses `Oracle12cDialect` for Oracle 12c and later, including 19c.
- Hibernate 6/7 use `OracleDialect`; prefer letting Hibernate auto-detect version from JDBC metadata.
- Do not assume `Oracle19cDialect` exists; verify classes in the actual artifact.
- Spring Boot BOM dictates the default Hibernate version; use the dependency tree to confirm rather than guessing.
- Oracle Database release and `COMPATIBLE` are distinct; check both when using new features.
- Choose `ojdbc` according to JDK, Oracle release, and the support matrix; driver version does not need to match the dialect name.
- After changing a dialect or upgrading Hibernate, verify SQL pagination, sequences/identity, type mappings, locking, and DDL against real Oracle.
- Create a custom dialect only when needed; custom APIs must target the exact Hibernate major/minor version.

## References

- [Hibernate ORM User Guide — Dialects](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#database-dialect)
- [Hibernate ORM 5.6 User Guide](https://docs.jboss.org/hibernate/orm/5.6/userguide/html_single/Hibernate_User_Guide.html)
- [Hibernate ORM 6 Migration Guide](https://docs.hibernate.org/orm/6.0/migration-guide/)
- [Hibernate ORM 7 User Guide](https://docs.hibernate.org/orm/7.0/userguide/html_single/Hibernate_User_Guide.html)
- [Spring Boot Reference Documentation — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Oracle JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/)
- [Oracle Database 19c SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/)
