# Setting Up jOOQ and Boot-Configured `DSLContext`

## 1. Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, a key approach to database integration is combining **JDBC and jOOQ** for controlled SQL execution. The module also covers HTTP clients, caches, message brokers, and Spring Integration adapters; consequently, database connectivity must align with environment configuration, transactions, data contracts, errors, duplicate handling, testing, and observability of real-world integration flows.

**jOOQ** (Java Object Oriented Querying) provides a DSL for constructing SQL in Java. When Java classes are generated from your database schema, the compiler can validate table names, column names, and many data types at compile time. **`DSLContext`** is the entry point for jOOQ queries such as **`select`**, **`insertInto`**, **`update`**, and **`deleteFrom`**.

**Spring Boot can automatically create a `DSLContext` bean** bound to the application's configured **`DataSource`**. In a standard single-database setup, the application usually only needs to declare the dependencies, configure JDBC properties, and inject `DSLContext`. You do not need to open JDBC connections manually or instantiate `DSLContext` inside every repository.

After this lesson, learners will be able to:

1. Configure jOOQ dependencies, the JDBC driver, and the datasource in Spring Boot.
2. Explain which beans Boot can auto-configure and the conditions required for auto-configuration to activate.
3. Distinguish **runtime `DSLContext` configuration** from **build-time code generation**.
4. Use Spring-managed `DSLContext` inside a repository with type-safe queries.
5. Integrate jOOQ queries with transactions, error handling, tests, and connection pool limits.
6. Know when to use **`DefaultConfigurationCustomizer`** vs. manually configuring `DSLContext`.

## 2. Role of Each Component

Architecture for an inventory management application:

~~~mermaid
flowchart TD
    A["application.yml / environment variables"] --> B["Spring Boot DataSource auto-configuration"]
    C["JDBC driver + connection pool"] --> B
    B --> D["DataSource"]
    D --> E["jOOQ auto-configuration"]
    F["spring.jooq.sql-dialect"] --> E
    G["TransactionManager if present"] --> E
    H["DefaultConfigurationCustomizer if present"] --> E
    E --> I["org.jooq.Configuration"]
    I --> J["DSLContext bean"]
    J --> K["InventoryRepository"]
    K --> L["Application service"]
    M["Database schema + jOOQ code generator"] --> N["Java table / field classes"]
    N --> K
~~~

| Component | Responsibility | When Is It Created? |
| --- | --- | --- |
| **`DataSource`** | Supplies JDBC connections, typically via a pool like HikariCP | Runtime, by Boot or application configuration |
| **`SQLDialect`** | Tells jOOQ which SQL syntax variant to render | Runtime, inferred by Boot from the datasource or set explicitly |
| **`org.jooq.Configuration`** | Bundles `ConnectionProvider`, dialect, `Settings`, listeners, and other providers | Runtime, created by Boot when applicable |
| **`DSLContext`** | API for executing DSL queries based on `Configuration` | Runtime, exposed by Boot as a Spring bean |
| **Generated tables/records** | Java types modeling schema, columns, and records | Build time, produced by the jOOQ code generator |
| **Repository/application service** | Implements queries and business logic on `DSLContext` | Runtime, written by the application |

Three distinctions to keep clear:

- **Spring Boot does not run jOOQ code generation automatically just because the starter is present.** Code generation is a separate build step requiring access to an input schema.
- **`DSLContext` is not a fixed connection**; it holds configuration and borrows connections per query via its `ConnectionProvider`. Inject a shared `DSLContext` into repositories instead of instantiating it on every call.
- **jOOQ over JDBC is blocking I/O.** Running it alongside reactive I/O requires appropriate thread scheduling; a JDBC `DSLContext` never turns into an R2DBC client.

## 3. Preparing Dependencies

### 3.1. Maven Example

For projects managed by **`spring-boot-starter-parent`** or the Spring Boot BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jooq</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**`spring-boot-starter-jooq`** supplies the dependencies needed to integrate jOOQ with JDBC in Spring Boot. The PostgreSQL driver must be on the runtime classpath so **`DataSource`** can connect to PostgreSQL. If using MySQL, MariaDB, or H2, swap in the corresponding driver.

For Gradle projects with Spring Boot dependency management, the equivalent declaration is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jooq'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

These snippets assume the Spring Boot plugin and dependency management are configured. Never arbitrarily mix a starter from one Boot version with an incompatible jOOQ runtime or codegen version. **Always check the Java, Spring Boot, and jOOQ compatibility matrix for your project**; auto-configuration package names also change across Spring Boot generations.

### 3.2. An Illustrative Schema

Suppose the PostgreSQL database has an inventory table:

~~~sql
CREATE TABLE inventory (
    sku           varchar(64) PRIMARY KEY,
    available_qty integer NOT NULL CHECK (available_qty >= 0),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
~~~

This is illustrative DDL only. In production projects, manage DDL through migrations such as Flyway or Liquibase with clear per-environment ordering. jOOQ is for **querying**; adding the starter does not replace migrations.

## 4. Configuring `DataSource` and Dialect

Example **`application.yml`** for a local environment:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      connection-timeout: 2000
  jooq:
    sql-dialect: POSTGRES
~~~

Meaning:

- **`spring.datasource.url / username / password`**: JDBC connection properties. The password comes from the **`DB_PASSWORD`** environment variable; never commit real passwords to source control.
- **`spring.datasource.hikari.maximum-pool-size`**: maximum connections in this example's HikariCP pool; illustrative only, not a universal recommendation for every service.
- **`spring.datasource.hikari.connection-timeout`**: wait limit in milliseconds to borrow a connection from the pool; not the timeout for an executing SQL statement.
- **`spring.jooq.sql-dialect`**: instructs jOOQ to render PostgreSQL syntax.

When the datasource is recognized, Spring Boot can **auto-detect the SQL dialect**; when unrecognized, Boot falls back to **`DEFAULT`**. When a deterministic dialect is critical, declaring it explicitly and verifying in tests gives tighter control. Keep in mind Boot only auto-configures dialects supported by the active jOOQ version and edition.

For deployments, separate per-environment configuration and inject credentials via a secrets manager, environment variables, or secure configuration mechanism. Do not grant DDL privileges to the runtime application database user if runtime does not need them.

## 5. How Does Spring Boot Create `DSLContext`?

When required dependencies are present, a **`DataSource`** is available, and the application has not provided overriding beans, Spring Boot's jOOQ auto-configuration typically provides:

1. A **`ConnectionProvider`** wired to the Spring-managed `DataSource`.
2. A **`TransactionProvider`** integrating Spring transactions when an appropriate **`PlatformTransactionManager`** exists.
3. Integration for translating SQL errors into Spring's data-access exception hierarchy.
4. **`org.jooq.Configuration`**, combining dialect, connection provider, settings, listeners, and customizers.
5. A **`DSLContext`** bean backed by that `Configuration`.

Bean creation uses **`@ConditionalOnMissingBean`**: if the application defines its own bean for the same role, Boot may back off from its auto-configuration. Therefore, avoid declaring **`new DefaultDSLContext(...)`** or **`DSL.using(...)`** beans merely to "enable jOOQ"—doing so can bypass Boot's connection wiring, transaction participation, and exception translation.

Basic usage:

~~~java
import org.jooq.DSLContext;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {

    private final DSLContext dsl;

    public InventoryRepository(DSLContext dsl) {
        this.dsl = dsl;
    }

    // Query methods using dsl are shown later.
}
~~~

Spring injects the pre-configured `DSLContext` bean. The repository neither holds a **`Connection`** nor calls **`close()`** on connections it does not own. When executing queries, jOOQ and the underlying infrastructure acquire and release connections automatically.

### Verifying the System Receives Boot's Bean

In application tests, you can assert `DSLContext` and its dialect:

~~~java
@SpringBootTest
class JooqWiringTest {

    @Autowired
    private DSLContext dsl;

    @Test
    void bootConfiguresDslContext() {
        assertNotNull(dsl);
        assertEquals(
                SQLDialect.POSTGRES,
                dsl.configuration().dialect()
        );
    }
}
~~~

JUnit and Spring Test imports are omitted. The test requires a properly configured test database; checking bean presence alone does not prove queries can connect and execute. If startup fails, inspect Spring Boot's **Condition Evaluation Report**, `DataSource` initialization errors, and credential sources rather than instantiating `DSLContext` manually as a workaround.

## 6. Code Generation: Configured Separately

jOOQ can construct dynamic SQL using **`DSL.table(...)`** and **`DSL.field(...)`**, yet its primary strength lies in **Java classes generated from the schema**. Generated classes capture table names, columns, and data types so the compiler catches mismatches whenever columns are renamed.

Recommended workflow:

~~~mermaid
flowchart LR
    A["SQL migrations"] --> B["Database schema for build/test"]
    B --> C["jOOQ code generator"]
    C --> D["Generated Java sources"]
    D --> E["Compile application"]
    E --> F["Runtime: Boot injects DSLContext"]
~~~

With Maven, configure **`org.jooq:jooq-codegen-maven`** in the **`generate-sources`** phase:

~~~xml
<plugin>
    <groupId>org.jooq</groupId>
    <artifactId>jooq-codegen-maven</artifactId>
    <executions>
        <execution>
            <phase>generate-sources</phase>
            <goals>
                <goal>generate</goal>
            </goals>
        </execution>
    </executions>
    <dependencies>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>${postgresql.version}</version>
        </dependency>
    </dependencies>
    <configuration>
        <jdbc>
            <driver>org.postgresql.Driver</driver>
            <url>${env.JOOQ_CODEGEN_URL}</url>
            <user>${env.JOOQ_CODEGEN_USER}</user>
            <password>${env.JOOQ_CODEGEN_PASSWORD}</password>
        </jdbc>
        <generator>
            <database>
                <name>org.jooq.meta.postgres.PostgresDatabase</name>
                <inputSchema>public</inputSchema>
            </database>
            <target>
                <packageName>com.example.shop.jooq</packageName>
                <directory>target/generated-sources/jooq</directory>
            </target>
        </generator>
    </configuration>
</plugin>
~~~

**Example assumptions:** the POM uses **`spring-boot-starter-parent`** to manage plugin and dependency versions, including **`postgresql.version`**; if your project imports only a BOM or uses another build layout, declare versions and plugin management explicitly. The **`JOOQ_CODEGEN_*`** environment variables must exist when Maven runs and point to a database with migrations already applied. Because codegen runs during builds, use metadata-read-only credentials where possible and never point it straight at production.

Key decisions to make explicitly:

- Generate sources in CI from a **migrated schema**, avoiding stale or out-of-sync schemas.
- Keep **jOOQ codegen** and **jOOQ runtime** versions aligned, especially across major/minor upgrades.
- Choose a target package and artifact policy—some teams commit generated code while others generate every build. Ensure builds remain reproducible.
- Treat migration column names and data types as the single source of truth. Schema edits require regenerating sources and re-running tests before release.
- In Gradle, use a jOOQ codegen plugin compatible with your jOOQ version; plugin configuration belongs to the build pipeline rather than runtime `DSLContext` wiring.

**Note:** the classes illustrated below assume jOOQ generated **`com.example.shop.jooq.tables.references.INVENTORY`** or the equivalent import for your generator version and configuration. Match the exact package and class layout produced by your build; many configurations expose tables via a **`Tables`** class.

## 7. Writing a Type-Safe Repository with Injected `DSLContext`

Assume codegen produced **`INVENTORY.SKU`**, **`INVENTORY.AVAILABLE_QTY`**, and **`INVENTORY.UPDATED_AT`**. The repository uses them directly:

~~~java
import java.util.Optional;
import org.jooq.DSLContext;
import org.springframework.stereotype.Repository;
import static com.example.shop.jooq.Tables.INVENTORY;

@Repository
public class InventoryRepository {

    private final DSLContext dsl;

    public InventoryRepository(DSLContext dsl) {
        this.dsl = dsl;
    }

    public Optional<Integer> availableQuantity(String sku) {
        Integer value = dsl
                .select(INVENTORY.AVAILABLE_QTY)
                .from(INVENTORY)
                .where(INVENTORY.SKU.eq(sku))
                .fetchOne(INVENTORY.AVAILABLE_QTY);

        return Optional.ofNullable(value);
    }

    public int decreaseIfEnough(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        return dsl.update(INVENTORY)
                .set(INVENTORY.AVAILABLE_QTY,
                        INVENTORY.AVAILABLE_QTY.minus(quantity))
                .set(INVENTORY.UPDATED_AT, DSL.currentOffsetDateTime())
                .where(INVENTORY.SKU.eq(sku))
                .and(INVENTORY.AVAILABLE_QTY.ge(quantity))
                .execute();
    }
}
~~~

In this snippet, import **`org.jooq.impl.DSL`** for the timestamp expression; **`currentOffsetDateTime()`** must match the column type, dialect, and generator mapping. Alternatively, let the database update timestamps via schema design or centralized SQL to avoid timestamp-mapping assumptions.

Important details:

- **`fetchOne(field)`** returns the value or **`null`** when no row matches; wrapping in **`Optional`** distinguishes missing SKUs cleanly.
- Checking **`available_qty >= quantity`** **inside the `UPDATE` itself** prevents inventory from going negative under write contention. Inspect the affected row count to confirm whether the update succeeded.
- jOOQ binds values via parameterized queries; never concatenate user-supplied SKUs into raw SQL strings.
- **`execute()`** returns the affected row count. A `0` result may mean either missing SKU or insufficient stock; if the domain must distinguish the two, add appropriate lookups/state modeling while accounting for race conditions.

In integration systems, repositories should return explicit data or outcome statuses so application services can decide whether to continue transactions, return business errors, or emit events.

## 8. Spring Transactions and jOOQ Sharing a `DataSource`

When **`DSLContext`** and **`PlatformTransactionManager`** are configured consistently on the same datasource, jOOQ queries join Spring-managed transactions. A service decrementing stock and writing a reservation record:

~~~java
@Service
public class ReservationService {

    private final DSLContext dsl;

    public ReservationService(DSLContext dsl) {
        this.dsl = dsl;
    }

    @Transactional
    public void reserve(UUID reservationId, String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        int changed = dsl.update(INVENTORY)
                .set(INVENTORY.AVAILABLE_QTY,
                        INVENTORY.AVAILABLE_QTY.minus(quantity))
                .where(INVENTORY.SKU.eq(sku))
                .and(INVENTORY.AVAILABLE_QTY.ge(quantity))
                .execute();

        if (changed != 1) {
            throw new IllegalStateException(
                    "SKU not found or insufficient stock");
        }

        dsl.insertInto(RESERVATION,
                        RESERVATION.ID,
                        RESERVATION.SKU,
                        RESERVATION.QUANTITY)
                .values(reservationId, sku, quantity)
                .execute();
    }
}
~~~

This assumes codegen produced **`RESERVATION`** (imports omitted). If the insert fails and a runtime exception exits the service, Spring **normally** rolls back the transaction, including the preceding `UPDATE`. For checked exceptions, understand default rollback rules or configure **`rollbackFor`** where appropriate.

Critical conditions:

1. **`@Transactional`** methods must be called through Spring's proxy/transaction interceptor; internal self-calls within the same class can bypass transaction advice.
2. **`DSLContext`** and the transaction manager must share the same datasource or compatible transaction infrastructure; a manually created `DSLContext` with its own connection may sit outside the transaction.
3. JDBC transactions **do not cover** HTTP calls to external systems or broker publishes. To prevent data/event drift, use a **transactional outbox**, deduplication, and idempotent consumers.
4. A unique constraint on **`reservation_id`** prevents duplicate records when callers retry; decide whether the application service returns the prior result or signals a conflict.
5. Keep transactions short; avoid holding database connections open while waiting on slow downstream HTTP calls.

Spring Boot provides **`SpringTransactionProvider`** for jOOQ when a compatible **`PlatformTransactionManager`** is present. Whenever replacing `ConnectionProvider` or the transaction provider with custom beans, verify real transaction participation and rollbacks via tests.

## 9. Customizing `DSLContext` While Preserving Auto-Configuration

When you only need to adjust **`Settings`**, keep Boot's `DSLContext` and register a **`DefaultConfigurationCustomizer`**:

~~~java
@Configuration
public class JooqSettingsConfiguration {

    @Bean
    DefaultConfigurationCustomizer jooqCustomizer() {
        return configuration -> {
            configuration.settings().setRenderSchema(false);
            configuration.settings().setExecuteLogging(false);
        };
    }
}
~~~

What these settings do:

- **`renderSchema(false)`**: omits schema qualifiers from rendered SQL; safe only when the connection's search path/default schema is strictly controlled. With multiple schemas or tenants, dropping qualifiers can hit the wrong table.
- **`executeLogging(false)`**: disables jOOQ's built-in query logger; does not disable driver, monitoring, or proxy SQL logs. When enabling SQL logs for troubleshooting, guard against sensitive data and restrict by environment.

Import note: in Spring Boot 3.x, the customizer lives in **`org.springframework.boot.autoconfigure.jooq.DefaultConfigurationCustomizer`**; in Spring Boot 4.x, jOOQ auto-configuration packages were reorganized, e.g., **`org.springframework.boot.jooq.autoconfigure.DefaultConfigurationCustomizer`**. Always import the type matching your actual Boot version rather than copying across major releases blindly.

Beyond `Settings`, advanced customization covers **`ExecuteListenerProvider`**, connection providers, transaction providers, or custom bindings. When customizing these, verify listener ordering, exception translation, and Boot's auto-configured beans.

### When Should You Manually Construct `Configuration` or `DSLContext`?

Usually there is no need when an application uses **a single datasource** and one jOOQ configuration. Construct them manually only for concrete needs such as:

- Multiple datasources requiring distinct dialects, schemas, and transaction managers.
- Custom connection or tenant routing rules not safely expressible with default configuration.
- Specialized listener or transaction-provider wiring that must replace the standard setup.

With multiple datasources, explicitly bind each `DSLContext` to its datasource using **`@Qualifier`**, **`@Primary`**, and dedicated transaction managers. Never assume Boot auto-configures a complete `DSLContext` **for every datasource**. A miswired `DSLContext` can silently read or write the wrong database with valid SQL.

## 10. Data-Access Errors and Resource Limits

Runtime behavior is still governed by **the JDBC driver, `DataSource`/pool, and database**, even when queries are built with jOOQ:

| Issue | Symptoms | Approach |
| --- | --- | --- |
| Cannot connect to database | Driver, DNS, auth, or TLS failures | Verify URL, credentials, network, and security settings |
| Pool exhausted | Requests stall then fail acquiring connections | Measure active connections, checkout times, slow queries, and long transactions |
| Query / lock timeout | Queries wait on locks or run too long | Set JDBC/database timeouts; analyze execution plans and lock contention |
| Schema drift or stale codegen | "Table/column not found" or type mismatches | Synchronize migrations, code generation, and environments |
| Unique constraint violation | Duplicate reservation or request key inserts | Return appropriate business errors; enforce unique keys and idempotency |
| Wrong SQL dialect | Rendered SQL rejected by DB syntax | Check **`spring.jooq.sql-dialect`** against real engine |
| Missing transaction | Partial writes persist after an error | Verify annotations, transaction manager, connection provider, and proxy call path |

Spring Boot integrates exception translation for jOOQ SQL execution errors into Spring's **`DataAccessException`** hierarchy. Never depend blindly on one exact subclass across every driver; test real failure modes and distinguish business errors (such as insufficient stock) from infrastructure failures.

**HikariCP connection timeout is not statement timeout.** **`spring.datasource.hikari.connection-timeout`** limits how long callers wait to *borrow a connection*. To bound slow queries, configure JDBC/database statement timeouts and verify timeout handling, rollbacks, and retries.

**Never retry all writes blindly.** On a stock-decrement request, a timeout can strike after the DB commits yet before the caller receives the response. Re-issuing the request requires database or application-level deduplication.

## 11. Integration Testing and Observability

### Test Against the Real Database Engine

**`@JooqTest`** is Spring Boot's test slice for jOOQ; it configures `DSLContext` and data-access infrastructure. Custom repositories or services may still need **`@Import`** or broader test contexts. Annotation packages also differ across Boot releases. In **Spring Boot 4.x**, add the dedicated jOOQ test starter (e.g., **`org.springframework.boot:spring-boot-starter-jooq-test`**) to the test classpath, as the general test starter alone may omit this slice. In Spring Boot 3.x, verify the test auto-configuration packaged with your release.

For PostgreSQL-specific queries such as **`ON CONFLICT`**, `JSONB`, or locking, test against real PostgreSQL via Testcontainers or an isolated test database. H2 does not faithfully emulate PostgreSQL syntax, transaction isolation, or constraints.

Example repository slice test:

~~~java
@JooqTest
@Import(InventoryRepository.class)
class InventoryRepositoryTest {

    @Autowired
    InventoryRepository inventoryRepository;

    @Test
    void unknownSkuReturnsEmpty() {
        assertTrue(
                inventoryRepository.availableQuantity(
                        "SKU-DOES-NOT-EXIST").isEmpty()
        );
    }
}
~~~

Running this requires matching schema and test data in the test datasource. Tests against mocks verify DSL logic, whereas tests against a real datasource validate connectivity, dialect, migrations, and transactions.

Recommended test suite scenarios:

1. Application context creates `DSLContext` with the expected dialect.
2. `SELECT` queries cover existing SKUs, missing SKUs, and boundary values.
3. Two concurrent requests decrementing stock never produce negative stock or oversell beyond available quantity.
4. `INSERT` fails mid-transaction and rolls back the prior `UPDATE` cleanly.
5. Re-submitting the same **`reservationId`** is handled by unique constraints or idempotency as designed.
6. Column-renaming migrations fail codegen/compilation before deployment.
7. DB unavailability, pool timeouts, and lock waits are not disguised as "not found."

### Key Observability Signals

- **SQL execution latency** per operation/query class; watch p95/p99 and slow queries.
- **HikariCP active, idle, and pending connections**, plus pool acquisition timeouts.
- **Transaction duration**, rollbacks, and deadlock/lock timeouts.
- **Error rates** grouped by `DataAccessException` type or SQLState; keep high-cardinality values like SKUs out of metric tags.
- **Correlation IDs/traces** linking business requests to DB queries, outbox events, and downstream calls.

Exercise strict care with sensitive data before enabling **jOOQ execute logging**, bind-value logging, or SQL audits. Never log passwords, tokens, PII, or sensitive business payloads. Pair database statistics, query plans, and pool metrics to locate true bottlenecks.

## 12. Common Misconceptions

**"Adding `spring-boot-starter-jooq` automatically generates Java `Tables` classes."** False. Boot sets up runtime beans; code generation is configured separately in your build and reads a real schema.

**"Every repository must call `DSL.using(dataSource)` itself."** Usually unnecessary. Doing so duplicates setup and can bypass Boot's transaction integration and listeners.

**"`DSLContext` is a connection that should be opened and closed per request."** Incorrect. `DSLContext` is the configuration-backed DSL entry point; connections are borrowed and returned via `ConnectionProvider` per lifecycle rules.

**"Auto-detected `SQLDialect` is always right for every database."** Not guaranteed. Boot can fall back to `DEFAULT` or hit edition constraints; verify at runtime against the real database.

**"`@Transactional` alone suffices even when writing to both DB and message broker."** JDBC transactions protect only resources managed by the matching transaction manager; use an outbox or other integration pattern for cross-system consistency.

**"Using jOOQ makes I/O non-blocking."** jOOQ over JDBC is blocking. Design thread models, concurrency bounds, and connection pools accordingly.

**"Hikari `connection-timeout` caps SQL query duration."** It bounds waiting to borrow a connection; statement/database timeouts are separate settings.

## 13. Implementation Checklist

Before adopting jOOQ in an integration flow, verify:

1. Starter, JDBC driver, and jOOQ/codegen versions align with your Spring Boot and Java versions.
2. `DataSource` reads URL, username, and credentials from environment-appropriate configuration.
3. `DSLContext` is Spring-injected and `SQLDialect` matches the target database.
4. Migrations and generated sources track the exact same versioned schema.
5. Repositories use typed DSL fields/records, bind parameters, and handle empty results intentionally.
6. Multi-step writes share one transaction on the right datasource and rollbacks are tested.
7. Unique keys/idempotency protect operations that callers or consumers may retry.
8. Pool limits, statement timeouts, lock waits, retries, and DB capacity are measured rather than guessed.
9. Tests run against the real dialect for vendor-specific features; metrics and logs aid diagnosis without leaking data.

With this setup, **Spring Boot-configured `DSLContext`** serves as a unified SQL access layer. jOOQ's core value lies in type-safe SQL and expressive query composition, while integration reliability continues to rely on schema governance, transactions, connection pools, testing, and disciplined operations.

## References

- [Spring Boot Reference — SQL Databases / Using jOOQ](https://docs.spring.io/spring-boot/reference/data/sql.html): datasource, `DSLContext` auto-configuration, dialects, and customizers.
- [Spring Boot 3.5 Reference — SQL Databases / Using jOOQ](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): guide for the Spring Boot 3.x branch.
- [Spring Boot API — JooqAutoConfiguration (3.5)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jooq/JooqAutoConfiguration.html): `ConnectionProvider`, `TransactionProvider`, and `DSLContext` beans.
- [jOOQ Manual — Code Generation Configuration](https://www.jooq.org/doc/latest/manual/code-generation/codegen-configuration/): generator settings and schema metadata sources.
- [jOOQ Manual — Transaction Management](https://www.jooq.org/doc/current/manual/sql-execution/transaction-management/): transaction providers and transaction interaction.
