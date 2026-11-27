# Method return value

## Objectives

After this lesson, you will be able to:

- Explain how a resolver method's return value becomes the value of a GraphQL field.
- Choose the appropriate Java type when a resolver returns a scalar, an object, or a list.
- Understand the impact of `null`, empty collections, and nullability in the SDL.
- Return asynchronous results using `CompletionStage`, `Mono`, or `Flux`.
- Distinguish `Flux` used for a query collection field from a subscription stream.
- Use `DataFetcherResult` when you need to return data alongside GraphQL errors or local context.
- Test resolver return values using `GraphQlTester`.

## How does a method return value become a field value?

In Spring for GraphQL, an annotated controller method acts as a resolver for a GraphQL field. The value returned by the method is used by the GraphQL runtime as the result of that field. Spring supports multiple return types so controllers can work with synchronous, asynchronous, or reactive data.

Example schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Resolver:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
~~~

The method returns a `Book` object. GraphQL does not serialize the entire Java object into an arbitrary JSON blob. Instead, the runtime continues resolving the fields the client selected, such as `Book.id` and `Book.title`. Those fields can come from default properties/getters or from dedicated `@SchemaMapping` resolvers.

This means the client's selection set determines which fields are executed. The `bookById` resolver supplies the source object; downstream resolvers supply data for the required child fields.

## Choosing a return type based on the GraphQL type

The Java type should accurately reflect the kind of data exposed by the schema:

| GraphQL field | Common Java types | Example |
| --- | --- | --- |
| Scalar | `String`, `Integer`, `Boolean`, `BigDecimal`, or the type matching a custom scalar | `String title()` |
| Object | Domain object or DTO | `Book bookById(...)` |
| List | `List<T>`, `Collection<T>`, or an appropriate array | `List<Book> books()` |
| Absent value | Reference type returning `null` when absent | `Book findBook(...)` |
| Asynchronous result | `CompletionStage<T>`, `Mono<T>` | `Mono<Book> bookById(...)` |
| Subscription event stream | `Flux<T>` or `Publisher<T>` | `Flux<Book> bookAdded()` |

The Java type does not need to share the exact name of the GraphQL type. What matters is that the GraphQL runtime can read its child fields and determine the concrete type when the schema uses an interface or union.

### Returning a scalar

For a scalar field, the method returns the corresponding value:

~~~graphql
type Query {
  serviceName: String!
  bookCount: Int!
}
~~~

~~~java
@QueryMapping
public String serviceName() {
    return "library-api";
}

@QueryMapping
public int bookCount() {
    return bookService.count();
}
~~~

GraphQL serializes values according to the declared scalar. For custom scalars, the Java value must be compatible with the implementation registered in runtime wiring. For example, a `DateTime` scalar may expect `OffsetDateTime`; do not assume every Java date/time type is converted automatically.

### Returning an object

A method can return a domain object or DTO:

~~~java
@QueryMapping
public Book bookById(@Argument("id") String id) {
    return bookService.findById(id).orElse(null);
}
~~~

If the client only selects `id` and `title`, GraphQL only needs to resolve those two fields. If the client also selects `author`, the runtime continues processing `Book.author`. That field can come from a `Book` property or from a `@SchemaMapping` method.

Return a DTO or domain model tailored to the GraphQL schema. Avoid returning persistence entities with uncontrolled lazy relationships if reading a field might trigger unexpected queries.

### Returning a collection

For a list field, you can return `List<T>`:

~~~graphql
type Query {
  booksByAuthor(authorId: ID!): [Book!]!
}
~~~

~~~java
@QueryMapping
public List<Book> booksByAuthor(
        @Argument("authorId") String authorId) {
    return bookService.findByAuthorId(authorId);
}
~~~

The element order in the response follows the order of the collection returned by the resolver. If the API needs deterministic ordering, sort in the service or query with an explicit `ORDER BY`; do not rely on arbitrary database ordering.

An empty collection is normally represented by an empty list `[]`, which is distinct from `null`. Return an empty collection when the query succeeds but has no elements. Return `null` only when the field's semantics allow representing an absent value.

## Nullability determines how missing values are handled

The GraphQL SDL determines whether a field can return `null`:

~~~graphql
type Query {
  optionalBook(id: ID!): Book
  requiredBooks: [Book!]!
}

type Book {
  id: ID!
  title: String!
}
~~~

`optionalBook` can return `null` if no book is found. `requiredBooks` must return a non-null list, and every element inside the list must also be non-null.

Common combinations:

| SDL | Allowed values |
| --- | --- |
| `Book` | Object or `null` |
| `Book!` | Non-null object |
| `[Book]` | List or `null`; elements may be `null` |
| `[Book!]` | List or `null`; elements must not be `null` |
| `[Book]!` | Non-null list; elements may be `null` |
| `[Book!]!` | Non-null list; every element must be non-null |

If a resolver returns `null` for a non-null field, GraphQL creates an execution error and propagates `null` up to the nearest nullable parent field. If the parent field is also non-null, the error continues propagating upward. Therefore, choose `!` only when the server truly guarantees a value is always present in every valid case.

For example, if `Book.title` is `String!`, the resolver for `title` must never return `null`. If legacy data contains books missing a title, clean the data or define an appropriate business rule before exposing the field as non-null.

### Object not found

If the field is declared nullable, you can return `null` when not found:

~~~java
@QueryMapping
public Book bookById(@Argument("id") String id) {
    return bookService.findById(id).orElse(null);
}
~~~

If you want to return a meaningful error such as `BOOK_NOT_FOUND`, throw a business exception and map it to a GraphQL error using `DataFetcherExceptionResolver`. Do not change a field to non-null just to force GraphQL to report an error when an object does not exist; nullability describes the data contract, while business errors should be represented according to API policy.

If a service returns `Optional<Book>`, decide the semantics clearly and convert it to the appropriate value before returning from the resolver, such as `orElse(null)` or throwing an exception. Do not assume `Optional` will automatically serialize as a GraphQL object.

## Return values of nested fields

A `@SchemaMapping` method receives a source object and returns the value for a field on that object:

~~~graphql
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

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId()).orElse(null);
    }
}
~~~

Here, `Book` is the source object; the method returns `Author` as the value of `Book.author`. GraphQL continues resolving `Author.id` and `Author.name` according to the selection set.

If `Book` already has an `author` property holding an `Author` object, you may not need a separate resolver. When data requires additional lookup, `@SchemaMapping` gives you control over how the value is fetched.

## Asynchronous return with `CompletionStage`

If a service already exposes an asynchronous API based on Java `CompletionStage`, the resolver can return that type directly:

~~~java
@QueryMapping
public CompletionStage<Book> bookById(@Argument("id") String id) {
    return bookService.findByIdAsync(id);
}
~~~

`CompletableFuture<T>` is a common implementation of `CompletionStage<T>`. The GraphQL runtime waits for the result to complete before finalizing the corresponding field. Independent fields can execute asynchronously according to GraphQL Java's execution model.

Do not call `.join()` or `.get()` immediately in the controller to wait for the future to complete. Doing so turns an asynchronous operation into a blocking one and ties up a thread while waiting.

If you must run blocking work on a separate executor, design the service intentionally and use a properly managed executor. Do not arbitrarily use the common pool for long-running I/O calls.

## Returning `Mono` and `Flux` in reactive applications

Spring for GraphQL supports reactive types such as `Mono<T>` and `Flux<T>`. They are useful when services use reactive repositories or reactive HTTP clients.

### `Mono` for a single value

`Mono<T>` represents at most one value:

~~~java
@QueryMapping
public Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

A `Mono` can emit one object or complete without a value. Completing empty is treated as a `null` result, so check it against the field's nullability in the SDL.

### `Flux` for lists in regular queries

`Flux<T>` represents a sequence of elements. For regular query fields, Spring for GraphQL collects the elements into a collection result so GraphQL processes it as a list:

~~~java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
~~~

If there are no elements, the resulting collection is an empty list. For large lists, apply pagination or size limits; do not emit an unbounded amount of data and collect all of it into memory.

You can use `Mono<List<Book>>` if the service returns a list asynchronously. Choose a return type that fits the service API and data-loading model; there is no need to convert every collection into a `Flux` if it provides no real benefit.

### Do not block the reactive pipeline

Do not call `.block()` inside a resolver to extract a value from a `Mono` or `Flux`:

~~~java
// Avoid: blocks the thread waiting for the reactive result.
@QueryMapping
public Book bookById(@Argument("id") String id) {
    return bookService.findById(id).block();
}
~~~

Return the reactive type directly instead:

~~~java
@QueryMapping
public Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Returning a `Mono` or `Flux` does not automatically turn an underlying blocking call into a non-blocking one. If the service uses JDBC or a blocking HTTP client, the pipeline can still block threads. To take advantage of WebFlux, use reactive data access/clients or isolate blocking operations on an appropriate scheduler/executor.

## `Flux` in Subscriptions vs. `Flux` in Queries

For query collections, `Flux<T>` is collected into a list to produce a single normal GraphQL response. For subscriptions, `Flux<T>` is a stream of events emitted over time through a streaming-capable transport.

Schema:

~~~graphql
type Subscription {
  bookAdded: Book!
}
~~~

Resolver:

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<Book> bookAdded() {
        return eventService.bookAdded();
    }
}
~~~

Each element emitted by the `Flux` becomes a subscription result. The client receives events over time via a transport such as WebSocket or Server-Sent Events depending on configuration. When the client cancels the subscription or disconnects, the event source should release the subscription and related resources.

Do not use `Flux` for a subscription merely because a field returns a list. Queries and subscriptions have different semantics: a query produces a single response per execution, whereas a subscription maintains a stream of results.

## Returning `DataFetcherResult` when data needs metadata or errors

Normally a resolver simply returns the field value. When you need to attach GraphQL errors or local context alongside data, GraphQL Java provides `DataFetcherResult<T>`.

Example:

~~~java
import graphql.GraphqlErrorBuilder;
import graphql.execution.DataFetcherResult;

@QueryMapping
public DataFetcherResult<Book> bookDetails(
        @Argument("id") String id) {

    Book book = bookService.findById(id).orElse(null);
    if (book == null) {
        return DataFetcherResult.<Book>newResult()
                .data(null)
                .error(GraphqlErrorBuilder.newError()
                        .message("Book not found")
                        .build())
                .build();
    }

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .build();
}
~~~

`DataFetcherResult` lets you return `data` along with one or more `GraphQLError` instances. It is useful when you need to express a field-level error while preserving valid partial data according to GraphQL semantics. However, if the field is declared non-null, returning `data(null)` can still trigger null propagation.

Do not use `DataFetcherResult` just to replace normal return types. For exceptions thrown in services, a shared exception resolver can standardize errors; for results containing both data and errors simultaneously, `DataFetcherResult` is the better choice.

`DataFetcherResult` also supports local context and extensions. Local context can be passed to child field resolvers when internal data needs to be shared while resolving a branch. Only put necessary data into context, and never use it as global state across requests.

## Combining return values with type resolution

If the schema returns an interface or union, the GraphQL runtime must determine the concrete object type of the Java value. Example:

~~~graphql
interface SearchResult {
  id: ID!
  title: String!
}

type Book implements SearchResult {
  id: ID!
  title: String!
  isbn: String!
}

type Article implements SearchResult {
  id: ID!
  title: String!
  url: String!
}

type Query {
  search: [SearchResult!]!
}
~~~

The resolver can return `List<SearchResult>` containing `Book` and `Article` objects:

~~~java
@QueryMapping
public List<SearchResult> search() {
    return searchService.search();
}
~~~

GraphQL needs to determine whether each Java object corresponds to `Book` or `Article`. If the default type resolution mechanism cannot infer the type properly, register a `TypeResolver` via `RuntimeWiringConfigurer`. A return value implementing the right Java interface without proper type resolution can still fail at GraphQL execution time.

When adding a new concrete type, check both the resolver return value and the runtime type mapping. Do not only test that the Java list has elements; verify `__typename` in the GraphQL response.

## Performance and resolver scope of work

The return type alone does not determine overall performance. A method returning `Mono<Book>` can still make a blocking database call; a method returning `List<Book>` can load too much data; a child field resolver can trigger N+1.

When designing resolvers:

- Use pagination for large collections and enforce a page size limit.
- Query only the data needed for the requested fields when possible.
- Use `@BatchMapping` or `DataLoader` to batch queries for relational fields invoked repeatedly.
- Avoid returning entities with lazy relationships if property access triggers unexpected queries.
- Never block on a reactive pipeline.
- Measure latency and repository/service call counts when testing queries with many nested fields.

For example, a query fetching 50 books where each book has an `author` field can cause 50 calls to `AuthorService` if the resolver loads each author individually. Switching to `@BatchMapping` or `DataLoader` batches the author loading into a single batch call.

## Testing method return values with `GraphQlTester`

`GraphQlTester` verifies results after the GraphQL runtime executes the resolver, regardless of whether the method returns a synchronous object or an asynchronous type.

Example object query:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL Guide");
~~~

You should test these cases:

1. Scalar returns the expected type and value.
2. Returned object resolves its child fields.
3. List preserves order, and an empty list returns `[]`.
4. Nullable field returns `null` when data is absent.
5. Non-null field does not return `null` in valid scenarios.
6. `Mono` or `CompletionStage` completes with the expected value.
7. `Mono.empty()` is handled properly according to nullability.
8. Resolver errors produce GraphQL errors matching the contract.
9. `DataFetcherResult` returns data and errors as expected.
10. Subscriptions emit events and stop when the client unsubscribes.

For subscriptions, use a tester or integration test suited to the configured streaming transport. A regular query test cannot verify WebSocket/SSE handshakes, stream lifecycle, and cancellation.

## Common issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Object field returns, but child fields are `null` | Object lacks matching property/getter or lacks `@SchemaMapping` | Check the source object and child field resolvers |
| GraphQL reports a non-null error | Resolver returned `null` for a field with `!` | Fix data/logic or adjust nullability to match the contract |
| List returns `null` instead of `[]` | Service returned `null` for a collection | Normalize absent collection results to an empty list |
| Reactive query still blocks | Blocking call or `.block()` inside the resolver | Return the reactive type directly or isolate blocking work |
| Subscription returns only one response | Used a query mapping or a transport that does not support streaming | Use `@SubscriptionMapping` and configure a streaming transport |
| Interface/union fails to resolve | Runtime cannot determine the concrete GraphQL type | Configure a `TypeResolver` and test `__typename` |
| Response has errors even with data | `DataFetcherResult` contains errors or a child field raised an error | Inspect `errors` and nullability along the response branch |
| List query is slow | Child field resolver causes N+1 or loads too much data | Add pagination and use batching/`DataLoader` |

## Comprehensive practice

Build a library API with the following resolvers:

1. `bookById(id: ID!): Book` returning `Book` or `null` when not found.
2. `books(first: Int!): [Book!]!` returning a bounded list and an empty list when no books exist.
3. `Book.author: Author` using `@SchemaMapping` to load the author.
4. Change `bookById` to return `Mono<Book>` if the service uses a reactive repository.
5. Create an asynchronous method returning `CompletionStage<Book>` if the service already provides that API.
6. Add a `@SubscriptionMapping` returning `Flux<Book>` for new book events.
7. Use `DataFetcherResult<Book>` for a use case that needs to return a structured field error.
8. Write `GraphQlTester` tests verifying objects, lists, nulls, errors, and nested fields.

Once finished, explain why `Mono<Book>` fits a single value, how `Flux<Book>` has different semantics between queries and subscriptions, and why a non-null field must never return `null`.

## Key takeaways

A resolver method's return value becomes the value of the GraphQL field. Scalars are serialized according to the scalar type; objects serve as sources to resolve child fields; collections become lists. Nullability in the SDL dictates whether a field may be absent and how GraphQL propagates errors. Spring for GraphQL supports synchronous types, `CompletionStage`, `Mono`, `Flux`, and `DataFetcherResult`; choose based on the semantics of the field and service. Query collections gather elements into a list, while subscriptions use a publisher to emit events over time. Never block a reactive pipeline, keep N+1 under control, and test both results and errors with `GraphQlTester`.
