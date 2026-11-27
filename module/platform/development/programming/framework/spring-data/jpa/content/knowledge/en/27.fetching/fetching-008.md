# LazyInitializationException and Designing Data Read Boundaries

Hibernate uses lazy loading to defer loading associations until the application actually accesses that data. This avoids fetching unnecessary relationships, but the entity must still be attached to an active persistence context when Hibernate needs to query the database.

**LazyInitializationException** commonly occurs when code accesses a LAZY proxy or collection after the persistence context/Session has closed. A typical scenario is a service returning an entity to a controller, the transaction ending, and then the JSON serializer accessing a collection while rendering the response.

The sustainable fix is to design clear **data read boundaries**: determine which fields and associations a use case needs, load them inside the transaction using a suitable fetch plan, and convert to a DTO before leaving the service. This lesson explains the error mechanism, the role of transactions and OSIV, how to use `EntityGraph`, `JOIN FETCH`, DTO projections, batch fetching, and how to write tests that catch N+1.

**Example prerequisites:** code snippets use Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate, and Spring MVC. Applications require **spring-boot-starter-data-jpa**, **spring-boot-starter-web**, a JDBC driver, a DataSource, and a matching schema. These are parts of a Spring Boot application, not standalone programs runnable solely via `javac`.

## 1. Lazy Loading and the Persistence Context

A LAZY association is loaded when the application accesses it, rather than eagerly alongside the parent entity.

Example where `Author` has many `Book`s:

~~~java
@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(
        mappedBy = "author",
        fetch = FetchType.LAZY,
        cascade = CascadeType.PERSIST
    )
    private List<Book> books = new ArrayList<>();

    protected Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public void addBook(Book book) {
        books.add(book);
        book.assignAuthor(this);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<Book> getBooks() {
        return books;
    }
}
~~~

`Book` side:

~~~java
@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private Author author;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    void assignAuthor(Author author) {
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

When calling:

~~~java
Author author = entityManager.find(Author.class, 1L);
~~~

Hibernate may query only the `authors` table. The `books` collection is represented by an uninitialized persistent collection. When calling:

~~~java
int count = author.getBooks().size();
~~~

if the persistence context is still open, Hibernate executes a query to load the related `Book`s.

The persistence context is JPA's entity-management region, typically bound by Spring to a transaction in service code. Hibernate `Session` is the concrete Hibernate API backing the persistence context in typical setups.

## 2. When Does LazyInitializationException Occur?

If a LAZY association is uninitialized and the entity has become detached, Hibernate no longer has a `Session` to run supplementary queries.

Common failure flow:

~~~text
Controller
    |
    v
Calls service
    |
    v
@Transactional service
    |
    +--> repository loads Author
    |
    +--> books remains LAZY, uninitialized
    |
    v
Service finishes, transaction/persistence context closes
    |
    v
Controller receives detached Author
    |
    v
JSON serializer calls author.getBooks()
    |
    v
Hibernate needs a Session to load books
    |
    v
LazyInitializationException
~~~

Example:

~~~java
@Service
public class AuthorService {

    private final AuthorRepository repository;

    public AuthorService(AuthorRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Author findEntity(Long id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

Controller returning the entity directly:

~~~java
@GetMapping("/authors/{id}")
public Author getAuthor(@PathVariable Long id) {
    return authorService.findEntity(id);
}
~~~

When the service returns, the transaction-scoped persistence context typically closes. If no other persistence context holds the entity, `Author` becomes detached. If the serializer accesses the uninitialized `books`, Hibernate can throw `LazyInitializationException`.

Notes:

- The error happens when accessing an uninitialized proxy or collection, not simply because LAZY is used.
- If the association was already loaded before the context closed, reading it afterward does not throw this error.
- If the association is not needed, do not access it just for serialization.
- `LazyInitializationException` is a Hibernate-specific exception; other JPA providers may surface lazy-access errors differently.

## 3. @Transactional Does Not Automatically Load Every Association

A common misconception is that adding **@Transactional** to a service solves every `LazyInitializationException`.

A transaction keeps the persistence context active during execution, but does not automatically load all LAZY associations. If code accesses an association inside the transaction, Hibernate can load it. If code does not access it, the association may still be uninitialized when the transaction ends.

Example:

~~~java
@Transactional(readOnly = true)
public AuthorDetailDto getDetail(Long id) {
    Author author = repository.findById(id).orElseThrow();

    // Accessed inside the transaction, so the collection can be loaded here.
    List<String> titles = author.getBooks().stream()
        .map(Book::getTitle)
        .toList();

    return new AuthorDetailDto(author.getId(), author.getName(), titles);
}
~~~

This snippet transforms the needed data into a DTO while the persistence context is active. However, if a page has many `Author`s and a mapper accesses each one's `books`, the code can still trigger N+1 queries. Pair transaction boundaries with an appropriate fetch plan.

Points about Spring transactions:

- Spring typically applies `@Transactional` through proxies.
- Calling a transactional method from another method on the same object (self-invocation) usually bypasses the proxy, so the annotation may not start a new transaction as expected.
- The service transaction should span both reading and DTO mapping.
- `@Transactional(readOnly = true)` expresses read intent and allows provider optimizations, but does not make entities strictly read-only or automatically fetch associations.

## 4. Data Read Boundary: Return a DTO Before Leaving the Service

An easy-to-control design is having services return DTOs instead of entities. The service is responsible for fetching the right data and converting it within the transaction.

DTOs:

~~~java
package com.example.author.dto;

import java.util.List;

public record AuthorDetailDto(
    Long id,
    String name,
    List<BookSummaryDto> books
) {
}

public record BookSummaryDto(
    Long id,
    String title
) {
}
~~~

Service:

~~~java
@Service
public class AuthorService {

    private final AuthorRepository repository;

    public AuthorService(AuthorRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public AuthorDetailDto getDetail(Long id) {
        Author author = repository.findWithBooksById(id)
            .orElseThrow();

        List<BookSummaryDto> books = author.getBooks().stream()
            .map(book -> new BookSummaryDto(
                book.getId(),
                book.getTitle()
            ))
            .toList();

        return new AuthorDetailDto(
            author.getId(),
            author.getName(),
            books
        );
    }
}
~~~

Once the method returns, the DTO already holds the needed data and does not depend on a Hibernate `Session`. The controller simply returns the DTO:

~~~java
@GetMapping("/authors/{id}")
public AuthorDetailDto getAuthor(@PathVariable Long id) {
    return authorService.getDetail(id);
}
~~~

This draws a clean boundary: repositories/services work with entities inside the persistence context; controllers and serializers work with independent DTOs.

## 5. Using @EntityGraph to Declare a Fetch Plan

**@EntityGraph** lets you specify associations to load alongside a repository query. This declares a fetch plan per use case without modifying the entity's default fetch types.

Repository:

~~~java
public interface AuthorRepository
        extends JpaRepository<Author, Long> {

    @EntityGraph(attributePaths = "books")
    @Query("select a from Author a where a.id = :id")
    Optional<Author> findWithBooksById(@Param("id") Long id);
}
~~~

When calling this method, Spring Data instructs the JPA provider to load `Author` along with its `books` association per the entity graph. Once the query completes, the service can iterate `books` inside the transaction to build the DTO.

Advantages:

- The fetch plan lives close to the use case's repository method.
- No need to switch every query of `Author` to EAGER.
- Multiple associations can be listed via `attributePaths`.
- Named entity graphs declared on the entity can also be referenced.

Example loading both `books` and `publisher` details:

~~~java
@EntityGraph(attributePaths = {"books", "books.publisher"})
@Query("select a from Author a where a.id = :id")
Optional<Author> findDetailById(@Param("id") Long id);
~~~

Paths must match entity associations. Final SQL behavior depends on the provider and graph type; inspect the actual SQL.

`EntityGraph` is a fetch plan directive, not a guarantee of a single SQL statement in all cases. If a graph contains multiple collections, the provider may issue multiple queries or complex joins; measure performance and inspect row counts.

## 6. Using JOIN FETCH in JPQL

Another option is declaring a fetch join directly in JPQL:

~~~java
public interface AuthorRepository
        extends JpaRepository<Author, Long> {

    @Query("""
        select distinct a
        from Author a
        left join fetch a.books
        where a.id = :id
        """)
    Optional<Author> findDetailById(@Param("id") Long id);
}
~~~

**JOIN FETCH** both joins the association and instructs the provider to initialize it in the result. Use `LEFT JOIN FETCH` when you still want `Author` returned even if there are no `Book`s.

The **distinct** keyword expresses the intent that each `Author` appears once in the logical result even though joining a collection produces multiple SQL rows for the same `Author`. Exact deduplication mechanics can differ by provider/version; always inspect results and SQL.

You can fetch join to-one relationships:

~~~java
@Query("""
    select b
    from Book b
    join fetch b.author
    where b.id = :id
    """)
Optional<Book> findWithAuthorById(@Param("id") Long id);
~~~

Fetch join fits well when a specific query's fetch plan is well defined. Avoid adding fetch joins for every association to every query, as that over-fetches data and multiplies rows.

## 7. Caution When Paginating with Collection Fetch Joins

Paginating alongside a collection fetch join requires special attention:

~~~java
@Query("""
    select distinct a
    from Author a
    left join fetch a.books
    """)
Page<Author> findAuthorsWithBooks(Pageable pageable);
~~~

One `Author` with many `Book`s generates multiple SQL rows. Applying limit/offset to joined rows may no longer correspond to the desired number of `Author`s. Hibernate may have to paginate in memory or emit warnings/errors depending on configuration.

Common solutions:

1. Paginate `Author` IDs first, then run a fetch query for details on that ID list.
2. Use a DTO projection to select only needed columns.
3. Use `EntityGraph`/to-one fetches appropriately and avoid fetching collections inside paginated queries.
4. For screens needing child lists, load collections in a controlled subsequent step.

Two-step example:

~~~java
Page<Long> authorIds = repository.findIdsByActiveTrue(pageable);

List<Author> authors =
    repository.findWithBooksByIdIn(authorIds.getContent());
~~~

Repository:

~~~java
@Query(
    value = "select a.id from Author a where a.active = true",
    countQuery = "select count(a) from Author a where a.active = true"
)
Page<Long> findIdsByActiveTrue(Pageable pageable);

@Query("""
    select distinct a
    from Author a
    left join fetch a.books
    where a.id in :ids
    """)
List<Author> findWithBooksByIdIn(@Param("ids") Collection<Long> ids);
~~~

Both steps should execute in an appropriate transaction if consistent reads within the same persistence context are required. The second step's result may not preserve the ID list order; if order matters, re-sort by ID position or add an appropriate `ORDER BY`.

## 8. Direct DTO Projections from Queries

If a use case only needs read data, repositories can return DTOs directly instead of loading entities and mapping them.

DTO:

~~~java
public record BookListItemDto(
    Long id,
    String title,
    String authorName
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.catalog.dto.BookListItemDto(
        b.id,
        b.title,
        a.name
    )
    from Book b
    join b.author a
    where b.status = :status
    order by b.title
    """)
List<BookListItemDto> findBookList(
    @Param("status") BookStatus status
);
~~~

The JPQL constructor expression selects the exact three values needed. The returned DTO is not a managed entity and has no LAZY associations for a serializer to traverse.

DTO projections typically fit:

- List APIs or reports.
- Read-only screens needing a few fields across multiple tables.
- Queries with joins where entity updates are unnecessary.
- Use cases needing exact column control while avoiding full entity materialization.

If pagination is needed, the method can return `Page<DTO>`, provided the count query matches the join/filter logic.

## 9. N+1 and How Batch Fetching Reduces Queries

N+1 happens when one query loads a list of parent entities and each entity then triggers a separate query to load a LAZY association.

Example:

~~~java
List<Author> authors = authorRepository.findAll();

for (Author author : authors) {
    System.out.println(author.getBooks().size());
}
~~~

With 100 `Author`s, Hibernate may execute one query for `Author`s plus 100 queries for `books`. That is N+1.

### Using Batch Fetching

Hibernate can group multiple uninitialized associations into batched queries.

On a collection:

~~~java
@BatchSize(size = 32)
@OneToMany(mappedBy = "author", fetch = FetchType.LAZY)
private List<Book> books = new ArrayList<>();
~~~

Or global default configuration:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 32
~~~

When code accesses collections on multiple `Author`s within the same `Session`, Hibernate can load the association for multiple `Author`s via an `IN` query instead of one query per `Author`.

Batch fetching reduces round-trips, though it still requires an open `Session`. Nor does it guarantee a single query; batch count depends on entity count, batch size, provider, and database.

### When to Use EntityGraph, JOIN FETCH, or Batch Fetching?

| Approach | Appropriate When | Trade-off |
|---|---|---|
| EntityGraph | Fetch plan varies by repository use case | Exact SQL chosen by provider |
| JOIN FETCH | Want to explicitly declare fetched associations in query | Collection joins can multiply rows and complicate pagination |
| DTO projection | Need only read data with explicit column selection | Requires defining DTOs/queries per read model |
| Batch fetching | Multiple LAZY associations accessed in groups | Still issues supplementary queries and requires an open Session |
| Hibernate.initialize | Need to initialize a specific association within a Session | Hibernate-dependent and can obscure fetch plans if overused |

## 10. What Is OSIV and Why Should You Not Rely on It?

**Open EntityManager in View (OSIV)** keeps the `EntityManager` open across the entire HTTP request lifecycle. As a result, LAZY associations can still be loaded when a controller or JSON serializer accesses them after the service transaction ends.

In Spring Boot web applications, OSIV may be enabled by default depending on configuration. It can be disabled explicitly:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

With OSIV disabled, accessing uninitialized associations after the transaction surfaces immediately as `LazyInitializationException`. This is a useful signal for spotting APIs that rely on lazy loading outside service boundaries.

OSIV can hide problems:

- SQL can execute while the serializer generates JSON.
- N+1 queries arise easily without being obvious in service code.
- Database access extends through the end of the HTTP request.
- Controllers/serializers inadvertently dictate the fetch plan.
- API performance becomes harder to predict and test at the service layer.

OSIV is not always wrong, but it should not be used as the default fix for `LazyInitializationException`. Designing services to return DTOs with intentionally loaded data is usually easier to control.

## 11. Do Not Switch Every Association to EAGER to Fix Errors

A common reaction is switching LAZY to EAGER to avoid exceptions. This can cause queries to over-fetch data across every use case.

For example, if `Author.books` is EAGER, every `Author` query may load the entire `books` collection even when a screen needs only the author's name. That can:

- Increase joined rows and transferred data volume.
- Trigger supplementary queries depending on provider.
- Cause N+1 on EAGER associations not fetched with the query.
- Make pagination harder to predict.
- Increase memory usage and entity materialization cost.

Under JPA, EAGER is a fetch requirement, whereas LAZY is a hint that providers can handle flexibly. For to-one relationships, JPA defaults to EAGER; for to-many, it defaults to LAZY. In Hibernate applications, many teams choose LAZY for associations and specify fetch plans per use case.

Do not treat LAZY as an absolute guarantee that the provider will never load early, or EAGER as a guarantee that everything is fetched in one JOIN. Inspect actual SQL.

## 12. Explicit Initialization: Use Only with Clear Reason

Hibernate provides:

~~~java
Hibernate.initialize(author.getBooks());
~~~

This initializes a proxy or collection while the `Session` is active. It can be useful in some Hibernate-specific code, though services should prefer declaring fetch plans via `EntityGraph`, `JOIN FETCH`, or DTO queries.

Do not call `Hibernate.initialize` after an entity is detached; there is no longer an active `Session` to load data, and lazy access errors can still occur.

You can check loaded state without triggering initialization using JPA's `PersistenceUtil`:

~~~java
boolean loaded = Persistence
    .getPersistenceUtil()
    .isLoaded(author, "books");
~~~

With Hibernate, you can also use **Hibernate.isInitialized(...)**. These inspection APIs are useful in tests or diagnostics, and should not become primary business branching logic.

## 13. Do Not Let the JSON Serializer Control Data Loading

If a controller returns an entity, Jackson may invoke getters to generate JSON. When a getter accesses a LAZY proxy/collection, the serializer unintentionally triggers database queries.

Bidirectional relationships can also create cycles:

~~~text
Author
  -> books
       -> author
            -> books
                 -> ...
~~~

Jackson annotations such as **@JsonIgnore** or **@JsonManagedReference/@JsonBackReference** can address some serialization cycles, but do not solve the underlying issue of using persistence entities as API response contracts.

A cleaner approach:

1. Service determines the data the endpoint needs.
2. Repository loads data according to the fetch plan.
3. Service converts entities into DTOs inside the transaction.
4. Controller serializes DTOs without accessing entities/proxies.

If an API has multiple response shapes, create dedicated DTOs per use case instead of overloading one entity with serialization annotations.

## 14. Distinguishing Lazy Access Errors from Transaction Errors

Not every error when accessing entities outside a transaction is a `LazyInitializationException`.

| Scenario | Possible Behavior |
|---|---|
| Reading an already-loaded basic field on a detached entity | Usually readable because the value resides in the object |
| Reading an uninitialized LAZY collection after Session closes | Hibernate may throw `LazyInitializationException` |
| Calling persist/remove without an active transaction | May encounter `TransactionRequiredException` or transaction errors |
| Accessing a LAZY association inside an active transaction | Provider can load the association |
| Using a detached entity and calling merge | `merge` creates/returns a managed copy per JPA semantics |

Transactions, persistence contexts, and entity states are related but distinct concepts. A transaction manages commit/rollback boundaries; a persistence context tracks entities; a detached entity is no longer managed by that context.

## 15. Testing LazyInitializationException and Its Fix

To reliably reproduce the error, let the service transaction end before accessing the association. Disable OSIV in tests so HTTP requests do not keep the `EntityManager` open.

Service intentionally returning an entity:

~~~java
@Transactional(readOnly = true)
public Author findEntity(Long id) {
    return authorRepository.findById(id).orElseThrow();
}
~~~

Integration test:

~~~java
@SpringBootTest(properties = "spring.jpa.open-in-view=false")
class AuthorLazyLoadingTest {

    @Autowired
    private AuthorService authorService;

    @Test
    void accessingUninitializedCollectionAfterServiceReturnsFails() {
        Author author = authorService.findEntity(existingAuthorId);

        assertThatThrownBy(() -> author.getBooks().size())
            .isInstanceOf(LazyInitializationException.class);
    }
}
~~~

The test assumes `Author` data exists and `books` is uninitialized. The test must not be annotated with `@Transactional` at the class or method level, otherwise the test transaction would keep the persistence context open and mask the error.

Test for the fix:

~~~java
@Test
void dtoContainsBooksLoadedInsideServiceTransaction() {
    AuthorDetailDto detail = authorService.getDetail(existingAuthorId);

    assertThat(detail.books()).isNotEmpty();
}
~~~

`getDetail` uses `EntityGraph` or `JOIN FETCH` to load `books` and maps to a DTO inside the transaction. After returning, the DTO remains readable because it does not depend on a Hibernate `Session`.

When testing for N+1, seed multiple `Author`s with multiple `Book`s, enable SQL logging or Hibernate Statistics, and confirm query counts do not scale linearly with `Author` count. Test both empty collections and multi-element associations.

## 16. Common Mistakes

| Symptom | Cause | Solution |
|---|---|---|
| LazyInitializationException during JSON serialization | Controller returns entity with unloaded associations | Map to DTO inside the transaction |
| Added @Transactional yet still fails | Association not accessed inside transaction or transaction proxy bypassed | Check call path, fetch plan, and self-invocation |
| Switching to EAGER slows queries | All use cases load unneeded data | Keep fetch plans scoped per use case |
| Disabling OSIV breaks API | API relied on lazy loading during serialization | Load required data inside the service |
| N+1 remains even without exceptions | Mapper/serializer accesses collections per entity | `EntityGraph`, DTO queries, or batch fetching |
| Page is wrong/expensive when fetching collections | Collection join multiplies rows during pagination | Paginate IDs first then fetch details |
| Hibernate.initialize still fails | Called after Session closed | Initialize in transaction or change fetch plan |
| DTO mapper triggers many SQLs | Mapper reads unfetched LAZY associations | Pick query/fetch plan before mapping |
| JSON has Author-Book cycle | Serializing bidirectional relationship directly | Use DTOs for responses |
| Test fails to reproduce error | Test transaction or OSIV keeps context open | Test outside transaction and disable OSIV |

## 17. Data Read Boundary Design Checklist

- [ ] Identify which fields and associations each endpoint/use case needs.
- [ ] Keep associations LAZY where appropriate; do not switch everything to EAGER to fix exceptions.
- [ ] Use a service transaction spanning both data reads and DTO mapping.
- [ ] Verify `@Transactional` actually executes through the Spring proxy.
- [ ] Use `EntityGraph` or `JOIN FETCH` for needed associations.
- [ ] Use direct DTO projections when only read data is needed.
- [ ] Avoid collection fetches with pagination unless cardinality is handled.
- [ ] Use batch fetching when multiple LAZY collections are accessed in groups.
- [ ] Do not let the JSON serializer dictate the fetch plan.
- [ ] Evaluate whether OSIV fits; prefer response DTOs independent of the persistence context.
- [ ] Inspect SQL to detect N+1 and over-fetching.
- [ ] Test both closed-Session scenarios and uninitialized associations.

## 18. Conclusion

**LazyInitializationException** typically happens when Hibernate needs to load a LAZY proxy or collection, but the entity is detached and the `Session` has closed. `@Transactional` only keeps the persistence context alive within transaction boundaries; it does not automatically fetch every association.

Design data read boundaries per use case: load required associations with `EntityGraph` or `JOIN FETCH`, or query DTOs directly; map data inside the transaction and return DTOs from controllers. Check OSIV, N+1, collection pagination, and actual SQL so APIs never rely on serializers accidentally touching entities after transactions end.