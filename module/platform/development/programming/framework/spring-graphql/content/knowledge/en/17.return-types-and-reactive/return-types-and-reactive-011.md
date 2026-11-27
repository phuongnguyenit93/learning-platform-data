# Async Return and Error Handling

In Spring for GraphQL, a resolver does not have to return data immediately when the method is called. It can return a result that will complete later, such as `Mono<T>`, `Flux<T>`, or `CompletionStage<T>`. GraphQL Java coordinates asynchronous results to continue resolving the field tree and build the response once the required work finishes.

When an asynchronous task fails, the error must be turned into a GraphQL error. Spring for GraphQL provides extension points such as `@GraphQlExceptionHandler`, `DataFetcherExceptionResolver`, and `SubscriptionExceptionResolver` to handle errors at the right execution stage. Choosing the right return type and error-handling mechanism helps the API preserve partial data responses, manage cancellation, and avoid leaking internal information.

This lesson explains asynchronous return types in annotated controllers and DataFetchers, how `Mono` and `Flux` are handled by GraphQL, how errors flow through responses, how to handle exceptions for fields and Subscriptions, along with timeouts, context propagation, and testing.

## 1. Synchronous and asynchronous in resolvers

A synchronous resolver returns a value directly:

```java
@QueryMapping
public Book bookById(@Argument String id) {
    return bookService.findById(id);
}
```

The method only returns after `bookService.findById` finishes. If the service calls a database using a blocking API, the executing thread must wait for that operation.

An asynchronous resolver returns a handle representing work that will complete later:

```java
@QueryMapping
public Mono<Book> bookById(@Argument String id) {
    return bookService.findByIdReactive(id);
}
```

The method returns `Mono<Book>` immediately. The `Book` value will be emitted once the data source finishes. The GraphQL engine can continue coordinating other fields and wait for asynchronous results before finalizing the response.

Core differences:

| Return approach | Meaning |
| --- | --- |
| `T` | Value is already available when the method returns |
| `Mono<T>` | One asynchronous value or no value |
| `Flux<T>` | An asynchronous sequence of multiple values |
| `CompletionStage<T>` | A Java result that will complete in the future |
| `Callable<T>` | Synchronous work executed asynchronously via a configured Executor |

Simply using an asynchronous type does not automatically make code faster. Benefits depend on the I/O source, thread model, and how the application coordinates work. Wrapping a blocking call inside `Mono.just(...)` does not make that call non-blocking.

## 2. Return types supported by Spring for GraphQL

For annotated controller methods, Spring for GraphQL supports these main return types:

| Return type | Meaning |
| --- | --- |
| `T` | Already resolved application value |
| `Mono<T>` | Asynchronous result with at most one element |
| `Flux<T>` | Multiple asynchronous results |
| Kotlin `suspend fun` / `Flow` | Automatically adapted to corresponding reactive types |
| `Callable<T>` | Runs work via the Executor on `AnnotatedControllerConfigurer` |
| `DataFetcherResult<P>` | Full GraphQL result, optionally carrying errors, extensions, or local context |

At the GraphQL Java layer, a `DataFetcher` can return `CompletionStage`; Spring for GraphQL supports this mechanism and uses it for asynchronous field execution. `CompletableFuture` is a common implementation of `CompletionStage`. With annotated controllers, `Mono`/`Flux` are the natural reactive choices; `Callable` fits blocking work that needs to be offloaded to an Executor.

### Returning CompletableFuture

When integrating a low-level DataFetcher or a Java API already providing `CompletionStage`, you can return `CompletableFuture`:

```java
DataFetcher<CompletableFuture<Book>> bookFetcher =
        environment -> CompletableFuture.supplyAsync(
                () -> bookService.findById(environment.getArgument("id")),
                executor);
```

Pass an appropriate Executor instead of defaulting to the common pool for every task. When using annotated controllers, choose return types explicitly supported by your Spring version.

## 3. Mono<T>: a single asynchronous result

`Mono<T>` fits fields returning a single object or scalar:

```java
@Controller
public class BookQueryController {

    private final ReactiveBookService bookService;

    public BookQueryController(ReactiveBookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> bookById(@Argument String id) {
        return bookService.findById(id);
    }
}
```

A `Mono<Book>` can:

- Emit exactly one `Book` and complete.
- Complete without emitting any element.
- Terminate with an error signal.

For nullable GraphQL fields, an empty Mono is usually represented as `null`. If SDL declares a non-null field yet no value is produced, GraphQL applies null propagation rules and generates an appropriate execution error.

Do not call `block()` in a WebFlux resolver just to extract the value from a Mono. Doing so blocks the thread and defeats the benefits of the reactive pipeline.

## 4. Flux<T>: multiple asynchronous results

`Flux<T>` fits when a data source emits multiple elements:

```java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
```

For a regular Query field, Spring for GraphQL converts reactive DataFetcher return values into an asynchronous form GraphQL Java can handle. Specifically, `Mono` is adapted to `CompletableFuture`; elements of `Flux` are collected into a `List` before the field completes.

Therefore, `Flux<Book>` in a Query does not mean the HTTP response sends each book immediately as elements arrive. The client normally receives one GraphQL response after the field list has been aggregated.

Example SDL:

```graphql
type Query {
  books: [Book!]!
}
```

Controller:

```java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
```

The GraphQL response still has a list structure:

```json
{
  "data": {
    "books": [
      { "id": "book-1", "title": "GraphQL Basics" },
      { "id": "book-2", "title": "Spring GraphQL" }
    ]
  }
}
```

If the list can be very large, design pagination rather than relying on an unbounded Flux to return all data in one response.

## 5. Flux in Subscriptions differs from Flux in Queries

Subscription is the operation meant for data produced over time. In this case, `Flux<T>` can be retained as a Reactive Streams Publisher so the transport sends events as each emission occurs.

SDL:

```graphql
type Subscription {
  bookPublished: Book!
}
```

Controller:

```java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<Book> bookPublished() {
        return eventService.bookPublished();
    }
}
```

Client opens a subscription:

```graphql
subscription {
  bookPublished {
    id
    title
  }
}
```

For a regular Query, Flux is collected into a list. For a Subscription, the publisher is retained so the transport receives continuous events. Therefore, choose the operation type based on the API contract:

| Need | Representation |
| --- | --- |
| Fetch an existing list | Query returning List or Flux |
| Observe new events | Subscription returning Flux |
| Fetch a single object asynchronously | Query returning Mono |

Subscriptions require a streaming-capable transport such as WebSocket or RSocket. Standard HTTP POST cannot sustain a streaming subscription response in that manner.

GraphQL can resolve fields of each event asynchronously. Therefore, if events are processed concurrently across field layers, the order of events leaving the transport may differ from upstream order. When the application requires preserving order, you can configure subscription event ordering via GraphQL context according to the documentation for your GraphQL Java version.

## 6. Callable and executing blocking code

If an existing service uses JDBC or a blocking API, do not call it directly from a WebFlux event-loop thread. One option is using `Callable<T>` with an Executor configured on `AnnotatedControllerConfigurer`:

```java
@SchemaMapping
public Callable<BookDetails> details(Book book) {
    return () -> blockingBookService.loadDetails(book.id());
}
```

Spring for GraphQL submits the Callable to the configured Executor. If no Executor is configured, do not assume Callable automatically runs on a background thread.

With Java 21+, when `AnnotatedControllerConfigurer` has an Executor, controller methods with blocking signatures can be invoked asynchronously. Spring Boot can auto-configure an Executor backed by virtual threads when enabled:

```yaml
spring:
  threads:
    virtual:
      enabled: true
```

Virtual threads make managing many blocking tasks more convenient, but they do not turn JDBC into non-blocking I/O. Understand the thread model of both the transport and dependencies to choose the execution approach.

### Choosing an execution approach

| Data source | Recommended approach |
| --- | --- |
| Reactive repository or WebClient | Return Mono/Flux |
| Java API returning CompletionStage | Return CompletionStage in the appropriate DataFetcher |
| Blocking service on MVC | Can return `T` directly; consider Executor/virtual threads if needed |
| Blocking service on WebFlux | Offload work to an appropriate Executor or use Callable with configurer |
| Event stream | Return Flux from Subscription |

Do not use `CompletableFuture.supplyAsync` with the common pool indiscriminately for blocking calls. Manage Executors, concurrency limits, and timeout policies explicitly.

## 7. AsyncExecutionStrategy and concurrent field execution

GraphQL Java typically uses `AsyncExecutionStrategy` to coordinate fetching fields. A DataFetcher can return a `CompletionStage`; the engine awaits stage completion and combines results across the GraphQL tree.

Example query:

```graphql
query {
  bookById(id: "book-1") {
    title
    inventory
    reviews {
      rating
    }
  }
}
```

If the `inventory` and `reviews` fields are independent branches, GraphQL can execute their corresponding data fetchers concurrently rather than waiting for one branch to finish before starting the other. This is a benefit of async execution, though it does not guarantee every database call automatically runs in parallel or faster.

Never rely on the completion order of independent Query fields. If steps depend on each other, express the dependency inside the resolver/service or use an explicit coordinating use case.

For Mutations, top-level mutation fields are executed sequentially per the GraphQL specification. Async returns can still be used within each field, without altering the sequential execution rule for root mutation fields.

## 8. Errors in asynchronous return types

Errors can occur at several points:

| Error source | Example |
| --- | --- |
| Before returning async handle | Method throws an exception immediately when invoked |
| Inside CompletionStage | Future completes exceptionally |
| Inside Mono | Pipeline emits an error signal |
| Inside Query Flux | An element or upstream terminates with an error |
| Inside Subscription Flux | Publisher emits an error after transport has subscribed |
| Before calling DataFetcher | GraphQL document parsing or validation fails |

Example error from Mono:

```java
@QueryMapping
public Mono<Book> bookById(@Argument String id) {
    return bookService.findById(id)
            .switchIfEmpty(Mono.error(
                    new BookNotFoundException(id)));
}
```

Example error from CompletionStage:

```java
@QueryMapping
public CompletableFuture<Book> bookById(@Argument String id) {
    return bookService.findByIdAsync(id)
            .toCompletableFuture();
}
```

Errors in async handles are observed by the GraphQL engine when the stage or publisher finishes. For regular Query/Mutation fields, Spring for GraphQL uses built-in exception handling to convert data-fetching errors into entries in the response `errors`.

## 9. GraphQL responses with both data and errors

GraphQL allows a response to contain both successfully retrieved data and field errors. For example, a `reviews` field fails while `title` still succeeds:

```json
{
  "data": {
    "bookById": {
      "title": "Spring GraphQL",
      "reviews": null
    }
  },
  "errors": [
    {
      "message": "Review service is unavailable",
      "path": ["bookById", "reviews"]
    }
  ]
}
```

This is a partial response. The failing field is set to null per GraphQL nullability rules; independent fields that resolved successfully can still appear in `data`.

If the failing field is declared non-null, GraphQL propagates null up to the nearest nullable parent. That propagation can continue higher up the response tree. Thus, nullability in SDL directly affects how much data is lost when a resolver fails.

A GraphQL error typically includes:

- `message`: error message.
- `locations`: location of the field in the GraphQL document if determinable.
- `path`: path to the field that caused the error.
- `extensions`: additional metadata such as error codes or classification.

Not every error is HTTP 500. A field-level error can be returned in a GraphQL response alongside a normal HTTP response, depending on the transport and error kind. Clients should inspect both `data` and `errors`.

## 10. Handling errors with @GraphQlExceptionHandler

For annotated controllers, you can use `@GraphQlExceptionHandler` to handle exceptions thrown while invoking handler methods. An error-handling method placed inside a controller applies only to that controller; if placed in `@ControllerAdvice`, it can apply across multiple controllers.

Example domain exception:

```java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
```

Global exception advice:

```java
@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handle(
            GraphqlErrorBuilder<?> errorBuilder,
            BookNotFoundException exception) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .build();
    }
}
```

`GraphqlErrorBuilder` is supplied by Spring as a method argument and is already bound to the current `DataFetchingEnvironment`. This helps construct errors with the right field path and execution context. In the example, the client receives a safe message; detailed IDs or internal info can be logged on the server per application policy.

Spring GraphQL provides common error categories via `ErrorType`:

| ErrorType | Appropriate scenario |
| --- | --- |
| `BAD_REQUEST` | Invalid input or request |
| `UNAUTHORIZED` | Unauthenticated |
| `FORBIDDEN` | Insufficient permissions |
| `NOT_FOUND` | Resource not found |
| `INTERNAL_ERROR` | Unexpected system error |

Do not return raw exception messages for all error types. Messages may contain SQL, table names, internal URLs, or sensitive information. Map domain errors to messages and classifications matching the API contract.

## 11. DataFetcherExceptionResolver for non-controller DataFetchers

`@GraphQlExceptionHandler` integrates with annotated controller invocations. If the application registers DataFetchers manually with GraphQL Java or uses another DataFetcher type, you can use `DataFetcherExceptionResolver`.

Spring Boot automatically detects `DataFetcherExceptionResolver` beans and includes them in `GraphQlSource`'s error-handling pipeline. Multiple resolvers can be registered; they are tried in order until one resolves the exception into a list of `GraphQLError`s.

`DataFetcherExceptionResolverAdapter` is a convenience class providing protected methods to map an exception to one or more GraphQL errors. When shared error handling for low-level DataFetchers is needed, this is the right extension point.

Note on scope:

- Exceptions from controller handlers: prefer `@GraphQlExceptionHandler`.
- Exceptions from custom DataFetchers: use `DataFetcherExceptionResolver`.
- Request parse or validation errors before DataFetchers run: not handled by `DataFetcherExceptionResolver`; inspect transport interceptors.
- Errors emitted after a Subscription publisher has been subscribed to: use `SubscriptionExceptionResolver`.

## 12. Errors in Subscription publishers

Subscriptions have a different lifecycle from Queries. Initially, the DataFetcher only returns a Publisher; afterwards the transport subscribes to the Publisher and receives multiple events. Therefore, if the publisher emits an error after the subscription has started, that error occurs after the initial DataFetcher already finished.

`DataFetcherExceptionResolver` cannot handle error signals emitted after that point. Spring for GraphQL provides `SubscriptionExceptionResolver` to translate errors from Subscription Publishers into GraphQL errors sent over the transport, such as a final WebSocket message.

Example of a publisher that may fail:

```java
@SubscriptionMapping
public Flux<Book> bookPublished() {
    return eventService.bookPublished()
            .onErrorMap(
                    EventSourceUnavailableException.class,
                    ex -> new BookEventStreamException());
}
```

This snippet converts the source exception into a meaningful domain exception. To format the final subscription error, register a `SubscriptionExceptionResolver` appropriate for your Spring for GraphQL version.

Do not treat `DataFetcherExceptionResolver` as if it handles the entire publisher lifecycle. Distinguish errors occurring while creating the publisher from errors occurring after the publisher has started emitting events.

## 13. Request errors vs. data fetching errors

Not every GraphQL error originates from a resolver:

| Stage | Example | Handling mechanism |
| --- | --- | --- |
| Document parsing | Invalid GraphQL syntax | GraphQL engine and transport |
| Document validation | Non-existent field or argument | GraphQL engine and transport |
| Input coercion | Wrong variable type or missing non-null value | GraphQL engine |
| Data fetching | Resolver throws exception or async stage fails | `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver` |
| Subscription stream | Publisher emits error after subscribing | `SubscriptionExceptionResolver` |

Parse/validation errors occur before any DataFetcher is called. Responses typically have `data: null` and errors with no field path. If you need to customize request-level errors, inspect `ExecutionResult` inside a `WebGraphQlInterceptor`.

## 14. Timeouts and cancellation

A GraphQL request can take too long due to slow queries, hung dependent services, or non-terminating streams. Spring for GraphQL provides `TimeoutWebGraphQlInterceptor` for web transports:

```java
@Configuration
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(5));
    }
}
```

When a request exceeds the timeout, the interceptor terminates the request according to transport policy and sends a cancel signal up the pipeline. Reactive data fetchers can observe cancellation to stop in-flight work.

This timeout does not replace per-dependency timeouts. Applications should consider:

- Database query timeouts.
- WebClient or HTTP client timeouts.
- GraphQL request timeouts.
- Concurrency limits and stream item limits.
- Cancellation propagation to data sources.

If you only place a timeout at the outer layer while dependencies do not support cancellation or continue running in the background, server resources can still be consumed after the client disconnects.

## 15. Context propagation when switching threads

Async execution can cause resolvers and related components to run on a different thread from the one that accepted the request. Spring for GraphQL supports propagating context from the transport through GraphQL Java:

- With Spring MVC, `ThreadLocal` values can be propagated via Micrometer Context Propagation once appropriate accessors are registered.
- With Spring WebFlux, reactive data fetchers can read the Reactor `Context` propagated from the request pipeline, including context added by `WebGraphQlInterceptor`.

In reactive pipelines, use Reactor Context or `GraphQLContext` to pass request-scoped data rather than storing state in mutable instance fields. If you switch threads manually, know which context is propagated and which requires explicit registration.

Do not assume every `ThreadLocal` is automatically present on every thread. If your application uses MDC, request attributes, or custom security context in async tasks, verify propagation under your actual configuration.

## 16. DataFetcherResult when metadata is needed

Normally a resolver only returns domain data. When you need to attach GraphQL errors, extensions, or local context to the result, you can return `DataFetcherResult<P>`.

Example:

```java
@QueryMapping
public DataFetcherResult<Book> bookById(@Argument String id) {
    Book book = bookService.findById(id);

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .localContext(Map.of("source", "catalog"))
            .build();
}
```

`DataFetcherResult` is GraphQL Java's full result type. Generic `P` can be a regular value or a supported async type such as `Mono`. Only use it when metadata or local context is genuinely needed; for normal resolvers, returning `T`, `Mono<T>`, or `Flux<T>` directly is simpler.

## 17. Testing async returns and errors

You can use `@GraphQlTest` and `GraphQlTester` to test resolvers returning `Mono`:

```java
@GraphQlTest(BookQueryController.class)
class BookAsyncQueryTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    ReactiveBookService bookService;

    @Test
    void returnsBookFromMono() {
        given(bookService.findById("book-1"))
                .willReturn(Mono.just(
                        new Book("book-1", "Spring GraphQL")));

        graphQlTester.document("""
                query {
                    bookById(id: "book-1") {
                        id
                        title
                    }
                }
                """)
                .execute()
                .path("bookById.title")
                .entity(String.class)
                .isEqualTo("Spring GraphQL");
    }
}
```

Testing errors:

```java
given(bookService.findById("missing"))
        .willReturn(Mono.error(
                new BookNotFoundException("missing")));
```

Then execute the query and verify the GraphQL response includes the field path and error classification configured by the advice. Also verify data according to schema nullability.

For reactive services, use Reactor Test and `StepVerifier` to test pipelines independently. `GraphQlTester` tests integration from the GraphQL document through resolvers to the response; these two test levels serve different purposes.

Scenarios worth testing:

- Mono emitting a value.
- Empty Mono for both nullable and non-null fields.
- Mono emitting an error.
- Query Flux aggregated into a list.
- Query Flux emitting an error mid-stream.
- Subscription publisher emitting multiple events and then emitting an error.
- Timeouts and cancellation.
- Context remaining present after thread switches or across reactive pipelines.

## 18. Common errors and diagnostics

| Symptom | Possible cause | Troubleshooting |
| --- | --- | --- |
| Resolver still blocks event loop | Calling blocking API or using `block()` in WebFlux | Use a reactive client or move blocking calls to an appropriate Executor |
| Empty Mono causes non-null error | SDL declares field non-null while resolver has no value | Adjust nullability or ensure domain always returns a value |
| Query Flux only returns after completion | Flux on regular fields is collected into a List | Use pagination for large lists; use Subscription if an event stream is needed |
| Subscription sends no events | Transport lacks streaming support or publisher emits no data | Check WebSocket/RSocket, subscription mapping, and event source |
| Async error not converted to business code | Missing appropriate exception resolver | Use `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver` |
| Subscription error bypasses regular resolvers | Error emitted after publisher was subscribed | Register a `SubscriptionExceptionResolver` |
| Parse error does not hit DataFetcherExceptionResolver | Request never reached data fetching stage | Handle in transport/interceptor if customization is needed |
| Entire parent object disappears from response | Failing field sits under a non-null branch | Review nullability and nullable boundaries in SDL |
| Timeout yet work keeps running | Dependency lacks cancellation support or code detached from reactive chain | Configure dependency timeouts and propagate cancellation |
| Request context disappears after thread switch | ThreadLocal not propagated or Reactor Context not preserved | Use proper context propagation and test across thread boundaries |
| CompletableFuture overloads common pool | Blocking tasks occupy common pool worker threads | Use a dedicated bounded Executor and manage its lifecycle |

When debugging, first determine whether the error occurred before or after the DataFetcher was called. Then identify what the resolver returns and whether the error is raised synchronously, via `CompletionStage`, via a Reactor signal, or after the Subscription started.

## 19. Principles for designing async returns and errors

- Use `Mono<T>` for asynchronous results with at most one value.
- Use `Flux<T>` for multiple values; remember Query Flux is typically collected into a List.
- Use `Flux<T>` in Subscriptions when continuous event emission is needed.
- Use `CompletionStage<T>` when integrating asynchronous Java APIs at the DataFetcher layer.
- Use `Callable<T>` for blocking work needing a configured Executor.
- Never call `block()` inside a reactive request pipeline.
- Never use the common pool for blocking work without evaluating load.
- Design nullability so a single field failure does not discard more data than necessary.
- Use `@GraphQlExceptionHandler` for exceptions from annotated controllers.
- Use `DataFetcherExceptionResolver` for other DataFetchers.
- Use `SubscriptionExceptionResolver` for errors from Subscription publishers.
- Use `WebGraphQlInterceptor` for request-level errors if customization is required.
- Never return stack traces or infrastructure details to clients.
- Configure timeouts and cancellation on both GraphQL requests and dependencies.
- Test partial responses, error paths, null propagation, and context propagation.

## 20. Practice exercise

Build a library API with asynchronous Queries and Subscriptions:

1. Create `ReactiveBookService` returning `Mono<Book>` for `findById`.
2. Write `@QueryMapping` returning `Mono<Book>` and verify results with `GraphQlTester`.
3. Create a method returning `Flux<Book>` for a list field and confirm the Query response is an aggregated list.
4. Create `BookEventService` emitting `Flux<Book>` and map it to `@SubscriptionMapping`.
5. Create `BookNotFoundException` and handle it with `@GraphQlExceptionHandler` using `ErrorType.NOT_FOUND`.
6. Add a manual DataFetcher and handle its errors via `DataFetcherExceptionResolver`.
7. Make the Subscription publisher emit an error after several events and configure `SubscriptionExceptionResolver`.
8. Add `TimeoutWebGraphQlInterceptor` and verify cancellation when a request times out.
9. Create one nullable field and one non-null field, then observe the difference in null propagation when resolvers emit errors.
10. Explain why request parse errors are not handled by `DataFetcherExceptionResolver`.

After the exercise, you should be able to distinguish async returns from streaming Subscriptions, choose among `Mono`/`Flux`/`CompletionStage`/`Callable`, and pick the right exception resolver for each error stage.

## 21. References

- [Spring for GraphQL — Request Execution, Thread Model, Reactive DataFetcher and Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers, Return Values and Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring Framework — WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)

Details of supported return types, virtual thread integration, and exception resolvers may vary across versions of Spring Boot, Spring for GraphQL, and GraphQL Java. When upgrading dependencies, check the reference documentation for the exact versions your project uses.
