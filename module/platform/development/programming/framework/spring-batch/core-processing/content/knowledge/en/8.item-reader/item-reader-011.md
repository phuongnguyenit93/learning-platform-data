# Reading in Order and the Meaning of Order

In Spring Batch, `ItemReader` provides items one by one to a Step in a sequence. This sequence matters because it determines which item is read first, which item is read next, and the order in which data enters the processor and writer. For some business cases, order affects only how data is displayed or written to a file; for others, order can change calculation results, reconciliation, and restartability.

`ItemReader` does not impose a single general sorting rule on all data sources. A reader returns items in the order provided by the source or the reader's implementation. Therefore, when order matters, the application must clearly define the ordering rule in the data source or the reader and ensure that rule remains stable across runs.

## 1. In What Order Does `ItemReader` Read Items?

The basic contract of `ItemReader<T>` is to return one item on each `read()` call, or return `null` when there are no more items:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

For example, a reader reads a source containing items A, B, C, and D:

```text
read() call        Item returned
----------------------------------
1                  A
2                  B
3                  C
4                  D
5                  null (end of input)
```

The order A → B → C → D is the order in which the reader supplies data. Spring Batch calls `read()` repeatedly to build a chunk; the framework does not re-sort all items by ID, time, or some attribute before passing them to the processor.

The source of the order can be:

- The physical position of records in a file.
- The order specified by a SQL query.
- The sort keys configured for a paging reader.
- The order of resources/files traversed by a multi-resource reader.
- Rules implemented by a custom reader itself.

If the order is not clearly defined, the application should not assume that data will always appear in the same sequence on every run.

## 2. The Meaning of Order in Batch Processing

Order is the rule that determines the sequence in which items are read and passed through the processing pipeline. That rule can carry technical or business meaning.

### Technical Order

Technical order makes reading predictable and recoverable. For example, reading records by ascending primary key gives the reader a deterministic sequence; on restart, the checkpoint can reference the position or key already processed.

### Business Order

Business order reflects how data must be processed according to domain rules. For example:

- Account transactions need to be applied in the order they occurred.
- Events need to be processed in the sequence number order supplied by the source system.
- Change versions of a record need to be applied in order of effective time.
- Reports need to be sorted by date, group, and entity code for easy reconciliation.

An ID key does not always represent the true business order. An auto-incrementing ID may reflect the order records were created in the database, but not necessarily when the event actually happened. Choose the sorting attribute according to business requirements.

### Order Can Affect Results

If the processor processes each item independently, order may not change the value of individual items. However, order can still affect write order, log order, or file output order.

If processing is stateful or cumulative, order can directly change the result. For example, when calculating an account balance by applying transactions sequentially, debit and credit transactions must be applied in the correct business order. If the reader returns transactions out of sequence, intermediate balances and limit checks may produce different results.

## 3. For Databases, You Must Use `ORDER BY` When Order Matters

Relational databases do not guarantee query result order if the SQL statement has no `ORDER BY`. The fact that a query currently happens to return data in ID order or by an index does not create a guarantee of order. Execution plans, indexes, statistics, database versions, or changing data can alter the result order.

Example of a query with undefined order:

```sql
SELECT id, account_id, amount, created_at
FROM transactions
WHERE status = 'READY';
```

If you want to read transactions by creation time, specify it explicitly:

```sql
SELECT id, account_id, amount, created_at
FROM transactions
WHERE status = 'READY'
ORDER BY created_at ASC, id ASC;
```

Here:

- `created_at ASC` sorts by ascending time.
- `id ASC` is a secondary key to distinguish records that share the same `created_at`.

The secondary key is very important. If you only use `ORDER BY created_at`, multiple records with the same timestamp can appear in an unstable order. Adding a unique key, such as the primary key, creates a deterministic total order.

The sort direction must also reflect the business accurately:

```sql
-- Oldest first, newest last
ORDER BY created_at ASC, id ASC

-- Newest first, oldest last
ORDER BY created_at DESC, id DESC

-- By group, then by time and unique key
ORDER BY department_id ASC, created_at ASC, id ASC
```

Do not rely on the database's default order or the physical order of rows in the table.

## 4. Configuring Order for Database Readers

### JDBC Cursor Reader

With `JdbcCursorItemReader`, the application supplies the SQL statement to the reader. If order matters, the SQL statement needs `ORDER BY`:

```java
@Bean
@StepScope
JdbcCursorItemReader<TransactionInput> transactionReader(DataSource dataSource) {
    return new JdbcCursorItemReaderBuilder<TransactionInput>()
            .name("transactionReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT id, account_id, amount, created_at
                    FROM transactions
                    WHERE status = 'READY'
                    ORDER BY created_at ASC, id ASC
                    """)
            .rowMapper((rs, rowNum) -> new TransactionInput(
                    rs.getLong("id"),
                    rs.getLong("account_id"),
                    rs.getBigDecimal("amount"),
                    rs.getTimestamp("created_at").toInstant()))
            .build();
}
```

The reader fetches results in the cursor's order. The SQL statement determines the data order; `ItemReader` returns the rows one by one in that sequence.

### JDBC Paging Reader

With `JdbcPagingItemReader`, the reader fetches data page by page. Sort keys must be explicitly configured so that pages follow each other in a stable order. Example with Spring Batch 5:

```java
@Bean
@StepScope
JdbcPagingItemReader<CustomerInput> customerReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider) {

    return new JdbcPagingItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .pageSize(500)
            .rowMapper(customerRowMapper())
            .build();
}
```

The query provider needs sort keys, for example `created_at` combined with `id`, according to the configuration API appropriate for the database and version. When using a builder or query provider, ensure the sort keys are sufficient to uniquely distinguish every row in the result set.

If you sort only by a non-unique column, page boundaries may be unstable. Records with the same sort key value may be paginated inconsistently, leading to duplicate reads or missed records when data changes or when the reader moves to the next page.

## 5. Order When Reading Files and Multiple Resources

### FlatFileItemReader

`FlatFileItemReader` typically reads a file in physical line order: first line, next line, and so on until EOF. If the file contains transactions already sorted by date, the reader preserves that sequence.

File example:

```csv
transactionId,createdAt,amount
T001,2026-11-15T08:00:00,100.00
T002,2026-11-15T08:05:00,50.00
T003,2026-11-15T08:10:00,25.00
```

The reader will deliver T001, T002, T003 in line order. If the source file is not sorted properly, `FlatFileItemReader` does not automatically sort the lines by `createdAt`.

### MultiResourceItemReader

When reading multiple files with `MultiResourceItemReader`, you must determine both the file order and the order of records within each file. If resource order matters, configure an explicit comparator instead of relying on the order returned by the operating system or filesystem.

For example, if you need to read files by date:

```text
transactions-2026-11-13.csv
transactions-2026-11-14.csv
transactions-2026-11-15.csv
```

After sorting resources by name or date metadata, the reader reads each file in turn, and then each line within that file. Ensure the naming rule or metadata accurately reflects the desired business order.

## 6. How Does Order Affect Chunks and Writers?

In chunk processing, the reader supplies items in order; the processor receives each item in that order; the writer receives the chunk's list of processed items. For a normal sequential Step, the order of items in the chunk reflects the order returned by the reader, except for items filtered out by the processor or special processing mechanisms.

For example, the reader returns A, B, C, D, E with chunk size 3:

```text
Reader:      A -> B -> C -> D -> E -> null
                         |          |
                         v          v
Chunk 1:             [A, B, C]   [D, E]
                         |          |
Processor:            process    process
                         |          |
Writer:                write      write
                         |          |
                      Commit     Commit
```

If the processor returns `null` for item B to filter it out, B is not passed to the writer. The remaining items keep their relative order A, C, D, E in the sequential flow.

However, do not assume every writer preserves the observable order at the destination. A writer may write to a database without a default query order; the database does not promise order when read back without `ORDER BY`. If output needs to be sorted, specify the order in the read query or generate the output using a mechanism that guarantees an explicit order.

## 7. Order and Restart: Why Must It Be Stable?

Spring Batch can save the reader's checkpoint in `ExecutionContext`. When a Job fails and is restarted, the reader uses the saved state to resume from the appropriate position. This capability depends on the reader supporting saving/restoring state and the input data remaining consistent.

Suppose a reader has processed up to the record with `id=500` in `created_at, id` order. If between the run and the restart, the source data is modified or the ordering rule is changed, the next record may differ from the one the original checkpoint expected.

Changes that can cause problems:

- New records are inserted before the already-read position.
- Already-read records are deleted or have their sort key modified.
- The source file is replaced or re-sorted.
- The SQL query changes from `ORDER BY created_at, id` to `ORDER BY id`.
- A non-unique sort column causes the order among tied records to change.

The result can be duplicate reads, missed items, or processing data in a different sequence from the initial run. Therefore:

1. Keep the SQL query and sort keys stable across restarts.
2. Use a unique sort key or add a unique tie-breaker.
3. If possible, process an immutable data snapshot or a data set bounded by a cutoff/watermark.
4. Do not replace the input file between runs; you can store files by version or checksum.
5. Design an idempotent writer to reduce harm if items need to be re-read.

With a paging reader, data changing during pagination requires special attention. Offsets or page numbers can shift when records are added or deleted. Using a snapshot or stable range conditions helps keep pagination results more consistent. For large continuously changing sources, consider keyset-based pagination on a stable sort key, depending on the reader and query provider used.

## 8. Order and Parallel Processing

In a sequential Step, the reader returns items in order and chunks are processed in that sequence. When moving to a multi-threaded Step, partitioning, or remote chunking, completion order can differ from the initial read order.

For example, two workers receive two portions of data:

```text
Source in order:     1 2 3 4 5 6
                     |       |
                     v       v
                  Worker A Worker B
                  1 2 3     4 5 6
                     |       |
                     v       v
                  Finishes Finishes
                  after B  before A

Completion order could be: 4 5 6 1 2 3
```

If the writer or target system receives data as soon as each worker finishes, the global output order may no longer match the source order. This is normal in parallel processing.

If the business strictly requires preserving global order:

- Keep the Step sequential if throughput meets requirements.
- Attach a sequence number to items and sort/merge results in a later step.
- Partition by non-overlapping ranges while still having a merge step ordered by the sequence key.
- Avoid using a non-thread-safe reader from multiple threads if the reader does not support that model.

Do not rely on worker completion time to infer business order. Order needs to be expressed by an explicit key or metadata.

## 9. Distinguishing Item Order from `@Order` and Step Order

In Spring, the word "order" can appear in multiple contexts. Distinguish them:

| Concept | Meaning |
|---|---|
| Item order in ItemReader | The sequence in which the reader returns each record |
| SQL `ORDER BY` | The rule for sorting rows in a query result |
| Sort keys of a paging reader | Keys that determine ordering and pagination of results |
| Step order in a Job | The sequence or flow in which the Job orchestrates Steps |
| Spring `@Order` / `Ordered` | Priority order when Spring sorts supported beans or components |

`@Order` on a bean does not automatically sort the items returned by `ItemReader`. Similarly, Step order in a Job does not determine record order within a Step. To sort items, you must configure the data source or reader logic appropriately.

## 10. How to Design Reliable Read Ordering

When building a Job, start by defining what order means to the business:

1. **Choose the right sort field:** use effective time, sequence number, period code, or a key appropriate to the domain.
2. **Create a deterministic order:** if the primary field is not unique, add a unique secondary key as a tie-breaker.
3. **Put the order into the read source:** SQL `ORDER BY`, paging reader sort keys, a comparator for file lists, or explicit logic in a custom reader.
4. **Keep the rule stable:** do not change the order between the first run and a restart.
5. **Control source data:** use snapshots, cutoffs, or file versions if the source can change while the Job runs.
6. **Evaluate the impact of parallelism:** if global order is required, design partitions and a merge step clearly.
7. **Define output order:** if results are read back from a database or object storage, specify the order in the export/read step rather than assuming the writer preserved order.

For example, for a Job applying account transactions by occurrence time, the rule could be:

```sql
SELECT id, account_id, event_time, sequence_no, amount
FROM account_events
WHERE batch_id = :batchId
ORDER BY event_time ASC, sequence_no ASC, id ASC;
```

Here `event_time` determines chronological order, `sequence_no` reflects the order supplied by the source system, and `id` is the final tie-breaker to guarantee unique ordering. The `batch_id` condition scopes it to a stable batch of data.

## 11. Common Mistakes

**Assuming the database returns rows by ID automatically:** without `ORDER BY`, result order is not guaranteed.

**Sorting only by a non-unique column:** rows with the same sort key value can swap positions between reads or pages. Add a unique tie-breaker.

**Using ID as a substitute for business order without checking:** ID may not reflect effective time or event sequence.

**Changing sort keys between restarts:** the old checkpoint may no longer point to the right position in the new sequence.

**Thinking `ItemReader` sorts automatically:** a reader usually delivers data according to the source or configuration; it does not sort every kind of input on its own.

**Confusing `@Order` with item order:** `@Order` controls bean order in contexts Spring supports; it does not replace `ORDER BY` or reader sort keys.

**Expecting global order in parallel execution:** workers may finish out of assignment order. If final order is needed, design a merge or sort mechanism.

## Conclusion

Read order is the sequence in which `ItemReader` supplies items to a Step. `ItemReader` does not define a single universal ordering rule; order comes from the file, database query, paging reader sort keys, or custom reader logic. When order matters, define the business meaning clearly, use an appropriate `ORDER BY` or comparator, and add a unique secondary key to produce a stable order. Keep the source order unchanged across restarts, control data changes, and remember that parallel processing can alter completion order. Spring's `@Order` and Step order are separate concepts and do not sort items in a reader.
