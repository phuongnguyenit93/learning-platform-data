# Flyway, Liquibase, and Migration Resources by Supported Version

## 1. Why Database Migrations Require Separate Verification in Native Image

A Spring Boot application often needs to update the database schema before repositories, JPA `EntityManagerFactory`, or business services begin accessing data. Flyway, Liquibase, and Spring Boot's SQL initialization mechanism can all perform this work. On the JVM, migration tools typically scan scripts on the classpath, parse changelogs, load database drivers, and execute SQL when the application starts.

When compiling an application into a **GraalVM Native Image**, the classpath and resource set are determined at build time. Resource scanning, loading classes by name, Java migrations, or custom changes may not be fully recognized by static analysis. A migration might exist in the source tree yet fail to be packaged into the executable, or be packaged yet go undetected by the migration tool because resource scanning differs from the JVM.

Spring Boot supports Flyway and Liquibase integration in native applications, but compatibility depends on the Spring Boot version, migration tool version, database module/driver, and how resources are organized. This lesson focuses on choosing a tool, packaging migration resources, configuring hints, and testing on the native executable.

After this lesson, you will be able to:

- Configure Flyway or Liquibase via Spring Boot auto-configuration.
- Organize SQL migrations and changelogs on the classpath so Native Image retains the resources.
- Add `RuntimeHints` for migration directories or dynamically referenced files.
- Handle Flyway Java migration and resource scanning limitations across Spring Boot versions.
- Use `schema.sql`/`data.sql` when only simple initialization is needed.
- Verify migrations on the native executable, including files in subdirectories and included changelogs.

## 2. Principle of Choosing One Database Initialization Mechanism

Spring Boot supports several ways to create initial schemas and data:

| Mechanism | Suitable When | Typical Resources |
|---|---|---|
| Flyway | Managing schema changes with versioned migrations and execution history | `db/migration/V1__create_orders.sql` |
| Liquibase | Managing changeSets, preconditions, contexts/labels, and multi-format changelogs | `db/changelog/db.changelog-master.yaml` |
| Spring SQL initialization | Small apps, demos, simple initial schema/data | `schema.sql`, `data.sql`, `schema-${platform}.sql` |

Choose **one primary mechanism** to manage the schema. Spring Boot does not recommend using `schema.sql`/`data.sql` alongside Flyway or Liquibase; support for combining these basic initializers will be removed in the future. If you already use a migration tool, let that tool manage the entire schema and seed data.

Do not let `spring.jpa.hibernate.ddl-auto=create`, `update`, or `create-drop` compete with migrations in production. For applications using Flyway/Liquibase, typically set `ddl-auto=validate` or `none` depending on deployment needs.

## 3. Preparing Resources and Dependencies by Spring Boot Version

### 3.1. Spring Boot 3.x and 4.x Package Starters Differently

Artifact names and auto-configuration packages changed between major versions. Use Spring Boot's dependency management to select compatible versions; do not copy a Flyway/Liquibase or database driver version from an example targeting a different major version.

| Component | Spring Boot 3.x | Spring Boot 4.x |
|---|---|---|
| Flyway | Typically uses `org.flywaydb:flyway-core` with required database module | Provides `spring-boot-starter-flyway`; add matching database module |
| Liquibase | Uses `org.liquibase:liquibase-core` | Provides `spring-boot-starter-liquibase` |
| Flyway customizer package | `org.springframework.boot.autoconfigure.flyway` | `org.springframework.boot.flyway.autoconfigure` |
| Liquibase auto-configuration package | `org.springframework.boot.autoconfigure.liquibase` | `org.springframework.boot.liquibase.autoconfigure` |

Maven dependency example for Spring Boot 4.x with PostgreSQL:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-flyway</artifactId>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
</dependencies>
```

With Spring Boot 3.x, the baseline dependencies are typically:

```xml
<dependencies>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
</dependencies>
```

Liquibase example on Spring Boot 4.x:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-liquibase</artifactId>
</dependency>
```

On Spring Boot 3.x, use `org.liquibase:liquibase-core` and let Boot manage the version. If the project is on an older minor version, consult the documentation for that exact minor version to see which starters/artifacts are provided.

### 3.2. Keep the Version Managed by Spring Boot

Flyway's native support in Spring Boot integrates with `NativeImageResourceProvider` and certain Flyway scanner APIs. Therefore, overriding Flyway to a newer minor version than the BOM can break native auto-configuration even though the JVM application still runs. Spring Boot maintains native support for Flyway with the **default Boot-managed version**; if you override the version, you take responsibility for compatibility and may need to supply your own `ResourceProvider`.

The same rule applies to Liquibase and database drivers: inspect the dependency tree, use the compatible Boot-managed version first, and override only with a clear reason and after running native integration tests.

With Maven, inspect resolved versions:

```bash
./mvnw dependency:tree \
  -Dincludes=org.flywaydb,org.liquibase,org.postgresql
```

With Gradle:

```bash
./gradlew dependencyInsight \
  --dependency flyway-core \
  --configuration runtimeClasspath
```

Do not infer native compatibility solely from successful dependency resolution or passing JVM tests.

## 4. Flyway in Spring Boot Native Image

### 4.1. Organizing SQL Migrations on the Classpath

By default, Flyway searches for migrations at `classpath:db/migration`. Versioned migration filenames typically follow `V<VERSION>__<DESCRIPTION>.sql`:

```text
src/main/resources/
  db/
    migration/
      V1__create_orders.sql
      V2__add_order_status.sql
      R__refresh_order_summary.sql
```

Example `V1__create_orders.sql`:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    total_amount DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

Example `V2__add_order_status.sql`:

```sql
ALTER TABLE orders
    ADD COLUMN status VARCHAR(24) NOT NULL DEFAULT 'PENDING';
```

Migrations that have already run in shared environments should be treated as immutable. When schema changes are needed, create a new migration file instead of editing an old one; Flyway tracks history in the `flyway_schema_history` table.

### 4.2. Configuring Locations and Database

```yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_HOST:localhost}:5432/orders
    username: ${DB_USER:orders_app}
    password: ${DB_PASSWORD:change-me}
  flyway:
    enabled: true
    locations:
      - classpath:db/migration
    validate-on-migrate: true
  jpa:
    hibernate:
      ddl-auto: validate
```

If there are database-vendor-specific migrations, you can use the `{vendor}` placeholder:

```yaml
spring:
  flyway:
    locations: classpath:db/migration,classpath:db/migration/{vendor}
```

Or configure a migration directory outside the executable directly:

```yaml
spring:
  flyway:
    locations: classpath:db/migration,filesystem:/opt/orders/migrations
```

`classpath:` points to resources packaged inside the native image; `filesystem:` points to actual files on the filesystem at runtime. Files outside the image do not require resource hints, yet must be mounted/copied into the container with appropriate read permissions.

### 4.3. Resource Hints for Flyway

Spring Boot has mechanisms supporting Flyway classpath scanning in native mode. When using the default location, start with auto-configuration and the Boot-managed version. If migrations live in a custom location or the native executable reports missing resources, you can add explicit hints:

```java
package com.example.orders.config;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

class OrderMigrationRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("db/migration/**");
        hints.resources().registerPattern("db/migration-extra/**");
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(OrderMigrationRuntimeHints.class)
class OrderMigrationNativeConfiguration {
}
```

The `**` pattern covers files in subdirectories. Register relative to the classpath root—do not include `src/main/resources/` in the pattern. If using another location, register the pattern matching the exact resources accessed.

Note: a resource hint only ensures files are retained in the image. It does not fix a Flyway runtime scanner bug and does not guarantee every Flyway version is compatible with Boot's `NativeImageResourceProvider`. For nested multi-level migrations, use a Spring Boot version containing the subdirectory scanning fix and run tests to confirm each migration is actually discovered.

### 4.4. Limitations of Java-Based Migrations

Flyway supports SQL migrations and Java migrations. However, **automatic discovery of Java migrations is not fully supported in Spring Boot Native Image**. If a project requires Java migrations, register migration instances explicitly via `FlywayConfigurationCustomizer` instead of relying on classpath scanning.

Example for Spring Boot 4.x:

```java
package com.example.orders.config;

import org.springframework.boot.flyway.autoconfigure.FlywayConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import db.migration.V3__BackfillOrderStatus;

@Configuration(proxyBeanMethods = false)
class FlywayJavaMigrationConfiguration {

    @Bean
    FlywayConfigurationCustomizer registerJavaMigrations() {
        return configuration -> configuration.javaMigrations(
                new V3__BackfillOrderStatus());
    }
}
```

The migration class registered above must be present on the application classpath. Condensed example:

```java
package db.migration;

import java.sql.PreparedStatement;

import org.flywaydb.core.api.migration.BaseJavaMigration;
import org.flywaydb.core.api.migration.Context;

public class V3__BackfillOrderStatus extends BaseJavaMigration {

    @Override
    public void migrate(Context context) throws Exception {
        try (PreparedStatement statement = context.getConnection().prepareStatement(
                "UPDATE orders SET status = 'PENDING' WHERE status IS NULL")) {
            statement.execute();
        }
    }
}
```

Close only the `PreparedStatement`; do not close the connection provided by Flyway through `Context`.

On Spring Boot 3.x, import `FlywayConfigurationCustomizer` from `org.springframework.boot.autoconfigure.flyway`. Both examples assume `V3__BackfillOrderStatus` is on the application classpath and can be instantiated at build time.

Prefer SQL migrations whenever changes can be expressed in SQL. If a Java migration uses reflection, loads resources dynamically, or resolves classes by name, you still must verify the corresponding runtime hints. Registering the migration instance does not automatically supply every reflection/resource hint needed by code inside the migration.

### 4.5. Warnings and Build Flags You May Encounter

The Spring Boot Native Image wiki documents several version-specific behaviors:

- Flyway may log the warning `Unable to scan location: /db/migration (unsupported protocol: resource)` when using the native resource provider. This can be a warning from the JVM resource-scanning path not used in native; ignore it only after confirming migrations were discovered and applied by checking `flyway_schema_history` and the actual schema.
- Starting with Flyway 12.3, Flyway may construct an `https://` URL during startup. GraalVM does not enable all URL protocols by default; if the native build fails with `Accessing a URL protocol that was not enabled`, add `--enable-url-protocols=https` to build arguments.
- Some Spring Boot versions had bugs discovering migrations in subdirectories. Spring Boot 3.5.13 included a fix for `NativeImageResourceProvider`; check the release notes of your exact Boot branch before deploying.

Gradle Native Build Tools example when HTTPS must be enabled:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add('--enable-url-protocols=https')
        }
    }
}
```

With Maven Native Build Tools, pass the same option in `buildArgs` of `native-maven-plugin`:

```xml
<configuration>
    <buildArgs>
        <buildArg>--enable-url-protocols=https</buildArg>
    </buildArgs>
</configuration>
```

Add this option only when the dependency/version actually requires it or the build fails with a URL protocol error. Do not use this flag to mask a scanner bug or missing migration resources.

## 5. Liquibase in Spring Boot Native Image

### 5.1. Organizing Changelogs and Included Files

By default, Liquibase reads the master changelog at:

```text
classpath:db/changelog/db.changelog-master.yaml
```

Supported changelog formats include YAML, XML, JSON, and SQL. You can split changesets into separate files and include them from the master:

```text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      changes/
        001-create-orders.yaml
        002-add-order-status.yaml
      sql/
        seed-order-types.sql
```

Master changelog example:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-orders.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-order-status.yaml
      relativeToChangelogFile: true
```

A changelog can reference an SQL file via `sqlFile`:

```yaml
databaseChangeLog:
  - changeSet:
      id: seed-order-types
      author: orders-team
      changes:
        - sqlFile:
            path: ../sql/seed-order-types.sql
            relativeToChangelogFile: true
            splitStatements: true
```

`relativeToChangelogFile: true` resolves paths relative to the changelog containing the reference. Keep referenced files inside `src/main/resources` so they are packaged with the application.

### 5.2. Configuring Liquibase

```yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_HOST:localhost}:5432/orders
    username: ${DB_USER:orders_app}
    password: ${DB_PASSWORD:change-me}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    contexts: production
  jpa:
    hibernate:
      ddl-auto: validate
```

Spring Boot auto-configures `SpringLiquibase` when the Liquibase starter/dependency is present and uses the primary `DataSource` if no separate datasource is configured. The changelog runs when the context starts; to control `contexts`, `labels`, schema, or changelog path, configure `spring.liquibase.*`.

### 5.3. Ensuring All Changelog Resources Exist in the Native Image

Liquibase needs both the master changelog and every file referenced via `include`, `includeAll`, `sqlFile`, or other resources. Spring Boot includes baseline runtime hints for Liquibase, yet with custom changelog layouts you must inspect AOT-generated resource config and run native integration tests to verify nested files are found.

If included files are missing, you can add hints for the owning directory:

```java
package com.example.orders.config;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;
import com.example.orders.db.NormalizeOrderCodes;

class LiquibaseChangelogRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("db/changelog/**");
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(LiquibaseChangelogRuntimeHints.class)
class LiquibaseNativeConfiguration {
}
```

This pattern covers the master file, child changelogs, SQL files, and resources in subdirectories. If the project stores changelogs under a different root, adjust the pattern to match the exact classpath path. Do not register `**/*` across the entire application when only one migration directory needs to be retained.

### 5.4. Custom Changes and Classes Loaded by Name

Liquibase can use custom changes, custom preconditions, `includeAll` with resource filters/comparators, or extensions loaded by class name. These classes are not mere resources; they also need reachability/reflection metadata when instantiated dynamically.

Example custom change:

```java
package com.example.orders.db;

import liquibase.change.custom.CustomTaskChange;
import liquibase.database.Database;
import liquibase.exception.CustomChangeException;
import liquibase.exception.SetupException;
import liquibase.exception.ValidationErrors;
import liquibase.resource.ResourceAccessor;

public class NormalizeOrderCodes implements CustomTaskChange {

    @Override
    public void execute(Database database) throws CustomChangeException {
        // Perform data changes using the appropriate Liquibase/JDBC API.
    }

    @Override
    public void setUp() throws SetupException {
    }

    @Override
    public void setFileOpener(ResourceAccessor resourceAccessor) {
    }

    @Override
    public ValidationErrors validate(Database database) {
        return new ValidationErrors();
    }

    @Override
    public String getConfirmationMessage() {
        return "Order codes normalized";
    }
}
```

If a custom class is referenced by name in a changelog, register reflection hints for that class when the native build reports missing metadata:

```java
package com.example.orders.config;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

class LiquibaseCustomChangeRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                NormalizeOrderCodes.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(LiquibaseCustomChangeRuntimeHints.class)
class LiquibaseCustomChangeConfiguration {
}
```

Do not register reflection hints for every class in a package out of habit. Identify the exact classes dynamically loaded by Liquibase and which constructors and methods need to be invoked.

## 6. Spring Boot SQL Resources When Flyway/Liquibase Are Not Needed

### 6.1. `schema.sql` and `data.sql`

For small apps or demo/test databases, Spring Boot can run basic scripts:

```text
src/main/resources/
  db/
    schema.sql
    data.sql
```

Examples:

```sql
-- schema.sql
CREATE TABLE feature_flag (
    flag_key VARCHAR(100) PRIMARY KEY,
    enabled BOOLEAN NOT NULL
);
```

```sql
-- data.sql
INSERT INTO feature_flag(flag_key, enabled)
VALUES ('order-export', TRUE);
```

By default, Spring Boot initializes SQL scripts only for embedded databases. To run against other databases, set:

```yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:db/schema.sql
      data-locations: classpath:db/data.sql
```

To disable this mechanism, set `spring.sql.init.mode=never`. This mechanism does not maintain versioned migration history like Flyway or Liquibase; if schema evolution across releases must be managed, use a dedicated migration tool.

### 6.2. Resource Hints for Custom Scripts

If scripts are configured via dynamic paths or not recognized by Spring AOT, register resource hints:

```java
package com.example.orders.config;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

class SqlInitializationRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("db/schema.sql");
        hints.resources().registerPattern("db/data.sql");
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(SqlInitializationRuntimeHints.class)
class SqlInitializationNativeConfiguration {
}
```

Inspect generated resource metadata in AOT output before adding manual hints. For constant paths recognized by Spring Boot, the framework or GraalVM may already infer the required resources.

### 6.3. Platform-Specific Scripts

Spring Boot supports platform-qualified files:

```text
schema-postgresql.sql
data-postgresql.sql
schema-mysql.sql
data-mysql.sql
```

Configure `spring.sql.init.platform=postgresql` to select the corresponding scripts. These files remain classpath resources and must be present in the native image. If the application builds separate native artifacts per database, each artifact must package the right script set for that platform.

## 7. Choosing Classpath vs. Filesystem for Migrations

| Migration Placement | Packaged in Native Image? | When to Use | What to Verify |
|---|---|---|---|
| `classpath:db/migration` | Yes, if resources are included in the image | Migrations released alongside the application version | Resource hints, scanner, and files in subdirectories |
| `classpath:db/changelog/...` | Yes, if changelogs and all includes are in the image | Liquibase changelogs versioned with the application | Master, `include`, `includeAll`, `sqlFile`, custom changes |
| `filesystem:/opt/migrations` | No; files live outside the executable | Want to deploy migrations independently or mount from pipeline | Files exist in container, read permissions, and configured path |
| `schema.sql`/`data.sql` | Yes, if scripts are kept as classpath resources | Simple schema/data initialization | `spring.sql.init.mode`, platform, and resource hints |

Classpath resources produce an artifact whose migrations are tied to the exact application version. Filesystem resources allow changing migrations without rebuilding the native image, though the schema can then drift from code. Manage read/write permissions and migration versioning strictly.

## 8. Avoiding Running Multiple Migration Mechanisms Simultaneously

Do not let Flyway and Liquibase manage the same schema together, or let Hibernate `ddl-auto=update` compete with migrations. Having multiple tools alter table structures makes database history and state unpredictable.

A typical configuration:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
  liquibase:
    enabled: false
  sql:
    init:
      mode: never
```

If choosing Liquibase, flip `flyway.enabled` and `liquibase.enabled`. You do not need to declare both prefixes when the corresponding dependency is absent; the example above merely illustrates disabling the other mechanism.

Spring Boot recognizes Flyway/Liquibase as database initializers and orders database-dependent beans to run after initialization completes. For custom beans needing an already-migrated schema, you can use `@DependsOnDatabaseInitialization` if auto-detection misses that dependency.

## 9. Migrations in Native Applications: Run at Startup or as a Separate Job?

Spring Boot can run Flyway/Liquibase when the application context starts. This is simple for small applications or single-instance deployments. However, in multi-replica production environments, migrations require DDL privileges and can delay readiness times.

Two common deployment models:

| Model | How It Works | Advantages | What to Control |
|---|---|---|---|
| Migration at app startup | Native executable runs migrations before serving requests | Artifact ensures required schema exists before running code | DDL privileges, locks, startup/readiness, multiple replicas |
| Separate migration job | Run migrations in a job/init container or pipeline before app rollout | Separates migration privileges from runtime privileges; easier observability and release rollback | Job must complete before new app instances receive traffic |

Flyway uses schema history and locks to coordinate migrations; Liquibase uses `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK` tables. These mechanisms aid synchronization, yet do not replace release discipline and monitoring when multiple replicas start simultaneously.

A safe deployment pattern uses a dedicated migration database user with DDL permissions, while the runtime user has only the read/write data permissions needed. If a separate migration job already ran, configure the application not to rerun startup migrations or use an appropriate mechanism to verify the schema matches.

## 10. Testing Migrations on Native Image

### 10.1. Checks Before the Native Build

1. Run migrations on the JVM against the same database type/version as production.
2. Verify filenames, changelog paths, `include`, `includeAll`, and `sqlFile`.
3. Inspect the dependency tree to ensure Flyway/Liquibase and the JDBC driver are properly managed by Boot.
4. Run Spring AOT and verify resource hints already include required migrations/changelogs.
5. If using Java migrations or custom changes, confirm classes are explicitly registered and have needed reflection hints.

### 10.2. Running the Native Executable Against a Clean Database

Build the native executable/container image per your project workflow. Using a clean database, run the executable and verify:

- The application starts successfully.
- Flyway creates `flyway_schema_history` or Liquibase creates `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK`.
- All expected versioned migrations/changesets were applied.
- Tables, indexes, constraints, and seed data exist.
- Migration files in subdirectories and all included files were found.

### 10.3. Rerunning and Upgrading from an Older Schema

Do not test only the initial run. Rerun the native executable against the same database to confirm migrations are not reapplied twice. Then create a database at an older schema version, run the new executable, and confirm upgrade migrations execute in order.

For Flyway, inspect `flyway_schema_history` and `validate` results. For Liquibase, inspect `DATABASECHANGELOG` and changeset checksums. If using SQL init, confirm existing data/schema handling and fail-fast behavior on script errors.

### 10.4. Testing Resources and Custom Configuration

At minimum, cover these cases:

- Default migrations in the root directory.
- Migrations in one or more subdirectories.
- Changelogs including other SQL/YAML/XML files.
- Custom locations or `{vendor}`.
- Migrations configured via filesystem path if used.
- Database driver matching the target native platform.
- Failed migrations causing the application/job to return a clear failure status.

A passing native build does not prove migration resources were found. Only a native integration test run against a real database or equivalent database environment verifies the migration path.

## 11. Common Errors and How to Resolve Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Flyway reports no migrations found in native | Resources unpackaged or scanner cannot find resources | Check `spring.flyway.locations`, resource metadata, Boot-managed Flyway version, and `flyway_schema_history` |
| Flyway logs `unsupported protocol: resource` | Warning from JVM resource-scanning path when native uses its own provider | Ignore only after confirming migrations were discovered and applied; check logs and history table |
| Flyway misses files in subdirectories | Spring Boot version lacks recursive resource discovery fix or provider flattens paths | Use a Boot version with the fix (Boot 3.5.13+ for 3.5 line) and test subdirectories on native |
| `NoSuchMethodError` in `NativeImageResourceProviderCustomizer` | Flyway overridden to a version incompatible with Boot | Revert to Boot BOM-managed version or supply a compatible `ResourceProvider` via `FlywayConfigurationCustomizer` |
| Flyway does not auto-detect Java migrations | Automatic detection unsupported in native | Register instances via `FlywayConfigurationCustomizer` and check reflection hints inside the migration |
| Native build reports `https` URL protocol not enabled | Flyway 12.3+ constructs HTTPS URLs at startup, GraalVM protocol disabled | Add `--enable-url-protocols=https` if this exact error occurs |
| Liquibase finds master but misses included files | Child changelogs/SQL files not retained in image or wrong include path | Register `db/changelog/**`, check `relativeToChangelogFile` and generated resource metadata |
| Liquibase fails to instantiate custom change | Class referenced by name lacks reflection/constructor metadata | Register required class and members via `RuntimeHintsRegistrar` |
| SQL init runs on JVM but not on native | Scripts missing from image or `spring.sql.init.mode` is `embedded` | Set `mode=always` if needed; check resource hints and native logs |
| Migrations run before database is ready | Database connection not yet ready or deployment lacks dependency ordering | Check readiness/connection retries and schedule migration job before app rollout |
| Two tools modify the schema together | Flyway, Liquibase, SQL init, or Hibernate DDL enabled simultaneously | Choose only one schema initialization mechanism; set `ddl-auto=validate`/`none` |
| Native app fails at startup due to DB permissions | Runtime user lacks DDL permissions or migration job has not run | Use a dedicated migration user/job or grant controlled permissions |

## 12. Hands-On Exercise: Packaging Flyway and Liquibase Resources

**Context:** `order-service` uses PostgreSQL and must create an `orders` table, then add a `status` column. You will try two variants: Flyway SQL migrations and a Liquibase changelog.

### Option A — Flyway

1. Add the Flyway starter/module matching your Spring Boot version and the PostgreSQL driver module.
2. Create `V1__create_orders.sql` and `V2__add_order_status.sql` under `src/main/resources/db/migration`.
3. Configure `spring.flyway.locations=classpath:db/migration`.
4. Keep the Flyway version managed by the Spring Boot BOM.
5. If using migrations in subdirectories, verify your Spring Boot patch includes the recursive resource fix.
6. Build native, run against a clean PostgreSQL database, and inspect `flyway_schema_history`.

### Option B — Liquibase

1. Add the Liquibase starter/dependency per your Spring Boot version.
2. Create `db.changelog-master.yaml` and included files under `db/changelog`.
3. Configure `spring.liquibase.change-log=classpath:db/changelog/db.changelog-master.yaml`.
4. Check Boot hints; add `db/changelog/**` if child changelogs are not retained.
5. Build native, run against a clean PostgreSQL database, and inspect `DATABASECHANGELOG`.

### Option C — Simple SQL Initialization

1. Create `db/schema.sql` and `db/data.sql` on the classpath.
2. Set `spring.sql.init.mode=always` if using a non-embedded database.
3. Inspect resource metadata for both files.
4. Run the native executable and verify schema/data creation.

### Result Sheet

| Item | Result to Record |
|---|---|
| Spring Boot version | _(record)_ |
| Migration tool/version | Flyway / Liquibase / SQL init |
| Database and driver version | _(record)_ |
| Classpath locations | _(record)_ |
| Resource hints | _(record pattern)_ |
| Migrations in subdirectories | PASS/FAIL |
| Changelog include/sqlFile | PASS/FAIL |
| Native build | PASS/FAIL |
| Migration on clean DB | PASS/FAIL |
| Rerun without duplicate application | PASS/FAIL |
| Upgrade from older schema | PASS/FAIL |

## 13. Key Takeaways

Flyway, Liquibase, and SQL initialization can all work in Spring Boot Native Image when the tool, version, driver, and migration resources are compatible. Use Boot-managed versions, keep migration files on the classpath when packaging inside the executable, and add resource/reflection hints for dynamically accessed files or classes not inferred by AOT.

Flyway SQL migrations are typically the simplest option for native. Java migrations must be registered explicitly via `FlywayConfigurationCustomizer`; Flyway native integration depends tightly on the Boot-managed Flyway version. Liquibase requires ensuring all included changelogs and SQL resources—not only the master changelog—exist in the image. For simple scripts, Spring SQL initialization is lighter, though it does not replace versioned migration history. Only a single mechanism should own creating and updating the schema.

### Official Documentation

- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot — GraalVM Native Image Compatibility Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-with-GraalVM)
- [Spring Boot — FlywayConfigurationCustomizer API (4.x)](https://docs.spring.io/spring-boot/4.2/api/java/org/springframework/boot/flyway/autoconfigure/FlywayConfigurationCustomizer.html)
- [Spring Boot — LiquibaseAutoConfiguration API (4.x)](https://docs.spring.io/spring-boot/4.2/api/java/org/springframework/boot/liquibase/autoconfigure/LiquibaseAutoConfiguration.html)
- [Redgate Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations)
- [Redgate Flyway — Java-based Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/java-based-migrations)
- [Spring Boot issue — Flyway Java migrations and Native Image](https://github.com/spring-projects/spring-boot/issues/33458)
- [Spring Boot issue — Flyway NativeImageResourceProvider and subdirectories](https://github.com/spring-projects/spring-boot/issues/49661)
- [Spring Boot issue — Flyway version compatibility with Native Image](https://github.com/spring-projects/spring-boot/issues/47368)
- [Spring Boot issue — Liquibase changelog resource hints](https://github.com/spring-projects/spring-boot/issues/34678)
- [Liquibase — CustomTaskChange API](https://javadocs.liquibase.com/liquibase-core/liquibase/change/custom/CustomTaskChange.html)
