# Transactions Ineffective Due to Proxy, Context, or Thread Boundaries

## 1. Identifying the Problem

In Spring Data Relational R2DBC, a method annotated with `@Transactional` may still commit partial data, fail to roll back on error, or have repository calls appear to execute outside a transaction. This is usually a transaction boundary problem: Spring fails to intercept the call, the transaction manager does not manage the right `ConnectionFactory`, the Reactor Context does not flow along with the publisher, or database operations have detached from the returned reactive stream.

Common symptoms:

- A method has `@Transactional`, yet an error in the second operation fails to roll back the first operation.
- Calling a transactional method from another method in the same class does not apply the transaction.
- Repository `save` is called via `subscribe()` inside a service; the method returns before the operation completes.
- Data is persisted even though the publisher terminated with an error the developer expected to trigger rollback.
- One repository participates in the transaction, while another commits independently.
- Code running on another thread appears to lose the transaction.
- A test with `@Transactional` leaves data behind after the test or fails to reflect production behavior.
- A publisher is created inside the method but never composed into the final returned publisher.

You must identify precisely which transaction is expected, which operations must commit/roll back together, and which publisher is actually subscribed. The annotation is only part of the mechanism; reactive transactions are bound to the subscription and Reactor Context.

## 2. Lifecycle of a Reactive Transaction

With R2DBC, Spring normally uses `ReactiveTransactionManager`, most commonly `R2dbcTransactionManager`. The transaction manager acquires a connection from `ConnectionFactory`, begins the transaction, and binds the resource into the current subscription's Reactor Context.

Overview flow:

~~~text
Caller invokes service through Spring proxy
                 |
                 v
        Service returns Publisher
                 |
                 v
          Caller subscribes
                 |
                 v
    Transaction interceptor / operator
                 |
                 v
     ReactiveTransactionManager
                 |
                 v
      Acquire R2DBC Connection
                 |
                 v
      Bind resource to Reactor Context
                 |
                 v
       Repository / DatabaseClient
                 |
                 v
        Execute SQL statements
                 |
          +------+------+
          |             |
          v             v
       Complete        Error
          |             |
          v             v
        COMMIT        ROLLBACK
          |             |
          +------+------+
                 |
                 v
       Release / cleanup connection
~~~

The critical difference compared to imperative transactions is that reactive transactions are not propagated primarily via `ThreadLocal`. They attach to the reactive subscription and Reactor Context. An unchained publisher, a manual subscription, or a different `ConnectionFactory` can prevent operations from joining the expected transaction.

Furthermore, reactive publishers are typically lazy. Calling a repository method normally only builds a `Publisher`; SQL executes upon subscription. Thus, a Java method may return a `Publisher` before the transaction even begins.

## 3. Proxy Fails to Intercept Method Calls

Spring declarative transactions are normally implemented via AOP proxies. A call must pass through the proxy for the transaction interceptor to run. There are several ways code accidentally bypasses the proxy.

### 3.1. Self-Invocation Within the Same Class

This is the most common cause.

Example:

~~~java
@Service
class OrderService {

    public Mono<Void> placeOrder(CreateOrderCommand command) {
        return saveOrderAndLines(command);
    }

    @Transactional
    public Mono<Void> saveOrderAndLines(CreateOrderCommand command) {
        return orderRepository.save(toOrder(command))
                .flatMap(order ->
                        orderLineRepository.saveAll(toLines(order.id(), command))
                                .then()
                );
    }
}
~~~

If `placeOrder` calls `saveOrderAndLines` directly via `this` on the same instance, the call bypasses the Spring proxy. The transaction interceptor on `saveOrderAndLines` will not run.

The preferred fix is placing the transaction boundary on a public method invoked from another bean:

~~~java
@Service
class OrderService {

    private final OrderPersistenceService persistenceService;

    OrderService(OrderPersistenceService persistenceService) {
        this.persistenceService = persistenceService;
    }

    public Mono<Void> placeOrder(CreateOrderCommand command) {
        return persistenceService.saveOrderAndLines(command);
    }
}

@Service
class OrderPersistenceService {

    @Transactional
    public Mono<Void> saveOrderAndLines(CreateOrderCommand command) {
        return orderRepository.save(toOrder(command))
                .flatMap(order ->
                        orderLineRepository.saveAll(toLines(order.id(), command))
                                .then()
                );
    }
}
~~~

The call from `OrderService` to `OrderPersistenceService` goes through the persistence bean's proxy. Alternatively, `TransactionalOperator` can express the transaction boundary directly in the publisher pipeline.

Do not shuffle `@Transactional` across multiple methods without identifying which method is the true transaction entry point.

### 3.2. Instantiating Objects Manually with `new`

Example:

~~~java
OrderService service = new OrderService(repository);
service.placeOrder(command);
~~~

An object instantiated with `new` is not a Spring-managed bean. Spring creates no proxy for that instance, injects no transaction interceptor, and applies no related bean post-processors.

Inject beans from the `ApplicationContext` via constructor injection. In tests, use a Spring context when you need to verify real proxies; unit tests constructing objects with `new` test business logic, not `@Transactional` behavior.

### 3.3. Private, Final Methods, or Final Classes

Interception depends on the proxy strategy:

- JDK dynamic proxies intercept calls through interface proxies.
- Class-based proxies use subclassing and cannot override `final` or `private` methods.
- `final` classes cannot be subclassed by CGLIB.
- Internal calls via `this` still bypass the proxy even if the method is `public`.

Spring may support additional visibility modes with class-based proxies depending on configuration/version, but the most predictable rule is placing transaction boundaries on `public`, non-`final` methods of a Spring bean invoked from another bean.

Do not annotate a `private` helper with `@Transactional` expecting it to start an independent transaction. Private helpers should run inside an already-intercepted transactional method or move to a separate bean if a distinct boundary is needed.

### 3.4. Methods Called Inside Constructors or Before Proxy Initialization

Do not invoke transactional methods from a bean's constructor or initialization logic before bean proxy creation completes. During construction, the object being initialized is not yet the proxy callers receive later.

Move transactional work into service methods invoked after context startup, an application runner, or an appropriate orchestration component.

### 3.5. Annotation Present, Yet Another Method Path Is Invoked

The annotation may live on an overloaded method, interface, or different implementation than the one actually called. Check:

- Which implementation bean was injected?
- Does the call go through an interface proxy or class proxy?
- Which method/class holds the annotation?
- Did an overriding method alter annotations?
- Is the method invoked via another reference or manually instantiated object?
- Is AOP proxy mode configured differently than expected?

Do not just grep for `@Transactional` in source code and assume the call is definitely intercepted.

## 4. Selecting the Right Transaction Manager

An application may have multiple transaction managers, especially during JDBC/JPA and R2DBC coexistence.

Common types:

- `PlatformTransactionManager`, such as `JpaTransactionManager` or `DataSourceTransactionManager`, for imperative transactions.
- `ReactiveTransactionManager`, such as `R2dbcTransactionManager`, for reactive transactions.
- Distinct transaction managers per database or resource.

If the application has both `JpaTransactionManager` and `R2dbcTransactionManager`, do not leave Spring guessing which manager an annotation needs. Specify the R2DBC manager explicitly:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderLineRepository.saveAll(toLines(order.id(), command))
                            .thenReturn(order)
            );
}
~~~

The bean name in the example must match your application's actual bean name. Spring Boot can auto-configure an R2DBC manager; when declaring multiple managers manually, name them clearly and verify which bean gets chosen.

If `JpaTransactionManager` is mistakenly chosen for an R2DBC publisher, the JPA transaction does not automatically manage R2DBC connections. Likewise, `R2dbcTransactionManager` does not automatically manage JDBC `Connection` or `EntityManager`.

### 4.1. Checking the Return Type

A reactive transaction manager requires a reactive return type, such as `Mono`, `Flux`, or `Publisher`. If a method returns `void`, a primitive, or a synchronous object while creating and discarding a `Publisher` internally, the reactive transaction does not wrap that publisher.

Incorrect example:

~~~java
@Transactional
public void createOrder(Order order) {
    orderRepository.save(order);
}
~~~

`save` returns a `Publisher` that is never returned or subscribed in a controlled manner. The `void` method exits before the reactive operation runs.

Correct example:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order);
}
~~~

If a method performs multiple operations, return a single publisher representing all the work, chaining steps with `flatMap`, `then`, `concatMap`, or suitable operators.

### 4.2. Multiple ConnectionFactories

`R2dbcTransactionManager` manages one specific `ConnectionFactory`. Repositories or `DatabaseClient` join the transaction only when they use the same `ConnectionFactory` resource managed by that transaction manager.

If an application defines two `ConnectionFactory` beans—or creates two separate pools for the same database—the transaction manager for pool A does not automatically bind connections for repositories using pool B.

Configuration example:

~~~java
@Bean
ConnectionFactory primaryConnectionFactory() {
    // Create pooled ConnectionFactory for the primary database.
}

@Bean
ConnectionFactory reportingConnectionFactory() {
    // Create pooled ConnectionFactory for the reporting database.
}

@Bean
ReactiveTransactionManager primaryR2dbcTransactionManager(
        @Qualifier("primaryConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}
~~~

Ensure repositories, `DatabaseClient`, and the transaction manager are wired with their corresponding `ConnectionFactory`. Check bean qualifiers, repository `basePackages`, and custom templates.

A transaction on the primary database does not automatically span operations on the reporting database. If atomic changes across multiple databases/resources are needed, design an appropriate coordination mechanism; do not assume a plain `@Transactional` creates a distributed transaction.

## 5. Reactive Transactions Use Reactor Context, Not ThreadLocal

Imperative transactions typically bind resources to threads via `ThreadLocal`. Reactive pipelines can switch threads across operators, so Spring uses Reactor Context to propagate transaction resources and synchronizations.

This means:

- Normal `publishOn` and `subscribeOn` do not drop Reactor Context by themselves.
- Switching threads does not automatically lose the transaction.
- Reading transaction/security state from `ThreadLocal` can return wrong or missing state.
- Creating a new standalone subscription does not inherit the original subscription's transaction context.
- Crossing into callbacks/executors or non-Reactor APIs may require explicit context bridging.

Do not use imperative `TransactionSynchronizationManager` or `TransactionAspectSupport` to inspect reactive transaction state. Those imperative APIs rely on thread-bound state.

When you need to inspect the active reactive transaction, use the reactive transaction context API for your Spring version, or observe via integration tests and transaction manager instrumentation.

### 5.1. `publishOn` and `subscribeOn` Are Not the Default Cause of Lost Transactions

Example:

~~~java
return orderRepository.findById(id)
        .publishOn(Schedulers.parallel())
        .flatMap(order ->
                orderRepository.save(order.withStatus("PROCESSING"))
        );
~~~

Reactor Context propagates through standard Reactor operators. Switching schedulers here does not drop the transaction automatically.

Problems usually arise when code leaves the chain, reads `ThreadLocal`, or starts a new reactive stream unattached to the managed publisher.

Do not fix context issues by blindly removing `publishOn`/`subscribeOn`. Locate where context is actually severed.

### 5.2. `ThreadLocal` Is Not Where Actors or Transactions Live in Reactive Flows

A helper like:

~~~java
String actor = SecurityContextHolder.getContext()
        .getAuthentication()
        .getName();
~~~

relies on the imperative `SecurityContextHolder` and may miss the identity in a WebFlux reactive flow. Likewise, custom `ThreadLocal` variables do not travel automatically with Reactor Context.

Use `ReactiveSecurityContextHolder` for reactive Spring Security, and Reactor Context or context-aware abstractions for custom metadata. Do not infer the actor or tenant from the current thread.

## 6. `subscribe()` Inside a Service Creates a Separate Transaction Boundary

This is a very common pitfall when transitioning from imperative to reactive code.

Incorrect example:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> createOrder(CreateOrderCommand command) {
    orderRepository.save(toOrder(command))
            .subscribe();

    return Mono.empty();
}
~~~

What happens:

1. The method builds the `save` publisher.
2. `subscribe()` starts an independent subscription immediately inside the method.
3. The returned publisher is `Mono.empty()`.
4. The transaction interceptor manages the returned empty publisher, not necessarily the manually started `save` subscription.
5. The caller sees the method finish while `save` may still be running.

Replace with composition:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .then();
}
~~~

When multiple operations are needed:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(saved ->
                    orderLineRepository.saveAll(toLines(saved.id(), command))
                            .thenReturn(saved)
            );
}
~~~

Every database operation must be part of the returned publisher. The caller subscribes to the final publisher; the transaction interceptor or `TransactionalOperator` manages that same subscription.

### 6.1. `subscribe()` Inside `doOnNext` Also Detaches Side Effects

Example:

~~~java
return orderRepository.findById(id)
        .doOnNext(order ->
                auditRepository.save(toAudit(order)).subscribe()
        );
~~~

The audit save runs in its own subscription. It does not join the `findById` publisher's transaction and may complete before or after the main flow.

Chain the audit operation into the pipeline:

~~~java
return orderRepository.findById(id)
        .flatMap(order ->
                auditRepository.save(toAudit(order))
                        .thenReturn(order)
        );
~~~

If both operations must be atomic, ensure the entire chain sits inside the reactive transaction and both repositories share the same `ConnectionFactory`.

### 6.2. `block()` Also Creates a Separate Subscription

Do not call `block()` to extract reactive results inside a reactive transaction:

~~~java
@Transactional
public Mono<Void> update(Long id) {
    Order order = orderRepository.findById(id).block();
    // ...
    return Mono.empty();
}
~~~

`block()` subscribes and blocks. It may run outside the expected transaction context, block threads, or deadlock if called on an event-loop thread. Replace with `flatMap`/`map`/`then` to maintain a single reactive chain.

## 7. Publishers Created Without Being Chained Into the Flow

Reactive code can instantiate a `Publisher` without subscribing to it. No SQL runs in that case.

Example:

~~~java
@Transactional
public Mono<Void> create(Order order, AuditEvent event) {
    Mono<Order> saveOrder = orderRepository.save(order);
    Mono<AuditEvent> saveAudit = auditRepository.save(event);

    return saveOrder.then();
}
~~~

`saveAudit` is never connected to the returned publisher. It never executes.

Chain both:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> create(Order order, AuditEvent event) {
    return orderRepository.save(order)
            .then(auditRepository.save(event))
            .then();
}
~~~

If the audit event needs the order's generated ID:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> create(Order order, Function<Long, AuditEvent> eventFactory) {
    return orderRepository.save(order)
            .flatMap(saved ->
                    auditRepository.save(eventFactory.apply(saved.id()))
            )
            .then();
}
~~~

Patterns to watch for in code:

- Publishers assigned to local variables that are never returned, composed, or intentionally subscribed.
- Using `map` producing nested `Mono`/`Flux` instead of `flatMap`.
- Calling repositories inside imperative callbacks and ignoring the result.
- Returning `Mono.empty()` despite constructing another publisher.
- Using `thenReturn` or `onNext` in ways that drop a publisher carrying side effects.

### 7.1. `map` and `flatMap` Differ

`map` is for synchronous transformations:

~~~java
Mono<OrderSummary> summary =
        orderRepository.findById(id)
                .map(this::toSummary);
~~~

`flatMap` is used when the transformation returns a `Publisher`:

~~~java
Mono<Customer> customer =
        orderRepository.findById(id)
                .flatMap(order ->
                        customerRepository.findById(order.customerId())
                );
~~~

Using `map` with a function returning `Mono` creates `Mono<Mono<Customer>>`. The inner publisher does not run until flattened/subscribed. Use `flatMap` to chain dependent reactive operations.

## 8. Swallowing Errors Causes Transactions to Commit

Reactive transactions usually commit when the publisher completes successfully and roll back when the publisher emits an error matching rollback rules. If code turns an error into completion before it reaches the transaction boundary, the transaction can commit.

Example:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> transfer(...) {
    return debitAccount(...)
            .then(creditAccount(...))
            .onErrorResume(error -> {
                log.warn("Transfer failed", error);
                return Mono.empty();
            });
}
~~~

`onErrorResume` converts the error into `Mono.empty()`. To the transaction manager, the publisher completed cleanly; rollback is no longer triggered by the swallowed error.

To roll back while logging, keep the error signal:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> transfer(...) {
    return debitAccount(...)
            .then(creditAccount(...))
            .doOnError(error ->
                    log.warn("Transfer failed", error)
            );
}
~~~

`doOnError` only observes the error without altering the signal. The error continues to the transaction boundary.

If you need to translate the exception to another type, emit a new error:

~~~java
return work()
        .onErrorMap(DatabaseException.class,
                error -> new TransferFailedException(error));
~~~

### 8.1. Placement of `onErrorResume` Determines Rollback

These two placements have opposite semantics:

~~~java
// Error crosses the transaction boundary first, then gets handled.
return transactionalOperator.transactional(work)
        .onErrorResume(error -> fallback());
~~~

~~~java
// Error is handled inside the transaction boundary.
return transactionalOperator.transactional(
        work.onErrorResume(error -> fallback())
);
~~~

In the first example, the transaction operator sees the error and can roll back before the caller applies the fallback. In the second example, the transaction operator sees only a clean completion from the fallback and can commit.

Place error recovery at the right business boundary. If the fallback is part of the transaction and intended to commit, that may be intentional. If failure means the entire operation must roll back, let the error cross the transaction boundary.

### 8.2. `Mono.empty()` Is a Successful Completion

`Mono.empty()` is not an error. Transactions typically commit when a publisher completes empty without a rollback-only marker or other error.

Example:

~~~java
return orderRepository.findById(id)
        .switchIfEmpty(Mono.empty())
        .flatMap(this::updateOrder);
~~~

If the order is not found, the publisher completes empty. That does not roll back automatically. If business rules treat a missing order as a failure, emit an exception:

~~~java
return orderRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new OrderNotFoundException(id)
        ))
        .flatMap(this::updateOrder);
~~~

Do not use empty as a rollback signal. Distinguish "no data found" from "transaction must fail."

### 8.3. Checked Exceptions and Rollback Rules

Spring transactions by default roll back on `RuntimeException` and `Error`. Checked exceptions do not trigger rollback automatically without explicit rules.

If a reactive pipeline emits a checked exception and business logic requires rollback, declare it explicitly:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    rollbackFor = ImportRejectedException.class
)
public Mono<Void> importData(...) {
    return performImport(...);
}
~~~

Verify rollback rules for your Spring Framework version and actual exception types. Do not check only logs; verify database state after the transaction.

## 9. Transaction Boundaries Failing to Cover All Operations

A method may execute multiple repository calls while only some sit inside the transactional chain.

Example:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order -> {
                notificationRepository.save(toNotification(order)).subscribe();
                return orderLineRepository.saveAll(toLines(order.id(), command))
                        .thenReturn(order);
            });
}
~~~

`Order` and `OrderLine` participate in the transaction, while the notification save runs on an independent subscription. If `orderLineRepository` fails, the notification may still commit.

Fix with composition:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderLineRepository.saveAll(toLines(order.id(), command))
                            .then(notificationRepository.save(toNotification(order)))
                            .thenReturn(order)
            );
}
~~~

If notification means sending a message to an external system, do not make network calls directly inside a database transaction expecting atomicity. Write an outbox row in the same transaction and publish after commit.

## 10. Mixing JDBC/JPA and R2DBC in a Single Transaction

A hybrid application may contain both `JpaTransactionManager` and `R2dbcTransactionManager`. They manage two distinct resource types.

Example:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> updateBoth(...) {
    return r2dbcRepository.save(...).then(
            Mono.fromRunnable(() -> jpaRepository.save(...))
    );
}
~~~

The R2DBC transaction manager does not enlist a JDBC connection or `EntityManager`. The JPA save may execute in another imperative transaction—or with no transaction at all if unconfigured. If R2DBC commit fails after JPA has committed, data can drift out of sync.

Do not treat a single method annotation as a distributed transaction. Options:

- Keep all atomic operations within one persistence technology/resource when possible.
- Split into independent steps with a state machine.
- Use transactional outbox with idempotent consumers.
- Use sagas/compensating actions for multi-resource workflows.
- Use distributed transactions only when the entire resource stack explicitly supports and verifies them.

During migrations, avoid writing via both JPA and R2DBC in one use case without an explicit consistency design.

## 11. Using `TransactionalOperator` When You Want Explicit Boundaries

`TransactionalOperator` wraps a publisher in a transaction explicitly.

Configuration:

~~~java
@Configuration
class TransactionConfiguration {

    @Bean
    TransactionalOperator r2dbcTransactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

When multiple managers exist, inject the right manager using a qualifier:

~~~java
@Bean
TransactionalOperator r2dbcTransactionalOperator(
        @Qualifier("r2dbcTransactionManager")
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

Usage:

~~~java
@Service
class TransferService {

    private final TransactionalOperator tx;
    private final AccountRepository accounts;

    TransferService(
            TransactionalOperator tx,
            AccountRepository accounts) {
        this.tx = tx;
        this.accounts = accounts;
    }

    Mono<Void> transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        Mono<Void> work =
                accounts.debit(fromId, amount)
                        .then(accounts.credit(toId, amount));

        return tx.transactional(work);
    }
}
~~~

`TransactionalOperator` makes it clear exactly which publisher is wrapped. It does not automatically fix bugs caused by calling `subscribe()` inside, using another `ConnectionFactory`, or swallowing errors.

### 11.1. Using `execute` When `TransactionStatus` Is Needed

`TransactionalOperator` also accepts a callback returning a `Publisher` via `execute`:

~~~java
Mono<Void> work =
        tx.execute(status ->
                accounts.debit(fromId, amount)
                        .then(accounts.credit(toId, amount))
        ).then();
~~~

This fits when you need to interact with `TransactionStatus` inside the callback. Do not call `subscribe` inside the callback; return the `Publisher` so the operator controls its lifecycle.

### 11.2. Do Not Wrap Unrelated Publishers Inside a Transaction

A transaction should wrap only the group of operations requiring atomicity. Wrapping an entire HTTP request, streaming export, or unrelated tasks can hold connections open too long.

Define boundaries around business invariants: which changes must commit or roll back together? Only those operations belong inside the transaction.

## 12. Nested Calls and Propagation

A transactional method calling another transactional method may join the existing transaction or require different semantics depending on propagation.

Points to verify:

- `REQUIRED` normally joins an existing transaction or starts a new one if none exists.
- `REQUIRES_NEW` requests an independent transaction as supported by the transaction manager.
- `SUPPORTS`/`NOT_SUPPORTED` and other propagation modes alter how transactions are joined.
- `NESTED`/savepoints depend on transaction manager and driver support.

Do not assume imperative and reactive propagation behave identically across all versions/drivers. When using `REQUIRES_NEW` or savepoints, test the capabilities of `R2dbcTransactionManager` and your specific R2DBC driver.

Self-invocation remains an issue: a propagation annotation on an internal method is ignored if the call bypasses the proxy. When a distinct transaction boundary is needed, move the method to another bean or use `TransactionalOperator` with the appropriate manager.

## 13. Streaming `Flux` Can Prolong Transactions

When a transactional method returns a `Flux`, the transaction can remain open for as long as the stream is being consumed, until completion, error, or cancellation.

Example:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Flux<Document> exportDocuments(UUID tenantId) {
    return documentRepository.findAllByTenantId(tenantId)
            .map(this::toExportRow);
}
~~~

If clients read slowly or downstream processes slowly, the transaction and connection stay open longer. This increases connection hold duration, retains snapshots/locks depending on the query, and creates pool pressure.

Consider:

- Is a single consistent transaction really needed for the entire export?
- Can keyset pagination process in batches?
- Can a dedicated snapshot/export job be used?
- Should concurrent streams be capped?
- Have cancellation and cleanup behaviors been tested?

Do not buffer massive datasets into memory just to close the transaction early. Pick an appropriate pagination or export workflow.

## 14. Cancellation and Timeouts

Reactive transactions receive cancellation signals when the caller cancels the subscription or a timeout fires. The transaction manager must clean up resources and roll back open transactions per driver semantics.

However:

- Cancellation cannot undo an already-committed transaction.
- A timeout placed outside the transaction cancels the publisher and triggers asynchronous cleanup.
- If a timeout wraps only an inner publisher and its error is swallowed, the transaction may not roll back as intended.
- A write committed on the database before response loss can still leave the client uncertain of the outcome.

For critical writes, use idempotency keys or status checks to handle retries safely. Never treat cancellation as proof that the database wrote nothing.

Example:

~~~java
return transactionalOperator.transactional(work)
        .timeout(Duration.ofSeconds(3));
~~~

Here, the timeout sits downstream of the publisher wrapped by the transaction operator. When timeout cancels upstream, the transaction manager gets the chance to perform cancellation/rollback. Test against the real driver to confirm cleanup and resulting data state.

## 15. Context Detached When Integrating with Callbacks or Non-Reactor APIs

Standard Reactor operators propagate Reactor Context. However, context can be lost when code:

- Calls `subscribe()` manually.
- Switches to an `Executor`/`CompletableFuture` without bridging context.
- Registers callbacks with libraries unaware of Reactor Context.
- Creates a new publisher and subscribes independently.
- Uses `ThreadLocal` to read transactions or actors.
- Calls a synchronous service and starts a fresh reactive chain from its result.

When bridging to non-Reactor APIs, use context-propagation mechanisms appropriate for your Spring/Reactor versions and keep resource lifecycles inside managed chains.

Never attempt to pass `Connection` or `TransactionStatus` objects around in global variables. Connections must be managed by the transaction manager and corresponding reactive lifecycle.

## 16. Common Configuration Errors

### 16.1. Repository and Transaction Manager Use Different `ConnectionFactory` Beans

Check:

- `ConnectionFactory` bean used by the repository.
- `ConnectionFactory` bean used by `DatabaseClient`.
- `ConnectionFactory` passed into `R2dbcTransactionManager`.
- Qualifiers in multi-database configurations.
- Whether pool wrappers or decorators produce different resource keys.

Having the same database URL does not mean sharing the same `ConnectionFactory` resource. Transaction resource binding keys off the configured `ConnectionFactory`, not just hostname/database name.

### 16.2. Missing R2DBC Transaction Manager

If no matching `ReactiveTransactionManager` exists, annotations may pick another manager or transaction setup will not behave as expected. Inspect actual beans in the `ApplicationContext` and the interfaces they implement.

Do not rely merely on method or class names. A `PlatformTransactionManager` bean is not a reactive manager.

### 16.3. Ambiguous Multi-Manager Configuration

If both JDBC/JPA and R2DBC managers exist, specify `transactionManager` explicitly on `@Transactional` or create `TransactionalOperator` with a qualified manager injection.

Do not rely on bean registration order or assume the default manager is always R2DBC.

### 16.4. Repository Uses a Different `DatabaseClient`

A custom `DatabaseClient` may be constructed from a different `ConnectionFactory` than the main repositories. If the transaction manager manages only factory A, SQL executed via client B does not join transaction A.

Ensure all components in an atomic unit share the same factory/transaction manager.

## 17. Testing to Prove Transactions Actually Work

Unit tests with mocks cannot prove database commits/rollbacks. You need integration tests using real repositories, a real R2DBC driver, and an appropriate database.

A rollback test should:

1. Create fixture data with a distinct business key.
2. Perform at least two write operations in one transaction.
3. Intentionally emit an error after the first write or between steps.
4. Consume the publisher through the error.
5. After the transaction completes, read data using an operation outside that transaction.
6. Confirm none of the atomic group's changes were committed.

Example with `TransactionalOperator`:

~~~java
@Test
void shouldRollbackAllWritesWhenSecondStepFails() {
    Mono<Void> work =
            orderRepository.save(orderWithKey("tx-test-1"))
                    .then(Mono.error(
                            new IllegalStateException("force rollback")
                    ));

    StepVerifier.create(transactionalOperator.transactional(work))
            .expectError(IllegalStateException.class)
            .verify();

    StepVerifier.create(orderRepository.existsByBusinessKey("tx-test-1"))
            .expectNext(false)
            .verifyComplete();
}
~~~

Adapt the example to your real repositories. The crucial point is that the assertion reads state after the transaction finishes and is not masked by an outer test transaction.

### 17.1. Verifying Real Proxies

In integration tests, inject services from the Spring context:

~~~java
@SpringBootTest
class OrderTransactionIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    // Test invokes the Spring-managed bean.
}
~~~

Do not instantiate `new OrderService(...)` when testing AOP proxies. You can check whether a service is an AOP proxy via Spring AOP utilities, though testing real commit/rollback behavior is far stronger evidence.

### 17.2. Do Not Confuse Test-Managed Transactions with Reactive Transactions

A test method annotated with `@Transactional` does not automatically prove every reactive publisher ran in the intended transaction. Test transaction management depends on Spring Framework/TestContext versions and the transaction manager type.

For reactive tests, verify actual transaction boundaries using `ReactiveTransactionManager`/`TransactionalOperator` and check database state after completion. Even if your version's test framework supports reactive transactional tests, ensure publishers subscribe within the framework-managed lifecycle.

When testing service rollbacks, avoid wrapping the entire test in an outer transaction that discards changes at test end, as that prevents assertions from proving the inner transaction rolled back.

### 17.3. Testing Swallowed Errors

Write tests for both behaviors:

- Error crosses the transaction boundary: expect rollback.
- Error handled inside the transaction and publisher completes: expect commit unless marked rollback-only.

This clarifies `onErrorResume` placement and prevents accidentally turning failures into silent commits.

### 17.4. Testing Cancellation and Timeouts

For cancellable operations, use `StepVerifier` or coordinated test utilities to cancel the subscription. After cleanup, inspect database state and the connection pool.

Do not use arbitrary `Thread.sleep` calls to guess whether a transaction rolled back. Use terminal signals, latches, or bounded synchronization mechanisms. Run against the production driver/database if cancellation semantics are critical.

## 18. Ordered Diagnostic Procedure

When a transaction seems ineffective, check in order to pinpoint the failing layer.

### Step 1: Identify the Final Publisher

- Does the transactional method return `Mono`/`Flux`/`Publisher`?
- Are all repository calls chained into that publisher?
- Are there any `subscribe()`, `block()`, `toFuture()`, or detached callbacks?
- Was any publisher created and discarded?

### Step 2: Confirm Calls Go Through the Proxy

- Is the bean injected by Spring or instantiated with `new`?
- Is there self-invocation?
- Can the method be intercepted by a proxy?
- Is it called from a constructor or initialization path?
- Is it called through the real bean reference?

### Step 3: Verify the Transaction Manager

- Does the bean implement `ReactiveTransactionManager`?
- Does the annotation select the right manager?
- Does the manager manage the R2DBC `ConnectionFactory`?
- Are `JpaTransactionManager`/`DataSourceTransactionManager` also present?

### Step 4: Verify the `ConnectionFactory`

- Do repositories and `DatabaseClient` use the same factory?
- Does the transaction manager receive that exact factory?
- Are there multiple pools/`ConnectionFactory` beans for the same database?
- Is there a wrong custom configuration/qualifier?

### Step 5: Verify Reactor Context and Error Signals

- Is a new subscription being created?
- Does code rely on `ThreadLocal`?
- Does `onErrorResume`/`onErrorComplete` convert errors into completion?
- Are there checked exceptions needing `rollbackFor`?
- Does the publisher complete empty when rollback was expected?

### Step 6: Inspect Database State

- Are you reading state after the transaction finishes?
- Does the verification query hit the same database/schema?
- Is an outer test transaction wrapping the test?
- Are triggers, autocommit, or other operations touching the same data?
- Is another service updating the row concurrently?

### Step 7: Inspect Logs and Metrics

- Did transaction begin occur?
- Was commit or rollback invoked?
- Which connection was acquired?
- Did repository queries join the same transaction?
- Were there acquire timeouts, cancellations, or cleanup failures?

## 19. Common Symptoms and Causes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Method has `@Transactional`, yet no rollback | Self-invocation or manually created with `new` | Invoke through Spring bean proxy |
| Second save errors, yet first save persists | Two detached publishers/subscriptions or different managers | Chain publishers and share `ConnectionFactory` |
| Method returns before save completes | Internal `subscribe()` or `void` method | Return final `Publisher` |
| Error logged, yet data commits | `onErrorResume`/`onErrorComplete` swallowed error | Let error cross transaction boundary |
| Row not found, yet transaction commits | `Mono.empty` is a clean completion | Emit error if business logic requires rollback |
| JPA rolls back, yet R2DBC commits | Wrong transaction manager or two separate resources | Use right manager; design hybrid consistency |
| Transaction lost only after switching threads | Reading `ThreadLocal` or broken context bridge | Use Reactor Context; inspect chain |
| One repository joins, another does not | Different `ConnectionFactory` | Share factory/manager configuration |
| Rollback test passes, yet production fails to roll back | Outer test transaction or mocks | Run integration tests with real DB and boundaries |
| Transaction stays open until client finishes `Flux` | Transaction wraps entire stream | Re-evaluate streaming/pagination and boundaries |
| Timeout occurs, yet data sometimes persists | Commit happened before timeout/response loss | Use idempotency and state checks |
| Annotation on private helper has no effect | Proxy cannot intercept | Move boundary to public bean method |
| `REQUIRES_NEW` does not create a new boundary | Self-invocation or manager/driver semantics | Invoke via proxy and check manager support |
| Audit/message still emits despite rollback | Side effect subscribed independently | Use transactional outbox |

## 20. Anti-Patterns to Eliminate

- Calling `subscribe()` inside a service just to trigger a query.
- Calling `block()` to extract entities mid-reactive transaction.
- Invoking transactional methods via `this`.
- Creating services with `new` in production code.
- Putting `@Transactional` on `private`/`final` methods expecting proxy interception.
- Using `JpaTransactionManager` for R2DBC repositories.
- Creating multiple `ConnectionFactory` beans and assuming they share transactions because they share a URL.
- Constructing `Publisher` instances without composing them into the final result.
- Using `map` when `flatMap` is needed to chain a `Publisher`.
- Swallowing errors inside a transaction while expecting rollback.
- Treating `Mono.empty()` as an error.
- Making unnecessary HTTP or message broker calls inside long transactions.
- Writing via both JDBC and R2DBC assuming one manager covers both.
- Using `ThreadLocal` to hold reactive transaction/actor context.
- Checking only for the presence of annotations instead of verifying database state after commit/rollback.

## 21. Transaction Boundary Verification Checklist

Before concluding transactions work, verify:

- [ ] Entry method is called through a Spring-managed proxy.
- [ ] No self-invocation bypasses the proxy at required boundaries.
- [ ] Method returns `Mono`, `Flux`, or an appropriate `Publisher`.
- [ ] The right `ReactiveTransactionManager` is selected.
- [ ] Transaction manager and repositories share the same `ConnectionFactory`.
- [ ] All database operations are composed into the returned publisher.
- [ ] No `subscribe()` or `block()` detaches the flow.
- [ ] No `Publisher` is discarded or wrongly nested via `map`.
- [ ] Reactor Context is preserved across operators and integration boundaries.
- [ ] Errors requiring rollback cross the transaction boundary.
- [ ] Rollback rules match the exception types.
- [ ] Empty completion is distinguished from failure.
- [ ] Non-database side effects run post-commit or via an outbox.
- [ ] Long `Flux` streams do not hold transactions open unnecessarily.
- [ ] Integration tests confirm database state after commit/rollback.
- [ ] Tests use the real database/driver and are not masked by an outer transaction.

## 22. Conclusion

Ineffective R2DBC transactions generally stem from one of three boundary issues: proxies fail to intercept due to self-invocation, manual instantiation, or non-proxiable methods; the transaction manager or `ConnectionFactory` is mismatched; or the reactive publisher detached from the subscription and Reactor Context managed by the transaction. Additionally, swallowing errors, returning `Mono.empty()`, or mixing JDBC/JPA with R2DBC can produce outcomes that defy rollback expectations.

Ensure calls pass through Spring proxies, pick the right `ReactiveTransactionManager`, keep repositories on the same `ConnectionFactory`, and compose all database operations into a single publisher. Reactive transactions rely on Reactor Context rather than `ThreadLocal`; avoid calling `subscribe()` or `block()` inside services to drive execution. For rollback, errors must cross the transaction boundary and match rollback rules. When explicit boundaries are preferable, use `TransactionalOperator`.

Finally, prove behavior with integration tests on a real database: run multiple operations, deliberately emit an error, wait for transaction completion, and inspect data from outside the boundary. Observing begin/commit/rollback, connection acquisition, and context separates proxy, configuration, and reactive-flow issues instead of blindly adding annotations or resizing pools.
