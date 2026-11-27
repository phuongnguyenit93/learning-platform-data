# Executor for Blocking Controllers in Spring for GraphQL

An annotated controller in Spring for GraphQL can return synchronous values such as `Book`, `List<Book>`, or `String`. For handlers calling JDBC, JPA, synchronous HTTP clients, or blocking I/O APIs, the method can hold the thread executing GraphQL for the entire wait duration. Configuring an `Executor` on `AnnotatedControllerConfigurer` allows Spring to run blocking handlers on a separate thread.

There are two mechanisms to distinguish:

- `Callable<T>` is submitted to the `Executor` so the work inside the `Callable` runs asynchronously. This mechanism works across different Java versions once an `Executor` is configured.
- Starting with Spring for GraphQL 1.3 on Java 21+, when an `Executor` is present, controller methods with blocking signatures can be automatically invoked asynchronously even when the method returns `T` directly. This mechanism is convenient for keeping controllers synchronous while using blocking libraries.

The Spring Boot starter can auto-configure an `Executor` backed by virtual threads when `spring.threads.virtual.enabled` is enabled. This article explains how it works, configuration, choosing an executor, testing, and the limits to watch out for.

## 1. Why do blocking controllers need an Executor?

GraphQL often resolves multiple fields in a single operation. Example query:

~~~graphql
query BookDetails($id: ID!) {
    book(id: $id) {
        id
        title
        author {
            id
            name
        }
        reviews {
            id
            comment
        }
    }
}
~~~

Resolvers for `book`, `author`, and `reviews` may access different data sources. If handlers use synchronous APIs, each call to a database or HTTP client can hold the thread until I/O completes.

Example of a blocking controller:

~~~java
@Controller
public class BookController {

    private final BookRepository bookRepository;

    public BookController(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @QueryMapping
    public Book book(@Argument("id") Long id) {
        return bookRepository.findById(id).orElse(null);
    }
}
~~~

Spring Data JPA's `findById` is a synchronous call. When the handler runs on a request-handling thread, that thread must wait for the database to return results. If many concurrent requests are waiting on I/O, the number of request-serving threads can become the throughput bottleneck.

An `Executor` creates a dedicated execution boundary for handlers considered blocking. GraphQL still receives the data fetcher's result asynchronously, while the controller can continue to be written in the familiar imperative style.

## 2. Role of AnnotatedControllerConfigurer

`AnnotatedControllerConfigurer` detects `@Controller` beans, finds methods annotated with `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, `@SchemaMapping`, or `@BatchMapping`, and registers them as GraphQL `DataFetcher`s.

This class has a `setExecutor(Executor)` method to configure an executor for:

- `Callable<T>` return values from controller methods.
- Controller methods with blocking signatures on Java 21+ when the Spring for GraphQL version supports automatic offloading and the executor does not indicate a preference for short-lived tasks.

When no executor is configured, blocking controller methods are invoked synchronously. `Callable` is also unsupported if the configurer has no executor.

~~~mermaid
flowchart TD
    A[GraphQL operation] --> B[GraphQL DataFetcher]
    B --> C[AnnotatedControllerConfigurer]
    C --> D{Controller method type}
    D -->|Reactive: Mono / Flux / CompletionStage| E[Return async value]
    D -->|Blocking signature on Java 21+ with Executor| F[Submit invocation to Executor]
    D -->|Callable with Executor| G[Submit Callable to Executor]
    D -->|Synchronous without Executor or older Java| H[Invoke on current thread]
    E --> I[GraphQL async execution]
    F --> I
    G --> I
    H --> I
~~~

The diagram illustrates the main branches. Whether a method is considered blocking depends on its return type and the `blockingMethodPredicate` configuration on `AnnotatedControllerConfigurer`.

## 3. Return types and execution behavior

| Return type | Execution behavior |
| --- | --- |
| `T` such as `Book`, `String`, `List<Book>` | Invoked synchronously by default. On Java 21+ with an executor suitable for blocking tasks, methods with blocking signatures can be offloaded automatically |
| `Callable<T>` | Work inside the `Callable` is submitted to the executor; requires configuring an executor |
| `CompletableFuture<T>` | Method supplies the asynchronous result itself; not considered blocking by the default predicate |
| `Mono<T>`, `Flux<T>` | Uses the reactive model; Spring for GraphQL adapts the result to GraphQL Java's async mechanism |
| Kotlin `suspend` or `Flow` | Adapted to the corresponding reactive type |

A common point of confusion: merely declaring an `Executor` does not make every method asynchronous on every Java version. Automatic offloading of methods returning `T` requires Java 21+ and Spring for GraphQL 1.3+. On older versions, you can use `Callable<T>` to submit blocking work to the executor.

## 4. Configuring virtual threads with Spring Boot

For Spring Boot applications using the Spring for GraphQL starter, the shortest configuration is enabling virtual threads:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

Java 21 or newer is required. Spring Boot auto-configures an `AsyncTaskExecutor` based on `SimpleAsyncTaskExecutor` using virtual threads, and the Spring for GraphQL starter configures `AnnotatedControllerConfigurer` to use that executor. On Spring for GraphQL 1.3+ with Java 21+, controller methods with blocking signatures are invoked asynchronously.

Example controller still returning `Book` directly:

~~~java
@Controller
public class BookController {

    private final BookRepository repository;

    public BookController(BookRepository repository) {
        this.repository = repository;
    }

    @QueryMapping
    public Book book(@Argument("id") Long id) {
        // Synchronous JPA call, invoked asynchronously on a virtual thread
        // when the runtime and configuration support blocking invocation.
        return repository.findById(id).orElse(null);
    }
}
~~~

There is no need to change the method to `Callable<Book>` just to use virtual threads when automatic blocking invocation is supported. Keeping the direct return type also lets the method signature reflect the data the resolver returns.

Virtual threads are a JVM feature, not a way to make JDBC or HTTP clients non-blocking. They allow an application to serve many waiting I/O tasks with lower thread overhead compared to creating many platform threads.

## 5. Using Callable with an Executor

`Callable<T>` is an explicit choice when you want to specify the work submitted to the executor:

~~~java
import java.util.concurrent.Callable;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookRepository repository;

    public BookController(BookRepository repository) {
        this.repository = repository;
    }

    @QueryMapping
    public Callable<Book> book(@Argument("id") Long id) {
        return () -> repository.findById(id).orElse(null);
    }
}
~~~

The method creates and returns the `Callable` on the thread calling the controller; the repository call sits inside the lambda and is executed by the executor. An executor must be configured on `AnnotatedControllerConfigurer`, otherwise the `Callable` return type is not supported.

`Callable` is useful when:

- The application runs on Java lower than 21 yet needs to separate blocking work from the current thread.
- You want to explicitly mark the work that should run asynchronously.
- Only certain resolvers need to be offloaded to an executor, or automatic offloading cannot be enabled yet.

Do not return `Callable` merely to wrap a tiny non-blocking calculation. Submitting tasks, transferring results, and handling errors all have overhead; only use it when justified by execution needs.

## 6. Using a custom ThreadPoolTaskExecutor in Spring Boot

Spring Boot auto-configures a default executor. If you need to tune pool and queue limits for your application, you can declare an `AsyncTaskExecutor` named `applicationTaskExecutor`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class GraphQlExecutorConfiguration {

    @Bean(name = "applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("graphql-blocking-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

Spring Boot uses the `applicationTaskExecutor` bean for corresponding task execution integrations, including executing `Callable` in Spring for GraphQL. Spring Boot GraphQL auto-configuration also picks up this executor to configure `AnnotatedControllerConfigurer`.

Note on automatic blocking invocation: `ThreadPoolTaskExecutor` implements `SchedulingTaskExecutor` and by default reports that it prefers short-lived tasks. Spring for GraphQL checks the `prefersShortLivedTasks` hint when deciding whether to offload blocking methods that return `T` directly. Therefore, the thread pool in this example is suitable for running `Callable<T>`; do not assume it will offload synchronous methods returning `T`. For methods returning `T` directly, use the virtual-thread executor configured by Spring Boot or an appropriate executor that does not declare a preference for short-lived tasks.

Bean names matter when an application has multiple executors. If you create another `Executor` with a custom name, do not assume Spring Boot GraphQL will automatically pick it up. Check qualifiers and auto-configuration behavior for the exact Spring Boot version you are using.

If you want Spring Boot to use virtual threads automatically, do not declare a thread-pool `applicationTaskExecutor` bean like this example; a custom bean replaces the auto-configured executor. Choose one configuration suited to your application's workload.

The example above uses a bounded thread pool. Values for `corePoolSize`, `maxPoolSize`, and `queueCapacity` are only illustrative starting points, not universal optimal settings. Measure real load and align them with database connection counts, downstream limits, and request concurrency.

## 7. Configuring AnnotatedControllerConfigurer directly

In non-Spring Boot applications, or when intentionally replacing the default configurer, you can create the bean and call `setExecutor`:

~~~java
import java.util.List;

import java.util.concurrent.Executor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.data.method.annotation.support.AnnotatedControllerConfigurer;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
public class GraphQlConfiguration {

    @Bean
    AnnotatedControllerConfigurer controllerConfigurer(Executor executor) {
        AnnotatedControllerConfigurer configurer =
                new AnnotatedControllerConfigurer();
        configurer.setExecutor(executor);
        return configurer;
    }
}
~~~

`AnnotatedControllerConfigurer` is a `RuntimeWiringConfigurer`. When configuring `GraphQlSource` manually, pass the configurer into runtime wiring:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .configureRuntimeWiring(controllerConfigurer)
        .exceptionResolvers(List.of(controllerConfigurer.getExceptionResolver()))
        .build();
~~~

In Spring Boot, do not replace the default configurer just to set an executor if a property or executor bean already meets your needs. When declaring `AnnotatedControllerConfigurer` yourself, the application is responsible for preserving any needed customizations such as custom argument resolvers and exception resolvers.

If the executor passed here is a `ThreadPoolTaskExecutor`, use it for `Callable<T>` or short-lived tasks. To automatically offload synchronous methods returning `T` on Java 21+, choose an executor suitable for blocking work according to the `prefersShortLivedTasks` rule.

## 8. Choosing which methods are considered blocking

On Java 21+ when an executor is present, Spring for GraphQL by default treats a controller method as blocking if its return type is not a known async type such as `Mono`, `Flux`, or `CompletableFuture`, and the method is not a Kotlin suspending function.

`AnnotatedControllerConfigurer` provides `setBlockingMethodPredicate(...)` to customize blocking method detection. The predicate receives a `HandlerMethod`, allowing you to inspect annotations, classes, or method names according to application conventions. The predicate only decides which methods are considered blocking; the executor must still be suitable for automatic blocking invocation and not prefer short-lived tasks.

Example explicitly marking blocking resolvers with a custom annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface BlockingGraphQl {}
~~~

When configuring `AnnotatedControllerConfigurer` manually, the predicate can check for this annotation:

~~~java
configurer.setBlockingMethodPredicate(handlerMethod ->
        handlerMethod.getMethod().isAnnotationPresent(BlockingGraphQl.class)
);
~~~

Usage example:

~~~java
@QueryMapping
@BlockingGraphQl
public Book book(@Argument("id") Long id) {
    return repository.findById(id).orElse(null);
}
~~~

A custom predicate is only needed when the default rule does not fit. Check the Spring for GraphQL and Java versions in use because automatic blocking invocation has version prerequisites. On Java 20 and earlier, the explicit and more compatible choice is returning `Callable<T>` when an executor is needed.

## 9. Distinguishing Executor from reactive return types

An executor serves blocking controllers. With `Mono` or `Flux`, the method already returns a publisher representing asynchronous work; Spring for GraphQL adapts that publisher to a `CompletionStage` for GraphQL Java to process.

Reactive example:

~~~java
@Controller
public class ReactiveBookController {

    private final ReactiveBookRepository repository;

    public ReactiveBookController(ReactiveBookRepository repository) {
        this.repository = repository;
    }

    @QueryMapping
    public Mono<Book> book(@Argument("id") Long id) {
        return repository.findById(id);
    }
}
~~~

There is no need to move a reactive resolver onto an `Executor` just to make it run asynchronously. A reactive pipeline should use suitable reactive drivers/clients. If a blocking library is called inside a reactive pipeline, isolate the blocking portion with an appropriate scheduler such as `Schedulers.boundedElastic()` or replace it with a non-blocking client; do not assume `AnnotatedControllerConfigurer` will automatically detect blocking inside a `Mono` lambda.

| Scenario | Recommended approach |
| --- | --- |
| Resolver uses synchronous JPA/JDBC | Executor for blocking controllers; Java 21+ can automatically offload blocking signatures |
| Resolver returns `Callable<T>` | Configure an executor so the Callable is submitted |
| Resolver uses R2DBC and returns `Mono<T>` | Keep reactive return types and reactive I/O |
| Resolver returns `CompletableFuture<T>` | Manage future creation and internal executor yourself if needed |
| Resolver returns `Mono<T>` yet calls synchronous JDBC inside a lambda | Isolate the blocking section or switch to a reactive client; do not rely on controller auto-offload |

## 10. Executor does not increase database capacity

Increasing the number of threads lets the application wait on more I/O concurrently, but it does not automatically make the database process queries faster. If the pool runs 100 concurrent tasks while the connection pool only has 10 connections, many tasks will still wait to acquire a connection.

When choosing an executor, consider:

- Database connection pool size.
- Concurrency limits of HTTP clients and downstream services.
- Average and p95/p99 latency of blocking calls.
- Number of concurrent GraphQL requests and how many field resolvers may execute per operation.
- Queue capacity and overload task rejection policy.
- GraphQL request timeouts and per-downstream timeouts.

A thread pool with an unbounded queue can accumulate a large backlog when a downstream slows down. A bounded queue surfaces backpressure earlier, though once full, task submissions can be rejected and must be handled as execution errors. Do not set `maxPoolSize` far above what backend resources can sustain without empirical measurements.

## 11. Virtual threads: benefits and limits

Virtual threads fit the thread-per-request/task model when much of the work is waiting on blocking I/O. They reduce the cost of creating and holding threads compared to platform threads, keeping imperative code readable.

Virtual threads do not make CPU-bound work run faster. Nor do they increase database connection limits, the request rate a downstream service accepts, or network bandwidth. If each request holds a connection for a long duration, the connection pool remains the bottleneck.

Points to watch:

1. Use Java 21+; Java 24+ is recommended for a better virtual threads experience per current Spring Boot documentation.
2. Check for pinned virtual threads when the application has `synchronized` blocks or native calls holding carrier threads for long periods.
3. Measure connection pools, downstream concurrency, and wait times—not just thread counts.
4. When virtual threads are enabled, thread pool sizing properties no longer apply to the Boot auto-configured virtual-thread executor.
5. Virtual threads are typically daemon threads; applications relying on background tasks should verify JVM lifecycle and appropriate keep-alive settings.

## 12. Thread-local context and transaction boundaries

When a controller is invoked via an executor, the method may run on a different thread from the transport-handling thread. Do not assume every `ThreadLocal` from the initial thread automatically appears on the worker thread.

For data serving GraphQL such as principal, tenant, or correlation ID, prefer passing it via `GraphQLContext`, method arguments supported by Spring for GraphQL, or an appropriate context propagation mechanism. If the application relies on Spring Security's `SecurityContextHolder` or custom thread-locals, verify the executor configuration and corresponding context propagation setup.

Transactions are also thread-bound in common imperative transaction managers. If a transaction is opened on the request thread and then the controller method is offloaded, that transaction does not automatically transfer to the worker thread. Place transaction boundaries on the service invoked inside the worker thread, or use a transaction model matching the execution model. Do not assume a transaction opened in a parent resolver spans child resolvers running concurrently on different threads.

## 13. Handling exceptions from blocking controllers

Exceptions thrown during controller invocation or inside a `Callable` enter GraphQL's error handling flow. You can use `@GraphQlExceptionHandler` in a controller or `@ControllerAdvice` to convert exceptions into GraphQL errors with appropriate codes and messages.

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book was not found")
                .build();
    }
}
~~~

Do not include database details, connection strings, or stack traces in messages returned to clients. Log exceptions on the server with a correlation ID to aid investigation. Running methods on an executor does not change GraphQL error design principles.

## 14. Testing which executor is used

With Spring Boot and Java 21+, you can enable virtual threads in tests and confirm the resolver runs on a virtual thread. Example:

~~~java
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ThreadInfoController {

    @QueryMapping
    public boolean virtualThread() {
        return Thread.currentThread().isVirtual();
    }
}
~~~

SDL:

~~~graphql
type Query {
    virtualThread: Boolean!
}
~~~

Integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.threads.virtual.enabled=true"
)
@AutoConfigureHttpGraphQlTester
class BlockingControllerExecutorTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void invokesBlockingControllerOnVirtualThread() {
        graphQlTester.document("{ virtualThread }")
                .execute()
                .path("virtualThread")
                .entity(Boolean.class)
                .isEqualTo(true);
    }
}
~~~

This test requires Java 21+, Spring Boot with virtual thread support, and Spring for GraphQL 1.3+ with automatic blocking invocation. With Spring Boot 3.x, add `org.springframework.graphql:spring-graphql-test`; if using `HttpGraphQlTester` over WebTestClient without a test transport on the classpath, add `org.springframework.boot:spring-boot-starter-webflux` in test scope. Import `AutoConfigureHttpGraphQlTester` from `org.springframework.boot.test.autoconfigure.graphql.tester`. With Spring Boot 4.x, use `spring-boot-starter-graphql-test` and package `org.springframework.boot.graphql.test.autoconfigure.tester`. For environments without virtual threads, inspect thread names or thread identity matching the custom executor rather than calling `Thread.isVirtual()`.

In addition, add tests for:

1. `Callable<T>` executing on the configured executor.
2. Reactive `Mono`/`Flux` methods not being marked blocking by the default predicate.
3. Exceptions from blocking methods converting into GraphQL errors properly.
4. Full executor queues or rejected tasks producing observable error behavior.
5. Required context such as principal/tenant remaining available inside resolvers.

## 15. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `Callable` is not registered or fails to run | `AnnotatedControllerConfigurer` lacks an executor | Configure `setExecutor` or use an appropriate Spring Boot executor |
| Method returning `Book` still runs synchronously | Java below 21 or Spring for GraphQL below 1.3, or no executor | Check Java, Spring GraphQL, and executor bean |
| Virtual threads enabled yet method still does not offload | Property not applied, Boot starter did not configure configurer, or return type treated as async | Check effective properties, dependency versions, and method signature |
| Reactive method gets blocked | Blocking call placed inside `Mono`/`Flux` pipeline | Use a reactive client or isolate the blocking step with an appropriate scheduler |
| Database remains slow despite many virtual threads | Connection pool or database is the bottleneck | Measure pool wait, query time, and cap concurrency |
| Request times out when queue grows long | Tasks wait too long in executor or downstream | Bound the queue, set timeouts, and monitor rejections |
| Lost SecurityContext/ThreadLocal | Method executes on a different thread | Pass context explicitly or configure context propagation |
| Transaction does not span other resolvers | Transactions are thread-bound and resolvers may run concurrently | Set transaction boundaries on the right service; do not rely on another thread's transaction |

## 16. Workflow for choosing an Executor for controllers

When a controller uses blocking APIs:

1. Identify which methods genuinely call JDBC/JPA, blocking HTTP clients, or synchronous I/O.
2. When feasible, prefer reactive clients and reactive return types for reactive flows.
3. If using Java 21+ and Spring for GraphQL 1.3+, configure an executor so automatic blocking invocation can offload methods returning `T`.
4. With Spring Boot, consider `spring.threads.virtual.enabled=true` if the workload fits virtual threads.
5. If a bounded thread pool is needed, configure `applicationTaskExecutor` and size pool/queue against downstream resources.
6. On Java below 21 or when explicitly marking async portions, use `Callable<T>` with an executor.
7. Only replace `AnnotatedControllerConfigurer` when direct control is needed; preserve required custom resolvers and exception handling.
8. Test execution threads, errors, context propagation, timeouts, and database pressure.

An executor isolates blocking calls from request-handling threads and lets GraphQL continue coordinating asynchronous results. Real-world effectiveness depends on executor selection, database/downstream capacity, and cleanly distinguishing blocking controllers from reactive controllers.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Thread Model](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL 1.4 — AnnotatedControllerConfigurer API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/support/AnnotatedControllerConfigurer.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Spring Boot — Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.virtual-threads)
