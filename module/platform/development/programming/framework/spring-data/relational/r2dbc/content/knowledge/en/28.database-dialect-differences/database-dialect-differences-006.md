# Checking Oracle and Other Driver Characteristics Before Use

Spring Data Relational R2DBC offers a unified data access model, yet it does not make every database engine and R2DBC driver behave identically. A feature may exist in the R2DBC SPI without being implemented by a driver; a driver may support it while the Spring Data dialect does not generate the right SQL; or the database may accept a statement with semantics different from what the team used previously.

Oracle is a prime example that requires systematic verification. Pagination syntax, sequences, generated values, data types, LOBs, transaction isolation, locking, DDL, and error codes can differ from PostgreSQL, MySQL, SQL Server, or H2. Simply booting the application and running a basic SELECT does not prove all persistence features behave correctly.

This lesson guides you through evaluating Oracle R2DBC and other drivers before adopting them in a project. The focus is on distinguishing three capability layers—database, R2DBC driver, and Spring Data R2DBC dialect—building a feature matrix, testing critical scenarios with integration tests, and documenting limitations before deployment.

## 1. Why R2DBC Drivers Cannot Be Treated as Equivalent

R2DBC defines a common SPI for opening connections, creating statements, binding values, executing queries, reading results, and managing transactions. The SPI lets applications use a consistent reactive API style.

However, the SPI does not standardize all SQL or every engine-specific database feature. Differences can arise in:

- SQL syntax and bind parameter placeholders.
- ID generation, sequences, and returning generated values.
- Data types and conversions between the database and Java.
- LOBs, JSON, arrays, enums, XML, and user-defined types.
- Transaction isolation, savepoints, locking, and DDL.
- Schema, table, column, and generated-key metadata.
- Batch statements, multiple results, and stored procedures.
- Cancellation, timeouts, pooling, and TLS.
- SQLState, vendor error codes, and exception translation.

An application can use the same ReactiveCrudRepository across two databases and still need adjustments to schemas, queries, mappings, or transaction handling.

~~~text
Spring Data R2DBC Application
          |
          v
Spring Data dialect / mapping
          |
          v
R2DBC SPI
          |
          v
Specific driver
          |
          v
Database engine
~~~

Each layer has its own contract. Identify which layer owns a needed feature before evaluating support.

## 2. Three Layers to Verify: Database, Driver, and Spring Data Dialect

### 2.1. Database Capabilities

The database engine determines which SQL is valid and its execution semantics:

- Does it support OFFSET ... FETCH or require ROWNUM/ROW_NUMBER()?
- Which isolation levels are supported?
- Can DDL roll back in a transaction or does it trigger an implicit commit?
- How do sequences and generated columns work?
- How are RETURNING, SELECT FOR UPDATE, JSON, arrays, or LOBs supported?

A database feature may exist without the driver exposing a convenient API for it.

### 2.2. R2DBC Driver Capabilities

The driver determines how the SPI maps to the database protocol and APIs:

- Which SQL placeholders are accepted?
- Does Statement.returnGeneratedValues(...) work?
- Which Java types can be bound and read?
- Are Blob/Clob streamed?
- Are savepoints, isolation levels, and cancellation supported?
- Which R2dbcException subclasses wrap database errors?

Never conclude a driver supports a feature solely because the underlying database does.

### 2.3. Spring Data R2DBC Dialect Capabilities

Spring Data uses the dialect to know how to generate SQL and express database differences. The dialect can supply information on:

- Bind markers.
- Pagination syntax.
- How generated values are retrieved.
- Identifier processing.
- Simple data types and conversions.
- Certain engine-specific SQL capabilities.

A driver may run manual SQL fine while the Spring Data dialect fails to generate correct SQL for a repository method or entity callback. Conversely, a dialect may advertise a capability that the current driver version has not fully implemented.

**Technical conclusions must cover all three layers.** Never take "Oracle supports it" as proof that Oracle R2DBC, your chosen driver version, and your current Spring Data release all support that feature.

## 3. Oracle R2DBC in the Spring Ecosystem

Oracle provides its own R2DBC driver for Oracle Database. The driver artifact, driver version, underlying Oracle JDBC dependency (if required by that driver release), R2DBC SPI version, and database version must be selected from the vendor's compatibility matrix.

Record these details before integrating:

1. Target Oracle Database version and edition.
2. Oracle R2DBC driver version.
3. R2DBC SPI version targeted by the driver.
4. Spring Boot and Spring Data Relational versions.
5. Java version.
6. Underlying libraries and versions required by the driver.
7. Operating system, architecture, and runtime packaging.
8. Oracle features the application actually needs.

Never mix arbitrary latest versions of each dependency. Inspect dependency compatibility matrices and release notes for the driver, Spring Boot BOM, and Spring Data release train. Upgrading a driver can bring changes to SPI versions, JDBC dependencies, mappings, or database requirements.

### 3.1. Declaring Dependencies and Connections

Take artifact coordinates and versions from the chosen release's compatibility documentation. General configuration example:

~~~xml
<dependency>
    <groupId>com.oracle.database.r2dbc</groupId>
    <artifactId>oracle-r2dbc</artifactId>
    <version>`${oracle.r2dbc.version}`</version>
</dependency>
~~~

Artifact names and transitive dependencies can change across releases; use exact Maven coordinates published by the vendor for your target version.

The connection URL uses an Oracle R2DBC scheme, such as:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:oracle://db-host:1521/service-name
    username: `${DB_USERNAME}`
    password: `${DB_PASSWORD}`
~~~

This is an illustrative structure. Service names, SIDs, wallets, TCPS, TLS, and connection options must follow driver docs and your actual Oracle configuration. Never replace the R2DBC scheme with a JDBC URL like jdbc:oracle:thin:....

If the driver requires or wraps an Oracle JDBC driver underneath, verify compatible versions and avoid forcing an unsupported JDBC driver onto the classpath.

### 3.2. Do Not Infer Non-Blocking Behavior From Return Types Alone

The R2DBC API returns Publishers, yet how non-blocking the underlying I/O is and how the driver uses underlying libraries are implementation details. For the Oracle driver, read the specific release documentation to understand its architecture, dependency requirements, thread model, and operational limits.

Never add block() inside services "to make Oracle work." If the driver has constraints or paths needing a dedicated scheduler, follow official guidance and measure under load tests. Returning Mono does not guarantee every underlying stage is non-blocking.

## 4. Verifying Whether the Spring Data Dialect Recognizes Oracle

Spring Data R2DBC uses a dialect to generate database-appropriate SQL. When switching drivers, confirm that the resolved dialect actually corresponds to Oracle.

Questions to answer:

- Does your Spring Data Relational version include a built-in Oracle dialect?
- Does the resolver recognize the Oracle R2DBC driver's metadata?
- If multiple ConnectionFactories exist, is the dialect bound to the right factory?
- What bind markers and pagination SQL does the dialect emit?
- Is the generated-value strategy compatible with Oracle?
- Is a custom dialect or DatabaseClient with explicit SQL needed?

Never guess class names or force a dialect solely from a database name. Check Spring Data documentation for your exact release and verify with integration tests.

If a built-in dialect is missing or lacks a feature, options include:

1. Upgrading to a Spring Data version with appropriate support after checking compatibility.
2. Using DatabaseClient for specific queries with explicit Oracle SQL.
3. Writing a custom dialect/provider if supported by that Spring Data version's extension points and maintainable by your team.
4. Using repositories for portable SQL and isolating Oracle-specific queries in a dedicated adapter.

Never replace internal dialects via reflection or override non-public classes; that easily breaks on upgrades.

## 5. Pagination SQL: How Oracle Differs From LIMIT/OFFSET

Many PostgreSQL or MySQL SQL examples use:

~~~sql
SELECT id, order_number
FROM purchase_order
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;
~~~

Oracle Database supports OFFSET ... ROWS FETCH NEXT ... ROWS ONLY pagination in versions supporting the row-limiting clause:

~~~sql
SELECT id, order_number
FROM purchase_order
ORDER BY created_at DESC, id DESC
OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

On older Oracle versions lacking this clause, ROWNUM or ROW_NUMBER() in subqueries is typically needed. Check the actual database version rather than relying solely on the name Oracle.

When using Spring Data Pageable, do not assume the dialect automatically generates valid SQL just because Pageable compiles. Run integration tests on Oracle to verify:

- First page.
- Middle page.
- Last page.
- Page size 0 or invalid values.
- Multi-column sorting.
- Sort keys with duplicate values.
- Large offsets.
- Queries with joins or projections.

Pagination always requires a deterministic sort order, typically adding a unique key as a tie-breaker. Without ORDER BY, the database does not guarantee row order across requests.

### 5.1. Keyset Pagination Reduces Reliance on Offsets

For large or rapidly changing lists, seek/keyset pagination filters on sort keys instead of using offsets. Example in descending order:

~~~sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE created_at < :last_created_at
   OR (created_at = :last_created_at AND id < :last_id)
ORDER BY created_at DESC, id DESC
FETCH NEXT :page_size ROWS ONLY;
~~~

Verify bind marker syntax and limit binding support with the Oracle R2DBC driver. The snippet above illustrates SQL logic; do not treat :last_created_at as a portable placeholder across every driver API.

Keyset pagination still requires a cursor holding all sort keys and does not create a snapshot. If sort keys can mutate, rows can shift past the cursor.

## 6. Placeholders and Parameter Binding

R2DBC SPI exposes Statement.bind(index, value) and bindNull, while SQL placeholder syntax depends on the driver.

Some drivers use ?, while others use named or numbered forms like $1 or :name/:1. Never copy SQL verbatim from PostgreSQL to Oracle without checking.

Spring DatabaseClient provides a named-parameter abstraction and converts parameters into the dialect's bind markers. Still, verify that the right dialect is chosen and the driver accepts the converted syntax.

When writing SQL directly:

- Use placeholders documented by your current Oracle R2DBC release.
- Bind values; never concatenate user strings into SQL.
- Use bindNull(index, type) or the supported equivalent API.
- Test binding enums, timestamps, UUIDs, and numeric types.
- Never bind table names, column names, or sort keywords as value parameters; use identifier whitelists.
- Verify parameter order when queries are constructed dynamically.

A minimal smoke test should run at least one parameterized SELECT, one parameterized INSERT, one UPDATE, and one null bind.

## 7. Primary Key Generation: Sequences, Identity, and Generated Values

Oracle supports several ID generation strategies:

- Explicit sequences.
- Identity columns on supported Oracle versions.
- Triggers paired with sequences in legacy schemas.
- Application-assigned IDs.

A sequence value can be fetched before inserting:

~~~sql
SELECT order_seq.NEXTVAL FROM dual;
~~~

Then bind the ID into INSERT:

~~~sql
INSERT INTO purchase_order (id, order_number, status)
VALUES (:id, :order_number, :status);
~~~

DUAL is a special single-row table commonly used in Oracle to evaluate expressions. Replace placeholders in examples with your driver's actual bind syntax.

Oracle has RETURNING ... INTO syntax to return values created or modified by DML, yet using it through R2DBC depends on the Oracle R2DBC driver and Statement.returnGeneratedValues(...) support in your release.

Before relying on generated values, verify:

1. Does the driver support returnGeneratedValues for that type of INSERT/UPDATE?
2. Which column names can be requested?
3. Are results returned via Result.map or another API?
4. Do identity columns and sequences behave identically?
5. Do batch inserts return generated values per row?
6. When inserting multiple rows, is generated key ordering guaranteed?

Never use SELECT MAX(id) to find the newly inserted ID. Under concurrent requests, the result could belong to another transaction. If generated-value APIs are insufficient, fetch the sequence beforehand and insert with the known ID after confirming that fits the schema.

## 8. Oracle Data Types and Java Mappings

Oracle data type names differ from PostgreSQL and MySQL. Automatic mapping depends on the driver, Spring converters, and exact column definitions.

| Common Oracle Type | Candidate Java Type | What to Verify |
|---|---|---|
| NUMBER | BigDecimal | Precision, scale, and value limits |
| NUMBER(p,0) | Long, Integer, BigInteger, or BigDecimal | Whether actual values can exceed type bounds |
| VARCHAR2 | String | Character set, byte/char length semantics, and collation |
| NVARCHAR2 | String | Unicode and driver conversion |
| CHAR / NCHAR | String | Space padding and comparison semantics |
| DATE | Suitable Java date/time type | Oracle DATE includes a time component |
| TIMESTAMP | LocalDateTime or driver-supported type | Precision and timezone semantics |
| TIMESTAMP WITH TIME ZONE | OffsetDateTime/Instant if supported | Whether offset is preserved or normalized to instant |
| TIMESTAMP WITH LOCAL TIME ZONE | Driver-appropriate temporal type | Values are normalized per session timezone |
| RAW | byte[] or ByteBuffer | Length and conversion |
| BLOB | Blob/byte publisher or application type | Streaming, buffering, and resource lifetime |
| CLOB / NCLOB | Clob or text | Character encoding and large payloads |
| JSON, XMLTYPE, object types | String or specialized type | Driver support and conversion per version |

This table is a design guide, not a conversion guarantee across all driver releases. Check the driver's type-mapping documentation and write round-trip tests for critical types.

### 8.1. NUMBER Is Not Automatically Long

Oracle NUMBER can store huge integers, decimals, or arbitrary numbers. Mapping every NUMBER to Long risks truncating decimals or overflowing.

- Use BigDecimal when precision and scale must be preserved.
- Use Long when schema and business rules guarantee bounded integers.
- Inspect precision and scale in the schema.
- Test boundary, negative, null, and decimal values.

Never use double for money or data requiring exact decimal precision.

### 8.2. Oracle DATE Includes Time

Oracle DATE stores year, month, day, hour, minute, and second; it is not merely a calendar date like DATE in some other engines. Mapping it to LocalDate can discard the time portion.

If business logic needs a timestamp, choose an appropriate Java type and converter—often LocalDateTime or a timezone-aware type depending on the column and system conventions.

### 8.3. Timezones and Sessions

TIMESTAMP WITH TIME ZONE and TIMESTAMP WITH LOCAL TIME ZONE have different semantics. Session timezone can also affect how values are displayed or converted.

Verify via tests:

- Store an instant with a non-UTC offset.
- Read it back on the same connection and a fresh connection.
- Change the session timezone if the application ever alters it.
- Confirm the instant does not shift unexpectedly.
- Confirm precision when the database rounds or truncates fractional seconds.

Never treat LocalDateTime as UTC implicitly if the schema lacks timezone awareness and the application has no explicit convention.

## 9. LOBs and Large Data

Oracle commonly uses BLOB, CLOB, and NCLOB for large data. R2DBC SPI defines Blob and Clob abstractions, but streaming, lifecycles, and mappings depend on the driver.

Verify:

- Does the driver support streaming LOB reads?
- Does it buffer the entire payload into memory automatically?
- Do LOB locators remain valid after the result or connection closes?
- Must LOBs be explicitly consumed or freed?
- Does cancelling mid-stream release resources?
- Do batches or transactions impose LOB restrictions?

Never materialize huge BLOBs into byte[] if sizes can exceed safe memory budgets. For large files, stream in chunks and limit concurrency.

Test with empty payloads, nulls, payloads smaller than buffers, larger than buffers, and near application limits. Verify uploads, downloads, cancellation, and cleanup.

## 10. JSON, Arrays, Enums, and Specialized Data Types

An application migrating from PostgreSQL to Oracle may rely on jsonb, arrays, native enums, or custom operators. Never assume Oracle represents these or the driver maps them identically.

Inventory all specialized data types in use:

- JSON documents and JSON query operators.
- SQL arrays.
- Enums.
- UUIDs.
- Spatial/geospatial types.
- XML.
- User-defined object types.
- Binary/RAW.
- Full-text or vector types if used.

For each type, determine:

1. Which Oracle Database version supports the type?
2. Can the driver bind and read it via the R2DBC SPI?
3. Is a Spring Data converter built in, or is a custom converter needed?
4. Are query operators portable?
5. Are suitable indexes and execution plans available?
6. Does data round-trip without losing precision or formatting?

If no standard mapping exists, you can store JSON in text/CLOB or use a dedicated adapter, weighing indexing, validation, queryability, and conversion costs. Never pick a workaround type simply because a trivial test runs.

## 11. Identifiers, Schemas, and Metadata

Oracle stores unquoted identifiers in uppercase by default; quoted identifiers preserve case sensitivity. This can affect:

- Table and column names in @Table and @Column.
- Aliases in native queries.
- Schemas and owners.
- Metadata returned by RowMetadata.
- How Spring Data renders identifiers.
- Migrations creating quoted table names.

Example:

~~~sql
CREATE TABLE CUSTOMER (
    ID NUMBER(19) PRIMARY KEY,
    EMAIL VARCHAR2(200) NOT NULL
);
~~~

If you create quoted lowercase identifiers:

~~~sql
CREATE TABLE "customer" (
    "id" NUMBER(19) PRIMARY KEY
);
~~~

then quoted names must be referenced with the exact casing used at creation. Avoid mixing quoted and unquoted rules without strong reason.

When using projections or DatabaseClient, use explicit aliases:

~~~sql
SELECT c.ID AS CUSTOMER_ID,
       c.EMAIL AS CUSTOMER_EMAIL
FROM CUSTOMER c;
~~~

Verify how the driver returns column names and how label/index lookups behave. Never assume metadata casing matches PostgreSQL.

## 12. Sequences, Schema Owners, and Permissions

Oracle organizes objects by schema owner. The connecting user may not own the tables and will need explicit grants.

Before deploying, check:

- Does the connecting user have SELECT/INSERT/UPDATE/DELETE grants on the tables?
- Does it have privileges to use sequences?
- Are synonyms used, and how do the driver/schema metadata handle them?
- How is the current schema/session configured?
- Which user runs migrations?
- Which schema owns the objects?
- Do quoted identifiers and owner names match?

Never run applications as a DBA or overly privileged schema owner just to bypass permission errors. Create a least-privilege runtime user and a separate migration user if deployment processes require it.

## 13. Transaction Isolation and DDL Semantics

Isolation levels do not share identical semantics across database engines.

Oracle typically defaults to READ COMMITTED and supports SERIALIZABLE with its own consistency model. Never assume Oracle provides exact REPEATABLE READ behavior matching PostgreSQL or SQL Server. Check Oracle documentation and how the driver maps R2DBC SPI isolation requests.

Questions to verify:

- Which isolation levels does the driver accept?
- Does setTransactionIsolationLevel actually alter the session?
- Does the database reject or remap unsupported levels?
- Is snapshot consistency statement-level or transaction-level?
- How does the driver represent serialization/transaction conflicts?
- Do savepoints work through the driver?
- Are read-only transactions enforced by the database?

### 13.1. DDL Can Trigger Implicit Commits

Oracle's DDL semantics differ from several other engines: most DDL statements issue implicit commits before and after execution. Therefore, never assume CREATE TABLE, ALTER TABLE, or DROP TABLE can roll back like ordinary DML.

This matters in tests using @Transactional rollbacks. DDL executed during a test can persist after rollback or affect transactions unexpectedly.

Run migrations and schema setup in a dedicated initialization phase, separate from business transaction tests. If testing DDL itself, use ephemeral databases/schemas and verify behavior directly.

### 13.2. Savepoints and Nested Transactions

Spring's NESTED propagation typically relies on savepoints. Verify whether the Oracle driver supports the savepoint operations required by the transaction manager in your release.

Never infer REQUIRES_NEW, NESTED, or isolation behavior from annotations alone. They also depend on the connection pool, transaction manager, and driver.

## 14. Locking and Engine-Specific Clauses

Oracle supports row locking such as SELECT ... FOR UPDATE; options like NOWAIT, WAIT, and SKIP LOCKED carry specific semantics.

Illustrative example:

~~~sql
SELECT id, available_quantity
FROM INVENTORY
WHERE id = :id
FOR UPDATE;
~~~

Verify placeholders and exact syntax with the Oracle R2DBC driver. Locks are typically held until the transaction commits or rolls back. Longer transactions increase lock contention.

If using SKIP LOCKED for worker job queues, define behavior when no rows are available and prevent starvation. With NOWAIT, lock conflicts may need translation into retries or business conflict responses.

Other engines have different locking syntax and behavior. Do not put locking queries in shared repositories expecting them to work unmodified across all drivers.

## 15. Stored Procedures, Functions, and Multiple Results

Stored procedures and functions vary widely across Oracle, PostgreSQL, SQL Server, and MySQL:

- Invocation syntax.
- IN/OUT/IN OUT parameters.
- Cursors/ref cursors.
- Multiple result sets.
- Returned object/record types.
- Transaction behavior inside procedures.
- Exceptions and error codes.

The R2DBC SPI models Result, yet support for OUT parameters or specific cursors depends on the driver. Never assume a JDBC stored procedure call maps directly to the same R2DBC APIs.

If an application depends on procedures:

1. Build an isolated spike against the target driver.
2. Invoke a procedure with simple inputs.
3. Test scalar outputs.
4. Test cursors/result sets.
5. Test nulls, numeric types, and LOBs.
6. Test errors raised inside the procedure.
7. Test transaction commit/rollback behavior.
8. Test cancellation and connection cleanup.

If the driver lacks adequate support, consider replacing procedures with SQL or service-side orchestration, or maintaining a separate JDBC adapter if architecture permits dual connection models.

## 16. Batches and Multiple Statements

Not all drivers implement batches or Statement.add() with identical performance and behavior.

Verify:

- Does the batch execute every binding set?
- Does getRowsUpdated() emit one count or multiple counts?
- Does an error mid-batch halt subsequent items?
- Can partial results be committed?
- Can batches return generated keys per row?
- Are there limits on batch size or parameter counts?
- Do batches behave properly inside transactions?

When atomicity is required, wrap batches in a transaction and test rollback on the target database. Never assume a batch is automatically atomic.

Measure throughput and memory with realistic batch sizes. Overly large batches can pressure memory, locks, or redo/undo logs.

## 17. Cancellation, Timeouts, and Connection Pools

Reactive APIs let subscribers cancel subscriptions, yet drivers differ in how they send cancels to the database and reclaim resources.

Verify:

- Does cancelling a running SELECT abort the server-side statement?
- Could cancelling an INSERT before receiving the response have already committed on the server?
- Are connections safely returned to the pool after cancellation?
- Are statement timeouts and transaction timeouts distinct?
- Are pool acquisition timeouts distinguished from query timeouts?
- Does the driver validate/reset connections before returning them to the pool?

Never retry a write solely because the client observed cancellation. The database may have executed and committed the operation before the cancel arrived. Use idempotency keys, unique constraints, or status checks to safely resolve outcomes after timeouts.

When sizing pools, measure:

- Active and idle connection counts.
- Connection acquire wait times.
- Validation failure counts.
- Disposed connection counts.
- Query and transaction durations.
- Timeout and cancellation rates.

Never share one connection across concurrent requests unless explicitly supported by the driver and API; normally each transaction requires clear connection ownership.

## 18. TLS, Wallets, and Real-World Oracle Connections

Oracle deployments may require TLS/TCPS, wallets, certificates, or custom authentication mechanisms. Connection option configuration depends on driver version and the Oracle environment.

Before production:

- Confirm the driver supports the TLS mode and certificate chain in use.
- Confirm wallets/credentials are mounted and loaded from a secret manager.
- Verify hostname verification and certificate rotation.
- Never disable certificate verification just to test connectivity.
- Never log passwords or wallet secrets.
- Test connectivity from the exact container/VM/runtime used in production.
- Measure connection establishment time and failover behavior.

A successful connection from a developer laptop does not prove production deployments have the right network routes, wallets, and permissions.

## 19. Error Codes and Exception Translation

The same business error can produce different exception subtypes, SQLStates, or vendor codes between Oracle and other drivers.

Examples:

- Unique constraint violations.
- Foreign key violations.
- Deadlocks or lock timeouts.
- Serialization conflicts.
- Lost connections.
- Invalid SQL.
- Data conversion errors.

Spring can translate R2DBC errors into DataAccessException, though exact subtypes depend on information exposed by the driver and your Spring version's translator.

Never hard-code PostgreSQL SQLStates or Oracle vendor codes inside domain services. If specific constraints must be distinguished, place that logic in a database-specific adapter and test with real errors.

Test exception translation by intentionally triggering real unique/FK violations rather than only mocking DuplicateKeyException.

## 20. Feature Verification Matrix Before Choosing a Driver

Build a matrix covering the features your application actually uses:

| Category | Checks | Required Evidence |
|---|---|---|
| Connectivity | URL, authentication, TLS/wallet, failover | Smoke test in production-like environment |
| Compatibility | Java, SPI, driver, Spring Boot, database versions | Dependency matrix/release notes |
| Dialect | Resolver selects correct dialect | Integration tests and actual generated SQL |
| CRUD | Insert, select, update, delete | Repository tests |
| Binding | Positional/named markers, nulls, numbers, timestamps | Typed bind tests |
| Pagination | Pageable, multi-column sort, large offsets | First/middle/last page tests |
| Generated keys | Identity, sequences, returning generated values | Single and batch insert tests |
| Mapping | NUMBER, DATE, TIMESTAMP, RAW, LOB, JSON | Round-trip tests |
| Transactions | Commit, rollback, isolation | Two-connection tests |
| Locking | FOR UPDATE, NOWAIT, SKIP LOCKED | Concurrent integration tests |
| Savepoints | Nested transactions | Rollback-to-savepoint tests |
| DDL | Migrations and implicit commits | Clean database tests |
| Batches | Add bindings, counts, mid-batch errors | Integration tests |
| Procedures | IN/OUT, cursors, multiple results | Real procedure tests |
| Cancellation | Cancel SELECT/INSERT, cleanup | StepVerifier and pool metrics |
| Error translation | Constraints, timeouts, locks, network | Assert real exceptions/causes |
| Performance | Query plans, pools, throughput, LOB memory | Load tests and execution plans |
| Operations | Metrics, tracing, health checks, secret rotation | Deployment-like environment tests |

Not every application needs every row. Mark unused features N/A; mark untested features Unknown. Never change Unknown to Supported simply because code compiles.

## 21. Minimum Smoke Test Suite for Oracle R2DBC

Before writing full repositories, create a small test module connected to your exact Oracle version and run:

1. Create and close a connection.
2. SELECT a constant or single row from a test table.
3. Parameterized SELECT.
4. Typed SQL NULL binding.
5. INSERT and read generated ID or sequence.
6. UPDATE and verify rows updated.
7. DELETE and verify constraints.
8. Read integer and decimal NUMBER columns.
9. Round-trip DATE/TIMESTAMP with fractional seconds.
10. Read/write LOBs if used by the application.
11. Commit and roll back a transaction.
12. Test isolation/locking using two connections.
13. Run a paginated query.
14. Cancel a publisher and inspect connection pool state.
15. Trigger unique/FK violations and inspect exceptions.
16. Run migrations against a fresh database.

Automate smoke tests in CI if Oracle is the production database. Use the exact driver, Spring Data version, and connection settings intended for deployment.

## 22. Comparing Differences With Other Drivers

When comparing Oracle against PostgreSQL, MySQL/MariaDB, SQL Server, or H2, use a comparison checklist rather than product names alone:

| Area | Oracle | PostgreSQL | MySQL/MariaDB | SQL Server | H2 |
|---|---|---|---|---|---|
| Pagination syntax | OFFSET/FETCH on supported versions; legacy alternatives exist | LIMIT/OFFSET | LIMIT/OFFSET | OFFSET/FETCH requiring ORDER BY | Own syntax depending on compatibility mode |
| Generated IDs | Sequences/identity and driver generated values | Identity/sequences, often RETURNING | Auto-increment | Identity/sequences, OUTPUT | Identity/sequences |
| Bind markers | Per Oracle R2DBC release | Per PostgreSQL driver | Per driver | Per driver | Per driver |
| JSON/arrays | Depends on Oracle type and driver | Rich JSONB/arrays | JSON and differing array support | JSON/TVP depending on version | Version-dependent |
| Isolation | Default usually READ COMMITTED; SERIALIZABLE | MVCC and distinct levels | Engine-dependent, typically InnoDB | Levels and snapshots by configuration | Not representative of production engines |
| DDL transactions | Most DDL triggers implicit commit | Most DDL is transactional | Statement/engine-dependent | Statement-dependent | Differs from production |
| LOBs | BLOB/CLOB/NCLOB | Large objects/bytea/text | BLOB/TEXT | LOB types | Compatible types |
| Error codes | Oracle SQL/vendor codes | SQLState/vendor codes | SQLState/vendor codes | SQLState/vendor codes | Own codes |

This table indicates where to inspect differences, not version-certified compatibility. Each driver has distinct releases and capabilities. In particular, H2 compatibility modes do not make H2 behave like real Oracle or PostgreSQL.

## 23. Mistakes When Migrating From Another Database to Oracle

| Assumption | Risk | Action Required |
|---|---|---|
| LIMIT works on Oracle | Syntax error | Use dialect or version-appropriate Oracle SQL |
| NUMBER always maps to Long | Precision loss or overflow | Pick Java type from precision/scale |
| Oracle DATE holds only date | Time portion dropped | Pick suitable Java type |
| Sequences behave like auto-increment | Wrong IDs or non-portable queries | Verify sequences/identity and generated keys |
| RETURNING matches PostgreSQL | Driver does not support the same invocation | Test returnGeneratedValues and Oracle syntax |
| Placeholder ? works in every driver | Binding fails | Use the driver/dialect bind markers |
| Every dialect handles Pageable identically | Broken pagination SQL | Test generated SQL on target database |
| REPEATABLE_READ is always available | Driver/database rejects or remaps | Verify supported isolation levels |
| DDL rolls back like DML | Schema mutates despite test rollback | Separate migrations from transaction tests |
| @Transactional keeps all raw SQL in one transaction | Operations use separate connections or commit independently | Verify resource binding |
| Passing H2 tests proves Oracle passes | Different SQL, types, and transaction semantics | Run Oracle integration tests |
| Exception subtypes match across drivers | Wrong business error mapping | Assert real exceptions on target driver |
| Cancellation means statement never ran | Write may have already committed | Design idempotency and status checks |
| Batches are automatically atomic | Partial writes may commit | Wrap in a transaction for atomicity |

## 24. Pre-Adoption Decision Process

Before adopting Oracle R2DBC or switching drivers, follow these steps:

1. List database, driver, Spring Boot/Data, and Java versions.
2. Read the compatibility matrix, release notes, and type-mapping docs for the exact driver.
3. Verify Spring Data dialect support and that the resolver picks the right dialect.
4. Inventory the persistence features the application actually needs.
5. Build a small spike checking connectivity, binding, CRUD, generated keys, and transactions.
6. Verify critical data types, LOBs, timezones, and nulls.
7. Verify pagination, locking, isolation, savepoints, and DDL.
8. Verify error translation, cancellation, pooling, and TLS.
9. Run integration tests on the real database/driver, not just H2.
10. Measure execution plans, latency, throughput, and memory with production-like data.
11. Classify features as Supported, Unsupported, Workaround, or Unknown.
12. Proceed to implementation only once mandatory features have test evidence and acceptable workarounds.

A driver decision record should capture exact versions, reference docs, test results, and known limitations. Whenever upgrading the driver or database, rerun the matrix since behavior can change.

## 25. Key Takeaways

- R2DBC SPI unifies the reactive API, not all SQL syntax or database features.
- Verify the database engine, R2DBC driver, and Spring Data dialect independently.
- Oracle R2DBC has its own versions, dependencies, and capabilities; consult the compatibility matrix for your chosen release.
- Never replace an R2DBC URL with a JDBC URL and never infer non-blocking execution from return types alone.
- Oracle pagination, bind markers, sequences, generated values, and identifier semantics differ from other database engines.
- Oracle NUMBER, DATE, timestamps, LOBs, and specialized types require round-trip tests with real Java types.
- Isolation, savepoints, locking, and DDL semantics must be verified on the target Oracle version.
- returnGeneratedValues, batching, procedures, cancellation, and metadata are driver capabilities requiring verification.
- The Spring Data dialect must recognize Oracle properly; manual SQL working on the driver does not prove repositories generate valid SQL.
- Never use H2 compatibility modes as evidence replacing integration tests on the production database.
- Test real constraint errors and SQLStates; do not assume identical exception subtypes across drivers.
- Cancellation or timeouts do not prove writes failed to commit; design idempotent retries.
- Maintain a versioned matrix of Supported/Unsupported/Workaround/Unknown and re-verify on upgrades.
- Only promote a driver to production once mandatory features are backed by tests and operational trials.
