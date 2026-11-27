# When to Use R2DBC and When to Consider JDBC

Both R2DBC and JDBC allow Java applications to work with relational databases. The biggest difference lies in how the program waits for results from the database:

- **JDBC** uses a synchronous, blocking model. The calling thread typically waits until the SQL statement completes before continuing.
- **R2DBC** provides a reactive, non-blocking database access API. The application receives results as a publisher and can continue processing when the I/O operation completes.

Therefore, choosing between R2DBC and JDBC is a decision about execution architecture, control flow organization, transactions, and library ecosystems. R2DBC is not the default choice for every application, nor does it automatically make SQL statements run faster.

## 1. Understanding JDBC, R2DBC, and Spring Data Relational

### JDBC: Synchronous Data Access API

JDBC is Java's long-standing standard API for connecting to and working with relational databases. When calling a method like `executeQuery()`, the execution thread is usually held while the driver sends the statement, waits for the database to process it, and receives the results.

For example, with Spring Data JDBC, a repository typically returns an object, `Optional`, `Iterable`, or `List`:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByStatus(String status);
}
```

The call `findByStatus("ACTIVE")` completes synchronously: when the method returns, the results have already been fetched and can be used immediately.

### R2DBC: Reactive Data Access API

R2DBC stands for *Reactive Relational Database Connectivity*. It is an SPI (Service Provider Interface) for relational database drivers capable of supporting non-blocking I/O. Spring Data R2DBC builds data mapping and repository utilities on top of this SPI.

In Spring Data R2DBC, repositories typically return Reactor types:

- `Mono<T>` represents a result that may emit zero or one value.
- `Flux<T>` represents a sequence of zero, one, or many results.

Example:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);
}
```

Calling `findByStatus("ACTIVE")` returns a `Flux<Customer>`. The publisher describes the data retrieval process; results are emitted when the publisher is subscribed to and the asynchronous operation completes. Consequently, you compose publishers in a pipeline instead of assuming data is immediately available right after calling the repository.

### Non-Blocking Does Not Mean No Waiting

The application still has to wait for the database to process the query. The difference is that while waiting for I/O, a non-blocking model can free the thread to handle other work instead of keeping one thread blocked per pending operation.

Reactive Streams also includes backpressure so the consumer can regulate the rate at which data is emitted. Actual streaming capabilities, how the driver fetches partial results, and specific backpressure support still depend on the driver and database.

## 2. When Should You Choose R2DBC?

R2DBC fits best when an application has a clear reason to build an end-to-end reactive processing flow.

### 2.1. The Application Already Uses WebFlux and a Reactive Stack

If controllers, services, and other I/O calls all return `Mono` or `Flux`, Spring Data R2DBC lets database operations participate in that same pipeline.

For example, a request can query the database, call another HTTP service, and combine the results without blocking a thread at each step:

```java
public Mono<CustomerView> getCustomerView(Long id) {
    Mono<Customer> customer = customerRepository.findById(id);
    Mono<Preference> preference = preferenceClient.getPreference(id);

    return Mono.zip(customer, preference)
            .map(tuple -> new CustomerView(tuple.getT1(), tuple.getT2()));
}
```

This example illustrates publisher composition. In a real application, handle cases where a source has no data, fails, or times out according to business requirements.

If an application uses imperative Spring MVC and all services are blocking, converting only the repository to R2DBC rarely provides benefits worth the migration cost. Evaluate the entire request flow before choosing reactive.

### 2.2. High Concurrent I/O and Significant Wait Times

R2DBC is worth considering for services with many concurrent requests where each request frequently waits on the database or other I/O services. Under the right workload, non-blocking I/O can reduce the number of threads held waiting and improve resource utilization.

Common examples:

- API gateways or data aggregation services calling multiple sources.
- Services with many concurrent connections where most request time is spent on I/O.
- Data processing pipelines that coordinate multiple asynchronous operations.
- APIs that need to stream data incrementally instead of waiting for the full result set.

This does not mean R2DBC always achieves higher throughput than JDBC. If the database is already the bottleneck—slow queries, missing indexes, or an overloaded connection pool—changing the data access API will not fix those root causes.

### 2.3. Maintaining Backpressure Through the Pipeline

When data flows through multiple reactive stages, backpressure helps control emission and consumption rates between components. This is helpful in pipelines with multiple asynchronous stages or queries capable of emitting many records.

However, do not assume every R2DBC query streams data row-by-row from the database to the application. Fetching and buffering behavior depends on the driver, configuration, and query type. Check your driver's documentation and measure memory usage with realistic data.

### 2.4. Database and Driver Have Appropriate Support

Before selecting R2DBC, confirm the target database has an R2DBC driver compatible with your version. Verify the capabilities your application actually needs, such as:

- Specialized data types and data mappings.
- SQL statements, functions, stored procedures, or database-specific features.
- Transactions, isolation levels, and locking.
- Connection pooling, timeouts, retries, and error observability.
- Driver stability, maintenance status, and compatibility.

The R2DBC ecosystem offers several useful drivers, though their maturity and feature coverage are not necessarily uniform compared to corresponding JDBC drivers.

## 3. When Should You Consider JDBC?

JDBC is usually the sensible choice when a blocking model fits the application and the JDBC ecosystem meets requirements well.

### 3.1. Application Uses Spring MVC and Imperative Architecture

For traditional Spring MVC applications where services call repositories sequentially and process results directly, JDBC is typically simple, readable, and easy to maintain.

```java
public Customer getCustomer(Long id) {
    return customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
```

There is no need to introduce `Mono` or `Flux` into every layer if the rest of the application is not reactive. A clear synchronous model may be a better fit for the development team and current operations.

### 3.2. No Thread Contention or Scalability Issues

If current load fits comfortably within the thread pool, connection pool, and database capacity, switching to R2DBC can increase complexity without delivering measurable gains.

Stick with JDBC if metrics show the application meets latency, throughput, and resource requirements well. Only change when there is a specific problem that a reactive architecture can solve.

### 3.3. Need the JDBC Ecosystem or Familiar ORM Features

JDBC has a long-standing ecosystem broadly supported by libraries, tools, drivers, and database administration solutions. Consider JDBC when your project relies on:

- Libraries that only expose JDBC APIs or only support blocking calls.
- Tools, drivers, or vendor-specific features lacking equivalent R2DBC support.
- Spring Data JPA/Hibernate with ORM features such as dirty checking, lazy loading, or complex relationship mapping.
- Existing JDBC codebases that are already stable where migration cost outweighs expected benefits.

Note: Spring Data JDBC and Spring Data R2DBC both belong to the Spring Data Relational family, but they are not JPA/Hibernate. Spring Data R2DBC does not provide full ORM features like dirty checking or lazy loading. If the application needs those features, evaluate JPA/Hibernate and JDBC as a separate option.

### 3.4. Existing Transactions and Integrations Are JDBC-Based

Many applications already organize transactions imperatively using `PlatformTransactionManager`, `JdbcTemplate`, Spring Data JDBC, or JPA. If transaction boundaries, libraries, and operational workflows are all JDBC-based, staying with JDBC keeps the architecture consistent.

R2DBC uses a reactive transaction manager and reactive context. Migrating requires rethinking how transactions start, propagate through pipelines, and complete—not just changing repository return types.

## 4. Quick Comparison

| Criterion | R2DBC | JDBC |
| --- | --- | --- |
| I/O model | Reactive, non-blocking when driver supports it | Synchronous, blocking while waiting for I/O |
| Common return types in Spring Data | `Mono<T>`, `Flux<T>` | `T`, `Optional<T>`, `Iterable<T>`, `List<T>` |
| Composing multiple steps | Compose publishers with reactive operators | Sequential calls via standard method invocation |
| Common frameworks | Spring WebFlux and reactive services | Spring MVC and imperative applications |
| Transactions | Reactive transaction manager, reactive context | Platform transaction manager, typically thread-bound |
| Drivers | Requires a dedicated R2DBC driver | Broad, long-standing JDBC driver ecosystem |
| ORM | Spring Data R2DBC maps aggregates; not JPA | Can use Spring Data JDBC, JPA/Hibernate, or JDBC API |
| Complexity | Higher if the team is unfamiliar with reactive programming | Usually more approachable in synchronous apps |
| Performance | Can improve thread efficiency under suitable concurrent I/O load | Simple, performs well for many standard applications |

No row in this table guarantees one technology is always faster. Real-world results depend on queries, database, driver, pool, workload, and implementation.

## 5. Configuration and Repository Examples

### 5.1. Spring Data R2DBC Configuration

With Spring Boot, dependencies typically include the R2DBC starter and the corresponding driver. Example using PostgreSQL with Gradle:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
```

Connection settings can be placed in `application.properties`:

```properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/shop
spring.r2dbc.username=app
spring.r2dbc.password=secret
```

Driver versions should be managed to remain compatible with your project's Spring Boot/Spring Data version. Do not use a `jdbc:...` URL for an R2DBC connection; URLs have a driver-specific scheme, such as `r2dbc:postgresql:...`.

### 5.2. Declaring an Entity and Reactive Repository

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;
    private String status;

    // Constructors, getters, and setters omitted.
}
```

Repository using `ReactiveCrudRepository`:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);

    Mono<Customer> findFirstByName(String name);
}
```

The service preserves reactive types when calling the repository:

```java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Flux<Customer> findActiveCustomers() {
        return repository.findByStatus("ACTIVE");
    }

    public Mono<Customer> create(Customer customer) {
        return repository.save(customer);
    }
}
```

A WebFlux controller can return publishers directly:

```java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<Customer> findActive() {
        return service.findActiveCustomers();
    }

    @PostMapping
    public Mono<Customer> create(@RequestBody Customer customer) {
        return service.create(customer);
    }
}
```

In this pipeline, the controller does not call `.block()` to retrieve data. The framework subscribes and writes the HTTP response reactively.

### 5.3. Same Business Logic with Spring Data JDBC

If the application chooses Spring Data JDBC, dependencies and connection configuration use the JDBC starter and a JDBC DataSource. The repository might look like:

```java
import org.springframework.data.repository.CrudRepository;
import java.util.List;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByStatus(String status);
}
```

The repository call returns data synchronously. The service can process it directly:

```java
public List<Customer> findActiveCustomers() {
    return repository.findByStatus("ACTIVE");
}
```

Both examples share the same business goal, but the repositories, return types, connection configurations, and transaction managers belong to two different stacks. Once a stack is chosen, keep it consistent across application layers.

## 6. Key Differences to Watch When Using R2DBC

### 6.1. Do Not Call `block()` in the Reactive Request Path

`block()` turns a reactive call into a synchronous call by waiting for the result. If invoked on a WebFlux event-loop thread, it can block a thread responsible for handling many requests and defeat the purpose of non-blocking I/O.

Instead of:

```java
Customer customer = customerRepository.findById(id).block();
```

keep the result as a publisher and compose using `map`, `flatMap`, `zip`, or another suitable operator:

```java
public Mono<CustomerView> getView(Long id) {
    return customerRepository.findById(id)
            .flatMap(customer -> preferenceClient.getPreference(id)
                    .map(preference -> new CustomerView(customer, preference)));
}
```

If integrating a blocking library is unavoidable, isolate the blocking portion on an appropriate scheduler and limit concurrency. This is an intentional compatibility measure—it does not make a blocking library non-blocking.

### 6.2. Reactive Transactions Propagate Context Differently

With JDBC, transactions are typically bound to the executing thread. With R2DBC, reactive transactions are managed via the reactive context so they can follow the publisher chain even when steps do not execute on the same thread.

When using `@Transactional` for an R2DBC flow, ensure the method returns a publisher and the application has an appropriate reactive transaction manager. `TransactionalOperator` can be used when expressing transaction boundaries directly in the pipeline.

Do not call `.block()` in the middle of a reactive transaction or detach a step from the pipeline while assuming the transaction remains active. Nor should you assume a single transaction manager can cover both JDBC and R2DBC operations simultaneously; the two stacks typically have separate connection factories, connection pools, and transaction managers.

### 6.3. Spring Data R2DBC Is Not Reactive JPA

R2DBC provides reactive SQL access for relational databases. Spring Data R2DBC focuses on data mapping and aggregates following the Spring Data Relational approach.

Do not expect all features commonly found in JPA/Hibernate, such as:

- A persistence context tracking object changes and dirty checking.
- Automatic lazy loading for entity relationships.
- JPA-style cascading and entity graphs.
- Modifying a field and having the entire object graph flushed automatically.

Aggregate design, SQL queries, and persistence operations must be explicit in the application. If a project relies heavily on JPA's ORM model, re-evaluate the benefits of switching to R2DBC.

### 6.4. Managing Connection Pools and Concurrency

Non-blocking allows an application to handle many I/O-bound operations in flight, yet the database still has limits on connections, CPU, memory, and query throughput. Increasing concurrency without bounds can exhaust the pool, grow queues, or overload the database.

In operations, monitor at least:

- Active connections, idle connections, and connection acquisition wait times.
- Query latency, timeouts, connection errors, and retry counts.
- Throughput, concurrent requests, and queue depth.
- Database CPU, memory, and load.

Set concurrency limits matched to database and connection pool capacity. With operators like `flatMap`, consider bounding concurrency if a pipeline can trigger many simultaneous queries.

## 7. Should You Combine JDBC and R2DBC in the Same Application?

Both stacks can coexist in one application—for example, a legacy module still using JDBC while a new flow uses WebFlux and R2DBC. However, clear boundaries must be designed:

1. Each stack has connection and pool settings suited to its driver.
2. Clearly identify which transaction manager governs each operation.
3. Never assume a JDBC transaction automatically covers R2DBC operations, or vice versa.
4. Never call blocking JDBC directly on an event-loop thread.
5. Monitor the combined connection count across both pools to avoid exceeding database limits.

If a business operation must update resources across both stacks, treat data consistency and error handling as a dedicated design problem. A single `@Transactional` annotation does not create a distributed atomic transaction across two independent connections.

For new systems, only run both in parallel when there is a specific need. Otherwise, choosing one primary data access model makes code, transactions, and operations easier to reason about.

## 8. Making the Decision for Your Project

Before choosing a technology, answer these questions in order:

1. Is the application using Spring MVC or Spring WebFlux? Are current services and clients blocking or reactive?
2. What problem needs to be solved: insufficient I/O concurrency, excessive thread counts, or merely wanting to try new technology?
3. Does your database have a suitable R2DBC driver that fully supports the features your project needs?
4. Does the application depend on JPA/Hibernate, JDBC-specific libraries, or specialized stored procedures?
5. Does the development team have experience with `Mono`, `Flux`, backpressure, reactive error handling, and reactive transactions?
6. Are there benchmarks or production metrics proving JDBC is the bottleneck?

You can apply the following initial guidelines:

| Situation | Initial Choice |
| --- | --- |
| WebFlux app, all I/O layers reactive, strong driver support | Prioritize evaluating R2DBC |
| Spring MVC app, synchronous services and repositories | Prioritize JDBC |
| Project needs JPA/Hibernate features | Prioritize the JDBC stack with JPA/Hibernate |
| High concurrent I/O load and JDBC measured as a thread-resource bottleneck | Test R2DBC with realistic benchmarks |
| R2DBC driver lacks critical database features | Use JDBC or keep the current solution |
| Application is stable with no measured performance problems | Continue using the current stack |

If you decide to migrate, pilot on one measurable business flow. Compare identical data, identical queries, and identical load; measure p50/p95/p99 latency, throughput, CPU, memory, connection counts, timeouts, and error rates. Test transaction behavior and failure cases as well—not just a simple CRUD query.

## 9. Conclusion

Choose **R2DBC** when the application genuinely needs a reactive model, handles high concurrent I/O, can stay non-blocking end-to-end across processing layers, and has a driver meeting database requirements. Choose **JDBC** when an imperative architecture fits well, the JDBC ecosystem meets requirements, or the project relies on JDBC/JPA-based libraries and features.

The best decision is grounded in current architecture, business requirements, driver capabilities, and real load metrics. Do not switch to R2DBC expecting non-blocking I/O to automatically make every query faster.
