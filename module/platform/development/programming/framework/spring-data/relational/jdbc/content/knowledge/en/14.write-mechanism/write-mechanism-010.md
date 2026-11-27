# Distinguishing saveAll from JDBC Batch and Evaluating Write Costs in Spring Data JDBC

## 1. Two ways to write many records, two different goals

When saving multiple records, Spring Data JDBC provides §saveAll(...)§ on repositories. Spring JDBC provides batch APIs such as §JdbcTemplate.batchUpdate(...)§. Both can write multiple rows, yet they solve two different problems.

- **§saveAll(entities)§** persists multiple entities/aggregate roots according to Spring Data JDBC's mapping model and lifecycle.
- **JDBC batch** groups multiple executions of the same parameterized SQL statement into a JDBC batch, giving the driver/database an opportunity to reduce the overhead of sending and executing many statements.

A call to §saveAll§ **is not a guarantee of JDBC batching**. A repository may need to execute multiple statements per aggregate, such as writing the root, writing child collections, updating version, or handling relational data. Conversely, JDBC batch only executes SQL supplied by the application; it does not understand aggregates, does not automatically apply entity mappings, and does not run the full repository lifecycle.

Choose the tool according to your requirements:

- Need to save aggregates with domain models, mappings, generated IDs, versioning, and lifecycles: prefer repository §save§ / §saveAll§.
- Need to write bulk tabular data with simple, uniform SQL and explicit batch control: consider §JdbcTemplate.batchUpdate§.
- Need very high throughput: database-native bulk load/import mechanisms may be required after evaluating constraints, transactions, and recoverability.

## 2. What does saveAll do?

On §CrudRepository§, the common signature is:

~~~java
<S extends T> Iterable<S> saveAll(Iterable<S> entities);
~~~

The method accepts a collection of entities and returns the saved entities. If the repository extends §ListCrudRepository§, the corresponding return type can be §List<S>§.

Example:

~~~java
List<Book> input = List.of(
        new Book(null, "Book A", new BigDecimal("100000")),
        new Book(null, "Book B", new BigDecimal("120000")),
        new Book(null, "Book C", new BigDecimal("150000"))
);

Iterable<Book> saved = bookRepository.saveAll(input);

for (Book book : saved) {
    log.info("Saved id={}", book.id());
}
~~~

The returned result matters because entities may receive database-generated IDs, new versions, or new instances if designed as immutable. Always use the entities in the return value when continuing processing.

### 2.1. saveAll promises neither a single statement nor a batch

The method name simply expresses a repository operation over multiple entities. It does not promise that:

- All rows are written with a single §INSERT ... VALUES (...), (...), ...§ statement.
- The driver receives only a single §executeBatch()§ call.
- All aggregates are written in a single round trip.
- Each entity takes only one statement.
- Every entity type produces the same number of SQL statements.

An aggregate can consist of a root and multiple child components. Saving aggregates may require multiple SQL operations to preserve relationships and lifecycles. Thus, statement count can exceed the number of input aggregates.

Internal repository implementation details can vary across Spring Data versions. If performance depends on a specific detail, inspect the implementation/version in use and measure actual SQL. **Do not infer JDBC batching merely because code makes a single call to §saveAll§.**

### 2.2. saveAll still provides domain-layer value

When using a repository, Spring Data JDBC handles mapping-driven tasks:

- Detecting whether an entity is new or existing via ID/version or new-state detection mechanisms.
- Executing the appropriate INSERT or UPDATE.
- Retrieving generated keys per database/dialect/driver support.
- Applying optimistic locking if the entity uses §@Version§.
- Converting Java/SQL types via mappings and custom conversions.
- Saving the aggregate root together with child components per declared relationships.
- Invoking corresponding lifecycle callbacks.

This is why §saveAll§ fits when the data consists of application aggregates. Switching to plain JDBC batch shifts responsibility for mappings and all these rules onto application code.

## 3. How does JDBC batch work?

JDBC batch is a mechanism for accumulating multiple parameter bindings for the same SQL statement and submitting the batch to the JDBC driver for execution. Conceptual flow:

~~~mermaid
flowchart TD
    A["Input data list"] --> B["Prepare one SQL statement"]
    B --> C["Bind parameters for element 1"]
    C --> D["addBatch()"]
    D --> E["Bind parameters for element 2"]
    E --> F["addBatch()"]
    F --> G["... up to batch size"]
    G --> H["executeBatch()"]
    H --> I["JDBC driver"]
    I --> J["Database executes batch"]
    J --> K["Update counts / errors"]
~~~

Plain JDBC example:

~~~java
String sql = """
        INSERT INTO audit_events (event_type, message)
        VALUES (?, ?)
        """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    for (AuditEvent event : events) {
        statement.setString(1, event.type());
        statement.setString(2, event.message());
        statement.addBatch();
    }

    int[] counts = statement.executeBatch();
}
~~~

The application binds multiple parameter sets to one §PreparedStatement§. §addBatch()§ queues a parameter set into the batch; §executeBatch()§ asks the driver to execute the accumulated items.

In Spring code, §JdbcTemplate.batchUpdate(...)§ reduces connection and statement management boilerplate:

~~~java
int[] counts = jdbcTemplate.batchUpdate(
        "INSERT INTO audit_events (event_type, message) VALUES (?, ?)",
        events,
        500,
        (ps, event) -> {
            ps.setString(1, event.type());
            ps.setString(2, event.message());
        }
);
~~~

The §500§ argument is the batch size the API uses to chunk execution. An appropriate size depends on the driver, database, payload size, transaction duration, and parameter limits.

### 3.1. Batch is not synonymous with a multi-row SQL statement

Three concepts are easily confused:

| Mechanism | Meaning |
|---|---|
| JDBC batch | Multiple parameter sets for a statement, executed via batch APIs |
| Multi-row INSERT | A single SQL statement containing multiple §VALUES§ tuples |
| Bulk load/import | Database-specific mechanism for loading large volumes of data |

Drivers may optimize batches, combine statements, or transmit them in driver-specific ways. For instance, some drivers offer options to rewrite batched INSERTs into multi-row INSERTs. That depends on the driver, configuration, and SQL statement. The JDBC API does not guarantee one single physical transmission format.

### 3.2. Update counts and batch errors

§executeBatch()§ returns an array of update counts. Values can be:

- Number of affected rows.
- §Statement.SUCCESS_NO_INFO§: statement succeeded, but the driver did not report an exact row count.
- §Statement.EXECUTE_FAILED§: batch element failed in certain error-reporting modes.

Drivers may also throw §BatchUpdateException§; the exception contains update counts for items executed before the failure was reported. Do not assume all drivers report partial results identically or automatically continue after errors.

When handling batch failures, understand the database and driver in use, whether the transaction rolled back, and which elements require retry. Never blindly retry an entire batch if part of the data already committed or the operation is not idempotent.

## 4. Comparing saveAll and JDBC batch

| Criterion | Spring Data JDBC §saveAll§ | JDBC batch / §JdbcTemplate.batchUpdate§ |
|---|---|---|
| Operation unit | Entity/aggregate root | Parameterized SQL executions |
| Entity mapping | Includes metadata and converters | Application binds and maps manually |
| Aggregate relationships | Managed per Spring Data JDBC mappings | Application writes root/child manually |
| Generated ID | Repository handles per dialect/driver | Must handle manually; batch generated keys vary by driver/API |
| Optimistic locking | Can apply with §@Version§ | Manually write version predicates and check update counts |
| Lifecycle callbacks | Follows Spring Data mechanisms | Repository callbacks do not run automatically |
| SQL | Framework generates from mappings or queries | Application writes explicit SQL |
| Batch execution | Not guaranteed by the API | Direct goal of batch APIs |
| Transactions | Repository transaction semantics; extendable at service | Needs appropriate transaction if atomicity is desired |
| Result | Saved entities | Update counts or batch results |
| Best suited for | Aggregate CRUD, domain persistence | Simple, uniform bulk SQL writes |

Neither choice is universally faster. For an aggregate spanning multiple tables and callbacks, §saveAll§ provides the right domain semantics. For millions of simple log rows, §JdbcTemplate.batchUpdate§ or native bulk import can significantly reduce overhead.

## 5. What makes up write cost?

Evaluating performance is not just counting Java method calls. Overall write cost can include:

1. **Network round trips:** how many times the application/driver communicates with the database.
2. **SQL parsing/planning:** database parsing and execution plan generation.
3. **Statement preparation:** creating and preparing statements.
4. **Parameter binding/conversion:** converting Java values to JDBC/SQL types.
5. **Index maintenance:** updating indexes on INSERT/UPDATE/DELETE.
6. **Constraint checks:** verifying primary keys, unique constraints, foreign keys, check constraints.
7. **Transaction log/WAL:** writing logs for durability and recovery.
8. **Locking/concurrency:** lock waits, conflicts, and resource contention.
9. **Object mapping:** instantiating entities, collections, converters, and callbacks.
10. **Memory/GC:** retaining inputs, results, statement state, and object graphs.
11. **Commit/flush:** synchronizing data and finalizing transactions.

Conceptual cost diagram:

~~~mermaid
flowchart TD
    A["Application"] --> B["Object mapping / conversion"]
    B --> C["JDBC statement preparation"]
    C --> D["Network / driver"]
    D --> E["Database execution"]
    E --> F["Index + constraints"]
    E --> G["Locks + transaction log"]
    F --> H["Commit"]
    G --> H
    H --> I["Return result"]
~~~

JDBC batch typically reduces repetitive overhead in the driver, network, and statement execution layers. It does not eliminate costs from indexes, constraints, WAL, locks, or commits. If the database must update many indexes or write heavy logs, batching cannot remove that portion of cost.

## 6. Estimating round trips and batch size impact

Suppose §N§ records must be written using the same SQL statement. Sending each record individually yields a statement submission count close to §N§. Using batch size §B§, the approximate number of batch groups is:

\[
\text{batchCount} = \left\lceil \frac{N}{B} \right\rceil
\]

For example, with §N = 10,000§ and §B = 500§, there are 20 batch groups. This is the number of batch calls at the application layer, **not a guarantee that the database receives exactly 20 network round trips**. Drivers may split, merge, or handle batches according to their wire protocol.

### 6.1. Illustrative batch group counts

| Record count N | Batch size B | Theoretical groups |
|---:|---:|---:|
| 1,000 | 100 | 10 |
| 1,000 | 250 | 4 |
| 10,000 | 500 | 20 |
| 10,000 | 1,000 | 10 |
| 100,000 | 1,000 | 100 |

Increasing batch size reduces group count, yet does not guarantee higher throughput. Excessively large batches can:

- Increase memory usage in the application and driver.
- Increase lock hold duration.
- Prolong transactions and rollback time.
- Make batch failures harder to pinpoint and recover from.
- Hit parameter, packet, or buffer limits of the driver/database.
- Increase latency of a chunk and impact concurrent requests.

### 6.2. No single batch size is optimal for every system

A practical process is to test small, medium, and large sizes (for example 100, 500, 1,000), measure against the real database and realistic data, and choose a balance among throughput, latency, memory, and recoverability.

These numbers are starting points for benchmarking, not recommended defaults for every database. Account for row size, column count, indexes, constraints, payload size, and concurrency.

## 7. Why can saveAll emit more SQL than JDBC batch?

Suppose each §Book§ is a simple single row; saving it can be fairly compact. However, a §PurchaseOrder§ with many §OrderLine§ items requires writing to multiple tables per aggregate.

Example:

~~~text
purchase_orders
    id
    ordered_on

order_lines
    order_id
    line_number
    product_code
    quantity
~~~

When saving multiple aggregates, Spring Data JDBC must preserve root-child relationships and aggregate rules. Depending on the operation and version, writing can emit statements for both root and children. A call to §saveAll(orders)§ therefore cannot be evaluated as a simple single-table batch INSERT.

Plain JDBC batch can write the §order_lines§ table very fast, yet the application must manually:

- Obtain or generate root IDs.
- Attach the right §order_id§ to each child.
- Ensure collection keys do not collide.
- Maintain write ordering compatible with foreign keys.
- Manage transactions across root and child writes.
- Handle mid-batch errors and data recovery.
- Maintain optimistic locking/lifecycle rules if required by the domain.

Hand-writing batches for speed while omitting aggregate invariants can make data faster yet business-incorrect.

## 8. When should you use saveAll?

Use §saveAll§ when:

- The input is a set of Spring Data JDBC aggregate roots.
- Mapping annotations like §@Id§, §@Column§, and §@MappedCollection§ are needed.
- Repository-managed generated IDs or versions are needed.
- Spring Data conversions and lifecycle callbacks are required.
- Aggregate rules for saving/deleting children must be preserved.
- Data volume is moderate and current throughput meets requirements.
- Maintainable code aligned with domain models and repositories is preferred.

Example:

~~~java
@Transactional
public List<Book> registerBooks(List<Book> input) {
    Iterable<Book> saved = bookRepository.saveAll(input);

    List<Book> result = new ArrayList<>();
    saved.forEach(result::add);
    return result;
}
~~~

Use the returned results to access IDs and versions. A service-level transaction clearly expresses the business scope, especially when the use case includes additional operations beyond one repository method.

## 9. When should you use JDBC batch?

JDBC batch fits when:

- Writing many rows sharing the same SQL structure.
- Data is simple tabular records without complex aggregate mapping.
- The application wants direct control over SQL and parameter binding.
- High throughput is needed for imports, audit logs, events, or staging tables.
- The application can manage IDs, foreign keys, constraints, and transactions directly.
- Benchmarks prove batching resolves a measured bottleneck.

Batch INSERT example:

~~~java
@Repository
public class AuditEventBatchDao {

    private final JdbcTemplate jdbc;

    public AuditEventBatchDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int[] insertBatch(List<AuditEvent> events) {
        String sql = """
                INSERT INTO audit_events (event_type, message, created_at)
                VALUES (?, ?, ?)
                """;

        return jdbc.batchUpdate(
                sql,
                events,
                500,
                (ps, event) -> {
                    ps.setString(1, event.type());
                    ps.setString(2, event.message());
                    ps.setTimestamp(3, Timestamp.from(event.createdAt()));
                }
        );
    }
}
~~~

The code explicitly controls columns and bind types. §AuditEvent§ is not automatically mapped through Spring Data JDBC entity metadata; that is intentional in a plain SQL DAO.

### 9.1. Writing multiple SQL shapes

Batching is typically most effective when many items share the exact same statement shape. If every item requires a different SQL statement, batching benefits shrink or do not apply cleanly.

If multiple dependent tables must be written, split into ordered per-table batches:

1. Batch INSERT parent table and obtain/prepare keys.
2. Batch INSERT child table with foreign keys.
3. Commit in an appropriate transaction.

However, retrieving generated keys from batches varies by driver and API. For linking IDs, you can generate IDs in the application upfront (e.g., UUIDs), or use a key-retrieval strategy verified on your driver/database. Never assume §batchUpdate§ always returns a generated key for every element.

## 10. Transactions and atomicity in batches

Batch execution and transactions are two distinct mechanisms:

- **Batch** controls how multiple statements are sent/executed.
- **Transaction** defines commit/rollback boundaries.

JDBC batches can execute within a transaction:

~~~java
@Service
public class AuditImportService {

    private final AuditEventBatchDao dao;

    public AuditImportService(AuditEventBatchDao dao) {
        this.dao = dao;
    }

    @Transactional
    public void importEvents(List<AuditEvent> events) {
        dao.insertBatch(events);
        // Additional operations can run in the same transaction.
    }
}
~~~

If the transaction manager manages the same §DataSource§, JDBC statements executed through §JdbcTemplate§ participate in the current transaction.

Do not assume batches are always atomic. Behavior on error depends on the database, driver, transaction manager, and error handling. If the transaction rolls back properly on a transactional database, changes within the transaction can roll back. Without a shared transaction, part of the batch may have already committed or require reconciliation.

By default Spring rolls back on §RuntimeException§ and §Error§; checked exceptions normally require configuring §rollbackFor§ to trigger rollback. Let persistence exceptions exit the transaction boundary when rollback is required; catching and swallowing errors can cause the transaction to commit or be marked rollback-only depending on the situation.

## 11. Chunking and transaction boundaries

For large imports, processing the entire input in one giant transaction is not always desirable. You can chunk work to control memory and execution time:

~~~java
public void importInChunks(List<AuditEvent> events) {
    int chunkSize = 500;

    for (int start = 0; start < events.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, events.size());
        List<AuditEvent> chunk = events.subList(start, end);

        auditEventBatchDao.insertBatch(chunk);
    }
}
~~~

The snippet above does not automatically create a separate transaction per chunk. Transaction boundaries depend on where §@Transactional§ is placed and how calls pass through Spring proxies.

Two common strategies:

| Strategy | Characteristics |
|---|---|
| One transaction for the entire import | Business-wide atomicity if database/transaction supports it; locks and rollback cost can be large |
| One transaction per chunk | Reduces lock duration and rollback scope; earlier chunks may have committed when a later chunk fails |

If each chunk must commit independently, place transaction logic on a proxy-invoked method or use appropriate transaction propagation. That changes semantics: earlier chunks can remain committed even if a later chunk fails.

For multi-million-row imports, add resumability, idempotency, checkpointing, and row-count reconciliation. Chunking alone solves only part of operational cost.

## 12. Evaluating write costs through benchmarking

Do not choose between §saveAll§ and JDBC batch by intuition. Benchmark under conditions close to production.

### 12.1. Metrics to measure

| Metric | Meaning |
|---|---|
| Rows/second | Write throughput |
| Total duration | Time to finish the entire workload |
| p50/p95/p99 latency | Latency of a chunk or single invocation |
| SQL statement count | Actual statement count |
| Batch count / batch size | Number of batches and size per batch |
| DB CPU / IO | Processing cost on the database |
| Lock wait / deadlock | Contention during concurrent writes |
| WAL/transaction log volume | Amount of log generated |
| Heap / allocation / GC | Memory and object mapping overhead |
| Error rate / rollback rate | Stability under invalid data or high load |

### 12.2. Designing a fair benchmark

When comparing, hold variables constant:

- Same database, schema, indexes, and constraints.
- Same dataset and data types.
- Same record count and concurrency.
- Same transaction boundaries and durability settings.
- Same network environment and connection pool.
- Warm up JVM and connection pool before measuring.
- Run multiple iterations and report median and percentiles rather than just the fastest run.

Above all, compare with equal semantics. If §saveAll§ persists an aggregate with root and children while JDBC batch only INSERTs into one table, their throughput numbers do not represent equivalent work.

### 12.3. Throughput calculation example

Suppose a benchmark writes 50,000 rows in 25 seconds:

\[
\text{throughput} = \frac{50,000}{25} = 2,000 \text{ rows/second}
\]

If another approach writes the same data in 10 seconds:

\[
\text{throughput} = \frac{50,000}{10} = 5,000 \text{ rows/second}
\]

Throughput increase:

\[
\frac{5,000 - 2,000}{2,000} \times 100\% = 150\%
\]

Numbers are meaningful only when both runs perform the exact same work, durability guarantees, and consistency checks. You cannot claim JDBC batch is 150% better if one option skipped constraints, callbacks, or child tables that the other had to process.

## 13. Other optimizations beyond batching

Batching is not the only lever to lower write costs. Other factors can have a major impact:

### 13.1. Minimize unnecessary indexes

Every INSERT/UPDATE may have to update multiple indexes. Indexes accelerate reads yet add write overhead and storage cost. Keep only indexes serving real queries or constraints.

### 13.2. Check constraints and foreign keys

Constraints protect data and are usually essential. However, large imports must ensure valid write ordering and valid reference data. Never disable constraints in production just for speed unless a verified validation and recovery workflow is in place.

### 13.3. Size the connection pool appropriately

Too many concurrent connections can overload the database. Large batches under high concurrency can worsen lock contention instead of raising throughput. Pool size should match database capacity and workload.

### 13.4. Reduce unnecessary payload and mapping

Write only needed columns. With aggregate repositories, design reasonably sized aggregates to avoid loading/saving oversized object graphs. With JDBC batch, bind proper types and avoid unnecessary intermediate objects.

### 13.5. Use native bulk load when appropriate

Some databases provide dedicated data loading tools (such as `COPY` or bulk insert mechanisms). They can outperform JDBC batch for huge imports, yet have distinct semantics and limits around constraints, triggers, transactions, formats, and error handling. Use them only with benchmarks and a clear operational plan.

## 14. Tool selection workflow

~~~mermaid
flowchart TD
    A["Need to write many records"] --> B{"Is data a Spring Data JDBC aggregate?"}
    B -->|Yes| C{"Need mapping, lifecycle, version, generated ID?"}
    C -->|Yes| D["Use saveAll / repository"]
    C -->|No or specialized SQL write| E{"Uniform SQL shape and tabular data?"}
    B -->|No| E
    E -->|Yes| F["Benchmark JdbcTemplate.batchUpdate"]
    E -->|No| G["Design custom SQL / import strategy"]
    D --> H["Benchmark with equal semantics"]
    F --> H
    G --> H
    H --> I["Choose by throughput, latency, consistency, and recoverability"]
~~~

Practical rules of thumb:

1. **Routine domain CRUD:** use repositories and §save§/§saveAll§.
2. **Importing many simple rows:** benchmark JDBC batch.
3. **Writing multi-table aggregates:** prefer repositories if mapping/lifecycle must be preserved; hand-write batches only when explicitly enforcing invariants.
4. **Massive imports:** consider staging tables or native bulk load, then validate and merge into main tables.
5. **Atomic business operations:** define clear transaction boundaries regardless of whether repositories or batches are used.

## 15. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Assuming §saveAll§ always uses JDBC batch | Misguided performance expectations | Measure actual SQL and inspect version implementation |
| Picking JDBC batch solely from an unequal benchmark | May bypass aggregates/lifecycles/constraints | Compare with identical semantics and data |
| Setting batch size too large | Memory, lock duration, and rollback time spike | Test multiple sizes and measure |
| Missing shared transaction across multi-table writes | Can leave partial data behind | Define transaction boundaries and handle errors |
| Assuming batches always return generated keys | Cannot obtain IDs to link child tables | Check driver/API or generate IDs in the application |
| Ignoring update counts | Cannot tell which items succeeded or failed | Inspect counts and §BatchUpdateException§ |
| Retrying whole batch after failure | Can cause duplicate writes or repeated side effects | Design idempotency and reconciliation |
| Writing children before root | Foreign key violations | Order writes properly or use suitable key strategies |
| Chunking yet keeping one giant transaction | Fails to shrink lock/rollback scope | Split transactions per chunk if semantics allow |
| Disabling constraints for faster imports | Invalid data enters tables | Use staging, validation, and controlled constraints |

## 16. Hands-on exercises

### Exercise 1 — Observing saveAll

Create a list of 100 §Book§ instances, call §saveAll§, enable SQL logging, and count actual statements. Record the number of INSERT/UPDATE statements and how generated IDs are returned.

### Exercise 2 — Writing a JDBC batch

Create a simple three-column §audit_events§ table. Write a DAO using §JdbcTemplate.batchUpdate§ with batch sizes 100, 500, and 1,000. Compare duration, throughput, and memory.

### Exercise 3 — Fair comparison

Run both approaches writing the same 10,000 rows with identical schema/indexes/constraints and transaction policy. Compare total duration, rows/second, p95 latency, and SQL statement count.

### Exercise 4 — Batch with errors

Place an element violating a unique constraint in the middle of a batch. Observe §BatchUpdateException§, update counts, and database state after rollback/commit. Repeat on your target production database if semantics depend on the driver.

### Exercise 5 — Aggregate root and children

Create §PurchaseOrder§ instances with multiple §OrderLine§ items. Persist using §saveAll§. Then try writing roots and children using plain JDBC batch. List the invariants and lifecycle behaviors the batch code must enforce manually.

### Exercise 6 — Chunks and transactions

Import 50,000 rows in chunks of 500. Compare a single overall transaction against per-chunk transactions. Observe lock duration, rollback scope, and ability to resume after failure.

### Exercise 7 — Reading execution metrics

Use SQL logs, connection pool metrics, and database observability tools to identify whether the bottleneck is network, statement execution, indexes, constraints, locks, or transaction logs. Choose optimizations based on the measured bottleneck.

## 17. Key takeaways

- §saveAll§ is an API for saving multiple entities/aggregates under Spring Data JDBC semantics; it **does not guarantee** JDBC batching or a single SQL statement.
- JDBC batch executes multiple parameter sets for a statement; the application manually manages SQL, mappings, generated IDs, relationships, and invariants.
- §saveAll§ fits aggregates, mappings, conversions, lifecycles, and optimistic locking; JDBC batch fits uniform, high-volume SQL writes.
- Batching reduces part of repeated send/execute overhead, yet cannot eliminate index, constraint, WAL, lock, commit, and mapping costs.
- Batch sizes require benchmarking; overly large batches increase memory, lock duration, and rollback costs.
- Batching and transactions are distinct mechanisms. Clear transaction boundaries are required whenever multiple writes must be atomic.
- Performance evaluation must compare **equal work and equal semantics**, using throughput, latency, statement count, database resources, and recoverability.
