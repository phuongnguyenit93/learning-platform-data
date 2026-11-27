# Asynchronous Queries with @Async and Limitations of Synchronous JPA

## 1. Why Run Queries Asynchronously?

An endpoint may need to read data that takes a long time: searching with many conditions, aggregating reports, checking order status, or loading data for a background task. If a controller calls a repository synchronously, the thread handling the HTTP request waits until JDBC and the database finish the query.

Spring Framework provides `@Async` to execute a method on a task executor. Spring Data JPA can combine `@Async` with query methods returning `Future` or `CompletableFuture`. This frees the calling thread from directly waiting for the method to finish.

However, an important limitation must be understood: **JPA and JDBC remain synchronous, blocking APIs**. When a query runs on an executor thread, that thread still blocks waiting for the database to return results. `@Async` offloads work to another thread and allows concurrent execution of multiple tasks; it does not convert JDBC into non-blocking I/O and does not make an SQL statement run faster on its own.

Three concepts must be distinguished:

- **Synchronous:** the caller invokes a method and waits for the result directly on the same execution thread.
- **Asynchronous with @Async:** Spring dispatches the call to an executor; the caller receives a Future and can continue working while a worker thread runs the blocking query.
- **Reactive/non-blocking:** processing flows do not hold a thread waiting on I/O; requires an end-to-end non-blocking driver and data access stack.

Spring Data JPA fits the imperative/blocking model. If true reactive database access is required, evaluate Spring Data R2DBC and a compatible database driver.

## 2. How Does @Async Work?

### 2.1. Proxy Mechanism and TaskExecutor

When async support is enabled, Spring creates a proxy for beans containing methods annotated with `@Async`. When another bean calls the method through the proxy:

1. The proxy intercepts the call and determines which executor to use.
2. The work is submitted to the executor as a task.
3. The executor picks a worker thread to run the method.
4. The caller receives a Future/CompletableFuture instead of waiting directly for the result.
5. Once the method finishes, the Future completes with the result or an exception.

Conceptual flow:

```text
HTTP request thread
       |
       | calls method via Spring proxy
       v
   @Async proxy
       |
       | submit task
       v
  TaskExecutor queue
       |
       v
   Worker thread
       |
       | calls repository / JDBC
       v
     Database
       |
       | result
       v
 CompletableFuture completes
       |
       v
 Spring MVC / caller continues processing
```

The worker thread remains occupied while JDBC waits on the database. The benefit is that the calling thread is freed or can continue other work while the query executes independently on the executor.

### 2.2. Enabling Async Support

`@EnableAsync` must be declared in Spring configuration:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

Imports:

```java
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.context.annotation.Configuration;
```

Adding `@Async` alone without enabling async support may cause the method to still execute synchronously like an ordinary Java method.

### 2.3. @Async Relies on Spring Proxies

Calls must pass through a Spring proxy. The following example does not trigger async execution:

```java
@Service
public class ReportService {

    public CompletableFuture<Report> generate() {
        return generateAsync(); // self-invocation
    }

    @Async
    public CompletableFuture<Report> generateAsync() {
        // Heavy work
        return CompletableFuture.completedFuture(new Report());
    }
}
```

`generateAsync()` is called directly on the same instance via `this`, bypassing the proxy, so the `@Async` interceptor is not applied.

A better design is to place the async method on a separate Spring bean and invoke that bean from another service. Avoid self-injection or manual proxy lookups merely to work around self-invocation when responsibilities can be cleanly separated.

Async methods should be public methods invoked from another bean. When using class-based proxies, `final` classes or methods can prevent subclass proxying; adhere to the proxy mode configured in your application.

## 3. Configuring ThreadPoolTaskExecutor

### 3.1. Why Use a Dedicated Executor?

If no executor is specified, Spring may pick a default executor depending on application configuration. For JPA queries, define a named dedicated executor to control worker thread counts and queue bounds.

Configuration example:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean(name = "jpaQueryExecutor")
    public ThreadPoolTaskExecutor jpaQueryExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("jpa-query-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);

        return executor;
    }
}
```

Spring manages the bean lifecycle and initializes the ThreadPoolTaskExecutor. The numbers in the example are illustrative starting points, not optimal settings for every application.

### 3.2. Meaning of Parameters

| Property | Meaning |
|---|---|
| corePoolSize | Number of core worker threads retained in the pool |
| maxPoolSize | Maximum number of workers under increased load |
| queueCapacity | Maximum number of tasks waiting in the queue |
| threadNamePrefix | Prefix helping identify workers in thread dumps and logs |
| waitForTasksToCompleteOnShutdown | Allows queued/running tasks to finish during shutdown per executor policy |
| awaitTerminationSeconds | Wait timeout for executor termination during shutdown |

Queues should not be unbounded. If the database slows down while the application keeps accepting tasks, an unbounded queue can accumulate huge numbers of requests, retaining data in heap and raising latency. A bounded queue gives the system a backpressure control point.

When both the pool and queue are full, the executor can reject tasks. The application must decide how to respond, retry, or route work to a durable queue. Never silently drop critical tasks.

### 3.3. Executor Size Must Align with the Connection Pool

Each JPA query requires a database connection when executing SQL. If there are 50 worker threads but the connection pool only allows 10 connections, many workers will wait for connections; they still occupy threads without executing SQL.

Conversely, enlarging the connection pool too far can overload the database. Consider simultaneously:

- Concurrent async request volume.
- Connection pool size (e.g., HikariCP).
- Connection limits permitted by the database.
- Average and p95/p99 query durations.
- Database CPU, I/O, and processing capacity.
- Resources reserved for synchronous requests and other jobs.

There is no rigid formula such as always setting maxPoolSize equal to the connection pool. Measure under realistic load, reserve connections for critical paths, and set appropriate concurrency limits.

## 4. Querying Repositories with @Async

### 4.1. Declaring an Async Query Method

Suppose we need to find customers by status and return DTOs:

```java
public record CustomerSummary(Long id, String name) {
}
```

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Async("jpaQueryExecutor")
    @Transactional(readOnly = true)
    @Query("""
        select new com.example.customer.dto.CustomerSummary(
            c.id,
            c.name
        )
        from Customer c
        where c.status = :status
        order by c.name, c.id
        """)
    CompletableFuture<List<CustomerSummary>> findSummariesAsync(
        @Param("status") CustomerStatus status
    );
}
```

Key points to note:

- `@Async("jpaQueryExecutor")` selects the named configured executor.
- The query method returns `CompletableFuture<List<CustomerSummary>>`, rather than returning List directly, to use async query execution.
- `@Transactional(readOnly = true)` explicitly specifies the query should run in a read transaction.
- The JPQL constructor expression produces DTOs, avoiding returning entities with lazy associations to callers on another thread.
- `ORDER BY` includes ID as a tie-breaker for a more deterministic result order.

Spring Data JPA supports async query methods with appropriate Future types. Exact syntax and specific capabilities depend on the Spring Data version. Check your project's dependencies when using special return types or combining complex paging/projections.

### 4.2. Why Is an Explicit Transaction Needed?

Query methods declared by name or `@Query` do not necessarily inherit the same default transaction configuration as inherited CRUD methods. Declare `@Transactional` on the appropriate method or service layer.

Spring's imperative transactions are bound to the executing thread. When `@Async` dispatches a call to a worker thread, an active transaction on the caller thread does not automatically propagate to the worker thread.

Therefore, if a query needs a transaction, the transaction must be started on the worker thread. Place the transaction boundary on the async query method or call a dedicated `@Transactional(readOnly = true)` worker service from the async thread.

### 4.3. Calling and Handling Results

The caller receives a CompletableFuture:

```java
CompletableFuture<List<CustomerSummary>> future =
    customerRepository.findSummariesAsync(CustomerStatus.ACTIVE);

future.thenAccept(customers -> {
    // Handle result on completion
});
```

Do not call `get()` or `join()` immediately after receiving the future in a controller if the goal is to avoid blocking the request thread. Doing so blocks the caller again and negates the benefit of async execution.

If transforming the result is needed:

```java
CompletableFuture<CustomerPageResponse> response =
    customerRepository
        .findSummariesAsync(CustomerStatus.ACTIVE)
        .thenApply(CustomerPageResponse::from);
```

Callbacks like `thenApply`/`thenAccept` without the Async suffix may execute on the thread that completes the future. If the follow-up processing step is CPU-intensive or blocking, consider a dedicated executor for that step instead of occupying worker threads reserved for JPA queries.

## 5. Service-Layer Async and Transaction Workers

In many applications, placing async at the service layer decouples the asynchronous API from the repository. The repository stays a synchronous JPA API; the service invokes it from a worker thread.

Example:

```java
@Service
public class CustomerAsyncService {

    private final CustomerQueryWorker queryWorker;

    public CustomerAsyncService(CustomerQueryWorker queryWorker) {
        this.queryWorker = queryWorker;
    }

    @Async("jpaQueryExecutor")
    public CompletableFuture<List<CustomerSummary>> searchAsync(
        String keyword
    ) {
        List<CustomerSummary> result =
            queryWorker.search(keyword);

        return CompletableFuture.completedFuture(result);
    }
}
```

Worker with its own transaction:

```java
@Service
public class CustomerQueryWorker {

    private final CustomerRepository repository;

    public CustomerQueryWorker(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<CustomerSummary> search(String keyword) {
        return repository.searchSummaries(keyword);
    }
}
```

The repository method in this example is a standard synchronous query:

```java
@Query("""
    select new com.example.customer.dto.CustomerSummary(
        c.id,
        c.name
    )
    from Customer c
    where lower(c.name) like lower(concat('%', :keyword, '%'))
    order by c.name, c.id
    """)
List<CustomerSummary> searchSummaries(
    @Param("keyword") String keyword
);
```

Separating the beans ensures `queryWorker.search()` goes through the transaction proxy. The transaction starts on the worker thread because the call happens inside the async method. `CompletableFuture.completedFuture()` wraps the result already computed on the worker; there is no need to spawn a second executor.

Choose one of the two approaches:
- Async directly on the repository query method when only a single standalone query needs to run.
- Async at the service layer calling a synchronous worker/repository when multiple business steps must be grouped inside the same worker transaction.

Do not nest multiple `@Async` executors for a single query without a clear reason.

## 6. Transactions Are Not Inherited from the Caller

### 6.1. Transactions Are Thread-Bound

In the imperative model, Spring's transaction manager typically holds transaction resources and state per current thread. `@Transactional` on a caller thread does not automatically carry over to an executor thread.

Example:

```java
@Transactional
public void createOrderAndStartReport() {
    orderRepository.save(newOrder);

    reportService.generateAsync();
}
```

If `generateAsync()` runs on a worker thread, it does not automatically join the transaction of `createOrderAndStartReport()`. The worker needs its own transaction if its queries or writes require one.

### 6.2. Async May Execute Before the Caller Transaction Commits

A dangerous scenario:

1. The caller saves a new record inside a transaction.
2. The caller dispatches an async task to read that record.
3. The worker starts before the caller commits.
4. The worker uses a separate transaction and may not yet see the new record.

Never assume an async task will see uncommitted data from the caller. If work must run after the originating transaction commits, use a post-commit event such as `@TransactionalEventListener(phase = AFTER_COMMIT)` or a transactional outbox for high-reliability tasks.

Post-commit event example:

```java
public record OrderCreatedEvent(Long orderId) {
}
```

Publishing the event inside the transaction:

```java
publisher.publishEvent(new OrderCreatedEvent(order.getId()));
```

Listener:

```java
@Component
public class OrderCreatedListener {

    private final ReportAsyncService reportAsyncService;

    public OrderCreatedListener(ReportAsyncService reportAsyncService) {
        this.reportAsyncService = reportAsyncService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        reportAsyncService.generateAsync(event.orderId());
    }
}
```

The listener is triggered only after the transaction commits successfully. If you must ensure events are never lost if the process crashes between commit and dispatch, a transactional outbox is usually more appropriate than a plain in-memory event.

## 7. Do Not Share EntityManager or Managed Entities Across Threads

### 7.1. EntityManager Is Not Thread-Safe

EntityManager and the persistence context are not designed for concurrent use by multiple threads. Each worker needs its own Spring-managed persistence context and transaction.

Never pass an EntityManager from a request thread to an async thread. Never manually open an EntityManager and share it across multiple tasks.

### 7.2. Managed Entities Can Become Detached

A repository query can return entities managed within the worker transaction's persistence context. When the transaction ends and the persistence context closes, those entities are no longer managed in that context.

If the caller receives an entity and accesses lazy associations after the worker transaction has ended, Hibernate may throw `LazyInitializationException`.

Therefore, you should:
- Return DTOs or projections containing the exact required data.
- Fetch needed associations inside the worker transaction.
- Map entities to DTOs before returning results.
- Never send managed entities to another thread expecting dirty checking to keep working.

Example query returning DTOs via a constructor expression:

```java
@Query("""
    select new com.example.customer.dto.CustomerSummary(
        c.id,
        c.name
    )
    from Customer c
    where c.status = :status
    """)
List<CustomerSummary> findSummaries(
    @Param("status") CustomerStatus status
);
```

The DTO holds materialized data and does not depend on lazy proxies after the transaction closes.

### 7.3. Do Not Pass Uninitialized Lazy Associations

Even when an entity is returned via a Future, lazy proxies inside it may still be uninitialized. Merely calling getters after the transaction closes can raise errors. If associations are needed, use fetch joins, EntityGraph, or projections to load the necessary data before the worker transaction finishes.

## 8. CompletableFuture and Error Handling

### 8.1. Propagating Exceptions Through Future

If an async method throws an exception, the CompletableFuture completes exceptionally. The caller can handle it:

```java
CompletableFuture<List<CustomerSummary>> future =
    customerRepository.findSummariesAsync(CustomerStatus.ACTIVE);

future.exceptionally(error -> {
    // Log the error and return an appropriate fallback value
    return List.of();
});
```

Do not turn every error into an empty list if business logic must distinguish "no data found" from "database error". Map errors to results or HTTP responses matching the API contract.

Use `handle()` when handling both the result and exceptions:

```java
future.handle((result, error) -> {
    if (error != null) {
        throw new CompletionException(error);
    }

    return result;
});
```

### 8.2. Combining Multiple Tasks

Independent queries can run in parallel:

```java
CompletableFuture<List<CustomerSummary>> customers =
    customerRepository.findSummariesAsync(CustomerStatus.ACTIVE);

CompletableFuture<List<OrderSummary>> orders =
    orderRepository.findRecentSummariesAsync();

CompletableFuture<DashboardResponse> dashboard =
    customers.thenCombine(orders, DashboardResponse::new);
```

Both queries can run concurrently on the executor, though doing so increases connection usage and database load. Only parallelize when tasks are independent and the database has spare capacity.

If steps depend on one another's results, use `thenCompose` to chain Futures rather than blocking threads with `get()` or `join()`.

### 8.3. Timeouts and Cancellation

Callers can set wait timeouts using CompletableFuture APIs or HTTP-layer timeouts. However, a caller timeout does not necessarily stop the SQL statement executing in the database.

Distinguish:
- Future wait timeout.
- Query timeout configured for JPA/provider/database.
- HTTP request timeout.
- Future cancellation.
- The database actually canceling the statement.

If query execution time must be bounded, configure an appropriate query timeout and verify whether the driver/database enforces it. Do not assume `future.cancel(true)` always cancels the JDBC statement or immediately rolls back the worker transaction.

### 8.4. Async Methods Returning void

A `@Async` method returning `void` has no Future for the caller to observe outcomes. Exceptions cannot be returned to the caller like a Future; Spring uses `AsyncUncaughtExceptionHandler` for this case.

For work whose success or failure must be tracked, return `CompletableFuture<T>` or persist durable job state in a database/job system.

## 9. Integrating with Spring MVC

Spring MVC supports asynchronous return types such as `CompletableFuture`. Example:

```java
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerRepository repository;

    public CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/search")
    public CompletableFuture<List<CustomerSummary>> search(
        @RequestParam String status
    ) {
        return repository.findSummariesAsync(
            CustomerStatus.valueOf(status)
        );
    }
}
```

Spring MVC can keep the request in async mode within the Servlet container and complete the response when the Future finishes. The initial Servlet request thread can be released while the worker thread executes the query.

This does not mean the overall request uses zero threads. A worker thread is still held while JDBC blocks; once the Future completes, MVC resumes processing to write the response.

For async errors, use appropriate Spring MVC exception handling such as `@ControllerAdvice` and check how exceptions are unwrapped from CompletionException/ExecutionException in your framework version.

Do not call `future.get()` in the controller and return a synchronous result. That blocks the request thread again.

## 10. @Async Does Not Make Spring Data JPA Reactive

### 10.1. JPA Still Uses Blocking JDBC

Spring Data JPA relies on a JPA provider, usually Hibernate, and a JDBC driver. When invoking a query, the JDBC thread waits for the database to execute and return data. `@Async` only decides which thread runs the call.

Therefore:
- A slow query remains slow.
- Each concurrent query still consumes a connection while accessing the database.
- Adding more workers can raise throughput up to a point, after which it overloads the database.
- Large thread pools do not replace SQL, index, and fetch-plan optimization.

### 10.2. Do Not Use Flux/Mono as If JPA Were Reactive

Spring Data JPA does not provide true reactive repository execution over JPA. You cannot merely change a return type from `List<T>` to `Flux<T>` to turn a Hibernate/JDBC query into non-blocking I/O.

If end-to-end reactive access is needed, use:
- Spring WebFlux for the reactive web stack.
- Spring Data R2DBC for relational database access using a supported reactive driver.
- Reactive clients for downstream services.

If JPA must be called from WebFlux, it remains a blocking call. Isolate blocking work onto a suitable bounded elastic/scheduler and control concurrency; better yet, avoid mixing blocking JPA onto event-loop threads.

### 10.3. Choosing Technology by Need

| Need | Suitable choice |
|---|---|
| Standard JPA query within a request | Synchronous repository |
| Let request thread continue while blocking query runs | @Async + CompletableFuture |
| Background tasks needing retries, state, and restart recovery | Job queue or message broker |
| End-to-end reactive database access | Spring Data R2DBC with a reactive driver |
| Very large imports/exports | Batch processing, JDBC batching, or database bulk tools |

## 11. Limiting Load and Protecting the Database

### 11.1. Async Can Increase Concurrency

If an endpoint receives 1,000 requests in a short burst and each dispatches an async query, the executor only bounds active workers; the rest can sit in the queue. If the queue is too large, latency climbs and the heap retains many tasks.

You should:
- Set reasonable core/max pool sizes.
- Set a bounded queue capacity.
- Enforce max page sizes and bound query inputs.
- Apply API rate limits or concurrency limits where needed.
- Monitor queue depth, active threads, rejected tasks, and wait times.
- Cap the number of concurrent queries hitting the database.

### 11.2. Handling Rejected Tasks

When the executor is out of workers and the queue is full, Spring may throw `TaskRejectedException`. Translate this error into an appropriate response or route the work to a durable job system.

Avoid blindly using `CallerRunsPolicy` for JPA queries: this policy can run tasks directly on the caller thread, blocking the very request intended to be async. If choosing this policy, understand it is deliberate backpressure.

### 11.3. Observing the Executor and Database

Monitor at minimum:
- Active worker threads.
- Queue size and rejected task counts.
- Task wait time before execution.
- Query duration and connection acquisition time.
- Active/idle connections in the pool.
- Database CPU, locks, slow queries, and timeouts.
- Number of pending Futures awaiting completion.

If the executor has many threads waiting for connections, increasing maxPoolSize usually will not fix the problem. Look for the bottleneck in the connection pool or database.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| @Async method still runs synchronously | @EnableAsync missing or self-invocation | Enable async support and call through a Spring proxy/another bean |
| Caller still blocks | Calling Future.get()/join() immediately | Return Future or compose callbacks |
| Async query misses newly saved data | Worker runs before caller transaction commits | Trigger after commit via event/outbox |
| LazyInitializationException | Returning entity with unloaded associations across transaction boundary | Return DTOs or fetch data inside worker transaction |
| Transaction is not shared | Imperative transactions are thread-bound | Open a dedicated transaction on the worker thread |
| Database overloaded | Pool/queue permits too many concurrent queries | Cap concurrency and size against connection pool |
| Tasks rejected | Executor out of workers and queue space | Handle TaskRejectedException, tune capacity/backpressure |
| Exceptions ignored | Method returns void or Future is unobserved | Return CompletableFuture and handle exceptional completion |
| Future canceled but SQL still runs | Cancellation does not guarantee canceling the JDBC statement | Configure query timeout and verify driver behavior |
| WebFlux stalls | Calling blocking JPA on event-loop threads | Isolate blocking work or use R2DBC |

## 13. Testing Async Queries

### 13.1. Verifying Results and Exceptions

You can use integration tests with a real Spring context to ensure `@EnableAsync`, the executor, and repository proxies are configured:

```java
@SpringBootTest
class CustomerAsyncRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void returnsAsyncQueryResult() throws Exception {
        CompletableFuture<List<CustomerSummary>> future =
            repository.findSummariesAsync(CustomerStatus.ACTIVE);

        List<CustomerSummary> result =
            future.get(5, TimeUnit.SECONDS);

        assertThat(result).isNotNull();
    }
}
```

Test timeouts only limit how long the test waits; they do not guarantee the database query is canceled when the timeout expires. Tests need clear data fixtures and appropriate transaction setups.

### 13.2. Verifying the Executing Thread

To verify the method runs on the executor, you can record the thread name inside the worker or use a test probe. A thread name prefix such as `jpa-query-` makes observation easier.

Do not verify merely by calling a method inside the same class because self-invocation bypasses the proxy. Tests must invoke beans injected from the Spring context.

### 13.3. Verifying Transactions and Lazy Loading

Tests should confirm:
- Queries execute inside a worker transaction when needed.
- DTOs contain complete data after the Future finishes.
- No lazy proxy access occurs after the transaction closes.
- Database exceptions propagate through the Future.
- The executor rejects tasks under overload according to the chosen policy.
- Concurrent tasks do not exceed expected bounds.
- Application shutdown handles in-flight tasks according to configured policy.

Use the same database engine as production for tests depending on dialects, locks, or transaction behavior. H2 is handy for fast tests but does not replace full integration testing.

## 14. Pre-Use Checklist for @Async with JPA

- [ ] `@EnableAsync` is enabled.
- [ ] Methods are invoked via Spring proxies, not self-invocation.
- [ ] Methods return appropriate `Future` or `CompletableFuture`.
- [ ] A named executor with clear bounds is configured.
- [ ] Pool size/queue capacity align with the connection pool and database.
- [ ] Queries have transaction boundaries on the worker thread when needed.
- [ ] Caller transactions are not assumed to propagate to workers.
- [ ] EntityManager or managed entities are never passed across threads.
- [ ] DTOs/projections include all required data before the transaction closes.
- [ ] Exceptions, timeouts, cancellation, and task rejection are handled.
- [ ] Callers do not block immediately with get()/join().
- [ ] Metrics exist for the executor, connection pool, and query latency.
- [ ] Verified that @Async only moves blocking JPA onto another thread.
- [ ] If reactive non-blocking is needed, R2DBC has been evaluated instead of changing JPA return types.

## 15. Conclusion

`@Async` lets Spring execute repository queries or service methods on a TaskExecutor and return results via `Future`/`CompletableFuture`. For it to work, enable `@EnableAsync`, invoke methods via proxies, and configure a bounded executor. It is useful for separating blocking queries from request threads or running independent tasks concurrently.

JPA/JDBC remains blocking. Caller transactions do not automatically propagate to worker threads; workers need their own transactions. EntityManager is not thread-safe and entities with lazy associations can become detached after a transaction ends, so DTOs/projections are usually a more suitable return type.

Async does not speed up SQL and can increase database load if pools/queues are oversized. Tune concurrency alongside the connection pool, handle errors and timeouts explicitly, and measure queue/query latency. When genuine non-blocking database access is required, choose a reactive stack such as Spring Data R2DBC with a compatible driver rather than treating `@Async` as reactive JPA.
