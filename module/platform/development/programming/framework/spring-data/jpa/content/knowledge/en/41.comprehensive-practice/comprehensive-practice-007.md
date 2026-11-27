# Large-Scale Data Import with Chunking, Flushing, and Error Recovery

When importing tens of thousands or millions of records with Spring Data JPA, processing each Entity inside a single huge transaction places heavy pressure on the heap, persistence context, database connections, locks, and transaction logs. A common approach is to split the input into controlled chunks, write via JDBC batching, flush and clear the persistence context periodically, and explicitly define which chunks commit independently.

Three concepts should be kept distinct:

- **JDBC batch size:** the number of SQL statements of the same type grouped together for JDBC batch execution.
- **Flush/clear interval:** the number of Entities processed before synchronizing the persistence context to the database and releasing managed Entities.
- **Transaction chunk size:** the number of records belonging to a single transaction that commit or roll back together.

These three values are related, yet they do not have to be equal. You can flush multiple times within a single transaction chunk, while the transaction commits only when the transactional method completes successfully.

## 1. Why Chunking Is Needed for Large Imports

Suppose you need to import 500,000 CSV rows. Reading and saving all of them inside one transaction:

~~~java
@Transactional
public void importAll(List<ImportRow> rows) {
    for (ImportRow row : rows) {
        repository.save(toEntity(row));
    }
}
~~~

This approach can encounter several issues:

- The persistence context retains a massive number of managed Entities.
- Hibernate must track state changes and run dirty checking across a huge object set.
- Heap memory grows and garbage collection spends significant CPU time.
- The transaction holds a database connection for a long duration.
- Locks may be held too long, forcing other transactions to wait.
- If an error occurs on the last row, all prior work can roll back.
- Retrying the whole file repeats a vast amount of work.
- Pinpointing the failing row and resuming from where processing stopped becomes difficult.

Splitting data into smaller chunks bounds memory usage, transaction duration, and recovery scope. For instance, 500,000 rows can be processed in chunks of 500 or 1,000 rows depending on the workload and database.

There is no single optimal chunk size for every system. Measure on representative data and a production-like database.

## 2. Distinguishing Chunk, Flush, and Commit

A large import pipeline typically has three layers:

~~~text
File / data source
        |
        v
Read one transaction chunk
        |
        v
Process small Entity batches
        |
        +--> persist/update Entity
        +--> flush at interval
        +--> clear persistence context
        |
        v
Update checkpoint in same transaction
        |
        v
COMMIT transaction chunk
        |
        v
Read next chunk
~~~

For example, a transaction chunk of 1,000 rows with a flush interval of 100:

- Process 100 rows, then flush and clear.
- Process the next 100 rows, then flush and clear.
- Repeat through all 1,000 rows.
- Update the checkpoint.
- Commit the transaction once for the entire 1,000-row chunk.

If an error happens at row 950, all 1,000 rows in that transaction chunk still roll back, including the 100-row groups flushed earlier. Flushing sends SQL to the database within the active transaction; it does not commit.

## 3. Persistence Context and Dirty Checking

Entities loaded or persisted inside a transaction become managed. Hibernate tracks managed Entities to detect changes and generate SQL on flush.

Example:

~~~java
@Transactional
public void updateCustomer(Long id) {
    Customer customer = repository.findById(id).orElseThrow();
    customer.changeName("New name");
    // No need to call save() again for dirty checking to detect the change.
}
~~~

In a batch, if each iteration persists thousands more Entities without clearing, the persistence context can retain all those objects until the end of the transaction.

`EntityManager.clear()` detaches every managed Entity in the current persistence context. After clearing:
- Previously managed Entities are no longer tracked by dirty checking.
- Do not keep modifying old objects expecting JPA to persist those changes automatically.
- Objects requiring further updates must be reloaded or intentionally merged.
- New Entities persisted after clearing become managed again.

For DTO/record-based imports, you typically only need to convert each row to an Entity, persist, flush, and clear; there is no need to retain old Entities in memory.

## 4. flush() Is Not Commit

`EntityManager.flush()` instructs the persistence provider to synchronize pending changes in the persistence context to the database.

~~~java
entityManager.persist(entity);
entityManager.flush();
~~~

After flushing:
- SQL statements may have executed.
- Constraint violations, unique violations, or SQL errors can surface.
- The database is still inside the active transaction.
- The transaction can still roll back.

Commit happens only at the transaction boundary managed by the transaction manager, typically when the `@Transactional` method finishes normally.

Example:

~~~java
@Transactional
public void saveBatch(List<ImportRow> rows) {
    for (ImportRow row : rows) {
        entityManager.persist(toEntity(row));
    }

    entityManager.flush();

    if (shouldFailForDemo()) {
        throw new ImportException("Simulated failure");
    }
}
~~~

If `ImportException` is a `RuntimeException` and escapes the method, the transaction rolls back even though `flush()` already ran. None of the `INSERT`s sent to the database in that transaction are committed.

## 5. clear() Bounds Memory Usage

Combine flush and clear on an interval:

~~~java
@Transactional
public void persistChunk(List<ImportRow> rows) {
    int count = 0;

    for (ImportRow row : rows) {
        entityManager.persist(toEntity(row));
        count++;

        if (count % 100 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

Flush before clearing so pending changes are synchronized to the database. Then clear so the persistence context does not keep holding the processed Entities.

Do not clear before flushing if pending changes need to be saved. Clearing detaches Entities; unflushed changes on them may be lost.

The example above assumes each row creates a new Entity. If updating loaded Entities, ensure every mutation is flushed before clearing. Never keep using detached references as if they were still managed.

## 6. Configuring Hibernate JDBC Batching

Flush/clear controls the persistence context, while JDBC batching controls how Hibernate dispatches SQL statements.

Example Spring Boot configuration:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
          batch_versioned_data: true
        order_inserts: true
        order_updates: true
~~~

Meaning:
- `hibernate.jdbc.batch_size`: maximum JDBC batch size for eligible statements.
- `hibernate.order_inserts`: sorts `INSERT`s to increase grouping of identical statements.
- `hibernate.order_updates`: sorts `UPDATE`s to improve batching and potentially reduce deadlocks in certain workloads.
- `hibernate.jdbc.batch_versioned_data`: allows batching versioned updates when the driver/provider supports checking updated row counts properly.

Exact property names and defaults depend on the Hibernate version. Verify supported configuration in your project's version.

A JDBC batch size of 50 does not mean Hibernate constructs a single SQL `INSERT` with 50 value tuples. Usually the driver receives a batch of multiple executions of the same prepared statement. SQL logs can look different from actual network round trips; use driver/database metrics or appropriate observability tools to confirm batching.

## 7. Note on IDENTITY and JDBC Insert Batching

ID generation strategy affects batching capability. In Hibernate, using `GenerationType.IDENTITY` generally disables JDBC insert batching for Entities using the identity generator because Hibernate must execute the `INSERT` immediately to obtain the database-generated primary key.

Example:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

If a large import workload relies on insert batching, consider a sequence generator or an ID mechanism compatible with your database/provider:

~~~java
@Id
@GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "import_record_seq"
)
@SequenceGenerator(
        name = "import_record_seq",
        sequenceName = "import_record_seq",
        allocationSize = 50
)
private Long id;
~~~

This example assumes a database that supports sequences. Not all databases support the same strategies. Sequence allocation reduces ID-fetch round trips and enables better batching, but you must verify schema alignment, increment/allocation size, and actual Hibernate configuration.

Do not change an ID strategy solely to optimize batching if the system has compatibility constraints or existing data prevents it. Measure and choose according to your database.

## 8. saveAll() Does Not Mean a Single Bulk INSERT

`JpaRepository.saveAll()` is convenient for persisting a collection:

~~~java
repository.saveAll(entities);
~~~

However, do not assume this method always issues a single `INSERT` statement. Spring Data typically iterates over the Entities and calls `save` for each item; Hibernate can group compatible SQL into JDBC batches if configuration and ID strategy allow.

For new Entities, Spring Data's newness detection decides between `persist` and `merge`. If IDs are pre-assigned or newness state is unclear, `saveAll` may take the `merge` path and incur unnecessary select/synchronization overhead.

When importing new Entities, design ID and newness detection properly. If you need explicit control over each persist and flush/clear cycle, use `EntityManager` directly inside a dedicated custom repository or service.

## 9. Choosing the Three Sizes Independently

Consider the three parameters independently:

| Parameter | Example | Primary Impact |
|---|---:|---|
| JDBC batch size | 50 | Number of statements grouped when sent over JDBC |
| Flush/clear interval | 100 | Persistence context size and SQL synchronization frequency |
| Transaction chunk size | 1,000 | Number of rows committing/rolling back together |

For instance, a 1,000-row transaction chunk can run 10 flush/clear cycles of 100 rows each, while the JDBC batch size is 50.

If the flush interval is smaller than the JDBC batch size, you might not accumulate enough homogeneous statements to fill a full batch. If the flush interval is too large, the persistence context retains more Entities and buffered SQL grows.

If the transaction chunk is too large, transaction duration and rollback blast radius grow. If it is too small, transaction start/commit and checkpoint overhead increase. Benchmark different values.

## 10. Placing Transactions on the Chunk Worker

To commit each chunk independently, place the transaction boundary on a worker method invoked through a Spring proxy.

Example coordinator without an outer transaction:

~~~java
@Service
public class ImportCoordinator {

    private final ImportBatchWorker worker;

    public ImportCoordinator(ImportBatchWorker worker) {
        this.worker = worker;
    }

    public void importAll(List<List<ImportRow>> chunks) {
        for (List<ImportRow> chunk : chunks) {
            worker.persistChunk(chunk);
        }
    }
}
~~~

Worker:

~~~java
@Service
public class ImportBatchWorker {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void persistChunk(List<ImportRow> rows) {
        int count = 0;

        for (ImportRow row : rows) {
            entityManager.persist(toEntity(row));

            if (++count % 100 == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

Because the coordinator has no transaction, each call to `persistChunk()` through the proxy starts a new transaction under the default `REQUIRED` propagation; the transaction commits when that method finishes cleanly. If a chunk fails, that chunk rolls back and the exception propagates back to the coordinator.

This is critical: if the coordinator also carries `@Transactional` and the worker uses the default `REQUIRED`, the worker joins the existing outer transaction. Chunks will no longer commit independently; everything would commit together at the end of the coordinator.

## 11. When Is REQUIRES_NEW Needed?

If the caller already holds a transaction yet each chunk must commit independently, you can use:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void persistChunk(List<ImportRow> rows) {
    // Persist, flush, and clear one chunk.
}
~~~

`REQUIRES_NEW` suspends the outer transaction and opens an independent transaction for the worker. When the worker commits, that chunk's changes persist even if the outer transaction later rolls back.

Trade-offs:
- The outer transaction may hold a connection while the inner transaction needs a second connection.
- The connection pool must have sufficient capacity.
- Locks held by the outer transaction can block or conflict with the chunk transaction.
- Committed chunks cannot roll back together with the outer transaction.
- Coordination and retry logic becomes more complex.

If the coordinator does not need a transaction, keeping the coordinator non-transactional and the worker `REQUIRED` is usually simpler. Use `REQUIRES_NEW` only when isolation from an existing caller transaction is truly required.

## 12. Avoiding Self-Invocation Breaking Transaction Boundaries

Standard Spring transactions are applied through proxies. Internal calls via `this` bypass the proxy:

~~~java
@Service
public class ImportService {

    public void importAll(List<List<ImportRow>> chunks) {
        for (List<ImportRow> chunk : chunks) {
            this.persistChunk(chunk);
        }
    }

    @Transactional
    public void persistChunk(List<ImportRow> chunk) {
        // May not receive a new transaction as expected.
    }
}
~~~

Separating the coordinator and worker into two beans as in the previous example ensures calls traverse the proxy. Never rely on self-invocation to start a separate transaction for each chunk.

Also verify method visibility and proxy mode per your Spring configuration. In standard proxy mode, only calls coming from outside the bean pass through the transaction interceptor.

## 13. Writing Checkpoints in the Same Transaction as Data

If a job stops partway through, a checkpoint identifies where to resume. The checkpoint should be updated in the same transaction as the chunk's records.

Example:

~~~java
@Transactional
public void persistChunk(
        String jobId,
        long lastSourceSequence,
        List<ImportRow> rows) {

    for (ImportRow row : rows) {
        entityManager.persist(toEntity(row));
    }

    ImportCheckpoint checkpoint =
            checkpointRepository.findById(jobId).orElseThrow();

    checkpoint.advanceTo(lastSourceSequence);

    entityManager.flush();
    entityManager.clear();
}
~~~

When imported Entities and the checkpoint share the same transaction manager/resource:
- When the chunk commits, both data and checkpoint commit together.
- When the chunk rolls back, both data and checkpoint roll back together.
- When the process restarts, it reads the checkpoint to resume after the last committed position.

Do not update the checkpoint in a separate transaction before chunk data commits. If the checkpoint advances while data rolls back, a subsequent run could skip unsaved rows.

Nor should you update the checkpoint after commit in an unprotected operation assuming no crash window exists. If the process crashes after data commits but before the checkpoint updates, the chunk may run again. The reliable approach is writing data and checkpoint in the same transaction.

## 14. Designing Idempotent Imports

Even with transactional checkpoints, a job may still receive duplicate inputs or re-run due to retries, operator restarts, or duplicate message delivery. Design import operations to be safely repeatable.

Common techniques:
- Store a source ID or external key backed by a unique constraint.
- Use upsert by business key when supported by the database and semantically appropriate.
- Record job ID and source sequence to detect already-processed rows.
- Avoid external side effects outside the database before a chunk commits.
- Use an outbox if messages must be emitted after commit.
- Define clearly whether duplicate records are skipped, updated, or flagged as errors.

Example Entity storing a source key:

~~~java
@Entity
@Table(
    name = "imported_record",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_imported_record_source",
        columnNames = {"source_system", "source_id"}
    )
)
public class ImportedRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false)
    private String sourceSystem;

    @Column(nullable = false)
    private String sourceId;
}
~~~

The unique constraint protects data even if two workers accidentally process the same row. The application must still handle duplicate errors according to the chosen policy; never rely solely on an "exists" check before `INSERT`, because two concurrent transactions can both pass that check.

## 15. Recovering When a Chunk Fails

When the worker throws an exception and its transaction rolls back, the coordinator can record the failed chunk outside that transaction:

~~~java
public void importAll(List<List<ImportRow>> chunks) {
    for (int index = 0; index < chunks.size(); index++) {
        try {
            worker.persistChunk(chunks.get(index));
        } catch (RuntimeException exception) {
            failureRecorder.record(index, exception);
            throw exception;
        }
    }
}
~~~

This example only shows where to catch the error. If the coordinator writes the failure record inside the same rolled-back transaction, that record rolls back too. `failureRecorder` must execute after the worker transaction ends and use its own transaction if persisting failure state durably.

You can choose one of these policies:

- **Fail fast:** stop the job on the failing chunk; an operator fixes the data and resumes.
- **Retry transient failures:** retry the chunk with backoff for deadlocks, timeouts, or temporary network errors.
- **Quarantine rows:** move invalid rows into an error/dead-letter table and continue if business rules permit skipping.
- **Split chunk:** subdivide the failing chunk into smaller pieces to isolate the offending rows.
- **Manual review:** retain job and error state for operator decision.

Never catch every exception and proceed as if the chunk succeeded. That can advance the checkpoint improperly or leave missing data.

## 16. Distinguishing Transient Errors from Data Errors

Not every error should be retried:

| Error Type | Examples | Appropriate Action |
|---|---|---|
| Transient database failure | Deadlock, lock timeout, connection reset | Bounded retry with backoff in a new transaction |
| Constraint violation | Unique, FK, `NOT NULL` | Inspect data or handle duplicates per business rules |
| Mapping/type error | String cannot parse to number/date | Fix or quarantine the row |
| Optimistic locking | Concurrent version change | Reload and decide whether to retry per business rules |
| Resource exhaustion | Heap OOM, connection pool exhaustion | Reduce chunk/concurrency, fix operational root cause |
| Procedure/external failure | Downstream system unresponsive | Retry using idempotency and suitable timeouts |

Retries must execute in a fresh transaction after the previous transaction rolled back. Never keep executing statements inside a transaction already marked rollback-only.

If using Spring Retry or `RetryTemplate`, place the retry around the proxy call to the transactional worker, or configure explicit advisor ordering so each attempt receives a fresh transaction. Test the retry/transaction ordering under your actual configuration; never assume annotations create a new transaction under self-invocation.

## 17. Never Swallow Exceptions Inside Transactional Workers

Unsafe example:

~~~java
@Transactional
public void persistChunk(List<ImportRow> rows) {
    try {
        // Write data.
    } catch (DataIntegrityViolationException exception) {
        log.error("Import failed", exception);
        // Return normally.
    }
}
~~~

If the exception is caught and not rethrown, the proxy sees the method return normally and attempts to commit. Certain database/provider errors have already marked the transaction rollback-only; attempting to commit can throw `UnexpectedRollbackException`.

If the whole chunk must fail, rethrow an appropriate exception:

~~~java
catch (DataIntegrityViolationException exception) {
    throw new ImportChunkException("Chunk is invalid", exception);
}
~~~

If you intend to skip a bad row and continue, design error-handling boundaries explicitly per row or sub-batch. Never wrap everything in a blanket try/catch to mask errors and still mark the checkpoint successful.

## 18. Handling Bad Rows While Preserving Valid Ones

If business rules permit partial imports, validate data before writing:

1. Parse and validate format.
2. Separate valid and invalid rows.
3. Persist valid rows in chunks.
4. Write row errors to a quarantine table or error report file.
5. Update checkpoint and metrics within the appropriate transaction.

Example:

~~~java
List<ImportRow> validRows = new ArrayList<>();
List<RowError> invalidRows = new ArrayList<>();

for (ImportRow row : inputRows) {
    ValidationResult result = validator.validate(row);

    if (result.isValid()) {
        validRows.add(row);
    } else {
        invalidRows.add(new RowError(
                row.sourceSequence(),
                result.message()
        ));
    }
}

worker.persistChunk(jobId, validRows, invalidRows);
~~~

The worker can persist valid data, errors, and the checkpoint in a single transaction if policy requires recording a chunk atomically. If errors are persisted in a separate transaction, specify clearly what state the checkpoint represents.

For constraints enforced only at the database level, pre-validation does not replace database constraints. Unique/FK relationships can change concurrently; the worker must still handle errors at flush/commit time.

## 19. Bulk DML May Fit Better Than Entity Batching

If you only need to update the same column value across many rows, a JPQL bulk update can be more efficient than loading each Entity and modifying it:

~~~java
@Modifying
@Query("""
    update Customer c
       set c.active = false
     where c.lastLoginAt < :cutoff
    """)
int deactivateInactiveCustomers(Instant cutoff);
~~~

Bulk DML runs directly against the database without hydrating individual Entities. However, it bypasses Entity lifecycle callbacks, dirty checking, and cascades as performed by normal Entity operations. The persistence context can hold stale state after a bulk update.

You can use:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
~~~

to request flushing before and clearing the persistence context after the bulk operation per Spring Data configuration. Understand the effect on any managed Entities carrying uncommitted changes.

Choose Entity batching when you need lifecycle callbacks, auditing, domain validation/behavior, or cascades. Choose bulk DML for simple set-based operations expressible directly in SQL/JPQL, once version handling, auditing, and persistence-context synchronization are accounted for.

## 20. Reading Large Datasets Without Holding Everything in Heap

Not only writes—reading an entire file or loading every Entity into a `List` before processing also strains memory.

Options:
- Stream files line by line and assemble DTO chunks.
- Use `Pageable` to read page by page.
- Use keyset/scrolling when deep offsets become expensive.
- Use JDBC cursors/fetch sizes when supported by provider and driver.
- Use projections to read only needed columns.

Example reading page by page:

~~~java
int pageNumber = 0;
Page<SourceRecord> page;

do {
    page = sourceRepository.findAll(
            PageRequest.of(pageNumber, 500, Sort.by("id").ascending())
    );

    process(page.getContent());
    pageNumber++;
} while (page.hasNext());
~~~

Offset pagination slows down on deep pages and is sensitive to concurrent inserts/deletes during traversal. For large datasets, a stable sort with a keyset cursor is usually more suitable.

A repository returning `Stream<T>` does not automatically guarantee row-by-row fetching by the driver/database. Streams can hold open `ResultSet`, `Statement`, and database connections; they require an active transaction and must be closed with `try-with-resources`. Verify fetch sizes and actual driver behavior.

## 21. Avoiding N+1 and Keeping Input Data Lean

During imports, if every row needs to look up a reference Entity, querying the repository inside the row loop creates N+1 queries.

Inefficient example:

~~~java
for (ImportRow row : rows) {
    Category category = categoryRepository.findByCode(row.categoryCode())
            .orElseThrow();
    entityManager.persist(toEntity(row, category));
}
~~~

Instead, collect the chunk's category codes, load them once, and build a map:

~~~java
Set<String> codes = rows.stream()
        .map(ImportRow::categoryCode)
        .collect(Collectors.toSet());

Map<String, Category> categories =
        categoryRepository.findByCodeIn(codes).stream()
                .collect(Collectors.toMap(
                        Category::getCode,
                        Function.identity()
                ));
~~~

Then match each row with its corresponding `Category`. If reference tables are huge, any cache/reference map may need size bounds and freshness policies.

Do not hold an entire reference table map in heap if the dataset is too large. Load only the keys needed by the current chunk or use a bounded cache.

## 22. Monitoring Progress and Performance

A batch job should capture metrics sufficient for operations and recovery:

| Metric | Purpose |
|---|---|
| Rows read | Total rows read from the source |
| Rows valid/invalid | Counts passing or failing validation |
| Rows persisted | Rows successfully written |
| Chunks committed | Transaction chunks committed |
| Chunk duration | Processing time per chunk |
| Flush duration | Cost of synchronizing the persistence context |
| Retry count | Number of retries and their causes |
| Failed row/chunk | Location and error for recovery |
| JDBC batch metrics | Whether batching is actually taking effect |
| Heap/GC | Detecting excessive object retention |
| DB latency/lock wait | Spotting database bottlenecks |
| Connection pool usage | Detecting transactions holding connections too long |

Log `jobId`, chunk number, source sequence range, and error codes for traceability. Avoid logging full input rows containing personal information or secrets.

Increasing chunk size can reduce transaction overhead but increases memory, lock duration, and rollback scope. Increasing JDBC batch size can cut round trips but does not fix an oversized persistence context. Tune each parameter based on measurements.

## 23. Testing Batch Imports and Error Recovery

Integration tests must prove successful writes, within-chunk rollbacks, and independent commits across chunks.

Cases to include:
1. Valid chunk: all rows are saved.
2. Mid-chunk failure: all database changes in that chunk roll back.
3. Previously committed chunk: a failure in a later chunk does not undo earlier committed chunks when designed for independent commits.
4. Checkpoint advances only when chunk data commits.
5. Restarting from a checkpoint skips no data.
6. Re-running the same input creates no unintended duplicates.
7. Unique/FK/`NOT NULL` violations are classified accurately.
8. Retries of transient failures run in a new transaction.
9. Flush/clear does not lose changes intended to be saved.
10. Persistence context memory does not grow unbounded over long batches.
11. JDBC batching actually works on the target database/driver.
12. Bulk DML does not leave managed Entities holding stale state.

Example test for rollback after flush:

~~~java
@SpringBootTest
class ImportBatchIntegrationTest {

    @Autowired
    private ImportBatchWorker worker;

    @Autowired
    private ImportedRecordRepository repository;

    @Test
    void failedChunkRollsBackAllItsRows() {
        List<ImportRow> rows = List.of(
                new ImportRow("source-1", "A"),
                new ImportRow("source-2", "B"),
                new ImportRow("source-3", "C")
        );

        assertThrows(
                ImportChunkException.class,
                () -> worker.persistChunkWithFailure(rows, 2)
        );

        assertEquals(0, repository.count());
    }
}
~~~

This is an illustrative structure; `persistChunkWithFailure` is a test hook or test fixture worker intentionally throwing after flush. The test method itself should not carry an enclosing transaction if the goal is observing that the worker transaction rolled back independently. If using `@DataJpaTest` (which wraps tests in a transaction by default), account for the test transaction and use a new transaction/cleared context when verifying committed state.

Testing independent chunk commits:

~~~java
@Test
void firstChunkRemainsCommittedWhenSecondChunkFails() {
    coordinator.importChunksWithFailureAfterFirstChunk();

    assertEquals(100, repository.count());
}
~~~

This example assumes the coordinator invokes each chunk through the worker proxy, the first chunk commits, the second rolls back, and the error is handled by the coordinator. Verify state using a fresh transaction/read context rather than relying on previously managed Entities.

Use Testcontainers with a database engine and version close to production to verify JDBC batching, identity/sequences, constraints, locking, and SQL dialects. H2 does not prove identical behavior to MySQL, PostgreSQL, SQL Server, or Oracle.

## 24. Common Pitfalls

**Assuming saveAll() automatically creates a bulk INSERT**

`saveAll` typically loops over `save`; JDBC batching depends on Hibernate, the driver, the ID strategy, and configuration.

**Flushing without clearing in long batches**

SQL is sent to the database, yet the persistence context retains all managed Entities. Memory can keep growing.

**Clearing before flushing**

Unflushed changes can be dropped from the persistence context. Flush first, then clear.

**Confusing flush with commit**

Flush does not end the transaction. Flushed changes can still roll back.

**Putting @Transactional on the coordinator so chunks do not commit independently**

Workers using `REQUIRED` join the outer transaction. Keep the coordinator non-transactional or intentionally use `REQUIRES_NEW`.

**Calling the worker via self-invocation**

Internal calls bypass standard proxies, so transaction boundaries may not apply.

**Retrying inside a rollback-only transaction**

Retries must start a fresh transaction. Place retry logic outside the transactional proxy call.

**Updating the checkpoint before data commits**

A crash can cause the job to skip uncommitted rows. Write the checkpoint in the same transaction as the chunk data.

**Non-idempotent re-runs**

Job restarts/retries can create duplicates. Use source keys, unique constraints, and explicit upsert/duplicate policies.

**Using IDENTITY and expecting JDBC insert batching**

Hibernate generally disables insert batching for Entities using `IDENTITY`. Consider sequences or an appropriate ID strategy.

**Oversized chunks**

Transactions last longer, rollbacks are expensive, and more resources stay locked. Measure and shrink chunk sizes when needed.

**Undersized chunks**

Transaction and checkpoint overhead rise. Benchmark instead of guessing.

**Catching exceptions and continuing without recording failure state**

Jobs can advance progress erroneously or silently drop data. Classify errors and record failures after rollback.

**Running bulk updates without clearing the persistence context**

Managed Entities may retain stale data. Flush/clear/refresh within the right scope.

## 25. Large Data Import Implementation Workflow

When building batch imports with Spring Data JPA:

1. Define input schemas, source keys, and idempotency requirements.
2. Choose a transaction chunk size based on acceptable processing time, locks, and rollback scope.
3. Choose a flush/clear interval to bound the persistence context.
4. Configure JDBC batch size and verify the ID generation strategy.
5. Place transactions on a worker bean invoked through a proxy.
6. Keep the coordinator non-transactional if each worker call must commit independently; use `REQUIRES_NEW` when separating from an existing caller transaction.
7. Flush periodically and then clear to bound memory.
8. Write checkpoints in the same transaction as chunk data.
9. Choose a policy among fail-fast, retry, quarantine, or chunk splitting.
10. Retry transient errors in a new transaction with backoff and a max-attempt cap.
11. Ensure import operations are idempotent to support restarts.
12. Avoid direct HTTP/message broker calls inside long transactions; use an outbox for durable side effects.
13. Measure heap, GC, JDBC batching, DB latency, lock waits, and chunk duration.
14. Integration-test rollbacks, independent commits, checkpoints, duplicates, and restarts on the target database.

## 26. Conclusion

Large-scale data import with Spring Data JPA requires managing JDBC batch size, flush/clear interval, and transaction chunk size independently. JDBC batching cuts round trips when supported by driver and provider; flush synchronizes SQL without committing; clear releases Entities from the persistence context. To make each chunk commit independently, place the transaction on a proxy-invoked worker and ensure no outer `REQUIRED` transaction wraps the entire job, or use `REQUIRES_NEW` when truly required.

For safe recovery, persist checkpoints in the same transaction as chunk data, make imports idempotent, distinguish transient failures from data errors, and retry in fresh transactions. Test within-chunk rollbacks, prior-chunk commits, checkpoint restarts, actual batching, and data correctness on a production-like database. Never equate `saveAll` with bulk `INSERT`, never confuse flush with commit, and never increase chunk sizes without measuring the impact on heap, locks, connections, and recovery time.