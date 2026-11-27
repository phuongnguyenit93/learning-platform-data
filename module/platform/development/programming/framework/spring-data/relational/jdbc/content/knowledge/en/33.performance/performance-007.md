# Distinguishing saveAll, Batch Insert, and Batch Update via Direct JDBC

When writing many records, three options are commonly mentioned: ¤saveAll(...)¤, batch insert, and batch update using JDBC. All of them can reduce overhead when processing multiple objects, yet they do not share the same semantics.

- Spring Data JDBC's ¤saveAll(...)¤ persists multiple **aggregates** using Spring Data's mapping and persistence lifecycle.
- ¤JdbcAggregateTemplate.insertAll(...)¤ and ¤updateAll(...)¤ explicitly state whether all inputs are new aggregates or existing aggregates.
- ¤JdbcTemplate.batchUpdate(...)¤ or ¤NamedParameterJdbcTemplate.batchUpdate(...)¤ sends multiple parameter sets for a single JDBC SQL statement.
- A set-based ¤UPDATE ... WHERE ...¤ or ¤INSERT ... SELECT ...¤ statement can outperform even batching when many rows share a single SQL rule.

Choosing among them depends on whether the data belongs to an aggregate, whether domain invariants/callbacks/versions are needed, whether the statement is identical across rows, and whether the application requires generated IDs or per-row results.

This lesson examines semantics, executed SQL, Java examples, transactions, batch sizes, update count results, and limits that must be measured on real databases and drivers.

## 1. Three Concepts That Are Not Synonymous

Suppose an application imports 2,000 items into the ¤inventory_items¤ table.

| Write approach | Unit of work | Who builds SQL? | Preserves aggregate mapping? |
|---|---|---|---|
| ¤repository.saveAll(items)¤ | Multiple aggregate roots | Spring Data JDBC | Yes |
| ¤JdbcAggregateTemplate.insertAll(items)¤ | Multiple new aggregates | Spring Data JDBC | Yes |
| ¤JdbcAggregateTemplate.updateAll(items)¤ | Multiple existing aggregates | Spring Data JDBC | Yes |
| JDBC batch insert | Multiple parameter sets for one INSERT | Application supplies SQL | Not automatically |
| JDBC batch update | Multiple parameter sets for one UPDATE | Application supplies SQL | Not automatically |
| Set-based UPDATE | One statement affecting many rows | Application supplies SQL | Not automatically |

A common source of confusion is the word "batch". ¤saveAll¤ supports collecting aggregate changes and grouping compatible actions for optimization, yet it still persists according to the aggregate model. Direct JDBC batching focuses on reusing one prepared statement with multiple parameter sets.

Both can cut round trips or execution overhead, but their mapping, callbacks, versioning, and SQL differ.

## 2. What Does Spring Data JDBC's saveAll Do?

Repository:

~~~java
@Table("inventory_items")
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private Long version;

    private String sku;
    private BigDecimal unitPrice;
    private Integer available;

    // Constructors, getters, and domain methods omitted.
}
~~~

~~~java
public interface InventoryItemRepository
        extends CrudRepository<InventoryItem, Long> {
}
~~~

Saving multiple aggregates:

~~~java
@Service
public class InventoryImportService {

    private final InventoryItemRepository repository;

    public InventoryImportService(InventoryItemRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void importItems(List<InventoryItem> items) {
        repository.saveAll(items);
    }
}
~~~

¤saveAll¤ persists all passed-in aggregates. For each aggregate, Spring Data JDBC determines whether the entity is new or existing via entity state detection, then picks insert or update.

In current implementations, ¤JdbcAggregateTemplate.saveAll¤ collects aggregate changes into a ¤SaveBatchingAggregateChange¤. Batchable operations are grouped to take an optimized execution path. That does not mean an entire aggregate graph turns into a single INSERT: an aggregate can span multiple tables, dependent relations, and multiple database action types.

### 2.1. saveAll Handles Both Inserts and Updates

For example, a list might contain:

- Item A without an ID, detected as new.
- Item B with a database-assigned ID, detected as existing.
- Item C with an application-assigned ID whose entity state still reports new under the configured detection strategy.

Spring Data JDBC chooses the action based on entity state, not solely on whether the ID property is null. When using assigned IDs, implement ¤Persistable.isNew()¤ or an appropriate entity state detection mechanism.

Do not treat ¤saveAll¤ as a "guaranteed insert" operation. To force inserts for all aggregates, use ¤insertAll¤ on ¤JdbcAggregateTemplate¤.

### 2.2. Aggregate Updates Can Emit More SQL Than Expected

Spring Data JDBC does not track dirty state like some ORMs. When updating an existing aggregate, the framework typically:

1. Deletes referenced entities in collections.
2. Updates the aggregate root.
3. Reinserts the referenced entities.

Thus, if only one child line changed in an aggregate with many children, saving can generate far more SQL than a simple UPDATE.

This is why ¤saveAll¤ fits when aggregate semantics are needed and sizes are reasonable, yet is not automatically the fastest choice for every bulk ingestion task.

### 2.3. saveAll Preserves Spring Data JDBC Responsibilities

When persisting through repositories/templates, Spring Data JDBC still performs aggregate mapping and corresponding lifecycle steps, including callbacks, auditing, and optimistic locking when configured.

If an aggregate has ¤@Version¤, the framework checks the version during updates. When versions mismatch, the operation can throw ¤OptimisticLockingFailureException¤.

This matters greatly for business updates. Do not rewrite an aggregate command into raw SQL batching solely because of volume while forgetting invariants and concurrency rules.

## 3. insertAll and updateAll via JdbcAggregateTemplate

Beyond ¤saveAll¤, Spring Data JDBC provides more explicit APIs through ¤JdbcAggregateTemplate¤ or ¤JdbcAggregateOperations¤.

~~~java
@Service
public class InventoryAggregateWriter {

    private final JdbcAggregateTemplate aggregateTemplate;

    public InventoryAggregateWriter(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    @Transactional
    public List<InventoryItem> insertNewItems(
            List<InventoryItem> newItems
    ) {
        return aggregateTemplate.insertAll(newItems);
    }

    @Transactional
    public List<InventoryItem> updateExistingItems(
            List<InventoryItem> existingItems
    ) {
        return aggregateTemplate.updateAll(existingItems);
    }
}
~~~

| API | Meaning | When to use |
|---|---|---|
| ¤saveAll¤ | Chooses insert/update by entity state | List may contain both new and existing entities |
| ¤insertAll¤ | Forces insert for all aggregates | Input is guaranteed to contain only new aggregates |
| ¤updateAll¤ | Forces update for all aggregates | Input is guaranteed to contain only existing aggregates |

¤insertAll¤ is useful when the application assigns IDs to new aggregates. ¤updateAll¤ is useful when callers already know all aggregates exist and want to skip new/existing detection.

This is still aggregate persistence, not a universal replacement for ¤JdbcTemplate.batchUpdate¤.

### 3.1. Do Not Use insertAll to "Try Insert If Missing"

If a row already exists, inserting can fail on primary key or unique constraints. ¤insertAll¤ does not automatically turn into an upsert.

If insert-or-update is needed, check whether the database dialect supports upsert and an appropriate API exists, such as ¤JdbcAggregateTemplate.upsert¤ for a single aggregate when the dialect supports single-statement upsert. For many rows, database-specific SQL may be required.

### 3.2. Versioning with updateAll

¤updateAll¤ still enforces optimistic locking when aggregates carry ¤@Version¤. An element with a stale version can fail the batch.

Do not manually increment the version on an object and call `updateAll` to bypass conflicts. Reload the fresh state and reapply the command according to business rules.

## 4. What Is a JDBC Batch Insert?

A JDBC batch insert executes the same INSERT statement multiple times with different parameter sets on a prepared statement.

Example table:

~~~sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    unit_price NUMERIC(15, 2) NOT NULL,
    available INTEGER NOT NULL
);
~~~

With ¤NamedParameterJdbcTemplate¤:

~~~java
@Repository
public class InventoryBatchDao {

    private final NamedParameterJdbcTemplate jdbc;

    public InventoryBatchDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int[] insertBatch(List<NewInventoryRow> rows) {
        String sql = """
            INSERT INTO inventory_items (
                sku,
                unit_price,
                available
            )
            VALUES (
                :sku,
                :unitPrice,
                :available
            )
            """;

        SqlParameterSource[] batch = rows.stream()
                .map(row -> new MapSqlParameterSource()
                        .addValue("sku", row.sku())
                        .addValue("unitPrice", row.unitPrice())
                        .addValue("available", row.available()))
                .toArray(SqlParameterSource[]::new);

        return jdbc.batchUpdate(sql, batch);
    }
}
~~~

Input DTO:

~~~java
public record NewInventoryRow(
        String sku,
        BigDecimal unitPrice,
        Integer available
) {
}
~~~

The application supplies one INSERT statement and multiple parameter sets. Spring JDBC binds each set into the prepared statement and executes the batch via the JDBC driver.

### 4.1. Batch Insert Is Not One Multi-VALUES INSERT Statement

A JDBC batch generally represents multiple executions of the same prepared statement. It does not necessarily rewrite into a single SQL statement of the form:

~~~sql
INSERT INTO inventory_items (sku, unit_price, available)
VALUES
    ('SKU-001', 10.00, 20),
    ('SKU-002', 15.00, 12),
    ('SKU-003', 25.00, 5);
~~~

Some drivers/databases can optimize batches into more efficient execution forms, depending on driver and configuration. Do not assume every JDBC batch becomes a multi-row INSERT.

### 4.2. Generated IDs During Batch Insert

The example above returns ¤int[]¤ affected row counts per element, not a list of ¤InventoryItem¤ with generated IDs.

If generated keys are needed:

- Check whether ¤JdbcTemplate.batchUpdate¤ has an overload accepting ¤KeyHolder¤ in your Spring Framework version.
- Check how your database and JDBC driver support returning generated keys for batches.
- Do not assume every driver returns all keys in the exact input order.
- If aggregate mapping, versioning, auditing, and lifecycle callbacks are needed, consider Spring Data JDBC ¤insertAll¤.

Generated-key behavior must be verified against the target database/driver, especially for multi-row batch inserts.

## 5. What Is a JDBC Batch Update?

A batch update runs the same UPDATE statement while varying parameter sets per row.

Example updating prices and stock counts by SKU:

~~~java
public int[] updateBatch(List<InventoryUpdateRow> rows) {
    String sql = """
        UPDATE inventory_items
        SET unit_price = :unitPrice,
            available = :available
        WHERE sku = :sku
        """;

    SqlParameterSource[] batch = rows.stream()
            .map(row -> new MapSqlParameterSource()
                    .addValue("sku", row.sku())
                    .addValue("unitPrice", row.unitPrice())
                    .addValue("available", row.available()))
            .toArray(SqlParameterSource[]::new);

    return jdbc.batchUpdate(sql, batch);
}
~~~

DTO:

~~~java
public record InventoryUpdateRow(
        String sku,
        BigDecimal unitPrice,
        Integer available
) {
}
~~~

Each element creates an UPDATE execution with its own values. This fits when each row receives different update values under the same SQL structure.

### 5.1. Batch Update vs. Set-Based Update

If all matching rows need the same change under a single condition, a set-based SQL statement can be simpler and faster.

For example, zeroing out all discontinued products:

~~~sql
UPDATE inventory_items
SET available = 0
WHERE discontinued = TRUE;
~~~

Comparison:

| Situation | Usually suitable choice |
|---|---|
| Each row has different new values | JDBC batch update |
| Many rows receive the same value by predicate | A single set-based UPDATE |
| Each aggregate has distinct domain rules | Repository/domain operation |
| Updating a few technical columns with deterministic SQL | JDBC batch or set-based SQL |

Set-based SQL avoids sending per-row parameter sets from the application and lets the database process the set in one statement. When invariants can be safely expressed in SQL, benchmark this option before choosing batch update.

## 6. Direct Batching with JdbcTemplate

When tighter control over JDBC parameter types is needed, use ¤BatchPreparedStatementSetter¤.

~~~java
@Repository
public class InventoryJdbcBatchDao {

    private final JdbcTemplate jdbcTemplate;

    public InventoryJdbcBatchDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int[] insertBatch(List<NewInventoryRow> rows) {
        String sql = """
            INSERT INTO inventory_items (
                sku,
                unit_price,
                available
            )
            VALUES (?, ?, ?)
            """;

        return jdbcTemplate.batchUpdate(
                sql,
                new BatchPreparedStatementSetter() {

                    @Override
                    public void setValues(
                            PreparedStatement ps,
                            int index
                    ) throws SQLException {
                        NewInventoryRow row = rows.get(index);

                        ps.setString(1, row.sku());
                        ps.setBigDecimal(2, row.unitPrice());
                        ps.setInt(3, row.available());
                    }

                    @Override
                    public int getBatchSize() {
                        return rows.size();
                    }
                }
        );
    }
}
~~~

¤BatchPreparedStatementSetter¤ has two responsibilities:

- ¤getBatchSize()¤ tells Spring how many parameter sets are in the batch.
- ¤setValues(...)¤ binds parameters for the execution at the given index.

This is useful when explicit JDBC types are needed or `NULL` values require specific SQL types.

With named parameters, ¤NamedParameterJdbcTemplate¤ is generally easier to read when SQL touches many columns.

## 7. Interpreting Batch Update Counts Correctly

Batch APIs usually return ¤int[]¤, with each entry corresponding to a command in the batch.

Example:

~~~text
[1, 1, 0, 1]
~~~

Interpretation:

- ¤1¤: one row affected.
- ¤0¤: no rows matched the predicate.
- ¤Statement.SUCCESS_NO_INFO¤ (¤-2¤): driver reports command succeeded without providing an exact row count.
- ¤Statement.EXECUTE_FAILED¤ (¤-3¤): the corresponding batch item failed in results reported by the driver.

Do not assume every element can only be 0 or 1. JDBC drivers can return special values per the JDBC contract.

If the application must know for sure whether every single row updated, check driver capabilities. With ¤SUCCESS_NO_INFO¤, exact affected row counts cannot be inferred.

### 7.1. Batch Updates Can Mask Optimistic Locking Conflicts

Suppose each update has a version predicate:

~~~sql
UPDATE inventory_items
SET available = :available,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

If an element returns 0, either the ID does not exist or the version no longer matches. If the driver returns ¤SUCCESS_NO_INFO¤, the application knows the statement succeeded according to the driver, without knowing the exact row count.

If per-aggregate conflict feedback is needed, design appropriate results and checks; do not rely on an assumption that update counts are always exact.

## 8. Batch Size and Chunking

Do not dump all data into a single batch by default. Oversized batches can:

- Consume memory holding parameter objects.
- Create long transactions.
- Hold locks too long.
- Inflate log/WAL volume and replication pressure.
- Exceed database bind-parameter or packet-size limits.
- Cause a small error to affect a massive data slice.

Split data into chunks:

~~~java
public void insertInChunks(List<NewInventoryRow> rows, int batchSize) {
    for (int start = 0; start < rows.size(); start += batchSize) {
        int end = Math.min(start + batchSize, rows.size());

        List<NewInventoryRow> chunk = rows.subList(start, end);
        insertBatch(chunk);
    }
}
~~~

Appropriate batch size depends on:

- Size of each row and number of bind parameters.
- JDBC driver and database.
- Network latency.
- Connection pool capacity.
- Concurrent workload.
- Acceptable lock and log duration.

Measure on production-like data rather than picking a fixed constant from the snippet above.

### 8.1. One Transaction for All vs. Per-Chunk Transactions

Two distinct strategies exist:

| Strategy | Pros | Trade-offs |
|---|---|---|
| One transaction wrapping entire batch | All succeed or roll back together | Long transaction, heavy locks/logs, costly rollback |
| One transaction per chunk | Can resume and bound resources | Can commit partial data |

If all-or-nothing is required, wrap the entire operation in a single appropriate transaction and measure real duration.

For very large imports, you can commit per chunk, provided you add checkpoints, idempotency, and restartability. The overall job is then no longer one atomic transaction.

## 9. Using @Transactional with JDBC Batching

Spring JDBC templates participate in Spring transactions when sharing the same ¤DataSource¤ and transaction manager.

Example:

~~~java
@Service
public class InventoryBatchService {

    private final InventoryBatchDao dao;

    public InventoryBatchService(InventoryBatchDao dao) {
        this.dao = dao;
    }

    @Transactional
    public void updatePrices(List<InventoryUpdateRow> rows) {
        dao.updateBatch(rows);
        // Additional operations can run in the same transaction.
    }
}
~~~

When multiple write operations must commit or roll back together, place transaction boundaries on the application service. Never open raw connections via ¤DriverManager.getConnection(...)¤ inside a method already participating in a Spring transaction.

For per-chunk commit strategies, design separate transaction boundaries for each chunk. Do not keep an outer transaction wrapping all chunks if the goal is partial commits.

### 9.1. Batching Does Not Automatically Guarantee Atomic Commit

¤batchUpdate¤ is a mechanism for sending multiple commands over JDBC. Atomicity depends on transactions and the database.

When running outside a transaction under autocommit, the driver/database may commit each execution on its own terms. When all statements must succeed together, use an explicit transaction and test rollback against a real database.

## 10. Does Direct Batch Insert Preserve Aggregate Invariants?

Not automatically.

For example, a ¤PurchaseOrder¤ aggregate has invariants:

- Only draft orders can add lines.
- Total quantity cannot exceed limits.
- Order pricing is finalized according to business rules.
- Each SKU appears at most once per order.

A JDBC batch INSERT into ¤order_lines¤ only enforces constraints declared in the database. It does not invoke ¤purchaseOrder.addLine(...)¤.

If records belong to the same aggregate, perform domain validation before writing. When aggregate state transitions are required, repositories/templates are normally the right write path.

Direct batch SQL should be reserved for use cases with well-defined boundaries and invariants, such as importing pre-validated data, technical synchronization, or updating a read model.

## 11. Auditing, Callbacks, and Generated Values

Spring Data JDBC repositories/templates apply entity lifecycle callbacks, auditing, and mapping according to configuration.

Direct JDBC batching does not automatically traverse the aggregate lifecycle. Thus, fields such as:

- ¤createdBy¤.
- ¤createdAt¤.
- ¤modifiedBy¤.
- ¤modifiedAt¤.
- ¤version¤.

must be handled explicitly when direct SQL needs to update them.

Similarly, converters for enums, custom types, embedded objects, and aggregate children do not run automatically when you write raw SQL and bind parameters manually.

When relying on database defaults or triggers, clearly define which fields are database-generated and how the application reads those values back.

## 12. Optimistic Locking in Direct Batch Updates

When batch-updating aggregate roots with ¤@Version¤, SQL must check the old version and increment the new version within the same statement.

Example:

~~~sql
UPDATE inventory_items
SET available = :available,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Each parameter set must supply the previously read ¤expectedVersion¤.

However, direct batch updates protect only that SQL statement. They do not invoke domain methods, verify other invariants, or update child tables per aggregate mapping.

If an aggregate spans multiple tables, define how locking/versioning and transactions cover all related statements.

## 13. Error Handling and Retries

Batches can fail due to:

- Unique constraints or foreign keys.
- Invalid data.
- Deadlocks or lock timeouts.
- Network failures.
- Driver incompatibility with a batch/generated-key mode.
- A parameter set with an incompatible data type.

Do not blindly retry an entire batch without knowing which statements the database already executed or whether the transaction committed.

Appropriate strategies:

1. With all-or-nothing transactions, let errors trigger rollback and verify transaction status.
2. With per-chunk commits, persist a checkpoint for committed chunks.
3. Make operations safely re-runnable via unique keys or idempotency keys.
4. Separate transient errors from data errors.
5. Never retry constraint violations as if they were network glitches.
6. Record business IDs/keys of failing rows for targeted reprocessing.

On deadlocks, the database may roll back the transaction. Retries must re-run the entire transaction with fresh data and consistent lock ordering rather than continuing mid-way inside a rolled-back transaction.

## 14. Choosing Between saveAll and JDBC Batch

Comparison table:

| Criterion | Spring Data JDBC saveAll | Direct JDBC batch |
|---|---|---|
| Data model | Aggregate | Rows/tables |
| New/existing detection | Yes | Application decides |
| Aggregate mapping | Yes | Hand-written SQL |
| Child entities | Framework handles per mapping | Manually written in dependency order |
| Domain invariants | Can be invoked via domain methods before save | Application must enforce |
| Lifecycle callbacks/auditing | Yes per configuration | Do not run automatically |
| Optimistic locking | Handled via `@Version` | Must write version predicates |
| SQL control | Framework generates SQL | Application controls SQL |
| Batch SQL | Spring Data groups batchable actions | Explicit JDBC batching for a statement |
| Generated IDs | Handled by mapping/framework strategy | Depends on driver/API and key retrieval |
| Typical use case | Saving business aggregates | Imports/ETL/bulk updates with fixed SQL |

A middle-ground option is ¤JdbcAggregateTemplate.insertAll/updateAll¤: it preserves aggregate mapping and states explicit insert/update intent while using Spring Data JDBC's batch-aware API.

## 15. Measuring Performance Properly

Do not conclude JDBC batching is faster merely because it involves fewer abstractions. Measure:

- Round trips to the database.
- Actual SQL statement counts.
- Bind and execute time.
- Batch size.
- Transaction duration.
- Lock waits and deadlocks.
- Database CPU, I/O, and WAL.
- Connection pool utilization.
- Application memory usage.
- Generated key retrieval.
- Aggregate child row volume.

Benchmarks should compare identical datasets, schemas, indexes, and transaction policies.

Example three-way comparison:

1. Calling ¤repository.save¤ in a loop.
2. Calling ¤repository.saveAll¤.
3. Using ¤NamedParameterJdbcTemplate.batchUpdate¤.

Measure new inserts and existing aggregate updates separately. Do not mix the two cases, because updating existing aggregates in Spring Data JDBC can delete and reinsert referenced entities.

## 16. Testing Batches

Tests should cover:

| Scenario | What to verify |
|---|---|
| Empty list | No unexpected SQL emitted |
| Valid batch insert | Exact row count and data |
| Unique key collision | Error classified and transaction handled properly |
| An update matches no row | Corresponding update count interpreted properly |
| Driver returns `SUCCESS_NO_INFO` | Code does not assume count is always 1 |
| Version mismatch | Conflict detected per design |
| Chunk failure | Rollback or partial commit matches policy |
| Chunk retry | No duplicate data created |
| Generated keys | Keys retrieved accurately for the driver/database |
| Aggregates with children | Insert/update order and FKs are valid |
| Callbacks/auditing | Run for repositories/templates; not assumed for direct SQL |

Use a database engine and JDBC driver close to production. H2 can differ from PostgreSQL, MySQL, or SQL Server in batching, generated keys, DDL, and update counts.

## 17. Common Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Assuming `saveAll` is always a single INSERT | Misjudging SQL and aggregate persistence cost | Treat it as batch-aware aggregate save |
| Calling `saveAll` on millions of aggregates at once | Huge memory retention and giant transactions | Chunk with explicit transaction policies |
| Using `insertAll` on data that may already exist | Primary key/unique constraint failures | Determine new/existing or use intentional upsert |
| Using `updateAll` on new entities | UPDATE matches no root | Use only with existing aggregates |
| Calling `save` in a loop without measuring | Separate executions and extra round trips | Benchmark `saveAll`/template batching |
| Thinking `batchUpdate` is only for UPDATE | Missing batch INSERT/DELETE capabilities | Use the same API with appropriate SQL |
| Assuming batch is always one SQL statement | Misreading driver behavior | Inspect actual SQL/driver behavior |
| Ignoring special update counts | Misclassifying outcomes | Handle `SUCCESS_NO_INFO`/`EXECUTE_FAILED` |
| Batch SQL skipping version/audit fields | Out-of-sync metadata | Update metadata/versions explicitly |
| One massive transaction | Costly locks, logs, and rollbacks | Choose chunking and checkpoints |
| Retrying non-idempotent batches | Duplicate writes or repeated updates | Use unique/idempotency keys and checkpoints |
| Batching children before parents | FK violations | Respect dependency order |

## 18. Selection and Implementation Workflow

When writing many records, follow these steps:

**Step 1 — Identify the data unit.** Is this an aggregate or flat technical rows?

**Step 2 — Identify the operation type.** Are inputs new entities, existing entities, or mixed?

**Step 3 — Check invariants.** Are there domain methods, child mappings, auditing, or versions to preserve?

**Step 4 — Pick the API.** Use `saveAll` for mixed aggregates; `insertAll`/`updateAll` when state is known; JDBC batching when direct SQL is needed.

**Step 5 — Determine generated values.** Are generated IDs, defaults, triggers, or callbacks required?

**Step 6 — Design the SQL.** Does one statement fit all rows? Would a set-based statement be even better?

**Step 7 — Choose batch size.** Start with moderate chunks and benchmark on the target driver/database.

**Step 8 — Choose transaction policy.** All-or-nothing or per-chunk commits?

**Step 9 — Handle results.** Check update counts, constraint errors, version conflicts, and generated keys.

**Step 10 — Measure and observe.** Compare latency, round trips, locks, logs, memory, and recoverability.

~~~text
Need to write many records
        |
        v
Data belongs to aggregates?
      /          \
    Yes            No
    |               |
    v               v
Mixed new/old?   Identical SQL structure?
  /      \          /       \
Yes       No      Yes        No
|           |      |           |
v           v      v           v
saveAll   insertAll / updateAll  JDBC batch  Split use cases
           via JdbcAggregateTemplate
        |
        v
Same value for many rows?
        |
       Yes
        |
        v
Consider set-based SQL
        |
        v
Choose transaction + chunk size
        |
        v
Test driver/database and measure performance
~~~

## 19. Self-Check Scenarios

**Scenario A — List contains both new and existing items**

A list has 10 new aggregates and 5 existing aggregates. Which API should you start with?

**Hint:** ¤saveAll¤ if entity state detection is configured correctly. Spring Data JDBC selects insert or update per aggregate state.

**Scenario B — All are new aggregates with application-assigned IDs**

Should you use ¤saveAll¤?

**Hint:** You can, if entity state detection identifies them accurately. If the caller wants to force inserts explicitly, ¤JdbcAggregateTemplate.insertAll¤ fits better.

**Scenario C — Updating 5,000 different prices**

Each SKU gets a different new price, but the SQL structure is identical. What should you use?

**Hint:** JDBC batch update is a strong candidate. Each parameter set provides a SKU and its corresponding price.

**Scenario D — Setting available = 0 across matching rows**

All products with the `discontinued` flag need `available` set to 0. Should you send 10,000 parameter sets?

**Hint:** You can use a single set-based UPDATE with a `discontinued` predicate if invariants allow.

**Scenario E — Needing generated IDs**

A direct batch INSERT succeeds, yet the application needs each row's generated ID. Can you assume the driver returns all keys in input order?

**Hint:** No. Verify API, database, and driver behavior. If aggregate mapping is needed, consider Spring Data JDBC `insertAll`.

**Scenario F — Version conflict in a batch**

A batch update includes `WHERE version = expectedVersion`, yet the driver returns `SUCCESS_NO_INFO`. Can you conclude every aggregate updated exactly one row?

**Hint:** No. The driver only reports command success without exact row counts. Use another verification/reconciliation mechanism if per-item conflict detection is required.

## 20. Key Takeaways

| Component | Responsibility |
|---|---|
| ¤CrudRepository.saveAll¤ | Persists aggregate lists, choosing insert/update by entity state |
| ¤JdbcAggregateTemplate.insertAll¤ | Inserts multiple new aggregates |
| ¤JdbcAggregateTemplate.updateAll¤ | Updates multiple existing aggregates |
| ¤SaveBatchingAggregateChange¤ | Collects aggregate changes and groups batchable actions |
| ¤JdbcTemplate.batchUpdate¤ | JDBC batching with prepared statements and positional parameters |
| ¤NamedParameterJdbcTemplate.batchUpdate¤ | JDBC batching with named parameters |
| ¤BatchPreparedStatementSetter¤ | Supplies parameters for each batch element |
| ¤int[] update counts¤ | Per-command results, potentially containing JDBC special constants |
| Set-based SQL | One statement affecting many rows by predicate |
| ¤@Transactional¤ | Protects atomicity according to transaction policy |
| Batch size | Balances round trips, memory, locks, and logs |
| ¤@Version¤ | Optimistic locking for aggregates; direct SQL must coordinate explicitly |

**saveAll, aggregate insert/update, and JDBC batching solve different problems.** Use ¤saveAll¤ when saving multiple aggregates while preserving Spring Data JDBC mapping and lifecycle; use ¤insertAll¤ or ¤updateAll¤ when input state is known upfront; use JDBC batching when repeating the same SQL statement with multiple parameter sets; and prefer set-based SQL when a single predicate can update the entire set. Always account for generated IDs, versioning, auditing, update counts, transactions, and batch sizes on the real driver and database.

## References

- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): aggregate save semantics, root updates, and referenced entity handling.
- [Spring Data Relational — JdbcAggregateOperations Javadoc](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html): `saveAll`, `insertAll`, `updateAll`, and `upsert`.
- [Spring Data Relational — JdbcAggregateTemplate Javadoc](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html): aggregate persistence API.
- [Spring Data Relational — SaveBatchingAggregateChange Javadoc](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/conversion/SaveBatchingAggregateChange.html): grouping batchable aggregate actions for optimization.
- [Spring Framework — JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html): batching with `JdbcTemplate` and `NamedParameterJdbcTemplate`.
- [Spring Framework — JdbcOperations Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html): `batchUpdate`, update counts, and fallback when drivers do not support batching.
