# query() for Retrieving a List of Objects with Spring JDBC

In Spring JDBC, **`JdbcTemplate.query(...)`** is the primary API for reading **multiple rows** from a relational database and turning each row into a Java object. Instead of manually managing `Connection`, `PreparedStatement`, `ResultSet`, and a `while (rs.next())` loop, you provide the SQL and mapping rule to `JdbcTemplate`. Spring executes the query, iterates through each result row, invokes the mapper, and returns a `List<T>`.

For example: if a SQL query returns three rows from the `books` table, `query(...)` can return a `List<Book>` containing three `Book` objects. If the SQL returns no rows, the normal result is an **empty list**, not a "single record not found" exception.

This lesson belongs to **JDBC Queries** and focuses directly on **`query()` for retrieving a list of objects**: overload signatures, `RowMapper`, parameter binding, zero-row results, DAO design, pagination, and common mistakes.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Read the signature `<T> List<T> query(String sql, RowMapper<T> rowMapper, Object... args)` and trace the flow from SQL to each `List<T>` element.
2. Write `RowMapper<Book>` using a lambda, dedicated class, or reusable constant; never advance the `ResultSet` cursor manually.
3. Use `?` placeholders or named parameters to filter data safely instead of concatenating user strings.
4. Choose properly among `query`, `queryForObject`, `queryForList`, `queryForStream`, and `RowCallbackHandler`.
5. Handle `NULL`, column names, result ordering, duplicate rows from `JOIN`s, SQL dialects, and performance when querying many rows.
6. Test record counts, object contents, empty results, SQL errors, and pagination ordering.

## 2. How It Works: One Row to One Object

Suppose the query is:

~~~sql
SELECT id, title, pages
FROM books
WHERE pages >= ?
ORDER BY id
~~~

Returning:

| id | title | pages |
| ---: | --- | ---: |
| 1 | Java Basics | 320 |
| 2 | Spring JDBC | 240 |

You define the data type:

~~~java
public record Book(long id, String title, int pages) { }
~~~

And map each row into a `Book`:

~~~java
RowMapper<Book> bookMapper = (rs, rowNum) ->
        new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getInt("pages")
        );
~~~

Then call:

~~~java
List<Book> books = jdbcTemplate.query(
        """
        SELECT id, title, pages
        FROM books
        WHERE pages >= ?
        ORDER BY id
        """,
        bookMapper,
        240
);
~~~

These are **integration snippets**: assuming `jdbcTemplate` is provided by Spring and the `books` table and sample data exist; not a standalone program. Section 4 has a complete runnable program.

Conceptually, Spring performs:

~~~text
DAO calls JdbcTemplate.query(sql, mapper, args)
    |
    v
Acquire appropriate JDBC Connection from DataSource/transaction
    |
    v
Create PreparedStatement, bind parameters (pages >= 240)
    |
    v
Execute SQL -> ResultSet
    |
    +-- row 0 -> mapper.mapRow(rs, 0) -> Book(1, ...)
    |
    +-- row 1 -> mapper.mapRow(rs, 1) -> Book(2, ...)
    |
    +-- no more rows
    |
    v
Close ResultSet/Statement, release Connection as appropriate
    |
    v
Return List<Book>
~~~

### Responsibilities of Each Component

| Component | Responsibility |
| --- | --- |
| `JdbcTemplate` | Executes SQL, manages JDBC resources, translates `SQLException`, and collects results |
| `DataSource` | Supplies a JDBC `Connection` or pooled connection |
| `PreparedStatement` | Executes SQL with bound parameters |
| `ResultSet` | Cursor reading the rows returned by the query |
| `RowMapper<T>` | Converts **the currently positioned row** into one `T` |
| `List<T>` | Holds the objects after the query completes; stored in application memory |

**Most important point:** `JdbcTemplate` is responsible for calling `rs.next()` to advance through each row. `RowMapper.mapRow(rs, rowNum)` only reads **the current row** and returns an object. **Do not call `rs.next()` inside `RowMapper`.** Manually advancing the cursor can skip rows, return wrong data, or break the template's iteration loop.

The `rowNum` parameter is the 0-based result row index; it is neither the table's ID nor a stable index across runs if SQL lacks `ORDER BY`.

## 3. Overloads of query() and How to Choose

The following patterns all use Spring JDBC `JdbcTemplate`:

~~~java
// A. Fixed SQL, no bound parameters: returns List<Book>.
List<Book> all = jdbcTemplate.query(
        "SELECT id, title, pages FROM books ORDER BY id",
        bookMapper);

// B. SQL with positional parameter: RowMapper first, values after.
List<Book> filtered = jdbcTemplate.query(
        "SELECT id, title, pages FROM books WHERE pages >= ? ORDER BY id",
        bookMapper,
        240);

// C. Multiple parameters: match the order of ? in SQL.
List<Book> range = jdbcTemplate.query(
        """
        SELECT id, title, pages FROM books
        WHERE pages >= ? AND pages <= ?
        ORDER BY pages, id
        """,
        bookMapper,
        150,
        350);
~~~

All are snippets requiring `jdbcTemplate`, `bookMapper`, and the existing schema. **The modern syntax to prefer** is:

~~~java
jdbcTemplate.query(sql, rowMapper, arg1, arg2);
~~~

An older overload taking `Object[] args` before `RowMapper` has been deprecated in modern Spring Framework branches; avoid copying old examples just because they show `query(sql, new Object[]{...}, mapper)`.

### 3.1. Lambda RowMapper vs. Dedicated Class

If a mapper is used in only one place and the mapping is short, a lambda is clear enough:

~~~java
List<Book> books = jdbcTemplate.query(
        "SELECT id, title, pages FROM books ORDER BY id",
        (rs, rowNum) -> new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getInt("pages")));
~~~

If multiple DAO methods share the same mapping, extract a constant:

~~~java
private static final RowMapper<Book> BOOK_MAPPER =
        (rs, rowNum) -> new Book(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getInt("pages"));
~~~

If the mapping is long, involves substantial conversion/domain validation, or is shared across classes, implement a `BookRowMapper implements RowMapper<Book>` class. Either way, the mapper should be **stateless**: do not store `ResultSet` or the current list in singleton fields, and do not mutate shared objects across requests.

### 3.2. PreparedStatementSetter for Specialized Binding

When you need SQL type control or binding beyond simple values, there is an overload accepting `PreparedStatementSetter`:

~~~java
List<Book> books = jdbcTemplate.query(
        """
        SELECT id, title, pages
        FROM books WHERE pages >= ? ORDER BY id
        """,
        ps -> ps.setInt(1, 240),
        BOOK_MAPPER);
~~~

This is a DAO snippet with `JdbcTemplate` and `BOOK_MAPPER`. JDBC uses **1-based** parameter indices (`ps.setInt(1, ...)`), unlike mapper `rowNum` which starts at 0. Never use `PreparedStatement` to concatenate unsafe input. For normal parameter counts, the varargs overload is simpler.

### 3.3. What Happens When There Are No Rows?

~~~java
List<Book> none = jdbcTemplate.query(
        "SELECT id, title, pages FROM books WHERE pages > ?",
        BOOK_MAPPER,
        1_000_000);
System.out.println(none.isEmpty()); // true
~~~

This example applies when the database has no `books.pages` matching the condition. `query` returns an empty `List<Book>`; the mapper **is not invoked** if the `ResultSet` has no rows. There is no need for `try/catch(EmptyResultDataAccessException)` just to handle an empty list.

Conversely, invalid SQL, lost connections, permission errors, or invalid bindings can still throw a `DataAccessException` (or a runtime error from mapping code). **An empty list does not mean a failed query.**

## 4. Runnable Program: Java 17+, Spring JDBC, and H2

This example creates an H2 table, inserts three books, and demonstrates querying all rows, querying with a condition, querying zero rows, and querying by a boolean. It **does not require Spring Boot**, yet uses real Spring JDBC APIs.

Structure:

~~~text
jdbc-list-query/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/App.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jdbc-list-query'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.11'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}
~~~

`src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;
import java.util.List;

public class App {

    public record Book(
            long id, String title, int pages, boolean available) {
    }

    public static class BookDao {
        private static final RowMapper<Book> BOOK_MAPPER =
                (rs, rowNum) -> new Book(
                        rs.getLong("id"),
                        rs.getString("title"),
                        rs.getInt("pages"),
                        rs.getBoolean("available"));

        private final JdbcTemplate jdbc;

        public BookDao(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public List<Book> all() {
            return jdbc.query(
                    """
                    SELECT id, title, pages, available
                    FROM books ORDER BY id
                    """,
                    BOOK_MAPPER);
        }

        public List<Book> withAtLeastPages(int minPages) {
            return jdbc.query(
                    """
                    SELECT id, title, pages, available
                    FROM books
                    WHERE pages >= ?
                    ORDER BY id
                    """,
                    BOOK_MAPPER,
                    minPages);
        }

        public List<Book> available() {
            return jdbc.query(
                    """
                    SELECT id, title, pages, available
                    FROM books
                    WHERE available = ?
                    ORDER BY id
                    """,
                    BOOK_MAPPER,
                    true);
        }
    }

    public static void main(String[] args) {
        DataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:library;DB_CLOSE_DELAY=-1", "sa", "");
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE books (
                    id BIGINT PRIMARY KEY,
                    title VARCHAR(100) NOT NULL,
                    pages INT NOT NULL,
                    available BOOLEAN NOT NULL
                )
                """);

        jdbc.update(
                "INSERT INTO books VALUES (?, ?, ?, ?)",
                1L, "Java Basics", 320, true);
        jdbc.update(
                "INSERT INTO books VALUES (?, ?, ?, ?)",
                2L, "Spring JDBC", 240, true);
        jdbc.update(
                "INSERT INTO books VALUES (?, ?, ?, ?)",
                3L, "SQL Primer", 180, false);

        BookDao dao = new BookDao(jdbc);

        System.out.println("All: " + dao.all());
        System.out.println("At least 240 pages: " + dao.withAtLeastPages(240));
        System.out.println("Not found: " + dao.withAtLeastPages(500));
        System.out.println("Available: " + dao.available());
    }
}
~~~

Run inside the `jdbc-list-query` directory, with JDK 17+ and a compatible Gradle version:

~~~bash
gradle run --quiet
~~~

**Program stdout** (excluding any log lines Gradle/the driver might print):

~~~text
All: [Book[id=1, title=Java Basics, pages=320, available=true], Book[id=2, title=Spring JDBC, pages=240, available=true], Book[id=3, title=SQL Primer, pages=180, available=false]]
At least 240 pages: [Book[id=1, title=Java Basics, pages=320, available=true], Book[id=2, title=Spring JDBC, pages=240, available=true]]
Not found: []
Available: [Book[id=1, title=Java Basics, pages=320, available=true], Book[id=2, title=Spring JDBC, pages=240, available=true]]
~~~

### 4.1. Step-by-Step Walkthrough

1. `DriverManagerDataSource` creates a JDBC connection source to in-memory H2. `DB_CLOSE_DELAY=-1` keeps the database alive for the JVM lifetime even after the last connection closes. This is a **demo** configuration with no pooling.
2. `jdbc.execute(CREATE TABLE ...)` creates four `NOT NULL` columns so the mapper can read `long`, `int`, and `boolean` without handling SQL `NULL`.
3. Three `jdbc.update` calls use `?` to bind data separately from SQL. Binding mitigates SQL injection through input **values**.
4. `BookDao` receives `JdbcTemplate` via its constructor and uses a stateless `BOOK_MAPPER`. Each row becomes a new `Book`; Java records generate `toString()`, so printed output has the form `Book[id=..., title=..., ...]`.
5. `all()` returns three elements; `withAtLeastPages(240)` returns two; `withAtLeastPages(500)` returns an empty list; `available()` filters on a `BOOLEAN` column.
6. Every SQL query includes `ORDER BY id`, making element order in `List` predictable. Without `ORDER BY`, the database **does not guarantee** row order.
7. After each `query`, `JdbcTemplate` closes the JDBC statement/result set and releases the connection within scope (or participates in an active transaction). `List<Book>` holds **already-mapped Java objects**, with no open `ResultSet`.

The example omits `@Transactional` because it only illustrates independent queries. When transactional services exist, let Spring manage the transaction manager and boundaries. In Spring Boot, you normally inject the auto-configured `JdbcTemplate` bean instead of instantiating `DriverManagerDataSource` in business code.

## 5. Placing query() in a DAO/Repository

A common layout:

~~~text
Controller / Scheduled job
          |
          v
       Service
          |
          v
    BookRepository
          |
          v
  JdbcTemplate.query(...)
          |
          v
        Database
~~~

Instead of letting controllers write SQL, the DAO encapsulates lookups into meaningful methods:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public class BookRepository {
    private static final RowMapper<Book> MAPPER = (rs, n) ->
            new Book(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getInt("pages"));

    private final JdbcTemplate jdbc;

    public BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Book> findByMinimumPages(int minPages) {
        return jdbc.query(
                """
                SELECT id, title, pages FROM books
                WHERE pages >= ? ORDER BY id
                """,
                MAPPER,
                minPages);
    }
}
~~~

This is a snippet in a Spring application that already has a `JdbcTemplate` bean and the three-field `Book` type from section 2; it is not a standalone class. Constructor injection makes dependencies explicit and easy to swap in tests. `@Repository` registers the bean when component scanning is enabled; a single constructor does not need `@Autowired`.

Do not cache the resulting `List<Book>` in a singleton field just to "reuse" it without a clear caching/invalidation strategy: that data changes in the database, unlike reusing `JdbcTemplate` or a stateless `RowMapper`.

### 5.1. Designing Return Contracts

Several options:

- `List<Book> findAll()`: use `query`; no rows -> empty `List`.
- `List<Book> findByStatus(...)`: still use `query`, since 0 to N rows may exist.
- `Optional<Book> findById(...)`: typically query a small list and check 0/1, or use a single-row API with appropriate cardinality handling.
- `Book getRequiredById(...)`: if business rules require exactly one row, use `queryForObject` and translate "not found" into an appropriate domain error.
- `Page<Book> findPage(...)`: requires pagination SQL and a total-count query as needed; `JdbcTemplate.query` by itself only produces a `List` and does not populate `Page` metadata.

Do not force every SELECT to use `queryForObject`: that method's name clearly states it expects **one row**.

## 6. Easily Confused Differences with Other Query APIs

| API | Result / mechanism | When to use |
| --- | --- | --- |
| `query(sql, rowMapper, args...)` | `List<T>`, each row becomes one `T` | 0..N objects with custom mapping |
| `queryForObject(sql, rowMapper, args...)` | One `T`; errors if row count != 1 | Queries requiring exactly one row |
| `queryForList(sql, String.class, args...)` | `List<String>` for **single-column** results | Scalar lists: names, emails, codes |
| `queryForList(sql, args...)` | `List<Map<String,Object>>` | Dynamic data inspection without a fixed DTO |
| `queryForStream(sql, rowMapper, args...)` | `Stream<T>` holding resources that must be closed | Controlled streaming result processing |
| `query(sql, RowCallbackHandler)` | Callback processing each row without building `List<T>` | Avoid accumulating all data in memory while processing |
| `query(sql, ResultSetExtractor<T>)` | Function receiving the full `ResultSet` to extract `T` | Merging multiple rows into a special object graph |
| `JdbcClient.sql(...).query(Book.class).list()` | Fluent API building a list via an appropriate mapper | Spring Framework 6.1+ code preferring fluent syntax |

### 6.1. queryForObject() Throws on Zero Rows

~~~java
Book book = jdbcTemplate.queryForObject(
        "SELECT id, title, pages FROM books WHERE id = ?",
        BOOK_MAPPER,
        123L);
~~~

If the SQL returns no rows, `queryForObject` throws `EmptyResultDataAccessException` (a branch of `IncorrectResultSizeDataAccessException`). If it returns more than one row, it also throws an incorrect-result-size error. This differs from `query(...)`, which returns an empty list on zero rows.

This snippet requires `BOOK_MAPPER` for `Book` and a real database. How `not found` is handled should be decided by the business contract; do not force every method to return `null`.

### 6.2. queryForList() for Scalar Lists

~~~java
List<String> titles = jdbcTemplate.queryForList(
        "SELECT title FROM books WHERE pages >= ? ORDER BY id",
        String.class,
        240);
~~~

Returns `List<String>`, needing no `RowMapper<Book>` since the query selects one column. If the query returns multiple columns while you request `String.class`, a column-count mismatch error is thrown. For multi-field DTOs, `query(...)` with `RowMapper` is usually clearer than `List<Map<String,Object>>`.

### 6.3. ResultSetExtractor vs. RowMapper

`RowMapper` converts **one row into one object**. `ResultSetExtractor<T>` is invoked with the entire `ResultSet` so it can control `rs.next()` and aggregation logic itself. If a `JOIN` causes a book to repeat per author, you can use `ResultSetExtractor` to assemble one `BookWithAuthors` from multiple rows. For simple 1-row = 1-object queries, `RowMapper` is less error-prone and easier to test.

## 7. Handling SQL NULL Columns and Type Mapping

The mapper must reflect the schema. The example above uses `id BIGINT NOT NULL`, `pages INT NOT NULL`, `available BOOLEAN NOT NULL`. If a column can be `NULL`:

~~~java
int rawPages = rs.getInt("pages");
Integer pages = rs.wasNull() ? null : rawPages;
~~~

Reason: primitive getters like `getInt(...)`, `getLong(...)`, and `getBoolean(...)` return `0`/`false` for SQL `NULL`; to distinguish null, call `rs.wasNull()` **immediately after** that column's getter. For `String`, `getString(...)` returns `null` on SQL NULL.

Example mapper for a nullable record:

~~~java
record BookView(long id, String title, Integer pages) {}

RowMapper<BookView> mapper = (rs, rowNum) -> {
    int raw = rs.getInt("pages");
    Integer pages = rs.wasNull() ? null : raw;
    return new BookView(
            rs.getLong("id"),
            rs.getString("title"),
            pages);
};
~~~

These two snippets belong inside a mapper/method; they are not standalone programs. If `id` is also nullable, choose a wrapper type and matching read logic.

### 7.1. Column Aliases for Stable Mappers

When SQL has expressions, joins, or column names differing from the DTO, use aliases:

~~~sql
SELECT
    b.id AS book_id,
    b.title AS book_title,
    COUNT(r.id) AS review_count
FROM books b
LEFT JOIN reviews r ON r.book_id = b.id
GROUP BY b.id, b.title
ORDER BY b.id
~~~

The matching mapper reads `rs.getLong("book_id")`, `rs.getString("book_title")`, `rs.getLong("review_count")`. This is **illustrative SQL**, requiring a `reviews` table to exist. Aliases prevent ambiguity when two tables share an `id` column and establish a clear contract between query and mapper.

Select only the columns actually needed; avoid `SELECT *` in APIs with fixed DTOs, because schema changes or JOINs can introduce ambiguous columns and increase network/memory load.

### 7.2. Automatic Mapping with BeanPropertyRowMapper/DataClassRowMapper

Spring also provides:

- `BeanPropertyRowMapper<T>`: maps column names to JavaBean properties with a no-arg constructor and matching setters; convenient for simple JavaBean DTOs.
- `DataClassRowMapper<T>`: supports data-class-style constructors/record mapping, relying on constructor parameter-name metadata; fits when column names match record components.
- `ColumnMapRowMapper`, `SingleColumnRowMapper`: serve map results or single-column results.

**Integration illustration** for the three-field record from section 2:

~~~java
import org.springframework.jdbc.core.DataClassRowMapper;

List<Book> books = jdbcTemplate.query(
        "SELECT id, title, pages FROM books ORDER BY id",
        DataClassRowMapper.newInstance(Book.class));
~~~

Not every SQL alias/type matches automatically. Automatic mappers rely on reflection/conversion, which is convenient but may detect column mismatches or missing data later and carry extra overhead compared to explicit mappers. For performance-critical paths, custom conversions, or strict schema contracts, a hand-written `RowMapper` is usually easier to control.

## 8. Parameter Binding and SQL Safety

For user-supplied values, **never concatenate directly** into SQL:

~~~java
// Wrong: vulnerable to SQL injection.
String sql = "SELECT id, title, pages FROM books WHERE title = '"
        + userInput + "'";
List<Book> unsafe = jdbcTemplate.query(sql, BOOK_MAPPER);
~~~

Replace with `?` placeholders:

~~~java
List<Book> safe = jdbcTemplate.query(
        """
        SELECT id, title, pages
        FROM books WHERE title = ?
        ORDER BY id
        """,
        BOOK_MAPPER,
        userInput);
~~~

These snippets assume `userInput`, `BOOK_MAPPER`, and the repository are defined. The JDBC driver binds value parameters in a `PreparedStatement`, preventing them from being interpreted as SQL syntax.

**Caveat:** Placeholders normally substitute **values** only, not identifiers like table/column names or `ORDER BY ASC/DESC` direction. If sorting by user input is allowed, use an **allowlist** of valid columns/directions and assemble only validated identifiers. Never accept raw SQL fragments from an API.

### 8.1. NamedParameterJdbcTemplate for Complex Conditions

When there are many optional conditions, named parameters are more readable than positional `?` ordering:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

MapSqlParameterSource parameters =
        new MapSqlParameterSource()
                .addValue("minimum", 150)
                .addValue("maximum", 350);

List<Book> books = namedJdbc.query(
        """
        SELECT id, title, pages FROM books
        WHERE pages BETWEEN :minimum AND :maximum
        ORDER BY id
        """,
        parameters,
        BOOK_MAPPER);
~~~

`namedJdbc` is a `NamedParameterJdbcTemplate` injected into the DAO; this is an integration snippet. Spring parses named parameters into placeholders and binds them safely. `IN (:ids)` also supports appropriate collections, but you must handle an empty `ids` collection proactively: do not rely on `IN ()`, which may be invalid in your SQL dialect. When an ID collection is empty, usually return `List.of()` immediately or apply another query policy.

In a repository with multiple APIs, choose `JdbcTemplate` or `NamedParameterJdbcTemplate` based on SQL clarity; both can share the same `DataSource` and participate in appropriate transactions.

## 9. Ordering, JOINs, DISTINCT, and Duplicate Objects

**`List` preserves the row order returned by the query.** However, if SQL lacks `ORDER BY`, the database does not guarantee a stable order, even with a primary key. For paginated APIs, always define a deterministic order, such as `ORDER BY created_at DESC, id DESC` to break ties.

`JOIN` can multiply rows. For example, if a book has three tags, joining `books`–`book_tags` yields three rows for the same book. `query(..., BOOK_MAPPER)` will create **three `Book` objects**, because basic mapping is **one row -> one element**; the template does not deduplicate IDs automatically.

How to handle this depends on requirements:

1. Only need distinct books: rewrite the SQL using `EXISTS`, `SELECT DISTINCT`, or query book keys first, depending on data and SQL dialect.
2. Need a book + tags object graph: use `ResultSetExtractor` to fold multiple rows into one parent object, or run separate parent/child queries and merge in a controlled way.
3. Need parent pagination: paginate on parent keys first; avoid applying `LIMIT/OFFSET` directly to a child-joined result, which causes missing/partial parents.

Do not rely on `stream().distinct()` after loading millions of rows to "patch over" a bad JOIN query; fixing it at the SQL level is usually far more efficient.

## 10. Paginating Lists: Avoiding Unbounded Loads

`jdbcTemplate.query(...)` with a standard `RowMapper` materializes the **entire `List<T>`** before the method returns. If a query returns millions of rows, allocating and retaining all those objects can consume large amounts of RAM and create GC pressure. Paginate in the database, bound result sizes, and select only needed projections.

SQL example for PostgreSQL, H2, or dialects supporting `LIMIT/OFFSET` (application snippet with existing mapper):

~~~java
public List<Book> findPage(int pageSize, long offset) {
    if (pageSize < 1 || pageSize > 100 || offset < 0) {
        throw new IllegalArgumentException("Invalid page request");
    }
    return jdbcTemplate.query(
            """
            SELECT id, title, pages FROM books
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            BOOK_MAPPER,
            pageSize,
            offset);
}
~~~

`LIMIT/OFFSET` is not portable SQL across every database. SQL Server, Oracle, and other dialects have different syntax; binding/pagination must be verified on your actual driver.

**Recommendations:**

- Enforce page size limits in the service/API; do not let clients request hundreds of thousands of records at once.
- Use a deterministic `ORDER BY`, adding a unique column like `id` to break ties.
- Consider **keyset pagination** for very deep lists (filtering by the last returned key) to avoid large OFFSET costs; requires suitable SQL and indexes.
- If the API needs total row counts, run an appropriate `COUNT(*)` query via `queryForObject(..., Long.class)`; `query` only returns the data list, not total page counts.
- Avoid `SELECT *` and loading large blobs/texts when a list view only needs a few fields.

### 10.1. Fetch Size Is Not Page Size

`JdbcTemplate.setFetchSize(500)` is a **JDBC driver hint** for how many rows to fetch per round-trip, not a guarantee that the result contains only 500 items. `jdbcTemplate.query(...)` can still collect the entire list in RAM. Fetch size effectiveness depends on the driver, DB, autocommit/transaction state, and cursors.

`setMaxRows` can cap a result set at the statement level, yet it is no substitute for pagination semantics with `ORDER BY` and explicit SQL conditions. If a template is shared across DAOs, setting max rows globally can silently truncate data in other queries.

## 11. Processing Large Datasets Without Building a Huge List

When processing row by row (file export, aggregation, forwarding to a pipeline) instead of returning a list to an API, consider `RowCallbackHandler` or `queryForStream`.

### 11.1. RowCallbackHandler

~~~java
jdbcTemplate.query(
        "SELECT id, title, pages FROM books ORDER BY id",
        rs -> {
            long id = rs.getLong("id");
            String title = rs.getString("title");
            int pages = rs.getInt("pages");
            exportOneRow(id, title, pages);
        });
~~~

This snippet assumes `exportOneRow(...)` writes to an appropriate sink. Spring already advances the cursor; `RowCallbackHandler.processRow` **must not call `rs.next()`**. This avoids building a `List<Book>`, though the SQL driver may still buffer rows; check DB streaming/cursor settings and avoid slow I/O inside long transactions without assessing the impact.

### 11.2. queryForStream Requires Closing the Stream

~~~java
import java.util.stream.Stream;

try (Stream<Book> stream = jdbcTemplate.queryForStream(
        "SELECT id, title, pages FROM books ORDER BY id",
        BOOK_MAPPER)) {
    stream.forEach(book -> processBook(book));
}
~~~

This snippet requires `processBook` and the existing mapper. `queryForStream` returns a `Stream` holding JDBC resources until closed; **use try-with-resources** and consume it within a valid connection/transaction scope. Never return a stream tied to an open `ResultSet` out of a service and forget to close it.

**Note:** JDBC is still blocking I/O. Using Java `Stream` does not turn `JdbcTemplate` into R2DBC/reactive and does not create cross-driver backpressure. For APIs returning a bounded page list, `query(..., RowMapper)` remains the simpler choice.

## 12. Transactions, DataSource, and Thread Safety

`JdbcTemplate` acquires connections through Spring's infrastructure; inside a JDBC transaction coordinated by `DataSourceTransactionManager` or `JdbcTransactionManager`, templates sharing the same `DataSource` can reuse the connection bound to the current transaction.

~~~text
Service @Transactional
    |
    +--> dao.findBooks() -> jdbcTemplate.query(...) -> transaction Connection
    |
    +--> dao.findTags()  -> jdbcTemplate.query(...) -> same transaction context
    |
    +--> commit or rollback
~~~

Conditions: calls must go through proper transaction infrastructure, share the same resource, and manage context properly. Sharing one `JdbcTemplate` across two DAOs does **not** automatically start a transaction; without `@Transactional`, each query may run on its own autocommit/connection.

`@Transactional(readOnly=true)` can serve as an optimization/hint for read queries, though it does not guarantee the database blocks all writes. Do not keep read transactions open across external API calls, user wait times, or very slow file exports when a consistent snapshot is unnecessary.

**Concurrency:** A configured `JdbcTemplate` itself is thread-safe for sharing across threads. However, if a `RowMapper` or DAO holds mutable fields acting as a buffer for the list being read, race conditions still occur. Each `query` call should create its own result objects; do not mutate `jdbcTemplate.setFetchSize`/`setQueryTimeout` across concurrent requests as if they were per-call options.

## 13. Exception Handling: SQL Errors vs. Empty Lists

Spring translates many JDBC errors into the `DataAccessException` (runtime) hierarchy. Cases to distinguish:

| Symptom | How to interpret |
| --- | --- |
| Valid query returns no rows | `query(...)` returns an empty list |
| Valid query returns 10 rows | List contains 10 mapped results (unless mapper itself returns `null` for a row) |
| Invalid SQL syntax | Typically `BadSqlGrammarException`, a `DataAccessException` |
| Dropped connection | A `DataAccessException` subtype depending on translator/driver |
| Mapper reads non-existent column | May throw `SQLException` translated by Spring, or a corresponding runtime error |
| Mapper throws `IllegalArgumentException` | Runtime error from mapping logic; not automatically converted to `DataAccessException` |
| `queryForObject` gets no rows | `EmptyResultDataAccessException` |
| `queryForObject` gets more than one row | `IncorrectResultSizeDataAccessException` |

Do not wrap queries in `catch(Exception e) { return List.of(); }`: that turns outages or SQL bugs into "no data" results, hiding incidents. Let errors propagate to the service/exception handler layer; return an empty list only when the query genuinely succeeded with zero records.

A mapper returning `null` for a row differs from an empty list: the resulting list can contain `null` elements. For domain DTOs, either map cleanly or throw an explicit error rather than silently returning null per row.

## 14. Testing query() Meaningfully

In integration tests against H2 or a production-compatible database, prepare data with intentional ordering and verify:

1. **Multiple rows:** `query` returns the exact element count and matching id/title/pages—do not check only `size()`.
2. **Zero rows:** `query` returns an empty `List`, without throwing `EmptyResultDataAccessException`.
3. **Parameter binding:** with minPages 240, SQL selects the right books; test unusual inputs to verify no unsafe SQL concatenation.
4. **Ordering:** `ORDER BY id` returns rows by ID; with pagination, test ties on the sort key.
5. **Null/type mapping:** include a nullable column and verify NULL is not conflated with `0`/`false`.
6. **JOIN/duplicates:** if the query joins one-to-many, verify whether the API returns the expected parent count or produces duplicate items like the SQL result.
7. **Error paths:** intentionally reference a missing table/column in a dedicated test and verify errors are not turned into an empty list.
8. **Result bounds:** query a sufficiently large set to test paging, memory, and fetch/cursor behavior on the real driver.

In Spring Boot, `@JdbcTest` provides a JDBC test slice; for dialect-specific SQL, locking, or collation, H2 alone is insufficient. Run tests on a production-compatible database (e.g., via Testcontainers). Mocking `JdbcTemplate` helps test service business decisions, but does not prove the SQL query and mapper actually work.

### Practice Exercises

- **Exercise 1:** In the section 4 example, add `findByTitle(String title)` returning `List<Book>`, using `WHERE title = ?`. Test a matching title and a non-existent title.
- **Exercise 2:** Change the mapper to a record `BookSummary(long id, String title)` and SELECT only two columns in SQL. Compare fetched data against `SELECT *`.
- **Exercise 3:** Add a nullable `description` field and map `String` properly; then test nullable `pages` using `getInt()/wasNull()`.
- **Exercise 4:** Add a `LIMIT ? OFFSET ?` query and test two consecutive pages with `ORDER BY id`; write a test case for an invalid page size.
- **Exercise 5:** Suppose books have multiple authors; write a SQL JOIN causing the same book to appear twice. Choose `EXISTS`/`DISTINCT` or `ResultSetExtractor` per API needs and explain why.
- **Exercise 6:** Write a test demonstrating "`query` with zero rows -> `[]`" vs. "`queryForObject` with zero rows -> exception".

## 15. Production Checklist for Using query()

- [ ] SQL selects only columns needed by the DTO; mapper reads exact column names/aliases and types.
- [ ] `ORDER BY` is present whenever stable order matters, especially for pagination.
- [ ] Use `?`/named binding for values; allowlists for dynamic identifiers/sort order.
- [ ] `RowMapper` maps only the current row, never calls `rs.next()`, and holds no shared request state.
- [ ] Choose `List<T>` for 0..N rows; handle empty lists according to contract.
- [ ] Use `queryForObject` only when expecting exactly one row; `queryForList` when only scalars/maps are needed.
- [ ] Handle nullable numeric/boolean values properly using wrappers and `rs.wasNull()`.
- [ ] Check whether JOINs multiply rows and use suitable projections/mappings.
- [ ] Cap page size and fetched rows; never read millions of records into a list by default.
- [ ] When using `queryForStream`, always close the stream; with callbacks, avoid accidentally buffering everything.
- [ ] Inject the configured `JdbcTemplate`; use the proper `DataSource`/transaction manager.
- [ ] Never swallow SQL errors as empty lists; log and handle `DataAccessException` properly.
- [ ] Test results, zero rows, SQL errors, and real dialect behavior via integration tests.

**Key takeaway:** `JdbcTemplate.query(sql, rowMapper, args...)` means **"run a multi-row SQL query, turn each row into an object, and return a list"**. `RowMapper` bridges one `ResultSet` row to one `T`; `JdbcTemplate` handles iteration and JDBC resources. Empty results, sorting, safe parameter binding, and row bounds are essential parts of the repository contract.

## Official Documentation

- [Spring Framework — JdbcTemplate and Querying Data](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — JDBC Data Access](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework — RowMapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html)
- [Spring Framework — BeanPropertyRowMapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html)
- [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Boot — Working with SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
