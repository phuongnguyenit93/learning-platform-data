# Reading Results with Stream<T> Within Transaction Boundaries

## Objectives

After this lesson, you will be able to declare repository methods returning `Stream<T>`; consume data streams inside an open transaction; close resources with `try-with-resources`; distinguish Java Streams from true incremental fetching by the database; control fetch size, persistence context, and lazy loading; and choose `Stream`, `Page`, `Slice`, or batch processing for the right use case.

Examples use Java 17+, Spring Boot 3+, Spring Data JPA, and Jakarta Persistence (`jakarta.persistence.*`). Code snippets belong to the illustrative package `com.example.learning.customer`; they need to run inside a Spring Boot application with `spring-boot-starter-data-jpa`, a configured `DataSource`, and a JDBC driver.

## 1. Why Can a Repository Return Stream<T>?

Normally, repositories return `List<T>` or `Page<T>`. With `List<T>`, the entire result set is typically materialized into a collection before the application processes it. If a query returns hundreds of thousands of records, holding the full list in heap can consume substantial memory.

Spring Data JPA supports the `Stream<T>` return type for query methods. Streams allow the application to consume results sequentially using Java Stream API operations such as `map`, `filter`, and `forEach`.

Declaration example:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Stream<Customer> findByActiveTrueOrderByIdAsc();
}
```

The method above finds active customers sorted by ID and returns `Stream<Customer>`. Callers can process elements one by one instead of requesting a `List<Customer>` from the repository.

However, `Stream<T>` does not automatically mean the database sends data one row at a time. Spring Data, the JPA provider, the JDBC driver, and the database together determine how results are retrieved. Stream is a result-consumption API; incremental fetching must be verified at the provider/driver layer.

## 2. Streams Must Be Consumed Within a Transaction

A repository's stream result may hold persistence-layer resources, such as a JDBC `ResultSet`, statement, and connection. These resources must remain valid throughout reading.

Therefore, place the transaction boundary on a service method encompassing both the repository call and the terminal operation on the stream. `@Transactional(readOnly = true)` is an appropriate choice for read-only use cases:

```java
package com.example.learning.customer;

import java.util.function.Consumer;
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
    public void exportActiveEmails(Consumer<String> emailWriter) {
        try (Stream<Customer> stream = customers.findByActiveTrueOrderByIdAsc()) {
            stream
                .map(Customer::getEmail)
                .forEach(emailWriter);
        }
    }
}
```

In this example:

- The service opens a transaction before calling the repository.
- The repository creates the stream inside that transaction.
- `forEach` is a terminal operation, so all results are consumed while the transaction is still open.
- `try-with-resources` closes the stream on completion or when an exception occurs.
- The method returns after the stream has been closed; the caller never receives a stream still dependent on an open transaction.

Placing the transaction on the service gives a use case a clear boundary. Query methods declared on a repository should not be assumed to automatically maintain a transaction around the entire caller consumption of a stream. Without an enclosing transaction, the stream may lose persistence resources before the caller finishes reading.

### 2.1. Do Not Return a Stream from a Transactional Method

This is a dangerous pattern:

```java
// Avoid: the transaction ends when the method returns the stream.
@Transactional(readOnly = true)
public Stream<Customer> findActiveCustomers() {
    return customers.findByActiveTrueOrderByIdAsc();
}
```

When the method returns, the Spring-managed transaction may already have ended. The caller only starts reading the stream afterward, while the cursor or connection may already be closed. Lazy loading operations on entities can also fail because the persistence context is no longer active.

Consume the stream completely inside the transactional method. If you need to return data to a controller or another layer, convert each element to a DTO and write it to the target within the proper processing boundary, or use pagination to return independent pages.

### 2.2. The Transactional Proxy Must Actually Be Invoked

In Spring, `@Transactional` is typically enforced via a proxy. A public method call from another bean goes through the proxy and opens a transaction as configured.

If one method in the same object directly calls another method annotated with `@Transactional` (self-invocation), the internal call usually bypasses the proxy; the annotation on the called method may not start a new transaction as expected. Place transaction boundaries on public service methods invoked from outside the bean or structure services so calls pass through Spring proxies.

`readOnly = true` expresses read-only intent and can help the transaction manager/provider optimize execution. It is not an absolute security mechanism forbidding all database write statements.

## 3. Always Close Streams with try-with-resources

Java `Stream<T>` extends `BaseStream`, has `close()`, and supports `try-with-resources`. When a stream comes from a repository, close it explicitly:

```java
try (Stream<Customer> stream = customers.findByActiveTrueOrderByIdAsc()) {
    stream.forEach(customer -> process(customer));
}
```

Do not close only on success. `try-with-resources` still invokes `close()` if the terminal operation throws an exception, releasing resources attached to the stream.

Do not simply call a terminal operation and abandon the stream without closing it. Plain in-memory Java streams do not hold external resources, but streams from a repository can hold cursors, result sets, or connections. The safe rule is to always use `try-with-resources`.

A stream can only be consumed once. After `forEach`, `collect`, `count`, or another terminal operation, do not reuse the same stream. If you need to query again, call the repository to create a new stream inside an appropriate transaction.

## 4. Using @Query to Define Stream-Returning Queries

Streams are not limited to derived queries. A repository can declare JPQL with `@Query` and return `Stream<T>`:

```java
package com.example.learning.customer;

import java.util.stream.Stream;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("""
        select c
        from Customer c
        where c.active = true
        order by c.id asc
        """)
    Stream<Customer> streamActiveCustomers();
}
```

JPQL uses the `Customer` entity and properties `active`, `id`; it does not use SQL table or column names. Consuming and closing the stream must still occur within a transaction as shown in the earlier service example.

If only a few fields are needed, you can return a projection/DTO instead of an entity:

```java
package com.example.learning.customer;

public record CustomerEmailRow(Long id, String email) {
}
```

```java
@Query("""
    select new com.example.learning.customer.CustomerEmailRow(c.id, c.email)
    from Customer c
    where c.active = true
    order by c.id asc
    """)
Stream<CustomerEmailRow> streamActiveEmailRows();
```

DTO projections limit the data the query returns and avoid exposing managed entities outside the use case. This is usually a good choice for exports or read-only processing when entities do not need to be modified.

## 5. Stream Does Not Mean Row-by-Row Fetching from the Database

This is the most critical point when optimizing large datasets. The Java Stream API allows sequential processing, but the provider may have already loaded many or all results from the database before the stream begins consuming them.

Incremental fetching depends on:

- The JPA provider and how it implements query result streams.
- The JDBC driver and cursor/fetch-size support.
- The database, transaction mode, and connection configuration.
- Whether the query involves joins, sorts, groups, collection fetches, or specific result types.
- The fetch size configured on the statement.

Therefore, do not conclude an application uses low memory merely because a method returns `Stream<T>`. Measure heap usage, fetched row counts, round trips, and driver behavior on the target database.

### 5.1. Fetch Size

Fetch size is a hint to the JDBC driver indicating how many rows to retrieve per round trip from the database. It can enable the provider/driver to use cursors or batch fetching, though exact semantics depend on the driver and database.

With Hibernate, you can try a fetch size hint as follows:

```java
import java.util.stream.Stream;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.QueryHints;

@QueryHints(
    value = @QueryHint(name = "org.hibernate.fetchSize", value = "200")
)
Stream<Customer> findByActiveTrueOrderByIdAsc();
```

`org.hibernate.fetchSize` is a Hibernate-specific hint, not a portable Jakarta Persistence guarantee. If using another provider, check that provider's documentation. Even when fetch size is set, a driver may ignore it or interpret it differently; verify with integration tests and runtime observation.

There is no single optimal fetch size for every system. Too small a value can increase round trips; too large a value can increase buffer memory. Choose based on row size, network latency, driver behavior, and memory limits.

### 5.2. SQL Sorting and Query Plans

Streams do not make an inherently expensive query cheaper. If a query must sort millions of records, the database still needs to perform the sort or use an appropriate index before returning results.

For example, a query with `ORDER BY id` may leverage the primary key index, depending on the schema and execution plan. Inspect indexes, filter predicates, rows read, and query plans instead of optimizing only on the Java side.

## 6. The Persistence Context Can Still Grow in Memory

When a stream returns entities, each loaded entity typically becomes managed in the persistence context. Even though the application does not create a `List` holding all results, the Hibernate/JPA persistence context may retain references to loaded entities for its identity map and dirty checking.

Consequently, streaming entities over a very large dataset can still increase heap usage in proportion to the number of entities read. Two distinct concerns must be separated:

- **JDBC fetch:** the number of rows the driver keeps in its buffer/cursor at a time.
- **Persistence context:** the number of entities currently managed by JPA in the session/entity manager.

Lowering the fetch size does not automatically remove entities from the persistence context. Conversely, `EntityManager.clear()` releases managed state in the persistence context but does not replace JDBC fetch configuration.

For read-only processing where managed entities are unnecessary, consider DTO/scalar projections to reduce entity hydration and retention. If processing huge numbers of entities is unavoidable, split into batches and clear the persistence context using a tested strategy. When clearing, all managed entities become detached; read all needed data and associations before detaching, and verify behavior with your provider.

Do not call `clear()` indiscriminately while still needing to lazy-load relationships or update entities. Once detached, changes to objects are no longer automatically written to the database by dirty checking.

## 7. Lazy Loading, N+1, and Relationships

Streaming entities inside a transaction allows accessing lazy associations while the persistence context remains open, but that does not mean querying relationships will be efficient.

Example:

```java
try (Stream<Customer> stream = customers.findByActiveTrueOrderByIdAsc()) {
    stream.forEach(customer -> {
        String city = customer.getAddress().getCity();
        process(customer.getEmail(), city);
    });
}
```

If `address` is a lazy association, calling `getAddress()` may trigger an additional query per customer. This is the N+1 pattern: one query for the customer list, followed by many small queries for associations.

How to handle it:

- If only a few fields are needed, use a DTO projection and select those fields in a single query.
- If relationships are needed, consider batch fetching or a query with an appropriate join.
- Check actual SQL query counts and avoid invoking lazy getters in loops without understanding the cost.
- Do not pass entities outside the transaction and expect lazy associations to still load.

Be cautious with collection fetch joins on a stream query. One-to-many joins can multiply SQL rows per parent entity, creating duplicates or forcing complex result assembly in the provider. Inspect SQL, root entity uniqueness, and provider limitations; projections or batch queries are often easier to control.

## 8. Error Handling and Connection Hold Time

While consuming a stream, exceptions can originate from callbacks, mapping, JDBC, or the database. `try-with-resources` ensures `close()` is called on block exit, while the transaction still must complete properly to roll back or commit per Spring rules.

Long-running streams hold transactions and may hold connections for extended periods. This reduces available connections for other requests, especially when callbacks write files slowly or call external services.

Avoid making HTTP calls or slow network operations per row while holding a database cursor open. For large exports, consider reading in batches, writing files in chunks, or separating reading from data transmission. Monitor the connection pool and transaction duration during task execution.

Do not hand off a stream to `CompletableFuture`, another thread, or call `.parallel()` for concurrent processing. `EntityManager`/persistence context is not thread-safe; a JDBC result set is also not a data source for arbitrary multi-threaded reads. Process sequentially within the transaction, or divide data into independent units with separate transactions.

## 9. Integration Test for a Stream Repository

Minimal entity example:

```java
package com.example.learning.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String email;

    @Column(nullable = false)
    private boolean active;

    protected Customer() {
    }

    public Customer(String email, boolean active) {
        this.email = email;
        this.active = active;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public boolean isActive() { return active; }
}
```

Repository:

```java
package com.example.learning.customer;

import java.util.stream.Stream;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Stream<Customer> findByActiveTrueOrderByIdAsc();
}
```

Integration test:

```java
package com.example.learning.customer;

import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerRepositoryStreamTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void consumesActiveCustomersInsideTestTransaction() {
        customers.saveAll(List.of(
            new Customer("ada@example.test", true),
            new Customer("grace@example.test", false),
            new Customer("linus@example.test", true)
        ));
        customers.flush();

        try (Stream<Customer> stream = customers.findByActiveTrueOrderByIdAsc()) {
            assertThat(stream.map(Customer::getEmail).toList())
                .containsExactly("ada@example.test", "linus@example.test");
        }
    }
}
```

`@DataJpaTest` typically runs each test inside a transaction that rolls back when the test finishes. Because the stream is consumed and closed inside the test method, it executes within the open test transaction. `flush()` forces new records to be sent to the database before querying.

This test verifies that the repository returns the expected data and demonstrates proper stream consumption/closing. It does not prove the driver actually fetches via a cursor or that memory stays constant. To verify incremental fetching, run integration tests against the target database/driver and measure actual behavior.

## 10. When to Use Stream, Page, Slice, or Batch?

| Need | Suitable approach |
| --- | --- |
| Need full small result set immediately | `List<T>` |
| UI needs page numbers and total record count | `Page<T>` |
| UI only needs to know if a next page exists | `Slice<T>` |
| Sequential processing of a large result set in one transaction | `Stream<T>` if provider/driver supports and is verified |
| Long-running job needing short transactions and batch recovery | Pagination or batch processing |
| Only need a few columns for export/reporting | DTO or projection, optionally combined with `Stream` |

`Page` and `Slice` split results into independent calls. They generally make transaction duration and connection hold times easier to control when each batch can complete before fetching the next.

For very large datasets, offset pagination on deep pages can be costly. If a stable sort key exists, you can use keyset pagination or a scrolling/batching mechanism supported by your Spring Data version. When choosing this approach, define a unique order and handle data changing while the job runs.

Stream fits when a task needs a single sequential pass over a result set within a controllable transaction boundary. It is not the default choice for every large task; connections are held longer and the persistence context can still consume memory.

## 11. Common Pitfalls

- **No transaction wrapping the read process.** Place `@Transactional(readOnly = true)` on the service method consuming the stream.
- **Returning `Stream<T>` from a transactional method.** The stream may be read after the transaction/connection has closed; consume it inside the method.
- **Not closing the stream.** Use `try-with-resources` to release result sets, statements, and associated resources.
- **Assuming Stream always fetches row by row.** The provider/driver may buffer many or all results; verify fetch size and actual behavior.
- **Reducing fetch size without managing the persistence context.** Loaded entities may still stay managed; consider DTOs or controlled batch/clear.
- **Calling lazy associations inside a loop without measuring SQL.** Can generate N+1 queries.
- **Calling external services per row inside a long transaction.** Connections stay held long; switch to batching or separate processing stages.
- **Using parallel streams with EntityManager/JDBC cursors.** The persistence context and JDBC sources are not safe for arbitrary concurrent access.
- **Collecting a stream into a huge `List`.** `toList()`/`collect()` can negate the memory benefits of sequential processing.
- **Using Hibernate fetch size hints on other providers.** Hints are provider-specific; verify names and effectiveness on your actual stack.
- **Assuming `readOnly = true` strictly forbids writes.** It is a transaction optimization hint, not a substitute for database constraints and permissions.

## 12. Pre-Deployment Checklist

- [ ] Repository methods returning `Stream<T>` or appropriate DTO projections are used only for large-read use cases.
- [ ] A service method holds a transaction wrapping both the repository call and the terminal operation.
- [ ] The stream is consumed before the transactional method returns.
- [ ] The stream is always closed with `try-with-resources`.
- [ ] Streams are never returned across controllers, other threads, or async tasks.
- [ ] Verified that the provider and JDBC driver fetch incrementally as intended.
- [ ] Fetch size has been tested on the target database if needed.
- [ ] Evaluated persistence context/heap growth when reading many entities.
- [ ] Checked for N+1 queries, lazy loading, and collection fetch joins.
- [ ] Transaction/connection hold time fits the connection pool budget.
- [ ] Compared against `Page`, `Slice`, or batching for long-running jobs.
- [ ] Integration tests verify data, transactions, and stream closing.

## Conclusion

`Stream<T>` in Spring Data JPA enables sequential result processing, but streams must be consumed and closed inside an open transaction. Place transactions on service methods, use `try-with-resources`, verify fetch size/provider/driver behavior, and monitor both JDBC buffers and the persistence context. When only partial data is needed, DTO projections usually reduce entity management overhead; when short transactions or resumable batch processing are needed, `Page`, `Slice`, or batching are usually easier to operate.