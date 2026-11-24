# JdbcClient Provides a Fluent API Starting in Spring Framework 6.1

> **Topic:** Spring Framework – data-access  
> **Knowledge Group:** JdbcClient  
> **Target Version:** Spring Framework **6.1** and above, with concrete examples on Spring **6.1.14** and Java **17+**

## 1. The Problem JdbcClient Solves

Spring JDBC already has `JdbcTemplate` for executing SQL with positional parameters `?`, along with `NamedParameterJdbcTemplate` for executing SQL with named parameters `:id`, `:status`. Both APIs are stable and useful, but when query code involves many parameters and mapping options, calls can become verbose and require choosing an overload up front.

**Starting in Spring Framework 6.1**, `org.springframework.jdbc.core.simple.JdbcClient` provides a unified **fluent API** facade for common JDBC query and update operations. Developers write a chain of actions in a natural sequence:

~~~text
client
  .sql("SELECT ... WHERE id = :id")
  .param("id", wantedId)
  .query(Book.class)
  .optional()
~~~

The flow is immediately readable: build the SQL statement → bind parameters → choose the mapping strategy → choose the result shape. For writing data:

~~~text
client
  .sql("UPDATE ... SET ... WHERE ...")
  .param(...)
  .update()
~~~

**Key point:** `JdbcClient` is **not a new JDBC driver, ORM, or JPA repository**. It reorganizes how those core JDBC capabilities are invoked and **delegates to `JdbcTemplate` and `NamedParameterJdbcTemplate`** underneath. Therefore, the application still needs a `DataSource` and a JDBC driver, and still needs to write SQL and handle SQL injection, mapping, transactions, connection pooling, and exception handling.

Objectives after this lesson: understand the place of `JdbcClient` in Spring JDBC, use the exact 6.1 syntax, choose positional/named parameters, map scalars/maps/records in multiple ways, handle 0/1/n rows, write data, integrate beans and transactions, recognize the facade's limitations, and run a Java 17 demo.

## 2. Where Does JdbcClient Sit in the Spring Data Access Architecture?

~~~text
Application / Service
         |
         v
Hand-written SQL Repository
         |
         v
JdbcClient  (fluent facade, since Spring Framework 6.1)
         |
         +--> JdbcTemplate                (positional params)
         |
         +--> NamedParameterJdbcTemplate  (named params)
                  |
                  v
          DataSource / JDBC Connection
                  |
                  v
             JDBC Driver
                  |
                  v
               Database
~~~

`JdbcClient` lives in the `spring-jdbc` artifact, package:

~~~java
import org.springframework.jdbc.core.simple.JdbcClient;
~~~

With the basic API:

~~~java
JdbcClient client = JdbcClient.create(dataSource);
~~~

or by reusing an already configured template:

~~~java
JdbcTemplate template = new JdbcTemplate(dataSource);
JdbcClient client = JdbcClient.create(template);
~~~

In addition to `DataSource` and `JdbcOperations`, Spring 6.1 also provides the `create(NamedParameterJdbcOperations)` factory method. These factories do not execute SQL on their own; they create a client to execute statements when a terminal operation such as `.update()`, `.single()`, or `.list()` is called.

### 2.1. The Facade Does Not Replace Templates

`JdbcClient` is well suited for **standard queries and updates**. In Spring **6.1**, complex operations such as batch updates or stored procedures still typically use `JdbcTemplate`, `NamedParameterJdbcTemplate`, `SimpleJdbcInsert`, or `SimpleJdbcCall`. Do not use the `batch()` method if strict Spring 6.1 compatibility is your goal: the 6.1 interface does not expose that fluent batch API; features from newer versions should not be assumed backward into 6.1.

The facade also does not turn SQL into an object-oriented query language, does not auto-create tables, and does not automatically manage an entity/persistence context like JPA.

### 2.2. Compatibility with Spring Framework 6.1

`JdbcClient` was introduced with `@since 6.1`; you cannot assume a Spring Framework 6.0 project automatically has the same class/API. You must check the **actual `spring-jdbc` version on the runtime classpath**, not just the Spring Boot version mentioned in documentation. If using Spring Boot, use a Boot line that manages a Spring Framework version containing `JdbcClient` (for example, Boot 3.2 integrates Spring Framework 6.1); when declaring dependencies manually, ensure all Spring modules use consistent versions.

## 3. Fluent API: Understanding Each Step in a Call Chain

A SELECT query with a named parameter:

~~~java
String title = client
        .sql("SELECT title FROM book WHERE id = :id")
        .param("id", 10L)
        .query(String.class)
        .single();
~~~

This is an **illustrative snippet** inside a method that has `client`, a `book` table, and a record with ID 10. It is not a standalone class.

The parts:

1. `sql(String)` starts a `JdbcClient.StatementSpec` holding the SQL statement.
2. `param("id", 10L)` binds a value by the name `:id`. You can chain `.param(name, value)` multiple times.
3. `query(String.class)` requests a mapper that converts a **single column** value into `String`.
4. `single()` executes the query and requires **exactly one result**. If there are no rows or more than one row, the result violates the required cardinality and Spring throws the corresponding exception.

For UPDATE:

~~~java
int affected = client
        .sql("UPDATE book SET title = :title WHERE id = :id")
        .param("title", "Spring JDBC")
        .param("id", 10L)
        .update();
~~~

`update()` is a terminal operation for running INSERT/UPDATE/DELETE, returning the **number of affected rows** as an `int`. An UPDATE statement that matches no rows normally returns 0; that is not automatically a "not found" exception. The service layer should check `affected` if the business logic requires exactly one row to be modified.

### 3.1. `sql()` Itself Does Not Execute

Code that only builds a `StatementSpec`:

~~~java
JdbcClient.StatementSpec spec =
        client.sql("SELECT title FROM book WHERE id = :id")
              .param("id", 10L);
~~~

has not yet requested any result. The query is executed when an appropriate terminal method such as `query(...).single()`, `query(...).list()`, or `update()` is called. Avoid storing and sharing a `StatementSpec` with mutable parameters across multiple threads; build a fresh chain on each call, while a `JdbcClient` configured on a `DataSource` can be used as a repository dependency.

### 3.2. Code Readability

The traditional JDBC approach with named parameters:

~~~java
Integer count = namedParameterJdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM book WHERE pages >= :minPages",
        Map.of("minPages", 200),
        Integer.class);
~~~

The fluent approach:

~~~java
Integer count = client
        .sql("SELECT COUNT(*) FROM book WHERE pages >= :minPages")
        .param("minPages", 200)
        .query(Integer.class)
        .single();
~~~

Both can be correct. `JdbcClient` makes specifying parameters, the mapper, and cardinality **appear as distinct steps**, rather than automatically being faster or changing SQL semantics.

## 4. Positional and Named Parameters in the Same Facade

`JdbcClient` supports **two styles** per SQL statement.

### 4.1. Positional `?`

~~~java
List<String> titles = client
        .sql("SELECT title FROM book WHERE pages >= ? AND pages <= ? ORDER BY id")
        .param(150)
        .param(350)
        .query(String.class)
        .list();
~~~

The two `param(value)` calls are registered in the order the two `?` placeholders appear, corresponding to the first and second placeholders.

When you already have a list of values, there are `params(Object... values)` and `params(List<?> values)`:

~~~java
List<String> titles = client
        .sql("SELECT title FROM book WHERE pages BETWEEN ? AND ? ORDER BY id")
        .params(150, 350)
        .query(String.class)
        .list();
~~~

These two examples share the same SQL meaning for a closed range when the column is non-null. `params` is intended for **controlled values**; do not concatenate SQL strings from user input.

### 4.2. Explicit JDBC Indexing

Spring 6.1 includes an overload:

~~~java
client.sql("SELECT title FROM book WHERE id = ?")
      .param(1, 10L)
      .query(String.class)
      .single();
~~~

`param(int jdbcIndex, Object value)` requires a **1-based** JDBC index, not a 0-based Java array index. It can be useful when code builds bindings programmatically, though with only a few parameters `.param(value)` is usually easier to read.

### 4.3. Named `:name`

~~~java
List<String> titles = client
        .sql("SELECT title FROM book " +
             "WHERE pages >= :minPages AND pages <= :maxPages ORDER BY id")
        .param("minPages", 150)
        .param("maxPages", 350)
        .query(String.class)
        .list();
~~~

The names `minPages`/`maxPages` must match the placeholders in the SQL. A name appearing multiple times in the SQL can take the same value according to Spring's named parameter handling.

Named parameters are easier to maintain when there are many conditions because readers do not have to count `?` placeholders. For 1–2 simple parameters, positional parameters are also a great fit.

### 4.4. `params(Map)` and `paramSource(...)`

For data already organized in a map:

~~~java
Map<String, Object> parameters = Map.of(
        "minPages", 150,
        "maxPages", 350);

List<String> titles = client
        .sql("SELECT title FROM book " +
             "WHERE pages BETWEEN :minPages AND :maxPages ORDER BY id")
        .params(parameters)
        .query(String.class)
        .list();
~~~

If parameters come from a record/bean with matching property names, Spring 6.1 supports `paramSource(Object)`; and `paramSource(SqlParameterSource)` for specialized sources:

~~~java
record Filter(int minPages, int maxPages) {}

Filter filter = new Filter(150, 350);

List<String> titles = client
        .sql("SELECT title FROM book " +
             "WHERE pages BETWEEN :minPages AND :maxPages ORDER BY id")
        .paramSource(filter)
        .query(String.class)
        .list();
~~~

This is a snippet inside a method; the `Filter` definition can be placed anywhere valid in Java 17. For properties that may be null or require an explicit SQL type, use `MapSqlParameterSource` to carry type metadata.

**Do not mix positional and named binding in the same SQL statement** expecting Spring to automatically combine a `?` with `:id`. Choose one style per statement; internally Spring picks the corresponding delegate path, and mixing them can throw `InvalidDataAccessApiUsageException`.

## 5. Retrieving Results: `query(mappedClass)`

A convenient API in JdbcClient 6.1 is:

~~~java
List<Book> books = client
        .sql("SELECT id, title, pages FROM book ORDER BY id")
        .query(Book.class)
        .list();
~~~

If `Book` is a Java record whose components `id`, `title`, and `pages` match the column labels and have compatible conversion types, Spring can map each row to the record.

~~~java
public record Book(long id, String title, int pages) {}
~~~

For `query(Class<T>)`, Spring 6.1 selects the appropriate mapper between a single-column scalar type and a multi-property class (JavaBean, record, or holder). **Do not confuse this with** `JdbcTemplate.queryForList(sql, Book.class)`: that classic overload is for single-column scalars and does not automatically construct a multi-column `Book`.

### 5.1. Scalar Value

~~~java
long count = client
        .sql("SELECT COUNT(*) FROM book")
        .query(Long.class)
        .single();
~~~

`COUNT(*)` is one column, one row. `Long.class` expresses the desired result value type; if the driver/SQL type differs, choose a compatible type. Use explicit SQL aliases/mappers when mapping multi-field data.

### 5.2. Multi-Column Record/DTO

~~~java
record BookSummary(long id, String title) {}

List<BookSummary> books = client
        .sql("SELECT id, title FROM book ORDER BY id")
        .query(BookSummary.class)
        .list();
~~~

Column names and types must match how the mapper looks up fields, properties, or constructor components. `query(BookSummary.class)` does not automatically enforce business invariants and does not automatically resolve multi-table JOINs into an object graph like an ORM.

For cases with complex conversions, duplicate column names after a JOIN, driver-specific enum/date-time types, or multiple tables merged into a single object, prefer a hand-written `RowMapper<T>` for explicitness.

## 6. Retrieving Results: `query(RowMapper<T>)`

When you want complete control over how `ResultSet` is read:

~~~java
RowMapper<Book> mapper = (rs, rowNum) -> new Book(
        rs.getLong("id"),
        rs.getString("title"),
        rs.getInt("pages")
);

List<Book> books = client
        .sql("SELECT id, title, pages FROM book ORDER BY id")
        .query(mapper)
        .list();
~~~

*This is a Java example inside a method that has `client` and the `Book` class/record.*

`RowMapper` is suitable when:

- The SQL uses special aliases or column names that do not match component names.
- You need intentional conversion of SQL NULL, enums, date/time values, JSON, or nested structures.
- You want to keep the domain contract explicit without relying on implicit property matching.
- The same mapping rule is reused across multiple queries.

`JdbcClient` does not force a choice between "automatic mapping" and "custom mapper". Both are exposed via the `query(Class<T>)` and `query(RowMapper<T>)` overloads.

### 6.1. `RowCallbackHandler` and `ResultSetExtractor`

Spring 6.1 also provides:

~~~java
client.sql("SELECT id, title FROM book ORDER BY id")
      .query(rs -> {
          // RowCallbackHandler: process each row in the ResultSet.
      });
~~~

This is only an **illustrative** snippet of a per-row handler overload; to avoid lambda overload ambiguity, real code should declare the callback with type `RowCallbackHandler` or use a concrete mapper.

For logic that needs to aggregate the entire `ResultSet` in a way that is not one-row-equals-one-object, use the `query(ResultSetExtractor<T>)` overload. These options let you solve complex data reading without leaving the facade, though `JdbcTemplate` remains useful when lower-level JDBC control is needed.

## 7. Choosing the Result Shape: `list()`, `single()`, `optional()`

Three common terminal methods of `MappedQuerySpec<T>`:

| API | Result | No rows | Multiple rows |
| --- | --- | --- | --- |
| `.query(Book.class).list()` | `List<Book>` | Empty list | List with multiple elements |
| `.query(Book.class).single()` | `Book` | `EmptyResultDataAccessException` | `IncorrectResultSizeDataAccessException` |
| `.query(Book.class).optional()` | `Optional<Book>` | `Optional.empty()` | `IncorrectResultSizeDataAccessException` |
| `.query(Book.class).set()` | `Set<Book>` | Empty set | Unique elements by `equals/hashCode`, preserving order from mapper/list |
| `.query(Book.class).stream()` | `Stream<Book>` (must be closed) | Empty stream | Stream of results, not pre-loaded like `list()` |

Example where an ID might not exist:

~~~java
Optional<Book> book = client
        .sql("SELECT id, title, pages FROM book WHERE id = :id")
        .param("id", requestedId)
        .query(Book.class)
        .optional();
~~~

Here `Optional.empty()` is a valid result for "not found". If the SQL returns multiple rows, `optional()` **does not automatically pick the first row**. That still violates the expectation of at most one row.

Conversely, if the ID is required to exist and missing data is a business error, `single()` makes that requirement explicit, though the service should translate `DataAccessException` into an appropriate business error at the application boundary if needed.

### 7.1. Streams Must Be Closed

~~~java
try (Stream<Book> stream = client
        .sql("SELECT id, title, pages FROM book ORDER BY id")
        .query(Book.class)
        .stream()) {
    stream.forEach(System.out::println);
}
~~~

*This snippet requires importing `java.util.stream.Stream`.* The `stream()` result can hold onto JDBC resources until the stream is closed. **Do not** return a live stream outside a finished transaction/context, and do not store it in a field to process on another thread. Use `list()` when the row count is small and you want a list detached from JDBC resources.

### 7.2. `set()` Is Not SQL DISTINCT

`set()` collects the results into a `Set` preserving encounter order and deduplicating by the Java type's `equals/hashCode`. It does not replace the intent and cost savings of `SELECT DISTINCT` in the database. For large results, perform filtering/grouping in the appropriate place.

## 8. Querying Without a Mapped Class: `query()`

Not every result needs a `Book`. Spring Framework 6.1 provides `ResultQuerySpec` from `query()` (with no arguments):

~~~java
List<Map<String, Object>> rows = client
        .sql("SELECT id, title, pages FROM book ORDER BY id")
        .query()
        .listOfRows();

Map<String, Object> row = client
        .sql("SELECT id, title FROM book WHERE id = ?")
        .param(1L)
        .query()
        .singleRow();
~~~

`listOfRows()` is useful for reporting tables with flexible projections; each row is a map from column label to value. `singleRow()` requires one row. A map lacks domain type-safety: code must handle keys, aliases, SQL NULL, `Object` types, and possible duplicate column labels when joining.

Other methods of `ResultQuerySpec` in Spring **6.1**:

~~~java
List<Object> ids = client
        .sql("SELECT id FROM book ORDER BY id")
        .query()
        .singleColumn();

Object id = client
        .sql("SELECT id FROM book WHERE id = ?")
        .param(1L)
        .query()
        .singleValue();

SqlRowSet rowSet = client
        .sql("SELECT id, title FROM book ORDER BY id")
        .query()
        .rowSet();
~~~

*These are illustrative snippets; `SqlRowSet` requires importing `org.springframework.jdbc.support.rowset.SqlRowSet`.*

`singleColumn()` returns a list of values of **one column** with elements of type `Object`, while `singleValue()` requires a single-cell result. For scalar data whose type you know, forms like `query(Long.class).single()` or `query(String.class).list()` are usually easier to maintain.

**Important version note:** The `ResultQuerySpec.optionalValue()` API appeared in versions after 6.1 and should not be used when targeting Spring 6.1. `query(Book.class).optional()` is the appropriate method in 6.1 for expressing optionality with a mapper.

### 8.1. SQL Does Not Check Cardinality for You

If you only want a single record, ensure the `WHERE` clause filters on an appropriate key/constraint. If SQL returns two rows and you call `singleRow()` or `single()`, the framework will not silently pick the first row. You should fix the query criteria rather than automatically adding `LIMIT 1` to mask a uniqueness issue.

### 8.2. Aliases and Mapping

~~~sql
SELECT b.id AS book_id, b.title AS book_title
FROM book b
~~~

If a map result needs the two keys `book_id` and `book_title`, use explicit aliases. If using the record `Book(long id, String title, ...)`, the projection must provide names/types matching the mapper. After a JOIN, do not select two columns both named `id` and expect a map to represent both unambiguously.

## 9. Writing Data: `update()` and Generated Keys

Use fluent update for `INSERT`, `UPDATE`, or `DELETE`:

~~~java
int inserted = client
        .sql("INSERT INTO book(id, title, pages) VALUES (?, ?, ?)")
        .params(1L, "Clean Java", 320)
        .update();

int changed = client
        .sql("UPDATE book SET pages = :pages WHERE id = :id")
        .param("pages", 350)
        .param("id", 1L)
        .update();

int deleted = client
        .sql("DELETE FROM book WHERE id = ?")
        .param(1L)
        .update();
~~~

On a table where `id` is the primary key, an INSERT with a duplicate ID will throw a database exception translated by Spring into the appropriate `DataAccessException`. The `int` return value represents the number of affected rows; it is not a generated ID.

### 9.1. Generated Keys in Spring 6.1

`JdbcClient.StatementSpec` has overloads `update(KeyHolder)` and `update(KeyHolder, String... keyColumnNames)`. If the schema has an identity/generated column and the driver supports retrieving generated keys:

~~~java
KeyHolder holder = new GeneratedKeyHolder();

int inserted = client
        .sql("INSERT INTO book(title, pages) VALUES (:title, :pages)")
        .param("title", "New Book")
        .param("pages", 240)
        .update(holder, "id");

Number key = holder.getKey();
~~~

**This is an illustrative snippet only when `book.id` is declared auto-generated**, unlike the demo schema in section 11 where IDs are supplied explicitly. `KeyHolder.getKey()` may not provide a key if the driver/DB does not support it or metadata differs from expectations; do not assume every database returns the same `Number` subtype. Test this with your actual SQL DDL and driver.

### 9.2. Multiple Business Operations Require a Transaction

`update()` executes a single statement. It does not automatically wrap other statements into an atomic transaction for an entire use case. `@Transactional` or `TransactionTemplate` with a compatible transaction manager still controls begin/commit/rollback.

## 10. Null Parameters, SQL Types, and SQL Safety

`JdbcClient.StatementSpec` in Spring 6.1 supports overloads with a SQL type:

~~~java
client.sql("UPDATE book SET note = ? WHERE id = ?")
      .param(1, null, Types.VARCHAR)
      .param(2, 1L, Types.BIGINT)
      .update();
~~~

And with named parameters:

~~~java
client.sql("UPDATE book SET note = :note WHERE id = :id")
      .param("note", null, Types.VARCHAR)
      .param("id", 1L)
      .update();
~~~

These two snippets are only **illustrative** for a table with a `note` column, not for the `book(id, title, pages)` demo schema in section 11. You can use `paramSource(MapSqlParameterSource)` when passing multiple parameters with SQL types:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("note", null, Types.VARCHAR)
        .addValue("id", 1L, Types.BIGINT);

client.sql("UPDATE book SET note = :note WHERE id = :id")
      .paramSource(params)
      .update();
~~~

*In this case `MapSqlParameterSource` carries type metadata, not just a value map.* `Map.of("note", null)` would immediately throw a `NullPointerException` in Java because `Map.of` does not allow null values.

Why is a SQL type needed for null? Because Java `null` carries no runtime class; some JDBC drivers/SQL expressions lack enough information to infer the parameter's SQL type. Specifying `Types.VARCHAR`, `Types.DATE`, etc. matching the schema makes binding explicit.

### 10.1. Do Not Concatenate User Values into SQL

Correct:

~~~java
client.sql("SELECT id, title, pages FROM book WHERE title = :title")
      .param("title", suppliedTitle)
      .query(Book.class)
      .list();
~~~

Wrong:

~~~java
String unsafeSql =
        "SELECT id, title, pages FROM book WHERE title = '" +
        suppliedTitle + "'";
~~~

Parameter binding is meant to substitute **values**, not table/column names or `ORDER BY` directions. If the user is allowed to choose a sort column, validate against a whitelist of allowed identifiers instead of concatenating arbitrary strings.

## 11. Complete Runnable Demo: Java 17, Spring JDBC 6.1.14, and H2

The program uses **Maven 3.9+**, **JDK 17+**, `spring-jdbc:6.1.14`, and `h2:2.2.224`. This is a Java console application **without Spring Boot**. It creates a `DataSource`, `JdbcTemplate`, and `JdbcClient`, then demonstrates positional/named parameters, Java record mapping, `list()`, `single()`, `optional()`, `update()`, and affected row counts.

### 11.1. Project Structure

~~~text
jdbc-client-demo/
├── pom.xml
└── src/main/java/demo/
    └── JdbcClientDemo.java
~~~

### 11.2. File `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jdbc-client-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.3. File `src/main/java/demo/JdbcClientDemo.java`

~~~java
package demo;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class JdbcClientDemo {

    public record Book(long id, String title, int pages) {}

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:jdbc_client_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate template = new JdbcTemplate(ds);
        JdbcClient client = JdbcClient.create(template);

        template.execute("CREATE TABLE book (" +
                "id BIGINT PRIMARY KEY, " +
                "title VARCHAR(100) NOT NULL, " +
                "pages INTEGER NOT NULL)");

        int a = client
                .sql("INSERT INTO book(id, title, pages) VALUES (?, ?, ?)")
                .params(1L, "Clean Java", 320)
                .update();

        int b = client
                .sql("INSERT INTO book(id, title, pages) " +
                     "VALUES (:id, :title, :pages)")
                .param("id", 2L)
                .param("title", "Spring JDBC")
                .param("pages", 200)
                .update();

        int c = client
                .sql("INSERT INTO book(id, title, pages) " +
                     "VALUES (:id, :title, :pages)")
                .param("id", 3L)
                .param("title", "Data Access")
                .param("pages", 260)
                .update();

        System.out.println("Inserted rows: " + (a + b + c));

        List<Book> initial = client
                .sql("SELECT id, title, pages FROM book ORDER BY id")
                .query(Book.class)
                .list();
        System.out.println("Books: " + initial.size());
        System.out.println("First title: " + initial.get(0).title());

        long count = client.sql("SELECT COUNT(*) FROM book")
                .query(Long.class)
                .single();
        System.out.println("Count before update: " + count);

        Optional<Book> missing = client
                .sql("SELECT id, title, pages FROM book WHERE id = :id")
                .param("id", 999L)
                .query(Book.class)
                .optional();
        System.out.println("Missing present: " + missing.isPresent());

        int changed = client
                .sql("UPDATE book SET pages = :pages WHERE id = :id")
                .param("pages", 350)
                .param("id", 1L)
                .update();
        System.out.println("Updated rows: " + changed);

        int pages = client
                .sql("SELECT pages FROM book WHERE id = ?")
                .param(1L)
                .query(Integer.class)
                .single();
        System.out.println("Pages for id=1: " + pages);

        int removed = client
                .sql("DELETE FROM book WHERE id = ?")
                .param(3L)
                .update();
        System.out.println("Deleted rows: " + removed);

        List<Book> remaining = client
                .sql("SELECT id, title, pages FROM book ORDER BY id")
                .query(Book.class)
                .list();
        System.out.println("Remaining ids: " +
                remaining.stream().map(Book::id).toList());

        long remainingCount = client.sql("SELECT COUNT(*) FROM book")
                .query(Long.class)
                .single();
        System.out.println("Count after delete: " + remainingCount);
    }
}
~~~

Run inside the `jdbc-client-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JdbcClientDemo
~~~

**Lines printed by the program itself** (excluding any Maven logs):

~~~text
Inserted rows: 3
Books: 3
First title: Clean Java
Count before update: 3
Missing present: false
Updated rows: 1
Pages for id=1: 350
Deleted rows: 1
Remaining ids: [1, 2]
Count after delete: 2
~~~

### 11.4. Why This Output Is Correct

1. The program creates the `book` table with `id BIGINT`, `title VARCHAR`, and `pages INTEGER`. `DriverManagerDataSource` opens new connections; `DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive across connection usages within the same JVM.
2. Each of the three `INSERT` statements writes one row. The first uses positional `params(...)`; the next two use `param(name, value)`. Because ID is a unique primary key, the three rows are distinguished by ID.
3. `SELECT ... ORDER BY id` returns three rows in ascending ID order. `query(Book.class)` maps the `id/title/pages` columns to the corresponding record components. `list()` returns a list, so the first element is `Clean Java`.
4. `SELECT COUNT(*)` returns a single number, received as 3 via `query(Long.class).single()`.
5. Querying ID 999 matches no rows; `optional()` returns `Optional.empty()` rather than throwing a missing-row error.
6. The UPDATE for ID 1 changes pages from 320 to 350; `update()` returns 1 affected row. The corresponding scalar SELECT prints 350.
7. The DELETE for ID 3 affects exactly one row; `update()` returns 1. The final SELECT leaves ID 1 and ID 2, producing `[1, 2]` with `ORDER BY id`.
8. `COUNT(*)` after deletion is 2. There is no multi-statement transaction in this example because the goal is to verify the fluent JDBC API; if business logic requires atomicity across multiple changes, configure a transaction separately.

### 11.5. Experiments to Try on the Demo

**Experiment A — empty result:** replace `.optional()` with `.single()` for ID 999. The expected result is `EmptyResultDataAccessException` instead of `Optional.empty()`.

**Experiment B — duplicate result:** use `.single()` with `SELECT id, title, pages FROM book` when two rows exist. The expected result is `IncorrectResultSizeDataAccessException`; you need a WHERE clause on a unique key or `list()` if multiple rows are valid.

**Experiment C — checking named parameters:** rename `:pages` in the SQL without changing `.param("pages", 350)`. The binding error shows that SQL placeholder names and parameter names must stay in sync.

**Experiment D — SQL mapping:** change the alias of `pages` to `page_count` while still relying on automatic mapping to `Book.pages`. Check the result and use the alias `AS pages` or an appropriate `RowMapper` instead of trusting the mapper to guess every alias.

**Experiment E — update not found:** change `WHERE id = :id` to ID 999. `update()` normally returns 0; the service must explicitly treat that as a business error when needed.

**Experiment F — conversion:** change the SQL to only `SELECT title FROM book` and use `query(Book.class)`. Because the query does not contain all components of the record, domain mapping cannot be considered valid; use `query(String.class)` for a single-column scalar.

## 12. Using JdbcClient in a Spring Application

In an application using dependency injection, create a bean from an existing `DataSource`:

~~~java
@Configuration
public class JdbcConfig {
    @Bean
    JdbcClient jdbcClient(DataSource dataSource) {
        return JdbcClient.create(dataSource);
    }
}
~~~

This is a **configuration snippet**, not a standalone program. It requires importing `org.springframework.context.annotation.Configuration`, `Bean`, `javax.sql.DataSource`, and `JdbcClient`. If the Boot ecosystem in use already provides a compatible `JdbcClient` bean, do not inadvertently register a duplicate; check the project's actual configuration.

A repository using constructor injection:

~~~java
@Repository
public class BookRepository {

    private final JdbcClient client;

    public BookRepository(JdbcClient client) {
        this.client = client;
    }

    public Optional<Book> findById(long id) {
        return client.sql(
                "SELECT id, title, pages FROM book WHERE id = :id")
                .param("id", id)
                .query(Book.class)
                .optional();
    }

    public int updatePages(long id, int pages) {
        return client.sql(
                "UPDATE book SET pages = :pages WHERE id = :id")
                .param("pages", pages)
                .param("id", id)
                .update();
    }
}
~~~

This is **architectural illustration code**; `Book` needs a valid record/class in the application. `@Repository` helps Spring discover the class when component scanning is configured and indicates its data-layer role. `JdbcClient` does not turn the repository into a bean by itself; it is a dependency that Spring injects through the constructor.

### 12.1. Transactions Are Still Managed at the Service Layer

~~~java
@Service
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public void revise(long id, int pages) {
        int affected = books.updatePages(id, pages);
        if (affected != 1) {
            throw new IllegalStateException("Book not found or not unique");
        }
        // Other JDBC changes in the same transaction when using the right DataSource.
    }
}
~~~

The code above only illustrates class organization and requires an appropriate Spring transaction manager. `@Transactional` must actually be enabled, typically via a proxy/interceptor; self-invocation can bypass the proxy. JDBC operations on the same `DataSource` with a compatible manager can participate in the transaction. `JdbcClient` does not automatically call commit/rollback for a use case spanning multiple statements.

Do not add a transaction just because you are using the fluent syntax: a simple list query may not need a long business transaction; consistency requirements should determine the transaction boundary.

## 13. Reusing JdbcTemplate and DataSource Configuration

If the project already has a `JdbcTemplate` configured with `queryTimeout`, `fetchSize`, a translator, or a dedicated DataSource, consider:

~~~java
JdbcClient client = JdbcClient.create(existingJdbcTemplate);
~~~

It uses the existing `JdbcOperations` delegate, preserving configuration instead of creating an entirely separate template. Similarly, there is a factory for `NamedParameterJdbcOperations`.

**Do not automatically assume** that two `JdbcClient` instances created separately with two different `DataSource`s will share the same transaction. For local JDBC transactions, calls must use the exact managed datasource/manager. Especially in multi-database or multi-tenant systems, verify the actual tenant, DataSource routing, and transaction manager before use.

### API Comparison

| Task | `JdbcTemplate` / `NamedParameterJdbcTemplate` | `JdbcClient` 6.1 |
| --- | --- | --- |
| Single-row scalar query | `queryForObject(sql, args, Long.class)` and corresponding overloads | `sql(...).param(...).query(Long.class).single()` |
| Multi-row mapped query | `query(sql, rowMapper, args)` | `sql(...).param(...).query(rowMapper).list()` |
| Named parameter query | `namedTemplate.query(sql, params, rowMapper)` | `sql(...).param("name", value).query(rowMapper).list()` |
| Query list of row maps | `queryForList(sql, args)` | `sql(...).query().listOfRows()` |
| Single update | `update(sql, args...)` | `sql(...).params(...).update()` |
| Generated key | `KeyHolder` APIs in templates | `sql(...).param(...).update(keyHolder)` |
| Batch update | `batchUpdate(...)` overloads | In **6.1**, use templates |
| Stored procedure | `SimpleJdbcCall`, low-level JDBC | Use dedicated/low-level APIs |

Not every overload has identical syntax, but these correspondences help orient your mental model. Switching from `JdbcTemplate` to `JdbcClient` should be motivated by **better readability**, without assuming higher speed or different SQL behavior.

## 14. Exception Handling, Not Found, and Incorrect Result Size

Common situations:

| Situation | Typical behavior | Approach |
| --- | --- | --- |
| `list()` query returns 0 rows | Empty list | Appropriate for search/listing |
| `optional()` returns 0 rows | `Optional.empty()` | Appropriate for lookups that may miss |
| `single()` returns 0 rows | `EmptyResultDataAccessException` | Check cardinality/use case |
| `single()` returns >1 row | `IncorrectResultSizeDataAccessException` | Check WHERE clause and unique constraints |
| `optional()` returns >1 row | `IncorrectResultSizeDataAccessException` | Do not automatically take the first row |
| `update()` affects 0 rows | Integer 0 | Service checks if exactly one row was expected |
| Invalid SQL syntax or broken connection | Appropriate `DataAccessException` | Inspect root cause/SQL/driver |
| INSERT violates unique key | `DataIntegrityViolationException` or specific subclass, depending on translator | Do not "catch and ignore" if business logic requires rollback |

`JdbcClient` uses Spring JDBC infrastructure underneath, so SQL/driver errors can be translated into `DataAccessException`. An exception being translated does **not** mean the transaction automatically rolls back in all cases: it still depends on transaction boundaries, rollback policies, and whether the exception is caught.

### Do Not Catch Every `DataAccessException` to Return an Empty List

A SQL syntax error, offline database, or timeout is different from "no record found". With `optional()`, the 0-row case is represented by `Optional.empty()` without turning system errors into normal results.

## 15. Performance, Pagination, and Resource Safety

### 15.1. The Fluent API Does Not Auto-Paginate

~~~java
List<Book> books = client
        .sql("SELECT id, title, pages FROM book ORDER BY id")
        .query(Book.class)
        .list();
~~~

`list()` materializes the elements in memory. If a table has millions of rows, do not fetch everything by default. Use `WHERE`, `ORDER BY`, and pagination suited to your dialect; use projections to select only the needed columns.

### 15.2. Query Streams and Connection Lifecycle

`stream()` supports lazy processing, but the stream must be closed to release JDBC resources. Do not treat it as a guarantee that every driver fetches one row at a time; fetch size, transactions, cursors, and drivers affect memory and network behavior.

### 15.3. Do Not Share State Across Requests via StatementSpec

A singleton repository can hold a `final JdbcClient` field. However, `StatementSpec` holds the SQL/parameter state for **one statement**. Recreate the spec on each method invocation. Do not store a mutable spec in a singleton and mutate parameters across threads.

### 15.4. Parameter Binding and SQL Injection

`.param(value)` / `.param(name, value)` binds **values**, avoiding concatenating user input into SQL strings. However, table/column names, ORDER BY fields, and sort directions cannot be turned into arbitrary bound values. Whitelist identifiers and use controlled SQL branches.

### 15.5. Do Not Treat JdbcClient as an ORM

If you need dirty checking, entity relationship management, lazy loading, or JPQL, you need an ORM/JPA technology. `JdbcClient` preserves the strengths of explicit SQL, flexible mapping, and direct query control; it does not auto-generate `@Entity` classes, sessions, or migrations.

## 16. Common Misconceptions When Learning JdbcClient 6.1

**Misconception 1 — "JdbcClient was introduced to completely replace JdbcTemplate".** No. `JdbcClient` is a facade delegating common queries and updates; templates still have their role for batching and advanced SQL.

**Misconception 2 — "JdbcClient supports all the latest APIs even when using 6.1".** No. Check the 6.1 Javadoc. For instance, fluent batch APIs added later must not be assumed as core 6.1 APIs.

**Misconception 3 — "Calling `sql()` already runs the query".** No. You must call an appropriate terminal method.

**Misconception 4 — "You can freely mix `?` and `:name` in the same statement".** You should not; choose one consistent binding style per SQL statement.

**Misconception 5 — "`optional()` picks the first row even when multiple rows are returned".** No. It accepts at most one result.

**Misconception 6 — "`query(Book.class)` automatically maps every kind of JOIN or nested object".** No. For complex structures, use `RowMapper` and intentional SQL aliases.

**Misconception 7 — "`list()` does not use memory because the API is fluent".** No. The list is pre-loaded; choose pagination or resource-managed streaming if the dataset is large.

**Misconception 8 — "`update()` returns the new ID".** No. It returns the number of affected rows; generated keys require `KeyHolder` and driver support.

**Misconception 9 — "Having JdbcClient automatically gives you transactions".** No. The transaction manager and service boundaries remain separate configuration.

**Misconception 10 — "`param("name", null)` is always enough for every driver".** No. There are cases that require the overload passing `sqlType` or a `SqlParameterSource` carrying metadata.

**Misconception 11 — "You can use JdbcClient for JPA queries and let it persist entities automatically".** No. This is Spring JDBC, not an ORM.

## 17. Practice Exercises

### Exercise 1 — Convert Positional to Named

Given the SQL:

~~~sql
SELECT id, title, pages
FROM book
WHERE pages >= ? AND pages <= ?
ORDER BY id
~~~

Write two `JdbcClient` versions: one using `params(min, max)`, and one using `:min`/`:max` with `param(name, value)`. Compare the row count and ordering returned.

**Suggested solution:**

~~~java
List<Book> a = client
        .sql("SELECT id, title, pages FROM book " +
             "WHERE pages >= ? AND pages <= ? ORDER BY id")
        .params(150, 350)
        .query(Book.class)
        .list();

List<Book> b = client
        .sql("SELECT id, title, pages FROM book " +
             "WHERE pages >= :min AND pages <= :max ORDER BY id")
        .param("min", 150)
        .param("max", 350)
        .query(Book.class)
        .list();
~~~

### Exercise 2 — Distinguish `optional` and `single`

For a non-existent ID 999, test both approaches:

~~~java
Optional<Book> optional = client
        .sql("SELECT id, title, pages FROM book WHERE id = ?")
        .param(999L)
        .query(Book.class)
        .optional();
~~~

The result `optional.isPresent()` is `false`. If you switch the terminal method to `single()` for the same SQL, a missing-row error will occur. Choose the API based on the business meaning of "not found".

### Exercise 3 — Checking UPDATE Row Count

Given an ID not present in the table:

~~~java
int affected = client
        .sql("UPDATE book SET pages = :pages WHERE id = :id")
        .param("pages", 400)
        .param("id", 999L)
        .update();
~~~

Verify `affected == 0`. In the service layer, decide whether this is a "not found" error, a valid no-op result, or a concurrency conflict. Do not rely on `JdbcClient` to pick business rules for you.

### Exercise 4 — Null with a SQL Type

Suppose the table has an additional column `note VARCHAR(120) NULL`. Write NULL using `.param("note", null, Types.VARCHAR)`. Compare with `MapSqlParameterSource.addValue("note", null, Types.VARCHAR)` and `.paramSource(...)`. Test against the target driver rather than assuming null values always bind with the right type.

### Exercise 5 — Safe Streaming

Replace `.list()` with `.stream()` to iterate over a large dataset. Use `try-with-resources` to close the stream. If pagination/throttling or transactions are involved, verify driver and connection lifecycle behavior before concluding that streaming saves memory in every scenario.

## 18. Quick Review Questions

**1. Which Spring Framework version introduced `JdbcClient`?**  
Since **6.1**; it belongs to `spring-jdbc` and the `org.springframework.jdbc.core.simple` package.

**2. Does `JdbcClient` execute SQL directly instead of a driver, or does it delegate?**  
It delegates to Spring's JDBC templates; it still uses a `DataSource` and an actual JDBC driver.

**3. How do you return multiple record objects?**  
`client.sql(sql).query(MyRecord.class).list()`, with matching columns and types.

**4. When 0 rows is a normal case, what should you use?**  
`optional()` for a lookup returning at most one row; `list()` for a list that may be empty.

**5. Does `single()` pick the first row when SQL returns multiple rows?**  
No. It requires exactly one result and may throw `IncorrectResultSizeDataAccessException`.

**6. How do you bind by name in SQL?**  
Use `:name` and `.param("name", value)`, `params(Map)`, or `paramSource(...)`.

**7. What does `update()` return?**  
The number of affected rows, not an auto-generated ID.

**8. When batch updates are needed in Spring 6.1, what should you use?**  
The appropriate APIs on `JdbcTemplate` or `NamedParameterJdbcTemplate`; do not assume a newer fluent batch method exists in 6.1.

**9. Does `stream()` need to be closed?**  
Yes. Close the stream in `try-with-resources` to release JDBC resources.

**10. What do you need if a single transaction must wrap multiple `update()` calls?**  
Define a transaction boundary with a compatible transaction manager, typically using `@Transactional` in the service layer or `TransactionTemplate`.

## 19. Official Documentation

- [Spring Framework 6.1 – JDBC Core](https://docs.spring.io/spring-framework/reference/6.1/data-access/jdbc/core.html): `JdbcClient` unifying positional/named queries and updates.
- [JdbcClient Javadoc – Spring Framework 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html): factory methods and facade contract.
- [JdbcClient.StatementSpec Javadoc – 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.StatementSpec.html): `sql`, `param`, `params`, `paramSource`, `query`, `update`.
- [JdbcClient.MappedQuerySpec Javadoc – 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html): `list`, `single`, `optional`, `set`, `stream`.
- [JdbcClient.ResultQuerySpec Javadoc – 6.1.14](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.ResultQuerySpec.html): `rowSet`, `listOfRows`, `singleRow`, `singleColumn`, `singleValue`.

**Conclusion:** `JdbcClient` from Spring Framework 6.1 is a readable fluent interface for common JDBC SQL commands: `sql → param → query/mapping → list/single/optional` or `sql → param → update`. It preserves the existing JDBC/Spring JDBC infrastructure, lets you choose positional/named parameters and flexible mapping, and does not replace transaction managers, advanced JDBC templates, or ORMs.
