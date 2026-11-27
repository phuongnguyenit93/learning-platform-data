# Reactive DataFetcher

## Objectives

After this lesson, you will be able to:

- Explain how a GraphQL `DataFetcher` returns `Mono` or `Flux` in Spring for GraphQL.
- Distinguish GraphQL Java's asynchronous contract from Spring's Reactor support.
- Register a reactive DataFetcher directly with `RuntimeWiringConfigurer`.
- Understand how Spring converts reactive results into `CompletableFuture` for Queries and Mutations.
- Distinguish a `Flux` collected into a list in a Query from a publisher used for a Subscription.
- Handle empty publishers, errors, Reactor Context, and blocking calls.
- Integrate reactive repositories and test DataFetchers using `GraphQlTester`.

## 1. What is a reactive DataFetcher?

In GraphQL Java, a `DataFetcher` is the component that provides a value for a field in the schema. A DataFetcher can return a regular object or an asynchronous result such as a `CompletionStage`.

Spring for GraphQL extends this integration so DataFetchers can return Reactor `Mono` or `Flux`. The GraphQL runtime still executes operations asynchronously, while Spring handles converting the publisher into a form GraphQL Java understands.

For example, a field fetching a book by ID can return `Mono<Book>`:

~~~java
DataFetcher<Mono<Book>> bookFetcher =
        environment -> bookService.findById(
                environment.getArgument("id"));
~~~

A field fetching multiple books can return `Flux<Book>`:

~~~java
DataFetcher<Flux<Book>> booksFetcher =
        environment -> bookService.findAll();
~~~

The key point is that a reactive DataFetcher does not need to call `subscribe()` itself to trigger the publisher. The GraphQL runtime manages execution and receives results through Spring for GraphQL's integration mechanism.

## 2. How does Spring convert Mono and Flux?

The default `GraphQlSource` builder enables reactive DataFetcher support. Spring converts Reactor results according to the GraphQL operation type:

| DataFetcher result | Query or Mutation | Subscription |
|---|---|---|
| `Mono<T>` | Converted to `CompletableFuture<T>` | Publisher completes with one value or no value |
| `Flux<T>` | Elements collected into a List and converted to `CompletableFuture<List<T>>` | Publisher retained to emit events over time |
| `T` | Returned directly | May be an initial value depending on operation design |
| `CompletionStage<T>` | Handled asynchronously by GraphQL Java | Suitable for a single asynchronous result |

For Queries and Mutations, a `Flux<Book>` does not cause GraphQL responses to be sent multiple times. Spring collects the elements into a list to complete the operation's response.

Example SDL:

~~~graphql
type Query {
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
}
~~~

A DataFetcher returning `Flux<Book>` produces the data for the `books` field. The client receives a single response containing the list of books after the field completes.

For Subscriptions, the publisher is retained so GraphQL Java can process the event stream. This is an important difference between a list field in a Query and a stream of updates over time.

## 3. Registering a reactive DataFetcher with RuntimeWiringConfigurer

When working directly with GraphQL Java, you can create a DataFetcher returning `Mono` or `Flux` and register it in `RuntimeWiringConfigurer`.

SDL:

~~~graphql
type Query {
  book(id: ID!): Book
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
}
~~~

Service:

~~~java
public interface BookService {
    Mono<Book> findById(String id);
    Flux<Book> findFirst(int limit);
}
~~~

Configuration:

~~~java
@Configuration
public class ReactiveBookWiring {

    @Bean
    RuntimeWiringConfigurer reactiveBookFetchers(BookService bookService) {

        DataFetcher<Mono<Book>> bookFetcher = environment -> {
            String id = environment.getArgument("id");
            return bookService.findById(id);
        };

        DataFetcher<Flux<Book>> booksFetcher = environment -> {
            Integer first = environment.getArgument("first");
            int limit = first == null ? 20 : first;
            return bookService.findFirst(limit);
        };

        return builder -> builder.type("Query", typeBuilder ->
                typeBuilder
                        .dataFetcher("book", bookFetcher)
                        .dataFetcher("books", booksFetcher)
        );
    }
}
~~~

Points to note:

- The `DataFetcher` is still registered against the exact GraphQL type and field in SDL.
- `environment.getArgument(...)` retrieves arguments of the currently executing field.
- The service returns a publisher; the DataFetcher does not wait for the result itself.
- Spring Boot automatically detects `RuntimeWiringConfigurer` beans and includes them when building `GraphQlSource`.

Use constructor injection or bean method parameters to supply services to the configurer. Do not instantiate new repositories or services inside a DataFetcher.

## 4. Reactive return types in annotated controllers

If manual DataFetcher registration is unnecessary, you can use annotated controllers. Spring registers controller methods as DataFetchers and supports the same reactive return types.

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
}
~~~

Both styles share the goal of providing asynchronous data for fields:

- Use annotated controllers when you want Java methods and annotations to describe mappings directly.
- Use `RuntimeWiringConfigurer` when you need DataFetcher-level control in GraphQL Java or are integrating a component that builds DataFetchers for you.

Avoid registering both a controller mapping and a manual DataFetcher for the same field without clear intent. Having two places own a mapping can cause conflicts or make configuration harder to trace.

## 5. Combining multiple reactive data sources

A DataFetcher can coordinate multiple asynchronous services. Reactor provides operators to combine publishers without blocking threads.

For example, a book details page needs `Book` information and the review count:

~~~graphql
type Query {
  bookSummary(id: ID!): BookSummary
}

type BookSummary {
  book: Book!
  reviewCount: Int!
}
~~~

DataFetcher:

~~~java
DataFetcher<Mono<BookSummary>> summaryFetcher = environment -> {
    String id = environment.getArgument("id");

    Mono<Book> book = bookService.findById(id);
    Mono<Integer> reviewCount = reviewService.countByBookId(id);

    return Mono.zip(book, reviewCount)
            .map(tuple -> new BookSummary(
                    tuple.getT1(),
                    tuple.getT2()));
};
~~~

`Mono.zip` combines results once all input publishers have emitted values. Independent calls can progress asynchronously without writing nested callbacks.

If `bookService.findById` can return `Mono.empty()`, `Mono.zip` may also complete empty and produce no `BookSummary`. Define the behavior when `Book` is not found before combining:

~~~java
return bookService.findById(id)
        .switchIfEmpty(Mono.error(new BookNotFoundException(id)))
        .flatMap(book ->
                reviewService.countByBookId(id)
                        .map(count -> new BookSummary(book, count)));
~~~

Use `map` for synchronous value transformations; use `flatMap` when the next step returns a publisher. Avoid creating nested publishers such as `Mono<Mono<T>>` when a single processing chain is intended.

## 6. Handling empty Mono and GraphQL nullability

`Mono.empty()` represents the case where a publisher completes without emitting a value. When converted to a GraphQL result, this corresponds to a field having no value, typically represented as `null`.

The schema must allow that result if it is a normal case.

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

With a nullable field, not finding a book can return `null`. If the schema declares:

~~~graphql
type Query {
  book(id: ID!): Book!
}
~~~

then the resolver must not complete without a value. If the DataFetcher returns `Mono.empty()`, GraphQL creates an execution error and applies null propagation rules.

You can turn an empty publisher into a business error if the API requires the book to exist:

~~~java
return bookService.findById(id)
        .switchIfEmpty(Mono.error(
                new BookNotFoundException(id)));
~~~

For list fields:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

`Flux.empty()` produces an empty list, not null. This is a valid result because the list exists even though it has no elements.

Distinguish clearly:

- `Mono.empty()`: no value for a single field.
- `Flux.empty()`: a list with zero elements in a Query.
- `Mono.error(...)` or `Flux.error(...)`: the publisher terminates with an error.

## 7. Handling errors from reactive DataFetchers

Errors can arise when accessing a database, calling an external service, or transforming data. Errors in a reactive pipeline are delivered to the GraphQL runtime when the publisher emits an error signal.

Example converting a technical error into a business exception:

~~~java
DataFetcher<Mono<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");

    return bookService.findById(id)
            .onErrorMap(
                    DataAccessException.class,
                    ex -> new BookLookupException(
                            "Unable to load book " + id, ex)
            );
};
~~~

Spring for GraphQL can use `DataFetcherExceptionResolver` to convert exceptions into appropriate GraphQL errors:

~~~java
@Component
public class BookExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Book was not found")
                    .errorType(ErrorType.NOT_FOUND)
                    .build();
        }

        return null;
    }
}
~~~

The example resolver above only handles recognized error types; it returns `null` for others so subsequent handlers can apply. Do not expose SQL, stack traces, or sensitive details in public messages.

Key principles:

- Use `onErrorMap` when you need to change the exception type.
- Use `onErrorResume` when there is a valid replacement result.
- Do not convert every error into `Mono.empty()`, as doing so hides failures.
- Keep missing data, business rule violations, and infrastructure failures distinct.
- Check field nullability to understand how errors propagate up the response.

## 8. Distinguishing Flux in a Query from Flux in a Subscription

Spring for GraphQL handles `Flux` differently depending on the operation type being executed.

Query fetching a list:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

~~~java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
~~~

The Flux elements are collected into a list to produce a single GraphQL response for the Query. The client does not receive each book as a separate response.

Subscription receiving events:

~~~graphql
type Subscription {
  bookAdded: Book!
}
~~~

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded() {
    return bookEventPublisher.events();
}
~~~

For a Subscription, `Flux` is a publisher emitting multiple events over time. GraphQL Java executes the selected fields for each event and emits the corresponding subscription results.

| Criterion | Flux in a Query | Flux in a Subscription |
|---|---|---|
| Meaning | Elements of a list field | Event stream over time |
| Spring handling | Aggregated into a List | Retained as a Reactive Streams Publisher |
| Number of GraphQL responses | One response for the operation | Multiple responses/events |
| Completion | When the publisher completes | When the publisher completes or the subscription is cancelled |
| Example | List of books | Notification when a new book arrives |

If you need to preserve original event ordering when events execute asynchronously, GraphQL Java provides the `SubscriptionExecutionStrategy.KEEP_SUBSCRIPTION_EVENTS_ORDERED` option in `GraphQLContext`. When enabled, GraphQL Java may buffer events to preserve order; weigh latency and memory impact before applying it.

## 9. Reactive Context in DataFetchers

With WebFlux, Spring for GraphQL supports propagating Reactor Context from the request-processing chain into reactive DataFetchers. This allows publishers to access metadata established at the transport layer or in a `WebGraphQlInterceptor`.

Example using Reactor Context in a service:

~~~java
public Mono<Book> findForCurrentTenant(String id) {
    return Mono.deferContextual(contextView -> {
        String tenantId = contextView.get("tenantId");
        return repository.findByIdAndTenantId(id, tenantId);
    });
}
~~~

A DataFetcher can call this service as usual:

~~~java
DataFetcher<Mono<Book>> bookFetcher =
        environment -> bookService.findForCurrentTenant(
                environment.getArgument("id"));
~~~

Reactor Context fits metadata that needs to flow along the reactive chain. It differs from source objects and GraphQL field arguments:

| Data | Scope | Example |
|---|---|---|
| Source object | Current parent field | `Book` returned from a Query |
| Argument | Currently executing field | ID sent by client |
| GraphQLContext | One GraphQL request | Shared request metadata |
| Reactor Context | Reactive chain | Tenant, tracing, or security metadata propagated through the pipeline |

Do not store the current user or tenant in a mutable field on a singleton DataFetcher. Concurrent requests can overwrite each other's data. Use appropriately scoped context and only trust metadata populated by a trusted authentication layer.

## 10. Avoiding blocking in reactive DataFetchers

A DataFetcher returning `Mono` does not automatically make the work inside non-blocking. If the publisher calls a synchronous JPA repository directly, the thread remains held while the database call runs.

Avoid writing:

~~~java
DataFetcher<Mono<Book>> bookFetcher = environment ->
        Mono.just(jpaRepository.findById(
                environment.getArgument("id")).orElse(null));
~~~

The JPA call already ran before `Mono.just` was created. It is still blocking.

If you temporarily need to integrate a blocking API, defer the call with `Mono.fromCallable` and offload it to the bounded elastic scheduler:

~~~java
DataFetcher<Mono<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");

    return Mono.fromCallable(() ->
                    jpaRepository.findById(id).orElse(null))
            .subscribeOn(Schedulers.boundedElastic());
};
~~~

This isolates the blocking call from event-loop threads, though it does not make JPA reactive. A bounded elastic thread is still occupied while accessing the database.

Whenever possible, use a reactive driver or client suited to your system, such as R2DBC for supported databases. Do not use `Schedulers.parallel()` for blocking tasks, and do not treat bounded elastic as an unlimited resource.

## 11. Reactive Spring Data DataFetchers

Spring for GraphQL includes integrations to build DataFetchers from Spring Data repositories. With reactive repositories, builders can create DataFetchers returning `Mono` or `Flux`.

Example with Querydsl:

~~~java
DataFetcher<Mono<Account>> accountFetcher =
        QuerydslDataFetcher.builder(reactiveRepository).single();

DataFetcher<Flux<Account>> accountsFetcher =
        QuerydslDataFetcher.builder(reactiveRepository).many();
~~~

The repository must implement the appropriate reactive Querydsl executor, such as `ReactiveQuerydslPredicateExecutor`. Similarly, Query by Example can create reactive DataFetchers when the repository supports `ReactiveQueryByExampleExecutor`.

These DataFetchers can be registered via `RuntimeWiringConfigurer`:

~~~java
@Bean
RuntimeWiringConfigurer accountFetchers(
        DataFetcher<Mono<Account>> accountFetcher,
        DataFetcher<Flux<Account>> accountsFetcher) {

    return builder -> builder.type("Query", typeBuilder ->
            typeBuilder
                    .dataFetcher("account", accountFetcher)
                    .dataFetcher("accounts", accountsFetcher)
    );
}
~~~

This illustrates how to structure wiring; DataFetcher beans should be created from the application's actual repositories and builders. Before using them, verify whether your Spring Data module, database type, and repository interface support reactive Querydsl or Query by Example.

Not every Spring Data module provides reactive repositories for all features. If a repository only supports blocking access, the builder cannot automatically turn blocking access into reactive access.

## 12. Limiting results and resources

Reactive publishers can emit large numbers of elements. For a Query, Spring must collect a `Flux` into a list to finish the response, so an unbounded Flux can inflate memory usage and processing time.

Enforce limits right in the schema and DataFetcher:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}
~~~

~~~java
DataFetcher<Flux<Book>> booksFetcher = environment -> {
    Integer first = environment.getArgument("first");
    int limit = first == null ? 20 : first;

    if (limit < 1 || limit > 100) {
        return Flux.error(
                new IllegalArgumentException(
                        "first must be between 1 and 100"));
    }

    return bookService.findFirst(limit);
};
~~~

For large datasets, use cursor pagination or connection types instead of loading an entire collection. Consider:

- Limiting the maximum number of elements.
- Setting timeouts for downstream calls.
- Bounding concurrency when calling multiple services.
- Using batch loading to prevent N+1.
- Monitoring DataFetcher duration and returned element counts.
- Cancelling publishers when requests or subscriptions are cancelled.

Backpressure helps with reactive streams, yet Queries still need to collect results to build a complete response. Business limits and pagination remain essential.

## 13. Testing reactive DataFetchers

You can test DataFetchers directly or through the GraphQL runtime. Integration tests via `GraphQlTester` verify SDL, wiring, reactive adaptation, and responses together.

Example:

~~~java
@Test
void shouldResolveBookFromReactiveDataFetcher() {
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

Cases worth testing:

1. `Mono` emits one value and the field returns the expected object.
2. `Mono.empty()` with a nullable field.
3. `Mono.empty()` with a non-null field.
4. `Flux` emits multiple elements and the Query returns an ordered list.
5. `Flux.empty()` produces an empty list for a non-null list field.
6. Publisher emits an error and the exception resolver produces an appropriate GraphQL error.
7. Reactor Context is propagated to the DataFetcher when running over WebFlux.
8. Subscription emits multiple events and completes cleanly on lifecycle end.
9. Publisher is cancelled when the client cancels the subscription.
10. Pagination limits reject out-of-range values.

Do not call `subscribe()` manually in tests to trigger a DataFetcher. Let the GraphQL runtime and `GraphQlTester` execute the operation, then assert data and errors.

## 14. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Field returns a Mono object instead of data | Reactive adaptation is not configured in `GraphQlSource` | Use Spring for GraphQL's default builder |
| List query only returns a single response | This is normal request-response behavior | Use Subscription if an event stream is needed |
| Query Flux consumes too much memory | Flux emits too many elements and gets aggregated into a List | Add limits and pagination |
| Field unexpectedly returns null | `Mono.empty()` or service found no data | Check nullability and `switchIfEmpty` |
| Errors turned into null | Inappropriate `onErrorResume` returning `Mono.empty()` | Keep errors and handle them via exception resolvers |
| Subscription events arrive out of order | Events and fields execute asynchronously | Consider GraphQL Java's ordering option |
| Event loop blocked | Calling blocking APIs directly inside the publisher | Use reactive clients or isolate blocking calls |
| Tenants/users mixed across requests | Storing metadata in shared mutable state | Use properly scoped Reactor Context or GraphQLContext |

## 15. Principles for designing reactive DataFetchers

When implementing reactive DataFetchers:

- Return `Mono` for single fields and `Flux` for list fields or appropriate subscriptions.
- Use the default `GraphQlSource` builder to enable reactive adaptation.
- Never call `block()` or `subscribe()` inside a DataFetcher.
- Combine publishers using `map`, `flatMap`, and `zip` matching the data types.
- Design nullability compatible with `Mono.empty()` and empty list results.
- Handle errors explicitly with Reactor operators and `DataFetcherExceptionResolver`.
- Never call blocking APIs directly on event-loop threads.
- Use Reactor Context for metadata flowing along the reactive chain.
- Bound Query results and use pagination.
- Use reactive repositories when the data source supports them.
- Test Queries, Subscriptions, empty cases, errors, and cancellation.

## Conclusion

Spring for GraphQL supports DataFetchers returning `Mono` and `Flux` through `GraphQlSource`'s reactive adaptation. For Queries and Mutations, publishers are converted into `CompletableFuture`; Flux values are collected into a `List`. For Subscriptions, the publisher is preserved to emit multiple GraphQL responses over time.

You can register reactive DataFetchers directly with `RuntimeWiringConfigurer` or use annotated controllers. Whichever approach you choose, keep the pipeline non-blocking, handle empty and error signals according to nullability, pass context in the right scope, and bound aggregated data. These practices let the GraphQL runtime leverage the reactive stack while keeping responses, errors, and operation lifecycles predictable.

## References

- [Spring for GraphQL — Reactive DataFetcher and Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers and Return Values](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Reactive Data Integration](https://docs.spring.io/spring-graphql/reference/data.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [GraphQL Java — DataFetcher API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetcher.html)
