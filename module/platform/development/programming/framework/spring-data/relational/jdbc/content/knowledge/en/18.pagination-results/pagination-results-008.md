# Streaming Results and Closing Resources with try-with-resources

## 1. When Should Results Be Read as a Stream?

A repository method typically returns `List<T>` or `Page<T>`. This is convenient when the row count is bounded: the query runs, results are mapped into objects, and the application processes the collection in memory.

Imagine, however, needing to export one million transactions to a file, aggregate a massive dataset, or run a verification job across all customers. Loading everything into a `List<T>` forces the application to hold a huge number of objects simultaneously. Memory usage can spike, and the wait time before processing the first element becomes long.

For suitable JDBC queries, Spring Data JDBC can return `Stream<T>` so the caller processes each element through a Java Stream pipeline. A stream may be backed by JDBC resources such as a connection, statement, and result set. Therefore, **closing the Stream properly is part of releasing database resources**.

Key points to keep in mind from the start:

- `Stream<T>` is a way of consuming results; it does not automatically guarantee the database driver uses a server-side cursor or avoids prefetching data.
- A JDBC-backed stream can keep a connection and result set open for the entire duration of consumption.
- The stream must be closed, even on error or early termination.
- Use `try-with-resources` to ensure `close()` is invoked.
- A transaction must remain active while the stream is read; typically place the transaction on the service consuming the stream.
- If pagination, checkpoints, retries, or independent chunk processing are needed, `Page`, `Slice`, or keyset queries may fit better.

## 2. `Stream<T>` in Spring Data JDBC Repositories

A query method can declare a return type of `Stream<T>` when the module, Spring Data JDBC version, and driver support that execution mode. Example:

```java
import java.util.stream.Stream;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.Repository;

public interface CustomerRepository
        extends Repository<Customer, Long> {

    @Query("""
        SELECT id, name, email
        FROM customers
        ORDER BY id
        """)
    Stream<Customer> streamAllCustomers();
}
```

When the method is called, the repository provides a `Stream` for the caller to iterate over customers. Table names, column names, and mappings in the example must match the actual schema. `ORDER BY id` provides a stable processing order; SQL does not guarantee row order without `ORDER BY`.

If the repository already extends `CrudRepository`, the stream method can be declared alongside CRUD methods:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Query("""
        SELECT id, name, email
        FROM customers
        ORDER BY id
        """)
    Stream<Customer> streamAllCustomers();
}
```

Do not confuse `Stream<T>` with `Flux<T>`:

| Type | Model | Characteristics |
| --- | --- | --- |
| `List<T>` | Synchronous collection | Results are typically materialized into a list before the caller processes them. |
| `Stream<T>` | Java Stream pipeline | Sequential/lazy traversal via Stream abstraction; must be closed if backed by JDBC resources. |
| `Page<T>` | A page of results + metadata | Typically needs a page data query and may run an additional count query. |
| `Slice<T>` | A slice of results | Indicates whether a next page exists, usually avoiding total row count. |
| `Flux<T>` | Reactive Streams | Non-blocking reactive API with backpressure; not a standard blocking JDBC return type. |

## 3. Why Must a Stream Be Closed?

A stream from a JDBC query may sit atop the following resources:

```text
Application code
      |
      v
Java Stream<Customer>
      |
      v
ResultSet  -------- cursor / current row
      |
      v
PreparedStatement
      |
      v
JDBC Connection
      |
      v
Connection pool / Database
```

As the caller traverses the stream, JDBC reads rows and maps them into objects. If the stream is not closed, associated resources may fail to be released on time:

- The connection may stay checked out of the pool, reducing connections available to other requests.
- The result set and statement may remain open.
- The database may have to hold a cursor or query state.
- The transaction may stay open longer than expected.

Never wait for the garbage collector to release these resources. Garbage collection is not a deterministic closing mechanism for JDBC resources.

Java `Stream` extends `AutoCloseable`. Therefore, it can be used directly with `try-with-resources`:

```java
try (Stream<Customer> customers = repository.streamAllCustomers()) {
    customers.forEach(this::process);
}
```

Upon exiting the block, Java calls `close()` on the stream. This happens whether the block completes normally or throws an exception.

## 4. Using `try-with-resources` to Close the Stream

This is the fundamental usage pattern to prefer:

```java
try (Stream<Customer> customers = repository.streamAllCustomers()) {
    customers.forEach(customer -> {
        System.out.println(customer.id() + " - " + customer.name());
    });
}
```

`try-with-resources` guarantees `close()` is called. You do not need to write a manual `finally` block to close the stream in ordinary cases.

### 4.1. Processing One Element at a Time

Example processing each customer:

```java
try (Stream<Customer> customers = repository.streamAllCustomers()) {
    customers.forEach(customer -> {
        customerService.recalculate(customer.id());
    });
}
```

The pipeline does not construct a `List<Customer>` holding the entire result set. However, this only avoids holding a result collection in heap; it does not prove the driver/database avoids buffering data at a lower level. Check the driver, fetch size, and configuration if true streaming over large datasets is needed.

### 4.2. Closing the Stream on Errors

Suppose an element throws an exception:

```java
try (Stream<Customer> customers = repository.streamAllCustomers()) {
    customers.forEach(customer -> {
        if (customer.email() == null) {
            throw new IllegalStateException("Customer has no email");
        }
        sendNotification(customer);
    });
}
```

When the exception exits the block, `try-with-resources` still invokes `close()`. If both the block body and `close()` throw exceptions, Java preserves the primary exception and attaches the closing exception as a suppressed exception.

Do not write:

```java
Stream<Customer> customers = repository.streamAllCustomers();
customers.forEach(this::process);
// No close(): resources may remain held.
```

That snippet neglects resource cleanup responsibility.

### 4.3. Early Termination Still Requires Closing

A pipeline may not consume all data:

```java
try (Stream<Customer> customers = repository.streamAllCustomers()) {
    customers
            .filter(customer -> customer.name().startsWith("A"))
            .findFirst()
            .ifPresent(this::process);
}
```

`findFirst()` is a short-circuit terminal operation: it can stop after finding the first matching element. Yet that **does not automatically substitute for closing the stream**. `try-with-resources` is still required.

Likewise, terminal operations such as `anyMatch`, `allMatch`, and `limit(...).forEach(...)` can stop before reading all rows. Keep the stream inside an explicit resource scope.

## 5. A Transaction Must Encompass Stream Consumption

This is especially important in Spring Data JDBC. A JDBC-backed stream may need the connection and result set throughout traversal. If the transaction or connection scope ends before the caller reads the data, the stream may no longer have valid resources to continue.

A safe way to structure this is placing `@Transactional(readOnly = true)` on **the service method consuming the stream**, opening and closing the stream right inside that method:

```java
package com.example.customer;

import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerExportService {

    private final CustomerRepository customers;

    public CustomerExportService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public void exportAll() {
        try (Stream<Customer> stream = customers.streamAllCustomers()) {
            stream.forEach(this::writeRow);
        }
    }

    private void writeRow(Customer customer) {
        // Write one row to output managed by the service.
        System.out.println(customer.id() + "," + customer.name());
    }
}
```

Execution flow:

1. Spring opens a transaction when the service is called through its proxy.
2. The repository runs the query within the active transaction.
3. The service consumes the stream while the connection/transaction remains valid.
4. `try-with-resources` closes the stream after completion or on error.
5. The service exits; the transaction interceptor completes the transaction.

### Do Not Return a Stream Out of a Transactional Service

Avoid writing:

```java
@Transactional(readOnly = true)
public Stream<Customer> streamCustomers() {
    return customers.streamAllCustomers();
}
```

If the transaction was opened by this method's proxy, the transaction can end as soon as the method returns the `Stream`. The caller begins traversing the stream afterward, when the transaction scope has already closed. Depending on the implementation and driver, reading may fail or lose guarantees.

Instead, have the service both open the transaction and consume the stream as in `exportAll()`. If the API genuinely must return results to a caller, consider returning `List`, `Page`, `Slice`, DTOs, or designing an abstraction with an explicitly managed resource lifecycle.

### Transactional Annotations Must Pass Through a Spring Proxy

`@Transactional` operates via proxy/AOP mechanisms in standard Spring setups. Calling a transactional method from another method on the same instance (`this.someTransactionalMethod()`) may bypass the proxy and fail to activate the transaction as expected. Place transaction boundaries on public service methods invoked from other beans or use a structure compatible with your application's transaction management.

## 6. Stream Does Not Automatically Mean Server-Side Cursor

Do not infer that declaring `Stream<T>` automatically makes the database send rows one by one over the network without buffering. Several layers affect this:

- Spring Data JDBC query execution.
- Spring JDBC and `ResultSet` handling.
- The JDBC driver.
- Fetch size configuration.
- Autocommit and transactions.
- The database server and dialect.

Some drivers default to loading many or all results to the client; others support cursors/batched fetching when configured properly. Actual behavior depends on the database and driver.

### 6.1. Fetch Size

JDBC defines fetch size, allowing a hint for how many rows the driver should retrieve per round trip from the database. It is a **hint**; not every driver honors it identically.

With some drivers, a default fetch size of 0 causes the driver to read the entire result set. With others, fetch size only takes effect under specific transaction/autocommit conditions. Therefore, when exporting millions of rows:

1. Read the documentation of the JDBC driver in use.
2. Check how fetch size is configured in your Spring Data JDBC/Spring JDBC version.
3. Verify the driver's transaction and autocommit requirements.
4. Measure memory and rows read using a sufficiently large dataset.

Do not set an arbitrary fetch size and assume it takes effect identically across all databases.

### 6.2. Fetch Size Is Not Page Size

These are two distinct concepts:

| Property | Meaning |
| --- | --- |
| Fetch size | Hint to the JDBC driver on how many rows to fetch from the result set in batches. |
| Page size | Number of rows requested by the application in a paginated query. |

Fetch size does not split a query into multiple paginated SQL statements. Page size participates in query limits and typically causes the application to invoke the repository multiple times.

## 7. Stream vs. Other Result-Handling Approaches

Not every large query needs `Stream<T>`. Choose a return style based on the use case requirements:

| Requirement | Suitable option | Why |
| --- | --- | --- |
| Tens or hundreds of rows for display | `List<T>` | Simple and easy to use after the query completes. |
| Paginated UI needing total count | `Page<T>` | Provides content, page number, and total metadata; may need a count query. |
| Only need to know if more results follow | `Slice<T>` | Avoids the cost of counting total rows when unnecessary. |
| Sequential scan of a large set in one continuous resource scope | `Stream<T>` | Caller processes incrementally and closes the stream when finished. |
| Batch execution with checkpoints/retries | Pagination or keyset/chunking | Each batch has clear boundaries and progress can be saved. |
| End-to-end reactive data | R2DBC with `Flux<T>` | Non-blocking reactive API with backpressure; requires reactive driver and full pipeline support. |

### 7.1. Page

`Page<T>` suits UIs needing total result counts and page counts:

```java
Page<Customer> findByStatus(
        CustomerStatus status,
        Pageable pageable
);
```

Typically, the framework queries the page's data and may run an additional count query to calculate totals. On very large datasets, the count query can be expensive.

### 7.2. Slice

`Slice<T>` fits when the UI only needs to know whether a next page exists:

```java
Slice<Customer> findByStatus(
        CustomerStatus status,
        Pageable pageable
);
```

It avoids requesting the total row count. The implementation typically fetches one extra row to determine whether more data follows; details depend on the execution path.

### 7.3. Keyset/Chunk Processing

For large batches, instead of keeping a result set open for hours, read in chunks:

```sql
SELECT id, name, email
FROM customers
WHERE id > :lastSeenId
ORDER BY id
LIMIT :batchSize;
```

After processing a chunk, save the last ID and query the next chunk. This is the keyset pagination model. It can shorten connection hold times and support resuming after failures, though it requires a stable sort key, matching indexes, and clear semantics if data mutates during execution.

## 8. Processing a Stream with Java Pipelines

Streams support familiar intermediate and terminal operations:

```java
try (Stream<Customer> stream = customers.streamAllCustomers()) {
    long activeCount = stream
            .filter(Customer::active)
            .peek(customer -> logCustomer(customer.id()))
            .count();

    System.out.println("Active customers: " + activeCount);
}
```

A few notes:

- Intermediate operations like `filter`, `map`, and `sorted` normally do not consume data immediately.
- Terminal operations like `forEach`, `collect`, `count`, and `findFirst` trigger traversal.
- A Stream can be consumed only once.
- `sorted()` typically buffers elements to sort the whole set; using it on a large JDBC stream can negate memory benefits.
- `collect(toList())` materializes the results into a collection and can load the entire dataset onto the heap.
- `peek()` should be reserved for simple observation/debugging; avoid hiding critical side effects inside it.

### 8.1. Mapping to a DTO

If exporting lighter data than full entities:

```java
try (Stream<Customer> stream = customers.streamAllCustomers()) {
    stream
            .map(customer -> new CustomerExportRow(
                    customer.id(),
                    customer.name(),
                    customer.email()
            ))
            .forEach(csvWriter::write);
}
```

However, if the query only needs three columns, consider a projection/DTO query so the database returns only the needed columns rather than loading full aggregates. Exact projection mapping support depends on your Spring Data JDBC version.

### 8.2. Do Not Use Parallel Streams on a JDBC Result Set

Avoid calling:

```java
try (Stream<Customer> stream = customers.streamAllCustomers()) {
    stream.parallel().forEach(this::process);
}
```

A stream backed by a JDBC result set is normally not designed for multiple threads concurrently reading from a single cursor/connection. Parallel execution can also scramble processing order and spike concurrent load on the database. If parallel processing is needed, read independent batches, close the current query, and dispatch batches to a bounded worker pool.

## 9. Do Not Hold Connections Open During Slow External Work

Example:

```java
try (Stream<Customer> stream = customers.streamAllCustomers()) {
    stream.forEach(customer -> {
        remoteApi.send(customer);
    });
}
```

If `remoteApi.send` takes seconds per row, the connection and transaction may stay open for a very long time. This can:

- Exhaust the connection pool.
- Hold snapshots/transactions open for long periods, affecting vacuuming or locks depending on the database.
- Make the batch prone to mid-run network failures.
- Make retries difficult when determining which items were already processed.

For external integrations, consider reading in batches, closing the read transaction before calling remote APIs, and recording checkpoints. If a single spanning transaction is required, clearly understand the database and connection pool costs and limits.

## 10. A Resource-Managed CSV Export Service Example

Suppose a writer is created and closed by the caller. The service uses a stream inside a transaction:

```java
package com.example.customer;

import java.io.BufferedWriter;
import java.io.IOException;
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerCsvExportService {

    private final CustomerRepository customers;

    public CustomerCsvExportService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public void writeCsv(BufferedWriter writer) throws IOException {
        writer.write("id,name,email");
        writer.newLine();

        try (Stream<Customer> stream = customers.streamAllCustomers()) {
            stream.forEach(customer -> {
                try {
                    writer.write(csv(customer.id()));
                    writer.write(",");
                    writer.write(csv(customer.name()));
                    writer.write(",");
                    writer.write(csv(customer.email()));
                    writer.newLine();
                } catch (IOException ex) {
                    throw new CsvWriteException(ex);
                }
            });
        }
    }

    private String csv(Object value) {
        if (value == null) {
            return "";
        }
        String text = value.toString();
        return "\"" + text.replace("\"", "\"\"") + "\"";
    }

    private static class CsvWriteException extends RuntimeException {
        CsvWriteException(IOException cause) {
            super(cause);
        }
    }
}
```

This example illustrates only the stream closing scope; production file handling also requires deciding who owns and closes `BufferedWriter`, character encoding, CSV escaping, and temporary file cleanup if the read transaction fails. Do not let a service close a resource owned by the caller unless the contract specifies it.

If an exception is wrapped into a runtime exception, default Spring transactions normally roll back when it propagates out of the transactional method. Because this is a read transaction, rollback alters no data, yet the connection/resources still need to be closed.

## 11. Resource Lifecycle and Closing Order

With `try-with-resources`:

```java
try (Stream<Customer> stream = repository.streamAllCustomers()) {
    // consume stream
}
```

Java invokes `stream.close()` upon exiting the block. Streams from Spring Data JDBC/Spring JDBC may register close handlers to release the result set, statement, and related resources according to the implementation. The caller does not need to close `ResultSet` or `Connection` directly if the repository owns them.

If the caller opens additional resources:

```java
try (
        Stream<Customer> stream = repository.streamAllCustomers();
        BufferedWriter writer = Files.newBufferedWriter(path)
) {
    stream.forEach(customer -> write(writer, customer));
}
```

Resources are closed in reverse declaration order: `writer` closes first, then `stream` closes. Keep this order in mind if writing output still depends on the stream being active; in this example, both are used only inside the block and released cleanly on exit.

If a stream is wrapped via Java Stream operations, the source stream's close handler is propagated along the pipeline; closing the final stream closes the source. Avoid creating derived streams and abandoning the original stream without a clear ownership scope.

## 12. Common Mistakes

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Connection pool exhausted after batch | Stream was not closed or was held too long | Use `try-with-resources` and bound consumption duration. |
| Stream fails when reading begins | Transaction/connection scope ended before stream was consumed | Put the transaction on the service consuming the stream; do not return streams outside transactional methods. |
| Large dataset still uses high heap | Driver buffers everything, fetch size has no effect, or pipeline uses `collect`/`sorted` | Inspect driver, fetch size, transaction, and intermediate/terminal operations. |
| Read a few rows and stopped, yet resources stay open | `findFirst`, `limit`, or `anyMatch` do not auto-close the stream | Wrap the stream in `try-with-resources`. |
| Parallel processing causes JDBC errors | Calling parallel stream on a cursor/connection-backed source | Iterate sequentially or read independent batches before parallel processing. |
| Batch holds transaction too long | Slow API/file/network calls inside the pipeline | Split into chunks, close queries between batches, and checkpoint progress. |
| Result order changes across runs | Query lacks `ORDER BY` | Add a deterministic sort, usually with a unique key tie-breaker. |
| Query returning Stream is unsupported | Version/module/driver does not support the execution mode or return type | Check version-specific docs; use `JdbcTemplate` or pagination if needed. |

## 13. Workflow for Choosing Stream vs. Pagination

Before choosing `Stream<T>`, determine:

1. **Data volume:** hundreds of rows or millions of rows?
2. **Processing style:** continuous pass, or saving checkpoints after each group?
3. **Processing time:** fast per-row work, or slow external I/O?
4. **Transactions:** can a read transaction remain open for the entire pass?
5. **Driver:** does it support streaming/cursors and fetch size as desired?
6. **Retry capability:** if the job crashes mid-way, does it need to resume from the last position?
7. **Ordering:** is deterministic ordering needed for resuming or exporting?

Choose `Stream<T>` when performing a single sequential read in a short resource scope where the caller explicitly consumes and closes the stream and the driver is configured accordingly. Choose pagination/chunking when long processing times, checkpoints, retries, bounded transactions, or independent batching are required.

## 14. Practice Exercises

**Exercise 1 — Basic Stream.** Create a query method returning `Stream<Customer>`, invoke it in a service, and traverse it using `try-with-resources`. Confirm all data is read accurately.

**Exercise 2 — Short-Circuiting.** Use `findFirst()` or `limit(5)` to read only part of the results. Keep `try-with-resources` and explain why terminal operations do not close resources automatically.

**Exercise 3 — Intentionally Omitting Close.** Write a test-environment example without `try-with-resources`, observe connection pool or resource metrics, then fix it. Never run pool-exhaustion experiments on shared environments.

**Exercise 4 — Transaction Scope.** Create a service returning a stream from a `@Transactional` method and consume it in the caller. Compare with a service that consumes the stream inside the transaction and explain the difference in connection lifecycle.

**Exercise 5 — Fetch Size.** Using your project's actual database/driver, configure fetch size per the driver guide. Measure heap and duration on a large dataset; compare with `List<T>`.

**Exercise 6 — Chunking.** Replace a long stream with keyset pagination by ID, process each batch, and persist a checkpoint. Describe how to resume when the job stops between two batches.

**Exercise 7 — Parallel Streams.** Explain why calling `parallel()` directly on a JDBC result-set-backed stream is unsafe. Design an approach that reads batches and processes them in parallel with a bounded worker pool.

## 15. Key Takeaways

`Stream<T>` is a useful option for consuming query results through a Java pipeline, yet in Spring Data JDBC a stream may keep JDBC resources open while reading. Always close it with `try-with-resources`, consume it within an active transaction scope, and avoid returning a stream out of a service whose transaction has already ended.

A stream does not guarantee the driver uses a server-side cursor or avoids buffering data; fetch size and actual behavior depend on the driver, database, and transaction. For long-running work requiring checkpoints or retries, pagination/chunking is usually easier to manage. Choose based on resource lifecycles and operational requirements of the use case, not just row counts.

### References

- [Spring Data Relational – Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Data Commons – Repository Query Return Types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html)
- [Java 21 – Stream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html)
- [Java 21 – AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html)
