# H2 Test Results Differ from the Production Database

A Spring Data R2DBC test may pass on H2 yet fail when deployed against PostgreSQL, SQL Server, MySQL, or another database engine. That does not necessarily mean the test code is wrong. H2 is a distinct database with its own SQL parser, dialect, data types, transaction rules, locking, collation, and driver. H2 compatibility modes emulate only a subset of another engine's behavior; they do not turn H2 into PostgreSQL, SQL Server, or MySQL.

When test results diverge from production, locate where the difference lies: generated SQL, bound/mapped data types, schema migrations, constraints, transactions, concurrency, or database configuration. The sustainable approach is using H2 for fast tests where appropriate while running integration tests on the exact database engine and R2DBC driver used in deployment.

## 1. Why H2 Cannot Replace the Production Database

H2 is a lightweight relational database often used in tests because it starts quickly and runs embedded/in-memory. PostgreSQL, SQL Server, and MySQL each have distinct ecosystems covering data types, syntax, optimizers, lock managers, extensions, collations, and drivers.

Even where two databases support standard SQL, each engine differs in extensions and execution details. A statement valid on H2 may fail on the production database; conversely, SQL using production-specific features may fail on H2.

Common differences:

- **SQL dialect:** pagination syntax, upserts, generated values, string/date-time functions, CTEs, and DDL statements.
- **Data types:** `UUID`, `JSON`/`JSONB`, arrays, enums, binary, temporal types, decimal precision, and vendor-specific types.
- **Identifiers:** casing rules, quoting, default schemas, and reserved keywords.
- **Constraints:** unique, foreign keys, checks, nullability, deferred constraints, and error reporting.
- **Transactions:** isolation, transactional DDL, locking, deadlocks, savepoints, and rollbacks.
- **Concurrency:** row locking, lock acquisition order, phantom reads, lost updates, and serialization failures.
- **Drivers:** bind markers, codecs, generated keys, cancellation, and exception translation.
- **Migrations:** migration scripts may create slightly different schemas or run only on one dialect.
- **Optimizers:** indexes, execution plans, statistics, and query costs are not equivalent.

Therefore, "green tests on H2" only proves code works with your H2 version, H2 driver, and H2 configuration. It does not prove every SQL statement or transaction behavior matches production.

## 2. Separating Three Diagnostic Layers

When an H2 test behaves differently from production, identify which layer the error belongs to first:

| Layer | Components | Example Failures |
|---|---|---|
| Application and Spring Data | Repositories, `R2dbcEntityTemplate`, `DatabaseClient`, converters, transaction managers | Mis-mapped columns, wrong transaction manager, callbacks not firing. |
| R2DBC driver | H2/PostgreSQL/SQL Server/MySQL drivers, codecs, and bind markers | Cannot convert `OffsetDateTime`, generated value not returned, invalid bind type. |
| Database engine | Parser, schema, constraints, isolation, locking, collation, optimizer | SQL syntax error, unique violation, deadlock, precision differences. |

A mapping bug can look like a database error when the root cause is a converter or driver. Conversely, the same repository code can generate different SQL because Spring Data picks a dialect per database. Do not modify entities or queries before checking the actual SQL and parameter types sent.

## 3. H2 Compatibility Modes Have Limits

H2 supports compatibility modes for several engines, usually enabled via URL or configuration options. These modes alter selected parser behaviors or functions to ease porting/testing.

For example, an H2 JDBC URL may enable PostgreSQL mode:

```text
jdbc:h2:mem:testdb;MODE=PostgreSQL;DB_CLOSE_DELAY=-1
```

This is an illustrative JDBC URL. When using R2DBC H2, URLs and option syntax depend on the R2DBC H2 driver version; do not copy JDBC URLs verbatim to R2DBC.

Compatibility modes do not fully reproduce:

- PostgreSQL planner, MVCC, locking behavior, and extensions.
- SQL Server `IDENTITY`, `OUTPUT`, `rowversion`, collations, and native types.
- MySQL storage engines, SQL modes, collations, implicit conversions, and DDL behavior.
- Production R2DBC driver codecs, bind parameter handling, and generated values.
- Real server settings, time zones, encodings, isolation, and exact database versions.

Accordingly, use compatibility mode to run more portable SQL if helpful, not as proof of production compatibility. Whenever code relies on engine-specific features, test directly against that engine.

## 4. Spring Data R2DBC Dialects Can Differ

Spring Data Relational uses `R2dbcDialect` to bridge database differences inside framework-managed abstractions, such as bind markers, data types, and parts of generated SQL.

When connected to H2, Spring Data selects the H2 dialect. When connected to PostgreSQL or SQL Server, the matching dialect is selected. Thus, `R2dbcEntityTemplate` can generate different SQL for the very same entity operation.

For example, paginated queries can render as `LIMIT/OFFSET`, `OFFSET/FETCH`, or another form depending on dialect and framework/database versions. Explicit queries written with `DatabaseClient` are not rewritten completely by dialect. If custom SQL uses `ON CONFLICT`, `OUTPUT INSERTED`, JSON operators, or vendor functions, it must still match the target database.

When investigating, record:

- Spring Boot and Spring Data Relational versions.
- R2DBC driver and version.
- Database engine/version.
- Actual resolved dialect.
- SQL after framework bind-marker expansion.
- Java type and database type of each bind parameter.

Do not assume "Spring Data handles dialects" means every SQL string in `@Query` or `DatabaseClient` is portable.

## 5. Common SQL Syntax Differences

Statements that look similar are often non-portable:

| Need | PostgreSQL | SQL Server | MySQL | Notes |
|---|---|---|---|---|
| Pagination | `LIMIT ... OFFSET ...` or `OFFSET ... FETCH` | `ORDER BY ... OFFSET ... FETCH NEXT ...` | `LIMIT ... OFFSET ...` | SQL Server requires `ORDER BY` with `OFFSET/FETCH`. |
| Upsert | `INSERT ... ON CONFLICT ...` | `MERGE` or matching `UPDATE`/`INSERT` pattern | `INSERT ... ON DUPLICATE KEY UPDATE` | Concurrency and constraint semantics differ. |
| Generated insert values | `RETURNING` | `OUTPUT INSERTED...` | Generated keys or driver mechanism | Syntax is not interchangeable. |
| Boolean | `BOOLEAN` | `BIT` | `BOOLEAN` is usually an alias for `TINYINT(1)` | Mapping/codecs must be verified. |
| UUID | `UUID` | `UNIQUEIDENTIFIER` | Usually `BINARY(16)` or `CHAR(36)` | Storage types and codecs differ. |
| JSON | `JSON`/`JSONB` | `NVARCHAR`/JSON functions per schema | `JSON` | Operators and indexes differ. |

H2 may accept portions of similar syntax without matching every feature or semantic nuance of these engines.

## 6. Example: Upsert Passes on H2 Yet Fails in Production

A repository might contain:

```sql
INSERT INTO customer_setting (customer_id, setting_key, setting_value)
VALUES (:customerId, :key, :value)
ON CONFLICT (customer_id, setting_key)
DO UPDATE SET setting_value = EXCLUDED.setting_value;
```

This is PostgreSQL syntax. It depends on a unique constraint/index on `(customer_id, setting_key)`. SQL Server does not support `ON CONFLICT`; MySQL uses different syntax. H2 compatibility mode may support parts of it yet cannot validate production semantics.

Ways to handle this:

1. If the application only supports PostgreSQL, use PostgreSQL in integration tests.
2. If supporting multiple databases, separate SQL adapters per dialect or use abstractions with semantics supported across all target engines.
3. If portable behavior is required, design explicit transactions/constraints and test race conditions on each engine.

Do not swap syntax just to make H2 pass while sacrificing atomicity. A `SELECT`-then-`INSERT` pattern without unique constraints/locking can still produce duplicates under concurrent requests.

## 7. Data Type Differences

A Java entity property can map to different SQL types across engines. Notable differences:

| Domain Type | H2 | PostgreSQL | SQL Server | MySQL |
|---|---|---|---|---|
| UUID | Support depends on version/config | `UUID` | `UNIQUEIDENTIFIER` | Often `BINARY(16)` or `CHAR(36)` |
| Boolean | `BOOLEAN` | `BOOLEAN` | `BIT` | `BOOLEAN`/`TINYINT(1)` |
| JSON | Type/support depends on version | `JSON`/`JSONB` | Usually text with JSON functions | `JSON` |
| Large binary | `BLOB`/binary type | `BYTEA` | `VARBINARY(MAX)` | `BLOB` |
| Date/time with offset | Temporal support varies by version | `TIMESTAMP WITH TIME ZONE` | `DATETIMEOFFSET` | `TIMESTAMP`/`DATETIME` with distinct semantics |
| Decimal | `DECIMAL`/`NUMERIC` | `NUMERIC` | `DECIMAL`/`NUMERIC` | `DECIMAL` |

This table lists common choices; exact mapping depends on schema, engine version, driver, and converters. Do not choose Java types merely because an H2 test reads/writes them.

## 8. UUIDs and Identifiers

PostgreSQL has a native `UUID` type. SQL Server uses `UNIQUEIDENTIFIER`. MySQL typically stores UUIDs as `BINARY(16)` or `CHAR(36)` strings. H2 provides its own `UUID` type depending on version.

In Java, `java.util.UUID` is usually a clean domain representation, provided the driver has a matching codec. If production uses `BINARY(16)`, standardize byte order/encoding. If using strings, standardize formatting so multiple representations of the same UUID cannot occur.

An H2 test may succeed because H2's codec accepts `UUID` directly, while the production driver rejects that binding or uses a different converter. Test insert, select, `WHERE id = :id` predicates, and generated IDs against the real driver.

## 9. JSON and Vendor-Specific Types

An application might store JSON in an entity:

```java
@Table("customer_profile")
public class CustomerProfile {
    @Id
    private UUID id;

    private String displayName;

    @Column("preferences")
    private Json preferences;
}
```

The `Json` type here is illustrative; exact codecs and converters depend on the driver. PostgreSQL `JSONB` has dedicated operators and indexes; MySQL JSON has its own functions; SQL Server typically stores JSON as text and queries via JSON functions. H2 supports JSON in certain versions without reproducing production operators, indexing, and edge behaviors.

If queries use `->`, `->>`, `@>`, `JSON_VALUE`, `JSON_QUERY`, or custom JSON paths, run tests on the actual database. To reduce dialect coupling for small payloads, you can map JSON as `String`/domain objects in the application, weighing validation, indexing, and read/write costs.

## 10. Decimal Precision and Rounding

H2 and production engines can differ in precision/scale, numeric conversions, and overflow errors. For money or exact decimals, use `BigDecimal` in Java and `DECIMAL(p,s)`/`NUMERIC(p,s)` in schemas.

Example:

```sql
amount DECIMAL(19, 4) NOT NULL
```

H2 tests might permit a value or conversion that production rejects, or round/truncate differently. Never treat a passing insert on H2 as proof of precision correctness.

Test these cases:

- Values matching exact scale.
- Values at the precision boundary.
- Values exceeding precision.
- Negative/positive boundaries per constraints.
- `NULL` in nullable columns.
- `SUM` expressions that may widen the column type.
- Conversion between `BigDecimal` and Java types when mapped by the driver.

Define rounding rules in the domain using an explicit `RoundingMode`. Do not let the database engine round implicitly with uncontrolled semantics.

## 11. Date/Time and Time Zones

Databases differ in temporal types and time zone storage. For example:

- PostgreSQL `TIMESTAMP WITH TIME ZONE` stores an instant with `timestamptz` semantics; it does not preserve the original zone name.
- SQL Server `DATETIMEOFFSET` stores date, time, and offset.
- MySQL `TIMESTAMP` converts using session time zone; `DATETIME` stores no time zone.
- H2 supports many temporal types without guaranteeing identical precision or codecs as production.

In Java, distinguish:

- `Instant`: a point on the UTC timeline.
- `OffsetDateTime`: date and time with a UTC offset.
- `LocalDateTime`: local date and time without offset/zone.
- `LocalDate`: calendar date.
- `LocalTime`: time of day.

Do not map `LocalDateTime` to a timezone-aware column and assume it means UTC. Standardize time zones across application and database sessions, and test DST transitions if business logic uses local time.

Tests should cover day boundaries, varying offsets, fractional seconds, and DST boundaries where applicable. H2 tests running under a developer machine's default time zone can differ from production containers.

## 12. Booleans, Enums, and Collations

SQL Server uses `BIT` for booleans; MySQL often represents `BOOLEAN` as `TINYINT(1)`; PostgreSQL has `BOOLEAN`. Drivers may map these to `Boolean`, yet column types, nullability, and codecs still require verification.

Enums can be stored as names (`VARCHAR`) or ordinals (`INTEGER`). Storing ordinals is fragile when enum order changes; prefer stable codes via converters. If using native database enums, migrations and driver support become vendor-specific.

Collation affects string comparisons and sorting. For example, production may be case-insensitive or accent-insensitive per collation while H2 applies different rules. A query searching for `An` may return different matches than `an` or `Án` depending on collation.

Do not assume Java's `String.equals()` has identical semantics to SQL comparison. If business rules normalize emails, product codes, or usernames, define normalization explicitly and consider storing a normalized column/index.

## 13. Identifiers, Schemas, and Reserved Keywords

Databases differ in how they resolve unquoted table/column names:

- PostgreSQL folds unquoted identifiers to lowercase; quoted identifiers preserve case and become case-sensitive.
- H2 has its own case-folding rules that configuration options can alter.
- SQL Server uses collations and identifier rules; default schemas affect name resolution.
- MySQL table name sensitivity can depend on OS filesystems and `lower_case_table_names`.

An entity with `@Table("Customer")` can resolve differently across environments. Choose simple, consistent naming conventions, avoid reserved words, and declare `@Table`/`@Column` explicitly when needed.

Example:

```java
@Table("customer_account")
public class CustomerAccount {
    @Id
    private UUID id;

    @Column("display_name")
    private String displayName;
}
```

Do not tweak identifier casing merely to make H2 pass without checking the production schema. Migrations and mapping annotations must align on the target database.

## 14. Generated IDs and Generated Values

Engines generate IDs differently:

- PostgreSQL typically uses identity/sequences and supports `RETURNING`.
- SQL Server uses `IDENTITY`, `SEQUENCE`, and `OUTPUT INSERTED`.
- MySQL uses `AUTO_INCREMENT` and driver-level generated keys.
- H2 supports identity/sequences, yet its SQL and APIs do not represent all production engines.

Spring Data R2DBC can retrieve generated IDs via dialect/driver along supported entity persistence paths. When using explicit SQL, understand the driver's generated-values API or write database-appropriate SQL.

Do not run an H2 test asserting non-null ID and assume production generated-value behavior is identical. Test against the real production driver and inspect the entity returned by `save`, especially for immutable entities.

## 15. Constraints and Error Reporting

Databases can differ in:

- Constraint violation names/formats.
- SQLState and vendor error codes.
- Timing of constraint evaluation.
- Deferred constraint support.
- Unique constraints with nullable columns.
- Foreign key cascade and update/delete behavior.
- Check constraints and implicit conversions before evaluation.

Unique constraint example:

```sql
ALTER TABLE customer
ADD CONSTRAINT uq_customer_email UNIQUE (email);
```

H2 tests can confirm duplicate emails are rejected, yet they do not guarantee matching exception types, SQLStates, or constraint names in production. If services classify errors by constraint name or vendor code, test against the real driver.

Do not catch every `DataIntegrityViolationException` and translate it to "email already exists." The violation could come from a foreign key, check constraint, not-null constraint, or a different unique constraint. Classify by specific constraint and rethrow unrecognized errors.

## 16. `NULL` and Unique Constraints

Databases differ when unique indexes contain `NULL`. For instance, PostgreSQL by default permits multiple `NULL` rows in a unique column because `NULL` is not equal to `NULL` under normal comparison semantics; newer PostgreSQL versions offer `NULLS NOT DISTINCT`. SQL Server and other engines have their own rules for nulls in unique indexes.

If business rules require each customer to have at most one external reference when provided, design constraints/filters matching the database and test on the production engine. Do not rely on H2 to validate unique-null edge cases.

If a column must always have a value, declare `NOT NULL` instead of relying on unique constraints to handle nulls.

## 17. Foreign Keys, Cascades, and Write Ordering

H2 tests can diverge from production schemas if test migrations omit foreign keys or build simplified tables. Verify:

- Foreign keys are actually created in the database.
- Referenced columns have matching types and collations.
- `ON DELETE`/`ON UPDATE` actions match intent.
- Parent/child insert order is valid.
- Transactions roll back when child inserts violate foreign keys.
- Cascades delete only intended rows per business rules.

Do not disable constraints in tests just to simplify fixture setup and then conclude persistence logic is safe. When seeding relational test data, insert in valid parent-child order or use clean SQL fixtures.

## 18. Transactional DDL and Migration Differences

A frequent reason migrations pass on H2 yet fail in production is differing DDL semantics. Some engines execute DDL transactionally; others trigger implicit commits or fail to roll back as expected.

Examples:

- PostgreSQL supports transactional behavior for many DDL statements, with documented exceptions and locking considerations.
- MySQL causes implicit commits on many DDL statements.
- SQL Server supports transactions for many DDL operations with statement-specific limits and semantics.
- H2 has its own DDL and transaction behaviors.

Do not assume a failed migration leaves the schema untouched on every engine. For multi-step migrations, verify post-failure state and design recovery plans. Migration tools track history, but they cannot make non-transactional DDL roll back.

## 19. Isolation and Locking Differ

Sequential H2 tests rarely surface race conditions. Production handles concurrent requests, multiple instances, and lock contention. Databases differ in MVCC, row locks, gap/next-key locks, predicate locks, and deadlock detection.

Scenarios requiring attention:

- Two requests updating the same account concurrently.
- Two transactions inserting the same unique key.
- Read-then-write based on stale state (lost update).
- Reading a list then inserting a matching row (phantom).
- Two transactions acquiring locks in opposite orders (deadlock).
- Transactions holding locks too long while reactive pipelines await network calls or heavy CPU work.

When business rules require conditions like "debit only if balance is sufficient," encode the predicate in `UPDATE` and check `rowsUpdated`, or use suitable locking/versioning strategies. Never rely solely on read-then-save in Java.

## 20. Default Isolation Levels Are Not Identical

Never infer production isolation from H2's default. Verify the actual isolation level from the database, transaction manager, and application configuration.

Key concepts:

| Isolation | General Goal | What to Check |
|---|---|---|
| `READ UNCOMMITTED` | May read uncommitted data on supporting engines | Dirty reads and engine-specific semantics. |
| `READ COMMITTED` | Reads only committed data per engine semantics | Non-repeatable reads and per-statement snapshots. |
| `REPEATABLE READ` | Keeps read rows repeatable per engine semantics | Phantom behavior varies across engines. |
| `SERIALIZABLE` | Produces outcomes equivalent to serial execution | May raise serialization failures requiring retries. |

Identical isolation names do not guarantee identical implementations. For example, PostgreSQL `REPEATABLE READ` uses snapshot isolation with behavior distinct from lock-based engines; SQL Server may use locking or row-versioning depending on `READ_COMMITTED_SNAPSHOT`/snapshot isolation settings.

Concurrency tests must run on the production database or matching engine with the deployment's isolation configuration.

## 21. Reactive Transaction Tests Differ from Imperative Tests

Spring Data R2DBC uses reactive transaction contexts propagated via Reactor Context. Tests that call `block()` mid-chain, manually call `subscribe()`, or rely on imperative test transaction semantics may fail to test the real transaction context.

Guidelines:

- Keep all database operations inside the same `Mono`/`Flux` chain.
- Use the right `ReactiveTransactionManager` bound to the repository/client `ConnectionFactory`.
- When tests require transactions, use appropriate reactive transaction support and verify publishers execute inside that context.
- Do not assume `@Transactional` on a JUnit test method automatically wraps every reactive publisher as expected.
- To verify rollbacks, actively start transactions in the service/test and re-query state after the transaction finishes.

An H2 test may pass even if two operations accidentally use separate connections or the transaction misses the pipeline; production concurrency makes those bugs visible.

## 22. R2DBC Driver Behavior Is Part of the Difference

It is not only the database engine that changes. The R2DBC driver governs how Java types are bound/read, how statements execute, and how cancellations/errors translate into Reactive Streams signals.

Differences can arise in:

- `UUID`, JSON, array, enum, binary, and temporal codecs.
- Null binding and requiring Java types for null parameters.
- Generated values and `returnGeneratedValues`.
- Batch statements and `Statement.add()`.
- `Clob`/`Blob` mapping or large objects.
- Cancellation and query timeouts.
- Exception types, SQLStates, and vendor codes.
- Connection acquisition, validation, and pooling behavior.

Unit tests mocking `DatabaseClient` pass without testing driver codecs. Nor does the H2 R2DBC driver represent PostgreSQL/SQL Server/MySQL drivers. Run tests through the production driver.

## 23. Configuring H2 for R2DBC Tests

When using H2 R2DBC, declare the test driver and URL per driver version documentation:

```groovy
testImplementation 'io.r2dbc:r2dbc-h2'
```

Illustrative configuration:

```yaml
spring:
  r2dbc:
    url: r2dbc:h2:mem:///r2dbc-test
```

URLs, options keeping databases alive across connections, schema initialization, and database lifecycles depend on the R2DBC H2 driver. Do not copy JDBC options like `DB_CLOSE_DELAY` into R2DBC URLs without checking the driver. With in-memory databases, ensure the database is not closed between schema setup and repository connections.

H2 fits fast tests when queries and schemas stay within H2-supported SQL and tests are not meant to validate production dialects/locking.

## 24. Running Real Migrations in Tests

Tests creating tables with a stripped-down `schema.sql` can miss constraints, indexes, defaults, and conversions present in production migrations. When testing persistence integration, run actual migration scripts against the test database.

If migrations contain PostgreSQL/SQL Server/MySQL-specific syntax, H2 may reject them. Do not maintain a fake H2 schema differing from production without documenting test scope. Preferably run real migrations on Testcontainers for the target engine.

Migration tests should verify:

- A clean database can execute all migrations from scratch.
- Previous schema versions can upgrade to the current version.
- Migrations create expected constraints, indexes, defaults, and sequences.
- Failed migrations leave understood state with recovery paths.
- Data backfills preserve invariants.
- New code stays compatible with schemas during rolling deployments if required.

## 25. Using Testcontainers with the Production Database

Testcontainers spins up the database engine in a container so integration tests run on the same database type as production. PostgreSQL example:

```groovy
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
testImplementation 'io.r2dbc:r2dbc-postgresql'
```

Manage dependency versions with an appropriate BOM. Example test:

```java
@SpringBootTest
@Testcontainers
class TransferRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
            "r2dbc:postgresql://" + postgres.getHost() + ":"
                + postgres.getMappedPort(5432) + "/"
                + postgres.getDatabaseName());
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);

        registry.add("spring.flyway.url", postgres::getJdbcUrl);
        registry.add("spring.flyway.user", postgres::getUsername);
        registry.add("spring.flyway.password", postgres::getPassword);
    }
}
```

This example uses a Spring Boot test context, Testcontainers, and Flyway over JDBC; the project needs the PostgreSQL R2DBC driver, PostgreSQL JDBC driver, and the migration tool. If your application does not use Flyway, omit the Flyway properties and initialize schemas with your actual migration mechanism.

Container images should pin a version aligned with production—such as matching major/minor versions when testing version-specific behavior. Avoid `latest` so tests do not change behavior when images update.

## 26. Using the Right Engine for Each Production Environment

If production runs SQL Server, use SQL Server Testcontainers/images and the R2DBC SQL Server driver. If production runs MySQL, use MySQL accordingly. PostgreSQL tests do not prove SQL Server queries work, even though both are relational databases.

Beyond the engine itself, align:

- Database major/minor version.
- Collation and character set.
- Time zone/session settings.
- SQL mode or compatibility level.
- Extensions and modules used in production.
- Isolation/row-versioning settings.
- Schema and migration versions.
- R2DBC driver version.

Testcontainers does not automatically replicate every managed production database setting. When production uses custom extensions, collations, or server flags, configure test containers accordingly or add targeted tests verifying the differences.

## 27. Tiering Tests by Purpose

Not every test needs a real database container. Tier your suite:

| Test Type | Database | Purpose | Examples |
|---|---|---|---|
| Domain/service unit tests | None or mocks/fakes | Business rules, validation, pure mapping logic | Positive amounts, currency, authorization policies. |
| Reactive pipeline tests | Fake publishers, `StepVerifier`/`TestPublisher` | Signals, retries, fallbacks, cancellation | Empty vs error, retry counts. |
| Fast persistence tests | H2 R2DBC | Basic mapping and CRUD within H2's scope | Simple insert/select, portable repository queries. |
| Database integration tests | Testcontainers production engine | Dialect, codecs, migrations, constraints, transactions | Generated values, JSON, locking. |
| Concurrency tests | Production engine and driver | Race conditions, deadlocks, isolation | Concurrent transfers, unique conflicts. |
| Performance tests | Production-like environment | Query plans, indexes, latency, throughput | Pagination, batching, pool saturation. |

Tiering keeps fast tests valuable without asking H2 to verify behaviors it cannot represent.

## 28. `@DataR2dbcTest` and `@SpringBootTest`

Spring Boot's `@DataR2dbcTest` is a test slice focused on R2DBC components, suitable for focused repository/mapping tests. `@SpringBootTest` builds a broader application context, suited for verifying service wiring, transaction managers, migrations, and production-like beans.

Depending on Spring Boot version and project setup, test slices alter which auto-configurations load. Do not assume `@DataR2dbcTest` runs Flyway automatically or loads all service/transaction beans. When tests need real migrations or broader beans, import them explicitly or use `@SpringBootTest`.

With Testcontainers, configure container properties via `@DynamicPropertySource` or service-connection support in your Spring Boot version. Ensure R2DBC properties point to the real container; overriding only JDBC URLs while repositories use R2DBC leaves tests hitting the wrong database.

## 29. Inspecting Generated SQL and Custom SQL

When a query runs on H2 yet fails in production, separate framework-generated SQL from handwritten SQL:

- Derived repository queries: Spring Data generates SQL from metadata and dialect.
- `R2dbcEntityTemplate`: framework generates SQL from `Query`, `Criteria`, sort, and mapping metadata.
- `@Query`: developer-written SQL, still utilizing Spring Data binding/mapping.
- `DatabaseClient`: developer-controlled SQL directly.
- R2DBC SPI: driver-specific statements and markers.

For the first two groups, inspect dialect and mapping metadata. For `@Query`/`DatabaseClient`, inspect exact SQL syntax on the production engine. Do not assume `@Query` automatically rewrites `LIMIT` to `OFFSET/FETCH` or `ON CONFLICT` to `MERGE`.

In test environments, enable controlled SQL logging or a proxy/listener to observe queries. Never log sensitive bind values. Compare actual SQL between H2 and production tests to spot syntax or alias differences.

## 30. Entity Mapping and Column Names

An entity may work on H2 because H2 resolves column names leniently, while production reports column not found due to case/quoting/schema rules.

Example:

```java
@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private UUID id;

    @Column("created_at")
    private Instant createdAt;
}
```

Ensure migrations create `purchase_order.created_at` in the right schema and the dialect quotes identifiers as needed. Avoid mixed-case column names or reserved keywords unless required.

If production uses a dedicated schema like `orders.purchase_order`, configure schema mapping/search path/default schema explicitly. H2 tests using only a default schema can miss missing schema qualifications.

## 31. Checking Constraints and Migrations Instead of Creating Fake Schemas

Some H2 tests construct schemas via simplified `schema.sql` or `@Sql`, while production uses Flyway/Liquibase. Test schemas may omit:

- Unique constraints.
- Foreign keys.
- Check constraints.
- Not-null constraints.
- Default expressions.
- Triggers.
- Sequences/identities.
- Partial/filtered indexes.
- Collations or generated columns.

Tests then pass solely because the test database lacks the constraints enforcing data integrity. For persistence integration tests, run actual migrations on the target database. If a narrow test uses a minimal table for isolated logic, document its scope and never use it to claim production schema correctness.

## 32. Testing Transaction Rollback on the Real Engine

A transfer test may pass on H2 yet fail in production due to differences in transaction managers, drivers, connection binding, or locking. Rollback tests should:

1. Seed accounts A and B.
2. Start a reactive transaction.
3. Debit A.
4. Intentionally fail crediting B.
5. Assert the publisher emits an error.
6. After the transaction ends, re-query via an independent transaction/query.
7. Confirm balances of A and B remain unchanged with no partial ledger/outbox records.

Do not just assert `expectError` and assume rollback succeeded. Always read back committed state. Nor should you rely on JUnit's test transaction support unless you know for sure it wraps the reactive chain.

## 33. Concurrency Tests Must Run on the Production Database

H2 handles locking and concurrency differently from real engines. Key tests include:

- Two requests concurrently debiting the same account.
- Two requests inserting the same idempotency key.
- Two transactions updating two accounts in opposite orders.
- Optimistic version conflicts.
- Deadlocks/serialization failures and retries.
- Concurrent unique/foreign-key conflicts.
- Queries under the real isolation level.

Tests must actually execute concurrently using barriers/latches or reactive coordination, then read back final state. Running two requests sequentially does not test race conditions.

Do not rely on H2 as sole proof that accounts cannot overdraw or duplicate transfers cannot happen. Test on the production engine and isolation configuration.

## 34. Execution Plans and Performance Cannot Be Inferred from H2

H2 has its own optimizer and storage engine. A query running fast on H2 does not guarantee proper index usage or comparable latency on PostgreSQL/SQL Server/MySQL.

Differences include:

- Statistics and cardinality estimation.
- Index access paths.
- Join algorithms.
- Sort/hash memory and disk spill behavior.
- Lock contention.
- Buffer/cache and storage I/O.
- Parallel query execution.
- Network round-trips and result decoding.

Do not use H2 benchmarks to decide production indexes. Inspect execution plans and metrics on the real engine with data distributions close to production. H2 remains helpful for checking basic query logic, not performance.

## 35. Time Zones, Locales, and Environment Drift

Local tests often run in UTC or the developer machine's time zone, whereas production containers run UTC or another configured zone. Locales, collations, and encodings can also vary.

Pin time zone and locale settings in tests while still inspecting actual database session state:

- Database/server/session time zone.
- JVM/container time zone.
- Encoding and collation.
- Application locale.
- Timestamp precision and rounding.

For timestamps representing instants, prefer explicit UTC/`Instant` conventions. For business calendar dates, use `LocalDate` instead of converting arbitrarily through timestamps. Test boundary values and daylight saving transitions if handling local times.

## 36. Diagnosing Errors by Symptom

| Symptom | Possible Cause | How to Confirm |
|---|---|---|
| H2 passes, production reports syntax error | Different SQL dialect or function | Capture raw SQL and run on production engine/version. |
| Column/table not found | Different schema, casing, quoting, or migration | Inspect schema metadata and migration history. |
| Bind parameter type error | Incompatible driver codec or Java type | Check bind types, `bindNull`, and driver version. |
| Generated ID is null | Different dialect/driver generated-value behavior | Test insert on real driver; inspect returned entity/`OUTPUT`/`RETURNING`. |
| Different unique constraint error type | Different exception translation/vendor code | Capture SQLState, vendor code, and exact constraint. |
| Rollback test passes, production leaves partial data | Different transaction manager/connection factory/context | Inspect transaction boundaries and re-query after errors. |
| Deadlocks happen only in production | Concurrency, lock order, indexes, or isolation | Run concurrency tests and inspect deadlock reports. |
| String searches return different results | Collation/case/accent sensitivity | Inspect collation and normalization rules. |
| Timestamp offset drift | Different time zone/precision/codec | Inspect session time zone and SQL/Java types. |
| Query fast on H2, slow in production | Different optimizer/indexes/data volume | Inspect execution plan and metrics on real engine. |
| Migration passes on H2, fails in production | Different DDL syntax/transaction/lock semantics | Run actual migrations on production engine/version. |

Do not fix by adding an H2-specific branch in production code when the real problem is that the test is using the wrong database for the behavior being verified. Add multi-dialect abstractions only when the application genuinely supports multiple engines.

## 37. Step-by-Step Diagnostic Procedure

When a test passes on H2 yet fails in production, follow this sequence:

1. Record the database engine/version, R2DBC driver/version, Spring Data version, and session settings.
2. Collect the exception type, SQLState, vendor code, and cause chain without logging sensitive bind values.
3. Determine whether the SQL comes from repository derivation, template, `@Query`, or `DatabaseClient`.
4. Capture the actual SQL and test it directly on the target engine/version.
5. Check Java bind types, nullability, and driver codecs.
6. Compare schema/migration history, constraints, indexes, and defaults between H2 and production.
7. If the error appears only under load/concurrency, inspect isolation, lock order, transaction context, and pooling.
8. If related to date/time or strings, check time zones, precision, collation, and normalization.
9. Write a reproducing integration test using Testcontainers or a production-equivalent environment.
10. Keep H2 tests if still useful for fast feedback; move dialect/engine-dependent behavior to real database tests.

Do not change multiple code layers simultaneously. Testing one variable at a time finds the root cause faster.

## 38. Recommended Test Matrix

A project can organize its test matrix as follows:

| Test Suite | H2 R2DBC | Production Engine via Testcontainers |
|---|---|---|
| Domain validation | Not needed | Not needed |
| Reactive operators/retry/fallback | Fake publishers work | Not needed unless persistence interacts |
| Basic CRUD mapping | Optional | Should have representative tests |
| Derived repository queries | Fine for portable queries | Yes, to confirm production dialect |
| Native SQL/`@Query` vendor-specific | Insufficient | Mandatory |
| JSON/UUID/array/temporal codecs | Insufficient | Mandatory if used in production |
| Generated values | Basic checks | Mandatory on production driver |
| Constraints and exception translation | Insufficient for exact details | Mandatory for key error mappings |
| Transaction rollback | Basic checks possible | Mandatory for critical use cases |
| Concurrency/deadlocks/isolation | Insufficient | Mandatory for concurrent invariants |
| Migrations | Only if scripts are portable | Mandatory on production engine |
| Performance/indexes/execution plans | Do not use as evidence | Use production-like environment |

This matrix does not mean every test must run twice. Choose suites based on purpose and feature risk.

## 39. Keeping H2 Tests Fast While Limiting Conclusions

H2 remains valuable for:

- Testing basic entity mapping with portable schemas.
- Testing simple repository CRUD.
- Testing reactive services against a small test database.
- Testing standard SQL validations/constraints supported by both engines.
- Creating fast fixtures for dialect-independent logic.

Keep each test's scope explicit. When using H2, avoid treating it as proof for:

- Vendor-specific SQL.
- Native JSON/array/spatial types.
- Engine-specific generated values.
- Production locking, deadlocks, or isolation.
- Production DDL migrations.
- Production collations or time zones.
- Query plans and performance.

If H2 tests constantly require adding `MODE`, `NON_KEYWORDS`, function aliases, or fake schemas to mimic production, that is a strong signal to move those tests to the real database.

## 40. Common Test Design Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Using only H2 for all persistence tests | Misses dialect, driver, and concurrency differences | Add Testcontainers for the production engine. |
| Using compatibility mode and treating it as identical | False confidence | Treat compatibility mode as partial syntax support only. |
| Creating test schemas different from real migrations | Missing constraints/indexes/defaults | Run real migrations on test databases. |
| Mocking `DatabaseClient` exclusively | Never tests SQL/codecs/transactions | Keep integration tests with the real driver. |
| Query tests without `ORDER BY` asserting order | Flaky tests across engines | Add deterministic ordering or assert as sets. |
| Benchmarking on H2 | Wrong conclusions about optimizers/indexes | Measure on real engine and production-like data. |
| Asserting only errors without re-reading data | Does not prove rollback | Query state after transaction ends. |
| Testing transactions with arbitrary `block()`/`subscribe()` | May bypass reactive context | Compose publishers and use `StepVerifier`. |
| Running Testcontainers with `latest` | Results drift over time | Pin image and driver versions. |
| Ignoring database settings | Test/prod drift in collation/time zone/isolation | Align critical server settings. |

## 41. Checklist Before Concluding a Bug Is in Application Code

When comparing H2 and production, verify:

1. Do test and production run the expected engine/major version?
2. Are R2DBC driver and Spring Data versions compatible?
3. What is the actual SQL, and which abstraction generated it?
4. Do bind markers, Java types, and null bindings match the driver?
5. Was the schema built from the same migration scripts?
6. Are table/column/schema casing and quoting consistent?
7. Do data types, precision, time zones, and collations match?
8. Are constraints, triggers, sequences, defaults, and indexes present?
9. Does the transaction manager use the right `ConnectionFactory`?
10. Do isolation and locking settings match production?
11. Does the test actually run concurrently when testing race conditions?
12. Can the issue be reproduced on Testcontainers with the production engine?

## 42. Adoption Workflow in a Spring Data R2DBC Project

A practical strategy:

1. Keep unit tests and reactive pipeline tests database-independent where possible.
2. Use H2 for simple CRUD/mapping and portable SQL if execution speed is a priority.
3. Use the exact production R2DBC driver and database engine in Testcontainers for vendor-specific queries, migrations, generated values, type mapping, and constraints.
4. Run concurrency tests for critical invariants like balances, idempotency, and unique keys on the production engine.
5. Use real migrations to create test schemas; avoid simplified schemas for the main integration suite.
6. Pin database images, drivers, and framework versions so tests remain reproducible.
7. Align time zones, collations, isolation, and key extensions with production.
8. When tests fail, classify the error under application, driver, or engine before editing code.
9. Keep compatibility mode only for tests where it genuinely helps; never extrapolate conclusions beyond its supported scope.
10. Run the production-equivalent suite in CI before releasing critical persistence changes.

H2 is a useful tool for running basic R2DBC tests quickly, yet it is not a replica of the production database. Divergent results usually stem from SQL dialects, data types, driver codecs, schema migrations, constraints, collations, transactions, or concurrency. Use H2 within its fitting scope and run integration tests with the real production engine/driver for database-dependent behavior. When diagnosing, compare actual SQL, bind types, schemas, and transaction setups; Testcontainers helps reproduce production-like environments in CI. This layered approach preserves test speed while catching bugs that surface only on real databases.
