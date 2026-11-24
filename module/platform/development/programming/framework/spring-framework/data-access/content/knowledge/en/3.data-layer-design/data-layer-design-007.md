# Returning Data Independent of Closed Resources

## 1. Problem: Objects Still Exist While Their Underlying Data May Have Expired

In Spring Framework's data access layer, a database read method typically uses short-lived resources: a JDBC `Connection`, `Statement`, and `ResultSet`; or in JPA, an `EntityManager`, persistence context, and lazy-loading associations. Those resources must be closed or returned to the pool once the work finishes. Yet the object returned by the service to its caller must still be readable.

**Design principle:** finish reading, converting, and copying the required values **while the resource is still valid**; public methods return DTOs/value objects that already contain all data needed for the caller's purpose. The caller should not need a `ResultSet`, `Connection`, `EntityManager`, or an active database session to read the exposed fields.

Example: a book catalog screen needs id, title, and price. The repository must extract those three values while the `ResultSet` is open, build `BookView` instances, and return `List<BookView>`. After JDBC closes the `ResultSet` and the transaction completes, the screen can still read titles and prices. If the repository returned a `ResultSet`, a `Stream` backed by an active database query, or an object waiting to traverse a lazy relation, upper layers could fail once resources are closed.

This is a **resource lifetime boundary** problem, not merely a connection-closing issue. Questions to answer before designing a data-reading API:

1. What data does the caller actually need, and to what depth must it be loaded?
2. Which values have already been materialized into Java objects, and which would trigger another query on access?
3. Who owns closing the `ResultSet`, `Stream`, `Connection`, or persistence context?
4. Does the result need to be immutable so it cannot be modified after leaving the method?
5. If the result set is very large, should it be paginated, batched, or streamed within a transaction?

## 2. Distinguishing Resource-Independent Data from Resource-Bound Data

| Return value | Usable after data resources close? | Conditions / notes |
| --- | --- | --- |
| `String`, primitive, `BigDecimal`, `LocalDate` already read from `ResultSet` | Yes | Extracted Java values; no JDBC callback is needed. |
| Record/DTO holding only already-read values | Yes | Holds no JDBC handles, lazy proxies, or deferred-read components. |
| `List<DTO>` already mapped by `JdbcTemplate.query` | Yes | Every element is materialized; watch total size if data is large. |
| `ResultSet`, `Statement`, `Connection` | No | JDBC handles bound to finite-lifetime resources. |
| `Stream` provided by `JdbcTemplate.queryForStream` | Should not escape resource ownership scope | Stream remains tied to `ResultSet`/`Statement`; must be closed via `try-with-resources` after use. |
| `Stream` created from an already-loaded `List<DTO>` | Yes, if DTOs are independent | Source data is already in memory; this is not a JDBC stream. |
| JPA entity with already-loaded scalar fields | Loaded values remain readable | The entity may be detached; uninitialized lazy relations are a separate concern. |
| Unloaded lazy association on a detached JPA entity | Unsafe | Accessing it after the persistence context is unavailable may throw `LazyInitializationException`. |
| JDBC `Blob`/`Clob` locator or `InputStream` read from database | Not by default | May depend on an open connection/statement/locator; must be consumed or copied while valid. |
| `byte[]` fully read from a binary column | Yes | No longer depends on JDBC, though `byte[]` is mutable and can consume significant memory. |

Do not conclude "every JPA entity breaks as soon as the transaction ends". Already-initialized data can usually still be read after the entity is detached. The risk lies in operations that force the ORM to load additional data or mutate state through an unavailable persistence context. Likewise, do not assume "having `@Transactional` makes every returned value safe"; the annotation does not automatically materialize deferred data.

## 3. Correct Timeline in Spring JDBC

A normal query with `JdbcTemplate` follows this path:

~~~text
Caller
  │
  ▼
BookCatalogService.listBooks()      ← @Transactional(readOnly = true)
  │
  ▼
BookRepository.findAll()
  │  JdbcTemplate borrows Connection from DataSource/transaction
  │  Statement executes SELECT and creates ResultSet
  │  RowMapper reads each row, creates plain Java BookView
  │  JdbcTemplate collects List<BookView>
  │  ResultSet/Statement are closed
  ▼
List<BookView> with complete data
  │
  ▼
Service returns List.copyOf(...)
  │  Transaction ends; Connection is released back to DataSource/pool
  ▼
Caller reads List<BookView>              ← triggers no new queries
~~~

Without a transaction, `JdbcTemplate` still manages acquiring and releasing a connection for a single query; `ResultSet` closing and mapping remain sound. With a transaction, Spring keeps the connection bound to the transaction until the transaction finishes. What matters is that `RowMapper` reads values **before** the `ResultSet` is closed.

### Counterexample: Returning a Closed ResultSet

The following Java snippet **illustrates the bug only**; assume JDBC/`DataSource` imports and class declarations already exist:

~~~java
ResultSet findBooksWrong(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
                 "SELECT id, title, price FROM books");
         ResultSet resultSet = statement.executeQuery()) {

        return resultSet; // Wrong: resource is closed before caller uses it.
    }
}
~~~

This syntax compiles, yet as soon as `return` completes, Java closes the resources in `try-with-resources`. The caller receives a reference to a closed `ResultSet`, and reading from it throws `SQLException` (exact message depends on the driver).

The right way is to read data inside the `try` block and return Java values:

~~~java
List<BookView> findBooksWithPlainJdbc(DataSource dataSource)
        throws SQLException {
    List<BookView> result = new ArrayList<>();

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
                 "SELECT id, title, price FROM books ORDER BY id");
         ResultSet rs = statement.executeQuery()) {

        while (rs.next()) {
            result.add(new BookView(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getBigDecimal("price")));
        }
    }
    return List.copyOf(result);
}
~~~

This is also an **illustrative snippet inside a class**, using `BookView` and requiring imports for `DataSource`, `SQLException`, `ArrayList`, `List`, and `java.sql.*`. It demonstrates the lifetime rule; in Spring, prefer `JdbcTemplate` to eliminate manual resource closing, mapping boilerplate, and `SQLException` handling.

## 4. Complete Runnable Spring JDBC Example with Java 21

We will build a console application that reads a book list from H2. The service method runs in a read-only transaction; after the method returns, the runner proves the transaction is no longer active yet the DTOs remain readable.

Minimal structure:

~~~text
book-data-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/dataaccess/
    │   ├── BookCatalogApplication.java
    │   ├── BookView.java
    │   ├── BookRepository.java
    │   └── BookCatalogService.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
~~~

### 4.1. Gradle and H2 Configuration

File `settings.gradle`:

~~~groovy
rootProject.name = 'book-data-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:bookdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

File `src/main/resources/data.sql`:

~~~sql
INSERT INTO books (id, title, price) VALUES
    (1, 'Spring JDBC', 129.00),
    (2, 'Transaction Basics', 89.50);
~~~

The console application uses an in-memory database. On each startup in a new process, Spring Boot creates the schema and loads two sample rows. No separate database server is needed.

### 4.2. Plain Java DTO

File `src/main/java/example/dataaccess/BookView.java`:

~~~java
package example.dataaccess;

import java.math.BigDecimal;

public record BookView(long id, String title, BigDecimal price) {
}
~~~

`BookView` holds no `ResultSet`, `EntityManager`, supplier, or proxy to run queries later. Its `long`, `String`, and `BigDecimal` fields are already-read values with no ability to "self-fetch" more data. Records provide a simple carrier, though a record is **not automatically deep-immutable** if its fields are mutable `List`s, mutable `Date`s, `byte[]`, or an entity/proxy.

### 4.3. Repository Maps Immediately While ResultSet Is Alive

File `src/main/java/example/dataaccess/BookRepository.java`:

~~~java
package example.dataaccess;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BookRepository {
    private final JdbcTemplate jdbc;

    public BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<BookView> findAll() {
        return jdbc.query("""
                SELECT id, title, price
                FROM books
                ORDER BY id
                """,
                (rs, rowNum) -> new BookView(
                        rs.getLong("id"),
                        rs.getString("title"),
                        rs.getBigDecimal("price")));
    }
}
~~~

`JdbcTemplate` handles creating the `PreparedStatement`/`ResultSet` for the query and closing them when the query finishes. `RowMapper` runs while `ResultSet` is still open, converting each row into a `BookView`. The `query` method returns a materialized `List`. Never put `ResultSet` into a DTO field, and never store `RowMapper` to reuse the same `ResultSet` afterward.

### 4.4. Service Finalizes Data Before the Transaction Ends

File `src/main/java/example/dataaccess/BookCatalogService.java`:

~~~java
package example.dataaccess;

import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class BookCatalogService {
    private final BookRepository repository;

    public BookCatalogService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<BookView> listBooks() {
        System.out.println("In transaction: "
                + TransactionSynchronizationManager
                        .isActualTransactionActive());

        List<BookView> books = repository.findAll();
        return List.copyOf(books);
    }
}
~~~

`List.copyOf` creates a list whose structure cannot be altered via `add`/`remove`/`set`, preventing callers from mutating the container returned by the service. In this example, the `BookView` elements also contain only immutable types. For `List<MutableEntity>`, `List.copyOf` **does not** make each entity immutable: you must map and deep-copy any fields that need protection.

`readOnly = true` expresses read-only intent and may be optimized by the transaction manager/driver; it is not a guarantee that every write statement is blocked. What guarantees the data can be read after the transaction is that the repository converted all required values into DTOs.

### 4.5. Runner Reads Data After the Service Completes

File `src/main/java/example/dataaccess/BookCatalogApplication.java`:

~~~java
package example.dataaccess;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootApplication
public class BookCatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookCatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(BookCatalogService service) {
        return args -> {
            List<BookView> books = service.listBooks();

            System.out.println("Outside transaction: "
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());
            System.out.println("Book count: " + books.size());
            System.out.println("First book: " + books.get(0).title());
        };
    }
}
~~~

Run with JDK 21 and a Java 21-compatible Gradle (e.g., Gradle 8.5) in the `book-data-demo` directory:

~~~bash
gradle bootRun
~~~

Four lines printed by the program:

~~~text
In transaction: true
Outside transaction: false
Book count: 2
First book: Spring JDBC
~~~

This is the expected output of the runner executing outside any other transaction, calling the service through the Spring bean proxy. If an outer transaction wrapped the caller as well, the state outside the service would differ. In this standalone example, the output proves `List<BookView>` remains usable after the service's transaction has finished. **No open connection needs to be kept for the UI layer.**

## 5. Streaming Query Results: An Important Difference

Spring's `JdbcTemplate` provides `queryForStream`. Unlike a `List` from `query`, this `Stream` remains bound to the query and must be closed when finished. If a service returns the `Stream` directly to a controller and then ends the transaction, the caller may start iterating too late—when the connection/`ResultSet` is no longer valid—or forget to close it, leaking resources.

A method **must not expose** a JDBC `Stream` if callers are expected to consume it outside the JDBC scope:

~~~java
// Illustrates an error-prone API design, not an example to follow.
@Transactional(readOnly = true)
public Stream<BookView> listBooksAsOpenStream() {
    return jdbc.queryForStream(
            "SELECT id, title, price FROM books",
            (rs, rowNum) -> new BookView(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getBigDecimal("price")));
}
~~~

Upon `return`, the transaction proxy may complete the transaction; there is no guarantee the caller traverses the `Stream` before resources are released. Moreover, the `Stream` is not closed where it was created.

**The safe approach when streaming data:** consume and close the `Stream` **inside** the method that owns the query and transaction. Below is an illustrative method for a Spring bean with a `JdbcTemplate jdbc` field and imports for `Stream`, `Transactional`, and `BookView`:

~~~java
@Transactional(readOnly = true)
public long countBooksWithinTransaction() {
    try (Stream<BookView> stream = jdbc.queryForStream(
            "SELECT id, title, price FROM books",
            (rs, rowNum) -> new BookView(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getBigDecimal("price")))) {

        return stream.count();
    }
}
~~~

`try-with-resources` calls `Stream.close()` even if an exception occurs while consuming. This method returns a computed `long`, independent of `Stream` and JDBC. The method must be called through a Spring proxy for `@Transactional` to take effect under common proxy configurations. Pure row counting in production should usually use `SELECT COUNT(*)` rather than scanning all rows; the snippet above exists solely to illustrate `Stream` lifetime.

Additional notes:

- **A `Stream` created from a materialized `List<DTO>`** no longer depends on the database; for example, after receiving the `List` from `listBooks`, the caller can safely call `stream()` on the list.
- JDBC streaming does not automatically mean low memory usage: drivers may buffer rows; fetch size and cursor behavior vary by database/driver.
- For very large datasets, use pagination/keyset pagination or process sequentially inside a controlled transaction scope. Never return a connection-holding `Stream` to a presentation layer that runs for an indeterminate duration.

## 6. JPA/Hibernate: Detached Entities and Lazy Associations

With JPA, an entity can remain in memory after the persistence context ends. Its already-loaded scalar fields keep their values, but when code accesses an uninitialized lazy association, Hibernate normally must issue another query. If no session is available to serve the query, that operation can throw `LazyInitializationException`.

Example scenario:

~~~text
Service inside transaction:
  OrderEntity order = repository.findById(id).orElseThrow()
  return order

Controller/serializer after transaction:
  order.getLines()       ← lines have not been loaded
  needs another query    ← persistence context may already be closed
  LazyInitializationException
~~~

In web applications, Open Session in View (OSIV) can keep the persistence context open through rendering/serialization and mask late-firing queries. Do not rely on OSIV to define API contracts or solve N+1 problems; web requests can fire hard-to-control queries outside service transactions. OSIV settings and the framework/provider determine actual lifetimes, so the error does not always surface in every environment.

### Designing a Snapshot DTO Before Leaving the Transaction

The pattern below **illustrates a JPA service**, not a standalone program: assume `OrderEntity` with `getLines()`, `LineEntity` with `getSku()/getQuantity()`, and a Spring Data repository for `OrderEntity` already exist.

~~~java
record LineSnapshot(String sku, int quantity) {}

record OrderSnapshot(long id, List<LineSnapshot> lines) {
    public OrderSnapshot {
        lines = List.copyOf(lines);
    }
}

@Transactional(readOnly = true)
public OrderSnapshot findOrderSnapshot(long id) {
    OrderEntity order = orderRepository.findById(id).orElseThrow();

    List<LineSnapshot> lines = order.getLines().stream()
            .map(line -> new LineSnapshot(
                    line.getSku(), line.getQuantity()))
            .toList();

    return new OrderSnapshot(order.getId(), lines);
}
~~~

All required lazy-association access happens inside the transaction while the entity is still attached to the persistence context. The result consists of plain Java scalars and `LineSnapshot`s; once the service returns, callers never touch a lazy proxy. DTOs also restrict exposed data and avoid accidentally serializing an entire entity graph.

For a single order, loading lines inside the service may be reasonable. For a list of many orders, calling `getLines()` on each entity can trigger N+1 `SELECT`s. Proactively pick a fetch plan: JPQL DTO projection, fetch join, `@EntityGraph`, or batch fetching depending on context. Above all, **design the exact data to return and materialize at the right time**, rather than making every relation `EAGER` by default (which inflates query cost and graph size).

Also distinguish a snapshot DTO from a database snapshot transaction. A DTO is a snapshot of values already read; if the database changes afterward, the DTO does not auto-refresh. `@Transactional(readOnly = true)` does not by itself guarantee multiple queries observe the same data version: that also depends on isolation level, database engine, and query structure.

## 7. Nested Data, Mutable Data, and Large Columns

### 7.1. Nested Lists and Multi-Level Datasets

A DTO containing a `List` or `Map` is truly independent only if every needed element has been materialized and no longer retains proxies/lazy loaders. For example, an `OrderSnapshot` holding `List<LineSnapshot>` is safe when `LineSnapshot` contains only `String`, `int`, and `BigDecimal`. By contrast, copying a `List<OrderEntity>` protects only the **list structure**, not lazy associations inside each entity.

For nullable fields, define clearly the meaning of `null`, an empty list, and nonexistent data. Avoid placing a `Supplier` or `Function` inside a DTO to "lazy-load on demand", as that reintroduces a dependency on a service or session later.

### 7.2. Arrays, Mutable Objects, and Defensive Copies

When a `RowMapper` reads a `byte[]` from a binary column, the array is already loaded yet remains mutable. If a DTO exposes the array reference directly, callers can mutate the DTO's contents. To prevent that, copy both on construction and on access:

~~~java
public record BinarySnapshot(byte[] content) {
    public BinarySnapshot {
        content = content == null ? null : content.clone();
    }

    @Override
    public byte[] content() {
        return content == null ? null : content.clone();
    }
}
~~~

The record above is standalone Java 17+ when placed in `BinarySnapshot.java`. It illustrates that **lifetime independence** and **immutability to callers** are two distinct goals. For nested collections or other mutable objects, explicitly decide whether to deep-copy, map to immutable types, or expose a read-only view.

### 7.3. BLOB/CLOB and Loading Large Data

A JDBC `Blob`/`Clob` can be a locator tied to a connection. Similarly, an `InputStream` read from the database may require an open resource. Never return raw `Blob`/`Clob`/`InputStream` assuming the caller can read it arbitrarily after the repository closes JDBC. If the data is small and bounded, read the full `byte[]`/`String` inside `RowMapper` and return a DTO with an appropriate copy.

For large images, files, or reports, loading the entire payload into `byte[]` can create memory pressure. In that case, design a streaming API with an **explicit owner of the transaction, connection, and close**, or move the asset to object storage and return metadata/access links instead. Never mix long downloads with unnecessarily long database transactions.

## 8. Transaction Boundaries Are Not Object Boundaries

Several common misconceptions:

**Misconception 1: "Returning a JPA entity means the entity always dies when the transaction closes."** False. A detached entity is still a Java object; already-loaded data usually remains readable. Hidden failures arise from lazy associations, dirty checking no longer syncing automatically, or calling operations that require a persistence context.

**Misconception 2: "Having `@Transactional` on the method makes returning any `Stream` safe."** False. With proxy transactions, the transaction covers **method execution time**. When the method returns an active query `Stream`, the caller consumes the `Stream` after the transaction has already ended. Consume inside the same method and close the `Stream`, or return a loaded `List`/`Page` DTO.

**Misconception 3: "Keeping the `Connection` unclosed prevents errors."** This causes connection leaks, exhausts the pool, and degrades availability. The fix is to select and materialize data within a controlled resource lifetime.

**Misconception 4: "`List.copyOf` makes the entire object graph immutable."** Only the list becomes structurally unmodifiable. Elements, arrays, and entities may still be mutable or lazy.

**Misconception 5: "A materialized DTO means the data is always fresh."** An independent DTO allows safe reading without touching the database; it does not refresh when database rows change. If fresh data is needed, run a new query or use an intentional caching/invalidation strategy.

**Misconception 6: "Loading every relationship eagerly before returning is always best."** Making everything `EAGER` inflates queries, joins, and memory. Design DTOs per use case, load only needed fields, and paginate large sets.

**Misconception 7: "Self-calling a `@Transactional` method within the same class definitely opens a new transaction."** With default Spring proxying, self-invocation usually bypasses the proxy so the annotation on the self-called method does not take effect as expected. Place transaction boundaries on a public method called through another Spring bean, or use an appropriate architecture/proxy setup.

## 9. Verifying Behavior and Choosing Designs by Scenario

| Scenario | Appropriate approach | Why |
| --- | --- | --- |
| API needs to return 20 books | `JdbcTemplate.query` → `List<BookView>` | All 20 DTOs are mapped before resources close. |
| Listing page across 10,000 books | Paginated query + `List<DTO>` per page | Independent results without holding 10,000 objects in one response. |
| Sequential processing of millions of rows | Stream/cursor consumed and closed within resource owner's scope, or batching | Never exposes live handles; controls connections, transactions, and memory. |
| Returning a JPA `Order` with its line items | DTO projection or materialize `OrderSnapshot` in service | Callers never trigger lazy queries after the transaction. |
| Returning a small binary file | Read full `byte[]` and copy as needed | Avoids holding a `Blob` locator and prevents unintended data mutation. |
| Very large files | Streaming with clear lifecycle or storing files outside the database | Avoids loading everything into RAM and avoids long transactions. |

To self-verify the complete example in Section 4:

1. Run the application and verify the line `"In transaction: true"`, followed by `"Outside transaction: false"`.
2. Verify `List<BookView>` still holds two books, with the first title being `Spring JDBC`, even after the service transaction has finished.
3. Try mutating the `List` with `add` or `clear`: `List.copyOf` makes structural modifications throw `UnsupportedOperationException`.
4. Try creating an API that returns `ResultSet` from `try-with-resources` as in the counterexample: explain why `return` does not keep the resource open.
5. Simulate an entity with a `LAZY` association, return the entity when the persistence context is no longer active, and then redesign the API around a DTO containing only the fields the screen needs.
6. For a dataset of millions of rows, explain why proper lifetime materialization still requires size limits or pagination.

## 10. Checklist for a Data-Reading Method

Before publishing a data-reading API from a repository/service, verify:

- **Result contract:** DTO/value object holds all needed fields and carries no unexpected JDBC handles or lazy associations.
- **Materialization timing:** all values are read while the required `ResultSet`, persistence context, or stream is still valid.
- **Resource ownership:** `JdbcTemplate` or `try-with-resources` closes `Statement`/`ResultSet`/`Stream`; never pass ambiguous closing responsibility to callers.
- **Transactions:** placed on the service per use case; proxy actually applies; `readOnly` is not misused as a substitute for materialization.
- **Size:** controlled pagination, batching, or streaming for large lists; avoid unbounded deep copies just to dodge lazy errors.
- **Stability:** copy mutable collections/arrays when required by the contract; distinguish materialized snapshots from live data.
- **Verification:** run a test reading the DTO **after the transactional method returns**, disable OSIV when checking lazy-loading risks in web apps, and monitor the connection pool for leaks.

**Lesson conclusion:** a well-designed data layer returns **self-contained values**, while the lifecycles of `Connection`, `ResultSet`, `Stream`, and `EntityManager` are handled within clear ownership boundaries. Spring manages resources; developers must still decide what data to materialize, when transactions are needed, and what may cross service boundaries.

### References

- Spring Framework — Data Access with JDBC: https://docs.spring.io/spring-framework/reference/data-access/jdbc.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Boot — Working with SQL Databases: https://docs.spring.io/spring-boot/reference/data/sql.html
- Spring Framework API — JdbcTemplate: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
