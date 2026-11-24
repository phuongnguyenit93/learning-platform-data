# Readers for Files, Databases, and Resources

In Spring Batch, `ItemReader<T>` is the component that supplies input items one at a time to a chunk-oriented step. Data can come from a text file, a database, XML, or a resource that Spring represents through the `Resource` abstraction. Choosing the right reader directly affects performance, resource management, restartability, and job stability.

Spring Batch provides many ready-made readers. Instead of writing your own file-reading loop or database query in a tasklet, the application can choose an appropriate reader and combine it with an `ItemProcessor` and an `ItemWriter`. The framework coordinates chunk-based reading, manages transactions, and saves execution state.

## 1. The Role and Contract of ItemReader

The core interface looks like this:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Each time Spring Batch calls `read()`, the reader returns the next item. When there is no more data, the reader returns `null` to signal the end of input. `null` is a control signal in the reader contract; do not use it to represent a record whose data fields are empty.

For example, an order reader may return in turn:

```text
read() -> OrderInput("O-001", "C-101", 250000)
read() -> OrderInput("O-002", "C-102", 180000)
read() -> OrderInput("O-003", "C-103", 99000)
read() -> null
```

A reader usually focuses on fetching data and mapping the source structure into items. Business rules such as checking amounts, classifying orders, or calculating tax usually belong to the `ItemProcessor`.

Some readers also implement `ItemStream` to manage the resource lifecycle and restart state. The important callbacks are `open`, `update`, and `close`: open the resource/restore state, write the checkpoint into the `ExecutionContext`, and release resources.

## 2. What Is a Resource in Spring?

`Resource` is a Spring abstraction used to describe an input resource. It helps code avoid being tightly dependent on a specific kind of location such as a file path on a machine. A `Resource` can represent a file in the filesystem, a file on the classpath, a URL, or data held in memory.

Common implementations:

| Resource | How the resource is identified | Use case |
|---|---|---|
| `FileSystemResource` | A file path on the filesystem | Input files that are uploaded or placed in a data directory. |
| `ClassPathResource` | A resource on the application's classpath | Configuration files or sample data packaged with the application. |
| `UrlResource` | A URL such as HTTP or another supported protocol | Resources with a URL address; consider stability and whether it can be accessed again. |
| `ByteArrayResource` | A byte array in memory | Small data that is already available in memory. |
| `InputStreamResource` | An InputStream that has already been provided | A data stream created by another component; usually readable only once. |

`Resource` describes where the data comes from; it is not itself an `ItemReader`. For example, `FlatFileItemReader` uses a `Resource` to open a file and read it line by line.

Example of creating resources:

```java
Resource fileResource = new FileSystemResource("data/orders.csv");
Resource classpathResource = new ClassPathResource("samples/orders.csv");
```

With a classpath resource, the application can usually only read it; do not assume you can overwrite a resource packaged inside a JAR. For an input file uploaded by a user, `FileSystemResource` or a resource corresponding to durable storage is usually more appropriate.

### Resource and the Ability to Reopen a Stream

A reader may need to reopen a resource on restart or when the framework re-initializes the step. Therefore, the Resource type must support opening a stream in an appropriate way. `InputStreamResource` usually represents an already existing stream that cannot be reopened multiple times. If restart is needed, use a resource that can be reopened such as `FileSystemResource`, or design your own mechanism to save and restore the data source.

With `UrlResource`, consider whether the URL's content may change or whether it may be temporarily inaccessible. A job reading directly from a URL may encounter different content on restart. For important data, a safer approach is usually to download it to immutable storage, determine a batch/file ID, and then process from that stored copy.

## 3. Reading Text Files with FlatFileItemReader

`FlatFileItemReader<T>` is a common reader for reading text files line by line. It can use a line mapper to convert a line into a Java object. For CSV or files with delimiter characters, the builder supports declaring column names and mapping a `FieldSet`.

Suppose the file `orders.csv` has the following content:

```csv
order_id,customer_id,amount
O-001,C-101,250000
O-002,C-102,180000
O-003,C-103,99000
```

The object that receives the data:

```java
public record OrderInput(
        String orderId,
        String customerId,
        BigDecimal amount) {
}
```

The reader can be declared as follows using the Spring Batch 5 API:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderFileReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderFileReader")
            .resource(new FileSystemResource(inputFile))
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fieldSet -> new OrderInput(
                    fieldSet.readString("orderId"),
                    fieldSet.readString("customerId"),
                    fieldSet.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

Explanation of the configuration:

- `name`: a stable reader name, used to identify the stream's state in the metadata.
- `resource`: the resource containing the file to read.
- `encoding`: the character set used to decode the file content.
- `linesToSkip(1)`: skips the CSV header line.
- `delimited()`: declares that the data has delimited fields.
- `names(...)`: the column names in order of appearance.
- `fieldSetMapper(...)`: converts each parsed line into an `OrderInput`.
- `saveState(true)`: allows saving the read state to support restart.

`@StepScope` allows the reader to be created when the step execution starts and gets the `inputFile` value from JobParameters by late binding. If the file path changes with each run, do not create a fixed singleton reader with a value that is known only at runtime.

### Useful FlatFileItemReader Options

| Option | Meaning |
|---|---|
| `encoding` | Chooses the encoding, for example UTF-8. |
| `linesToSkip` | Skips a number of leading lines, usually the header. |
| `comments` | Declares the prefixes of comment lines to be skipped. |
| `strict` | Specifies how to handle the case where the resource does not exist or cannot be opened, according to the configuration. |
| `saveState` | Enables or disables saving state for restart. |
| `recordSeparatorPolicy` | Controls how record boundaries are recognized, useful for multi-line records. |
| `lineMapper` | Maps a line to an object, and can be combined with a tokenizer and a field set mapper. |

When the data contains commas inside strings enclosed in double quotes, you need to configure a tokenizer appropriate to the actual CSV format. Do not split strings with `String.split(",")` because that simple approach does not fully handle double quotes, escape characters, and empty fields.

### Handling File and Data Line Errors

A file may not exist, may have the wrong encoding, may be missing columns, or may have values that cannot be converted. `FlatFileItemReader` may raise exceptions related to opening the resource or parsing a line, for example `FlatFileParseException`.

You should distinguish source errors from business errors:

- A file that does not exist or cannot be opened is usually an input/infrastructure error that should make the job fail.
- A line with an incorrect structure can be skipped if the business allows it and there is a mechanism to record the error.
- A line with a valid structure but that violates business rules is usually checked in the processor.

Do not skip every file-reading error. If the file is truncated or has the wrong encoding, continuing to process may produce results with missing data that go undetected.

## 4. Reading Multiple Files with MultiResourceItemReader

When a job needs to read multiple files of the same format, `MultiResourceItemReader<T>` can supply each resource in turn to a delegate reader. For example, a directory containing order files by day or by partition.

```text
orders-001.csv --+
orders-002.csv --+--> MultiResourceItemReader
orders-003.csv --+           |
                             v
                     FlatFileItemReader
                             |
                             v
                       each OrderInput
```

Example configuration with a set of resolved resources:

```java
@Bean
MultiResourceItemReader<OrderInput> multiOrderReader(
        Resource[] orderFiles,
        FlatFileItemReader<OrderInput> orderFileDelegate) {

    return new MultiResourceItemReaderBuilder<OrderInput>()
            .name("multiOrderReader")
            .resources(orderFiles)
            .delegate(orderFileDelegate)
            .build();
}
```

`orderFiles` can be created from `PathMatchingResourcePatternResolver`, application configuration, or a component that prepares the input. The `FlatFileItemReader` delegate is responsible for reading the content of each file. `MultiResourceItemReader` manages the order of the resources and the state of moving from one file to another.

The resource order must be stable between the first run and the restart. If the file list changes or the order is changed while the job is processing, the checkpoint may no longer point to the same data set. You should fix the list of files for a batch, sort them by a deterministic rule, and keep those files unchanged until the job ends.

If each file has a header, the delegate needs to be configured to skip the header for each resource. At the same time, make sure the delegate reader supports a resource-aware lifecycle so that it receives the correct current resource.

## 5. Reading XML from a Resource with StaxEventItemReader

When the source is XML, `StaxEventItemReader<T>` can read XML elements in a streaming fashion. The reader uses StAX to process each fragment instead of loading the entire XML document into memory.

XML example:

```xml
<orders>
    <order>
        <orderId>O-001</orderId>
        <customerId>C-101</customerId>
        <amount>250000</amount>
    </order>
    <order>
        <orderId>O-002</orderId>
        <customerId>C-102</customerId>
        <amount>180000</amount>
    </order>
</orders>
```

The reader can be configured to take each `order` element as a fragment and use an `Unmarshaller` to convert the fragment into an object:

```java
@Bean
@StepScope
StaxEventItemReader<OrderXml> orderXmlReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        Unmarshaller orderUnmarshaller) {

    return new StaxEventItemReaderBuilder<OrderXml>()
            .name("orderXmlReader")
            .resource(new FileSystemResource(inputFile))
            .addFragmentRootElements("order")
            .unmarshaller(orderUnmarshaller)
            .saveState(true)
            .build();
}
```

The `Unmarshaller` needs to be configured to map the XML fragment to the `OrderXml` type. With large XML, streaming reduces the need to keep the entire document in memory. You need to check the namespace structure, the fragment name, the encoding, and how invalid XML is handled.

## 6. Reading a Database with JdbcCursorItemReader

`JdbcCursorItemReader<T>` uses a JDBC cursor to read query results in a forward direction. The reader opens a `ResultSet`, and each `read()` call takes the next row and maps it to a Java object.

For example, the `orders` table has the columns `order_id`, `customer_id`, `amount`, and `status`. The reader can fetch orders that are waiting to be processed:

```java
@Bean
JdbcCursorItemReader<OrderInput> orderCursorReader(DataSource dataSource) {
    return new JdbcCursorItemReaderBuilder<OrderInput>()
            .name("orderCursorReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT order_id, customer_id, amount
                    FROM orders
                    WHERE status = ?
                    ORDER BY order_id
                    """)
            .preparedStatementSetter(
                    ps -> ps.setString(1, "READY"))
            .rowMapper((rs, rowNum) -> new OrderInput(
                    rs.getString("order_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount")))
            .fetchSize(500)
            .saveState(true)
            .build();
}
```

Main components:

- `dataSource`: the datasource used to create JDBC connections.
- `sql`: the query that fetches the data.
- `preparedStatementSetter`: assigns values to the SQL parameters.
- `rowMapper`: maps each ResultSet row to an object.
- `fetchSize`: a hint to the JDBC driver about the number of rows to fetch at a time; the specific behavior depends on the driver and the database.
- `saveState`: allows saving the read position to support restart.

### Advantages and Limitations of the Cursor Reader

A cursor reader can read a large result set without loading all rows into a collection in the application. It suits queries with a stable order and when the database/driver supports cursors efficiently.

However, a cursor usually holds the ResultSet and the connection for the entire duration of reading. For a long-running job, this can hold a connection for a long time and affect the pool or the database's resource limits. You need to understand how the driver handles fetch size, transactions, and cursors; some drivers require specific transaction or fetch size configuration for streaming to actually be effective.

`ORDER BY` should have a stable order. If multiple rows have the same sort value, add a unique key as a secondary criterion so that the results have a deterministic order. This is especially important when checkpoint and restart are needed.

## 7. Reading a Database by Page with JdbcPagingItemReader

`JdbcPagingItemReader<T>` splits the query into multiple pages. Each time it fetches a page, the reader executes a paged query and maps the rows to items. This approach avoids having to keep a cursor open for the entire reading time.

Example:

```java
@Bean
JdbcPagingItemReader<OrderInput> orderPagingReader(DataSource dataSource) {
    return new JdbcPagingItemReaderBuilder<OrderInput>()
            .name("orderPagingReader")
            .dataSource(dataSource)
            .selectClause("select order_id, customer_id, amount")
            .fromClause("from orders")
            .whereClause("where status = :status")
            .parameterValues(Map.of("status", "READY"))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new OrderInput(
                    rs.getString("order_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount")))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

A paging reader needs to know how to paginate in a way appropriate to the database. Spring Batch uses a `PagingQueryProvider` to create the query corresponding to the configured database management system. The select, from, where, and sort key parts determine the data set as well as the page order.

### The Sort Key Must Be Stable

The sort key is an important element of paging. Choose a unique key or a combination of keys that produces a unique order. If the sort key is not unique, rows with the same value may be repeated or missed at page boundaries, depending on how the database paginates.

In addition, if the source data changes while the job is running, a row may move into or out of the query condition, changing the paging position. For a job that needs consistent results, process on a snapshot or limit the data with a fixed time marker/batch ID, and avoid letting the source data set fluctuate unexpectedly during the run.

### Page Size and Fetch Size

`pageSize` is the number of items the reader fetches in a page. `fetchSize` is a hint at the JDBC layer about the number of rows the driver fetches per fetch. The two concepts are related to performance but are not the same. Page size affects the number of items each paged query returns; fetch size depends on how the driver transfers rows from the database to the application.

## 8. Other Database Readers

Besides JDBC cursor and paging, Spring Batch also has readers for JPA and Spring Data.

| Reader | How it works | When to consider using it |
|---|---|---|
| `JpaPagingItemReader` | Uses EntityManager and a JPQL query to read entities page by page. | When the application already uses JPA and needs to process entities page by page. |
| `RepositoryItemReader` | Calls a repository method that supports paging/sorting. | When you want to reuse a Spring Data repository and the query is appropriately expressed through a repository method. |
| `JdbcCursorItemReader` | Reads sequentially from a JDBC ResultSet cursor. | When you need cursor-based streaming and can manage a long-lived connection/cursor. |
| `JdbcPagingItemReader` | Runs paged queries by sort key. | When you want to read by page and avoid keeping a cursor open for a long time. |

`RepositoryItemReader` example:

```java
@Bean
RepositoryItemReader<OrderEntity> repositoryOrderReader(
        OrderRepository orderRepository) {

    return new RepositoryItemReaderBuilder<OrderEntity>()
            .name("repositoryOrderReader")
            .repository(orderRepository)
            .methodName("findByStatus")
            .arguments(List.of(OrderStatus.READY))
            .sorts(Map.of("id", Sort.Direction.ASC))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

The repository needs a method compatible with paging, for example `Page<OrderEntity> findByStatus(OrderStatus status, Pageable pageable)`. The property name used in `sorts` must be a valid property of the entity. The order should be stable and have a unique key.

`JpaPagingItemReader` example:

```java
@Bean
JpaPagingItemReader<OrderEntity> jpaOrderReader(
        EntityManagerFactory entityManagerFactory) {

    return new JpaPagingItemReaderBuilder<OrderEntity>()
            .name("jpaOrderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("select o from OrderEntity o " +
                    "where o.status = 'READY' order by o.id")
            .pageSize(500)
            .saveState(true)
            .build();
}
```

The JPA paging reader manages the EntityManager according to the reader lifecycle and fetches entities page by page. Consider the page size, the persistence context, and the fact that entities are detached/cleared according to the reader's behavior. If the job only needs data in projection form or needs direct JDBC performance, a JDBC reader may be more appropriate.

## 9. Reading from a Resource via JobParameters

In many applications, the location of the input file is known only when the job is requested to run. You can pass the path in JobParameters and create the reader with `@StepScope`.

JobParameters example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "data/inbound/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();
```

The reader gets the parameter when the step starts:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    Resource resource = new FileSystemResource(inputFile);

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(resource)
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fieldSet -> new OrderInput(
                    fieldSet.readString("orderId"),
                    fieldSet.readString("customerId"),
                    fieldSet.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

In this example, the `inputFile` parameter is both used to create the `Resource` and can take part in identifying the JobInstance. If the same JobInstance is restarted, the file must keep content corresponding to the original run. The same path with replaced content can make the checkpoint no longer accurate.

If you need to use `ClassPathResource`, you can create the corresponding resource in place of `FileSystemResource`. If the resource is chosen based on the type of input source, you can put the logic for creating the Resource in a small factory or service so the reader does not have to contain many branches for selecting the source.

## 10. Comparing File Readers and Database Readers

| Criterion | File reader | Database reader |
|---|---|---|
| Source | CSV, text, XML, or another file | Table, view, or query result |
| Mapping | LineMapper, FieldSetMapper, Unmarshaller | RowMapper, JPA mapping, or repository method |
| Resources | File stream, file handle | Connection, ResultSet, EntityManager |
| Paging | Usually reads sequentially by line/record | Has a cursor or paging depending on the reader |
| Restart | Based on the read position and the resource state | Based on the item count/page, query, and sort key depending on the reader |
| Source-change risk | The file is overwritten or changed between runs | The table changes while the job is paging or querying |
| Common errors | Encoding, line structure, missing file, wrong delimiter | SQL, connection, timeout, lock, unstable sort key |

No reader is best for every case. Choose based on the actual data source, the size of the data set, transaction requirements, restart, and how the data changes while the job runs.

## 11. Reader Restart and Checkpoints

A reader can restart when the state needed to continue reading is saved and restored correctly. Many built-in readers implement `ItemStream`, so Spring Batch can save the checkpoint into the `ExecutionContext` at the commit boundary.

For a file reader, the checkpoint may be the read position in the file. For a cursor or paging reader, the checkpoint may relate to the number of items read or the query state. How it is saved depends on the implementation.

For a reliable restart:

- Use a stable reader name between runs.
- Enable state saving if the reader supports it and the job needs restart.
- Keep the file, resource, or source data set unchanged throughout the JobInstance lifecycle.
- With paging, use a unique and stable sort key.
- With a database query, keep the filter conditions and parameters consistent between the first run and the restart.
- Do not use a one-time `InputStreamResource` if you need to reopen the stream.
- With a self-written reader, implement ItemStream to save and restore the checkpoint.

Restart does not mean continuing at exactly the last Java statement. The framework continues from the saved state. Items in an uncommitted chunk may be read again; therefore the processor and writer must tolerate repeated processing.

## 12. Resource and Transaction Management

A reader usually opens resources in `open` and closes them in `close`. When reading a file, you need to release the stream to avoid leaking file handles. When reading a database with a cursor, you need to release the ResultSet and the connection in the proper lifecycle.

With a cursor reader, the connection may be held for a long time. Consider the pool size, the transaction manager, the isolation level, and how the JDBC driver performs fetches. If the job runs for a long time, a paging reader can reduce the time the cursor is held, but will generate many paged queries.

A reader does not necessarily write data, but the transaction can still affect how the reader interacts with the database, for example data snapshots, locks, or cursor visibility. Choose the transaction manager and isolation level based on the batch's consistency requirements.

For files, reading a file does not automatically participate in the database transaction. If a chunk rolls back, Spring Batch can restore the state of a reader that supports checkpoints, but the file content is not rolled back by the database transaction manager. For output files or multiple resources, use a separate management mechanism to avoid intermediate files being left in an incomplete state.

## 13. Performance and Data Size

Reader performance depends on how data is fetched and the characteristics of the source:

- With files, use a streaming reader instead of reading the entire file into a `List`.
- With a JDBC cursor, configure an appropriate fetch size and check the driver's behavior.
- With paging, choose a reasonable page size and ensure the sort key has an index if the query needs it.
- With JPA, avoid holding too large a persistence context; consider how the reader manages entities per page.
- With a repository, check the actual SQL and the query plan; the repository abstraction does not by itself guarantee an efficient query.
- With multiple files, use `MultiResourceItemReader` and fix the resource list for the batch.

Do not confuse `chunk size`, `pageSize`, and JDBC `fetchSize`:

| Value | What does it control? |
|---|---|
| `chunk size` | The number of input items processed in one write/commit cycle of the step. |
| `pageSize` | The number of items the paging reader fetches in one page query. |
| JDBC `fetchSize` | A hint to the driver about the number of rows fetched from the database per fetch. |

These values can be set equal in some cases, but they serve different layers. You need to measure throughput, query time, the number of commits, and memory usage to choose an appropriate configuration.

## 14. Common Errors When Using Readers

| Problem | Likely cause | How to handle it |
|---|---|---|
| The reader cannot find the file | Wrong path, a different working directory, or the file has not yet been delivered. | Check the JobParameters, the resource, and when the job is invoked. |
| Vietnamese characters are read incorrectly | The file's encoding does not match the configuration. | Determine the source encoding and configure `encoding` explicitly. |
| CSV columns are misaligned | The tokenizer does not handle the delimiter, quote, or escape in the correct format. | Use an appropriate tokenizer and check the actual file structure. |
| Restart reads again from the beginning | The reader does not save state, the reader name changed, or the state is not restored. | Use a reader that supports ItemStream, a stable name, and `saveState(true)` when needed. |
| Restart reads the wrong content | A file at the same path was changed between the two runs. | Store immutable files and identify them by batch/file version. |
| Paging misses or repeats rows | The sort key is not unique or the source data changes during paging. | Use a stable order, a unique key, and a fixed data set/snapshot. |
| A cursor holds a connection too long | The cursor stays open for the entire read time. | Consider paging, fetch size, the pool, and the run time. |
| An InputStream cannot be reopened | The resource represents only a one-time stream. | Use a resource that can be reopened or redesign how the input is provided. |
| A self-written reader cannot restart | It does not save the necessary state into the ExecutionContext. | Implement ItemStream and test checkpoint restoration. |
| A parallel job causes reader errors | The reader holds internal state and is not thread-safe. | Use a separate reader per partition or an appropriate synchronization mechanism. |

## 15. Which Reader for Each Situation?

| Situation | Reader that usually fits | Reason |
|---|---|---|
| Reading a large CSV file | `FlatFileItemReader` | Sequential reading, line mapping, and checkpoint support. |
| Reading multiple files of the same format | `MultiResourceItemReader` combined with a delegate reader | Coordinates multiple resources in order. |
| Reading XML element by element | `StaxEventItemReader` | Streaming by fragment, avoiding loading the whole XML. |
| Querying a database by cursor | `JdbcCursorItemReader` | Sequential reading on a ResultSet. |
| Reading a database by page | `JdbcPagingItemReader` | Queries page by page, without keeping a cursor open throughout. |
| Reading entities via JPA | `JpaPagingItemReader` | Leverages JPQL and EntityManager. |
| Reading via a Spring Data repository | `RepositoryItemReader` | Reuses a repository method with paging/sorting. |
| Reading a file packaged in the application | `FlatFileItemReader` with `ClassPathResource` | Uses a classpath resource as the file source. |

When choosing, answer these questions: where does the data reside, how large is the data set, is paging needed, does the source change while the job runs, can the reader restart, and which resources will be held for a long time?

## 16. How to Read Reader Code in a Spring Batch Application

When you come across a reader bean, trace the following details:

1. **Reader type:** file, JDBC cursor, JDBC paging, JPA, repository, or XML.
2. **Data source:** which `Resource`, `DataSource`, `EntityManagerFactory`, or repository is used.
3. **Item type:** which DTO, entity, or intermediate object the reader returns.
4. **Mapping approach:** `FieldSetMapper`, `LineMapper`, `RowMapper`, `Unmarshaller`, or repository method.
5. **Runtime parameters:** whether the file path, business date, SQL conditions, or page size come from JobParameters.
6. **Restart state:** the reader name, `saveState`, ItemStream, and ExecutionContext.
7. **Resources:** how the stream, cursor, connection, or EntityManager is opened and closed.
8. **Order and consistency:** whether the file is immutable, whether the SQL has a stable `ORDER BY`, whether paging has a unique sort key.

After understanding the reader, continue to look at the processor and writer to know where the item is transformed and saved. From there you can fully understand the step's chunk processing flow.

## 17. Points to Remember

- `ItemReader<T>` returns one item per `read()` call and returns `null` when the data is exhausted.
- `Resource` is an abstraction describing the location of a resource; readers such as `FlatFileItemReader` are the components that actually read items.
- `FlatFileItemReader` suits text files and can map lines to objects with a tokenizer, FieldSetMapper, or LineMapper.
- `MultiResourceItemReader` coordinates a delegate reader across multiple resources; the file list and order must be stable on restart.
- `StaxEventItemReader` reads XML by fragment through streaming.
- `JdbcCursorItemReader` reads sequentially with a cursor; consider the connection and ResultSet being held for a long time.
- `JdbcPagingItemReader` reads page by page; it needs a stable sort key, preferably unique.
- `JpaPagingItemReader` and `RepositoryItemReader` fit when the application uses JPA or Spring Data.
- `ItemStream`, `ExecutionContext`, and `saveState` support saving checkpoints for restart.
- The resource and the input data set must be stable between the first run and the restart.
- Distinguish chunk size, page size, and JDBC fetch size because they control different layers.

When building a reader, choose the implementation based on the type of source, the data size, consistency requirements, and restartability. A correctly configured reader helps the batch flow read data reliably, use resources sensibly, and continue safely after an execution fails.
