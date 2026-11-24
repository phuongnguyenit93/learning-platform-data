# Flyway, Liquibase, and Schema Upgrade Verification in Spring Boot Testing

## Learning Objectives

A Spring Boot system may run fine on a **brand-new** database yet fail when deployed against a database **already containing real data**. The reason is that creating tables in their final state is not equivalent to **upgrading a schema from an older version to a newer version**. Migrations must protect **structure**, **existing data**, **constraints**, **version history**, and **repeatable deployment**.

Two tools commonly used in Spring Boot are:

- **Flyway:** manages versioned migrations, typically via SQL files `V1__...sql`, `V2__...sql`, tracked in the `flyway_schema_history` table.
- **Liquibase:** manages **changesets** using XML/YAML/JSON/formatted SQL, tracked in `DATABASECHANGELOG` with a `DATABASECHANGELOGLOCK` locking mechanism.

This lesson belongs to the **Spring Boot – testing** module, **Test Data** branch, covering **Flyway, Liquibase, and schema upgrade verification**. The focus is not merely configuring migrations to run, but writing tests that detect regressions when transitioning from an old schema to a new one.

After this lesson, you will be able to:

1. Distinguish schema migrations, Hibernate schema generation, and test SQL fixtures.
2. Configure Flyway/Liquibase in the proper Spring Boot lifecycle, avoiding two tools managing the same schema concurrently.
3. Write ordered migrations: **create V1 table → add V2 column → backfill data → apply NOT NULL/default constraints**.
4. Write tests that genuinely build **V1**, insert V1-shaped data, and then run **V2 on that same database**.
5. Verify legacy data remains readable, new columns hold expected values, constraints take effect, and history records all migrations.
6. Confirm **tool-level idempotency**: re-running `migrate`/`update` does not re-apply already-succeeded migrations.
7. Verify migrations run automatically before the application uses JDBC beans on Spring Boot startup.
8. Use isolated databases/schemas and Testcontainers when migrations contain PostgreSQL/MySQL-specific syntax.
9. Evaluate checksum drift, mid-migration failures, transactional DDL, rollbacks, expand–contract, and safe CI/CD strategies.
10. Run a demonstration project using **Java 17, Spring Boot 3.3.5, Gradle, JUnit Jupiter, H2, Flyway, and Liquibase**.

**Principle:** A migration test **does not merely ask “does the new schema have the column?”**. It must ask: “does a database upgraded from an older version preserve data, transform it properly, and satisfy the new version's contract?”

## 1. A Brand-New Schema and an Upgraded Schema Are Two Different Problems

Suppose release V1 has this table:

~~~sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(120) NOT NULL
);
~~~

Release V2 requires adding `status` and ensuring existing accounts receive the `ACTIVE` status.

If you only create the final schema:

~~~sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(120) NOT NULL,
    status VARCHAR(16) DEFAULT 'ACTIVE' NOT NULL
);
~~~

then you **have not verified** critical questions:

- When a V1 database has existing rows, does the upgrade preserve IDs and emails?
- Is legacy data backfilled to `ACTIVE` before enforcing `NOT NULL`?
- If the constraint were added before the backfill, would the migration fail on a populated table?
- Was the migration marked successful in schema history?
- When the application restarts, does the tool avoid re-running failing ALTER/INSERT statements?
- Are we targeting the right DB engine and migration locations?
- Was an older migration edited, causing checksum drift?
- Does DDL transaction behavior differ across PostgreSQL, MySQL, and H2?

A **true** upgrade test must start from **V1** with data, execute the V2 steps, and then verify the **post-upgrade state**.

### From Baseline to New Version

~~~text
Empty database (test-only, isolated)
           |
           v
Apply V1 -> customer_accounts(id, email)
           |
           v
Insert legacy account: (101, "old@example.test")
           |
           v
Apply V2 -> add status
           |    backfill status = ACTIVE
           |    set NOT NULL and DEFAULT
           v
Read account ID=101
  - email unchanged
  - status = ACTIVE
  - NOT NULL constraint active
  - migration history has only V1, V2
           |
           v
Run migrate/update again
  - V1/V2 not re-applied
  - data neither duplicated nor deleted
~~~

**Terminology note:** “Safe repeatable migration” here means the tool inspects history and **does not re-run succeeded changesets/versions**, not that every individual SQL migration statement is idempotent if you execute it manually in a loop.

## 2. How Do Flyway and Liquibase Differ?

| Criterion | Flyway | Liquibase |
| --- | --- | --- |
| Primary unit | Versioned/repeatable migration | Changeset inside a changelog |
| Common files | `V1__create.sql`, `V2__alter.sql`, `R__refresh.sql` | XML, YAML, JSON, formatted SQL |
| Ordering | By version; repeatables by checksum and dependencies | By changelog/include order, with conditions |
| History table | `flyway_schema_history` | `DATABASECHANGELOG` |
| Concurrency locking | Engine/mechanism-dependent migration locking | `DATABASECHANGELOGLOCK` |
| Drift detection | `validate()`/checksum, info status | Changeset checksum/validation |
| Upgrading V1 → V2 in tests | `Flyway.configure().target("1")`, then latest | Run V1-only changelog then master V1+V2 |
| Environment selection | Locations, placeholders, configuration | Contexts, labels, preconditions |
| Rollback | Usually **forward-fix**; undo depends on edition/version | Can declare rollbacks per changeset, though not every data change is automatically reversible |
| Risks | Editing deployed versioned migrations, wrong SQL dialect | Changing changeset identity/checksum, misapplied context/label, moving changelog paths |
| Tool choice | Teams preferring direct SQL and explicit versioned files | Teams preferring a changeset model, multi-format support, contexts/labels/rollback definitions |

**Never unintentionally enable both Flyway and Liquibase to migrate the same schema.** Pick one tool as the source of truth for the primary database. If an organization genuinely operates both, separate schema/datasource ownership, ordering, and responsibilities explicitly and verify them in CI. The project below includes both **for learning and comparison**, while separating databases and **disabling Liquibase auto-migration** in the Flyway Spring Boot startup test.

## 3. When Does Spring Boot Run Migrations?

With the right dependencies and config, Spring Boot triggers migrations **during ApplicationContext startup**, before beans declaring dependence on database initialization are used. A `Flyway` or `SpringLiquibase` bean may be created. Still, verify actual behavior, since custom wiring, profiles, or bean ordering can alter startup flow.

### Flyway

In Spring Boot 3.3, the core dependency is:

~~~groovy
implementation 'org.flywaydb:flyway-core'
~~~

By default, Flyway searches for versioned SQL under `classpath:db/migration`. Example filenames:

~~~text
V1__create_customer_accounts.sql
V2__add_status_and_backfill.sql
R__refresh_reporting_view.sql
~~~

- `V1`, `V2` define the version.
- Two underscores `__` separate version from description.
- `R__...` files are **repeatable migrations**; use them only when you understand when checksums change and how ordering works.
- `spring.flyway.locations` controls where migrations are discovered.
- `spring.flyway.enabled=false` disables automatic context integration when orchestrating migrations manually in a special test.
- Some database engines in Flyway 10 require dedicated modules, such as `org.flywaydb:flyway-database-postgresql` for PostgreSQL.
- Do not confuse the Flyway Java API with the **Flyway Gradle plugin**: calling Flyway from Java tests does not require adding the `org.flywaydb.flyway` plugin to `build.gradle`.

### Liquibase

In Spring Boot 3.3 you can add:

~~~groovy
implementation 'org.liquibase:liquibase-core'
~~~

By default Boot looks for the master changelog at `db/changelog/db.changelog-master.yaml`, or specify:

~~~properties
spring.liquibase.change-log=classpath:db/changelog/db.changelog-master.xml
spring.liquibase.enabled=true
~~~

Liquibase tracks unapplied changesets by an identity composed of **id, author, and filename/logical file path**, along with checksums. Important properties:

- `spring.liquibase.enabled=false`: disables Liquibase auto-update in the Spring Boot context.
- `spring.liquibase.contexts`: selects changesets for specific environments.
- `spring.liquibase.labels`: filters changesets by labels.
- `spring.liquibase.change-log`: path to the master file.
- For multi-DataSource setups, Boot supports `@LiquibaseDataSource` or `spring.liquibase.url/user/password` as appropriate.

**Version warning:** API/config semantics in this lesson target **Spring Boot 3.3.5**. Boot 4 or newer Flyway/Liquibase major versions may change module names, defaults, and runtime requirements; never copy dependencies from a newer blog post into an older project without checking the BOM and Javadoc.

## 4. What Should a Good Migration Test Verify?

At minimum, check all six layers:

1. **V1 initialization:** the old schema has the expected tables/columns; V2's new column does not exist yet.
2. **Historical data seeding:** insert one or more records matching the V1 contract.
3. **Upgrade:** apply V2 using the real tool, without manually executing V2 SQL in test code on the engine's behalf.
4. **Data preservation:** legacy IDs, emails, and existing fields are neither lost nor altered outside spec.
5. **New schema:** `status` is backfilled; `NOT NULL`, defaults, and indexes take effect.
6. **History/idempotency:** the tool records all migrations and does not re-apply them on restart.

For production schemas, also verify:

- Are foreign keys, check constraints, and indexes actually enforced?
- Do timestamps, timezones, and decimal precisions behave properly?
- Does the backfill handle null, blank, or quirky legacy rows?
- Do queries from the **older** application version still work during a rolling deployment?
- Does a zero-downtime rollout avoid long table locks or massive table rewrites?
- Can data migrations support batching, retries, and restarts?
- Do different users or tenants have edge-case data shapes?
- Have rollback/restore paths and backups been rehearsed?

**Never equate “the schema has the column” with “the data upgrade succeeded.”** A bare `ALTER TABLE ADD COLUMN` can leave `status` all null; a metadata-only test passes while V2 application code requires `status` to be non-null.

## 5. Why Not Use Hibernate `ddl-auto=create-drop` to Test Migrations?

Spring Data JPA/Hibernate can generate schemas from entity mappings. For example:

~~~properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

This works for isolated JPA demos, **but it does not test Flyway/Liquibase SQL**. It builds tables in **the current entity state**, skipping the `V1 → V2` version history. If V2's migration is broken or forgets to backfill, tests still pass because Hibernate created the final schema directly.

When migrations are the source of truth:

- Use **Flyway/Liquibase** to manage DDL.
- With JPA, set `spring.jpa.hibernate.ddl-auto=validate` or `none` as appropriate.
- Do not let `schema.sql`/`data.sql` accidentally recreate tables in parallel.
- Validate entity mappings against the migrated schema rather than letting entities silently update the schema in place of migrations.
- Run real migrations on a database seeded with V1 data to test the upgrade path.

**`ddl-auto=validate` only checks that mappings match the visible schema**; it does not verify backfills, history, legacy data preservation, or rollback strategies.

## 6. Runnable Java 17 / Spring Boot 3.3.5 Project

The project below intentionally uses **in-memory H2 and JDBC** to focus on migrations. No Docker or external database is needed. Each upgrade test creates an isolated H2 instance to avoid state collisions. One test uses Spring Boot auto-configuration to confirm Flyway migrates automatically on context startup.

### 6.1. File Listing

~~~text
schema-upgrade-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/com/example/migration/
    │   │   └── SchemaUpgradeApplication.java
    │   └── resources/db/migration/flyway/
    │       ├── V1__create_customer_accounts.sql
    │       └── V2__add_status_and_backfill.sql
    └── test/
        ├── java/com/example/migration/
        │   ├── FlywayUpgradeTest.java
        │   ├── LiquibaseUpgradeTest.java
        │   └── BootFlywayStartupTest.java
        └── resources/db/changelog/accounts/
            ├── 001-create.xml
            ├── 002-upgrade.xml
            ├── only-v1.xml
            └── master.xml
~~~

**Liquibase XML files live under `src/test/resources`**, serving purely as tool-verification examples rather than an automatic production migration chain in this lab. The Flyway SQL files under `src/main/resources` form the default chain used by the Spring Boot startup test via `spring.flyway.locations`.

Gradle Wrapper files are generated by Gradle; the source text below omits binary JAR contents.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'schema-upgrade-lab'
~~~

### 6.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.flywaydb:flyway-core'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.liquibase:liquibase-core'

    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Why this configuration?**

- `spring-boot-starter-jdbc`: provides `JdbcTemplate`, `DataSource`, `DriverManagerDataSource`, Hikari, and transaction infrastructure.
- `flyway-core`: provides the Flyway Java API and Boot Flyway auto-configuration.
- `liquibase-core`: provides the Liquibase Java API inside **test code**.
- `spring-boot-starter-test`: JUnit Jupiter, Spring TestContext, and assertions.
- H2 in `testRuntimeOnly`: embedded engine used only in tests.
- Never let Flyway and Liquibase migrate the same `DataSource`. The Boot smoke test sets `spring.liquibase.enabled=false` so having Liquibase on the test classpath does not trigger auto-migration.
- `useJUnitPlatform()` tells Gradle to run JUnit 5.

In practice, most production services include only **one migration tool** on the runtime classpath. This project adds Liquibase as a test dependency to compare testing patterns across both tools.

### 6.4. `SchemaUpgradeApplication.java`

**`src/main/java/com/example/migration/SchemaUpgradeApplication.java`**

~~~java
package com.example.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SchemaUpgradeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SchemaUpgradeApplication.class, args);
    }
}
~~~

The project defines no production/default JDBC URL; the runnable target is **Gradle test**, where each test provisions an isolated test database. Do not run `bootRun` in an environment lacking a `DataSource` just because a `main` class is present.

## 7. Flyway SQL Migrations: V1 and V2

**`src/main/resources/db/migration/flyway/V1__create_customer_accounts.sql`**

~~~sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(120) NOT NULL
);
~~~

V1 omits `status`. This lets the test genuinely observe the “pre-upgrade schema.”

**`src/main/resources/db/migration/flyway/V2__add_status_and_backfill.sql`**

~~~sql
ALTER TABLE customer_accounts
    ADD COLUMN status VARCHAR(16);

UPDATE customer_accounts
SET status = 'ACTIVE'
WHERE status IS NULL;

ALTER TABLE customer_accounts
    ALTER COLUMN status SET NOT NULL;

ALTER TABLE customer_accounts
    ALTER COLUMN status SET DEFAULT 'ACTIVE';

CREATE INDEX idx_customer_accounts_status
    ON customer_accounts(status);
~~~

Step-by-step explanation:

1. **Add a nullable column** so an existing populated V1 database does not fail immediately.
2. **Backfill** existing rows: every null `status` is set to `'ACTIVE'`.
3. **Enforce `NOT NULL`** once all rows satisfy the constraint.
4. **Set `DEFAULT`** so demo INSERTs omitting `status` still receive `'ACTIVE'`.
5. **Create an index** supporting common queries filtered by status.

In the H2 demo, these SQL statements are compatible. On production PostgreSQL/MySQL, syntax, locking, and transaction semantics for `ALTER`/`DEFAULT`/`INDEX` may differ; **test against the exact production engine and version**.

### Why Not Enforce NOT NULL Right Away?

If the table holds legacy rows, adding a non-null column without a default can fail because existing rows have no valid value. Splitting into **expand → backfill → contract** reduces risk. In this demo, those steps sit together in V2 for clarity; during rolling deployments with multiple live app versions, split them across **multiple deployments/migrations** so both V1 and V2 code remain compatible through the transition.

### What Does “Never Edit Released Migrations” Mean?

Once V1 has run against a real DB, **never edit V1's contents** to tweak the schema. Instead, create a new V3/V4 migration for further changes. Flyway stores checksums of versioned migrations; editing an applied file triggers checksum drift in `validate`, which is a signal to investigate rather than something to hide with `repair` casually.

## 8. JUnit: Testing Flyway Upgrade from V1 to V2

**`src/test/java/com/example/migration/FlywayUpgradeTest.java`**

~~~java
package com.example.migration;

import java.util.UUID;

import javax.sql.DataSource;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.dao.DataIntegrityViolationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FlywayUpgradeTest {

    private static final String LOCATION =
            "classpath:db/migration/flyway";

    private DataSource newDatabase() {
        String name = "flyway_" +
                UUID.randomUUID().toString().replace("-", "");

        return new DriverManagerDataSource(
                "jdbc:h2:mem:" + name + ";DB_CLOSE_DELAY=-1",
                "sa",
                "");
    }

    private Flyway flyway(DataSource source) {
        return Flyway.configure()
                .dataSource(source)
                .locations(LOCATION)
                .load();
    }

    @Test
    void upgradesOldDataFromV1ToV2() {
        DataSource source = newDatabase();
        JdbcTemplate jdbc = new JdbcTemplate(source);

        // Step 1: Run migrations only up to V1.
        Flyway first = Flyway.configure()
                .dataSource(source)
                .locations(LOCATION)
                .target("1")
                .load();

        first.migrate();

        assertEquals("1",
                first.info().current().getVersion().getVersion());

        // V1 does not have STATUS yet.
        Integer statusColumns = jdbc.queryForObject(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS " +
                "WHERE TABLE_NAME = ? AND COLUMN_NAME = ?",
                Integer.class, "CUSTOMER_ACCOUNTS", "STATUS");

        assertEquals(0, statusColumns);

        // Step 2: Insert data under the V1 schema.
        jdbc.update(
                "INSERT INTO customer_accounts(id, email) " +
                "VALUES (?, ?)",
                101L, "old@example.test");

        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer_accounts",
                Integer.class));

        // Step 3: Upgrade the existing DB to latest (V2).
        Flyway latest = flyway(source);
        latest.migrate();
        latest.validate();

        assertEquals("2",
                latest.info().current().getVersion().getVersion());

        // Step 4: Legacy account preserved, status backfilled.
        String email = jdbc.queryForObject(
                "SELECT email FROM customer_accounts WHERE id = ?",
                String.class, 101L);
        String status = jdbc.queryForObject(
                "SELECT status FROM customer_accounts WHERE id = ?",
                String.class, 101L);

        assertEquals("old@example.test", email);
        assertEquals("ACTIVE", status);

        // Step 5: NOT NULL constraint is active.
        assertThrows(DataIntegrityViolationException.class, () ->
                jdbc.update(
                    "INSERT INTO customer_accounts(id, email, status) " +
                    "VALUES (?, ?, NULL)",
                    102L, "null@example.test"));

        // Step 6: Database history has V1 and V2 succeeded.
        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM flyway_schema_history " +
                "WHERE success = TRUE",
                Integer.class));

        // Step 7: Re-running applies no further migrations.
        assertEquals(0, latest.migrate().migrationsExecuted);
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer_accounts",
                Integer.class));
    }

    @Test
    void freshDatabaseGetsLatestSchemaOnce() {
        DataSource source = newDatabase();
        JdbcTemplate jdbc = new JdbcTemplate(source);
        Flyway tool = flyway(source);

        assertEquals(2, tool.migrate().migrationsExecuted);
        assertEquals(0, tool.migrate().migrationsExecuted);

        // DEFAULT applies to rows inserted after migration.
        jdbc.update(
                "INSERT INTO customer_accounts(id, email) " +
                "VALUES (?, ?)",
                201L, "new@example.test");

        assertEquals("ACTIVE", jdbc.queryForObject(
                "SELECT status FROM customer_accounts WHERE id = ?",
                String.class, 201L));

        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM flyway_schema_history " +
                "WHERE success = TRUE",
                Integer.class));

        assertTrue(tool.info().current().getVersion()
                .getVersion().equals("2"));
    }
}
~~~

### Reading the Key Assertions

| Check | Evidence |
| --- | --- |
| `first.info().current() == 1` | Only migrations up to V1 were applied |
| `INFORMATION_SCHEMA.COLUMNS` query returns 0 | V1 lacks `STATUS`, so the test distinguishes “before/after” |
| Insert ID 101 before V2 | Migration upgrades **existing data**, not just an empty DB |
| `latest.info().current() == 2` | Database reached V2 |
| Email unchanged | Preserves critical business data |
| Status = ACTIVE | Backfill succeeded |
| INSERT with NULL status rejected | `NOT NULL` constraint enforced |
| History has two successful rows | Flyway history matches expectations |
| `migrationsExecuted == 0` on second run | Does not re-apply V1/V2 |
| Fresh database receives default ACTIVE | V2 also works when starting from an empty DB |

**Why use `DriverManagerDataSource`?** It opens connections directly from a JDBC URL without pooling, which is enough for small tests. Each JUnit method creates a randomly named H2 database `flyway_<UUID>` so methods never share state. H2's `DB_CLOSE_DELAY=-1` keeps the in-memory database alive in the JVM after individual connections close, enabling multiple statements using separate connections. This is a **temporary, test-only database**, not a production config.

**Why not wrap the migration test in `@Transactional`?** Flyway manages its own migration and history transactions. Opening an enclosing JUnit transaction around DDL or expecting rollback of V2 at method end behaves differently across database engines. Spinning up a fresh database per test is far clearer to observe.

**Limitation:** Passing H2 tests does not guarantee your V2 SQL runs on PostgreSQL/MySQL; Section 17 covers Testcontainers for that requirement.

## 9. Liquibase: Defining Schemas with Changesets

For a fair comparison, Liquibase uses the **exact same business contract**: V1 has `id`/`email`; V2 adds `status`, backfills `'ACTIVE'`, and enforces `NOT NULL`/default.

Rather than creating one master file with two changesets and running everything at once, the lab uses **two entrypoints**:

- `only-v1.xml` includes only the V1 changeset to build the starting state.
- `master.xml` includes both V1 and V2 to execute the real upgrade.

Both entrypoints include **the same physical V1 file** using a consistent path. This matters: Liquibase identifies a changeset by **id + author + filename/logicalFilePath**; changing the filename between V1 and master makes Liquibase treat it as a different changeset and try to recreate the table.

### 9.1. `001-create.xml`

**`src/test/resources/db/changelog/accounts/001-create.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.20.xsd">

    <changeSet id="001-create-accounts" author="training">
        <createTable tableName="customer_accounts">
            <column name="id" type="BIGINT">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="email" type="VARCHAR(120)">
                <constraints nullable="false"/>
            </column>
        </createTable>
    </changeSet>
</databaseChangeLog>
~~~

### 9.2. `002-upgrade.xml`

**`src/test/resources/db/changelog/accounts/002-upgrade.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.20.xsd">

    <changeSet id="002-add-status-and-backfill"
               author="training">
        <addColumn tableName="customer_accounts">
            <column name="status" type="VARCHAR(16)"/>
        </addColumn>

        <update tableName="customer_accounts">
            <column name="status" value="ACTIVE"/>
            <where>status IS NULL</where>
        </update>

        <addNotNullConstraint
            tableName="customer_accounts"
            columnName="status"
            columnDataType="VARCHAR(16)"/>

        <addDefaultValue
            tableName="customer_accounts"
            columnName="status"
            columnDataType="VARCHAR(16)"
            defaultValue="ACTIVE"/>

        <createIndex
            indexName="idx_customer_accounts_status"
            tableName="customer_accounts">
            <column name="status"/>
        </createIndex>
    </changeSet>
</databaseChangeLog>
~~~

Liquibase supports most DDL via engine-independent change types, reducing direct SQL syntax coupling. Still, **how a change type behaves still depends on the database engine**; a changeset passing on H2 does not prove identical semantics or locking on PostgreSQL/MySQL.

### 9.3. V1-Only Entrypoint

**`src/test/resources/db/changelog/accounts/only-v1.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.20.xsd">

    <include file="001-create.xml"
             relativeToChangelogFile="true"/>
</databaseChangeLog>
~~~

### 9.4. Full V1 and V2 Entrypoint

**`src/test/resources/db/changelog/accounts/master.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.20.xsd">

    <include file="001-create.xml"
             relativeToChangelogFile="true"/>
    <include file="002-upgrade.xml"
             relativeToChangelogFile="true"/>
</databaseChangeLog>
~~~

**Why don't the two entrypoints re-run V1?** Both `include` the exact same `001-create.xml` via the same relative path; Liquibase records changeset identity and checksum and recognizes V1 is already applied. If you **move or rename a changeset** after deployment, its identity may change; production projects can use `logicalFilePath` and explicit migration policies rather than arbitrarily renaming deployed paths.

## 10. JUnit: Testing Liquibase Upgrade from V1 to V2

**`src/test/java/com/example/migration/LiquibaseUpgradeTest.java`**

~~~java
package com.example.migration;

import java.sql.Connection;
import java.util.UUID;

import javax.sql.DataSource;

import liquibase.Contexts;
import liquibase.LabelExpression;
import liquibase.Liquibase;
import liquibase.database.Database;
import liquibase.database.DatabaseFactory;
import liquibase.database.jvm.JdbcConnection;
import liquibase.resource.ClassLoaderResourceAccessor;

import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class LiquibaseUpgradeTest {

    private static final String V1 =
            "db/changelog/accounts/only-v1.xml";

    private static final String LATEST =
            "db/changelog/accounts/master.xml";

    private DataSource newDatabase() {
        String name = "liquibase_" +
                UUID.randomUUID().toString().replace("-", "");

        return new DriverManagerDataSource(
                "jdbc:h2:mem:" + name + ";DB_CLOSE_DELAY=-1",
                "sa",
                "");
    }

    private void update(DataSource source, String changelog)
            throws Exception {

        try (Connection connection = source.getConnection()) {
            Database database = DatabaseFactory.getInstance()
                    .findCorrectDatabaseImplementation(
                            new JdbcConnection(connection));

            try (Liquibase tool = new Liquibase(
                    changelog,
                    new ClassLoaderResourceAccessor(),
                    database)) {

                tool.update(new Contexts(), new LabelExpression());
            }
        }
    }

    @Test
    void upgradesV1ToV2AndPreservesHistoricalRows()
            throws Exception {

        DataSource source = newDatabase();
        JdbcTemplate jdbc = new JdbcTemplate(source);

        // Step 1: Liquibase executes V1 only.
        update(source, V1);

        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM DATABASECHANGELOG",
                Integer.class));

        // Before upgrade, STATUS does not exist.
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS " +
                "WHERE TABLE_NAME = ? AND COLUMN_NAME = ?",
                Integer.class, "CUSTOMER_ACCOUNTS", "STATUS"));

        // Step 2: Historical data present under V1 schema.
        jdbc.update(
                "INSERT INTO customer_accounts(id, email) " +
                "VALUES (?, ?)",
                301L, "legacy@example.test");

        // Step 3: Same DB, switch entrypoint to master V1 + V2.
        update(source, LATEST);

        // Step 4: No data loss and proper backfill.
        assertEquals("legacy@example.test",
                jdbc.queryForObject(
                    "SELECT email FROM customer_accounts WHERE id = ?",
                    String.class, 301L));

        assertEquals("ACTIVE",
                jdbc.queryForObject(
                    "SELECT status FROM customer_accounts WHERE id = ?",
                    String.class, 301L));

        // Step 5: Reject NULL status after V2.
        assertThrows(DataIntegrityViolationException.class, () ->
                jdbc.update(
                    "INSERT INTO customer_accounts(id,email,status) " +
                    "VALUES (?,?,NULL)",
                    302L, "bad@example.test"));

        // Step 6: Two changesets recorded once each.
        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM DATABASECHANGELOG",
                Integer.class));

        // Step 7: Re-running update leaves state unchanged.
        update(source, LATEST);

        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM DATABASECHANGELOG",
                Integer.class));
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer_accounts",
                Integer.class));
    }

    @Test
    void freshLiquibaseUpdateAppliesAllChangeSetsOnce()
            throws Exception {

        DataSource source = newDatabase();
        JdbcTemplate jdbc = new JdbcTemplate(source);

        update(source, LATEST);

        jdbc.update(
                "INSERT INTO customer_accounts(id,email) " +
                "VALUES (?,?)",
                401L, "fresh@example.test");

        assertEquals("ACTIVE",
                jdbc.queryForObject(
                    "SELECT status FROM customer_accounts WHERE id = ?",
                    String.class, 401L));

        update(source, LATEST);

        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM DATABASECHANGELOG",
                Integer.class));
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer_accounts",
                Integer.class));
    }
}
~~~

### Why Test Liquibase with Two Root Changelogs?

The `update(...)` API advances to the latest state of the supplied changelog by default. Because we want to observe **real V1** before upgrading to V2, we provide `only-v1.xml` first and then `master.xml`. Crucially, **the included V1 file preserves its identity**.

In the test:

- `DATABASECHANGELOG` has one row after V1.
- After V2, it has two rows corresponding to the two changesets.
- `DATABASECHANGELOGLOCK` is also managed by Liquibase to guard against concurrent updates.
- When `update` runs again, no new changesets apply; history remains two rows.
- Preserving ID 301 proves the backfill **did not lose existing accounts**.
- Constraints and `DEFAULT` are verified with negative and positive `INSERT`s.

### Note on Closing Connections

`Liquibase` 4.x implements `AutoCloseable` in this example's API. The test uses `try-with-resources` for both the connection and the tool to prevent handle leaks. Calling the API directly on an unpooled H2 `DataSource` fits a small lab; in a real app, Boot manages `SpringLiquibase` and connection lifecycles at startup.

### Liquibase Contexts and Labels

`new Contexts()` and `new LabelExpression()` in the test represent no filtering. **Never assume a changeset with `context="test"` only runs when the test context is enabled**: depending on syntax and version, context-tagged changesets can still run if the client supplies no context filter. For changesets that **must only run in tests**, Liquibase supports required context syntax (such as `@test`) or separate changelog/test-profile strategies; verify exact behavior for your version.

Never use test-only changesets to insert real customer data into production. When tests need fixtures, isolate sources/config and verify migration location and context safety.

## 11. Spring Boot Startup Test: Automatically Applying Flyway Before Querying

The two classes above test the **migration tool APIs**. To verify that Spring Boot genuinely integrates Flyway when the `ApplicationContext` starts, add a full-context smoke test.

**`src/test/java/com/example/migration/BootFlywayStartupTest.java`**

~~~java
package com.example.migration;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = SchemaUpgradeApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.datasource.url="
            + "jdbc:h2:mem:boot_upgrade_smoke;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.flyway.locations=classpath:db/migration/flyway",
        "spring.liquibase.enabled=false",
        "spring.sql.init.mode=never"
    })
class BootFlywayStartupTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private Flyway flyway;

    @Test
    void bootAppliedMigrationsBeforeTestStarted() {
        assertEquals("2",
                flyway.info().current().getVersion().getVersion());

        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM flyway_schema_history " +
                "WHERE success = TRUE",
                Integer.class));

        // Test does not call migrate() itself: app startup already migrated.
        jdbc.update(
                "INSERT INTO customer_accounts(id,email) " +
                "VALUES (?,?)",
                501L, "boot@example.test");

        assertEquals("ACTIVE", jdbc.queryForObject(
                "SELECT status FROM customer_accounts WHERE id = ?",
                String.class, 501L));
    }

    @Test
    void bootKeepsFlywayHistoryOnTheActualDatabase() {
        assertTrue(flyway.info().current().getVersion()
                .getVersion().equals("2"));

        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM flyway_schema_history " +
                "WHERE success = TRUE",
                Integer.class));
    }
}
~~~

**Key takeaway:** `@SpringBootTest` has no test-managed transaction by default, so the INSERT in the first test commits to H2. The second test avoids relying on business-table row counts, asserting only history so it stays independent of method order. In real apps, use an isolated test database/schema with proper teardown to prevent leftover rows.

### Should You Also Write a Boot Liquibase Startup Test?

When a project picks **Liquibase as its primary migration tool**, write a similar smoke test:

- Enable `spring.liquibase.enabled=true`.
- Disable Flyway with `spring.flyway.enabled=false`.
- Point `spring.liquibase.change-log=classpath:db/changelog/accounts/master.xml`.
- Use an isolated test database.
- Assert `DATABASECHANGELOG` holds all changesets and that a migrated table/column actually works.

**This is an optional extension**, omitted as a seventh test in this sample so two tools do not compete over one schema. The alternative config reuses the same XML files from this lesson and requires `liquibase-core` on the test runtime classpath.

## 12. Running Gradle and Expected Results

Complete test summary:

| Test Class | `@Test` Count | Goal |
| --- | ---: | --- |
| `FlywayUpgradeTest` | 2 | Upgrade V1→V2, backfill, constraints, history, rerun |
| `LiquibaseUpgradeTest` | 2 | Run changesets V1→V2, verify data/history/idempotency |
| `BootFlywayStartupTest` | 2 | Flyway runs automatically during Spring Boot startup |
| **Total** | **6** | Both tools + Boot integration |

From the project root with Wrapper, JDK 17, and downloaded dependencies:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run individually:

~~~bash
./gradlew test --tests 'com.example.migration.FlywayUpgradeTest'
./gradlew test --tests 'com.example.migration.LiquibaseUpgradeTest'
./gradlew test --tests 'com.example.migration.BootFlywayStartupTest'
~~~

Expected: **6 methods pass** in a compatible environment. This is an **expected outcome from the source**, not a claim that Gradle/JUnit was executed on the reader's machine.

Reports typically appear at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.migration.FlywayUpgradeTest.xml
    ├── TEST-com.example.migration.LiquibaseUpgradeTest.xml
    └── TEST-com.example.migration.BootFlywayStartupTest.xml
~~~

There are no `System.out.println` calls in the project, so there is **no fixed business stdout**. If Gradle reports `UP-TO-DATE` or `FROM-CACHE`, the task reused cached results; to force a fresh run for diagnostics:

~~~bash
./gradlew test --rerun-tasks
~~~

If a fresh project lacks a Wrapper yet has a compatible Gradle installed, generate one:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then commit the Wrapper scripts/JAR per your repository conventions. Production projects should standardize Wrapper/JDK versions in CI.

### How to Read Expected Output

During Flyway/Liquibase execution, logs may report applied migrations, locks acquired/released, and schema history. **Never hardcode exact log text**: Flyway/Liquibase versions, loggers, and dialects change message wording. The reliable assertions in this lesson inspect **database state** and **migration history** read back after updating.

## 13. Checking Checksums and Migration Drift

### Flyway

Flyway stores version history, checksums, and applied status. If you modify a `V1__...` file that has already run on a DB, `validate()` reports a checksum mismatch. That is a critical warning about **schema drift**.

A useful regression check:

1. On a test database, apply V1 using the released versioned file.
2. Run against the migration files from the new branch.
3. Call `validate()`.
4. On mismatch, fail the build and investigate during code review/deployment—**never auto-repair blindly**.

`repair` adjusts metadata/history; it does not magically transform a live schema to **match an edited file**. If a migration failed leaving inconsistent state, inspect **both the actual schema and history** before deciding whether to adjust history.

### Liquibase

Liquibase stores a checksum for each changeset, identified by id, author, and file path/`logicalFilePath`. Editing a deployed changeset fails checksum validation unless mechanisms like `runOnChange` or `validCheckSum` are intentionally configured. Those options **must not be used to hide arbitrary discrepancies**.

Good habits:

- An applied changeset/version is **immutable**.
- Subsequent schema changes belong in a new changeset/version.
- Avoid renaming or moving changelog files in ways that alter identity.
- Code-review migration SQL/DDL like production code changes.
- Have CI test upgrades from previously released versions, not just brand-new schemas.

### Why Valid Checksums Alone Are Not Enough

Checksums only guard consistency of **already-applied migration definitions**. They do not prove:

- New query code is compatible with legacy data.
- New constraints match real production data.
- Index creation won't lock tables for too long.
- Previous migrations didn't corrupt data due to faulty backfill logic.
- Production DB settings match H2.
- Rolling deployments won't break older application instances.

Combine checksum validation with **data, schema, and compatibility** assertions.

## 14. Rollback, Repair, and DDL Transactions

Not all databases roll back DDL identically.

| Topic | What to Check |
| --- | --- |
| PostgreSQL | Many DDL statements are transactional; certain statements/modes like `CREATE INDEX CONCURRENTLY` have special rules |
| MySQL | Many DDL statements trigger implicit commits, even inside a transaction |
| H2 | Demo use only; semantics do not fully represent production |
| Flyway failed migration | May leave failed history entries or partially applied schema changes depending on the DB |
| Liquibase failed changeset | May roll back transactions when supported by the engine, though not all DDL/side effects are reversible |
| Application version rollback | Does not automatically roll back the database schema |
| `clean`/`dropAll` | Destructive; never run against production or shared DBs |
| Backup restore | Requires tested backup/restore procedures before incidents occur |

**Never treat “undo” as safe by default.** For data-destructive operations like `DROP COLUMN` or `TRUNCATE`, rollback SQL cannot recover lost data without a backup, snapshot, or prior copy strategy.

In real deployments, teams usually prefer:

- **Forward-fix:** author a new migration correcting the deployed state.
- **Backward-compatible schemas:** keep both old and new code working across transitions.
- **Backup + tested restore:** for cases requiring full state recovery prior to a migration.
- **Runbooks:** defining stop conditions, approvers, metrics, app rollback steps, and database restore steps.

A green H2 test is no substitute for a restore rehearsal.

## 15. Expand–Migrate–Contract in Rolling Deployments

The demo adds `NOT NULL` and `DEFAULT` in a single V2 because tests do not run multiple application versions simultaneously. Production services with rolling instances often split this across releases:

**Release A — Expand**

~~~sql
ALTER TABLE customer_accounts
    ADD COLUMN status VARCHAR(16);
~~~

- Add a nullable column so older code can still INSERT.
- New code reads `status` with a safe fallback.
- New code begins writing `status`.

**Release B — Backfill and Dual-Write / Compatibility**

~~~sql
UPDATE customer_accounts
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

For large tables, use **batched backfills**, checkpoints, throttling, failure resumption, and row-count verification. The full-table `UPDATE` in the demo is not recommended as-is on hundreds of millions of rows.

**Release C — Contract After Old Versions Are Retired**

~~~sql
ALTER TABLE customer_accounts
    ALTER COLUMN status SET NOT NULL;
~~~

When renaming a column, you usually need parallel read/write support and only drop the old column once every app instance has upgraded. Avoid deploying the “contract” schema before legacy code stops referencing the old column.

### Which Tests Protect Each Phase?

- Test V1 code against the **expanded** schema to confirm backward compatibility.
- Test V2 code against the migrated V1 schema + backfilled data.
- Test old readers / new writers during dual-write if applicable.
- Test post-migration constraints against diverse legacy data shapes.
- Test backfill repeatability/retries.
- Run integration tests against the real DB engine with representative index sizes.

**Important:** Migration tests and application-compatibility tests are distinct; keep both when downtime or mixed-version deployments pose high risk.

## 16. Test Data: Avoiding “Fresh Database Bias”

Useful fixtures go beyond a single clean row. For real migrations, include:

- **Empty database:** V1→latest migrations from scratch.
- **Database with historical data:** legacy emails/IDs, foreign keys, nullable legacy fields.
- **Boundaries:** max-length text, min/max numbers, timestamps/timezones, Vietnamese Unicode.
- **Quirky data:** old rows with null values or deprecated enum values.
- **Scale:** batch backfills, index builds, connection pools, lock contention.
- **Concurrent writes:** if the app keeps writing during migration, measure compatibility and locking.
- **Multiple tenants/schemas:** migrations applied across each schema per runbook.
- **Failure injection:** a step fails mid-migration; verify state, retry, or restore per engine.

Never put un-anonymized production customer data into tests. Use synthetic data or datasets sanitized per security policy. Migration tests must never hold privileges to alter or write to production DBs.

### Strong vs. Weak Assertions

**Weak:**

~~~java
assertTrue(jdbc.queryForObject(
        "SELECT COUNT(*) FROM customer_accounts",
        Integer.class) >= 0);
~~~

This query passes even if the table is empty and legacy accounts were wiped.

**Strong:**

~~~java
assertEquals("legacy@example.test",
        jdbc.queryForObject(
            "SELECT email FROM customer_accounts WHERE id = ?",
            String.class, 301L));

assertEquals("ACTIVE",
        jdbc.queryForObject(
            "SELECT status FROM customer_accounts WHERE id = ?",
            String.class, 301L));
~~~

Two independent assertions confirm **old data was preserved** and **new data was transformed properly**. Never compute expected values from the migration script itself; derive test expectations from the business contract.

## 17. PostgreSQL Testcontainers for Production-Like Migrations

H2 works well for teaching mechanics and simple migrations. When production runs PostgreSQL, execute the exact SQL/changelogs in **PostgreSQL Testcontainers**, especially when migrations involve:

- `jsonb`, arrays, enums, UUID types, `ILIKE`, or SQL functions.
- Transactional DDL and locking different from H2.
- `CREATE INDEX CONCURRENTLY`, extensions, or custom schemas.
- Foreign-key validation and row-level locks.
- Backfills over large datasets, indexes, or complex constraints.
- PostgreSQL-specific default expressions or type casts.

### Extension Dependencies for Boot 3.3

In a Flyway project:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    // Flyway 10 uses a dedicated PostgreSQL support module.
    implementation 'org.flywaydb:flyway-database-postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
~~~

This snippet extends a project already configured with starters and JUnit, not a complete `build.gradle`. Requires a container runtime and permission to pull/run the Postgres image.

### An Appropriate Test Context

~~~java
@Testcontainers
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.flyway.locations=classpath:db/migration/flyway",
        "spring.liquibase.enabled=false"
    })
class PostgresMigrationIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired DataSource, JdbcTemplate, Flyway...
    // Assert DatabaseProductName = PostgreSQL
    // Assert actual schema, history, migrated data.
}
~~~

This is an architectural snippet requiring imports, dependencies, DDL/fixtures, and assertions to compile. `@ServiceConnection` supplies connection details to the auto-configured `DataSource` when configured properly, yet **starting a container alone does not prove the app used it**. Always inspect JDBC metadata on the live `DataSource` to confirm the engine.

### Slice Tests with a PostgreSQL Container

When using `@DataJpaTest` or `@JdbcTest` on **Spring Boot 3.3**, test database auto-configuration usually replaces the `DataSource` with embedded H2. To keep PostgreSQL Testcontainers active, add:

~~~java
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
~~~

`Replace.NON_TEST` arrived in Boot 3.4+, so it does not apply to Boot 3.3 code. If you omit `Replace.NONE`, tests may silently run on H2 and pass even when native Postgres SQL is broken. Asserting `getDatabaseProductName() == "PostgreSQL"` catches this mistake.

### Testing V1→V2 Upgrade in a Container

Against a brand-new PostgreSQL database dedicated to each test:

1. Run **V1 migration** on the real engine, stopping at V1.
2. Insert historical fixture rows.
3. Run V2 or latest.
4. Assert data, status, constraints, and history via JDBC against PostgreSQL.
5. Re-run the tool to verify idempotency and checksums.
6. Destroy the test container/schema after the suite finishes.

Whether using `@SpringBootTest` or the Java API directly, **never share a container or schema across tests** if table-wide cleanup could interfere across tests.

## 18. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Migration test passes on fresh DB, V1 deploy fails | Upgrade with legacy data never tested | Build V1 + seed data, then upgrade to V2 |
| `STATUS` column exists but is all null | Backfill omitted | Assert legacy row status and constraint |
| Migration adding `NOT NULL` fails | Constraint placed before backfill | Expand → backfill → contract |
| Flyway cannot find files | Wrong `locations` or `V...__...sql` naming | Verify classpath and naming pattern |
| Flyway checksum mismatch validation error | Edited an already-applied versioned migration | Create a new migration; do not auto-repair |
| Flyway hits the wrong schema | Misconfigured DataSource/schema | Check JDBC metadata + schema history |
| Flyway and Liquibase fight over tables | Both auto-enabled on one DB | Pick one tool/scope; disable the other |
| Liquibase re-runs V1 changeset | Changed id/author/file path | Keep identity or manage `logicalFilePath` intentionally |
| Liquibase lock stays held | Migration job killed or failed | Inspect `DATABASECHANGELOGLOCK`; never clear blindly |
| Test only asserts history count | Migration recorded metadata while corrupting data | Assert business records + constraints |
| Second `migrate` causes duplicates | Migration bypassed history / broken identity | Check version/changeset identity |
| H2 passes, PostgreSQL fails | SQL dialect/DDL/locking differences | Testcontainers with real engine |
| Hibernate `create-drop` masks bugs | ORM built schema, bypassing migrations | Make migrations the schema source; use JPA `validate` |
| `@Sql` seed runs before migrations | Listener order or missing schema | Sequence lifecycle/fixtures after migrations |
| Order-dependent tests | Shared DB without reset | Isolate DB/schema per test |
| Production DB altered accidentally | Wrong test profile/credentials | CI network isolation, test-only DB allowlist |
| Flyway repeatable re-runs unexpectedly | Checksum of `R__` file changed | Understand repeatables and dependency ordering |
| Liquibase test context runs in prod | Context filtering not enforced properly | Use required contexts / test-only changelogs and CI checks |
| Backfill takes hours | Huge full-table UPDATE/lock | Batch, checkpoint, benchmark, test in staging |
| Rollback fails to restore data | Implicit DDL commit or dropped column | Restore/forward-fix strategy |
| Native SQL migration not portable | DB-specific syntax | Verify on target engine/version |
| Schema migration leaks data | Test fixtures hold production PII | Use synthetic/anonymized data and least-privilege access |

### Diagnostic Workflow

1. Confirm the **tool**, Spring Boot version, and migration paths.
2. Inspect the **actual** database the app/tool connects to, not just properties files.
3. Inspect the history table and current version/changeset identities.
4. Check whether migration files and checksums were modified post-deploy.
5. Re-run in an isolated DB **from V1 with data**, not just a fresh DB.
6. Read the root-cause SQL/DDL error, including constraints, indexes, and types.
7. Check transaction semantics and DB state after a failed migration.
8. Cross-check business data, schema constraints, and indexes.
9. If production uses a non-H2 engine, move testing to matching Testcontainers.
10. Never run `clean`/`dropAll` or automatic `repair` to paper over an uninvestigated failure.

## 19. Criteria for Evaluating a Migration Test Pipeline in CI

A solid pipeline generally spans these layers:

**Layer A — Static / Code Review:**

- Released V1/V2 files are untouched; new changes get distinct version/changeset IDs.
- SQL/changelogs parse cleanly; no production passwords or URLs appear.
- Backward compatibility and failure remediation notes are documented.
- Destructive changes include a backup/restore plan.

**Layer B — Empty Schema Test:**

- Run all migrations from an empty database.
- Confirm the final schema has all tables, columns, and indexes.
- Migrations apply once and pass validation.

**Layer C — Upgrade Test:**

- Start from the real prior schema version.
- Seed fixtures representing legacy data.
- Run new migrations.
- Verify data preservation, backfill, and constraints.
- Re-run the tool to verify idempotency.

**Layer D — Production-Engine Test:**

- PostgreSQL/MySQL/Testcontainers matching the production major version.
- Flyway/Liquibase targets that datasource without H2 replacement.
- Verify DB-specific SQL, transactions/DDL, and locking.
- Where needed, test with enough data volume for profiling.

**Layer E — App Compatibility:**

- Boot the new application against the migrated schema.
- Verify key repository and API queries.
- Test old app code against the expanded schema when rolling deployments require it.
- Inspect startup logs, migration history, alerts, and ownership.

**Layer F — Operational Readiness:**

- Backup, snapshot, and restore have been rehearsed.
- Migrations have execution-time budgets and lock monitoring.
- Destructive changes require explicit approval.
- CI never holds access to production DBs outside policy.

Large projects need not run the most expensive tests on every commit, but must ensure **genuine upgrade coverage** before release—not just fresh-DB tests.

## 20. Hands-On Exercises

**Exercise A — Missing backfill:** In a test copy, remove `UPDATE customer_accounts SET status='ACTIVE'`. Run the upgrade test with a V1 row. Analyze why the migration fails on `NOT NULL` or why legacy rows violate the contract.

**Exercise B — Overly weak test:** Temporarily drop the assertions checking email/ID preservation, asserting only that the table exists. Inject a buggy V2 containing `DELETE FROM customer_accounts`. Observe why weak tests miss data loss.

**Exercise C — Idempotency:** Run `migrate`/`update` twice. Assert history still contains two versions/changesets and row counts are unchanged. Distinguish tool-level behavior from raw SQL statement idempotency.

**Exercise D — Flyway drift:** On a test database already migrated to V1, edit the V1 file in an experimental branch and call `validate()`. Observe the checksum mismatch and revert. Never do this on a shared database.

**Exercise E — Liquibase identity:** Try changing the `id` or file path of the V1 changeset in a lab copy. Analyze why the tool attempts to re-run `createTable` and how to manage `logicalFilePath` safely.

**Exercise F — Before and after fixtures:** Add two historical customers with Vietnamese Unicode emails and boundary-length strings in V1, upgrade to V2, and verify all remain intact and `ACTIVE`.

**Exercise G — NOT NULL / default:** After V2, test inserting a null `status` and inserting without `status`. The first must fail; the second must receive `DEFAULT`.

**Exercise H — Spring Boot wiring:** In `BootFlywayStartupTest`, point `spring.flyway.locations` at an empty folder. The test should detect the missing schema/history rather than merely celebrating context startup.

**Exercise I — Preventing both tools from running together:** Temporarily enable Liquibase auto-migration in a separate test context with its own DB. Observe and explain how both tools alter the same schema, then restore isolated config.

**Exercise J — Testcontainers:** Run Flyway V1/V2 against a PostgreSQL 16 test container. Verify engine, data, index, history, and transactional DDL behavior.

**Exercise K — Expand–contract:** Split V2 into three migrations (add nullable, backfill, enforce `NOT NULL`). Write tests showing old code works after expand and new code works after contract.

**Exercise L — Dirty legacy data:** Add V1 rows whose email/fields violate a new rule. Design a controlled backfill/repair migration without arbitrarily deleting data.

**Exercise M — External schema drift:** Execute a manual `ALTER` on a test DB outside migrations, then run tests. Distinguish history checksum consistency from actual schema consistency; add metadata/constraint assertions.

**Exercise N — Rollback/restore runbook:** Simulate a migration failing mid-way in a sandbox DB, inspect state, and draft a forward-fix or restore plan suited to the DB engine. Never run destructive experiments in production.

## 21. Pre-Merge Migration Checklist

- [ ] Are schema migrations the source of truth without `ddl-auto=create-drop` masking bugs?
- [ ] Is exactly one tool (Flyway or Liquibase) enabled per schema?
- [ ] Do migration paths, versions, and changeset identities follow conventions and stay immutable post-deploy?
- [ ] Is there an upgrade test **from a populated V1 DB** to V2, not just an empty DB?
- [ ] Are assertions verifying preservation of critical IDs and business fields?
- [ ] Are backfills for null and legacy data explicitly verified?
- [ ] Are `NOT NULL`, defaults, indexes, and foreign keys tested where part of the contract?
- [ ] Does tool history confirm migrations applied once?
- [ ] Does running migrations a second time avoid re-applying succeeded entries?
- [ ] Does checksum drift fail builds rather than being hidden by blind `repair`?
- [ ] Do tests use isolated DBs/schemas to avoid fixture collisions and cross-test deletion?
- [ ] Is H2 restricted to behavior independent of production SQL dialect?
- [ ] When production is PostgreSQL/MySQL, are there tests against that matching engine?
- [ ] Do `@DataJpaTest`/`@JdbcTest` use `Replace.NONE` when keeping Testcontainers on Boot 3.3?
- [ ] Is JPA set to `ddl-auto=validate` or `none` when migrations manage schemas?
- [ ] Are test-only Liquibase contexts and Flyway locations prevented from running in production?
- [ ] Does a startup test prove Spring Boot applies migrations before queries run?
- [ ] Are migrations compatible with rolling deployments using expand–contract where needed?
- [ ] Are failure semantics (failed DDL, implicit commits, lock timeouts) understood?
- [ ] Is there a backup/restore or forward-fix runbook for risky changes?
- [ ] Is CI blocked from holding destructive credentials or privileges against production DBs?
- [ ] Do migration logs avoid printing secrets/PII, with alerts routed to an owner on failure?
- [ ] Do Gradle/JUnit reports confirm tests actually executed rather than being skipped via cache?

## 22. References

Links should be consulted for your exact version. The sample project pins Spring Boot 3.3.5 / Java 17 and uses the Flyway/Liquibase versions managed by the Boot BOM; APIs in newer major releases may differ.

- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): Flyway/Liquibase auto-configuration, startup migrations, and test-specific migrations.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, JDBC/JPA slices, and test database replacement.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection` and connection details.
- [Flyway — Java API](https://documentation.red-gate.com/flyway/reference/usage/api-java): `Flyway.configure`, `migrate`, `validate`, `info`, `target`.
- [Flyway — Validate](https://documentation.red-gate.com/flyway/reference/commands/validate): checksum drift and migration validation.
- [Liquibase — Using XML Changelogs](https://www.liquibase.com/blog/using-xml-changelogs-liquibase): changesets, master include structure.
- [Liquibase — Include Changelogs](https://docs.liquibase.com/reference-guide/changelog-attributes/include): `include`, relative paths, and changeset filename identity.
- [Liquibase — Contexts](https://docs.liquibase.com/reference-guide/changelog-attributes/what-are-contexts): context filtering, required contexts.
- [Liquibase — Core API](https://javadocs.liquibase.com/liquibase-core/liquibase/Liquibase.html): `update(Contexts, LabelExpression)` and Java API.
- [Testcontainers for Java](https://java.testcontainers.org/): database containers for testing migrations on production engines.

**Remember:** Proper schema migration testing requires **two paths**: creating a fresh database from scratch **and** upgrading an existing database holding legacy data. With Flyway, verify versions, history, and checksums; with Liquibase, verify changeset identity, history, and checksums. Both require independent data and constraint assertions, execution against the real engine when SQL is dialect-specific, and safe rollback/restore plans. A test showing only that “the app boots on H2” never proves production schema upgrades are safe.
