# Reading Data via JDBC to Avoid Asserting Only the ORM Cache

When testing a data layer using Spring Data JPA or Hibernate, calling a repository again right after saving an entity does not guarantee that data was written to and read back from the database. JPA manages a **persistence context** and holds managed entities in memory. Consequently, a repository read can return the exact in-memory object without re-reading the table row.

A more independent check is synchronizing ORM changes to the database via `flush()`, and then using JDBC—such as `JdbcTemplate`—to run a direct SQL `SELECT`. JDBC does not look up entities in JPA's persistence context. Query results therefore show what values the database actually returns within the current transaction.

## 1. Why Can Re-Reading via Repository Give False Confidence?

JPA maintains a persistence context scoped to an `EntityManager`. This serves as a first-level cache and the place where JPA tracks entity state. Within a persistence context, an entity with a given identifier is normally represented by a single managed instance. When the application modifies that object, JPA records the change and schedules the appropriate SQL statements.

For example, suppose a test executes:

```java
Book saved = bookRepository.save(new Book("978-0132350884", "Clean Code"));

Book found = bookRepository.findById(saved.getId()).orElseThrow();

assertThat(found.getTitle()).isEqualTo("Clean Code");
```

This assertion can succeed because `found` is the exact entity already managed in the persistence context. JPA already knows that object has title `Clean Code`; the subsequent read might not even issue a new `SELECT`. At that point, the test has only verified the in-memory object's state, not directly verified what is stored in the table.

Even when a JPQL query or repository method issues SQL, entity results are reconciled against the persistence context. If an entity with the same identity is already managed, JPA usually returns that managed instance instead of creating an independent copy. Therefore, asserting properties of an entity reloaded via ORM is not always independent proof of persisted data.

This issue is particularly relevant when testing:

- Whether an `INSERT`, `UPDATE`, or `DELETE` was actually sent to the database.
- Whether column values after writing match expectations.
- Whether database-generated columns, default values, or triggers worked properly.
- Whether the database enforced unique, foreign key, `NOT NULL`, and other data rules.

## 2. JDBC Provides a Read Path Independent of the Persistence Context

`JdbcTemplate` executes SQL through a `DataSource`. When calling `queryForObject`, `query`, or `update`, it works directly with the SQL results returned by the database. It does not ask JPA to look up entities in the persistence context and does not read from Hibernate's first-level cache.

The test flow can be structured as follows:

```text
Test
  |
  | 1. Call repository to save entity
  v
JPA / Hibernate
  |
  | 2. Track entity in persistence context
  | 3. EntityManager.flush()
  v
DataSource / JDBC connection
  |
  | 4. Send INSERT / UPDATE / DELETE to database
  v
Database
  ^
  | 5. JdbcTemplate executes direct SELECT
  |
Test receives column values or row count
```

The key point is that the two access paths have distinct responsibilities:

| Component | Role in the Test |
| --- | --- |
| Repository / JPA | Performs write operations following the entity model and ORM rules. |
| `EntityManager.flush()` | Forces pending changes in the persistence context to synchronize as SQL. |
| `JdbcTemplate` | Reads rows and columns directly via SQL, bypassing the persistence context. |
| Assertions | Compare SQL results against expected data. |

JDBC still uses Spring's connection configuration. If `JdbcTemplate` and JPA share the same `DataSource` inside a Spring-managed transaction, they typically participate in the same transaction and use the connection synchronized for that transaction. This is the desired behavior in standard tests: ORM writes and JDBC reads both see the data state within the current transaction.

## 3. Preparing an Example Entity and Repository

Suppose an application stores book information in the `books` table. We explicitly declare table and column names so SQL statements in tests align with the schema.

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "isbn", nullable = false, unique = true, length = 20)
    private String isbn;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    protected Book() {
    }

    public Book(String isbn, String title) {
        this.isbn = isbn;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
```

The repository simply extends `JpaRepository`:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
}
```

The example uses Spring Boot with JPA. `@DataJpaTest` creates a test slice for the JPA layer, configuring needed components such as repositories, `EntityManager`, and `DataSource`, and by default runs each test inside a transaction that rolls back when the test finishes.

## 4. Verifying Data Rows with `JdbcTemplate`

We inject the repository, `JdbcTemplate`, and `EntityManager` into the test. The repository performs the write; `EntityManager.flush()` synchronizes changes; then JDBC reads table columns directly.

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class BookJdbcPersistenceTest {

    @Autowired
    private BookRepository bookRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void shouldWriteBookRowThatJdbcCanRead() {
        Book saved = bookRepository.save(
                new Book("978-0132350884", "Clean Code")
        );

        entityManager.flush();

        Long rowCount = jdbcTemplate.queryForObject(
                "select count(*) from books where isbn = ?",
                Long.class,
                saved.getIsbn()
        );

        String storedTitle = jdbcTemplate.queryForObject(
                "select title from books where isbn = ?",
                String.class,
                saved.getIsbn()
        );

        assertThat(rowCount).isEqualTo(1L);
        assertThat(storedTitle).isEqualTo("Clean Code");
    }
}
```

### Walking Through the Test Step by Step

**Step 1 — Write through the repository.**

```java
Book saved = bookRepository.save(
        new Book("978-0132350884", "Clean Code")
);
```

The repository asks JPA to save the entity. The entity may now be managed in the persistence context. Depending on the key generation strategy and execution timing, some SQL may already have been sent; do not rely on that detail to skip explicit synchronization.

**Step 2 — Synchronize changes with `flush()`.**

```java
entityManager.flush();
```

`flush()` instructs JPA to synchronize pending changes with the database. Necessary `INSERT`, `UPDATE`, or `DELETE` statements are generated and executed. If data violates a constraint, errors typically surface at flush time or transaction commit rather than necessarily at the `save()` call.

`flush()` does not mean commit. Data remains within the current transaction and can still roll back.

**Step 3 — Read the row count via JDBC.**

```java
Long rowCount = jdbcTemplate.queryForObject(
        "select count(*) from books where isbn = ?",
        Long.class,
        saved.getIsbn()
);
```

SQL is sent directly to the database. The `?` placeholder is bound via the JDBC API, eliminating any need to concatenate input values into SQL strings. The `COUNT(*)` query confirms exactly one row exists with the saved ISBN.

**Step 4 — Read the actual column value.**

```java
String storedTitle = jdbcTemplate.queryForObject(
        "select title from books where isbn = ?",
        String.class,
        saved.getIsbn()
);
```

The result is the `title` column value returned by the database. This assertion differs in meaning from `saved.getTitle()`: it checks the outcome of a `SELECT` executed through JDBC.

**Step 5 — Compare against expected results.**

Both assertions verify row existence as well as column content. Checking only row count could allow a row saved with the wrong title to pass. Checking only the title requires certainty that the query targets the right key with no confusing duplicates. Combining appropriate checks makes the assertions unambiguous.

## 5. Distinguishing `flush()`, `clear()`, and `commit()`

These three operations appear frequently in JPA testing, each serving a distinct purpose.

| Operation | Effect | Commits the Transaction? |
| --- | --- | --- |
| `entityManager.flush()` | Sends pending changes in the persistence context down to the database. | No. |
| `entityManager.clear()` | Removes managed entities from the current persistence context. | No. |
| Transaction commit | Completes the transaction; changes become committed data per database semantics. | Yes. |

### `flush()` Is an Important Precondition Before Reading via JDBC

The ORM can defer SQL generation until an automatic or explicit flush. Running a JDBC `SELECT` before changes are flushed may fail to see the new row or still see stale values. Therefore, the test must call `flush()` before the reading SQL to control execution order.

### `clear()` Is Useful When Re-Reading via JPA

`clear()` is not required for `JdbcTemplate` to bypass the persistence context; JDBC already ignores the persistence context. However, if a test also wants to verify that a subsequent JPA read does not simply return the still-managed entity, it can flush and clear before calling the repository:

```java
entityManager.flush();
entityManager.clear();

Book reloaded = bookRepository.findById(saved.getId()).orElseThrow();
assertThat(reloaded.getTitle()).isEqualTo("Clean Code");
```

After `clear()`, the old entity is no longer managed in the persistence context. The JPA read must reload the entity. Even so, when the goal is an ORM-independent read, a `JdbcTemplate` query expresses the verification boundary more explicitly.

### `flush()` Does Not Prove Data Was Committed

In `@DataJpaTest`, the test transaction typically rolls back when the test method ends. JDBC can read the newly written row because the query participates in the same transaction and observes that transaction's writes. This proves SQL executed and in-transaction state is right; it does not prove another transaction can see the data after commit.

## 6. When Do You Need to Verify Post-Commit Readability?

Two levels of verification should be distinguished:

| Verification Level | Approach | Conclusion Supported |
| --- | --- | --- |
| Reading within the same transaction | Write via JPA, call `flush()`, read via `JdbcTemplate` inside the test transaction. | SQL synchronized to the database and JDBC reads the current transaction's state. |
| Reading after commit | Let the write transaction complete successfully, then read in another transaction or outside the write transaction. | Committed data is visible to a subsequent reading transaction. |

When testing the second level, structure the test so the test method does not wrap the entire flow in one transaction, invoke a `@Transactional` service to write data, and run the JDBC query after the service call returns. Once the service transaction commits successfully, the subsequent query running outside the write transaction verifies post-commit visibility.

With the `@DataJpaTest` slice, another option is explicitly ending the test transaction after flagging it for commit via `TestTransaction`:

```java
import org.springframework.test.context.transaction.TestTransaction;

// After saving data and calling entityManager.flush():
TestTransaction.flagForCommit();
TestTransaction.end();

// Test transaction has ended; the subsequent JDBC query runs outside that transaction.
Long rowCount = jdbcTemplate.queryForObject(
        "select count(*) from books where isbn = ?",
        Long.class,
        "978-0132350884"
);

assertThat(rowCount).isEqualTo(1L);
```

This illustrates a commit boundary, not the default pattern for every test. When explicitly committing in a test, data will no longer be rolled back automatically by the ended test transaction. The test needs a clear cleanup strategy, such as deleting records by test key or using an isolated database recreated between tests. When post-commit visibility does not need checking, keep `@DataJpaTest`'s default rollback transaction so tests remain isolated and repeatable.

## 7. Using JDBC to Verify Database-Generated Values

Another benefit of JDBC is checking values determined by the database. For example, a column with `DEFAULT CURRENT_TIMESTAMP`, a trigger updating an audit column, or a SQL expression computing a normalized value. The in-memory entity may not yet reflect those changes.

Suppose the `books` table has a `created_at` column populated by the database default on insert. After writing and flushing, the test can read this column:

```java
Timestamp createdAt = jdbcTemplate.queryForObject(
        "select created_at from books where isbn = ?",
        Timestamp.class,
        saved.getIsbn()
);

assertThat(createdAt).isNotNull();
```

Similarly, for a trigger modifying a column after insert or update, JDBC reads the final value stored by the database. If you later need to resynchronize the entity in the persistence context, you can use `entityManager.refresh(entity)` or clear and reload. Remember `refresh()` is an ORM operation; a JDBC read remains more direct evidence of column values.

JDBC is also helpful when verifying data constraints. For example, if `isbn` has a `UNIQUE` constraint, you can try saving two records with duplicate ISBNs, call `flush()`, and assert the operation is rejected. Errors may be translated to `DataIntegrityViolationException` at the Spring layer depending on where and how exceptions are handled. Verification must sit at the appropriate SQL execution point; merely calling `save()` and letting the test end may not trigger the constraint immediately.

## 8. Transaction and Database Configuration Notes in Tests

### JDBC and JPA Must Share the Same `DataSource` to Read Within the Same Transaction

In standard Spring configurations, `JpaTransactionManager` can synchronize a JDBC connection with JPA's `DataSource`. `JdbcTemplate` uses Spring's connection management, enabling SQL statements to participate in the active transaction.

If the application configures multiple `DataSource`s, multiple transaction managers, or a `JdbcTemplate` pointing to a different database, JDBC queries may not see uncommitted JPA changes. Check the wiring in such cases: `EntityManagerFactory`, transaction manager, and `JdbcTemplate` must target the right data source for the test's goal.

### The Test Database Can Differ from Production

`@DataJpaTest` often replaces the datasource configuration with an embedded database if a matching dependency is on the project classpath. This is convenient for fast tests, yet results only reflect the behavior of the database running in the test. SQL syntax, data types, collations, locks, isolation levels, triggers, and certain constraints can differ among H2, PostgreSQL, MySQL, and other DBMSs.

If a test depends on behavior specific to the production database, run it against that exact DBMS, typically via Testcontainers or a configured test datasource. In Spring Boot, `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` prevents `@DataJpaTest` from replacing the datasource; real test connection details must still be supplied separately and safely.

### Automatic Rollback Has Clear Boundaries

Rolling back the transaction after a test cleans up data and prevents one test from affecting another. JDBC reading inside that transaction still sees writes just made. Therefore, do not interpret JDBC results inside a test transaction as proof that a commit succeeded or that data is visible to an independent session.

## 9. Common Design Mistakes

**Reading via repository and concluding the database was checked.**

A repository is an ORM access path. Entities can be returned from the persistence context. When the goal is verifying rows and columns in the database, use JDBC after flushing.

**Skipping `flush()` before the JDBC query.**

Changes may still be pending in the persistence context. A SQL query running before flush may read stale state. Control ordering with `entityManager.flush()`.

**Assuming `flush()` equals commit.**

Flush only synchronizes SQL within the current transaction. Constraints may be checked at flush, yet the transaction can still roll back. When verifying committed data, check after the write transaction finishes.

**Asserting only `saved.getTitle()`.**

That is a Java object field value. It does not prove the database stored the same value. Query the `title` column via JDBC.

**Checking only `COUNT(*)` without checking key data.**

Row existence does not guarantee every column is accurate. Read the columns directly tied to the behavior under verification.

**Using SQL that mismatches the actual schema.**

Table and column names in SQL must match mappings and schema. Explicit `@Table` and `@Column` declarations make examples and tests easier to follow. In projects with naming strategies, migrations, or custom schemas, verify the actual schema of the test database.

**Using an embedded database to draw conclusions about production-specific database behavior.**

JDBC removes the persistence context from the read path, but it does not turn H2 into PostgreSQL or MySQL. Choose the right test database when behavior depends on dialect or engine-specific features.

## 10. Workflow for Applying This in Data-Layer Tests

When verifying that an ORM write produced the expected database state, apply this sequence:

1. Create input data with clear identifying keys to avoid reading the wrong record.
2. Invoke the repository or service to perform the write operation under test.
3. Call `entityManager.flush()` to force the ORM to send pending changes to the database.
4. Use `JdbcTemplate` to run a parameterized `SELECT` targeting the exact row and columns under test.
5. Assert on the JDBC results, such as row count, column values, default values, or trigger-generated outcomes.
6. Clarify whether the test checks in-transaction state or committed data. Change transaction and cleanup strategies only when requirements genuinely demand post-commit verification.

Not every repository test needs JDBC added. When the goal is checking query rules or ORM-level mappings, standard repository tests may be enough. JDBC is particularly valuable when the test question is: **what row and column values does the database actually return after the write?**

## Conclusion

Reading data via JDBC establishes a verification step decoupled from JPA's persistence context. By combining `EntityManager.flush()` with `JdbcTemplate`, a test verifies the state returned by the database within the current transaction rather than merely checking an entity sitting in ORM memory.

Always distinguish flush from commit: standard `@DataJpaTest` tests read via JDBC inside the same transaction and roll back afterward. If you need to verify data was committed and visible to another transaction, design the corresponding transaction boundaries. Likewise, run against the right database type when the behavior under test depends on a specific DBMS.
