# Database output and unique constraints in Spring Batch

A batch job often reads data from files, APIs, or databases and writes results into a target table. If the same input is processed twice, the job may create duplicate records, overwrite data unintentionally, or corrupt business figures. This situation can occur when the source file contains duplicates, when an operator restarts a job, when a scheduler triggers a re-run, or when multiple partitions process the same business key simultaneously.

A unique constraint is the final line of defense in the database ensuring that one or more columns do not hold duplicate values under the declared rules. In Spring Batch, this constraint works together with writers, transactions, retries, skips, and restarts to protect output consistency. However, merely adding a constraint does not solve every duplicate scenario on its own. The job must still define which records count as the same business entity, handle duplicates according to the contract, and design writers safely for repeated calls.

## 1. Why does database output need unique constraints?

Suppose a job imports orders from a file. Each order has a source order ID and a customer ID. If the same order appears twice, a plain INSERT statement can create two identical rows:

~~~text
Input file
  |
  +--> Order O-100
  +--> Order O-101
  +--> Order O-100   (duplicate)
  |
  v
JdbcBatchItemWriter
  |
  v
imported_order
  |
  +--> O-100
  +--> O-101
  +--> O-100   (unwanted)
~~~

One Java-side check is keeping a Set of seen IDs, yet that only controls the scope observed by a single instance. It cannot protect against:

- Another run processing the same file.
- A job restart after a side effect already committed.
- Two partitions processing the same key.
- Two application instances running the same batch.
- Another request writing to the same table outside the batch job.

A database unique constraint is enforced where data is stored, so it protects data across competing concurrent writers. It is an essential safeguard for business keys and idempotency keys.

## 2. What is a unique constraint?

A unique constraint requires that the value of a column or combination of columns not repeat across rows according to database rules.

For example, a table allowing only one order with the same source order ID:

~~~sql
create table imported_order (
    id bigint generated always as identity primary key,
    source_order_id varchar(80) not null,
    customer_id varchar(80) not null,
    total_amount decimal(18, 2) not null,
    imported_at timestamp not null,
    constraint uk_imported_order_source
        unique (source_order_id)
);
~~~

If an INSERT tries to create a second row with the same source_order_id, the database rejects the operation with a unique violation error. An explicit constraint name makes logs and error messages easier to interpret.

Unique constraints are usually enforced by the database via a unique index or equivalent index structure. They are database-guaranteed rules, not optional checks in Java.

## 3. How do a primary key and a unique constraint differ?

A primary key identifies the main identity of a row. A unique constraint ensures uniqueness for a business key or another combination of attributes.

| Aspect | Primary key | Unique constraint |
| --- | --- | --- |
| Purpose | Identify the row | Prevent duplicates of a value or combination of values |
| Count per table | One primary key | Multiple unique constraints allowed |
| NULLs | Does not allow NULL | NULL handling depends on the database |
| Foreign references | Commonly referenced by foreign keys | Can be referenced if database rules are met |
| Example | id | source_system + source_record_id |

A table can use a surrogate primary key such as id while also having a unique constraint on source_system and source_record_id to prevent the same source record from being imported twice.

Do not rely solely on a generated primary key to prevent business duplicates. If every import generates a new ID, two copies of the same source record can still become two valid rows under the primary key.

## 4. Multi-column unique constraints

Often a single column is not enough to identify a record uniquely. For example, a customer code may repeat across tenants, or an external reference may only be unique within one source system.

~~~sql
create table customer_import (
    id bigint generated always as identity primary key,
    tenant_id varchar(40) not null,
    source_system varchar(40) not null,
    source_customer_id varchar(80) not null,
    customer_name varchar(200) not null,
    constraint uk_customer_import_source
        unique (tenant_id, source_system, source_customer_id)
);
~~~

In this example, the same source_customer_id can appear in a different tenant or a different source system, but cannot repeat within the same three-column combination.

Column order in a unique constraint does not change the logical uniqueness rule of the combination, though it can affect how the backing index supports queries. Design indexes for both the constraint and actual lookup queries.

## 5. Choosing the right business key

A unique constraint helps only when its column or columns reflect the true business identity. Some examples:

| Data kind | Candidate business key |
| --- | --- |
| Records imported from a file | source_file_id + source_record_number |
| Events from a message broker | source_system + event_id |
| Customers across multiple systems | tenant_id + source_system + external_customer_id |
| Payment transactions | payment_provider + provider_transaction_id |
| Invoice lines | invoice_id + line_number |

Before adding a constraint, answer:

- Do two records with the same key definitely represent the same business entity?
- Can the key change over time?
- Is the key unique only within a tenant, source system, or business date?
- Do multiple versions of the same record need to be retained?
- If a producer resends an old record with different content, is that a duplicate or an update?

Do not pick a seemingly convenient column like customer name or email as a unique key if business rules allow multiple customers to share a value or allow that value to change.

## 6. Idempotency key vs. business key

A business key identifies a business entity, whereas an idempotency key identifies an operation or event that should be applied at most once logically.

For example, the same customer can have multiple address updates. Customer ID is the customer's business key, yet it cannot be used to discard every event after the first one. Each update requires its own event ID:

~~~text
Customer C-100
  |
  +--> Event E-001: address change 1
  +--> Event E-002: address change 2
  +--> Event E-003: address change 3
~~~

You can create an inbox or processed_event table:

~~~sql
create table processed_event (
    source_system varchar(40) not null,
    event_id varchar(100) not null,
    processed_at timestamp not null,
    constraint uk_processed_event
        unique (source_system, event_id)
);
~~~

When an event is reprocessed due to retry/restart, the unique key on the event detects that the operation was already applied. The business table still keeps its own key to protect the uniqueness of the customer/order.

Never use a business key as an idempotency key if the same business entity is allowed to receive multiple valid events.

## 7. Declaring unique constraints in JPA entities

With JPA, unique constraints can be described using @Table:

~~~java
@Entity
@Table(
    name = "customer_import",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_customer_import_source",
            columnNames = {
                "tenant_id",
                "source_system",
                "source_customer_id"
            }
        )
    }
)
public class CustomerImport {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "source_system", nullable = false)
    private String sourceSystem;

    @Column(name = "source_customer_id", nullable = false)
    private String sourceCustomerId;
}
~~~

@UniqueConstraint describes the schema for the JPA provider when generating DDL. In production, do not rely on Hibernate auto-updating the schema to ensure the constraint exists. Use a migration tool such as Flyway or Liquibase to deploy constraints in a controlled manner.

Annotations do not replace verifying the actual database. Confirm that the unique constraint was created in the exact target schema and environment.

## 8. @Column(unique = true) and @Table(uniqueConstraints)

@Column(unique = true) suits single-column unique constraints:

~~~java
@Column(name = "external_id", nullable = false, unique = true)
private String externalId;
~~~

For multi-column unique constraints, use @Table(uniqueConstraints = ...):

~~~java
@Table(
    uniqueConstraints = @UniqueConstraint(
        name = "uk_tenant_external_id",
        columnNames = {"tenant_id", "external_id"}
    )
)
~~~

These annotations are mapping metadata. Whether the database actually has the constraint depends on how the schema is created/updated. If production uses migrations, the migrations must contain the corresponding DDL.

Do not declare unique constraints in Java and assume every environment already has the same structure. Check migrations, schema versions, and database catalogs.

## 9. Creating unique constraints via migration

A SQL migration can add a constraint:

~~~sql
alter table imported_order
add constraint uk_imported_order_source
unique (source_system, source_order_id);
~~~

Before running a migration on a table with existing data, find and resolve existing duplicates:

~~~sql
select source_system, source_order_id, count(*) as duplicate_count
from imported_order
group by source_system, source_order_id
having count(*) > 1;
~~~

If the query returns rows, the migration adding the constraint can fail. Determine which record is canonical and which records must be merged, archived, or deleted according to business rules.

Do not delete duplicates automatically based purely on newest/oldest creation timestamp without knowing which record is valid. Differences may exist in status, payments, or foreign key relationships.

## 10. Unique constraints and NULL

Do not assume every database handles NULL inside unique constraints identically. Some databases allow multiple rows with NULL in a unique column because NULL is treated as unknown; other engines or index types follow different rules. With multi-column unique constraints, behavior also depends on the column combination and vendor.

If a business key must always have a value, declare component columns as NOT NULL:

~~~sql
source_system varchar(40) not null,
source_record_id varchar(100) not null,
constraint uk_source_record
    unique (source_system, source_record_id)
~~~

If NULL carries business meaning, explicitly decide whether multiple records without keys are allowed. You may need a partial/filtered unique index or expression index depending on the database. This is a vendor-specific feature requiring migrations and integration tests on the exact engine.

Do not use an empty string or a sentinel like UNKNOWN as a shared key for all records missing an ID if that causes valid records to collide with one another.

## 11. Normalizing data before applying unique keys

Two values can differ in representation yet be treated by the business as the same key:

- ABC and abc.
- Emails with leading/trailing whitespace.
- Codes with or without hyphens.
- Unicode encoded in different normalization forms.

If the database collation is case-insensitive, the unique constraint may treat ABC and abc as the same value. If the collation is case-sensitive, they may be treated as distinct. Exact rules depend on the database and column type.

You can normalize keys before writing:

~~~java
public String normalizeExternalId(String value) {
    if (value == null) {
        throw new InvalidInputException("externalId is required");
    }
    return value.strip().toUpperCase(Locale.ROOT);
}
~~~

Apply the same rule across every producer/writer and consider storing the raw value as well if needed for auditing. Do not change normalization rules across restarts of the same batch without versioning.

## 12. Do not concatenate multiple columns into an arbitrary string key

An error-prone approach that easily causes collisions is string concatenation:

~~~java
String key = tenantId + "-" + externalId;
~~~

If data contains hyphens, two different combinations can yield the same string. For example, tenant A-B with ID C and tenant A with ID B-C both produce A-B-C.

It is better to put the unique constraint across the individual columns:

~~~sql
unique (tenant_id, external_id)
~~~

If the system strictly requires a single idempotency string, use unambiguous encoding, length-prefixing, or a UUID/hash derived from a versioned canonical representation. The database should still protect the original business columns whenever possible.

## 13. The database is where uniqueness is decided

A pre-insert check commonly looks like:

~~~java
if (!repository.existsBySourceOrderId(order.sourceOrderId())) {
    repository.save(order);
}
~~~

This approach has a race condition:

~~~text
Worker A: SELECT -> O-100 not found
Worker B: SELECT -> O-100 not found
Worker A: INSERT O-100 -> succeeds
Worker B: INSERT O-100 -> duplicate
~~~

Two workers can both observe the non-existent state before either writes. Java-side checks only improve error messaging or avoid some redundant writes; they do not replace unique constraints.

A database constraint is the final mechanism that arbitrates between competing transactions.

## 14. Why SELECT-then-INSERT is not enough

Even when a job runs single-threaded, another application or another batch run can write the same key during the window between SELECT and INSERT.

This is a check-then-act race. Ordinary transaction isolation does not turn two separate statements into an atomic insert-if-absent operation.

Options include:

- Attempt INSERT directly and let the unique constraint decide.
- Use database-supported upsert/insert-if-absent syntax.
- Use deliberate locking/serialization if business logic requires it.
- Use staging and merge in a clearly transactioned workflow.

Do not use SELECT NOT EXISTS as the sole barrier against duplicates when concurrency exists.

## 15. Writing output with JdbcBatchItemWriter

JdbcBatchItemWriter is well-suited to writing many items using the same SQL statement:

~~~java
@Bean
JdbcBatchItemWriter<ImportedOrder> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<ImportedOrder>()
        .dataSource(dataSource)
        .sql("""
            insert into imported_order
                (source_system, source_order_id, customer_id, total_amount)
            values
                (:sourceSystem, :sourceOrderId, :customerId, :totalAmount)
            """)
        .beanMapped()
        .assertUpdates(true)
        .build();
}
~~~

If a chunk contains two items with the same source_system and source_order_id, the unique constraint rejects the duplicate. JdbcBatchItemWriter propagates the JDBC error to the step; Spring Batch handles it according to transaction and fault-tolerance policies.

assertUpdates(true) checks update counts per writer rules, yet does not replace the unique constraint. The unique constraint protects uniqueness; assertUpdates checks whether statements affected the expected rows.

## 16. Duplicate keys in JDBC batches

When an item in a JDBC batch violates a unique constraint, the driver may throw BatchUpdateException or an exception translated by Spring into DataAccessException, often DuplicateKeyException depending on the driver and execution path.

Details to keep in mind:

- Exceptions may be wrapped in multiple layers; inspect the root cause and SQLState/vendor code when needed.
- Update counts may show that some statements executed before the error occurred.
- Not all drivers pinpoint the exact offending item in the same way.
- If the batch runs within a chunk transaction, rollback undoes uncommitted transactional changes.
- With autocommit or out-of-transaction resources, partial results may remain.

Do not assume a failed batch means the database executed zero statements. Rely on real transactions and the actual database engine to protect consistency.

## 17. Should unique violations be skipped?

A duplicate key can have two very different meanings:

1. Input is bad or two conflicting records share the same business key.
2. The job is replaying a record already written successfully in a previous run, and the duplicate simply signals the operation was already applied.

You cannot decide whether to skip solely from the class name DuplicateKeyException. You need to know which constraint failed and the output contract.

Examples:

| Situation | Typical appropriate handling |
| --- | --- |
| Two lines in the same file share a source key with different content | Quarantine or fail per policy |
| Same event resent after a timeout | Idempotent replay or confirm already processed |
| Business key already exists from a prior batch, but this is a newer update | Versioned or event-ID-based UPDATE/upsert |
| Unique constraint violation unrelated to idempotency | Fail and investigate data/schema |

Skipping every DuplicateKeyException can hide key-design bugs or conflicting data.

## 18. Insert-if-absent and upsert

When supported by the database, SQL can handle duplicates atomically:

PostgreSQL:

~~~sql
insert into imported_order
    (source_system, source_order_id, customer_id, total_amount)
values
    (:sourceSystem, :sourceOrderId, :customerId, :totalAmount)
on conflict (source_system, source_order_id) do nothing;
~~~

MySQL:

~~~sql
insert into imported_order
    (source_system, source_order_id, customer_id, total_amount)
values
    (:sourceSystem, :sourceOrderId, :customerId, :totalAmount)
on duplicate key update
    customer_id = values(customer_id),
    total_amount = values(total_amount);
~~~

This syntax is vendor-specific, not portable SQL. Choose explicit behavior:

- DO NOTHING: keep the existing row if the key already exists.
- DO UPDATE: update the existing row with new data.
- MERGE: express matched/unmatched branches per database dialect.

An upsert does not by itself decide which data is newer or safe to overwrite. You need version conditions, event timestamps, or business rules to prevent an older event from overwriting newer state.

## 19. assertUpdates when using DO NOTHING

With INSERT ... ON CONFLICT DO NOTHING, a duplicate item can produce an update count of 0 because the database inserted no new row. If JdbcBatchItemWriter has assertUpdates(true), the writer may treat a zero-row result as an error.

If zero updates is the expected outcome for duplicate replays, you can configure:

~~~java
.assertUpdates(false)
~~~

However, disabling the assertion also means the writer will not catch other zero-row cases that might represent bugs. Use this only when the SQL is designed so zero-row is a valid outcome and tests confirm it.

If you need to distinguish inserted, already existed, and rejected, use database-specific SQL/returning clauses or a custom writer recording outcomes. Do not infer business state merely from the writer not throwing an exception.

## 20. Upserts must protect newer data from older data

A naive upsert can overwrite an existing row even when the new input is actually older:

~~~sql
insert into customer_snapshot
    (customer_id, status, source_version)
values
    (:customerId, :status, :sourceVersion)
on conflict (customer_id)
do update set
    status = excluded.status,
    source_version = excluded.source_version;
~~~

If event version 5 arrives after event version 8, the SQL above can regress data back to version 5.

You can add a version guard:

~~~sql
insert into customer_snapshot
    (customer_id, status, source_version)
values
    (:customerId, :status, :sourceVersion)
on conflict (customer_id)
do update set
    status = excluded.status,
    source_version = excluded.source_version
where excluded.source_version > customer_snapshot.source_version;
~~~

This is a PostgreSQL example. Syntax and semantics must be adapted for other databases. If two equal versions carry different payloads, determine whether that is a valid replay or a data conflict.

## 21. Multi-layered duplicate prevention

A solid design usually includes multiple layers of protection:

~~~text
Input
  |
  v
Normalize business key
  |
  v
Optional in-memory/chunk dedup
  |
  v
Processor validation
  |
  v
Database writer
  |
  v
Unique constraint / upsert
  |
  v
Persisted output
~~~

Each layer serves a specific purpose:

- Normalization ensures the same key has the same representation.
- Chunk-level dedup reduces duplicate trips to the database.
- Validation produces clear business errors.
- Unique constraints protect concurrency and all write paths.
- Upsert/idempotency handles replays according to contract.

Never drop the unique constraint just because the processor performs dedup. In-memory dedup cannot protect competing processes or transactions.

## 22. Deduplicating within a chunk

If chunks are small and duplicates are obvious, a processor or writer adapter can detect duplicates within chunk scope. However, ItemProcessor receives one item at a time; holding a Set in a processor field leaks state across chunk boundaries and can behave wrongly under retries or multi-threading.

An intentional alternative is deduplicating at the source with SQL:

~~~sql
select source_system, source_order_id, customer_id, total_amount
from (
    select s.*,
           row_number() over (
               partition by source_system, source_order_id
               order by source_updated_at desc, source_row_id desc
           ) as rn
    from staging_order s
    where batch_id = :batchId
) ranked
where rn = 1
order by source_system, source_order_id;
~~~

This query picks one record according to defined version/time rules. Verify database support for window functions and confirm the winner-selection rule fits business requirements.

If duplicates must be reported as errors rather than picking a winner, the query or validation step should detect duplicate groups and route them to quarantine.

## 23. Deduplication through a staging table

For large inputs, a staging table helps control duplicates before writing to the business table:

~~~text
Source file
   |
   v
Staging table
   |
   +--> validate source key
   |
   +--> detect duplicate groups
   |
   +--> select accepted records
   |
   v
Target table with unique constraint
~~~

Staging can store batch ID, source row number, raw key, normalized key, and validation status. Once duplicates are identified, the job can:

- Accept one record under explicit rules.
- Reject the entire duplicate group.
- Pick the latest source version.
- Save duplicate groups to an error table for operator handling.

Staging lets you re-run validation without re-reading the original file, though it needs retention and cleanup policies so data does not grow unboundedly.

## 24. Chunk transactions and unique constraints

In a chunk-oriented step, the writer typically runs inside the chunk transaction:

~~~text
BEGIN CHUNK TRANSACTION
  Read items
  Process items
  INSERT batch into target
  Update checkpoint metadata
COMMIT
~~~

If an insert violates a unique constraint and the exception rolls back the transaction, uncommitted transactional changes of the chunk are undone. Items in the chunk may be re-read/reprocessed under retry or restart policies.

To keep business output and checkpoints consistent, the writer must use the datasource/transaction manager properly configured for the step. If output goes to a different datasource or a separate autocommit connection, chunk rollback does not automatically undo that output.

Unique constraints remain necessary even when transaction rollback works properly. They protect data when another transaction or another job execution writes the same key.

## 25. Restarts and duplicate output

A common failure window:

~~~text
1. Job reads item K-100
2. Writer writes K-100
3. Database commit succeeds
4. Process stops before execution/checkpoint state is synchronized as expected
5. Job is restarted
6. K-100 may be sent again
~~~

Atomicity between business output and batch metadata depends on the JobRepository/transaction manager configuration. When they do not share a transaction, you cannot rely solely on checkpoints to guarantee an item is never re-sent.

A unique key based on source identity prevents inserting a second row. Upsert or insert-if-absent makes replay safe if that matches the contract. For non-database side effects, use idempotency keys or outbox/inbox.

Do not claim a unique constraint delivers exactly-once processing. It protects row uniqueness by key; business processing, events, and other resources still require dedicated design.

## 26. Multiple jobs or partitions writing the same key

Suppose two partitions read two files sharing a source order ID:

~~~text
Partition A -> INSERT source_order_id = O-100
Partition B -> INSERT source_order_id = O-100
~~~

One transaction may win while the other receives a unique violation or upsert result depending on SQL. This is desirable behavior if only one row is allowed to exist.

If arrival order decides the winner, outcomes can become non-deterministic when two partitions run concurrently. Do not let final data depend on which worker commits first if the business requires explicit version or precedence rules.

Approaches to handle this:

- Partition by business key so the same key always routes to the same partition.
- Use versioned upserts that accept only newer versions.
- Use staging and merge under deterministic rules.
- Use locks or serialization when ordering is strictly necessary.
- Write conflicts to a dedicated table for later resolution.

A unique constraint prevents duplicate rows, but does not decide which record is right when two different payloads carry the same key.

## 27. Is retrying a duplicate key useful?

A duplicate key caused by the same input is usually a deterministic error. Retrying the same item with the same key will keep violating the constraint. Therefore, do not configure DuplicateKeyException as a transient retry exception by default.

Retries may fit if the actual exception is a deadlock or transient connection failure. A duplicate key should only be treated as success/replay when the application can confirm it is the same operation previously applied.

For example, two events with the same event ID but different payloads should not automatically be ignored as harmless duplicates. The producer might have wrongly reused an ID or data may have changed. Compare checksums/versions or store a payload fingerprint to detect conflicts.

## 28. Skip duplicates or quarantine?

If duplicates represent data errors, you can configure skip exceptions after accurately identifying the constraint:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(orderWriter)
    .faultTolerant()
    .skip(DuplicateOrderException.class)
    .skipLimit(25)
    .listener(orderSkipListener)
    .build();
~~~

In practice, JdbcBatchItemWriter may emit different JDBC/Spring exceptions depending on the driver and how the batch executes. If you want to skip only one specific constraint, you may need an adapter translating root cause, SQLState/vendor code, and constraint name into DuplicateOrderException.

Do not catch every DuplicateKeyException and ignore it. Another constraint may indicate a severe data error. If the record must be reprocessed later, quarantine must store source key, batch ID, row number, and reason.

## 29. Identifying which constraint was violated

A table can have multiple unique constraints:

~~~sql
constraint uk_order_source unique (source_system, source_order_id),
constraint uk_order_number unique (order_number)
~~~

Violating uk_order_source may mean replaying the same source record. Violating uk_order_number may mean two different orders were assigned the same document number. The two errors may warrant different policies.

Constraint names may appear in messages/vendor exceptions, though format depends on database and driver. Avoid free-text message parsing when more reliable SQLState, vendor codes, or exception metadata are available.

If per-constraint logic is required, wrap the persistence layer to translate database errors into clearly typed business exceptions. Log the root cause so operators can still investigate.

## 30. JPA writers and when constraints are checked

With JPA, entities may be persisted into the persistence context before SQL actually runs. Unique constraints are typically checked by the database when INSERT/UPDATE flushes or when the transaction commits.

Example:

~~~java
public class CustomerJpaWriter implements ItemWriter<CustomerImport> {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public void write(Chunk<? extends CustomerImport> chunk) {
        for (CustomerImport item : chunk) {
            entityManager.persist(item);
        }
        entityManager.flush();
    }
}
~~~

flush() pushes pending SQL to the database so constraint errors can surface during the write phase. However, the transaction has not committed just because flush succeeded; deferred constraints (if supported and configured in the database) may still be checked only at commit.

Without flushing inside the writer, exceptions may appear later during transaction commit. When debugging or configuring skips, understand where in the lifecycle exceptions arise.

JpaItemWriter or repositories may have version-specific flush/clear behavior. Verify the implementation/configuration in use and test against a real database.

## 31. Unique constraints and JPA cascades

Persisting an entity can cascade to child entities. Unique constraints may live on child tables, join tables, or association tables. When persisting a parent, failures can stem from a child record rather than the main table.

Example:

~~~java
@OneToMany(cascade = CascadeType.PERSIST)
private List<OrderLine> lines;
~~~

If two orders both contain a line key that must be unique per invoice, the constraint on order_line may fail on flush. The exception may not clearly identify which parent item caused the error.

Design cascades intentionally, identify business keys for every table, and check constraints on all target tables. For large batches, persisting complex graphs can make isolating failing records hard; consider DTOs/flat outputs and specialized writers.

## 32. Unique constraints with soft deletes

If a table uses soft deletes, old records stay in the database:

~~~sql
update customer
set deleted_at = current_timestamp
where customer_id = :customerId;
~~~

An ordinary unique constraint still includes soft-deleted rows. Thus, you cannot insert a new row with the same key if the constraint covers the whole table.

If business rules allow reusing keys after soft deletion, you can use:

- A partial/filtered unique index covering only non-deleted rows, if the database supports it.
- Separate current-state and history tables.
- A composite key with version or validity range.
- A workflow that restores the old row instead of inserting a new one.

Partial/filtered indexes are database-dependent features. Verify migrations, query plans, and behavior when restoring records.

## 33. Unique constraints and version history

If multiple versions of the same entity must be stored, do not place a unique constraint solely on the business key. Extend the key with a version or separate current and history tables.

Example:

~~~sql
create table customer_version (
    customer_id varchar(80) not null,
    version_no integer not null,
    customer_name varchar(200) not null,
    effective_from date not null,
    constraint pk_customer_version
        primary key (customer_id, version_no)
);
~~~

If you must guarantee only one current version exists, enforcement depends on the database and model. You can use a current flag with a filtered unique index, or manage validity ranges with appropriate transactions/constraints.

Do not remove unique constraints to allow duplicates and hope the application picks the right version. Model versioning in the schema.

## 34. Unique keys in multi-tenant systems

In multi-tenant systems, keys are often unique only within a tenant:

~~~sql
unique (tenant_id, external_customer_id)
~~~

If you only declare unique(external_customer_id), two tenants might be blocked from importing the same valid code. Conversely, omitting tenant_id from lookup queries can let a processor update another tenant's data by mistake.

Ensure:

- Tenant ID is part of the unique key when the contract requires it.
- JobParameters include tenant scope and stay stable on restart.
- Reader, processor, and writer all bind the tenant properly.
- Cache keys include tenant ID.
- Integration tests verify two tenants using the same external ID.

Do not trust a tenant ID from an untrusted payload when the job was launched for a specific tenant. Compare and reject mismatches to prevent cross-tenant writes.

## 35. Unique constraints and collations

Database collations determine string comparisons, including case sensitivity or accent sensitivity in many systems. This affects uniqueness:

- Case-insensitive collations may treat abc and ABC as the same key.
- Case-sensitive collations treat them as two distinct keys.
- Some collations apply specific accent or Unicode normalization rules.

If a business key must be case-insensitive, align canonicalization with the index/collation. Do not merely call toUpperCase() in one processor if other write paths do not apply the same rule.

On databases supporting functional indexes, you can create a unique index over a normalized expression such as lower(email). This is vendor-specific SQL, and queries must use the same expression to leverage the index.

## 36. Batch writers and multiple constraints

An INSERT can violate multiple kinds of rules:

- Primary key duplicate.
- Business key duplicate.
- Missing foreign key.
- NOT NULL violation.
- CHECK constraint.

Do not lump everything into "duplicate" or "invalid item". Classify by constraint and cause:

| Constraint | Meaning | Handling approach |
| --- | --- | --- |
| Primary key | Internal ID collision | Usually a severe error or ID generation bug |
| Business unique key | Business record already exists | Replay/upsert/quarantine per contract |
| Foreign key | Parent/reference missing | Enrich/validate, quarantine, or fail |
| NOT NULL | Mandatory field missing | Data validation/skip if allowed |
| CHECK | Value outside valid domain | Business validation or quarantine |

Database constraints are the final line of protection. Processors can validate earlier for clearer error messages, yet constraints must still exist to guard against race conditions and all write paths.

## 37. Duplicate input data and processing order

If the same key appears multiple times in a file with different payloads, define a rule:

- First wins: keep the first occurrence.
- Last wins: keep the last occurrence.
- Highest version wins: keep the highest source version.
- Reject all duplicates: quarantine every record in the group.
- Merge: combine fields according to domain rules.

Do not let outcomes depend on chunk size. If first/last wins is computed only within a single chunk, duplicates spanning two chunks can yield different outcomes. Deduplicate across the whole batch or use staging/queries with deterministic ordering.

If input order matters, store source sequence/row number and use it in winner-selection rules. Never rely on the commit order of parallel partitions.

## 38. Index tuning for unique constraints

Unique constraints usually require an index for the database to enforce uniqueness and serve lookups. Consider:

- Choosing suitable key length and data types.
- Avoiding overly wide keys when unnecessary.
- Ordering columns to match query patterns.
- Avoiding redundant duplicate indexes.
- Assessing write cost since every insert/update maintains the index.
- Monitoring lock contention when multiple workers write to the same key range.

Unique indexes add write overhead, yet are usually a necessary trade-off for data protection. If a job needs high throughput, inspect execution plans and lock waits rather than dropping constraints for speed.

## 39. Handling migrations when a table already contains duplicates

Before adding a unique constraint to a large table:

1. Run a query detecting duplicates under the proposed key.
2. Identify causes and rules for retaining/merging data.
3. Plan handling for foreign keys and dependent tables.
4. Assess locks and index-build duration on large tables.
5. Deploy migrations compatible with the database's online indexing capabilities.
6. Verify the constraint exists after migration.
7. Test the writer with duplicates to verify violations are caught.

Some databases support creating indexes online/concurrently with specific limitations. Do not assume DDL behaves identically across vendors. For large tables, migration may need staged cleanup, index creation, and constraint attachment following database-supported workflows.

Do not just add an entity annotation and wait for Hibernate to alter production schemas.

## 40. Testing unique constraints with a real database

Unit tests mocking repositories do not prove unique constraints exist. You need integration tests using a production-compatible database engine, such as Testcontainers.

Essential tests:

- First insert of a key succeeds.
- Second insert of the same key is rejected or handled by upsert.
- Two composite keys with identical values for different tenants are accepted if allowed by contract.
- Same tenant/source/key is rejected.
- NULL and empty strings follow policy.
- Case normalization and collation produce expected results.
- Soft-deleted rows block or allow new keys per schema design.

H2 can work for some portable SQL tests, yet does not replace testing on the production database when using partial indexes, upserts, collations, or driver-specific semantics.

## 41. Testing duplicates within the same chunk

Create input containing two items with the same idempotency key:

~~~java
Chunk<ImportedOrder> chunk = new Chunk<>(List.of(
    order("SRC-A", "O-100"),
    order("SRC-A", "O-101"),
    order("SRC-A", "O-100")
));
~~~

With standard INSERT and a unique constraint, tests must confirm:

- The writer throws the expected exception on duplicate.
- The chunk transaction rolls back per configuration.
- No rows from the uncommitted chunk remain if the transaction rolled back.
- Skip/quarantine behavior works properly if the step is configured as fault tolerant.

Exact behavior when a batch statement fails depends on the driver/database. Inspect the table after the transaction finishes rather than asserting only exception types.

## 42. Testing duplicates across two chunks

Duplicates can span two different chunks:

~~~text
Chunk 1: O-100, O-101 -> COMMIT
Chunk 2: O-100, O-102 -> duplicate O-100
~~~

A local Set in a processor might detect duplicates if it holds step-wide state, yet that complicates restart and concurrency. The unique constraint must still catch cross-chunk duplicates.

Integration tests should run the step with a small chunk size to force the duplicate into a subsequent chunk. Verify the first chunk remains persisted, the second chunk rolls back/skips per policy, and no duplicate row exists.

## 43. Testing restarts and idempotent replay

A restart test should simulate an item written successfully and then resent:

1. Run the job with a batch having stable source record IDs.
2. Commit one or more chunks.
3. Stop the job at a failure point that leads to replay.
4. Restart the same JobInstance.
5. Verify unique keys prevent duplicate rows or upserts preserve exact state.
6. Verify counts and payloads for every business key.

Tests should distinguish same-payload replay from same-key different-payload. Same-payload replay may be a valid no-op; different payloads may be a conflict requiring quarantine or version checks.

Do not assert only total row counts if the table may contain records from earlier batches. Query by batch ID/source key to verify accurately.

## 44. Testing concurrency and race conditions

To verify a unique constraint protects two concurrent writers:

1. Prepare two transactions or two job workers.
2. Have both attempt to insert the same key.
3. Synchronize them so both start close together.
4. Verify the database stores only one row for that key.
5. Verify the losing worker receives the expected duplicate/upsert outcome per design.

Concurrency tests require a real database and proper synchronization barriers; sequential tests do not prove race conditions are guarded.

If the application uses multiple datasources or database instances, a constraint protects only the database/schema where it lives. There is no unique constraint spanning independent databases.

## 45. Testing JPA flush and constraint timing

With a JPA writer, test both timings:

- When calling persist/merge.
- When flushing or committing the transaction.

Example:

~~~java
assertThatThrownBy(() -> {
    writer.write(new Chunk<>(List.of(first, duplicate)));
    entityManager.flush();
}).isInstanceOf(PersistenceException.class);
~~~

Specific exceptions may be wrapped by Hibernate/Spring. Tests should inspect root causes and verify the database holds no duplicates after rollback.

Avoid holding an outer test transaction open if it distorts chunk transactions or hides commit/rollback behavior. Set up fixtures and verify data in explicit separate transactions.

## 46. Monitoring duplicates and conflicts in production

Metrics should distinguish:

- Items inserted successfully.
- Replays that already existed and were handled as no-ops.
- Business key conflicts.
- Unique violations per constraint.
- Retries, skips, and quarantines.
- Upsert updates versus inserts when the database provides that info.
- Other constraint failures such as foreign key, NOT NULL, or CHECK.

Logs should include job execution ID, step execution ID, source batch ID, business key, and constraint name if identifiable. Do not log full sensitive payloads.

A sudden spike in duplicates may indicate a producer resending files, overlapping scheduler runs, out-of-sync checkpoints, or overlapping partitions. Alerts help find root causes rather than simply raising skip limits.

## 47. Common mistakes when using unique constraints in batch

**Using only a Java Set to prevent duplicates:** does not protect across processes or restarts. Keep unique constraints in the database.

**Choosing the wrong business key:** keys that are too broad or too narrow block valid records or allow duplicates. Define the contract before creating constraints.

**Omitting tenant/source system from composite keys:** two sources may reuse the same external ID. Include scope in the key when business rules require it.

**Assuming NULL behaves identically across all databases:** verify the engine and use NOT NULL when keys are mandatory.

**Using SELECT-then-INSERT as the barrier:** suffers from race conditions. Use constraints and appropriate upsert/insert-if-absent statements.

**Skipping every DuplicateKeyException:** can mask other constraint errors or payload conflicts. Identify the constraint and business meaning.

**Retrying duplicate keys:** identical input keeps failing. Retry only transient failures; handle replays via idempotency.

**Disabling assertUpdates to ignore errors:** zero-row updates can hide wrong business keys. Disable only when zero-row is a designed outcome.

**Assuming unique constraints produce exactly-once:** they only protect row uniqueness by key. Remote side effects and multiple datasources need separate idempotency/outbox.

**Upserts without version checks:** old events can overwrite newer data. Add source version/effective time to update rules.

**Adding constraints to tables with existing duplicates:** migrations can fail or demand cleanup. Inspect data before deploying.

**Using annotations instead of migrations:** production schemas may lack constraints. Manage DDL via migrations and verify post-deploy.

**Not testing against the production database:** H2 can differ on NULLs, collations, upserts, update counts, and error behavior. Use the real engine for vendor-dependent tests.

**Letting outcomes depend on which worker wins the race:** same key with different payloads can yield non-deterministic output. Use version/precedence rules or quarantine conflicts.

## 48. Process for designing database output with unique constraints

First, define business keys and idempotency keys separately. Decide uniqueness scope: global, per tenant, per source system, per batch, or per version. Standardize key representations and define NULL, case sensitivity, soft delete, and version semantics.

Next, deploy primary keys, unique constraints, NOT NULLs, and indexes via migrations. Check existing duplicates before adding constraints. In the writer, use prepared/named parameters and choose INSERT, upsert, or insert-if-absent according to contract. Do not rely on SELECT-before-INSERT to prevent races. Distinguish duplicate replays from conflicting data; retry only transient errors and skip/quarantine only when business rules allow.

Finally, test against a real database with duplicates inside the same chunk, across chunks, across restarts, and between two concurrent transactions. Verify transaction rollbacks, update counts, JPA flush timing, and exact driver behavior. Monitor duplicates/conflicts per constraint in production and maintain a workflow to inspect and reprocess quarantined records.

Database output and unique constraints form the foundation for batch jobs to write consistent data when inputs contain duplicates, jobs restart, or multiple workers compete. Unique constraints enforce data rules in the database; writers and transactions define how errors are handled; idempotency keys and upserts make replays safe under contract. When business keys are chosen well, schemas are managed by migrations, and failure windows are tested on a real database, batches can re-run without creating duplicate data or overwriting valid results wrongly.
