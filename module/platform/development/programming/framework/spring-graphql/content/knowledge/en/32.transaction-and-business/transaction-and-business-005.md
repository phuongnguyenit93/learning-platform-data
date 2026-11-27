# Lazy Loading in Resolvers

Lazy loading is an ORM mechanism that defers loading an association until the application actually accesses it. With JPA/Hibernate, a GraphQL resolver may receive an entity loaded from the database and then read a `LAZY` relationship such as `author`, `category`, or `reviews`. At that point, Hibernate may issue additional SQL statements to initialize the proxy or collection.

In GraphQL, clients choose which fields to read and can request nested associations across many nodes. Consequently, lazy loading inside resolvers easily causes N+1 queries: one query to fetch the list of parents, followed by each child resolver firing a separate query per parent. If the persistence context is already closed, the same access throws a `LazyInitializationException`. If the persistence context remains open due to Open Session in View, the error may be hidden, yet the query cost still exists.

Good design requires defining what data must be loaded for each GraphQL operation, placing transactions on the appropriate application services, and using fetch plans, projections, or DataLoader/`@BatchMapping` to batch queries. Lazy loading remains useful, but you should not let getter calls inside resolvers randomly dictate the number of SQL statements per request.

## 1. Lazy Loading in JPA/Hibernate

Entities often declare relationships with other entities:

~~~java
@Entity
public class Book {

    @Id
    private UUID id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private Author author;

    @OneToMany(mappedBy = "book", fetch = FetchType.LAZY)
    private List<Review> reviews = new ArrayList<>();

    // getters
}
~~~

When querying `Book`, Hibernate may load only columns from the `book` table. The `author` and `reviews` relationships are not necessarily loaded yet. Depending on the mapping and provider, Hibernate holds a proxy or persistent collection that knows how to fetch the data when needed.

~~~java
Book book = bookRepository.findById(bookId).orElseThrow();

// May trigger an additional query to load Author.
String authorName = book.getAuthor().getName();

// May trigger another query to load all Reviews.
int reviewCount = book.getReviews().size();
~~~

Lazy loading avoids loading unused associations, but it shifts the data-loading decision to access time. In a GraphQL request with many parent objects, accessing the same association on each parent can trigger many small queries.

## 2. FetchType LAZY and EAGER

JPA defines two primary fetch types:

| Fetch Type | General Behavior | Notes |
| --- | --- | --- |
| `LAZY` | Provider defers loading the association until needed | For some relationships, `LAZY` is a hint/request; the provider may still load eagerly |
| `EAGER` | Association must be loaded when the entity is fetched | Does not always mean a SQL `JOIN`; the provider may issue separate queries |

By default in JPA mappings, to-one relationships like `@ManyToOne` and `@OneToOne` are `EAGER`; to-many relationships like `@OneToMany` and `@ManyToMany` are `LAZY`. You can explicitly declare `LAZY` for to-one relationships to avoid unintended wide loads, though you should verify provider behavior and bytecode enhancement configuration if the application relies on it.

Do not switch all relationships to `EAGER` to fix `LazyInitializationException`. `EAGER` can load unneeded data, generate extra queries, or bloat the object graph. Likewise, do not mark everything `LAZY` and rely on Open Session in View so resolvers can access fields arbitrarily. Decide the fetch plan per use case.

## 3. How Can GraphQL Resolvers Trigger Lazy Loading?

Suppose the schema is:

~~~graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
~~~

The root resolver loads the list of Books:

~~~java
@QueryMapping
public List<Book> books() {
    return bookRepository.findAll();
}
~~~

The `author` field resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return book.getAuthor();
}
~~~

When the client only queries `id` and `title`, the `author` field is not selected, so the `author` resolver does not run. When the client queries `author.name`, GraphQL calls the resolver for each `Book`. Every `book.getAuthor()` call may trigger an association load if the association has not yet been initialized.

The GraphQL selection set determines which resolvers run. However, if each child resolver accesses a separate lazy association on each parent, database workload can grow with the number of parents on the page.

## 4. N+1 Queries Caused by Lazy Loading

Suppose the query is:

~~~graphql
query {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

With 50 books, the query flow might be:

1. One SQL query fetches 50 `Book` rows.
2. The `author` resolver runs for the first `Book` and loads its `Author`.
3. The `author` resolver runs for the second `Book` and loads its `Author`.
4. This repeats for the remaining `Book` items.

If the association is not cached or the Books have different authors, the total query count can approach 1 + 50. This is the N+1 query problem.

Illustrative SQL log:

~~~sql
SELECT id, title, author_id FROM book;
SELECT id, name FROM author WHERE id = ?;
SELECT id, name FROM author WHERE id = ?;
SELECT id, name FROM author WHERE id = ?;
-- repeated for many Books
~~~

If multiple Books reference the same Author and the persistence context already manages that Author, Hibernate can reuse the loaded entity. However, do not rely on data duplication to consider N+1 solved; query count can still scale with the number of distinct authors.

For collections like `reviews`, the risk is even higher: each `Book` can trigger a query loading its list of `Review` rows, sharply increasing row count and processing time.

## 5. LazyInitializationException

Hibernate requires an open persistence context to initialize an unloaded proxy or persistent collection. If an entity is returned outside the transaction and an association is accessed after the `EntityManager`/`Session` closes, Hibernate has nowhere to execute SQL.

~~~java
public Book findBook(UUID id) {
    return bookRepository.findById(id).orElseThrow();
}
~~~

If the repository method ends the transaction and the persistence context closes, a resolver calling:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return book.getAuthor();
}
~~~

may fail with:

~~~text
org.hibernate.LazyInitializationException:
could not initialize proxy - no Session
~~~

This error does not mean the related data does not exist. It means Hibernate needed to load the association but no suitable `Session` remained.

Do not fix this by invoking getters inside an arbitrary transaction and still returning the entity if nested resolvers will access other associations after the transaction ends. Load and map the needed data into DTOs within the transaction boundary, or let a dedicated service/batch loader fetch associations inside its own transaction.

## 6. Transaction Boundaries and Persistence Context

In a Spring application, the `EntityManager` is typically bound to a transaction or request depending on configuration. A transaction boundary should enclose a specific data use case:

~~~java
@Service
public class BookQueryService {

    private final BookRepository repository;

    public BookQueryService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public BookDetails findDetails(UUID id) {
        Book book = repository.findById(id).orElseThrow();
        return new BookDetails(
            book.getId(),
            book.getTitle(),
            book.getAuthor().getName());
    }
}
~~~

Here, the DTO is constructed while the transaction is still active. The resolver simply returns the prepared data:

~~~java
@QueryMapping
public BookDetails bookDetails(@Argument UUID id) {
    return bookQueryService.findDetails(id);
}
~~~

If the service returns an entity with uninitialized associations, the method's transaction may end before GraphQL executes nested resolvers. Subsequent lazy loading then depends on whether another persistence context happens to remain open.

Do not assume a transaction on a root resolver automatically spans the entire GraphQL process until all child fields finish. GraphQL may execute fields asynchronously, DataLoader can run in a separate dispatch phase, and publishers have different lifecycles. Place transactions explicitly on the service methods performing the required queries or batches.

`EntityManager` is not thread-safe. Do not pass an open persistence context across multiple threads or share a single mutable `EntityManager` among concurrently executing resolvers.

## 7. Open Session in View Is Not an N+1 Optimization

Open Session in View (OSIV) keeps the `EntityManager`/`Session` open across the HTTP request lifecycle so views or code running after the service layer can lazy-load associations.

In some Spring Boot servlet configurations, OSIV may be enabled by default. Resolvers can then access associations after the service method ends without immediately throwing `LazyInitializationException`.

However, OSIV does not solve N+1:

- Getters inside individual resolvers can still emit separate SQL statements.
- Query count can vary with the selection set and node count.
- Database access can leak into the presentation/resolver layer outside clear service boundaries.
- GraphQL async execution may use different threads; a thread-bound persistence context cannot be treated as safely shared.
- Long-running requests can hold the persistence context open longer than intended.

Consider disabling OSIV to detect out-of-transaction lazy association access early:

~~~properties
spring.jpa.open-in-view=false
~~~

This is an architectural choice that must be tested across the entire application. If OSIV is disabled, use cases must have explicit fetch plans or transactional services. Do not toggle OSIV solely to make one specific test pass without understanding its impact on other endpoints.

## 8. Solution 1: Fetch Join for Required Associations

If an operation almost always needs `author` alongside `Book`, load it with a fetch join:

~~~java
public interface BookRepository extends JpaRepository<Book, UUID> {

    @Query("""
        select b
        from Book b
        join fetch b.author
        where b.id = :id
        """)
    Optional<Book> findWithAuthorById(UUID id);
}
~~~

Service:

~~~java
@Transactional(readOnly = true)
public BookDetails findDetails(UUID id) {
    Book book = repository.findWithAuthorById(id).orElseThrow();
    return new BookDetails(
        book.getId(),
        book.getTitle(),
        book.getAuthor().getName());
}
~~~

Fetch join works well when the fetch graph is small, predictable, and required for the use case. It avoids extra queries for the joined association.

Do not fetch-join every relationship in every query. Joining multiple collections can multiply rows, increase data transfer from the database, and break pagination results. Exercise particular care with to-many collections combined with pagination.

## 9. Solution 2: @EntityGraph

Spring Data JPA supports `@EntityGraph` to specify associations to fetch for a repository method:

~~~java
public interface BookRepository extends JpaRepository<Book, UUID> {

    @EntityGraph(attributePaths = {"author"})
    Optional<Book> findById(UUID id);
}
~~~

An entity graph can be applied to a specific set of queries without writing fetch joins in JPQL. Entity graphs can be defined statically on the entity or dynamically on repository methods.

~~~java
@EntityGraph(attributePaths = {"author", "category"})
List<Book> findByStatus(BookStatus status);
~~~

An entity graph is only a fetch plan. The provider still decides how to execute SQL and may use joins or extra queries. Inspect the actual SQL and query count; do not conclude N+1 is gone simply because `@EntityGraph` was added.

## 10. Solution 3: DTO Projections

If a GraphQL operation only needs a handful of fields, DTO projections are often clearer and cheaper than returning entities:

~~~java
public record BookSummary(
        UUID id,
        String title,
        String authorName) {
}
~~~

JPQL projection:

~~~java
@Query("""
    select new com.example.graphql.BookSummary(
        b.id, b.title, a.name)
    from Book b
    left join b.author a
    where b.status = :status
    order by b.createdAt desc, b.id desc
    """)
List<BookSummary> findSummaries(BookStatus status);
~~~

The DTO is constructed from a query with an explicit join. The resolver no longer touches association proxies:

~~~java
@QueryMapping
public List<BookSummary> books(@Argument BookStatus status) {
    return bookQueryService.findSummaries(status);
}
~~~

Projections suit read models with stable structures. If different GraphQL selection sets request different fields, create tailored projections/use cases instead of loading the entire entity graph for every request.

## 11. Solution 4: DataLoader for Nested Associations

GraphQL lets clients select the `author` field inside each `Book`. DataLoader gathers author IDs from multiple parent objects into a single batch:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<UUID, Author> authorLoader) {

    return authorLoader.load(book.getAuthorId());
}
~~~

With Spring for GraphQL, register a batch loader via `BatchLoaderRegistry`:

~~~java
@Component
public class AuthorBatchLoader {

    public AuthorBatchLoader(
            BatchLoaderRegistry registry,
            AuthorQueryService authorQueryService) {

        registry.forTypePair(UUID.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                Mono.fromCallable(() ->
                    authorQueryService.findByIds(authorIds)));
    }
}
~~~

The service loads all authors in one transaction:

~~~java
@Service
public class AuthorQueryService {

    private final AuthorRepository repository;

    public AuthorQueryService(AuthorRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Map<UUID, Author> findByIds(Set<UUID> ids) {
        return repository.findAllById(ids).stream()
            .collect(Collectors.toMap(
                Author::getId,
                Function.identity()));
    }
}
~~~

This example illustrates a mapped batch loader returning a key-indexed `Map`. When using blocking JPA on WebFlux, offload the query to a scheduler dedicated to blocking I/O and ensure the transaction opens on the thread executing the query. In MVC/imperative applications, a synchronous batch method matching the application's execution model can be used.

DataLoader caches per GraphQL execution/request. Multiple resolvers calling `load` with the same key can be batched and share the result. Never share a DataLoader instance across requests or principals; results depending on tenant or authorization must be scoped appropriately.

## 12. Solution 5: @BatchMapping

When a nested field maps directly from parent objects to related objects, `@BatchMapping` makes writing batch resolvers shorter:

~~~java
@Controller
public class BookController {

    private final AuthorQueryService authorService;

    public BookController(AuthorQueryService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        Set<UUID> authorIds = books.stream()
            .map(Book::getAuthorId)
            .filter(Objects::nonNull)
            .collect(Collectors.toSet());

        Map<UUID, Author> authors = authorService.findByIds(authorIds);

        return books.stream().collect(Collectors.toMap(
            Function.identity(),
            book -> authors.get(book.getAuthorId())));
    }
}
~~~

`@BatchMapping` automatically registers a DataLoader for the corresponding field. It works well when the batch function takes a list of source objects and returns a `Map` from source to value. When complex keys, custom cache keys, or sharing one loader across multiple consumers are needed, explicit DataLoader registration can be more flexible.

If blocking JPA runs in WebFlux, do not make repository calls directly on the event loop. Use reactive persistence or offload the entire batch operation to an appropriate scheduler; the transaction must start on that execution thread.

## 13. Hibernate Batch Fetching

Hibernate supports batch fetching to group initialization of multiple proxies/collections into fewer queries:

~~~java
@BatchSize(size = 32)
@ManyToOne(fetch = FetchType.LAZY)
private Author author;
~~~

Or via default configuration:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

When several proxies of the same type are accessed within a persistence context, Hibernate can load multiple associations in one query using `IN`. This is an ORM-level optimization that reduces query count compared to plain N+1.

Batch fetching does not mean a single query for all data. Batch count still depends on the number of associations, batch size, key count, and the persistence context. Nor does it replace designing a clear fetch plan. Measure query count and latency before and after configuring it.

## 14. Beware of Fetch Join with Collection Pagination

Fetch-joining to-one associations is usually easier to control than fetch-joining to-many associations. If you query `Book` and join-fetch `reviews`, a `Book` with multiple `Review` rows produces multiple SQL rows for the same `Book`.

When combining `LIMIT`/`OFFSET` or pagination with a collection fetch join, the database limits post-join rows rather than necessarily limiting the number of `Book` entities. Hibernate may have to perform pagination in memory or emit warnings; the result can be very resource-intensive.

Do not use a single query fetch-joining multiple collections to load the entire GraphQL response. A safer approach:

1. Query the page of parent IDs with a stable sort.
2. Query the required parent and to-one data for those IDs.
3. Use DataLoader or `@BatchMapping` to load to-many associations in batches.
4. Preserve the original first-page ID order when assembling results.

For collections requiring their own pagination, design a connection for that collection and query by parent ID and cursor. Do not load all reviews and slice the list in Java.

## 15. Choosing a Solution by Use Case

| Situation | Appropriate Solution |
| --- | --- |
| A query always needs a to-one association | Fetch join or `@EntityGraph` |
| Read API returns only a few fixed fields | DTO projection |
| Multiple Books request `author` | DataLoader or `@BatchMapping` |
| Many proxies of the same type accessed in one persistence context | Hibernate batch fetching |
| Large to-many collection | Batch loading or dedicated connection for the collection |
| Query with pagination and collection associations | Page parents first, batch associations afterward |
| Many different GraphQL selection sets | Use-case fetch plans, DTOs/read models, or DataLoader |

Multiple approaches can be combined. For instance, the root query can use a projection for Book summaries, DataLoader can fetch Authors for selected fields, and a `reviews` field can use a dedicated connection. No single fetch strategy is optimal for every GraphQL operation.

## 16. Testing Lazy Loading and N+1

Tests that only verify the JSON response are insufficient to prove query efficiency. You need to inspect SQL query counts or query behavior.

With Hibernate, statistics can be enabled in tests:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

After executing the GraphQL operation, read Hibernate `Statistics` and check the prepared statement/query count against the fixture. Reset statistics before each test and avoid running tests in parallel against the same `SessionFactory` when assertions depend on global counters.

Conceptual test example:

~~~java
Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

graphQlTester.document("""
        query {
            books {
                id
                author {
                    name
                }
            }
        }
        """)
    .execute()
    .errors()
    .verify();

long queryCount = statistics.getPrepareStatementCount();
assertThat(queryCount).isLessThanOrEqualTo(3);
~~~

Exact counts depend on the schema, test setup, transactions, caches, and auxiliary queries. Do not copy the threshold `3` mechanically; establish a baseline from a small test fixture, then verify the query count does not grow linearly with the number of Books.

A useful comparison:

- Run the query with 2 Books and record the SQL count.
- Run the same query with 20 Books.
- If the query count increases roughly 18x, there is an N+1 issue.
- If the query count stays nearly constant or grows only by batch count, batch loading is working as expected.

For repository tests, use database integration tests to verify fetch joins, entity graphs, keyset queries, and indexes. For GraphQL tests, use `GraphQlTester` to confirm resolvers only load associations when the corresponding fields are selected.

## 17. Observing SQL and Performance

Tools that can help:

- Hibernate SQL logging in development environments.
- Hibernate `Statistics` to count prepared statements, entity fetches, and collection fetches.
- DataSource proxies or JDBC instrumentation to observe query count/latency.
- Micrometer Observation and tracing to correlate GraphQL fields with processing duration.
- Database slow query logs and `EXPLAIN ANALYZE` to inspect query plans.

Do not enable verbose SQL logging in production indiscriminately, as it can expose bind values or increase I/O. Use controlled logging and mask sensitive data.

GraphQL field observation shows which fields take time, but does not by itself prove an N+1 issue. Combine traces, SQL metrics, and parent object counts. A slow field can be caused by a large table scan, network dependency, or serialization—not only lazy loading.

## 18. Controlling Selection Sets and Data Size

GraphQL lets clients select arbitrary fields within schema limits. A query can nest multiple associations deeply:

~~~graphql
query {
    books {
        author {
            books {
                author {
                    books {
                        id
                    }
                }
            }
        }
    }
}
~~~

Even when DataLoader reduces query count, a deep or wide selection set can still load massive amounts of data. Consider depth limits, query complexity/cost limits, page size caps, and field-level authorization.

Do not automatically fetch the entire entity graph just because one field is selected. Scope associations to the use case, paginate large collections, and select only needed columns.

## 19. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `LazyInitializationException` in nested resolver | Persistence context closed before the association was accessed | Use service transactions, fetch plans, or batch loaders |
| Response is correct, yet many queries execute | OSIV allows lazy loading per parent | Count SQL queries and use DataLoader/`@BatchMapping` |
| Switching all relationships to `EAGER` | Over-fetches data and can still issue extra queries | Fetch according to use case |
| Fetch-joining collection breaks or slows pagination | Join multiplies rows and database limit applies to joined rows | Page parents first, batch collections afterward |
| Root resolver transaction is insufficient | Nested resolver/async loader runs past the boundary | Place the transaction in the service executing the batch query |
| Entities returned to GraphQL carry proxies | Presentation layer depends on persistence models | Use DTOs/projections |
| Hibernate batch size does not reduce queries enough | Batch fetching only groups proxies within context by batch size | Measure SQL, choose fetch plans or DataLoader |
| `@BatchMapping` still queries item by item | Batch method calls repository inside a loop | Collect keys and query once |
| Using blocking JPA on the event loop | Thread gets blocked and transaction context does not fit | Use an appropriate scheduler or reactive persistence |
| Deep GraphQL query loads too much data | Missing depth/cost/page-size limits | Enforce query complexity limits and pagination |

## 20. Design Principles for Lazy Loading in Resolvers

Lazy loading avoids loading unused associations, yet GraphQL resolvers can trigger it repeatedly per parent object. This creates N+1 queries or `LazyInitializationException` depending on whether the persistence context remains open. Open Session in View can mask closed-session errors, but it is not a solution for query volume.

Define a fetch plan per operation: use fetch joins or `@EntityGraph` for small, always-needed associations; use DTO projections for stable read models; use DataLoader or `@BatchMapping` for nested associations that need batching across multiple parents; consider Hibernate batch fetching as a supplemental optimization. Avoid fetch-joining large collections with pagination, and do not pass entities with uninitialized proxies outside a transaction if subsequent resolvers will access them.

Place read-only transactions on the application services executing queries or batch loads, never share an `EntityManager` across threads, and do not rely on a single root resolver transaction to cover all GraphQL fields. Test with `GraphQlTester` alongside Hibernate `Statistics`/SQL instrumentation to confirm query counts do not scale linearly with parent counts. Lazy loading is only performance-safe when the timing and scope of data loading are controlled.
