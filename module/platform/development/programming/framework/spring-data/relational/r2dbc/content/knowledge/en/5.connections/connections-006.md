# Acquiring, Using, and Releasing Connections in the Reactive Stream Lifecycle

In Spring Data R2DBC, working with a database is more than sending an SQL statement and receiving results. The application must also manage the lifecycle of the connection: acquiring a connection when needed, holding it while statements and results are being processed, and releasing it at the right time when the stream completes, errors, or is cancelled.

The key point of the reactive model is that these operations are tied to the **subscription lifecycle of a Publisher**. Creating a Mono or Flux usually only builds a pipeline; a connection is not necessarily acquired at that moment. When a subscriber subscribes, the pipeline executes and begins using resources. Consequently, how connections are opened and closed must handle all three stream termination signals: completion, error, and cancellation.

## 1. Basic Lifecycle of an R2DBC Connection

R2DBC defines a reactive API for applications to work with relational databases. Key abstractions include:

- **ConnectionFactory:** creates connections to the database or supplies connections from a connection pool.
- **Connection:** represents a connection currently in use by the application.
- **Statement:** represents the SQL statement to execute.
- **Result:** represents the execution result of a statement.
- **Publisher:** emits results and asynchronous signals according to Reactive Streams.

A typical lifecycle:

~~~text
Subscriber subscribes to Mono / Flux
             |
             v
Acquire Connection from ConnectionFactory
             |
             v
Create Statement and bind parameters
             |
             v
Execute Statement
             |
             v
Consume Result / Row in reactive pipeline
             |
             v
Stream ended?
             |
             v
       Complete / Error / Cancel
             |
             v
        Release Connection
             |
             v
     Connection ready for reuse
~~~

Three principles to uphold:

1. The connection must be acquired before using a statement.
2. The connection must remain held for as long as results need to be read or processed.
3. The connection must be released along every termination path: normal completion, error, and subscription cancellation.

If released too early, the application may encounter errors while reading results. If forgotten, the connection remains held and the pool can be exhausted. If only normal completion is handled while errors or cancellations are ignored, resources can leak under real load.

## 2. ConnectionFactory and the Acquire Operation

In the R2DBC SPI, ConnectionFactory's create() method returns a Publisher<Connection>. Thus, acquiring a connection is represented as a reactive operation:

~~~java
Publisher<Connection> connectionPublisher =
    connectionFactory.create();
~~~

In a Reactor application, this publisher can be wrapped into a Mono:

~~~java
Mono<Connection> connectionMono =
    Mono.from(connectionFactory.create());
~~~

Mono.from(...) does not acquire a connection immediately. It describes a source for obtaining a connection upon subscription. This design allows acquisition to participate in the reactive pipeline instead of blocking a thread while waiting for a connection.

ConnectionFactory can be configured to open new physical connections or be wrapped by a connection pool. When pooled, acquisition typically takes an idle connection or waits until a suitable connection becomes available. The application interacts with the Connection API as usual; the pool manages resource distribution and reuse underneath.

Do not call subscribe() inside a service just to obtain a connection and continue processing on another flow. Doing so detaches acquisition from the caller's pipeline, making error handling, cancellation, and execution ordering difficult to control.

## 3. Using Connections and Consuming Results

After obtaining a Connection, the application creates a Statement, binds parameters, and executes. Direct query example using the R2DBC SPI:

~~~java
Mono<List<String>> customerNames =
    Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection ->
            Flux.from(
                connection
                    .createStatement(
                        "SELECT name FROM customer WHERE active = $1"
                    )
                    .bind(0, true)
                    .execute()
            )
            .flatMap(result ->
                result.map((row, metadata) ->
                    row.get("name", String.class)
                )
            )
            .collectList(),
        Connection::close,
        (connection, error) -> connection.close(),
        Connection::close
    );
~~~

The example above illustrates using Mono.usingWhen to manage a connection:

- The first argument is the publisher supplying the resource, here a Connection.
- The second function describes the work performed once the connection is acquired.
- The third function releases the connection when the work completes normally.
- The fourth function releases the connection when the work raises an error.
- The fifth function releases the connection when the subscriber cancels.

Result.map(...) converts each result row into a Java value. Results are consumed within the pipeline before usingWhen runs cleanup. The example uses collectList() to return a list, which fits small datasets; for large datasets, stream processing with Flux can avoid holding all results in memory.

In practice, placeholders and binding syntax depend on the R2DBC driver. Using $1 and index 0 in the example illustrates the bind style of some drivers such as PostgreSQL; do not copy that exact syntax blindly across every database.

## 4. Why Must usingWhen Be Used?

For synchronous resources, Java has try-with-resources to close resources automatically upon exiting a block. An R2DBC connection is an asynchronous resource: Connection.close() returns a Publisher<Void>. Therefore, you cannot simply call close() while ignoring the returned publisher and expect release to have completed.

Reactor provides usingWhen to manage resources with asynchronous cleanup operations. It ties cleanup to the terminal outcomes of the publisher using the resource:

| Pipeline outcome | Cleanup invoked |
|---|---|
| Normal completion | Completion cleanup function |
| Error emitted | Error cleanup function |
| Subscriber cancels | Cancellation cleanup function |

This is critical for database streams. An HTTP request may be disconnected by the client, an operator may cancel upstream, or a timeout may cause the subscription to be cancelled. Even then, the application must still release the connection.

Avoid the following pattern:

~~~java
connectionFactory.create()
    .subscribe(connection -> {
        // Perform query in a detached subscription
        connection.close();
    });
~~~

This code creates an independent subscription, fails to connect query results to the caller's lifecycle, and does not guarantee proper handling of every error or cancellation path. It also easily loses transaction context. Return a Mono or Flux so the caller controls subscription and use reactive resource management.

## 5. How Does Spring Data R2DBC Manage Connections Automatically?

In typical applications, you do not need to call ConnectionFactory.create() manually for every repository method. Spring provides DatabaseClient to execute SQL and manage acquiring, using, and releasing connections. Spring Data R2DBC builds repository and mapping operations atop these abstractions.

Example using DatabaseClient:

~~~java
Mono<Customer> customer =
    databaseClient.sql(
            "SELECT id, name FROM customer WHERE email = :email"
        )
        .bind("email", email)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .one();
~~~

The application only describes the SQL statement, binds values, and maps rows to Customer. DatabaseClient coordinates with Spring's connection management mechanism to acquire and release the connection according to the operation's lifecycle.

Spring Data R2DBC repositories share the same goal:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByActiveTrue();
}
~~~

When calling a repository, the application receives a Mono or Flux. Query execution happens when the publisher is subscribed to. Spring manages the required resources while the operation runs and releases them when the stream ends.

Therefore, when using DatabaseClient, R2dbcEntityTemplate, or Spring Data repositories in the standard way, do not manually acquire another connection just to run the same operation. Let Spring's abstractions manage connections, especially when the application uses transactions.

## 6. Connection Pools and Connection Reuse

Opening a physical connection to a database has overhead: establishing a socket, authenticating, initializing session state, and negotiating protocol details. If every query opened and closed a new physical connection, the application could waste resources and increase latency.

A **connection pool** retains a set of reusable connections. When the application acquires, the pool lends an idle connection. When the application releases, the connection is returned to the pool so another request can use it.

With R2DBC, the r2dbc-pool library provides ConnectionPool. Direct configuration example:

~~~java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(5)
        .maxSize(20)
        .maxAcquireTime(Duration.ofSeconds(5))
        .maxIdleTime(Duration.ofMinutes(30))
        .build();

ConnectionPool connectionPool =
    new ConnectionPool(configuration);
~~~

Values in the example are illustrative only. Pool size and timeouts must be chosen based on allowed database connections, number of application instances, concurrency level, and actual query durations.

When using a connection pool:

- Calling close() on a pooled connection normally means returning the lease to the pool, not necessarily closing the physical socket immediately.
- A released connection may be issued to another operation.
- If all connections are in use, an acquire operation may wait or fail if it exceeds the wait timeout.
- Idle or invalid connections may be validated and evicted by the pool according to configuration.

A pool does not make a connection safe for arbitrary concurrent use across multiple requests. Each acquisition must be treated as a lease with a clearly bounded scope. After release, code must not continue using the old connection or statement.

Nor does a pool replace proper release. If a pipeline forgets to release, the pool does not know the application is finished; the connection remains held and subsequent operations may wait until timeout.

## 7. Release Does Not Always Mean Closing the Physical Connection

Two concepts must be distinguished:

- **Release:** the application finishes using the connection and returns ownership of the resource to the managing component.
- **Physical close:** closing the physical connection to the database, such as closing the socket or ending the session.

Without a pool, Connection.close() typically closes the connection per the driver's implementation. With a pool, close() typically returns the connection to the pool. The pool decides whether to keep it for reuse or evict it based on connection state and management policies.

Therefore, application code must still invoke cleanup at the right time even when a pool is present. Do not skip close() assuming the pool will automatically reclaim the connection.

On application shutdown, the pool also needs to be disposed according to the application lifecycle to stop accepting new acquisitions and free resources. In Spring Boot, let the pool-managing bean/lifecycle close alongside the application context; avoid disposing the pool manually after each request.

## 8. Connections in Reactive Transactions

Transactions add another management layer to connection lifecycle. When using R2dbcTransactionManager, Spring acquires a connection and binds it to the reactive transaction context. Database operations participating in the transaction use the connection bound in that context.

High-level flow:

~~~text
Reactive transaction begins
             |
             v
Acquire Connection
             |
             v
Bind Connection to Reactor Context
             |
             v
DatabaseClient / Repository operations
             |
             v
       Success or error
             |
             v
       Commit or Rollback
             |
             v
       Release Connection
~~~

Example using @Transactional:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customerRepository;
    private final AuditRepository auditRepository;

    @Transactional
    public Mono<Void> updateCustomer(Customer customer) {
        return customerRepository.save(customer)
            .then(auditRepository.recordUpdate(customer.getId()))
            .then();
    }
}
~~~

Because the method returns a Mono, Spring can wrap the subscription in a reactive transaction if the application has configured an appropriate ReactiveTransactionManager. The repositories must use the same ConnectionFactory managed by the transaction manager to participate in the same transaction.

You can use TransactionalOperator when wrapping transactions programmatically:

~~~java
Mono<Void> operation =
    customerRepository.save(customer)
        .then(auditRepository.recordUpdate(customer.getId()))
        .then();

return operation.as(transactionalOperator::transactional);
~~~

In a reactive transaction, context is propagated via Reactor Context rather than relying on ThreadLocal as in the traditional imperative model. Therefore, do not detach database operations by calling subscribe() inside a transactional method. Doing so can cause the new subscription to run outside the original transaction context.

Do not call close() manually on a connection managed by Spring's transaction manager. The transaction manager is responsible for committing or rolling back and then releasing the connection when the transaction finishes. If application code closes the connection prematurely, subsequent operations within the same transaction may fail.

If you need to access the R2DBC SPI directly while still participating in a Spring transaction, use Spring's transaction-aware connection acquisition and release mechanism, such as ConnectionFactoryUtils, instead of calling connectionFactory.create() directly and creating an independent connection.

Framework example of direct connection management using Spring's mechanism:

~~~java
Mono<List<String>> names =
    Mono.usingWhen(
        ConnectionFactoryUtils.getConnection(connectionFactory),
        connection -> executeQuery(connection),
        connection ->
            ConnectionFactoryUtils.releaseConnection(
                connection, connectionFactory
            ),
        (connection, error) ->
            ConnectionFactoryUtils.releaseConnection(
                connection, connectionFactory
            ),
        connection ->
            ConnectionFactoryUtils.releaseConnection(
                connection, connectionFactory
            )
    );
~~~

ConnectionFactoryUtils can return the connection already bound to the current transaction. When releasing a transaction-bound connection, Spring retains management of it until the transaction commits or rolls back. Use this approach only when direct SPI access is genuinely needed; for normal queries, DatabaseClient or repositories are simpler and less error-prone.

## 9. Cancellation, Timeouts, and Errors

In a reactive system, not every request reaches onComplete. A subscriber may cancel the subscription; a timeout may cancel upstream; a mapping step may throw an error; the database may reject the connection or return an SQL error.

Common scenarios:

| Scenario | What happens to the pipeline | Requirement for the connection |
|---|---|---|
| Query returns all data | Publisher emits onComplete | Release after results are consumed |
| Database returns an error | Publisher emits onError | Clean up then propagate error to caller |
| HTTP client disconnects | Subscription may be cancelled | Clean up to return connection to pool |
| Timeout | Timeout operator may cancel upstream | Clean up even if timeout occurs mid-read |
| Mapping error | Pipeline terminates with error | Do not leave connection held |
| Acquire timeout | Failed to obtain connection | Return appropriate error; no connection to release |

usingWhen handles asynchronous cleanup for completion, error, and cancellation cases. When using DatabaseClient or Spring Data repositories, Spring takes care of the corresponding lifecycle. The application must let cancellation signals propagate through the pipeline and avoid swallowing signals with a detached subscription.

A query operation can be cancelled while reading data. Thus, if code interacts with the R2DBC SPI directly, do not release right after calling execute(). Wait until the result publisher is consumed or cancelled so cleanup occurs at the right moment.

## 10. Backpressure and Connection Hold Duration

R2DBC delivers data via publishers, allowing downstream to regulate demand through backpressure. However, that does not mean the connection is returned to the pool after each row. While a query is emitting data, the connection usually must remain held until results finish being consumed or the subscription is cancelled.

For example:

~~~java
Flux<Customer> customers =
    databaseClient.sql("SELECT id, name FROM customer")
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all();
~~~

If downstream processes each item slowly, the subscription can stay open longer and hold the connection longer. If many requests hold connections for long periods simultaneously, the pool can be exhausted even if the number of queries at a given instant is not huge.

Some ways to reduce connection hold time:

- Select only needed columns and avoid querying large unused data.
- Apply reasonable filter predicates and data limits.
- Avoid heavy CPU processing or slow HTTP service calls while holding database results open.
- If an external service must be called, consider fetching the required data and finishing the database operation before calling that service, if consistency requirements allow.
- Monitor acquire time, connection hold duration, and query time to identify bottlenecks.

Calling collectList() is not always ideal either. It consumes the full result in one go and returns a collection, but can use substantial memory for large datasets. Conversely, streaming a very long stream can hold the connection for a long time. Balance dataset size, memory, and connection hold duration.

## 11. Lazy Execution and Multiple Subscriptions

Mono and Flux are typically lazy publishers. Creating a publisher does not mean the query has executed:

~~~java
Mono<Customer> customerMono =
    customerRepository.findById(10L);
~~~

At this point, the customerMono variable describes an operation. When subscribed to, Spring executes the query and acquires the necessary resources.

Subscribing twice to a cold publisher may execute the operation twice, and each subscription may acquire a separate connection:

~~~java
Mono<Customer> customerMono =
    customerRepository.findById(10L);

customerMono.subscribe();
customerMono.subscribe();
~~~

The snippet above is generally not appropriate in service code. It creates two independent subscriptions and does not ensure querying only once. Return the publisher to the calling layer or compose operations using operators such as flatMap, zip, or then.

Retries can also re-subscribe upstream. As a result, a database operation may re-run and acquire a new connection. Only retry when error policies and business idempotency permit; do not assume a retry merely continues on the old connection or old transaction.

## 12. Common Connection Management Mistakes

| Mistake | Possible consequence | How to fix |
|---|---|---|
| Acquiring a connection without releasing it | Connection leak, pool exhaustion | Use usingWhen or Spring APIs that manage lifecycle |
| Releasing only on complete | Errors or cancellations leave connections held | Configure cleanup for complete, error, and cancel |
| Calling close() without consuming the cleanup publisher | Asynchronous release may not complete | Chain the cleanup publisher into the pipeline |
| Closing right after execute() | Results have not finished being read | Hold connection until Result consumption finishes |
| Calling subscribe() manually inside a service | Detaches lifecycle, errors, and transaction context | Return Mono/Flux to the caller |
| Using a connection after release | State errors or accessing a resource issued to another request | Do not use a connection outside its lease scope |
| Calling connectionFactory.create() inside a Spring transaction | May create a different connection outside the current transaction | Use DatabaseClient, repositories, or ConnectionFactoryUtils |
| Closing a connection managed by the transaction manager | Transaction may fail before completion | Let the transaction manager commit/rollback and release |
| Streaming data for too long | Connections held too long, pool starved | Shorten operations, filter data, and avoid slow work while holding connections |

## 13. Observing and Configuring Connection Lifecycle

In application operations, monitor metrics related to the pool and queries:

- Number of active (in-use) connections and idle connections.
- Number of pending acquire requests.
- Acquire wait time and number of acquire timeouts.
- Duration a connection is held before release.
- New connection creations, evicted connections, and connection errors.
- Query duration and number of rows read.

If the pool is frequently at maximum capacity, increasing maxSize is not always the right solution. The application may be holding connections too long, running slow queries, having slow downstream consumers, or leaking connections. Compare against database connection limits and total application instance count.

Acquire timeouts allow operations to fail boundedly when no idle connections remain. Query timeouts or request-layer timeouts must also be designed consistently to avoid holding resources longer than business limits allow. After a timeout or cancellation, cleanup must execute so the connection is returned to the pool.

On application shutdown, allow in-flight operations time to finish according to system policy and dispose the pool via a lifecycle bean. Do not create a new pool per request and do not dispose the pool after a single query.

## 14. Choosing the Right Abstraction

| Need | Recommended approach |
|---|---|
| Standard CRUD and entity mapping | Spring Data R2DBC repository |
| Custom SQL while letting Spring manage connections | DatabaseClient |
| Aggregate mapping and operations via template API | R2dbcEntityTemplate |
| Reactive transactions across multiple operations | R2dbcTransactionManager with @Transactional or TransactionalOperator |
| Genuine need for low-level R2DBC SPI API | ConnectionFactory combined with usingWhen |
| Low-level SPI usage needing Spring transaction participation | ConnectionFactoryUtils and corresponding cleanup |
| Connection reuse and connection count limits | R2DBC connection pool |

Prefer the highest-level abstraction that still satisfies your requirements. Repositories and DatabaseClient substantially reduce the risk of forgetting cleanup. Manage a Connection directly only when you need capabilities higher abstractions do not provide.

## 15. Key Takeaways

- ConnectionFactory.create() supplies connections as a reactive publisher; acquisition is tied to subscription.
- A Connection must remain valid throughout the time statements and results are in use.
- Connection.close() is an asynchronous operation; the cleanup publisher must be consumed.
- usingWhen manages cleanup on stream completion, error, or cancellation.
- DatabaseClient, R2dbcEntityTemplate, and Spring Data repositories manage connections for standard operations.
- Connection pools reuse connections; release normally returns the lease to the pool instead of closing the physical socket.
- Reactive transactions bind connections to Reactor Context; use the right ConnectionFactory and do not detach with manual subscribe calls.
- When streaming data for long periods, connections may be held longer; backpressure does not automatically return a connection after each row.
- Never use a connection after release, skip cleanup, or manually close a connection managed by the transaction manager.
