# Blocking resolvers and thread pools

A GraphQL operation can invoke many resolvers to fetch data for nested fields. If a resolver calls JDBC, JPA, a synchronous HTTP library, or an SDK that waits on I/O, the executing thread is held until the operation completes. When many requests arrive concurrently, request-processing threads can become exhausted, increasing wait times and reducing throughput.

In Spring for GraphQL, it is essential to understand which resolvers run synchronously, which return asynchronous results, and which executor receives offloaded blocking work. A **thread pool** isolates blocking tasks and caps concurrency. It does not magically turn a blocking library into a non-blocking one, nor does it replace query optimization, batch loading, or connection pool tuning.

This lesson explains GraphQL Java's thread model, differences between Spring MVC and WebFlux, how Spring for GraphQL handles synchronous and asynchronous DataFetchers, using Callable, CompletionStage, Reactor, and virtual threads, configuring bounded executors, coordinating with DataLoader, testing execution threads, and handling pool saturation.

## 1. What is a blocking resolver?

A resolver retrieves the value for a field in the GraphQL schema. In Spring for GraphQL, a method can be registered as a DataFetcher via @QueryMapping, @MutationMapping, @SchemaMapping, or @BatchMapping.

Example of a synchronous resolver:

~~~java
@Controller
public class BookController {

    private final BookRepository repository;

    public BookController(BookRepository repository) {
        this.repository = repository;
    }

    @QueryMapping
    public Book bookById(@Argument Long id) {
        return repository.findById(id).orElse(null);
    }
}
~~~

If the repository uses JPA/JDBC, calling findById waits for the database to return a result. While waiting, the thread calling the resolver cannot process other work.

Common blocking operations include JDBC/JPA, synchronous HTTP clients, filesystem I/O, synchronous SDKs, and waiting on a Future via get() or join(). A resolver that simply reads an already-loaded property on an object usually does not need offloading to a thread pool. Focus on operations that wait on I/O or consume significant CPU.

## 2. GraphQL Java's thread model

Spring for GraphQL uses GraphQL Java to execute operations. Queries typically use AsyncExecutionStrategy, allowing DataFetchers to return a CompletionStage so fields can complete concurrently. However, AsyncExecutionStrategy does not automatically offload synchronous methods onto a thread pool.

Distinguish two concepts:

1. **Concurrent execution**: multiple fields can have in-flight CompletionStages at the same time.
2. **Thread offloading**: a task is dispatched to another Executor so the current thread does not wait on blocking work.

A DataFetcher returning Book directly executes its repository call immediately when the GraphQL engine invokes the DataFetcher. To avoid holding the GraphQL execution thread while waiting on a blocking API, offload the task to an Executor or use a non-blocking API.

Query fields can only benefit from concurrency when their work is expressed asynchronously, such as via CompletionStage or a reactive publisher. A synchronous resolver still blocks the thread while the DataFetcher is invoked.

### Queries and mutations follow different execution rules

Top-level query fields may execute concurrently according to the execution strategy. Top-level mutation fields execute sequentially to preserve mutation ordering. Child fields of an object are still processed according to the corresponding execution strategy.

Therefore, do not assume every resolver in an operation runs in parallel. Resolver design must account for operation type, dependencies between fields, and data update ordering.

## 3. Spring MVC and Spring WebFlux

Spring for GraphQL supports both Spring MVC and Spring WebFlux. Their threading models differ:

| Stack | Processing model | Risk when resolvers block |
|---|---|---|
| Spring MVC | Servlet container uses a request thread pool | Occupies request threads; when many requests wait on I/O, the pool can exhaust |
| Spring WebFlux | Event-loop threads handle non-blocking I/O | Blocking the event loop can stall many requests simultaneously |

### With Spring MVC

The Servlet stack is designed to handle blocking operations on request threads. A resolver using synchronous JDBC works normally, though each request waiting on the database holds a servlet thread.

As load grows, thread count can become a bottleneck. Increasing the servlet thread pool infinitely does not fix the root cause because database connections, CPU, and memory remain finite.

### With Spring WebFlux

WebFlux uses an event loop and non-blocking I/O. One event-loop thread can serve many requests as long as handlers do not block the thread.

If a resolver calls synchronous JPA or JDBC directly on the event loop, that thread stays blocked for the entire database wait time. Other requests assigned to the same event loop will also be delayed.

With WebFlux, prefer reactive/non-blocking clients such as WebClient and R2DBC. If you must use a blocking library, offload only the blocking portion to an appropriate executor and return an asynchronous result to the GraphQL engine.

Never call block(), Future.get(), or join() inside a WebFlux resolver to wait for results. Those calls turn the flow blocking and can stall the event loop.

## 4. Choosing a return type for resolvers

Spring for GraphQL supports several return types to represent synchronous or asynchronous work:

| Return type | Behavior | When to use |
|---|---|---|
| T | Returns result synchronously | Fast logic without I/O waiting |
| CompletableFuture or CompletionStage | Returns a result completing in the future | Tasks run on an Executor or future-returning APIs |
| Mono or Flux | Reactive publisher | WebFlux, WebClient, R2DBC, or reactive sources |
| Callable<T> | Spring runs the task on a configured Executor | Blocking resolvers offloaded via AnnotatedControllerConfigurer |
| Kotlin suspend or Flow | Coroutines adapted by Spring | Kotlin applications |

Do not choose a return type merely to have "asynchronous" in the signature. What matters is that blocking work actually executes on an appropriate thread and never blocks the event loop.

### 4.1. Using Callable with AnnotatedControllerConfigurer

Spring for GraphQL supports resolvers returning Callable. The Callable is submitted to the Executor managed by AnnotatedControllerConfigurer. If no Executor is configured, this return type is not supported.

~~~java
@Controller
public class BookController {

    private final AuthorRepository authorRepository;

    public BookController(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    @SchemaMapping
    public Callable<Author> author(Book book) {
        return () -> authorRepository
                .findById(book.authorId())
                .orElse(null);
    }
}
~~~

The method returns the Callable immediately, and the repository call executes when the Executor runs the Callable. This is an explicit way to mark resolvers that should run asynchronously.

Standalone configuration example:

~~~java
@Configuration
public class GraphQlConfiguration {

    @Bean
    AnnotatedControllerConfigurer controllerConfigurer(
            @Qualifier("graphqlBlockingExecutor") Executor executor) {

        AnnotatedControllerConfigurer configurer =
                new AnnotatedControllerConfigurer();
        configurer.setExecutor(executor);
        return configurer;
    }
}
~~~

This AnnotatedControllerConfigurer bean is added to GraphQlSource as a RuntimeWiringConfigurer. In a Spring Boot application, the starter creates this configurer automatically. Declare a replacement bean only when you deliberately manage GraphQlSource and know which default settings must be preserved.

In standalone setups, register the configurer on the builder:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(schemaResource)
        .configureRuntimeWiring(controllerConfigurer)
        .build();
~~~

Key imports for the standalone example include org.springframework.graphql.data.method.annotation.support.AnnotatedControllerConfigurer, org.springframework.graphql.execution.GraphQlSource, org.springframework.beans.factory.annotation.Qualifier, and java.util.concurrent.Executor.

### 4.2. Using CompletableFuture with a dedicated executor

If you want to choose a specific executor per task, return CompletableFuture:

~~~java
@Controller
public class BookController {

    private final AuthorRepository authorRepository;
    private final Executor graphqlBlockingExecutor;

    public BookController(
            AuthorRepository authorRepository,
            @Qualifier("graphqlBlockingExecutor") Executor graphqlBlockingExecutor) {
        this.authorRepository = authorRepository;
        this.graphqlBlockingExecutor = graphqlBlockingExecutor;
    }

    @SchemaMapping
    public CompletableFuture<Author> author(Book book) {
        return CompletableFuture.supplyAsync(
                () -> authorRepository
                        .findById(book.authorId())
                        .orElse(null),
                graphqlBlockingExecutor);
    }
}
~~~

Here, the repository call is dispatched to graphqlBlockingExecutor. The GraphQL engine receives a CompletionStage and continues assembling the response when the future completes.

Always pass an explicit executor to supplyAsync. Omitting the executor argument causes CompletableFuture to use ForkJoinPool.commonPool, making blocking tasks compete for threads with other JVM workloads.

### 4.3. Using Mono when isolating a blocking API

With WebFlux, if a blocking library cannot yet be replaced, wrap the call in Mono.fromCallable and specify a scheduler backed by an executor:

~~~java
@SchemaMapping
public Mono<Author> author(Book book) {
    return Mono.fromCallable(() ->
                    authorRepository
                            .findById(book.authorId())
                            .orElse(null))
            .subscribeOn(Schedulers.fromExecutor(graphqlBlockingExecutor));
}
~~~

The Callable inside Mono only runs when the publisher is subscribed to and is scheduled onto the specified scheduler. Never call block() after this snippet.

If the repository already uses R2DBC or the service returns a Mono from WebClient, do not wrap it in fromCallable or offload to a blocking executor. Return the reactive publisher directly to leverage non-blocking I/O.

## 5. Configuring ThreadPoolTaskExecutor

For blocking tasks, use an explicitly bounded executor. ThreadPoolTaskExecutor lets you configure core thread count, max thread count, queue capacity, and thread naming.

Example:

~~~java
@Configuration
public class GraphQlExecutorConfiguration {

    @Bean("graphqlBlockingExecutor")
    public ThreadPoolTaskExecutor graphqlBlockingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("graphql-blocking-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
~~~

These numbers are purely illustrative. Real pool sizes should be chosen based on dependency latency, database connection count, concurrent requests, and application resource limits.

Key imports include org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor, org.springframework.context.annotation.Bean, and Configuration. Examples using CompletableFuture require java.util.concurrent.CompletableFuture and Executor; examples using Callable require java.util.concurrent.Callable.

ThreadPoolTaskExecutor starts with corePoolSize threads. Once all core threads are busy, tasks enter the queue. Once the queue is full, the pool grows up to maxPoolSize threads. If the queue remains full at maxPoolSize, tasks are rejected per the rejection policy.

Set a finite queueCapacity to bound queued work. An overly large queue lets requests wait a long time in line without available threads, inflating latency and retaining many objects in memory.

Do not rely on ThreadPoolTaskExecutor's defaults for production workloads. By default, core pool size is small, max pool size is huge, and queue capacity is unbounded; an unbounded queue prevents maxPoolSize from ever scaling up as expected.

### Spring Boot configuration

The Spring Boot GraphQL starter auto-configures AnnotatedControllerConfigurer and uses applicationTaskExecutor if present. With Boot's default configuration, controller Callable return values are dispatched to this executor.

If you want to replace Boot's shared executor, declare a bean named applicationTaskExecutor:

~~~java
@Bean(name = "applicationTaskExecutor")
public ThreadPoolTaskExecutor applicationTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(24);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("application-");
    return executor;
}
~~~

Note that applicationTaskExecutor may be shared across other Spring integrations such as Spring MVC, WebFlux, WebSocket, and async tasks. When replacing this bean, account for the combined load of all components sharing the pool.

If you only want a dedicated executor for a specific resolver or group of GraphQL tasks, inject graphqlBlockingExecutor and pass it directly to CompletableFuture.supplyAsync as shown earlier. This avoids altering the application's shared executor.

### Standalone configuration

When creating AnnotatedControllerConfigurer manually, call setExecutor with the executor intended for Callables. The configurer bean must be added to GraphQlSource as a RuntimeWiringConfigurer. With Spring Boot, do not create a second configurer if the starter already provides the default one.

## 6. Virtual threads on Java 21+

Virtual threads allow applications to create many lightweight threads compared to platform threads, making them well-suited for I/O-blocking workloads with heavy wait times. They help utilize I/O wait time, but they do not make the database faster or increase the number of connections the database allows.

With Java 21+ and Spring Boot versions supporting virtual threads (e.g., Spring Boot 3.2+), you can enable:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

Spring Boot can configure applicationTaskExecutor to use virtual threads. The Spring Boot GraphQL starter also configures AnnotatedControllerConfigurer with that executor. Starting in Spring for GraphQL 1.3, when AnnotatedControllerConfigurer has an Executor and runs on Java 21+, controller methods with blocking signatures can be invoked asynchronously. Async return types such as Mono, Flux, CompletableFuture, and Kotlin suspending functions are not treated as blocking methods under the default rule.

AnnotatedControllerConfigurer also allows customizing the blocking method predicate if the default detection rule does not suit your controllers.

With this support, methods can return T directly instead of wrapping in Callable. However, verify your Spring Boot and Spring for GraphQL versions, as this behavior depends on version and executor configuration.

Virtual threads suit blocking I/O. CPU-bound work remains bounded by CPU cores; spawning more virtual threads does not add compute capacity. Connection pools, external API limits, and semaphores must still be managed.

## 7. Sizing a thread pool

There is no single corePoolSize or maxPoolSize that fits every GraphQL service. Choose sizes based on workload type and downstream limits.

### CPU-bound work

If resolvers perform heavy computation, concurrent thread count should stay close to the number of CPU cores actually allocated to the container or host. Adding too many threads increases context switching and can lengthen processing times.

### I/O-bound work

If resolvers frequently wait on databases or remote APIs, you may need more threads than CPU cores to overlap wait times. However, the real bottleneck usually lies in the database connection pool, remote API rate limits, sockets, and memory.

For example, if the database only grants 20 connections to the application while the executor runs 100 concurrent JDBC queries, most tasks will simply block waiting for a connection. A huge thread pool does not make the database process faster.

When sizing, consider:

- Concurrent GraphQL requests.
- How many blocking resolvers can run within a single request.
- Average and p95/p99 latency of databases or remote APIs.
- Connection pool size and dependency concurrency limits.
- Container CPU cores and memory limits.
- Active platform threads or virtual threads.
- Queue depth and wait time before tasks start.

Measure under representative load and tune one parameter at a time. Never copy thread counts from a developer laptop into production.

## 8. Using DataLoader to reduce blocking I/O calls

Thread pools isolate blocking operations, but if every child field runs a separate database query, the application still suffers from N+1.

Suppose a query fetches 100 books and each book has an author field. If the author resolver calls the repository once per book, the application triggers 100 extra queries. Moving all 100 queries onto a thread pool does not eliminate that cost; it merely runs 100 blocking waits on another executor.

Use BatchMapping or BatchLoaderRegistry to group keys into a single batch load:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Callable<Map<Book, Author>> author(List<Book> books) {
        return () -> authorService.findAuthorsForBooks(books);
    }
}
~~~

In this example, a single batch method receives the list of Books and returns Map<Book, Author>. The Callable is dispatched through the Executor configured on AnnotatedControllerConfigurer. Instead of running one blocking task per book, the application executes a single batch query.

If the batch service is already non-blocking, return Mono<Map<Book, Author>> or Flux<Author> in exact input list order. There is no need to offload reactive batch loads onto a blocking executor.

DataLoader caches per request. Therefore, avoid creating a separate DataLoader or executor per field invocation. Use Spring's BatchLoaderRegistry to register loaders and preserve request scoping.

## 9. Queuing, rejection, and backpressure

Thread pools need an explicit policy when task volume exceeds processing capacity.

| State | Behavior | Meaning |
|---|---|---|
| Idle thread available | Task runs immediately | No queue wait |
| Threads busy, queue has space | Task is queued | Latency increases by queue wait time |
| Queue full, pool below max | Pool spawns threads up to maxPoolSize | Concurrency rises, adding load on dependencies |
| Pool at max and queue full | Task is rejected | System is overloaded beyond configured limits |

Never use an unbounded queue just to avoid task rejection errors. Unbounded queues cause requests to stall excessively and retain large amounts of data in memory. When queues fill up, controlled rejection is far easier to operate than unbounded latency growth.

ThreadPoolTaskExecutor uses an abort/rejection policy by default when both pool and queue are full. Handle TaskRejectedException at an appropriate layer to return an observable error.

Avoid CallerRunsPolicy for blocking resolvers in WebFlux. That policy can run tasks on the submitting thread; if that thread is an event-loop thread, blocking I/O ends up blocking the event loop.

Configure timeouts on database queries and remote clients. A GraphQL request timeout does not automatically stop every underlying blocking operation; each dependency still needs its own timeout and cancellation support.

## 10. Transactions and context across thread switches

When a resolver is offloaded to an executor, work runs on a different thread from the request thread. Several Spring mechanisms store state in ThreadLocal, so do not assume that state automatically follows the task.

### Transactions

Spring transactions with synchronous transaction managers are normally bound to the executing thread. If a GraphQL request opens a transaction on the request thread and a resolver runs on a worker thread, the worker thread does not automatically join that transaction.

With JDBC/JPA, a more controllable pattern is placing transaction boundaries around the service method performing database access. When the service method is invoked inside a Callable or CompletableFuture on a worker thread, the transaction opens and closes on that same worker thread.

Avoid opening a single synchronous transaction spanning an entire GraphQL query whose DataFetchers execute concurrently. If business logic requires a single transaction across an operation, design the execution strategy and transaction lifecycle deliberately; this is an advanced case because the default execution strategy can run fields on multiple threads.

### Security, logging, and tracing context

When using CompletableFuture.supplyAsync with a custom executor, ThreadLocals such as MDC or observation context may not automatically propagate to worker threads.

With Spring Framework 6.1+, configure ContextPropagatingTaskDecorator on ThreadPoolTaskExecutor:

~~~java
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
~~~

This decorator uses Micrometer Context Propagation to restore registered context accessors while the task executes. For SecurityContext or custom application contexts, verify the corresponding integration or pass required data explicitly. Do not pass the entire request object to another thread if only a few values are needed.

The ContextPropagatingTaskDecorator class lives in package org.springframework.core.task.support and was introduced in Spring Framework 6.1.

GraphQLContext is the proper place to pass per-request data during GraphQL execution. With DataLoader, prefer Spring's BatchLoaderRegistry to receive context and leverage framework context propagation.

## 11. Testing blocking resolvers

A good test verifies two things: the GraphQL response is correct, and the blocking work actually ran on the expected executor.

Example controller recording the thread name that executed the resolver:

~~~java
@Controller
public class DiagnosticsController {

    private final AtomicReference<String> lastThreadName =
            new AtomicReference<>();

    @QueryMapping
    public Callable<String> resolverThread() {
        return () -> {
            lastThreadName.set(Thread.currentThread().getName());
            return "ok";
        };
    }

    public String getLastThreadName() {
        return lastThreadName.get();
    }
}
~~~

After executing the query with GraphQlTester, verify the response and thread name:

~~~java
graphQlTester.document("{ resolverThread }")
        .execute()
        .path("resolverThread")
        .entity(String.class)
        .isEqualTo("ok");

assertThat(diagnosticsController.getLastThreadName())
        .startsWith("graphql-blocking-");
~~~

This test requires configuring AnnotatedControllerConfigurer with an executor using the matching threadNamePrefix. If the resolver runs on the request thread, the test catches that offloading is not active.

Key imports for the example include java.util.concurrent.Callable, java.util.concurrent.atomic.AtomicReference, org.springframework.graphql.data.method.annotation.QueryMapping, org.springframework.graphql.test.tester.GraphQlTester, and static imports for AssertJ assertions.

In addition to the above, test:

1. Queries with multiple asynchronous fields return complete responses.
2. Exceptions thrown by resolvers map to appropriate GraphQL errors.
3. Timed-out Callables or futures behave predictably.
4. A full queue produces observable rejection instead of hanging requests indefinitely.
5. Concurrent tasks never exceed configured bounds.
6. DataLoader batches are invoked with expected key counts.
7. Required context such as trace ID or user info remains available on worker threads.

Do not test only with a single isolated request. Run concurrent load tests to observe queue depth, active threads, response latency, and task rejection rates.

## 12. Monitoring thread pools at runtime

In production, monitor both GraphQL requests and the executor running blocking tasks.

Metrics to observe:

| Metric | Used to detect |
|---|---|
| Active thread count | Threads currently executing tasks |
| Pool size | Current number of threads in the pool |
| Queue size | Tasks waiting to be executed |
| Completed task count | Total completed tasks |
| Rejected task count | Tasks rejected when pool is overloaded |
| Task queue wait time | How long tasks wait before starting |
| Task execution time | Duration of the blocking operation |
| GraphQL p95/p99 latency | Impact of pool behavior on response times |

ThreadPoolTaskExecutor exposes metrics such as pool size and active count. You can expose these via JMX or metrics depending on application configuration. With Spring Boot Actuator, monitor them alongside servlet/event-loop metrics, database connection pools, and HTTP client pools.

If active threads stay pinned at maxPoolSize and the queue grows steadily, the executor is saturated. If the queue stays low while the database connection pool is exhausted, the bottleneck is likely the database or connection hold times. If the executor is idle yet GraphQL requests remain slow, inspect resolvers, network, and other dependencies.

Do not look at thread counts alone. Queue wait time and execution time distinguish tasks slow due to queuing from tasks slow due to the dependency itself.

## 13. Common pitfalls with blocking resolvers and thread pools

| Symptom | Possible cause | Resolution |
|---|---|---|
| WebFlux runs abnormally slow calling JPA | Blocking resolver runs on event loop | Use R2DBC or offload blocking work to an executor |
| AsyncExecutionStrategy enabled yet requests still block | Resolver returns synchronous T and does I/O before returning | Return CompletionStage, Mono, or Callable on an executor |
| Callable fails on controller registration | AnnotatedControllerConfigurer lacks an Executor | Configure an Executor on the configurer |
| Resolver does not run on expected thread pool | CompletableFuture uses commonPool or executor was omitted | Pass an explicit executor to supplyAsync |
| Pool accumulates a huge queue | Queue too large or dependency is slow | Set a finite queue, measure queue wait time, inspect dependency |
| Tasks rejected as load grows | Pool reached max and queue is full | Size capacity for real load, rate-limit requests, handle rejection |
| Adding threads does not speed up DB | Connection pool or database is already saturated | Align executor bounds with connection pool and optimize queries |
| Child resolvers emit too many queries | N+1, each field blocking individually | Use BatchMapping or BatchLoaderRegistry |
| Trace ID or MDC lost on worker threads | Context not propagated across custom executor | Configure context propagation or pass data explicitly |
| Transaction does not cover offloaded resolver | Transaction bound to request thread while resolver runs elsewhere | Place transaction around service method running on worker thread |
| CPU spikes when increasing threads | CPU-bound workload or excessive context switching | Reduce concurrency and optimize algorithms |
| Resolver times out while JDBC keeps running | GraphQL timeout cannot abort JDBC calls | Configure query timeouts and cancellation on dependencies |

## 14. Workflow for implementing blocking resolvers

When a resolver must call a blocking library:

1. Identify which operation is genuinely blocking and measure its wait time.
2. Replace it with a non-blocking API such as WebClient or R2DBC if possible.
3. If the blocking library must remain, choose a bounded executor.
4. Use Callable with AnnotatedControllerConfigurer, or CompletableFuture.supplyAsync with an explicit executor.
5. In WebFlux, never call block() on the event loop; offload only the blocking part to an appropriate scheduler.
6. Size corePoolSize, maxPoolSize, and queueCapacity according to dependency limits.
7. Set timeouts for databases and remote APIs.
8. Use BatchMapping or BatchLoaderRegistry to eliminate N+1.
9. Verify transactions open on the actual thread executing the service.
10. Configure context propagation if trace IDs, MDC, or other context is needed on worker threads.
11. Test responses, thread names, concurrency, rejections, and timeouts.
12. Monitor active threads, queue size, queue wait time, dependency pools, and GraphQL latency under real load.

Blocking resolvers do not always require a separate thread pool. In Spring MVC, blocking on request threads can be acceptable when load and servlet pool limits fit. In WebFlux, avoiding blocking on the event loop is critical. When offloading is necessary, use a bounded Executor or Java 21+ virtual threads with Spring's support. Combine thread pools with DataLoader, timeouts, and runtime observability to manage concurrency from GraphQL resolvers down to databases and external services.

## References

- Spring for GraphQL — Request Execution and Thread Model: https://docs.spring.io/spring-graphql/reference/request-execution.html
- Spring for GraphQL — Annotated Controllers and Callable: https://docs.spring.io/spring-graphql/reference/controllers.html
- Spring Boot — Task Execution and Scheduling: https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring for GraphQL — Batch Loading: https://docs.spring.io/spring-graphql/reference/request-execution.html#execution-batch-loading
