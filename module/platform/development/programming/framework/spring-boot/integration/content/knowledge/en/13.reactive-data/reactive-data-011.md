# Coordinating R2DBC with JDBC-Based Migration Tools

## 1. The problem in a Spring Boot integration system

Suppose an integration service ingests HTTP events, writes business state and an *outbox* record to PostgreSQL, and runs a relay publishing events to a message broker. The service adopts **Spring Data R2DBC** for non-blocking reactive data access, yet still needs controlled creation and evolution of tables, columns, indexes, and schema history.

The crux is that **R2DBC and migration tools solve two separate jobs**:

- **R2DBC** provides a `ConnectionFactory` and Reactive Streams database API well suited for non-blocking business processing in Spring WebFlux.
- **Flyway/Liquibase** manage schema versions and reference data through ordered migrations, history tracking, and drift detection. In standard relational database setups, these tools operate over **JDBC**, which is blocking I/O.
- **Spring Boot** can wire both connection mechanisms to **the exact same physical database**: JDBC handles migrations at startup or in a deployment job, while R2DBC handles runtime queries.

Having JDBC on the classpath **does not turn R2DBC queries into JDBC**. Likewise, running business logic on R2DBC **does not make Flyway/Liquibase run over R2DBC automatically**.

### Responsibility diagram

~~~mermaid
flowchart TD
    Deploy["Startup / deployment pipeline"] --> Migration["Flyway or Liquibase"]
    Migration --> JDBC["JDBC driver"]
    JDBC --> DB[("PostgreSQL: schema + data")]
    App["HTTP / broker adapter"] --> Service["Reactive service"]
    Service --> R2DBC["Spring Data R2DBC / ConnectionFactory"]
    R2DBC --> DB
    DB --> Outbox["Business tables and integration_outbox"]
~~~

| Criterion | Migration path | Runtime business path |
|---|---|---|
| Purpose | DDL, schema versioning, controlled seed data | Application reads and writes |
| Connection API | JDBC `DataSource` or Flyway/Liquibase's own JDBC connection | R2DBC `ConnectionFactory` |
| PostgreSQL URL | `jdbc:postgresql://host:5432/db` | `r2dbc:postgresql://host:5432/db` |
| Timing | Before serving traffic, or in a deployment job | During requests, messages, and scheduled jobs |
| I/O model | Blocking | Reactive, non-blocking per driver contract |
| Transactions | Managed by migration tool / database capabilities | `R2dbcTransactionManager` or `TransactionalOperator` |
| Ideal privileges | Account with necessary DDL grants | Application account restricted to DML grants |

**Core rule:** both URLs must target **the exact intended database and schema**, though they need not share the same user account. Succeeding with migrations in database A does nothing for an R2DBC app accidentally pointing at database B.

## 2. Choosing an integration approach

Two common operational patterns exist:

**Option A — migrate at application startup.** Spring Boot executes Flyway/Liquibase synchronously while building the application context; if migrations fail, startup aborts cleanly. Convenient for local development, testing, and simple deployments.

**Option B — migrate as a separate deployment step.** A CI/CD pipeline or Kubernetes Job runs the migration tool first, confirms success, and only then rolls out the new R2DBC service pods. Better suited for multi-replica clusters, long migrations, strict DDL credential isolation, or controlled rollout timing.

Never invoke migrations from controllers, message consumers, reactive operators, or request-triggered `Mono.fromCallable(...)` blocks. Offloading JDBC to a scheduler avoids blocking the event loop, yet **fails to solve** schema governance and deployment ordering.

## 3. Complete example: PostgreSQL, Flyway, and Spring Data R2DBC

This example uses Flyway to create an `integration_outbox` table, then uses R2DBC to read pending records awaiting delivery to a broker. Table names and the `event_key` column demonstrate duplicate-event prevention in integration services.

### 3.1. Declaring dependencies

For a **Spring Boot 4.x** project using the Spring Boot BOM, Maven dependencies might look like:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Flyway uses JDBC to execute migrations. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-flyway</artifactId>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

On **Spring Boot 3.x**, projects typically declare `org.flywaydb:flyway-core` instead of Boot 4's Flyway starter, alongside the matching PostgreSQL support module for your Flyway version and the JDBC driver. Keep dependency versions managed by your active Spring Boot BOM rather than mixing incompatible Flyway artifacts. The dual-URL configuration below follows the same pattern across both version lines.

Pick either Flyway or Liquibase as the **single schema-management owner**. Having both libraries active on the same database makes migration ordering and history error-prone.

### 3.2. Two independent URL configurations

`src/main/resources/application.yml`:

~~~yaml
spring:
  r2dbc:
    url: ${APP_R2DBC_URL}
    username: ${APP_DB_USER}
    password: ${APP_DB_PASSWORD}

  flyway:
    enabled: true
    url: ${MIGRATION_JDBC_URL}
    user: ${MIGRATION_DB_USER}
    password: ${MIGRATION_DB_PASSWORD}
    locations: classpath:db/migration

  sql:
    init:
      mode: never
~~~

Example environment variables during local development:

~~~text
APP_R2DBC_URL=r2dbc:postgresql://localhost:5432/integration_db
MIGRATION_JDBC_URL=jdbc:postgresql://localhost:5432/integration_db
~~~

Supply usernames and passwords via environment variables or a secret manager. In production, grant `APP_DB_USER` least-privilege DML permissions and restrict DDL rights to `MIGRATION_DB_USER` per deployment policy.

**Why configure `spring.flyway.url`?** When an R2DBC `ConnectionFactory` exists, Spring Boot does not auto-configure a default JDBC `DataSource`. Providing `spring.flyway.url` and credentials lets Flyway create its own dedicated JDBC connection without exposing a shared runtime `DataSource` to reactive services. If your project explicitly manages multiple JDBC `DataSource` beans, dedicate one specifically for Flyway so migrations never target the wrong database.

`spring.sql.init.mode: never` disables default `schema.sql`/`data.sql` execution so two mechanisms never fight over schema creation. If JPA also coexists, lock down `hibernate.hbm2ddl.auto` or `spring.jpa.hibernate.ddl-auto` so the ORM never mutates schemas behind the migration history's back.

### 3.3. Writing versioned migrations

Place `src/main/resources/db/migration/V1__create_integration_outbox.sql`:

~~~sql
CREATE TABLE integration_outbox (
    id UUID PRIMARY KEY,
    event_key VARCHAR(120) NOT NULL UNIQUE,
    destination VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_integration_outbox_status
        CHECK (status IN ('PENDING', 'SENT', 'FAILED'))
);

CREATE INDEX idx_integration_outbox_pending
    ON integration_outbox (created_at, id)
    WHERE status = 'PENDING';
~~~

Flyway discovers migrations named `V<version>__<description>.sql` with **two underscores** before the description and monotonically advancing versions. `flyway_schema_history` logs applied versions, checksums, and outcomes so completed migrations do not re-run.

When a new requirement adds retry tracking, create **a new file** `V2__add_outbox_retry_count.sql`:

~~~sql
ALTER TABLE integration_outbox
    ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
~~~

Never edit `V1` after deploying it to shared environments: its checksum changes and Flyway fails validation. Fix mistakes via subsequent migrations or controlled recovery procedures.

The DDL above targets PostgreSQL. For other databases, adapt `UUID`, `JSONB`, `TIMESTAMPTZ`, partial indexes, and transactional DDL assumptions accordingly.

### 3.4. Querying with R2DBC after migration

Example adapter reading unsent events via Spring Data R2DBC `DatabaseClient`:

~~~java
package example.integration.outbox;

import java.util.UUID;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;

record PendingEvent(UUID id, String eventKey, String destination, String payload) {}

@Repository
public class OutboxReader {
    private final DatabaseClient databaseClient;

    public OutboxReader(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<PendingEvent> findPending(int limit) {
        return databaseClient.sql("""
                SELECT id, event_key, destination, payload::text AS payload
                  FROM integration_outbox
                 WHERE status = 'PENDING'
                 ORDER BY created_at, id
                 LIMIT :limit
                """)
            .bind("limit", limit)
            .map((row, metadata) -> new PendingEvent(
                row.get("id", UUID.class),
                row.get("event_key", String.class),
                row.get("destination", String.class),
                row.get("payload", String.class)))
            .all();
    }
}
~~~

In PostgreSQL, `payload::text` casts `JSONB` to text for simple mapping; production systems may use driver JSON codecs or custom types. `findPending` returns a `Flux`: execution triggers on subscription over an R2DBC connection with **no** runtime dependency on JDBC or Flyway.

Production outbox relays also require claim/locking, status updates, retries, and redelivery handling; this `SELECT` strictly illustrates querying **a migrated table**, not a multi-worker dispatch algorithm.

### 3.5. Expected startup sequence

1. Spring Boot reads `spring.flyway.*` and `spring.r2dbc.*`.
2. Flyway connects to PostgreSQL via JDBC, checks `flyway_schema_history`, and applies pending migrations in order.
3. If any migration fails, startup aborts and readiness remains false so no broken instance serves traffic.
4. Once migrations finish, runtime data-access components use the R2DBC `ConnectionFactory`.
5. HTTP handlers, consumers, and outbox relays run against the updated schema.

Spring Boot tracks database initializers and bean dependencies during startup. Still, custom beans that **eagerly query the database during initialization** may need `@DependsOnDatabaseInitialization` or explicit ordering—never assume every `@PostConstruct` DB query automatically waits for Flyway.

## 4. Transaction boundaries and integration reliability

**JDBC migrations and R2DBC transactions live in separate boundaries.** DDL transactions opened by Flyway never merge into a request's reactive `@Transactional`. Sharing the same physical database means both paths see the same committed schema and rows—it never builds a distributed transaction across JDBC, R2DBC, and brokers.

In the outbox flow, to guarantee business state and the outbox record succeed or fail together, wrap both in **one R2DBC transaction**:

~~~java
// Conceptual illustration: both writes share one R2DBC connection/transaction.
Mono<Void> storeAndQueue(Command command) {
    return transactionalOperator.transactional(
        saveBusinessRecord(command)
            .then(insertOutboxRecord(command))
    );
}
~~~

Here `saveBusinessRecord` and `insertOutboxRecord` are R2DBC methods returning `Mono`, and `transactionalOperator` uses the matching reactive transaction manager (not copy-pasteable standalone APIs). After commit, a separate worker publishes to the broker. Receivers still need **idempotency**, because relay retries can emit duplicates despite atomic outbox writes.

Never invoke `Flyway.migrate()`, `JdbcTemplate`, or `DataSource.getConnection()` on reactive HTTP/consumer event loops. JDBC fits startup or isolated background jobs, never inline reactive request paths.

## 5. Operating migrations safely across environments

### 5.1. Development and staging

In test environments, letting Spring Boot run Flyway at startup catches missing migrations early. Run identical migration scripts on both empty databases and snapshots of populated data, verifying R2DBC APIs still read and write cleanly.

For pre-existing databases adopting Flyway, audit the live schema carefully and establish a controlled **baseline**. Never blindly enable `baselineOnMigrate` to silence errors without verifying schema parity.

### 5.2. Production and multi-replica deployments

With multiple replicas, avoid relying on application pods racing to mutate schemas while serving live traffic. Even though migration tools use locking to serialize execution, older and newer pods overlap during rolling deployments.

Typical production rollout:

1. Build artifacts containing reviewed migrations and test them against a realistic data copy.
2. Run Flyway in a dedicated deployment job with DDL privileges and the target JDBC URL.
3. Deploy the new R2DBC app pods only after the migration job succeeds; halt rollout if migration fails.
4. When migrating out-of-band, disable runtime Flyway via `spring.flyway.enabled=false` (or omit migration tools from the runtime image).
5. Monitor readiness, SQL errors, query latency, and outbox/consumer backlogs post-deploy.

For breaking schema changes, follow **expand -> migrate/backfill -> contract**: add new columns without breaking old code; roll out dual-compatible app code; backfill in batches; drop obsolete columns once no old replicas remain. On large tables, assess lock durations, concurrent index creation costs, DDL rollback limits, and live traffic impact.

### 5.3. Permissions and configuration hygiene

- Use a dedicated migration account for DDL; restrict the R2DBC runtime account to minimum operational DML privileges.
- Verify **host, port, database, schema, and `search_path`** for both paths per profile; matching database names on different hosts remain distinct databases.
- Supply passwords via secrets/external config outside source code; enable TLS per infrastructure and driver rules.
- Monitor migration history, pipeline outcomes, startup duration, `relation does not exist` errors, checksum/permission failures, and post-migration type conversion issues.
- If JDBC must also run inside the app, size JDBC and R2DBC connection pools separately—the two protocols do not share a pool.

## 6. Using Liquibase instead of Flyway

Liquibase follows the same JDBC pattern: swap Flyway configuration for Liquibase and point to your changelog:

~~~yaml
spring:
  r2dbc:
    url: ${APP_R2DBC_URL}
    username: ${APP_DB_USER}
    password: ${APP_DB_PASSWORD}
  liquibase:
    enabled: true
    url: ${MIGRATION_JDBC_URL}
    user: ${MIGRATION_DB_USER}
    password: ${MIGRATION_DB_PASSWORD}
    change-log: classpath:/db/changelog/db.changelog-master.yaml
  sql:
    init:
      mode: never
~~~

For Liquibase, add the matching dependency for your Boot version (e.g., `liquibase-core` on Boot 3.x or the Liquibase starter on Boot 4.x) plus the PostgreSQL JDBC driver. Change history lives in changelog metadata tables such as `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK`. Never enable both `spring.flyway.enabled=true` and `spring.liquibase.enabled=true` on the same schema without an intentional tool-migration plan.

| Need | Flyway | Liquibase |
|---|---|---|
| Ordered SQL migrations | Versioned SQL files (`V...__....sql`) | SQL/XML/YAML/JSON changelogs with ID/author changesets |
| Execution history | `flyway_schema_history` | `DATABASECHANGELOG` |
| Migration locking | Handled by Flyway and DB mechanism | Built-in changelog lock table |
| Pairing with R2DBC runtime | Separate JDBC configuration | Separate JDBC configuration |
| Selection fit | Simple, review-friendly SQL scripts | Rich changeset/changelog workflows and multi-format features |

Your choice depends on team schema workflows; neither tool absolves you from ensuring application versions stay schema-compatible.

## 7. Testing JDBC migrations + R2DBC together

The highest-value test is an **integration test against real PostgreSQL** (via Testcontainers), because H2 and mocks fail to reproduce PostgreSQL `JSONB`, timestamp types, locks, and DDL semantics.

Configure a shared PostgreSQL container for both paths:

~~~text
spring.r2dbc.url      = r2dbc:postgresql://<test-host>:<test-port>/<test-db>
spring.flyway.url     = jdbc:postgresql://<test-host>:<test-port>/<test-db>
spring.r2dbc.username = <test-user>
spring.flyway.user    = <test-user>
~~~

These illustrate the property mapping; in actual tests, populate them dynamically from the container (e.g., via `@DynamicPropertySource`) using test-only credentials.

Essential test cases:

1. **Empty database:** startup runs `V1`, creating `integration_outbox` and its index; R2DBC queries succeed.
2. **Second startup:** already-applied migrations do not re-run; schema history stays consistent.
3. **Schema evolution:** adding `V2` keeps `V1` data readable while supporting new queries.
4. **Misconfiguration:** migration JDBC pointing to the wrong DB or lacking privileges fails loudly before serving traffic.
5. **Broken migration:** invalid SQL fails startup/job execution rather than letting the app serve against a half-migrated schema.
6. **Checksum mismatch:** altering an already-applied versioned script triggers validation failure rather than auto-running `repair`.
7. **Business write + outbox:** failing the outbox insert rolls back the business write in R2DBC; retrying with the same `event_key` hits the unique guard against duplicate insertion.

With a message broker in the loop, also test duplicate publishes, crashes between publish and status update, retry/backoff, and rolling schema compatibility across replicas—testing **end-to-end data flow**, not just DDL completion.

## 8. Common failures and diagnostics

| Symptom | Likely cause | Check / fix |
|---|---|---|
| Flyway does not run | Missing starter/auto-config or `spring.flyway.enabled=false` | Verify Boot-compatible dependencies, properties, and startup logs |
| Missing `DataSource` or JDBC driver not found | App only had R2DBC; missing JDBC URL/driver | Add PostgreSQL JDBC driver plus `spring.flyway.url`, user, and password |
| Unsupported PostgreSQL error | Missing Flyway PostgreSQL module on Flyway versions splitting DB support | Add compatible `flyway-database-postgresql` |
| `relation "integration_outbox" does not exist` | Migration skipped, ran on different DB/schema, or queried too early | Compare JDBC/R2DBC URLs + schemas, history table, and startup ordering |
| Validation / checksum error | Edited an already-applied script or DB drifted manually | Diff release vs. history; issue a new fix migration instead of tampering with history |
| Slow startup / timeout | Expensive DDL, table locks, or migration lock contention | Benchmark migrations, optimize DDL, or move to a deployment job |
| High latency or blocking warnings | Calling JDBC inside WebFlux request flows | Keep JDBC in startup/jobs; keep runtime queries on R2DBC |
| Passes locally, fails in staging | Differing profiles, grants, schema names, networking, TLS, or Postgres versions | Inspect effective config and migration logs per environment |

## 9. Questions you should be able to answer

- Why does a reactive service still legitimately include a JDBC driver on its classpath? What boundary keeps JDBC from blocking requests?
- When both `spring.r2dbc.url` and `spring.flyway.url` are set, what proves both hit the same database and schema?
- Why doesn't R2DBC `@Transactional` encompass Flyway DDL or broker publishes?
- With five running replicas and a new mandatory column, in what order do you deploy migrations, code, and backfill so mixed versions run safely?
- Where do you look if migrations succeeded yet the new API still throws `relation does not exist`?

**Technical conclusion:** In Spring Boot Integration, pairing **JDBC for controlled schema migrations** with **R2DBC for runtime data access** is a clean, practical architecture. Integration reliability hinges on identical target databases, rollout sequencing, proper transaction boundaries, error/duplicate handling, testing against a real database, and end-to-end observability.

### References

- Spring Boot — [Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): Flyway/Liquibase, initialization ordering, and avoiding competing schema initializers.
- Spring Boot — [SQL Databases / Using R2DBC](https://docs.spring.io/spring-boot/reference/data/sql.html): `ConnectionFactory`, `spring.r2dbc.*` properties, and interaction with JDBC `DataSource`.
- Flyway — [PostgreSQL Database](https://documentation.red-gate.com/fd/postgresql-database-277579325.html): JDBC driver and PostgreSQL support module requirements.
