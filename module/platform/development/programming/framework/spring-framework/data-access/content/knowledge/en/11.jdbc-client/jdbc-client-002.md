# Creating a Client from a Suitable DataSource or Template

> **Key takeaway:** Starting in **Spring Framework 6.1**, `org.springframework.jdbc.core.simple.JdbcClient` provides a unified fluent API for JDBC queries and updates, supporting both positional `?` parameters and named `:name` parameters. There are three common factory methods: **`JdbcClient.create(DataSource)`**, **`JdbcClient.create(JdbcOperations)`**, and **`JdbcClient.create(NamedParameterJdbcOperations)`**. Choose according to the resources already configured: if you only have a `DataSource`, create from the connection source; if you already have a customized `JdbcTemplate` or `NamedParameterJdbcTemplate`, **prefer reusing the corresponding template** to preserve its settings.

This guide focuses on **how to create, choose, declare beans for, and use `JdbcClient` properly within the Spring Data Access architecture**. A `JdbcClient` is not a physical connection, does not create additional databases on its own, and does not replace every advanced feature of `JdbcTemplate`.

## 1. Placing JdbcClient at the Right Abstraction Layer

Related types:

```java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
```

- **`DataSource`** (`javax.sql.DataSource`): source providing `java.sql.Connection` instances. It may connect directly or go through a connection pool such as HikariCP.
- **`JdbcOperations`**: interface containing high-level JDBC operations using positional parameters, implemented by `JdbcTemplate`.
- **`JdbcTemplate`**: Spring JDBC implementation using a `DataSource`, managing connections, statements, result sets, callbacks, and translating many `SQLException`s into `DataAccessException`s.
- **`NamedParameterJdbcOperations`**: interface for SQL operations with named parameters, implemented by `NamedParameterJdbcTemplate`.
- **`NamedParameterJdbcTemplate`**: provides `:id`, `:name`, and `SqlParameterSource` parameter sources; it uses `JdbcTemplate` underneath.
- **`JdbcClient`**: fluent interface wrapping the operations/templates above, unifying how common queries and updates are written.

Diagram:

```text
Service / Repository
       |
       v
    JdbcClient
       |
       +---- ? param ------------> JdbcOperations / JdbcTemplate
       |
       +---- :name param --------> NamedParameterJdbcOperations
       |                             / NamedParameterJdbcTemplate
       |                                       |
       +---------------------------------------+
                                               |
                                               v
                                          JdbcTemplate
                                               |
                                               v
                                           DataSource
                                               |
                                               v
                                            Connection
                                               |
                                               v
                                           Database
```

This is a **responsibility diagram**; when creating a client from `JdbcOperations`, Spring can create an appropriate named-parameter wrapper sharing that delegate. Do not interpret the diagram as a rule that "each `JdbcClient` opens a new connection". Connection lifecycle continues to be governed by the `DataSource`, pool, and transaction manager.

### What Kind of API Is JdbcClient?

`JdbcClient` is an **interface**, so you do not call `new JdbcClient()`. Use the static factory `JdbcClient.create(...)` to obtain an implementation, or inject the bean provided by Spring Boot/Spring configuration.

```java
JdbcClient client = JdbcClient.create(dataSource);
```

This is **an illustrative statement inside a method**, assuming a configured `DataSource dataSource` variable. The output of `create(...)` is a reusable fluent object; it is not a JDBC `Connection` and **does not need `close()` called after every query**.

A simple query:

```java
Long count = client.sql("SELECT COUNT(*) FROM books WHERE price >= ?")
    .param(new java.math.BigDecimal("100.00"))
    .query(Long.class)
    .single();
```

The parts:

1. `sql(...)` starts a statement specification.
2. `param(...)` binds a value to the `?` marker.
3. `query(Long.class)` specifies the result mapping type.
4. `single()` requires exactly one row; `COUNT(*)` without `GROUP BY` fits because it always produces one row, even when the count is 0.

The statement only runs when the terminal operation `single()` is called. `sql(...)` and `param(...)` build the request configuration; they do not send a query to the DB each time they are called. Once the query finishes, JDBC resources are managed by the underlying templates.

## 2. Three Key Factory Methods

`JdbcClient` exposes three primary creation methods, each taking a different input object:

| Factory method | Prerequisite | When to use | Things to remember |
| --- | --- | --- | --- |
| `JdbcClient.create(DataSource)` | `DataSource` | Plain Spring Framework, small examples, or no custom template yet | Spring creates the needed JDBC delegates from the data source |
| `JdbcClient.create(JdbcOperations)` | `JdbcOperations`, typically `JdbcTemplate` | A configured `JdbcTemplate` already exists; want to preserve its settings | Reuses the existing delegate, including its data source and template configuration |
| `JdbcClient.create(NamedParameterJdbcOperations)` | `NamedParameterJdbcOperations`, typically `NamedParameterJdbcTemplate` | A named-parameter template already exists; want to reuse its underlying configuration | Reuses the existing named-parameter delegate |

These factory methods belong to Spring Framework 6.1+. Do not use a Spring Framework 6.0 project and expect importing `JdbcClient` to succeed: the API does not exist in that line.

With the same `DataSource` and default template configuration, all three options can produce equivalent SQL results. The notable difference is **the degree of reuse of existing configuration and objects**, not that "DataSource only supports `?`, while named template only supports `:name`". `JdbcClient` provides both parameter styles through a unified facade.

## 3. Option A: Creating from a DataSource

If the application already has a `DataSource` bean but no template that needs to be reused:

```java
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;

public final class SimpleBookReader {
    private final JdbcClient client;

    public SimpleBookReader(DataSource dataSource) {
        this.client = JdbcClient.create(dataSource);
    }

    public long countBooks() {
        Long value = client.sql("SELECT COUNT(*) FROM books")
            .query(Long.class)
            .single();
        return java.util.Objects.requireNonNull(value);
    }
}
```

This is a Java 17+ class that **requires Spring JDBC on the classpath**, a `DataSource` passed to the constructor, and the `books` table existing at runtime. It has no `main` method, so it is not a standalone runnable program. `JdbcClient.create(dataSource)` is the initialization point; calling `countBooks()` will use that data source to execute SQL.

### Declaring a Bean in Plain Spring Framework

```java
package example;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;

@Configuration
public class JdbcClientConfig {
    @Bean
    JdbcClient jdbcClient(DataSource dataSource) {
        return JdbcClient.create(dataSource);
    }
}
```

The file should be `src/main/java/example/JdbcClientConfig.java` in a Spring project with appropriate component scanning/`@Import`. **Prerequisite:** there must be exactly one matching `DataSource` in the context, or you must add `@Qualifier` to select the right bean when multiple data sources exist.

Once the bean exists, a repository only needs constructor injection:

```java
public BookRepository(JdbcClient client) {
    this.client = client;
}
```

The snippet above is a constructor inside a class that has already declared a `JdbcClient client` field and imports that type; it is not a standalone class.

### Where Does the DataSource Come From?

- Spring Boot can auto-configure a `DataSource` based on JDBC dependencies and `spring.datasource.*`.
- Plain Spring Framework applications can define a `@Bean DataSource` with a pool, or obtain one from JNDI/a container.
- Whether the data source uses a connection pool or not, `JdbcClient` only needs the `DataSource` contract.

**Do not initialize a new pool in every repository or on every HTTP request.** A `DataSource`/pool is typically a shared resource; creating unnecessary pools increases connections to the database and makes transactions harder to manage.

### Limitations of Using Only a DataSource

Suppose an existing `JdbcTemplate` has been customized with `setQueryTimeout(...)`, `setFetchSize(...)`, `setMaxRows(...)`, or `setExceptionTranslator(...)`. If you call `JdbcClient.create(dataSource)` to create a **new** set of delegates, you **should not assume by default** that all runtime configurations of the old `JdbcTemplate` will be inherited. In this situation, options B/C in the following sections preserve the existing template.

## 4. Option B: Creating from an Existing JdbcOperations/JdbcTemplate

`JdbcTemplate implements JdbcOperations`, so you can create a `JdbcClient` from an already configured template.

```java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;

JdbcTemplate template = new JdbcTemplate(dataSource);
template.setQueryTimeout(15);
template.setFetchSize(100);

JdbcClient client = JdbcClient.create(template);
```

This is a **code fragment inside a configuration method** where `DataSource dataSource` already exists. It is not a standalone Java file.

When `JdbcClient.create(template)` is called, Java selects the overload accepting `JdbcOperations`. The template remains the delegate performing the JDBC work. This is especially valuable if the existing template already has:
- a verified and properly routed `DataSource`;
- statement timeout (`query timeout`);
- fetch size (`fetchSize`), row limit (`maxRows`);
- a SQL exception translator or specific execution settings.

Depending on the driver, hints such as `fetchSize` may not have the same effect for every SQL statement. Architecturally, however, **the client uses the existing template**, rather than creating a completely separate template and losing the settings already configured in code.

### Injecting via the Interface

You can avoid depending directly on the `JdbcTemplate` class:

```java
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.simple.JdbcClient;

public final class BookLookup {
    private final JdbcClient client;

    public BookLookup(JdbcOperations operations) {
        this.client = JdbcClient.create(operations);
    }
}
```

`BookLookup` is a class that Spring can instantiate if a `JdbcOperations` bean already exists; usually the actual bean is a `JdbcTemplate`. Do not conflate `JdbcOperations` with `DataSource`: they are two different abstractions.

If defining a `JdbcClient` bean manually:

```java
@Configuration
class ExistingTemplateClientConfig {
    @Bean
    JdbcClient jdbcClient(JdbcTemplate jdbcTemplate) {
        return JdbcClient.create(jdbcTemplate);
    }
}
```

This `@Configuration` snippet needs imports for `org.springframework.context.annotation.Configuration`, `Bean`, `org.springframework.jdbc.core.JdbcTemplate`, and `org.springframework.jdbc.core.simple.JdbcClient`. It is an **alternative configuration option**, so **do not place it alongside** the `JdbcClientConfig` bean in section 3 if both define beans of the same meaning without distinct names/`@Qualifier`.

**Do not arbitrarily replace a configured `JdbcTemplate` bean with `new JdbcTemplate(dataSource)`** while the rest of the application still uses the old bean. Even against the same DB, differences in timeout, exception translation, and execution policies can make debugging difficult.

## 5. Option C: Creating from NamedParameterJdbcOperations

An application using `NamedParameterJdbcTemplate` typically has many queries with named parameters `:id`, `:status`, `:minPrice`. If that template is already configured, you can create the client using the overload accepting `NamedParameterJdbcOperations`:

```java
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;

JdbcClient client = JdbcClient.create(namedParameterJdbcTemplate);
```

`namedParameterJdbcTemplate` is an already configured bean variable of type `NamedParameterJdbcTemplate`. The snippet belongs in a method/configuration rather than a standalone class.

Example of creating the template from an existing `JdbcTemplate`:

```java
JdbcTemplate classic = new JdbcTemplate(dataSource);
classic.setQueryTimeout(10);

NamedParameterJdbcTemplate named =
    new NamedParameterJdbcTemplate(classic);

JdbcClient client = JdbcClient.create(named);
```

`JdbcTemplate` and `NamedParameterJdbcTemplate` are Spring JDBC classes; `dataSource` must be supplied beforehand. When obtaining `JdbcClient` from `named`, the client reuses the named delegate and the underlying `JdbcTemplate`, including its `DataSource` and related settings.

### Creating a Bean from a Named Template

```java
@Configuration
class NamedTemplateClientConfig {
    @Bean
    JdbcClient jdbcClient(
            NamedParameterJdbcTemplate namedParameterJdbcTemplate) {
        return JdbcClient.create(namedParameterJdbcTemplate);
    }
}
```

This is a **configuration option independent of options A/B**, applicable only when the context already has a `NamedParameterJdbcTemplate` bean and corresponding imports. Do not define three `JdbcClient` beans of the same type just to try all three overloads in one context; if you truly need multiple databases/clients, qualify the beans clearly.

### One Client Still Supports Both Parameter Styles

Whether created from `DataSource`, `JdbcOperations`, or `NamedParameterJdbcOperations`, the `JdbcClient` facade API can handle both positional and named parameters in common cases:

**Positional:**

```java
long id = 7L;
var result = client.sql("SELECT title FROM books WHERE id = ?")
    .param(id)
    .query(String.class)
    .optional();
```

**Named:**

```java
long id = 7L;
var result = client.sql("SELECT title FROM books WHERE id = :id")
    .param("id", id)
    .query(String.class)
    .optional();
```

The two blocks above are **two alternatives** for the same method; do not declare the `result` variable twice in the same scope. With 0 rows, `optional()` returns `Optional.empty()`; with more than one row, the operation expects at most one result and may throw a result-size error. With `SELECT title`, if the SQL value of the column is `NULL`, consider the nullable mapping contract and the meaning of `Optional`.

**Do not arbitrarily mix `?` and `:id` in the same SQL statement.** Choose one consistent style per statement. Having Spring parse and bind parameter names does not turn them into a mechanism for substituting table/column names; placeholders only represent **values**.

## 6. Spring Boot: Inject JdbcClient Without Calling create

In Spring Boot **3.2+**, when Spring JDBC and the required auto-configurations are available, Boot can pre-create `JdbcTemplate`, `NamedParameterJdbcTemplate`, and `JdbcClient`. Specifically, `JdbcClientAutoConfiguration` depends on the presence of a matching `NamedParameterJdbcTemplate` candidate and backs off when a user-defined `JdbcClient` bean is already present.

Typical flow:

```text
Spring Boot + spring-boot-starter-jdbc + JDBC driver
                       |
                       v
                Auto-config DataSource
                       |
                       v
                Auto-config JdbcTemplate
                       |
                       v
            Auto-config NamedParameterJdbcTemplate
                       |
                       v
                 Auto-config JdbcClient
                       |
                       v
             Inject into repository/service
```

A repository can receive the client directly via constructor:

```java
package example;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public final class BookStore {
    private final JdbcClient jdbc;

    public BookStore(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public long countBooks() {
        return java.util.Objects.requireNonNull(
            jdbc.sql("SELECT COUNT(*) FROM books")
                .query(Long.class)
                .single()
        );
    }
}
```

This is a repository bean when package `example` is component-scanned by Spring, the database has a `books` table, and the context has a `JdbcClient` bean. There is no `main`, so the code is not standalone.

**Prefer injecting the auto-configured bean** when it meets your needs. When Spring Boot already provides `JdbcClient`, calling `JdbcClient.create(dataSource)` inside every repository is not necessarily functionally wrong, but it duplicates setup and bypasses `JdbcTemplate` customizations that Boot or the project has applied, such as `spring.jdbc.template.*`.

### When Do You Still Need to Manually Declare @Bean JdbcClient in Boot?

- The application has multiple `DataSource`s/templates and needs a client for a specific source.
- You want independent bean configuration/naming without relying on default auto-configuration.
- You have a specialized template configured with policies different from the default template.

When declaring a bean manually, keep Boot's `@ConditionalOnMissingBean` mechanism and the actual number of beans of the same type in mind. A manual definition causes `JdbcClient` auto-configuration to back off; this is intentional if you genuinely want to replace the default bean.

### Common Error Conditions

If a project uses **Spring Framework 6.0** or **Spring Boot 3.1**, importing `JdbcClient` will fail to compile because the bundled Spring Framework version does not yet include the API. You must upgrade to a supported version (Spring 6.1+/Boot 3.2+) or continue using `JdbcTemplate`/`NamedParameterJdbcTemplate`.

If the context lacks a valid `DataSource`, the client bean will not invent a DB connection either. If there are multiple data sources/templates and no primary candidate, auto-configuration may fail to produce a single `JdbcClient`; you must design the beans explicitly.

## 7. Runnable Example: Spring Boot + JdbcClient from Configured Infrastructure

This example uses **Java 17+, Spring Boot 3.3.x**, `spring-boot-starter-jdbc`, and H2 in-memory. Goal: observe Boot supplying the `JdbcClient` bean, the repository using the fluent API for both `:name` and `?`, while the underlying `JdbcTemplate` and `DataSource` are shared properly.

Create a Spring Boot 3.3.x Gradle project with the Boot plugin and dependency management as in a standard Spring Boot project. In the `dependencies` block of `build.gradle`, declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

This is a **dependencies block to add into an existing Boot project's build script**, not an entire Gradle file. Spring Boot 3.3.x corresponds to Spring Framework 6.1.x and Java 17.

### 7.1. DataSource Configuration

**`src/main/resources/application.yml`:**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:jdbc_client_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
```

In-memory H2 lets you test without a separate database server. When using PostgreSQL/MySQL in a real environment, provide the corresponding driver, JDBC URL, and credentials. Do not hard-code production credentials in the repository.

### 7.2. Data Record

**`src/main/java/example/Book.java`:**

```java
package example;

import java.math.BigDecimal;

public record Book(long id, String code, String title, BigDecimal price) {}
```

`record` has been available since Java 16 and fits Java 17. `price` uses `BigDecimal` to avoid binary floating-point rounding errors of `double` when storing SQL `DECIMAL` monetary values.

### 7.3. Repository Depending Only on JdbcClient

**`src/main/java/example/BookCatalogRepository.java`:**

```java
package example;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public final class BookCatalogRepository {
    private static final RowMapper<Book> BOOK_MAPPER =
        (rs, rowNum) -> new Book(
            rs.getLong("id"),
            rs.getString("code"),
            rs.getString("title"),
            rs.getBigDecimal("price")
        );

    private final JdbcClient jdbc;

    public BookCatalogRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(Book book) {
        return jdbc.sql("""
                INSERT INTO book_catalog (id, code, title, price)
                VALUES (:id, :code, :title, :price)
                """)
            .param("id", book.id())
            .param("code", book.code())
            .param("title", book.title())
            .param("price", book.price())
            .update();
    }

    public Optional<Book> findById(long id) {
        return jdbc.sql("""
                SELECT id, code, title, price
                FROM book_catalog
                WHERE id = :id
                """)
            .param("id", id)
            .query(BOOK_MAPPER)
            .optional();
    }

    public List<Book> findAtLeast(BigDecimal minimum) {
        return jdbc.sql("""
                SELECT id, code, title, price
                FROM book_catalog
                WHERE price >= ?
                ORDER BY id
                """)
            .param(minimum)
            .query(BOOK_MAPPER)
            .list();
    }

    public int rename(long id, String newTitle) {
        return jdbc.sql("UPDATE book_catalog SET title = ? WHERE id = ?")
            .param(newTitle)
            .param(id)
            .update();
    }
}
```

For each method:
- `insert` uses four named parameters; the names in `:id`, `:code`, `:title`, `:price` must match the bound names.
- `findById` returns `Optional<Book>`. `optional()` avoids forcing the application to catch a "zero rows" exception; if the query returns more than one row, the single-result contract is still enforced.
- `findAtLeast` uses positional `?` and `param(minimum)`; `ORDER BY id` guarantees result ordering rather than relying on storage order.
- `rename` has two markers, binding newTitle before id; the return value of `update()` is the affected row count. If the ID does not exist, it normally returns 0.
- `BOOK_MAPPER` converts `ResultSet` into `Book`; the class above is a component-scanned Spring repository and does not manage connections itself.

Notably, **the same `JdbcClient` bean serves both parameter styles**; there is no need to create two clients or two `DataSource`s just because one SQL statement uses `:id` and another uses `?`.

### 7.4. Run and Observe Output

**`src/main/java/example/JdbcClientDemoApplication.java`:**

```java
package example;

import java.math.BigDecimal;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class JdbcClientDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcClientDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate template, BookCatalogRepository books) {
        return args -> {
            template.execute("""
                CREATE TABLE book_catalog (
                    id BIGINT PRIMARY KEY,
                    code VARCHAR(20) NOT NULL UNIQUE,
                    title VARCHAR(100) NOT NULL,
                    price DECIMAL(12, 2) NOT NULL
                )
                """);

            Book javaBook = new Book(
                1L, "JAVA-1", "Java Core",
                new BigDecimal("90.00")
            );
            Book springBook = new Book(
                2L, "SPR-2", "Spring JDBC",
                new BigDecimal("150.50")
            );

            System.out.println("insert1=" + books.insert(javaBook));
            System.out.println("insert2=" + books.insert(springBook));
            System.out.println("expensive=" +
                books.findAtLeast(new BigDecimal("100.00")));
            System.out.println("found=" + books.findById(1L));
            System.out.println("missing=" + books.findById(99L));
            System.out.println("renamed=" +
                books.rename(1L, "Java Core 17"));
            System.out.println("after=" + books.findById(1L));
        };
    }
}
```

Run from the project root directory:

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`. With a freshly initialized in-memory H2 database, no other table/data scripts, and Boot successfully configuring `JdbcClient`, in addition to Spring/Hikari logs, **the program itself prints**:

```text
insert1=1
insert2=1
expensive=[Book[id=2, code=SPR-2, title=Spring JDBC, price=150.50]]
found=Optional[Book[id=1, code=JAVA-1, title=Java Core, price=90.00]]
missing=Optional.empty
renamed=1
after=Optional[Book[id=1, code=JAVA-1, title=Java Core 17, price=90.00]]
```

Explanation:
1. `JdbcTemplate` is injected into `CommandLineRunner` to run DDL. The `JdbcClient` received by the repository is also configured by Boot on top of the application's JDBC infrastructure; both access the same matching `DataSource`.
2. `insert` is called twice and returns `1` affected row for each successful `INSERT`.
3. `findAtLeast(100.00)` retrieves the book priced at `150.50`; `90.00` does not meet the threshold.
4. `findById(1)` gets one record; `findById(99)` matches no row and returns `Optional.empty()`.
5. `rename` updates one row's title via two positional parameters; the `after` query reflects the new value.
6. SQL `DECIMAL(12,2)` and `BigDecimal` preserve two decimal places in the printed prices under the conditions described.

The three Java files above form **a complete Spring Boot application when placed in a project with the proper build script and dependencies listed above**; they are not files meant for plain JDK `javac` alone. If the application has another custom `JdbcClient` bean or picks the wrong `DataSource`, check bean wiring rather than assuming every query targets the example H2 database.

## 8. Creating Directly from DataSource and Templates: Three Versions of the Same Query

You can see all three overloads provide the facade with the same statement structure:

### Approach 1: DataSource Only

```java
JdbcClient client = JdbcClient.create(dataSource);

Long total = client.sql("SELECT COUNT(*) FROM book_catalog")
    .query(Long.class)
    .single();
```

`dataSource` is an existing `DataSource` variable; the snippet resides inside a method/configuration.

### Approach 2: Configured JdbcOperations

```java
JdbcTemplate template = new JdbcTemplate(dataSource);
template.setQueryTimeout(12);

JdbcClient client = JdbcClient.create(template);

Long total = client.sql("SELECT COUNT(*) FROM book_catalog")
    .query(Long.class)
    .single();
```

Customizing query timeout is a setting on the template being reused. In a real project, **if a configured `JdbcTemplate` bean already exists, inject it** rather than calling `new` just to create a client.

### Approach 3: NamedParameterJdbcOperations

```java
NamedParameterJdbcTemplate named =
    new NamedParameterJdbcTemplate(template);

JdbcClient client = JdbcClient.create(named);

Long total = client.sql("SELECT COUNT(*) FROM book_catalog")
    .query(Long.class)
    .single();
```

In this approach the `template` variable was initialized in the previous section; this snippet belongs in the same context and is not self-contained. `NamedParameterJdbcTemplate` delegates to the classic template, so its settings are preserved.

**Do not declare all three `client` variables in a single block**, as these are three alternatives for comparison. In an application with one primary data source, usually only **one shared client bean** is needed.

## 9. Parameter Binding: Fluent Does Not Mean Ignoring JDBC

With positional parameters, each `?` receives a value in order:

```java
int changed = client.sql("""
        UPDATE book_catalog
        SET title = ?, price = ?
        WHERE id = ?
        """)
    .param("Spring Advanced")
    .param(new java.math.BigDecimal("199.90"))
    .param(2L)
    .update();
```

There are three markers corresponding to title, price, and id. If you swap their order, the statement can produce wrong data or fail depending on data types; the framework does not infer positions from Java variable names.

With named parameters:

```java
int changed = client.sql("""
        UPDATE book_catalog
        SET title = :title, price = :price
        WHERE id = :id
        """)
    .param("id", 2L)
    .param("price", new java.math.BigDecimal("199.90"))
    .param("title", "Spring Advanced")
    .update();
```

The order of `param("name", value)` calls does not need to match the order in the SQL because Spring matches by name; **names must match** and types still need to be SQL-compatible.

### Map and NULL Parameters

A SQL statement with a nullable column:

```java
var parameters =
    new org.springframework.jdbc.core.namedparam.MapSqlParameterSource()
        .addValue("note", null, java.sql.Types.VARCHAR)
        .addValue("id", 7L, java.sql.Types.BIGINT);

int changed = client.sql(
        "UPDATE book_catalog SET note = :note WHERE id = :id")
    .paramSource(parameters)
    .update();
```

**This is an illustrative snippet for a schema that has an added `note VARCHAR` column;** the demo table in section 7 **does not have a note column**, so do not run this statement verbatim on the unmodified demo table. `MapSqlParameterSource` can pass null with an explicit SQL type; `Map.of("note", null)` is invalid because `Map.of` forbids null values.

Beyond names and types, keep input values separate from SQL text: `JdbcClient` still relies on `PreparedStatement` underneath and helps prevent SQL injection at **value positions**. Elements such as table names, column names, and sort modes **must not use placeholders to substitute identifier names**; whitelist them when they are dynamic choices.

### IN with Multiple Values

```java
var ids = java.util.List.of(1L, 2L, 3L);

var books = client.sql("""
        SELECT id, code, title, price
        FROM book_catalog
        WHERE id IN (:ids)
        ORDER BY id
        """)
    .param("ids", ids)
    .query(BOOK_MAPPER)
    .list();
```

This is a snippet inside a class that has `JdbcClient client` and `RowMapper<Book> BOOK_MAPPER`; it requires the example table. With named parameters, Spring can expand a collection into multiple appropriate positional markers. An empty list needs an explicit policy (`IN ()` is not portable); if there are no IDs to look up, typically return `List.of()` without issuing SQL. Do not write a single `IN (?)` and expect every driver to interpret a Java `List` as multiple SQL values.

## 10. Query Results: single, optional, list, and Mapping

`JdbcClient` separates **how SQL is executed** from **how result size is interpreted**:

| Fluent API | Expectation | Behavior to understand |
| --- | --- | --- |
| `query(MyType.class).single()` | Exactly one value/row | No rows throws an empty-result error; multiple rows throws a size error |
| `query(rowMapper).single()` | Exactly one object/row | Suitable when querying by unique key and existence is required |
| `query(rowMapper).optional()` | 0 or 1 row | `Optional.empty()` when no rows; multiple rows is a violation |
| `query(rowMapper).list()` | 0..N rows | Empty list when 0 rows |
| `sql(...).update()` | Appropriate write/DDL statement | Returns affected row count (`int`), depending on SQL and driver |

If a repository method is `findById` (may not exist), `optional()` is usually appropriate; if it is `getRequiredById`, `single()` expresses a clear contract.

Example using a mapper:

```java
Book required = client.sql("""
        SELECT id, code, title, price
        FROM book_catalog WHERE id = :id
        """)
    .param("id", 7L)
    .query(BOOK_MAPPER)
    .single();
```

This snippet requires `BOOK_MAPPER` defined as in the demo repository. If `id=7` does not exist, Spring throws an error for the "exactly one row" contract; **it does not return `null` by default just because no row was found**. With `query(Book.class)` Spring also supports property/record-based mapping under suitable conditions, though a custom `RowMapper` is often clearer when column names differ from fields or conversions follow business rules.

### Resource Management

`JdbcClient` has no `close()` method to call after each `sql(...)`. Operations beneath the facade use JDBC templates to borrow/return connections, prepare statements, process `ResultSet`s, and translate exceptions. Do not retain a `ResultSet` or `Connection` outside a mapper callback. When using an API that returns a `Stream` or resource with a special lifecycle from a lower layer, follow that API's closing contract rather than assuming every result stream releases itself immediately upon creation.

## 11. Transactions: Choosing the Right DataSource or Template Is What Truly Matters

`JdbcClient` **does not automatically create a transaction spanning multiple SQL statements** just because two operations run on the same client object. JDBC transactions are managed through the `Connection` and the Spring transaction manager bound to the corresponding **`DataSource`**.

Example of a service calling a repository:

```java
package example;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class CatalogService {
    private final BookCatalogRepository books;

    public CatalogService(BookCatalogRepository books) {
        this.books = books;
    }

    @Transactional
    public void addTwo(Book first, Book second) {
        books.insert(first);
        books.insert(second);
    }
}
```

This is a component used within a Spring context that has a compatible transaction manager. When `addTwo` is called **through the Spring transaction proxy**, and both repository operations use a client/template bound to **the same `DataSource`** managed by the transaction manager, they can participate in a shared JDBC transaction. If the second insert throws `DuplicateKeyException` (a runtime exception), the default rollback policy normally rolls back the first insert as well.

- **Creating `JdbcClient` from the right `DataSource`/template** is essential for transactions to work as expected.
- `JdbcClient.create(dataSource)` does not start a transaction when the client is created.
- `JdbcClient.create(template)` reuses the template's configuration; transaction integration still depends on the data source and transaction manager.
- If a service uses two `DataSource`s pointing to two different DBs, a standard JDBC `@Transactional` **does not automatically become an atomic distributed transaction**.
- Standard Spring AOP proxies do not intercept internal self-invocations like `this.addTwo(...)` within the same bean; in that case the annotation may not be applied.
- Do not manually call `commit`/`rollback` on a connection owned by the Spring transaction manager.

The biggest distinction among the three ways of creating a client is **not** "which factory supports transactions"; all of them use the appropriate Spring JDBC mechanism matching the chosen delegate and data source.

## 12. Multiple DataSources: Creating Clients per Source

Suppose an application has `primaryDataSource` and `reportingDataSource`. Injecting `DataSource` by type alone without a qualifier or primary designation may prevent Spring from choosing a bean, or cause a client to query the wrong database.

A configuration pattern when a bean named **`reportingDataSource` already exists**:

```java
package example;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;

@Configuration
public class ReportingJdbcConfig {
    @Bean("reportingJdbcClient")
    JdbcClient reportingJdbcClient(
            @Qualifier("reportingDataSource") DataSource source) {
        return JdbcClient.create(source);
    }
}
```

This **configures a client for the reporting source** and does not define the underlying data source itself. The `reportingDataSource` bean must be provided by another configuration. In the repository, inject the bean explicitly:

```java
public ReportingRepository(
        @Qualifier("reportingJdbcClient") JdbcClient jdbc) {
    this.jdbc = jdbc;
}
```

This constructor snippet requires importing `@Qualifier` and belongs in a class with a `JdbcClient jdbc` field. If the application also has a primary `JdbcClient` bean, the two beans need clear names/`@Primary`/`@Qualifier`; do not create unqualified beans and hope Spring guesses the right DB.

### Should You Create from DataSource or Template for the Second Source?

If the reporting DB already has a dedicated `JdbcTemplate` with `queryTimeout` and `fetchSize` tuned for long queries, create `JdbcClient.create(reportingJdbcTemplate)` to **reuse that configuration**. If no such template exists and defaults suffice, creating from `reportingDataSource` is reasonable.

For transactions on a secondary source, the transaction manager qualifier must also match—for example, selecting the right transaction manager bean in `@Transactional("reportingTxManager")` if that bean actually exists and writes are permitted. Do not assume adding `@Qualifier` to the client is enough to turn two data sources into a single transaction.

## 13. Testing Wiring: Which Client Uses Which Source?

There are two separate questions worth testing:

1. **Proper initialization?** Does the context contain a `JdbcClient` bean backed by the expected DataSource/template without `NoSuchBeanDefinitionException` or `NoUniqueBeanDefinitionException`?
2. **Proper execution?** Does the SQL run against the expected database, bind parameters properly, map results accurately, and manage transactions and resources appropriately?

For the Spring Boot demo project in section 7, you can use a JDBC slice test. Add to `build.gradle`:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

**`src/test/java/example/BookCatalogRepositoryTest.java`:**

```java
package example;

import java.math.BigDecimal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Import(BookCatalogRepository.class)
class BookCatalogRepositoryTest {
    @Autowired
    JdbcTemplate template;

    @Autowired
    BookCatalogRepository books;

    @BeforeEach
    void setUp() {
        template.execute("""
            CREATE TABLE IF NOT EXISTS book_catalog (
                id BIGINT PRIMARY KEY,
                code VARCHAR(20) NOT NULL UNIQUE,
                title VARCHAR(100) NOT NULL,
                price DECIMAL(12, 2) NOT NULL
            )
            """);
        template.update("DELETE FROM book_catalog");
    }

    @Test
    void clientCreatedByBootSupportsNamedAndPositional() {
        Book item = new Book(
            7L, "BOOK-7", "Effective Java",
            new BigDecimal("120.00")
        );
        assertEquals(1, books.insert(item));
        assertEquals(item, books.findById(7L).orElseThrow());

        var expensive = books.findAtLeast(new BigDecimal("100.00"));
        assertEquals(1, expensive.size());
        assertEquals(7L, expensive.get(0).id());
        assertEquals(1, books.rename(7L, "Effective Java 3"));
        assertEquals(
            "Effective Java 3",
            books.findById(7L).orElseThrow().title()
        );
    }

    @Test
    void optionalIsEmptyWhenRowDoesNotExist() {
        assertTrue(books.findById(999L).isEmpty());
        assertEquals(0, books.rename(999L, "Absent"));
    }
}
```

Run:

```bash
./gradlew test
```

With Spring Boot **3.3.x**, `@JdbcTest` auto-configures the required JDBC components, including `JdbcClient` when conditions match, and `@Import` registers the repository bean for the slice test. **2 tests are expected to pass** when H2 and the schema match. `@JdbcTest` uses an embedded DB by default and rolls back transactions after each test; the application does not need to run the full `CommandLineRunner`.

**Why is this test useful?** It proves that an actual `JdbcClient` bean is injected, both parameter styles work together, the mapper returns the record accurately, and a query with no matching row returns `Optional.empty()`. A unit test that only mocks the client cannot verify SQL, the driver, or actual `DataSource` configuration.

In applications running PostgreSQL/MySQL in production, add integration tests with the real DB/driver (for example via Testcontainers); H2 does not replace verifying dialect, schema, conversions, and transactions in the real environment.

### Dedicated Tests When Using a Custom Template

If your goal is "create a client from an already configured template", write a configuration test:

- Create or inject the target `JdbcTemplate` with an observable setting configured (such as `queryTimeout`).
- Create the client via `JdbcClient.create(existingTemplate)`, without creating another `new JdbcTemplate`.
- Verify the corresponding data source and execution behavior in an integration test environment.
- When multiple DBs are present, insert distinct data into each source and verify that each client only sees data from the right DB.

Do not only assert `client != null`: a client can exist while still pointing to the wrong data source or wrong template.

## 14. Common Design Mistakes

| Mistake | Consequence / Fix |
| --- | --- |
| Using Spring 6.0/Boot 3.1 while importing `JdbcClient` | API is not supported; upgrade to Spring 6.1+/Boot 3.2+ or use older templates |
| Treating `JdbcClient` as a `Connection` | Wrong abstraction layer; `JdbcClient` is a facade, while connections come from the data source at execution time |
| Calling `JdbcClient.create(dataSource)` repeatedly in every request even when Boot provides a client bean | Increases duplicate setup and bypasses shared template settings; inject and reuse the bean |
| Having a customized `JdbcTemplate` but creating the client from the data source | May lose existing template settings; use `create(existingTemplate)` |
| Having a `NamedParameterJdbcTemplate` but creating a brand new template | Ignores the existing delegate/configuration; create the client from the injected named template |
| Defining multiple `@Bean JdbcClient` beans without clear qualifiers | Injection ambiguity, multiple-bean errors, or querying the wrong DB; use `@Qualifier`/`@Primary` |
| Assuming calling `create(...)` verifies the DB is alive | The client can be created without running any query; test actual connectivity/SQL |
| Inconsistently mixing `:name` and `?` in one SQL statement | Prone to binding errors; choose one consistent placeholder style per statement |
| Parameters with matching names but incompatible SQL types | Conversion errors or corrupted data; verify SQL type, precision, and nullability |
| Treating `optional()` as "get the first record" | It represents 0 or 1, and multiple rows is an error; use `list()` or a proper query |
| Treating the fluent client as an ORM or JPA `EntityManager` | No JPA persistence context or dirty checking; you still write SQL |
| Assuming operations through the same client automatically share a transaction | Use a transaction manager/`@Transactional` bound to the right DataSource |
| Trying to force all stored procedures/batch workflows through `JdbcClient` | For advanced operations, see `JdbcTemplate`, `SimpleJdbcInsert`, and `SimpleJdbcCall` |
| Holding onto a query's statement spec and sharing it across threads | Only share the configured client; build a separate `sql(...).param(...)` chain per operation |
| Using `JdbcClient.create(new JdbcTemplate(dataSource))` instead of the existing template bean | May bypass infrastructure/observability configuration; inject the existing bean |

### Do Not Expect JdbcClient to Replace Every High-Level SQL API

`JdbcClient` is a facade that **simplifies common queries and updates**. Tasks such as complex batch updates, advanced custom callbacks, retrieving generated keys under various strategies, or stored procedures with metadata and multiple result sets may call for lower-level or specialized APIs:

- `JdbcTemplate` / `JdbcOperations`;
- `NamedParameterJdbcTemplate` / `NamedParameterJdbcOperations`;
- `SimpleJdbcInsert` and `SimpleJdbcCall`.

There is no reason to discard these templates when adding `JdbcClient`: the client is built directly on top of them and can coexist cleanly in the architecture.

## 15. Checklist for Choosing How to Create a Client

**When starting a new Spring JDBC repository:**

1. Check versions: **Spring Framework 6.1+** is required; if using Boot, **3.2+** is typically needed for `JdbcClient` auto-configuration.
2. Check if the context already has a **configured `JdbcClient` bean**. If yes and it uses the right data source/template, **inject it directly**.
3. If no client exists yet and you only have a `DataSource`, use `JdbcClient.create(dataSource)` or define a shared `@Bean`.
4. If you already have a customized `JdbcTemplate`/`JdbcOperations`, use `JdbcClient.create(jdbcOperations)` to preserve its configuration.
5. If you already have a customized `NamedParameterJdbcTemplate`/`NamedParameterJdbcOperations`, use `JdbcClient.create(namedOperations)`.
6. With multiple data sources, qualify beans with `@Qualifier` and pair them with the matching transaction manager.
7. Use positional `?` or named `:name` consistently within each statement; never concatenate user values into raw SQL.
8. Choose `single()`, `optional()`, or `list()` based on the **result-size contract**.
9. Write integration tests to confirm schema, mapping, result ordering, timeouts/transactions, and the selected DB.
10. When an advanced API does not fit the facade, reuse the existing template rather than working around `JdbcClient`.

## 16. Self-Check Questions

**Question 1.** You have a `DataSource` bean and no customized JDBC template yet. Which creation approach should you use?

**Answer:** `JdbcClient.create(dataSource)` is the direct choice; if using Spring Boot 3.2+ which already auto-configures a client from the appropriate infrastructure, you usually just inject the `JdbcClient` bean.

**Question 2.** You have a `JdbcTemplate` with query timeout, fetch size, and an exception translator already set. What should you create the client from?

**Answer:** From that same `JdbcTemplate` via `JdbcClient.create(jdbcTemplate)` (the `JdbcOperations` overload), to preserve the existing settings and data source.

**Question 3.** Your application created a `NamedParameterJdbcTemplate`. Can `JdbcClient` accept it as a delegate?

**Answer:** Yes, via `JdbcClient.create(namedParameterJdbcTemplate)` (the `NamedParameterJdbcOperations` overload). The client reuses the named template and the underlying classic template.

**Question 4.** Can a client created from a `DataSource` run a query using `:id`?

**Answer:** Yes. `JdbcClient` supports both named and positional parameters for common statements; you do not need to create it from a named template just to use `:id`.

**Question 5.** Why does creating the client from the right `DataSource` matter for `@Transactional`?

**Answer:** The JDBC transaction manager coordinates connections on the corresponding data source. If the client uses a different data source, its SQL will not automatically join the same transaction just because the service carries the annotation.

**Question 6.** Does calling `JdbcClient.create(dataSource)` immediately open a new physical connection for each instance?

**Answer:** You should not assume that. The factory creates the JDBC facade/delegates; actual connections depend on the data source/pool and the moment an operation executes.

**Question 7.** Does `JdbcClient` automatically fix a SQL query missing `ORDER BY` to keep results deterministic?

**Answer:** No. Query ordering is only guaranteed when the SQL specifies it; the facade does not alter SQL semantics.

**Question 8.** Does using `JdbcClient` make `JdbcTemplate` obsolete or require removing it from the application?

**Answer:** No. `JdbcClient` delegates to the templates; complex APIs or deep configuration still use the templates directly.

**Question 9.** You have two `JdbcClient` beans, one for reporting and one for transactions. How do you choose between them?

**Answer:** Use `@Qualifier` or `@Primary` explicitly in configuration and injection; ensure the template, data source, and transaction manager match.

## 17. Official References

- [Spring Framework — `JdbcClient` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html): the three static `create` factories, overloads accepting `DataSource`, `JdbcOperations`, and `NamedParameterJdbcOperations`, and the fluent client contract.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): introduction to `JdbcClient` since 6.1, positional/named parameters, `RowMapper`, and query/update operations.
- [Spring Boot 3.3 — SQL Databases](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html): auto-configuration of `DataSource`, `JdbcTemplate`, `NamedParameterJdbcTemplate`, and `JdbcClient`.
- [Spring Boot — `JdbcClientAutoConfiguration`](https://docs.spring.io/spring-boot/docs/3.2.1/api/org/springframework/boot/autoconfigure/jdbc/JdbcClientAutoConfiguration.html): conditions for creating the `JdbcClient` bean, based on an available named template and absence of a custom client bean.
- [Spring Framework — `JdbcTemplate` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): template configuration and low-level operations reused beneath the client.
- [Spring Framework — Parameter Handling](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): SQL types and null parameters in Spring JDBC.
- [Spring Boot 3.3 — JDBC Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@JdbcTest` and JDBC slice testing principles.

**Takeaway:** `JdbcClient` is a **facade created from a `DataSource` or configured JDBC templates**, not a separate connection. **If you have a `DataSource`, use `create(dataSource)`; if you have a customized template, use `create(template)` to reuse its settings; if Spring Boot provides a `JdbcClient` bean, usually just inject it.** Choosing the right connection source keeps queries, exception translation, timeouts, and transactions consistent across the entire data access layer.