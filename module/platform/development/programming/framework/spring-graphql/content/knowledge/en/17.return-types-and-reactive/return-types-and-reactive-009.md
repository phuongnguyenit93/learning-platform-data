# Blocking Methods in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Distinguish synchronous methods from blocking I/O operations.
- Understand how the resolver execution thread has to wait when a method calls external resources.
- Write `@QueryMapping` and `@SchemaMapping` returning regular Java values.
- Identify operational differences between Spring MVC and Spring WebFlux.
- Assess the risks of calling JPA/JDBC, synchronous HTTP clients, or the filesystem inside resolvers.
- Choose between synchronous values, `CompletableFuture`, and reactive return types.
- Offload blocking work away from the event loop when using WebFlux.
- Configure timeouts, bound concurrency, and monitor thread pools.
- Recognize the impact of thread switching on transactions, security context, and tracing.
- Test and observe the performance of blocking resolvers.

## 1. What is a blocking method?

An annotated controller method can return a regular Java value:

~~~java
@Controller
class BookQueryController {

    private final BookService bookService;

    BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") UUID id) {
        return bookService.findById(id);
    }
}
~~~

The `book` method is called synchronously. GraphQL invokes the method, waits for it to return `Book`, and then uses that value to continue processing the selection set.

Returning a synchronous object does not by itself mean the method always performs blocking I/O. If the method only computes in memory or reads an existing property, it can complete very quickly. A method becomes blocking in an operational sense when it must wait for an incomplete operation, such as:

- Querying a database via JDBC or JPA.
- Making an HTTP call with a synchronous client.
- Reading a file or accessing the filesystem.
- Waiting for a lock, semaphore, or shared resource.
- Calling a third-party library with a synchronous API and waiting for the result.

Example:

~~~java
@QueryMapping
public Book book(@Argument("id") UUID id) {
    // findById may wait for the database to return a result.
    return bookRepository.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

While the repository waits on the database, the thread running the resolver cannot be used for other work. This is an important characteristic to consider when choosing blocking methods.

## 2. Lifecycle of a blocking resolver

GraphQL executes an operation according to the selection set. For a synchronous field, the resolver is invoked and GraphQL needs that field's result before completing dependent steps.

The basic flow can be visualized as:

~~~mermaid
flowchart TD
    A["HTTP request /graphql"] --> B["Spring GraphQL transport"]
    B --> C["GraphQL execution"]
    C --> D["Invoke synchronous resolver"]
    D --> E["Blocking call: JDBC / JPA / HTTP"]
    E --> F["Thread waits for result"]
    F --> G["Resolver returns Java value"]
    G --> H["Resolve selected fields and build response"]
    H --> I["HTTP response"]
~~~

Example operation:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

If `Query.book` calls a synchronous JPA repository, the resolver only returns after the database operation completes. GraphQL then proceeds to read `id` and `title` from the `Book` object.

For nested fields, the same principle applies to each resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorRepository.findById(book.getAuthorId())
            .orElse(null);
}
~~~

If a query fetches many books and each resolution of `Book.author` waits on a separate query, total wait time and thread usage can grow rapidly. In that case, consider batch loading, DataLoader, or appropriate relationship fetching.

## 3. Distinguishing synchronous return from blocking I/O

These two concepts are related but not identical:

- **Synchronous return:** the method returns the result directly, rather than returning an asynchronous handle such as `Mono`, `Flux`, or `CompletableFuture`.
- **Blocking I/O:** the thread must wait for an I/O or resource operation to complete before continuing.

Example that is synchronous with negligible wait time:

~~~java
@SchemaMapping(typeName = "Book", field = "displayLabel")
public String displayLabel(Book book) {
    return book.getTitle() + " (" + book.getId() + ")";
}
~~~

Example that is synchronous and potentially blocking:

~~~java
@QueryMapping
public List<Book> books() {
    return bookRepository.findAll();
}
~~~

The second method may wait on the database. The first method mainly computes from already available data.

| Characteristic | Synchronous, in-memory processing | Synchronous, blocking I/O |
| --- | --- | --- |
| Return type | Regular Java value | Regular Java value |
| Waits on external resource | Usually no | May occur |
| Thread during method execution | Performs computation | May be held while waiting |
| Example | String concatenation, property calculation | JPA, JDBC, synchronous HTTP client |
| Main risk | CPU if calculation is too heavy | Thread occupation, pool exhaustion under load |

Therefore, there is no need to convert every synchronous method to reactive. Determine what the method actually does and what kind of thread it runs on.

## 4. Blocking methods with Spring MVC

In a Spring MVC application, requests are typically handled on servlet threads. A synchronous resolver can run on the execution thread handling the request/field. Example using JPA:

~~~java
@Controller
class BookQueryController {

    private final BookRepository bookRepository;

    BookQueryController(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @QueryMapping
    public Book book(@Argument("id") UUID id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

This is straightforward and fits many servlet applications using JPA. During the database query, the thread serving that work must wait.

Risks appear when wait times grow long or concurrent requests increase:

- Many servlet threads are held waiting on the database.
- The thread pool can run out of threads ready to accept new requests.
- New requests must wait in a queue or are rejected per server configuration.
- The database connection pool can also become a bottleneck.
- A GraphQL query with many blocking nested resolvers can trigger multiple I/O waits.

Using Spring MVC does not mean blocking is always safe. Bound query durations, and size thread pools and connection pools to match expected load.

## 5. Blocking methods with Spring WebFlux

Spring WebFlux is designed around a non-blocking, event-loop model. An event-loop thread needs to handle many short tasks, so it should not be held for long by JPA/JDBC or synchronous HTTP clients.

Example to avoid on the WebFlux execution path:

~~~java
@Controller
class BookQueryController {

    private final BookRepository bookRepository;

    BookQueryController(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @QueryMapping
    public Book book(@Argument("id") UUID id) {
        // If running on the event loop, a blocking JPA call
        // can hold this thread while waiting for the database.
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Do not assume Spring GraphQL automatically moves every synchronous method to a dedicated worker thread. A synchronous method body runs on the thread that calls it; the actual thread depends on the transport and execution configuration. With WebFlux, design so blocking work does not run on the event loop.

If the project uses reactive database drivers and reactive services, return reactive types so threads are not held while waiting on I/O. If using a blocking library is unavoidable, offload that operation to a dedicated scheduler or executor.

## 6. Using reactive return types with non-blocking data sources

If repositories and services already support reactive execution, the controller can return `Mono` or `Flux`.

Example with a reactive repository:

~~~java
@Controller
class BookReactiveQueryController {

    private final ReactiveBookRepository bookRepository;

    BookReactiveQueryController(ReactiveBookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @QueryMapping
    public Mono<Book> book(@Argument("id") UUID id) {
        return bookRepository.findById(id);
    }

    @QueryMapping
    public Flux<Book> books() {
        return bookRepository.findAll();
    }
}
~~~

In this example, the repository returns publishers. The controller does not call `block()` to wait for results. Spring for GraphQL integrates reactive return values into GraphQL execution.

For a regular Query, `Mono<Book>` represents a single result or no result. A `Flux<Book>` returned from a Query field is collected into a list for that field's response; it does not turn the Query into a multi-response stream. For subscriptions, publishers serve a special role emitting multiple responses over time; do not confuse a Query `Flux` with a GraphQL subscription.

Reactive return types only achieve non-blocking behavior if the underlying processing is also non-blocking. Wrapping a synchronous JPA call inside `Mono` without offloading it can still block the thread invoking the publisher.

## 7. Offloading blocking libraries with boundedElastic

When a WebFlux application must continue using JPA or a blocking library, you can create a publisher from a callable and shift execution to `Schedulers.boundedElastic()`:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
class BookQueryController {

    private final BookRepository bookRepository;

    BookQueryController(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @QueryMapping
    public Mono<Book> book(@Argument("id") UUID id) {
        return Mono.fromCallable(() ->
                    bookRepository.findById(id)
                            .orElseThrow(() -> new BookNotFoundException(id))
                )
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Steps:

1. `Mono.fromCallable` creates a publisher from a synchronous operation.
2. The callable does not run merely because the publisher was created.
3. `subscribeOn` specifies the scheduler to run the operation when the publisher is subscribed to.
4. `boundedElastic` provides a thread pool better suited for bounded blocking work.
5. When the callable finishes, `Mono` emits the value or error for GraphQL to continue processing.

Do not call `block()` inside the resolver. The following pattern loses the benefit of returning a publisher and can hold the current thread:

~~~java
@QueryMapping
public Book book(@Argument("id") UUID id) {
    return Mono.fromCallable(() -> bookRepository.findById(id).orElseThrow())
            .subscribeOn(Schedulers.boundedElastic())
            .block();
}
~~~

`boundedElastic` has resource and queue limits; it is not infinite capacity for running every query. For heavy blocking workloads or when explicit isolation is needed, configure a dedicated scheduler with appropriate concurrency limits and monitor its usage.

## 8. Offloading with CompletableFuture and Executor

Another option is returning `CompletableFuture`. Spring for GraphQL supports this asynchronous return type in annotated controllers.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Qualifier;

@Controller
class BookAsyncQueryController {

    private final BookService bookService;
    private final Executor graphqlExecutor;

    BookAsyncQueryController(
            BookService bookService,
            @Qualifier("graphqlExecutor") Executor graphqlExecutor) {
        this.bookService = bookService;
        this.graphqlExecutor = graphqlExecutor;
    }

    @QueryMapping
    public CompletableFuture<Book> book(@Argument("id") UUID id) {
        return CompletableFuture.supplyAsync(
                () -> bookService.findById(id),
                graphqlExecutor
        );
    }
}
~~~

The executor should be configured with bounded threads and queue capacity. Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class GraphQlExecutorConfiguration {

    @Bean("graphqlExecutor")
    Executor graphqlExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("graphql-blocking-");
        return executor;
    }
}
~~~

Spring manages initialization and shutdown lifecycle of the executor bean. These numbers are only illustrative examples, not optimal values for every system. Adjust them according to I/O duration, concurrent requests, connection pools, and resource limits of the deployment environment.

Avoid calling `CompletableFuture.supplyAsync` without passing an executor for important blocking tasks. Otherwise, tasks may run on the shared common `ForkJoinPool`, making load hard to control and affecting other work.

## 9. Do not switch threads casually

Moving blocking work to another thread can free the event loop, but it also alters several assumptions in the application.

### 9.1. Transaction context

In imperative applications using Spring transaction management, transactions are typically bound to the executing thread. If you start a transaction and then offload processing to another executor, do not assume the original transaction automatically follows.

Place transaction boundaries on the service method invoked on the worker thread executing business logic, or use transaction management matching the execution model. With reactive transactions, context is managed via Reactor Context rather than relying on traditional thread-locals.

Do not open a transaction on one thread and return a `CompletableFuture` for another thread to continue database operations inside that transaction without a clear design.

### 9.2. Security context and request context

Security context, tracing context, and request information may rely on context propagation mechanisms. When switching threads, do not assume `ThreadLocal` values are automatically copied.

If a task needs a principal, tenant, or correlation ID, pass the needed data explicitly or configure appropriate context propagation. Avoid storing mutable request objects in fields of a singleton controller.

### 9.3. Singleton controllers and shared state

Spring controllers are normally singletons. Do not store source objects, arguments, or request results in mutable instance fields:

~~~java
// Do not do this: one request can overwrite another request's state.
private UUID currentBookId;
~~~

Keep request data in method parameters, local variables, or framework-managed request context.

## 10. Timeouts and resource limits

A blocking call can wait a long time if a database, HTTP service, or filesystem runs into trouble. Without timeouts, threads can be held far longer than expected.

Configure timeouts at the right layers:

- **Database:** query timeout, transaction timeout, and connection acquisition timeout.
- **HTTP client:** connect timeout, response/read timeout, and connection pool limits.
- **Executor:** thread limits, queue capacity, and overload rejection policy.
- **Application:** request deadline or timeout aligned with the API's SLA.
- **GraphQL operation:** complexity limits, field count limits, or selection set size limits where appropriate for the system.

A timeout on the GraphQL request does not necessarily stop an already-blocking JDBC or HTTP call. The underlying task needs its own timeout. Similarly, cancelling a `CompletableFuture` does not guarantee the I/O library stopped working or the database cancelled the statement.

Do not grow thread pools indefinitely to mask slow downstreams. Find the bottleneck, set limits, and apply backpressure or load shedding when the system exceeds serving capacity.

## 11. Blocking nested resolvers and N+1

GraphQL can invoke nested resolvers many times within a single operation. A blocking method on a nested field multiplies wait cost by the number of source objects.

Example:

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

If `Query.books` returns 100 books and each resolution of `Book.author` runs a JPA query, the system may execute 100 separate author queries. Each query can hold a thread while waiting on the database.

You can batch data loading using `@BatchMapping`:

~~~java
@Controller
class BookBatchController {

    private final AuthorService authorService;

    BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsByBooks(books);
    }
}
~~~

The service can query by a set of `authorId`s and return a matching map. This reduces I/O calls and total thread-hold time. DataLoader can also be used to batch keys and cache within the request scope.

Batching does not by itself make queries non-blocking. If the batch service still uses synchronous JPA, it remains a blocking call, though the number of database calls can be substantially lower. If running on WebFlux, still offload the batch call or use reactive data access.

## 12. Error handling from blocking methods

A blocking resolver can throw an exception directly:

~~~java
@QueryMapping
public Book book(@Argument("id") UUID id) {
    return bookRepository.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Exceptions raised during field resolution pass through the application's GraphQL error handling mechanism, such as `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler`.

If the resolver returns `CompletableFuture`, exceptions may appear as exceptional completions. With `Mono`, errors are emitted as error signals. Regardless of return type, the application must map business and infrastructure errors consistently.

GraphQL can return partial data if one field fails while other fields succeed. If the failing field is non-null, the error can propagate to parent fields according to null propagation rules. Do not catch all exceptions and return `null` to hide database or system failures.

## 13. Observing performance of blocking resolvers

To know whether blocking methods are causing problems, observe both GraphQL and the underlying infrastructure.

| Group | Metrics to monitor |
| --- | --- |
| Resolver | Execution duration per field, invocation count, and error rate |
| Servlet/executor | Active threads, waiting threads, queue depth, and rejected tasks |
| WebFlux | Blocked event loops, event-loop latency, and blocking warnings |
| Database | Query latency, active connections, pending acquisitions, and timeouts |
| HTTP client | Connection pool usage, pending requests, and response latency |
| GraphQL | Operation duration, resolved field count, and errors by path |

Record operation names, field paths, or correlation IDs when possible. Avoid logging raw variables or payloads containing personal data, tokens, or secrets.

If operation duration is high, break down resolver time, database time, and downstream HTTP time to identify where time is actually spent waiting. Increasing a thread pool before understanding the root cause can increase pressure on the database without improving throughput.

## 14. Testing blocking resolvers

You can use `GraphQlTester` to test synchronous operations:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

For resolvers calling repositories, you can mock the service or repository and verify the exact number of calls. For nested fields, check invocation counts to catch N+1 issues in tests with multiple source objects.

Scenarios worth testing:

- Method returning an object directly.
- Blocking service throwing an exception and the error mapping properly.
- Database or HTTP timeout producing an appropriate error response.
- Asynchronous resolver completing successfully and propagating errors properly.
- Blocking call offloaded away from the event loop in a WebFlux setup.
- Batch resolver reducing the number of repository calls.
- Non-null field error triggering null propagation as expected by the schema.

Unit tests can verify method logic. Integration tests via `GraphQlTester` verify schema, mapping, and GraphQL responses. To verify event loops, thread pools, or timeouts, test at an integration level matching the deployed transport and runtime.

## 15. Choosing blocking or asynchronous/reactive?

Not every application needs to be reactive. Choose based on stack and I/O characteristics:

| Scenario | Recommended approach |
| --- | --- |
| Existing Spring MVC using JPA under controlled load | Synchronous resolver may be appropriate |
| Resolver only computes from already-loaded data | Return Java value directly |
| Spring WebFlux with R2DBC or reactive HTTP client | Return `Mono`/`Flux`, do not block |
| WebFlux forced to call JPA/JDBC | Offload with bounded scheduler or bounded executor |
| Blocking task needing a dedicated executor | Return `CompletableFuture` using a configured executor |
| Nested resolver causing N+1 | Use `@BatchMapping` or DataLoader |
| CPU-heavy work | Use an executor suited for CPU workloads, do not default to boundedElastic |

Practical rules:

- Do not convert a method to reactive just to change its return type if everything underneath remains blocking.
- Never call `block()` inside a WebFlux resolver.
- Never use the event loop to wait on JPA/JDBC or synchronous HTTP clients.
- Never use unbounded thread pools.
- Set timeouts for downstream I/O.
- Measure performance before and after changing execution models.

## 16. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| WebFlux slows down under load | Synchronous resolver calling JPA/JDBC on an inappropriate thread | Use reactive data access or offload blocking calls |
| Changed `Book` to `Mono<Book>` yet still blocks | Calling `block()` or executing I/O before creating the publisher | Defer the call inside the publisher and offload to the right scheduler |
| Thread pool exhausted | Slow I/O, high concurrency, or pool lacks proper bounds | Set timeouts, bound queues, and inspect downstream services |
| `CompletableFuture` causes uncontrolled load | Using common pool or unbounded executor | Pass a dedicated bounded executor |
| Transaction no longer active after switching threads | Relying on thread-local transaction on the original thread | Place transaction on the service invoked on the worker thread |
| Security context lost | Switching threads without propagating context | Configure context propagation or pass required data explicitly |
| GraphQL query incurs many database waits | Nested resolver causing N+1 | Use `@BatchMapping` or DataLoader |
| Request cancelled yet I/O keeps running | Cancelling a future does not stop blocking libraries | Configure timeouts and cancellation at client/database layers |
| Unknown which resolver causes slowness | Only measuring total request time | Measure duration by field, database, and downstream |

## 17. Workflow for implementing blocking resolvers

When writing a resolver that may perform I/O, follow this sequence:

1. **Identify the type of work.** Does the method only compute in memory or must it wait on I/O?
2. **Identify the transport/runtime.** Does the application use Spring MVC or Spring WebFlux?
3. **Choose the return type.** Use Java values for synchronous processing, reactive types for non-blocking sources, or futures when an executor is needed.
4. **Check the execution thread.** Do not assume the framework automatically offloads synchronous methods.
5. **Offload if needed.** With WebFlux and blocking libraries, use a bounded scheduler or bounded executor.
6. **Set timeouts.** Configure them on the database, HTTP client, and executor.
7. **Review transactions and context.** Verify transactions, security, and tracing across thread switches.
8. **Check for N+1.** Use batch loading if nested resolvers repeat I/O per source.
9. **Test errors and load.** Include timeouts, exceptional completions, pool saturation, and null propagation.
10. **Monitor production.** Measure resolver latency, thread pools, and downstream resources before tuning settings.

## 18. Summary

A blocking method is a synchronous method whose execution thread must wait for an external operation such as JPA/JDBC, an HTTP client, or the filesystem to complete. Spring for GraphQL supports resolvers returning Java values directly; this generally fits Spring MVC applications using blocking libraries when load and I/O duration are under control.

With Spring WebFlux, do not let blocking operations hold the event loop. Prefer reactive data access and return `Mono`/`Flux`; if using blocking libraries is unavoidable, offload to a bounded scheduler or bounded executor and never call `block()` inside a resolver. Switching threads also affects transactions, security context, and tracing, so design explicitly. Combining timeouts, batch loading, testing, and thread pool observability keeps resolvers stable as load grows.
