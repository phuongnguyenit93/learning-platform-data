# Reading Release Notes and Checking Compatibility Matrices Before Upgrading

Upgrading Spring Data R2DBC is not just bumping a version number in Gradle or Maven. An R2DBC application runs across multiple interdependent layers: Java, Spring Boot, Spring Framework, Spring Data, Reactor, R2DBC SPI, the database driver, the connection pool, and the database server itself. A newer release may require a higher Java version, a newer Spring Framework, a different SPI version, or alter mapping and transaction behavior.

Before upgrading, read the release notes and migration guides across the entire version range from your current release to the target release, then cross-check every component against official compatibility matrices. The outcome should be an evidence-backed decision: the target version is supported, changes affecting the application are identified, the dependency graph is aligned, and testing/rollback plans are clear.

## 1. Why Read Release Notes Before Changing Versions?

Release notes document changes between versions: new features, bug fixes, deprecations, breaking changes, dependency baselines, and adjusted behaviors. An upgrade can compile cleanly yet still alter runtime behavior.

In Spring Data R2DBC, impact can appear across multiple layers:

- Spring Data Relational/R2DBC changes mapping, query derivation, repository APIs, converters, or dialects.
- Spring Framework changes reactive transactions, bean lifecycles, proxies, or Reactor integration.
- R2DBC SPI changes interfaces/contracts implemented by drivers and pools.
- Database drivers change type mapping, parameter binding, generated values, cancellation, or protocol behavior.
- Spring Boot changes auto-configuration, property names, dependency versions, and bean conditions.
- Java baseline shifts prevent the application or build plugins from running on older JDKs.
- Older or newer database servers may fall outside the driver's support matrix.

Reading release notes surfaces these changes before they turn into production incidents.

### 1.1. A Successful Upgrade Means More Than a Passing Build

A passing build only tells you the source code and dependencies passed compile and part of the test checks. It does not prove:

- The driver is compatible with the database server in use.
- Transaction rollback/commit still behaves accurately.
- Mappings for JSON, UUID, enum, array, timestamp, or decimal remain intact.
- The connection pool handles timeouts, validation, and shutdown correctly.
- Custom queries still run under the right SQL dialect.
- Existing migrations and schemas remain compatible.
- Production Java runtimes meet the new baseline.

Therefore, combine release-note review, dependency analysis, compatibility matrices, and integration tests against the target database.

## 2. Determine Your Exact Current Versions

Before choosing a target version, verify which versions the application is actually running. Versions declared directly in build files can differ from final resolved versions due to BOMs, dependency constraints, plugins, or transitive dependencies.

Collect at minimum:

| Component | What to Identify |
|---|---|
| Java | JDK used for building and JRE/JDK used at runtime |
| Spring Boot | Plugin and dependency management version |
| Spring Framework | `spring-core`, `spring-context`, `spring-r2dbc`, and related modules |
| Spring Data | Release train and `spring-data-relational`/`spring-data-r2dbc` |
| Reactor | `reactor-core` and Reactor BOM |
| R2DBC SPI | `io.r2dbc:r2dbc-spi` |
| Database driver | E.g., `r2dbc-postgresql` or `r2dbc-mysql` |
| Connection pool | E.g., `r2dbc-pool` if used |
| Database server | Engine, major/minor version, and extensions |
| Build tool | Gradle wrapper or Maven wrapper |
| Migration tool | Flyway/Liquibase version and JDBC driver if applicable |

### 2.1. Inspect the Actual Dependency Graph

With Gradle, view the dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

To see why a specific version was resolved:

~~~bash
./gradlew dependencyInsight --dependency spring-data-r2dbc --configuration runtimeClasspath
~~~

Inspect related components:

~~~bash
./gradlew dependencyInsight --dependency r2dbc-spi --configuration runtimeClasspath
./gradlew dependencyInsight --dependency r2dbc-postgresql --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn dependency:tree
~~~

Filter by artifact:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-r2dbc
mvn dependency:tree -Dincludes=io.r2dbc:r2dbc-spi,io.r2dbc:r2dbc-postgresql
~~~

Inspect the output and confirm where each dependency version originates. Do not look only at the build file. Check dependency lockfiles, version catalogs, platforms/BOMs, plugins, and CI configurations to know actual versions across all environments.

## 3. Define Target Versions and Upgrade Scope

Before selecting a target, answer:

- Is the current version still supported and receiving security fixes?
- Are there CVEs or critical bugs forcing an upgrade?
- Does the target version support your production JDK?
- Which Spring Framework and Spring Data release trains does the target Spring Boot manage?
- Does the target R2DBC driver support your current database server?
- Must the database server be upgraded at the same time?
- Are there breaking changes or migration guides to follow?
- Do current build tools/plugins support the required JDK?

### 3.1. Distinguish Patch, Minor, and Major Releases

Versioning names and rules vary across projects. Do not apply SemVer mechanically to every Spring component.

A practical breakdown:

- **Patch updates:** typically focus on bug fixes and security fixes within the same release line, though release notes still matter because behavior or transitive dependencies can change.
- **Minor/feature updates:** can add APIs, deprecate older APIs, and raise dependency baselines.
- **Major or release-train transitions:** likely introduce breaking changes, require newer JDKs/Spring Framework versions, and include explicit migration steps.

Spring Data uses release trains to align modules. Spring Boot curates a tested set of versions for Spring Framework, Spring Data, Reactor, and other dependencies. Choose a supported combination as your target rather than picking the highest version of each individual artifact.

### 3.2. Never Skip Intermediate Release Notes

Suppose the application is on release train A and wants to move to train D. Read the changes for B, C, and D—not just the release notes for D.

A change may be introduced in B, deprecated in C, and removed in D. Reading only D can cause you to miss why an old API was replaced and the recommended migration path introduced earlier.

For major upgrades, map out the version chain:

~~~text
Current
  -> intermediate release 1
  -> intermediate release 2
  -> target release
~~~

You do not necessarily have to deploy every intermediate version to production. However, read and address migration notes across the whole upgrade span; sometimes building and testing intermediate milestones helps isolate root causes of errors.

## 4. Official Documentation Sources to Cross-Check

Prioritize official documentation for each project at the exact matching versions.

| Source | Used to Verify |
|---|---|
| Spring Boot release notes and migration guide | JDK baseline, auto-configuration, property changes, dependency versions |
| Spring Boot dependency versions appendix | Managed versions of Spring Framework, Spring Data, Reactor, and libraries |
| Spring Data release notes | Repository, mapping, query, dialect, converter, and module changes |
| Spring Data compatibility matrix | Relationship between release train and Spring Framework baseline |
| Spring Framework release notes | Reactive transactions, bean lifecycle, proxies, and framework APIs |
| R2DBC SPI release notes/specification | Contract between framework, drivers, and pools |
| R2DBC driver documentation | Database server, Java, SPI, TLS, type mapping, and driver-specific behavior |
| Database vendor support matrix | Supported server versions, protocols, and features |
| Reactor release notes/BOM | Reactor APIs and Spring Framework compatibility |
| Gradle/Maven release notes | JDK and plugin/build compatibility |
| Security advisories/CVEs | Affected versions and patches |

Never rely on an outdated compatibility table in a blog post or forum answer as sole proof. If a blog conflicts with official documentation, record the discrepancy and verify against the version-specific official docs.

### 4.1. Read the Right Documentation Version

Reference documentation pages often default to the latest release. When upgrading to an older target version, switch the documentation selector to the exact target version or read the corresponding release tag.

Cross-check documentation within the same target line. Do not mix the latest Spring Boot migration guide with an older driver without verifying compatibility.

### 4.2. Check Support Lifecycle

Compatibility does not mean active support. A combination might run fine yet already be past its end-of-life for security patches.

Note release dates and support status, community or commercial end-of-support dates if your organization uses commercial support, whether security fixes are backported, whether the target belongs to an organization-approved release line, and when the next upgrade will be due.

## 5. Build a Compatibility Matrix for Your Application

A compatibility matrix records current versions, target versions, official constraints, and verification results for each component.

Example template:

| Component | Current | Target | Required Evidence | Status |
|---|---|---|---|---|
| Java runtime | Current JDK | Target JDK | Spring Boot system requirements | Unverified |
| Spring Boot | Boot current | Boot target | Boot release notes/dependency appendix | Unverified |
| Spring Framework | Framework current | Boot-managed target | Boot BOM + Framework release notes | Unverified |
| Spring Data train | Train current | Boot-managed target | Spring Data compatibility matrix | Unverified |
| `spring-data-r2dbc` | Resolved current | Managed target | Spring Data release notes | Unverified |
| Reactor | Resolved current | Boot-managed target | Reactor BOM/release notes | Unverified |
| R2DBC SPI | Resolved current | Driver-compatible target | SPI contract + driver docs | Unverified |
| R2DBC driver | Driver current | Driver target | Driver compatibility matrix | Unverified |
| Connection pool | Pool current | Pool target | Pool/SPI compatibility | Unverified |
| Database server | Server current | Current or target | Vendor support matrix | Unverified |
| Build tool | Wrapper current | Wrapper target | Gradle/Maven JDK compatibility | Unverified |
| Migration tool | Flyway/Liquibase current | Target | Migration tool compatibility | Unverified |

Do not mark something “compatible” merely because version numbers look close. Each status needs concrete evidence such as a documentation page name, version range, or integration test result.

### 5.1. Status Classifications in the Matrix

You can use these statuses:

- **Supported:** explicitly confirmed by official documentation or included in a support matrix.
- **Verified:** tested in an appropriate environment and meets requirements.
- **Conditional:** subject to conditions such as minimum database version, JDK, or driver options.
- **Unknown:** insufficient reliable evidence found yet.
- **Unsupported:** documentation explicitly states it is not supported.
- **Blocked:** known incompatibility or unresolved issue exists.

*Supported* and *Verified* are distinct concepts. A combination can be vendor-supported without having been tested in your application; conversely, a combination might pass a few tests while sitting outside the official support matrix.

### 5.2. Record Sources and Verification Dates

Each critical row should include the official URL or document title, the doc version reviewed, the verification date, support conditions, internal test results, and an owner if required by organizational process.

Compatibility matrices go stale quickly as new drivers or databases ship. Recording sources and dates makes future upgrades easy to re-verify.

## 6. Relationship Between Spring Boot, Spring Framework, and Spring Data

In a Spring Boot application, the Boot BOM manages a curated set of dependency versions tested together. The Spring Data release train also coordinates versions across Spring Data modules.

Therefore, when upgrading Boot:

1. Choose the target Boot release.
2. Read Boot release notes and migration guides.
3. Check the dependency versions appendix for managed Framework, Data, Reactor, and related dependencies.
4. Check the Spring Data compatibility matrix for that release train.
5. Verify R2DBC drivers and databases separately, because not every driver is managed or tested end-to-end by Boot.

Never manually bump `spring-data-r2dbc` ahead of the Boot BOM merely because a newer artifact exists in Maven Central. Overriding it can introduce incompatibilities with Spring Data Relational, Spring Framework, or other APIs.

### 6.1. Using the Spring Boot BOM

With Gradle, a common setup uses the Spring Boot plugin and Boot-provided dependency management:

~~~kotlin
plugins {
    id("org.springframework.boot") version "<boot-target>"
    id("io.spring.dependency-management") version "<dependency-management-plugin>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Replace version placeholders with verified target versions. If the project uses Gradle `platform(...)` BOMs directly instead of the `dependency-management` plugin, stay consistent with the project's dependency management style.

With Maven, use `spring-boot-starter-parent` or import the `spring-boot-dependencies` BOM per project conventions. Do not declare individual versions on Spring Framework/Spring Data artifacts when the BOM manages them.

### 6.2. When Not Using Spring Boot

If using Spring Data R2DBC standalone:

- Pick a matching Spring Data release train.
- Import that train's Spring Data BOM.
- Verify the Spring Framework baseline required by the train.
- Pick R2DBC SPI and driver versions per driver documentation.
- Align Reactor and reactive dependencies to framework requirements.
- Verify dependency convergence yourself because there is no Boot BOM overseeing everything.

Do not mix Spring Data modules from different release trains unless official documentation explicitly notes a supported case.

## 7. Cross-Checking R2DBC SPI, Drivers, and Connection Pools

This step is especially important for R2DBC applications. Spring Data may be compatible with Spring Framework while a driver remains incompatible with the SPI used by the framework or pool.

### 7.1. R2DBC SPI Is the Contract Between Components

The R2DBC SPI defines abstractions such as `ConnectionFactory`, `Connection`, `Statement`, `Result`, `Row`, and transaction-related operations. Drivers implement those abstractions for specific databases.

When the SPI changes:

- The driver must support the corresponding contract.
- The pool must be compatible with both the SPI and driver.
- The framework must target the matching SPI APIs.
- Behaviors around cancellation, metadata, result mapping, or connection lifecycle may differ.

Never force an arbitrary `r2dbc-spi` version just to “silence” a dependency conflict. Determine which version is supported by both the driver and framework, and align dependency management accordingly.

### 7.2. Drivers Have Their Own Matrices

Check at minimum:

- Does the driver version support the resolved R2DBC SPI version?
- Does the driver support the Java runtime in use?
- Which database server major versions does the driver support?
- Does the driver support production TLS/authentication modes?
- Has type mapping changed across versions?
- Have parameter binding, generated keys, or batch statements changed?
- Are there new cancellation/timeout behaviors or limitations?
- Are there known issues with pooling or transactions?

PostgreSQL, MySQL, and SQL Server use completely different drivers; never infer one driver's compatibility from another's.

### 7.3. Connection Pools

If using `r2dbc-pool`, verify:

- Pool version and SPI version.
- Connection validation and validation queries.
- `max-size`, `initial-size`, and acquire timeout.
- `max-idle-time`, `max-life-time`, and background eviction.
- Behavior when connections close or the database restarts.
- Connection disposal on cancellation/timeout.
- Graceful shutdown and leak detection if supported.

Do not test only that the application opens a connection. Test the pool under load, across database restarts, and as connections expire.

## 8. Cross-Checking Database Servers and Used Features

Driver support for a database server version does not mean all database features behave identically across major versions.

Check:

- Is the current database server still vendor-supported?
- Which server major versions does the target driver support?
- Which SQL syntax or data types does the application use?
- Which extensions/plugins are enabled?
- Have TLS/authentication policies changed?
- Have query plans or index behaviors changed noticeably?
- Are replication, failover, or cluster topologies supported?
- Do migrations use features specific to a particular server version?

Upgrading both the database server and the R2DBC driver simultaneously can overlap changes. When possible, separate the two upgrades to make diagnosing failures straightforward.

### 8.1. Type Mapping and Data

Pay close attention to UUID, JSON/JSONB, enum, array, numeric/decimal precision, timestamp with/without time zone, binary/LOB, null handling, and generated identity/sequence values.

A driver can change returned Java types or parameter binding rules. Custom converters may need adjustment even when repository methods still compile.

### 8.2. Queries and Dialects

Check derived queries, `@Query`, `DatabaseClient` SQL, `Criteria`, and custom repository implementations. A query that worked on an older database version may rely on behavior that changed in the newer version.

Read dialect-related release notes and inspect query plans for critical queries after driver/database upgrades.

## 9. Reading Release Notes Systematically

Do not search only for the word “breaking.” Read release notes in structured order:

1. **Overview:** release goals and scope.
2. **Requirements:** JDK, Spring Framework, SPI, or database baselines.
3. **Breaking changes:** removed APIs, contract changes, incompatible behaviors.
4. **Deprecations:** newly deprecated APIs and expected removal timelines.
5. **Behavior changes:** changes to defaults, mapping, transactions, pooling, or error handling.
6. **Dependency updates:** BOM, driver, Reactor, or transitive library versions.
7. **Bug fixes:** whether issues affecting your application are fixed.
8. **Security fixes:** CVEs, severity, and patches.
9. **Migration guide:** concrete upgrade steps and replacement configurations.
10. **Known issues:** documented bugs or workarounds.

### 9.1. Map Changes Directly to Your Codebase

From your application inventory, list the APIs and features actively used:

- `ReactiveCrudRepository`, `R2dbcEntityTemplate`.
- `DatabaseClient` and `bind`/`bindNull`.
- Mapping annotations and custom converters.
- Auditing.
- Reactive transaction manager and `TransactionalOperator`.
- Custom dialect/repository implementations.
- `ConnectionFactory`, pooling, and driver options.
- Spring Boot R2DBC auto-configuration.
- Migrations and database initialization.

Search for these terms in release notes, migration guides, and issue trackers for the target versions. Reading general summaries without mapping back to your codebase misses real impacts.

### 9.2. Classify Every Relevant Change

Record each item in a table:

| Classification | Meaning | Action |
|---|---|---|
| Breaking API | Source code may fail to compile | Update code per migration guide |
| Breaking behavior | Compiles but runtime behavior differs | Add regression tests |
| Deprecation | API still works but will be removed | Schedule replacement |
| Dependency baseline | Requires newer JDK/Framework/SPI | Adjust platform |
| Security fix | Fixes a vulnerability | Determine urgency and scope |
| Bug fix | Fixes an existing issue | Test the relevant case |
| Configuration change | Property/default changed | Update config and deployment |
| Operational change | Pool, metrics, logging, or lifecycle changed | Update ops/monitoring |

You do not always have to replace every deprecated API immediately if the migration guide does not require it, but track them to avoid surprises during the next major upgrade.

## 10. Checking Changes in Spring Data R2DBC

Several change categories warrant special attention in Spring Data release notes.

### 10.1. Repository APIs and Query Derivation

Check changes to `ReactiveCrudRepository` method signatures, query method parsing, `Pageable`/sorting support, `@Query` parameter binding, projection/DTO mapping, and custom repository fragments.

Test important methods for single-result, empty-result, and multi-result cases.

### 10.2. Mapping and Conversion

Check naming strategies, constructor/property access, `@Id` and generated values, embedded/value-object mapping, custom converters, enums, UUIDs, JSON and database-specific types, nullability, and primitive/wrapper handling.

A conversion change may appear only when specific data values are read or written; compile tests are not sufficient.

### 10.3. Reactive Transactions

Check `R2dbcTransactionManager`, `TransactionalOperator`, reactive `@Transactional` methods, rollback rules, cancellation behavior, isolation/propagation, and connection binding in Reactor Context.

If the release updates Spring Framework or the R2DBC SPI, re-verify transaction behavior even when Spring Data APIs appear unchanged.

### 10.4. DatabaseClient and Templates

Check `DatabaseClient` APIs, `R2dbcEntityTemplate`, mapping converters, and result handling. Changes in parameter binding or `Result` mapping can affect custom SQL.

Run integration tests against a real database for inserts/updates/deletes, generated IDs, batches, and queries involving specialized data types.

## 11. Dependency Management and Avoiding Version Conflicts

An application can declare one version while receiving another via BOMs, plugins, or transitive dependencies. During upgrades, keep the dependency graph consistent.

### 11.1. Avoid Arbitrarily Overriding Individual Spring Modules

Never pin `spring-data-r2dbc` to a different release train than `spring-data-relational` or the Spring Framework managed by Boot.

Let the Boot BOM manage Spring modules when using Boot. Override only with a clear justification, official support documentation, and thorough testing.

### 11.2. R2DBC Drivers and SPI

Drivers typically declare a dependency on `r2dbc-spi`. Pools may depend on the SPI too. If another library pulls in a different SPI version, dependency resolution may pick a version incompatible with another driver or module.

Use `dependencyInsight`/`dependency:tree` to trace which path pulled in which version. Never silence conflicts by excluding or forcing an artifact before understanding the dependency relationships.

### 11.3. Lockfiles and Reproducibility

If the project uses Gradle dependency locking or Maven dependency management, update lockfiles intentionally and review the diff. Local builds and CI must resolve the exact same dependency graph.

Never use dynamic versions like `latest.release` for production dependencies; resolved versions can shift between builds without any source code change.

## 12. Post-Compatibility Verification Test Matrix

Once the matrix shows the target stack is viable, verify it against the real application.

| Test Category | What to Verify |
|---|---|
| Build/runtime | JDK, plugins, packaging, and startup |
| Connection | Connection creation, authentication, TLS |
| Repository | CRUD, derived queries, empty results, multiple rows |
| Mapping | UUID, JSON, enum, array, decimal, timestamp, null |
| Custom SQL | Parameter binding, `bindNull`, generated values, batching |
| Transactions | Commit, rollback, isolation, propagation |
| Cancellation/timeout | Query cancel, timeouts, connection cleanup |
| Pool | Acquire, validation, max size, idle/lifetime, shutdown |
| Migration | Flyway/Liquibase and existing schema |
| Performance | Latency, throughput, pool saturation, query plans |
| Security | CVEs, TLS, credential sources, permissions |
| Deployment | Config, health checks, graceful shutdown, rollback |

### 12.1. Integration Tests on the Target Database

Use Testcontainers or an equivalent test environment running the exact target database engine and major version. H2 or mocked repositories cannot capture dialect, type-mapping, locking, and transaction differences.

If production runs PostgreSQL with specific extensions, enable those extensions in tests. If running MySQL or SQL Server, test with the exact intended driver and server version.

### 12.2. Regression Tests for Fixed Bugs

If release notes report fixes for bugs relevant to your application, write tests reproducing those scenarios—such as incorrect JSON/UUID mapping, faulty null binding, missing generated keys, leaked transaction connections, pools failing to recover after network resets, cancellation failing to release resources, or sorted/paged queries generating invalid SQL.

This proves the upgrade genuinely resolves the targeted issues.

## 13. Step-by-Step Upgrade Process

### Step 1: Lock Down Baseline

- Record Java, Boot, Framework, Data, Reactor, SPI, driver, pool, and database versions.
- Save the current dependency graph.
- Run the test suite and document any pre-existing failures.
- Document active R2DBC and migration configurations.

### Step 2: Select a Supported Target

- Pick the target Spring Boot release if using Boot.
- Review the Boot dependency appendix.
- Confirm the corresponding Spring Data release train.
- Check R2DBC SPI/driver/database compatibility.
- Verify JDK and build tool baselines.
- Check support lifecycles and security advisories.

### Step 3: Read All Release Notes

- Read every release between baseline and target.
- Record breaking changes, deprecations, behavior changes, and migration steps.
- Search for APIs/features used by your application.
- Flag items requiring code changes, config updates, or new tests.

### Step 4: Update Dependency Management

- Update the Boot plugin/BOM or Spring Data BOM to the target.
- Remove no-longer-needed version overrides.
- Update the driver/pool per the compatibility matrix.
- Update JDK and build wrappers if needed.
- Refresh lockfiles under review.

### Step 5: Compile and Address Migration Steps

- Compile to surface removed/changed APIs.
- Update code according to migration guides.
- Update changed configuration properties.
- Avoid mixing unrelated refactors into the same change so root causes remain clear.

### Step 6: Test Thoroughly

- Run unit tests.
- Run integration tests against the target database.
- Verify transactions, type mapping, pooling, and migrations.
- Run performance/regression tests for critical workloads.
- Inspect logs, metrics, and startup in a production-like environment.

### Step 7: Controlled Deployment

- Deploy to staging first.
- Watch error rates, latency, connection pools, and database load.
- Use canary or phased instance rollouts if supported.
- Keep application and schema rollback paths ready.
- Expand rollout only when metrics are stable.

## 14. Managing Database Schema Changes During Upgrades

Upgrading frameworks/drivers and changing schemas at the same time complicates rollbacks. When schema changes are needed, use an expand-migrate-contract strategy:

1. **Expand:** add new columns/tables/indexes compatibly with existing code.
2. **Migrate:** update the application to read/write the new structure, backfilling data if required.
3. **Verify:** confirm all instances use the new structure.
4. **Contract:** drop old columns/tables only when no running code version depends on them.

Do not ship destructive migrations alongside an upgrade if the application needs the option to roll back to the previous version. Database migrations usually do not roll back automatically when an old binary is redeployed.

### 14.1. Rollback Must Account for Both App and Schema

Your rollback plan should answer:

- Can the old binary run against the new schema?
- Does the migration contain destructive operations?
- Would rollback require restoring a backup or issuing a forward-fix?
- Does the new driver write data in a different format?
- Can old and new versions run side by side during rollout?
- Must compatibility be preserved throughout rolling deployment?

Safe rollbacks rely on backward-compatible schemas during rollout, not on assuming the database can always be downgraded.

## 15. Example Compatibility Matrix Checklist for an Upgrade

Before approving a target stack, fill out a decision table:

| Question | Required Evidence |
|---|---|
| Does target Boot support production JDK? | Proof from system requirements |
| Which Spring Framework/Data versions does Boot BOM manage? | Exact versions from dependency appendix |
| Is the Spring Data train compatible with target Framework? | Confirmed in compatibility matrix |
| Is R2DBC SPI compatible with driver and pool? | Confirmed in driver/pool docs |
| Does the driver support the current database server? | Explicit supported version range |
| Have all intermediate release notes been read? | List of notes and migration steps |
| Have deprecated/breaking APIs been addressed? | Code changes or documented risk acceptance |
| Is the dependency graph conflict-free? | Reviewed tree/insight output |
| Do integration tests pass on the target DB? | CI test results |
| Have transactions/pools/mappings been tested? | Corresponding test coverage |
| Is security support still active? | Lifecycle status / CVE review |
| Are app and schema rollbacks feasible? | Documented plan and assigned owner |

If any critical component remains *Unknown* or *Unsupported*, do not consider the stack verified. Gather evidence, adjust the target, or record formal risk acceptance per organizational process.

## 16. Common Mistakes

**Reading only the target version's release notes.** You can miss deprecations and migration changes introduced in intermediate versions. Read the full version span.

**Picking the latest version of every dependency independently.** Spring modules, Reactor, SPI, and drivers have coupled compatibility relationships. Select a BOM/matrix-supported combination.

**Checking only declared versions in build files.** Actual versions can be altered by BOMs or transitive dependencies. Inspect the resolved dependency graph.

**Forcing an R2DBC SPI version to hide conflicts.** Drivers or pools may break. Trace dependency paths and select a supported driver/SPI pairing.

**Overlooking Java and build tools.** Code may compile locally while CI/production runs a JDK below the new baseline. Check both build and runtime JDKs.

**Overlooking the database server version.** The target driver might not support your running server version. Verify vendor/driver support matrices.

**Running only unit tests.** Mocks do not exercise wire protocols, type mapping, transactions, or pooling. Run integration tests against the target database.

**Upgrading framework, driver, and database together.** Failures become hard to attribute. Separate changes whenever feasible.

**Skipping migration checks.** The new binary may start yet fail against production schemas. Test migrations from a production-like snapshot.

**Having no rollback plan.** Destructive schemas or new data formats can prevent running the old binary again. Use expand-migrate-contract.

## 17. Design Principles

- Determine resolved versions before choosing a target.
- Select Spring Boot, Spring Framework, and Spring Data combinations from BOMs/compatibility matrices.
- Read release notes and migration guides for all intermediate versions.
- Document JDK, Reactor, R2DBC SPI, driver, pool, database server, and build tool versions.
- Verify compatibility via official version-matched docs with verification dates.
- Distinguish *Supported* from *Verified* in the matrix.
- Never arbitrarily override Spring modules or R2DBC SPI.
- Verify type mapping, queries, transactions, cancellation, and pool behavior.
- Run integration tests on the exact target database engine/major version.
- Review security advisories and support lifecycles.
- Update BOMs/lockfiles consistently and re-verify the dependency graph after upgrading.
- Separate framework, driver, and database upgrades when possible.
- Use expand-migrate-contract to keep schemas rollback-safe.
- Deploy to staging/canary and monitor latency, errors, pools, and database load.
- Archive the compatibility matrix, doc references, and test results for future upgrades.

## 18. Key Takeaways

Before upgrading Spring Data R2DBC, determine actual resolved versions from the dependency graph, pick a target aligned with Spring Boot/Spring Data compatibility matrices, and verify R2DBC SPI, driver, pool, Java, and database server compatibility. Read release notes across every intermediate release for breaking changes, deprecations, behavior changes, security fixes, and migration steps.

A compatibility matrix is only valuable when every entry cites official sources and verification outcomes. After aligning BOMs and the dependency graph, test repositories, mapping, SQL, transactions, pooling, cancellation, migrations, and critical workloads against the target database. Finally, roll out incrementally with backward-compatible schemas and a clear rollback plan.
