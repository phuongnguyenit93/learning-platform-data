# Persistence Context and Nested Fields

In a Spring for GraphQL application using Spring Data JPA, a root resolver may load an entity and return it to GraphQL. GraphQL then invokes resolvers for nested fields such as `author`, `reviews`, or `category`. If child fields access lazy associations after the root service's transaction has ended, the application can hit a `LazyInitializationException`. If Open EntityManager in View is enabled, the exception may disappear, yet SQL queries are silently fired while GraphQL resolves each field, leading to N+1 queries and unpredictable database access times.

To handle this properly, three concepts must be understood:

- Persistence context is the scope within which an `EntityManager` tracks managed entities.
- Transaction is the commit/rollback and isolation boundary of database operations.
- A nested GraphQL field is a field resolution based on the source object returned by its parent field.

These three scopes are related but not identical. An entity can remain in a persistence context after the transaction ends if the application uses Open EntityManager in View. Conversely, the transaction may finish and the persistence context may close right when the service method returns. Resolver design must explicitly determine which data should be preloaded, which should be fetched via a separate service, and which should be batched with DataLoader.

## What Is a Persistence Context?

A persistence context is the set of entity instances managed by an `EntityManager`. Within a persistence context, JPA maintains entity identity: the same entity type and primary key resolve to the same managed instance.

The persistence context is responsible for:

- Tracking new entities, loaded entities, and entities marked for removal.
- Detecting changes on managed entities to synchronize with the database.
- Maintaining an identity map, avoiding creating multiple managed instances for the same record within the same context.
- Managing lazy proxies and persistent collections.
- Synchronizing changes to the database upon flush or commit.

The persistence context is often referred to as the first-level cache. It is tied to an `EntityManager`, not shared across the whole application. When the `EntityManager` closes or an entity is detached, the persistence context no longer tracks that entity.

## Entity Lifecycle in JPA

An entity can transition through the following states:

| State | Meaning | Example |
| --- | --- | --- |
| New / transient | Newly created Java object, not yet managed by a persistence context | `new BookEntity(...)` |
| Managed | Entity is currently tracked by an `EntityManager` | `find()`, `getReference()`, `persist()` |
| Detached | Entity was previously managed but separated from the persistence context | Entity after `EntityManager` closes or `detach()` |
| Removed | Managed entity marked for deletion | `remove(entity)` |

Simple lifecycle diagram:

~~~mermaid
stateDiagram-v2
    [*] --> Transient
    Transient --> Managed: persist()
    Managed --> Detached: detach() / clear() / close()
    Detached --> Managed: merge() returns managed copy
    Managed --> Removed: remove()
    Removed --> [*]: commit
~~~

Common operations:

- `persist(entity)`: moves a new entity into the managed state; an `INSERT` statement may execute on flush or commit.
- `find(...)`: retrieves an entity; if it is already in the persistence context, the tracked managed instance can be returned.
- `detach(entity)`: detaches a single entity from the persistence context.
- `clear()`: detaches all currently managed entities.
- `close()`: closes the `EntityManager` and ends the persistence context.
- `remove(entity)`: marks a managed entity for deletion upon flush/commit.
- `merge(detached)`: copies state from a detached object onto a managed instance and returns that managed instance.

A common pitfall is that `merge()` does not make the original detached object managed. Use the returned instance instead:

~~~java
BookEntity managedBook = entityManager.merge(detachedBook);
managedBook.setTitle("New title");
~~~

If you keep modifying `detachedBook`, those changes are not tracked by the persistence context.

## EntityManager and Transactions

`EntityManager` is the API for interacting with the persistence context. `EntityManagerFactory` can be shared across threads, whereas an actual `EntityManager` instance is not thread-safe and must not be used concurrently from multiple threads.

In Spring, the common injection style is:

~~~java
@Repository
public class BookDao {

    @PersistenceContext
    private EntityManager entityManager;

    public BookEntity findById(String id) {
        return entityManager.find(BookEntity.class, id);
    }
}
~~~

With the default `PersistenceContextType.TRANSACTION`, Spring injects a shared `EntityManager` proxy. This proxy delegates to the `EntityManager` bound to the current transaction. It does not mean a single real `EntityManager` is shared concurrently across all requests.

When a `@Transactional` service method runs, the Spring transaction manager opens or joins a transaction and binds the corresponding `EntityManager` to the execution context. When the transaction ends, a transaction-scoped `EntityManager` is typically closed or returned to provider management; returned entities become detached unless another persistence context retains them.

Do not store an actual `EntityManager` in static fields, singleton state, or share it among concurrently running resolvers. Inject the shared proxy via `@PersistenceContext` or use Spring Data repositories so Spring selects the right `EntityManager` for the active transaction.

## Flush Is Not Commit

The persistence context can buffer changes in memory before sending SQL to the database. Flushing synchronizes managed entity state with the current database connection:

~~~java
entityManager.flush();
~~~

Flushing does not end the transaction and does not mean data has been committed. The transaction can continue and later roll back all flushed changes. Committing is the step that finalizes the transaction according to database rules.

For read-only queries, Hibernate can optimize dirty checking or flush behavior when the transaction is marked read-only. However, read-only does not replace the persistence context and does not automatically detach entities.

## How Nested GraphQL Fields Use the Source Object

GraphQL executes the parent field before resolving child fields that depend on its result. The value returned by the parent resolver becomes the source object for nested resolvers.

Schema example:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
  reviews: [Review!]!
}

type Author {
  id: ID!
  name: String!
}

type Review {
  id: ID!
  rating: Int!
}
~~~

Root resolver:

~~~java
@Controller
public class BookController {

    private final BookQueryService bookQueryService;

    public BookController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public BookEntity book(@Argument String id) {
        return bookQueryService.findEntity(id);
    }
}
~~~

Nested resolver:

~~~java
@Controller
public class BookFieldController {

    @SchemaMapping(typeName = "Book", field = "author")
    public AuthorEntity author(BookEntity book) {
        return book.getAuthor();
    }
}
~~~

The `BookEntity book` parameter is the source object returned by the parent field. If `author` is a lazy association, calling `book.getAuthor()` may require a database query.

Crucially, the transaction of `findEntity()` typically ends when the method returns. GraphQL's subsequent resolution of `author` is a separate step. Do not assume the root service's transaction stays open until the entire GraphQL response is built.

## Lazy Associations and LazyInitializationException

JPA allows deferring association loading. With `LAZY`, an entity holds a proxy or persistent collection and queries the database only when code accesses that data.

Entity example:

~~~java
@Entity
public class BookEntity {

    @Id
    private String id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    private AuthorEntity author;

    @OneToMany(mappedBy = "book", fetch = FetchType.LAZY)
    private List<ReviewEntity> reviews = new ArrayList<>();

    // getters
}
~~~

By JPA defaults, to-one relationships like `@ManyToOne` and `@OneToOne` are `EAGER`, whereas to-many relationships like `@OneToMany` and `@ManyToMany` are `LAZY`. You can explicitly specify the fetch mode in mappings; with GraphQL, consider `LAZY` for associations not always selected and define fetch plans per use case.

Service loading only `Book`:

~~~java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public BookEntity findEntity(String id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

If the transaction ends and the persistence context closes before a nested resolver accesses `book.getAuthor().getName()`, Hibernate can no longer load the proxy and may throw `LazyInitializationException`.

This error usually indicates the application is accessing lazy state on a detached entity. Do not solve it by switching every association to `EAGER`. `EAGER` can cause unnecessary data loads, generate extra queries, or make query plans unpredictable.

## EAGER Does Not Guarantee a Single SQL Join

`FetchType.EAGER` only requires the provider to load the association when the entity is fetched. It does not guarantee the association is fetched via a single SQL `JOIN` statement.

For lists of entities, `EAGER` can emit numerous secondary queries. Conversely, `LAZY` defers loading, though it requires clear fetch plans whenever you know which data a GraphQL selection set needs.

Common design guidelines:

- Keep associations `LAZY` when they are not always needed.
- Choose fetch plans per use case or GraphQL field.
- Use DTO projections when the response only needs a subset of data.
- Use `EntityGraph` or fetch joins when specific associations must be loaded.
- Use DataLoader/`@BatchMapping` for relationships loaded across multiple parents.

## Open EntityManager in View (OSIV)

Open EntityManager in View keeps an `EntityManager` open and bound to the request thread throughout web request processing. Its original goal was allowing lazy loading during view rendering even after the service transaction ended.

In Servlet web applications, Spring Boot registers `OpenEntityManagerInViewInterceptor` by default when JPA is configured. It can be disabled with:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

OSIV keeps the persistence context open per request, but it does not keep the service transaction open across the request. Once the service transaction ends, entities may remain managed in the `EntityManager` held by OSIV. If a GraphQL nested resolver accesses a lazy association on the same request thread, the provider can execute additional SQL even though the original business transaction already finished.

Therefore, leaving OSIV enabled can make `LazyInitializationException` vanish while leaving these problems behind:

- SQL is emitted late inside nested resolvers, making it hard to spot from service methods.
- Each parent entity can trigger a separate lazy query, causing N+1.
- Lazy queries may execute outside the initial business transaction, so they do not share the same snapshot/isolation as the root data.
- GraphQL response workload depends on the number of fields and items requested by the client.
- Persistence contexts and entity state are held longer. When database connections are acquired and released also depends on provider and transaction configuration.

OSIV is not a transaction boundary and should not be used as a data-loading strategy for GraphQL.

### Disable OSIV to Catch Errors Early

In development and integration test environments, consider disabling OSIV:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Then, if a resolver tries to access a lazy association after the transaction, the error surfaces immediately in tests. This is a useful way to catch code that implicitly relies on a request-wide open persistence context.

Disabling OSIV does not force every application to return DTOs for all fields. However, it forces each service/resolver to define explicit data-loading strategies and transaction boundaries.

### OSIV and Asynchronous GraphQL Execution

OSIV binds the `EntityManager` to the request thread and has mechanisms for Servlet async dispatch. However, GraphQL Java can execute data fetchers on another executor, or the application may offload work to a `CompletableFuture`/custom executor.

An actual `EntityManager` is not thread-safe. Do not share an entity manager or persistence context among concurrently running resolvers. Also do not assume a request-thread-bound `EntityManager` is automatically available on every thread spawned by the application.

If a nested resolver runs on a different thread, load data through a dedicated service method with an appropriate transaction or use DataLoader to batch. With JPA, each service invocation must use a Spring-managed `EntityManager` within its own execution context.

## Designing Nested Fields with DTOs

The most controllable pattern is for the service to load all data needed for the use case and convert it into DTOs before the transaction ends.

DTOs:

~~~java
public record AuthorView(String id, String name) {
}

public record BookDetailsView(
        String id,
        String title,
        AuthorView author) {
}
~~~

Service:

~~~java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public BookDetailsView findDetails(String id) {
        BookEntity book = bookRepository.findWithAuthorById(id)
                .orElseThrow(() -> new BookNotFoundException(id));

        AuthorEntity author = book.getAuthor();

        return new BookDetailsView(
                book.getId(),
                book.getTitle(),
                new AuthorView(author.getId(), author.getName()));
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookRepository
        extends JpaRepository<BookEntity, String> {

    @EntityGraph(attributePaths = "author")
    Optional<BookEntity> findWithAuthorById(String id);
}
~~~

The root resolver returns the DTO:

~~~java
@QueryMapping
public BookDetailsView book(@Argument String id) {
    return bookQueryService.findDetails(id);
}
~~~

GraphQL can read `author` from `BookDetailsView` as a plain property. There are no lazy proxies in the response path, and no need to keep a persistence context open while GraphQL processes the `author` field.

DTOs also help control which data is exposed to GraphQL, preventing accidental leakage of internal entity fields.

## Using Projections to Load Only Needed Fields

If a GraphQL response only needs a few scalar fields, projections avoid loading the entire entity.

Interface projection:

~~~java
public interface BookSummary {
    String getId();
    String getTitle();
    String getAuthorName();
}
~~~

Repository:

~~~java
public interface BookRepository
        extends JpaRepository<BookEntity, String> {

    @Query("""
            select b.id as id,
                   b.title as title,
                   a.name as authorName
            from BookEntity b
            join b.author a
            where b.id = :id
            """)
    Optional<BookSummary> findSummaryById(@Param("id") String id);
}
~~~

The projection exposes only the required attributes. Spring Data JPA can generate a proxy projection or execute a DTO projection depending on the projection type and query. There is no need to expose entities or touch lazy collections when GraphQL only selects those three fields.

For DTO class/record projections, declare a constructor matching the `select` clause:

~~~java
public record BookSummaryView(
        String id,
        String title,
        String authorName) {
}
~~~

~~~java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Query("""
        select new com.example.graphql.BookSummaryView(
            b.id, b.title, a.name)
        from BookEntity b
        join b.author a
        where b.id = :id
        """)
Optional<BookSummaryView> findSummaryViewById(@Param("id") String id);
~~~

The class name in a JPQL constructor expression must be the fully qualified class name.

## Using Controlled Fetch Joins

A fetch join loads an association alongside the entity in one query:

~~~java
@Query("""
        select b
        from BookEntity b
        join fetch b.author
        where b.id = :id
        """)
Optional<BookEntity> findWithAuthor(String id);
~~~

After the service fetches `Book` and maps it to a DTO inside the transaction, nested GraphQL fields do not need to access lazy associations.

Fetch joins suit to-one relationships or a single small, bounded collection. Avoid fetch-joining multiple to-many collections simultaneously in the same query, as that multiplies result rows, creates Cartesian products, and breaks pagination or is rejected by the provider.

If you need to paginate `Book` and also load `reviews`, paginate `Book` first and then batch-load `reviews` for the resulting list of IDs. Do not fetch-join a large collection into a paginated query merely to avoid `LazyInitializationException`.

## EntityGraph for Use-Case Fetch Plans

`EntityGraph` describes which associations to load for a query without writing fetch joins in JPQL:

~~~java
public interface BookRepository
        extends JpaRepository<BookEntity, String> {

    @EntityGraph(attributePaths = {"author"})
    Optional<BookEntity> findWithAuthorById(String id);
}
~~~

Nested paths can also be specified:

~~~java
@EntityGraph(attributePaths = {
        "author",
        "publisher.address"
})
Optional<BookEntity> findDetailedById(String id);
~~~

`EntityGraph` is a fetch plan, not a guarantee that the provider will always generate a single SQL statement. Inspect the actual SQL and execution plan when tuning performance.

`EntityGraph` is helpful when a use case requires a stable set of associations. If GraphQL queries have many client-driven field combinations, avoid creating one giant `EntityGraph` for every case; use projections, dedicated query services, or field-level DataLoaders.

## Using DataLoader or @BatchMapping for Nested Collections

A list of Books may request reviews for each Book:

~~~graphql
query Books {
  books {
    id
    title
    reviews {
      id
      rating
    }
  }
}
~~~

If the `reviews` resolver calls the repository once per Book, query count grows with parent count:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<ReviewView> reviews(BookView book) {
    return reviewQueryService.findByBookId(book.id());
}
~~~

With N Books, this can emit N `reviews` queries. DataLoader/`@BatchMapping` gathers the IDs into a single batch.

Batch service:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReviewQueryService {

    private final ReviewRepository reviewRepository;

    public ReviewQueryService(ReviewRepository reviewRepository) {
        this.reviewRepository = reviewRepository;
    }

    @Transactional(readOnly = true)
    public Map<String, List<ReviewView>> findByBookIds(
            Set<String> bookIds) {

        return reviewRepository.findByBookIdIn(bookIds).stream()
                .map(ReviewView::from)
                .collect(Collectors.groupingBy(ReviewView::bookId));
    }
}
~~~

Batch mapping:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookReviewController {

    private final ReviewQueryService reviewQueryService;

    public BookReviewController(ReviewQueryService reviewQueryService) {
        this.reviewQueryService = reviewQueryService;
    }

    @BatchMapping(typeName = "Book", field = "reviews")
    public Map<BookView, List<ReviewView>> reviews(List<BookView> books) {
        Set<String> ids = books.stream()
                .map(BookView::id)
                .collect(Collectors.toSet());

        Map<String, List<ReviewView>> byBook =
                reviewQueryService.findByBookIds(ids);

        Map<BookView, List<ReviewView>> result = new HashMap<>();
        for (BookView book : books) {
            result.put(
                    book,
                    byBook.getOrDefault(book.id(), List.of()));
        }
        return result;
    }
}
~~~

The batch service opens a read-only transaction for querying the set of IDs. Results are converted to DTOs before the method completes. The DataLoader cache is scoped to the GraphQL request; it is not a persistence context and does not provide transaction isolation.

The synchronous `Map` return example suits a Servlet stack or an executor dedicated to blocking data fetchers. With WebFlux, you can return `Mono` and offload the JPA call to `boundedElastic`:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@BatchMapping(typeName = "Book", field = "reviews")
public Mono<Map<BookView, List<ReviewView>>> reviews(
        List<BookView> books) {

    Set<String> ids = books.stream()
            .map(BookView::id)
            .collect(Collectors.toSet());

    return Mono.fromCallable(() -> reviewQueryService.findByBookIds(ids))
            .subscribeOn(Schedulers.boundedElastic())
            .map(byBook -> {
                Map<BookView, List<ReviewView>> result = new HashMap<>();
                for (BookView book : books) {
                    result.put(
                            book,
                            byBook.getOrDefault(book.id(), List.of()));
                }
                return result;
            });
}
~~~

The JPA transaction opens inside the service method when the callable runs on the worker thread. Do not retain an `EntityManager` from the request thread and pass it to `boundedElastic`; let the Spring transaction manager provide the persistence context for that service invocation.

If using entities as keys of the `Map` returned by `@BatchMapping`, ensure stable `equals`/`hashCode`. DTO records usually have value-based equality; for entities whose `equals`/`hashCode` depend on mutable fields or lazy associations, use a stable source DTO or an ID-keyed DataLoader.

## Using ID-Keyed DataLoader to Avoid Entity Keys

Another option is for the root resolver to return a DTO containing `authorId`, and then the nested resolver uses an ID-keyed DataLoader:

~~~java
public record BookView(
        String id,
        String title,
        String authorId) {
}
~~~

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;

@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<AuthorView> author(
        BookView book,
        DataLoader<String, AuthorView> authorLoader) {
    return authorLoader.load(book.authorId());
}
~~~

Batch loader registered via `BatchLoaderRegistry`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Configuration
public class AuthorDataLoaderConfiguration {

    public AuthorDataLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorQueryService authorQueryService) {

        registry.forTypePair(String.class, AuthorView.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        Mono.fromCallable(() ->
                                        authorQueryService.findViewsByIds(authorIds))
                                .subscribeOn(Schedulers.boundedElastic()));
    }
}
~~~

Service:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthorQueryService {

    private final AuthorRepository authorRepository;

    public AuthorQueryService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    @Transactional(readOnly = true)
    public Map<String, AuthorView> findViewsByIds(Set<String> ids) {
        return authorRepository.findAllById(ids).stream()
                .map(AuthorView::from)
                .collect(Collectors.toMap(
                        AuthorView::id,
                        Function.identity()));
    }
}
~~~

DataLoader holds only author IDs and DTO results. JPA entities are loaded and mapped inside the service transaction. Never pass detached entities carrying lazy associations across multiple resolvers.

## Persistence Context Is Not the DataLoader Cache

These two mechanisms serve different purposes:

| Mechanism | Scope | Purpose |
| --- | --- | --- |
| Persistence context | `EntityManager` | Tracks entity state, identity, and dirty checking |
| DataLoader cache | Typically per GraphQL request | Batches and caches data-loading results by key |
| Second-level cache | Per `EntityManagerFactory`/provider | Caches entities/queries across persistence contexts |
| Application cache | Per application configuration | Caches DTOs or business data by key |

DataLoader avoids calling the batch service multiple times for the same key within a GraphQL request. However, DataLoader does not make an entity managed and does not extend the `EntityManager` lifecycle.

Nor does the second-level cache replace the persistence context. It is a provider-level cache, while each transaction still has its own persistence context.

## Parallel Nested Resolvers and EntityManager Limits

GraphQL can resolve independent fields in parallel. For example, a query fetching multiple Books may request both `author` and `reviews` for each Book. Field resolvers may run on executors or via asynchronous data fetchers.

An actual `EntityManager` is not thread-safe. Therefore:

- Do not pass a single real `EntityManager` into multiple concurrently running resolvers.
- Do not manually share a persistence context across threads.
- Do not retain a managed entity and arbitrarily access lazy collections from callbacks running on other threads.
- Use dedicated transactional service methods to load needed data.
- Use DataLoader to batch similar requests and return DTOs.

Spring's shared `EntityManager` proxy allows singleton beans to inject an `EntityManager` safely in a Spring-managed manner. That does not make the underlying `EntityManager` instance thread-safe.

With WebFlux, JPA remains a blocking persistence API. Do not invoke blocking JPA directly on event-loop threads. If the application needs end-to-end reactivity, consider R2DBC and design data access around reactive transactions/contexts; R2DBC does not use JPA `EntityManager` or JPA persistence contexts.

## Data Reads and Consistency Between Nested Fields

If the root service loads `Book` in transaction A while a nested resolver calls the `Author` service in transaction B, the two queries can observe data at two different points in time.

Example:

1. Transaction A reads `Book` and `authorId`.
2. Another transaction updates `Author`.
3. Transaction B reads `Author` after the update.
4. The GraphQL response contains `Book` from the earlier point in time and `Author` from the later point in time.

This may be acceptable for typical informational screens. If business logic requires a consistent snapshot, gather related data in the same service use case and transaction with appropriate isolation, and return an aggregated DTO.

Do not try to keep an `EntityManager` open across the entire GraphQL operation to solve consistency. A long-lived persistence context does not itself create a consistent database snapshot; transaction isolation determines visibility of concurrent changes.

## Testing Nested Fields with OSIV Disabled

Integration tests should run with:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

This helps detect resolvers accessing lazy associations outside transactions.

Scenarios to verify:

| Scenario | What to Verify |
| --- | --- |
| Root query returns Book DTO | GraphQL reads scalar fields without an open `EntityManager` |
| Nested `author` uses projection | `author` field returns expected data without lazy loading |
| Nested field accesses lazy association after transaction | Test catches the error and forces fixing the fetch plan |
| `@EntityGraph`/fetch join | Required associations are loaded before the service returns the DTO |
| List of Books with `reviews` | Batch loader runs in one batch or the expected number of batches |
| DataLoader with duplicate keys | Results are cached within the request per expected semantics |
| Two concurrent requests | No shared `EntityManager` or persistence context state |
| WebFlux and JPA | Blocking JPA does not run on the event loop |

GraphQL test example:

Test dependencies require `spring-graphql-test`. For HTTP client tests, add Spring WebFlux test support if the application does not already have WebFlux on the classpath:

~~~kotlin
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
    testImplementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookNestedFieldTests {

    @Autowired
    private HttpGraphQlTester graphQlTester;

    @Test
    void shouldResolveAuthorWithoutOpenEntityManagerInView() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                        author {
                            id
                            name
                        }
                    }
                }
                """)
                .execute()
                .path("book.author.name")
                .entity(String.class)
                .isEqualTo("Ada Lovelace");
    }
}
~~~

The test requires seed data with `book-42` and its corresponding author. The goal is running full GraphQL execution with OSIV disabled and verifying nested fields still work via fetch plans/DTOs or batch services.

With Spring Boot and `RANDOM_PORT`, `HttpGraphQlTester` is auto-configured for the live server when `spring-graphql-test` is present. When using a mock web environment, add `@AutoConfigureHttpGraphQlTester`; the annotation package differs across Spring Boot versions.

Annotation package examples:

- Spring Boot 4.x: `org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureHttpGraphQlTester`.
- Spring Boot 3.5: `org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester`.

To detect N+1, count SQL statements in tests using a DataSource proxy or Hibernate statistics. For example, with 20 Books, verify the number of `reviews` queries does not grow to 20. Do not verify only the response values, because N+1 can still return accurate data.

## Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `LazyInitializationException` in nested field | Persistence context closed before child field accessed lazy association | Load associations in the service or return DTOs/projections |
| GraphQL breaks when OSIV is disabled | Code relied on an `EntityManager` kept open across the HTTP request | Design explicit fetch plans or batch resolvers |
| OSIV enabled but queries are slow | Lazy loading triggers inside each nested resolver | Use DataLoader/`@BatchMapping` and measure SQL counts |
| `EAGER` still produces multiple SQL queries | `EAGER` does not guarantee a single join | Use `EntityGraph`, fetch join, or appropriate projections |
| Entity is stale or fails to update | Using detached objects or wrong object reference after `merge` | Use the managed instance returned by `merge` and control transactions |
| Nested resolver runs on a different thread | Thread-bound persistence context is not shared | Call a dedicated service or DataLoader; never share `EntityManager` |
| Concurrent resolvers fail using `EntityManager` | Actual `EntityManager` used concurrently | Do not share persistence contexts across threads |
| `@BatchMapping` finds no match | Map key does not match source object or `equals`/`hashCode` is unstable | Use stable DTO keys or ID-keyed DataLoader |
| N+1 despite having a transaction | Transactions do not automatically batch SQL | Use DataLoader, `@BatchMapping`, or set-based ID queries |
| Fetch-join pagination returns wrong results | Collection fetch join multiplies rows and skews pagination | Page parents first, batch-load collections afterward |
| WebFlux stalls | Blocking JPA runs on event-loop threads | Offload blocking work to an appropriate scheduler or use R2DBC |
| Response reads data from different timestamps | Root and nested services run separate transactions | Gather data in one use case if a consistent snapshot is needed |

## Principles for Designing Persistence Contexts for Nested Fields

When implementing GraphQL with JPA, remember:

1. **Understand the entity lifecycle.** Managed entities are only tracked inside a persistence context; detached entities no longer provide reliable lazy loading.
2. **Distinguish transactions from persistence contexts.** OSIV can keep an `EntityManager` open after the service transaction has finished.
3. **Place transactions in services.** Each service method clearly defines the scope of database access and DTO mapping.
4. **Do not casually return entities with lazy associations.** GraphQL may invoke nested resolvers after the root service's transaction ends.
5. **Prefer DTOs/projections.** Load and expose only the data GraphQL fields require.
6. **Choose explicit fetch plans.** Use `EntityGraph` or controlled fetch joins; avoid blanket `EAGER` mappings.
7. **Batch repeated relationships.** Use DataLoader/`@BatchMapping` for nested fields over lists.
8. **Never share an `EntityManager` across threads.** Spring's shared proxy does not make the underlying `EntityManager` thread-safe.
9. **Do not rely on OSIV to mask N+1.** Disabling OSIV in tests helps catch out-of-transaction lazy access.
10. **Align consistency with business requirements.** If a snapshot is needed, group queries into the same transaction with appropriate isolation.
11. **Measure actual SQL.** A correct response does not mean the query plan is efficient.
12. **Respect the web stack.** JPA is blocking; reactive WebFlux requires handling persistence according to the proper execution model.

The persistence context manages entity lifecycle and state, while nested GraphQL fields resolve data from the source object returned by parent fields. When the root service transaction ends, entities can become detached and lazy associations can no longer be loaded. Open EntityManager in View can keep the persistence context open for the request without keeping business transactions open, easily masking N+1 and late-firing queries. A stable design loads data via DTOs/projections or fetch plans inside service transactions, uses DataLoader/`@BatchMapping` for repeated nested fields, and never shares an `EntityManager` across threads. Disabling OSIV in integration tests catches hidden persistence context dependencies early.

## References

- [Spring Framework - JPA and EntityManager](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html)
- [Spring Boot - Open EntityManager in View](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Data JPA - Query Methods and EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA - Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring for GraphQL - Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - Request Execution and DataLoader](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Hibernate ORM - An Introduction to Hibernate 6](https://docs.hibernate.org/orm/6.6/introduction/html_single/)
