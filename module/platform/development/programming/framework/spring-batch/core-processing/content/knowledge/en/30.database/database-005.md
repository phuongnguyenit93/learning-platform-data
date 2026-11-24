# Cursor Transactions

In Spring Batch, a cursor reader typically opens a database cursor and holds it for the entire lifecycle of the Step to read rows sequentially from a ResultSet. Meanwhile, a chunk-oriented Step typically opens a transaction for each chunk, writes data, and then commits or rolls back. These two lifecycles are related, but they do not necessarily use the same JDBC connection or the same transaction.

The key point to understand is that a cursor can stay open across multiple chunk commits. With the default configuration of JdbcCursorItemReader, the cursor typically uses a separate connection, isolated from the chunk-processing transaction. When a shared extended connection is enabled, the cursor can use a connection shared with the Step's transaction and requires the driver to support holding cursors over commit. This choice affects isolation, rollback behavior, database resources, and how the reader resumes upon restart.

## 1. Cursor reader and chunk transactions have different lifecycles

A cursor reader executes a query and keeps the ResultSet open to fetch each row. A chunk-oriented Step groups items into batches, processes them, and writes them inside a transaction.

For example, with a chunk size of 100:

~~~text
Step starts
   |
   v
Open cursor and ResultSet
   |
   v
Read 100 items
   |
   v
Processor processes
   |
   v
Writer writes 100 items
   |
   v
Commit chunk 1 transaction
   |
   v
Read next 100 items from open cursor
   |
   v
Writer writes chunk 2
   |
   v
Commit chunk 2 transaction
   |
   v
...
   |
   v
Close cursor when Step ends
~~~

The cursor typically outlives a single chunk. Chunk transactions start and end multiple times within the same Step. Confusing these two lifecycles into one can lead to errors where the cursor closes after commit, transactions are held too long, or the data visible to the reader is misunderstood.

Distinguish between:

- **Cursor lifecycle:** opening statement/ResultSet, fetching rows, closing resources.
- **Chunk transaction:** wrapping a group of items and related write operations.
- **StepExecution lifecycle:** managing the entire Step run, including reader/writer state and checkpoint metadata.

## 2. By default JdbcCursorItemReader uses a separate connection

JdbcCursorItemReader normally opens the cursor on a separate connection that does not participate in the transaction wrapping the chunk. This connection is held to read the ResultSet until the reader closes.

In the default configuration, useSharedExtendedConnection is false. Therefore:

- The transaction manager controls the connection used for chunk operations, such as a JDBC writer.
- The cursor reader uses a different connection to hold the ResultSet.
- Committing or rolling back the writer does not directly commit or roll back the cursor connection.
- The cursor can continue reading after the chunk transaction has committed.

Model:

~~~text
                    Step
                     |
          +----------+----------+
          |                     |
          v                     v
   Cursor connection      Chunk transaction
          |                     |
          v                     v
   SELECT / ResultSet       INSERT / UPDATE
          |                     |
          |                     v
          |                 COMMIT chunk
          |
          v
    Fetch next row
~~~

Separating connections allows the reader to keep the cursor open while the write transaction commits chunk by chunk. It also means the cursor does not automatically see or participate in every change made within the writer transaction.

Do not deduce that just because the reader and writer use the same DataSource bean, they definitely share the same JDBC connection. What matters is the actual connection allocated and how the transaction manager binds connections.

## 3. Why does a cursor need to survive across multiple commits?

A cursor query may return millions of records. Closing and reopening the query after every chunk would force the database to repeat significant work and require the reader to reposition its read point.

The cursor reader keeps the ResultSet open for incremental fetching. Chunk transactions can commit repeatedly while the reader continues advancing through the cursor.

Example:

~~~text
Cursor query:
  SELECT id, amount
  FROM orders
  WHERE business_date = ?
  ORDER BY id

Chunk 1: id 1..100       -> commit
Chunk 2: id 101..200     -> commit
Chunk 3: id 201..300     -> commit
...
Chunk N: last id         -> commit
~~~

Committing every chunk limits the write transaction duration and the amount of data needing rollback. The cursor remains open to read the rest.

However, a long-lived cursor also holds a connection and database resources for a long time. Depending on the database, it may hold snapshots, keep a transaction session open, or increase pressure on undo/version storage. Balance streaming benefits against resource hold times.

## 4. What is a shared extended connection?

JdbcCursorItemReader has an option to use a shared extended connection. When enabled, the cursor connection is shared with other operations in the Step via ExtendedConnectionDataSourceProxy.

The goal is to share the connection in a way that allows the cursor to survive across chunk commits. The database driver must support cursor holdability over commit, typically related to HOLD_CURSORS_OVER_COMMIT.

Conceptual setup:

~~~text
Transaction manager
        |
        v
Physical JDBC connection
        ^
        |
ExtendedConnectionDataSourceProxy
        |
        +--> JdbcCursorItemReader
        |
        +--> JDBC operations in the Step
~~~

In this mode, the connection is kept open across chunk commits so the ResultSet/cursor is not closed. Both the proxy and the reader property must be configured properly; merely enabling the shared connection flag with a plain DataSource will not satisfy this mechanism's requirements.

Do not enable shared connection just because you want the reader and writer "in the same transaction." Clearly identify the objective: keeping the cursor across commits, sharing the same connection, or needing a specific isolation boundary. Shared connections carry their own prerequisites and trade-offs.

## 5. Configuring ExtendedConnectionDataSourceProxy

To use a shared extended connection, create a proxy wrapping the underlying DataSource and configure the reader to use that proxy.

Configuration example:

~~~java
@Bean
ExtendedConnectionDataSourceProxy extendedDataSource(
        DataSource dataSource) {
    return new ExtendedConnectionDataSourceProxy(dataSource);
}
~~~

Reader declaration:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Order> orderCursorReader(
        ExtendedConnectionDataSourceProxy extendedDataSource) {

    JdbcCursorItemReader<Order> reader =
            new JdbcCursorItemReader<>();

    reader.setName("orderCursorReader");
    reader.setDataSource(extendedDataSource);
    reader.setSql("""
            select id, customer_id, amount
            from orders
            where business_date = ?
            order by id
            """);
    reader.setRowMapper((rs, rowNum) -> new Order(
            rs.getLong("id"),
            rs.getLong("customer_id"),
            rs.getBigDecimal("amount")));
    reader.setUseSharedExtendedConnection(true);
    reader.setFetchSize(500);
    reader.setSaveState(true);

    return reader;
}
~~~

ExtendedConnectionDataSourceProxy must wrap the DataSource used by the Step's transaction manager. Both the transaction manager and the reader must reference the same underlying connection source per application configuration.

Imports, bean wiring, and transaction manager configuration depend on the Spring version and how the application declares its DataSource. Do not create two separate pools and expect the proxy to share a physical connection between them.

## 6. The driver must support HOLD_CURSORS_OVER_COMMIT

When shared extended connection is enabled, the cursor must survive across chunk commits. This requires the JDBC driver and database to support holding cursors over commit.

JDBC defines holdability:

- CLOSE_CURSORS_AT_COMMIT: the cursor is closed when the transaction commits.
- HOLD_CURSORS_OVER_COMMIT: the cursor stays open across commits.

JdbcCursorItemReader using a shared extended connection requires the ability to hold cursors over commit. Drivers may behave differently depending on the database, cursor type, and statement creation method.

Do not assume every database supports identical behavior. Before enabling shared connection, verify:
- Database engine and version.
- JDBC driver version.
- Cursor type/holdability actually granted by the driver.
- How the transaction manager commits the connection.
- How the driver handles the ResultSet after commit.
- Behavior upon rollback or reconnect.

If the driver does not support the required holdability, the reader may fail at commit time, the cursor may be closed, or subsequent reads may become invalid. In that case, use the default separate cursor connection or choose another more suitable reader/pattern.

## 7. Transaction manager and DataSource must match

Chunk transactions are controlled by PlatformTransactionManager. For JDBC, the transaction manager is usually configured over the corresponding DataSource.

Example:

~~~java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

In a shared extended connection setup, ExtendedConnectionDataSourceProxy must wrap the exact DataSource that the transaction manager uses. The proxy lets the reader obtain the extended connection managed alongside the transaction lifecycle.

If the transaction manager uses DataSource A while the reader uses DataSource B or a different pool, the two sides will not share connections as intended. Even with the same database URL, two physical connections remain two independent sessions.

With multiple DataSources, clearly define which database the reader reads from and which the writer writes to. A standard JDBC transaction manager does not automatically create an atomic distributed transaction across two DataSources.

## 8. Chunk commit does not mean the cursor query is re-executed

When a chunk commits, the writer transaction ends. The cursor reader continues reading from the current ResultSet if the connection/driver keeps the cursor valid.

Example:

~~~text
Cursor opened once:
  SELECT ... ORDER BY id

Chunk transaction:
  begin -> write chunk 1 -> commit
  begin -> write chunk 2 -> commit
  begin -> write chunk 3 -> commit

Cursor:
  fetch rows 1..100
  fetch rows 101..200
  fetch rows 201..300
  close when Step finishes
~~~

Because the cursor is not recreated after every chunk, the reader does not re-execute the entire query at every commit. However, the data returned by the cursor is determined by database semantics, transaction isolation, and how the driver implements cursors.

Do not assume the cursor always reflects the latest committed data after each chunk. Many databases determine the result set when the query opens or according to a specific snapshot/transaction. Exact behavior depends on the database and isolation level.

## 9. Isolation levels and data consistency

Transaction isolation affects what data the reader sees while the Job is running. Distinguish between the isolation of the cursor connection and that of the chunk transaction when they use two separate connections.

Common isolation levels:

| Isolation | General behavior | What to watch with cursors |
|---|---|---|
| READ_UNCOMMITTED | May read uncommitted data if supported by the database | Risk of dirty reads |
| READ_COMMITTED | Reads only committed data as of read time per database semantics | Subsequent reads may see new changes depending on cursor/database |
| REPEATABLE_READ | Maintains stronger consistency within a transaction | May hold versions/locks longer |
| SERIALIZABLE | Highest isolation level; can restrict concurrency | Prone to blocking or serialization failures |

Isolation levels are implemented differently across databases. A single cursor query does not necessarily have identical snapshot behavior on every engine. For example, some databases use MVCC and hold a SELECT snapshot; some cursor mechanisms require a long-running transaction; some drivers fetch in batches.

If an immutable dataset is needed for the entire Job, consider:
- Running the query on a snapshot or staging table.
- Using a fixed watermark determined before reading.
- Using a fixed business date or batch ID in WHERE.
- Using a stable and unique sort key.
- Choosing an appropriate isolation level after measuring its impact on the database.

Do not raise isolation to SERIALIZABLE by default just to "be safe." Long transactions and long-lived cursors can reduce concurrency or cause lock contention.

## 10. Separate cursor connection and source data changes

With the default configuration, the cursor reader and chunk writer can use two separate connections. This matters when a Step both reads from and updates the same database.

For instance, the reader reads rows with status NEW, and the writer updates status to PROCESSED. If the cursor query opens first and the database fixes the result set via a snapshot, the reader may continue seeing the rows from the initial set. However, exact behavior depends on the database, isolation, and cursor implementation.

Questions to answer before implementation:

- Are other transactions inserting new rows matching the query while the Job is running?
- Can already-read rows be updated or deleted by another process?
- Does the writer update the exact table the reader is reading?
- Does the cursor hold a snapshot from query execution time or fetch under different semantics?
- If the Job restarts, will the source data still be at the same version?
- Can a batch ID or watermark be used to fix the dataset?

If the Job must process an exact input batch, it is usually best to have a stable filter condition, such as batch_id = ?, or create a snapshot/staging set before starting the cursor. Do not rely on the cursor automatically creating a business snapshot without verifying database behavior.

## 11. How do chunk commits and rollbacks affect the reader?

When a writer throws an exception, the chunk transaction may roll back. Rollback undoes transactional changes in the chunk, but does not mean the JDBC cursor automatically rewinds to before the items were read.

A cursor is a forward-moving ResultSet. The read position in memory and the checkpoint stored in ExecutionContext are two different things.

Spring Batch manages item recovery according to chunk processing and fault-tolerance semantics. For some readers, the framework can buffer items for re-presentation after rollback; upon restart, the reader recovers from the committed checkpoint. Do not write custom logic assuming a JDBC rollback will move the cursor back to the first row of the chunk.

Conceptual model:

~~~text
Checkpoint committed at item 200
          |
          v
Read items 201..300
          |
          v
Writer fails -> chunk rollback
          |
          v
Step reprocesses per retry/recovery policy
          |
          v
If process stops and restarts:
  open new cursor
  recover from durable checkpoint
  resume after saved commit point
~~~

Checkpoints are normally updated at chunk commit boundaries. Thus, if the process stops after a committed chunk, restart can resume from the last checkpoint. If there are non-transactional side effects, such as writing files or calling HTTP APIs, idempotency or reconciliation is required to avoid duplicate side effects.

## 12. JdbcCursorItemReader checkpoints and restart

JdbcCursorItemReader can store read state in the Step ExecutionContext. On restart, the reader reopens the query and restores its read position from the saved checkpoint.

For reliable restart:

- Assign a stable reader name via setName or the builder's name.
- Enable saveState(true) if checkpointing is needed.
- Use ORDER BY with a deterministic and unique key.
- Keep the query and parameters affecting the result set unchanged.
- Ensure source data does not mutate in a way that invalidates the old checkpoint.
- Do not change the reader name or state structure across deployments requiring restart.

Some cursor readers recover by advancing to the previously read item; this may require reading/skipping rows from the start of the query. On large datasets, restart time can grow with the checkpoint position. Drivers supporting absolute positioning can help optimize in suitable cases, but driver semantics and capabilities must be verified.

Do not rely on a row-number checkpoint if result ordering is unstable. Always include a proper ORDER BY, preferably based on a unique key. If multiple rows share the same sort value, their relative order may be non-deterministic.

## 13. Fetch size and cursor transactions

Fetch size is a hint to the JDBC driver on how many rows to retrieve from the database at a time. It can affect network round trips, client-side memory, and cursor hold time.

Example:

~~~java
reader.setFetchSize(500);
~~~

Fetch size is not chunk size:

- Chunk size determines the number of items processed/written in one transaction.
- Fetch size is a hint for how many rows the driver fetches from the database per trip.
- The two values can differ.

For example, with chunk size 100 and fetch size 500: the driver may prefetch a batch larger than one chunk, while the Step still commits every 100 items. This can reduce round trips, but also increases buffered data and may affect memory.

Some drivers only truly stream when fetch size is set and the connection is in an appropriate transaction state. PostgreSQL JDBC, for instance, has specific requirements regarding auto-commit and fetch size. Do not assume setFetchSize alone guarantees a server-side cursor on every driver.

Measure in practice with a production-like database/driver and pick values based on throughput, heap usage, and connection hold duration.

## 14. Query timeout, max rows, and cursor resources

Long-open cursors consume database resources. Additional appropriate limits can be configured:

- Fetch size to tune batch fetching.
- Query timeout to cap initial query execution time.
- Max rows if only a bounded subset needs processing.
- Driver-specific properties to tune cursors or streaming.
- Connection pool size sufficient for both cursor connections and chunk connections.
- Timeouts/monitoring for Jobs and Steps.

Query timeout typically limits SQL statement execution time, not necessarily the total time the cursor remains open and reading. After the query executes, fetching rows can drag on; understand how the driver applies timeouts.

Do not leave cursors open indefinitely when a Job hangs. Set Job time limits, handle controlled stops/shutdowns, and ensure the reader closes resources when the Step finishes.

## 15. Separate cursor connections affect the connection pool

When using a separate cursor connection, a Step may require at least one connection for the reader and one connection for the chunk transaction if the writer also accesses the database through the transaction manager.

When running multiple Jobs or partitions in parallel, connection counts multiply:

~~~text
4 worker partitions
  |
  +--> 4 cursor connections
  |
  +--> 4 chunk transaction connections
  |
  +--> connections for other services
~~~

This is an illustrative model; actual connection counts depend on the reader/writer and transaction resources. However, size the connection pool for concurrency, not just the number of Steps.

If the pool is too small, readers can hold cursor connections while writers wait for another connection, causing pool exhaustion or starvation. With a shared extended connection, one connection is shared as configured, though this can increase contention or limit throughput.

Monitor active/idle/pending connections, connection acquisition time, and cursor open duration. Do not just increase pool size without checking database connection limits.

## 16. Cursors and updating the same table being read

A common scenario is reading rows to process and having the writer update the status of those exact rows.

Example:

~~~sql
SELECT id, status
FROM orders
WHERE status = 'NEW'
ORDER BY id
~~~

The writer updates status to PROCESSED.

Determine whether the cursor query keeps returning rows from the initial result set or is affected by updates, depending on the database/driver. If the reader and writer use two separate connections, writer commits do not necessarily alter the already-open result set. If using a shared connection, semantics may differ and require testing.

A more stable design is to fix the input set before processing:
- Assign a batch ID to selected rows.
- Snapshot the ID list into a staging table.
- Use a fixed watermark and unique sort key.
- Transition rows to IN_PROGRESS using an explicit transaction/claim strategy.

Do not let multiple concurrent Jobs select and process NEW rows without an appropriate claim or locking mechanism. Cursor transactions do not automatically resolve contention across Jobs.

## 17. Comparing separate cursor connection vs. shared extended connection

| Criterion | Separate connection (default) | Shared extended connection |
|---|---|---|
| Reader connection | Separate from chunk transaction | Shared via proxy with transaction connection |
| Cursor across chunk commits | Held on dedicated reader connection | Requires holdability over commit |
| DataSource | Standard DataSource can be used | Requires ExtendedConnectionDataSourceProxy |
| Driver requirement | Depends on standard cursor support | Requires HOLD_CURSORS_OVER_COMMIT support |
| Isolation | Cursor and writer can be in different sessions/transactions | Same connection so semantics differ |
| Connection pool | May need extra connections for cursors | Can reduce separate connections but holds connection long |
| Best suited for | Default setup, independent reader/writer | When shared connection is needed and driver clearly supports it |

Neither option is best for every database. Use a separate connection if there is no specific reason to share and the driver lacks holdability support. Use a shared extended connection when those semantics are needed, the driver supports it, and it has been tested with the real transaction manager.

## 18. When should you use JdbcCursorItemReader?

A cursor reader is typically suitable when:
- You need to sequentially read a large dataset.
- The query can return a stable ResultSet.
- The database and driver support suitable cursor/streaming behavior.
- Holding a connection open for the Step duration is acceptable.
- Data ordering and restart strategy are well defined.

Consider alternatives when:
- Connections are constrained or the Job runs very long.
- The cursor holds snapshots/locks causing heavy pressure.
- Source data changes continuously and an exact input set must be fixed.
- Restarting from the start of the query is too expensive.
- The driver does not support the required cursor behavior.

JdbcPagingItemReader is a common alternative. It reads page by page instead of keeping a ResultSet cursor open throughout. However, paging also requires stable sort keys and a strategy to avoid omissions/duplicates when source data changes. Choose the reader based on data semantics, not speed benchmarks alone.

## 19. Testing cursor transactions

Testing with H2 or mocks helps verify basic configuration, but does not fully prove cursor holdability for a production database. Integration tests on a database and JDBC driver close to the real environment are essential.

Important scenarios:

| Scenario | What to verify |
|---|---|
| Reading across multiple chunks | Cursor continues after each chunk commit |
| Writer commit | ResultSet still reads the next item |
| Writer rollback | Chunk is recovered per retry/restart semantics |
| Shared connection enabled | Driver holds cursor across commits |
| Driver lacks holdability | Error is clearly detected on startup/test |
| Job restart | Reader recovers from last committed checkpoint |
| Source changes during Job run | Behavior stays consistent with chosen isolation |
| Writer updates source table | No unintended lost or duplicate rows |
| Multiple concurrent Jobs | Connection pool and lock behavior remain acceptable |
| Step stopped | Cursor and connection are closed per lifecycle |
| Query timeout | Job terminates per timeout policy |
| Changing fetch size | Throughput and memory are measured, not guessed |

A useful restart integration test:
1. Run the Step with a small chunk size.
2. Force the writer to fail intentionally after several committed chunks.
3. Verify StepExecution saved the checkpoint.
4. Restart the same JobInstance.
5. Verify the reader resumes at the exact position and output has no duplicates/omissions.
6. Re-run with shared extended connection if the application uses that mode.

Also observe allocated connections, cursor open/close events, and transaction states. Do not rely solely on the final read count to conclude the driver held the cursor properly across commits.

## 20. Common mistakes when working with cursor transactions

**Assuming the default cursor connection participates in the chunk transaction.** By default JdbcCursorItemReader typically uses a separate connection; writer commits do not control that connection.

**Enabling shared connection without ExtendedConnectionDataSourceProxy.** The reader lacks the extended connection mechanism required.

**Driver not supporting hold cursors over commit.** The ResultSet may be closed or subsequent reads may fail.

**Confusing fetch size with chunk size.** The two parameters control two different layers.

**Assuming rollback rewinds the cursor to the start of the chunk.** Cursor position and transaction checkpoints are two separate mechanisms.

**Query without a stable ORDER BY.** Restarts may skip or duplicate rows if ordering shifts.

**Using a cursor for very long-running Jobs without accounting for resources.** Connections and database cursors can be held for hours.

**Not sizing the connection pool for both readers and writers.** Multiple workers can exhaust the pool.

**Not understanding database isolation.** The reader may observe a different dataset than expected when source data changes.

**Using shared connection merely to save an extra connection.** Can increase contention and requires driver-specific behavior.

**Letting multiple Jobs read/update the same row set without claiming data.** Cursors do not replace coordination and business locking mechanisms.

## 21. Workflow for choosing the right cursor transaction

When using JdbcCursorItemReader, follow this sequence:

1. Determine whether the cursor needs to share a connection with the Step's transaction.
2. Start with the default configuration using a separate cursor connection unless another requirement exists.
3. If enabling shared extended connection, wrap the DataSource with ExtendedConnectionDataSourceProxy and enable useSharedExtendedConnection.
4. Confirm the proxy wraps the exact DataSource used by the transaction manager.
5. Verify database/driver support for HOLD_CURSORS_OVER_COMMIT.
6. Choose an isolation level and snapshot/watermark strategy matching data requirements.
7. Use a stable ORDER BY, preferably with a unique key.
8. Configure fetch size, query timeout, and connection pool based on actual measurements.
9. Enable saveState and keep reader name/query/inputs stable if restart is needed.
10. Test commits, rollbacks, restarts, source mutations, and stops on a real database.
11. Monitor cursor hold time, connection pool, lock/version storage, and throughput.

Cursor transaction is the relationship between an open ResultSet and the chunk transactions executing within a Step. The default configuration separates the cursor connection from chunk transactions; shared extended connection allows sharing a connection across commits when supported by both proxy and driver. When choosing the right model, controlling isolation, stabilizing queries, and testing restarts on a real database, a cursor reader can stream large datasets while keeping write transactions at clear chunk boundaries.

