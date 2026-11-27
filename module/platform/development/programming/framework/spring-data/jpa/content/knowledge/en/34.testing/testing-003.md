# Creating Test Data With TestEntityManager

## Objectives

In persistence testing, input data must be created according to the JPA mappings so repositories and services can execute against the database. Spring Boot provides `TestEntityManager` as a test-specific utility wrapping commonly used `EntityManager` operations and adding helpers to persist, flush, retrieve IDs, and reload entities.

`TestEntityManager` is especially useful in `@DataJpaTest`: tests can create fixtures directly through JPA, force data to the database, clear the persistence context, and then call the repository to verify results. This approach ensures queries genuinely run against stored data rather than merely reading objects sitting in memory.

After this lesson, you will be able to:

- Distinguish `TestEntityManager` from repositories and standard `EntityManager`.
- Inject `TestEntityManager` into a JPA test slice.
- Create data using `persist`, `persistAndFlush`, and `persistAndGetId`.
- Use `flush`, `clear`, `find`, and `refresh` appropriately.
- Set up fixtures with relationships and cascades on the proper owning side.
- Test repositories after data has been written to the database.
- Understand transaction rollback in `@DataJpaTest`.
- Avoid false positives caused by the first-level cache, shared test data, and test execution order.
- Choose an embedded database or Testcontainers matching production.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA. The API and package of `TestEntityManager` change across Spring Boot major versions; check your project's version.

## 1. What Is TestEntityManager?

`TestEntityManager` is a utility in Spring Boot test support that provides a subset of JPA `EntityManager` operations alongside helpers for preparing and verifying test data.

In Spring Boot 3.x, import:

```java
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
```

In Spring Boot 4.x, the package moved to:

```java
import org.springframework.boot.jpa.test.autoconfigure.TestEntityManager;
```

Do not add both imports to the same class. Use the package corresponding to the Spring Boot version your project runs on.

Common operations:

| Method | Purpose |
|---|---|
| `persist(entity)` | Puts a new entity into the persistence context in managed state |
| `persistAndFlush(entity)` | Persists the entity and flushes immediately |
| `persistAndGetId(entity, Long.class)` | Persists and returns the ID |
| `persistFlushFind(entity)` | Persists, flushes, and then finds by ID |
| `flush()` | Synchronizes pending changes to the database |
| `clear()` | Detaches all entities in the persistence context |
| `find(Type.class, id)` | Finds an entity by primary key |
| `refresh(entity)` | Reloads the entity state from the database |
| `detach(entity)` | Detaches a single entity |
| `merge(entity)` | Merges an object's state into the persistence context |
| `remove(entity)` | Marks a managed entity for removal |
| `getId(entity)` | Retrieves the entity's identifier |
| `getEntityManager()` | Retrieves the underlying `EntityManager` used by `TestEntityManager` |

`TestEntityManager` is neither a fake database nor a repository mock. It uses the persistence infrastructure and JPA provider configured for the test.

## 2. Creating a Test Slice With @DataJpaTest

`@DataJpaTest` configures a test slice focused on JPA: entity mappings, repositories, and related persistence components.

Example:

```java
package com.example.demo.book;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private TestEntityManager testEntityManager;

    @Autowired
    private BookRepository bookRepository;

    @Test
    void testContextStarts() {
        // TestEntityManager and repository have been injected.
    }
}
```

In this example, `TestEntityManager` and `BookRepository` participate together in the Spring-managed test transaction. Each test method normally runs within a transaction that is rolled back when the test completes.

`@DataJpaTest` typically uses an embedded database if an appropriate dependency is present. If you want to run on a Testcontainers database or a production-equivalent database, configure the test datasource explicitly; for instance, with Testcontainers you can use `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` to prevent replacing the configured datasource.

Do not use `@DataJpaTest` to test the entire HTTP/controller/security stack. It focuses solely on persistence. If you need to test services with transactions, events, or multiple collaborating beans, use `@SpringBootTest` or an appropriate test slice.

## 3. Sample Entities and Repository

Use a `Book` entity with a generated ID, title, ISBN, and to-one relationships to `Author` and `Publisher`. `Publisher` is an optional association to illustrate multi-level fixtures later.

Author:

```java
package com.example.demo.book;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @OneToMany(
        mappedBy = "author",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<Book> books = new ArrayList<>();

    protected Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void addBook(Book book) {
        books.add(book);
        book.setAuthor(this);
    }
}
```

Book:

```java
package com.example.demo.book;

import jakarta.persistence.*;

@Entity
@Table(
    name = "books",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_books_isbn",
        columnNames = "isbn"
    )
)
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, length = 20)
    private String isbn;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private Author author;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "publisher_id")
    private Publisher publisher;

    protected Book() {
    }

    public Book(String title, String isbn, Author author) {
        this(title, isbn, author, null);
    }

    public Book(
            String title,
            String isbn,
            Author author,
            Publisher publisher
    ) {
        this.title = title;
        this.isbn = isbn;
        this.author = author;
        this.publisher = publisher;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getIsbn() {
        return isbn;
    }

    public Author getAuthor() {
        return author;
    }

    public void setAuthor(Author author) {
        this.author = author;
    }
}
```

Publisher:

```java
package com.example.demo.book;

import jakarta.persistence.*;

@Entity
@Table(name = "publishers")
public class Publisher {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Publisher() {
    }

    public Publisher(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Repository:

```java
package com.example.demo.book;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByTitleContainingIgnoreCase(String title);

    Optional<Book> findByIsbn(String isbn);
}
```

Subsequent examples use these entities and repository. Public constructors keep fixture creation readable; protected no-arg constructors are kept so JPA can instantiate entities.

## 4. Injecting TestEntityManager and Persisting Fixtures

Use `persist` to place new entities into the persistence context:

```java
@Test
void persistsBook() {
    Author author =
            testEntityManager.persist(new Author("Ada Lovelace"));

    Book book = testEntityManager.persistAndFlush(
            new Book(
                    "Spring Data JPA",
                    "9780000000001",
                    author
            )
    );

    assertThat(book.getId()).isNotNull();
}
```

`persist` invokes JPA's persist operation. The entity becomes managed in the current persistence context. However, that does not mean all changes have already been sent to the database at that line of code.

The ID may be assigned immediately or when the insert executes, depending on the ID generation strategy and provider. Do not write tests assuming every ID starts at 1 or increments by exactly one; sequences/identities and test data can produce different values.

### 4.1. Persisting Multiple Fixtures and Flushing Once

When creating multiple baseline records, you can persist each entity and flush at the end:

```java
@Test
void createsSeveralBooks() {
    Author author =
            testEntityManager.persist(new Author("Ada Lovelace"));

    testEntityManager.persist(
            new Book("Spring Data JPA", "9780000000001", author)
    );
    testEntityManager.persist(
            new Book("Hibernate Basics", "9780000000002", author)
    );
    testEntityManager.persist(
            new Book("JPA in Practice", "9780000000003", author)
    );

    testEntityManager.flush();
}
```

This avoids flushing after every individual fixture when unnecessary. The database receives pending operations when `flush` is called or when the provider auto-flushes before a query requiring synchronized data.

### 4.2. Using persistAndFlush

If you want to write a fixture immediately and catch constraint errors at a specific point:

```java
Author author = testEntityManager.persistAndFlush(
        new Author("Ada Lovelace")
);
```

`persistAndFlush` is equivalent to calling `persist` then `flush`. It is useful when:

- You need the database/provider-assigned ID before creating dependent entities.
- You want a constraint violation to surface immediately during setup.
- You want to ensure data has been sent to the database before running a query.
- You want to separate fixture stages to pinpoint errors more easily.

Flush is still not commit. The transaction can continue and roll back at the end of the test.

## 5. Retrieving IDs With persistAndGetId and getId

You can retrieve the ID immediately upon persisting:

```java
Long authorId = testEntityManager.persistAndGetId(
        new Author("Ada Lovelace"),
        Long.class
);
```

Or retrieve the ID from an already persisted entity:

```java
Author author = testEntityManager.persist(
        new Author("Ada Lovelace")
);

Long authorId = testEntityManager.getId(author, Long.class);
```

This is useful when a fixture needs an ID to pass into a query or to associate related entities via foreign keys through the appropriate API.

Do not cast IDs based on assumptions if the entity uses UUIDs, composite keys, or another type. Use the overload taking a class parameter to express the expected ID type. If the ID has not yet been generated under the active strategy, the value may not be available until the insert executes.

## 6. Flush, Clear, and Find: Verifying Data Actually Stored

This is the most important sequence when testing repositories:

1. Persist the fixture.
2. Flush to send changes to the database.
3. Clear the persistence context to detach managed entities.
4. Call the repository or `find` to read back.

Example:

```java
@Test
void readsBookFromDatabaseAfterPersisting() {
    Author author =
            testEntityManager.persistAndFlush(
                    new Author("Ada Lovelace")
            );

    Book book = testEntityManager.persist(
            new Book(
                    "Spring Data JPA",
                    "9780000000001",
                    author
            )
    );

    testEntityManager.flush();
    Long bookId = book.getId();

    testEntityManager.clear();

    Book reloaded = bookRepository.findById(bookId)
            .orElseThrow();

    assertThat(reloaded.getTitle()).isEqualTo("Spring Data JPA");
    assertThat(reloaded.getAuthor().getName()).isEqualTo("Ada Lovelace");
}
```

### 6.1. Why Is clear Needed?

The JPA persistence context is a first-level cache. If you call `find` or repository `findById` while the entity is still managed, the provider usually returns the same object already sitting in the context instead of reloading state from the database.

That can produce false positives: the test sees the values just set on the object and assumes the database stored them properly.

`clear()` detaches all managed entities in the current context. Afterward, queries reading entities must load state from the database within the transaction. This is a useful way to verify mappings, inserts/updates, and queries.

Note: `clear()` affects the entire persistence context, not just the newly created entity. Unflushed changes will no longer be managed for automatic persistence. Therefore, call `flush` before `clear` if you want to retain those changes.

### 6.2. Flush Is Not Commit

`flush()` synchronizes changes in the persistence context with the current database connection/transaction. It does not end the transaction and does not make data durable to other transactions.

In `@DataJpaTest`, transactions typically roll back after tests. Therefore:

- After flush, queries within the same transaction can see the written data.
- Other test methods should not rely on uncommitted data from an earlier test.
- Transaction rollback cleans up test changes via database/transaction mechanisms.
- Constraints deferred until commit (if the database supports deferred constraints) may not raise errors at flush time.

Do not use flush as a way to keep test data after a test finishes.

## 7. How Is persistFlushFind Different?

`persistFlushFind(entity)` is a helper combining three operations:

1. Persist the entity.
2. Flush the persistence context.
3. Find the entity by that object's ID.

Example:

```java
Book found = testEntityManager.persistFlushFind(
        new Book(
                "Spring Data JPA",
                "9780000000001",
                author
        )
);
```

This helper is convenient when you need to persist and find right away. However, it does not clear the persistence context before finding. Because the newly persisted entity may still be managed, `find` can return the same instance already in the first-level cache.

If the goal is to prove a query reads data from the database after writing, use the explicit sequence:

```java
Book saved = testEntityManager.persistAndFlush(book);
Long id = saved.getId();

testEntityManager.clear();

Book reloaded = testEntityManager.find(Book.class, id);
```

Or clear and then call the repository method under test. This avoids confusing in-memory object state with reloaded data.

## 8. Creating Fixtures With Relationships on the Proper Owning Side

JPA only synchronizes associations based on the mapping and the owning side. With `@ManyToOne` and `@OneToMany(mappedBy = ...)`, the side holding `@JoinColumn` is usually the owning side.

In the example:

- `Book.author` is the owning side because `Book` has `@JoinColumn(name = "author_id")`.
- `Author.books` (if present) is the inverse side because it declares `mappedBy = "author"`.

If an entity has a bidirectional relationship, domain helpers should update both sides:

```java
@Entity
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "author",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<Book> books = new ArrayList<>();

    public void addBook(Book book) {
        books.add(book);
        book.setAuthor(this);
    }
}
```

In a fixture:

```java
Author author = new Author("Ada Lovelace");
Book book = new Book(
        "Spring Data JPA",
        "9780000000001",
        author
);

author.addBook(book);

testEntityManager.persistAndFlush(author);
```

This example assumes `Book` has an appropriate setter or assignment method for `Author`. Cascade `PERSIST` allows persisting `Author` to cascade to `Book`; without cascading, you must persist each entity in the appropriate order.

Do not merely add `Book` to the inverse collection and expect the database to update the foreign key automatically. You must set the owning side. Otherwise, after clearing and reloading, the relationship may not exist even though the initial in-memory collection looked right.

### 8.1. Creating Multi-Level Relationship Fixtures

For multi-level relationships, create parents before children if children require persisted parents:

```java
Author author = testEntityManager.persist(
        new Author("Ada Lovelace")
);

Publisher publisher = testEntityManager.persist(
        new Publisher("Example Press")
);

Book book = testEntityManager.persist(
        new Book(
                "Spring Data JPA",
                "9780000000001",
                author,
                publisher
        )
);

testEntityManager.flush();
testEntityManager.clear();
```

If mappings have appropriate cascades, you can persist the aggregate root and let cascading save components. Pick one clear approach and avoid unnecessarily mixing cascading with redundant explicit persists on the same entity.

With `@ManyToMany`, update the owning side of the join table. With `@OneToOne`, identify which entity holds the join column. When fixtures grow complex, write factories/helpers named after the aggregate being built to keep tests readable.

## 9. Using TestEntityManager in @BeforeEach

Shared test data can be created using `@BeforeEach`:

```java
@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private TestEntityManager testEntityManager;

    @Autowired
    private BookRepository bookRepository;

    @BeforeEach
    void setUp() {
        Author author = testEntityManager.persist(
                new Author("Ada Lovelace")
        );

        testEntityManager.persist(
                new Book("Spring Data JPA", "9780000000001", author)
        );
        testEntityManager.persist(
                new Book("Hibernate Basics", "9780000000002", author)
        );

        testEntityManager.flush();
        testEntityManager.clear();
    }

    @Test
    void findsBookByTitle() {
        List<Book> result =
                bookRepository.findByTitleContainingIgnoreCase("spring");

        assertThat(result)
                .extracting(Book::getTitle)
                .containsExactly("Spring Data JPA");
    }
}
```

Because each test method typically has its own transaction that rolls back when finished, fixtures created in `@BeforeEach` are recreated for each test. This keeps tests independent, though it can add overhead if the fixture is very large.

Do not create shared data in a committed transaction and make tests depend on execution order. Each test should set up the data it needs so it can run independently.

## 10. Testing Constraints and Flush Failures

Many errors only surface when the provider sends SQL to the database. For example, ISBN has a unique constraint:

```java
@Test
void duplicateIsbnViolatesUniqueConstraint() {
    Author author = testEntityManager.persist(
            new Author("Ada Lovelace")
    );

    testEntityManager.persistAndFlush(
            new Book("Spring Data JPA", "9780000000001", author)
    );

    assertThatThrownBy(() -> testEntityManager.persistAndFlush(
            new Book(
                    "Another Book",
                    "9780000000001",
                    author
            )
    )).isInstanceOf(RuntimeException.class);
}
```

This example illustrates when errors typically occur; the exact exception class may depend on the JPA provider, database, and Spring's exception translation. When testing a service/repository boundary, check the Spring-translated exception at that boundary rather than asserting an internal Hibernate exception.

After a failed flush, the transaction/persistence context may be in a state where it cannot be safely used further. Do not catch the exception and continue querying as if the transaction were still healthy. Let the test finish and roll back; if you need to test multiple independent failure cases, use separate test methods.

## 11. Using refresh to Reload Database Changes

`refresh(entity)` reloads a managed entity's state from the database, overwriting unsynchronized in-memory changes.

For example, suppose a database trigger updates a column:

```java
Book book = testEntityManager.persistAndFlush(new Book(...));

// A trigger or procedure changes a property in the database.

testEntityManager.refresh(book);

assertThat(book.getTitle()).isEqualTo("Value currently in database");
```

Do not call `refresh` when the object has unflushed changes you want to keep, because `refresh` overwrites that state with database data.

Differences between operations:

| Operation | Result |
|---|---|
| `flush()` | Sends pending changes to the database |
| `refresh(entity)` | Updates a managed object from the database |
| `clear()` | Detaches all managed entities |
| `detach(entity)` | Detaches a single entity |
| `find(Type.class, id)` | Finds an entity; may return an already-managed object in the context |

If you want to verify a repository query or mapping after saving, typically use `flush` + `clear` + repository call. If you only need to sync a single managed entity with database changes, `refresh` can be suitable.

## 12. merge and remove in Tests

`merge(entity)` is useful when bringing a detached object's state back into the persistence context:

```java
Book detached = testEntityManager.find(Book.class, bookId);
testEntityManager.clear();

detached.setTitle("Updated title");

Book managed = testEntityManager.merge(detached);
testEntityManager.flush();

assertThat(managed.getTitle()).isEqualTo("Updated title");
```

`merge` returns the managed instance after merging. The input object does not become managed itself; continue working with the returned object.

To remove an entity:

```java
Book book = testEntityManager.find(Book.class, bookId);

testEntityManager.remove(book);
testEntityManager.flush();

assertThat(testEntityManager.find(Book.class, bookId)).isNull();
```

`remove` requires a managed entity. If you hold a detached entity, find it again or merge it with the proper semantics before deleting. Do not use `merge` just to delete an object if you can directly find the managed entity.

## 13. TestEntityManager vs. Repository: Which Tool to Use?

The two tools serve different roles:

| Task | Appropriate Tool |
|---|---|
| Rapidly creating fixtures per JPA mappings | `TestEntityManager` |
| Getting ID after persist | `TestEntityManager.getId` or `persistAndGetId` |
| Flush/clear/refresh in tests | `TestEntityManager` |
| Testing repository query methods | The Repository under test |
| Testing derived queries, JPQL, Specifications | Repository |
| Testing service business logic | Call the real service; use `TestEntityManager` for fixtures |
| Testing HTTP/controllers/security | Appropriate web test or `SpringBootTest` |
| Testing production migrations and dialects | Matching test database, typically via Testcontainers |

Example testing a service:

```java
@Test
void serviceReturnsOnlyActiveBooks() {
    Author author = testEntityManager.persist(
            new Author("Ada Lovelace")
    );

    testEntityManager.persist(
            new Book("Spring Data JPA", "9780000000001", author)
    );
    testEntityManager.persist(
            new Book("Old Book", "9780000000002", author)
    );

    testEntityManager.flush();
    testEntityManager.clear();

    List<Book> result = bookService.findBooksByTitle("spring");

    assertThat(result)
            .extracting(Book::getTitle)
            .containsExactly("Spring Data JPA");
}
```

This service test assumes the service is injected and has a `findBooksByTitle(String)` method returning `List<Book>`, which delegates to the repository to search by title. `TestEntityManager` only prepares data; assertions go through the real service to verify business logic.

Do not call `TestEntityManager` in place of the service/repository under test. If a test only calls `EntityManager` directly and concludes the repository works, the test has not tested the repository.

## 14. @DataJpaTest Transactions and Rollback

`@DataJpaTest` typically marks tests as transactional and rolls them back when each test finishes. This ensures every test starts with a clean data state.

Points to remember:

- `persist` and `flush` still stay inside the test transaction.
- Flush does not commit.
- Queries inside the same transaction can read freshly flushed data.
- Other tests must not rely on uncommitted data from the current test.
- `@Commit` or `@Rollback(false)` changes cleanup behavior; use only with a specific testing reason.
- Tests spanning multiple transactions or threads may not share a persistence context.
- Asynchronous tests require dedicated transaction and visibility design.

If you need to check data after commit or across two transactions, do not assume `clear()` equals commit. `clear` only detaches objects from the persistence context; it does not end the transaction.

For tests verifying transaction boundaries, you can use `TransactionTemplate` or appropriate test configuration to commit/roll back intentionally. Avoid turning every repository test into a non-rolling-back transaction because it leaves leftover data and introduces cross-run dependencies.

## 15. Stable and Maintainable Test Data

A good fixture set should:

- Use concrete, readable values that do not depend on the current time unless necessary.
- Use unique ISBNs/emails/codes to avoid unique constraint collisions.
- Provide sufficient matching and non-matching cases for queries.
- Control dates/times using fixed `Instant` values and explicit timezones.
- Not depend on database-assigned ID sequences.
- Set associations via the owning side.
- Create only the data needed, avoiding huge fixtures for a small test.
- Not share mutable entities across test methods.
- Provide helper factories when the same aggregate is used repeatedly.

Example factory:

```java
private Book createBook(
        String title,
        String isbn,
        String authorName
) {
    Author author = testEntityManager.persist(
            new Author(authorName)
    );

    return testEntityManager.persist(
            new Book(title, isbn, author)
    );
}
```

Usage:

```java
@Test
void findsBooksByAuthor() {
    createBook("Spring Data JPA", "9780000000001", "Ada");
    createBook("Hibernate", "9780000000002", "Grace");

    testEntityManager.flush();
    testEntityManager.clear();

    List<Book> result = bookRepository.findByAuthorName("Ada");

    assertThat(result)
            .extracting(Book::getTitle)
            .containsExactly("Spring Data JPA");
}
```

Factories should keep business-meaningful names and parameters. Avoid overly generic helpers with dozens of nullable parameters that make it hard for readers to see what data the fixture actually contains.

## 16. Embedded Databases and Testcontainers

Embedded databases are useful for fast tests, but SQL dialects, data types, collations, constraints, locking, and transaction semantics may differ from production.

Use a database matching production when tests rely on:

- Native SQL or stored procedures.
- JSON/array/geospatial or engine-specific types.
- Functions, collations, and case sensitivity.
- Locks, isolation, deadlocks, or specialized constraints.
- DDL migrations.
- Generated columns, triggers, or sequence behavior.

With Testcontainers, configure the database container and let Spring use that datasource. Example PostgreSQL container:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class BookRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private TestEntityManager testEntityManager;

    @Autowired
    private BookRepository bookRepository;

    // Repository tests...
}
```

This example requires Testcontainers PostgreSQL, JUnit integration dependencies, and a Spring Boot version supporting `@ServiceConnection`. If your project version does not support this annotation, configure the datasource via `@DynamicPropertySource`.

Testcontainers runs tests against a real database inside a container, though proper migrations and fixture data are still needed. Do not assume an embedded H2 test proves PostgreSQL stored procedures or native SQL work.

## 17. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Repository returns an object with stale values | Entity is still in the first-level cache | Flush then clear before querying |
| ID missing after persist | ID strategy/provider has not inserted yet | Flush or use `persistAndFlush` |
| Constraint violation surfaces at end of test | SQL only executes on flush/commit | Flush at the point you want to verify the error |
| Relationship not saved | Updated only the inverse side, skipped owning side | Set the association on the side with `JoinColumn` |
| One test's fixture affects another test | Data committed or uncleaned database | Use transaction rollback and dedicated fixtures |
| `refresh` loses changes | Refresh overwrites object state from database | Flush first if changes must be kept |
| `merge` does not update input object | Merge returns a different managed instance | Use the instance returned by `merge` |
| `clear` drops pending changes | Clear detaches entities before flush | Flush before clear |
| `TestEntityManager` not injected | Test is not in a JPA test configuration or missing test support | Check `@DataJpaTest` and dependencies |
| Test passes on H2 but fails in production | Different dialect, driver, or database behavior | Use Testcontainers with the matching DBMS |
| Test depends on a specific ID | Assumed sequence/identity starts at a certain value | Read ID from `TestEntityManager` |
| Test checks the wrong layer | Used `TestEntityManager` instead of the repository/service | Build fixtures with `TestEntityManager`, call the real component under test |

## 18. Checklist for Creating Data With TestEntityManager

- [ ] Test uses `@DataJpaTest` or an appropriate JPA test configuration.
- [ ] `TestEntityManager` is injected from Spring Boot test support.
- [ ] Package import matches the Spring Boot version.
- [ ] Fixtures are built using meaningful constructors/factories.
- [ ] IDs are retrieved from entities or `persistAndGetId`, not hard-coded.
- [ ] Associations are assigned on the owning side.
- [ ] Cascades are well understood before persisting aggregates.
- [ ] Flush is called at the exact point SQL/constraints need verification.
- [ ] Clear is called before asserting that a repository query reads persisted data.
- [ ] Understand that flush is not commit.
- [ ] Use `refresh` when needing to sync a managed entity from the database.
- [ ] Use the object returned by `merge`.
- [ ] Do not share mutable fixtures across tests.
- [ ] Tests do not depend on execution order or specific IDs.
- [ ] Use a production-matching database for dialect-dependent behavior.
- [ ] Tests exercise the real repository/service being verified.

## 19. References

- [Spring Boot 3.5 — TestEntityManager API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/TestEntityManager.html)
- [Spring Boot — @DataJpaTest](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html)
- [Spring Data JPA — Testing](https://docs.spring.io/spring-data/jpa/reference/repositories/testing.html)
- [Jakarta Persistence — EntityManager API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)

## Conclusion

`TestEntityManager` helps create and control fixtures using your actual JPA mappings in Spring Boot persistence tests. `persist`, `persistAndFlush`, and `persistAndGetId` simplify data preparation; `flush`, `clear`, `find`, and `refresh` help verify state synchronization between the persistence context and the database.

For repository tests, create fixtures, flush, clear, and then invoke the repository so the first-level cache does not produce misleading test results. Assign associations on the owning side, obtain IDs dynamically, keep every test independent, and remember that `@DataJpaTest` normally rolls back transactions after a test ends. When queries depend on dialects, migrations, or procedures, run tests on a production-equivalent database with Testcontainers. `TestEntityManager` should assist with data setup and verification; final assertions must still pass through the repository or service the test is meant to protect.