# Choosing a Database or File Reader in Spring Batch

## 1. The Design Problem

A Spring Batch project often starts with the question: "Where does the data to be processed live?" If the data is in a SQL table, many teams pick `JdbcCursorItemReader` or `JdbcPagingItemReader`. If a partner delivers a CSV file over SFTP, another team picks `FlatFileItemReader`. However, deciding between **a database reader or a file reader** does not depend solely on where the data initially resides.

Suppose a reconciliation job must process 8 million transactions every night. The data currently lives in PostgreSQL; another system could also export daily CSVs. Both approaches can feed into `ItemProcessor` and `ItemWriter`, yet they differ in consistency, database load, auditability, restartability, access permissions, latency, and operational behavior when data changes while the job is running.

This lesson belongs to *Spring Batch Core Processing → Design Decisions*. The goal is to help you choose a read source that **meets business and operational requirements with evidence**, rather than assuming "files are faster" or "databases are more modern."

After this lesson, you will be able to:

- Distinguish `JdbcCursorItemReader`, `JdbcPagingItemReader`, `JpaPagingItemReader`, `FlatFileItemReader`, and `MultiResourceItemReader`.
- Evaluate **snapshot stability**, restartability, checkpointing, and avoiding missing or duplicate reads.
- Compare database load, JVM memory, I/O, latency, operational cost, and decoupling between systems.
- Configure database/file readers with Spring Batch 5.x, `JobParameters`, and `@StepScope`.
- Select appropriate chunk size, page size, fetch size, and partitioning strategies.
- Design tests for mutating data, modified files, crashes, restarts, and schema/encoding errors.
- Write an **Architecture Decision Record (ADR)** for your reader choice.

The code examples use **Java 17+, Spring Boot 3.x, and Spring Batch 5.2.x**. The concepts remain useful in Spring Batch 6.x, though some packages/APIs may differ; consult the documentation for your exact version before copying code.

---

## 2. First Decision: What Is the Source Data and Who Owns It?

Before looking at reader class names, identify the nature of the data source.

| Question | If the answer is database | If the answer is file |
|---|---|---|
| Who owns the data? | Service/database actively serving transactions | Partner or a snapshot export process |
| Can the source change while the batch runs? | Concurrent inserts/updates/deletes are possible | Can be immutable after publishing with a solid contract |
| How is data selected? | SQL filters, joins, cutoffs, partitions | File name, manifest, header, business period |
| Need to rerun the exact same snapshot? | Requires fixed snapshot/version/conditions | Easier if the original file + checksum are retained |
| Can the source handle additional load? | Must consult DBA/SRE and measure | Must ensure storage/network/format capacity |
| How is access restricted? | SQL accounts, row-level policies, schema permissions | SFTP/bucket ACLs, encryption, expiry |
| Must data be available immediately? | Near real-time once committed | Depends on file generation and transfer time |
| Need exact source auditing? | Query + snapshot/version + parameters | Immutable file ID, checksum, manifest |
| Need to distribute the same data to multiple consumers? | Separate queries per consumer can multiply load | A single snapshot can be shared in a controlled manner |
| Error occurs mid-run? | Cursor/page checkpoint and consistency | File path/position checkpoint, requires immutable files |

**The most important thing is the data contract.** A "good" reader cannot fix a source that mutates continuously and breaks record set consistency. Conversely, files only truly provide a snapshot advantage when the sender guarantees the file is complete and is not modified during or after consumer processing begins.

### 2.1. Four Common Data Source Patterns

1. **Active transactional database (OLTP):** data changes continuously; batch queries can impact application latency.
2. **Database replica/warehouse or staging table:** suitable for large read queries if a clear snapshot/cutoff mechanism exists.
3. **Immutable snapshot file:** data is finalized per period and exported into one or more files with a manifest/checksum.
4. **In-progress file or temporary export API:** can only be used safely after being "closed" and confirmed complete.

The third model is usually easier to rerun, though it carries snapshot creation, storage, and file transfer costs. The second model is often flexible for filtering and avoids copying, but requires careful control of isolation, locks, and sort key stability.

---

## 3. Reader Architecture in Spring Batch

Spring Batch uses the `ItemReader<T>` interface:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Each call to `read()` returns one item, or `null` when data is exhausted. For restart-capable readers, the `ItemStream` interface adds `open`, `update`, and `close`.

```text
Job
 │
 ▼
Step (chunk-oriented)
 │
 ├── ItemReader.read()
 │      ├── JDBC cursor/paging/JPA
 │      └── flat file/multi-file
 │
 ├── ItemProcessor.process()
 │
 └── ItemWriter.write(Chunk)
          │
          ▼
     Transaction commit
     + ItemStream checkpoint
          │
          ▼
       JobRepository
```

Thanks to this abstraction, many pipelines can **keep the same processor and writer** and only swap the reader. However, two readers are not automatically equivalent in ordering, input dataset, or restartability.

### 3.1. A Reader Is Not a Transaction Coordinator

`FlatFileItemReader` can record line positions for restart, but reading a file does not roll back together with the database. `JdbcCursorItemReader` reads over a JDBC connection/cursor with its own transaction configuration; do not assume every query/reader runs in the same transaction as the writer. A successful batch commit only records the chunk and configured metadata—it does not create a new snapshot of the source.

For example, a job reads source database A, processes, and writes to target database B:

```text
Source DB A               Spring Batch              Target DB B
    │                          │                         │
    ├──── SELECT rows ────────►│                         │
    │                          ├──── write/commit ──────►│
    │                          │                         │
    └── source may still be updated/deleted concurrently │
```

If A and B do not share a meaningful transaction, committing on B does not lock source state on A. Similarly, reading a file whose row positions have changed can invalidate line-based checkpoints.

---

## 4. Quick Comparison Table

| Criterion | Database reader | File reader |
|---|---|---|
| Data freshness | Can be close to latest committed data | Depends on snapshot/export cycle |
| Data filtering | SQL WHERE/JOIN/partition is convenient | Usually requires scanning or separate manifest/index |
| Load on transactional system | Risk of heavy queries, long cursors/connections | Reduces direct DB read load once snapshot completes |
| Rerun exact same dataset | Must control snapshot/version/mutations | Easier if files are immutable and retained |
| Restart | Cursor/page/checkpoint; depends on query/sort stability | Position/resource; depends on unchanged byte/line/file order |
| Consistency | Isolation, snapshot, high-water mark, CDC | Complete file/manifest, checksum, schema version |
| Memory | Depends on fetch/page size, driver, JPA graph | Depends on line/parser; no need to load whole file |
| I/O | DB connection, SQL over network, paging | File system/object store/SFTP, disk/network |
| Parallel execution | Partition by ID/range, keyed queries | Partition by file, or byte range for supported formats |
| Audit | Must record query, filters, snapshot ID | File ID/checksum/manifest serve as convenient evidence |
| Very large data | Must evaluate DB capacity | Easy to split files, but has export/storage cost |
| Security | DB roles, row/column permissions | ACLs, encryption at rest/in transit, key lifecycle |
| Schema changes | DB schema migrations, query mapping | Header/layout/versioning, backward compatibility |
| Source failures | Timeouts, deadlocks, replica lag, lost cursor | Missing, corrupt, truncated file, wrong encoding |
| Multiple consumers | Multiple DB queries can duplicate load | Controlled sharing of the same snapshot file |
| Deletion/retention | Table/snapshot policies | Object version, file archive, and cleanup policies |

These are **tendencies**, not absolute conclusions. A file on slow network storage can be slower than a database. An analytics-tuned DB replica may deliver a more stable snapshot and higher throughput than a temporary file export pipeline. Measure on your actual system.

---

## 5. Database Branch: Cursor, Paging, and JPA

### 5.1. JdbcCursorItemReader

`JdbcCursorItemReader` uses a JDBC `ResultSet` as a sequential cursor. When `read()` is called, the reader fetches the next row and maps it via a `RowMapper`.

```text
Database:
  SELECT id, amount FROM orders WHERE ...
         │
         ▼
     JDBC ResultSet / cursor
         │
         ├── row #1 → read()
         ├── row #2 → read()
         ├── row #3 → read()
         └── ... until exhausted
```

**When worth considering:**

- Query produces a large result set that needs sequential reading.
- Database/driver supports cursors/streaming properly.
- Per-request pagination is unnecessary.
- Holding the connection and cursor for the processing duration is acceptable.
- Simple data mapping with low ORM overhead is desired.

**Risks:**

- Long-lived cursor/connection; if the processor/writer is slow, resources may be held for hours.
- The driver might buffer the entire `ResultSet` if streaming is not configured properly.
- Large queries can compete for CPU/I/O with OLTP traffic.
- If the connection drops, the reader/job must restart via supported mechanisms; physical cursors cannot always be resumed.
- Data changing during the query can affect results depending on DB isolation/snapshot semantics.

Spring Batch 5.x configuration example:

```java
@Bean
@StepScope
JdbcCursorItemReader<OrderRow> cursorOrderReader(
        DataSource dataSource,
        @Value("#{jobParameters['cutoffId']}") Long cutoffId) {

    if (cutoffId == null) {
        throw new IllegalArgumentException("cutoffId required");
    }

    return new JdbcCursorItemReaderBuilder<OrderRow>()
            .name("cursorOrderReader")
            .dataSource(dataSource)
            .sql("""
                SELECT id, customer_id, amount
                FROM source_orders
                WHERE id <= ?
                ORDER BY id
                """)
            .preparedStatementSetter(ps -> ps.setLong(1, cutoffId))
            .rowMapper((rs, rowNum) -> new OrderRow(
                    rs.getLong("id"),
                    rs.getLong("customer_id"),
                    rs.getBigDecimal("amount")))
            .fetchSize(500)
            .build();
}
```

Key imports:

```java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
```

`OrderRow` is the model declared in the complete example section below.

**Note:** `fetchSize(500)` is a hint to the JDBC driver, **not a hard memory cap**. Some drivers require disabling autocommit or enabling a specific stream/cursor mode. Check the actual behavior of PostgreSQL/MySQL/Oracle/JDBC drivers in your environment; do not infer from a single config line.

### 5.2. JdbcPagingItemReader

Instead of holding a long-lived query cursor, `JdbcPagingItemReader` executes multiple queries fetching one page at a time. Each page holds roughly `pageSize` rows, and the reader returns items one by one as `read()` is called.

```text
Query page #1 → [row 1 ... row 500]
                         │
                     read() each row
                         │
Query page #2 → [row 501 ... row 1000]
                         │
                     read() each row
                         ▼
                     end of data
```

**Critical requirement:** the sort key must be **unique and stable**. Spring Batch documentation notes that a unique sort key is required to prevent data loss upon restart. The reader uses the saved sort key value to reposition on resume, though this **does not automatically create a consistent snapshot** if the source mutates.

Example creating a `PagingQueryProvider` for a table with primary key `id`:

```java
@Bean
PagingQueryProvider orderPagingQueryProvider(DataSource dataSource)
        throws Exception {

    SqlPagingQueryProviderFactoryBean factory =
            new SqlPagingQueryProviderFactoryBean();

    factory.setDataSource(dataSource);
    factory.setSelectClause("SELECT id, customer_id, amount");
    factory.setFromClause("FROM source_orders");
    factory.setWhereClause("WHERE id <= :cutoffId");
    factory.setSortKey("id");
    factory.afterPropertiesSet();

    return factory.getObject();
}
```

Reader:

```java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> pagedOrderReader(
        DataSource dataSource,
        PagingQueryProvider orderPagingQueryProvider,
        @Value("#{jobParameters['cutoffId']}") Long cutoffId) {

    if (cutoffId == null) {
        throw new IllegalArgumentException("cutoffId required");
    }

    return new JdbcPagingItemReaderBuilder<OrderRow>()
            .name("pagedOrderReader")
            .dataSource(dataSource)
            .queryProvider(orderPagingQueryProvider)
            .parameterValues(Map.of("cutoffId", cutoffId))
            .rowMapper((rs, n) -> new OrderRow(
                    rs.getLong("id"),
                    rs.getLong("customer_id"),
                    rs.getBigDecimal("amount")))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

Corresponding imports:

```java
import java.util.Map;

import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.PagingQueryProvider;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.batch.item.database.support.SqlPagingQueryProviderFactoryBean;
```

`SqlPagingQueryProviderFactoryBean` generates paginated SQL according to the database dialect. A stable `ORDER BY id` is essential. Indexes matching the predicate/sort help avoid full table scans on large datasets.

**When to consider paging:** long-running jobs, wanting short per-page queries, needing easy ID-based partitioning, having a unique sort key, and a database that supports efficient paging.

**Paging risks:**

- Each page query is a new query and can observe data changes between pages.
- If the predicate filters on `status='NEW'` while the writer updates status to `PROCESSED`, the result set shrinks mid-run. Spring Batch JDBC paging with sort-key checkpointing avoids some offset-shift issues, but **does not guarantee** zero data loss across all update/filter strategies.
- Non-unique or mutated sort keys risk missing or duplicating reads.
- Too large a page size increases memory; too small increases DB round-trips.
- When using a multi-threaded reader, `saveState` usage and thread safety must be designed explicitly; do not assume sharing a single reader instance across threads is restart-safe.

### 5.3. Cursor vs. Paging?

| Question | Cursor | Paging |
|---|---|---|
| Number of main queries | One long-lived query/ResultSet | Multiple per-page queries |
| Holds connection/cursor | Usually yes, long-lived | Per page fetch, depending on datasource |
| Driver streaming dependency | High | Usually more explicit per page |
| Sequential read of large sets | Convenient | Convenient if key/pages are stable |
| Consistent snapshot query | Depends on isolation and DB | Harder because queries run at different times |
| ID-range partitioning | Possible, with separate cursor per partition | Typically convenient |
| Restart | Restores position via state/count | Uses sort key/state per reader |
| DB round-trips | Fewer queries, long connection | Many queries |
| Workload and query planner | One long query | Many small queries; indexing is critical |

Do not assume paging is "always better than cursor." On databases with strong server-side cursor support, a single sequential read on a replica can be very efficient. For multi-hour processing over unreliable networks, paging can make resource management easier. Benchmarks and consistency requirements decide.

### 5.4. JpaPagingItemReader

`JpaPagingItemReader` fits projects using JPA that want entity mapping via JPQL. Example:

```java
@Bean
@StepScope
JpaPagingItemReader<OrderEntity> jpaOrderReader(
        EntityManagerFactory emf) {

    return new JpaPagingItemReaderBuilder<OrderEntity>()
            .name("jpaOrderReader")
            .entityManagerFactory(emf)
            .queryString("""
                select o
                from OrderEntity o
                order by o.id
                """)
            .pageSize(500)
            .build();
}
```

JPA readers manage the persistence context per page; in Spring Batch 5.x, `JpaPagingItemReader` clears the persistence context / detaches entities after each page. Even so, lazy/eager associations can still materialize large object graphs or trigger N+1 queries if the processor traverses relationships deeply.

**When to use JDBC instead of JPA?**

- If you only need a few columns for a DTO/report, JDBC is usually simpler and avoids entity tracking overhead.
- If processing true domain entities requiring mapping/relationships and suitable JPQL already exists, JPA is convenient.
- If querying millions of rows without mutating entities, a DTO projection/JDBC reader is worth considering to curb memory and N+1 queries.
- If using complex native SQL or window functions, JDBC is usually easier to control.

With JPA readers, distinguish **query semantics**, persistence context lifecycle, transactions, and reader checkpointing. Never treat using an ORM as automatically providing snapshot consistency or safe restarts.

---

## 6. File Branch: FlatFileItemReader

### 6.1. A File Is a Resource, Not a SQL Table

`FlatFileItemReader` reads text files line/record by line/record and uses a `LineMapper` to map them to items. Key components:

- `Resource`: file location (e.g., `FileSystemResource`, `ClassPathResource`).
- `LineMapper`: converts a line into a domain object.
- `LineTokenizer`: splits CSV/fixed-width fields.
- `FieldSetMapper`: converts fields into Java types.
- `encoding`: charset of the input.
- `linesToSkip`: number of header/comment lines to skip.
- `strict`: policy when the resource does not exist.

CSV example:

```csv
id,customer_id,amount
1001,71,120.50
1002,72,0.00
1003,73,99.99
```

Reader:

```java
@Bean
@StepScope
FlatFileItemReader<OrderRow> fileOrderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile required");
    }

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("fileOrderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("id", "customer_id", "amount")
            .fieldSetMapper(fs -> new OrderRow(
                    fs.readLong("id"),
                    fs.readLong("customer_id"),
                    fs.readBigDecimal("amount")))
            .build();
}
```

Basic imports:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;
```

**Why `strict(true)`?** For a mandatory file, a missing input error should make the job fail clearly. `strict(false)` accepts a non-existent resource and treats the reader as empty; that is only appropriate when business rules define an absent input as valid and separate monitoring is in place.

### 6.2. CSV Is Not Always as Simple as split(",")

A CSV line can contain commas inside quoted fields, newlines inside quoted text, escaped quotes, a BOM, or non-UTF-8 encodings. For complex formats, configure `DelimitedLineTokenizer`/`RecordSeparatorPolicy` per contract; if data has RFC 4180-style quoting, test edge cases rather than calling `line.split(",")`.

Every file should have a **schema version/contract** specifying:

- Encoding (UTF-8 or another encoding).
- Whether a header is mandatory, column names, and order.
- Delimiter, quote/escape rules, newline convention.
- Date/time formats, timezone, and decimal separator.
- Null/empty values and maximum field lengths.
- Reject/skip policy for malformed records.
- Trailer row, record count, and checksum if present.

A file with the right name but wrong schema must still be caught before or during reading.

### 6.3. Files Must Be Complete and Immutable

Suppose a partner writes `orders.csv` into a directory; the batch job sees the file exists and starts reading while the partner has only written 60%. The reader may hit early EOF and finish the job with only 60% of the data.

You need a **"ready" protocol**:

```text
Producer:
    write orders-2026-11-15.csv.tmp
              │
              ▼
        flush + close
              │
              ▼
        checksum/manifest
              │
              ▼
    atomic rename / ready marker
              │
              ▼
Consumer:
    only pick up READY files
              │
              ▼
    verify fileId, size, checksum
              │
              ▼
    FlatFileItemReader
```

On object storage, rename may not be an atomic operation like on a local filesystem. You can upload objects under immutable keys and then publish a **manifest/ready object** after upload succeeds. Consumers only read objects recorded/signed as complete in the manifest.

### 6.4. Checksum and Versioning

At minimum, record:

```text
fileId=orders-VN-2026-11-15
objectKey=incoming/orders-VN-2026-11-15-v3.csv
sizeBytes=...
sha256=...
schemaVersion=3
businessDate=2026-11-15
recordCount=...
publishedAt=...
```

`SHA-256` detects byte changes from corruption or tampering **provided the expected checksum comes from a trusted source**. An attacker replacing both file and checksum is not stopped by an unsigned/unprotected manifest hash alone. For sensitive data, use TLS, access control, encryption, and signed/authenticated manifests per threat model.

On restart, you must **re-read the exact same file version**, same bytes, same parser configuration, and same file order. Never rely solely on wildcards or a `latest.csv` name that could point to a different object.

---

## 7. Multiple Files: MultiResourceItemReader

If a data period consists of hundreds of files sharing the same schema, `MultiResourceItemReader` can read multiple `Resource`s sequentially through a delegate like `FlatFileItemReader`.

```java
@Bean
@StepScope
MultiResourceItemReader<OrderRow> multiFileReader(
        @Value("#{jobParameters['inputDirectory']}") String directory) {

    Path root = Path.of(directory).toAbsolutePath().normalize();

    Resource[] resources = resolveFrozenManifest(root);
    // resolveFrozenManifest is an application-implemented business method:
    // retrieves the list of READY files from an immutable manifest.

    FlatFileItemReader<OrderRow> delegate =
            new FlatFileItemReaderBuilder<OrderRow>()
                    .name("fileDelegate")
                    .encoding(StandardCharsets.UTF_8.name())
                    .strict(true)
                    .linesToSkip(1)
                    .delimited()
                    .names("id", "customer_id", "amount")
                    .fieldSetMapper(fs -> new OrderRow(
                            fs.readLong("id"),
                            fs.readLong("customer_id"),
                            fs.readBigDecimal("amount")))
                    .build();

    return new MultiResourceItemReaderBuilder<OrderRow>()
            .name("multiFileReader")
            .resources(resources)
            .delegate(delegate)
            .build();
}
```

This is a guiding example: `resolveFrozenManifest(root)` must be implemented according to your project's manifest format and security rules, returning only `Resource`s that actually exist, are authorized, and do not change.

**Crucial restart detail:** Spring Batch enforces resource ordering via a comparator; however, if you add, remove, or replace files in the input set during a run or restart, the checkpoint position may no longer point to the same record. Therefore, **freeze the file list** from a manifest with stable file IDs/versions, process within a directory dedicated to that job instance, and clean up only after completion.

### 7.1. Partitioning by File

When there are many independent files, a common strategy is assigning each partition one file or a group of files:

```text
Manifest: 200 files
          │
          ▼
Partitioner
  ├─ partition-1 → files 001–025
  ├─ partition-2 → files 026–050
  ├─ partition-3 → files 051–075
  └─ ...
          │
          ▼
Workers (each partition has its own reader)
          │
          ▼
Writer/output per partition
          │
          ▼
Merge/publish when all succeed
```

Ensure outputs do not write concurrently to an unsynchronized shared target, partition IDs remain stable across restarts, and each file is processed only once per business rules. If there is only a single huge file, you can consider byte-range partitioning **when the format permits**; for CSVs with quoted newlines, splitting at arbitrary byte offsets can slice mid-record and corrupt data.

---

## 8. Data Consistency: The Difference That Often Decides

### 8.1. Same Query Does Not Guarantee Same Data Across Two Runs

On a live database:

```sql
SELECT id, customer_id, amount
FROM source_orders
WHERE business_date = DATE '2026-11-15'
ORDER BY id;
```

If a record is modified after the first page is read but before a later page executes, the batch job may process a mixed result set across two points in time. `ORDER BY id` only guarantees ordering within each query per DB semantics; it **does not freeze record contents**.

Options by consistency level:

1. **High-water mark:** lock `maxId` or `updatedAt cutoff` before the job, filtering only records within the published window.
2. **Snapshot/version column:** select a frozen data version.
3. **Database snapshot transaction/isolation:** leverage DB MVCC/snapshot capabilities, weighing long-lived transactions and resource load.
4. **Staging table:** copy target keys/data into a batch snapshot table, then read from that table.
5. **CDC/event log:** process changes via a stream with offsets/checkpoints; suitable when continuous sync is required over nightly snapshots.
6. **Immutable exported file:** freeze data into files and a manifest, and have the batch read only that snapshot.

A high-water mark like `id <= cutoffId` **only blocks inserts with higher IDs**; it does not prevent updates or deletes on older rows. If business rules require exact data at a point in time, you need a true snapshot/version or a source contract stating "historical data is immutable after cutoff."

### 8.2. Paging and Mutating Filter Predicates

Example query:

```sql
SELECT id, status, amount
FROM orders
WHERE status = 'NEW'
ORDER BY id;
```

If the step itself updates `status='PROCESSED'` after writing, OFFSET-based pagination over the `NEW` set can skip remaining rows as the result set shrinks.

`JdbcPagingItemReader` supports sort-key checkpointing, which avoids some pure-offset issues. Still, the design needs:

- A unique, stable sort key.
- State transitions that do not drop unread records from the reader's view.
- Assurance that no other process creates/modifies records in the processing window in a contract-breaking way.
- Testing with concurrent inserts/updates/deletes and restarts.

A reliable approach is **materializing the list of IDs to process** for each batch run in a staging table:

```sql
CREATE TABLE batch_run_items (
    run_id         VARCHAR(100) NOT NULL,
    order_id       BIGINT NOT NULL,
    PRIMARY KEY (run_id, order_id)
);
```

At startup, capture eligible IDs into `batch_run_items`; the reader fetches by stable `run_id` and `order_id`. If point-in-time column values are needed, snapshot the mutable columns too or record a version and query that version rather than IDs alone.

### 8.3. File Snapshots Are Not Safe If Overwritten

With files:

```text
JobExecution A:
   read file version v1 up to line 1,500,000
   crash

During downtime:
   producer replaces same-named file with v2
   adds/removes a line at the top

Restart:
   reader resumes at line position 1,500,001
   but that line belongs to different data
```

Line/position checkpoints become meaningless. Thus file snapshots must preserve their version, checksum, and contents until the job completes or the retention window ends. You need a manifest and immutable object keys, not merely "the same path as last time."

### 8.4. Alignment Between DB, File, and Business Logic

When switching from a DB reader to a file reader, ask:

- Does the file contain the exact records the SQL query previously fetched?
- Are filters for `businessDate`, `tenant`, and `status` applied at the same point in time and in the same timezone?
- Do table joins produce a consistent snapshot?
- Have null representations or decimal/date normalizations changed?
- If the file export fails halfway, will the consumer detect it?
- Which period do late-arriving records belong to?

A CSV file is not automatically equivalent to `"SELECT ..."` without an explicit export contract.

---

## 9. Restartability: What Does the Reader Save and What Must Be Protected?

### 9.1. ItemStream and ExecutionContext

Stateful readers typically follow this lifecycle:

```java
open(ExecutionContext context)
read()
read()
...
update(ExecutionContext context)
close()
```

Spring Batch manages checkpoints at appropriate step/transaction boundaries and persists metadata in `JobRepository`.

**Database cursor:** the reader can save its read count/position; on restart, the query must return compatible data and ordering. The reader does not "restore the exact physical connection/cursor" from the dead run.

**Database paging:** the reader saves state and the sort-key checkpoint; on restart, it requires a unique sort key and a stable dataset.

**Flat file:** the reader saves line/record position and stream state; on restart, it requires the same resource bytes, encoding, and parser semantics.

**Multi-file:** additionally requires stable resource ordering and the same input set.

### 9.2. saveState(false) Is Not a Free Speedup Button

`saveState(false)` may fit when the reader is coordinated externally, but disabling reader state usually **loses automatic checkpoint-based restartability**. In multi-threaded steps, some readers have specific state/thread-safety caveats; never toggle `saveState` without understanding recovery requirements.

Do not try to solve a race condition by turning off checkpoints and accepting full re-reads if your application has non-idempotent side effects.

### 9.3. Identifying JobParameters

A stable pattern:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSnapshotId", "snapshot-20261115-v1", true)
        .addString("requestedAtUtc", "2026-11-15T19:00:00Z", false)
        .toJobParameters();
```

`businessDate` and `sourceSnapshotId` identify the `JobInstance`; `requestedAtUtc` is observational metadata so each retry does not create a new instance.

If an instance fails, restarting must re-access **the exact same snapshot**. If the snapshot was deleted, never silently read "latest" and treat it as a safe restart.

### 9.4. File Paths Should Not Point to "latest"

Avoid:

```text
inputFile=/data/latest.csv
```

If `latest.csv` can be replaced, restarts are not guaranteed to read the same data. Prefer:

```text
inputFile=/data/snapshots/orders-2026-11-15-v1.csv
inputVersionId=...
inputSha256=...
```

If object storage provides a version ID, save the version ID safely per job and read that exact version on restart.

### 9.5. Output Idempotency Always Matters

A reader with solid checkpointing still does not fully prevent duplicate side effects:

- Chunk reads from DB, but the writer calls an external API that succeeds before the job rolls back.
- Flat file reader fails mid-chunk after the writer partially wrote an output file.
- Job restarts after output was published but before metadata finished updating.

Therefore, alongside the reader, design writers with business keys, unique constraints/upserts, outboxes, or conditional publishing. **End-to-end exactly-once does not emerge automatically from choosing a DB or file reader.**

---

## 10. Memory Usage and Performance

### 10.1. DB Cursor: fetchSize Is Not a Hard Cap

A JDBC driver may prefetch/buffer rows according to its own implementation. `fetchSize(500)` is only a hint. To verify true streaming:

- Read the documentation for the deployed JDBC driver and version.
- Check transaction/autocommit mode and cursor support.
- Measure live heap as the dataset scales 10x.
- Measure connection lifetimes and DB wait events.
- Check query plans, indexes, and throughput.

### 10.2. Database Paging: pageSize and Chunk Size Are Independent

Suppose `pageSize=2000` and `chunkSize=100`: the reader may hold many items from a page in memory across commits; lowering the chunk size does not necessarily shrink the entire working set. Conversely, `pageSize=100` and `chunkSize=1000` can cause one chunk to fire multiple queries.

| pageSize | chunkSize | What to Measure |
|---:|---:|---|
| 100 | 100 | Query count, latency, and GC |
| 500 | 500 | Balance of query round-trips vs. heap |
| 2,000 | 100 | Page buffer retained across multiple chunks |
| 100 | 2,000 | Multiple pages within a single transaction |
| 2,000 | 2,000 | Peak heap, transaction/DB load |

Do not pick parameters just because they are round numbers. Measure with p95/p99 record sizes, not just average size.

### 10.3. File Reader: Memory Scales with Record Size

`FlatFileItemReader` generally reads sequentially, but:

- An extremely long line can allocate large `String`/char arrays.
- Multiline quoted CSVs and parsers can buffer multiple lines.
- Mapping to deep object graphs makes items heavier than raw CSV bytes.
- Custom readers calling `Files.readAllLines()` destroy streaming.
- Decompression or JSON array parsers can spike memory sharply.

For multi-GiB files, avoid loading everything into a list or `byte[]` just to map records. For complex binary/JSON/XML, pick an appropriate streaming parser rather than forcing `FlatFileItemReader` on every format.

### 10.4. Choosing Based on Bottlenecks

| Bottleneck | Database reader | File reader |
|---|---|---|
| High DB CPU/IO/locks | Can offload to replica/staging/export file | Reading separate files offloads runtime queries |
| Slow network from DB to worker | Cursor/paging pays many DB round-trips or stream latency | Files can be staged near workers |
| Low storage throughput | DB can optimize scans/indexes | Disk/object store file reads can bottleneck |
| Expensive file export | Direct DB read avoids export wait | Needs investment in faster snapshot pipeline |
| Job needs parallel execution | ID/range partitioning and SQL indexes | File partitioning is clean when files are independent |
| High JVM memory | Reduce page/fetch size, use projections, trim JPA graphs | Bound record size, parser buffers, avoid preloading |
| Slow restarts | Stable keyset/snapshot, checkpoints | Immutable files, file offset/line, manifest |

If the workload is "report 100,000 records nightly," either approach is likely fast enough; pick the simpler one with a clear contract. If the workload is 5 billion records, snapshot, export, and partitioning architecture will matter far more than reader class choice.

---

## 11. System Coupling and Inter-System Architecture

### 11.1. DB Readers Couple Systems Directly

Reading the source database directly couples the batch job to:

- Database health and configuration.
- Schema/table/column layout and permissions.
- Indexes and query plans.
- Transaction isolation and OLTP load.
- Network connectivity, pooling, and credential rotation.
- Database maintenance windows.
- Cross-team schema compatibility policies.

Pros: no export/transfer pipeline needed, flexible querying, avoids temporary data duplication. Cons: source DB changes can break the batch directly. A data-owning team may also refuse to grant `SELECT` access on operational tables to another team.

### 11.2. Files Act as a Decoupled Exchange Contract

The partner produces versioned-schema files, publishes a manifest, and grants access to the consumer. The batch job needs no knowledge of the source DB's physical schema.

Pros:

- Reduces direct coupling to the source database.
- Easy to audit a specific snapshot version.
- Same snapshot can be distributed to multiple consumers.
- No need to hold connections to OLTP during processing.

Cons:

- Export, transfer, storage, and cleanup overhead.
- Data lags behind the live source.
- Requires versioning, schema validation, and manifests.
- Must handle late, missing, corrupt, partial, or duplicate files.

### 11.3. Combining Both Approaches

You do not always have to choose strictly one side. A common architecture:

```text
OLTP Database
     │
     ├── snapshot / SQL export / CDC
     ▼
Immutable staging data
     │
     ├── snapshot table / read replica
     │
     └── immutable files + manifest
              │
              ▼
         Spring Batch
              │
              ▼
        Target database / files
```

If SLAs are strict but you cannot query OLTP during the batch window, export/snapshot beforehand and read from files or staging tables. If there are only a few thousand records and the source is stable, building a dedicated snapshot pipeline can add unnecessary complexity.

---

## 12. Unified Design Example: Swap Reader, Keep Processor/Writer

Problem: generate an invoice table from finalized orders in a business period. Two authorized sources exist:

- `DB`: `source_orders` table containing `id`, `customer_id`, `amount`. The batch reads IDs not exceeding a predetermined `cutoffId`.
- `FILE`: an immutable CSV containing the exact three columns `id,customer_id,amount`.

Both options must produce the same `OrderRow` model.

### 12.1. Model

```java
package com.example.batch.design;

import java.math.BigDecimal;

public record OrderRow(
        long id, long customerId, BigDecimal amount) {}

public record InvoiceRow(
        long orderId, BigDecimal amountWithFee) {}
```

Stateless processor:

```java
@Bean
ItemProcessor<OrderRow, InvoiceRow> invoiceProcessor() {
    return order -> new InvoiceRow(
            order.id(),
            order.amount().multiply(new BigDecimal("1.05")));
}
```

For currency contracts with scale 2, explicitly define rounding:

```java
return new InvoiceRow(
        order.id(),
        order.amount()
                .multiply(new BigDecimal("1.05"))
                .setScale(2, RoundingMode.HALF_UP));
```

Use the rounding policy mandated by business rules; `HALF_UP` is merely illustrative.

### 12.2. Two Reader Implementations Under the Same Bean Name

Use Spring Boot `@ConditionalOnProperty` to register exactly one `orderReader` bean at context startup. For the file source, the path is resolved from `JobParameters`.

```java
package com.example.batch.design;

import java.nio.charset.StandardCharsets;

import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemStreamReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration(proxyBeanMethods = false)
class OrderReaderConfiguration {

    @Bean("orderReader")
    @StepScope
    @ConditionalOnProperty(
            prefix = "batch.input",
            name = "type",
            havingValue = "db")
    ItemStreamReader<OrderRow> dbOrderReader(
            DataSource dataSource,
            @Value("#{jobParameters['cutoffId']}") Long cutoffId) {

        if (cutoffId == null) {
            throw new IllegalArgumentException(
                    "cutoffId must be specified");
        }

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("dbOrderReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT id, customer_id, amount
                    FROM source_orders
                    WHERE id <= ?
                    ORDER BY id
                    """)
                .preparedStatementSetter(ps ->
                        ps.setLong(1, cutoffId))
                .rowMapper((rs, n) -> new OrderRow(
                        rs.getLong("id"),
                        rs.getLong("customer_id"),
                        rs.getBigDecimal("amount")))
                .fetchSize(500)
                .build();
    }

    @Bean("orderReader")
    @StepScope
    @ConditionalOnProperty(
            prefix = "batch.input",
            name = "type",
            havingValue = "file")
    ItemStreamReader<OrderRow> fileOrderReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException(
                    "inputFile must be specified");
        }

        return new FlatFileItemReaderBuilder<OrderRow>()
                .name("fileOrderReader")
                .resource(new FileSystemResource(inputFile))
                .encoding(StandardCharsets.UTF_8.name())
                .strict(true)
                .linesToSkip(1)
                .delimited()
                .names("id", "customer_id", "amount")
                .fieldSetMapper(fs -> new OrderRow(
                        fs.readLong("id"),
                        fs.readLong("customer_id"),
                        fs.readBigDecimal("amount")))
                .build();
    }
}
```

**Configuration notes:**

- Two beans share the name `orderReader` conditionally; only **one** should be registered per property value. Never enable both `db` and `file` simultaneously.
- `@StepScope` resolves `JobParameters` at step execution time. Never pull paths or cutoffs from static global mutable state.
- For `DB`, `cutoffId` blocks higher IDs as a high-water mark. It does not guard against updates/deletes on rows with smaller IDs.
- For `FILE`, the application must validate and freeze the input file before the step starts.
- In production multi-source setups, you can separate configs by profile/module instead of toggling readers with a single property; the choice depends on deployment and access control.

### 12.3. Shared Writer and Step

Example writing invoices to a JDBC target table with a unique key on `order_id`:

```java
package com.example.batch.design;

import java.math.BigDecimal;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemStreamReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
class InvoiceJobConfiguration {

    @Bean
    ItemProcessor<OrderRow, InvoiceRow> invoiceProcessor() {
        return order -> new InvoiceRow(
                order.id(),
                order.amount().multiply(new BigDecimal("1.05")));
    }

    @Bean
    JdbcBatchItemWriter<InvoiceRow> invoiceWriter(
            DataSource targetDataSource) {

        return new JdbcBatchItemWriterBuilder<InvoiceRow>()
                .dataSource(targetDataSource)
                .sql("""
                    INSERT INTO invoices (order_id, amount_with_fee)
                    VALUES (?, ?)
                    """)
                .itemPreparedStatementSetter((item, ps) -> {
                    ps.setLong(1, item.orderId());
                    ps.setBigDecimal(2, item.amountWithFee());
                })
                .build();
    }

    @Bean
    Step invoiceStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("orderReader")
                    ItemStreamReader<OrderRow> orderReader,
            ItemProcessor<OrderRow, InvoiceRow> invoiceProcessor,
            JdbcBatchItemWriter<InvoiceRow> invoiceWriter) {

        return new StepBuilder("invoiceStep", repository)
                .<OrderRow, InvoiceRow>chunk(500, transactionManager)
                .reader(orderReader)
                .processor(invoiceProcessor)
                .writer(invoiceWriter)
                .build();
    }

    @Bean
    Job invoiceJob(JobRepository repository, Step invoiceStep) {
        return new JobBuilder("invoiceJob", repository)
                .start(invoiceStep)
                .build();
    }
}
```

This pattern illustrates the abstraction. Projects must ensure `source_orders` and `invoices` exist, along with proper datasource/JDBC transaction settings and target schema. If source and target `DataSource`s are separate DBs, define transaction boundaries carefully; a local transaction manager does not atomically commit/roll back both DBs.

**Critical for restart:** a plain `INSERT` will fail if the target already holds an ID from a prior run. In production, design appropriate idempotency (unique keys, dialect-specific UPSERT, merge, or staging-and-publish) instead of blindly skipping all duplicate errors. Writer design is part of overall correctness.

### 12.4. Application Configuration

Select DB reader:

```yaml
batch:
  input:
    type: db

spring:
  batch:
    job:
      enabled: false
```

Or select file reader:

```yaml
batch:
  input:
    type: file

spring:
  batch:
    job:
      enabled: false
```

For DB:

```java
JobParameters dbParams = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("cutoffId", 9000000L, true)
        .toJobParameters();
```

For file:

```java
JobParameters fileParams = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSnapshotId", "orders-20261115-v2", true)
        .addString("inputFile",
                "/data/ready/orders-20261115-v2.csv", false)
        .toJobParameters();
```

An application normally selects one reader strategy per deployment/context. Do not assume changing `batch.input.type` between restarts of the same `JobInstance` is safe: doing so can change the dataset, reader state keys, and record ordering. To support restarts across deployment changes, preserve the same **source strategy and snapshot identity**, or implement controlled state migration.

### 12.5. When Are Two Readers Considered Equivalent?

Define a **source contract**:

```text
InputDatasetContract:
  businessDate         = 2026-11-15
  datasetId            = orders-20261115-v2
  expectedRecordCount  = ...
  schemaVersion        = 3
  orderingKey          = id (unique)
  amountScale          = 2
  timezone             = Asia/Ho_Chi_Minh
  allowedLateChanges   = false after cutoff
```

If the DB reader's query filters `status='SETTLED'` while the file export includes `PENDING`, the two readers are **not equivalent**, even though the Java model is identical. Verifying total counts, business keys, sums, and exceptions will expose discrepancies.

---

## 13. Performance and Operational Cost: How to Measure?

### 13.1. Metrics to Measure

| Metric | Database reader | File reader |
|---|---|---|
| Read throughput | Rows/s, query/page time | Lines/s, bytes/s |
| Processing throughput | Items/s after processor/writer | Same if pipeline is equivalent |
| Latency to first item | Open cursor / fetch page | File transfer/ready + open |
| End-to-end completion time | DB query + processing | Export + transfer + processing |
| Memory/GC | Driver/page/ORM object graph | Parser/line/object graph |
| Source system impact | DB CPU/I/O/locks/connections | Export DB load, storage/network |
| Restart cost | Re-query/reposition snapshot | Reopen/skip-to-line or resource checkpoint |
| Retry behavior | Connection lost, deadlock, timeout | Missing/truncated/corrupt file, remote storage error |
| Operational cost | DB capacity, read replica | Storage, retention, transfer, manifest |
| Data freshness | Query/commit timestamp | Snapshot ready timestamp |
| Correctness | Missing/duplicate by business key | Count/hash/schema/version |

If you only measure `invoiceStep` after the file is ready, the file reader may look faster while hiding a 40-minute export. When choosing an architecture, measure **from the time the business needs the data until final output is ready**, not just `JobExecution` duration.

### 13.2. Representative Benchmark

Example measurement plan:

1. Pick datasets of 1M, 10M, and 50M items as environment capacity allows.
2. Use the exact same business contract and writer.
3. For DB, test cursor `fetchSize` 100/500/1000; paging `pageSize` 100/500/1000.
4. For files, test local SSD, object storage staging, and multi-file partitions.
5. Keep heap/GC, thread count, DB workload, and target schema constant.
6. Measure p50/p95 latency, max heap, GC pauses, DB CPU/I/O, network, and file transfer.
7. Trigger retries/restarts after deliberate mid-run failures.
8. Verify output data using business keys and total sums, not just `COMPLETED` status.

Empirical results template:

| Reader | Input size | Export/prepare time | Step runtime | Peak heap | Source load | Restart time |
|---|---:|---:|---:|---:|---|---:|
| JDBC cursor | 10M | 0 | Measure | Measure | Measure | Measure |
| JDBC paging | 10M | 0 | Measure | Measure | Measure | Measure |
| Flat file SSD | 10M | Measure | Measure | Measure | Measure | Measure |
| File via object storage | 10M | Measure | Measure | Measure | Measure | Measure |

Never fill in fake numbers as benchmarks. A valid benchmark requires data, drivers, databases, storage, and networks matching production.

### 13.3. Variables That Skew Benchmarks

- Warm vs. cold DB buffer cache.
- JIT/JVM warm-up and GC ergonomics.
- DB replica replication lag.
- File sitting in OS page cache.
- Network bandwidth / SFTP throttling.
- Different SQL plans/indexes across environments.
- Concurrent jobs running at the same time.
- Row graph size and malformed record ratio.
- Chunk size and writer commit frequency.

Run multiple iterations and report results alongside exact configurations. A reader that is fast on small data may become unstable at 10x scale.

---

## 14. Architecture for Very Large Datasets

### 14.1. Key-Based Database Partitioning

One partitioning layout:

```text
Snapshot run S-20261115
       │
       ├─ partition A: id 1 ... 1,000,000
       ├─ partition B: id 1,000,001 ... 2,000,000
       ├─ partition C: id 2,000,001 ... 3,000,000
       └─ ...
                │
                ▼
         Dedicated reader per partition
                │
                ▼
       Independent process / write
```

Requirements:

- Ranges must be **non-overlapping** and cover all target keys.
- Stable snapshot and predicates.
- Do not assume contiguous IDs unless guaranteed.
- Cap concurrent connections and queries so the DB is not overloaded.
- Each partition's reader/`ExecutionContext` must have a stable identity on restart.

If source keys are skewed, min/max range splitting can create hotspots in some partitions; consider quantile-based distribution, hash partitioning, or materialized key lists.

### 14.2. File Partitioning

If a dataset is exported into 100 comparably sized immutable files, each partition can handle a subset of files:

```text
Manifest + checksums
     │
     ▼
File partitioner
  ├─ worker 1 → files 1-25
  ├─ worker 2 → files 26-50
  ├─ worker 3 → files 51-75
  └─ worker 4 → files 76-100
     │
     ▼
Output staging / merge / publish
```

Guarantees:

- Manifest version and file list never change on restart.
- No single file is processed by two workers unless proper idempotency is in place.
- Partition outputs are not mixed or duplicated; publish only after all parts succeed.
- Total record count and checksums match the manifest.
- Late-arriving files are not injected into an in-flight batch.

### 14.3. When Streaming/CDC Beats Both

If requirements demand near real-time updates every few seconds, rescanning a 100M-row table every minute or continuously exporting full CSVs wastes resources. A CDC/event-driven pipeline may be better suited for incremental capture, with Spring Batch handling initial backfills, snapshots, or periodic reconciliation.

This does not mean "Batch cannot handle streaming": Spring Batch can run incremental micro-batches using watermarks or time windows. However, when the source mutates constantly, you need a reliable **change log/offset** so updates and deletes are never missed.

---

## 15. Security and Source Ownership

### 15.1. Database Reader

Permissions should follow least privilege:

- `SELECT` only on required views/tables.
- Only permitted columns/fields; avoid `SELECT *`.
- For multi-tenant data, enforce predicates/row-level security and parameterization.
- Use managed credentials/workload identities with rotation and auditing.
- Never log SQL parameters containing PII or secrets.
- For DB replicas, confirm data policies and acceptable replication lag.
- Never grant update privileges just to support a reader unless strictly required.

### 15.2. File Reader

Controls:

- TLS/SFTP/mTLS in transit.
- Bucket/object ACLs with least-privilege prefix/file access.
- Encryption at rest and application-level encryption if required by contract.
- Signed manifests/checksums from a trusted source.
- Path allowlists to prevent path traversal and symlink attacks.
- Staging directory permissions, file retention windows, and quarantine.
- Never store raw PII files in public buckets or broadly shared folders.
- Never log entire malformed CSV lines containing PII.

### 15.3. Do Not Store Secrets in JobParameters

`JobParameters` are persisted by Spring Batch in the repository. They are suitable for `businessDate`, `snapshotId`, `fileId`, cutoff IDs, or validated paths, **not for raw database passwords, API tokens, or AES keys**.

If object names or paths contain sensitive details, avoid displaying them raw in dashboards or logs. Use logical file IDs and an authorized resolution service.

---

## 16. Ready Files, Schemas, and Error Handling

### 16.1. File Exists Without a Valid Contract

A file can exist in full yet be wrong:

- Non-UTF-8 encoding.
- Renamed or reordered header columns.
- Date values in an unexpected timezone.
- Decimal values using commas as separators.
- Record count mismatches the manifest.
- Duplicate business keys.
- Right filename, wrong business date.
- Invalid footer/trailer.

A pre-read validation step should check format, version, metadata, and cutoff. For sensitive data, verify signatures/authenticated encryption before trusting contents.

### 16.2. DB Schema and Query Versioning

A DB schema change dropping `customer_id` can crash the reader at startup. You need contracts and migrations:

- Use versioned stable views to decouple batch jobs from internal tables.
- Use explicit column selection and mapping.
- Test queries against schema migrations.
- Coordinate producer/consumer rollouts.
- Establish schema compatibility policies (column additions, renames, type changes).

### 16.3. Skip and Retry Policies

| Failure | DB reader | File reader |
|---|---|---|
| Temporary source unavailability | DB timeout/connection error; bounded retry | SFTP/object storage timeout; bounded retry |
| Schema mismatch | SQL mapping/type mismatch | Malformed CSV / header mismatch |
| Missing input | Missing table/query/snapshot, per contract | Missing resource or manifest |
| Source changed on restart | Query returns a different set | File bytes or line order changed |
| Individual bad record | RowMapper/field conversion failure | LineMapper/FieldSet conversion failure |
| Severe source corruption | DB failover, lost snapshot | Truncated file / checksum failure |

**Skip only when business rules allow dropping a record.** Never use `skipLimit` to hide a truncated file or a mutated database snapshot. Dataset-level errors generally require failing the entire job, quarantining, and investigating.

---

## 17. Testing the Design: What Must Be Proven?

### 17.1. Reader Unit Tests

For `FlatFileItemReader`:

- Header is skipped accurately.
- ID/decimal/date types map accurately.
- UTF-8 accented/multibyte characters read properly.
- Edge-case lines, quoted delimiters, and malformed data follow policy.
- EOF returns `null`.
- `strict(true)` throws on missing resources.
- State saves and restores via `ExecutionContext` on unchanged input.

For `JdbcCursorItemReader`/`JdbcPagingItemReader`:

- SQL filters `businessDate`/`cutoffId` accurately.
- Ordering by unique key.
- No skipped or duplicated rows across pages.
- Empty result returns `null`.
- Connection errors propagate properly.
- Restart resumes at the correct position.
- SQL NULL/decimal/timestamp mapping is exact.

### 17.2. Two-Source Equivalence Integration Test

Given the same 4-record snapshot:

```csv
id,customer_id,amount
1001,71,120.50
1002,72,0.00
1003,73,99.99
1004,74,5.25
```

Insert four matching rows into `source_orders` in a test H2/PostgreSQL database. Run both reader configurations in **two separate contexts/test runs** with the same processor and writer, using isolated target tables or cleanups. Assertions:

- `readCount=4` and `writeCount=4`.
- Output `order_id` sets are identical.
- Total `amountWithFee` matches per rounding policy.
- Ordering matches if required by contract; never rely on arbitrary ordering.
- Job status is `COMPLETED`.
- Zero duplicate records.
- `businessDate`/`cutoffId`/`snapshotId` match the fixture.

### 17.3. FlatFile Restart Test

Procedure:

1. Read several items with `FlatFileItemReader` and persist checkpoints through a real step.
2. Force the writer to fail in a controlled way.
3. Restart with the same `JobInstance` and exact same file checksum.
4. Assert final output is accurate with no missing or duplicate items.
5. Modify a line near the top of the file between runs and prove the restart contract was violated—the system should block via checksum/version rather than silently processing misaligned data.

### 17.4. Paging Restart Test

Procedure:

1. Run paging reader with a unique sort key.
2. Fail after several chunks.
3. Restart on an immutable dataset and assert complete output.
4. Test inserting rows above the cutoff, updating old rows, and deleting old rows; document expected behavior per snapshot contract.
5. Avoid assuming "having a cutoffId means an immutable snapshot" if updates/deletes are still allowed.

### 17.5. Missing/Late File Tests

- No ready marker yet: do not run or fail per policy; never treat an empty/absent file as success.
- File exists but upload is in progress: consumer does not open it.
- Record count/checksum mismatch: fail and quarantine.
- Manifest changed between restarts: reject or require an explicit reprocess decision.
- Extra file arrives after manifest freeze: process in the next period, never inject into an existing instance.

### 17.6. DB Load and Transaction Tests

Do not test correctness alone: benchmark with large data to inspect SQL query plans, connection counts, DB CPU, locks, rows scanned, fetch times, heap, GC, throughput, and impact on OLTP. A query that returns right results while stalling the transactional system by 5 seconds is not an acceptable design.

---

## 18. Real-World Selection Scenarios

### Scenario A — End-of-Day Financial Reporting from OLTP

Requirements:

- 20 million transactions/day.
- Must not add significant load to the transactional DB during peak hours.
- Must audit each day's exact dataset.
- Must rerun the exact period within 90 days.

**Design worth considering:** create a snapshot on a read replica/staging table or export immutable files with a manifest, then run `FlatFileItemReader`/`MultiResourceItemReader`. If using a DB reader, prove replica/snapshot isolation and acceptable query cost.

The decision depends on existing snapshot infrastructure, export speed, and late-arriving data.

### Scenario B — Cleaning 100,000 Records in a Staging Table

Requirements:

- Data is imported through a single workflow with no concurrent updates.
- The same system owns both the staging table and the batch job.
- No need to share the dataset externally.
- Fast implementation with minimal tooling desired.

**Design worth considering:** `JdbcPagingItemReader` or `JdbcCursorItemReader` with stable queries/indexes; avoid creating an unnecessary file export step. Use `cutoffId`, run ID, or staging snapshot ID if reruns are needed.

### Scenario C — Partner Sends CSV Over SFTP

Requirements:

- Partner sends one signed/checksummed file daily.
- No access to the partner's database.
- Must retain original source data evidence.

**Choosing a file reader** is almost obvious after an ingestion/validation step. You need a ready protocol, encryption/ACLs, header/schema versioning, file ID and checksum auditing, and quarantine for bad files.

### Scenario D — Continuously Mutating Data Requiring Sub-Minute Sync

Requirements:

- Frequent updates/deletes on the same business key.
- End-to-end latency under one minute.
- Hourly full snapshots are too expensive.

**Consider CDC/incremental event pipelines** rather than full DB scans or full file exports. Spring Batch remains valuable for initial backfills and reconciliation, while nightly snapshots will not meet latency SLAs.

### Scenario E — Highly Relational JPA Model When Only Three Columns Are Needed

If a job only extracts `id`, `totalAmount`, and `businessDate` from 5 million entities, `JdbcPagingItemReader` with a projection can cut memory and N+1 queries compared to loading full JPA entities. If complex domain rules tied to the entity are required, JPA can make sense—provided you test lazy associations, detached entities, and page sizes.

### Scenario F — Large 100 GiB File on Object Storage

Streaming an `InputStream` from object storage into `FlatFileItemReader` requires analyzing reopen/restart behavior and durability. A practical approach is staging immutable objects onto managed local disk, validating checksums, and partitioning by file. With direct object storage readers, design retry/seek/range handling and pin version IDs to avoid reading a mutated `latest` object.

---

## 19. Decision Framework and Weighted Scoring

There is no answer to "which reader is better" without prioritizing requirements. Use a weighted scoring matrix.

Example for a reconciliation job:

| Criterion | Weight | DB reader (1–5) | File reader (1–5) |
|---|---:|---:|---:|
| Exact snapshot/replay | 5 | 3 | 5 |
| Zero added OLTP load | 5 | 2 | 5 |
| Data freshness | 3 | 5 | 3 |
| Fewer auxiliary pipelines | 2 | 5 | 2 |
| Source file audit | 4 | 3 | 5 |
| Parallel execution | 3 | 4 | 4 |
| Storage cost | 2 | 4 | 2 |
| Schema flexibility | 2 | 4 | 3 |

**These scores are illustrative assumptions**, not an objective rating of every database or file setup. Each team must substitute weights and scores based on real measurements and constraints. There may also be *hard constraints* that disqualify an option immediately: for example, a partner refuses DB access, or regulations forbid plaintext snapshots outside a secure zone.

### 19.1. Decision Workflow

```text
Confirm business contract
         │
         ▼
Is data already in immutable files?
    ├─ Yes → File reader + validate manifest
    └─ No
         │
         ▼
Is batch authorized/responsible to query DB?
    ├─ No → Snapshot/export API/file
    └─ Yes
         │
         ▼
Is dataset stable across full job & restarts?
    ├─ No → Snapshot/version/staging/CDC
    └─ Yes
         │
         ▼
Evaluate volume, SLA, concurrency, DB load
         │
         ├─ Direct DB read suffices → JDBC cursor/paging/JPA
         └─ High DB load or multi-consumer → Export file/snapshot
         │
         ▼
Benchmark + test restart/idempotency
         │
         ▼
Finalize ADR + runbook + monitoring
```

If both options meet requirements, prefer the lower total lifecycle cost (export, transfer, processing, auditing, maintenance, failure recovery), not merely fewer lines of reader config.

---

## 20. Sample Architecture Decision Record (ADR)

```markdown
# ADR-012: Reader Selection for Daily Settlement Batch

## Status
Accepted

## Context
- Source: PostgreSQL OLTP, ~12 million transactions/day.
- Data cut-off: 23:59 in business timezone.
- Runtime window: under 90 minutes.
- Must not degrade OLTP latency.
- Must replay the exact dataset for 60 days.

## Options
1. JdbcCursorItemReader directly against OLTP.
2. JdbcPagingItemReader against a read replica/snapshot.
3. Snapshot to immutable files and use FlatFileItemReader.

## Decision
Choose Option 3 provided the file export pipeline meets SLA and
snapshot contracts are enforced via ready manifests,
checksums, and object version IDs.

## Rationale
- Offloads OLTP during batch execution.
- Provides immutable source artifacts for auditing and restarts.
- Simplifies distribution to authorized downstream consumers.

## Risks and Mitigations
- Late export: alert on missing input/ready marker.
- Corrupt file: checksum/schema validation and quarantine.
- Storage growth: retention policies, backup, and cleanup.
- Restart: pin object version + checksum in metadata.

## Re-evaluation Triggers
- Export exceeds 30 minutes or end-to-end SLA is missed.
- Dataset grows 5x.
- Read replica offers significantly cheaper snapshot queries.
```

Your ADR does not have to match the choice above. Stating explicit re-evaluation triggers prevents an architectural decision from turning into a rigid dogma as the system evolves.

---

## 21. Failure Runbooks by Read Source

### 21.1. Database Reader Timeout or DB Failover

1. Confirm `JobExecutionId`, `StepExecution`, and query/cutoff/snapshot ID.
2. Distinguish transient timeout, DB failover, deadlock, and permission/schema errors.
3. Inspect DB primary/replica health, query plan, connection pool, and isolation level.
4. Before restarting, ensure the dataset/snapshot has not changed or a clear recovery policy exists.
5. Relaunch with the same identifying parameters when valid.
6. Reconcile counts, business keys, and output idempotency.

Never alter the cutoff just to "keep going" without understanding the impact on the dataset.

### 21.2. Missing/Corrupt or Mid-Run Modified File

1. Verify ready manifest and file ID/version.
2. Check byte length, checksum, schema version, and record count.
3. Inspect access permissions, encryption, and transfer status.
4. Never silently use `strict(false)` to turn a missing file into empty input.
5. Quarantine corrupt files, request redelivery, or fall back to an approved prior snapshot.
6. Restart only after restoring the exact file version/checksum; if a new snapshot arrives, initiate an explicit reprocess workflow.

### 21.3. Missing/Duplicate Output

1. Separate reader causes (missing input, wrong cursor/page/file ordering) from writer causes (duplicate publish, transaction boundaries).
2. Inspect `readCount`, `writeCount`, `filterCount`, and `skipCount`.
3. Reconcile business key sets, not just raw counts.
4. Identify which chunks/partitions committed.
5. Fix idempotency or the snapshot contract before restarting.
6. Run reconciliation and save audit records.

---

## 22. Practice Exercises

### Exercise 1 — Choose Readers for Three Systems

Select a reader for: (a) a stable 100,000-row staging table, (b) a partner sending 100 signed CSVs, (c) an OLTP database with 20M transactions/day under continuous updates. Document criteria, risks, and decision conditions.

### Exercise 2 — JDBC Cursor

Implement `JdbcCursorItemReader` for an `orders` table reading 1 million rows with `fetchSize=100/500/1000`. Measure throughput, heap, and DB connection lifetime. Verify whether the driver streams as expected.

### Exercise 3 — JDBC Paging

Use `JdbcPagingItemReader` with a unique `id` sort key. Test page sizes 100/500/2000, crash mid-job, and restart. Test inserting IDs above cutoff and updating/deleting older rows; explain the consistency policy.

### Exercise 4 — File Reader

Create a UTF-8 CSV with header, quoted commas, malformed rows, and negative/zero amounts. Configure the reader and test mapping, EOF, strict mode, and skip policy.

### Exercise 5 — MultiResourceItemReader

Create three files and a manifest in stable order. Fail mid-way through the second file and restart. Add a new file to the directory while keeping the old manifest; verify the new file is not pulled into the active instance.

### Exercise 6 — Two Sources, One Output

With the same dataset, run one job using a DB reader and another using a file reader. Assert identical sets of business IDs, counts, total amounts, and outputs. Compare error and duplicate handling as well.

### Exercise 7 — Mutating Source

Update row `status`/`amount` in the database while paging is running. Design a snapshot table/version or suitable isolation to produce accurate point-in-time output.

### Exercise 8 — Unready File

Simulate an in-progress producer upload. Write a validation step allowing the job to open the resource only after receiving a valid manifest/ready marker and checksum; assert it does not run on a partial file.

### Exercise 9 — Partitioning and Performance

Partition 20 million records by ID range and then by multiple files. Benchmark 1, 4, and 8 workers across heap, DB I/O, storage throughput, output correctness, and restarts. Identify where concurrency slows the system down.

### Exercise 10 — ADR

Write a one-page ADR for your real project including weighted criteria, decision, benchmark measurements, and re-evaluation triggers. Finalize an option only when restartability and data correctness are verifiable.

---

## 23. References

- [Spring Batch — Database ItemReaders and ItemWriters](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): JDBC cursor/paging, `PagingQueryProvider`, `JpaPagingItemReader`, and unique sort key notes.
- [Spring Batch — FlatFileItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html): Resource, encoding, strict mode, line mapping.
- [Spring Batch — Multi-File Input](https://docs.spring.io/spring-batch/reference/readers-and-writers/multi-file-input.html): `MultiResourceItemReader`, resource ordering, and restart.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open/update/close` and execution context.
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): read/process/write within chunk transactions.
- [Spring Batch — Database Reader API 5.2](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/database/JdbcPagingItemReader.html): JDBC paging reader behavior and restart.
- [Spring Batch — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning and concurrency.
- [Spring Batch — Job Repository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): checkpoint metadata, transactions, and restart support.
- [Spring Batch — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, and job/step testing.

**Conclusion:** choosing a database or file reader must stem from the **dataset contract, snapshot consistency, restart requirements, source system load, and end-to-end SLA**. Database readers offer SQL filtering and access to fresh data, but require tight control over queries, sort keys, isolation, and concurrent mutations. File readers excel when data is frozen, shared, and audited, but require manifests, immutability, schema validation, and policies for missing or corrupt files. The right choice is the option you can fully verify for **no missing reads, no duplicate reads, recoverability, and acceptable operational cost**—not simply the reader class with the fewest lines of code.
