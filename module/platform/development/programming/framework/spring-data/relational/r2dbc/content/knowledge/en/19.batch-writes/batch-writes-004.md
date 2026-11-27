# Multi-Row SQL Inserts and Database Engine Limits

When writing multiple records with Spring Data Relational R2DBC, a multi-row INSERT statement can reduce the number of commands sent to the database compared to executing one INSERT per entity. However, the number of rows that can fit into a single statement is not unlimited. Bind parameter limits, packet size, SQL length, application memory, transactions, database-specific syntax, and R2DBC driver capabilities all affect batch size.

The common syntax is:

~~~sql
INSERT INTO products (name, price, status)
VALUES
    ('Keyboard', 49.90, 'ACTIVE'),
    ('Mouse', 19.90, 'ACTIVE'),
    ('Monitor', 229.00, 'ACTIVE');
~~~

In an application, never concatenate values directly into SQL like the illustrative example above. Generate placeholders and bind each value instead. Table and column names must be fixed or chosen from a server-side allowlist.

This lesson explains how to build a multi-row INSERT with DatabaseClient, how to distinguish it from R2DBC Statement.add(), how to calculate bind parameter and packet limits, the differences across PostgreSQL, MySQL/MariaDB, SQL Server, SQLite, and Oracle, how to pick a chunk size, and how to handle generated keys, transactions, errors, and testing against real databases.

## 1. What is a multi-row INSERT?

A multi-row INSERT inserts multiple tuples in a single statement:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada Lovelace', 'ada@example.test'),
    ('Grace Hopper', 'grace@example.test'),
    ('Katherine Johnson', 'katherine@example.test');
~~~

If there are N rows and each row has C bound columns, the approximate total number of bind parameters is:

\[
P = N \times C
\]

If the statement also has K shared parameters, the total is:

\[
P = N \times C + K
\]

Therefore, if the database/driver allows at most Pmax parameters, the maximum number of rows based solely on the parameter limit is:

\[
N_{max} = \left\lfloor \frac{P_{max} - K}{C} \right\rfloor
\]

This is only one limit. Actual row count is further constrained by packet size, SQL text size, vendor syntax row limits, memory, execution time, and transaction budget.

### Comparison with row-by-row writes

Suppose you need to insert 1,000 rows, each with 5 columns:

- Row-by-row writes: typically 1,000 INSERT executions.
- Multi-row INSERT: can split into 10 statements of 100 rows each.
- Statement batch: can send the same SQL statement with 1,000 binding sets, depending on the driver.
- Bulk loader: uses the database's dedicated data loading protocol.

Multi-row INSERTs usually reduce execution count and round-trips. However, they do not let the database skip indexes, constraints, triggers, WAL/redo logging, or actual data write cost.

## 2. How multi-row INSERT differs from saveAll and Statement.add()

The following mechanisms are often grouped together as "batching" but have different semantics.

| Mechanism | How it works | Is it a single SQL with multiple VALUES? |
| --- | --- | --- |
| repository.save per entity | Calls save logic for each entity. | No. |
| repository.saveAll | Multi-entity save API; implementation may still save per entity. | Not guaranteed. |
| buffer(chunk) + saveAll | Groups items at the application layer, then calls saveAll. | Not automatically. |
| R2DBC Statement.add() | Multiple binding sets for one statement, if supported by driver. | Not necessarily. |
| Multi-row INSERT | One INSERT statement containing multiple VALUES tuples. | Yes. |
| Bulk loading | Uses a dedicated loading protocol/API. | Does not necessarily use INSERT. |

The name saveAll is not a promise that Spring Data emits a single multi-row INSERT statement. If you want to pack multiple tuples into one statement, you must control the SQL or use a driver-supported batch API.

### When to choose which approach?

- Saving a few entities in a request: repository.save is usually simplest.
- Saving a moderate set needing Spring Data mapping: saveAll after checking implementation and performance.
- Needing one INSERT statement with multiple tuples: DatabaseClient and multi-row VALUES.
- Executing the same SQL repeatedly: consider Statement.add() if supported by the driver.
- Very large imports: consider a bulk loader such as PostgreSQL COPY or equivalent.

## 3. Using DatabaseClient for multi-row INSERT

DatabaseClient lets you build SQL with a specific number of tuples and bind values. Fixed two-row example:

~~~java
Mono<Integer> insertTwoPeople(
        DatabaseClient databaseClient,
        String firstEmail,
        String secondEmail) {

    return databaseClient.sql("""
        INSERT INTO people (first_name, email)
        VALUES (:name0, :email0), (:name1, :email1)
        """)
        .bind("name0", "Ada Lovelace")
        .bind("email0", firstEmail)
        .bind("name1", "Grace Hopper")
        .bind("email1", secondEmail)
        .fetch()
        .rowsUpdated();
}
~~~

The email and name values are bound. The SQL text contains only the table name, column names, and fixed placeholders.

### Generating a dynamic number of tuples

When row count varies per chunk, generate placeholders from the index. Indices are generated by the application, never taking SQL fragments from the request.

~~~java
Mono<Long> insertPeople(
        DatabaseClient databaseClient,
        List<PersonInput> people) {

    if (people.isEmpty()) {
        return Mono.just(0L);
    }

    String tuples = IntStream.range(0, people.size())
        .mapToObj(i -> "(:name" + i + ", :email" + i + ")")
        .collect(Collectors.joining(", "));

    String sql = """
        INSERT INTO people (first_name, email)
        VALUES %s
        """.formatted(tuples);

    DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql);

    for (int i = 0; i < people.size(); i++) {
        PersonInput person = people.get(i);
        spec = spec
            .bind("name" + i, person.name())
            .bind("email" + i, person.email());
    }

    return spec.fetch()
        .rowsUpdated()
        .map(Integer::longValue);
}
~~~

The snippet illustrates two non-null columns. For nullable fields, DatabaseClient does not accept null via regular bind; use bindNull with the corresponding Java type:

~~~java
spec = spec.bindNull("nickname" + i, String.class);
~~~

Choose a bind type matching the mapping and driver. For enums, JSON, arrays, or value objects, converters or specialized types may be needed.

### Safety rules

- Table and column names are fixed in code or come from an allowlist.
- Placeholder indices are generated from row counts.
- All data values are bound.
- Never concatenate name/email values into SQL text.
- Explicitly reject or handle empty lists.
- Cap chunk size before building SQL.
- Never build an unbounded SQL statement from an entire import file.

## 4. Bind parameters and calculating maximum rows

Suppose each row has 8 bound columns, the statement has 2 additional shared parameters, and the driver/database limit is 2,100 parameters:

\[
N_{max} = \left\lfloor \frac{2100 - 2}{8} \right\rfloor = 262
\]

262 rows is the maximum based solely on the parameter limit in this example. Do not pick this exact maximum by default because of overhead and other constraints. Start lower and benchmark.

### Calculating across multiple limits

A safe chunk size should consider all constraints simultaneously:

\[
N \leq \min(
N_{parameters},
N_{packet},
N_{statement},
N_{vendor},
N_{application}
)
\]

Where:

- Nparameters: bind parameter limit divided by parameters per row.
- Npacket: packet/message limit divided by average payload size.
- Nstatement: SQL length limit and parse time.
- Nvendor: engine syntax/row limits.
- Napplication: memory, latency, and transaction budgets set by the application.

Packet limits cannot be computed accurately from Java object sizes alone. Account for protocol framing, encoding, parameter names, and SQL text.

### Do not use the maximum as the default chunk size

Even if a database allows 2,100 parameters, a 2,100-parameter batch is not necessarily optimal. Large statements can incur heavy parse time, consume memory, create long transactions, and make a single chunk failure affect more rows.

Pick a threshold well below technical limits, measure throughput and p95/p99 latency, and adjust.

## 5. PostgreSQL limits and characteristics

PostgreSQL supports multi-row VALUES:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test');
~~~

Generated values can be returned with RETURNING:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test')
RETURNING id, first_name, email;
~~~

### Bind parameter limit

The PostgreSQL extended query protocol uses a 16-bit parameter count field; the commonly cited limit is 65,535 parameters per prepared/extended statement. That is a protocol ceiling, not a recommendation to build statements with tens of thousands of parameters.

With 10 bound columns per row, the theoretical parameter ceiling is around 6,553 rows, before accounting for statement size, memory, packet, and driver limits.

### RETURNING

RETURNING is useful when you need database-generated IDs or columns. For multi-row INSERTs, the result can contain multiple rows. To match results back to the right inputs, include an explicit business key or correlation key; do not assume returned row order always matches input order unless database/driver semantics are confirmed.

### COPY for large imports

For very large datasets, PostgreSQL COPY is often more efficient than generating huge INSERT statements. COPY has its own API/protocol, data streaming format, and semantics. The R2DBC SPI does not provide a portable COPY API; a supported PostgreSQL-specific driver or library is required.

COPY fits large ETL/imports. If you need domain validation, generated IDs, callbacks, or per-row error mapping, additional steps must be designed.

## 6. MySQL/MariaDB limits and characteristics

MySQL and MariaDB support multi-row INSERT:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test'),
    ('Katherine', 'katherine@example.test');
~~~

Vendor upsert syntax can be used, such as MySQL/MariaDB's ON DUPLICATE KEY UPDATE. This is vendor-specific syntax, and update semantics on key collision must be defined clearly.

### max_allowed_packet

A critical limit is packet size. max_allowed_packet configures the maximum message size accepted by client/server. A multi-row INSERT can be rejected when SQL text plus bound values exceeds the packet limit.

Default and maximum values depend on version, server configuration, and client/driver. Do not hard-code one universal number for all MySQL/MariaDB deployments. Check your actual server and driver configuration.

### Prepared statement parameters

MySQL's prepared statement protocol represents parameter counts using a 16-bit field, though packet size, statement size, and driver behavior are often the practical limits to watch simultaneously. Do not rely solely on a parameter count to pick batch size.

### Generated IDs

With AUTO_INCREMENT, the driver may expose generated values depending on the R2DBC implementation. Do not infer every ID in a multi-row insert by taking the first ID and incrementing by 1: concurrent inserts, auto-increment increment/offset settings, triggers, and server config can invalidate that assumption.

To map generated IDs accurately back to inputs, use driver-supported generated values APIs or re-query by a unique business key.

## 7. SQL Server limits and characteristics

SQL Server supports the table value constructor in INSERT:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test');
~~~

### 1,000-row limit in INSERT ... VALUES

SQL Server limits a table value constructor used directly in INSERT ... VALUES to 1,000 rows per statement. A table value constructor used as a derived table in certain SELECT contexts has different limit semantics, though syntax should not be converted mechanically without inspecting execution plans and version documentation.

### 2,100-parameter limit

SQL Server has a 2,100-parameter limit for stored procedures and functions; parameter limits on statements executed via drivers are also a practical constraint to verify with your provider/version. When using prepared statements with many bind markers, keep total parameters below 2,100 to avoid hitting the limit.

With 10 bound columns per row, the theoretical 2,100-parameter cap allows only about 210 rows, lower than the 1,000-row VALUES limit. The parameter limit often becomes the binding constraint first.

### OUTPUT INSERTED

SQL Server uses OUTPUT INSERTED to return generated values:

~~~sql
INSERT INTO people (first_name, email)
OUTPUT INSERTED.id, INSERTED.first_name
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test');
~~~

This syntax differs from PostgreSQL's RETURNING. Check whether your driver supports returning generated rows in an R2DBC statement.

### Bulk copy and table-valued parameters

For large imports or tabular payloads, SQL Server offers mechanisms such as bulk copy and table-valued parameters. Availability from R2DBC depends on the driver/library. A vendor-specific integration path may be needed instead of expressing every workload as a massive INSERT statement.

## 8. SQLite limits and characteristics

SQLite supports multi-row VALUES:

~~~sql
INSERT INTO people (first_name, email)
VALUES
    ('Ada', 'ada@example.test'),
    ('Grace', 'grace@example.test');
~~~

An important constraint is the number of host parameters in a prepared statement.

- SQLite versions prior to 3.32.0 typically default SQLITE_MAX_VARIABLE_NUMBER to 999.
- Starting with SQLite 3.32.0, the default is typically 32,766.
- The actual limit can be changed at compile time via SQLITE_MAX_VARIABLE_NUMBER or lowered at runtime via sqlite3_limit.

This is a build/runtime-configurable limit, not an immutable constant across all SQLite distributions.

### Batch calculation example

If SQLite uses a 999-variable limit and each row has 6 bind parameters:

\[
N_{max} = \left\lfloor \frac{999}{6} \right\rfloor = 166
\]

If the binary uses the 32,766 limit, the theoretical ceiling is much higher. Applications should check the actual version/build or pick conservative chunk sizes compatible with the deployment environment.

### SQLite and concurrency

SQLite is an embedded database without a server connection model like PostgreSQL. Concurrent writes can be constrained by locking and journal mode. Adding more connections does not scale write throughput linearly.

For contended write workloads, consider serializing writers, batching transactions, and using an appropriate busy timeout. Test on the exact driver and SQLite build your application uses.

## 9. Oracle: different syntax and strategies

Do not assume every database supports identical syntax:

~~~sql
INSERT INTO table_name (a, b)
VALUES (...), (...);
~~~

Traditional Oracle versions commonly use multi-table insert syntax like INSERT ALL or INSERT ... SELECT/array binding strategies rather than PostgreSQL/MySQL-style multi-row VALUES syntax. Syntax support varies by Oracle version; verify the documentation for your deployed database version.

INSERT ALL example:

~~~sql
INSERT ALL
    INTO people (first_name, email) VALUES ('Ada', 'ada@example.test')
    INTO people (first_name, email) VALUES ('Grace', 'grace@example.test')
SELECT 1 FROM dual;
~~~

This is Oracle-specific syntax. Each INTO clause is an insert target within the same statement.

### Array binding/batch execution

For many rows sharing the same SQL shape, driver array binding or batch execution can be a better fit than building a very long SQL string. With R2DBC, verify how the Oracle driver supports Statement.add() and generated values.

### IN-list limit is not the multi-row INSERT limit

Oracle has separate version-dependent limits on the number of expressions in an IN list; this limit must not be equated with INSERT ALL row counts or prepared statement bind parameter limits. When building IN queries, check your specific version and split lists or use an appropriate collection/table mechanism.

Do not use the IN-list limit as your chunk size for INSERTs.

## 10. Quick comparison across database engines

| Database | Multi-row insert | Common limits to check | Generated values / bulk mechanisms |
| --- | --- | --- | --- |
| PostgreSQL | VALUES (...), (...) | Extended protocol has a 65,535 bind parameter limit; plus statement/memory/driver limits. | RETURNING; COPY for large imports. |
| MySQL | VALUES (...), (...) | max_allowed_packet, statement size, and prepared parameter count. | AUTO_INCREMENT/driver generated values; bulk/load utilities. |
| MariaDB | VALUES (...), (...) | max_allowed_packet and driver/server version limits. | AUTO_INCREMENT; bulk/load utilities. |
| SQL Server | VALUES (...), (...) | 1,000 rows in INSERT VALUES; 2,100 parameters is a key limit. | OUTPUT INSERTED; bulk copy/TVP. |
| SQLite | VALUES (...), (...) | SQLITE_MAX_VARIABLE_NUMBER: commonly defaults to 999 before 3.32.0, 32,766 from 3.32.0; builds can differ. | last_insert_rowid/driver support; transaction batching. |
| Oracle | Version-dependent syntax; INSERT ALL/array binding are traditional options. | Bind, SQL size, and version-specific expression/IN-list limits. | RETURNING/array binding and driver bulk mechanisms. |

These figures are common technical reference points, not guaranteed settings across every distribution or driver. Always verify server version, build options, driver version, protocol, and actual configuration.

## 11. Packet and SQL size limits

Even when parameter count stays below the limit, a statement can still be too large.

Message size depends on:

- SQL text length and placeholder count.
- UTF-8 string sizes.
- JSON/BLOB/binary sizes.
- Encoded data types.
- Protocol framing and metadata.
- Whether the driver copies buffers in memory.

For example, 500 rows with 3 small numeric columns differ dramatically from 500 rows each carrying a few hundred KB of JSON.

### MySQL packets

MySQL/MariaDB have max_allowed_packet. If a statement or packet exceeds the configured setting, the server/driver may return a packet-too-large error or close the connection depending on the case. Check both client/server configuration and the driver.

### PostgreSQL messages and statements

PostgreSQL has a protocol parameter count limit, though statement text and message size are still subject to practical memory, protocol, and server limits. Do not target 65,535 parameters as a batch size.

### SQL Server and SQLite

SQL Server has row constructor and parameter limits. SQLite has build/runtime host parameter limits. In both, statement size and execution duration can still become limiting factors before hitting the parameter cap.

## 12. Choosing chunk size safely

Chunk size should be based on the lowest applicable limit, then reduced further for headroom.

A guiding formula:

\[
N_{chunk} = \min(
\lfloor P_{safe}/C \rfloor,
N_{packet},
N_{vendor},
N_{memory},
N_{latency}
)
\]

Where:

- Psafe is a parameter budget below the hard limit.
- C is columns/parameters per row.
- Npacket is the row count fitting the packet budget.
- Nvendor is the database syntax limit.
- Nmemory is the row count the application can safely retain.
- Nlatency is the row count processable within transaction/request budgets.

For example, with SQL Server, 8 bound columns per row, and a 1,800-parameter budget:

\[
N_{chunk} \leq \lfloor 1800/8 \rfloor = 225
\]

You might start at 100 or 150 rows, measure, and adjust upward. There is no need to push right up against the 2,100 limit.

### Chunk size depends on row shape

Do not use the same chunk size for every table. A table with 4 small columns can handle larger chunks than a table with 30 columns, large JSON, or binary data.

If a chunk rolls back, the entire chunk may need to be retried. Larger chunks also increase failure blast radius and transaction duration.

## 13. Handling empty lists and nulls

An empty list must not generate SQL:

~~~sql
INSERT INTO people (name, email) VALUES
~~~

Return Mono.just(0L) or Mono.empty according to the repository helper's contract.

Nullable fields must bind null with an explicit Java type:

~~~java
spec = spec.bindNull("middleName0", String.class);
~~~

Do not use bind("middleName0", null) if the API does not accept null. For enums or custom types, select the appropriate Java type/converter.

If a row has invalid data, decide before generating the statement:

- Reject the entire chunk.
- Filter out invalid rows and write a failure report.
- Subdivide to locate the failing row.
- Use a staging table to validate data before moving to the main table.

Never silently drop rows without reporting counts and reasons.

## 14. Generated IDs and insert results

A multi-row INSERT can generate multiple IDs. Retrieval mechanisms vary by database and driver:

| Database | Common mechanism |
| --- | --- |
| PostgreSQL | RETURNING id, ... |
| SQL Server | OUTPUT INSERTED.id |
| MySQL/MariaDB | AUTO_INCREMENT and driver-specific generated values |
| SQLite | last_insert_rowid per connection; driver-specific batch behavior |
| Oracle | RETURNING INTO or array/batch binding depending on API |

The R2DBC SPI includes Statement.returnGeneratedValues(...) in supported versions, though the driver must implement that capability. Check your driver version and run integration tests rather than assuming a portable API returns all generated IDs for every multi-row statement.

### Do not infer IDs by addition

Do not take the first generated ID and add 1 for subsequent rows. Sequence/identity IDs can be affected by concurrent inserts, increment/offset settings, rollbacks, triggers, sequence caches, and database configuration.

To correlate results with inputs, use a unique business key or correlation key stored with the row. When the database returns multiple rows via RETURNING/OUTPUT, map by a stable key rather than relying solely on position.

## 15. Transactions and atomicity

A multi-row INSERT is usually a single statement. If the statement fails, the database handles the statement according to its semantics. However, the final outcome also depends on transactions, constraints, triggers, and the database engine.

Options:

### One statement per chunk

Each chunk is one statement. Without a transaction spanning the whole import, earlier chunks may have committed when a later chunk fails.

### One transaction across multiple chunks

~~~java
return transactionalOperator.transactional(
    Flux.fromIterable(chunks)
        .concatMap(this::insertChunk)
);
~~~

If an error escapes the transaction boundary, all chunks within the transaction can roll back. The trade-off is a longer transaction holding connections and locks longer.

### One transaction per chunk

~~~java
return Flux.fromIterable(chunks)
    .concatMap(chunk ->
        transactionalOperator.transactional(insertChunk(chunk))
    );
~~~

Each chunk commits independently. When a later chunk fails, earlier chunks may remain committed. Checkpointing/idempotency is needed for safe retries.

### Transactions do not create batches

Wrapping 1,000 save calls in a transaction does not turn them into a multi-row INSERT. Transactions control atomicity, not the number of SQL statements.

## 16. Constraints, upserts, and duplicate handling

A multi-row INSERT can encounter a row violating UNIQUE, CHECK, or FOREIGN KEY constraints. How the database handles the statement and transaction depends on the vendor.

Common upsert syntaxes:

- PostgreSQL: ON CONFLICT ... DO NOTHING/DO UPDATE.
- MySQL/MariaDB: ON DUPLICATE KEY UPDATE.
- SQL Server: conditional UPDATE/INSERT or appropriate mechanism; use caution with MERGE depending on version/semantics.
- SQLite: ON CONFLICT.
- Oracle: MERGE or appropriate insert/update mechanism.

Do not use one upsert syntax across all databases. Specify clearly whether duplicates should be skipped, updated, or raise a conflict. An upsert can overwrite newer data if update conditions are not strict enough.

### One failing row can fail the entire statement

If one tuple violates a constraint, the multi-row statement can fail. Do not assume other valid tuples were still written. Verify on the target database.

If per-row success/failure is required, use smaller chunks, pre-validate, or use a staging table to isolate errors. Never swallow exceptions and report the whole batch as succeeded.

## 17. Safe dynamic SQL

Generating a dynamic number of tuples is necessary, but only the placeholders should be generated from the count. Never let clients control table names, column names, or SQL expressions.

Safe example:

~~~java
String tupleSql = IntStream.range(0, rows.size())
    .mapToObj(i -> "(:name" + i + ", :price" + i + ")")
    .collect(Collectors.joining(", "));

String sql = """
    INSERT INTO products (name, price)
    VALUES %s
    """.formatted(tupleSql);
~~~

The table name products and column names name, price are fixed. The name/price values are bound.

If a table must be selected by tenant or archive, map a key through a server-side allowlist. Never concatenate request.tableName or request.sort into SQL.

### Do not use escaping instead of binding

Never manually wrap strings in quotes and concatenate them into SQL. Quotes, backslashes, encoding, and dialects each have specific rules. Bind parameters are the proper mechanism for values.

## 18. When to use Statement.add()?

R2DBC SPI Statement.add() adds the current binding set to the same statement's batch. General example:

~~~java
Statement statement = connection.createStatement(
    "INSERT INTO people (first_name, email) VALUES ($1, $2)"
);

statement
    .bind(0, "Ada")
    .bind(1, "ada@example.test")
    .add();

statement
    .bind(0, "Grace")
    .bind(1, "grace@example.test");

Publisher<? extends Result> results = statement.execute();
~~~

This example uses PostgreSQL positional markers. Other drivers may use different markers.

Statement.add() differs from multi-row VALUES:

- Multi-row: one SQL INSERT containing multiple tuples.
- Statement.add(): one SQL statement with multiple binding sets.
- The driver decides how the batch is transmitted and executed.
- Generated values and rowsUpdated can differ across drivers.

Do not assume Statement.add() is always faster than multi-row INSERT or always makes a single network round-trip. Measure with the real driver and database.

When acquiring a Connection manually, manage closing and transactions properly. Inside a Spring-managed transaction, use the connection managed by the transaction infrastructure; do not open a separate connection and expect it to join the current transaction.

## 19. Bulk loading when multi-row INSERT is no longer suitable

For very large datasets, a bulk loader is often more effective than building SQL with tens of thousands of tuples.

Database examples:

- PostgreSQL: COPY.
- MySQL/MariaDB: LOAD DATA or suitable import tooling.
- SQL Server: Bulk Copy API.
- Oracle: SQL*Loader, array binding, or driver bulk mechanisms.
- SQLite: a transaction with repeated prepared statements or chunked imports; SQLite lacks a server bulk protocol like PostgreSQL.

Bulk loading may require specific file formats, elevated privileges, or driver-specific APIs. Verify trigger, constraint, default, generated key, and transaction semantics. This is an option for large ETL/imports, not the default for a small HTTP request.

## 20. Optimizing when source data lives in the database

If the rows to insert come from another query in the same database, use INSERT ... SELECT instead of pulling rows into the application and sending them back:

~~~sql
INSERT INTO archived_orders (id, customer_id, status, total)
SELECT id, customer_id, status, total
FROM orders
WHERE created_at < :cutoff;
~~~

This cuts round-trips and avoids moving data through the application heap. It still requires transactions, indexes, and control over affected row counts.

In PostgreSQL, CTEs/RETURNING can be used when further processing is needed. Across other databases, syntax and capabilities differ. The cutoff value is still bound; table and column names remain fixed structure.

## 21. Testing multi-row INSERT on real databases

Use Testcontainers to test against your target database vendor. Tests should verify:

- Multi-row VALUES SQL syntax.
- Correct mapping of bound parameters.
- Affected row counts.
- Generated IDs or RETURNING/OUTPUT.
- Constraint behavior when one tuple fails.
- Chunk sizes staying within parameter/packet limits.
- Transaction rollback/commit as required.
- Null and custom type mapping.
- Duplicate/upsert semantics.

Integration test example with DatabaseClient:

~~~java
@Test
void insertsSeveralRowsInOneStatement() {
    String suffix = UUID.randomUUID().toString();

    StepVerifier.create(
        databaseClient.sql("""
            INSERT INTO people (first_name, email)
            VALUES (:name0, :email0), (:name1, :email1)
            """)
            .bind("name0", "Ada")
            .bind("email0", "ada-" + suffix + "@example.test")
            .bind("name1", "Grace")
            .bind("email1", "grace-" + suffix + "@example.test")
            .fetch()
            .rowsUpdated()
    )
    .expectNext(2)
    .verifyComplete();
}
~~~

The type of rowsUpdated may be Integer or Long depending on API version; assertions should match the actual Spring Data R2DBC version in use.

After inserting, query back by suffix to verify both rows. Do not rely solely on rowsUpdated, as triggers or conflict policies can affect semantics.

### Limit testing

You do not need to test millions of rows on every build. Keep fast unit tests for chunking logic and separate integration/performance tests for sizes near your chosen thresholds.

When testing vendor limits, use matching database versions and configurations. Do not extrapolate from H2 if production runs SQL Server or SQLite.

## 22. Benchmarking and choosing chunk size

Measure alternatives against the same schema, indexes, constraints, driver, and transaction semantics:

1. Sequential repository.save.
2. repository.saveAll.
3. buffer + saveAll.
4. Statement.add().
5. Multi-row INSERT.
6. Bulk loader if available.

Collect:

- Rows/second.
- Total import duration.
- p50/p95/p99 latency per chunk.
- Application CPU and heap.
- Database CPU/I/O.
- Connection pool active/pending/acquire duration.
- Transaction duration and lock waits.
- Error/retry counts.
- Replication lag if applicable.

Run multiple iterations, warm up the connection pool and prepared statements, and use identical payloads. Do not compare a transactional write path against a non-transactional one and conclude based purely on throughput.

### Stepping up chunk size

Start small, such as 50 or 100 rows, then test 200, 500, or 1,000 depending on row shape and vendor. Watch where throughput stops improving or latency/errors spike. Pick a level below that knee for headroom.

These are experimental starting points, not fixed recommendations for every database.

## 23. Common errors

| Error | Cause | Fix |
| --- | --- | --- |
| Too many bind parameters | N × C exceeds driver/database limit. | Reduce chunk size to fit parameter budget. |
| Packet too large | SQL/bind payload exceeds max packet/message. | Reduce chunk size or use a bulk loader. |
| SQL statement too long | Built an oversized VALUES query. | Split into chunks and measure parse time. |
| SQL syntax error on Oracle | Used multi-row VALUES syntax unsupported in that version. | Use vendor-appropriate INSERT ALL/array binding. |
| SQL Server reports too many row constructors | Exceeded 1,000 rows in INSERT VALUES. | Split into chunks or use an appropriate bulk mechanism. |
| SQLite variable number exceeded | Exceeded build's SQLITE_MAX_VARIABLE_NUMBER. | Reduce row count or check compile/runtime limits. |
| Duplicate fails entire chunk | One tuple violated UNIQUE. | Pre-validate, subdivide, or use upsert with clear semantics. |
| Generated IDs mismatched | Assumed contiguous IDs or RETURNING order. | Use driver-supported generated values/correlation keys. |
| saveAll is not faster | Implementation still persists per entity. | Use multi-row or batching after benchmarking. |
| Transaction too long | Chunk too large or whole import in one transaction. | Commit per chunk if business rules allow. |
| High memory usage | Built SQL and bound entire dataset at once. | Stream and buffer with bounded chunk sizes. |
| Retries create duplicates | Timeout after commit before response arrived. | Idempotency keys and unique constraints. |

## 24. Workflow for implementing safe multi-row INSERTs

When adding multi-row inserts for a repository or use case:

1. **Identify database and driver:** note exact vendor, version, and R2DBC driver.
2. **Check syntax:** multi-row VALUES, INSERT ALL, OUTPUT, RETURNING, or dedicated mechanisms.
3. **Count parameters per row:** count actual bindings, including extra fields.
4. **Check vendor limits:** parameters, row constructors, packets, statements, and IN-list limits separately.
5. **Choose chunk size with headroom:** never use the absolute ceiling as the default.
6. **Generate dynamic placeholders safely:** generate only from indices; never concatenate data into SQL.
7. **Bind every value:** use bindNull for nulls and converters for special types.
8. **Define generated values:** test RETURNING/OUTPUT or driver generated values.
9. **Choose transaction scope:** whole import or per chunk; define partial success behavior.
10. **Design duplicate/retry handling:** unique keys, upserts, and checkpoints.
11. **Integration test:** use Testcontainers matching production database.
12. **Benchmark:** measure throughput, latency, memory, and pool behavior.
13. **Monitor production:** statement sizes, acquire timeouts, errors, and import progress.

Multi-row INSERT reduces execution count by packing multiple tuples into one statement, though safe sizing depends on bind parameters, packets, statements, vendor syntax, and row shape. PostgreSQL, MySQL/MariaDB, SQL Server, SQLite, and Oracle have distinct limits and ways of returning generated values; there is no single portable batch size for all of them. Use placeholders and bind values, calculate chunks from the tightest limit, test transaction and error semantics on a real database, and move to a bulk loader only when workload scale justifies the added complexity.
