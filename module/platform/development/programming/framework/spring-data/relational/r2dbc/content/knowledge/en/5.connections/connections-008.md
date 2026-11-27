# Distinguishing Multiple Subscriptions from Reusing a Connection

## 1. Why Must These Two Concepts Be Distinguished?

In Spring Data Relational R2DBC, database access operations are represented by reactive publishers such as Mono and Flux. A publisher describes work to be performed; work usually begins only when a subscriber subscribes to receive results.

This leads to two easily confused concepts:

- **Multiple subscriptions:** the same publisher is subscribed to multiple times. With a cold database query publisher, each subscription typically re-executes the query operation and goes through acquiring a connection.
- **Reusing a single connection:** multiple database statements share the same connection within an intentional scope, typically inside a reactive transaction. Those operations share the same transaction state and the same database session.

In addition, there is connection pooling, a mechanism that allows reusing opened physical connections after one usage turn completes. Connection pooling and sharing one connection within a transaction solve two different problems.

If you do not distinguish these three mechanisms, you may accidentally run an SQL statement multiple times, add extra load to the pool, lose consistency across statements, or assume two operations share a transaction when they actually use two independent connections.

## 2. Publisher, Subscription, and Connection Are Three Different Things

### 2.1. A Publisher Only Describes Work

For example:

~~~java
Mono<Long> totalOrders =
    databaseClient.sql("SELECT COUNT(*) AS total FROM orders")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();
~~~

The snippet above creates a publisher describing a query that counts orders. With normal reactive usage of DatabaseClient, the SQL statement has not executed merely because the totalOrders variable was created. Execution happens when the publisher is subscribed to.

A publisher is a description of a processing flow. It is neither a connection nor an open database session being held.

### 2.2. A Subscription Triggers One Execution

When a subscriber subscribes, a cold publisher typically starts a new execution. For a database operation, the flow usually looks like:

~~~text
Create publisher
     |
     v
Subscriber subscribes
     |
     v
Acquire connection from ConnectionFactory
     |
     v
Execute SQL statement
     |
     v
Read results and emit signals
     |
     v
Close or return connection to pool
~~~

The exact lifecycle depends on the abstraction in use and the transaction context. DatabaseClient, R2dbcEntityTemplate, and Spring Data repositories manage connection lifecycle for standard operations. When an operation finishes, the connection is released according to ConnectionFactory's mechanism; if pooling is used, the connection is typically returned to the pool so a later usage can borrow it again.

### 2.3. A Connection Is the Resource That Communicates with the Database

The R2DBC SPI defines ConnectionFactory to supply connections. The create() method returns a Publisher of Connection. Therefore, calling create() and actually receiving a connection are also separated under the reactive model: a subscriber must subscribe for the publisher to provide the resource.

A connection represents a logical working session with the database. It can carry state such as the active transaction, isolation level, selected schema, or session-level settings. A connection must have its lifecycle managed properly and be released when no longer in use.

Do not confuse a publisher with a connection. Nor should you keep a connection in an application-wide shared variable.

## 3. Subscribing to the Same Publisher Multiple Times Can Run Queries Multiple Times

Query publishers created by DatabaseClient are typically cold publishers. Each independent subscription can trigger a database execution.

For example:

~~~java
Mono<Long> totalOrders =
    databaseClient.sql("SELECT COUNT(*) AS total FROM orders")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();

return Mono.zip(totalOrders, totalOrders);
~~~

Mono.zip needs to subscribe to both input publishers. Because totalOrders is a cold publisher, using the same variable twice does not mean only one SQL statement runs. In this example, the count query may execute twice. If the two subscriptions occur concurrently outside the same transaction, each execution may borrow a separate connection.

This is a critical point: **reusing a publisher variable does not equate to reusing results or a connection**.

Another pattern that can also cause multiple executions is subscribing twice:

~~~java
Mono<Long> totalOrders =
    databaseClient.sql("SELECT COUNT(*) AS total FROM orders")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();

totalOrders.subscribe(value -> log.info("First read: {}", value));
totalOrders.subscribe(value -> log.info("Second read: {}", value));
~~~

Two subscribe calls are two independent execution requests. This snippet is only meant to illustrate subscription behavior; in service, controller, or repository code, you should normally return the publisher for the framework to manage instead of calling subscribe manually.

Operators such as retry and repeat can also re-subscribe to a publisher. Therefore, a query with side effects or a write statement may re-run after an error if the pipeline has retry configured. Review idempotency and transaction boundaries before retrying write operations.

### 3.1. To Use One Result Across Multiple Steps, Chain the Pipeline

If you only need to run a query once and use the result in subsequent steps, handle the result within the same pipeline:

~~~java
return databaseClient.sql("SELECT COUNT(*) AS total FROM orders")
    .map((row, metadata) -> row.get("total", Long.class))
    .one()
    .flatMap(total -> {
        log.info("Total orders: {}", total);
        return createReportFor(total);
    });
~~~

In this example, the query publisher is subscribed to once in the pipeline. The total value is passed to the next step via flatMap. There is no need to create a second subscription just to read the same value again.

If you need to use the result across multiple branches, fan out those branches from the received value within a single pipeline. For example:

~~~java
return loadCustomer(customerId)
    .flatMap(customer ->
        Mono.zip(
            loadOrderSummary(customer.getId()),
            loadRewardSummary(customer.getId())
        ).map(summaries -> buildCustomerView(customer, summaries))
    );
~~~

The two queries inside zip are still two independent database operations. However, customer data is loaded only once in this pipeline. If both summary queries must run inside the same transaction, place the entire chain inside a reactive transaction.

### 3.2. cache() Stores Result Signals, Not Connections

Reactor provides operators that share or cache signals, such as cache():

~~~java
Mono<Long> cachedTotalOrders = totalOrders.cache();
~~~

With this publisher, the first subscription triggers the source and the result signal is cached so subsequent subscribers receive the cached signal. This is publisher signal caching. It does not hold a connection open for subsequent subscribers to reuse.

Distinguish between:

- Result caching: subsequent subscribers receive the cached value or signal.
- Connection reuse: a subsequent database operation uses the same managed connection within a valid scope.
- Connection pooling: a physical connection is returned to the pool after a turn of use and can be re-issued to another turn of use.

Do not use cache() merely to avoid acquiring a connection. Result caching can return stale data, retain an error signal that occurred, or yield data that does not reflect the current transaction. Use caching only when a data caching policy has been clearly defined regarding TTL, consistency, and refresh rules.

## 4. Connection Pools Reuse Physical Connections Over Time

### 4.1. ConnectionFactory and ConnectionPool

ConnectionFactory is the entry point providing connections to the application. Using a raw factory directly may require opening a new physical connection on each acquire depending on implementation.

In real applications, you can wrap the factory with a connection pool, such as R2DBC Connection Pool. The pool maintains a set of physical connections and lends them to operations as needed.

Typical lifecycle:

~~~text
Operation A needs a connection
        |
        v
Pool lends physical connection P1
        |
        v
A executes SQL and releases connection
        |
        v
P1 returns to pool
        |
        v
Operation B needs a connection
        |
        v
Pool may re-issue P1 to B
~~~

The pool can also issue a different connection if P1 is busy, no longer valid, or pool policies require it. Therefore, two independent operations have no guarantee of receiving the same physical connection.

### 4.2. Closing a Pooled Connection Normally Returns It to the Pool

When the application uses a connection managed by a pool, calling close() on the borrowed connection usually releases the lease and returns the connection to the pool. The pool can reuse that physical connection after completing necessary validation and reset steps.

Thus, do not assume that every time an operation finishes, the database must close the physical socket. Nor should you assume a connection returned to the pool will be reserved exclusively for the same request next time.

### 4.3. Pools Do Not Guarantee Shared Session State Across Operations

Suppose operation A sets a session-level variable or creates a temporary table on connection P1 and then finishes. Later, operation B is issued connection P2. B will not see P1's private state.

Even if B happens to receive P1 again, the application must not rely on that coincidence for correctness. The pool may reset connections, issue a different connection, or replace faulty connections.

If multiple statements must share a transaction, temporary table, session variable, or session state, keep them within a single transaction or an explicitly managed connection scope.

### 4.4. Pools and Transactions Solve Two Different Needs

| Mechanism | How connections are used | Goal |
|---|---|---|
| Multiple independent subscriptions | Each execution typically acquires a connection; pool may issue different physical connections or reuse after return | Executing multiple independent requests |
| Connection pool | Lends and reclaims physical connections across multiple uses over time | Reducing connection creation overhead and bounding connection count |
| Single reactive transaction | Operations participating in the same transaction are bound by Spring to the same connection in the transaction context | Ensuring statements share the same transaction and session state |
| Manual connection management | Code holds one connection within a defined scope and releases it manually | Special scenarios requiring explicit session or resource lifecycle control |

## 5. Reusing the Same Connection Within a Reactive Transaction

### 5.1. The Transaction Manager Binds a Connection to the Reactor Context

When using R2dbcTransactionManager, Spring manages transactions using a connection from the configured ConnectionFactory. The connection is bound to the reactive pipeline's transaction context.

Database operations using Spring's integrated abstractions such as DatabaseClient, R2dbcEntityTemplate, or Spring Data repositories can participate in that transaction. When a subsequent operation runs inside the same reactive transaction context, Spring retrieves the bound connection instead of borrowing an independent connection for each statement.

This enables multiple SQL statements to execute on the same connection and within the same transaction:

~~~text
Start reactive transaction
        |
        v
Acquire connection C1 and bind to Reactor Context
        |
        +--> UPDATE orders on C1
        |
        +--> INSERT audit_log on C1
        |
        +--> UPDATE inventory on C1
        |
        v
Commit or rollback transaction
        |
        v
Release C1 back to ConnectionFactory / pool
~~~

If a statement fails and the error propagates out of the transaction, the transaction manager can roll back the entire transaction according to configured rules. This is a crucial difference compared to two independent operations that merely happen to receive the same physical connection from the pool at two different times.

### 5.2. Using TransactionalOperator

TransactionalOperator allows wrapping a reactive pipeline in a transaction:

~~~java
@Service
public class OrderService {

    private final DatabaseClient databaseClient;
    private final TransactionalOperator transactionalOperator;

    public OrderService(
            DatabaseClient databaseClient,
            TransactionalOperator transactionalOperator) {
        this.databaseClient = databaseClient;
        this.transactionalOperator = transactionalOperator;
    }

    public Mono<Void> confirmOrder(Long orderId) {
        Mono<Void> updateOrder =
            databaseClient.sql("""
                UPDATE orders
                SET status = :status
                WHERE id = :orderId
                """)
                .bind("status", "CONFIRMED")
                .bind("orderId", orderId)
                .fetch()
                .rowsUpdated()
                .then();

        Mono<Void> insertAudit =
            databaseClient.sql("""
                INSERT INTO order_audit(order_id, action)
                VALUES (:orderId, :action)
                """)
                .bind("orderId", orderId)
                .bind("action", "CONFIRMED")
                .fetch()
                .rowsUpdated()
                .then();

        return transactionalOperator.transactional(
            updateOrder.then(insertAudit)
        );
    }
}
~~~

The two operations are chained with then(), so the audit write runs only after the order update completes. When the pipeline executes inside a transaction, both operations participate in the same transaction context and use the connection managed by the transaction manager.

If inserting the audit record fails, the error propagates out of the transaction and the transaction can roll back the order status update as well. This avoids leaving an order marked confirmed without its confirmation audit record, assuming both tables and operations support transactions under the database configuration.

In real code, configure R2dbcTransactionManager and TransactionalOperator with the exact ConnectionFactory used by DatabaseClient. If they use different factories, operations may not participate in the same transaction.

### 5.3. Using @Transactional on Methods Returning a Publisher

Spring also supports declarative transactions with @Transactional for reactive methods:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditRepository auditRepository;

    public OrderService(
            OrderRepository orderRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Void> confirmOrder(Long orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Order not found")
            ))
            .flatMap(order -> {
                order.setStatus("CONFIRMED");
                return orderRepository.save(order);
            })
            .flatMap(order ->
                auditRepository.save(
                    new OrderAudit(order.getId(), "CONFIRMED")
                )
            )
            .then();
    }
}
~~~

For reactive transactions, the method must return a Publisher so Spring can establish the transaction context when the publisher executes. Spring uses the matching reactive transaction manager to open, commit, or roll back the transaction.

Note that Spring's transaction proxy must actually be applied. Calling a @Transactional method from another method on the same instance can bypass the proxy under standard proxy configuration. Place transaction boundaries on the appropriate beans and calls.

### 5.4. Conditions for Operations to Truly Use the Same Connection

For operations to participate in the same reactive transaction:

1. Use the same ConnectionFactory in the transaction manager and data access abstractions.
2. Wrap the operations in the same reactive transaction using properly configured TransactionalOperator or @Transactional.
3. Return and chain publishers so Spring propagates the Reactor Context throughout the pipeline.
4. Use DatabaseClient, R2dbcEntityTemplate, or repositories integrated with Spring's connection management mechanism.
5. Do not open a detached subscription or acquire a connection directly from the factory if the goal is to participate in the current transaction.

If code calls ConnectionFactory.create() manually inside a transaction, that connection may be a brand-new connection not bound to the current transaction context. When low-level R2DBC SPI operations are needed, use ConnectionFactoryUtils to acquire and release connections through Spring's resource management mechanism.

## 6. Do Not Subscribe or Block Manually Inside a Transaction

Reactor Context is tied to the subscriber, not traditional ThreadLocal. Reactive transactions rely on this context to locate the bound connection.

The following code is problematic:

~~~java
@Transactional
public Mono<Void> confirmOrder(Long orderId) {
    orderRepository.updateStatus(orderId, "CONFIRMED")
        .subscribe();

    return auditRepository.writeConfirmation(orderId).then();
}
~~~

Calling subscribe() starts a separate subscription flow. That subscription can run outside the transaction context Spring manages for the returned publisher. The method also returns before the manually subscribed work finishes, so commit/rollback boundaries no longer cover all intended work.

Chain publishers into the returned sequence instead:

~~~java
@Transactional
public Mono<Void> confirmOrder(Long orderId) {
    return orderRepository.updateStatus(orderId, "CONFIRMED")
        .then(auditRepository.writeConfirmation(orderId))
        .then();
}
~~~

Similarly, do not call block() to wait for database results inside a reactive transaction. block() creates a subscription and blocks the current thread; doing so can lose required context, break reactive resource management, and risk deadlocks or reduced throughput.

In a reactive application, let the framework or an application-boundary component subscribe to publishers. Business code should return and compose publishers rather than controlling subscriptions manually.

## 7. A Connection Should Not Be Used Concurrently Without Care

When multiple operations participate in the same transaction, they typically share a single connection. A connection is a stateful resource; many drivers/databases do not support arbitrarily sending concurrent independent operations over the same connection.

For example, inside a transaction, the following snippet can create concurrent operations:

~~~java
return transactionalOperator.transactional(
    Mono.when(
        updateOrderStatus(orderId),
        updateInventory(productId),
        insertAudit(orderId)
    )
);
~~~

Mono.when subscribes to the input publishers and waits for all to complete. If those publishers share a single connection inside the transaction, the operations may contend on that connection. Exact behavior depends on the driver and how operations are executed; do not assume a connection handles arbitrary concurrent commands safely.

If execution order must be preserved or operations share a connection, chain them sequentially:

~~~java
return transactionalOperator.transactional(
    updateOrderStatus(orderId)
        .then(updateInventory(productId))
        .then(insertAudit(orderId))
);
~~~

When processing a collection inside a transaction, consider concatMap for sequential execution:

~~~java
return transactionalOperator.transactional(
    Flux.fromIterable(items)
        .concatMap(this::saveItem)
        .then()
);
~~~

flatMap can allow multiple inner publishers to run concurrently depending on concurrency settings. Use parallelism only when connection design, transactions, driver support, and pool limits allow it; never assume a shared connection can take arbitrary concurrent queries.

## 8. When Do You Need to Manage a Connection Manually?

For ordinary queries, prefer DatabaseClient, R2dbcEntityTemplate, and Spring Data repositories. These abstractions integrate with connection lifecycle, pooling, and the transaction manager.

Certain specialized scenarios may require holding one connection across multiple statements:

- Creating and using temporary tables scoped to a database session.
- Setting session variables and running queries that depend on them.
- Using advisory locks or session-level locking mechanisms of a database engine.
- Running a specialized command sequence that higher-level APIs cannot express.
- Integrating directly with the R2DBC SPI.

When acquiring a connection manually outside a transaction, ensure the connection is closed or returned to the pool in every case: success, error, and cancellation. Reactor provides usingWhen for managing asynchronous resources:

~~~java
private Mono<Void> runWithOneConnection() {
    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> executeStatements(connection),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
~~~

In this example, executeStatements(connection) executes statements on the acquired connection. The three cleanup callbacks handle normal completion, error, and cancellation respectively. With a connection pool, close() normally returns the connection to the pool.

The snippet above illustrates managing one connection manually within a subscription scope. It does not automatically join a Spring-managed transaction. If you need to participate in the current transaction, acquire the connection via ConnectionFactoryUtils instead of calling ConnectionFactory.create() directly.

Do not store a connection in a static field, singleton service, or variable shared across requests. Connections are stateful, have bounded lifetimes, and must be returned to their manager. Holding a connection too long occupies a pool slot, causing other requests to wait or time out.

## 9. Common Mistakes and Correct Mental Models

| Misconception or mistake | What actually happens | How to fix |
|---|---|---|
| Creating one Mono variable and using it twice means the query runs once | A cold publisher may be subscribed to twice and run the query twice | Reuse the result within the same pipeline if only one read is needed |
| Calling subscribe() twice to get results again | Creates two independent subscriptions | Return the publisher and let the framework manage subscription |
| Reusing the same publisher variable means using the same connection | A publisher does not represent a connection | Use a transaction context if statements need the same connection |
| The pool always returns the same connection for a request | The pool may issue any suitable connection | Do not rely on session state across two separate acquisitions |
| Closing a connection always closes the physical socket | With a pool, close() normally returns the connection to the pool | Let the pool manage physical connections |
| Using cache() reuses the connection | cache() caches result signals, not connections | Cache only when a clear data caching policy exists |
| Calling ConnectionFactory.create() inside a transaction definitely gets the transaction connection | May acquire a new connection outside the transaction context | Use Spring abstractions or ConnectionFactoryUtils |
| Calling subscribe() inside a @Transactional method stays in the same transaction | The new subscription may lack the current transaction context | Chain the publisher into the returned publisher |
| Using Mono.when for multiple commands on the same transaction connection is always safe | Commands may race on the same connection | Serialize with then() or concatMap when needed |
| Keeping a connection in a field to reuse across requests | Connection may be used concurrently, expire, or exhaust the pool | Scope connections to a subscription/transaction and release properly |

## 10. How to Observe and Diagnose

When suspecting a flow is creating too many connections or executing duplicate queries, distinguish SQL execution count from open physical connection count.

### 10.1. Observing Query Counts

Use SQL logs or logs at the repository/DatabaseClient layer to determine how many executions a business operation triggers. If the same SQL statement appears multiple times, check:

- Whether the publisher is used in multiple branches causing multiple subscriptions.
- Whether subscribe() is called manually in multiple places.
- Whether retry(), repeat(), or reactive loops re-trigger the query.
- Whether multiple distinct requests are calling the same endpoint.

Creating a publisher once does not mean the SQL is sent only once. Count actual executions.

### 10.2. Observing the Connection Pool

If using a pool, monitor the metrics exposed by the pool, such as active connections, pending acquire count, max connections, and idle connections. Exact metric names depend on library version and configuration.

- High active connection count may reflect many concurrent operations or connections held too long.
- Rising pending waits may indicate the pool has hit its limit or queries/transactions are holding connections too long.
- Many idle connections are not necessarily an error; the pool may keep connections ready to reduce creation cost.
- An increase in acquire counts does not mean physical connections increased proportionally, since the pool can reuse opened connections.

Do not increase pool size just to hide a pipeline creating duplicate subscriptions or overly long transactions. Find the root cause first, then tune the pool to load and database limits.

### 10.3. Verifying Transaction Boundaries

If two statements are expected to commit or roll back together, confirm:

- The transaction manager uses the right ConnectionFactory.
- Repositories/DatabaseClient participate in the same reactive transaction.
- The method returns Mono or Flux and publishers are chained continuously.
- There are no subscribe(), block(), or detached flows in between.
- Errors from later operations propagate out of the transaction so the transaction manager can roll back.
- No code acquires connections directly in a way that detaches operations from the transaction.

## 11. Choosing the Right Mechanism by Scenario

| Scenario | Appropriate approach |
|---|---|
| An independent read query | Create a publisher and let the framework subscribe; connections are managed automatically |
| Using a query result across multiple steps in one request | Use flatMap/map to pass the result within the same pipeline |
| Two statements must succeed or fail together | Use a reactive transaction with TransactionalOperator or @Transactional |
| Multiple independent requests need to share connection infrastructure | Configure a connection pool |
| Need to preserve a temporary table or session state across statements | Keep the same connection in a transaction or clearly managed connection scope |
| Need to reuse a queried value for a period of time | Design a data cache with expiration/refresh policy; do not cache connections |
| Need direct R2DBC SPI in transactional Spring code | Use ConnectionFactoryUtils to participate and release properly |

## 12. Self-Check Exercises

### Exercise 1: One publisher, two subscriptions

How many times does the following code typically execute the query when the outer pipeline is subscribed to once?

~~~java
Mono<Long> total =
    databaseClient.sql("SELECT COUNT(*) AS total FROM orders")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();

return Mono.zip(total, total);
~~~

Hint: Mono.zip subscribes to both sources. With a cold query publisher, the source may execute twice. Reusing the same total variable does not make the publisher automatically share results.

### Exercise 2: Using a result once

You need to read the order count, log it, and build a report from that count. Write a pipeline so the query executes only once.

Hint:

~~~java
return loadOrderCount()
    .flatMap(total -> {
        log.info("Total orders: {}", total);
        return createReport(total);
    });
~~~

### Exercise 3: Two operations in the same transaction

A business flow updates an order status and writes an audit log. If writing the audit log fails, the order status must also roll back. Where would you place the transaction boundary?

Hint: Chain the two publishers with then() and wrap the whole chain with TransactionalOperator or place it in a @Transactional method returning a Publisher. Use the same ConnectionFactory in the transaction manager and DatabaseClient/repositories.

### Exercise 4: Why not call subscribe() inside a service?

A service calls repository.save(entity).subscribe() and then returns another Mono<Void>. Why can this cause the save operation to run outside the method's transaction?

Hint: subscribe() creates a separate subscription. That subscription may not carry the Reactor Context of the transaction managed for the returned publisher. Chain the save operation into the pipeline instead of subscribing manually.

### Exercise 5: Does a pool guarantee a temporary table exists in the next query?

An operation creates a temporary table and finishes. Another operation later queries that temporary table through the same ConnectionFactory—is it guaranteed to see the table?

Hint: No. The pool may issue a different physical connection, and temporary table state is typically session-scoped. Keep the statements within the same transaction or appropriate connection scope.

### Exercise 6: When should cache() be used?

You call a publisher that reads an account balance and want to reuse the value across multiple requests. Should you just add cache() to the publisher?

Hint: cache() stores the publisher's signal, which can hold stale values or errors. Design caching around data policies, ownership, TTL, and invalidation. It is neither a connection reuse mechanism nor a transaction consistency guarantee.

## 13. Key Takeaways for Working with Spring Data Relational R2DBC

- Subscription triggers publisher execution. Multiple subscriptions to a cold query publisher can run the SQL statement multiple times.
- Creating or reusing the same Mono/Flux variable does not automatically share results or connections.
- Connection pools reuse physical connections across multiple acquire/release cycles; they do not guarantee two independent operations use the same connection or session state.
- Reactive transactions bind a connection to the Reactor Context so operations participating in the same transaction share that connection.
- Use TransactionalOperator or @Transactional with reactive publishers and a matching ConnectionFactory.
- Do not call subscribe() or block() inside a reactive service/transaction; chain publishers instead.
- When multiple operations share one connection, serialize commands if the driver does not support concurrent execution on that connection.
- When managing a connection manually, release the resource on completion, error, or cancellation. Inside a Spring transaction, use ConnectionFactoryUtils if low-level access is required.
- cache() stores result signals, not connections; use it only with an explicit data caching policy.

When designing an R2DBC flow, clarify how many times the publisher is subscribed to, where connections are acquired and released, and whether statements need the same transaction. Those three questions help control SQL execution counts, use the connection pool effectively, and keep data consistent.
