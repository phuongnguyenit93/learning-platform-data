# Testing Hibernate Extensions Across Target Versions and Databases

A Hibernate extension may pass unit tests yet fail on a different Hibernate version or a real database. The root cause is often differences in APIs/SPIs, how the provider generates SQL, JDBC data types, transaction semantics, dialects, migrations, or the extension failing to register in `SessionFactory`.

Testing an extension must verify three things together: the extension loads properly into Hibernate, its business behavior is correct, and it is compatible with the exact combination of Hibernate/Jakarta Persistence/JDK/JDBC driver/database supported by the application. H2 is useful for fast tests, yet cannot substitute for integration tests against the target database.

This lesson builds a testing strategy from unit tests to Testcontainers, establishes a compatibility matrix, demonstrates custom mapping on PostgreSQL, and details required checks for UserType, Integrator, event listeners, interceptors, Dialects, filters, generators, caches, and bytecode enhancement.

## 1. Identify Exactly What Needs Testing

Before writing tests, classify the extension under development. Each kind has distinct failure modes.

| Extension or Extension Point | What Must Be Verified |
|---|---|
| Jakarta Persistence AttributeConverter | Java ↔ JDBC conversion, nulls, precision/scale, querying, and round-trips |
| Hibernate UserType, JavaType, JdbcType, BasicType | JDBC bind/extract, dirty checking, equality/hash, SQL type, cache representation |
| Integrator, ServiceContributor, ServiceRegistry | Extension is discovered and registered cleanly in every SessionFactory |
| EventListenerRegistry, Hibernate event listeners | Events fire in the right phase, exact invocation count, transaction rollback, and listener order |
| Interceptor, StatementInspector | SQL is observed/modified accurately without recursion or unintended data mutations |
| Custom Dialect, SQL functions, type contributors | Generated SQL is valid on the actual dialect and database |
| Filters, multi-tenancy, soft delete | Filter predicates apply to the right queries without cross-tenant data leaks |
| Identifier generator | Generates valid keys under concurrent inserts, rollbacks, and multi-node deployments |
| Second-level cache, query cache | Cache hits/misses, invalidation, and cross-Session consistency |
| Bytecode enhancement | Lazy loading, dirty tracking, and association behavior when classes are genuinely enhanced |
| Envers, Search, Spatial, Vector, or other extensions | Modules, schemas, drivers, and database extensions are installed properly and reads/writes work |

Not every extension is a Hibernate SPI. `AttributeConverter` belongs to Jakarta Persistence and is more portable. `UserType`, `Integrator`, `StatementInspector`, and many service registry contracts are Hibernate-specific APIs. Identify the contract your extension relies on before selecting tests.

### 1.1. Distinguish API, SPI, and internal implementation

Just because a package compiles does not mean it is a long-term supported API.

- Prefer public contracts documented in Javadocs and the Integration Guide.
- Check stability annotations such as `@Incubating` or `@Internal` if present.
- Avoid depending on classes in `org.hibernate.internal` or undocumented implementation details.
- If an extension must use an SPI, pin compatible Hibernate versions and run compatibility tests when upgrading.
- Do not assume an extension compiled against Hibernate 6 will run unmodified on Hibernate 7.

Unit tests can verify the extension's isolated algorithms, yet only integration tests with real Hibernate confirm bootstrapping, registration, and invocation across the full lifecycle.

## 2. Build a Compatibility Matrix Before Writing Tests

A deployment stack involves more than a Hibernate version alone. At a minimum, record:

- Java runtime/JDK.
- Spring Boot and Spring Framework if using Spring.
- Spring Data JPA.
- Hibernate ORM.
- Jakarta Persistence API.
- JDBC driver.
- Database engine and version.
- Migration tool and version.
- Companion extension artifacts or modules shipped with Hibernate.
- Cache provider, search engine, or database extensions if applicable.

Example tracking table:

| Component | Production Version | Upgrade Candidate | Notes |
|---|---|---|---|
| JDK | 21 | 25 | Both compile and runtime |
| Spring Boot | Current deployed BOM version | Target BOM | Do not override Hibernate arbitrarily |
| Hibernate ORM | BOM-managed version | Version supported in new stack | Check API/SPI changes |
| Jakarta Persistence | Stack-managed version | Corresponding Hibernate version | Avoid mixing namespaces/APIs |
| JDBC driver | Current driver | Target driver | Check release notes |
| Database | Production engine/version | Target upgrade version | Match major/minor wherever possible |
| Extension | Currently released artifact | Build candidate | Check transitive dependencies |

Do not pick the newest version of each library and mix them arbitrarily. Use the compatibility matrix and Spring Boot/Hibernate dependency management to select a supported combination.

As of 09-11-2026, Hibernate's release page lists Hibernate ORM 7.4.15.Final as the latest stable release; the 7.4 line is compatible with Java 17, 21, 25, or 26 and Jakarta Persistence 3.2, and lists Spring Boot 4.1 in its matrix. Hibernate 6.6 remains under limited support and pairs with Spring Boot 3.4–3.5. The 7.1 line is end-of-life. This illustrates why you must check the support status of the entire stack before upgrading; a project running Spring Boot 3 should not swap `hibernate-core` alone to 7.4. [Hibernate ORM releases and compatibility matrix](https://hibernate.org/orm/releases/).

### 2.1. Reading the compatibility matrix properly

When checking a combination:

1. Confirm Hibernate supports your target JDK.
2. Confirm Hibernate implements the exact Jakarta Persistence version required by the framework.
3. Verify Spring Boot/Spring Data JPA manages and supports that Hibernate line.
4. Confirm extension modules share the same release train as `hibernate-core`.
5. Confirm the JDBC driver supports the target database version.
6. Confirm the database version falls within the dialect's supported range.
7. Store the matrix so it can be re-executed in CI.

When using the Spring Boot BOM, never declare a separate Hibernate version just to "test quickly" without updating related dependencies. Inspect the dependency tree to see which artifacts actually resolve.

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.hibernate,org.springframework.data,jakarta.persistence
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
~~~

Output must confirm the version actually running at runtime, not just the version written in build files.

### 2.2. Selecting points in the matrix

You do not need to run every permutation of JDK × Hibernate × database if cost is prohibitive. You can partition into:

- **Minimum supported:** the oldest combination the application commits to supporting.
- **Production exact:** exact engine, driver, and versions running in production.
- **Upgrade candidate:** the combination planned for the next upgrade.
- **Critical combinations:** combinations exercising specialized extension features, such as PostgreSQL JSONB or MySQL generated columns.
- **Nightly matrix:** remaining combinations to catch regressions early.

Never skip testing on the production database solely because H2 and another database passed.

## 3. What Does the Database Dialect Control?

A Dialect informs Hibernate of database characteristics and translates Hibernate expressions into appropriate SQL. The same mapping can produce different column types, functions, pagination, locking, or DDL on PostgreSQL, MySQL, Oracle, and SQL Server.

In Hibernate ORM 7.4, the dialect guide lists minimum supported database versions such as PostgreSQL 14, MySQL 8.0, MariaDB 10.6, Oracle 19, SQL Server 12, and H2 2.1.214. These are minimum dialect baselines in the documentation, not a guarantee that every application feature works on every database release at those versions. [Hibernate Dialects](https://docs.hibernate.org/stable/core/dialect/).

For third-party dialects, compatibility responsibility rests with the dialect maintainer; Hibernate does not run official CI for every external dialect. Consult that dialect's own documentation and test suite.

### 3.1. Why H2 cannot replace the target database

H2 is great for fast startup and convenient repository tests. However, it differs from production databases in:

- Data types such as JSON, ARRAY, UUID, enums, spatial, or vector types.
- Handling of precision, scale, time zones, and collations.
- DDL syntax, generated columns, partial indexes, and check constraints.
- Native queries, stored procedures, and SQL functions.
- Pagination, locking, isolation levels, and deadlocks.
- Sequences, identity columns, generated keys, and batch statements.
- Transactional DDL, triggers, and foreign key behavior.
- Query optimizers and execution plans.

H2's compatibility modes do not turn H2 into real PostgreSQL or MySQL. Use H2 for fast tests; use the real database engine for dialect-dependent features.

## 4. Layered Testing Strategy

Do not put every check into a single type of integration test. Split tests by cost and the class of bugs they catch.

### 4.1. Unit tests for pure logic

Use unit tests for parts that do not require Hibernate or a database:

- Data normalization rules inside a converter.
- Extension configuration validation.
- Pure Java helpers generating column names or expressions.
- Mapping from internal events to domain events.
- Tenant/filter decision rules.
- Error handling and fallbacks in extension code.

Unit tests must stay fast and avoid booting `SessionFactory` unnecessarily. They do not prove JDBC binding or dialect-generated SQL is correct.

### 4.2. Bootstrap tests for extension registration

Boot Hibernate or a Spring application context with the real extension and verify:

- The extension is discovered.
- No classloading or service-loading errors occur.
- Registration occurs exactly once per `SessionFactory`.
- Mapping metadata contains the expected types/contributors.
- Listeners or interceptors are actually invoked.
- Closing `SessionFactory` releases extension resources and leaves no lingering listeners.

If an extension registers via properties, service loaders, Integrator, or Spring customizers, tests must exercise the exact production registration path. Manually instantiating a listener in a unit test bypasses registry verification.

### 4.3. Integration tests against a real database

Use a database engine and version close to production to verify:

- Insert, update, select, delete, and round-trips.
- Actual SQL types and persisted values.
- Query predicates, sorting, pagination, and aggregates.
- Flush/clear/reload behavior.
- Transaction commit and rollback.
- Concurrency and locking.
- Indexes, constraints, triggers, and native functions.
- Schema migrations from prior versions.

This is the decisive test layer for database compatibility.

### 4.4. Migration tests

Run migrations on both an empty schema and a legacy schema populated with representative data:

1. Create the schema at the previous release version.
2. Seed sample data including nulls, precision boundaries, legacy formats, and relationships.
3. Run Flyway/Liquibase migrations up to the new version.
4. Start Hibernate against the migrated schema.
5. Use `ddl-auto=validate` to verify mapping/schema alignment.
6. Read back existing rows, check constraints/indexes, and insert new records.

Relying solely on `create-drop` in quick mapping tests does not prove production migrations are safe.

## 5. Using Testcontainers with the Target Database Engine

Testcontainers spins up disposable databases in containers, letting integration tests run against the real engine without requiring every developer to install database servers locally.

With JUnit 5, include the JUnit Jupiter module and the database module. Testcontainers supports launching database containers via annotations or specialized JDBC URLs. [Testcontainers JDBC support](https://java.testcontainers.org/modules/databases/jdbc/).

### 5.1. Dependencies

Gradle example; use the Testcontainers BOM to align module versions:

~~~groovy
dependencies {
    testImplementation platform(
        "org.testcontainers:testcontainers-bom:${testcontainersVersion}"
    )
    testImplementation "org.testcontainers:junit-jupiter"
    testImplementation "org.testcontainers:postgresql"
}
~~~

Set the BOM version selected by the project and verify JDK/CI compatibility. Do not let individual Testcontainers modules resolve conflicting versions.

### 5.2. Spring Boot test configuration

The example below pins the PostgreSQL image tag for reproducible results. In real projects, set the image tag to match your production major/minor or upgrade candidate.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class HibernateExtensionPostgresTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4")
                    .withDatabaseName("app")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private EntityManager entityManager;

    @Test
    void databaseIsTheTargetPostgresEngine() {
        Object product = entityManager
                .createNativeQuery("select version()")
                .getSingleResult();

        assertThat(product.toString()).contains("PostgreSQL");
    }
}
~~~

This example uses `@DataJpaTest` to initialize the JPA slice. `@AutoConfigureTestDatabase(replace = NONE)` prevents Spring from replacing the container datasource with an embedded database. `@DynamicPropertySource` supplies JDBC URL and credentials once the container starts.

The test above only proves connectivity to PostgreSQL. Subsequent tests must exercise the actual mapping or extension and assert business outcomes.

### 5.3. Installing required database extensions

If your extension requires PostgreSQL extensions such as PostGIS, pgvector, or custom functions, the database image must have the exact extension and version installed. Use a prebuilt image or an init script executed when the container initializes.

Do not check only that `CREATE EXTENSION` succeeds. Verify:

- The database extension is installed and enabled.
- The extension version matches production.
- Required data types, operators, and functions are available.
- The JDBC driver reads and writes the type properly.
- Hibernate mappings and queries actually use the feature.

## 6. Example Testing a Custom Mapping with AttributeConverter

The example uses `Money` as a value object and a converter to `NUMERIC`. This is a Jakarta Persistence extension point; testing on PostgreSQL catches precision/scale and JDBC representation differences.

Value object:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public record Money(BigDecimal amount) {

    public Money {
        Objects.requireNonNull(amount, "amount is required");
        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

Converter:

~~~java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.math.BigDecimal;

@Converter
public class MoneyConverter
        implements AttributeConverter<Money, BigDecimal> {

    @Override
    public BigDecimal convertToDatabaseColumn(Money money) {
        return money == null ? null : money.amount();
    }

    @Override
    public Money convertToEntityAttribute(BigDecimal value) {
        return value == null ? null : new Money(value);
    }
}
~~~

Entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "product_price")
public class ProductPrice {

    @Id
    private Long id;

    @Convert(converter = MoneyConverter.class)
    @Column(nullable = false, precision = 19, scale = 2)
    private Money price;

    protected ProductPrice() {
    }

    public ProductPrice(Long id, Money price) {
        this.id = id;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public Money getPrice() {
        return price;
    }
}
~~~

Add the following test method to `HibernateExtensionPostgresTest` from the previous section:

~~~java
@Test
void persistsAndReloadsMoneyValue() {
    entityManager.persist(
            new ProductPrice(
                    1L,
                    new Money(new BigDecimal("12.30"))
            )
    );

    entityManager.flush();
    entityManager.clear();

    ProductPrice loaded =
            entityManager.find(ProductPrice.class, 1L);

    assertThat(loaded.getPrice().amount())
            .isEqualByComparingTo("12.30");
}
~~~

`flush()` forces Hibernate to send the INSERT; `clear()` evicts the entity from the persistence context; `find()` forces the provider to read the value back over JDBC and invoke the converter in reverse. This test runs against the same PostgreSQL container configured above.

### 6.1. Additional edge cases to test for converters/types

A single happy-path round-trip is not enough. Add tests for:

- Null values if the mapping allows nulls.
- Negative values, zero, and values near precision limits.
- Scale larger than the column's scale.
- Values unrepresentable under the rounding policy.
- `equals`/`hashCode` of the value object.
- Comparison predicates, sorting, and aggregates if queries filter by the property.
- Dirty checking when replacing the value object.
- Second-level caching if the entity is cached.
- Native SQL or stored procedures if the extension interacts with them.

If the converter intentionally rejects invalid scale, tests must assert the converter's exception. If the database rejects precision overflow, tests must verify the database error propagates to the proper layer.

## 7. Testing Hibernate UserType and the Type System

`UserType` or type contributors reach deeper than AttributeConverter because they can control JDBC types, binding, extraction, equality, mutability, and cache representation.

Do not test only the two conversion methods. A type test suite should verify:

1. **Bootstrap:** does the mapping register the expected type?
2. **DDL:** does Hibernate generate or validate the right SQL column type?
3. **Bind:** which JDBC type code is used to bind Java values?
4. **Extract:** does reading from ResultSet reconstruct the right object?
5. **Null:** are JDBC nulls handled cleanly?
6. **Equality:** does the provider recognize two equivalent values?
7. **Dirty checking:** do real changes trigger UPDATE while unchanged values avoid redundant UPDATEs?
8. **Mutability:** are snapshots protected from unintended mutation when mutable objects change?
9. **Cache:** are serialization/deserialization and cache keys consistent?
10. **Query:** do parameter binding, predicates, ordering, and projections work?

Pay special attention to `equals`, `hashCode`, deep copy, and disassemble/assemble if caching is supported. A type can pass round-trip tests yet fail dirty checking, causing Hibernate to miss updates or issue unnecessary updates.

### 7.1. Verifying SQL types and persisted database values

For each target database, verify both column metadata and stored values. Never infer SQL types solely from Java classes.

You can use native queries or JDBC metadata to verify:

- Actual column type.
- Precision, scale, length, and nullability.
- Binary/text encoding.
- JSON/ARRAY/UUID representation.
- Timezone behavior.
- Default values and generated expressions.

Avoid asserting exact full DDL strings unless necessary. DDL formatting can change between Hibernate versions while schema semantics remain equivalent. Assert the schema attributes your application actually relies upon.

## 8. Testing Integrator, ServiceContributor, and EventListener

Extensions registered via Integrator, ServiceContributor, or registries must be tested at both bootstrap time and runtime.

### 8.1. Verifying registration

Tests must boot `SessionFactory` with production configuration and verify the extension is invoked. Avoid instantiating a listener manually in a test and calling its method directly, as that skips registry verification.

Questions to answer:

- Is the Integrator discovered via service loader or configuration?
- Is the service added to the right registry?
- Is the listener registered on the right event types?
- Does each `SessionFactory` get exactly one registration?
- When `SessionFactory` closes, are extension resources released?
- When the context restarts, are old context listeners gone?

### 8.2. Verifying event lifecycles

For pre/post insert, update, or delete listeners, persist real entities and execute real transactions:

- Which events fire?
- Does the callback run once or multiple times?
- Does it run before or after SQL/flush?
- Does a rollback leave any side effects outside the transaction?
- Do batch inserts/updates fire the expected number of callbacks?
- Do bulk HQL/Criteria DML statements bypass entity lifecycles?

Do not assume bulk updates/deletes fire the same lifecycle events as per-entity `EntityManager.persist()` or `remove()`. Tests must match the exact operations the application uses.

### 8.3. Verifying listener thread-safety

A single `SessionFactory` serves many threads. If a listener holds mutable state, concurrency tests must confirm:

- Neither `EntityManager` nor `Session` is shared across threads.
- Request-scoped data is never stored in singleton fields.
- Counters/registries use proper synchronization.
- Retried transactions do not emit duplicate events.
- Data never leaks across tenants or sessions.

## 9. Testing Interceptor and StatementInspector

Interceptors and StatementInspectors are commonly used to audit, observe, or adjust SQL.

Tests must confirm:

- SQL is observed for the intended operations.
- Parameters are not logged exposing sensitive data.
- Rewritten SQL remains valid on every target dialect.
- Predicates are never appended twice.
- Query caching and batching are not broken.
- Extensions issuing queries themselves do not trigger infinite recursion.
- Bind parameter order and count are not corrupted.
- Extensions never retain `Session`/`Connection` past the transaction.

When asserting SQL, prefer capturing statements in tests and checking essential properties such as presence of a tenant predicate or SELECT counts. Avoid brittle exact-string assertions on full SQL, because quoting, aliases, whitespace, and formatting vary across dialects and Hibernate versions.

If an extension rewrites SQL, execute the rewritten query against a real database. String unit tests alone never prove the database accepts the syntax.

## 10. Testing Custom Dialects and SQL Functions

Custom Dialects or function contributors must be tested on the databases they claim to support.

Steps:

1. Bootstrap Hibernate with the target dialect/registration.
2. Verify the function is recognized in HQL/Criteria.
3. Execute queries using the function against the real database.
4. Verify return values, null semantics, and return types.
5. Test with bound parameters, Unicode, and boundary values.
6. Inspect generated SQL on each target Hibernate version.
7. Confirm the lowest supported database version executes it successfully.

Do not assert only that the function is registered in metadata. A function can register cleanly yet translate to SQL syntax unsupported by that database version.

If a function uses PostgreSQL-specific syntax, passing on H2 proves nothing. For third-party dialects, run the dialect vendor's test suite and document support boundaries.

## 11. Testing Filters, Tenancy, and Soft Delete

Filters and tenancy extensions carry high data-leakage risk. Test both simple queries and less obvious access paths:

- `findById`, `findAll`, and derived queries.
- JPQL/HQL and Criteria queries.
- Lazy collection loading.
- EntityGraph and fetch joins.
- Native queries.
- Bulk updates/deletes.
- Cache hits from Session or second-level cache.
- Sessions opened before tenant context changes.
- Background jobs and async threads.

Never assume Hibernate filters apply to every native SQL query or bulk operation. Inspect actual query paths. When tenant isolation is a security boundary, consider database row-level security or additional constraints alongside ORM filters.

For soft delete, test:

- Do marked entities stay hidden from normal queries?
- Can administrative queries still reach them?
- Do unique constraints handle deleted records properly?
- Do associations and cascades behave as expected?
- Do native SQL paths accidentally bypass soft-delete predicates?
- Does restoration work and handle conflicts cleanly?

## 12. Testing Identifier Generators and Concurrency

Generators using sequences, identity, tables, or custom algorithms must be tested on the target database.

Key scenarios:

- Insert a single entity and confirm an ID is assigned.
- Insert multiple entities within one transaction.
- Insert concurrently from multiple transactions/threads.
- Roll back after ID allocation.
- Restart the application or create a new `SessionFactory`.
- Batch inserts if batching is enabled.
- Sequence allocation size vs. database sequence increment.
- Multiple application instances sharing one database.

Sequences can leave gaps after rollbacks; do not write tests assuming contiguous IDs unless the generator and database guarantee it.

For custom generators, verify zero duplicate IDs under concurrency. Use database unique constraints as the final safeguard; sequential unit tests cannot prove multi-node uniqueness.

## 13. Testing Caching and Bytecode Enhancement

### 13.1. Second-level cache and query cache

If an extension interacts with caching, test across multiple distinct Sessions:

1. Session A reads an entity and warms the cache.
2. Session B updates or deletes the entity.
3. Session C reads again and must observe the updated state.
4. Verify query cache invalidation when underlying tables change.
5. Verify rollbacks never leave uncommitted data in the cache.
6. Verify eviction, expiration, and serialization if required by the cache provider.

Test with the actual cache provider used in production. A mocked in-memory cache does not verify cluster invalidation or cross-node serialization.

### 13.2. Bytecode enhancement

If an extension depends on enhancement, test classes built with the exact production enhancement plugin and options. Tests running against unenhanced classes do not test enhancement-based dirty tracking or lazy loading.

Verify:

- The build actually executes the enhancement goal/task.
- Entities carry the corresponding enhancement markers/behavior.
- Lazy attributes load only when accessed.
- Dirty tracking detects field changes.
- Bidirectional associations do not synchronize incorrectly.
- Enhancement does not break proxies, serialization, or the test runtime.

Do not run enhancement twice with differing options. Consult migration guides when upgrading Hibernate, as plugin options and behavior can change.

## 14. Testing Migrations and Schema Compatibility

Extensions may require custom columns, indexes, functions, sequences, or database extensions. Schema tests must mirror real upgrade workflows.

### 14.1. Testing a fresh schema

- Run migrations from an empty database.
- Boot Hibernate against the created schema.
- Set `hibernate.hbm2ddl.auto=validate` or the equivalent Spring Boot property.
- Verify column types, nullability, precision, indexes, constraints, sequences, and functions.
- Run CRUD/queries exercising the extension.

### 14.2. Testing upgrades of an existing schema

Create a database using the previous release's migrations, seed representative data, and run the new migrations. Verify legacy data is not truncated, timezone-shifted, or stripped of precision.

If an extension changes storage representation, test bidirectional compatibility:

- Can new code read legacy data?
- Do migrations preserve semantics?
- Can application versions roll back safely during deployment?
- Are batched backfills needed?
- Is new code compatible with the schema during rolling deployments?

Never use Hibernate schema auto-update as a production migration tool instead of managed Flyway/Liquibase migrations.

## 15. Benchmarking Performance and Checking Query Regressions

A functionally correct extension can still introduce performance regressions:

- Issuing extra queries per entity.
- Disabling JDBC batching.
- Causing constant query cache misses.
- Introducing JOINs or casts that prevent index usage.
- Running reflection/serialization on every row.
- Holding `Session`/`Connection` open too long.

Useful measurements:

- SQL statement count per use case.
- Flush counts and actual batch sizes.
- Query counts when traversing associations.
- `SessionFactory` bootstrap time.
- Heap allocations when reading large batches.
- Execution plans and index usage.
- P95/P99 latency on critical query paths.

Use Hibernate Statistics or datasource instrumentation in tests. For performance-sensitive queries, run `EXPLAIN` on the target database with near-production cardinalities. Never extrapolate index or optimizer behavior from a few fixture rows.

## 16. Structuring CI for Version and Database Matrices

A practical pipeline can be structured as:

| Job | Scope | Cadence |
|---|---|---|
| Compile/unit | Compile extension on target JDK and Hibernate API; unit test pure logic | Every pull request |
| Bootstrap | Boot `SessionFactory`, confirm extension registration | Every pull request |
| Fast JPA | Mapping/repository tests on a lightweight database | Every pull request |
| Target DB | Testcontainers with production engine/version | Every pull request or main branch |
| Compatibility matrix | Supported Hibernate/JDK/database combinations | Nightly or release |
| Migration | Upgrade schema from the prior release | Every PR affecting schema |
| Performance smoke | Query count, batching, major regressions | Nightly/release |
| Upgrade candidate | Planned Hibernate/JDBC/database upgrades | Dedicated upgrade branch |

When an extension uses a Hibernate SPI, compile and test against every Hibernate line the application commits to supporting. Passing on the newest version alone does not prove compatibility with older supported lines.

If an extension supports only one Hibernate line, state that range clearly in dependency metadata, documentation, and release notes. Failing fast on unsupported versions is much easier to diagnose than obscure runtime errors.

## 17. Diagnosing Test Failures

| Symptom | Common Cause | Diagnostic Steps |
|---|---|---|
| Extension is never called | Not registered or registered in wrong registry | Check bootstrap logs, service loaders, and `SessionFactory` |
| Passes on H2 but fails on PostgreSQL | Dialect differences in SQL/types/functions | Run tests against the exact PostgreSQL image and driver |
| Compiles on new Hibernate yet fails at runtime | Incompatible SPI/API or dependency conflict | Inspect dependency tree and runtime classpath |
| Read value differs from written value | Converter/type binding or precision/scale mismatch | Inspect JDBC types, native values, and round-trips |
| Dirty checking misses updates | Broken equality, snapshots, or mutability plan | Test mutating mutable objects and flushing |
| SQL condition applied twice | Listener/interceptor registered multiple times | Check registration count and lifecycle |
| Another tenant reads foreign data | Filter skipped a query path or cache | Test native, bulk, collection loading, and caches |
| Tests pass yet migration fails | Used `create-drop` without upgrading prior schemas | Run migrations from a prior-release schema fixture |
| Duplicate IDs under load | Generator not thread-safe or wrong allocation | Test concurrent transactions and unique constraints |
| Queries slow down after adding extension | Added SQL, casts, JOINs, or disabled batching | Count statements and inspect execution plans |
| Cache serves stale data | Broken invalidation or serialization | Test across multiple Sessions and real nodes/providers |
| Upgrade breaks mappings | Changed APIs, defaults, or DDL | Read migration guides for each version |

When a test fails, capture complete reproduction context: Hibernate version, JDBC driver version, database image tag, JDK, dialect, schema migration version, generated SQL, and full exception chain. Never preserve only a stack trace without environment metadata.

## 18. Pre-Release Checklist for Extensions

- [ ] Identified whether the extension relies on Jakarta Persistence APIs or Hibernate-specific APIs/SPIs.
- [ ] Checked whether relied-upon APIs carry incubating/internal status.
- [ ] Maintained a compatibility matrix for JDK, Spring Boot, Spring Data JPA, Hibernate, JDBC driver, and database.
- [ ] Aligned Hibernate module versions with `hibernate-core`.
- [ ] Inspected the runtime dependency tree.
- [ ] Bootstrapped and registered the extension via the exact production mechanism.
- [ ] Covered pure logic, nulls, and boundary inputs with unit tests.
- [ ] Ran integration tests against the target database engine and version.
- [ ] Pinned Testcontainers image tags rather than using `latest`.
- [ ] Used H2 only for fast feedback, never as a substitute for real dialect tests.
- [ ] Tested type mappings for bind, extract, round-trip, equality, and dirty checking.
- [ ] Tested event listeners/interceptors for phases, call counts, and rollbacks.
- [ ] Executed custom Dialects/functions on a real database.
- [ ] Tested filters/tenancy across JPQL, native SQL, collections, bulk DML, and caches.
- [ ] Tested generators under concurrent transactions.
- [ ] Tested caching across multiple Sessions and production providers.
- [ ] Enabled bytecode enhancement in tests when production relies on it.
- [ ] Executed migrations from both an empty schema and the prior release's schema.
- [ ] Confirmed mapping compatibility with `ddl-auto=validate` on migrated schemas.
- [ ] Verified query counts, batching, and execution plans show no significant regressions.
- [ ] Configured CI jobs for minimum supported, production exact, and upgrade candidates.
- [ ] Documented supported Hibernate and database versions in release notes.

## 19. References

- [Hibernate ORM Releases and Compatibility Matrix](https://hibernate.org/orm/releases/) — release status, JDK, Jakarta Persistence, Spring Boot, and supported Hibernate lines.
- [Hibernate ORM 7.4 Documentation](https://hibernate.org/orm/documentation/7.4/) — User Guide, Integration Guide, Migration Guide, and Javadocs for that release line.
- [Hibernate ORM Integration Guide](https://docs.hibernate.org/stable/core/integrationguide/html_single/) — ServiceRegistry, Integrator, and integration points for extension developers.
- [Hibernate ORM User Guide](https://docs.hibernate.org/stable/core/userguide/html_single/) — mapping, type system, fetching, caching, schemas, and query behavior.
- [Hibernate Dialects](https://docs.hibernate.org/stable/core/dialect/) — supported dialects and minimum database versions.
- [Hibernate Migration Guides](https://hibernate.org/orm/documentation/migrate/) — API/SPI, default, and DDL changes across version lines.
- [Testcontainers JDBC Support](https://java.testcontainers.org/modules/databases/jdbc/) — database containers and JDBC wiring in integration tests.

An extension is truly production-ready only when it registers cleanly, preserves semantics on the target Hibernate line, and runs reliably on the production database. Test pure logic in unit tests, verify bootstrapping in integration tests, and use Testcontainers with the exact engine and version to validate JDBC, dialects, schemas, transactions, and extension behavior. Whenever upgrading Hibernate or the database, re-run the compatibility matrix and migration tests before release.