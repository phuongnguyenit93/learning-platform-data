# Distinguishing Inherited CRUD Methods from Declared Query Methods in Spring Data JPA

Spring Data JPA enables data operations through repository interfaces. When extending JpaRepository, a repository receives built-in CRUD methods such as save, findById, findAll, and deleteById. When business-specific queries are needed, we declare additional methods on the interface, such as findByAuthorIgnoreCase or a method annotated with @Query.

These two groups of methods have different definitions and purposes. Understanding the distinction keeps repositories concise and readable and avoids rewriting functionality Spring Data already provides.

## 1. How Does a Repository Work?

A repository is the data access layer. With Spring Data JPA, we typically create an interface extending JpaRepository:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {
}
~~~

The two type parameters of JpaRepository are:

- Book: the entity type managed by the repository.
- Long: the data type of the primary key in the Book entity.

Spring Data generates a proxy implementation for the interface at application startup. We simply inject BookRepository into a service or controller and invoke its methods. The framework handles data access through the JPA provider, typically Hibernate.

Basic execution flow:

~~~mermaid
flowchart TD
    A[Service or Controller] --> B[BookRepository interface]
    B --> C{Method type}
    C --> D[Inherited CRUD]
    C --> E[Declared query method]
    D --> F[Spring Data repository implementation]
    E --> F
    F --> G[JPA EntityManager / Hibernate]
    G --> H[(Database)]
~~~

A repository interface does not require writing an implementation class for standard methods. However, every custom-declared method must follow a query rule Spring Data can parse or provide an explicit query definition.

## 2. What Are Inherited CRUD Methods?

Inherited CRUD methods are methods already defined in foundational interfaces such as CrudRepository, ListCrudRepository, PagingAndSortingRepository, and JpaRepository. When an application's repository extends JpaRepository, it inherits common operations for creating, reading, updating, and deleting entities.

Example:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {
    // Built-in CRUD methods are already available.
}
~~~

There is no need to redeclare save, findById, findAll, or deleteById if you only need standard behavior.

### Commonly Used CRUD Methods

| Inherited Method | Meaning | Common Return Type |
|---|---|---|
| save(entity) | Saves a new entity or updates an entity | Saved entity |
| saveAll(entities) | Saves a collection of entities | List of entities |
| findById(id) | Finds one entity by primary key | Optional<T> |
| existsById(id) | Checks whether a primary key exists | boolean |
| findAll() | Retrieves all entities | List<T> when using JpaRepository |
| findAllById(ids) | Retrieves entities by a list of primary keys | List<T> |
| count() | Counts the number of entities | long |
| deleteById(id) | Deletes an entity by primary key | void |
| delete(entity) | Deletes the passed entity | void |
| deleteAll() | Deletes all entities | void |

The return type depends on the base interface. If extending CrudRepository directly, findAll() and findAllById() return Iterable<T>. With JpaRepository in modern Spring Data versions, the List-based CRUD contracts are used, so findAll() returns List<T>.

JpaRepository also provides JPA-related features and pagination/sorting:

| Method | Purpose |
|---|---|
| findAll(Sort sort) | Retrieves sorted data |
| findAll(Pageable pageable) | Retrieves one page of data |
| flush() | Synchronizes persistence context with the database |
| saveAndFlush(entity) | Saves entity and flushes immediately |
| saveAllAndFlush(entities) | Saves multiple entities and flushes |
| getReferenceById(id) | Retrieves an entity reference, often as a lazy proxy |
| deleteAllInBatch() | Performs bulk deletion |

Some batch methods behave differently from deleting entities one by one. Bulk deletes/updates can bypass entity lifecycle callbacks and leave an active persistence context holding stale data. Use them only when you understand their impact on cascades, caches, and entity state.

### Example Using Inherited CRUD

~~~java
@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Book create(Book book) {
        return repository.save(book);
    }

    public Optional<Book> findOne(Long id) {
        return repository.findById(id);
    }

    public List<Book> findAll() {
        return repository.findAll();
    }

    public boolean exists(Long id) {
        return repository.existsById(id);
    }

    public void delete(Long id) {
        repository.deleteById(id);
    }
}
~~~

These methods fit general operations by entity or primary key. They do not need to know business-specific details like searching by author, filtering by status, or matching a title substring.

### Notes on save()

save() does not always execute an INSERT. Spring Data JPA checks whether the entity is new, then typically calls persist for a new entity or merge for an existing entity. With merge, the returned object may be a different managed instance from the one passed in. Therefore, always use the returned value:

~~~java
Book saved = repository.save(book);
~~~

Do not assume calling save() will immediately trigger SQL at that exact line. JPA may defer SQL until flush or transaction commit.

### Notes on findById() and getReferenceById()

findById(id) executes a lookup and returns Optional<T>, which is suitable when you need to know whether the entity exists.

getReferenceById(id) retrieves an entity reference and may return an uninitialized proxy without hitting the database immediately. If the key does not exist, an error may only appear when the proxy is accessed. These two methods are not interchangeable.

## 3. What Are Declared Query Methods?

Declared query methods are methods added by developers to a repository interface to serve specific query requirements. Spring Data can generate a query from the method name (derived query), or use a query declared via the @Query annotation.

Example:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByAuthorIgnoreCase(String author);

    Optional<Book> findByIsbn(String isbn);

    boolean existsByTitleIgnoreCase(String title);
}
~~~

The three methods above are not standard CRUD methods inherited from JpaRepository. They are declared in BookRepository to express the application's specific query conditions.

There are two common ways to define query methods:

1. Derived query: Spring Data parses the method name and infers the query criteria.
2. Declared query: the developer writes an explicit query with @Query, using either JPQL or native SQL.

## 4. Derived Queries: Creating Queries from Method Names

Derived queries are a concise way to declare queries via naming conventions. Spring Data parses prefixes, property names, and keywords in the method name to build the query.

Suppose the Book entity has properties title, author, isbn, and published:

~~~java
List<Book> findByAuthor(String author);
~~~

Spring Data interprets this method as finding Books whose author property equals the passed value.

Other examples:

~~~java
List<Book> findByAuthorIgnoreCase(String author);

List<Book> findByTitleContainingIgnoreCase(String keyword);

List<Book> findByAuthorAndPublishedTrue(String author);

List<Book> findByPriceGreaterThan(BigDecimal minPrice);

List<Book> findByPublishedTrueOrderByTitleAsc();

Optional<Book> findByIsbn(String isbn);

boolean existsByTitleIgnoreCase(String title);

long countByPublishedTrue();

List<Book> findTop5ByOrderByTitleAsc();
~~~

Meaning:

- IgnoreCase: case-insensitive string comparison.
- Containing: substring match, usually equivalent to a LIKE condition with wildcards on both sides.
- And: combines multiple conditions with AND.
- PublishedTrue: checks that the boolean property published is true.
- GreaterThan: greater-than comparison.
- OrderByTitleAsc: sorts by title ascending.
- Top5: limits results to at most five records.
- existsBy: checks whether matching records exist.
- countBy: counts matching records.

### Common Keywords

| Keyword | Meaning | Example |
|---|---|---|
| And | Combines conditions with AND | findByAuthorAndPublishedTrue |
| Or | Combines conditions with OR | findByAuthorOrTitle |
| Between | Within a range | findByPriceBetween |
| LessThan | Less than | findByPriceLessThan |
| LessThanEqual | Less than or equal to | findByPriceLessThanEqual |
| GreaterThan | Greater than | findByPriceGreaterThan |
| IsNull | Value is null | findByPublishedAtIsNull |
| IsNotNull | Value is not null | findByPublishedAtIsNotNull |
| In | In a collection of values | findByAuthorIn |
| NotIn | Not in a collection of values | findByAuthorNotIn |
| Like | LIKE pattern match | findByTitleLike |
| Containing | Contains substring | findByTitleContaining |
| StartingWith | Starts with | findByTitleStartingWith |
| EndingWith | Ends with | findByTitleEndingWith |
| IgnoreCase | Case-insensitive | findByAuthorIgnoreCase |
| OrderBy | Sorts results | findByPublishedTrueOrderByTitleDesc |
| Distinct | Removes duplicate results | findDistinctByAuthor |
| Top / First | Limits number of results | findTop10ByOrderByTitleAsc |
| ExistsBy | Checks existence | existsByIsbn |
| CountBy | Counts results | countByPublishedTrue |
| DeleteBy / RemoveBy | Deletes matching entities | deleteByPublishedFalse |

Keywords and property names must match the entity model. Derived queries reference Java property names, not physical column names in the database.

### Choosing the Return Type

The return type specifies how the application wants to receive the results:

~~~java
Book findFirstByAuthorOrderByTitleAsc(String author);

Optional<Book> findByIsbn(String isbn);

List<Book> findByAuthor(String author);

Page<Book> findByPublishedTrue(Pageable pageable);

Slice<Book> findByAuthor(String author, Pageable pageable);

boolean existsByIsbn(String isbn);

long countByAuthor(String author);
~~~

- Use Optional<T> when at most one result is expected and you want to represent potential absence.
- Use List<T> when a list of results is needed and loading the full list is acceptable.
- Use Page<T> when a page of data plus total element/page counts are needed; usually incurs an extra count query.
- Use Slice<T> when you only need to know whether a next page exists, avoiding a total row count query.
- Use boolean for existence queries and long for count queries.

If a query can return multiple records, avoid declaring Optional<T> or a single entity unless uniqueness is guaranteed. Otherwise, Spring Data may throw an exception when more than one row is returned.

### Pagination and Sorting

Example calling the repository from a service:

~~~java
Page<Book> page = repository.findByPublishedTrue(
        PageRequest.of(0, 20, Sort.by("title").ascending())
);
~~~

PageRequest.of(0, 20, ...) requests the first page with up to 20 results. Page indices start at 0. Property names in Sort are entity properties, such as title.

Use Page when the UI needs total pages or total results. Use Slice when the UI only needs a "load more" button and you want to avoid the cost of counting total rows on large datasets.

## 5. Explicit Query Declarations with `@Query`

When method names become too long or conditions are complex, you can declare the query using @Query.

### JPQL

JPQL queries entities and Java properties rather than physical table and column names:

~~~java
@Query("select b from Book b where lower(b.author) = lower(:author)")
List<Book> searchByAuthor(@Param("author") String author);
~~~

In this example:

- Book is the entity name.
- b.author is the entity's author property.
- :author is a named parameter.
- @Param("author") binds the Java parameter to the JPQL parameter.
- lower() converts strings to lowercase for comparison.

Another query with multiple field conditions:

~~~java
@Query("""
       select b
       from Book b
       where b.published = true
         and b.price >= :minimumPrice
       order by b.price desc
       """)
List<Book> findPublishedBooksAbovePrice(
        @Param("minimumPrice") BigDecimal minimumPrice);
~~~

Java 17 text blocks make multi-line JPQL easy to read. JPQL supports object-oriented querying and is translated into database-specific SQL by the JPA provider.

### Native SQL with nativeQuery

If you need database-specific syntax or an already optimized SQL query, you can declare a native query:

~~~java
@Query(
    value = "select * from books where author = :author",
    nativeQuery = true
)
List<Book> findByAuthorUsingSql(@Param("author") String author);
~~~

With native queries:

- The query uses database table and column names.
- Syntax depends on the database engine and may not be portable across MySQL, PostgreSQL, and H2.
- Results can be mapped to entities or appropriate projections.
- SQL and mappings must be verified when switching databases.

Prefer JPQL when the query aligns naturally with the entity model. Use native queries when there is a clear reason—such as database-specific SQL features, CTEs, window functions, or specialized queries not conveniently expressed in JPQL.

## 6. Update and Delete Queries with `@Modifying`

@Query is normally used for read queries. When a JPQL or SQL statement performs an UPDATE or DELETE, mark the method with @Modifying.

Repository example:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update Book b set b.published = :published where b.id = :id")
    int updatePublishedStatus(
            @Param("id") Long id,
            @Param("published") boolean published);

    @Modifying
    @Query("delete from Book b where b.published = false")
    int deleteUnpublishedBooks();
}
~~~

Modifying methods return the number of affected rows. They must be called inside a transaction, typically placed on the service:

~~~java
@Service
public class BookMaintenanceService {

    private final BookRepository repository;

    public BookMaintenanceService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int publish(Long id) {
        return repository.updatePublishedStatus(id, true);
    }

    @Transactional
    public int removeDrafts() {
        return repository.deleteUnpublishedBooks();
    }
}
~~~

Key points to note:

- @Modifying tells Spring Data the query modifies data.
- @Transactional defines the transaction boundary; place it in the service if the operation is part of a business flow.
- flushAutomatically flushes pending changes before executing the bulk query.
- clearAutomatically clears the persistence context after the query to avoid continuing to use stale entities in memory.
- Bulk updates/deletes act directly on the database and do not update managed entities one by one like standard operations. They can bypass entity lifecycle callbacks and dirty checking.

Avoid bulk queries if business logic relies on callbacks, cascades, or logic executed per entity change without designing how to handle them.

## 7. Complete Repository Example

Illustrative entity:

~~~java
package com.example.library;

import java.math.BigDecimal;

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

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private String author;

    @Column(nullable = false, unique = true)
    private String isbn;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean published;

    protected Book() {
    }

    public Book(
            String title,
            String author,
            String isbn,
            BigDecimal price,
            boolean published) {
        this.title = title;
        this.author = author;
        this.isbn = isbn;
        this.price = price;
        this.published = published;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthor() {
        return author;
    }

    public String getIsbn() {
        return isbn;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isPublished() {
        return published;
    }
}
~~~

Repository combining all three groups—inherited CRUD, derived queries, and explicit queries:

~~~java
package com.example.library;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookRepository extends JpaRepository<Book, Long> {

    // Derived query: Spring Data infers conditions from the method name.
    List<Book> findByAuthorIgnoreCaseAndPublishedTrueOrderByTitleAsc(
            String author);

    Optional<Book> findByIsbn(String isbn);

    boolean existsByTitleIgnoreCase(String title);

    long countByPublishedTrue();

    Page<Book> findByPublishedTrue(Pageable pageable);

    // Declared JPQL query: query written explicitly with @Query.
    @Query("""
           select b
           from Book b
           where lower(b.title) like lower(concat('%', :keyword, '%'))
           """)
    List<Book> searchTitle(@Param("keyword") String keyword);

    // Native SQL: uses database table/column names.
    @Query(
        value = "select * from books where author = :author",
        nativeQuery = true
    )
    List<Book> findByAuthorNative(@Param("author") String author);

    // Bulk update: requires @Modifying and a transaction when invoked.
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update Book b set b.published = true where b.id = :id")
    int publishById(@Param("id") Long id);
}
~~~

This example shows that save(), findById(), findAll(), and deleteById() do not need to be redeclared. Only business-specific queries are added to the interface.

## 8. Comparing the Two Method Groups

| Criterion | Inherited CRUD | Declared Query Methods |
|---|---|---|
| Definition source | Spring Data foundational interfaces | Application's repository interface |
| Purpose | General CRUD and standard repository operations | Queries based on business criteria |
| Usage | Call directly after extending JpaRepository | Declare new methods |
| Query creation | Standard Spring Data implementation | Method name parsing or @Query |
| Examples | save, findById, findAll, deleteById | findByAuthor, existsByIsbn, searchTitle |
| Customizability | Standard, generic behavior | Can describe conditions, joins, projections, and custom SQL |
| When to use | When operations match basic CRUD | When filtering, searching, counting, paginating, or custom business queries are needed |

Also distinguish the two types of declared query methods:

| Type | How Defined | Best Fit |
|---|---|---|
| Derived query | Named by convention, e.g., findByAuthorAndPublishedTrue | Simple conditions, readable names |
| Declared query | Written in JPQL/SQL with @Query | Complex conditions, joins, projections, or specialized SQL |

## 9. Which Approach Should You Choose in Each Situation?

- Save a new entity or update an entity: use save().
- Find an entity by primary key: use findById().
- Fetch all entities: use findAll(), considering pagination for large datasets.
- Delete by primary key: use deleteById().
- Find by one or a few properties: use a derived query such as findByAuthorIgnoreCase().
- Check whether records matching a condition exist: use existsBy...().
- Count matching records: use countBy...().
- Query with multiple conditions where the name stays short and clear: continue using derived queries.
- Query with joins, expressions, or complex structure: consider @Query JPQL.
- Query needing database-specific features: consider native SQL and check compatibility.
- Dynamic query with many optional filters: consider Specification, Criteria API, Querydsl, or a custom repository implementation.

Avoid creating excessively long, hard-to-read, hard-to-verify method names. When a derived query name grows complex, switch to @Query or a more suitable query mechanism.

## 10. Common Errors

| Error | Cause | Fix |
|---|---|---|
| No property found for type | Property name in derived query does not exist on entity | Check spelling and Java property paths |
| Failed to create query for method | Method name violates conventions or parameter types do not match | Check keywords, data types, and property names |
| Incorrect JPQL | Using SQL table/column names in JPQL | Use entity names and Java properties |
| Native query fails when switching DB | SQL relies on dialect or column naming specifics | Verify syntax for target DB and write integration tests |
| NonUniqueResultException | Method returns single entity/Optional while query produces multiple rows | Use List or enforce uniqueness with constraints |
| Modifying query requires transaction | UPDATE/DELETE executed outside a transaction | Call from a @Transactional service or configure transactions appropriately |
| In-memory entities do not reflect bulk update | Bulk query bypasses managed entity state | Flush/clear persistence context or reload entities |
| findAll is slow | Loads an entire large table into memory | Use Pageable or Slice |

Derived query errors are typically detected when Spring starts up and creates repositories. Therefore, run the application or repository tests after adding or editing method names rather than relying solely on successful compilation.

## 11. Testing Repositories

You can use @DataJpaTest to verify entity mappings and query methods within the persistence slice. Example:

~~~java
package com.example.library;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private BookRepository repository;

    @Test
    void findsPublishedBooksByAuthorIgnoringCase() {
        repository.save(new Book(
                "Spring in Action",
                "Craig Walls",
                "ISBN-001",
                new BigDecimal("39.90"),
                true));

        repository.save(new Book(
                "Another Book",
                "Craig Walls",
                "ISBN-002",
                new BigDecimal("29.90"),
                false));

        var result = repository
                .findByAuthorIgnoreCaseAndPublishedTrueOrderByTitleAsc(
                        "CRAIG WALLS");

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getTitle()).isEqualTo("Spring in Action");
    }

    @Test
    void findsBookByInheritedIdMethod() {
        Book saved = repository.save(new Book(
                "Effective Java",
                "Joshua Bloch",
                "ISBN-003",
                new BigDecimal("45.00"),
                true));

        var found = repository.findById(saved.getId());

        assertThat(found).isPresent();
        assertThat(found.get().getIsbn()).isEqualTo("ISBN-003");
    }
}
~~~

@DataJpaTest typically configures an embedded test database if one is on the classpath and runs each test in a transaction that rolls back afterward. If you need to verify MySQL- or PostgreSQL-specific SQL behavior, test against that exact database engine, for example via Testcontainers.

## 12. Self-Assessment Checklist

- [ ] Can explain that JpaRepository provides inherited CRUD methods.
- [ ] Knows that save() can insert new entities or update existing ones.
- [ ] Can distinguish findById() from getReferenceById().
- [ ] Can build derived queries from property names and keywords.
- [ ] Can choose the right return type: List, Optional, Page, or Slice.
- [ ] Knows how to use Pageable and Sort for pagination/sorting.
- [ ] Can write JPQL with @Query and bind parameters with @Param.
- [ ] Can distinguish JPQL from native SQL.
- [ ] Knows how to use @Modifying for UPDATE/DELETE and place transactions properly.
- [ ] Understands the impact of bulk queries on the persistence context.
- [ ] Knows when to use inherited CRUD, derived queries, @Query, or custom repositories.
- [ ] Can write tests for both inherited methods and declared query methods.

## 13. Conclusion

Inherited CRUD from JpaRepository covers the general data operations most repositories need. Declared query methods add business-specific querying capabilities without writing repository implementation classes manually.

For simple conditions, derived queries are concise and easy to maintain. For complex queries, @Query makes the JPQL or SQL to execute explicit. Choosing the right method category reduces duplication, keeps repositories clear, and makes data access behavior easy to test.
