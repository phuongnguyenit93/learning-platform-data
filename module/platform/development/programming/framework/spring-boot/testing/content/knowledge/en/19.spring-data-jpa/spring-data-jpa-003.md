# TestEntityManager with persist, flush, clear, and find

## 1. Lesson Goal

When testing Spring Data JPA, a test can PASS even though data **has not been synchronized to the database**. The reason is that JPA manages entities in a **persistence context (first-level cache)**. A `find` call can immediately return the managed object itself instead of re-reading the actual state received by the database.

`TestEntityManager` is a Spring Boot Test utility that helps set up JPA data and perform concise `persist`, `flush`, `clear`, and `find` operations. Specifically, combining:

```java
BookEntity saved = testEntityManager.persist(
        new BookEntity("ISBN-001", "Spring Data JPA"));
testEntityManager.flush();
testEntityManager.clear();
BookEntity reloaded = testEntityManager.find(
        BookEntity.class, saved.getId());
```

lets you verify that an entity can be retrieved again **after the first-level persistence context has been cleared**. This sequence **is not a commit**: in `@DataJpaTest`, the test normally remains inside a transaction that is rolled back after the method completes.

This lesson belongs to the **Spring Data JPA** group, directly addressing **“TestEntityManager with persist, flush, clear, and find”**. We will cover:

- Entity lifecycle: transient/new → managed → detached; difference from removed.
- What `persist` does, when an ID receives a value, and why the ID generation strategy matters.
- `flush` synchronizes changes to the database within the current transaction, yet **does not commit**.
- `clear` detaches all entities from the first-level cache; unflushed changes can be lost.
- `find` looks up by primary key and can retrieve from the first-level cache if not cleared.
- Helper methods `persistAndFlush`, `persistAndGetId`, and `persistFlushFind`: uses and limitations you must understand accurately.
- Writing tests with `@DataJpaTest`, H2, and JUnit Jupiter; verifying via repositories, JPA, and JDBC when appropriate.
- Pitfalls involving auto-flush, dirty checking, unique constraints, transaction rollback, Hibernate-specific behavior, and real databases.

**Illustrative versions:** Java 17+, Spring Boot **3.3.5**, Spring Data JPA/Hibernate 6, and H2. The `TestEntityManager` API used in the examples belongs to Boot 3.3's `org.springframework.boot.test.autoconfigure.orm.jpa` package; do not copy packages changed in Boot 4 into a Boot 3.3 project.

## 2. Why Does TestEntityManager Exist?

Spring Boot `@DataJpaTest` creates an application context **focused on persistence**: JPA entities, Spring Data repositories, `EntityManager`, DataSource, and related components. When an embedded database like H2 is on the test runtime classpath, tests are typically configured to run against that database.

`TestEntityManager` provides a small API tailored for rapid fixture setup:

```java
@Autowired
TestEntityManager testEntityManager;
```

It is not a separate JPA implementation. Most methods simply delegate to an actual `jakarta.persistence.EntityManager` managed by the framework. `getEntityManager()` exposes the full JPA API when needed.

Under `@DataJpaTest`, a transaction is opened for a test method by default, then **rolled back when the test finishes**. Consequently, creating test data usually leaves no new rows in the database between tests. However, database-specific side effects such as **sequence values** do not necessarily roll back; never assert that the first entity ID is always `1`.

### TestEntityManager vs. Spring Data Repository

| Tool | Responsibility | When to Use |
| --- | --- | --- |
| `TestEntityManager` | Prepare/inspect JPA state, force flush, clear, find by ID | Repository tests, mapping tests, constraint tests |
| `EntityManager` | Standard full JPA persistence context and API | Queries, locking, entity lifecycle, criteria, refresh |
| `JpaRepository<T,ID>` | Application's query and persistence abstraction | Testing repository logic, derived queries |
| `JdbcTemplate` | Executes raw SQL directly, bypassing the JPA first-level cache | Checking DB rows after flush inside the same transaction |
| `@DataJpaTest` | Creates a JPA test context and default transaction | Testing repositories, entity mappings, JPA behavior |
| `@SpringBootTest` | Broader application context | Testing service/transaction boundaries across many beans |

An effective repository test often **prepares fixtures with TestEntityManager, flushes + clears, and then queries using the repository under test**. Using the repository itself to both set up and assert the exact same operation can sometimes miss mapping/flush bugs.

## 3. Entity Lifecycle: Four States to Distinguish

According to Jakarta Persistence, an entity instance can be in these primary states:

```text
new / transient
  |
  | entityManager.persist(entity)
  v
managed (attached to persistence context)
  | \
  |  \ entityManager.remove(entity)
  |   \-> removed (scheduled for deletion on transaction)
  |
  | entityManager.detach(entity)
  | or entityManager.clear()
  v
detached (has identity but no longer managed by context)
  |
  | entityManager.merge(entity)
  v
managed copy (may be a different instance)
```

**Transient/new:** an object just created with `new`, not yet attached to a context. `id` may be null or assigned by the app.

**Managed:** an object managed by the context. Modifications to its persistent fields are tracked by **dirty checking** and synchronized at flush/commit depending on flush mode.

**Detached:** an object that has an identity but is no longer managed by the context. Modifying a detached object directly **does not automatically update the DB**. To bring state back into the context, call `merge`, and use the managed entity returned by `merge`.

**Removed:** a managed entity marked for deletion. The database will receive a DELETE on flush/commit depending on provider/transaction.

Do not confuse `clear` with `remove`: `clear` **does not delete rows in the database**; it only turns entities in the persistence context into detached instances.

### First-Level Cache and Identity

Within a persistence context, calling `find(BookEntity.class, id)` a second time for the same entity normally returns **the exact same managed instance**. Thus:

```java
BookEntity b = testEntityManager.persistAndFlush(
        new BookEntity("ISBN-002", "Caching"));
BookEntity same = testEntityManager.find(
        BookEntity.class, b.getId());
assertSame(b, same);
```

is an example of expected behavior before `clear`. If a test only checks that `find` returns the right data immediately after `persist`, it might merely be checking an in-memory object — insufficient to prove persistence and readback via SQL/database.

## 4. persist(): Putting a New Entity into the Persistence Context

`persist` associates a new entity with the persistence context. Example:

```java
BookEntity entity = new BookEntity(
        "ISBN-003", "Transactions");
BookEntity managed = testEntityManager.persist(entity);
```

In Spring Boot 3.3's `TestEntityManager`, `persist(E)` delegates to `EntityManager.persist(Object)` and returns the passed entity. For an ordinary entity example, `managed == entity` is `true`.

**Do not assume persist always executes an INSERT immediately.** SQL may be deferred until flush/commit; timing depends on the ID generation strategy and provider:

- With `GenerationType.SEQUENCE`, Hibernate typically fetches a sequence value first and queues the INSERT until flush. Having an ID **does not prove** the row has been INSERTed.
- With `GenerationType.IDENTITY`, the provider usually must execute the INSERT early to obtain the database-generated ID; therefore do not use it to prove “persist hasn't run SQL yet”.
- With manually assigned IDs, the entity has an ID even before persist; an ID is even less proof of successful persistence.

In the example project, we choose `SEQUENCE` and H2 so the flush behavior is more predictable and transparent.

### persist Is Not merge

`persist` is for new entities; passing a detached entity or an entity that already has an identity in an invalid state can throw `EntityExistsException`, `PersistenceException`, or another provider error on flush. For a detached entity needing updates, use `merge` or load a managed entity and update its fields; do not use `persist` as a universal upsert operation.

## 5. flush(): Syncing JPA State to the Database Without Committing

`TestEntityManager.flush()` delegates to `EntityManager.flush()`. It tells the persistence provider to synchronize pending changes in the persistence context to the underlying database **within the current transaction**:

```java
testEntityManager.persist(book);
testEntityManager.flush();
```

In Hibernate, flush can emit pending `INSERT`, `UPDATE`, and `DELETE` SQL statements and expose errors caused by database constraints.

Crucially:

**Flush ≠ Commit.**

| Operation | Meaning | Transaction Committed? |
| --- | --- | --- |
| `persist(entity)` | Makes a new entity managed | No |
| `flush()` | Synchronizes pending changes to DB inside transaction | No |
| `clear()` | Detaches entities from the persistence context | No |
| `find(Entity.class,id)` | Looks up by primary key in context/DB | No |
| Transaction commit | Completes transaction and finalizes changes per DB | Yes, if successful |
| Transaction rollback | Discards uncommitted transactional changes | No committed changes |

In `@DataJpaTest`, `persist → flush → clear → find` can succeed, yet when the test finishes, the transaction is **rolled back** and the row does not persist across tests.

### Auto-Flush Can Happen Before a Query

Under `FlushModeType.AUTO` (typically the default), JPA may flush before a query if needed to ensure the query sees relevant pending changes. Therefore, a test like:

```java
testEntityManager.persist(book);
assertEquals(1L, repository.count());
```

does not prove `persist` already wrote SQL before `count()`: the repository query **may trigger an automatic flush by the provider**. When a test wants to pinpoint when SQL/database receives changes, call `flush` explicitly and observe across an appropriate boundary.

### Flush Can Fail Late

The fact that `persist` does not throw immediately does not mean the data is valid. Unique keys, NOT NULL, foreign keys, optimistic locking, or database-specific constraints may only be checked when SQL is issued at flush.

When testing a constraint failure, run it in a **separate test** and do not execute further queries in the failed transaction; the provider/transaction may be marked rollback-only. Do not catch the exception and try to run subsequent JPA operations as though the transaction were healthy.

## 6. clear(): Releasing the First-Level Cache and Detaching Managed Entities

`TestEntityManager.clear()` delegates to `EntityManager.clear()`: **all** managed entities in the persistence context become detached. It does not delete data already flushed to the database.

```java
BookEntity managed = testEntityManager.persistAndFlush(
        new BookEntity("ISBN-004", "Persistence"));
Long id = managed.getId();

testEntityManager.clear();

BookEntity reloaded =
        testEntityManager.find(BookEntity.class, id);
```

After `clear`, `managed` is no longer managed by the EntityManager, while `reloaded` is a newly managed entity in the current context. In the sample project without second-level caching enabled, `find` after `clear` can perform a database lookup. More precisely, **clear evicts entries from the first-level cache**; it does not guarantee the provider bypasses a second-level cache if the application configures an L2 cache.

### Why Flush Before Clear?

If you modify a managed entity and call `clear` **before flushing**, those modifications are no longer tracked and can be lost. Example:

```java
BookEntity entity = testEntityManager.persistAndFlush(
        new BookEntity("ISBN-005", "Original"));
entity.changeTitle("Unsaved");
testEntityManager.clear();
```

A subsequent find normally returns the title `Original`, because `Unsaved` was only a change on the managed object and was discarded before flush.

**Typically correct sequence to verify database state:**

```text
persist → flush → clear → find
                        ↑
              reloads the entity
              outside the old L1 context
```

**Dangerous sequence when unflushed modifications exist:**

```text
persist / mutate → clear → find
                    ↑
             pending changes may be lost
```

This does not mean every provider never writes SQL before `clear`: some operations/ID strategies may execute SQL early. Tests should intentionally choose an appropriate ID strategy and flush mode if verifying detailed timing.

## 7. find(): Primary Key Lookup and Cache Boundaries

`TestEntityManager.find(BookEntity.class, id)` delegates to `EntityManager.find(Class<T>, Object primaryKey)`.

- If the entity for that primary key is already managed, JPA normally returns that instance from the first-level cache.
- If it is not in the context, the provider fetches the entity from the appropriate persistence store/cache and returns a managed instance.
- If no record exists, it returns **`null`**, not `Optional.empty()`.
- Passing an invalid primaryKey type or null may throw `IllegalArgumentException` per the JPA API; do not pass a null ID to `find` as if it were a valid query.

Example:

```java
BookEntity existing =
        testEntityManager.find(BookEntity.class, persistedId);

BookEntity missing =
        testEntityManager.find(BookEntity.class, 999999999L);
```

If you want `Optional<BookEntity>`, `JpaRepository.findById(id)` provides a different API signature. Both express an ID lookup, though they do not necessarily share identical behavior regarding query filters or lazy proxies.

### find Is Not getReference

`EntityManager.getReference(...)` may return a proxy/reference without loading state immediately; accessing fields afterward can throw `EntityNotFoundException` if the DB row is missing. `find(...)` returns the entity or null per lookup contract. Do not use `getReference` to “prove a row exists” without accessing its state.

## 8. persistAndFlush, persistAndGetId, and persistFlushFind

Spring Boot 3.3's `TestEntityManager` provides these helpers:

| Method | Meaning in Boot 3.3 | What Not to Infer |
| --- | --- | --- |
| `persist(entity)` | Persists then returns the passed entity | SQL INSERT definitely ran |
| `persistAndFlush(entity)` | Persists, flushes, returns the original entity | Transaction committed |
| `persistAndGetId(entity)` | Persists, returns identifier | Record was flushed/committed |
| `persistAndGetId(entity, Long.class)` | Persists, returns typed ID | ID necessarily starts at 1 |
| `persistFlushFind(entity)` | `persistAndFlush` then `find` by ID | Automatically clears L1 or forces a fresh SELECT |
| `getId(entity)` | Retrieves identifier via PersistenceUnitUtil | Entity is always managed |
| `detach(entity)` | Detaches a single entity | Deletes the DB record |
| `clear()` | Detaches all managed entities | Flushed/committed beforehand |
| `getEntityManager()` | Accesses the real JPA EntityManager | Can be used without a transaction |

**Version-specific note:** in the Spring Boot **3.3** Javadoc, `persistFlushFind` is documented as delegating to `persistAndFlush` and then `find(Class, Object)`. It **is not documented in Boot 3.3 as guaranteeing an automatic clear** of the persistence context before the find. Therefore, do not write:

```java
BookEntity fresh = testEntityManager.persistFlushFind(
        new BookEntity("ISBN-006", "Demo"));
assertNotSame(original, fresh); // Not guaranteed in Boot 3.3!
```

The snippet above is a **counterexample** (and references an undefined `original`), shown only to emphasize not using an invalid identity assertion. When you want to prove **the first-level cache was bypassed**, use an explicit **`persist → flush → clear → find`** sequence and assert the new entity is not the same instance as the pre-clear entity.

An application upgrading to another Boot version should check the corresponding Javadoc/source; helper implementations can change without altering the nature of standard JPA methods.

## 9. Setting Up a Runnable Java 17+ / Spring Boot 3.3.5 Project

We create a small project with a single `BookEntity`, a Spring Data JPA repository, and `@DataJpaTest` using H2. There is no web server, external service, or production database.

Directory structure:

```text
jpa-test-entity-manager/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/jpatest/
│   ├── JpaTestApplication.java
│   ├── BookEntity.java
│   └── BookRepository.java
└── src/test/java/com/example/jpatest/
    └── BookPersistenceTest.java
```

### 9.1. settings.gradle

```groovy
rootProject.name = 'jpa-test-entity-manager'
```

### 9.2. build.gradle

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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
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

- `spring-boot-starter-data-jpa` provides JPA, Hibernate, and Spring Data repositories.
- `h2` at test runtime provides an embedded DB suited for the JPA slice without needing database accounts.
- `spring-boot-starter-test` brings JUnit Jupiter, AssertJ, and Spring Test.
- `junit-platform-launcher` lets Gradle execute JUnit Platform tests per configuration.

When a project uses Flyway/Liquibase or a real DataSource, schema creation/test database rules must be handled separately. In the **sample project** below, we instruct Hibernate `create-drop` to create the schema from the entity model in the test H2 database.

### 9.3. Application Root

`src/main/java/com/example/jpatest/JpaTestApplication.java`:

```java
package com.example.jpatest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpaTestApplication.class, args);
    }
}
```

`@DataJpaTest` discovers this `@SpringBootConfiguration`/`@SpringBootApplication` from the test's package. Running `main()` is not needed to test the repository.

### 9.4. Entity Using GenerationType.SEQUENCE

`src/main/java/com/example/jpatest/BookEntity.java`:

```java
package com.example.jpatest;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_books")
public class BookEntity {

    @Id
    @GeneratedValue(
            strategy = GenerationType.SEQUENCE,
            generator = "catalog_book_id_generator")
    @SequenceGenerator(
            name = "catalog_book_id_generator",
            sequenceName = "catalog_book_id_seq",
            allocationSize = 1)
    private Long id;

    @Column(nullable = false, unique = true, length = 32)
    private String isbn;

    @Column(nullable = false, length = 160)
    private String title;

    protected BookEntity() {
        // Constructor for the JPA provider.
    }

    public BookEntity(String isbn, String title) {
        if (isbn == null || isbn.isBlank()) {
            throw new IllegalArgumentException("isbn is required");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
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

    public void changeTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        this.title = title;
    }
}
```

**Why not use a Java record as a JPA entity?** A JPA entity generally needs a class with a no-arg constructor (at least protected), identity, and managed state/dirty checking. Records are final and immutable, making them unsuitable as the default for Hibernate JPA entities like this. Records remain great for DTOs or projections.

**Why use SEQUENCE?** H2 supports database sequences; Hibernate can assign an ID at persist time while deferring the INSERT until flush. Using `IDENTITY` changes the timing story because the provider typically needs an early INSERT to retrieve the generated ID. Even with `SEQUENCE`, do not assert exact SQL counts/timings across every database/provider without proper measurement mechanisms.

**Why have a unique ISBN?** To discuss database constraints and when flush validates errors. The runnable tests below focus on the successful persistence flow; testing constraint failures requires separate tests and care because a failed transaction may no longer be usable.

### 9.5. Repository Interface

`src/main/java/com/example/jpatest/BookRepository.java`:

```java
package com.example.jpatest;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository
        extends JpaRepository<BookEntity, Long> {

    Optional<BookEntity> findByIsbn(String isbn);

    long countByTitle(String title);
}
```

Spring Data JPA implements the derived query methods `findByIsbn` and `countByTitle`. A repository test should protect real methods rather than merely confirming TestEntityManager reads back the exact entity it persisted.

## 10. Complete Test Suite Using TestEntityManager

Create `src/test/java/com/example/jpatest/BookPersistenceTest.java`:

```java
package com.example.jpatest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
class BookPersistenceTest {

    @Autowired
    TestEntityManager entities;

    @Autowired
    BookRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void persistFlushClearFindReloadsEntity() {
        BookEntity initial = entities.persist(
                new BookEntity("ISBN-101", "JPA basics"));

        Long id = initial.getId();
        assertNotNull(id);

        entities.flush();
        entities.clear();

        assertFalse(
                entities.getEntityManager().contains(initial));

        BookEntity loaded = entities.find(BookEntity.class, id);
        assertNotNull(loaded);
        assertNotSame(initial, loaded);
        assertEquals("ISBN-101", loaded.getIsbn());
        assertEquals("JPA basics", loaded.getTitle());
        assertTrue(entities.getEntityManager().contains(loaded));
    }

    @Test
    void findWithoutClearCanReturnSameManagedInstance() {
        BookEntity initial = entities.persistAndFlush(
                new BookEntity("ISBN-102", "First level cache"));

        BookEntity found = entities.find(
                BookEntity.class, initial.getId());

        assertSame(initial, found);
    }

    @Test
    void clearDiscardsUnflushedManagedChanges() {
        BookEntity initial = entities.persistAndFlush(
                new BookEntity("ISBN-103", "Original"));

        Long id = initial.getId();
        initial.changeTitle("Not flushed");

        entities.clear();

        BookEntity loaded = entities.find(BookEntity.class, id);
        assertNotNull(loaded);
        assertEquals("Original", loaded.getTitle());
    }

    @Test
    void managedChangesPersistAfterFlushAndClear() {
        BookEntity initial = entities.persistAndFlush(
                new BookEntity("ISBN-104", "Before"));
        Long id = initial.getId();

        entities.clear();

        BookEntity managed = entities.find(BookEntity.class, id);
        assertNotNull(managed);
        managed.changeTitle("After");

        entities.flush();
        entities.clear();

        BookEntity loaded = entities.find(BookEntity.class, id);
        assertNotNull(loaded);
        assertEquals("After", loaded.getTitle());
    }

    @Test
    void repositoryFindByIsbnReadsFixtureAfterClear() {
        BookEntity initial = entities.persistAndFlush(
                new BookEntity("ISBN-105", "Repository query"));
        Long id = initial.getId();

        entities.clear();

        BookEntity found = repository
                .findByIsbn("ISBN-105")
                .orElseThrow();

        assertEquals(id, found.getId());
        assertEquals("Repository query", found.getTitle());
    }

    @Test
    void repositorySaveIsVisibleToEntityManager() {
        BookEntity saved = repository.save(
                new BookEntity("ISBN-106", "Saved by repository"));
        Long id = saved.getId();

        assertNotNull(id);
        entities.flush();
        entities.clear();

        BookEntity found = entities.find(BookEntity.class, id);
        assertNotNull(found);
        assertEquals("Saved by repository", found.getTitle());
    }

    @Test
    void findReturnsNullForMissingPrimaryKey() {
        BookEntity missing = entities.find(
                BookEntity.class, 999999999L);

        assertNull(missing);
    }

    @Test
    void persistAndGetIdCanReturnTypedIdentifier() {
        Long id = entities.persistAndGetId(
                new BookEntity("ISBN-107", "Identifier helper"),
                Long.class);

        assertNotNull(id);
        entities.flush();
        entities.clear();

        BookEntity found = entities.find(BookEntity.class, id);
        assertNotNull(found);
        assertEquals("ISBN-107", found.getIsbn());
    }

    @Test
    void persistFlushFindHelperReturnsMatchingEntity() {
        BookEntity found = entities.persistFlushFind(
                new BookEntity("ISBN-108", "Convenience method"));

        assertNotNull(found);
        Long id = found.getId();
        assertNotNull(id);
        assertEquals("Convenience method", found.getTitle());

        // Boot 3.3 helper does not guarantee L1 cache clear.
        entities.clear();
        BookEntity reloaded = entities.find(BookEntity.class, id);
        assertNotNull(reloaded);
        assertEquals("Convenience method", reloaded.getTitle());
    }

    @Test
    void detachOneEntityPreventsUnflushedUpdate() {
        BookEntity initial = entities.persistAndFlush(
                new BookEntity("ISBN-109", "Stored"));
        Long id = initial.getId();

        initial.changeTitle("Detached change");
        entities.detach(initial);

        assertFalse(
                entities.getEntityManager().contains(initial));

        entities.flush();
        entities.clear();

        BookEntity loaded = entities.find(BookEntity.class, id);
        assertNotNull(loaded);
        assertEquals("Stored", loaded.getTitle());
    }

    @Test
    void mergeCopiesDetachedStateToManagedInstance() {
        BookEntity detached = entities.persistAndFlush(
                new BookEntity("ISBN-110", "Before merge"));
        Long id = detached.getId();

        entities.clear();
        detached.changeTitle("After merge");

        BookEntity managed = entities.merge(detached);
        assertNotSame(detached, managed);

        entities.flush();
        entities.clear();

        BookEntity loaded = entities.find(BookEntity.class, id);
        assertNotNull(loaded);
        assertEquals("After merge", loaded.getTitle());
    }

    @Test
    void refreshRestoresFlushedDatabaseValue() {
        BookEntity managed = entities.persistAndFlush(
                new BookEntity("ISBN-111", "Persisted title"));

        managed.changeTitle("Only in memory");

        entities.refresh(managed);

        assertEquals("Persisted title", managed.getTitle());
    }

    @Test
    void repositoryCountUsesFlushedRows() {
        entities.persistAndFlush(
                new BookEntity("ISBN-112", "Count target"));
        entities.clear();

        assertEquals(1L, repository.countByTitle("Count target"));
    }

    @Test
    void jdbcSeesFlushedInsertInsideSameTransaction() {
        BookEntity entity = entities.persist(
                new BookEntity("ISBN-113", "JDBC check"));

        entities.flush();

        Long count = jdbc.queryForObject(
                "select count(*) from catalog_books where isbn = ?",
                Long.class,
                entity.getIsbn());

        assertEquals(1L, count);
    }
}
```

**There are 14 `@Test` methods** in this class. They are designed for the Boot 3.3.5, Hibernate, and H2 demo project on the test runtime classpath. This is a reproducible sample test suite; **we do not claim Gradle was executed at the time of writing**.

### 10.1. How to Read Each Test and What It Actually Proves

| Test Method | Core Operation Sequence | Evidence |
| --- | --- | --- |
| `persistFlushClearFindReloadsEntity` | persist → flush → clear → find | Entity after clear has synchronized state and is a distinct instance |
| `findWithoutClearCanReturnSameManagedInstance` | persistAndFlush → find | L1 context can return the exact same object |
| `clearDiscardsUnflushedManagedChanges` | persistAndFlush → mutate → clear → find | Unflushed managed field edits can be discarded |
| `managedChangesPersistAfterFlushAndClear` | persist/flush → clear → find/mutate → flush/clear/find | Dirty checking synchronizes updates to a managed entity |
| `repositoryFindByIsbnReadsFixtureAfterClear` | persistAndFlush → clear → repository query | Derived query finds the fixture across a fresh context/database |
| `repositorySaveIsVisibleToEntityManager` | repository.save → flush → clear → find | Repository writes an entity JPA can reload |
| `findReturnsNullForMissingPrimaryKey` | find nonexistent ID | `find` API returns null when missing |
| `persistAndGetIdCanReturnTypedIdentifier` | persistAndGetId → flush → clear → find | Helper returns typed ID and entity can be looked up again |
| `persistFlushFindHelperReturnsMatchingEntity` | persistFlushFind → clear → find | Helper persist/flush/find works; extra clear checks outside L1 |
| `detachOneEntityPreventsUnflushedUpdate` | mutate → detach → flush/clear/find | Detached mutations are not synchronized by dirty checking |
| `mergeCopiesDetachedStateToManagedInstance` | clear → mutate detached → merge → flush/clear/find | `merge` returns a managed copy with updated state |
| `refreshRestoresFlushedDatabaseValue` | persistAndFlush → mutate → refresh | Refresh overwrites unflushed edits with DB state |
| `repositoryCountUsesFlushedRows` | persistAndFlush → clear → derived count | Repository query sees fixture matching condition |
| `jdbcSeesFlushedInsertInsideSameTransaction` | persist → flush → JDBC COUNT | JDBC sees the row inside the same transaction |

**Important limitation:** `jdbcSeesFlushedInsertInsideSameTransaction` uses `JdbcTemplate` over the test's own transaction/DataSource. It confirms SQL row visibility within that transaction, **not that a client in another transaction sees a committed row**. Under default transaction isolation, an external session normally cannot read uncommitted data.

### 10.2. Why Is assertNotSame After clear Useful?

In `persistFlushClearFindReloadsEntity`:

1. `initial` is the managed entity after persist.
2. `flush` synchronizes pending SQL.
3. `clear` detaches `initial`.
4. `find` retrieves a managed entity in the reset context.
5. `assertNotSame(initial, loaded)` shows `find` did not return the same `initial` reference from the old first-level cache.
6. `assertEquals(...)` confirms key data can be read back.

If the application enables a second-level cache, a query after clear might read from the L2 cache; `assertNotSame` **does not by itself prove** a SELECT hit the database. For this sample project without L2 cache enabled, this sequence remains the standard way to avoid tests that merely read the same managed object.

### 10.3. Why Test Mutations Around clear?

`clearDiscardsUnflushedManagedChanges` has two versions of the title:

- Flushed version: `Original`.
- In-memory edit: `Not flushed`.

After `clear`, the old entity is detached; dirty checking no longer applies. `find` receives `Original`. If the test omitted the initial `flush`, there might be no record to reload, leading to misdiagnosis.

In `managedChangesPersistAfterFlushAndClear`, the test loads the managed entity, changes the title, calls `flush`, and then `clear`. The subsequent find must return `After`. This pair of tests shows that **flushing before clearing** is the decisive boundary for dirty checking.

### 10.4. Role of JdbcTemplate

`JdbcTemplate` here is configured by the Spring Boot JPA test slice to query the same H2 DataSource. It does not use the JPA first-level cache. A SQL `COUNT(*)` after flush verifies that the row exists in the underlying database **within the current transaction**.

Do not hard-code a SQL table name different from the `@Table(name="catalog_books")` mapping. If using another schema or naming strategy, raw SQL must be adjusted manually; unlike JPQL, it does not follow entity names automatically.

### 10.5. Why Do All Test Fixtures Use Different ISBNs?

The example uses `ISBN-101` through `ISBN-113` so each case is clearly independent just by reading the code. Although `@DataJpaTest` rolls back by default, tests must still never rely on execution order or reuse an auto-incremented ID expected to equal a specific number. When testing transaction commit/rollback across multiple contexts, intentionally create and clean up fixtures in an isolated environment.

## 11. How Do EntityManager and Repository Work Best Together in Tests?

A solid pattern for testing a derived query:

```java
BookEntity fixture = entities.persistAndFlush(
        new BookEntity("ISBN-200", "Spring Data Guide"));
entities.clear();

BookEntity actual = repository
        .findByIsbn("ISBN-200")
        .orElseThrow();

assertEquals(fixture.getId(), actual.getId());
assertEquals("Spring Data Guide", actual.getTitle());
```

This snippet builds on the classes already created in the project and fits inside a test method. It separates:

- **Arrange:** `TestEntityManager` stores the fixture.
- **Act:** `BookRepository` executes the exact query under test.
- **Assert:** the found entity has the expected ID and title.

Conversely, a test calling repository `save` then repository `findById` is not useless, yet it mainly checks the happy path of that abstraction itself and may not expose mapping issues after clearing the persistence context. For complex queries, prepare fixtures with TestEntityManager and cover filtering/sorting/pagination cases.

### Testing @Query and Lazy Relations

If an entity has `@ManyToOne`, `@OneToMany`, or a `LAZY` fetch policy, `clear` enables more realistic verification: after clear, the repository must load the entity/association according to the mapping. However, avoid accessing a lazy association on a **detached entity** after the transaction closes, as that can throw `LazyInitializationException`.

In `@DataJpaTest`, a transaction is active by default during the test method; after `clear` and `find`, the new entity is managed, so accessing a lazy relation can load it if the provider allows. To inspect N+1/SQL counts, use instrumentation like Hibernate Statistics or datasource-proxy; do not infer SELECT counts solely from `assertNotSame`.

### Testing Projections and DTOs

`TestEntityManager` is great for creating entity fixtures, while the act step can call a repository method returning a DTO projection, interface projection, or `Page<T>`. Assert on actual projection fields rather than only checking that the fixture was saved. For pagination, specify an explicit sort order instead of relying on default SQL table order.

## 12. Special Note: Flush Does Not Mean Transaction Commit

Spring `@DataJpaTest` is transactional by default and rolls back after each method. Thus:

```text
Test method begins
  ├─ Transaction BEGIN
  ├─ persist(Book)
  ├─ flush()       -> INSERT inside transaction
  ├─ clear()
  ├─ find(Book,id) -> found inside the same transaction
  └─ Test ends     -> ROLLBACK

Another test method cannot use fixtures from that transaction
```

Finding a record inside the same transaction is not proof it was committed. This holds for H2 and most RDBMS engines with transaction isolation.

### What If You Need to Test Real Transaction Boundaries?

Spring Test provides `TestTransaction` when tests run inside a framework-managed transaction. An advanced scenario can:

1. Persist/flush an entity in the test transaction.
2. Call `TestTransaction.flagForRollback()`.
3. End the transaction with `TestTransaction.end()`.
4. Start a new transaction with `TestTransaction.start()`.
5. Re-query to verify the row is gone.

This is an **extension approach**, excluded from the 14 runnable tests of the lesson, because manually ending/starting transactions requires careful lifecycle and cleanup control. If a test truly commits, use a dedicated test database and delete the data afterward—never run it against a production DB.

A test running with `@Transactional(propagation = Propagation.NOT_SUPPORTED)` or without a transaction may not be able to use `TestEntityManager` `flush` operations like the default; `EntityManager.flush()` requires an active transaction and may throw `TransactionRequiredException`.

## 13. Detecting Database Constraints with flush

Suppose the entity has:

```java
@Column(nullable = false, unique = true, length = 32)
private String isbn;
```

The schema Hibernate creates for H2 can enforce a unique constraint on ISBN. A test can persist two entities with the same ISBN and then flush:

```java
entities.persistAndFlush(
        new BookEntity("ISBN-DUP", "First"));
entities.persist(
        new BookEntity("ISBN-DUP", "Second"));

assertThrows(RuntimeException.class, entities::flush);
```

This is a **scenario snippet**, missing imports, and must be placed in a **separate test method**. Asserting `RuntimeException` only demonstrates timing; it is **insufficient to protect the right constraint**. Production tests should inspect the root cause/SQLState/error type appropriate for the database and current stack's exception translation, such as Jakarta `PersistenceException` or Spring `DataIntegrityViolationException` when translated at a repository boundary.

**Do not keep using the same transaction as if no error occurred.** After a constraint violation, the JPA provider typically marks the transaction rollback-only or leaves the session in an unsafe state. Let the test roll back and start a fresh test for another scenario.

### Why Not Assert Throw Immediately at persist()?

Because `GenerationType.SEQUENCE` in the demo usually defers the INSERT; the database unique constraint can only be detected when SQL is sent at flush. In other mappings/providers, INSERT may occur earlier. Tests should focus on **the database enforcing the constraint**, without locking onto an arbitrary moment if the code supports multiple databases.

### Do Not Trust @Column(unique=true) Alone

`@Column(unique=true)` is metadata for schema generation, not a substitute for deployed migrations. In production using Flyway/Liquibase, the unique index must exist in the real migration/schema. A passing H2 `create-drop` test does not prove the production database has the right unique constraint; check migrations and test against a production-compatible database when needed.

## 14. Other Helpers: detach, merge, refresh, and remove

`TestEntityManager` includes several methods beyond the core four operations:

### detach(entity)

Detaches **a single** entity, whereas `clear` detaches all entities. A detached entity modified in memory does not flush automatically. `detachOneEntityPreventsUnflushedUpdate` demonstrates this exact behavior.

### merge(entity)

When a detached entity has changes that need to enter the persistence context:

```java
BookEntity managedCopy = entities.merge(detached);
```

`merge` returns a **managed instance**, which can differ from the original detached object. Work with `managedCopy` afterward; do not assume the original detached reference became re-attached. When associations and cascade `MERGE` exist, verify behavior per mapping.

### refresh(entity)

`refresh` reloads database state into a **managed** entity, overwriting unflushed in-memory changes. For a detached entity, `refresh` may throw `IllegalArgumentException` or a provider-specific error; it is not a way to “reattach” an entity.

### remove(entity)

`remove` marks a managed entity for deletion; the DELETE statement executes per flush/commit. After `remove`, to test that the database no longer has the row within the transaction, you can use `flush + clear + find == null`; however, account for soft deletes, cascades, and foreign keys on real entities.

### getEntityManager()

`entities.getEntityManager()` exposes standard JPA APIs such as `contains`, `createQuery`, `setFlushMode`, `lock`, or provider unwrapping. When testing the four core operations, keep TestEntityManager usage simple rather than overusing provider-specific APIs.

## 15. Common Pitfalls: Frequent False Claims

### 15.1. persist Already Has an ID, So the DB Has the Row

**False.** A generated ID may be obtained from a sequence before INSERT flushes. An ID is not proof that the transaction committed or even that the INSERT ran.

### 15.2. flush Means commit

**False.** Flush synchronizes within the transaction, which can still roll back. In `@DataJpaTest`, rollback is the default behavior.

### 15.3. clear Deletes the Database

**False.** Clear detaches entities from the first-level context; flushed rows remain in the transaction until rollback/commit.

### 15.4. find After persist Definitely Runs a SELECT

**False.** When an entity is managed, `find` typically returns the instance from the first-level cache. Clear before `find` if your goal is to test loading outside the old context.

### 15.5. clear Automatically Flushes Pending Changes

**False.** Unflushed updates can be lost after `clear`. Explicitly flush whenever changes must be preserved.

### 15.6. persistFlushFind Always Creates a New Java Object

**Cannot be claimed in Boot 3.3.** This version's Javadoc describes `persistAndFlush` followed by `find`, with no guarantee of `clear`. Check the API for your version; use separate flush+clear+find if the identity/load boundary is the goal.

### 15.7. find After clear Definitely Issues a SELECT

**Not always true.** The L1 cache is reset, yet if an L2 cache or provider optimization exists, no SELECT may be issued. To count SQL, use proper instrumentation.

### 15.8. @DataJpaTest Loads All Application Beans

**False.** The JPA slice focuses on entities/repositories and related infrastructure; regular services/controllers are not auto-scanned. For service transaction tests with multiple collaborators, use a broader configuration or targeted `@Import`.

### 15.9. Using H2 Is Enough to Prove Production PostgreSQL/MySQL

**Insufficient.** SQL dialect, locking, transaction isolation, sequence/identity, JSON columns, case sensitivity, and constraints can differ. When behavior relies on database-specific features, use Testcontainers with the same database type or an appropriate integration environment.

### 15.10. Tests Relying on Execution Order and Sequential IDs

**Unstable.** Test transaction rollbacks do not necessarily reset sequences to prior values. Never assert that the first ID equals 1; instead use `assertNotNull(id)` and compare reloaded IDs.

### 15.11. Mixing javax.persistence and jakarta.persistence

**Wrong in Boot 3.x.** Use `jakarta.persistence.*` with Jakarta Persistence/Hibernate 6. Importing `javax.persistence.*` from a Boot 2 project can break entity mappings/tests or fail compilation.

### 15.12. Calling flush Without a Transaction

`EntityManager.flush()` requires a transaction per JPA. If you disable `@DataJpaTest`'s default transaction, manage transactions explicitly instead of calling `flush` in an unsupported context.

## 16. Optimizing Test Speed and Isolation

`@DataJpaTest` is typically lighter than `@SpringBootTest` because it only loads the JPA slice. Even so, creating EntityManagerFactory/Hibernate metadata and the H2 schema takes time; group tests sharing configuration to leverage the Spring TestContext cache.

Things to safeguard:

- Tests must not rely on fixtures left by another test method.
- Do not use `@Order` to force test A to run before test B.
- Do not keep static mutable caches for entities/IDs.
- Avoid putting `@DirtiesContext` on every test unless it genuinely alters the application context.
- If a test enables commits, delete data afterward.
- If parallel tests share a database/schema, isolate IDs/fixtures and control schema resets.
- SQL logging helps debugging, but never treat log output as an unstable test assertion.
- To prove query count and N+1, use Hibernate Statistics/datasource instrumentation with a concrete context/provider rather than guessing from repository call counts.

### Interaction with Transaction Isolation

A `JdbcTemplate` sharing the Spring-managed transaction sees flushed data, while another transaction might not due to isolation. When testing concurrency, read-committed, repeatable-read, or locking, use multiple controlled transactions/connections rather than just calling `clear()` inside one transaction.

### H2 in Test Runtime

Using embedded H2 makes sense for basic repository CRUD/mapping tests. However, Hibernate DDL `create-drop` only suits sandbox tests; in applications using migrations, prefer running the real schema managed by Flyway/Liquibase. Never set `spring.jpa.hibernate.ddl-auto=create-drop` in production.

## 17. Comparing a Weak Test with a Strong Test

**Weak test:**

```java
BookEntity saved = entities.persist(
        new BookEntity("ISBN-300", "Book"));
assertNotNull(saved.getId());

BookEntity found = entities.find(
        BookEntity.class, saved.getId());
assertEquals("Book", found.getTitle());
```

This test can PASS without checking SQL INSERT, because the ID may come from a sequence and `find` returns the managed object.

**Stronger test:**

```java
BookEntity saved = entities.persist(
        new BookEntity("ISBN-300", "Book"));
Long id = saved.getId();

entities.flush();
entities.clear();

BookEntity found = entities.find(BookEntity.class, id);

assertNotNull(found);
assertNotSame(saved, found);
assertEquals("Book", found.getTitle());
```

After `clear`, the lookup cannot return the old reference from the first-level context. If you also need to prove the database received the row, add a JDBC query **within the current transaction** like `jdbcSeesFlushedInsertInsideSameTransaction`.

**Never call a test “committed” simply because it uses flush+clear+find.** That tests database-state synchronization and the persistence-context boundary, not commit verification.

## 18. Troubleshooting by Symptom

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `No qualifying bean of type TestEntityManager` | Not using `@DataJpaTest` or missing `@AutoConfigureTestEntityManager` | Use the JPA test slice; if in another test context, configure support explicitly |
| `Unable to find a @SpringBootConfiguration` | Test is outside the application root package hierarchy | Move to the appropriate package or specify test configuration |
| `TransactionRequiredException` on flush | No active transaction | Use `@DataJpaTest`'s transactional default or declare a transaction |
| `Table not found` / schema error | H2 DDL/migrations/schema not initialized | Check JPA DDL settings, datasource, Flyway/Liquibase |
| ID null after persist | Strategy/assignment/provider differs from assumption | Check `@GeneratedValue`, `SEQUENCE`, and provider |
| Test PASSES before clear but FAILS after clear | Unflushed changes or broken mapping/SQL | Flush explicitly before clear; inspect root cause |
| `find` returns the same object before clear | L1 cache working as designed | Use clear when loading outside the old context |
| `find` returns null after clear | Insert not flushed, wrong ID, or row deleted/rolled back | Check persist/flush order and transaction |
| `find` after clear still issues no SELECT | L2 cache or provider optimization | Do not guess from code; measure with SQL instrumentation |
| Detached field edits not saved | Detached objects are not dirty-checked | Merge or load a managed instance and modify it |
| `LazyInitializationException` | Accessing lazy relation when detached/outside session | Design appropriate fetch plans/transactions |
| Duplicate ISBN only fails on flush | Unique constraint checked when SQL executes | Test constraints in a separate transaction |
| Unique constraint PASSES on H2 but fails in production | Different dialect/schema/migrations | Use Testcontainers for the same DB engine |
| Repository test cannot find service bean | `@DataJpaTest` loads only the slice | Import collaborators or use `@SpringBootTest` when needed |
| Test IDs change across runs | Sequences do not reset on rollback | Never assert fixed IDs |
| N+1/SQL performance goes undetected | Test checks only Java entity state | Use SQL counts/statistics with larger datasets |

### When Facing Failed to load ApplicationContext

Read the specific **Caused by** rather than just the wrapper message. Different causes require different fixes: DataSource error, dialect, entity mapping, schema migration, repository query parsing, or bean wiring. Do not switch to `@SpringBootTest` just to avoid figuring out why the JPA slice failed to load.

## 19. Hands-On Exercises

Using the project in sections 9–10:

1. Run `persistFlushClearFindReloadsEntity`, remove `clear`, and change the assertion to `assertSame(initial, loaded)`. Explain why it no longer tests loading after a context reset.
2. Call `persist` and inspect the ID, **without flushing**. Why does a non-null ID not prove the INSERT ran?
3. In `clearDiscardsUnflushedManagedChanges`, add `flush` after `changeTitle("Not flushed")` before clearing; update the expected title to `Not flushed`.
4. In `managedChangesPersistAfterFlushAndClear`, try removing the second `flush` and predict the result after `clear`.
5. Change `GenerationType.SEQUENCE` to `IDENTITY` in a sandbox, observe SQL INSERT timing, and explain the difference.
6. Try calling `repository.findByIsbn(...)` immediately after `persist` versus after `flush+clear`; explain how auto-flush can mask a test's assumptions.
7. Write a new test for a nonexistent ISBN; the repository returns `Optional.empty()`, whereas `TestEntityManager.find` returns `null`.
8. Add a duplicate unique ISBN case in a **separate test**, identify the exception type/root cause in H2, and avoid running further JPA operations in the failed transaction.
9. Split transactions with `TestTransaction` to prove `flush` is not `commit`, never running against a production DB.
10. Try `TestEntityManager.persistAndGetId(...)` with `Long.class`; do not assert ID equals 1.
11. Try `persistFlushFind` on Boot 3.3 and inspect instance identity before/after **explicit clear**; read the exact Javadoc for your version.
12. Use `JdbcTemplate` to query `catalog_books` after flush to confirm the row is synchronized in the current transaction.
13. Add a `@ManyToOne(fetch=LAZY)` association and test repository fetch behavior after clear; when measuring query counts, use instrumentation rather than inferring from `assertNotSame`.
14. Run similar tests against PostgreSQL Testcontainers to compare H2 on schemas, sequences, and constraints.
15. Verify the actual Gradle test report lists **14 @Test** methods with sensible FAIL/SKIPPED counts; do not treat sample code counts as executed CI results.

## 20. Checklist Before Merging JPA Tests

- [ ] Is the test meant to check entity mapping, repository queries, database constraints, or transaction boundaries?
- [ ] Does `@DataJpaTest` load the right entities/repositories and use an appropriate test datasource?
- [ ] Does the entity have a no-arg constructor, `@Id`, ID strategy, and `jakarta.persistence` annotations matching Boot 3.x?
- [ ] Are fixtures created with `persist`/`persistAndFlush` and given ISBNs/IDs independent of other tests?
- [ ] If DB synchronization is needed, is `flush` called at the right place?
- [ ] If reading outside the L1 context is needed, is `clear` called before `find`/repository queries?
- [ ] Avoided confusing `clear` with deleting database data or `flush` with committing?
- [ ] For detached entities, avoided expecting mutations to save automatically; used `merge` or a managed instance when needed?
- [ ] Tested both success and invalid/constraint cases when domain rules require them?
- [ ] Isolated unique/foreign key violations in separate tests without reusing a failed transaction?
- [ ] Avoided using `persistFlushFind` as default proof that the L1 cache cleared on Boot 3.3?
- [ ] Does the test avoid relying on fixed IDs, test method ordering, or sequence rollback?
- [ ] Have SQL constraints/migrations on a production-compatible database been verified when needed?
- [ ] Distinguished a query in the same transaction from external committed visibility?
- [ ] Avoided bypassing JPA slice failures by indiscriminately switching to full `@SpringBootTest`?
- [ ] Inspected actual test reports rather than claiming tests pass solely from sample code?

## 21. Official Documentation

- [Spring Boot 3.3 — TestEntityManager API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/TestEntityManager.html): `persist`, `persistAndFlush`, `persistFlushFind`, `clear`, `find`, and helper APIs.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@DataJpaTest`, embedded database, transaction/rollback, TestEntityManager.
- [Jakarta Persistence 3.1 — EntityManager](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html): `persist`, `flush`, `clear`, `find`, managed/detached.
- [Jakarta Persistence specification](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html): lifecycle states, dirty checking, and flush modes.
- [Spring Data JPA reference — Repositories](https://docs.spring.io/spring-data/jpa/reference/repositories.html): derived queries, repository testing, and transaction behavior.
- [Spring Framework — Transactional Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions, rollback, and `TestTransaction`.

## 22. Conclusion

**`TestEntityManager` is Spring Boot's persistence-context testing tool, not a new DB or transaction manager.** `persist` makes an entity managed; `flush` synchronizes changes to the DB inside the transaction; `clear` detaches managed entities to prevent reading back from the first-level cache; `find` looks up by primary key and can return the managed instance directly if not cleared.

The **`persist → flush → clear → find`** sequence is the foundation of many reliable JPA repository tests: it verifies data after synchronization and after the old context no longer manages the original object. However, **flush does not commit**, and **clear does not guarantee invalidating a second-level cache**. On Spring Boot 3.3, the `persistFlushFind` helper is not a substitute for explicit `clear` when testing the L1 cache boundary. Combining JUnit Jupiter, `@DataJpaTest`, TestEntityManager, repository queries, and targeted JDBC assertions clearly separates mapping, caching, transaction, and database state bugs.