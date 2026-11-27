# Avoiding Improper Concurrent Work on the Same Transaction Connection

In Spring Data Relational R2DBC, database operations within the same reactive transaction typically share a single connection bound to the Reactor Context by the transaction manager. Consequently, if a reactive pipeline issues multiple SQL statements concurrently via `flatMap`, `zip`, or `when`, those operations may access the same transaction-bound connection simultaneously.

Do not assume an R2DBC `Connection` can safely execute multiple statements concurrently. Concurrency support depends on the driver and database; some drivers reject overlapping operations, while others may queue them or enforce specific limits. Even when the driver accepts them, execution order and transaction state still need to be controlled.

**If multiple SQL statements must participate in the same transaction on the same connection, chain them sequentially using `then`, sequential `flatMap`, or `concatMap`.** Only run concurrently when tasks are genuinely independent, receive separate connections/transactions, and business logic permits independent commit or rollback.

## 1. Why do operations in the same transaction share a connection?

`R2dbcTransactionManager` manages transactions for a `ConnectionFactory`. When a reactive transaction starts, Spring acquires a `Connection`, starts the transaction, and binds the resource into the Reactor Context. `DatabaseClient` or repository operations using the same `ConnectionFactory` in the reactive chain can retrieve that bound connection.

General flow:

~~~text
Reactive transaction begins
             |
             v
Acquire one R2DBC Connection
             |
             v
Bind Connection to Reactor Context
             |
       +-----+------+
       |            |
       v            v
 Repository A   DatabaseClient B
       |            |
       +-----+------+
             |
             v
 Share transaction on that connection
             |
             v
       Commit / Rollback
             |
             v
        Release Connection
~~~

This is what allows operations across different repositories to commit or roll back together. However, it also means operations do not automatically receive separate connections simply because they sit in different reactive branches.

Reactor Context propagates with the subscription rather than depending on a fixed thread. Switching schedulers with `publishOn` or `subscribeOn` does not automatically create a new transaction or a new connection.

## 2. Why can issuing concurrent SQL on the same connection cause problems?

An R2DBC `Connection` is a stateful resource: it holds active transaction state, isolation, auto-commit mode, and ongoing protocol exchanges. Some drivers disallow multiple concurrent statements on one connection. Some drivers may serialize internally, yet you should not rely on that specific behavior as a portable guarantee.

When multiple branches emit statements concurrently on the same connection, the application may encounter:

- The driver throwing an error because the connection is busy or another exchange has not completed.
- The second statement waiting behind the first in an internal queue, eliminating any real concurrency gain from code structure.
- Completion ordering differing from the intended business order.
- One branch failing or cancelling while another branch is still executing.
- Difficulty determining which operations already ran before the transaction rolled back.
- Increased load on the connection and database without actual throughput gains.

Exact errors depend on the driver. You may see messages about concurrent statements, connection busy, protocol exchange, or transaction state. No single error message applies universally across all R2DBC drivers.

The core point is: reactive branches may be subscribed concurrently, yet doing so does not grant them independent transactional connections.

## 3. Operators that easily create concurrent queries

### flatMap

`flatMap` subscribes to inner publishers as source elements are emitted. By default, it can run multiple inner publishers concurrently:

~~~java
@Transactional
public Mono<Void> processOrder(Order order) {
    return Mono.when(
        inventoryRepository.reserve(order),
        orderRepository.save(order),
        auditRepository.save(toAudit(order))
    ).then();
}
~~~

In the example above, `Mono.when` subscribes to the input publishers to wait for all of them to complete. If they share the `ConnectionFactory` managed by the transaction manager, they may access the same transaction-bound connection simultaneously.

Another example:

~~~java
@Transactional
public Flux<CustomerView> loadViews() {
    return customerRepository.findAll()
        .flatMap(customer ->
            orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders ->
                    new CustomerView(customer, orders)
                )
        );
}
~~~

`flatMap` can issue multiple child queries concurrently. If the pipeline runs inside a transaction, those queries may contend for the same bound connection.

### zip

`Mono.zip` needs to subscribe to all sources to gather their results:

~~~java
@Transactional
public Mono<TransferView> loadTransferData(Long fromId, Long toId) {
    return Mono.zip(
        accountRepository.findById(fromId),
        accountRepository.findById(toId)
    ).map(tuple ->
        new TransferView(tuple.getT1(), tuple.getT2())
    );
}
~~~

Both queries can be subscribed concurrently. If they participate in the same reactive transaction, do not assume each query gets a different connection.

### parallel and runOn

~~~java
@Transactional
public Mono<Void> updateAll(List<Long> ids) {
    return Flux.fromIterable(ids)
        .parallel()
        .runOn(Schedulers.parallel())
        .flatMap(id -> customerRepository.refreshStatus(id))
        .sequential()
        .then();
}
~~~

`parallel()` splits data into multiple rails and `runOn()` schedules execution across threads. They do not automatically create separate transactions or connections per rail. If database operations use the active transaction context, they can still contend on the same connection.

### flatMapSequential

`flatMapSequential` preserves output emission order matching the source, yet can still subscribe to and execute inner publishers concurrently. It only reorders emitted results; it does not guarantee SQL executes sequentially on the same connection.

### concatMap

`concatMap` only subscribes to the next inner publisher after the current publisher finishes. This is the right choice when database operations must run one after another:

~~~java
return Flux.fromIterable(ids)
    .concatMap(id -> customerRepository.refreshStatus(id))
    .then();
~~~

## 4. Safe approach: chaining operations with then and flatMap

When business logic requires multiple database operations in the same transaction, chain them in the required order:

~~~java
@Transactional
public Mono<Void> placeOrder(Order order) {
    return inventoryRepository.reserve(order)
        .then(orderRepository.save(order))
        .flatMap(savedOrder ->
            orderLineRepository.saveAll(savedOrder.getLines())
                .then()
                .thenReturn(savedOrder)
        )
        .flatMap(savedOrder ->
            auditRepository.save(toAudit(savedOrder))
        )
        .then();
}
~~~

In this pipeline:

1. `reserve` completes before saving the order starts.
2. The order is saved before saving the order lines.
3. The order lines finish before writing the audit record.
4. The full publisher is returned for Spring to manage within the same transaction.

`then()` ignores the previous publisher's value and only subscribes to the next publisher once the previous one completes successfully. `flatMap` continues with a publisher built from the previous result.

If any step emits an error, the error propagates out of the reactive chain and the transaction rolls back by default on `RuntimeException` or `Error`. Do not self-subscribe inside the service.

### Multiple operations of the same type: use concatMap

If rows must be saved one by one in order:

~~~java
public Mono<Void> saveLines(List<OrderLine> lines) {
    return Flux.fromIterable(lines)
        .concatMap(orderLineRepository::save)
        .then();
}
~~~

`concatMap` guarantees each save completes before starting the next save. If the row count is very large, consider batch inserts or appropriate `saveAll` APIs instead of issuing one publisher per row; still, understand the semantics and driver execution behavior of your version.

## 5. Why avoid zip or when for SQL statements inside one transaction?

`zip` and `when` are very useful when sources can execute independently. However, when they emit multiple SQL statements on the same transaction-bound connection, they introduce unnecessary contention.

Example to avoid for write operations sharing one transaction:

~~~java
@Transactional
public Mono<Void> createCustomer(Customer customer) {
    return Mono.when(
        customerRepository.save(customer),
        auditRepository.save(toAudit(customer)),
        notificationRecordRepository.save(toNotification(customer))
    ).then();
}
~~~

If all three operations must commit together, chain them sequentially:

~~~java
@Transactional
public Mono<Void> createCustomer(Customer customer) {
    return customerRepository.save(customer)
        .flatMap(saved ->
            auditRepository.save(toAudit(saved))
                .then(notificationRecordRepository.save(
                    toNotification(saved)
                ))
        )
        .then();
}
~~~

This example also lets you use the database-generated ID from the first step in subsequent steps.

If the operations are genuinely independent and do not need the same transaction, they can run concurrently outside a shared transaction, or each task can have its own transaction. When doing so, accept that one task may commit while another fails.

## 6. Distinguishing operation serialization from preserving output order

These operators have distinct semantics:

| Operator | How inner publishers are handled | Guarantees non-concurrent execution? |
|---|---|---|
| `flatMap` | Can subscribe to multiple inner publishers simultaneously | No |
| `flatMapSequential` | Can run inner publishers concurrently, preserving output emission order | No |
| `concatMap` | Waits for current inner publisher to complete before subscribing to the next | Yes, along that chain |
| `then` | Runs the next publisher after the previous publisher completes | Yes, along that chain |
| `Mono.zip` | Combines results from multiple subscribed sources | No |
| `Mono.when` | Waits for multiple sources to complete | No |

If your goal is preserving result display order, `flatMapSequential` can help. If your goal is avoiding concurrent SQL on the same connection, use `concatMap` or sequential `then`/`flatMap` chaining.

Do not pick an operator based solely on output element ordering. Inspect when inner publishers are subscribed and when they perform I/O.

## 7. When is concurrent execution appropriate?

Concurrency is appropriate when tasks are data-independent and do not need to share a transaction-bound connection.

Examples:

- CPU computation over already-loaded data without executing SQL.
- Calling independent external services without holding a database transaction open.
- Processing independent messages where each message has its own transaction.
- Running independent batches where each batch uses its own transaction/connection and business logic permits independent commits.

The key condition is that each database branch requires its own transaction context and suitable connection. Changing schedulers alone is insufficient to achieve that.

### Independent CPU-bound tasks

After loading required data, pure CPU computations can run in parallel if the benefit is significant:

~~~java
return customerRepository.findAll()
    .collectList()
    .flatMapMany(customers ->
        Flux.fromIterable(customers)
            .parallel()
            .runOn(Schedulers.parallel())
            .map(this::calculateScore)
            .sequential()
    );
~~~

`calculateScore` in this example must compute over in-memory data without calling repositories or `DatabaseClient`. If it issues SQL, branches could again touch the same transaction context.

For heavy CPU work, weigh dataset size and memory impact of `collectList()`. Do not offload trivial computations to a parallel scheduler if coordination overhead outweighs the gain.

## 8. Running independent database tasks with separate transactions

If each item can commit or roll back independently, you can process multiple items concurrently while wrapping each item in its own transaction:

~~~java
public Flux<ProcessedResult> processIndependentItems(
        List<Command> commands) {

    return Flux.fromIterable(commands)
        .flatMap(
            command -> transactionalOperator.transactional(
                processOne(command)
            ),
            8
        );
}
~~~

In this structure:

- The entire outer method is not wrapped in a shared `@Transactional`.
- Each inner publisher is wrapped by `TransactionalOperator`.
- Each independent subscription can start its own transaction and acquire its own connection.
- A concurrency limit of 8 bounds how many transactions run concurrently in this example.
- A failing item rolls back only its own transaction; other items may have committed.

This strategy is valid only when business logic allows independence. If the entire list must succeed or fail as a single unit, you cannot split it into separate transactions while preserving overall atomicity. In that case, execute sequentially in one transaction or design an appropriate compensating/saga workflow.

If an outer transaction already exists, `TransactionalOperator`'s default `REQUIRED` propagation can cause inner operations to join the active transaction instead of starting independent transactions. Place boundaries carefully and use `REQUIRES_NEW` only when you truly want separate transactions, the transaction manager supports it, and business logic accepts that independence.

## 9. Limiting concurrency does not turn one transaction into multiple connections

You can pass a concurrency limit to `flatMap`:

~~~java
return Flux.fromIterable(commands)
    .flatMap(this::processCommand, 4);
~~~

This caps the number of active inner publishers. It does not mean Spring allocates four connections to four branches if they all run inside a single reactive transaction.

If `processCommand` executes SQL within the active transaction context, the branches can still share the same connection. Concurrency limits are helpful to protect systems from overload, yet they do not replace proper transaction boundary design.

To obtain multiple independent connections, each branch must genuinely execute within an independent transaction/subscription rather than inheriting an outer transaction context binding a shared connection.

## 10. Do not use schedulers to fix connection issues

R2DBC operations are designed to be non-blocking. Normally there is no need to wrap repository calls with `Schedulers.parallel()` or `subscribeOn` just to "run database calls on another thread."

Example that does not solve connection concurrency:

~~~java
@Transactional
public Mono<Void> update(Long id) {
    return customerRepository.findById(id)
        .subscribeOn(Schedulers.parallel())
        .flatMap(customer ->
            customerRepository.save(customer)
                .subscribeOn(Schedulers.parallel())
        )
        .then();
}
~~~

`subscribeOn` schedules subscription, yet the transaction resource propagates through Reactor Context. Switching threads does not automatically split transactions or allocate separate connections.

Do not use `block()` or `blockFirst()` to serialize R2DBC operations. That blocks threads, breaks the reactive flow, and can cause deadlocks or errors when executed on non-blocking schedulers.

If blocking libraries are involved, isolate blocking work from the R2DBC transaction and avoid holding connections/transactions while waiting on long blocking tasks. Switching schedulers does not turn JDBC or blocking I/O into reactive operations.

## 11. Keep transactions short and avoid calling external services inside transactions

A transaction holds a connection and may hold locks until commit or rollback. Calling an HTTP service, sending email, or waiting on slow processing inside a transaction keeps the connection occupied even while the database executes no SQL.

Example to avoid:

~~~java
@Transactional
public Mono<Order> placeOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            paymentClient.charge(saved)
                .thenReturn(saved)
        );
}
~~~

The payment call can be slow or time out while the database transaction remains open. If payment succeeds while the database transaction rolls back, the two systems can end up in an inconsistent state.

A generally better structure is:

1. Write the order and an outbox event within the same database transaction.
2. Commit the transaction.
3. A separate worker reads the outbox and calls payment/notification according to a retry policy.
4. Record the outcome or perform compensating actions when needed.

Outbox does not make an external service a member of the database transaction; it durably records the intent to emit an event alongside business data.

## 12. Example transfer requiring ordering

A money transfer needs to debit the source account, credit the destination account, and record the transfer. If all three must commit or roll back together, do not run the three SQL statements concurrently:

~~~java
@Transactional
public Mono<Void> transfer(
        Long fromId,
        Long toId,
        BigDecimal amount) {

    return accountRepository.debit(fromId, amount)
        .flatMap(debited ->
            accountRepository.credit(toId, amount)
        )
        .flatMap(credited ->
            transferRepository.record(
                fromId, toId, amount
            )
        )
        .then();
}
~~~

Each operation starts after the previous operation completes. The transaction manager maintains the same transaction context across the pipeline. If any operation emits an error matching rollback policy, the transaction rolls back.

In financial workflows, ordering also intersects with balance checks, optimistic/pessimistic locking, and isolation. Serializing statements on one connection does not by itself resolve all race conditions across different transactions. Use atomic conditional updates, `@Version`, locks, or isolation suited to business rules.

## 13. Example reading two records and combining results

If two queries need the same transaction to read a consistent snapshot or support a business decision, execute them sequentially:

~~~java
@Transactional
public Mono<TransferView> loadAccounts(Long fromId, Long toId) {
    return accountRepository.findById(fromId)
        .switchIfEmpty(Mono.error(
            new AccountNotFoundException(fromId)
        ))
        .flatMap(from ->
            accountRepository.findById(toId)
                .switchIfEmpty(Mono.error(
                    new AccountNotFoundException(toId)
                ))
                .map(to -> new TransferView(from, to))
        );
}
~~~

The second query starts only after the first returns. Both can share the same transaction and connection without issuing concurrent SQL.

If the same transaction or snapshot is not required and the two queries are truly independent, you can consider running them concurrently outside a shared transaction. Base the decision on data consistency requirements, not solely on wanting lower latency.

## 14. Error handling and cancellation when steps run sequentially

When publishers are chained with `then` or `concatMap`:

- The next step starts only after the previous step completes successfully.
- If a step emits `onError`, subsequent steps do not run.
- The error crosses the transaction boundary so Spring applies rollback policy.
- If the subscriber cancels, upstream is cancelled and the reactive transaction rolls back according to the transaction lifecycle.

Do not catch an error and turn it into `Mono.empty()` between steps if business logic requires rollback:

~~~java
return debit()
    .onErrorResume(error -> Mono.empty())
    .then(credit());
~~~

This snippet could proceed to `credit` even though `debit` failed. The publisher converted an error into normal completion, so the transaction may commit a broken business state.

To log errors, use `doOnError` and let the error continue propagating out. To translate errors into domain errors, use `onErrorMap` while preserving the `onError` signal.

## 15. Monitoring signs of improper connection usage

When troubleshooting errors or poor performance in reactive transactions, observe:

- Which SQL statements execute within the same request/transaction.
- Whether multiple statements start before the previous statement finishes.
- Whether the driver reports connection busy, concurrent request, or protocol exchange errors.
- Connection hold time and acquire wait time.
- Active/idle connection counts in the pool.
- Transaction duration and statement counts per transaction.
- Whether any publisher is cancelled or timed out while the transaction is active.

Distributed tracing can reveal overlapping database spans inside a single transaction. SQL logs and connection pool metrics help distinguish concurrency contention from slow queries or pool exhaustion.

Do not enable logging of sensitive query parameters in production merely to inspect concurrency. Use query fingerprints, trace IDs, and properly redacted timing information.

## 16. Testing to detect concurrent access within the same transaction

Write integration tests using a real R2DBC driver and database or Testcontainers:

1. Open a reactive transaction.
2. Run multiple repository operations on the same `ConnectionFactory`.
3. Verify operations serialized with `then`/`concatMap` complete in the expected order.
4. Test that when one operation fails, all changes in the transaction roll back.
5. Check whether code using `flatMap`/`zip` triggers errors or different behavior on your deployed driver.
6. When processing concurrently with separate transactions, confirm each item has an independent transaction and commits/rolls back properly.
7. Measure connections used and concurrent statements if instrumentation is available.

Do not rely on mocked repositories to prove whether a driver allows or rejects concurrent statements on the same connection. That semantics must be verified against the real driver.

## 17. Organization decision table

| Requirement | Appropriate approach |
|---|---|
| Multiple SQL statements must share an atomic transaction | Chain sequentially via `then`/`flatMap`/`concatMap` |
| Save multiple elements in order | `Flux.concatMap` or an appropriate batch API |
| Preserve result order while tasks are independent | `flatMapSequential` may be used after confirming separate connections/transactions |
| Multiple independent tasks, each committing on its own | Each task gets its own transaction and connection; bound concurrency |
| CPU computation on already-fetched data | Parallelize computation without calling SQL inside rails |
| HTTP calls or sending emails | Avoid holding database transactions open; consider outbox |
| All items must succeed or fail together | One shared transaction with sequential SQL operations |
| Want to reduce query latency | Optimize SQL/indexes or batch queries; do not fire concurrent statements on the same connection |

## 18. Common mistakes

| Practice | Issue | Fix |
|---|---|---|
| `Mono.when` across repository calls in one transaction | Multiple SQL queries may run concurrently on the same connection | Chain sequentially with `then`/`flatMap` |
| `Mono.zip` across two queries in a transaction | Both sources are subscribed concurrently | Run the second query after the first if sharing one connection |
| `flatMap` child query per entity | Creates concurrent queries and likely N+1 | Batch query or `concatMap` when sequential execution is needed |
| `flatMapSequential` assumed to serialize SQL | Inner publishers can still run concurrently | Use `concatMap` |
| `parallel()`/`runOn()` to split DB connections | Schedulers do not create new transactions/connections | Design separate transactions explicitly |
| Capping `flatMap` concurrency thinking it splits connections | Branches can still share the transaction context | Use independent transactions if business logic allows |
| `subscribe()` inside services | Spawns subscription outside caller lifecycle | Return publishers and compose |
| `block()` to wait between SQL statements | Blocks threads and breaks reactive flow | Use `then`/`concatMap` |
| Calling HTTP inside a transaction | Holds connection/locks while waiting on network | Separate side effects; consider outbox |
| Splitting transactions for workflows requiring full atomicity | One part can commit while another fails | Keep one transaction and run sequentially |

## 19. Decision workflow

Before using a concurrent operator in an R2DBC service, determine:

1. Which operations truly need to belong to the same transaction?
2. Do the operations use the same `ConnectionFactory` and transaction manager?
3. Does the operator subscribe to multiple inner publishers concurrently?
4. Do those inner publishers execute SQL on the transaction-bound connection?
5. Does SQL ordering matter to business correctness?
6. If split into separate transactions, does business logic accept partial commits?
7. Is a concurrency limit needed to protect the pool and database?
8. Does the actual driver support concurrent statements on one connection, and is there any valid reason to depend on it?
9. Can N+1 queries be replaced by a `JOIN` or batch query?
10. Have commit, rollback, cancellation, and final outcomes been tested on the real driver?

If multiple operations must be atomic within one transaction, default to running SQL sequentially. If you want higher concurrency, break work into independent units with separate transactions/connections and explicitly design the semantics when one unit fails.

## 20. Key takeaways

- `R2dbcTransactionManager` binds one connection to Reactor Context for a reactive transaction.
- Repositories and `DatabaseClient` using the same `ConnectionFactory` in a transaction typically share that transaction-bound connection.
- Do not assume multiple statements can safely execute concurrently on the same connection; exact behavior depends on the driver.
- `flatMap`, `zip`, `when`, and `parallel` can create concurrent subscriptions or I/O.
- `flatMapSequential` preserves output emission order but does not guarantee inner SQL runs sequentially.
- `then` and `concatMap` serialize database operations one after another within the same transaction.
- Switching schedulers does not automatically allocate new connections or transactions.
- Concurrency limits reduce active branches at once, yet do not split connections if branches share a transaction context.
- Parallelize database work only when each branch has its own transaction/connection and business logic permits independence.
- Do not call `subscribe()` or `block()` inside services to enforce ordering.
- Keep transactions short; avoid waiting on HTTP, email, or external tasks while holding a connection.
- Test against a real R2DBC driver to verify connection behavior, ordering, rollback, and cancellation.
