# Reactive Queries

## Objectives

After this lesson, you will be able to:

- Explain how Spring for GraphQL supports reactive return types in Queries.
- Distinguish between `Mono` and `Flux` when mapping to a single or list GraphQL field.
- Write Query controllers that compose reactive services without blocking threads.
- Combine multiple data sources using Reactor operators.
- Understand why returning `Flux` in a Query is not equivalent to Subscription streaming.
- Handle empty `Mono`, reactive errors, and schema nullability.
- Cap data volume, avoid uncontrolled fan-out, and test reactive Queries with `GraphQlTester`.

## 1. What Is a Reactive Query?

In GraphQL, a Query is an operation used to read data. With Spring for GraphQL, a method annotated with `@QueryMapping` can return synchronous objects or reactive types such as `Mono` and `Flux`.

Reactive programming models results as an asynchronous data stream. Instead of forcing a thread to wait for a database or another service to respond, the controller returns a publisher so the framework coordinates execution.

Two common Reactor types:

| Type | Result Count | Use Case |
|---|---:|---|
| Mono<T> | 0 or 1 | Fetching a single book, profile, or total count |
| Flux<T> | 0 to many | Fetching a list of books, search results, or elements of a list field |

Example:

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookService.findById(id);
}

@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
~~~

Spring for GraphQL integrates reactive return types via its reactive adapter mechanism. When a GraphQL field is a single object, `Mono` represents the asynchronous result of that field. For a list field, `Flux` can supply the elements for the list result.

This allows the controller to preserve the reactive model of the service or repository. You do not need to call `subscribe` manually to extract the value before returning.

## 2. Declaring Schemas for Reactive Queries

The Java return type must align with the GraphQL type declared in the SDL. Reactive execution does not change the schema; it only changes how the server produces the field's value.

Example schema:

~~~graphql
type Query {
  book(id: ID!): Book
  books(first: Int = 20): [Book!]!
  searchBooks(keyword: String!, first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

Mappings can use `Mono` or `Flux`:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Flux<Book> books(@Argument Integer first) {
        int limit = first == null ? 20 : first;
        return bookService.findFirst(limit);
    }

    @QueryMapping
    public Flux<Book> searchBooks(
            @Argument String keyword,
            @Argument Integer first) {
        int limit = first == null ? 20 : first;
        return bookService.search(keyword, limit);
    }
}
~~~

The example above assumes `BookService` returns the corresponding publishers. If the service uses synchronous types, the controller can return `Book` or `List<Book>`; there is no need to convert every method to reactive just because the application uses Spring GraphQL.

Keep the schema accurately reflecting the domain. For example, `book` can return null when not found if the field is declared nullable; `books` should return an empty list when there are no results and the schema requires a non-null list.

## 3. Mono for a Single Result

`Mono` fits when a field returns at most one value, such as a lookup by ID.

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookService.findById(id);
}
~~~

The service can use a reactive repository:

~~~java
@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Mono<Book> findById(String id) {
        return repository.findById(id);
    }
}
~~~

When no data is found, reactive repositories typically return `Mono.empty()`. When the publisher completes with no value, the field is treated as having no result. This corresponds to `null` for a nullable GraphQL field.

If the schema declares the field non-null, such as `book(id: ID!): Book!`, yet the resolver finds no `Book` and completes empty, GraphQL must raise an execution error and apply null propagation rules.

Therefore, choose nullability based on the business contract. If not found is a normal scenario, the field can be nullable. If a result must exist, the server should handle missing data as an intentional error.

You can convert an empty result into a business exception:

~~~java
public Mono<Book> requireBook(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new BookNotFoundException(id)));
}
~~~

Do not turn every not-found case into an error if the API is designed to return null. Keep behavior consistent across the schema, service, and clients.

## 4. Flux for List Fields

`Flux` fits when a service emits multiple elements. For a GraphQL field with a list type, Spring for GraphQL converts the reactive result into the field's value during GraphQL execution.

~~~java
@QueryMapping
public Flux<Book> books(@Argument Integer first) {
    int limit = first == null ? 20 : first;
    return bookService.findFirst(limit);
}
~~~

Corresponding SDL:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}
~~~

If there are no books, `Flux.empty()` represents a list with zero elements. For a `[Book!]!` field, an empty list result is still valid because the list exists and contains no null elements.

You can use `Mono<List<Book>>` if the service already constructs the full list:

~~~java
@QueryMapping
public Mono<List<Book>> books() {
    return bookService.findAllAsList();
}
~~~

These two options serve different service designs. `Flux` fits when the data source emits items one by one; `Mono<List<Book>>` fits when the service returns a list already collected into a single value. Check the return type your service actually provides and choose the clearest representation.

Note: a Query is still request-response. Even when a resolver returns `Flux`, the client receives a single GraphQL response for the operation with the list field resolved. Returning `Flux` here does not turn a Query into a connection that streams items as multiple independent responses. If you need continuous updates over time, use a Subscription.

## 5. Combining Multiple Reactive Services

A Query may need data from multiple independent sources. Reactor provides operators to combine publishers without blocking threads.

For example, a book overview page needs `Book` details and the `Review` count:

~~~graphql
type Query {
  bookSummary(id: ID!): BookSummary
}

type BookSummary {
  book: Book!
  reviewCount: Int!
}
~~~

DTO:

~~~java
public record BookSummary(Book book, Integer reviewCount) {
}
~~~

Controller:

~~~java
@QueryMapping
public Mono<BookSummary> bookSummary(@Argument String id) {
    Mono<Book> bookMono = bookService.findById(id);
    Mono<Integer> countMono = reviewService.countByBookId(id);

    return Mono.zip(bookMono, countMono)
            .map(tuple -> new BookSummary(
                    tuple.getT1(),
                    tuple.getT2()));
}
~~~

`Mono.zip` subscribes to the input publishers and combines their results once they emit values. Both independent tasks can progress asynchronously without nested callbacks.

If either publisher completes empty, `Mono.zip` does not produce a tuple. Therefore, decide explicitly how to handle a missing `Book`: you can check `Book` first with `flatMap`, or convert an empty result into an error if business rules require it.

~~~java
@QueryMapping
public Mono<BookSummary> bookSummary(@Argument String id) {
    return bookService.findById(id)
            .switchIfEmpty(Mono.error(
                    new BookNotFoundException(id)))
            .flatMap(book ->
                    reviewService.countByBookId(id)
                            .map(count ->
                                    new BookSummary(book, count)));
}
~~~

The second example ensures the review count is queried only after the `Book` is found. Using `flatMap` is appropriate when a subsequent step depends on the result of the previous step.

Some commonly used operators:

| Operator | Purpose |
|---|---|
| map | Synchronously transform a value |
| flatMap | Transform a value into another publisher |
| zip | Combine results from multiple publishers |
| filter | Keep values matching a condition |
| switchIfEmpty | Select a fallback publisher when no value is emitted |
| onErrorMap | Transform the error type |
| onErrorResume | Select a fallback publisher when an error occurs |

## 6. Distinguishing map and flatMap

Use `map` when the transformation returns an ordinary value. Use `flatMap` when the transformation returns another `Mono` or `Flux`.

~~~java
Mono<String> title = bookService.findById("b-01")
        .map(Book::getTitle);
~~~

Here, `Book` is transformed into `String`.

~~~java
Mono<Author> author = bookService.findById("b-01")
        .flatMap(book ->
                authorService.findById(book.getAuthorId()));
~~~

Here, fetching the `Author` is also asynchronous and returns `Mono<Author>`, so `flatMap` is needed to flatten the publisher.

If you used `map` in the second case, the result would be `Mono<Mono<Author>>`, producing nested types that do not match the intended return type.

## 7. Avoiding block() and subscribe() in Controllers

A common mistake when migrating synchronous code to reactive is calling `block()` to obtain the value immediately:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id).block();
}
~~~

This forces the thread to wait for the publisher to complete. It breaks the benefits of the reactive model and can cause stalls under high load or when running on an event-loop thread.

Another mistake is manually subscribing in the controller:

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    bookService.findById(id).subscribe();
    return Mono.empty();
}
~~~

`subscribe()` launches an independent execution stream detached from the GraphQL request. The framework no longer has full control over the result, errors, or completion timing of that work.

Return the publisher directly:

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Spring for GraphQL manages subscribing and integrating the result into GraphQL execution. The controller should simply describe the pipeline to run.

Never call `block()`, `subscribe()`, or trigger detached side effects inside a normal resolver. For background work outside the GraphQL request lifecycle, move it to a separate component with explicit lifecycle management.

## 8. Combining Blocking Systems with Reactive Code

Not every library in an application supports reactive execution. For example, a synchronous JPA repository may need to be called while gradually migrating a system.

If calling a blocking API is unavoidable, isolate that operation with `Mono.fromCallable` and offload it to `boundedElastic`:

~~~java
public Mono<Book> findById(String id) {
    return Mono.fromCallable(() ->
                    jpaRepository.findById(id).orElse(null))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

This prevents the blocking operation from running directly on an event-loop thread. However, it does not turn JPA into a reactive repository; a thread is still occupied while the database call executes.

Never use `Schedulers.parallel()` for blocking tasks. Do not mechanically wrap every call if a reactive driver or reactive client is already available. For high-load systems, prefer non-blocking data sources such as R2DBC or a reactive HTTP client when the architecture allows.

If a resolver calls multiple blocking services, shifting each call onto `boundedElastic` still consumes threads. Measure and bound load rather than treating `boundedElastic` as an infinite resource.

## 9. Handling Errors in Reactive Queries

Errors can occur when querying the database, calling external services, or transforming data. Reactor propagates errors down the publisher chain until an error operator handles them or GraphQL receives the error.

Example translating a technical error into a business error:

~~~java
public Mono<Book> findById(String id) {
    return repository.findById(id)
            .onErrorMap(
                    DataAccessException.class,
                    ex -> new BookLookupException(
                            "Cannot load book " + id, ex)
            );
}
~~~

With Spring for GraphQL, you can use `DataFetcherExceptionResolver` to translate exceptions into GraphQL errors with client-appropriate details. Never include SQL, stack traces, or sensitive information in public error messages.

Only use `onErrorResume` when a genuinely valid fallback value exists:

~~~java
public Mono<Book> findFeaturedBook() {
    return bookService.findFeatured()
            .onErrorResume(
                    FeaturedBookUnavailableException.class,
                    ex -> bookService.findFallback()
            );
}
~~~

Do not use `onErrorResume(error -> Mono.empty())` for all errors. That can hide database or service failures and mislead clients into thinking the data simply does not exist.

### Errors and Nullability

GraphQL handles error outcomes according to the schema:

- Nullable fields can receive `null` alongside `errors` in the response.
- Non-null fields cannot return `null`; errors may propagate up to the nearest nullable parent field.
- When multiple independent fields execute, an error in one field does not necessarily wipe out data for all other fields.

Design nullability based on business semantics and test both empty publishers and error-emitting publishers.

## 10. Query Limits and Pagination

Reactive does not mean unbounded data can be loaded. A `Flux` can emit many items, yet a GraphQL Query still needs to produce a complete response. Without limits, the server can consume excessive memory and time assembling results.

Enforce limits in both the schema and service:

~~~graphql
type Query {
  books(first: Int = 20, after: String): BookConnection!
}
~~~

A simple connection type:

~~~graphql
type BookConnection {
  edges: [BookEdge!]!
  pageInfo: PageInfo!
}

type BookEdge {
  cursor: String!
  node: Book!
}

type PageInfo {
  hasNextPage: Boolean!
  endCursor: String
}
~~~

The resolver can accept `first` and `after`, validate bounds, and call the service for a single page:

~~~java
@QueryMapping
public Mono<BookConnection> books(
        @Argument Integer first,
        @Argument String after) {

    int pageSize = first == null ? 20 : first;

    if (pageSize < 1 || pageSize > 100) {
        return Mono.error(
                new IllegalArgumentException(
                        "first must be between 1 and 100"));
    }

    return bookService.findConnection(pageSize, after);
}
~~~

Bounds should also be enforced in the service or data-access layer to prevent clients from passing oversized values. With cursor pagination, cursors must be stable and deterministically ordered to avoid skipping or duplicating items across pages.

## 11. Avoiding Uncontrolled Fan-Out

A single Query can trigger many service calls. For example, a client requests 100 books and each book resolves its `author` with a separate request. Even though each call is reactive, the sheer number of requests can still overwhelm backends.

Reactive avoids holding a thread per request, but it does not automatically reduce query count or backend load.

Ways to address this:

- Use `@BatchMapping` or DataLoader to batch related data fetches.
- Cap page sizes and maximum element counts.
- Limit concurrency when using `flatMap` against a rate-limited or quota-bound data source.
- Configure appropriate timeouts for external service calls.
- Monitor duration and invocation counts per resolver.
- Avoid querying unnecessary fields at the database layer.

Example limiting concurrency:

~~~java
Flux<Author> authors = Flux.fromIterable(authorIds)
        .flatMap(authorService::findById, 8);
~~~

The `8` parameter limits how many inner publishers are processed concurrently. Choose the number based on downstream service capacity and real load.

For one-to-many or many-to-one relationships, consider batch loading before increasing concurrency. Increasing parallel requests is no substitute for eliminating N+1 queries.

## 12. Reactive Context and Per-Request Data

In a reactive pipeline, per-request data can flow through Reactor Context or `GraphQLContext` depending on the integration point.

Never store the current user or request data in mutable fields of a singleton controller or service. Multiple GraphQL requests can be processed concurrently; shared mutable state easily leaks data across users.

With annotated controllers, you can read data from the GraphQL context using supported mechanisms such as `@ContextValue`. Example:

~~~java
@QueryMapping
public Mono<List<Book>> myBooks(
        @ContextValue("currentUserId") String userId) {
    return bookService.findByOwnerId(userId).collectList();
}
~~~

`currentUserId` must be placed into the GraphQL context by the authentication layer or an appropriate interceptor. Never trust client-supplied identity values when business rules require an authenticated identity.

If using reactive security or reactive transactions, ensure those components operate on the same reactive chain and are not broken by manual `block()` or `subscribe()` calls.

## 13. Testing Reactive Queries with GraphQlTester

`GraphQlTester` provides a way to test operations without an external GraphQL client. With reactive controllers, tests can wait for execution to finish and assert the data.

Example:

~~~java
@Test
void shouldReturnBookFromReactiveQuery() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "b-01")
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("b-01");
}
~~~

Cases to test:

1. `Mono` emitting a single value.
2. `Mono.empty()` with a nullable field.
3. `Mono.empty()` with a non-null field.
4. Publisher emitting an error and the GraphQL response containing appropriate `errors`.
5. `Flux` emitting multiple elements and the returned list preserving expected order.
6. `Flux.empty()` producing an empty list for a non-null list field.
7. Queries combining multiple services with `zip` or `flatMap`.
8. Pagination rejecting invalid bounds.
9. Batch loading avoiding N+1 queries.
10. User context not leaking across concurrent requests.

For asynchronous tests, let `GraphQlTester` manage execution and await the result. Do not call `subscribe()` manually in tests to trigger controllers.

## 14. How Do Reactive Queries Differ from Subscriptions?

Both Queries and Subscriptions can use reactive types in Spring for GraphQL, but their protocol semantics differ.

| Criterion | Reactive Query | Subscription |
|---|---|---|
| Purpose | Read data at request time | Receive events or updates over time |
| Annotation | @QueryMapping | @SubscriptionMapping |
| Typical return types | Mono<T>, Flux<T> for list fields | Flux<T> |
| Client-side result | A single GraphQL response for the operation | A stream of multiple responses/events |
| Termination | When all fields complete | When the publisher completes or the client cancels |
| Example | Fetch a list of books | Receive notifications when a new book arrives |

Query example:

~~~java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
~~~

Subscription example:

~~~java
@SubscriptionMapping
public Flux<BookEvent> bookAdded() {
    return bookEventPublisher.events();
}
~~~

In a Query, `Flux` builds a list field result inside a single response. In a Subscription, `Flux` represents events emitted over time. Do not use Queries to simulate push notifications, and do not use Subscriptions merely to return an ordinary list.

## 15. Reactive Query Implementation Checklist

Before deploying a reactive resolver to your application:

- [ ] SDL type matches the cardinality: object or list.
- [ ] `Mono` and `Flux` are used with the right semantics.
- [ ] Controller returns the publisher directly without blocking or manual subscribing.
- [ ] Reactive repository/client is used wherever possible.
- [ ] Blocking operations are isolated if they cannot yet be replaced.
- [ ] `Mono.empty` and errors are handled according to nullability.
- [ ] List queries enforce limits and pagination.
- [ ] Independent calls are composed using appropriate reactive operators.
- [ ] N+1 issues are addressed with batch loading or DataLoader.
- [ ] Timeouts, concurrency, and downstream errors have explicit policies.
- [ ] Context and security do not rely on shared mutable state.
- [ ] Tests cover values, empty emissions, errors, and empty lists.

## Conclusion

Spring for GraphQL lets annotated controllers return reactive types such as `Mono` and `Flux` for Queries. `Mono` suits single-value fields, while `Flux` suits list fields. Reactor provides operators such as `map`, `flatMap`, and `zip` to compose data from multiple sources without blocking threads.

A Query returning `Flux` remains a request-response operation with a list result; Subscription is the mechanism for emitting multiple events over time. For reactive Queries to perform reliably, avoid `block()` and manual `subscribe()`, handle empty and error signals in alignment with nullability, bound pagination and fan-out, and verify behavior with `GraphQlTester`.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
