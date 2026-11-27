# Checking Changes in Spring Data Relational, Spring R2DBC, and Drivers

## 1. Why Check Changes Before Upgrading?

A Spring Data R2DBC application does not depend on a single library. When executing a query, multiple layers coordinate:

1. Spring Data Relational provides shared abstractions and the mapping model.
2. Spring Data R2DBC provides reactive repositories and persistence integration with R2DBC.
3. Spring Framework R2DBC provides `ConnectionFactory` integration, `DatabaseClient`, and transaction support.
4. R2DBC SPI defines the contract between the framework and drivers.
5. The R2DBC driver translates operations into the concrete wire protocol of PostgreSQL, MySQL, SQL Server, or another database engine.
6. The connection pool and database server affect lifecycle, performance, and runtime behavior.

A change in one layer can impact the others. For example:

- A new driver requires a different R2DBC SPI version.
- Spring Framework changes bind APIs or transaction integration.
- Spring Data changes mapping metadata or query generation.
- A database server upgrade introduces reserved keywords or changes codecs.
- Bumping the Spring Boot BOM resolves many dependencies to new versions simultaneously.

Therefore, before upgrading, you need to know **which components changed, what kind of changes they are, whether the versions are compatible, and whether actual application behavior is affected**.

The goal of checking is not merely getting the project to compile. The application must also start up, connect to the database, map data accurately, execute queries correctly, manage transactions, and run stably under load.

## 2. Understanding Component Layers and Versions

First, identify which dependency belongs to which layer. Similar names do not mean they are the same module.

| Component | Primary Responsibility | Example Artifact / Package |
| --- | --- | --- |
| Spring Boot | Auto-configuration, starters, and dependency management | `spring-boot-starter-data-r2dbc` |
| Spring Data Relational | Mapping metadata and shared relational abstractions | `spring-data-relational` |
| Spring Data R2DBC | Reactive repositories and Spring Data R2DBC integration | `spring-data-r2dbc` |
| Spring Framework R2DBC | `DatabaseClient`, transaction manager, and connection integration | `spring-r2dbc` |
| R2DBC SPI | `ConnectionFactory`, `Connection`, `Statement`, `Result` contracts | `r2dbc-spi` |
| R2DBC driver | Communication with a specific database | `r2dbc-postgresql`, `r2dbc-mysql`, `r2dbc-mssql` |
| R2DBC pool | Connection pooling for `ConnectionFactory` | `r2dbc-pool` |
| Database server | SQL dialect, data types, protocol, and server behavior | PostgreSQL, MySQL, SQL Server |

### 2.1. Spring Data Relational and Spring Data R2DBC

Spring Data Relational contains relational components shared across the Spring Data ecosystem. Spring Data R2DBC builds reactive integration on top of those abstractions.

When reading release notes, distinguish changes in the shared relational module from changes specific to R2DBC. A mapping change can affect multiple modules, whereas a reactive repository or R2DBC query execution change impacts only the R2DBC layer.

### 2.2. Spring R2DBC Belongs to Spring Framework

Spring Framework provides the `org.springframework.r2dbc` package. APIs here include:

- `DatabaseClient`.
- `R2dbcEntityTemplate` integration.
- `R2dbcTransactionManager`.
- Connection lifecycle and transaction support.
- Bind marker abstractions used by Spring components.

When upgrading Spring Framework, check these APIs even if the Spring Data version did not change directly in your build file.

### 2.3. R2DBC SPI and Driver Must Be Checked Together

The R2DBC SPI defines the contract implemented by drivers. A given driver may require a specific SPI range and have its own behavior regarding:

- Bind markers and positional indexes.
- Codecs and data types.
- Prepared statements.
- Generated values and result metadata.
- Cancellation, timeouts, and error mapping.
- SSL/TLS, authentication, and protocols.

A new driver can compile cleanly yet behave differently at runtime. Always check both dependency compatibility and database integration.

## 3. Distinguishing Types of Changes

Not every change in release notes carries the same risk. You can classify them as follows:

| Change Type | Meaning | Impact Example |
| --- | --- | --- |
| Source/API | Changes to APIs called directly by code | Method removed, signature changed, or package moved |
| Binary | Changes at bytecode/linkage level | `NoSuchMethodError`, `NoClassDefFoundError` |
| Behavior | API still runs, but results or semantics change | Mapping, ordering, or transaction behavior |
| Configuration | Properties, defaults, or config keys change | Pool options, initialization, SSL |
| Dependency | Direct or transitive versions change | R2DBC SPI resolves differently |
| SQL/Dialect | Generated SQL or driver interpretation changes | Bind markers, pagination, generated keys |
| Type/Codec | Data encoding/decoding changes | UUID, JSON, timestamp, array |
| Performance | Latency, allocation, or resource usage changes | Pool acquire, fetch size, backpressure |
| Security | TLS, authentication, CVEs, or secure defaults change | Certificate validation, protocols |

During an upgrade review, record each change under these categories. Classification guides the right verification: compile tests for APIs, integration tests for behavior, dependency graphs for compatibility, and load tests for performance.

## 4. Capture Current Versions Before Reading Release Notes

Do not start by grabbing the latest versions and bumping everything at once. First, snapshot the currently running dependency state.

Collect:

- Spring Boot plugin and BOM version.
- Actual Spring Framework version.
- Spring Data release train and module versions.
- `r2dbc-spi` version.
- R2DBC driver and pool versions.
- Database server version.
- Java runtime version.
- Build tool and dependency management mechanism.

Example Gradle dependency declarations:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
```

When using Spring Boot dependency management, projects typically omit explicit versions for BOM-managed dependencies.

### 4.1. Save the Current Dependency Graph

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

On Windows:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
```

To inspect why an artifact version was selected:

```bash
./gradlew dependencyInsight \
  --dependency spring-data-relational \
  --configuration runtimeClasspath
```

Repeat for key artifacts:

```bash
./gradlew dependencyInsight --dependency spring-data-r2dbc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-r2dbc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency r2dbc-spi --configuration runtimeClasspath
./gradlew dependencyInsight --dependency r2dbc-postgresql --configuration runtimeClasspath
./gradlew dependencyInsight --dependency r2dbc-pool --configuration runtimeClasspath
```

With Maven:

```bash
mvn dependency:tree
```

Filter the dependency tree by artifact:

```bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-relational
mvn dependency:tree -Dincludes=org.springframework:spring-r2dbc
mvn dependency:tree -Dincludes=io.r2dbc:r2dbc-spi
```

Save the output as a baseline to compare after upgrading. Do not look only at versions written in `build.gradle`; the real versions are what the build tool resolves after applying BOMs, constraints, exclusions, and overrides.

### 4.2. Inspect the Runtime Classpath

A dependency listed in a build file is not guaranteed to be the version active at runtime. Check the right configuration:

- `compileClasspath`: dependencies used during compilation.
- `runtimeClasspath`: dependencies present at runtime.
- Test runtime configuration: dependencies used during integration tests.

Drivers and pools are typically runtime dependencies. If tests use a different driver than production, test results may not reflect production behavior.

## 5. Understanding BOMs and Dependency Management

A BOM (Bill of Materials) provides a curated set of versions tested together for compatibility. The Spring Boot BOM manages versions across Spring Framework, Spring Data, and integration libraries.

When upgrading Spring Boot, the BOM can simultaneously change:

- Spring Framework.
- The Spring Data release train.
- Micrometer.
- Reactor.
- Managed R2DBC SPI or drivers.
- Other supporting libraries.

That is why a Spring Boot upgrade is a coordinated group change rather than a single-line version bump.

### 5.1. Prefer BOM-Managed Versions

Example:

```groovy
plugins {
    id "org.springframework.boot" version "<boot-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
```

Replace `<boot-version>` with the version chosen after checking compatibility. Examples avoid hardcoding one specific version since projects run different release trains.

When a BOM manages versions, avoid manually adding versions for `spring-data-relational`, `spring-data-r2dbc`, `spring-r2dbc`, or `r2dbc-spi` unless there is a clear reason and verified compatibility.

### 5.2. When Overriding a Version Is Necessary

Sometimes a driver or dependency needs a fix not yet included in the BOM. Before overriding:

1. Identify why the BOM-managed version does not meet requirements.
2. Read the release notes of the overridden artifact.
3. Check dependency constraints of dependent artifacts.
4. Check which SPI version the driver requires.
5. Verify Spring modules using that SPI remain compatible.
6. Add integration tests running against the target driver and database.
7. Document why the override exists and when it can be removed.

Never override `r2dbc-spi` alone just to make dependency resolution stop complaining. Forcing a version may allow compilation while causing linkage or behavioral errors at runtime.

### 5.3. Spring Data Release Trains

Spring Data ships as release trains, aligning multiple Spring Data modules along a coordinated release line. When using Spring Boot, check which release train the Boot BOM manages.

Never mix Spring Data modules from different release trains without confirmed compatibility. A newer module may rely on APIs from a newer `spring-data-relational` or Spring Framework release.

## 6. Reading Release Notes in Order

When a dependency changes, read documentation in this order:

1. Release notes for the platform/framework being upgraded.
2. Migration guide or upgrade guide.
3. Changelogs of individual modified modules.
4. API documentation for affected classes/methods.
5. Release notes for the driver and R2DBC SPI.
6. Database server release notes if the server is also upgrading.

Each source answers a different question:

| Source | What to Look For |
| --- | --- |
| Spring Boot release notes | BOM, auto-configuration, properties, starters, and logging changes |
| Spring Data release notes | Repository, mapping, conversion, and query generation changes |
| Spring Framework release notes | `DatabaseClient`, transactions, connection lifecycle |
| R2DBC SPI release notes | Contract between framework and drivers |
| Driver changelog | Codecs, protocols, pooling, binding, SSL, and bug fixes |
| Database release notes | SQL syntax, types, reserved keywords, authentication, and server behavior |

Do not search only for headings containing "breaking." A changed default or bug fix can alter behavior without being labeled a breaking API change.

### 6.1. Look for Breaking Changes and Deprecations

Search for keywords:

- Breaking change.
- Removed.
- Deprecated.
- Behavior change.
- Default changed.
- Migration.
- Compatibility.
- Requires.
- Minimum supported.
- Security.

Deprecated does not mean immediately removed. Still, if code invokes deprecated APIs, identify the recommended replacement and when the API may be dropped.

### 6.2. Read the Full Version Span

If a project upgrades from version A to version D, inspect changes from A through D. Do not read only D's release notes; changes may have landed in B or C.

When release notes are split by minor release, read each milestone sequentially or use a consolidated migration guide. Record both the first version introducing a change and the final target version.

### 6.3. Check Issues and Pull Requests When Release Notes Are Brief

Release notes are sometimes concise. When a change could affect your code:

- Search issues matching the class/method name or behavior.
- Read the pull request that implemented the fix.
- Inspect new upstream tests added in that PR.
- Determine whether the change was a bug fix, API design change, or intentional behavior adjustment.

Issue discussions are helpful context, but they do not replace official release documentation. Upgrade decisions must rest on actual resolved artifact versions and your application's tests.

## 7. Checking Changes in Spring Data Relational

Spring Data Relational affects the mapping model and how the framework interprets entity metadata. When upgrading, pay attention to these areas.

### 7.1. Mapping Annotations and Metadata

Check:

- `@Table`, `@Column`, `@Id`.
- `@MappedCollection` and aggregate mapping.
- Naming strategies and table/column name generation.
- Embedded/complex property mapping if used.
- Entity constructors and property access.
- Generated identifiers and entity lifecycle.

A mapping change may compile cleanly yet cause the framework to read/write the wrong column, alter SQL identifier naming, or hydrate entities differently.

### 7.2. Aggregate and Collection Mapping

Spring Data Relational uses an aggregate model. Relationships between root entities and collections are persisted via framework-supported mapping rather than ORM lazy relationship tracking.

When upgrading, verify:

- Collections save and load properly.
- Foreign key / key columns resolve with the expected names.
- Collection ordering is preserved if required.
- Insert/update/delete behavior for child rows has not shifted.
- `@MappedCollection` mappings retain prior semantics.

### 7.3. Custom Conversions

Applications often use converters to translate Java types to database types:

- UUID.
- Enum.
- JSON documents.
- Value objects.
- Money or decimal wrappers.
- Date/time types.

Verify registration and precedence of custom converters after upgrading. A converter can still compile yet no longer be selected due to mapping configuration or converter discovery changes.

### 7.4. Entity Callbacks and Auditing

If the application uses callbacks or auditing, verify:

- Which callbacks execute before/after insert/update.
- Whether created/modified values update accurately.
- Whether reactive callbacks return publishers aligned with the lifecycle.
- Whether persisted entities reflect values updated by callbacks.

Do not unit-test callback methods in isolation only; execute real repository operations to confirm the framework invokes callbacks at the expected points.

### 7.5. Optimistic Locking and Version Fields

If entities use a version field to detect concurrent updates, verify:

- Version increments properly after updates.
- Updating with a stale version detects a conflict.
- Initial inserts initialize the version properly.
- Exceptions map accurately for the service layer.

This behavior must be tested against a real database because SQL update predicates and affected row counts depend on the dialect and driver.

## 8. Checking Changes in Spring Data R2DBC

Spring Data R2DBC provides reactive repositories and query execution integration. When upgrading, check:

### 8.1. Repository API

Check:

- `ReactiveCrudRepository` and derived query methods.
- `@Query` and parameter binding.
- `@Modifying` for write queries if used.
- Projections and result mapping.
- Supported paging/sorting APIs.
- Custom repository fragments/implementations.

If method signatures changed, compile errors surface only part of the impact. Also verify query derivation semantics and result mapping.

### 8.2. Query Derivation

Derived queries generate SQL from method names. After upgrading, confirm:

- Property names parse accurately.
- Nested property predicates work as intended.
- Sort ordering and null handling have not shifted unexpectedly.
- Query count and SQL shape do not regress.
- Method name keywords remain supported.

Do not assume every method name valid in other Spring Data modules works identically in R2DBC.

### 8.3. Custom Queries and Bind Parameters

For `@Query`, `DatabaseClient`, or custom repositories, verify:

- Named parameters expand to the right bind markers.
- Positional binding order does not shift.
- `null` binds with the proper type.
- Collection parameters and empty collections are handled properly.
- Identifiers are quoted properly per dialect.
- Native SQL does not rely on another database's syntax.

### 8.4. Reactive Semantics

Spring Data R2DBC works with `Mono` and `Flux`. Verify:

- Publishers remain lazy as expected.
- A single subscription does not unexpectedly trigger multiple queries.
- Cancellation releases resources.
- Errors propagate to callers.
- Backpressure is honored properly.
- No hidden `subscribe()` or `block()` crept into custom repositories.

### 8.5. Result Mapping and Projections

If the upgrade changes mapping metadata, projections, or constructor binding, verify:

- Column aliases in native queries.
- Constructor parameter names/types.
- Nullability.
- Numeric conversions.
- Timestamps/timezones.
- Column labels and casing.

## 9. Checking Changes in Spring Framework R2DBC

Spring Framework provides the direct bridge between the application and the R2DBC SPI. When upgrading Framework, read the data-access and R2DBC sections of its release notes.

### 9.1. DatabaseClient

If code uses `DatabaseClient` directly, verify:

- Builders and `ConnectionFactory` configuration.
- Named parameter expansion.
- Bind APIs by name and index.
- `bindNull` and SQL types.
- Row mapping and metadata.
- Fetch API, `rowsUpdated()`, and result consumption.

API changes can break compilation; behavioral changes can alter query execution with zero compile errors.

### 9.2. ConnectionFactory and Connection Lifecycle

Check:

- Connections acquire and release properly.
- Closing connections returns them to the pool.
- Cancellation frees resources.
- Error paths close resources.
- Connection validation or lifecycle hooks changed.

Lifecycle bugs often surface only under load or request cancellation, so isolated unit tests are insufficient.

### 9.3. Transaction Manager

If using `R2dbcTransactionManager` or `TransactionalOperator`, verify:

- Transactions begin at the expected point.
- Connections bind into the reactive transaction context.
- Repositories and `DatabaseClient` share the same `ConnectionFactory` when participating in the same transaction.
- Rollback triggers when publishers emit errors.
- Cancellation and nested transaction behavior match expectations.
- Isolation levels and timeouts apply as configured.

Pay special attention to context propagation. R2DBC transactions rely on reactive context; never substitute JDBC-style `ThreadLocal` transaction assumptions.

### 9.4. Bind Markers and Dialect Integration

If supporting multiple databases, check bind marker expansion and dialects. Framework upgrades may change marker generation or identifier quoting to match drivers.

Testing against the actual database/driver is far more reliable than asserting SQL strings in unit tests alone.

## 10. Checking Changes in the R2DBC SPI

The R2DBC SPI is the contract between the framework and drivers. SPI changes can affect multiple layers simultaneously.

Areas to review:

- `ConnectionFactory` interfaces and methods.
- `Connection`, `Statement`, `Batch`, `Result`.
- `Row`, `RowMetadata`, `ColumnMetadata`.
- `Readable`, `Parameter`, `Type`.
- `ValidationDepth` and validation APIs.
- Transaction methods and isolation levels.
- Lifecycle, cancellation, and reactive publisher contracts.

### 10.1. Compile Compatibility Is Not Enough

A driver may compile against an SPI while runtime behavior shifts due to:

- New default methods or contracts.
- New data types.
- Changed metadata returned.
- Changed cancellation handling.
- Changed error mapping.

Read SPI and driver release notes side by side. When a driver bumps its transitive SPI dependency, confirm Spring Framework/Spring Data supports that SPI version.

### 10.2. Never Force an SPI Version in Dependency Resolution

If Gradle/Maven reports an `r2dbc-spi` conflict, do not fix it by forcing a version right away. First determine:

1. Which artifact requests which SPI version.
2. Which SPI version the driver implements.
3. Which SPI contract Spring Framework supports.
4. Whether the BOM-managed version matches expectations.

Then choose a publisher-supported version set or upgrade the platform along a compatible path.

## 11. Checking Changes in the R2DBC Driver

The driver translates R2DBC operations into database protocol messages. Driver changelogs therefore often contain changes directly affecting data and operations.

### 11.1. Bind Parameters and Prepared Statements

Verify:

- Native bind markers.
- Binding by index and parameter name.
- Binding `null`.
- Batch execution.
- Prepared statement caching.
- Data type encoding.

A query's source code may be unchanged while a new driver encodes a parameter type differently.

### 11.2. Codecs and Type Mapping

Test every special type used by the application:

| Java Type / Data | What to Confirm |
| --- | --- |
| UUID | Format, byte order, or native type |
| `Instant`, `OffsetDateTime` | Timezone and precision |
| `BigDecimal` | Precision and scale |
| Boolean | Native boolean, bit, or numeric representation |
| Enum | String, ordinal, or custom codec |
| JSON | String/document codec and null handling |
| Array | Element type and collection mapping |
| Binary | Byte order, length, and memory behavior |

Run round-trip tests: write values, read them back, and compare according to domain semantics. Do not verify only that the query succeeded without error.

### 11.3. Generated Keys and Result Metadata

If a driver alters generated values or result metadata, repository inserts may be affected:

- Are IDs returned?
- Are column labels preserved?
- Did numeric types shift?
- Does row metadata preserve casing?
- Does `rowsUpdated` reflect exact row counts?

Test both single inserts and inserts inside transactions if the application relies on generated IDs.

### 11.4. Cancellation and Timeouts

Reactive requests can cancel when clients disconnect or time out. Check whether the new driver:

- Cancels running queries.
- Returns connections cleanly to the pool.
- Continues executing queries on the server after cancellation.
- Maps timeouts to the expected exception types.
- Leaves connections usable after cancellation.

These behaviors matter greatly for long queries, streamed results, and endpoints with tight client timeouts.

### 11.5. TLS, Authentication, and Protocols

Driver changelogs may change:

- TLS protocols or cipher suites.
- Certificate validation.
- Authentication mechanisms.
- Database protocol versions.
- DNS/host resolution.
- Keepalive and socket timeouts.

Never disable certificate validation to work around post-upgrade connection errors. Fix trust stores, certificate chains, and server policies according to driver docs.

## 12. Checking Connection Pool Changes

If using `r2dbc-pool`, read its changelog separately. Pooling directly governs concurrency and connection lifecycles.

Check:

- `maxSize`, `initialSize`.
- Acquire timeout.
- Max idle time and max life time.
- Validation queries or validation depth.
- Background eviction.
- Pool disposal/shutdown.
- Metrics for active, idle, and pending acquires.

A changed default can cause the application to open more connections or time out sooner even with zero code changes.

### 12.1. Distinguish Pool Timeouts from Query Timeouts

These two failures have different root causes:

- Acquire timeout: unable to borrow a connection from the pool within the allowed wait window.
- Query timeout: a connection was acquired, but the database operation exceeded its limit.

Traces and metrics should distinguish these two durations. When upgrading pools or drivers, test concurrency and connection exhaustion scenarios.

## 13. Reading Migration Guides and Handling Deprecated APIs

When release notes mark an API deprecated:

1. Search for the API across the codebase.
2. Understand why it was deprecated.
3. Read the recommended replacement.
4. Check behavioral differences between the old and new APIs.
5. Migrate within a small, bounded scope.
6. Run relevant tests.
7. Continue upgrading only after completing the migration step.

Do not silence deprecation warnings by suppressing them without planning a replacement. Warnings signal APIs likely to be removed in the next major release.

### 13.1. Search API Usages Across the Project

Search for commonly used classes:

```bash
rg -n "DatabaseClient|R2dbcEntityTemplate|R2dbcTransactionManager" src
rg -n "ReactiveCrudRepository|@Query|@MappedCollection" src
rg -n "ConnectionFactory|Statement\.bind|bindNull" src
```

Searching specific packages helps pinpoint all code impacted when an API changes.

### 13.2. Avoid Refactoring All Persistence in the Same Upgrade

If you bump versions while also redesigning repositories, query strategies, and mapping models, test failures become hard to attribute.

Separate platform upgrades from business refactoring whenever possible. If combining them is unavoidable, document each change and test each layer separately.

## 14. Comparing Dependency Graphs Before and After

After updating versions/BOMs, regenerate the dependency graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Compare key artifacts:

| Artifact | Baseline | Candidate | What to Verify |
| --- | --- | --- | --- |
| `spring-data-relational` | Current version | Post-upgrade version | Mapping metadata |
| `spring-data-r2dbc` | Current version | Post-upgrade version | Repositories/queries |
| `spring-r2dbc` | Current version | Post-upgrade version | `DatabaseClient`/transactions |
| `r2dbc-spi` | Current version | Post-upgrade version | Driver contract |
| R2DBC driver | Current version | Post-upgrade version | Codecs/protocol |
| `r2dbc-pool` | Current version | Post-upgrade version | Connection lifecycle |

Not every artifact has to share the same version number. Projects ship on independent release cadences. What matters is checking the compatibility matrix and supported dependency management.

### 14.1. Find Overridden Versions

Gradle `dependencyInsight` reveals why a version was chosen, such as:

- BOM/platform constraint.
- Version conflict resolution.
- Dependency constraint.
- Explicit version.
- Resolution rule.

If a resolved version differs from what the BOM specifies, investigate the cause before proceeding.

### 14.2. Lockfiles and Reproducibility

If the project uses Gradle dependency locking, update lock state intentionally and commit it alongside the dependency change. Never delete lockfiles just to let the build tool pick arbitrary newer versions.

If using dependency verification, update checksum/signature metadata per project policy after verifying artifact provenance.

## 15. Building a Compatibility Matrix

A compatibility matrix keeps the team aligned on which version combinations have been verified.

Example structure:

| Stack | Spring Boot | Spring Data train | Framework | R2DBC SPI | Driver | Database |
| --- | --- | --- | --- | --- | --- | --- |
| Current | Running version | Current train | Resolved version | Resolved version | Resolved version | Current server |
| Candidate | Target version | BOM train | BOM version | Supported version | Compatible driver | Target server |
| Tested | Passing test version | Passing train | Passing version | Passing version | Passing version | Passing server |

Never fill in versions by guesswork. Pull versions from dependency graphs and official project release documentation.

### 15.1. Rules for Reading the Matrix

- Start with the Spring Boot BOM to identify the managed version set.
- Ensure the Spring Data release train is compatible with the selected Spring Framework.
- Ensure the driver is compatible with the resolved R2DBC SPI version.
- Ensure the database server version is supported by the driver.
- Ensure the Java runtime meets minimum requirements of both platform and driver.
- Ensure the connection pool is compatible with both SPI and driver.

### 15.2. Upgrade Along Controlled Axes

When upgrading multiple layers, define a candidate stack and verify each component. Never assume the latest driver is always compatible with the latest Spring Data; they follow independent release cycles.

## 16. Safe Upgrade Workflow

A practical workflow breaks down into these steps:

### Step 1: Record the Baseline

- Record Java, Spring Boot, Spring Framework, and Spring Data versions.
- Save the dependency graph.
- Record database server and driver versions.
- Run existing tests to establish whether the baseline passes or has known failures.
- Capture latency, pool, and error-rate metrics if available.

### Step 2: Define the Upgrade Goal

State the rationale clearly:

- Security patch.
- Required bug fix.
- Support for a newer database version.
- Java/Spring Boot platform upgrade.
- Need for new APIs or features.
- End-of-support for the current version.

The goal shapes test scope. A security patch prioritizes CVEs and TLS checks; a major driver upgrade focuses on codecs and protocols.

### Step 3: Read Release Documentation

Read release notes, migration guides, and changelogs across the full version range. Build a list of:

- Breaking changes.
- Deprecated APIs.
- Default changes.
- Minimum supported Java/SPI/database versions.
- Driver fixes.
- Security fixes.
- Known issues.

### Step 4: Update Platform/BOM

When upgrading Spring Boot, update the plugin and BOM to the target release set. Avoid overriding individual Spring Data/Framework modules unless backed by a documented compatibility rationale.

### Step 5: Resolve the Dependency Graph

Run dependency reports and `dependencyInsight`. Confirm no SPI or framework version is forced inappropriately.

### Step 6: Fix Compilation/APIs

Resolve compile errors and deprecated APIs. Keep source changes strictly within necessary scope.

### Step 7: Run Unit and Slice Tests

Verify mapping logic, converters, query builders, and service behaviors.

### Step 8: Run Integration Tests with the Real Driver

Use Testcontainers or matching test databases. Verify queries, codecs, transactions, pooling, cancellation, and migrations.

### Step 9: Check Performance and Operations

Compare latency, throughput, pool usage, error rates, and resource consumption against the baseline.

### Step 10: Controlled Rollout

Deploy to staging/canary or phase rollouts if supported. Monitor driver errors, SQL states, pool exhaustion, and slow queries.

### Step 11: Document Verified Versions

Update the compatibility matrix, dependency locks, upgrade notes, and rollback instructions.

## 17. Required Test Suite After Upgrading

Not every application needs identical tests. Tailor tests to the persistence features your project actually uses.

| Category | Cases to Verify |
| --- | --- |
| Startup | Application context creates `ConnectionFactory` and repositories |
| Connectivity | Connections, authentication, TLS, and validation |
| CRUD | Insert, select, update, delete |
| Mapping | Table/column names, constructors, naming, aggregates |
| Conversion | UUID, enum, JSON, decimal, timestamp, boolean |
| Binding | Named, positional, null, and collections |
| Queries | Derived queries, native queries, sorting, and pagination |
| Generated values | Identity, sequence, or returned keys |
| Transactions | Commit, rollback, isolation, and timeouts |
| Concurrency | Optimistic locking and concurrent updates |
| Lifecycle | Cancellation, connection release, and pool shutdown |
| Error handling | SQL states, constraint violations, timeouts |
| Migration | Schema migrations and compatibility with existing data |
| Performance | Latency, throughput, pool saturation, and memory |

### 17.1. Unit Tests Do Not Replace Integration Tests

Unit tests can verify converters or business logic. They do not prove the driver executes SQL properly on a real database.

For example:

- Mocked repositories do not test bind markers.
- Mocked `ConnectionFactory` does not test codecs.
- H2 does not guarantee identical PostgreSQL or MySQL behavior.
- Insert-only tests do not exercise rollback or cancellation.

Keep unit tests for fast feedback while maintaining integration tests against the production driver and database.

### 17.2. Testcontainers

Testcontainers runs a real database inside the test environment:

```java
@Testcontainers
@SpringBootTest
class CustomerRepositoryIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    // Configure R2DBC URL and credentials from the container.
    // Run repository operations against this database.
}
```

This code is an illustrative skeleton. Spring R2DBC URL configuration must use the matching R2DBC driver; a Testcontainers JDBC URL does not become an R2DBC URL automatically.

If the project supports multiple databases, maintain separate test suites per officially supported driver/server.

## 18. Testing Schema Migrations and Existing Data

Upgrading drivers or frameworks can expose pre-existing schema issues. Before deploying:

- Run migrations from the current schema version.
- Check for newly reserved keywords on newer server versions.
- Check indexes, constraints, generated columns, and sequences.
- Confirm data types match the new codecs.
- Check legacy data for nulls or unusual formats.
- Verify old and new application versions can coexist during rollout if needed.

### 18.1. Expand-and-Contract

If upgrading the application while also changing the schema, you can use expand-and-contract:

1. Add new structures so old code continues working.
2. Deploy code capable of reading/writing the new structure.
3. Migrate data or enable feature flags.
4. Confirm all instances use the new structure.
5. Drop old structures in a subsequent release.

This reduces risk when instances do not roll out atomically.

### 18.2. Driver Rollback Does Not Roll Back Schema

If you roll back the application to an older driver, migrated schemas may no longer be compatible with the old code. Keep schemas backward-compatible or prepare compensating migrations.

## 19. Post-Upgrade Performance Testing

A new version can fix bugs while also changing allocations, codecs, pooling, or query execution.

Compare under identical workloads:

- Request latency p50, p95, p99.
- Query duration by operation.
- Throughput.
- Connection acquire time.
- Active/idle/pending pool connections.
- Timeout and error rates.
- CPU, heap, and garbage collection.
- Rows fetched and memory footprint.

Keep test data, concurrency, database config, and workload close to the baseline. Changing many factors at once obscures performance root causes.

### 19.1. Avoid Conclusions from a Single Run

Run benchmarks repeatedly, exclude warm-up periods, and examine latency distributions. A single faster run may reflect warm caches or lighter database load.

### 19.2. Query Spans and Database Execution Plans

If query spans grow longer than before:

1. Check connection acquire latency.
2. Check network and result consumption.
3. Compare generated SQL.
4. Capture execution plans from the database.
5. Check indexes and statistics.
6. Compare driver versions and codecs.

Do not blame the driver based solely on total publisher duration.

## 20. Security and Maintenance Review

Release notes often include security fixes or TLS/authentication changes. When upgrading:

- Scan the dependency tree for CVEs.
- Confirm drivers are off vulnerable versions.
- Verify TLS certificate validation.
- Check database authentication plugins.
- Verify secret rotation and credential handling.
- Ensure dependencies come from trusted repositories.
- Update SBOMs and dependency verification if used.

Never disable TLS validation or weaken authentication policies just to let a new driver connect. Find the real cause in certificates, server settings, and driver docs.

## 21. Automated Dependency Tracking

Tools like Renovate or Dependabot open pull requests when new dependency versions ship.

To review effectively:

- Group dependencies belonging to the same platform/BOM cleanly.
- Do not lump every driver and database upgrade into one unreviewable PR.
- Require dependency graph diffs and release notes in PR descriptions.
- Run automated unit and integration tests.
- Auto-merge only low-risk patch releases if project policy permits.
- Require compatibility and migration reviews for minor/major bumps.

Automation detects new versions, but it does not replace verifying behavior and stack compatibility.

## 22. Example Review of a Version Bump

Suppose a pull request upgrades Spring Boot from line A to line B and the PostgreSQL driver from line X to line Y.

Reviewers can inspect in this order:

### 22.1. Dependency Changes

```diff
- id("org.springframework.boot") version "<boot-A>"
+ id("org.springframework.boot") version "<boot-B>"
```

The driver may be BOM-managed or explicitly versioned. If the driver is overridden, the PR must document why and provide compatibility evidence.

### 22.2. Resolved Graph Changes

Include a diff summary:

```text
spring-data-relational: A -> B
spring-data-r2dbc:      A -> B
spring-r2dbc:           A -> B
r2dbc-spi:              A -> B
r2dbc-postgresql:       X -> Y
```

Symbols A/B/X/Y represent before/after versions. Reviewers must inspect actual versions in the dependency report.

### 22.3. Test Evidence

The PR should demonstrate:

- Application context starts cleanly.
- Repository CRUD tests pass.
- Custom queries and bindings pass.
- Converter round-trips pass.
- Transaction commit/rollback tests pass.
- Tests ran against the exact PostgreSQL driver/server version.
- Pool and latency show no notable regressions.

### 22.4. Conditional Approval

An upgrade is ready only once the version graph is understood, required migrations are applied, and tests reflect the real database. Successful compilation confirms source/API compatibility only up to a point.

## 23. Common Mistakes When Checking Changes

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Compile errors after upgrade | API changed/removed or modules mismatched | Read migration guide and verify version alignment |
| `NoSuchMethodError` at runtime | Runtime classpath differs from compile classpath or binary mismatch | Inspect the runtime dependency graph |
| `ClassNotFoundException` | Artifact/package moved or dependency dropped | Inspect dependency tree and migration guide |
| Driver fails to initialize | Incompatible R2DBC SPI | Check driver SPI requirements and BOM |
| Repositories run but map wrong data | Mapping/converter behavior changed | Run round-trip tests on a real database |
| Query syntax errors | Dialect or bind markers changed | Inspect generated SQL and driver native syntax |
| Insert does not return generated ID | Driver/result metadata behavior changed | Verify generated values and integration tests |
| Transactions fail to roll back | Reactive transaction context or `ConnectionFactory` mismatch | Check transaction manager and publisher chain |
| Connection pool exhaustion | Pool defaults/lifecycle or cancellation changed | Check pool metrics and stress tests |
| Passes locally, fails in prod | Different DB server/driver or configuration | Match production driver/server major versions in tests |
| Version chosen outside BOM | Explicit override or transitive constraint | Use `dependencyInsight` and fix the override source |
| Patch upgrade increases latency | Codec, pool, or query behavior changed | Compare benchmarks and per-operation traces |

## 24. Creating an Upgrade Change Report

A concise, reviewable report should include:

| Item | Content |
| --- | --- |
| Rationale | Security, bug fix, platform support, or feature |
| Baseline | Boot, Data, Framework, SPI, driver, pool, and database |
| Target | Post-upgrade version set |
| Release notes | Breaking changes, deprecations, defaults |
| Dependency graph | Changed artifacts and why versions were resolved |
| Source changes | API migrations and configuration updates |
| Data behavior | Mapping, codecs, binding, transactions, generated values |
| Test evidence | Compile, unit, integration, migration, performance |
| Risks | Unverified components or known limitations |
| Rollback | App version and schema compatibility |

Never write "bumped all dependencies to latest" as a sufficient description. Reviewers need to know which versions changed and why that combination is compatible.

## 25. Official Documentation to Consult

When executing an upgrade, prefer version-specific official release documentation:

- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/) — dependency management, auto-configuration, and observability.
- [Spring Boot Release Notes](https://github.com/spring-projects/spring-boot/releases) — per-release changes.
- [Spring Data Relational Documentation](https://docs.spring.io/spring-data/relational/reference/) — mapping, repositories, and relational behavior.
- [Spring Data Release Notes](https://github.com/spring-projects/spring-data-relational/releases) — changes in Spring Data Relational/R2DBC.
- [Spring Framework Reference](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html) — Spring R2DBC, `DatabaseClient`, and transactions.
- [Spring Framework Releases](https://github.com/spring-projects/spring-framework/releases) — Framework API and behavior changes.
- [R2DBC SPI](https://r2dbc.io/spec/) — contract between drivers and clients.
- [R2DBC Drivers](https://r2dbc.io/drivers/) — supported drivers and databases.
- [R2DBC Pool](https://github.com/r2dbc/r2dbc-pool) — pool releases and configuration.

Online docs often display the latest release by default. When investigating a specific project, open documentation/release tags matching your current and target versions rather than applying the newest docs blindly to older projects.

## 26. Pre-Merge Upgrade Checklist

Before merging a version change, confirm:

1. Current baseline and dependency graph are recorded.
2. Spring Boot, Spring Data, Spring Framework, R2DBC SPI, driver, pool, and database versions are all identified.
3. Release notes across the entire version span have been read.
4. Migration guides have been read and deprecated/breaking APIs addressed.
5. BOM and dependency constraints have been verified.
6. No SPI or Spring module has been overridden arbitrarily.
7. Runtime dependency graph matches intended versions.
8. Compilation and unit tests pass.
9. Integration tests run against the production driver/database.
10. Mapping, custom converters, binding, generated values, and transactions are verified.
11. Pool lifecycle, timeouts, and cancellation are tested.
12. Schema migrations remain compatible with old/new app versions per rollout plan.
13. Latency, throughput, pool usage, and error rates show no out-of-bounds regression.
14. Security/TLS/authentication are verified.
15. Version report, test evidence, and rollback plan are documented.

## 27. Handling Regressions Discovered After Upgrading

If errors appear after deployment:

1. Identify when errors started and the associated deployment/version.
2. Compare the running dependency graph against the baseline.
3. Classify the failure: API/linkage, mapping, driver, SQL, transactions, pool, or database server.
4. Use traces/logs to locate the first affected operation.
5. Check related release notes and upstream issues.
6. Reproduce with a minimal integration test against the exact driver/database.
7. Decide whether to roll back the application, driver, or database migration.
8. If rolling back, verify the current schema remains compatible with the old app.
9. Add a regression test before shipping a fix.
10. Update the compatibility matrix and upgrade notes once resolved.

Never force a dependency version in production just to stop immediate errors without understanding which contract broke. A controlled rollback is usually safer than an unverified dependency mix.

## 28. Conclusion

Checking changes across Spring Data Relational, Spring R2DBC, and drivers means tracking compatibility across multiple layers. Start from the actual dependency graph, use BOMs and release trains to align version sets, read migration guides across the entire upgrade range, and verify APIs, mapping, binding, codecs, transactions, pooling, and protocols. Compile checks are only the first step; integration tests with the exact R2DBC driver and database server verify true persistence behavior. Every upgrade should have a compatibility matrix, test evidence, documented risks, and a clear rollback plan.
