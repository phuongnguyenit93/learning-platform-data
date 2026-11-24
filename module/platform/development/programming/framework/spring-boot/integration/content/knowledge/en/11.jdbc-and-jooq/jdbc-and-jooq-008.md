# SQL Dialects, Schemas, and jOOQ Code-Generation Boundaries

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot coordinates system integration through HTTP clients, databases, caches, message brokers, and Spring Integration adapters. The emphasis goes beyond basic connectivity to cover configuration, data contracts, transactions, error handling, idempotency, testing, and observability of real-world integration flows.

Within the **JDBC and jOOQ** chapter, the topic **SQL dialects, schemas, and jOOQ code-generation boundaries** resolves three questions that are frequently conflated:

1. **SQL dialect:** Will jOOQ render SQL using PostgreSQL, MySQL, SQL Server, or another database's syntax?
2. **Database schema:** Where do the actual tables, columns, constraints, sequences, and types in the database come from?
3. **Code generation:** When does jOOQ introspect metadata to generate Java classes, and what falls **outside** the generator's responsibilities?

For example, an Order Service uses PostgreSQL to persist `app.orders` and `app.order_outbox`. Developers add a `currency` column, write Flyway migration V12, and then run jOOQ's generator against a staging database still on V11. Generated `ORDERS` lacks `CURRENCY`, breaking compilation. Another developer generates classes from V12 and deploys to an unmigrated production database, causing runtime `column ... does not exist` SQL errors. A third uses the H2 dialect in tests while production runs PostgreSQL, leaving `ON CONFLICT` and locking behavior unverified.

This lesson draws crisp boundaries between **build-time metadata**, **runtime SQL**, **DB migrations, and deployment**, preventing both compilation failures and silent data bugs.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish `DSLContext`, `SQLDialect`, JDBC `DataSource`, driver, and database server.
2. Correctly interpret catalogs, schemas, `search_path`, input/output schemas, and runtime mapping.
3. Configure Spring Boot + PostgreSQL + jOOQ and explain how SQL is rendered.
4. Analyze dialect differences: paging, upsert, `RETURNING`, `JSONB`, UUIDs, enums, sequences, time, and locking.
5. Design a jOOQ code-generation step for Maven or Gradle running before `compileJava`.
6. Use Flyway/Liquibase alongside consistent database metadata to regenerate models.
7. Control generated POJOs/records/DAOs, naming strategies, forced types, and converters.
8. Determine dependency scopes, generator classpaths, and metadata access privileges.
9. Diagnose schema drift across migrations, generated code, and runtime databases.
10. Test using PostgreSQL Testcontainers, CI codegen verification, rollbacks, and observability.

> **Guiding principle:** The jOOQ generator reads metadata and produces **Java source files**; it does not create production schemas, execute Flyway migrations, or replace the transaction manager. Clean compilation of generated Java does not prove the runtime database is compatible.

---

## 1. Boundary Diagram Across the Application Lifecycle

~~~mermaid
flowchart TD
    M["Versioned migrations in Git"] --> E["Migrate isolated PostgreSQL"]
    E --> S["Database schema metadata"]
    S --> G["jOOQ Code Generation at BUILD TIME"]
    G --> J["Generated Tables / Records / Keys / POJOs"]
    J --> C["Java compilation and Boot JAR"]
    C --> R["Runtime DSLContext + SQLDialect"]
    R --> Q["Rendered SQL + JDBC bind variables"]
    Q --> D["Hikari DataSource / JDBC driver"]
    D --> P["Real PostgreSQL database"]
~~~

| Component | Role | What It Does Not Do Automatically |
| --- | --- | --- |
| SQL migrations | Create/evolve versioned schemas | Generate Java classes |
| PostgreSQL catalog/schema | Source of physical metadata | Ensure Java was rebuilt |
| jOOQ `org.jooq.meta` | Introspect metadata | Run business DB transactions |
| jOOQ `org.jooq.codegen` | Generate Java source | Run production DDL |
| Generated `Tables`, `Keys`, `Records` | Typed Java DSL metadata | Create tables/columns in the DB |
| jOOQ `DSLContext` | Build, render, and execute SQL | Pick the right target DB if misconfigured |
| `SQLDialect` | Controls vendor-specific SQL rendering | Switch database engines |
| Spring JDBC / Hikari | Connection pool and JDBC sessions | Guarantee SQL portability |
| Flyway / Liquibase | Advance schema across migration versions | Execute Java ORM queries |
| Spring transaction manager | Coordinate local transactions | Provide distributed ACID with brokers/HTTP |

### 1.1. Different Meanings of the Word "Schema"

- **Physical database schema**: namespaces like `app`, `audit`, and `public` in PostgreSQL containing tables, views, and sequences.
- **Data contract schema**: JSON Schema, Avro, Protobuf, or XSD for HTTP/broker payloads.
- **Generated schema class**: Java representation of database metadata at codegen time.
- **Default schema / search path**: how unqualified table names resolve at runtime.
- **Schema migration version**: controlled ordering of DDL/data changes via Flyway/Liquibase.

Never expose a DB-generated record directly as a Kafka event simply because both are called "schemas." Wire contracts carry independent versioning and privacy requirements.

### 1.2. Does jOOQ Replace JDBC?

No. In the standard JDBC model:

~~~mermaid
sequenceDiagram
    participant S as OrderService
    participant J as jOOQ DSLContext
    participant H as HikariCP
    participant D as PostgreSQL
    S->>J: select/update using generated fields
    J->>J: Render SQLDialect.POSTGRES + bind values
    J->>H: Borrow JDBC connection
    H->>D: PreparedStatement execute
    D-->>H: ResultSet / SQLSTATE
    H-->>J: JDBC results
    J-->>S: Record / DTO
~~~

Codegen runs **before** Java compilation; runtime executes against the compiled generated classes. `DataSource` still governs the DB endpoint, credentials, TLS, pool, and transactions. jOOQ does not eliminate the need to understand SQL, indexes, or constraints.

## 2. Dependencies and Version Alignment

With Spring Boot 3.x / Java 17+ and PostgreSQL, an example Gradle setup:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jooq'

    // The jOOQ starter usually brings in JDBC infrastructure;
    // only add starter-jdbc explicitly if the project needs it.
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    implementation 'org.flywaydb:flyway-core'
    // For Flyway releases that split out the PostgreSQL support module:
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

Do not assume every dependency in this example is required in every project. Gradle/Spring Boot BOMs can manage jOOQ, PostgreSQL JDBC, and Flyway versions; Flyway's database-specific module depends on the release. Check compatibility matrices before copying into Boot 4 or commercial jOOQ editions.

### 2.1. Generator and Runtime Use Two Distinct Classpaths

| Artifact | Environment | Purpose |
| --- | --- | --- |
| `spring-boot-starter-jooq` | Application runtime | DSL / JDBC / Spring integration |
| PostgreSQL JDBC driver | Application runtime | Connect and execute SQL |
| `org.jooq:jooq-codegen` | Build tool | Generate Java sources |
| `org.jooq:jooq-meta` | Build tool (often transitive) | Read DB metadata |
| PostgreSQL JDBC driver for generator | Build-tool classpath | Open metadata connection |
| Generated Java files | Main source set | Compiled into the application |
| Flyway / Liquibase | Build/test/runtime per pipeline | Schema migrations |
| PostgreSQL Testcontainers | CI/test/build | Isolated real schema |
| jOOQ commercial edition | Per license/dialect | Dialects/features outside OSS |

As long as application code does not import generator types, keep `jooq-codegen` off the production runtime classpath rather than adding it just for IDE visibility.

### 2.2. `SQLDialect` Support by Edition and Version

`SQLDialect.POSTGRES` is the standard dialect when targeting PostgreSQL. Other dialects vary across OSS and commercial distributions, and support evolves across jOOQ releases. Never assume every database in the enum belongs to the OSS edition or that every vendor feature translates automatically.

Keep the generator version, runtime jOOQ version, and metadata modules aligned so generated sources never invoke methods absent at runtime. When upgrading major or minor jOOQ versions, inspect generated diffs and run compile plus integration tests.

## 3. Spring Boot Runtime Configuration for `DataSource` and SQL Dialect

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://orders-db.internal.example:5432/orders?sslmode=verify-full
    username: ${ORDERS_DB_USER}
    password: ${ORDERS_DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      connection-timeout: 3000
  jooq:
    sql-dialect: POSTGRES
~~~

- `spring.datasource.*`: endpoint, authentication, TLS, driver, and pool.
- `spring.jooq.sql-dialect`: specifies the SQL rendering dialect on Boot versions supporting this property.
- Spring Boot typically auto-configures `DSLContext` from `DataSource` when dependencies and bean conditions align.
- `SQLDialect.POSTGRES` **does not** turn a MySQL database into PostgreSQL.
- If omitted, Boot can detect the dialect from JDBC metadata on supported databases; multi-datasource or proxied setups should configure and verify it explicitly.

### 3.1. `DSLContext` at Runtime

~~~java
import org.jooq.DSLContext;
import org.springframework.stereotype.Repository;
import static com.example.db.jooq.tables.Orders.ORDERS;

@Repository
public class OrderQueryRepository {

    private final DSLContext dsl;

    public OrderQueryRepository(DSLContext dsl) {
        this.dsl = dsl;
    }

    public OrderSummary findById(long id) {
        return dsl.select(
                        ORDERS.ID,
                        ORDERS.ORDER_ID,
                        ORDERS.ORDER_STATUS,
                        ORDERS.AMOUNT_MINOR)
                .from(ORDERS)
                .where(ORDERS.ID.eq(id))
                .fetchOne(r -> new OrderSummary(
                        r.get(ORDERS.ID),
                        r.get(ORDERS.ORDER_ID),
                        r.get(ORDERS.ORDER_STATUS),
                        r.get(ORDERS.AMOUNT_MINOR)));
    }
}
~~~

`OrderSummary` is an application DTO; generated `Orders` and field names depend on your codegen target and configuration. `fetchOne` can return `null` when no row exists, so adapter APIs should define not-found behavior clearly. Never copy Java import paths blindly if your project uses a custom naming strategy.

### 3.2. Rendering SQL Without Executing

~~~java
String rendered = dsl
        .select(ORDERS.ID)
        .from(ORDERS)
        .where(ORDERS.ORDER_STATUS.eq("CONFIRMED"))
        .getSQL();
~~~

`getSQL()` builds SQL according to the dialect and settings, possibly containing bind markers per configuration. It does not check whether columns exist in production, verify `GRANT`s, or invoke the query planner.

To render offline without a datasource:

~~~java
import org.jooq.DSLContext;
import org.jooq.SQLDialect;
import org.jooq.impl.DSL;

DSLContext renderer = DSL.using(SQLDialect.POSTGRES);
~~~

This renderer has no JDBC connection. Never register it in place of Spring Boot's runtime bean and expect queries to execute.

### 3.3. Multiple Datasources

An integration service might write to an `orders` database and read from a `reporting` database:

~~~text
orderDataSource     -> orderDslContext     -> OrderTransactionManager
reportDataSource    -> reportDslContext    -> ReportTransactionManager
~~~

If the two sources differ in dialect or schema, define separate `DSLContext`, `ConnectionProvider`, and transaction-manager beans, inject them with `@Qualifier`, and test routing. Boot auto-configuration optimizes for **a single primary datasource**; multiple sources require explicit wiring. A transaction on `DataSource` A never covers `DataSource` B.

## 4. Where Dialects Differ

| Feature | PostgreSQL | What Other DBs May Use | Risk If Hardcoded |
| --- | --- | --- | --- |
| Pagination | `LIMIT ... OFFSET` | `FETCH FIRST`, `OFFSET ... FETCH`, `ROWNUM` | Syntax, cost, or ordering bugs |
| Upsert | `ON CONFLICT` | `ON DUPLICATE KEY`, `MERGE` | Divergent concurrency/conflict semantics |
| Generated values | `RETURNING` | `OUTPUT`, JDBC generated keys | Extra round-trips or differing result shapes |
| JSON | `JSONB`, `@>` | Different JSON functions/operators | Type and index semantics |
| UUID | Native `UUID` | `CHAR(36)`, `BINARY(16)`, vendor types | Java converter mismatches |
| Arrays | PostgreSQL `ARRAY` | JSON, strings, or child tables | Type semantics |
| Temporal | `TIMESTAMPTZ`, `interval` | Vendor date/time types | Timezone and precision bugs |
| Locks | `FOR UPDATE SKIP LOCKED` | Hints or other clauses | Broken outbox claim semantics |
| Identity | `GENERATED ... AS IDENTITY` | `AUTO_INCREMENT`, sequences | Generated-key handling |
| Name quoting | Double quotes, folding | Backticks or brackets | Case folding / reserved keywords |
| Schema/catalog | PostgreSQL schemas | Vendor-specific namespaces | Resolving the wrong physical object |
| Boolean | Native boolean | Numbers, bits, custom types | Converter issues |

jOOQ's DSL translates many constructs across vendor SQL, yet **does not guarantee identical runtime semantics**. Run integration tests against the real database engine.

### 4.1. Pagination Requires a Deterministic `ORDER BY`

~~~java
var page = dsl.select(ORDERS.ID, ORDERS.CREATED_AT)
        .from(ORDERS)
        .where(ORDERS.ORDER_STATUS.eq("CONFIRMED"))
        .orderBy(ORDERS.CREATED_AT.desc(), ORDERS.ID.desc())
        .limit(50)
        .offset(100)
        .fetch();
~~~

Without deterministic `ORDER BY`, pages can skip or duplicate rows. Deep `OFFSET` scans also grow costly. For high-throughput outboxes or projections, consider keyset pagination on `(created_at, id)` paired with consistency rules.

### 4.2. Upserts and Idempotent Inboxes

PostgreSQL SQL:

~~~sql
INSERT INTO app.processed_events(consumer_name, event_id, processed_at)
VALUES ('inventory', 'E-100', CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

This is PostgreSQL-specific syntax. MySQL and SQL Server have different variants; never assume identical race or transaction behavior simply because jOOQ exposes an upsert API.

Illustrative jOOQ shape:

~~~java
dsl.insertInto(PROCESSED_EVENTS)
        .set(PROCESSED_EVENTS.CONSUMER_NAME, "inventory")
        .set(PROCESSED_EVENTS.EVENT_ID, eventId)
        .set(PROCESSED_EVENTS.PROCESSED_AT,
                java.time.OffsetDateTime.now())
        .onConflict(
                PROCESSED_EVENTS.CONSUMER_NAME,
                PROCESSED_EVENTS.EVENT_ID)
        .doNothing()
        .execute();
~~~

This assumes generated field types align; if `EVENT_ID` in the DB is `UUID`, Java `eventId` must be `UUID`, not `String`. Verify generated signatures and driver support before copying.

### 4.3. `RETURNING` and Generated Keys

~~~sql
INSERT INTO app.orders(order_id, order_status, amount_minor, currency)
VALUES ('ORD-100', 'NEW', 150000, 'VND')
RETURNING id, created_at;
~~~

~~~java
var inserted = dsl.insertInto(ORDERS)
        .set(ORDERS.ORDER_ID, "ORD-100")
        .set(ORDERS.ORDER_STATUS, "NEW")
        .set(ORDERS.AMOUNT_MINOR, 150000L)
        .set(ORDERS.CURRENCY, "VND")
        .returning(ORDERS.ID, ORDERS.CREATED_AT)
        .fetchOne();
~~~

`returning()` support and emulation differ across databases, dialects, and jOOQ versions. If callers rely on returned `id` or timestamps as receipts, test real PostgreSQL round-trips rather than asserting rendered SQL strings alone.

### 4.4. `JSONB`, UUIDs, and Vendor Types

~~~sql
SELECT order_id
FROM app.orders
WHERE metadata @> '{"source":"mobile"}'::jsonb;
~~~

`@>` is PostgreSQL `JSONB` containment. GIN indexes and `JSONB` semantics belong to PostgreSQL and do not automatically map portably to MySQL JSON paths. jOOQ `JSON`/`JSONB` wrappers, converters, and bindings also vary by version. **Never concatenate raw request JSON into SQL strings**; bind parameters through the DSL or `PreparedStatement`.

### 4.5. Outbox Locking

~~~sql
SELECT id, event_id, payload
FROM app.order_outbox
WHERE status = 'NEW'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

When a relay runs multiple workers, this lock/query must execute inside an appropriate transaction. `SKIP LOCKED` reduces contention, yet does not guarantee exactly-once publishing: a worker can publish and crash before marking the outbox sent, causing replay. Consumers must deduplicate using a stable `eventId`.

### 4.6. `SQLDialect.DEFAULT` Is Not a "Portable Mode"

`SQLDialect.DEFAULT` handles generic SQL rendering, yet it does not make every query behave identically across databases. When production runs PostgreSQL, configure the PostgreSQL dialect and test PostgreSQL-specific behavior; H2 compatibility mode does not validate `JSONB`, locking, sequences, optimizer plans, or transaction isolation.

## 5. Catalogs, Schemas, `search_path`, and Generated Names

In PostgreSQL:

~~~text
database orders
  schema app
    orders
    order_outbox
    processed_events
  schema audit
    integration_events
  schema public
    extensions ...
~~~

### 5.1. SQL Name Resolution

~~~sql
SELECT current_database(), current_schema(), current_user;
SHOW search_path;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('app', 'audit')
ORDER BY table_schema, table_name;
~~~

Unqualified `SELECT * FROM orders` resolves via `search_path`, whereas `SELECT * FROM app.orders` names the schema explicitly. jOOQ provides schema qualification and mapping settings, yet the runtime database connection and `search_path` still matter.

### 5.2. Generator `inputSchema` and `outputSchema`

- `inputSchema`: source schema introspected by the generator.
- `outputSchema`: schema emitted in generated metadata when remapping, **not a filesystem output directory**.
- `inputCatalog`/`outputCatalog`: catalog mapping on databases that support catalogs.
- `schemata`: multiple source-schema mapping blocks.
- `target.directory`: filesystem path where generated `.java` files are written.
- `target.packageName`: root Java package.

Never infer from `target.directory=build/generated-src/jooq` that the runtime DB contains a schema named `jooq`.

### 5.3. Common Misconfigurations

| Misconfiguration | Outcome |
| --- | --- |
| Flyway migrates `app`; generator reads `public` | Missing tables/columns |
| Generator reads `orders_test`; runtime hits older `orders_prod` | Runtime SQL errors |
| Runtime user lacks `USAGE` on schema | Login succeeds; queries denied |
| `renderSchema(false)` with wrong `search_path` | Queries resolve to the wrong table |
| Same table `orders` exists in multiple schemas | Wrong generated class imported |
| Tenant isolation built solely on `search_path` | Over-privileged roles can read across tenants |

### 5.4. Multi-Tenant Schema Mapping

You can generate Java classes from a reference schema and remap the schema per tenant at runtime. However, runtime schema mapping must be paired with domain authorization and DB grants/RLS; never trust a raw `tenantId` HTTP header as an identity principal. Schema mapping is name rendering, not security isolation.

## 6. jOOQ Code Generation: What It Generates and What It Does Not

The generator can emit:

- Java classes for schemas, tables, and fields.
- `Keys` metadata for primary, foreign, and unique keys.
- `Record`/`UpdatableRecord` classes.
- POJOs, interfaces, and DAOs per configuration.
- Enum, sequence, routine, and UDT mappings per database, version, and edition.
- Custom forced types and converters.

The generator **does not**:

- Run Flyway or Liquibase in production.
- Create tables, columns, indexes, or roles on Spring Boot startup.
- Backfill data when changing column types.
- Deploy schema migrations automatically.
- Guarantee compiled Java models match the runtime database.
- Make CRUD or `@Transactional` atomic across Kafka or HTTP.
- Replace database constraints or unique keys.

### 6.1. Standard Workflow

~~~mermaid
flowchart LR
    M["Migration files in Git"] --> P["Create isolated PostgreSQL"]
    P --> F["Apply Flyway/Liquibase"]
    F --> G["jOOQ generator introspects metadata"]
    G --> J["Generated Java sources"]
    J --> C["compileJava"]
    C --> T["Integration tests"]
    T --> B["Boot JAR"]
~~~

Only compiled Java classes ship in the application artifact. The generator never needs to run on production pods if the build artifact already bundles compiled classes.

### 6.2. Metadata Sources

| Source | When Appropriate | Risks |
| --- | --- | --- |
| Migrated PostgreSQL Testcontainer | CI, local dev, high fidelity | Container startup overhead |
| Ephemeral PostgreSQL instance | Build pipelines with isolated DBs | Provisioning/version drift |
| Local PostgreSQL from migrations | Rapid local iteration | Stale data or unapplied migrations |
| Shared staging DB | Temporary with strict controls | Drift, races, uncontrolled edits |
| Production DB | Not recommended | Secret exposure and nondeterministic metadata |
| DDL parser (`DDLDatabase` where supported) | DB-less builds | Incomplete vendor metadata parity |

When migrations use PostgreSQL-specific features, PostgreSQL Testcontainers is far more trustworthy than H2. If using `DDLDatabase`, verify the parser supports all your DDL dialects, constraints, and extensions.

### 6.3. Example Schema

~~~sql
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE app.orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id VARCHAR(120) NOT NULL UNIQUE,
    order_status VARCHAR(24) NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE app.order_outbox (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    order_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES app.orders(order_id)
);

CREATE INDEX idx_outbox_pending
    ON app.order_outbox(status, created_at, id)
    WHERE status = 'NEW';
~~~

This is **illustrative DDL for migration scripts**, not advice to execute DDL automatically at application startup. PostgreSQL requires appropriate `pg_hba`, roles, and grants; the generator's read-only introspection role differs from the runtime DML user.

### 6.4. Generated Java Is Just a Snapshot

~~~text
com.example.db.jooq
    Tables.java
    Keys.java
    tables/Orders.java
    tables/OrderOutbox.java
    tables/records/OrdersRecord.java
~~~

This tree is illustrative; exact packages and subdirectories depend on generator configuration and version. Never hand-edit generated classes—migrate the schema first, regenerate, and review the diff.

 
## 7. Maven Code Generation: Build Plugin and Schema Metadata

jOOQ provides the Maven plugin `org.jooq:jooq-codegen-maven`. The configuration below assumes PostgreSQL **has already been provisioned and migrated** before Maven reaches `generate-sources`.

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.jooq</groupId>
      <artifactId>jooq-codegen-maven</artifactId>
      <version>${jooq.version}</version>
      <executions>
        <execution>
          <id>generate-jooq</id>
          <phase>generate-sources</phase>
          <goals><goal>generate</goal></goals>
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
          <url>${jooq.codegen.jdbc.url}</url>
          <user>${jooq.codegen.jdbc.user}</user>
          <password>${jooq.codegen.jdbc.password}</password>
        </jdbc>
        <generator>
          <name>org.jooq.codegen.JavaGenerator</name>
          <database>
            <name>org.jooq.meta.postgres.PostgresDatabase</name>
            <inputSchema>app</inputSchema>
            <includes>orders|order_outbox</includes>
            <excludes>flyway_schema_history</excludes>
          </database>
          <generate>
            <records>true</records>
            <pojos>true</pojos>
            <daos>false</daos>
          </generate>
          <target>
            <packageName>com.example.db.jooq</packageName>
            <directory>${project.build.directory}/generated-sources/jooq</directory>
          </target>
        </generator>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

This is an **illustrative fragment**, not a complete `pom.xml`:

- `${jooq.version}`, `${postgresql.version}`, and `${jooq.codegen.jdbc.*}` must come from BOMs, build properties, or CI secrets. Never commit passwords.
- Generator version X must align with runtime jOOQ version Y; pin versions per your project matrix.
- The plugin runs in its own **classloader/dependency realm**; an application `runtime` JDBC driver is not automatically visible to the plugin.
- `inputSchema=app` is the PostgreSQL source schema, not a Java package or runtime `search_path`.
- `includes`/`excludes` filter metadata using generator regex matching, not SQL `LIKE`.
- Credentials should belong to a codegen-only identity on an ephemeral database.
- With custom converters or forced types, generated output must compile with those converter classes on the classpath.
- `phase=generate-sources` does not run Flyway before the plugin unless the build pipeline orchestrates it explicitly.

### 7.1. Phase Ordering

~~~text
CI:
  provision isolated PostgreSQL
  apply Flyway/Liquibase migrations
  mvn generate-sources
    jOOQ codegen introspects migrated PostgreSQL
  mvn compile
  mvn test / integration tests
  package and deploy
~~~

Having `spring.flyway.enabled=true` run migrations on application startup **does not** make the Maven generator wait for application startup. Migrations must run prior to codegen during the build.

### 7.2. Metadata Privileges Differ from DML Privileges

The generator needs metadata visibility on the target schema, not permission to update production business rows. A PostgreSQL introspection role typically needs schema `USAGE` and metadata/object read access for your version; never grant unconditional `SUPERUSER` or reuse runtime DML credentials.

### 7.3. When Opening a DB During Builds Is Not Possible

You can use jOOQ DDL-based metadata (`DDLDatabase` or version-compatible `jooq-meta` extensions), metadata snapshots, or commit CI-verified generated sources. Keep in mind SQL parsers may miss PostgreSQL extensions, routines, partial indexes, or custom types; always validate with PostgreSQL integration tests.

## 8. Gradle Generator: Build Classpath vs. Runtime Classpath

An illustrative approach independent of any third-party community plugin uses a `JavaExec` task:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<supported-boot-version>'
}

configurations {
    jooqGenerator
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jooq'
    runtimeOnly 'org.postgresql:postgresql'

    jooqGenerator "org.jooq:jooq-codegen:${jooqVersion}"
    jooqGenerator "org.postgresql:postgresql:${postgresqlVersion}"
}

def generatedDir = layout.buildDirectory.dir('generated-src/jooq')

tasks.register('generateJooq', JavaExec) {
    group = 'code generation'
    description = 'Generate jOOQ sources from migrated schema'
    classpath = configurations.jooqGenerator
    mainClass = 'org.jooq.codegen.GenerationTool'

    args 'src/main/jooq/jooq-config.xml'

    inputs.file('src/main/jooq/jooq-config.xml')
    outputs.dir(generatedDir)
}

sourceSets {
    main {
        java {
            srcDir generatedDir
        }
    }
}

tasks.named('compileJava') {
    dependsOn 'generateJooq'
}
~~~

Assumptions to complete before using this pattern:

1. `jooqVersion` and `postgresqlVersion` are pinned, compatible project properties.
2. The XML config specifies `build/generated-src/jooq` as its target directory and connects to the right metadata source.
3. The build provisions and migrates the DB before `generateJooq` executes.
4. If generated code references Postgres extension types, add the matching generator dependencies.
5. This task never runs on production pods; sources compile prior to deployment.
6. Source paths, task inputs/outputs, and multi-module dependencies are verified.

### 8.1. Caching and Incremental Build Risks

If Gradle tracks only the XML file without knowing **migrations or DB metadata** changed, it can mark the task `UP-TO-DATE` and retain stale generated files. Model migration scripts/schema artifacts as task inputs or force regeneration in CI verification. Never treat a green incremental Gradle build as proof codegen matches the DB.

### 8.2. Official and Community Gradle jOOQ Plugins

Official jOOQ Gradle codegen support exists in newer versions alongside popular community plugins. Their DSLs, task names, and edition settings **differ**. Pick one plugin, consult docs for your exact release, align the dependency BOM, and never mix `nu.studer.jooq` configuration syntax with `org.jooq.jooq-codegen` without verification.

### 8.3. Runtime Never Opens a Generator Connection

~~~text
generateJooq (build-time):
   generator JDBC metadata source -> .java files

compileJava:
   .java -> classes inside application artifact

bootRun (runtime):
   Hikari DataSource -> JDBC query via DSLContext
~~~

The runtime application still needs credentials to query PostgreSQL, yet that should be a **runtime DB role**, separate from the build-time codegen account. Separating credentials reduces blast radius.

## 9. Configuring Target Package, `inputSchema`, Naming, and Generation Flags

Generator configuration fragment:

~~~xml
<generator>
  <name>org.jooq.codegen.JavaGenerator</name>
  <database>
    <name>org.jooq.meta.postgres.PostgresDatabase</name>
    <inputSchema>app</inputSchema>
    <includes>orders|order_outbox</includes>
  </database>
  <generate>
    <records>true</records>
    <pojos>true</pojos>
    <daos>false</daos>
    <javaTimeTypes>true</javaTimeTypes>
  </generate>
  <target>
    <packageName>com.example.db.jooq</packageName>
    <directory>build/generated-src/jooq</directory>
  </target>
</generator>
~~~

Flags and XML elements can vary across jOOQ major/minor releases; verify against the XML schema and documentation for your exact version.

### 9.1. `target.directory` Is Not a Database Schema

- `target.directory`: filesystem path where `.java` files are emitted.
- `target.packageName`: root Java package.
- `inputSchema`: source database namespace inspected by the generator.
- `outputSchema`: schema name emitted in generated metadata when remapping.
- `outputSchemaToDefault`: controls schema qualification where supported.
- `inputCatalog`/`outputCatalog`: catalog mapping on dialects/databases supporting catalogs.

Setting `target.directory=build/generated-src/jooq` **does not create** a PostgreSQL schema named `jooq`.

### 9.2. Generated Names and Naming Strategies

An SQL table `order_outbox` typically generates class `OrderOutbox`; column `event_id` becomes constant `EVENT_ID`. Exact generated layout depends on the naming strategy and jOOQ version. Changing a Java naming strategy can break imports across the codebase even when physical DB names remain unchanged.

Never edit `Orders.java` to rename `order_status` to `status`; to rename an SQL column, plan a migration and compatibility rollout. To adjust only the Java-facing names, configure a reviewed and tested custom naming strategy/mapping.

### 9.3. Records, POJOs, and DAOs

| Generated Artifact | When Useful | Things to Watch |
| --- | --- | --- |
| Table / Field objects | Type-safe SQL DSL | Reflects a build-time snapshot |
| Records | Reading/writing row values | Not a JPA entity session |
| `Keys` | PK/FK/unique metadata | Does not create constraints |
| POJOs | Repository mapping | Never expose directly as wire contracts |
| DAOs | Simple CRUD convenience | Does not replace custom SQL/transactions |
| Enum types | Domain/DB enum mapping | Adding new enum values can break older readers |
| Routines / sequences | Vendor-specific objects | Privilege, version, and edition rules |

Generate only the artifacts you actually use. A service centered on SQL DSL and outboxes often skips DAOs because atomic idempotency and claiming require custom SQL.

### 9.4. Codegen Must Never Print Secrets to Logs

Generators may log JDBC URLs, metadata, or config when misconfigured for debugging. Inject usernames/passwords via build secrets and avoid printing plugin configs or unredacted `--debug` logs. Never point the generator at production databases.

## 10. Forced Types, Converters, and Semantic Types

jOOQ maps SQL column types to default Java types or custom ones via `forcedTypes`, converters/bindings, and naming rules.

### 10.1. Verify Type Mappings in Generated Source

| PostgreSQL | Typical Java / jOOQ Type | Required Tests |
| --- | --- | --- |
| `BIGINT` | `Long` | Overflow / nullability |
| `INTEGER` | `Integer` | Absent/null vs. zero |
| `UUID` | `java.util.UUID` | Stable identity and serialization |
| `TIMESTAMPTZ` | `OffsetDateTime` (per version/config) | Offset and instant semantics |
| `TIMESTAMP` | `LocalDateTime` | Timezone assumptions |
| `JSONB` | `org.jooq.JSONB` or converter | Schema versioning and parsing |
| `NUMERIC(p,s)` | `BigDecimal` | Scale and precision |
| `CHAR(3)` | `String` | Padding and ISO currency semantics |
| PostgreSQL `ENUM` | Generated enum / user type | Compatibility on new values |
| `ARRAY` | Arrays/list binding (driver-dependent) | Element types and portability |

Never guess that generated `ORDERS.AMOUNT_MINOR` is `Long` when custom forced types or different source DBs are involved. Inspect the actual generated class signature and run PostgreSQL round-trip tests.

### 10.2. Converter Classes Are Runtime Dependencies

Suppose SQL `CHAR(3)` maps to a `CurrencyCode` value object. When generated fields reference a custom converter, `CurrencyCodeConverter` must be present on both compile and runtime classpaths. The generator emits **references** to your converter—it does not write business converters for you.

### 10.3. Nullability in Java vs. SQL

`NOT NULL`, defaults, generated values, and `CHECK` constraints belong to the database. Java nullability annotations on records/POJOs assist static analysis or validation policies, not DB enforcement. During rolling deployments, immediately adding a `NOT NULL` column can break older writers even if the newly generated Java compiles cleanly.

### 10.4. `DATE`/`TIMESTAMP` and Monetary Amounts

Changing `TIMESTAMP` to `TIMESTAMPTZ` can shift timezone semantics for historical rows. Widening `amount_minor` from `INTEGER` to `BIGINT` shifts generated Java signatures from `Integer` to `Long`. Treat compiler errors as helpful warnings—they **never replace backfills, data migrations, or API contract reviews**.

### 10.5. Database Extension Types

PostgreSQL `citext`, arrays, custom domains, user enums, or PostGIS introduce special metadata and codec needs. They may require extensions, jOOQ commercial editions, or forced converters; verify exact jOOQ/driver support before adopting them rather than assuming `SQLDialect.POSTGRES` handles every extension.

 
## 11. Schema Drift Across Migrations, Generated Source, and Runtime Databases

An integration pipeline has at least **four states** that must stay synchronized:

~~~text
Migration scripts in Git (V12)
  -> Metadata DB used by generator (V12?)
  -> Generated Java source (V12?)
  -> Deployed runtime DB (V12?)
~~~

Even a single mismatched state causes compile failures, query failures, or silent data bugs. A successful generator run against staging does not guarantee production shares the same schema.

### 11.1. Forms of Drift

| Drift | Symptom | Action |
| --- | --- | --- |
| New migration, stale generated code | Java lacks `ORDERS.CURRENCY` | Regenerate from migrated DB |
| Generated code V12, production DB V11 | SQLSTATE `42703` undefined column | Apply migrations in proper order |
| DB drops column still referenced by old Java | SQL errors post-deploy | Use expand–migrate–contract |
| Generator reads `public`, migrations target `app` | Missing or wrong generated tables | Fix `inputSchema` |
| Generator reads manually edited DB | Nondeterministic codegen diffs | Use fresh PostgreSQL + migrations |
| `SQLDialect` mismatches runtime DB | Divergent syntax, types, or SQL emulation | Fix dialect and driver |
| Codegen and runtime jOOQ versions diverge | Compile or linkage errors | Pin compatible versions |
| Converter lags behind SQL type change | Decode/mapper exceptions | Update forced types and converters |
| Application injects wrong `DSLContext` | Queries hit the wrong datasource | Add qualifiers and transaction tests |
| Runtime user lacks privileges | SQLSTATE `42501` | Grant permissions per least privilege |

### 11.2. Flyway/Liquibase as the Single Source of Truth

Standardize consistently:

- Versioned SQL migrations in Git govern physical schema evolution.
- Codegen executes **after** applying migrations to an isolated PostgreSQL instance.
- Generated classes are regenerated, never hand-edited.
- Runtime databases pass migration history/version checks before traffic shifts to code using new schema objects.
- Database migrations and application rollouts maintain a compatibility window for older pods, batch jobs, and downstream readers.

If a project uses a different schema-first workflow, document its canonical source, build artifacts, and migration discipline explicitly. Never allow hand-edited generated Java and manual SQL patches to compete as "sources of truth."

### 11.3. Commit Generated Sources or Regenerate on Build?

| Option | Pros | Risks | Required Gate |
| --- | --- | --- | --- |
| Do not commit | Less Git noise; always fresh | Devs/CI need generator metadata access | Reproducible build |
| Commit generated code | Easy IDE/offline work and diff review | Forgetting to regenerate; merge conflicts | Clean regenerate + diff check |
| Shared generated JAR | Reused across modules | Tight schema/version coupling | SemVer / internal artifact compatibility |
| Generate from staging DB | Quick for small teams | Drift, races, credential exposure | Phase out in favor of ephemeral DB |

No single option fits every organization. What matters is **reproducibility from migration sources**, and having CI fail loudly on drift rather than silently shipping stale classes.

### 11.4. Codegen Does Not Run Migrations Automatically

A Maven generator bound to `generate-sources` does not wait for Spring Boot startup to run Flyway. A Gradle codegen task wired before `compileJava` does not automatically know which version a database is on. **Order build steps explicitly** using Testcontainers lifecycles or CI provisioning jobs.

### 11.5. Database Schema Is a Contract Across Code Versions

During a rolling deployment with two pods:

~~~text
Pod A: generated classes V11
Pod B: generated classes V12
DB: schema V12
~~~

Additive changes let both pods coexist. Renames, drops, or tightened constraints can break Pod A's `INSERT`s or `SELECT`s. In Spring Integration flows, also account for batch consumers, outbox relays on older versions, and historical row replays.

## 12. Expand–Migrate–Contract and Deployment Boundaries

Assume schema V11:

~~~sql
CREATE TABLE app.orders (
    id BIGINT PRIMARY KEY,
    order_id VARCHAR(120) UNIQUE NOT NULL,
    amount_minor INTEGER NOT NULL,
    legacy_total VARCHAR(40)
);
~~~

Goals:

- Widen `amount_minor` to `BIGINT`.
- Add `currency`.
- Drop `legacy_total` once `amount_minor` is in full use.

### 12.1. EXPAND: Add Fields Safely for Older Writers

~~~sql
ALTER TABLE app.orders
    ADD COLUMN currency CHAR(3);
~~~

Adding it as nullable initially lets older pods keep inserting. New readers must handle `null`/missing values semantically (never guessing `USD` or `VND` for historical rows without guarantees).

### 12.2. MIGRATE: Backfill and Roll Out Readers/Writers

~~~text
1. Deploy new reader supporting missing currency.
2. New writer starts setting currency.
3. Backfill old rows using authoritative historical records.
4. Verify no invalid or unknown currencies remain.
5. Track all old pods, scheduled jobs, ETL consumers.
6. Observe rollback window and aggregate data counts.
~~~

Adding a required `NOT NULL` column before retiring old writers triggers `NOT NULL` violations. V12 codegen types may look spotless while migration sequencing still breaks production.

### 12.3. CONTRACT: Tighten Constraints and Remove Legacy Columns

~~~sql
ALTER TABLE app.orders
    ALTER COLUMN currency SET NOT NULL;
~~~

Tighten constraints only after every writer populates `currency` and historical rows are backfilled. Drop `legacy_total` in a separate migration/release once no consumer reads it.

### 12.4. Widening Integers

Changing `INTEGER` → `BIGINT` impacts SQL types, generated Java (`Integer` → `Long`), and REST/broker contracts. Never treat Java compiler errors as mere nuisances—they warn you to update mappings, numeric bounds, and budgets. On huge tables, DDL may take locks or rewrite tables depending on PostgreSQL version and operation; plan online migrations on realistic DBs rather than running unassessed DDL during peak traffic.

### 12.5. Code Rollback Is Not Data Rollback

If V12 code writes a new `JSONB` shape or enum value, rolling back to V11 code can fail reading those rows. Maintain forward reader compatibility, feature flags, two-phase releases, or versioned mappings per policy.

## 13. Transaction Boundaries: jOOQ, Spring JDBC, and Outboxes

### 13.1. Spring `@Transactional`

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public OrderReceipt confirm(ConfirmOrder command) {
        OrderReceipt result = orders.confirm(command);
        outbox.persistOrderConfirmed(
                command.operationId(), result.orderId());
        return result;
    }
}
~~~

`OrderRepository`, `OutboxRepository`, `ConfirmOrder`, and `OrderReceipt` are application types. **Both repositories must use the same transactional datasource/connection** to make the SQL update and outbox insert atomic. If one repository uses a `DSLContext` for DB A and the other uses `DataSource` B, local `@Transactional` cannot enforce atomicity across databases.

### 13.2. jOOQ Transaction API

When using jOOQ-managed transactions instead of Spring annotations:

~~~java
import org.jooq.DSLContext;
import org.jooq.impl.DSL;

public class OrderTransactionalRepository {

    private final DSLContext dsl;

    public OrderTransactionalRepository(DSLContext dsl) {
        this.dsl = dsl;
    }

    public void markConfirmed(long orderId) {
        dsl.transaction(configuration -> {
            DSLContext tx = DSL.using(configuration);

            tx.update(ORDERS)
                    .set(ORDERS.ORDER_STATUS, "CONFIRMED")
                    .where(ORDERS.ID.eq(orderId))
                    .execute();

            tx.insertInto(ORDER_OUTBOX)
                    .set(ORDER_OUTBOX.EVENT_ID,
                            java.util.UUID.randomUUID())
                    .set(ORDER_OUTBOX.ORDER_ID, "ORD-" + orderId)
                    .set(ORDER_OUTBOX.EVENT_TYPE, "OrderConfirmed")
                    .set(ORDER_OUTBOX.SCHEMA_VERSION, 1)
                    .set(ORDER_OUTBOX.PAYLOAD,
                            org.jooq.JSONB.valueOf("{}"))
                    .set(ORDER_OUTBOX.STATUS, "NEW")
                    .execute();
        });
    }
}
~~~

This is **illustrative logic**, omitting idempotency, real outbox payloads, domain validation, and authorization. Generated fields/types and imports must match your schema and generator. When using Spring-managed `@Transactional`, stick to one clear transaction ownership model and avoid mixing incompatible jOOQ transaction managers.

### 13.3. Spring `TransactionProvider` and Connections

Spring Boot jOOQ auto-configuration integrates transactions with Spring's `DataSource` and transaction manager when configured appropriately. Manually creating `DSLContext` via `DSL.using(SQLDialect.POSTGRES)` or supplying an isolated connection pool can break `@Transactional` propagation.

Write an integration test proving:

~~~text
BEGIN transaction
  update app.orders
  insert app.order_outbox
force exception before commit
ASSERT both changes rolled back
~~~

Never merely mock `DSLContext` and assert method invocations.

### 13.4. Transactions Do Not Span Kafka or HTTP

An SQL transaction is not ACID with Kafka producer sends or partner HTTP APIs. **Outbox pattern**: update the order and insert the outbox row in the same SQL `COMMIT`, then have a relay publish after commit with retries and deduplication.

~~~mermaid
sequenceDiagram
    participant S as OrderService
    participant D as PostgreSQL
    participant R as OutboxRelay
    participant K as Kafka
    S->>D: BEGIN + update order + insert outbox E-100
    D-->>S: COMMIT
    R->>D: Claim pending outbox
    R->>K: Publish event E-100
    K-->>R: Broker ACK
    R->>D: Mark sent
    Note over R,K: ACK may be lost; publish can repeat
~~~

### 13.5. Codegen and Business Idempotency

Generated primary-key metadata does not replace **unique business keys**. To achieve exactly-once business effects across duplicate HTTP or broker requests, enforce unique `operation_id` or `(consumer, event_id)` constraints in the DB, handle duplicates inside the transaction, return the persisted receipt, and keep `eventId` stable when the relay retries.

## 14. SQL Errors: Schema Mismatch, Permissions, and Concurrency

jOOQ provides `DataAccessException` and related exception types. JDBC root causes can carry SQLSTATE and vendor error codes. Classify failures instead of retrying every failed query.

| PostgreSQL SQLSTATE | Meaning | Response |
| --- | --- | --- |
| `42P01` | Undefined table | Schema/migration mismatch; fail fast |
| `42703` | Undefined column | Generated/runtime drift |
| `42501` | Insufficient privilege | `GRANT`/role issue; do not hot-retry |
| `23505` | Unique violation | Deduplication or business conflict |
| `23503` | Foreign key violation | Data invariant / ordering issue |
| `23502` | `NOT NULL` violation | Validation or rolling-deploy mismatch |
| `23514` | `CHECK` violation | Invalid business data |
| `40001` | Serialization failure | Controlled retry of the whole transaction |
| `40P01` | Deadlock detected | Bounded transaction retry |
| `08xxx` | Connection exception | Network/availability issue; `UNKNOWN` outcome if commit unclear |

### 14.1. `COMMIT` Outcome `UNKNOWN`

If the client sends SQL `COMMIT` and the network resets before the response arrives, the application cannot tell whether the DB committed. Never retry "create order" with a brand-new random `operationId`; rely on unique business keys and status lookups.

### 14.2. Dialect Errors vs. SQLSTATE Schema Errors

Rendering SQL under the wrong dialect causes syntax errors (`42601`) or unsupported operators/functions. Diagnose by checking:

1. What is the runtime `DSLContext.configuration().dialect()`?
2. What are the actual JDBC URL, DB product, and version?
3. How are the SQL and bind placeholders rendered?
4. What is the PostgreSQL error position and SQLSTATE?
5. Which table/field metadata did the generator use to build the query?

If the DB user lacks privileges, fixing the dialect will not resolve SQLSTATE `42501`.

### 14.3. Never Log Bind Values Containing PII

In production, avoid `ParamType.INLINED` or loggers printing raw SQL with customer emails, payment metadata, or secret tokens. Log normalized SQL shapes, statement types, durations, and `SQLSTATE` with redaction. Restrict access and retention on JDBC/jOOQ diagnostic logs.

## 15. SQL Injection and Dynamic Schemas/Identifiers

Typed DSL binds **data values**:

~~~java
dsl.selectFrom(ORDERS)
        .where(ORDERS.ORDER_ID.eq(requestOrderId))
        .fetchOne();
~~~

Normally jOOQ binds parameters instead of concatenating request strings into SQL. However, dynamic **identifiers**, raw SQL fragments, and DSL templates can still introduce SQL injection if mishandled.

### 15.1. Never Concatenate Table or Column Names from HTTP Input

~~~java
// Conceptual ANTI-PATTERN:
String query = "SELECT * FROM " + userProvidedTableName;
~~~

Table names cannot be bound as data values. When clients choose sorting or filtering fields, allowlist approved generated `Field`s and use `DSL.name(...)`/typed DSL over validated identifiers. Avoid passing untrusted strings to `DSL.field(String)`.

### 15.2. Multi-Tenant Dynamic Schemas

A client passing `tenantId` does not automatically authorize access to an arbitrary schema by name. When mapping tenant → schema, derive tenant identity from authenticated principals and domain authorization, restrict to allowed schemas, and enforce DB grants/RLS. Test cross-tenant isolation against a real datasource.

### 15.3. SQL Logging and Parameters

`renderInlined()` and inlined diagnostics can leak sensitive data into logs. Debug using sanitized query shapes, SQLSTATE, and traces; never store raw credit card numbers, PII, or access tokens in event logs.

## 16. Reproducible CI/CD Codegen Pipeline

Reference pipeline:

~~~mermaid
flowchart TD
    A["Checkout migrations, generator config"] --> B["Start PostgreSQL Testcontainers/ephemeral DB"]
    B --> C["Apply all migration versions"]
    C --> D["Run jOOQ code generation"]
    D --> E["Compile generated + handwritten source"]
    E --> F["Compare generated diff if committed"]
    F --> G["Run PostgreSQL integration tests"]
    G --> H["Publish immutable build artifact"]
    H --> I["Deploy migration then compatible application"]
~~~

### 16.1. CI Invariants

- Start a fresh schema DB from a pinned PostgreSQL image version.
- Migrate to the expected version with Flyway/Liquibase.
- Point jOOQ codegen strictly to **that DB**, never accidentally to local or staging.
- Keep generated output deterministic enough for clean reviews.
- Verify runtime jOOQ and generator versions are compatible.
- Compile and test the application against the same target dialect.
- Ensure no credentials appear in generated Java, CI logs, or build artifacts.
- Keep migration ordering compatible with running older pods.
- Allow no untracked manual schema modifications hidden in CI setup.

### 16.2. Determinism

Generated source diffs can shift due to:

- Upgrading jOOQ or JDBC driver versions.
- Metadata row ordering or configuration flags.
- Non-deterministic migration ordering.
- Changing generator naming strategies.
- Wrong `inputSchema`.
- Manual edits in a shared database.
- Timestamps, banners, or generation comments depending on version/config.
- Differing filesystem paths.

Avoid brittle golden-diff tests sensitive to timestamps if your generator includes options to omit nondeterministic headers. Focus on schema metadata semantics and build reproducibility.

### 16.3. Codegen Drift Verification

When teams commit generated Java, CI can enforce:

~~~text
clean build
generate sources from fresh migrated DB
compare generated output to committed tree
if difference unexpected: fail and request regeneration
~~~

Do not let CI silently auto-commit regenerated files on every PR unless explicitly intended; review schema-generated changes like any other code change.

## 17. Testing Correct Dialect and Schema Against PostgreSQL

### 17.1. Why H2 Tests Are Insufficient

H2 in PostgreSQL compatibility mode still diverges from PostgreSQL on:

- `JSONB` types and operators.
- Partial indexes.
- `INSERT ... ON CONFLICT`.
- Row locking and `SKIP LOCKED`.
- Transaction isolation and deadlock behavior.
- `TIMESTAMPTZ`, UUIDs, arrays, and enums.
- SQL planner, constraints, and sequences.
- Metadata introspection and generator output.

For these features, running real PostgreSQL via Testcontainers or an ephemeral DB provides faithful verification.

### 17.2. Spring Boot Integration Test Skeleton

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.jooq.DSLContext;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest
class OrderJooqIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.jooq.sql-dialect", () -> "POSTGRES");
    }

    @Autowired
    DSLContext dsl;

    @Test
    void usesPostgresDialect() {
        assertEquals(
                org.jooq.SQLDialect.POSTGRES,
                dsl.dialect());
    }
}
~~~

This test skeleton requires classpath migrations, generated models, and test resource configuration. When Testcontainers starts a fresh database, Spring Boot/Flyway must apply migrations before queries execute. `postgres:16-alpine` illustrates a pinned image; pick a version aligned with production and security policy, and never hardcode production secrets in tests.

### 17.3. Round-Trip Test for Generated Columns

~~~text
Given app.orders migrated to V12
When jOOQ inserts with generated ORDERS.CURRENCY and returning ID
Then PostgreSQL accepts the SQL
And returned Java types match generated mappings
And SELECT fetch maps currency/amount correctly
~~~

This tests **both generated code and the runtime schema**, providing far stronger evidence than unit tests comparing `.getSQL()`.

### 17.4. Transaction Rollback Test

~~~text
Given app.orders and app.order_outbox are empty
When @Transactional service updates order, inserts outbox
And throws before COMMIT
Then no business state or outbox intent is committed
~~~

Test against a real database using the production transaction manager and `DSLContext`. If the application uses multiple datasources, test every transaction boundary separately.

### 17.5. Concurrency and Unique-Key Test

~~~text
Given same operationId K-100 sent twice concurrently
When both workers attempt to insert reservation/receipt
Then one logical business effect exists
And duplicate attempt receives previous receipt/conflict
And eventId/outbox dedupe is preserved
~~~

Never merely mock repository returns: real SQL unique constraints and transaction races are the actual proof.

### 17.6. Schema Migration Compatibility Test

~~~text
Old generated client V11 + DB schema V12:
  must continue to read/write supported fields

New generated client V12 + DB schema V11:
  must not be deployed for code paths requiring V12 fields

After Flyway V12 and regeneration:
  new client V12 passes CRUD/upsert/lock/JSONB tests
~~~

When graceful rolling deployments are required, test both old and new builds against the expanded schema; only drop legacy fields in the contract phase.

## 18. Observability: Query Shape, Execution, and Migration State

Do not measure only whether `dsl.select(...).fetch()` succeeded. Track **dialect, database version, schema, pool, and SQLSTATE**.

| Signal | Why Needed |
| --- | --- |
| Configured `DSLContext` dialect | Detects wrong vendor SQL rendering |
| JDBC database product/version | Detects target DB mismatch |
| Database migration version | Compares generated vs. runtime schema |
| `current_database`, `current_schema` | Detects wrong endpoint or schema |
| Query latency p50/p95/p99 | Reveals SQL performance and locks |
| Query errors by SQLSTATE | Separates schema drift, auth, and connection issues |
| Hikari active/pending | Detects pool saturation |
| Connection acquisition latency | Reveals pool bottlenecks |
| Row counts | Flags N+1 queries or full table scans |
| Outbox backlog oldest age | Tracks relay consistency |
| DB lock waits / deadlocks | Exposes concurrency contention |
| Codegen duration/version | Tracks build reliability |
| Generated source drift count | Catches CI schema mismatches |
| Migration failures | Deployment readiness gate |

Micrometer/Actuator and jOOQ `ExecuteListener`/diagnostics can supply or assist part of this instrumentation depending on version and setup. These metric names are suggestions—**do not assume the framework auto-generates all of them**.

### 18.1. SQL Listeners and Tracing

jOOQ offers listener APIs around query execution lifecycles. A custom `ExecuteListener` can record timing, statement type, SQLSTATE, and propagate trace context with transactions. Never log sensitive bind variables or perform blocking network exports inside listener callbacks.

### 18.2. Cardinality

Reasonable tags:

~~~text
database=orders
dialect=POSTGRES
operation=select|insert|update
error_sqlstate=42703|42501|23505
schema_version=12
~~~

Never put `orderId`, raw SQL with literal data, customer emails, JWT tokens, or full JDBC URLs with passwords into Prometheus tags. Query IDs/hashes should normalize SQL shapes via tooling, with redaction and bounded cardinality.

### 18.3. Error Budgets

If codegen drift causes every query referencing `ORDERS.CURRENCY` to fail, that is a release/configuration bug—not a transient database outage. Circuit breakers and retries cannot fix SQLSTATE `42703`; fail fast, roll back the deployment, or apply the approved migration.

## 19. Runbook When jOOQ Queries or Codegen Fail

| Symptom | Likely Cause | Inspection Steps |
| --- | --- | --- |
| `ORDERS.CURRENCY` fails to compile | Stale generated Java | Check codegen DB schema version and regenerate |
| Empty generated files | Wrong `inputSchema` or regex | Check `current_schema` and generator logs |
| Codegen JDBC auth fails | Wrong build secret, URL, or TLS | Check metadata role, endpoint, and CA |
| Codegen reports missing driver | Driver absent from plugin classpath | Check Maven plugin deps / Gradle generator config |
| Codegen runs but output is uncompiled | Wrong source set or target directory | Check generated directory and task dependencies |
| Gradle task `UP-TO-DATE` despite migration edit | Task inputs omit migrations | Model inputs properly; run clean CI regeneration |
| SQLSTATE `42P01` | Table or schema missing | Check migrations, `inputSchema`, and runtime DB |
| SQLSTATE `42703` | Missing column | Check generated vs. runtime schema drift |
| SQLSTATE `42501` | Runtime DB role lacks `GRANT` | Verify schema `USAGE` and table/sequence privileges |
| SQL syntax fails on PostgreSQL | Wrong dialect or raw vendor SQL | Inspect `DSLContext.dialect()` and rendered SQL |
| `JSONB` operator fails | Test DB/dialect mismatch | Test against real PostgreSQL |
| Wrong `RETURNING` result | DB dialect/version semantics | Test real JDBC round-trip |
| `FOR UPDATE` behaves unexpectedly | Lock, isolation, or dialect differences | Check transaction and DB version |
| Converter `ClassNotFound` | Missing compile/runtime class | Check `ForcedType`/converter dependency |
| Type mismatch after migration | Stale Java signatures | Regenerate and update mappings |
| Outbox duplicate events | Ack loss / retries | Enforce stable `eventId` and inbox dedup |
| Database pool exhaustion | Long transactions or N+1 queries | Check Hikari pending and execution traces |
| Postgres TLS verification fails | CA/hostname mismatch | Check `sslmode=verify-full` and SANs |
| Rolled-back code fails on new values | Forward data incompatibility | Enforce versioned mapping/migration plan |

### 19.1. Investigation Order

1. Identify which `DSLContext` ran the query and the runtime JDBC URL / DB product.
2. Check dialect, generated package/version, and migration version.
3. Read the SQLSTATE and root cause, not merely `DataAccessException` text.
4. Inspect `current_schema`, `search_path`, privileges, and actual table definitions.
5. Check whether the SQL uses bind values, raw fragments, or vendor-specific features.
6. Compare generated SQL against the exact PostgreSQL dialect and reproduce on an isolated DB of the same version.
7. Inspect Hikari pool, lock, and transaction durations if timeouts occur.
8. Confirm CI codegen regenerated cleanly from a freshly migrated schema.
9. Fix the migration, generator config, or repository code—never hand-patch generated Java.
10. Verify errors and retries do not introduce duplicate business effects afterward.

## 20. Common Anti-Patterns

| Anti-Pattern | Why It Is Wrong | Replacement |
| --- | --- | --- |
| Editing generated `Orders.java` directly | Overwritten next run; no real DB column | Migrate schema then regenerate |
| Running codegen during production startup | Couples build to runtime; secret/race risks | Generate at build time |
| Pointing CI codegen at production DB | Privilege and drift hazards | Use ephemeral DB from migrations |
| Using H2 dialect for PostgreSQL production | Syntax, locking, and type mismatches | Use PostgreSQL Testcontainers |
| Changing `SQLDialect` to "upgrade the DB" | Does not alter database engine | Upgrade DB/driver/config via migrations |
| Ignoring `inputSchema` | Generates wrong or zero objects | Specify schema explicitly |
| Confusing `target.directory` with `outputSchema` | Filesystem path vs. DB namespace | Configure each distinctly |
| Generating from hand-edited staging DB | Nondeterministic output | Generate from clean migrations |
| Leaving generator/runtime versions unpinned | Java API or linkage mismatches | Pin via BOM |
| Gradle caching ignoring migration files | Stale generated classes | Declare migration inputs / CI verify |
| Generating DAOs for every domain blindly | Coupling and build bloat | Enable only what is used |
| Publishing `OrdersRecord` straight to Kafka | Leaks DB schema and PII | Use dedicated event DTOs |
| `SELECT *` in public contracts | Column changes break payloads | Project explicit fields |
| Concatenating HTTP input into SQL identifiers | SQL injection / cross-tenant leaks | Allowlist fields and schemas |
| Using `search_path` as tenant authorization | Not security isolation | Use DB grants, RLS, and domain auth |
| Holding JDBC transactions across partner HTTP calls | Locks and pool saturation | Use outbox/saga |
| Treating SQL unique violation as network error | Wrong retry behavior | Handle with business idempotency |
| Catching all SQL exceptions and retrying infinitely | DDL/auth bugs never self-heal | Use an SQLSTATE taxonomy |
| Ignoring migration versions at deploy | Production schema drift | Enforce migration readiness gates |
| Rolling back a JAR thinking data rolled back | New values remain in DB | Plan forward/backward compatibility |
| Logging bind parameters containing PII | Data leak | Redact and log normalized SQL |

## 21. Production Checklist for jOOQ + JDBC

### A. Dialect and Runtime

- [ ] Exact DB engine, version, and driver are known and paired with a supported dialect.
- [ ] `DSLContext` uses the right `DataSource`, credentials, SSL, and transaction manager.
- [ ] Multiple datasources have explicit qualifiers and boundaries.
- [ ] No H2-only tests substitute for PostgreSQL integration tests when vendor features are used.
- [ ] Raw SQL fragments bind values and never accept arbitrary client identifiers.
- [ ] SQL errors are classified by SQLSTATE rather than retried indiscriminately.
- [ ] Locking, upserts, `JSONB`, timezones, and generated keys are tested on the target DB.

### B. Schema and Codegen

- [ ] One canonical source owns versioned schema migrations.
- [ ] Codegen metadata comes from an isolated DB migrated to the expected version.
- [ ] `inputSchema`, includes/excludes, Java package, and target directory are accurate.
- [ ] Generator/runtime jOOQ, driver, and plugin versions are compatible.
- [ ] Generated code is never hand-edited; commit vs. regenerate policy is enforced.
- [ ] Gradle/Maven task graph enforces migrate → generate → compile → test.
- [ ] CI detects codegen drift after migrations.
- [ ] No production codegen credentials appear in builds, artifacts, or logs.
- [ ] Generated records are never exposed directly as HTTP/broker wire contracts.
- [ ] Forced types, converters, and nullability are verified with round-trip tests.

### C. Migration and Reliability

- [ ] Migrations deploy before application code accesses new columns or tables.
- [ ] Old and new pods remain compatible during rolling deployments.
- [ ] Expand–migrate–contract governs renames, drops, and new required columns.
- [ ] Historical data backfills use authoritative sources and progress metrics.
- [ ] Runtime, migration, and codegen DB roles are separated under least privilege.
- [ ] Outbox and business updates share the same local SQL transaction.
- [ ] Idempotency uses stable `operationId`/`eventId` and database uniqueness.
- [ ] Network drops on JDBC `COMMIT` are treated as `UNKNOWN` until reconciled.
- [ ] Transactions are never held open across slow HTTP/broker calls.
- [ ] JAR rollbacks account for forward data/schema compatibility.

### D. Testing and Operations

- [ ] Integration tests run on PostgreSQL matching the production dialect/version class.
- [ ] Tests cover generated-code/runtime-schema mismatches and SQLSTATEs.
- [ ] Tests cover `JSONB`, upserts, `RETURNING`, locks, and transactions.
- [ ] Tests cover concurrency, duplicate `operationId`s, and unique constraints.
- [ ] Deployment verifies Flyway/Liquibase schema version.
- [ ] Metrics cover query latency, SQLSTATEs, Hikari, outbox lag, and build codegen drift.
- [ ] No raw SQL binds or secrets appear in logs or metric tags.
- [ ] Runbooks distinguish schema mismatch, privileges, dialect errors, and connection failures.

**Remember:** In Spring Boot Integration, **the SQL dialect governs what SQL jOOQ renders**, **the database schema defines which objects and constraints truly exist**, and **jOOQ code generation runs at build time to emit Java metadata**. Flyway, Liquibase, or your designated migration pipeline owns production schema evolution. A reliable pipeline is **migrate isolated PostgreSQL → generate jOOQ → compile → test with the real dialect → deploy compatible migrations before code**; paired with transactions, outboxes, and idempotency, it prevents both build breaks and data corruption as integration flows evolve.

## References

- [jOOQ — Manual](https://www.jooq.org/doc/latest/manual/): DSL, SQL rendering, execution, records, and transactions.
- [jOOQ — SQL Dialect](https://www.jooq.org/doc/latest/manual/sql-building/dsl-context/sql-dialects/): RDBMS-specific rendering.
- [jOOQ — Code Generation](https://www.jooq.org/doc/latest/manual/code-generation/): metadata generators and Java output.
- [jOOQ — Code Generation Configuration](https://www.jooq.org/doc/latest/manual/code-generation/codegen-configuration/): `inputSchema`, target package, generated artifacts.
- [jOOQ — Maven Plugin](https://www.jooq.org/doc/latest/manual/code-generation/codegen-maven/): Maven generator lifecycle.
- [jOOQ — Gradle Code Generation](https://www.jooq.org/doc/latest/manual/code-generation/codegen-gradle/): official Gradle support and version-specific setup.
- [jOOQ — Forced Types](https://www.jooq.org/doc/latest/manual/code-generation/codegen-advanced/codegen-config-database/codegen-database-forced-types/): custom type mappings.
- [jOOQ — Transactions](https://www.jooq.org/doc/latest/manual/sql-execution/transaction-management/): transaction APIs and providers.
- [Spring Boot — jOOQ](https://docs.spring.io/spring-boot/reference/data/sql.html#data.sql.jooq): Spring Boot integration and SQL dialect settings.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transactional `DataSource` boundaries.
- [Spring JDBC Reference](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): `DataSource`, `JdbcTemplate`, exception translation.
- [PostgreSQL — Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html): namespaces, `search_path`, and privileges.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT`, `RETURNING`.
- [PostgreSQL — SELECT](https://www.postgresql.org/docs/current/sql-select.html): locking, ordering, and pagination.
- [PostgreSQL — JSON](https://www.postgresql.org/docs/current/datatype-json.html): `JSONB` operators and indexes.
- [Flyway — Documentation](https://documentation.red-gate.com/fd): versioned migrations.
- [Liquibase — Documentation](https://docs.liquibase.com/): changesets and schema changes.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): DB-backed integration tests.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): duplicate-safe processing.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): local transaction + durable message intent.
