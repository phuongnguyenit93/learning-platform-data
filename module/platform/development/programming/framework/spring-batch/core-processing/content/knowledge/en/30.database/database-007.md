# JdbcBatchItemWriter

JdbcBatchItemWriter is a built-in Spring Batch ItemWriter used to write a group of items to a database using JDBC batch updates. Instead of manually executing a separate write statement for each item, the writer receives the entire Chunk and sends the corresponding parameters as a batch via NamedParameterJdbcTemplate.

This component is suitable for import, synchronization, or data transformation Jobs where each item must be inserted into or updated in a relational database. It supports named parameters, parameter mapping from JavaBeans or Maps, and allows supplying a custom SqlParameterSource creation mechanism.

JdbcBatchItemWriter only handles the write operation. Spring Batch manages chunks, transactions, retries, skips, and checkpoints around the writer. Therefore, you must understand how the writer interacts with the transaction manager, the update counts reported by the database, and behavior when an item in the batch causes an error.

## 1. JdbcBatchItemWriter in chunk-oriented processing

A chunk-oriented Step reads and processes a group of items, then passes the resulting group to the writer. JdbcBatchItemWriter receives that chunk and executes the SQL statement for each item using a JDBC batch update.

~~~text
ItemReader
    |
    v
ItemProcessor
    |
    v
Chunk<T>
    |
    v
JdbcBatchItemWriter
    |
    v
NamedParameterJdbcTemplate
    |
    v
JDBC batchUpdate
    |
    v
Relational database
~~~

For example, with a chunk size of 100:

1. The reader reads up to 100 records.
2. The processor transforms or validates the records.
3. Spring Batch collects valid outputs into a chunk.
4. The writer creates an SqlParameterSource for each item.
5. NamedParameterJdbcTemplate executes the batch SQL.
6. If the chunk succeeds, the transaction is committed according to Step configuration.

If the processor returns null for an item, that item is filtered out and never reaches the writer. If the writer throws an exception, the chunk's transaction is handled according to configured rollback, retry, or skip policies.

## 2. Why use JdbcBatchItemWriter?

An application could write a custom ItemWriter and call JdbcTemplate.update() in a loop. However, JdbcBatchItemWriter provides a built-in way to turn a chunk into a batch update and integrates with the Step lifecycle.

Key benefits:

- Writes multiple items in a single writer invocation.
- Uses named parameters to keep SQL readable.
- Maps parameters from JavaBeans, Maps, or a custom provider.
- Participates in the chunk transaction when used with the right transaction manager.
- Offers an option to assert that each statement affected at least one row.
- Reduces boilerplate JDBC code in custom writers.

This writer fits when the operation can be expressed as a single SQL statement applied to each item, such as inserting a row or updating a record by key. If each item requires multiple complex statements, calls to multiple systems, or per-item generated key handling, a custom writer may be needed.

## 3. Basic configuration with JdbcBatchItemWriterBuilder

Spring Batch provides JdbcBatchItemWriterBuilder<T> to construct the writer. For a JavaBean model, you can use beanMapped():

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO customer
                        (customer_id, full_name, email)
                    VALUES
                        (:customerId, :fullName, :email)
                    """)
            .beanMapped()
            .build();
}
~~~

Configuration parts:

- dataSource(dataSource): provides the DataSource to create a NamedParameterJdbcTemplate.
- sql(...): the SQL statement used for each item in the chunk.
- beanMapped(): retrieves named parameter values from JavaBean properties.
- build(): creates the configured writer.

You can pass an existing NamedParameterJdbcTemplate instead of a DataSource using jdbcTemplate(...). Choose one way to supply the JDBC template matching application configuration and avoid creating unnecessary templates.

## 4. JavaBean model and beanMapped()

beanMapped() uses BeanPropertyItemSqlParameterSourceProvider to map item properties to named parameters. Placeholder names in SQL must match JavaBean property names.

Example model:

~~~java
public class Customer {

    private String customerId;
    private String fullName;
    private String email;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

With this model, the SQL can use:

~~~sql
INSERT INTO customer(customer_id, full_name, email)
VALUES (:customerId, :fullName, :email)
~~~

Spring reads the customerId, fullName, and email properties from each item. If the SQL uses :customer_id while the bean only has property customerId, the provider does not automatically infer snake_case-to-camelCase conversion. Placeholders and properties must be named consistently.

beanMapped() is convenient when items are DTOs or JavaBeans with matching getters. For models with nested structures, differing property names, or complex conversion rules, consider a custom provider to avoid relying on default introspection.

## 5. Mapping from a Map using columnMapped()

If the reader or processor produces items as Map<String, Object>, you can use columnMapped():

~~~java
@Bean
JdbcBatchItemWriter<Map<String, Object>> mapWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Map<String, Object>>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO imported_record
                        (record_id, record_name, record_status)
                    VALUES
                        (:record_id, :record_name, :record_status)
                    """)
            .columnMapped()
            .build();
}
~~~

The item must contain the corresponding keys:

~~~java
Map<String, Object> row = new HashMap<>();
row.put("record_id", "R-100");
row.put("record_name", "Sample");
row.put("record_status", "READY");
~~~

columnMapped() uses ColumnMapItemSqlParameterSourceProvider to look up values by key name. Map keys must match SQL placeholders. Use a consistent casing convention because map key behavior can depend on the Map type and how it was constructed.

Maps are useful when data structures vary or are produced from dynamic query results. However, JavaBeans or DTOs usually offer stronger type checking and reduce key typo errors.

## 6. Using a custom ItemSqlParameterSourceProvider

When an item is not a plain JavaBean or needs renaming/transforming values before binding, you can supply an ItemSqlParameterSourceProvider<T>:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO order_import
                        (order_id, customer_id, total_amount, imported_at)
                    VALUES
                        (:orderId, :customerId, :totalAmount, :importedAt)
                    """)
            .itemSqlParameterSourceProvider(order ->
                    new MapSqlParameterSource()
                            .addValue("orderId", order.getId())
                            .addValue("customerId", order.getCustomer().getId())
                            .addValue("totalAmount", order.getAmount())
                            .addValue("importedAt", Timestamp.from(order.getImportedAt())))
            .build();
}
~~~

The provider returns an SqlParameterSource for each item. You can use MapSqlParameterSource, BeanPropertySqlParameterSource, or a custom implementation.

This approach fits when:

- Java property names differ from SQL placeholder names.
- The item has nested structures.
- Values need normalization or conversion before writing.
- A value computed from the item needs to be added.
- SQL types or null values need to be bound explicitly.

The provider should be deterministic and side-effect-free. It may be invoked again if the writer is re-executed due to retries or fault-isolation scans.

## 7. Named parameters in SQL

JdbcBatchItemWriter uses NamedParameterJdbcTemplate, so the SQL uses named placeholders prefixed with a colon:

~~~sql
INSERT INTO customer(customer_id, full_name)
VALUES (:customerId, :fullName)
~~~

Placeholder names do not have to match column names. They are parameter names mapped to values in the item.

Update example:

~~~sql
UPDATE customer
SET full_name = :fullName,
    email = :email
WHERE customer_id = :customerId
~~~

Delete example:

~~~sql
DELETE FROM customer_staging
WHERE batch_id = :batchId
  AND customer_id = :customerId
~~~

Named parameters make SQL easier to read than positional `?` markers in PreparedStatement. Values are bound via JDBC rather than concatenated directly into the SQL string.

Do not put quotes around placeholders:

~~~sql
-- Correct
WHERE customer_id = :customerId

-- Wrong: turns placeholder into a literal string
WHERE customer_id = ':customerId'
~~~

Bind parameters cannot replace table names, column names, or SQL keywords. If SQL structure must vary based on parameters, select from a predefined allowlist and build the SQL from validated identifiers. Never concatenate user-supplied identifiers directly into SQL.

## 8. Writing data with INSERT

A common scenario is importing new items into a target table:

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerInsertWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO customer
                        (customer_id, full_name, email)
                    VALUES
                        (:customerId, :fullName, :email)
                    """)
            .beanMapped()
            .build();
}
~~~

For each item in the chunk, the writer builds a parameter source and batches the SQL insert. If a customer_id violates a unique constraint, the database may throw a duplicate key or data integrity exception.

If business rules treat duplicates as errors, let the exception fail the Step or configure specific skip/retry policies per requirements. If duplicates represent already-existing valid records, consider an upsert or idempotency check before writing. Do not skip every DataIntegrityViolationException because it can also indicate constraint failures other than duplicate keys.

## 9. Writing data with UPDATE

The writer can also perform updates by key:

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerUpdateWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    UPDATE customer
                    SET full_name = :fullName,
                        email = :email
                    WHERE customer_id = :customerId
                    """)
            .beanMapped()
            .build();
}
~~~

With updates, decide what happens when no rows match customerId. By default, assertUpdates is enabled. When JDBC reports an update count of 0 for an item, the writer raises an error instead of silently accepting that no record was modified.

This is useful behavior when every item must update exactly one record. If zero-row updates are valid under business rules, you can disable the assertion after deciding how to track such cases.

## 10. assertUpdates and affected row counts

JdbcBatchItemWriterBuilder provides the assertUpdates(boolean) option. The default is true.

~~~java
return new JdbcBatchItemWriterBuilder<Customer>()
        .dataSource(dataSource)
        .sql("""
                UPDATE customer
                SET email = :email
                WHERE customer_id = :customerId
                """)
        .beanMapped()
        .assertUpdates(true)
        .build();
~~~

When the assertion is enabled, the writer checks the update counts returned by the JDBC driver. If an item changes zero rows (update count of 0), the writer throws an exception indicating the statement did not update a record as expected.

You can disable the assertion:

~~~java
.assertUpdates(false)
~~~

This is appropriate when a statement can legitimately yield an update count of 0, such as:

- An update that only modifies data when the new value differs from the current one.
- A record that may have already been deleted by another process.
- Conditional SQL causing some items to require no update.
- Stored procedures or drivers with special update-count conventions.

Disable the assertion only if zero updates is an acceptable business outcome. If the record is required to exist, disabling the assertion can hide foreign key bugs, wrong IDs, or mismatched source data.

Some JDBC drivers may return SUCCESS_NO_INFO instead of exact row counts for a batch element. Therefore, do not assume every database/driver always reports identical update counts. Test with the driver used in production.

## 11. Configuring a Step with JdbcBatchItemWriter

Complete Step example in Spring Batch 5:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        JdbcBatchItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
~~~

chunk(500, transactionManager) sets the chunk size to 500 items and supplies the transaction manager to the Step. The writer is invoked with the output chunk after the reader and processor finish their respective work.

Chunk size affects the number of items in one batch update, memory, transaction duration, and the amount of work redone on rollback. Larger chunks can reduce commit count, but increase lock hold times and retry volume. Smaller chunks reduce transaction scope, but increase commit and round-trip overhead.

Chunk size does not guarantee the database driver executes all commands in a single network packet. JDBC drivers and databases may split or handle batches in their own ways. Measure performance with your actual driver, schema, and workload.

## 12. Transactions and rollbacks

JdbcBatchItemWriter does not open or commit an independent transaction per item. It executes batch updates within the Step-managed transaction if the writer's DataSource participates in the same transaction manager.

When the writer throws an exception and the chunk transaction rolls back:

- Uncommitted database changes in that transaction are undone.
- Previously committed chunks remain intact.
- Spring Batch can retry or skip according to the configured fault tolerance policy.
- Checkpoints and metadata are updated according to transaction/repository configuration.

Transaction configuration example:

~~~java
@Bean
Step writeCustomersStep(
        JobRepository jobRepository,
        @Qualifier("batchTransactionManager")
        PlatformTransactionManager transactionManager,
        JdbcBatchItemWriter<Customer> writer,
        ItemReader<Customer> reader) {

    return new StepBuilder("writeCustomersStep", jobRepository)
            .<Customer, Customer>chunk(200, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

The transaction manager must manage the exact DataSource used by the writer. If the writer writes to a different database/resource than the Step's transaction manager, you cannot assume those operations roll back together. With multiple resources, design appropriate transaction coordination or compensation mechanisms.

Never call commit() or rollback() manually inside a writer. Doing so can break the transaction boundaries managed by Spring Batch.

## 13. Skip and retry when batch writes fail

The writer can encounter errors such as:

- Duplicate keys.
- Foreign key or check constraint violations.
- Deadlocks or lock timeouts.
- Database connection failures.
- SQL syntax or mapping errors.

Not every error fits the same policy. Transient deadlocks can be retried; a record violating business rules can be skipped if business rules allow; SQL errors from misconfiguration typically must fail the Step.

Retry and skip configuration example:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .skip(DuplicateKeyException.class)
        .skipLimit(20)
        .listener(orderSkipListener)
        .build();
~~~

The example above is appropriate only if duplicate keys are genuinely skippable items. If duplicates indicate data corruption needing investigation, do not skip them. Also check driver exception translation to confirm the actual exception type thrown.

When fault tolerance must identify the failing item inside a batch writer, Spring Batch may re-invoke the writer with smaller item groups or single items to isolate the fault. Therefore, the writer must be safe when called multiple times during error handling. Database operations should remain transactional, and non-database side effects must be idempotent.

## 14. Idempotency and duplicate writes

Restarts or retries can send the same item to the writer more than once. If the SQL always inserts, a rerun can violate unique constraints or create duplicate data if the table lacks an appropriate unique key.

Ways to mitigate risk:

- Use a stable business key and unique constraints in the database.
- Use database-specific upsert syntax if business rules permit.
- Record a batch ID/source version to distinguish import runs.
- Use a staging table and merge data using deterministic rules.
- Reconcile results before replaying a failed chunk.

Upsert syntax is database-specific. With PostgreSQL:

~~~sql
INSERT INTO customer(customer_id, full_name, email)
VALUES (:customerId, :fullName, :email)
ON CONFLICT (customer_id)
DO UPDATE SET
    full_name = EXCLUDED.full_name,
    email = EXCLUDED.email
~~~

With other databases, syntax may be MERGE or another upsert form. Do not put database-specific upsert SQL into an application requiring portability without appropriate abstraction or testing.

Idempotency does not mean you must always update. It means repeating the same business operation does not produce incorrect results or duplicate side effects. Whether insert-only, update-only, or upsert applies depends on business requirements.

## 15. Writing to multiple tables or multiple statements

JdbcBatchItemWriter executes a single SQL template per item in the batch. If an item needs to write to multiple tables, you can:

- Use a custom writer calling multiple batch writers within the same transaction.
- Use a composite writer if writers can be composed and lifecycles are managed properly.
- Split data into separate Step flows if operations have different lifecycles or transactions.
- Use a stored procedure if multi-statement logic is managed in the database.

Example writer coordinating two writers:

~~~java
public class CustomerAndAuditWriter implements ItemWriter<Customer> {

    private final JdbcBatchItemWriter<Customer> customerWriter;
    private final JdbcBatchItemWriter<CustomerAudit> auditWriter;

    public CustomerAndAuditWriter(
            JdbcBatchItemWriter<Customer> customerWriter,
            JdbcBatchItemWriter<CustomerAudit> auditWriter) {
        this.customerWriter = customerWriter;
        this.auditWriter = auditWriter;
    }

    @Override
    public void write(Chunk<? extends Customer> chunk) throws Exception {
        customerWriter.write(chunk);

        Chunk<CustomerAudit> auditChunk = new Chunk<>();
        for (Customer customer : chunk) {
            auditChunk.add(CustomerAudit.from(customer));
        }
        auditWriter.write(auditChunk);
    }
}
~~~

This is an illustrative concept; Chunk types and conversion methods must match your Spring Batch version's API. Both writers must share the same transaction manager/DataSource if both operations must commit or roll back together. If the second writer fails after the first writer has run, the chunk transaction must roll back database changes from both.

If the two writers target two different databases, a standard local transaction does not guarantee atomicity across both resources. In that case, a distributed transaction or an outbox/saga/compensation design is required.

## 16. Generated keys and return values

JdbcBatchItemWriter focuses on batch updates and does not automatically map generated keys from each insert back onto the input objects. JDBC batch updates typically return an array of update counts; that is not a list of per-item generated keys.

If a subsequent step needs the newly generated database ID, you can:

- Use a stable business key already present from the source.
- Use sequences/IDs allocated prior to writing.
- Re-query by business key and batch ID.
- Write a custom ItemWriter using JDBC APIs that support generated keys as needed by the driver.
- Design a subsequent Step to read the written results from the database.

Do not assume JdbcBatchItemWriter will populate an ID field on your DTO after insert. If generated keys are central to the requirement, choose an appropriate write API and test against the real database/driver.

## 17. Nulls, SQL types, and date/time data

Named parameter providers extract values from objects, yet the database still needs matching SQL types. For null values, data types may need to be specified explicitly, especially when the driver cannot infer the type from null.

MapSqlParameterSource allows adding values with an SQL type:

~~~java
new MapSqlParameterSource()
        .addValue("customerId", customer.getCustomerId())
        .addValue("birthDate", customer.getBirthDate(), Types.DATE)
        .addValue("middleName", customer.getMiddleName(), Types.VARCHAR);
~~~

For LocalDate, LocalDateTime, BigDecimal, or enums, verify conversion and database column type compatibility. Use BigDecimal for money rather than float/double to avoid binary rounding errors.

If values need timezone normalization, agree on UTC or a business timezone convention before writing. Do not rely on the default timezone of the machine running the Job.

## 18. Performance and choosing chunk size

JdbcBatchItemWriter reduces overhead compared to individual update calls, yet overall performance still depends on:

- Chunk size.
- Number of columns and payload size per item.
- Table indexes, constraints, triggers, and foreign keys.
- Connection pool and transaction isolation.
- Whether the JDBC driver supports batching efficiently.
- Lock contention when multiple Jobs write to the same table concurrently.
- Batch sizes that the database can process efficiently.

Large chunks:

- Reduce commit frequency.
- Can increase throughput when the database handles batches well.
- Hold transactions and locks longer.
- Consume more memory.
- Enlarge rollback/retry scope.

Small chunks:

- Commit more frequently.
- Reduce the number of items redone after rollback.
- Can increase transaction and round-trip overhead.

Benchmark with representative data. Start with a moderate chunk size and monitor throughput, transaction duration, lock waits, and memory. Do not raise chunk size based solely on average item counts without observing the database.

## 19. Thread safety and multiple workers

JdbcBatchItemWriter is designed for Spring Batch environments and can be shared once configuration is complete. Do not mutate SQL, DataSource, or parameter providers while the Step is running.

When multiple threads or partitions use the writer:

- Items must be bound independently, without a shared mutable parameter map being overwritten.
- The DataSource/connection pool must support the concurrency level.
- Data ranges should avoid write conflicts where possible.
- Unique constraints and locking must protect consistency in the database.
- Custom providers must not hold per-item state in shared fields.

NamedParameterJdbcTemplate is safe to share after configuration. However, any service or collaborator invoked by a provider still needs to be evaluated for thread safety.

If multiple partitions insert/update the same key concurrently, the database may hit deadlocks or lock contention. Partition data sensibly, enforce consistent write ordering, or lower concurrency if needed.

## 20. Testing JdbcBatchItemWriter

Test the writer against a test database compatible with your actual SQL. H2 suits many basic tests, but if the application relies on PostgreSQL/MySQL/Oracle/SQL Server upsert syntax, data types, or locking, use Testcontainers or a matching integration environment.

Scenarios to test:

1. Writing a single item succeeds.
2. Writing multiple items in one chunk.
3. Bean properties or map keys bind properly.
4. Custom providers transform values accurately.
5. Null values and SQL types are handled properly.
6. Update finding no matching record when assertUpdates(true).
7. Zero updates accepted when assertion is disabled and business rules permit.
8. Constraint violation rolls back the transaction properly.
9. Retrying after deadlock or transient failure creates no duplicate records.
10. Restarting does not duplicate already-committed chunks.
11. Multiple partitions writing concurrently do not corrupt data.

Simple integration test example:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchWriterTestConfiguration.class)
class JdbcBatchItemWriterTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void writesAllItemsInTheChunk() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRun", "writer-basic-01", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM customer",
                Integer.class);
        assertEquals(3, count);
    }
}
~~~

This example assumes the test configuration supplies three input items, the schema is initialized, and the customer table is cleaned before the test. When running multiple tests, isolate databases or clean data by test ID so results do not depend on execution order.

## 21. Common mistakes

**Placeholder does not match property or map key:** :customerId requires a customerId property or matching key in the parameter source. Check spelling and naming conventions.

**Using the wrong provider:** beanMapped() fits JavaBeans; columnMapped() fits Maps; items with custom structures should use a custom provider.

**Forgetting DataSource or SQL:** the builder needs a JDBC template/DataSource and valid SQL before building.

**Disabling assertUpdates too early:** zero-row updates can mask nonexistent IDs or bad data. Disable only when zero updates is valid.

**Concatenating values into SQL:** introduces SQL injection risks and escaping errors. Use named parameters for data values.

**Assuming the writer commits by itself:** transactions belong to the Step/transaction manager. Never commit manually inside a writer.

**DataSource not participating in the Step transaction:** failures may not roll back alongside metadata or other operations. Configure the transaction manager and resources properly.

**Skipping every DataIntegrityViolationException:** this exception can represent multiple kinds of constraint violations. Skip only specific failures permitted by business rules.

**Writer with non-idempotent side effects:** retries/restarts can send notifications or call APIs multiple times. Use outbox or idempotency keys.

**Assuming generated keys appear on items:** JdbcBatchItemWriter does not automatically populate generated keys per item. Choose another writer/API if needed.

**Chunk too large:** transactions drag out, lock contention rises, and rollback costs grow. Benchmark and tune to the workload.

## Conclusion

JdbcBatchItemWriter writes a chunk of items to a database using JDBC batch updates and named parameters. Use beanMapped() for JavaBeans, columnMapped() for Maps, or itemSqlParameterSourceProvider() when custom mapping is needed. Configure SQL with placeholders matching item data, set assertUpdates based on expected affected row counts, and use a transaction manager managing the writer's DataSource. In operation, classify duplicate, constraint, deadlock, and infrastructure errors clearly; design idempotency for retries/restarts, benchmark chunk sizes, and test against a real database/driver. The writer handles writing chunk data, while transactions, skips, retries, and restarts remain governed by Step configuration and Spring Batch.
