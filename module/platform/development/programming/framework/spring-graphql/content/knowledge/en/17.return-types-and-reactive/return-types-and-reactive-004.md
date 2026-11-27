# CompletableFuture

In Spring for GraphQL, a resolver does not necessarily have to return data immediately at the moment it is called. An annotated controller method can return `CompletableFuture<T>` to represent a result that will complete in the future. GraphQL Java recognizes this asynchronous result, awaits the future's completion during operation execution, and then finishes building the response.

`CompletableFuture` is suitable when an application calls a remote service, an asynchronous database client, or needs to combine multiple independent tasks. It prevents the resolver from blocking the current thread to wait for results. However, creating a future with `supplyAsync` and running a blocking call on a thread pool is still blocking work; to achieve true non-blocking benefits, the data source should provide an asynchronous or reactive API.

## 1. What is CompletableFuture?

`CompletableFuture<T>` is an implementation of `Future<T>` and `CompletionStage<T>` in Java. It represents a result of type `T` that may complete later, either completing normally with a value or completing exceptionally with an exception.

Example:

```java
CompletableFuture<Book> future = bookClient.findById("book-01");
```

The call above returns a future immediately. When the remote client receives data, the future completes with a `Book`; if the request fails, the future completes exceptionally.

Common states:

| State | Meaning |
| --- | --- |
| Incomplete | The task has not completed yet |
| Completed normally | A result of type `T` is available |
| Completed exceptionally | The task ended with an exception |
| Cancelled | The future was cancelled per the task's cancellation mechanism |

`CompletableFuture` is not synonymous with a thread. A future can represent asynchronous I/O managed by an HTTP client or database driver without occupying a thread while waiting. Only when using `supplyAsync` does Java schedule a task on an executor to run the supplier.

## 2. Returning CompletableFuture from @QueryMapping

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

The service uses an asynchronous HTTP client and returns a future:

```java
@Service
public class BookService {

    private final BookClient bookClient;

    public BookService(BookClient bookClient) {
        this.bookClient = bookClient;
    }

    public CompletableFuture<Book> findByIdAsync(String id) {
        return bookClient.findById(id);
    }
}
```

The controller returns the future directly to Spring for GraphQL:

```java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public CompletableFuture<Book> bookById(@Argument("id") String id) {
        return bookService.findByIdAsync(id);
    }
}
```

Spring registers the controller method as a data fetcher. GraphQL Java receives `CompletableFuture<Book>` as an asynchronous result. When the future completes, the `Book` value is used to resolve child fields such as `id` and `title`.

You can use the same approach with `@SchemaMapping`:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(Book book) {
    return authorService.findByIdAsync(book.authorId());
}
```

The `Book.author` field only completes when the future returns `Author`. If the field is not selected in the selection set, the resolver does not need to be called.

## 3. Creating a CompletableFuture from blocking work

If an existing library only provides a synchronous API, you can isolate the blocking call using `CompletableFuture.supplyAsync` and a dedicated executor:

```java
@Service
public class BookService {

    private final BookRepository bookRepository;
    private final Executor graphqlExecutor;

    public BookService(
            BookRepository bookRepository,
            @Qualifier("graphqlExecutor") Executor graphqlExecutor) {
        this.bookRepository = bookRepository;
        this.graphqlExecutor = graphqlExecutor;
    }

    public CompletableFuture<Book> findByIdAsync(String id) {
        return CompletableFuture.supplyAsync(
            () -> bookRepository.findById(id).orElse(null),
            graphqlExecutor
        );
    }
}
```

You can declare the executor in Spring:

```java
@Configuration
public class GraphQlAsyncConfiguration {

    @Bean("graphqlExecutor")
    public ThreadPoolTaskExecutor graphqlExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("graphql-io-");
        return executor;
    }
}
```

The numbers above are only starting examples, not optimal settings for every application. Choose pool size and queue capacity according to dependency latency, concurrent requests, database connection limits, and external service capacity. Monitor queue depth, active threads, rejected tasks, and wait times to tune them.

Do not default to `ForkJoinPool.commonPool()` for all blocking I/O tasks. The common pool can be shared with other JVM tasks; a group of long-running blocking calls can exhaust threads and slow down unrelated parts. Use a bounded executor with a clear purpose for blocking work.

If an HTTP client or database driver already returns `CompletableFuture`, return that future directly. There is no need to wrap an async API in `supplyAsync` just to add another scheduling layer.

## 4. Combining multiple asynchronous steps

`CompletableFuture` provides combinators to build pipelines. Two commonly used methods are `thenApply` and `thenCompose`:

- `thenApply` transforms a completed value with a synchronous function and returns a future containing the new value.
- `thenCompose` invokes a function returning another future and flattens the result, avoiding `CompletableFuture<CompletableFuture<T>>`.

For example, fetching a book and then loading its author:

```java
public CompletableFuture<BookDetails> findDetails(String bookId) {
    return bookClient.findById(bookId)
        .thenCompose(book -> authorClient.findById(book.authorId())
            .thenApply(author -> new BookDetails(book, author)));
}
```

`bookClient.findById` returns `CompletableFuture<Book>`. Once the book arrives, `thenCompose` calls `authorClient.findById`, and then `thenApply` creates `BookDetails` from both results. If either future completes exceptionally, the pipeline also completes exceptionally unless the error is explicitly handled.

When two data sources are independent, you can start both and combine them with `thenCombine`:

```java
public CompletableFuture<Dashboard> loadDashboard(String customerId) {
    CompletableFuture<Customer> customerFuture =
        customerClient.findById(customerId);
    CompletableFuture<List<Order>> ordersFuture =
        orderClient.findRecentByCustomer(customerId);

    return customerFuture.thenCombine(
        ordersFuture,
        Dashboard::new
    );
}
```

Both requests are launched before combining. The resulting future completes when both required results are ready. If either future fails, the combined future also fails.

### When to use thenApply, thenCompose, and thenCombine?

| Method | Use case | Result type |
| --- | --- | --- |
| `thenApply` | Transform an already available value | `CompletableFuture<U>` |
| `thenCompose` | Next step itself returns a future | Flattened `CompletableFuture<U>` |
| `thenCombine` | Combine two independent futures | `CompletableFuture<R>` |
| `allOf` | Wait for multiple futures to complete without directly combining values | `CompletableFuture<Void>` |

`allOf` is useful when you need to wait for a group of tasks and then read results from each future. It does not collect values into a list by itself; the application must call `join()` on each future after `allOf` completes, or use a custom combining function.

## 5. Async callbacks and choosing an executor

Methods without the `Async` suffix, such as `thenApply`, may run the callback on the thread that completed the previous future or on the calling thread if the future is already complete. The variants `thenApplyAsync`, `thenComposeAsync`, and `thenCombineAsync` schedule callbacks asynchronously, typically on the common pool if no executor is passed.

Example specifying an executor:

```java
return bookClient.findById(bookId)
    .thenApplyAsync(this::toBookView, graphqlExecutor);
```

Choose an explicit executor when the callback performs CPU-intensive or blocking work. For very small callbacks that just convert an object, the non-`Async` variant is usually sufficient and avoids extra scheduling. Avoid calling `join()` or `get()` inside a callback to wait for another future; doing so can occupy threads, cause deadlocks, or lose asynchronous benefits. Use `thenCompose` to chain pipelines.

## 6. Multiple GraphQL fields and asynchronous execution

GraphQL Java can execute root query fields independently. If resolvers return futures, the engine can track those futures and complete the response once the requested fields have results. For example, an operation requests a book, an author, and a latest list; each resolver can call a separate asynchronous service.

This does not mean every Java method automatically runs on its own thread. A resolver returning a synchronous object still executes according to synchronous data fetcher behavior. A resolver returning a future already provided by an HTTP client may not occupy any thread waiting on I/O. A resolver using `supplyAsync` occupies a thread in the executor while the supplier runs.

Do not rely on the completion order of root query fields. If one operation needs to run after another, express the dependency within the same pipeline using `thenCompose`, or model data-modifying operations as mutations. Root fields of a mutation are executed sequentially by GraphQL; queries have no such ordering guarantee.

## 7. Exception handling in CompletableFuture

A future can complete exceptionally when a service throws an exception or a remote call fails. GraphQL Java converts data fetcher errors into GraphQL execution errors. Spring for GraphQL provides `DataFetcherExceptionResolver` to map exceptions into safe, API-appropriate errors.

There are three common callbacks:

| Method | Purpose |
| --- | --- |
| `whenComplete` | Observe result or error, commonly for logging/metrics; does not transform the result |
| `exceptionally` | Convert an error into a fallback value if a fallback is valid |
| `handle` | Process both result and error, and can produce a replacement value |

Example logging while preserving the original success or failure result:

```java
return bookClient.findById(id)
    .whenComplete((book, error) -> {
        if (error != null) {
            logger.warn("Could not load book {}", id, error);
        }
    });
```

Example using a fallback only when business logic permits:

```java
return recommendationClient.findForBook(id)
    .exceptionally(error -> List.of());
```

If the recommendation list can be treated as empty when the recommendation service temporarily fails, this fallback can be appropriate. Do not use `exceptionally(error -> null)` indiscriminately: it turns an error into null data and can mask failures or trigger null propagation if the field is non-null.

Exceptions thrown inside a pipeline are often wrapped in `CompletionException` or `ExecutionException`. When mapping errors, inspect the cause to identify business exceptions. Do not return stack traces or internal system details to clients.

If you need to convert exceptions into GraphQL errors with codes, you can implement `DataFetcherExceptionResolver` or `DataFetcherExceptionResolverAdapter`. The resolver should identify business error types, produce appropriate messages, and include error codes in `extensions`; unrecognized errors can be left to other resolvers or the default mechanism.

## 8. Timeout and fallback

Java provides `orTimeout` and `completeOnTimeout` to set time limits on a future:

```java
return bookClient.findById(id)
    .orTimeout(2, TimeUnit.SECONDS);
```

`orTimeout` completes the future exceptionally with `TimeoutException` if the deadline is exceeded. You can use `completeOnTimeout` when a fallback value makes sense:

```java
return recommendationClient.findForBook(id)
    .completeOnTimeout(List.of(), 1, TimeUnit.SECONDS);
```

Timing out a future does not guarantee the underlying I/O call has been cancelled. If an HTTP client, database driver, or background task is still running, it may continue consuming resources. Configure timeouts/cancellation on the client or dependency itself when supported. Also avoid placing a timeout on a future shared among multiple consumers if completing on timeout could affect all of those consumers.

Choose timeouts based on SLAs and actual dependency latency. Do not use an arbitrary number for every service. On timeout, distinguish retryable read operations from side-effecting commands that require idempotency.

## 9. Cancellation and request lifecycle

`CompletableFuture` has a `cancel` method, but cancelling a future does not automatically guarantee all underlying work stops. An already-sent HTTP request, a JDBC query, or a running task may continue if the client/driver does not support cancellation.

Do not assume that when a GraphQL client closes the connection, every future in the operation will definitely stop immediately. Check the cancellation behavior of the transport, GraphQL Java, and data sources in use. For resource-intensive tasks, design explicit deadlines, timeouts, and cancellation propagation; ensure cleanup operations do not leak or write partial data.

For mutations, cancelling a request after side effects have committed does not mean the side effects are rolled back. The client might miss the response and need to retry with the same idempotency key to retrieve the recorded result.

## 10. Context, security, and transactions when switching threads

An easily overlooked point is that `CompletableFuture` may run callbacks on a different thread. Many Spring or application contexts are stored using `ThreadLocal`, such as security context, MDC logging, locale, or transaction context. Do not assume these contexts automatically follow the future when work switches threads.

For request data needed inside an async task, pass required values explicitly, such as tenant ID, authenticated user ID, or correlation ID. If you need to propagate `SecurityContext` or MDC across an executor, configure an appropriate context propagation mechanism such as `TaskDecorator` or an executor wrapped using Spring Security's utilities.

Standard JDBC/JPA transactions are bound to a thread. If you open a transaction on the GraphQL handling thread and then offload querying to `supplyAsync` on another thread, the transaction and persistence context are not automatically shared. Do not pass managed entities or `EntityManager` across threads arbitrarily.

If an async task needs a transaction, have a service method invoked on the worker thread open its own transaction via a Spring proxy, or use a transaction model suitable for the data technology in use. A `@Transactional` method returning `CompletableFuture` does not automatically keep the transaction open until the future completes on another thread; transaction boundaries must be explicitly designed and tested.

## 11. CompletableFuture in @BatchMapping and DataLoader

Batch resolvers can also return asynchronous results. For example, `@BatchMapping` can return `CompletableFuture<Map<Book, Author>>` if loading the batch of authors happens asynchronously:

```java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public CompletableFuture<Map<Book, Author>> authors(List<Book> books) {
        Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        return authorService.findAllByIdsAsync(authorIds)
            .thenApply(authorsById -> {
                Map<Book, Author> result = new HashMap<>();
                for (Book book : books) {
                    result.put(book, authorsById.get(book.authorId()));
                }
                return result;
            });
    }
}
```

Spring for GraphQL integrates `@BatchMapping` with DataLoader to group source objects. Here, the future represents the result of the entire batch. Return a complete mapping keyed by source object and handle missing data according to field nullability.

If using DataLoader directly, `load(key)` typically returns a future for that key. The resolver can return this future to GraphQL Java instead of blocking with `join()`:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataFetchingEnvironment environment) {
    DataLoader<String, Author> loader =
        environment.getDataLoader("authorLoader");
    return loader.load(book.authorId());
}
```

Loaders must be registered under the right name and scoped per request, typically via `BatchLoaderRegistry` in Spring for GraphQL. Do not create a single application-wide shared DataLoader if caching could leak one request's or user's data to another request.

## 12. How does CompletableFuture differ from Mono and Flux?

`CompletableFuture<T>` represents a single result completing once. Reactor `Mono<T>` also represents at most one result, whereas `Flux<T>` represents a stream that can emit multiple elements over time.

| Type | Model | Commonly used for |
| --- | --- | --- |
| `CompletableFuture<T>` | One asynchronous result | HTTP call returning one object, background task completing once |
| `Mono<T>` | 0 or 1 reactive result | Reactive service returning one object or no data |
| `Flux<T>` | 0 to many reactive elements | Data lists/streams, subscription event streams |

A GraphQL subscription typically requires a publisher/`Flux` because it emits multiple events over the subscription's lifetime. `CompletableFuture` only represents a single result and therefore cannot replace a publisher for a continuous event stream.

Choose the return type that matches the application stack. There is no need to convert every API to `CompletableFuture` if services already use Reactor throughout; Spring for GraphQL supports reactive types. Avoid converting back and forth between futures and reactive types unnecessarily because it complicates cancellation, context, and error handling.

## 13. Testing resolvers returning CompletableFuture

`GraphQlTester` can test asynchronous resolvers just like synchronous ones. When calling `execute()`, the tester awaits operation completion using its built-in mechanism and then lets you assert paths in the response.

Example:

```java
graphQlTester.document("""
        query($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-01")
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring in Action");
```

You should also test these scenarios:

- Future completes normally with a valid object.
- Future completes normally with `null` for a nullable field.
- Future completes exceptionally and the exception is mapped to an appropriate GraphQL error.
- Future times out and the response contains an error matching the contract.
- Multiple root fields complete in different orders yet the response remains correct.
- `thenCompose` handles dependencies between tasks without calling `join()`.
- Required context/security remains present in callbacks running on another executor.
- Batch future returns accurate results for each source object.

To test a pipeline deterministically, you can use a test-controlled `CompletableFuture`: have a mock service return an incomplete future, then complete the future with a result or exception. This verifies the resolver does not block to fetch data and the response only completes after the future resolves.

## 14. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Resolver still blocks | Calling `join()` or `get()` right in the controller | Return the future directly and chain pipelines with `thenApply`/`thenCompose` |
| Thread pool exhaustion | Running many blocking tasks on the common pool or an unbounded pool | Use a bounded executor, monitor queue depth and processing time |
| Nested futures | Using `thenApply` for a function returning a future | Use `thenCompose` to flatten |
| Errors turned into null | Using `exceptionally(error -> null)` unintentionally | Let errors propagate to GraphQL or only use valid fallbacks |
| Missing SecurityContext in callback | Callback runs on another thread | Pass context explicitly or configure context propagation |
| Transaction does not cover async work | Thread-bound transaction ends before future completes | Open transaction in a service running on the worker thread or use a suitable model |
| Timeout yet dependency keeps running | Future timeout does not reliably cancel underlying I/O | Configure timeout/cancellation on the HTTP client or driver |
| Subscription emits only one result | Using `CompletableFuture` instead of a publisher | Use `Flux`/`Publisher` for event streams |
| Batch resolver returns incomplete data | Map does not match source objects or keys | Build a complete mapping and handle missing data cases |

## 15. Principles for using CompletableFuture

Return futures directly from services when dependencies already support async. Only use `supplyAsync` to isolate blocking work when no non-blocking API is available, and always choose an appropriately bounded executor. Use `thenApply` for synchronous transformations, `thenCompose` for dependent async steps, and `thenCombine` for independent tasks.

Let exceptions propagate to GraphQL's error handling mechanism if no valid fallback exists. Set timeouts on both the future and the dependency when needed, while understanding that cancellation does not automatically stop all I/O. When switching threads, pass necessary context explicitly and design transactions on the actual execution thread.

In Spring for GraphQL, `CompletableFuture` is a return type for resolvers to supply asynchronous results to GraphQL Java. It does not replace schemas, resolvers, or DataLoader; it represents when data becomes ready. Used properly, it reduces blocking wait time, allows combining independent dependencies, and keeps controller logic clean, while still requiring careful management of executors, errors, timeouts, and context.
