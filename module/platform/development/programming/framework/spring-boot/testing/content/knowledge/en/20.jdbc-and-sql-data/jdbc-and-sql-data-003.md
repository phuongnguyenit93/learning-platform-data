# @JooqTest and Configuring DSLContext in Spring Boot Testing

## 1. What Problem Does This Lesson Solve?

When an application uses **jOOQ** to write SQL queries via a Java DSL, a unit test that only mocks `DSLContext` often misses errors in SQL dialect, column names, data types, database constraints, or transaction configuration. Conversely, starting the entire application with `@SpringBootTest` for every small query makes tests slow and couples them to unrelated beans.

Spring Boot provides **`@JooqTest`**, a *test slice* focused on jOOQ data access infrastructure. It configures `DSLContext`, the DataSource, and components required for jOOQ, while **not automatically scanning every `@Component`/`@Repository` or `@ConfigurationProperties` in the application**. It uses the already configured DataSource by default; if you want to replace it with an embedded database, you must explicitly opt in with `@AutoConfigureTestDatabase`. `@JooqTest` tests run inside a Spring-managed transaction by default and roll back when the method ends.

This lesson focuses strictly on the topic **"@JooqTest and Configuring DSLContext"**, under **JDBC and SQL Data**. You will learn how to:

- Distinguish `@JooqTest`, `@JdbcTest`, `@DataJpaTest`, and `@SpringBootTest`.
- Understand what `DSLContext` holds: `DataSource`/`ConnectionProvider`, `SQLDialect`, `Settings`, transaction provider, and listener providers.
- Use `@AutoConfigureTestDatabase` to choose H2, keep a real database when needed, and avoid accidentally writing to production.
- Configure `spring.jooq.sql-dialect`, `DefaultConfigurationCustomizer`, and import collaborators under test.
- Write Java 17+ code with Spring Boot 3.3.5, the jOOQ DSL (without requiring a code generator), and an H2 test suite with a real SQL schema.
- Test SELECT/INSERT/UPDATE/DELETE queries, bind parameters, mapping, result ordering, unique/CHECK constraint errors, and transaction rollback.
- Know when H2 is not enough and database migrations plus Testcontainers for the real dialect are required.

**Example versions:** Java 17+, Spring Boot **3.3.5**, jOOQ 3.19.x managed by the Spring Boot BOM, and H2. This stack is pinned for reproducibility, not as a claim of the latest version; imports in Spring Boot 4 and newer jOOQ versions may differ.

## 2. What Is jOOQ and What Role Does DSLContext Play?

jOOQ (*Java Object Oriented Querying*) expresses SQL through a fluent Java API. Instead of concatenating SQL strings:

```java
String sql = "select * from books where isbn = '" + input + "'";
```

which risks SQL injection, jOOQ lets you build queries using typed `Field<T>` and **bind values**:

```java
dsl.select(ISBN, TITLE)
   .from(BOOKS)
   .where(ISBN.eq(input))
   .fetch();
```

This is a **snippet**; `DSLContext dsl`, `Field<String> ISBN/TITLE`, and `Table<?> BOOKS` are fully defined in the project later.

`DSLContext` is the entry point for building, rendering, and executing SQL. It holds a reference to `org.jooq.Configuration`, which includes:

| Component | Meaning | What to Test |
| --- | --- | --- |
| `SQLDialect` | SQL syntax rules and DB capabilities | H2 in tests vs. PostgreSQL in production—never assume they are identical |
| `ConnectionProvider` | How jOOQ obtains and releases JDBC connections | Connects to the test DataSource, not production |
| `TransactionProvider` | Coordinates transactions across jOOQ/Spring | Test DML participates properly in the transaction |
| `Settings` | SQL rendering, identifier names, bind values, and many other options | Whether customizers are actually applied |
| `ExecuteListenerProvider` | Observes query execution lifecycle | Instrumentation/logging when genuinely needed |
| `RecordMapperProvider` | Rules for converting a Record into a Java object | Whether custom mapping works |

When Spring Boot creates the `DSLContext` bean, it takes the `DataSource` from the Spring context, sets up providers, and determines the dialect. Therefore, tests must **inject this bean**, rather than arbitrarily creating `DSL.using("...")` manually when the goal is to verify Spring configuration.

### Test Execution Model

```text
JUnit Jupiter
     |
     v
@JooqTest (Spring TestContext, transaction, jOOQ slice)
     |
     +---- DataSource (H2, explicitly selected)
     |
     +---- jOOQ Configuration
     |       SQLDialect.H2
     |       Settings from DefaultConfigurationCustomizer
     |       Spring-aware connection / transaction
     |
     +---- DSLContext bean
     |       |
     |       +---- BookQueries (explicitly @Imported)
     |
     +---- SQL schema via @Sql BEFORE_TEST_CLASS
     |
     v
SELECT / INSERT / UPDATE / DELETE
     |
     v
H2 database (test method rollback)
```

jOOQ **is not an ORM like JPA/Hibernate**. Calling `insertInto(...).execute()` executes an explicit SQL statement immediately without waiting for JPA dirty checking/flush. Returning a jOOQ `Record` also differs from a JPA managed entity inside a persistence context.

## 3. @JooqTest vs. Other Test Slices

| Annotation | Focus | Typically Available Beans | When to Use |
| --- | --- | --- | --- |
| `@JooqTest` | jOOQ + SQL/DataSource | `DSLContext`, JDBC infrastructure, transactions | Testing SQL DSL, jOOQ repositories/DAOs |
| `@JdbcTest` | Plain JDBC | `JdbcTemplate`, DataSource, transactions | Testing SQL via JDBC/JdbcTemplate |
| `@DataJpaTest` | ORM/JPA | EntityManager, JPA repositories, TestEntityManager | Testing entity mapping, JPQL, JPA repositories |
| `@SpringBootTest` | Multiple app components | Full application context per config | Integration/service use cases across multiple layers |
| Plain JUnit + mocks | Java logic without DB | No real DB | Testing validation, branching, orchestration |

`@JooqTest` **does not set up REST controllers, a web server, or arbitrary service beans**. Nor does it provide `MockMvc` for HTTP testing. If you need end-to-end API verification, use a broader integration test and keep those to the necessary minimum.

Spring Boot 3.3 notes that `@JooqTest` uses the existing configured DataSource by default (unlike a common expectation from some other test slices) and rolls back test transactions. Thus, **never blindly assume the database is in-memory** simply because you see `@JooqTest`.

### When Is @Import Needed?

Suppose you have:

```java
@Repository
public class BookQueries {
    public BookQueries(DSLContext dsl) { ... }
}
```

This is only a signature snippet. In production, `@Repository` is picked up by component scanning. However, `@JooqTest` limits scanning; to test `BookQueries`, import it explicitly:

```java
@JooqTest
@Import(BookQueries.class)
class BookQueriesJooqTest { ... }
```

The practical configuration will import both `BookQueries` and `JooqConfig`. Importing a specific bean **does not turn the test into a full application test**. If that bean requires many collaborators, deliberately decide whether to import or mock dependencies to preserve the test scope.

## 4. Configuring the DataSource: Differences That Determine Safety

### 4.1. By Default JooqTest Uses the Configured Database

If a project contains:

```properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/store
```

then applying `@JooqTest` alone is **not enough** to claim the test switched to H2. When a database is already configured, Boot documentation instructs using `@AutoConfigureTestDatabase` when you want to replace it with an embedded database.

### 4.2. Intentionally Using H2 in the Demo

```java
@JooqTest(properties = "spring.jooq.sql-dialect=H2")
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.ANY)
class BookQueriesJooqTest { ... }
```

In the sample project, `com.h2database:h2` is on the test runtime classpath. `Replace.ANY` expresses replacing the test DataSource with an embedded database when auto-configuration applies. In Boot 3.3, `AutoConfigureTestDatabase` lives in package `org.springframework.boot.test.autoconfigure.jdbc`.

**Note:** forcing the H2 dialect is only valid because H2 is actually in use. The property `spring.jooq.sql-dialect=H2` **does not turn PostgreSQL into H2**, nor does it change the JDBC URL. A mismatched dialect can cause SQL failures or generate invalid syntax.

### 4.3. Keeping the Real Database Engine

When you need to test real PostgreSQL/MySQL or Testcontainers:

```java
@JooqTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgreSqlJooqTest { ... }
```

This is a strategy snippet without Testcontainers/DataSource setup, so it is not a standalone test. `Replace.NONE` keeps the supplied DataSource, for instance via `@DynamicPropertySource` or `@ServiceConnection`. In that case, ensure migrations/schema and container lifecycles are configured accurately. Never enable `Replace.NONE` while pointing at a production database.

### 4.4. Practical Guidelines

- Simple SQL CRUD, mapping logic, bind variables: H2 is usually fast enough.
- PostgreSQL `ON CONFLICT`, JSONB, arrays, advisory locks, engine-specific CTEs/locking: test against PostgreSQL.
- MySQL collations/`ON DUPLICATE KEY`, transaction isolation, auto-increment: test against the corresponding MySQL.
- Schema migrations: run actual Flyway/Liquibase scripts in the test environment if the system uses them.
- Do not treat H2 `MODE=PostgreSQL` as proof that all PostgreSQL semantics match.

## 5. Configuring DSLContext and SQLDialect

Spring Boot auto-configures `DSLContext` when jOOQ and a DataSource are present. A bean can be injected:

```java
@Autowired
DSLContext dsl;
```

`DSLContext.configuration().dialect()` returns the dialect jOOQ is using, such as `SQLDialect.H2` in the demo. The dialect governs SQL rendering, pagination, returning generated values, upserts, boolean expressions, and database compatibility.

### 5.1. Auto-Detect Dialect or Force the Property?

Normally Boot detects the SQL dialect from the DataSource; if unrecognized, it may fall back to `DEFAULT`. You can override it:

```properties
spring.jooq.sql-dialect=H2
```

When testing with H2, this property is explicit. For PostgreSQL in production, let Boot auto-detect it properly or specify `POSTGRES` if supported by your jOOQ edition and version. The open-source jOOQ edition supports an appropriate subset of dialects; do not assume all commercial dialects are included.

### 5.2. DefaultConfigurationCustomizer

In Boot 3.3, you can define a Spring `DefaultConfigurationCustomizer` bean. Boot invokes this callback before building the jOOQ `Configuration` bean. This is how to add `Settings`/listeners without replacing the entire `DSLContext`:

```java
@Bean
DefaultConfigurationCustomizer customizer() {
    return configuration ->
        configuration.settings().setRenderFormatted(true);
}
```

This snippet belongs inside a `@Configuration` class; the full file is in the project section. `renderFormatted` affects **how SQL is formatted for reading/logging/debugging**; it does not make SQL safer or replace bind variables.

### 5.3. Do Not Manually Construct Another DSLContext When Unnecessary

If you call:

```java
DSLContext another = DSL.using(SQLDialect.H2);
```

on its own, that context has a dialect but **lacks the DataSource/ConnectionProvider needed to execute queries**. It remains useful for pure SQL rendering, yet it is not equivalent to the Boot bean wired to H2. When testing SQL integration, inject the Spring-provided `DSLContext`.

Manually defining an `org.jooq.Configuration` or `DSLContext` bean can override auto-configuration; only do so when you need full ownership over connections, dialect, transaction provider, or listeners. Tests should then verify that the actual bean is used after customization.

## 6. Sample Project Structure

This hands-on project uses Spring Boot 3.3.5, Java 17, and H2; the SQL table is created by a script in **test resources**. You do not need to generate sources from the schema via the jOOQ code generator, allowing you to learn `@JooqTest` immediately. In production, jOOQ **code generation** is highly worthwhile because it generates typed Tables/Fields matching the real schema; section 17 explains more.

```text
jooq-slice-example/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/jooq/
│   ├── JooqLearningApplication.java
│   ├── BookSql.java
│   ├── BookRow.java
│   ├── BookQueries.java
│   └── JooqConfig.java
├── src/test/java/com/example/jooq/
│   └── BookQueriesJooqTest.java
└── src/test/resources/
    └── jooq-schema.sql
```

### 6.1. settings.gradle

```groovy
rootProject.name = 'jooq-slice-example'
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jooq'

    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-jooq` brings in jOOQ, Spring JDBC/transactions, and the needed auto-configurations. `spring-boot-starter-test` brings JUnit Jupiter and Spring Boot Test. `h2` is only on the test runtime classpath in this example, ensuring tests have an embedded database without starting an external DB.

**To run `bootRun` outside tests**, you must configure a separate DataSource/runtime DB because H2 here is only a test runtime dependency. This lesson intentionally focuses on `gradle test` and does not set up a production datasource.

### 6.3. Application Root

Create `src/main/java/com/example/jooq/JooqLearningApplication.java`:

```java
package com.example.jooq;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JooqLearningApplication {

    public static void main(String[] args) {
        SpringApplication.run(JooqLearningApplication.class, args);
    }
}
```

This class lives in the parent package of the components/tests, helping Spring locate the primary configuration. `@JooqTest` only loads the beans and config permitted by the slice, rather than auto-loading every REST/service bean just because `@SpringBootApplication` is present.

## 7. Dedicated SQL Table Created for Testing

Create `src/test/resources/jooq-schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS catalog_books (
    id BIGINT NOT NULL PRIMARY KEY,
    isbn VARCHAR(32) NOT NULL UNIQUE,
    title VARCHAR(160) NOT NULL,
    price_cents INTEGER NOT NULL
        CHECK (price_cents >= 0),
    active BOOLEAN NOT NULL
);
```

We intentionally use **test-supplied** IDs to keep assertions clear and avoid depending on identity/sequence behavior. `price_cents` is an integer in minor currency units—never use `double` for money. Unique ISBN and non-negative price CHECK constraints allow meaningful database error testing.

The schema is loaded via Spring Test `@Sql` with `ExecutionPhase.BEFORE_TEST_CLASS` (supported in Spring Framework 6.1/Boot 3.3):

```java
@Sql(
    scripts = "/jooq-schema.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS)
```

The script executes **before the test methods**, rather than running inside every test transaction to recreate the table repeatedly. We name it `jooq-schema.sql` instead of the default `schema.sql` to avoid Spring Boot's basic SQL initializer running the script automatically before `@Sql` executes. If a project uses Flyway/Liquibase, let the migration tool prepare the schema rather than mixing multiple DDL mechanisms.

**Important:** H2 DDL and transaction semantics differ from PostgreSQL; do not place CREATE/DROP TABLE inside individual test methods expecting DDL to always roll back. Tests modify **data rows** inside transactions, while the schema is prepared before the class runs.

## 8. Declaring Typed Table and Fields Without Code Generation

Create `src/main/java/com/example/jooq/BookSql.java`:

```java
package com.example.jooq;

import org.jooq.Field;
import org.jooq.Table;
import org.jooq.impl.DSL;
import org.jooq.impl.SQLDataType;

public final class BookSql {

    public static final Table<?> BOOKS =
            DSL.table(DSL.unquotedName("catalog_books"));

    public static final Field<Long> ID =
            DSL.field(DSL.unquotedName("id"), SQLDataType.BIGINT);

    public static final Field<String> ISBN =
            DSL.field(DSL.unquotedName("isbn"),
                    SQLDataType.VARCHAR(32));

    public static final Field<String> TITLE =
            DSL.field(DSL.unquotedName("title"),
                    SQLDataType.VARCHAR(160));

    public static final Field<Integer> PRICE_CENTS =
            DSL.field(DSL.unquotedName("price_cents"),
                    SQLDataType.INTEGER);

    public static final Field<Boolean> ACTIVE =
            DSL.field(DSL.unquotedName("active"),
                    SQLDataType.BOOLEAN);

    private BookSql() {
    }
}
```

**Why use `DSL.unquotedName`?** H2 typically stores identifiers created with unquoted DDL using case-folding rules. jOOQ by default may quote identifiers, turning `"catalog_books"` into a case-sensitive name. Using `unquotedName` for test tables and columns ensures SQL names match the `CREATE TABLE catalog_books` DDL. When moving to production with generated jOOQ types, use the names emitted by the code generator rather than typing literals.

**Why use typed Fields?** `Field<Integer> PRICE_CENTS` enables `eq(int)`, `add(int)`, and proper type binding. If you only use untyped `DSL.field("price_cents")`, code loses type-checking benefits and risks cast/mapping errors.

**Limitation of the manual approach:** if the schema renames a field or changes a type, these constants are not regenerated automatically, so errors may only surface at test runtime. Production systems usually run jOOQ codegen from schema/migrations to produce synchronized Java tables and fields.

## 9. DTO for Query Results

Create `src/main/java/com/example/jooq/BookRow.java`:

```java
package com.example.jooq;

public record BookRow(
        long id,
        String isbn,
        String title,
        int priceCents,
        boolean active
) {
}
```

This is a Java 17 **read/write data object**, not a JPA `@Entity`. It has no persistence context or dirty checking. When `BookQueries` reads SQL, it creates a new `BookRow`; mutating or copying a record does not automatically emit an UPDATE. To change data, you must run an intentional SQL UPDATE statement.

## 10. Real Query Class Using Spring's DSLContext

Create `src/main/java/com/example/jooq/BookQueries.java`:

```java
package com.example.jooq;

import java.util.List;
import java.util.Optional;

import org.jooq.DSLContext;
import org.jooq.Record;
import org.springframework.stereotype.Repository;

import static com.example.jooq.BookSql.ACTIVE;
import static com.example.jooq.BookSql.BOOKS;
import static com.example.jooq.BookSql.ID;
import static com.example.jooq.BookSql.ISBN;
import static com.example.jooq.BookSql.PRICE_CENTS;
import static com.example.jooq.BookSql.TITLE;

@Repository
public class BookQueries {

    private final DSLContext dsl;

    public BookQueries(DSLContext dsl) {
        this.dsl = dsl;
    }

    public int insert(BookRow book) {
        return dsl.insertInto(
                        BOOKS, ID, ISBN, TITLE, PRICE_CENTS, ACTIVE)
                .values(
                        book.id(), book.isbn(), book.title(),
                        book.priceCents(), book.active())
                .execute();
    }

    public Optional<BookRow> findById(long id) {
        return dsl.select(
                        ID, ISBN, TITLE, PRICE_CENTS, ACTIVE)
                .from(BOOKS)
                .where(ID.eq(id))
                .fetchOptional(BookQueries::toBookRow);
    }

    public Optional<BookRow> findByIsbn(String isbn) {
        return dsl.select(
                        ID, ISBN, TITLE, PRICE_CENTS, ACTIVE)
                .from(BOOKS)
                .where(ISBN.eq(isbn))
                .fetchOptional(BookQueries::toBookRow);
    }

    public List<BookRow> findActiveByTitlePrefix(String prefix) {
        return dsl.select(
                        ID, ISBN, TITLE, PRICE_CENTS, ACTIVE)
                .from(BOOKS)
                .where(ACTIVE.isTrue())
                .and(TITLE.like(prefix + "%"))
                .orderBy(ID.asc())
                .fetch(BookQueries::toBookRow);
    }

    public int rename(long id, String newTitle) {
        return dsl.update(BOOKS)
                .set(TITLE, newTitle)
                .where(ID.eq(id))
                .execute();
    }

    public int addPriceCents(long id, int delta) {
        return dsl.update(BOOKS)
                .set(PRICE_CENTS, PRICE_CENTS.add(delta))
                .where(ID.eq(id))
                .execute();
    }

    public int deactivate(long id) {
        return dsl.update(BOOKS)
                .set(ACTIVE, false)
                .where(ID.eq(id))
                .execute();
    }

    public int deleteById(long id) {
        return dsl.deleteFrom(BOOKS)
                .where(ID.eq(id))
                .execute();
    }

    public int countActive() {
        return dsl.fetchCount(BOOKS, ACTIVE.isTrue());
    }

    private static BookRow toBookRow(Record record) {
        return new BookRow(
                record.get(ID),
                record.get(ISBN),
                record.get(TITLE),
                record.get(PRICE_CENTS),
                record.get(ACTIVE));
    }
}
```

### 10.1. Parameterized Queries with Bind Values

`ISBN.eq(isbn)` does not concatenate user input directly into SQL text. jOOQ generates SQL with a `?` bind parameter (when using prepared statements/default settings) and binds the value separately. This prevents SQL injection at the **value** position of expressions and lets the JDBC driver handle types.

**However:** if you pass raw client-supplied SQL into `DSL.field(String)`, untrusted strings into `DSL.sql(String)`, or concatenate `ORDER BY` into plain SQL, jOOQ cannot automatically keep it safe. Dynamic identifiers must come from a trusted allowlist or table metadata, never freely from the client.

### 10.2. Wildcard Issues When Using LIKE

`TITLE.like(prefix + "%")` interprets `%` and `_` according to SQL LIKE syntax. The demo only passes a static prefix `Spring`. In a real API with user input, if you want a **literal prefix**, escape wildcard characters per dialect and specify `ESCAPE` semantics, or choose a different query. Bind parameters prevent SQL injection, yet they **do not turn LIKE wildcards into literals**.

### 10.3. Mapping a jOOQ Record to a Java Record

`Record.get(Field<T>)` returns the Java type matching the Field declaration. `toBookRow` produces a DTO, not a managed entity. If a database column is nullable while the Java record uses primitive `int`/`boolean`, unboxing null throws an error; the demo DDL declares `NOT NULL` so these fields are safe. In real systems, keep the schema and Java nullability contracts aligned.

### 10.4. Checking Affected Row Counts

`insert(...).execute()` typically returns the affected row count (`1` for a single insert in the demo); `rename(...)`, `addPriceCents(...)`, `deactivate(...)`, and `deleteById(...)` return `1` when one row matches and `0` when the primary key does not match. Tests should assert affected row counts, **not merely** check that the query threw no exception.

## 11. Configuring the jOOQ Customizer in the Application

Create `src/main/java/com/example/jooq/JooqConfig.java`:

```java
package com.example.jooq;

import org.springframework.boot.autoconfigure.jooq.DefaultConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class JooqConfig {

    @Bean
    DefaultConfigurationCustomizer jooqCustomizer() {
        return configuration ->
                configuration.settings()
                        .setRenderFormatted(true);
    }
}
```

Spring Boot 3.3's `DefaultConfigurationCustomizer` is applied during jOOQ auto-configuration. The test will assert:

```java
assertEquals(Boolean.TRUE,
        dsl.configuration().settings().isRenderFormatted());
```

This is an assertion on the **configuration of the injected DSLContext**, not on a freshly created `Settings` object in the test. Use `Boolean.TRUE.equals(...)` or `assertEquals(Boolean.TRUE, ...)` because the getter returns `Boolean`.

**Do not confuse:**
- `spring.jooq.sql-dialect` configures how jOOQ renders SQL for the DB.
- `DefaultConfigurationCustomizer` customizes `org.jooq.Configuration` (e.g., Settings, listener providers).
- `@Import(JooqConfig.class)` in the test slice makes the customizer bean available.
- `@Import(BookQueries.class)` makes the DAO/repository under test available even though the slice does not scan regular components.

### Should You Tune renderQuotedNames in a Real Project?

jOOQ provides `RenderQuotedNames` and `RenderNameCase` for identifiers. Setting `RenderQuotedNames.NEVER` can strip case sensitivity or cause reserved words to break. The demo uses `DSL.unquotedName` for these specific names and customizes only **renderFormatted**, avoiding silent changes to global quoting rules.

## 12. Complete @JooqTest Suite

Create `src/test/java/com/example/jooq/BookQueriesJooqTest.java`:

```java
package com.example.jooq;

import java.util.List;

import javax.sql.DataSource;

import org.jooq.DSLContext;
import org.jooq.SQLDialect;
import org.jooq.conf.ParamType;
import org.jooq.exception.DataAccessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jooq.JooqTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static com.example.jooq.BookSql.BOOKS;
import static com.example.jooq.BookSql.ID;
import static com.example.jooq.BookSql.ISBN;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JooqTest(properties = "spring.jooq.sql-dialect=H2")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
@Import({BookQueries.class, JooqConfig.class})
@Sql(
        scripts = "/jooq-schema.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS)
class BookQueriesJooqTest {

    @Autowired
    DSLContext dsl;

    @Autowired
    DataSource dataSource;

    @Autowired
    BookQueries books;

    @BeforeEach
    void cleanRowsWithinTransaction() {
        dsl.deleteFrom(BOOKS).execute();
    }

    private static BookRow book(
            long id, String isbn, String title,
            int priceCents, boolean active) {
        return new BookRow(
                id, isbn, title, priceCents, active);
    }

    @Test
    void createsDslContextWithH2DialectAndCustomizer() {
        assertNotNull(dsl);
        assertNotNull(dataSource);
        assertEquals(SQLDialect.H2, dsl.configuration().dialect());
        assertEquals(Boolean.TRUE,
                dsl.configuration().settings().isRenderFormatted());
    }

    @Test
    void jooqTestRunsInsideSpringTransaction() {
        assertTrue(
                TransactionSynchronizationManager
                        .isActualTransactionActive());
    }

    @Test
    void insertsAndFindsByPrimaryKey() {
        BookRow input =
                book(101L, "ISBN-101", "Spring Basics", 2500, true);

        assertEquals(1, books.insert(input));

        BookRow loaded = books.findById(101L).orElseThrow();
        assertEquals(input, loaded);
    }

    @Test
    void findsByIsbnAndReturnsEmptyForMissing() {
        BookRow input =
                book(102L, "ISBN-102", "SQL Queries", 3100, true);
        books.insert(input);

        assertEquals(input,
                books.findByIsbn("ISBN-102").orElseThrow());

        assertTrue(books.findByIsbn("ISBN-NOT-FOUND").isEmpty());
        assertTrue(books.findById(999999L).isEmpty());
    }

    @Test
    void filtersActiveBooksAndSortsById() {
        BookRow a = book(
                202L, "ISBN-202", "Spring Data", 2900, true);
        BookRow b = book(
                201L, "ISBN-201", "Spring Testing", 3400, true);
        BookRow inactive = book(
                203L, "ISBN-203", "Spring Archive", 1000, false);
        BookRow other = book(
                204L, "ISBN-204", "Java Basics", 2000, true);

        books.insert(a);
        books.insert(b);
        books.insert(inactive);
        books.insert(other);

        List<BookRow> result =
                books.findActiveByTitlePrefix("Spring");

        assertEquals(List.of(b, a), result);
    }

    @Test
    void updatesTitleAndReportsAffectedRow() {
        books.insert(book(
                301L, "ISBN-301", "Before", 1000, true));

        assertEquals(1, books.rename(301L, "After"));
        assertEquals("After",
                books.findById(301L)
                        .orElseThrow().title());
    }

    @Test
    void addsPriceUsingTypedSqlExpression() {
        books.insert(book(
                302L, "ISBN-302", "Price", 5000, true));

        assertEquals(1, books.addPriceCents(302L, 250));
        assertEquals(5250,
                books.findById(302L)
                        .orElseThrow().priceCents());
    }

    @Test
    void updateOfMissingRowChangesNothing() {
        assertEquals(0, books.rename(999L, "Absent"));
        assertEquals(0, books.addPriceCents(999L, 50));
        assertEquals(0, books.deactivate(999L));
    }

    @Test
    void deactivatesRowAndExcludesItFromCount() {
        books.insert(book(
                401L, "ISBN-401", "Active", 4000, true));
        books.insert(book(
                402L, "ISBN-402", "Inactive", 4000, false));

        assertEquals(1, books.countActive());
        assertEquals(1, books.deactivate(401L));
        assertEquals(0, books.countActive());
        assertFalse(books.findById(401L)
                .orElseThrow().active());
    }

    @Test
    void deletesOneRowButKeepsAnother() {
        books.insert(book(
                501L, "ISBN-501", "Delete me", 1900, true));
        books.insert(book(
                502L, "ISBN-502", "Keep me", 1900, true));

        assertEquals(1, books.deleteById(501L));
        assertEquals(0, books.deleteById(501L));
        assertTrue(books.findById(501L).isEmpty());
        assertTrue(books.findById(502L).isPresent());
    }

    @Test
    void queryBindsValueRatherThanConcatenatingSql() {
        var query = dsl.select(ID)
                .from(BOOKS)
                .where(ISBN.eq("ISBN-601"));

        assertTrue(
                query.getSQL(ParamType.INDEXED).contains("?"));
        assertEquals(
                List.of("ISBN-601"), query.getBindValues());
    }

    @Test
    void jdbcAndJooqSeeSameTransactionalRows() {
        books.insert(book(
                701L, "ISBN-701", "Shared DS", 2100, true));

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        Integer count = jdbc.queryForObject(
                "select count(*) from catalog_books where isbn = ?",
                Integer.class,
                "ISBN-701");

        assertEquals(1, count);
    }

    @Test
    void duplicateIsbnIsRejectedByDatabase() {
        books.insert(book(
                801L, "ISBN-DUP", "First", 100, true));

        assertThrows(DataAccessException.class,
                () -> books.insert(book(
                        802L, "ISBN-DUP", "Second", 100, true)));
    }

    @Test
    void negativePriceIsRejectedByDatabase() {
        assertThrows(DataAccessException.class,
                () -> books.insert(book(
                        901L, "ISBN-901", "Invalid", -1, true)));
    }
}
```

**By source count, there are 14 `@Test` methods**, each with an independent goal. They are **examples designed to run** on a Boot 3.3.5/H2 project when configured with the files above; no actual Gradle execution report is attached in the article, so do not claim "14 PASS" has already occurred.

### Why @Sql BEFORE_TEST_CLASS?

`jooq-schema.sql` runs once before methods need the `catalog_books` table. There is no fixed data in the script. Each test uses `@BeforeEach` to delete rows inside the test transaction and creates its own fixtures, while the test transaction rolls back by default at completion.

`@Sql(ExecutionPhase.BEFORE_TEST_CLASS)` is a Spring TestContext 6.1 feature. If an older project uses a Spring Framework version that does not support this phase, prepare the schema via Flyway/Liquibase or lifecycle-appropriate SQL init; never copy an annotation and assume it is supported.

### Why @Import BookQueries and JooqConfig?

`@JooqTest` does not scan regular components. `@Import` adds **precisely the beans the test needs**:

- `BookQueries`: the subject under test, injected with `DSLContext`.
- `JooqConfig`: the `DefaultConfigurationCustomizer` bean to verify configuration is also active inside the test slice.

If you omit `@Import(BookQueries.class)` in a project where the slice does not pick up this bean, the test can fail with `NoSuchBeanDefinitionException`. Do not fix that by converting the whole test to `@SpringBootTest` when the scope only requires jOOQ.

## 13. Analyzing Each Test Group

### 13.1. Context, Dialect, and Customizer

`createsDslContextWithH2DialectAndCustomizer` asserts directly:

- `DSLContext` is provided by Spring Boot.
- `DataSource` is injected.
- Dialect is `SQLDialect.H2`.
- `isRenderFormatted()` equals `Boolean.TRUE`.

A test asserting only `dsl != null` does not prove configuration is right. If `JooqConfig` is not imported, the formatting assertion can fail or differ from the expected value even while SQL queries continue running.

**Do not verify formatted SQL details by comparing an entire multiline string** unless a specific contract requires it: whitespace and keyword styling change between jOOQ versions. Asserting on `Settings` is stable and directly reflects the configured property.

### 13.2. SELECT/INSERT and Mapping

`insertsAndFindsByPrimaryKey` inserts a `BookRow` and reads it back. Asserting `record.equals` checks `id`, `isbn`, `title`, `priceCents`, and `active`, rather than just checking a count.

`findsByIsbnAndReturnsEmptyForMissing` checks `Optional<BookRow>` with one existing key and two missing keys. Using jOOQ's `fetchOptional` turns an absent row into `Optional.empty()`.

**Do not equate:** `fetchOne()` can return null, `fetchOptional()` returns Optional, and `fetchSingle()` enforces strictly one row. Pick the right API and test 0/multiple-row cases per query contract.

### 13.3. Filter/ORDER BY

`filtersActiveBooksAndSortsById` inserts 4 records in non-ascending ID order; only 2 rows have `active=true` and titles starting with `Spring`. The query includes `orderBy(ID.asc())`, so the expected list puts ID 201 before 202. Without `ORDER BY`, SQL result ordering **is not guaranteed**, even if H2 happens to return rows by primary key.

### 13.4. UPDATE and Deleted Row Counts

`updatesTitleAndReportsAffectedRow`, `addsPriceUsingTypedSqlExpression`, and `deletesOneRowButKeepsAnother` assert the returned affected row count. The update query:

```java
dsl.update(BOOKS)
   .set(PRICE_CENTS, PRICE_CENTS.add(delta))
   .where(ID.eq(id))
   .execute();
```

performs addition in the database rather than fetching the record to Java, adding, and writing back; this makes sense for single-statement updates. However, it **does not replace** concurrency controls or overflow checks if the domain allows arbitrary deltas.

With a missing ID, SQL UPDATE/DELETE affects 0 rows, and the test verifies this case. If a business API needs to return 404, the service/controller layer must translate 0 affected rows into an appropriate error; the DAO does not emit HTTP statuses.

### 13.5. Bind Parameters

`queryBindsValueRatherThanConcatenatingSql` builds a query without executing it yet and inspects `getSQL(ParamType.INDEXED)` and `getBindValues()`:

- Rendered SQL contains the `?` placeholder.
- The bind values list contains `"ISBN-601"`.

This is a **check on query construction in indexed binding mode**, not a comprehensive penetration test. If `Settings` changes `StatementType.STATIC_STATEMENT`, execution behavior differs and needs separate tests. Never concatenate raw input into `DSL.sql(...)` or dynamic identifiers just because a `?` test passed.

### 13.6. Two APIs Sharing the Same DataSource and Transaction

`jdbcAndJooqSeeSameTransactionalRows` inserts via jOOQ and then selects via `new JdbcTemplate(dataSource)`. Spring JDBC and Spring Boot jOOQ auto-configuration are designed to share the same Spring-managed DataSource and transaction. The test proves both APIs see the same row **within the current transaction**.

It **does not prove commit**. Another JDBC connection in a separate transaction might not see the uncommitted insert depending on isolation level. `@JooqTest` rolls back after each test, so data does not persist outside the test unless transaction configuration is altered.

### 13.7. Database Constraint Failures

`duplicateIsbnIsRejectedByDatabase` and `negativePriceIsRejectedByDatabase` intentionally trigger H2 unique/check constraint errors. jOOQ wraps the error in `org.jooq.exception.DataAccessException`, so tests check the exception at the jOOQ boundary.

After a SQL constraint violation, a transaction may enter a state requiring rollback; **do not keep executing queries as if the transaction were guaranteed healthy**. Isolating each negative case into its own test lets transaction rollback clean up. On production databases other than H2, inspect SQLState/root cause when you need to distinguish unique vs. check violations accurately.

## 14. Transaction Semantics of @JooqTest

In Spring Boot 3.3, `@JooqTest` is annotated with `@Transactional` and test-managed transactions roll back by default. This provides convenient isolation:

```text
JUnit test 1
    BEGIN (Spring TestContext)
    INSERT id=101
    SELECT id=101  -> sees row in same transaction
    ROLLBACK

JUnit test 2
    BEGIN
    INSERT id=101  -> typically does not conflict with rolled-back test 1
    ROLLBACK
```

`@BeforeEach` also runs inside the framework-managed test transaction per the standard lifecycle. It deletes rows within the test context, though it will not make table DDL exist unless the schema script has already run. Hence we prepare the schema before the test class.

### jOOQ Flush and Commit Differ from JPA

jOOQ executes statements immediately when `execute()`/`fetch()` is called—there is no JPA persistence context/dirty checking needing `EntityManager.flush()`. Still, a query executed **inside a transaction** is not yet committed. That is why seeing a row in a test does not mean the data persists after the test.

**Do not confuse `DSLContext.transaction(...)` with Spring TestContext transactions:**
- A Spring-managed transaction already exists inside `@JooqTest`.
- jOOQ has its own transaction API via `Configuration` and `TransactionProvider`; understand when to use `dsl.transaction(configuration -> ...)` and how it integrates with Spring.
- Avoid manually opening transactions or nested transactions in a simple CRUD test; if you need to test commits or savepoints, design dedicated tests and verify provider/database semantics.

### When to Disable Rollback or Transactions?

You can use Spring Test `@Rollback(false)` or `@Commit` in a test when justified, or `@Transactional(propagation = NOT_SUPPORTED)` to disable the test-managed transaction in special scenarios. Doing so allows test data to persist after the method and requires explicit cleanup. For the H2 demo, **keeping the default rollback** is safest and fastest.

**Never run `@Rollback(false)` or `Replace.NONE` against a production database** while learning unless you are certain the database is isolated.

## 15. Advanced DSLContext Configuration

### 15.1. Listener Lifecycle

jOOQ supports `ExecuteListener` and `ExecuteListenerProvider` to time queries, log SQL, observe errors, and count statements. Spring Boot can register listener providers in the auto-configured `Configuration`.

Illustrative snippet, not a file in the demo:

```java
@Bean
DefaultConfigurationCustomizer customizer() {
    return config -> {
        config.settings().setRenderFormatted(true);
    };
}
```

If listeners are needed, register a bean/provider with the appropriate lifecycle and test that it observes expected statements. **Do not use SQL logs as the sole proof of query results**; log formats can vary across versions. When logging bind values, mask sensitive data.

### 15.2. Modifying Settings via Customizer vs. Defining a Separate Bean

A `DefaultConfigurationCustomizer` lets you adjust the `DefaultConfiguration` bean Boot creates. If you declare your own `org.jooq.Configuration` bean, Boot may back off its corresponding auto-configuration; in that case, you become responsible for properly wiring `ConnectionProvider`, `SQLDialect`, and transaction integration.

In this exercise, no custom `DSLContext` bean is needed. The best way to test configuration is to inject the bean actually used by repositories/controllers and assert key properties.

### 15.3. Settings Control SQL Rendering, Not SQL Injection Policy

Settings such as `renderFormatted`, `renderQuotedNames`, `renderNameCase`, `statementType`, and `paramType` have distinct effects. Only alter `renderQuotedNames` or `statementType` when you understand the outcome and have tests guarding it. Making SQL look "pretty" must never silently change identifier casing or convert binds into inline literals unexpectedly.

### 15.4. DefaultConfigurationCustomizer and Bean Initialization Order

Customizers run while Boot builds the jOOQ configuration, before `DSLContext` is injected into repositories. If inside a test you call:

```java
dsl.configuration().settings().setRenderFormatted(true);
```

you are **mutating runtime config inside the test**, not verifying registration from production config. The demo avoids that and asserts that the customizer ran naturally via `@Import(JooqConfig.class)`.

### 15.5. @TestConfiguration Instead of Importing Production Config

If you want a customizer that **exists only in tests**, you can define a nested static `@TestConfiguration` class with a `@Bean DefaultConfigurationCustomizer` and `@Import` it. This works well for forcing test schema mappings or test listeners, though it differs from verifying your actual production configuration. This lesson imports real `JooqConfig` to verify the configuration actually defined.

## 16. Database Initialization: schema.sql, @Sql, Flyway, and Liquibase

Multiple mechanisms exist to prepare a database before tests, so **choose one intentionally**.

| Mechanism | Best Used When | Notes |
| --- | --- | --- |
| `@Sql("/jooq-schema.sql")` | Small demo/test tables | Choose execution phase and transaction mode for DDL |
| `schema.sql` / `spring.sql.init.mode` | Simple projects wanting Boot SQL init on context startup | Be careful not to duplicate migrations |
| Flyway/Liquibase | Projects with versioned schema migrations | Run real migrations to prevent drift from production |
| Testcontainers + migrations | SQL dialect/constraints/locking matter | Requires Docker/container test environment |
| Creating tables via `DSLContext` | DDL itself is the test subject in an isolated sandbox | Avoid running arbitrary DDL inside test transactions |

### Why Use @Sql BEFORE_TEST_CLASS in This Lesson?

- The test class needs only a single table and has no complex migrations.
- `jooq-schema.sql` resides on the test classpath and runs before test methods.
- Every test creates its own data without depending on `data.sql` or test ordering.
- DML rolls back; DDL does not need to roll back per test.

If another test class shares the same database/schema inside the Spring context cache, table/schema naming and parallel execution must be managed explicitly. `CREATE TABLE IF NOT EXISTS` in the demo makes the script safer if the table already exists; in production migration environments, never use `IF NOT EXISTS` to mask an out-of-sync schema version.

### H2 DDL Differs from Other Databases

H2 accepts `BOOLEAN` and `CHECK(price_cents >= 0)` in the demo. PostgreSQL supports similar syntax, yet enums, generated identities, JSON, arrays, operators, and transaction semantics still differ. Passing H2 tests does not confirm all application SQL runs cleanly on the production database.

## 17. Code Generation and Typed jOOQ Schemas

One of jOOQ's core strengths is its **code generator**, which reads the database schema and generates Java classes like `Tables.BOOKS` or `BOOKS.ISBN`. The demo uses manual `BookSql` so learners do not have to configure the generator right away, but in real applications codegen helps you:

- Catch schema changes and renamed columns at compile time (once code is regenerated).
- Gain type metadata and generated keys/records that make queries harder to mistype.
- Avoid quoting/case/naming bugs from string constants.
- Join tables, fetch records, and map fields easily.

A typical pipeline:

```text
Flyway/Liquibase migrations
    ↓
Temporary schema / database for codegen
    ↓
jOOQ code generator
    ↓
Generated Tables, Fields, Records
    ↓
BookQueries using typed generated API
    ↓
@JooqTest + matching database schema
```

Keep the test schema version synchronized with the generated code version. If generated classes reference a column missing from test H2, queries will fail at runtime despite compiling cleanly. Never validate generated DSL against a stale schema and assume type safety guarantees runtime compatibility.

**jOOQ edition:** dialect and codegen support for certain databases and features may depend on the open-source vs. commercial edition. Use a dialect and license compatible with your project; H2 is supported in the open-source edition.

## 18. Choosing Meaningful Assertions

A good SQL test usually includes:

1. **Arrange:** insert data through the right test DataSource.
2. **Act:** call the exact query under test rather than duplicating the same implementation inside the test to self-verify.
3. **Assert:** verify values, row counts, ordering, data types, and error paths.
4. **Isolation:** never depend on leftover data from another test.
5. **Dialect:** run against the DB/dialect appropriate for what you are proving.

Sample assertions:

```java
assertEquals(1, books.insert(book));
assertEquals(book, books.findById(book.id()).orElseThrow());
assertEquals(0, books.rename(999L, "missing"));
assertTrue(books.findByIsbn("unknown").isEmpty());
```

This snippet belongs inside a test class with `books` and `book` variables in scope. Asserting only "does not throw" is too weak: an UPDATE with a broken WHERE clause can touch 0 rows without throwing any error.

### Asserting Rendered SQL vs. Asserting SQL Execution

`getSQL(ParamType.INDEXED)` and `getBindValues()` inspect query construction. They help prove client input is properly bound, yet **they do not prove the table/column exists in the database or that the query returns the right rows**. Therefore, execution tests on H2 for INSERT/SELECT/UPDATE/DELETE remain essential.

Conversely, a SELECT execution test can pass falsely if the author seeded fixtures poorly so the WHERE clause is barely exercised. Pick discriminating data: active/inactive, matching/non-matching prefixes, IDs out of insertion order. That is why `filtersActiveBooksAndSortsById` seeds four distinct records.

## 19. When Are Testcontainers and @DynamicPropertySource Needed?

When the SQL domain depends on Postgres/MySQL features, H2 should only serve as a fast pre-filter. Approach:

- Start the matching database container.
- Run the application's real migrations.
- Pass the JDBC URL, username, and password into the Spring context via `@DynamicPropertySource` or `@ServiceConnection` as appropriate.
- Use `@JooqTest` with `@AutoConfigureTestDatabase(replace = NONE)`.
- Ensure `SQLDialect` is detected properly by Boot or configured accurately.
- Clean up rows/schemas per transaction and container lifecycle; never point at production.

Strategy snippet:

```java
@JooqTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgresJooqTest {
    @Autowired DSLContext dsl;
}
```

Without Testcontainers setup, this is **not a standalone runnable project**. When creating the real test, add the dependencies, container annotations/lifecycle, driver, and dynamic properties. If the database driver is present and Boot auto-detects the dialect, you do not necessarily need to force the property with a hardcoded value.

**A limitation of `@JooqTest`:** regular components are not scanned. If a production DAO depends on a query listener, custom converter, or service bean not auto-loaded by the slice, import the right collaborators or use a broader integration test to verify the interaction.

## 20. Preventing SQL Injection When Configuring DSLContext

The jOOQ fluent DSL uses `Field<T>` and bind values to avoid string-concatenation injection for **values**. Still, distinguish these cases:

### 20.1. User-Provided Values

Safer:

```java
dsl.select(ISBN)
   .from(BOOKS)
   .where(ISBN.eq(userInput));
```

The `userInput` value is bound by jOOQ according to the query-building configuration.

Unsafe when manually concatenating raw SQL:

```java
dsl.resultQuery(
    "select isbn from catalog_books where isbn = '"
    + userInput + "'");
```

This is an **anti-example**. `resultQuery(String)` accepts plain SQL; if the string includes user-controlled input, SQL injection becomes possible. If raw SQL is necessary, use placeholders and bind values:

```java
dsl.resultQuery(
    "select isbn from catalog_books where isbn = ?",
    userInput);
```

### 20.2. Dynamic Table/Column Names

SQL parameter placeholders **cannot substitute for table or column names**. If an API accepts a sort field from a query parameter, use an allowlist mapping a small set of public names such as `"title"` or `"price"` to defined typed `Field<?>` constants. Never pass client-supplied column names into `DSL.field(String)` or plain SQL templates without validation.

### 20.3. LIKE Patterns

Bind values do not remove SQL LIKE wildcard semantics. User input containing `%` or `_` can broaden the filter. When the contract demands a literal prefix, escape wildcards properly and write test cases with special characters.

### 20.4. Do Not Log Sensitive Data

jOOQ query logging and `ExecuteListener` can access SQL and bind values. Never enable logging of raw credentials, tokens, PII, or sensitive data into CI logs. When debugging, use redaction and query metrics that omit personal data.

## 21. Common Errors and How to Fix Them

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| `No qualifying bean of type DSLContext` | Missing starter-jooq/DataSource or context is not a jOOQ slice | Check dependencies, `@JooqTest`, JDBC driver |
| `No qualifying bean of type BookQueries` | `@JooqTest` does not scan regular `@Repository` | `@Import(BookQueries.class)` |
| `@JooqTest` hits external DB | Keeps configured DataSource by default | Use `@AutoConfigureTestDatabase(replace=ANY)` when H2 is desired |
| Wrong dialect | Wrong `spring.jooq.sql-dialect` or undetected | Assert `dsl.configuration().dialect()` |
| Customizer not running in slice | `JooqConfig` not imported | `@Import(JooqConfig.class)` or explicit test config |
| `Table not found` | Schema not created or wrong `@Sql` file path | Check `jooq-schema.sql` and `@Sql` execution phase |
| `Column not found` | Case/quoted identifier mismatch or schema mismatch | `DSL.unquotedName`/generated fields, inspect DDL |
| `NoSuchBeanDefinitionException` for service | Slice intentionally excludes unrelated beans | Import/mock needed dependency or use full test |
| `DataAccessException` on INSERT | Unique/CHECK/FK constraint or SQL error | Inspect SQLState/root cause; isolate exception tests |
| DML test leaves rows behind | Rollback disabled or connection outside transaction | Keep default `@Transactional` and Spring-aware DataSource |
| Passes alone, fails in suite | Shared schema/static data/context cache | Isolate fixtures, clean up within transactions |
| Query returns wrong order | Missing `ORDER BY` | Explicit `orderBy(...)` |
| LIKE matches too broadly | Input contains `%`/`_` | Escape wildcards per contract |
| `?` test passes yet SQL remains vulnerable | Plain SQL elsewhere concatenates raw input | Guard every query construction path |
| H2 PASS but PostgreSQL FAIL | Different dialect/SQL/schema | Testcontainers database of matching type |
| Test reports wrong SQL formatting | Different Settings or unimported config | Assert `dsl.configuration().settings()` |
| Cannot find `@SpringBootConfiguration` | Test is outside package hierarchy | Place test under main package or specify config explicitly |
| DDL rollback behaves unexpectedly | H2 auto-commits DDL | Prepare schema before test methods |
| Cannot determine suitable driver | H2 missing from test runtime or wrong DataSource | Check dependency and connection settings |
| Java fails to compile on `@JooqTest` package | Boot 4 import used in Boot 3 | Use `org.springframework.boot.test.autoconfigure.jooq.JooqTest` |

### Systematic Diagnosis Order

1. Read the root cause in the test report, not just `Failed to load ApplicationContext`.
2. Confirm Boot/jOOQ versions, test JDK, and H2 driver.
3. Assert `dsl != null`, `dataSource != null`, SQL dialect, and customizer.
4. Confirm `jooq-schema.sql` executed before the tests.
5. Check that `BOOKS`/`ID`/`ISBN` Field metadata matches the DDL.
6. Insert a single fixture and SELECT it back with jOOQ.
7. Verify transaction is active and rollback behavior works.
8. If an error occurs only on the production DB, reproduce with the real dialect via Testcontainers.
9. Eliminate dependencies on test ordering or shared mutable state.
10. Inspect SQL/binds safely when needed, never altering expected values to hide a bug.

## 22. Running Tests and Expected Results

The sample project contains **14 `@Test` methods** in `BookQueriesJooqTest`.

Run with the Gradle Wrapper (if the project includes a wrapper):

```bash
./gradlew test --tests 'com.example.jooq.BookQueriesJooqTest'
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If you have not generated a Gradle Wrapper yet and have a compatible Gradle installed:

```bash
gradle test
```

There is no fixed business stdout: JUnit and Gradle output test reports depending on the environment. Open:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

to inspect the exact count of executed tests, PASS/FAIL/SKIPPED counts, and stack traces. Mentions of "14 tests" in this article refer strictly to **the number of methods declared in source**, not an observed run in a specific Gradle environment.

### Practical Outcomes to Achieve

- A Spring-managed `DSLContext` bound to the H2 test DataSource.
- `SQLDialect.H2` confirmed.
- `DefaultConfigurationCustomizer` applying `renderFormatted=true`.
- `BookQueries` loaded into `@JooqTest` via `@Import`.
- CRUD queries, mapping, filtered ordering, and bind parameters running accurately.
- Unique/CHECK constraint errors caught at the jOOQ boundary.
- Active test transactions and default rollback protecting fixture isolation.

If an assertion fails, never blindly adjust the expected value to make it pass. Distinguish DataSource/dialect config errors, DDL/schema errors, DAO query errors, and test fixture errors.

## 23. Pre-Merge QA Checklist

- [ ] Is the test using `@JooqTest` with proper scope instead of booting the full app when only jOOQ is needed?
- [ ] Are Spring Boot and jOOQ versions pinned in dependencies/BOM?
- [ ] Is `DSLContext` obtained as a Spring bean rather than an unconnected manually created `DSLContext`?
- [ ] Is the test DataSource verified so it cannot touch the production DB?
- [ ] If an embedded DB is wanted, is `@AutoConfigureTestDatabase` declared explicitly?
- [ ] Does `SQLDialect` match the actual DB rather than being set arbitrarily?
- [ ] Are required `DefaultConfigurationCustomizer` beans or listeners imported?
- [ ] Are DAOs/repositories under test added via `@Import` if the slice does not scan them?
- [ ] Is the schema created via `@Sql`/migrations at the proper lifecycle phase?
- [ ] Do queries use typed Fields/generated jOOQ tables and bind variables for user input?
- [ ] Are there assertions on returned rows, mapping, and affected row counts?
- [ ] Is result ordering backed by `ORDER BY` when required by the contract?
- [ ] Are both positive and negative cases covered (not-found, zero affected, constraints)?
- [ ] Are constraint errors isolated into separate tests without reusing a transaction after SQL failure?
- [ ] Are default transaction rollback and visibility boundaries understood?
- [ ] Is H2 never treated as proof of production SQL dialect/locking?
- [ ] Are PostgreSQL/MySQL Testcontainers tests added when queries use vendor-specific features?
- [ ] Are SQL schema/migrations and jOOQ codegen outputs synchronized?
- [ ] Are tests independent of method ordering or shared/static fixtures?
- [ ] Was the actual test report checked rather than merely counting `@Test` in source?

## 24. Practice Exercises

1. Remove `@Import(BookQueries.class)`, run the tests, and distinguish a bean-scan error from a `DSLContext` error.
2. Remove `@Import(JooqConfig.class)` while keeping the `isRenderFormatted()` assertion; explain why the configuration test no longer verifies the customizer.
3. Remove `@AutoConfigureTestDatabase` in a project with a PostgreSQL DataSource and describe the risk of touching an external DB.
4. Intentionally misconfigure `spring.jooq.sql-dialect` (e.g., `POSTGRES` while using H2). Compare SQL rendering and errors; explain why the property does not switch the DB.
5. Change `BookSql.BOOKS` from `DSL.unquotedName` to `DSL.name` and observe case-sensitive quoted identifiers on H2.
6. In `filtersActiveBooksAndSortsById`, remove `orderBy` and explain why there is no longer an ordering contract.
7. Add a `findByPriceRange` query taking two bind values and write tests for boundary values.
8. Insert two identical ISBNs in a dedicated test and inspect the exception type and root cause from H2.
9. Test a negative price value and verify the `CHECK` constraint.
10. Inspect `getBindValues()` when input contains a single quote; explain why parameterization matters.
11. Write a `COUNT(*)` query with jOOQ and compare it against `JdbcTemplate` inside the same transaction.
12. Add an unimported `@Service` and explain why `@JooqTest` does not automatically scan it.
13. Use `@TestConfiguration` to define a test-only `DefaultConfigurationCustomizer` and examine how it differs from importing production config.
14. Create a PostgreSQL Testcontainers integration test with `Replace.NONE` to compare schema/dialect behavior against H2.
15. Use Flyway migrations to create the table, remove `@Sql`, and confirm the schema matches production.
16. Add jOOQ code generation and replace manual `BookSql` with generated Tables/Fields.
17. Run `gradle test` and confirm the executed test count from the report rather than just counting methods.
18. When enabling SQL logging, verify whether bind values containing PII/secrets are masked.

## 25. References

- [Spring Boot 3.3 — Auto-configured jOOQ Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@JooqTest`, component scan limits, `DSLContext` bean, DataSource, and default rollback.
- [Spring Boot 3.3 — SQL Databases / Using jOOQ](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html): `DSLContext`, `spring.jooq.sql-dialect`, and `DefaultConfigurationCustomizer`.
- [Spring Boot 3.3 — JooqTest Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jooq/JooqTest.html): Boot 3.x annotation APIs.
- [jOOQ 3.19 — DSLContext](https://www.jooq.org/doc/3.19/manual/sql-building/dsl-context/): `Configuration` structure and `DSLContext`.
- [jOOQ 3.19 — SQL Identifier Naming](https://www.jooq.org/doc/3.19/manual/sql-building/names/): quoting, case-sensitive identifiers, `DSL.unquotedName`.
- [jOOQ 3.19 — Custom Settings](https://www.jooq.org/doc/3.19/manual/sql-building/dsl-context/custom-settings/): `Settings` and SQL rendering configuration.
- [Spring Framework — Transactional Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback and test-managed transactions.
- [Spring Framework — Executing SQL Scripts with @Sql](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): SQL script lifecycle, execution phases, and transactions.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): `schema.sql`/`data.sql`, Flyway/Liquibase, init mode.

## 26. Conclusion

**`@JooqTest` is a test-slice tool for jOOQ, not a full application context.** It provides a Spring-managed `DSLContext` with DataSource, dialect, and transaction integration. In Boot 3.3, the existing database is used by default; **to replace it with H2, choose `@AutoConfigureTestDatabase` explicitly**. Test transactions roll back after each method by default.

To verify configuration properly, assert `dsl.configuration().dialect()` and critical `Settings`, and bring production `DefaultConfigurationCustomizer`/DAO beans into the slice via `@Import` when needed. Verify SQL behavior using discriminating fixtures, returned rows, row counts, bind values, ordering, and constraint failures. H2 is great for fast feedback loops, but whenever semantics depend on the database vendor, test further with migrations and Testcontainers on the matching database engine.