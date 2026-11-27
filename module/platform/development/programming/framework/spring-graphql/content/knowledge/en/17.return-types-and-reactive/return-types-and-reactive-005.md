# `Mono` in Spring for GraphQL

`Mono<T>` is a Project Reactor reactive type representing an asynchronous task that can emit at most one value of type `T`, complete without a value, or terminate with an error. In Spring for GraphQL, a controller can return `Mono<T>` to supply data for a GraphQL field without blocking a thread to wait for the result.

This fits queries and mutations that need to call reactive databases, other services, or multiple asynchronous data sources. GraphQL handles the value, empty completion state, or error signal of the publisher to build the response; `Mono` describes how that result is supplied over time.

## 1. What is `Mono<T>`?

`Mono<T>` belongs to Project Reactor, in the `reactor.core.publisher` package. A `Mono` has three main outcomes:

| Outcome | Meaning |
|---|---|
| `Mono.just(value)` | Emits exactly one value and completes. |
| `Mono.empty()` | Completes without emitting a value. |
| `Mono.error(exception)` | Terminates with an error. |

Example:

```java
Mono<Book> found = Mono.just(new Book("book-01", "GraphQL Basics"));
Mono<Book> missing = Mono.empty();
Mono<Book> failed = Mono.error(new IllegalStateException("Database unavailable"));
```

`Mono` is a Reactive Streams `Publisher`. Many `Mono` pipelines are lazy: the pipeline only executes when there is a subscriber. During a GraphQL request, Spring for GraphQL manages subscribing to the publisher and uses its signals to continue resolving fields.

A `Mono` cannot emit `null`. `Mono.just(null)` is invalid. If you have a Java value that may be `null`, use `Mono.justOrEmpty(value)` to turn `null` into `Mono.empty()`.

## 2. Using `Mono` as the return type of `@QueryMapping`

Suppose the GraphQL schema declares:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

The service uses a reactive repository:

```java
@Service
class BookService {

    private final BookRepository bookRepository;

    BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    Mono<Book> findById(String id) {
        return bookRepository.findById(id);
    }
}
```

The controller returns `Mono<Book>` directly:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Mono<Book> bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

When the client sends:

```graphql
query {
    bookById(id: "book-01") {
        id
        title
    }
}
```

Spring for GraphQL handles `Mono<Book>` as the asynchronous result of the `Query.bookById` field. When `Mono` emits `Book`, GraphQL continues resolving the `id` and `title` fields according to the selection set. The controller does not need to call `subscribe()` itself or wait for the result with `block()`.

The Java type `Mono<Book>` does not appear in SDL. The schema still declares the GraphQL type as `Book`; the reactive publisher is simply how the server provides the field's value.

## 3. Using `Mono` with `@MutationMapping`

Mutations can also return `Mono<T>` when the operation needs to run asynchronously:

```graphql
input CreateBookInput {
    title: String!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

```java
@MutationMapping
Mono<Book> createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
```

The service can validate the input, persist the record via a reactive repository, and emit the newly created object. GraphQL only finishes the response after the publisher emits a result or completes.

If a mutation only performs a side effect, such as deleting a record, do not have a Non-null GraphQL field receive `Mono<Void>` and expect it to produce a value automatically. `Void` is not a GraphQL output type and `Mono<Void>` completes without emitting a value. Design a meaningful return type instead, for example:

```graphql
type DeleteBookPayload {
    deletedId: ID!
}

type Mutation {
    deleteBook(id: ID!): DeleteBookPayload!
}
```

```java
public record DeleteBookPayload(String deletedId) {}

@Controller
class BookDeleteController {

    private final BookService bookService;

    BookDeleteController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    Mono<DeleteBookPayload> deleteBook(@Argument("id") String id) {
        return bookService.deleteById(id)
            .thenReturn(new DeleteBookPayload(id));
    }
}
```

Suppose `bookService.deleteById(id)` returns `Mono<Void>`. `thenReturn` waits for the delete operation to complete and then emits the payload. If the delete operation raises an error, the error continues along the reactive chain and is handled by the application's GraphQL error mechanism.

## 4. Distinguishing `map` and `flatMap`

When working with `Mono`, two commonly used operators are `map` and `flatMap`:

- `map` transforms a value synchronously and returns a new value.
- `flatMap` calls a function returning another publisher and flattens the result into the pipeline, avoiding `Mono<Mono<T>>`.

Example using `map` to convert an entity to a DTO:

```java
Mono<BookView> findBookView(String id) {
    return bookRepository.findById(id)
        .map(book -> new BookView(book.getId(), book.getTitle()));
}
```

Example using `flatMap` when you need to call another asynchronous service next:

```java
Mono<BookDetails> findBookDetails(String id) {
    return bookRepository.findById(id)
        .flatMap(book -> authorRepository.findById(book.getAuthorId())
            .map(author -> new BookDetails(book, author)));
}
```

If you use `map` with a function returning `Mono<Author>`, the result would be `Mono<Mono<Author>>`. `flatMap` flattens nested publishers and keeps the pipeline reactive.

## 5. Combining multiple data sources with `Mono.zip`

When a field needs data from multiple independent sources, you can use `Mono.zip` to combine the results:

```java
Mono<BookDashboard> dashboard(String bookId) {
    Mono<Book> book = bookRepository.findById(bookId);
    Mono<List<Review>> reviews = reviewRepository.findByBookId(bookId).collectList();
    Mono<Author> author = authorRepository.findByBookId(bookId);

    return Mono.zip(book, reviews, author)
        .map(tuple -> new BookDashboard(
            tuple.getT1(),
            tuple.getT2(),
            tuple.getT3()
        ));
}
```

`zip` coordinates the publishers and emits a result once every required source has emitted a value. Sources can be subscribed to within the same execution; the degree of concurrency depends on how each source executes and its scheduler.

Note: if one source completes empty, `Mono.zip` by default cannot build the full tuple and the combined result also completes empty. If a source is optional, specify a fallback value before zipping, for example:

```java
Mono<Author> author = authorRepository.findByBookId(bookId)
    .defaultIfEmpty(Author.unknown());
```

Only use a fallback value if it has business meaning. Do not turn missing required data into a fake object just to let the pipeline complete.

## 6. Handling `Mono.empty()` and nullability in GraphQL

`Mono.empty()` means the publisher completed without emitting a value. When used as the result of a GraphQL field, it corresponds to the field having no value (`null`). This result must match the nullability declared in SDL.

| SDL | When `Mono` completes empty |
|---|---|
| `book: Book` | Field can accept `null`; no Non-null violation. |
| `book: Book!` | Violates Non-null contract; GraphQL creates an execution error and applies null propagation. |
| `books: [Book!]!` with return type `Mono<List<Book>>` | List field cannot be `null`; emit `List.of()` when there are no elements. `Mono.empty()` becomes `null`, violating Non-null. |

If a repository returns `Flux<Book>`, you can use `collectList()` to create `Mono<List<Book>>`. This operator emits a list even when there are zero elements:

```java
Mono<List<Book>> books() {
    return bookRepository.findAll().collectList();
}
```

For example, if the book is not found and the API wants to return `null`:

```java
@QueryMapping
Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

With the schema `bookById(id: ID!): Book`, `Mono.empty()` is a valid result.

If not finding the book is considered a business error, you can turn empty into an exception:

```java
@QueryMapping
Mono<Book> requiredBook(@Argument("id") String id) {
    return bookService.findById(id)
        .switchIfEmpty(Mono.error(new BookNotFoundException(id)));
}
```

The exception can be mapped to a `GraphQLError` using `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`. When a field is declared Non-null, keep in mind that an error can cause `null` to propagate up to the parent level.

Do not use `Mono.just(null)`. If a legacy Java API returns a potentially `null` object, you can convert it using:

```java
Mono<Book> findLegacyBook(String id) {
    return Mono.fromCallable(() -> legacyBookService.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

`Mono.fromCallable` emits the value when the callable returns a non-`null` object and completes empty if the callable returns `null`. `Schedulers` is imported from `reactor.core.scheduler.Schedulers`. `boundedElastic` is more appropriate than an event-loop scheduler for bounded blocking tasks. However, this is a compatibility measure when a blocking API cannot yet be replaced; do not use it to turn an entire application into fake reactive code. Set limits and monitor task execution time.

## 7. Error handling in a reactive pipeline

When a publisher emits an error signal, subsequent operators do not receive normal values. You can transform the exception or recover with another publisher.

### `onErrorMap`

Use `onErrorMap` to convert technical errors into domain exceptions:

```java
Mono<Book> findBook(String id) {
    return bookRepository.findById(id)
        .onErrorMap(
            DatabaseUnavailableException.class,
            ex -> new BookLookupException("Cannot load book", ex)
        );
}
```

The exception can then be handled by a GraphQL exception handler. Do not expose raw technical messages directly to clients.

### `onErrorResume`

Use `onErrorResume` when there is a valid recovery strategy:

```java
Mono<BookSummary> summary(String id) {
    return bookService.loadSummary(id)
        .onErrorResume(ExternalCatalogException.class,
            ex -> cacheService.findSummary(id));
}
```

In this example, if the external catalog fails, the service tries reading data from the cache. Only fall back when the replacement data still satisfies the contract and business rules. Do not catch every exception and return `Mono.empty()`, because that can disguise system failures as "not found".

### `switchIfEmpty` vs `onErrorResume`

The two operators handle two different signals:

| Operator | Triggered when |
|---|---|
| `switchIfEmpty(...)` | Publisher completes without emitting a value. |
| `onErrorResume(...)` | Publisher terminates with an exception. |

Do not use `switchIfEmpty` to handle exceptions, and do not use `onErrorResume` to replace logic for absent data when the two cases have different meanings.

## 8. `Mono` is lazy: do not call `block()` or `subscribe()` in a resolver

A Reactor pipeline typically starts only when subscribed to. Spring for GraphQL receives `Mono` from the handler and manages subscribing when executing the field. Therefore, the resolver should return the publisher:

```java
@QueryMapping
Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Do not subscribe manually:

```java
@QueryMapping
Mono<Book> bookById(@Argument("id") String id) {
    bookService.findById(id).subscribe();
    return Mono.empty();
}
```

This incorrect snippet creates a separate subscription detached from the GraphQL lifecycle. GraphQL does not receive the query result and may return `null` before the detached task finishes; errors also bypass GraphQL's error handling path.

Do not block:

```java
@QueryMapping
Book bookById(@Argument("id") String id) {
    return bookService.findById(id).block();
}
```

`block()` blocks the thread to wait for the publisher. This defeats reactive execution and can fail when running on threads that disallow blocking. Return `Mono<Book>` so the framework coordinates asynchronously.

## 9. Avoiding blocking threads in a reactive flow

Returning `Mono` does not guarantee all work inside is non-blocking. If the pipeline invokes blocking JDBC, a blocking HTTP client, or synchronous I/O, threads can still be blocked.

Prefer using:

- Reactive database drivers/repositories when reactive data access is needed.
- `WebClient` or clients with reactive APIs for HTTP calls.
- Reactor operators to compose asynchronous tasks instead of waiting with `get()`, `join()`, or `block()`.

If calling a blocking API is unavoidable, isolate that task on a scheduler meant for blocking work:

```java
Mono<Book> findFromLegacySystem(String id) {
    return Mono.fromCallable(() -> legacyBookService.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

`Schedulers` is imported from `reactor.core.scheduler.Schedulers`. `Mono.fromCallable` already turns a `null` result into `Mono.empty()`, so there is no need to also wrap it in `Mono.justOrEmpty`. `boundedElastic` is better suited than an event-loop scheduler for bounded blocking work. Still, this is a compatibility bridge until the blocking API can be replaced; do not use it to make an entire application appear artificially reactive. Set bounds and monitor task execution times.

Do not call `subscribeOn` or `publishOn` out of habit in every pipeline. Only specify a scheduler when you need to control where a specific task runs. Reactive clients usually already manage their own I/O and internal schedulers.

## 10. Testing `Mono` in Spring for GraphQL

You can use `GraphQlTester` to test queries whose resolvers return `Mono`. Mock the service to emit a value with `Mono.just`:

```java
@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsBookFromMono() {
        given(bookService.findById("book-01"))
            .willReturn(Mono.just(new Book("book-01", "GraphQL Basics")));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    bookById(id: "book-01") {
                        id
                        title
                    }
                }
                """)
            .execute();

        response.path("bookById.id").entity(String.class).isEqualTo("book-01");
        response.path("bookById.title").entity(String.class).isEqualTo("GraphQL Basics");
    }
}
```

This is an illustrative example; imports, the static import `given`, the `Book` class, `BookService`, and SDL must exist in the test context. Depending on the Spring Boot version, the mock bean annotation may be `@MockitoBean` or `@MockBean`.

Add tests for the remaining signals as well:

- `Mono.empty()` with a nullable field: the response has value `null` and no errors solely from the empty field.
- `Mono.empty()` with a Non-null field: the response contains an execution error due to nullability violation.
- `Mono.error(...)`: the exception is mapped to a GraphQL error with an appropriate code and path.
- `onErrorResume(...)`: fallback is used only for expected error types.
- Mutation returning `Mono<Payload>`: verify the side effect completes before the payload is returned.

At the service layer, you can use `StepVerifier` to test publishers independently of GraphQL, such as verifying `Mono.empty()`, emitted values, or exceptions. `GraphQlTester` tests additionally confirm how Spring for GraphQL turns reactive signals into GraphQL responses.

## 11. `Mono` and other return types

| Return type | Meaning | Common use case |
|---|---|---|
| `Book` | One synchronous value | Synchronous service or already available data. |
| `Mono<Book>` | 0 or 1 asynchronous value | Looking up a single record, calling a reactive service. |
| `CompletableFuture<Book>` | One asynchronous result | Integrating Java async APIs or Future-based libraries. |
| `Flux<Book>` | 0 to many elements in a reactive stream | Reactive data lists or streams, depending on field and operation type. |
| `Mono<List<Book>>` | One result containing the whole list | Returning a collection once the query completes. |

`Mono<Book>` does not mean a GraphQL list. It represents a single `Book` value or no value. If the schema expects `[Book!]!`, the Java result can be `Mono<List<Book>>` to emit a complete list. For subscriptions or event streams, `Flux<T>` is usually more appropriate because it can emit multiple elements over time.

Do not pick reactive types just because they look modern. Choose based on how your services and data sources actually operate. If every layer is blocking, wrapping them in `Mono` does not automatically deliver non-blocking benefits.

## 12. Common errors

**Calling `block()` in the controller.** The thread is blocked and the reactive flow loses its benefits. Return the publisher directly to Spring for GraphQL.

**Calling `subscribe()` manually in a resolver.** Execution becomes detached from GraphQL execution; the framework does not wait and does not receive errors properly. Return `Mono` instead.

**Using `Mono.just(null)`.** Reactor does not allow emitting `null`. Use `Mono.empty()` or `Mono.justOrEmpty(value)`.

**Confusing `Mono.empty()` with `Mono.error(...)`.** Empty is completing without a value; error is terminating with a failure. Choose the signal according to business meaning.

**Not aligning with SDL nullability.** Empty maps to `null`; Non-null fields will trigger execution errors and null propagation.

**Wrapping a blocking API in `Mono` and assuming it is non-blocking.** The blocking body still blocks threads. Use reactive clients or isolate blocking tasks on an appropriate scheduler.

**Swallowing all errors with `onErrorResume`.** Falling back to empty or a default value can hide outages. Only recover from errors with a clear fallback strategy.

**Using `Mono<Void>` for a field needing a GraphQL value.** Empty completion produces no output. Return a meaningful payload or scalar after the side effect using `thenReturn`.

## Conclusion

`Mono<T>` enables Spring for GraphQL resolvers to supply a single asynchronous value or complete empty/with error without blocking a thread waiting for results. Use `map` for synchronous transformations, `flatMap` to chain reactive tasks, `zip` to combine independent sources, `switchIfEmpty` for missing data cases, and `onErrorResume` for intentional recovery strategies. Always align `Mono.empty()` with SDL nullability, avoid `block()`/`subscribe()` in resolvers, and test value, empty, and error cases with `GraphQlTester`.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — `Mono` API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
