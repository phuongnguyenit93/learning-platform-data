# Choosing Synchronous or Reactive Data APIs by Processing Flow

Spring Boot can access the same data stores using either **synchronous (imperative/blocking)** or **asynchronous/reactive (non-blocking)** APIs. For example, the Azure Cosmos DB Java SDK v4 provides `CosmosClient` and `CosmosAsyncClient`; Spring Data Cosmos provides `CosmosRepository` and `ReactiveCosmosRepository`. For relational databases, JDBC typically pairs with Spring MVC, while R2DBC pairs with Spring WebFlux. Spring Data Redis likewise provides `RedisTemplate` and `ReactiveRedisTemplate`.

Choose the API across the entire request path: web server, application service, database driver, outbound network calls, and response rendering. Switching only the controller to WebFlux while still calling blocking JDBC underneath does not produce a non-blocking pipeline. Conversely, a Spring MVC application can use an async client in specific places without converting the entire system to reactive.

This lesson belongs to the **Azure Data Services** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services across AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, including identity/permission configuration, storage, messaging, data, secrets, integration testing, and evaluating differences between cloud providers. This lesson uses Azure Cosmos DB, Azure Database for PostgreSQL/MySQL/SQL, and Redis to illustrate how to choose the right API.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish synchronous, asynchronous, non-blocking, and reactive programming.
- Choose Spring MVC + JDBC/JPA or WebFlux + R2DBC based on real workload and dependencies.
- Choose `CosmosClient` vs. `CosmosAsyncClient`, and `CosmosRepository` vs. `ReactiveCosmosRepository`.
- Choose `RedisTemplate` vs. `ReactiveRedisTemplate` with Lettuce.
- Build `Mono`/`Flux` flows without blocking the event loop while respecting backpressure.
- Identify bugs from using `block()`, `subscribe()`, or JDBC inside WebFlux.
- Distinguish imperative transactions from reactive transactions.
- Test and benchmark both models under identical workloads.

## 2. Clarifying Four Concepts

These terms are related but not synonymous:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Synchronous** | Caller waits for the call to return a result before continuing | `repository.findById(id)` returning `Optional<T>` |
| **Asynchronous** | Result completes later; caller receives a callback/future/publisher | `CompletableFuture<T>`, `Mono<T>` |
| **Non-blocking I/O** | Thread does not wait idle on network I/O; completion is signaled when data arrives | Netty, R2DBC, `CosmosAsyncClient` |
| **Reactive Streams** | Publisher/Subscriber model with demand/backpressure, typically expressed via `Mono`/`Flux` | `ReactiveCrudRepository` |

An async API is not automatically reactive. For example, `CompletableFuture` is async without the Reactive Streams backpressure protocol. Nor does returning a `Mono` guarantee non-blocking execution inside: if a method calls JDBC or `Thread.sleep`, it still blocks the executing thread.

**Reactive does not mean parallel.** Reactor can execute a pipeline sequentially on one thread, switch threads when instructed, and manage demand. Running multiple tasks concurrently requires explicit concurrency design.

## 3. Threading Models: Spring MVC vs. Spring WebFlux

### 3.1. Spring MVC with Blocking APIs

Spring MVC runs on the Servlet stack. Each request is typically handled on a worker thread; if a database query takes 100 ms, that worker thread waits during the I/O duration. The thread pool can scale up to serve many waiting requests, though each thread and in-flight request consumes resources.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as MVC worker thread
    participant DB as Database
    C->>W: HTTP request
    W->>DB: JDBC query
    Note over W,DB: Worker thread waits for I/O
    DB-->>W: Result
    W-->>C: HTTP response
~~~

This model is straightforward and suits JDBC/JPA, imperative transactions, and most moderate-load CRUD applications. When a database call blocks, thread waiting is the expected behavior of the model.

### 3.2. Spring WebFlux with Non-Blocking APIs

WebFlux typically runs on Netty with a small set of event-loop threads. When issuing a query via R2DBC or the Cosmos async API, the event loop does not wait on the socket response; the thread can serve other requests while I/O is pending. Once data returns, the pipeline resumes:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant E as WebFlux event loop
    participant DB as Non-blocking driver
    C->>E: HTTP request
    E->>DB: Start async query
    Note over E,DB: Event loop is free while I/O is pending
    DB-->>E: Publisher emits result
    E-->>C: HTTP response
~~~

WebFlux fits when most of the request path can stay non-blocking, many concurrent requests wait on I/O, or the app streams data or composes multiple remote services. Reactive/non-blocking does not necessarily make a single isolated request run faster; the primary gain is more efficient thread and memory usage under high I/O-latency concurrency.

Spring Framework recommends Spring MVC for architectures built around blocking persistence like JPA/JDBC. You can run blocking APIs in WebFlux on a dedicated scheduler, but doing so gives up full non-blocking benefits and requires sizing thread pools for those blocking segments.

## 4. Selection Rule: Inspect the Entire Pipeline

Do not decide based solely on controller style or library names. List every I/O operation on a request:

~~~text
HTTP request
  -> application service
  -> database query
  -> Redis cache
  -> HTTP call to another service
  -> serialize response
~~~

If the database uses blocking JDBC, Redis uses blocking APIs, and HTTP clients are blocking, Spring MVC is usually the simpler, more consistent choice. If the database uses R2DBC, Redis uses the reactive template, and HTTP calls use `WebClient`, WebFlux can keep the pipeline non-blocking end to end.

| Scenario | Starting Choice |
| --- | --- |
| Standard CRUD, JDBC/JPA, SQL transactions | Spring MVC + JDBC/JPA |
| Spring Data Cosmos sync repository, moderate throughput | Spring MVC + `CosmosRepository` |
| High I/O concurrency waiting on network, reactive drivers available | Spring WebFlux + R2DBC/`ReactiveCosmosRepository` |
| Cosmos DB needing high throughput with an existing Reactor pipeline | `CosmosAsyncClient` or `ReactiveCosmosRepository` |
| Redis used inside a WebFlux pipeline | `ReactiveRedisTemplate` |
| Batch jobs where imperative control flow is clearer | Sync or async API depending on throughput and concurrency limits |
| Blocking dependencies that cannot yet be replaced | Keep MVC or isolate blocking calls on a dedicated scheduler |

Also weigh driver maturity, transaction support, debuggability, team experience, and migration cost. Never rewrite an entire system to reactive just to change a few repository methods.

## 5. Azure Data API Matrix

| Service | Imperative/Sync API | Async/Reactive API | Key Notes |
| --- | --- | --- | --- |
| **Azure Cosmos DB for NoSQL** | Java SDK `CosmosClient`; Spring Data `CosmosRepository` | Java SDK `CosmosAsyncClient`; Spring Data `ReactiveCosmosRepository` | SDK v4 includes both APIs; Async uses Reactor and non-blocking I/O |
| **Azure Database for PostgreSQL** | PostgreSQL JDBC; Spring Data JDBC/JPA | R2DBC PostgreSQL; Spring Data R2DBC | Driver and TLS/auth configuration differ from JDBC |
| **Azure Database for MySQL** | MySQL Connector/J; Spring Data JDBC/JPA | R2DBC MySQL; Spring Data R2DBC | Uses a separate R2DBC driver, not Connector/J |
| **Azure SQL Database** | Microsoft JDBC Driver; Spring Data JDBC/JPA | R2DBC SQL Server (`r2dbc-mssql`) | JDBC authentication modes do not automatically carry over to R2DBC |
| **Azure Redis** | `RedisTemplate`, `StringRedisTemplate` | `ReactiveRedisTemplate`, `ReactiveStringRedisTemplate` | Both can use Lettuce; pick template to match pipeline |

This is a matrix of common libraries, not a guarantee of feature parity between sync and async APIs. Verify transactions, bulk operations, streaming, authentication, and version support for each specific driver before choosing.

## 6. Azure Cosmos DB: Sync API vs. Async API

### 6.1. Two Clients in Java SDK v4

The Azure Cosmos DB Java SDK v4 provides two clients:

- `CosmosClient` exposes the synchronous/blocking API.
- `CosmosAsyncClient` exposes the asynchronous API built on Project Reactor and Netty.

SDK v4 shares a single Maven artifact `com.azure:azure-cosmos`. The Sync API is essentially a blocking wrapper around the Async API. Choose the API when constructing the client; do not grab a `CosmosAsyncClient` expecting synchronous return types or vice versa.

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.CosmosAsyncClient;

// Imperative/blocking
CosmosClient syncClient = new CosmosClientBuilder()
    .endpoint(endpoint)
    .key(key)
    .buildClient();

// Asynchronous/reactive
CosmosAsyncClient asyncClient = new CosmosClientBuilder()
    .endpoint(endpoint)
    .key(key)
    .buildAsyncClient();
~~~

In production, use appropriate credentials such as Managed Identity/`TokenCredential` per your application's security setup. This snippet only highlights client construction differences; never store account keys in source code.

### 6.2. When to Choose the Sync API?

The Sync API fits when:

- Application services and controllers follow an imperative model.
- Throughput is not the primary bottleneck and sequential request/response logic is easier to follow.
- Most other dependencies are blocking.
- The team prioritizes straightforward debugging and imperative transaction/application flows.
- Batch or worker workloads run with controlled concurrency.

Example:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.PartitionKey;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {
    private final CosmosContainer orders;

    public OrderLookupService(CosmosContainer orders) {
        this.orders = orders;
    }

    public OrderDocument find(String id, String tenantId) {
        return orders.readItem(
            id,
            new PartitionKey(tenantId),
            OrderDocument.class
        ).getItem();
    }
}
~~~

The method returns the object directly once the network call completes. In Spring MVC, having the worker thread wait for the result is normal.

### 6.3. When to Choose the Async API?

The Async API fits when:

- High throughput and high request concurrency are needed.
- The pipeline uses WebFlux/Reactor.
- Queries must be composed with Redis, HTTP, or other async operations.
- Results need to be streamed instead of buffered entirely in memory.
- Cancellation/backpressure and bounded pipeline concurrency are desired.

Example:

~~~java
import com.azure.cosmos.CosmosAsyncContainer;
import com.azure.cosmos.models.PartitionKey;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderLookupService {
    private final CosmosAsyncContainer orders;

    public ReactiveOrderLookupService(CosmosAsyncContainer orders) {
        this.orders = orders;
    }

    public Mono<OrderDocument> find(String id, String tenantId) {
        return orders.readItem(
                id,
                new PartitionKey(tenantId),
                OrderDocument.class)
            .map(response -> response.getItem());
    }
}
~~~

The method returns `Mono<OrderDocument>`; callers subscribe through WebFlux or an outer pipeline. Never call `.block()` inside the service just to unwrap the item and return a synchronous object.

### 6.4. Spring Data Cosmos Repositories

Spring Data Cosmos provides two abstractions:

~~~java
import com.azure.spring.data.cosmos.repository.CosmosRepository;

public interface OrderRepository
        extends CosmosRepository<OrderDocument, String> {
}
~~~

~~~java
import com.azure.spring.data.cosmos.repository.ReactiveCosmosRepository;

public interface ReactiveOrderRepository
        extends ReactiveCosmosRepository<OrderDocument, String> {
}
~~~

Sync repositories return imperative types like `Optional<T>`, `List<T>`, or entities; reactive repositories return `Mono<T>`/`Flux<T>`. When configuring multiple repository packages, use `@EnableCosmosRepositories` or `@EnableReactiveCosmosRepositories` pointing to the matching template (`CosmosTemplate` or `ReactiveCosmosTemplate`). Avoid scanning the same package twice and accidentally wiring the wrong template.

### 6.5. Performance Differences

Microsoft describes the Async API as non-blocking I/O and the optimal choice when aiming to saturate provisioned throughput. The Sync API blocks while awaiting responses; throughput can drop as request/response latency increases. Sync remains sensible when the application model is predominantly synchronous and maximum throughput is not the priority.

The Async API does not lower the RU cost of an operation. RUs still depend on queries, partition routing, indexes, and data. Async helps the client utilize resources and dispatch/coordinate requests more efficiently; benchmark with identical queries and throughput settings to compare.

## 7. Relational Databases: JDBC or R2DBC?

### 7.1. JDBC and Spring Data JDBC/JPA

JDBC is a blocking API. Calling `JdbcTemplate.query(...)` or `JpaRepository.findById(...)` blocks the thread until the database returns. This fits Spring MVC naturally.

~~~java
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Imperative service:

~~~java
public Customer findCustomer(long id) {
    return customerRepository.findById(id)
        .orElseThrow(CustomerNotFoundException::new);
}
~~~

JDBC enjoys a mature ecosystem of drivers, pools, transactions, migrations, and monitoring. Unless workloads demand very high I/O concurrency or streaming, MVC + JDBC/JPA is often the practical choice.

### 7.2. R2DBC and Spring Data R2DBC

R2DBC is a non-blocking SPI for relational databases. Spring Data R2DBC provides `ReactiveCrudRepository`, `DatabaseClient`, and a reactive transaction manager. A genuine R2DBC driver is required; a JDBC driver does not become non-blocking by wrapping it in `Mono`.

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface ReactiveCustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
    Flux<Customer> findByStatus(String status);
}
~~~

WebFlux controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class CustomerController {
    private final ReactiveCustomerRepository customers;

    public CustomerController(ReactiveCustomerRepository customers) {
        this.customers = customers;
    }

    @GetMapping("/customers")
    public Flux<Customer> findActiveCustomers() {
        return customers.findByStatus("ACTIVE");
    }
}
~~~

Spring Boot typically configures `ConnectionFactory` from `spring.r2dbc.*`; production should use an appropriate R2DBC pool. Azure provides R2DBC guides for PostgreSQL Flexible Server, MySQL Flexible Server, and Azure SQL Database. Drivers are distinct, for example:

| Database | R2DBC Driver Artifact |
| --- | --- |
| PostgreSQL | `org.postgresql:r2dbc-postgresql` |
| MySQL | `io.asyncer:r2dbc-mysql` |
| SQL Server | `io.r2dbc:r2dbc-mssql` |

Verify driver versions, URL schemes, TLS, authentication, and feature support in the current driver docs. Passwordless JDBC starters do not automatically configure tokens for R2DBC drivers; Entra/Managed Identity support must be verified specifically for your R2DBC driver and version.

Example PostgreSQL R2DBC configuration using a pool URL:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:pool:postgres://${DB_HOST}.postgres.database.azure.com:5432/${DB_NAME}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    properties:
      sslMode: REQUIRE
~~~

This illustrates a PostgreSQL R2DBC driver setup; TLS and authentication properties vary by driver/version. MySQL and SQL Server use different URL schemes and options. Never blindly copy JDBC `spring.datasource.*` properties into `spring.r2dbc.*`.

### 7.3. R2DBC Limitations and Trade-Offs

- Not every JDBC/ORM feature has a reactive equivalent.
- Drivers can differ around stored procedures, batching, generated keys, metadata, isolation levels, and transactions.
- Never run blocking JPA/Hibernate inside a reactive pipeline while assuming the system is non-blocking.
- Size the R2DBC connection pool against database max connections and concurrency; never leave connections unbounded.
- Test TLS, Entra, failover, and reconnection on real Azure; Testcontainers only validates local engines/drivers.

## 8. Redis: `RedisTemplate` or `ReactiveRedisTemplate`?

Spring Data Redis provides both template APIs. Both can run over Lettuce; the difference is the application code contract:

~~~java
// Imperative
String value = stringRedisTemplate.opsForValue().get("product:42");
~~~

~~~java
// Reactive
Mono<String> value =
    reactiveStringRedisTemplate.opsForValue().get("product:42");
~~~

Reactive template:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class ReactiveProductCache {
    private final ReactiveStringRedisTemplate redis;

    public ReactiveProductCache(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> put(String id, String json) {
        return redis.opsForValue().set(
            "product:" + id,
            json,
            Duration.ofMinutes(5));
    }

    public Mono<String> get(String id) {
        return redis.opsForValue().get("product:" + id);
    }
}
~~~

In WebFlux, return the publisher so the framework manages subscription. With Spring MVC/JDBC, `StringRedisTemplate` usually composes more cleanly. Do not call the reactive template and `.block()` in every method just to adapt the return type.

Some Spring Cache APIs and Redis repository abstractions carry imperative contracts; when explicit reactive Redis access is needed, use `ReactiveRedisTemplate` or dedicated reactive APIs. Never assume all Spring Data Redis annotations/repositories automatically become reactive.

## 9. Backpressure and Bounding Concurrency

Reactive Streams gives subscribers the ability to request a specific number of upstream elements. This is **backpressure**: a slow downstream consumer can reduce demand so upstream does not emit unboundedly. However, backpressure only works across supporting publishers/operators; it does not automatically throttle RU/s or bound every queue in the system.

### 9.1. Bounding Concurrency Across Multiple Calls

~~~java
Flux<OrderDocument> orders = orderIds
    .flatMap(
        id -> reactiveOrderRepository.findById(id),
        16
    );
~~~

Here `16` bounds how many inner publishers are subscribed concurrently. Choose concurrency based on connection pools, throughput, RU/s, latency, and downstream capacity. Never run an unbounded `flatMap` over millions of IDs expecting Reactor to protect the database automatically.

For large streams, consider:

- `limitRate(n)` to pace upstream demand in batches.
- `buffer(n)` when batching items, keeping in mind that buffers consume memory.
- `concatMap` when strict sequential order is required.
- `flatMapSequential` when concurrent execution with ordered output is needed.
- `onBackpressureBuffer` only with explicit capacity bounds and overflow strategies.

### 9.2. Streaming Database Results

`Flux<T>` can emit items incrementally so WebFlux writes responses progressively. This avoids buffering an entire result set on the heap, though drivers/databases do not always stream row-by-row immediately. R2DBC drivers have their own fetch sizes/buffering; Cosmos queries paginate via continuations and RUs; Redis commands generally return compact results.

Never expose an unbounded `Flux` of an entire database over an HTTP endpoint. Enforce filters, pagination, max result caps, timeouts, and concurrency limits. For public APIs, cursor/pagination is usually safer and easier to govern than unbounded streams.

## 10. Never Block the Event Loop

In WebFlux, event-loop threads must return promptly. The following operations can block:

- JDBC/JPA queries.
- `Thread.sleep`, blocking file I/O, or blocking HTTP client calls.
- `Mono.block()`, `Flux.blockLast()`, `toIterable()`.
- Long-running CPU-intensive work on I/O threads.

Incorrect example:

~~~java
@GetMapping("/customers/{id}")
public Mono<Customer> find(@PathVariable long id) {
    Customer customer = jdbcCustomerRepository.findById(id)
        .orElseThrow(CustomerNotFoundException::new);
    return Mono.just(customer);
}
~~~

The controller returns a `Mono`, yet the JDBC query already ran synchronously before creating the publisher. The request still blocks the event loop.

### 10.1. Best Approach: Use a Reactive Driver

Replace JDBC with R2DBC or use the data service's async client:

~~~java
@GetMapping("/customers/{id}")
public Mono<Customer> find(@PathVariable long id) {
    return reactiveCustomerRepository.findById(id);
}
~~~

### 10.2. Temporary Bridge for Blocking APIs

If the driver cannot be replaced yet, isolate blocking calls on the bounded elastic scheduler:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<Customer> findCustomer(long id) {
    return Mono.fromCallable(() -> jdbcCustomerRepository.findById(id)
            .orElseThrow(CustomerNotFoundException::new))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

This is a **bridge** to keep the event loop unblocked; JDBC itself remains blocking and needs a bounded thread pool. Monitor queue depth, thread usage, timeouts, and the database connection pool. If most requests rely on this bridge, consider switching back to Spring MVC or investing in R2DBC instead of scaling `boundedElastic` endlessly.

## 11. Never Call `.subscribe()` Inside Application Services

A publisher describes work; it executes only upon subscription. In request flows, WebFlux subscribes to the publisher returned by the controller. If a service calls `.subscribe()` manually:

~~~java
public void createOrder(Order order) {
    reactiveOrderRepository.save(order).subscribe();
}
~~~

the service detaches the work from the request lifecycle. Callers do not know when saving finishes, exceptions may bypass HTTP error handlers, transaction context does not propagate, and tests become difficult to verify.

Return the publisher instead:

~~~java
public Mono<Order> createOrder(Order order) {
    return reactiveOrderRepository.save(order);
}
~~~

Only call `.subscribe()` at intentional application boundaries, such as startup/background processes with their own lifecycle, error handlers, and shutdown policies. Never use it to "trigger" a repository call inside a controller/service.

## 12. Transactions: Imperative vs. Reactive

### 12.1. Imperative Transactions

JDBC/JPA typically uses `PlatformTransactionManager`. `@Transactional` binds a transaction to the current thread; repositories sharing the same transaction manager/`DataSource` join that transaction:

~~~java
@Transactional
public Order createOrder(Order order) {
    Order saved = jdbcOrderRepository.save(order);
    auditRepository.record("ORDER_CREATED", saved.id());
    return saved;
}
~~~

### 12.2. Reactive Transactions

R2DBC uses `ReactiveTransactionManager` (commonly `R2dbcTransactionManager`). Transaction context attaches to the Reactor subscriber `Context`, rather than `ThreadLocal` as in imperative transactions. The method must return the publisher so the transaction wraps the entire reactive chain:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderService {
    private final ReactiveOrderRepository orders;
    private final ReactiveAuditRepository audit;

    public ReactiveOrderService(
            ReactiveOrderRepository orders,
            ReactiveAuditRepository audit) {
        this.orders = orders;
        this.audit = audit;
    }

    @Transactional
    public Mono<Order> create(Order order) {
        return orders.save(order)
            .flatMap(saved ->
                audit.record("ORDER_CREATED", saved.id())
                    .thenReturn(saved));
    }
}
~~~

This requires both repositories to use the same R2DBC `ConnectionFactory` and reactive transaction manager. Never call `.subscribe()` or `.block()` inside the method; terminating the publisher outside the transaction interceptor breaks transaction scoping.

Reactive transactions do not automatically create distributed transactions across PostgreSQL, Cosmos DB, Redis, Blob Storage, or Service Bus. Coordinating multiple independent resources still requires outbox/sagas/idempotency along service boundaries.

### 12.3. Do Not Mix Two Transaction Managers

If an app uses both JDBC and R2DBC, it usually has two separate connection factories and two transaction managers. A single `@Transactional` does not span both. Pick one datastore as the transactional source of truth for the business operation and coordinate the rest via outbox/sagas or an appropriate design.

## 13. Error Handling, Timeouts, and Retries

Reactive pipelines offer error-handling operators:

~~~java
return reactiveOrderRepository.findById(id)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
    .timeout(Duration.ofSeconds(2))
    .onErrorMap(TimeoutException.class,
        error -> new OrderLookupTimeoutException(id, error));
~~~

Place timeouts at the right boundaries: query timeouts, HTTP deadlines, pool acquire timeouts, and request deadlines serve different purposes. A controller timeout does not necessarily cancel every downstream operation; verify driver cancellation support.

Retries apply only to transient errors and idempotent semantics:

- Retrying reads is usually safe regarding side effects, though data may change between reads.
- Retrying creates/updates requires idempotency keys, ETag/versions, or unique constraints.
- Never retry validation, authentication, authorization, or schema errors as transient network faults.
- Use backoff + jitter, bounding attempts and total deadline.
- Avoid stacking simultaneous retries across controller, service, SDK, and gateway without a shared retry budget.

With Cosmos DB, async vs. sync does not change RU charges, partition keys, or consistency guarantees. With Redis, timing out after `INCR` leaves an ambiguous outcome; blind retries can increment twice.

## 14. Client and Resource Lifecycles

Cloud clients typically carry initialization and connection-management costs:

- Share a single `CosmosClient` or `CosmosAsyncClient` across the application lifecycle; the SDK recommends singleton/thread-safe clients.
- Use Spring-managed `RedisConnectionFactory` and Lettuce clients; never create a connection factory per request.
- R2DBC uses a connection pool sized to database limits.
- Close clients, pools, and subscriptions when the `ApplicationContext` shuts down.
- Never create a `Mono` and leave it dangling without subscribing or disposing.

Reactive does not eliminate the need for connection pools. An undersized pool stalls publishers waiting for connections; an oversized pool exhausts database connections. Monitor active/idle/pending connections, acquisition latency, query duration, and retry counts.

## 15. Testing

| Goal | Tool / Strategy |
| --- | --- |
| Verify items, errors, and completion signals | Reactor `StepVerifier` |
| Test WebFlux endpoints | `WebTestClient` |
| Test JDBC/R2DBC SQL and migrations | Testcontainers PostgreSQL/MySQL/SQL Server |
| Test Redis templates/caches | Testcontainers Redis or Redis container |
| Test Cosmos repositories/SDK | Cosmos DB Emulator and Azure test account |
| Test cancellation/backpressure | `StepVerifier` demand, cancellation, and large-stream tests |
| Test transaction rollback | Integration tests with the exact transaction manager/driver |
| Compare throughput/latency | Load tests using identical datasets, queries, RUs, pools, and hardware |

`StepVerifier` example:

~~~java
StepVerifier.create(service.findById("order-42"))
    .expectNextMatches(order -> order.id().equals("order-42"))
    .verifyComplete();
~~~

Do not test only the happy-path result. For reactive flows, also verify:

- Does the publisher emit the expected error types?
- Are empty results mapped properly?
- Does cancellation stop downstream requests?
- Does backpressure cap buffered data?
- Does the transaction roll back when the second step fails?
- Are there any blocking calls on the event loop?

## 16. Fair Benchmarking

To make data-driven decisions, compare both implementations under identical workloads:

1. Same Azure region, database tier, RU/s/throughput, and dataset.
2. Same queries, partition keys, indexes, and consistency levels.
3. Same client count and request arrival rate.
4. Same connection pool limits or equivalent resource budgets.
5. Warm up before recording metrics.
6. Run multiple iterations, capturing p50/p95/p99 and error rates.

Measure:

| Metric | Meaning |
| --- | --- |
| Throughput (requests/s) | Completed requests per unit of time |
| p50/p95/p99 latency | User-perceived latency, especially at the tail |
| CPU/memory | Processing and buffering overhead |
| Thread count / event-loop saturation | Thread utilization and blocking risk |
| Connection pool pending / acquire time | Pool contention bottlenecks |
| RU/query and 429s | Cost and throttling in Cosmos DB |
| Retries/timeouts/cancellations | Stability under high load or slow backends |

Reactive can improve throughput when many requests wait on I/O, yet if the bottleneck is RU/s, query scans, CPU serialization, or database connection limits, changing APIs will not fix it. Never benchmark using average request rates alone; inspect p95/p99 and resource usage.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling JDBC directly on WebFlux's event loop | Blocks event loop, drops server-wide throughput | Use R2DBC or a bounded blocking bridge |
| Calling `.block()` in reactive controllers/services | Blocks threads and risks deadlocks/latency spikes | Compose with `map`, `flatMap`, `zip` |
| Calling `.subscribe()` in services | Loses error/request/transaction context | Return `Mono`/`Flux` to callers |
| Assuming async is always faster than sync | Adds complexity without fixing real bottlenecks | Benchmark and choose per workload |
| Assuming reactive means parallel | Unexpected race conditions or concurrency | Bound `flatMap` and use operators matching semantics |
| Using unbounded `flatMap` | Overloads pools/DB/RUs | Configure concurrency limits and backpressure |
| Wrapping JDBC in `Mono.just(jdbcCall())` | JDBC runs before the publisher is even built | Use R2DBC or temporary `fromCallable` + `boundedElastic` |
| Using JDBC transaction manager for R2DBC | Reactive transactions lack proper context binding | Use `R2dbcTransactionManager` |
| Assuming Cosmos Async lowers RUs | Inaccurate cost estimates | RUs depend on queries/data/indexes, not API style |
| Copying JDBC URL/TLS/auth into R2DBC drivers | Connection failures or weak security | Follow the specific driver's documentation |
| Rewriting the whole system to reactive for one async client | Higher operational cost and complexity | Keep MVC and isolate the async boundary if appropriate |

## 18. Decision Workflow

~~~mermaid
flowchart TD
    A[List all I/O in a request] --> B{Do most dependencies have non-blocking drivers?}
    B -->|No| C{Can drivers be replaced or blocking isolated?}
    C -->|No| D[Spring MVC + imperative API]
    C -->|Yes| E[Evaluate WebFlux + reactive pipeline]
    B -->|Yes| E
    E --> F{Clear need for concurrency/streaming/backpressure?}
    F -->|No| G[Compare complexity against MVC]
    F -->|Yes| H[WebFlux + Mono/Flux]
    G --> I[Benchmark and verify transactions]
    H --> I
    D --> I
    I --> J[Choose by p95, throughput, resources, and maintainability]
~~~

Ask in sequence:

1. Are database/cache/HTTP/file calls on the request blocking or non-blocking?
2. Does the workload involve many concurrent requests waiting on I/O?
3. Is streaming data or bounded demand required?
4. Do the reactive drivers fully support all required features?
5. Do transactions stay within one resource or span multiple services?
6. Can the team operate Reactor, backpressure, schedulers, and reactive debugging?
7. Do benchmarks demonstrate measurable gains in p95/throughput/CPU/memory?

If there is no measurable benefit or key dependencies remain blocking, keeping the imperative model usually reduces complexity.

## 19. Practice Exercises

**Exercise 1 — Same use case, two Cosmos APIs.** Build one order-lookup endpoint using `CosmosRepository` in Spring MVC and another using `ReactiveCosmosRepository` in WebFlux. Measure latency and thread usage as concurrency scales.

**Exercise 2 — R2DBC.** Build a reactive CRUD API on Azure Database for PostgreSQL with Spring Data R2DBC. Verify TLS, connection pooling, `ReactiveCrudRepository`, and `WebTestClient`.

**Exercise 3 — Sync/reactive Redis.** Implement the same cache service with `StringRedisTemplate` and `ReactiveStringRedisTemplate`. Test TTL, timeouts, error handling, and cache misses.

**Exercise 4 — Detecting blocking.** Call `JdbcTemplate` from a WebFlux controller and inspect the event-loop thread. Fix it with R2DBC, then compare against a `boundedElastic` bridge.

**Exercise 5 — Backpressure.** Build a `Flux` reading many Cosmos items using `flatMap` concurrency of 4, 16, and 64. Record throughput, RUs, 429s, memory, and p95.

**Exercise 6 — Transactions.** Write an R2DBC service performing two writes inside `@Transactional`. Intentionally fail the second step and verify rollback. Then add a JDBC repository and demonstrate that one transaction manager does not cover both.

**Exercise 7 — Cancellation.** Use `StepVerifier` to cancel a subscription mid-stream on a query. Verify whether the driver stops reading/releases resources and note limitations if cancellation only halts downstream emission.

**Exercise 8 — Decision benchmark.** Run identical workloads with MVC+JDBC and WebFlux+R2DBC. Compare p50/p95/p99, throughput, CPU, memory, thread counts, pending pool waits, and errors. Write a recommendation documenting trade-offs.

## 20. Key Takeaways

- **Sync/async** describes how callers receive results; **blocking/non-blocking** describes thread behavior during I/O; **reactive** adds Publisher/Subscriber and backpressure.
- Spring MVC pairs naturally with JDBC/JPA and imperative services. WebFlux pays off when most of the pipeline uses non-blocking APIs.
- Cosmos DB Java SDK v4 offers `CosmosClient` (sync) and `CosmosAsyncClient` (Reactor async); Spring Data Cosmos offers `CosmosRepository` and `ReactiveCosmosRepository`.
- PostgreSQL/MySQL/SQL can use R2DBC with dedicated drivers; a JDBC driver does not become non-blocking by wrapping it in `Mono`.
- Redis provides `RedisTemplate` and `ReactiveRedisTemplate`; match the contract to your stack and never assume all Spring Cache/repository APIs are reactive.
- Never call `.block()` or `.subscribe()` inside reactive application services. Return publishers and compose with operators.
- Reactive transactions use `ReactiveTransactionManager` and Reactor Context; they do not span JDBC, Cosmos, Redis, or brokers.
- Configure backpressure/concurrency intentionally; measure p95/p99, pools, RUs, 429s, memory, and threads instead of watching requests/second alone.
- Choose APIs by workload and benchmarks; reactive is a tool for managing I/O concurrency, not an end in itself.

## 21. References

- [Spring Framework — Spring WebFlux overview and concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Framework — Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [Spring Data R2DBC reference](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)
- [Spring Data Redis — Reactive and imperative templates](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Azure Cosmos DB Java SDK v4 — Sync and Async API performance tips](https://learn.microsoft.com/en-us/azure/cosmos-db/performance-tips-java-sdk-v4-sql)
- [Azure Cosmos DB Java SDK v4 — client library](https://learn.microsoft.com/en-us/java/api/overview/azure/cosmos-readme?view=azure-java-stable)
- [Azure Spring Data Cosmos — CosmosRepository and ReactiveCosmosRepository](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-data-cosmos-readme?view=azure-java-stable)
- [Azure Cosmos DB Developer Guide for Java](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/how-to-guides-spring-data-cosmosdb)
- [Use Spring Data R2DBC with Azure Database for PostgreSQL](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-data-r2dbc-with-azure-postgresql)
- [Use Spring Data R2DBC with Azure Database for MySQL](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-data-r2dbc-with-azure-mysql)
- [Use Spring Data R2DBC with Azure SQL Database](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-data-r2dbc-with-azure-sql-server)
- [Reactor Reference Guide — Backpressure](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html)
