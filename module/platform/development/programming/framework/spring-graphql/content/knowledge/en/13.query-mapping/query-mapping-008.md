# Blocking Queries in Spring for GraphQL

In Spring for GraphQL, a `@QueryMapping` method can return an object directly after calling a repository or service. This style is straightforward, but if the internal call uses a synchronous API such as JDBC, JPA, or `RestTemplate`, the call will **block the current thread** until the I/O completes.

Blocking is not an inherent property of GraphQL Queries. It comes from how the DataFetcher performs its work. When an application uses Spring MVC, synchronous handling typically runs on the servlet request thread. When using Spring WebFlux, blocking I/O on the event loop can stall many other requests. Therefore, understand the web stack, I/O type, and executor setup before choosing how to implement a Query.

## What Does a Blocking Query Look Like?

Suppose a schema has a product lookup field:

```graphql
type Product {
  id: ID!
  name: String!
  price: Float!
}

type Query {
  product(id: ID!): Product
}
```

The controller can be written very concisely:

```java
@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id).orElse(null);
    }
}
```

The code above is a synchronous DataFetcher. If `findById` calls a Spring Data JPA repository, the executing thread must wait for the database to return the result before the method finishes. If the database takes 300 ms, that thread is held for that waiting period, plus the remaining processing time.

`@QueryMapping` only maps the method to a field on the Query root. The annotation does not automatically turn a synchronous call into an asynchronous one, nor does it automatically dispatch work to another thread pool.

## How Does Blocking Affect MVC and WebFlux?

### With Spring MVC

In the traditional servlet model, each request is typically handled on a servlet thread. When a DataFetcher calls synchronous JPA/JDBC, the request thread waits for I/O and then proceeds to build the GraphQL response.

This approach can be suitable when:

- The application uses Spring MVC and synchronous data access libraries.
- Query latency is bounded and the connection pool/database have appropriate limits.
- Concurrent requests stay within the capacity of the servlet thread pool.
- Timeouts and monitoring are in place to detect slow queries.

Even when blocking is acceptable, a surge of requests waiting on the database can still exhaust all servlet threads, causing new requests to queue or be rejected. Concurrency limits and query optimization are still necessary rather than simply increasing thread counts.

### With Spring WebFlux

WebFlux typically runs on an event loop with a small number of threads. A single event-loop thread can serve many connections. If a DataFetcher calls synchronous JDBC/JPA directly on this thread, it holds the event loop while waiting for I/O. Other requests assigned to that same event loop can also be delayed.

With WebFlux, prefer non-blocking clients and drivers such as WebClient or R2DBC. If you must use a blocking library, offload the work to an executor or scheduler dedicated to blocking I/O.

| Model | When a DataFetcher calls synchronous JDBC/JPA |
| --- | --- |
| Spring MVC | Blocks the servlet request thread until I/O completes. Acceptable when thread, connection, and timeout limits are reasonable. |
| Spring WebFlux | Risks blocking the event loop and degrading throughput for many requests. Blocking I/O must be offloaded to a worker thread. |

GraphQL Java can coordinate fields and combine asynchronous results, but that does not mean a synchronous DataFetcher call is automatically offloaded. If the code calls the repository before returning a result, the current thread is still blocked.

## Offloading Blocking I/O with CompletableFuture

A clear approach is to return a `CompletableFuture` and run the blocking call on a managed executor. For example, create a dedicated executor for GraphQL blocking I/O:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class GraphQlExecutorConfiguration {

    @Bean("graphqlBlockingExecutor")
    ThreadPoolTaskExecutor graphqlBlockingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("graphql-blocking-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

These numbers are only illustrative values. In deployment, size the pool and queue capacity based on database connection counts, downstream service limits, concurrency levels, and I/O duration. Do not increase max pool size arbitrarily because a large thread count can overwhelm the database or downstream services.

The controller injects the executor and returns a future:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductController {

    private final ProductService productService;
    private final Executor graphqlBlockingExecutor;

    public ProductController(
            ProductService productService,
            @Qualifier("graphqlBlockingExecutor") Executor graphqlBlockingExecutor) {
        this.productService = productService;
        this.graphqlBlockingExecutor = graphqlBlockingExecutor;
    }

    @QueryMapping
    public CompletableFuture<Product> product(@Argument String id) {
        return CompletableFuture.supplyAsync(
                () -> productService.findById(id).orElse(null),
                graphqlBlockingExecutor);
    }
}
```

Here the `productService.findById` call only begins inside the supplier executed by the executor. GraphQL receives the `CompletableFuture` and completes the field when the future finishes. The request does not hold the current thread waiting for that blocking call itself.

The executor has a bounded queue to avoid holding an unlimited number of tasks. Define behavior when the queue is full, and monitor queued task counts, wait times, and rejections. A dedicated pool also isolates GraphQL blocking I/O from other work in the application.

## Offloading with Reactor When the Application Uses WebFlux

For reactive controllers, you can wrap the blocking call with `Mono.fromCallable` and shift it onto `Schedulers.boundedElastic()`:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Mono<Product> product(@Argument String id) {
        return Mono.fromCallable(
                    () -> productService.findById(id).orElse(null))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
```

`fromCallable` defers the call until subscription. `subscribeOn(boundedElastic())` shifts execution of the callable onto a scheduler suited for blocking work. This is a useful transitional pattern when JDBC/JPA cannot yet be replaced with non-blocking drivers.

Do not write it like this:

```java
@QueryMapping
public Mono<Product> product(@Argument String id) {
    Product product = productService.findById(id).orElse(null);
    return Mono.just(product);
}
```

In this incorrect example, the repository has already been called synchronously before `Mono.just` is created. Returning `Mono` does not make the data access non-blocking.

`boundedElastic` is meant for bounded blocking work, not as the default choice for every task. If you already use WebClient or R2DBC with non-blocking APIs, return `Mono`/`Flux` directly from those APIs instead of switching to `boundedElastic` unnecessarily.

## Choosing Between Synchronous, CompletableFuture, and Mono

| Implementation | Suitable When | Considerations |
| --- | --- | --- |
| Returning object directly | MVC application using synchronous JPA/JDBC with controlled load. | Request thread waits on I/O; must monitor thread pool and connection pool. |
| `CompletableFuture` with executor | Offloading blocking I/O to a separate pool or integrating future-returning APIs. | Use a bounded executor; handle errors and context propagation across threads. |
| `Mono.fromCallable(...).subscribeOn(boundedElastic())` | Reactive application temporarily using blocking libraries. | The callable must wrap the blocking call; bound and monitor the scheduler. |
| `Mono`/`Flux` from non-blocking APIs | Using WebClient, R2DBC, or truly reactive sources. | Keep the pipeline non-blocking end-to-end; never call blocking APIs mid-pipeline. |

There is no single best return type for every project. Choose based on the web stack and data-layer APIs. A Spring MVC application with JPA does not need to convert every controller to Reactor just to appear asynchronous. A WebFlux application must not call JDBC directly on the event loop.

## Do Not Confuse Async with Faster Queries

Offloading a blocking query frees the request-handling thread, but it does not make the database execute the query faster. If a SQL statement takes 2 seconds, the task still consumes a connection and database resources for that duration.

Before increasing concurrency, check:

- Query plans, indexes, and actual rows scanned.
- Whether the connection pool is large enough for the expected concurrency.
- Whether redundant service or repository calls occur within a single operation.
- Whether returned data can be paginated or capped.
- Whether related fields can be batched to avoid N+1.
- Whether downstream services have appropriate timeouts and rate limits.

For example, a Query returning a list of Products and resolving the seller for each Product can trigger N+1 queries. Offloading each seller call to an executor merely runs many queries concurrently; it does not eliminate the redundant queries. Using DataLoader or `@BatchMapping` to group keys is usually much more effective.

## Controlling Thread Pools and Concurrent Load

When offloading blocking work, the executor becomes an operational resource. Pay attention to:

1. **Pool size:** balance with the connection pool and downstream service limits. If the executor has 32 threads while the database only has 10 connections, the remaining threads may simply wait for connections.
2. **Queue capacity:** a bounded queue creates application-level backpressure. An overly large queue increases latency and keeps many requests waiting longer.
3. **Rejection policy:** when both pool and queue are full, define explicit rejection behavior and map it to an appropriate error instead of spawning unbounded threads.
4. **Timeouts:** configure timeouts on database statements, HTTP clients, and dependent services. A client-side timeout does not necessarily stop a running JDBC call.
5. **Shutdown:** give the executor time to finish running tasks and track interrupted tasks when the application stops.
6. **Metrics:** monitor active threads, queue size, rejected tasks, wait time, and execution duration.

Never create a new executor per request or per resolver call. Use a Spring-managed bean with explicit bounds.

## Transactions and Context When Switching Threads

Moving blocking work to another thread can affect state bound to the current thread.

### Transactions

Spring's JDBC/JPA transactions are typically bound to a thread. If a controller starts a transaction and then creates a `CompletableFuture` on another executor, the original thread's transaction does not automatically follow the async task.

For work requiring a transaction, call a `@Transactional` service method inside the supplier so the transaction is opened on the worker thread:

```java
@Service
public class ProductService {

    @Transactional(readOnly = true)
    public Product findProduct(String id) {
        return productRepository.findById(id).orElse(null);
    }
}
```

```java
@QueryMapping
public CompletableFuture<Product> product(@Argument String id) {
    return CompletableFuture.supplyAsync(
            () -> productService.findProduct(id),
            graphqlBlockingExecutor);
}
```

In this example, the call through the Spring service proxy occurs on the worker thread, so the transaction applies to that executing thread. Do not assume the request thread's transaction covers work offloaded to an executor.

### Security Context, Tenant, and MDC

Data such as `SecurityContextHolder`, MDC, or request-scoped state may be stored in ThreadLocal. When switching threads, it is not automatically copied under all configurations.

- If the work needs user identity, extract the authenticated principal in the controller and pass an immutable identifier to the service.
- If code depends on `SecurityContextHolder`, use an executor that propagates `SecurityContext` such as `DelegatingSecurityContextExecutor` or configure an appropriate `TaskDecorator`.
- If correlation IDs are needed in logs, configure a `TaskDecorator` to copy and restore MDC, and clean up ThreadLocal after the task finishes.
- Do not pass `HttpServletRequest`, response, or request-scoped objects into tasks that may outlive the request lifecycle.

For tenant data, always verify the tenant on the server and pass the verified scope to the service. Never treat a client-supplied tenant ID as a source of authority.

## Cancellation and Errors

Clients may disconnect before a blocking task completes. Canceling a `CompletableFuture` does not guarantee the underlying JDBC call or blocking library stops immediately. Therefore, enforce timeouts on the database driver, HTTP client, or called service itself.

With Reactor, cancellation propagates through the pipeline, yet an in-flight blocking call cannot always be stopped safely. Use timeouts and cancellable APIs if supported by the library; do not rely solely on the client closing the connection.

Errors from `CompletableFuture` or `Mono` become field execution errors. Spring for GraphQL supports `DataFetcherExceptionResolver` to map exceptions to public messages and error codes. Never return stack traces, SQL, or infrastructure details to clients.

If a field is declared nullable, an error can turn that field into `null` while other fields still return data. If a field is Non-Null, null can propagate up to the parent field according to GraphQL rules. Nullability design and error handling must align with the API contract.

## Testing Blocking Queries

Tests should verify both the GraphQL result and how the application handles blocking work:

- The query returns the expected data when the repository finds a match.
- Not-found cases follow nullability and error conventions.
- Blocking calls run on the expected executor/scheduler under WebFlux configuration.
- The executor is bounded and queue-full behavior is handled appropriately.
- Service exceptions map to actionable GraphQL errors.
- Transactions are opened on the executing thread when the service requires a transaction.
- Principal, tenant, and correlation IDs propagate properly when tasks run asynchronously.
- Timeouts and cancellation do not leak resources indefinitely.
- Related fields do not trigger N+1 queries when querying large lists.

Example asserting results with `GraphQlTester`:

```java
@Test
void productQueryReturnsProduct() {
    graphQlTester.document("""
        query {
          product(id: "p-100") {
            id
            name
          }
        }
        """)
        .execute()
        .path("product.id")
        .entity(String.class)
        .isEqualTo("p-100");
}
```

To verify offloading, you can have the service record the thread name in tests or use an observable test executor. Do not judge a system as non-blocking solely by measuring the runtime of a single test; inspect execution threads and concurrent load in a production-like environment.

## Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| WebFlux slows down under database latency | JDBC/JPA running directly on the event loop. | Use R2DBC or offload blocking calls to a worker scheduler/executor. |
| Returning `Mono` yet thread still blocks | Blocking call executes before `Mono.just`. | Move the call inside `Mono.fromCallable` and use `subscribeOn`. |
| Adding threads does not increase throughput | Database connection pool or downstream is saturated. | Limit concurrency, inspect pools, and optimize queries. |
| Transaction does not cover async task | Transaction was started on a different thread. | Call a `@Transactional` service inside the task on the executor. |
| Logs missing correlation ID or lost principal | ThreadLocal context is not propagated to workers. | Pass context explicitly or configure an executor decorator. |
| Client times out while JDBC keeps running | Canceling a future does not stop a blocking call. | Configure timeouts on drivers and downstream services, and cap query duration. |
| List queries still issue many SQL calls | Offloading each resolver without batching related data. | Use DataLoader or `@BatchMapping`. |

## Takeaways

Blocking queries typically occur when `@QueryMapping` invokes synchronous APIs such as JDBC, JPA, or blocking HTTP clients. In Spring MVC, this blocks the servlet thread; in Spring WebFlux, blocking the event loop can impact many other requests. The `@QueryMapping` annotation and GraphQL async execution do not automatically offload blocking calls.

With MVC and JPA, synchronous handlers can work well when load, threads, and connections are properly controlled. With WebFlux, prefer non-blocking APIs; if you must use blocking libraries, move calls to a bounded executor or `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`. Manage transactions, security context, timeouts, cancellation, and N+1 queries alongside thread pools so Queries remain reliable.
