# Transactions in Queries

GraphQL Queries are typically used to read data, yet a single query can invoke multiple resolvers, access multiple repositories, and fetch data from different services. Without clearly defined transaction boundaries, an application is prone to lazy loading errors, inconsistent data reads, transactions held open for too long, or inadvertently executing many separate queries.

In Spring for GraphQL, the GraphQL engine orchestrates field execution. Spring transaction management manages transactions on methods where `@Transactional` is applied. These two mechanisms work together, but a GraphQL operation does not automatically become a single transaction.

For read queries, the common approach is to place a read-only transaction on the service method that executes the query. The resolver calls the service and returns a DTO or projection with all required data loaded. If a nested field requires a separate query, its corresponding service can open its own read-only transaction. With DataLoader, the batch service executes a single query for multiple keys within one transaction instead of opening a transaction per element.

## Why Do GraphQL Queries Need Transactions?

A GraphQL request can ask for data from multiple branches:

~~~graphql
query BookDetails($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
    reviews {
      rating
    }
  }
}
~~~

To build the response, the application might:

1. Read Book by ID.
2. Read Author by authorId.
3. Read the list of Reviews by bookId.
4. Map entities into the data returned to GraphQL.

Transactions help group database access operations within a defined boundary. They can enforce database transaction rules such as commit/rollback, isolation, and persistence context management.

Common problems when transactions are not clearly designed:

- An entity is returned from a service and then a field resolver accesses a lazy association, leading to a `LazyInitializationException`.
- Nested resolvers may open separate transactions and read data at different points in time.
- A resolver calls a repository multiple times, causing transactions to be opened and closed repeatedly.
- A GraphQL Query has multiple fields executing in parallel, while the code assumes the fields share a single transaction or `EntityManager`.
- A method returns a `CompletableFuture` or `Publisher`, yet the imperative transaction has already ended before the asynchronous processing finishes.

Transactions do not replace batching, pagination, or authorization. They define the consistency scope of database operations; N+1 and access-control issues still need to be addressed separately.

## GraphQL Operations Do Not Automatically Create Transactions

Spring for GraphQL does not automatically open a transaction wrapping the entire GraphQL operation. A transaction only starts when the application calls a method with transaction advice—such as a service method annotated with `@Transactional`—or when the code explicitly uses `TransactionTemplate`/`TransactionalOperator`.

For example, a query with two root fields:

~~~graphql
query Dashboard {
  currentUser {
    id
    name
  }
  recentOrders {
    id
    total
  }
}
~~~

GraphQL Query allows independent root fields to execute in parallel. If `currentUser` and `recentOrders` call two service methods annotated with `@Transactional(readOnly = true)`, each call may run in its own transaction. There is no guarantee that both read the same database snapshot.

Mutations have sequential execution rules for top-level mutation fields, but that also does not automatically create a database transaction spanning the entire operation. Transactions must still be designed at the application layer.

Therefore, define transaction boundaries around business tasks and service calls rather than assuming they match the GraphQL document boundary.

## Using @Transactional(readOnly = true) for Read Queries

For services that only read data, declare `readOnly = true`:

~~~java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public BookView findBook(String id) {
        BookEntity book = bookRepository.findById(id)
                .orElseThrow(() ->
                        new BookNotFoundException(id));

        return new BookView(
                book.getId(),
                book.getTitle());
    }
}
~~~

`readOnly = true` expresses the method's intent and gives the transaction manager/persistence provider an opportunity to optimize read operations. With Hibernate, Spring can apply an appropriate flush mode to reduce dirty checking in certain configurations.

This is an optimization hint and transaction metadata, not a security mechanism. Do not rely on `readOnly = true` to prevent all write statements at the database level. Exact behavior depends on the transaction manager, ORM, driver, and database. If the business logic requires guaranteeing no writes, design appropriate database privileges and APIs.

## Placing Transactions in Services Instead of Controllers

Resolvers should focus on mapping GraphQL arguments and invoking use cases. Services are responsible for transactions and data access:

~~~java
@Controller
public class BookController {

    private final BookQueryService bookQueryService;

    public BookController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public BookView book(@Argument String id) {
        return bookQueryService.findBook(id);
    }
}
~~~

Controllers do not need to open transactions themselves when the service already defines the boundary. This allows the same service to be reused from GraphQL, REST, scheduled jobs, or message handlers without transport coupling.

If a transaction spans multiple repository calls to produce a single business result, place `@Transactional` on the service method that orchestrates those operations:

~~~java
@Service
public class DashboardQueryService {

    private final UserRepository userRepository;
    private final OrderRepository orderRepository;

    public DashboardQueryService(
            UserRepository userRepository,
            OrderRepository orderRepository) {
        this.userRepository = userRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public DashboardView loadDashboard(String userId) {
        UserSummary user = userRepository.findSummaryById(userId)
                .orElseThrow(() -> new UserNotFoundException(userId));

        List<OrderSummary> orders =
                orderRepository.findRecentSummaries(userId);

        return new DashboardView(user, orders);
    }
}
~~~

The two repository queries above run within the same transaction managed by the service method. This is a clear boundary because together they build a `DashboardView`.

## Default Transaction Propagation

Spring transaction management defaults to `REQUIRED` propagation for `@Transactional`. If no transaction exists, the method opens a new one. If a suitable transaction already exists, the method participates in the current transaction.

| Propagation | Behavior | Common Use Cases |
| --- | --- | --- |
| REQUIRED | Joins the current transaction or creates a new one | Default choice for query services |
| REQUIRES_NEW | Suspends the current transaction and opens a new one | Only when an independent boundary is truly needed |
| SUPPORTS | Joins a transaction if one exists; otherwise runs non-transactionally | Read logic that can run inside or outside a transaction |
| MANDATORY | Requires the caller to already have an active transaction | Internal components requiring a caller transaction |
| NOT_SUPPORTED | Suspends the current transaction and runs non-transactionally | Work that should not hold a transaction |
| NEVER | Throws an error if a transaction is currently active | Rarely used in query flows |
| NESTED | Uses nested transactions/savepoints if supported by the transaction manager | When partial rollback control is needed |

For typical queries, `REQUIRED` is usually sufficient. Avoid using `REQUIRES_NEW` for every resolver because it can create unnecessary transactions, prevent a service workflow from sharing a single transaction, and increase database load.

Transaction annotations are typically applied through a Spring proxy. If a method in the same class directly calls another method annotated with `@Transactional`, that internal call bypasses the proxy and does not create a new transaction boundary. Place transactions on public service methods invoked from other beans, or use explicit transaction management when needed.

## Nested Resolvers and Transaction Boundaries

Suppose a root resolver returns a `BookView` (or entity), and then GraphQL invokes the `author` field:

~~~java
@QueryMapping
public BookEntity book(@Argument String id) {
    return bookQueryService.findEntity(id);
}

@SchemaMapping(typeName = "Book", field = "author")
public AuthorView author(BookEntity book) {
    return authorQueryService.findById(book.getAuthorId());
}
~~~

If `findEntity()` is a `@Transactional(readOnly = true)` method returning an entity, the transaction usually ends when the method returns. The `author` field may be invoked afterward in a separate resolver invocation. Do not assume the root resolver's transaction stays open while GraphQL resolves child fields.

There are two common design approaches:

**Approach 1: Load all required data in a single service method and return a DTO.**

~~~java
@Transactional(readOnly = true)
public BookDetailsView findBookDetails(String id) {
    BookEntity book = bookRepository.findDetailsById(id)
            .orElseThrow(() -> new BookNotFoundException(id));

    return new BookDetailsView(
            book.getId(),
            book.getTitle(),
            new AuthorView(
                    book.getAuthor().getId(),
                    book.getAuthor().getName()));
}
~~~

GraphQL receives a DTO that already contains the required data. Field mapping can rely on property access without needing to open a transaction to traverse lazy associations.

**Approach 2: Nested resolver calls a separate service.**

~~~java
@Service
public class AuthorQueryService {

    private final AuthorRepository authorRepository;

    public AuthorQueryService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    @Transactional(readOnly = true)
    public AuthorView findById(String id) {
        return authorRepository.findViewById(id)
                .orElseThrow(() -> new AuthorNotFoundException(id));
    }
}
~~~

The `author` resolver calls this service when data is needed. The service opens its own read-only transaction for its query. For large lists of Books, do not call the service once per Book; use DataLoader or `@BatchMapping` to combine IDs into a single batch.

## Avoiding Lazy Loading After the Transaction Ends

JPA often uses lazy loading to defer querying associations until code accesses them. If a resolver returns an entity outside the transaction and GraphQL later accesses an association, the persistence context may already be closed:

~~~java
@Transactional(readOnly = true)
public BookEntity findById(String id) {
    return bookRepository.findById(id)
            .orElseThrow();
}
~~~

If GraphQL subsequently reads `book.getAuthor().getName()`, a `LazyInitializationException` can occur because the entity is no longer attached to an `EntityManager`.

Do not rely on Open EntityManager in View to keep the persistence context open throughout GraphQL response rendering. This mechanism can trigger late database queries during field serialization/resolution, hide N+1 issues, and keep the persistence context open for too long. Nor does it turn the entire GraphQL execution into a single transaction.

Better alternatives:

- Use DTOs or projections to return only the required data.
- Use JPQL fetch joins or `EntityGraph` for associations that must be loaded.
- Use batch resolvers/DataLoader for one-to-many or many-to-one relationships.
- Keep both querying and entity-to-DTO mapping inside the transaction.
- Do not expose JPA entities as a public contract if GraphQL fields could still access lazy associations.

`EntityGraph` example:

~~~java
public interface BookRepository extends JpaRepository<BookEntity, String> {

    @EntityGraph(attributePaths = "author")
    Optional<BookEntity> findWithAuthorById(String id);
}
~~~

The service loads the association and converts it to a DTO before the transaction ends:

~~~java
@Transactional(readOnly = true)
public BookDetailsView findBookDetails(String id) {
    BookEntity book = bookRepository.findWithAuthorById(id)
            .orElseThrow(() -> new BookNotFoundException(id));

    return new BookDetailsView(
            book.getId(),
            book.getTitle(),
            book.getAuthor().getName());
}
~~~

`EntityGraph` only loads the specified association. If the response also needs `reviews`, decide how to load `reviews` separately rather than arbitrarily adding multiple collections to a single fetch join, which causes row multiplication or conflicts with pagination.

## Transactions and DataLoader

DataLoader groups multiple data requests into a single batch. The transaction should be opened in the batch service so that the entire batch query runs within a single boundary.

Example:

~~~java
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
@Controller
public class BookReviewController {

    private final ReviewQueryService reviewQueryService;

    public BookReviewController(ReviewQueryService reviewQueryService) {
        this.reviewQueryService = reviewQueryService;
    }

    @BatchMapping(typeName = "Book", field = "reviews")
    public Map<BookView, List<ReviewView>> reviews(List<BookView> books) {
        Set<String> bookIds = books.stream()
                .map(BookView::id)
                .collect(Collectors.toSet());

        Map<String, List<ReviewView>> byBook =
                reviewQueryService.findByBookIds(bookIds);

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

The transaction lives in `findByBookIds()`. A single batch can query multiple book IDs in one statement, map the results, and return DTOs. Do not place `@Transactional` on a method that takes one Book at a time and calls the repository separately for each element; that keeps the N+1 problem and creates repeated transactions.

If a custom batch loader uses `BatchLoaderRegistry`, let the batch service own the transaction. DataLoader's per-GraphQL-request cache is not a transaction and does not provide database isolation.

## Queries with Multiple Root Fields and Data Consistency

A query can have multiple independent root fields:

~~~graphql
query AccountOverview($accountId: ID!) {
  account(id: $accountId) {
    id
    balance
  }
  recentTransactions(accountId: $accountId) {
    id
    amount
  }
}
~~~

If two resolvers call two different service methods, each method may run in a separate transaction. One transaction might read `balance` before a new transaction is written, while the other reads `recentTransactions` after that transaction has committed.

This is not necessarily a bug. It depends on the screen's consistency requirements and the database isolation policy. If the response requires a consistent snapshot, design a single service use case that reads the related data within the same transaction and returns an aggregated DTO:

~~~java
@Transactional(
        readOnly = true,
        isolation = Isolation.REPEATABLE_READ)
public AccountOverviewView loadOverview(String accountId) {
    AccountView account = accountRepository.findViewById(accountId)
            .orElseThrow();

    List<TransactionView> transactions =
            transactionRepository.findRecentViews(accountId);

    return new AccountOverviewView(account, transactions);
}
~~~

`REPEATABLE_READ` isolation has different meanings depending on the database and can affect concurrency. Some databases use snapshot isolation; others have their own semantics. Isolation is only applied when a new transaction is created; if a method joins an existing transaction, the `isolation` attribute declared on the child method typically does not change the isolation of the current transaction.

Do not raise isolation to `SERIALIZABLE` for every query. Choose the level required by business invariants, transaction duration, and the database's contention tolerance.

## readOnly Does Not Mean Isolation

These two attributes solve two different goals:

| Attribute | Purpose |
| --- | --- |
| readOnly = true | Signals a read-only transaction and gives the provider optimization opportunities |
| isolation | Defines the isolation level between concurrent transactions |
| timeout | Limits transaction duration as supported by the transaction manager |
| propagation | Specifies how the method joins or creates a transaction |

A read-only transaction can still read data modified by another transaction, depending on the isolation level. Conversely, a `REPEATABLE_READ` transaction does not automatically become read-only.

If a query only needs to read data, using `readOnly = true` is appropriate. If a consistent snapshot is needed, evaluate isolation separately and confirm the database supports the desired semantics.

## Transactions with CompletableFuture and Asynchronous Resolvers

Spring imperative transactions are typically bound to the current thread. When the method returns, the transaction interceptor completes the transaction according to the method lifecycle. Do not assume the transaction continues to exist in a callback running later on another thread.

A misleading example:

~~~java
@Transactional(readOnly = true)
public CompletableFuture<BookView> findBookAsync(String id) {
    return CompletableFuture.supplyAsync(() ->
            bookRepository.findById(id)
                    .map(BookView::from)
                    .orElseThrow());
}
~~~

In this example, the repository call inside the supplier may execute after the method has returned the `CompletableFuture` and the imperative transaction has ended. A `ForkJoinPool` thread also does not automatically inherit the caller's transaction or `EntityManager`.

With JPA, the straightforward approach is to perform database work synchronously inside the transaction and return the materialized result:

~~~java
@Transactional(readOnly = true)
public BookView findBook(String id) {
    return bookRepository.findById(id)
            .map(BookView::from)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

If asynchronous execution is needed, create the transaction inside the worker/service method that actually performs the database work, or use a reactive persistence stack with a reactive transaction manager. Do not pass incompletely loaded JPA entities across threads.

## Reactive Transactions with WebFlux and R2DBC

With WebFlux and R2DBC, transactions are managed via the reactive context rather than relying solely on `ThreadLocal`. Spring supports `ReactiveTransactionManager` and `@Transactional` for methods returning a `Publisher` such as `Mono` or `Flux`.

Service example:

~~~java
@Service
public class ProductQueryService {

    private final ProductRepository productRepository;

    public ProductQueryService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional(readOnly = true)
    public Mono<ProductView> findById(String id) {
        return productRepository.findById(id)
                .map(ProductView::from);
    }
}
~~~

Controller:

~~~java
@Controller
public class ProductController {

    private final ProductQueryService productQueryService;

    public ProductController(ProductQueryService productQueryService) {
        this.productQueryService = productQueryService;
    }

    @QueryMapping
    public Mono<ProductView> product(@Argument String id) {
        return productQueryService.findById(id);
    }
}
~~~

A reactive transaction is maintained within the method's reactive pipeline. The `Publisher` must be subscribed to by the framework; do not call `subscribe()` or `block()` directly inside the service. Database operations must be composed within the same pipeline so they participate in the transaction.

For an annotation on a method returning `Mono`/`Flux` to create a reactive transaction, the application must have a suitable `ReactiveTransactionManager`, such as `R2dbcTransactionManager`. If only a JPA/JDBC `PlatformTransactionManager` is present, do not assume that transaction will manage R2DBC operations.

For more complex transactions, `TransactionalOperator` can be used:

~~~java
public Mono<ProductView> findProduct(String id) {
    return productRepository.findById(id)
            .map(ProductView::from)
            .as(transactionalOperator::transactional);
}
~~~

`TransactionalOperator` must be created from a `ReactiveTransactionManager`. This is a useful option when you need to wrap a specific reactive sequence rather than annotating the whole method.

Do not use a blocking JPA/JDBC repository inside a reactive transaction and expect it to automatically join the R2DBC transaction. They are two different transaction managers and two different resources. If the application uses JPA in Spring MVC, use an imperative transaction manager; if it uses R2DBC in WebFlux, use the corresponding reactive transaction manager.

## Do Not Block or Manually Subscribe in Reactive Transactions

The following patterns defeat the purpose of reactive transactions:

~~~java
@Transactional(readOnly = true)
public Mono<ProductView> findById(String id) {
    Product product = productRepository.findById(id).block();
    return Mono.just(ProductView.from(product));
}
~~~

~~~java
@Transactional(readOnly = true)
public Mono<Void> refreshCache(String id) {
    productRepository.findById(id)
            .doOnNext(this::updateCache)
            .subscribe();
    return Mono.empty();
}
~~~

`block()` blocks the thread and can execute outside the intended reactive flow. `subscribe()` creates a separate subscription detached from the publisher managed by the Spring transaction interceptor; the method can return and the transaction can close before the database work completes.

Return the publisher to the framework and compose steps using `map`, `flatMap`, `then`, or other appropriate operators. When multiple queries need to run within one transaction, compose them into the same sequence.

## Transactions and GraphQL Errors

GraphQL can return partial data alongside errors. One failing resolver does not necessarily cause the entire GraphQL operation to fail.

Example:

~~~json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Unable to load author",
      "path": ["book", "author"]
    }
  ]
}
~~~

If the `author` resolver calls a service method with its own transaction and that method throws an exception, its transaction is handled according to Spring's rollback rules. The GraphQL error handler then converts the exception into a GraphQL error. Other fields can continue returning data if GraphQL nullability permits.

With read-only queries, a rollback typically has no data changes to undo. However, if a query method performs unintended side effects, do not infer from GraphQL returning partial data that the transaction rolled back the entire operation.

Spring transactions roll back by default on `RuntimeException` and `Error`; checked exceptions do not automatically trigger rollback unless `rollbackFor` is configured. When custom rules are needed, explicitly declare `rollbackFor`/`noRollbackFor` on the service method. Do not put rollback logic in a GraphQL error handler because the resolver's transaction may have already ended by then.

## Transactions and Read Data Security

`readOnly = true` does not mean the user is allowed to read all data. Authorization must be checked separately in the service or query repository.

Example of a tenant-scoped query:

~~~java
@Transactional(readOnly = true)
public List<OrderView> findOrders(
        String tenantId,
        String subjectId) {

    return orderRepository.findVisibleOrders(tenantId, subjectId)
            .stream()
            .map(OrderView::from)
            .toList();
}
~~~

The tenant ID and subject ID must come from the authenticated identity or a trusted context. Do not use a client-supplied `tenantId` as proof of access rights. Transactions protect the consistency of database operations, while authorization determines which records may be read.

If the repository uses database row-level security, the tenant context must be set inside the proper transaction and cleaned up when the transaction ends. With connection pools, never let a tenant session variable leak into the next request.

## Testing Transactions in GraphQL Queries

Test both the GraphQL result and the transaction behavior in the service:

| Scenario | What to Verify |
| --- | --- |
| Successful query | Service returns correct data inside a read-only transaction |
| Entity not found | Service throws an exception and GraphQL error has the right path |
| Nested resolver | No lazy association access after the transaction closes |
| Batch mapping | One batch query handles multiple parent IDs within a transaction |
| Multiple root fields | Parallel fields are not assumed to share a transaction |
| CompletableFuture | Database work does not run after the imperative transaction ends |
| R2DBC Publisher | Operations in the same reactive pipeline use the proper reactive transaction |
| Authorization | Query only reads data belonging to the allowed tenant/subject |
| Isolation | Consistency level meets business requirements under concurrent updates |

Service test example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class BookQueryServiceTests {

    @Autowired
    private BookRepository bookRepository;

    @Autowired
    private BookQueryService bookQueryService;

    @Test
    void shouldReturnBookView() {
        BookEntity saved = bookRepository.save(
                new BookEntity("book-42", "Spring GraphQL"));

        BookView result = bookQueryService.findBook(saved.getId());

        assertThat(result.id()).isEqualTo("book-42");
        assertThat(result.title()).isEqualTo("Spring GraphQL");
    }
}
~~~

The test above illustrates an integration test calling a Spring-managed service bean so that the call goes through the transaction proxy. To verify the read-only flag or whether a transaction is active, you can use `TransactionSynchronizationManager` inside a service test hook or instrument the transaction manager in tests. Do not instantiate the service directly with `new`, because `@Transactional` will not be applied via a Spring proxy.

For GraphQL integration tests, use `GraphQlTester` or `HttpGraphQlTester` to send queries and verify responses. If you need to verify transaction boundaries, spy/mock the service or instrument the transaction manager in tests to confirm each service invocation runs within the expected boundary. Avoid checking only HTTP 200 since the response can still contain GraphQL errors.

## Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `LazyInitializationException` in nested field | Entity is returned after the service transaction ends | Return a DTO/projection or load associations inside the service |
| Child resolver does not join parent resolver's transaction | Each resolver is a separate invocation; the parent method's transaction has ended | Place the transaction on the child field's query service or gather data in one use case |
| N+1 despite having `@Transactional` | A transaction does not combine SQL statements into one query | Use DataLoader, `@BatchMapping`, projections, or a fetch plan |
| `CompletableFuture` has no transaction | The imperative transaction ends when the method returns the future | Execute DB work inside a transactional worker method or use an appropriate reactive stack |
| R2DBC transaction does not cover the query | Publisher was blocked/subscribed outside the pipeline | Return and compose `Mono`/`Flux`, and use `ReactiveTransactionManager` |
| Transaction does not roll back on checked exception | Default rules only roll back on `RuntimeException`/`Error` | Configure `rollbackFor` for checked exceptions when needed |
| Query returns data from different snapshots | Multiple root resolvers use separate transactions or low isolation | Combine data into a single service transaction or choose appropriate isolation |
| Read-only transaction can still write | `readOnly` is a hint, not an absolute write blocker | Use database privileges and clearly separate query/command APIs |
| Long-running transaction on large GraphQL responses | Service holds the transaction while doing extra work or long streaming | Materialize DTOs, scope the transaction to DB work, and avoid holding it across network calls |
| Tenant data leaks across requests | Tenant context/session state is not scoped to the transaction | Set and clear tenant context within the transaction, and test with connection pooling |

## Principles for Designing Transactions in GraphQL Queries

When implementing queries, apply the following principles:

1. **Do not assume a GraphQL operation shares one transaction.** Transactions occur on methods managed by the Spring transaction manager.
2. **Place read-only transactions in services.** Services clearly define the group of queries that need a shared boundary.
3. **Return DTOs or projections.** Prevent GraphQL field resolvers from accidentally accessing lazy associations after the transaction ends.
4. **Handle nested fields intentionally.** Preload required data or use a dedicated service for child resolvers.
5. **Batch before optimizing transactions.** `@BatchMapping`/DataLoader eliminates N+1; transactions only manage the batch query boundary.
6. **Respect GraphQL Query concurrency.** Root fields can execute in parallel and use separate transactions.
7. **Distinguish imperative from reactive.** JPA/JDBC uses thread-bound transactions; R2DBC uses reactive transaction contexts.
8. **Do not block or manually subscribe.** Keep all reactive operations within the same publisher pipeline.
9. **Choose isolation based on business invariants.** `readOnly` does not replace isolation and does not guarantee a consistent snapshot.
10. **Separate authorization from transactions.** `readOnly` does not grant permission to read data.
11. **Keep transactions short.** Do not hold a database transaction during slow network calls or infinite data streams.
12. **Test actual boundaries.** Verify service beans, nested resolvers, batch loaders, and reactive flows in an appropriate environment.

Transactions in GraphQL Queries define the boundary for managing database access across services and resolvers, not an automatic transaction covering the entire GraphQL document. With JPA/JDBC, use `@Transactional(readOnly = true)` on service methods and convert entities to DTOs before returning to GraphQL. For nested fields, avoid lazy loading after the transaction closes; for lists, use DataLoader or `@BatchMapping` to batch queries. In WebFlux/R2DBC, use a reactive transaction manager and keep database work inside the same `Mono`/`Flux` pipeline. Finally, select isolation based on consistency requirements, separate authorization from the read-only hint, and keep transactions short so GraphQL Queries remain stable under concurrent load.

## References

- [Spring Framework - Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework - Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework - Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring for GraphQL - Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - Request Execution and DataLoader](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Data JPA - Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
