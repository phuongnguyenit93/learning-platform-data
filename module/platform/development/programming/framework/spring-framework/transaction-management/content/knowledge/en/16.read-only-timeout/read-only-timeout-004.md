# Impact of Read-Only Transactions on Flushing and ORM Optimization in the Spring Framework

## 1. The Problem: Reading Data While the ORM Still Has to Manage Entities

A Spring service using JPA/Hibernate frequently loads dozens or thousands of entities to build reports, API responses, or lists. When entities are in the **managed** state, the ORM may store a snapshot of the initial state, track changes, and check whether `UPDATE` statements need to be generated. This incurs memory and CPU costs, even when the business logic only intends to read.

Spring allows declaring the intent:

~~~java
@Transactional(readOnly = true)
public BookDto loadBook(long id) {
    // Read and return data, without intending to modify the DB.
}
~~~

The snippet above **merely illustrates syntax** and is not a standalone program. Depending on the Spring transaction manager and ORM provider, `readOnly = true` can be passed down to the JDBC and Hibernate layers as an **optimization hint**. In common Spring + Hibernate configurations, it also affects the **flush mode** and **dirty checking**.

Questions this lesson answers:

1. What is **flush**, and how does it differ from **commit**?
2. Why does `readOnly=true` often cause Hibernate to use `FlushMode.MANUAL`?
3. Why can Hibernate reduce dirty checking/snapshots for entities loaded inside a read-only transaction?
4. Why is `readOnly=true` **not a safety lock** preventing every `INSERT`, `UPDATE`, or `DELETE` statement?
5. When does this benefit take effect, and when is it limited by propagation, the persistence context, and the transaction manager?
6. What impact does `timeout` have on long queries, the flush step, and performance?
7. How do you write a Java 17+ example to check both **values in the object** and **data actually committed**?

Main scope: **Spring Framework Transaction Management + Spring Data JPA/Hibernate ORM** with imperative thread-bound transactions. Hibernate-specific details will be named explicitly and should not be treated as mandatory rules for every JPA provider.

## 2. Distinguishing Persistence Context, Dirty Checking, Flush, and Commit

These four concepts are related but not synonymous.

### 2.1. Persistence Context and Managed Entities

In JPA, `EntityManager` manages a **persistence context**, typically holding entities loaded via `find` or JPQL queries. A **managed** entity can be observed by Hibernate when its properties change.

~~~java
Book book = entityManager.find(Book.class, 1L);
book.setTitle("New title");
// Java object modified; cannot yet conclude there is an UPDATE SQL or commit.
~~~

This is an **illustrative code fragment** inside an appropriate transaction. You do not need to call `repository.save(book)` for every change on a managed entity: in a read-write transaction, Hibernate can detect the change and flush it into SQL later.

### 2.2. Dirty Checking

**Dirty checking** is the process by which the ORM determines which managed entities have changed compared to their previously loaded/synchronized state.

With Hibernate, when using snapshot-based dirty checking, the ORM compares the current state against the snapshot. Bytecode enhancement can track modified properties to reduce comparison cost, though it does not eliminate dirty checking altogether.

Potential costs include:

- Storing the state of many managed entities in the persistence context.
- Comparing or tracking modified properties at flush time.
- Maintaining the action queue, handling relationships/cascades, and SQL ordering.
- Increasing heap usage, GC time, and transaction hold time if a single read loads too many entities.

For long read queries, you may only need to map entities to DTOs/projections and return them. If there is no intention to write, some of the ORM work above is reducible overhead.

### 2.3. Flush: Synchronizing Managed State into SQL

**Flush** tells the ORM to synchronize pending changes from the persistence context down to the database, typically via appropriate `INSERT`, `UPDATE`, and `DELETE` statements. Flush **is not necessarily commit**.

~~~text
Managed entity has a property modified
  -> Hibernate identifies pending changes
  -> FLUSH: sends SQL into the DB transaction
  -> COMMIT: ends the transaction, making changes durably effective
~~~

Example inside a transaction:

~~~java
book.setTitle("Draft");
entityManager.flush(); // May emit UPDATE SQL immediately.
throw new IllegalStateException("rollback");
// Transaction rolls back: the flushed UPDATE is still undone.
~~~

This snippet is **illustrative code**, accurate only when the entity is modifiable, an actual transaction exists, and no other mechanism prevents flushing. `flush()` does not turn changes into committed state. In most cases, only after a successful commit can you say the transaction is finalized.

### 2.4. Automatic Flushing Depends on Mode

Standard JPA has `FlushModeType.AUTO` and `FlushModeType.COMMIT`. Hibernate also has its own values such as `FlushMode.AUTO`, `COMMIT`, `MANUAL`, and `ALWAYS` (depending on version).

- **`AUTO`**: Hibernate may flush before commit and before queries when needed so query results reflect pending changes. There is no rule saying "every SELECT flushes".
- **`COMMIT`**: defers automatic flushing primarily until commit; pre-query behavior depends on JPA/provider.
- **`MANUAL`** (Hibernate-specific): Hibernate does not automatically flush on usual triggers; the user must flush explicitly to synchronize pending state. However, explicit SQL statements, sequence/identity handling, or other mechanisms can still emit SQL.
- **`ALWAYS`** (Hibernate-specific): may flush more frequently, including before queries.

**Note on API names:** `jakarta.persistence.FlushModeType` does not have `MANUAL`. If you write `FlushModeType.MANUAL`, the code will not compile. The `MANUAL` value in this lesson is `org.hibernate.FlushMode.MANUAL`.

## 3. What Does `@Transactional(readOnly = true)` Actually Do?

Spring's `@Transactional(readOnly = true)` expresses **intent**: this transaction is primarily read-only. `readOnly` is a transaction attribute processed by the transaction manager when a transaction is created or resources are prepared.

With **Spring + Hibernate/JPA** in a common setup:

1. The Spring transaction infrastructure receives the `readOnly=true` attribute.
2. `JpaTransactionManager`/`HibernateJpaDialect` can propagate metadata down to the JDBC connection as `Connection.setReadOnly(true)`, if dialect/connection handling permits.
3. The Hibernate Session's flush mode is set to **`MANUAL`**, reducing/eliminating automatic flushing inside the read-only scope.
4. For a transaction-local `EntityManager` prepared by Spring, the Hibernate Session may also be set to **`setDefaultReadOnly(true)`**. Entities loaded afterward are read-only by default; Hibernate does not need to dirty-check simple properties of those entities the way it does for read-write entities.

**The primary value is reducing ORM work when reading**, especially with many managed entities. However, do not treat these steps as an identical guarantee across all Spring/Hibernate versions, JPA providers, transaction managers, and ways of opening an `EntityManager`.

### Three Layers to Distinguish

| Layer | Read-Only Signal | Main Meaning |
| --- | --- | --- |
| Spring transaction metadata | `@Transactional(readOnly = true)` or `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` | Spring/caller declares this transaction is read-only. |
| Hibernate Session | `Session.getHibernateFlushMode() == MANUAL`, `Session.isDefaultReadOnly()` | Reduces auto-flushing, and may default to skipping dirty checks on subsequently loaded entities. |
| JDBC/database | `Connection.setReadOnly(true)` or a DB read-only transaction mode | Hint/setting on the connection; enforcement level depends on driver, DB, and configuration. |

**No layer proves 100% that every SQL write path is locked down via a single boolean.** Some DBs genuinely reject DML in read-only transactions, whereas elsewhere it is only a hint.

## 4. `FlushMode.MANUAL` and Read-Only Entities Are Not the Same Thing

These two Hibernate optimizations are related but should be kept separate.

### 4.1. `FlushMode.MANUAL`: Limiting Auto-Flushing

When the Session is in `MANUAL`, Hibernate does not automatically synchronize pending changes on the usual `AUTO` triggers. This is one reason `@Transactional(readOnly=true)` is useful when loading many entities without intending to write.

However:

- `entityManager.flush()` can request synchronization of changes on **entities that are still modifiable**.
- Bulk JPQL/native queries are **explicit data-modifying commands**, not dirty checking of entities loaded from SELECT.
- Hibernate `persist(...)` with certain identifier generation strategies and other operations can emit SQL earlier than you think at commit time.
- If the DB uses read-only enforcement, DML statements may be rejected; if the DB only receives a JDBC hint, DML statements may still run.

Thus, **MANUAL is not equivalent to "blocking all write commands"**.

### 4.2. `Session.setDefaultReadOnly(true)`: How Newly Loaded Entities Are Tracked

Hibernate also has a read-only state per **entity**:

~~~java
Session session = entityManager.unwrap(Session.class);
boolean defaultReadOnly = session.isDefaultReadOnly();
boolean entityReadOnly = session.isReadOnly(book);
~~~

The snippet above is an **API example**, requiring `import org.hibernate.Session` and `book` to be a managed entity in an appropriate transaction.

When `defaultReadOnly=true`, entities loaded afterward **by default** can be marked read-only. Hibernate does not dirty-check **ordinary scalar properties** of read-only entities to generate UPDATEs; snapshots used for simple tracking may also be omitted.

However:

- Changing `defaultReadOnly` **does not automatically change the state of previously managed entities**.
- `Session.setReadOnly(entity, true/false)` can change the state for a specific managed instance; you must understand its impact on snapshots and synchronization.
- Modifying **collections** or cascades can still produce SQL side effects depending on the mapping. Hibernate does not treat a read-only entity as strictly immutable across all associations.
- If you have a second-level cache, entity graphs, query hints, or an extended persistence context, you need to verify on your exact project setup.

### 4.3. Changing an Object in RAM Does Not Mean Changing the DB

Example:

~~~text
In a read-only transaction:
  Book loaded:     title = "Original"
  Java setter:     title = "Modified in memory"
  System.out:      "Modified in memory"
  Database:        may still be "Original" after the scope

In a read-write transaction:
  Book loaded:     title = "Original"
  Java setter:     title = "Committed"
  Hibernate dirty checking + flush at commit
  Database:        "Committed" after commit
~~~

This is a **conceptual diagram**; the demo in section 7 tests it in a concrete setup. You should not build business logic relying on "setters in read-only will be silently ignored"; that outcome depends on Hibernate and becomes a bug source if developers accidentally invoke write logic inside a read-only boundary.

## 5. Matrix: Read-Write vs. Read-Only in Spring + Hibernate

Assume both methods are called through a Spring proxy, **create a new transaction**, and use `JpaTransactionManager` with the Hibernate provider and a transaction-local `EntityManager`.

| Component | `@Transactional` (read-write) | `@Transactional(readOnly=true)` |
| --- | --- | --- |
| Service intent | May modify data | Primarily read-only |
| `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` | Usually `false` | Usually `true` |
| Hibernate flush mode | Usually `AUTO` | Usually `MANUAL` |
| Hibernate `defaultReadOnly` | Usually `false` | May be `true` with transaction-local EntityManager |
| Newly loaded entity | Usually modifiable, dirty state tracked | May default to read-only, reducing snapshots/dirty checking |
| Setter on managed entity | Can be flushed into `UPDATE` on commit | Scalar changes on a read-only entity are usually **not** synchronized |
| Explicit JPQL/native UPDATE | Can execute if permitted | **Not automatically blocked by the Spring annotation**; DB/driver may reject it |
| `entityManager.flush()` | Synchronizes pending changes, not yet committed | Still an explicit flush operation; effect depends on entity state and DB |
| Timeout | Per `timeout`/manager when creating transaction | Can also configure timeout; not an automatic consequence of readOnly |
| Commit/rollback guarantee | Depends on boundary and exceptions | Still depends on boundary and exceptions; cannot infer from hint alone |
| Performance | Good when writes and dirty checking are needed | May reduce CPU/heap for pure-read queries, must benchmark |

Words like **usually** and **may** are used because this is Spring/Hibernate integration behavior, not a JPA spec mandate requiring Hibernate `FlushMode.MANUAL` for every provider.

## 6. Using Read-Only Transactions at the Right Service Boundary

A common design:

~~~java
@Service
public class CatalogService {
    private final BookRepository books;

    public CatalogService(BookRepository books) {
        this.books = books;
    }

    @Transactional(readOnly = true)
    public BookDto find(long id) {
        Book book = books.findById(id).orElseThrow();
        return new BookDto(book.getId(), book.getTitle());
    }

    @Transactional
    public void rename(long id, String title) {
        Book book = books.findById(id).orElseThrow();
        book.setTitle(title); // Dirty checking in a read-write transaction.
    }
}
~~~

This is an **illustrative pattern**, not standalone source: `BookRepository` and `BookDto` must be defined (supplied separately if applied in a project). The key point is placing transaction boundaries at the **service use case**, rather than relying on annotations scattered across repository methods while ignoring the caller.

### What Are Spring Data JPA's Defaults?

According to Spring Data JPA documentation, CRUD methods inherited from `SimpleJpaRepository`:

- **Read** operations inherit a read-only transaction configuration.
- **Write** operations are configured with a read-write transaction.
- **User-declared query methods** are not guaranteed to automatically have a transaction simply because the repository is a Spring Data interface; place `@Transactional` appropriately on the repository or service as needed.
- If an outer service has already opened a transaction, the **outer boundary** usually dictates the actual transaction. You cannot always turn an outer read-only transaction into writable just via a read-write annotation on an inner repository method.

Example JPQL update distinguishing `@Modifying` and transaction:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {
    @Modifying
    @Transactional
    @Query("update Book b set b.title = :title where b.id = :id")
    int renameById(@Param("id") Long id, @Param("title") String title);
}
~~~

This is an **illustrative repository pattern**, requiring imports and the corresponding entity. `@Modifying` gives the query update semantics; `@Transactional` provides a boundary, yet if a service already opened a read-only transaction and the repository joins it, the repository-level annotation may **not override** the existing flush/connection read-only settings. Moreover, bulk updates bypass the persistence context of managed entities; you must understand stale entity state and clear/refresh requirements.

### Prefer Projections When Only a Few Columns Are Needed

If an API only needs `id` and `title`, DTO projections can reduce the number of materialized entities and avoid managing large object graphs. Read-only transactions help optimize when still loading entities, but **do not replace** column limiting, pagination, join strategies, indexes, and fetch plans.

Illustrative query structure example:

~~~java
@Query("select new demo.BookSummary(b.id, b.title) from Book b")
List<BookSummary> listSummaries();
~~~

`BookSummary` must have a matching constructor/record signature. This is an example of optimizing returned attributes, not proof that a specific query is faster without benchmarking.

## 7. Maven Java 17+ Demo: Checking Flush and Real DB Data

The demo uses **Spring Boot 3.4.4** (integrating Spring Framework 6.2.5 and Hibernate ORM via the Data JPA starter), **in-memory H2**, Java 17+, and Maven. Spring Boot is used for concise JPA/Hibernate configuration, while the transaction mechanism being demonstrated is **Spring Framework Transaction Management**.

Objectives:

1. Initialize the `books` table with one row `id=1, title=Original`.
2. Call `BookService.observeReadOnly()` through the Spring proxy. The Hibernate Session is inspected for flush mode and read-only flags; code mutates the Java object without **intending to write to the DB**.
3. Read the DB **after the read-only transaction ends**: still `Original`.
4. Call `BookService.changeInWritableTx()` through the Spring proxy, mutating the same entity in a writable transaction.
5. Read the DB **after commit**: becomes `Persisted from write tx`.

### 7.1. Directory Structure

~~~text
read-only-flush-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/
        │   ├── ReadOnlyFlushDemo.java
        │   ├── Book.java
        │   └── BookService.java
        └── resources/
            └── application.properties
~~~

### 7.2. Create `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.4</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>read-only-flush-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `spring-boot-starter-parent` BOM manages transitive versions such as Hibernate and H2. The demo does not pin individual dependencies so Boot uses the **compatibility-tested dependency set** in release 3.4.4. To reproduce the results, keep this parent version.

### 7.3. Create `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:flush_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
logging.level.root=ERROR
~~~

`ddl-auto=create-drop` is for demo use only, so Hibernate creates the table and cleans it up when closing the context. **Do not** put this setting into production because it can destroy schemas/data.

`open-in-view=false` prevents the example from holding an `EntityManager` context long across requests; with a CLI having no HTTP, this property simply makes intent explicit.

### 7.4. Create `src/main/java/demo/Book.java`

~~~java
package demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {
    @Id
    private Long id;

    @Column(nullable = false)
    private String title;

    protected Book() {
        // JPA constructor required to instantiate the entity.
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
}
~~~

The entity is loaded inside the transaction via `EntityManager.find(...)`. In the demo, the initial row is inserted directly via `JdbcTemplate`, so no parameterized constructor or `@GeneratedValue` is needed.

### 7.5. Create `src/main/java/demo/BookService.java`

~~~java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.hibernate.Session;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class BookService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public void observeReadOnly(long id) {
        Session session = entityManager.unwrap(Session.class);
        Book book = entityManager.find(Book.class, id);

        System.out.println("readOnly.flag="
                + TransactionSynchronizationManager.isCurrentTransactionReadOnly());
        System.out.println("readOnly.flushMode="
                + session.getHibernateFlushMode());
        System.out.println("readOnly.defaultReadOnly="
                + session.isDefaultReadOnly());
        System.out.println("readOnly.entityReadOnly="
                + session.isReadOnly(book));

        book.setTitle("Changed only in memory");
        System.out.println("readOnly.objectTitle=" + book.getTitle());
    }

    @Transactional
    public void changeInWritableTx(long id) {
        Session session = entityManager.unwrap(Session.class);
        Book book = entityManager.find(Book.class, id);

        System.out.println("readWrite.flag="
                + TransactionSynchronizationManager.isCurrentTransactionReadOnly());
        System.out.println("readWrite.flushMode="
                + session.getHibernateFlushMode());
        System.out.println("readWrite.defaultReadOnly="
                + session.isDefaultReadOnly());
        System.out.println("readWrite.entityReadOnly="
                + session.isReadOnly(book));

        book.setTitle("Persisted from write tx");
        // No explicit save() or flush() called.
        // Hibernate can dirty-check and flush on commit.
    }
}
~~~

What to observe: in the read-only transaction, `Session.getHibernateFlushMode()` is set to `MANUAL`, and `isDefaultReadOnly()`/`isReadOnly(book)` are expected to be `true`. The setter still changes the **Java object in RAM**, yet Hibernate does not automatically generate a scalar UPDATE for the read-only entity in this scope.

In the writable transaction, the Session normally uses `AUTO` and the loaded entity is modifiable; when the proxy finishes, the transaction manager commits and Hibernate flushes the `title` change.

### 7.6. Create `src/main/java/demo/ReadOnlyFlushDemo.java`

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class ReadOnlyFlushDemo {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ReadOnlyFlushDemo.class, args)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            BookService service = context.getBean(BookService.class);

            jdbc.update(
                    "INSERT INTO books (id, title) VALUES (?, ?)",
                    1L, "Original");

            service.observeReadOnly(1L);
            System.out.println("DB_after_readOnly=" + getTitle(jdbc));

            service.changeInWritableTx(1L);
            System.out.println("DB_after_readWrite=" + getTitle(jdbc));
        }
    }

    private static String getTitle(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT title FROM books WHERE id = 1",
                String.class);
    }
}
~~~

`@SpringBootApplication` enables JPA, DataSource auto-configuration, and component scanning in package `demo`. `BookService` is a Spring-managed bean retrieved from the context, with public methods invoked through the transaction proxy; **not** `new BookService()` or `this.method()`. Hibernate creates the table because of `ddl-auto=create-drop`, then `JdbcTemplate` inserts one row into the DB.

### 7.7. Running and Expected stdout

~~~bash
mvn -q spring-boot:run
~~~

Lines printed by `System.out` in code, omitting other framework/driver logs:

~~~text
readOnly.flag=true
readOnly.flushMode=MANUAL
readOnly.defaultReadOnly=true
readOnly.entityReadOnly=true
readOnly.objectTitle=Changed only in memory
DB_after_readOnly=Original
readWrite.flag=false
readWrite.flushMode=AUTO
readWrite.defaultReadOnly=false
readWrite.entityReadOnly=false
DB_after_readWrite=Persisted from write tx
~~~

**Explanation:**

1. `readOnly.flag=true` is the Spring metadata published for the new transaction.
2. `flushMode=MANUAL` is the flush optimization from `HibernateJpaDialect`. `defaultReadOnly=true` and `entityReadOnly=true` are entity-management optimizations in the transaction-local `EntityManager` configuration.
3. The setter puts the new title on the **Java object**; `readOnly.objectTitle` only proves the object changed. After the scope, a `JdbcTemplate` DB query still sees `Original`.
4. `changeInWritableTx` opens a new read-write transaction. Hibernate tracks the snapshot/dirty state and flushes changes on commit; afterward the DB query sees `Persisted from write tx`.
5. There is no `entityManager.flush()` in the demo. That highlights how Hibernate can auto-flush in a read-write transaction while a read-only transaction avoids unnecessary work.

**Limitations of expected results:** The `MANUAL/AUTO` and default read-only flags are expected under Spring Boot 3.4.4 using standard Hibernate/`JpaTransactionManager`. If a project replaces the transaction manager, provider, `EntityManager` creation method, or calls inside an outer transaction, values may differ; do not copy these results as a universal contract for every JPA system. The example is designed to compile/run, yet results should be verified with Maven in an environment having the corresponding dependencies.

## 8. Is a Read-Only Transaction Truly "Unable to Write"?

**Not guaranteed.** It is an **optimization hint and transaction metadata**, not a mandatory data-authorization rule.

Example:

~~~java
@Transactional(readOnly = true)
public void dangerousBulkUpdate() {
    entityManager.createQuery(
            "update Book b set b.title = 'Changed' where b.id = 1")
            .executeUpdate();
}
~~~

This is a **risk-illustration snippet**, not part of the complete demo. A bulk JPQL update is an explicit DML operation and does not depend entirely on dirty checking of an entity loaded with `find`. Depending on DB/JDBC read-only enforcement, it **may** run or be rejected by the DB/driver.

Similarly, calling `JdbcTemplate.update(...)` directly inside a read-only service is not automatically turned into "read-only" by Spring AOP. The JDBC connection may carry the read-only flag while the database does not fully enforce it. To **genuinely block writes**, you need read-only DB privileges, a read replica, a DB-level read-only transaction configuration when supported, or real security policies.

### "MANUAL" Does Not Mean "Never Flushes"

If a Session holds **modifiable** entities or other pending actions, `entityManager.flush()` is still an explicit request to synchronize. Hibernate skipping dirty-checking on simple properties of **already read-only entities** is a separate optimization; do not conflate the two mechanisms.

Hibernate read-only entities also do not mean every collection/cascade/delete is forbidden. When you need an absolute guarantee that "this function does not write data", tests must inspect actual SQL queries and DB privileges, not merely read a flag.

### Flush Is Not Commit and Does Not Guarantee Isolation

If a writable transaction flushed an UPDATE and then rolled back, the database undoes the change per transaction semantics. If you call `flush()` and then query within that same transaction, you can see the new data; whether another transaction sees it depends on isolation and commit.

Conversely, if a read-only entity in the persistence context has a property mutated by a setter, Java code in the same request may read back the new value on the object **even though the database retains the old value**. This is one reason not to mutate read-only entities and rely on "non-flushing" behavior as a business rule.

## 9. Propagation Determines the Effective Read-Only and Flush Mode

`@Transactional(readOnly=true)` has its strongest effect when Spring **creates a new transaction** with the corresponding resource/persistence context. If a method merely joins an existing transaction, attributes on the inner method are not necessarily re-applied to the physical transaction.

### 9.1. Outer Write Transaction, Inner Read-Only

~~~java
@Service
class Writer {
    private final Reader reader;

    Writer(Reader reader) {
        this.reader = reader;
    }

    @Transactional
    public void update() {
        reader.load(); // Calls another bean through the Spring proxy.
    }
}

@Service
class Reader {
    @Transactional(readOnly = true)
    public void load() {
        // May be participating in Writer's physical read-write transaction.
    }
}
~~~

**Illustrative code fragment**, not a complete program. With the default `Propagation.REQUIRED`, `Reader.load()` joins the existing transaction instead of creating a new one and switching the entire Session to `MANUAL`. Do not infer from the inner annotation that the connection/flush mode is actually read-only.

### 9.2. Outer Read-Only, Inner Write

~~~java
@Transactional(readOnly = true)
public void outerRead() {
    otherService.updateSomething(); // Default read-write @Transactional inner method.
}
~~~

If the inner `REQUIRED` simply joins the outer's read-only physical transaction, the inner's read-write declaration **is not guaranteed** to upgrade the transaction to writable. This is an easy bug to hit when marking a service class `@Transactional(readOnly=true)` and later adding a new write method while forgetting to override/adjust the proper boundary.

If business logic truly requires an independent write transaction, you can consider `Propagation.REQUIRES_NEW` on a **separate bean** to open a new physical transaction with read-write metadata, though you must weigh business atomicity, connection pooling, visibility, and exception handling. Do not treat `REQUIRES_NEW` as a "universal fix" for all read-only errors.

### 9.3. Read-Only + SUPPORTS and Manager Policy

A `@Transactional(propagation=SUPPORTS, readOnly=true)` method called outside a transaction does not open a new physical transaction. Spring may still publish read-only metadata and synchronization scope. The ORM provider might use that information when binding a Session, yet you must not assume it behaves identically to an already started transaction-local read-only JPA transaction.

**Principle:** when flush/read-only behavior matters, inspect the **actual transaction boundary**, Hibernate Session, and SQL on the DB, rather than inferring from source annotations alone.

## 10. How Does Timeout Affect Flushing and ORM Queries?

This lesson group also includes **timeout**, though timeout and read-only are two independent axes:

~~~java
@Transactional(readOnly = true, timeout = 5)
public List<BookDto> loadCatalog() {
    // Transaction with read-only intent and a 5-second timeout.
}
~~~

This is an **illustrative declaration fragment**, without implementation. `timeout=5` is a transaction timeout in **seconds**, not milliseconds. It is used by the transaction manager when **opening a new transaction** (usually with `REQUIRED` having no outer or with `REQUIRES_NEW`). An inner `REQUIRED` that merely joins an outer does not automatically replace the outer transaction's deadline with the new timeout.

### What Does Timeout NOT Mean?

- It does not automatically run a timer that always interrupts the Java thread immediately after 5 seconds.
- It does not guarantee canceling all CPU tasks, network I/O, or every DB operation if the driver/provider cannot enforce the timeout.
- It does not automatically switch Hibernate flush mode to `MANUAL`.
- It does not turn `readOnly=false` into `readOnly=true`.
- It does not guarantee that if a query timed out, the DB did zero work; the application must handle errors/rollbacks per manager and driver.

Spring can pass the timeout down to queries/statements or check the deadline when transaction-aware resources are used. JPA has a query timeout hint mechanism (typically milliseconds), though **transaction timeout** and **query timeout** are not strictly equivalent.

Example JPQL query with a query-level timeout hint:

~~~java
TypedQuery<Book> query = entityManager.createQuery(
        "select b from Book b order by b.id", Book.class);
query.setHint("jakarta.persistence.query.timeout", 2000); // ms
List<Book> books = query.getResultList();
~~~

This is an **illustrative snippet**, depending on provider/driver support for the hint. `2000` means 2,000 milliseconds; `@Transactional(timeout = 5)` means five seconds. Do not confuse units.

### How Can Flushing Be Affected by Timeout?

In a read-write transaction, Hibernate may emit multiple SQL statements while flushing before commit. If the SQL/flush process exceeds the transaction deadline, the transaction manager/provider/driver may throw an exception and the transaction can roll back. However, **at what point** the timeout is enforced depends on the actual mechanism.

In a read-only transaction with `MANUAL`, reducing auto-flushing and dirty checking can reduce work before commit/queries. That is **not** a fix for a slow SELECT caused by missing indexes, N+1 queries, poor join/fetch plans, or database lock contention. Measure the true source of latency.

### Anti-Pattern Example

~~~java
@Transactional(readOnly = true, timeout = 2)
public void doWork() throws InterruptedException {
    Thread.sleep(5000);
    // Cannot claim with certainty that the thread will be interrupted
    // at exactly the second second by Spring Transaction Management.
}
~~~

This is a non-standalone illustrative fragment. Spring timeout is not a Java thread interruption API. If a DB query runs afterward, there may be a deadline check or query timeout from the transaction manager.

## 11. ORM Optimization Techniques More Useful Than Just Enabling Read-Only

Read-only transactions are most helpful when **placed properly on genuinely read-only queries**, yet they do not replace query design decisions:

| Issue | Solution to Consider | Role of `readOnly=true` |
| --- | --- | --- |
| Loading many entities to return three fields | DTO projection / selecting fewer columns | Can reduce tracking when still loading entities, but does not avoid loading excess columns |
| N+1 queries from lazy associations | Fetch join, EntityGraph, or controlled batch fetching | Cannot fix N+1 |
| Returning too many rows | Pagination / keyset pagination, limiting windows | Does not reduce data volume if the query returns the whole table |
| Slow DB scans | Proper indexes, query plans, filter predicates | Does not replace query tuning |
| Read-only scan with many managed entities | Read-only transaction, projections, read-only Hibernate query/session, batch detach/clear | Can reduce snapshots and dirty checking |
| Batch updating thousands of entities | Batch size, batch flush/clear, careful bulk DML | Should not enable readOnly if changes must be persisted |
| Long transactions holding connections/locks long | Shorten boundaries, move network I/O out, paginate properly | Can reduce flush overhead, does not replace isolation/locks |
| Frequent query timeouts | Explain plan, indexes, lock waits, appropriate statement/query timeout | May help ORM CPU but does not solve DB contention |

### Hibernate Query-Level Read-Only

If only one large query is read-only while the service transaction also performs writes, Hibernate has an API like:

~~~java
Session session = entityManager.unwrap(Session.class);
List<Book> books = session.createQuery(
        "from Book", Book.class)
        .setReadOnly(true)
        .getResultList();
~~~

This is a provider-specific API example and does not mean entities already managed before the query change state. Using Hibernate query read-only requires understanding its effect on dirty checking of those specific entities; you should not mutate them and assume setters will be flushed.

### Avoid Optimizing Without Measurements

Some symptoms mistaken for flush overhead are actually:

- Slow SQL queries due to indexes/plans, not dirty checking.
- Too many N+1 SELECTs; flush mode does not reduce query count.
- Oversized entity graphs from unnecessary eager fetching.
- Long transactions due to HTTP/network calls inside the scope.
- DB lock waits slowing down commit.
- Overly verbose SQL logging/bind logging left enabled during benchmarks.

Any claim of "X% faster" must be measured under the specific workload; there is no default speedup factor for `readOnly=true`.

## 12. How to Measure and Test Properly

### 12.1. Measuring SQL and Commit Behavior

In a test environment you can selectively enable:

~~~properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

This is an **optional logging configuration**, omitted from the demo's `application.properties` to keep stdout easy to read. Do not log sensitive bind parameters in production.

For a method intended to be read-only, observe:

1. Is there any unexpected `UPDATE`/`INSERT` SQL?
2. What is `Session.getHibernateFlushMode()`?
3. Does a newly loaded entity have `Session.isReadOnly(entity)`?
4. Did DB data change **after the transaction ended**?
5. Do DB permission mechanisms actually reject writes when required?

### 12.2. Benchmarking Workloads

Compare the same query with `readOnly` false vs. true:

- DB query time (measured separately where possible).
- Hibernate ORM processing time, count of managed entities, and heap allocated.
- Flush count, entity update/insert/delete counts, and SQL statement count.
- GC pressure, p95/p99 latency, and throughput under realistic load.
- Effects of caching, connection pooling, OSIV, and fetch plans.

Hibernate has `Statistics`/metrics available when enabled; measuring flush counts and entity update counts can have diagnostic value. However, **a lower flush count does not by itself prove the DB is safe** or that the endpoint is faster.

### 12.3. Tests Worth More Than a Single Flag

- **Read-only scope:** load entity, modify a scalar property, inspect DB after the scope; expected result matches the chosen provider/config.
- **Read-write scope:** load and modify a scalar property, inspect DB after commit; proper UPDATE occurs.
- **Explicit DML inside read-only:** run on the target database and verify whether it is forbidden or permitted; do not use this test to write production data.
- **Outer read-only, inner write REQUIRED:** verify the joined transaction and actual result, not only the inner annotation.
- **Timeout:** test with a cancellable query and DB/driver timeout; do not substitute `Thread.sleep` and conclude timeout is broken.
- **Rollback after flush:** call `flush()` in a writable transaction then throw an unchecked exception; confirm the DB recovers after rollback.

If using Spring TestContext with `@Transactional` on the test method itself, it may open an outer transaction and roll back after the test. When you want to check the commit/rollback boundary of the method under test, **do not accidentally place the whole test inside an outer transaction**.

## 13. Common Mistakes

| Misunderstanding | Consequence | Right Approach |
| --- | --- | --- |
| "`readOnly=true` locks down writes absolutely" | Direct DML may still run, depending on DB | Use DB permissions or true DB read-only mode to enforce |
| "`flush()` equals commit" | Misreading results, misunderstanding rollback after flush | Distinguish SQL synchronization from final commit |
| "MANUAL cannot emit write SQL" | Overlooking explicit DML, persist/cascades | Inspect actual SQL write paths |
| "Setter modifying object means DB changed" | Returning RAM data that differs from DB | Check DB after boundary |
| "All JPA providers use MANUAL for read-only" | Assuming Hibernate-specific behavior is standard JPA | Check transaction manager/provider |
| "Default read-only changes all already-managed entities" | Old entities retain their own state | Check `Session.isReadOnly(entity)` |
| "Query read-only makes every entity immutable" | Collections/cascades may still have effects | Use proper APIs and test associations |
| "Repository write annotation overrides outer read-only" | Joining transaction may keep read-only settings | Place boundaries at service, check propagation |
| "Adding timeout skips flushing" | Two independent mechanisms | Optimize ORM/SQL separately and set proper deadlines |
| "`timeout=5` means 5 ms" | Misconfigured timeout scale | Spring transaction timeout is in seconds |
| "Any timeout interrupts the thread immediately" | Expecting a mechanism that does not exist | Understand manager/JDBC query timeouts |
| "Toggling readOnly fixes N+1" | Still many SELECTs | Fix fetch plan/projection/indexes |
| "`this.someMethod()` triggers transaction advice" | Inner method annotation may be bypassed | Call through a Spring-managed proxy |
| "Read-only is good for all methods" | Write paths may lose dirty-check/flush | Use only when the method is genuinely pure read |

## 14. Self-Check Questions

**Question 1.** An entity is loaded inside a Hibernate read-only transaction, then a setter changes its title. `System.out(book.getTitle())` shows the new value. Does this prove the DB received an UPDATE?

**Answer:** No. The Java object changed in RAM; Hibernate may skip dirty-checking read-only entities and skip auto-flushing. Inspect the DB after the transaction ends.

**Question 2.** Why is `FlushMode.MANUAL` in Hibernate not the same as `FlushModeType.COMMIT` in JPA?

**Answer:** `MANUAL` is a Hibernate-specific value primarily waiting for explicit flush calls; `COMMIT` is a JPA flush mode with its own semantics. The JPA `FlushModeType` API has no `MANUAL`.

**Question 3.** Why can `@Transactional(readOnly=true)` improve performance when reading thousands of entities?

**Answer:** It can suppress automatic flushing and reduce snapshot/dirty-checking cost for read-only entities in Hibernate. The degree of benefit depends on entity volume and real workload.

**Question 4.** Is a bulk JPQL UPDATE inside a `@Transactional(readOnly=true)` method guaranteed to be rejected by Spring?

**Answer:** No. Read-only is a hint/transaction metadata; SQL may be blocked by the DB or still run depending on configuration. Enforcement requires proper DB permissions/modes.

**Question 5.** A read-write `@Transactional` inner method is called inside a `@Transactional(readOnly=true)` outer with default `REQUIRED`. Is the inner guaranteed to receive a Session in `AUTO`?

**Answer:** No. The inner can join the outer's read-only physical transaction without changing established metadata/flush mode. You must identify the actual transaction boundary.

**Question 6.** `entityManager.flush()` sends an UPDATE SQL, then the method throws an unchecked exception. Must the DB keep the UPDATE?

**Answer:** No. If the SQL is inside the transaction and the transaction rolls back, the UPDATE is undone even though it was flushed.

**Question 7.** Does `@Transactional(timeout=3)` mean Spring automatically interrupts any Java thread after exactly 3 seconds?

**Answer:** No. Timeout depends on the transaction manager/provider and executed operations; it is not a universal Java thread timer.

**Question 8.** Read-only transactions are enabled, yet the endpoint is still slow due to N+1 SELECTs. Should you just change the flush mode?

**Answer:** No. N+1 is a fetch/query plan problem; you need appropriate projections, fetch joins, EntityGraphs, or batch fetching and re-measurement.

**Question 9.** A Hibernate Session calls `setDefaultReadOnly(true)` after loading an entity. Does the old entity automatically become read-only?

**Answer:** Not automatically. The default affects entities loaded afterward; there is a separate API to change the state of a managed instance.

## Key Takeaways

- **Flush ≠ commit.** Flush synchronizes state into SQL; commit ends the transaction. Flushing then rolling back still undoes SQL.
- **Spring readOnly is a hint.** In transaction-local Hibernate integration, Spring typically sets `FlushMode.MANUAL` and `Session.setDefaultReadOnly(true)`, reducing auto-flushing and dirty checking for newly loaded entities.
- **Object state ≠ DB state.** Setters can modify an entity in RAM without persisting when the entity is read-only.
- **MANUAL is not a write guard.** Explicit DML/operations can still execute; DB permissions and the provider determine whether writes are blocked.
- **Propagation matters.** An inner `REQUIRED` joining an outer may not re-apply read-only/flush settings from its own annotation.
- **Timeout does not change flush mode.** Spring's timeout in seconds must be understood and tested at the transaction manager/JDBC provider level.
- Effective ORM optimization relies on **measuring SQL, dirty checking, heap, query plans, fetch strategies, and post-boundary DB state**, not mechanically adding annotations.

## Official References

1. Spring Data JPA — [Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): readOnly is a hint, Hibernate uses MANUAL flush mode and optimizes dirty checking.
2. Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): readOnly, timeout, propagation, and rollback rules.
3. Spring Framework — [`HibernateJpaDialect` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/orm/jpa/vendor/HibernateJpaDialect.html): preparing Session/JDBC transactions and flush mode.
4. Hibernate ORM 6.6 — [User Guide](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): persistence context, flush, dirty checking, and read-only entities.
5. Hibernate ORM 6.6 — [`Session` Javadoc](https://docs.jboss.org/hibernate/orm/6.6/javadocs/org/hibernate/Session.html): `isDefaultReadOnly`, `setDefaultReadOnly`, `isReadOnly`.
6. Spring Framework — [TransactionDefinition Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/transaction/TransactionDefinition.html): read-only hint and transaction timeout.
7. Spring Boot — [3.4.4 release](https://spring.io/blog/2025/03/20/spring-boot-3-4-4-available-now/): version used in the Maven example.
