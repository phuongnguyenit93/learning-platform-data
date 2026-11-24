# Batch Update Writer in Spring Batch

In a chunk-oriented step, the reader fetches items, the processor normalizes or transforms them, and the writer persists results to the target system. When the target is a relational database and multiple items need to be written using the same SQL statement, Spring Batch provides `JdbcBatchItemWriter`. This writer uses JDBC batch updates to send multiple parameter sets for a single SQL statement in one chunk write.

Despite having "Batch" in its class name, `JdbcBatchItemWriter` is not limited to `UPDATE` statements. It can execute `INSERT`, `UPDATE`, or `DELETE` per item, as long as each item provides parameters for the configured SQL statement. This lesson focuses on batch writing, parameter binding, chunk transactions, checking affected row counts, error handling, and testing.

## 1. What Is a Batch Update Writer?

A simple way to write multiple items is calling `JdbcTemplate.update()` inside a loop:

~~~java
for (CustomerUpdate item : items) {
    jdbcTemplate.update(
        "update customer set status = ? where customer_id = ?",
        item.status(),
        item.customerId()
    );
}
~~~

This executes each update individually. When item counts are large, the application can generate many JDBC calls and round trips to the database.

`JdbcBatchItemWriter` receives an entire chunk, builds parameter sets for each item, and uses the JDBC batch mechanism to execute the same SQL statement with multiple parameter sets:

~~~text
Chunk<CustomerUpdate>
  |
  v
JdbcBatchItemWriter
  |
  +-- SQL: UPDATE customer SET status = ? WHERE customer_id = ?
  |
  +-- Parameters for item 1
  +-- Parameters for item 2
  +-- Parameters for item 3
  +-- ...
  |
  v
JDBC batchUpdate(...)
  |
  v
Database
~~~

Database drivers can optimize batch execution, reducing overhead compared to sending independent statements one by one. The actual improvement depends on driver, database, network, SQL, and chunk size; do not assume every batch always equals a single round trip.

## 2. When to Use JdbcBatchItemWriter

Use `JdbcBatchItemWriter` when each item maps to one execution of the same SQL statement:

- Updating status across many customers.
- Inserting many orders or transactions.
- Deleting many processed records.
- Writing normalized data into a staging table.
- Updating a target table by business key.

For example, a file contains customer update requests. The reader returns each `CustomerUpdate`; the processor validates and normalizes it; the writer sends all updates in the chunk to the database.

Do not use `JdbcBatchItemWriter` if the goal is simply running a single `UPDATE` affecting a large set of rows under one shared condition, such as updating all overdue records. That case usually fits `JdbcTemplate.update()`, a stored procedure, or a tasklet. `JdbcBatchItemWriter` is item-oriented: each item supplies one parameter set for the statement.

## 3. Configuring JdbcBatchItemWriter with Named Parameters

Named parameters make SQL easier to read than positional placeholders. You can use `BeanPropertyItemSqlParameterSourceProvider` to extract values from JavaBean properties:

~~~java
@Bean
JdbcBatchItemWriter<CustomerUpdate> customerUpdateWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<CustomerUpdate>()
        .dataSource(dataSource)
        .sql("""
            update customer
            set email = :email,
                status = :status,
                updated_at = :updatedAt
            where customer_id = :customerId
            """)
        .itemSqlParameterSourceProvider(
            new BeanPropertyItemSqlParameterSourceProvider<>()
        )
        .assertUpdates(true)
        .build();
}
~~~

Parameter names in SQL must correspond to properties exposed by the parameter source. For example, `:customerId` reads the value from property `customerId`. With JavaBeans, properties are typically discovered through getters; ensure the DTO has compatible accessors.

Example item:

~~~java
public class CustomerUpdate {

    private String customerId;
    private String email;
    private String status;
    private LocalDateTime updatedAt;

    public String getCustomerId() {
        return customerId;
    }

    public String getEmail() {
        return email;
    }

    public String getStatus() {
        return status;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
~~~

If using Java records, immutable objects, or special naming conventions, check the introspection support of your Spring Framework version. When exact control is needed, create a custom `ItemSqlParameterSourceProvider` or use `ItemPreparedStatementSetter`.

## 4. Configuring with ItemPreparedStatementSetter

If you want to use `?` positional placeholders, provide an `ItemPreparedStatementSetter`. The setter receives the current item and `PreparedStatement`, then binds each parameter:

~~~java
@Bean
JdbcBatchItemWriter<CustomerUpdate> customerUpdateWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<CustomerUpdate>()
        .dataSource(dataSource)
        .sql("""
            update customer
            set email = ?,
                status = ?,
                updated_at = ?
            where customer_id = ?
            """)
        .itemPreparedStatementSetter((item, ps) -> {
            ps.setString(1, item.getEmail());
            ps.setString(2, item.getStatus());
            ps.setTimestamp(
                3,
                Timestamp.valueOf(item.getUpdatedAt())
            );
            ps.setString(4, item.getCustomerId());
        })
        .assertUpdates(true)
        .build();
}
~~~

With `PreparedStatementSetter`, parameter order in code must match the exact order of `?` placeholders in the SQL. If you reorder columns in the SQL statement, you must update the binding indices accordingly.

Named parameters are usually easier to maintain when the SQL touches many columns. `PreparedStatementSetter` is useful when special data type binding is needed or when you want exact control over how parameters are set.

## 5. Bean Mapping and Custom Parameter Sources

Spring Batch supports multiple ways to produce parameters:

| Binding Approach | When Suitable |
| --- | --- |
| `BeanPropertyItemSqlParameterSourceProvider` | JavaBean properties match named parameter names |
| Custom `ItemSqlParameterSourceProvider` | Need to transform or compute parameters before binding |
| `ItemPreparedStatementSetter` | Using positional placeholders and controlling JDBC types |

A custom provider can return a `MapSqlParameterSource`:

~~~java
ItemSqlParameterSourceProvider<CustomerUpdate> provider = item ->
    new MapSqlParameterSource()
        .addValue("customerId", item.getCustomerId())
        .addValue("email", item.getEmail())
        .addValue("status", item.getStatus())
        .addValue("updatedAt", item.getUpdatedAt());
~~~

Then configure:

~~~java
new JdbcBatchItemWriterBuilder<CustomerUpdate>()
    .dataSource(dataSource)
    .sql("""
        update customer
        set email = :email,
            status = :status,
            updated_at = :updatedAt
        where customer_id = :customerId
        """)
    .itemSqlParameterSourceProvider(provider)
    .build();
~~~

A custom provider is helpful when field names differ from column names, when conversions are needed, or when items contain nested objects. Keep the provider stateless and perform no queries or side effects while creating the parameter source.

## 6. Using JdbcBatchItemWriter for INSERT

`JdbcBatchItemWriter` can insert one row per item:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderInsertWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            insert into imported_order
                (source_order_id, customer_id, total, status)
            values
                (:sourceOrderId, :customerId, :total, :status)
            """)
        .itemSqlParameterSourceProvider(
            new BeanPropertyItemSqlParameterSourceProvider<>()
        )
        .assertUpdates(true)
        .build();
}
~~~

Each item generates one parameter set for the same `INSERT` statement. If one item violates a unique constraint, the database may fail the batch. How drivers report update counts and details of the failing statement can vary.

If inputs may contain duplicate business keys, decide upfront whether to:

- Reject duplicates and let the step fail or skip the item per policy.
- Use upsert if business logic permits overwriting.
- Deduplicate before the writer.
- Route duplicate records into a quarantine table.

Do not assume `JdbcBatchItemWriter` automatically handles duplicates or converts `INSERT` into `UPDATE`.

## 7. Using JdbcBatchItemWriter for UPDATE

An update typically has a `WHERE` condition on a business key or primary key:

~~~sql
update customer
set status = :status,
    updated_at = :updatedAt
where customer_id = :customerId
~~~

Example item carrying update data:

~~~java
public record CustomerStatusChange(
    String customerId,
    String status,
    LocalDateTime updatedAt
) {}
~~~

If using a record, you can create an explicit `ItemSqlParameterSourceProvider`:

~~~java
ItemSqlParameterSourceProvider<CustomerStatusChange> provider = item ->
    new MapSqlParameterSource()
        .addValue("customerId", item.customerId())
        .addValue("status", item.status())
        .addValue("updatedAt", item.updatedAt());
~~~

Writer:

~~~java
new JdbcBatchItemWriterBuilder<CustomerStatusChange>()
    .dataSource(dataSource)
    .sql("""
        update customer
        set status = :status,
            updated_at = :updatedAt
        where customer_id = :customerId
        """)
    .itemSqlParameterSourceProvider(provider)
    .assertUpdates(true)
    .build();
~~~

The `WHERE` condition must narrow down to the exact intended record. If filtering only by a non-unique field, a single item could update multiple rows. Use a primary key or uniquely constrained business key when each item must correspond to exactly one row.

## 8. Using JdbcBatchItemWriter for DELETE

The writer can also delete records per item:

~~~java
@Bean
JdbcBatchItemWriter<ExpiredRecord> expiredRecordDeleteWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ExpiredRecord>()
        .dataSource(dataSource)
        .sql("""
            delete from temporary_record
            where record_id = :recordId
            """)
        .itemSqlParameterSourceProvider(
            new BeanPropertyItemSqlParameterSourceProvider<>()
        )
        .assertUpdates(true)
        .build();
}
~~~

If a record does not exist, `DELETE` may affect 0 rows. That could be an error you want to catch, or a valid outcome if the operation is designed to be idempotent. That decision governs `assertUpdates`.

## 9. assertUpdates and Update Counts

The builder provides the `assertUpdates` option. When enabled, `JdbcBatchItemWriter` inspects update counts returned for each item and raises an error if any statement affected zero rows. This is the common default behavior; configure it explicitly in code to express intent:

~~~java
.assertUpdates(true)
~~~

Example `UPDATE` by `customerId`:

~~~sql
update customer
set status = :status
where customer_id = :customerId
~~~

If `customerId` does not exist, the update count may be 0. With `assertUpdates` enabled, the writer throws `EmptyResultDataAccessException` instead of silently treating the item as updated.

`assertUpdates` verifies at least one row was affected; it does not guarantee that *exactly* one row was updated. If `WHERE` could match multiple rows and business rules require exactly one row, you need a unique constraint or update-count checks in a custom writer.

Some JDBC drivers return `SUCCESS_NO_INFO` when they know a batch statement succeeded without reporting an exact row count. Do not confuse this value with 0. Update count behavior must be verified against the actual driver and database.

## 10. When to Use assertUpdates(false)

You can disable the check:

~~~java
.assertUpdates(false)
~~~

This is appropriate when an update count of 0 is an acceptable result, such as:

- Deleting a record that was already deleted earlier.
- Updating status only when the record is currently in a specific state; not matching the condition can be a valid no-op.
- Using the writer for SQL where affecting zero rows is normal.

However, disabling `assertUpdates` can mask wrong business keys, missing source records, or buggy `WHERE` predicates. If every item must update a row, keep `assertUpdates` enabled and handle errors explicitly.

If you need to distinguish missing records from version conflicts or invalid states, a custom writer can query/inspect in greater detail. Do not simply turn off the assertion and ignore all zero-row updates.

## 11. Optimistic Locking in Batch Updates

When multiple processes can update the same row, optimistic locking helps detect data modified since it was read. Suppose a table has a `version` column:

~~~sql
update customer
set status = :status,
    version = version + 1
where customer_id = :customerId
  and version = :version
~~~

The item carries the version that was read:

~~~java
public record CustomerUpdate(
    String customerId,
    String status,
    long version
) {}
~~~

If the version in the database no longer matches, the `UPDATE` affects 0 rows. With `assertUpdates(true)`, the writer detects that the update failed. This may be an optimistic locking conflict rather than a missing record.

Do not blindly retry a version conflict using the same item and same version; the condition will continue to fail. You must re-read the data, reapply business logic, or route the record to a dedicated conflict-handling flow.

If you need to distinguish conflicts from missing rows, inspect with an additional query or custom writer, while keeping race conditions between checking and updating in mind. The unique key/version predicate remains the primary database safeguard.

## 12. Batch Updates and Upserts

Upsert means inserting if not present or updating if already present. Syntax depends on the database:

- PostgreSQL supports `INSERT ... ON CONFLICT ... DO UPDATE`.
- MySQL has `INSERT ... ON DUPLICATE KEY UPDATE`.
- Some databases support `MERGE` with their own syntax.

PostgreSQL example:

~~~sql
insert into customer_summary
    (customer_id, total_orders, updated_at)
values
    (:customerId, :totalOrders, :updatedAt)
on conflict (customer_id)
do update set
    total_orders = excluded.total_orders,
    updated_at = excluded.updated_at
~~~

`JdbcBatchItemWriter` can send this upsert SQL for each item as a batch. Check update counts and database-specific semantics; some upsert statements return different counts for inserts versus updates.

Do not assume one universal upsert syntax across databases. Write SQL for your target dialect and write integration tests against the actual engine.

## 13. Batch Updates with Nulls and SQL Types

Named parameter sources or `PreparedStatementSetter` must bind nulls with the right type. With some drivers, an untyped null can cause errors when the database cannot infer the SQL type.

With `MapSqlParameterSource`, you can specify the SQL type:

~~~java
new MapSqlParameterSource()
    .addValue("customerId", item.customerId(), Types.VARCHAR)
    .addValue("status", item.status(), Types.VARCHAR)
    .addValue("updatedAt", item.updatedAt(), Types.TIMESTAMP);
~~~

With `PreparedStatementSetter`, use the appropriate setter or `setNull`:

~~~java
if (item.getEmail() == null) {
    ps.setNull(1, Types.VARCHAR);
} else {
    ps.setString(1, item.getEmail());
}
~~~

A null parameter is normally sent as SQL `NULL`. It is not equivalent to omitting the column from an `INSERT` so the database applies a `DEFAULT`. If you need the database default, omit the column from the SQL or use appropriate `DEFAULT` syntax.

For monetary amounts, use `BigDecimal`; for dates/times, choose `LocalDate`, `LocalDateTime`, `Instant`, or a JDBC type matching the schema and driver. Avoid converting monetary amounts through `double` or formatting timestamps into strings unnecessarily.

## 14. Chunk Size and JDBC Batch Size

`JdbcBatchItemWriter` receives a `Chunk` from the step and generates batch parameters for the items in that chunk. If the processor filters items by returning null, the number of items actually reaching the writer is smaller than the number read by the reader.

Example:

~~~java
return new StepBuilder("updateCustomersStep", jobRepository)
    .<CustomerInput, CustomerUpdate>chunk(200, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(customerUpdateWriter)
    .build();
~~~

With chunk size 200, the writer typically receives at most 200 output items per write call. Chunk size also affects commit frequency, rollback scope, lock duration, and memory held in flight.

Do not confuse chunk size with the reader's page size. Page size controls how much data the reader fetches in one page query; chunk size controls how many items are processed within a single chunk transaction.

Larger chunks can improve batch efficiency but lengthen transactions and make rollbacks costlier. Smaller chunks shorten transactions but increase commit count and overhead. Benchmark with production-like data, database, and driver.

## 15. Optimizing JDBC Batch Performance

Factors affecting performance:

- Chunk size and number of parameter sets per batch.
- Whether the JDBC driver supports batching well.
- Whether the database optimizes/rewrites batch statements.
- Indexes on columns in `WHERE`.
- Table triggers, foreign keys, and constraints.
- Network latency between application and database.
- Available connections in the pool.
- Row width and data types being bound.

Practical guidelines:

1. Use one fixed SQL statement for all items in the same writer.
2. Update only the columns that actually need changing.
3. Ensure lookup columns in `WHERE` have appropriate indexes.
4. Pick chunk size through controlled benchmarks.
5. Avoid calling `JdbcTemplate.update()` individually per item when a batch writer can be used.
6. Avoid extra queries per item inside parameter providers.
7. Monitor write latency, lock waits, and database CPU.

Drivers may have batch optimization flags, such as rewriting multiple `INSERT`s into a more optimal SQL form. These options are vendor-specific and might not apply to `UPDATE`. Enable them only after reading driver documentation and benchmarking on your actual workload.

## 16. JdbcBatchItemWriter and Step Transactions

`JdbcBatchItemWriter` does not start or commit a transaction per item itself. In a chunk-oriented step, the step's transaction manager manages the transaction wrapping reading/processing/writing of the chunk as configured.

~~~text
BEGIN CHUNK TRANSACTION
  Read items
  Process items
  JdbcBatchItemWriter.write(chunk)
    -> JDBC batchUpdate
  Update execution context
COMMIT CHUNK
~~~

If the writer throws an exception configured to trigger rollback, the chunk transaction rolls back. Updates executed within that same database transaction will not be committed.

For this to hold, the datasource used by `JdbcBatchItemWriter` must participate in the transaction managed by the step's transaction manager. The standard setup uses the same `DataSource` for the writer and its corresponding transaction manager.

If the writer uses a different datasource or opens connections independently outside the transaction, operations may commit independently. In that case, step rollback is not guaranteed to undo those batch updates.

## 17. BatchUpdateException and Partial Failures

The JDBC driver may throw `BatchUpdateException` when one or more statements in the batch fail. The exception may contain update counts for statements that executed before the error or status indicators for statements in the batch.

Do not assume a batch always fails before any statement executes. Exact behavior depends on the driver and database.

If all statements participate in the same chunk transaction and the database supports rollback, transaction rollback undoes uncommitted changes. With autocommit, non-transactional tables, or external non-database resources, partial side effects may already persist.

When investigating failures:

- Record `SQLState`, vendor error code, and root cause.
- Identify the offending item/business key if the driver reports it.
- Check transaction manager and autocommit settings.
- Do not log full sensitive parameters.
- Use integration tests with the real driver to confirm behavior.

## 18. Retry and Skip on Batch Update Errors

Not all JDBC errors are suitable for retry or skip:

| Error | Typically Appropriate Handling |
| --- | --- |
| Transient deadlock | Bounded retry |
| Connection reset or temporarily unavailable resource | Retry if the exception is classified as transient |
| Duplicate key | Skip/quarantine if duplicates are allowed to be dropped; otherwise fail |
| Target row to update not found | Skip or fail depending on business rules |
| Version conflict | Re-read and resolve conflict; do not retry the same version indefinitely |
| Invalid column name or SQL syntax | Fail fast |
| Database out of disk space | Fail and address infrastructure |

Configuration example:

~~~java
return new StepBuilder("updateCustomersStep", jobRepository)
    .<CustomerUpdate, CustomerUpdate>chunk(200, transactionManager)
    .reader(reader)
    .writer(customerUpdateWriter)
    .faultTolerant()
    .retry(DeadlockLoserDataAccessException.class)
    .retryLimit(3)
    .skip(EmptyResultDataAccessException.class)
    .skipLimit(20)
    .build();
~~~

This example is only appropriate if a zero-row update count is considered a skippable record. If a missing customer is a critical error, do not skip that exception.

Do not configure skip for broad `DataAccessException`. That can swallow connection errors, broken SQL, or schema mismatches, causing data not to be written.

## 19. Idempotency and Restart

Spring Batch can re-read items from an uncommitted chunk on retry or restart. With a database writer, a chunk transaction sharing the datasource rolls back uncommitted batch updates. However, if the writer targets a different datasource, calls a remote service, or has side effects outside the transaction, the same items may be reprocessed.

To make updates safe on re-execution:

- Use stable business keys.
- Design `UPDATE`s to set final target values rather than unintentionally accumulating deltas.
- Use a version column when concurrent modifications must be detected.
- Use unique constraints or idempotency keys for inserts/upserts.
- Record a batch ID/source ID to distinguish one import run from another.

For instance, an `UPDATE` setting `status` to `COMPLETED` is usually idempotent if repeating it produces no extra side effects. By contrast, `set balance = balance + :amount` is not idempotent; re-running adds the amount twice. For cumulative operations, an operation ID and durable deduplication mechanism are required.

## 20. Generated Keys Are Not Automatically Populated Back into Items

`JdbcBatchItemWriter` is designed to execute batch statements, not as a general mechanism for retrieving database-generated keys per item and writing them back into input objects.

If database-generated IDs are needed:

- Let the database generate IDs and query them back using a business key.
- Use a sequence/service to allocate IDs before the writer runs.
- Use a custom writer with JDBC APIs supporting generated keys and verify key-to-item mapping.
- Separate the insert and re-read/lookup into appropriate steps.

Do not assume `JdbcBatchItemWriter` populates generated IDs back onto items after `INSERT`. If later steps need IDs, design how IDs are retrieved explicitly and test with the real database/driver.

## 21. Upserts and Database-Specific SQL

A SQL batch writer uses a fixed statement for every item. If syntax depends on the database, configure the writer by profile/dialect or via an appropriate repository.

Do not interpolate table/column names directly from item data into SQL. Named parameters only bind values, not SQL identifiers. If you must select a table by tenant or route, use a configuration-backed whitelist mapping and pick from predefined writers/queries.

Do not concatenate input strings directly into SQL statements. Use named parameters or `PreparedStatement` to bind values, preventing SQL injection and quoting bugs.

## 22. Using JdbcBatchItemWriter in a Step with a Processor

The processor typically transforms input into a command/update model:

~~~java
public class CustomerUpdateProcessor
        implements ItemProcessor<CustomerInput, CustomerUpdate> {

    @Override
    public CustomerUpdate process(CustomerInput input) {
        if (input.customerId() == null) {
            throw new InvalidCustomerException("customerId is required");
        }

        return new CustomerUpdate(
            input.customerId(),
            normalizeStatus(input.status()),
            LocalDateTime.now()
        );
    }
}
~~~

Step:

~~~java
return new StepBuilder("updateCustomersStep", jobRepository)
    .<CustomerInput, CustomerUpdate>chunk(200, transactionManager)
    .reader(customerReader)
    .processor(customerUpdateProcessor)
    .writer(customerUpdateWriter)
    .build();
~~~

The writer only needs to know about `CustomerUpdate` and the SQL. It does not need to know whether inputs came from JSON, CSV, JDBC, or a message source. Separating a command/update model establishes clean boundaries between SQL binding and business validation.

If the processor returns null, the item is filtered out and not sent to the writer. Track filtered counts separately if reconciliation between rows read and rows updated is required.

## 23. Writer Thread Safety and Lifecycle

`JdbcBatchItemWriter` is designed to be thread-safe once its properties are configured. Therefore, it can normally be declared as a singleton bean used in a step.

However, application-supplied components must also be concurrency-safe:

- `ItemSqlParameterSourceProvider` must not hold mutable per-item state.
- `ItemPreparedStatementSetter` must only write to the passed-in `PreparedStatement`.
- Do not store the current item or parameter source in shared fields.
- Do not share mutable DTO instances across workers if they can be modified.

The writer does not open and hold a long-lived connection itself. It uses the template/data source to execute batches; the transaction manager manages connections per transaction. Never manually close connections inside a provider or setter.

## 24. Testing JdbcBatchItemWriter

Unit testing providers/setters can verify how items map to parameters. However, to verify SQL, batch execution, update counts, null binding, and transactions, use integration tests against a database.

Scenarios to cover:

- Writing multiple items in one chunk and verifying all rows are updated.
- `UPDATE` by a nonexistent business key.
- `INSERT` violating a unique constraint.
- `DELETE` when the record no longer exists.
- Null parameters and temporal/numeric types.
- SQL with version conditions to detect optimistic locking conflicts.
- One failing item in a batch and transaction rollback.
- Restart/retry not creating duplicates or applying side effects twice.

H2 can be useful for basic SQL tests, but upsert syntax, update counts, type conversions, and batch error behavior can differ from production databases. Use Testcontainers or an integration environment with the exact database/driver for vendor-dependent behaviors.

## 25. Integration Test Example for Batch Updates

Suppose the `customer` table has two rows:

~~~sql
insert into customer(customer_id, status)
values ('C-1', 'NEW'), ('C-2', 'NEW');
~~~

Run the writer with two updates:

~~~java
Chunk<CustomerStatusChange> chunk = new Chunk<>(List.of(
    new CustomerStatusChange("C-1", "ACTIVE", now),
    new CustomerStatusChange("C-2", "SUSPENDED", now)
));

writer.write(chunk);
~~~

After the transaction commits, verify:

~~~sql
select customer_id, status
from customer
where customer_id in ('C-1', 'C-2')
order by customer_id;
~~~

The expected result is `C-1` with `ACTIVE` and `C-2` with `SUSPENDED`. Tests should also verify update counts or error behavior when adding an item with a nonexistent `customerId`.

In a full Spring Batch test, launch the step/job via `JobLauncherTestUtils` to verify the writer runs inside the chunk transaction and `StepExecution` reports the expected status, `writeCount`, and rollback/skip counts.

## 26. Testing Rollback When an Update Fails

To prove batch updates participate in the chunk transaction:

1. Prepare several customers and their initial states.
2. Let `JdbcBatchItemWriter` execute updates inside the chunk.
3. Intentionally throw an exception before the chunk commits, for instance via a subsequent writer in a composite or a test component designed to fail.
4. Verify the step rolls back.
5. Re-read the database and confirm updates from the uncommitted chunk did not take effect.

Tests must use the same datasource and transaction manager setup as production. If a writer opens a separate connection with autocommit enabled, behavior may differ and chunk rollback will not undo that update.

## 27. Common Pitfalls When Using Batch Update Writers

**Calling update item-by-item in a loop:** loses batching benefits. Use `JdbcBatchItemWriter` when multiple items execute the same SQL template.

**Named parameter names not matching properties:** the parameter source cannot find values. Check SQL, getters, and custom providers.

**Wrong question mark order:** `PreparedStatementSetter` binds to the wrong columns. Cross-check placeholder order against setter calls.

**Arbitrarily disabling assertUpdates:** updates matching no rows may be silently ignored. Disable it only when zero-row updates are valid outcomes.

**Assuming assertUpdates verifies exactly one row:** it checks that at least one row was affected, not exactly one row. Use unique constraints or explicit checks.

**Treating null as database default:** null parameters normally send SQL `NULL`. To use `DEFAULT`, adjust the SQL statement.

**Retrying permanent data errors:** duplicate keys, version conflicts, or invalid business keys will not heal on retry. Classify errors before retrying.

**Assuming JDBC batches are always atomic:** atomicity depends on transactions, database, and driver. Use chunk transactions and test on the real engine.

**Using overly large chunks:** long transactions, long locks, and expensive rollbacks. Measure and tune to the workload.

**Taking SQL identifiers from input:** named parameters only bind values; they do not protect identifiers concatenated into SQL. Use a configured whitelist.

**Expecting the writer to populate generated keys:** `JdbcBatchItemWriter` does not write generated keys back onto items. Design a lookup or custom writer.

**Using the writer for a single bulk UPDATE:** when only one set-based SQL statement is needed, a tasklet/`JdbcTemplate` is usually a better fit.

## 28. Production Deployment Workflow for Batch Update Writers

First, determine whether each item maps to an `INSERT`, `UPDATE`, or `DELETE`, and choose the appropriate business key/`WHERE` condition. Use fixed SQL, binding values via a named parameter provider or `PreparedStatementSetter`. If items need custom binding, build a stateless provider/adapter with explicit null and SQL type handling.

Next, configure `JdbcBatchItemWriter` with the datasource and SQL. Enable `assertUpdates` when each item must affect at least one row; disable it only when zero-row updates are business-acceptable. Register the writer in a chunk step using the transaction manager bound to that datasource. Pick chunk size based on performance, locking, and rollback scope.

Finally, test against a production-compatible database: multiple items in a batch, zero-row updates, constraint violations, null binding, optimistic locking, rollback, retry, and restart. Use idempotency keys or safe update semantics whenever items can be reprocessed. Monitor write duration, batch size, update failures, deadlocks, and connection pool metrics to tune operations.

`JdbcBatchItemWriter` enables Spring Batch to write multiple items using a single SQL template and multiple parameter sets per chunk. It supports inserts, updates, and deletes; named parameters or prepared statement setters govern how data is bound, while the step's transaction manager governs commit/rollback. By properly understanding update counts, null binding, optimistic locking, retry, and batch sizing, a batch update writer can write data efficiently while preserving job consistency and recoverability.
