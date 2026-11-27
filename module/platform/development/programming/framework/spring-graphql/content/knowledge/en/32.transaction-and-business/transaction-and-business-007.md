# DataLoader After Commit

In Spring for GraphQL, a mutation typically writes data inside a transaction and then returns an object for GraphQL to continue resolving nested fields. Nested fields can use DataLoader to batch-load related data. When the mutation's transaction has committed before the batch loader runs, the loader can read the durably persisted state. However, DataLoader retains its cache throughout the GraphQL request, so a subsequent mutation in the same request may observe stale data if the cache is not refreshed.

## Objectives

After this lesson, you will be able to:

- Explain why a mutation's transaction typically ends before GraphQL resolves child fields.
- Describe when DataLoader collects and dispatches keys during GraphQL execution.
- Register batch loaders using `BatchLoaderRegistry`.
- Use DataLoader inside `@SchemaMapping` to load related data.
- Distinguish the mutation's transaction from the batch loader's transaction.
- Refresh caches with `clear()`, `clearAll()`, and `prime()` after data changes.
- Register cache invalidation to run only after a transaction commits successfully.
- Understand the impact of multiple root mutation fields within a single request.
- Use `@TransactionalEventListener` for side effects that must execute after commit.
- Avoid lazy-loading errors when GraphQL resolves fields after the transaction has closed.
- Test fresh data, stale caches, commit, and rollback with `GraphQlTester`.

## 1. Why Care About DataLoader After Commit?

GraphQL lets clients select fields on demand. A mutation can create or update an object and return it so the client can select additional nested fields.

Example:

~~~graphql
mutation {
  adjustBalance(accountId: "42", delta: 10) {
    id
    availableBalance {
      amount
      currency
    }
  }
}
~~~

The root field `adjustBalance` modifies the account balance. The `availableBalance` field is resolved after GraphQL receives the `Account` object from the mutation. That resolver may use DataLoader to read the balance by account ID.

A typical execution flow:

1. GraphQL invokes the mutation resolver.
2. Spring opens a transaction for the `@Transactional` method.
3. The application updates the data and returns the result object.
4. The transaction interceptor commits the transaction when the method completes.
5. GraphQL continues resolving the client-requested fields on the returned object.
6. The field resolver calls `DataLoader.load(key)`.
7. GraphQL Java dispatches queued keys to the batch loader.
8. The batch loader reads the committed data and completes the futures.

DataLoader is not a transaction manager. It batches read requests and caches results within the request scope. Transaction boundaries are determined by Spring transaction management and how the application designs mutations.

## 2. GraphQL Does Not Automatically Define Transaction Boundaries

The GraphQL specification describes how operations execute and responses are constructed, but it does not mandate that a GraphQL request correspond to a single database transaction.

Applications must decide:

- Whether each mutation root field has its own transaction.
- Whether multiple business operations must share a single transaction.
- Whether nested fields read data in separate transactions or within a larger unit of work.
- When side effects such as sending emails, publishing messages, or evicting caches run.

Spring for GraphQL recommends the straightforward approach of placing the transaction on the mutation controller method or the service method called by the mutation. This creates a clear boundary: the transaction starts when the method is called and ends when the method returns.

Example:

~~~java
@Controller
public class AccountController {

    @MutationMapping
    @Transactional
    public Account adjustBalance(
            @Argument String accountId,
            @Argument BigDecimal delta) {

        // Read and update the account in the same transaction.
        return accountService.adjustBalance(accountId, delta);
    }
}
~~~

The transaction wraps the `adjustBalance` invocation. When the method finishes, Spring commits or rolls back before returning the result to the GraphQL engine.

Nested fields resolved by GraphQL afterward do not automatically belong to the mutation method's transaction.

## 3. Mutation Transactions End Before Nested Field Resolution

Suppose the schema has `Account` and `Balance`:

~~~graphql
scalar Decimal

type Mutation {
  adjustBalance(accountId: ID!, delta: Decimal!): Account!
}

type Account {
  id: ID!
  availableBalance: AccountBalance!
}

type AccountBalance {
  amount: Decimal!
  currency: String!
}
~~~

`Decimal` is a custom scalar in this example, configured by the application to map to `java.math.BigDecimal`. GraphQL only includes standard scalars like `Int`, `Float`, and `String`; if `Decimal` is used, the server must register the corresponding scalar.

The mutation resolver returns `Account`. `availableBalance` is a separate field that can be mapped with `@SchemaMapping` and DataLoader.

~~~java
@Controller
public class AccountController {

    private final AccountService accountService;

    public AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @MutationMapping
    @Transactional
    public Account adjustBalance(
            @Argument String accountId,
            @Argument BigDecimal delta) {

        return accountService.adjustBalance(
                Long.valueOf(accountId), delta);
    }
}
~~~

When `adjustBalance` returns, the transaction interceptor completes the transaction. Only then does GraphQL proceed to resolve `availableBalance` from the selection set.

This brings an important benefit: the batch loader can read the committed state without holding a write transaction open while GraphQL resolves the entire object graph.

It also comes with a limitation: if a child field must read data consistent with all write operations inside the same transaction, a per-mutation-method transaction does not provide that guarantee. In that case, redesign the unit of work—usually by performing all operations requiring atomicity inside one service method and returning a DTO prepared within that transaction.

## 4. Why Should You Avoid Holding a Transaction Open for the Entire GraphQL Request?

GraphQL lets clients request many fields, and fields are resolved independently. Keeping a transaction open from the start of a request until all nested fields finish can:

- Hold connections and database resources longer than necessary.
- Prolong lock durations.
- Increase the risk of deadlocks or contention.
- Tie the transaction to resolvers calling external services or waiting on DataLoader.
- Conflict with asynchronous and multi-threaded execution.

With synchronous JDBC/JPA-based transactions, Spring typically binds the transaction to `ThreadLocal`. If GraphQL executes DataFetchers asynchronously across threads, the transaction does not automatically propagate safely across every field.

Spring for GraphQL can support transactional instrumentation covering the entire request, but that is an advanced strategy. It requires an appropriate execution strategy and sequential DataFetcher execution on the same thread for `ThreadLocal`-based synchronous transactions. That can reduce concurrency and prolong transactions.

In most applications, a transaction per mutation method is easier to control. If a business operation needs to update multiple aggregates atomically, create a single mutation accepting all required inputs and call one `@Transactional` service method executing the full unit of work.

## 5. How Does DataLoader Defer Batch Loads?

DataLoader provides a `load(key)` API to resolvers. This call normally returns a `CompletableFuture` and enqueues the key instead of querying the backend immediately.

Example:

~~~java
@SchemaMapping(typeName = "Account", field = "availableBalance")
public CompletableFuture<AccountBalance> availableBalance(
        Account account,
        DataLoader<Long, AccountBalance> balanceLoader) {

    return balanceLoader.load(account.id());
}
~~~

When GraphQL resolves multiple `Account` objects, each resolver calls `load(account.id())`. Keys can be collected so the batch loader reads once.

For example, the client requests 3 accounts:

~~~graphql
query {
  accounts {
    id
    availableBalance {
      amount
      currency
    }
  }
}
~~~

If there are three accounts with IDs 10, 20, and 30, DataLoader can combine the three loads into one batch with the keys:

~~~text
[10, 20, 30]
~~~

The batch loader returns results matching those keys. DataLoader completes each future and GraphQL uses those values to build the response.

In Spring for GraphQL, GraphQL Java manages dispatching during execution. Do not manually call `dispatch()` in standard controllers or resolvers.

## 6. BatchLoaderRegistry Creates Per-Request DataLoaders

Spring for GraphQL provides `BatchLoaderRegistry` for registering batch-loading functions. Boot Starter auto-configures `BatchLoaderRegistry`, and `DefaultExecutionGraphQlService` uses this registry to create DataLoader registrations per GraphQL request.

Example registering a loader for `AccountBalance`:

~~~java
@Configuration
public class AccountLoaderConfiguration {

    public AccountLoaderConfiguration(
            BatchLoaderRegistry registry,
            AccountBalanceReadService readService) {

        registry.forTypePair(Long.class, AccountBalance.class)
                .registerMappedBatchLoader((accountIds, environment) ->
                        Mono.fromCallable(() ->
                                readService.findBalances(accountIds))
                            .subscribeOn(Schedulers.boundedElastic()));
    }
}
~~~

This example assumes `AccountBalanceReadService` uses Spring Data JPA or a blocking API. Work is offloaded to `boundedElastic` so blocking JDBC does not run on WebFlux's event loop.

Read service:

~~~java
@Service
public class AccountBalanceReadService {

    private final AccountBalanceRepository repository;

    public AccountBalanceReadService(
            AccountBalanceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Map<Long, AccountBalance> findBalances(
            Set<Long> accountIds) {

        return repository.findAllByAccountIdIn(accountIds)
                .stream()
                .collect(Collectors.toMap(
                        AccountBalanceEntity::getAccountId,
                        entity -> new AccountBalance(
                                entity.getAmount(),
                                entity.getCurrency())));
    }
}
~~~

The read transaction in `findBalances` is the batch query's own transaction. It opens when the read service executes and ends when the method returns.

With a reactive repository such as R2DBC, the batch loader can return `Mono<Map<Long, AccountBalance>>` directly without `boundedElastic`. Do not wrap reactive operations in `fromCallable` or shift them onto a scheduler meant for blocking work.

## 7. Using DataLoader in @SchemaMapping

The `availableBalance` field has no corresponding property on the `Account` DTO, so it needs a dedicated resolver:

~~~java
@Controller
public class AccountBalanceController {

    @SchemaMapping(
            typeName = "Account",
            field = "availableBalance")
    public CompletableFuture<AccountBalance> availableBalance(
            Account account,
            DataLoader<Long, AccountBalance> balanceLoader) {

        return balanceLoader.load(account.id());
    }
}
~~~

DataLoader is provided by Spring for GraphQL from the current request's `DataLoaderRegistry`. The default loader name is derived from the target value type—here, `AccountBalance`. The loader name can be customized upon registration if needed.

Per-request DataLoaders help:

- Batch multiple data requests of the same type.
- Avoid reading the same key multiple times within a single request.
- Keep caches and futures isolated across different users.
- Allow batch loaders to access `GraphQLContext` via `BatchLoaderRegistry`.

Do not declare a DataLoader as a singleton bean shared across requests. DataLoader is a stateful object with a queue and a cache; sharing a loader can leak data or mix caches across users.

## 8. DataLoader Dispatch After Commit in a Mutation

Putting the pieces together, an actual execution flow looks like:

~~~mermaid
sequenceDiagram
    participant Client
    participant GraphQL as GraphQL execution
    participant Mutation as Mutation resolver
    participant DB as Database
    participant Field as Nested field resolver
    participant Loader as DataLoader
    participant Batch as Batch loader

    Client->>GraphQL: adjustBalance
    GraphQL->>Mutation: invoke method
    Mutation->>DB: update balance
    DB-->>Mutation: updated Account
    Mutation-->>GraphQL: method returns
    Note over DB,GraphQL: Spring commits transaction
    GraphQL->>Field: resolve availableBalance
    Field->>Loader: load(accountId)
    Loader->>Batch: dispatch queued keys
    Batch->>DB: read committed balance
    DB-->>Batch: AccountBalance
    Batch-->>Loader: complete future
    Loader-->>Field: balance
    Field-->>GraphQL: field value
    GraphQL-->>Client: mutation response
~~~

The commit point occurs after the mutation method returns and before GraphQL proceeds to resolve nested fields under the transaction-per-controller-method strategy.

The batch loader reads the committed data if it queries the database after this step. If the batch loader uses a separate application cache, that cache still needs invalidation according to the application's caching policy.

## 9. DataLoader Cache Persists Throughout the Request

DataLoader maintains a memoization cache keyed by lookup key. Spring for GraphQL registers DataLoaders per request, but a loader's cache persists for the entire lifetime of that request.

This matters when a GraphQL operation contains multiple root mutation fields. GraphQL executes root mutation fields sequentially. Mutation fields in the same request still share the request context and `DataLoaderRegistry`.

Example:

~~~graphql
mutation {
  first: adjustBalance(accountId: "42", delta: 10) {
    id
    availableBalance {
      amount
    }
  }

  second: adjustBalance(accountId: "42", delta: 5) {
    id
    availableBalance {
      amount
    }
  }
}
~~~

Suppose the initial balance is 100:

1. Mutation `first` updates it to 110.
2. Nested field `availableBalance` loads and caches `110` under key `42`.
3. Mutation `second` updates the balance to 115.
4. If DataLoader still holds the cached key `42`, `second`'s nested field may receive `110` again.
5. If the cache is cleared after the second transaction commits, the next load fetches `115`.

This is a classic case where the DataLoader cache must be refreshed after a mutation.

## 10. Clearing the Cache After a Mutation Commits

Java DataLoader provides cache operations:

| Method | Meaning |
|---|---|
| `clear(key)` | Removes the cached entry for one key |
| `clearAll()` | Clears the entire cache of the loader |
| `prime(key, value)` | Inserts a value into the cache if the key is not already present |
| `clear(key).prime(key, value)` | Removes the old value and puts the new value into the cache |

If a mutation updates the balance of account `42`, only key `42` in the `AccountBalance` loader needs clearing. Other accounts retain their cached entries.

Avoid `clearAll()` when you know the exact modified key and the loader may hold many other cached items.

`clear(key)` only removes the cache entry so subsequent loads can invoke the batch loader again. It does not cancel a previously returned future and does not alter an in-flight load's result. If a batch for the same key is pending, design execution ordering carefully so a stale future is not confused with fresh data.

## 11. Registering Invalidation with TransactionSynchronization

If you simply need to clear the cache, you can do it right inside the mutation method. However, if you want the cache invalidated only when the transaction commits successfully, register an `afterCommit` callback.

Example:

~~~java
@Controller
public class AccountController {

    private final AccountService accountService;

    public AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @MutationMapping
    @Transactional
    public Account adjustBalance(
            @Argument String accountId,
            @Argument BigDecimal delta,
            DataLoader<Long, AccountBalance> balanceLoader) {

        Long id = Long.valueOf(accountId);
        Account updated = accountService.adjustBalance(id, delta);

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        balanceLoader.clear(id);
                    }
                });

        return updated;
    }
}
~~~

The `afterCommit` callback runs only after the transaction commits successfully. If the transaction rolls back, the callback does not run and the old cache remains intact.

An error thrown inside `afterCommit` cannot roll back an already-committed transaction. Depending on the transaction manager and exception propagation, the GraphQL request may still receive an error even though the data change persisted. Therefore, keep this callback brief—performing only in-memory operations like `clear(key)`—and avoid external work that might fail or take long.

This snippet assumes:

- The mutation method is invoked through a Spring proxy so `@Transactional` takes effect.
- The transaction manager is synchronous and relies on thread-bound transactions.
- DataLoader comes from the current request and remains valid during GraphQL execution.
- The callback only performs in-memory cache invalidation, not database writes.

`TransactionSynchronizationManager.registerSynchronization` requires active transaction synchronization. Do not use this outside a transaction or inside reactive transactions relying purely on Reactor Context.

If the mutation method might ever run outside a transaction, check whether synchronization is active and provide an appropriate fallback clear. For mutations that strictly require a transaction, ensure configuration and tests verify a transaction is always active.

## 12. Clear Inside the Transaction or After Commit?

Both approaches can be valid depending on requirements:

| Approach | Timing | Advantages | Notes |
|---|---|---|---|
| `clear(key)` right after update | Before commit | Simple, no synchronization callback needed | Cache is cleared even if the transaction rolls back; next read reloads committed data |
| `clear(key)` in `afterCommit` | After successful commit | Invalidates only when write succeeds | Suitable only with matching transaction synchronization type and lifecycle |
| `clear(key).prime(key, value)` | After obtaining a trustworthy new value | Avoids a follow-up batch read | Prime only when the value is complete and already committed |

Clearing before commit is usually safe because it only removes an entry from the per-request cache; on rollback, the next read fetches the old value from the database. However, never prime the cache with uncommitted values, because if the transaction rolls back, DataLoader would hold a value that does not exist in the database.

If you want to keep the cache on rollback and clear only upon commit, use `afterCommit` as shown above.

## 13. When Should You Prime the Cache?

Priming fits when the mutation already holds the exact complete value that subsequent resolvers need.

Example of a mutation creating a new `AccountBalance`:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                balanceLoader.clear(accountId)
                        .prime(accountId, savedBalance);
            }
        });
~~~

`prime()` does not overwrite an existing cache entry. Therefore, clear first if the key may have been loaded earlier in the same request.

Only prime when `savedBalance` is a complete projection reflecting the committed state. If the database updates columns, triggers, versions, or computed values after saving, clear instead and let the batch loader re-read rather than priming a potentially incomplete object.

Do not use `prime` to mask consistency issues. If the mutation has side effects outside the database or another system has not completed yet, the primed value must accurately reflect the state the API guarantees to the client.

## 14. Cache Invalidation When Multiple Loaders Depend on the Same Data

One business change can affect multiple DataLoaders.

For example, changing a customer address can affect:

- Customer loader keyed by customer ID.
- Address loader keyed by address ID.
- OrderSummary loader containing the shipping address.
- Search result loader containing denormalized data.

If the mutation only clears the Customer loader while other loaders still retain stale related caches, subsequent responses in the same request can become inconsistent.

Map out the data dependency graph:

| Changed Data | Loaders to Consider |
|---|---|
| Account balance | `AccountBalance` loader, `AccountSummary` loader |
| Customer profile | `Customer` loader, `CustomerProfile` loader |
| Order status | `Order` loader, `OrderSummary` loader |
| Product price | `Product` loader, `CartTotal` loader |
| Address | `Address` loader, `CustomerAddress` loader, `ShippingQuote` loader |

You do not need to clear every loader. Clear only the affected keys or caches. For loaders with complex keys, `clearAll()` can be used while considering the extra batch reads incurred.

## 15. DataLoader Cache Is Not a Shared Application Cache

DataLoader's cache mainly optimizes duplicate key loads within a single GraphQL request. It does not replace Redis, Caffeine, or a cache shared across multiple requests.

Distinguish them:

| Cache Type | Scope | When to Invalidate |
|---|---|---|
| DataLoader memoization cache | One GraphQL request | Clear when a mutation in the request stales data |
| Local application cache | One application instance | Evict after commit or via TTL |
| Distributed cache | Multiple instances | Publish invalidation or update by version |
| Database cache/buffer | Database layer | Managed by database mechanisms |

Clearing DataLoader does not automatically clear Redis or caches on other instances. Conversely, evicting Redis does not clear a DataLoader that already cached a value within an in-flight request.

For data requiring strong consistency, coordinate cache invalidation across every relevant layer.

## 16. @TransactionalEventListener for Post-Commit Side Effects

Some tasks must run only after a transaction succeeds:

- Sending notifications.
- Publishing events to a message broker.
- Evicting shared caches.
- Updating search indexes.
- Triggering other workflows.

You can publish a Spring application event inside the transaction and listen with `@TransactionalEventListener`:

~~~java
public record AccountBalanceChangedEvent(
        Long accountId,
        BigDecimal newBalance) {
}
~~~

Mutation service:

~~~java
@Service
public class AccountService {

    private final AccountRepository repository;
    private final ApplicationEventPublisher eventPublisher;

    public AccountService(
            AccountRepository repository,
            ApplicationEventPublisher eventPublisher) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Account adjustBalance(
            Long accountId,
            BigDecimal delta) {

        AccountEntity entity = repository.findById(accountId)
                .orElseThrow(AccountNotFoundException::new);

        entity.setBalance(entity.getBalance().add(delta));

        eventPublisher.publishEvent(
                new AccountBalanceChangedEvent(
                        accountId, entity.getBalance()));

        return new Account(entity.getId(), entity.getName());
    }
}
~~~

Listener:

~~~java
@Component
public class AccountBalanceChangedListener {

    private final AccountCache accountCache;

    public AccountBalanceChangedListener(
            AccountCache accountCache) {
        this.accountCache = accountCache;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onBalanceChanged(
            AccountBalanceChangedEvent event) {

        accountCache.evict(event.accountId());
    }
}
~~~

If the transaction rolls back, the `AFTER_COMMIT` listener does not run. If no transaction is active, a transactional event listener is not invoked by default unless `fallbackExecution` is enabled.

Do not confuse an `AFTER_COMMIT` listener with DataLoader dispatch. DataLoader is dispatched by GraphQL execution when resolvers call `load()`; transactional event listeners follow the transaction lifecycle.

## 17. Be Careful When Writing to the Database in an AFTER_COMMIT Listener

When an `AFTER_COMMIT` listener runs, the original transaction has already committed. Transactional resources may still be bound and accessible during completion, yet any database modifications made at this stage are not committed into the old transaction.

If the listener needs to write to the database, create a new transaction using `REQUIRES_NEW` propagation or call a service method that starts its own transaction.

Example:

~~~java
@Component
public class AccountAuditListener {

    private final AccountAuditService auditService;

    public AccountAuditListener(AccountAuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onBalanceChanged(
            AccountBalanceChangedEvent event) {

        auditService.record(event);
    }
}
~~~

Service:

~~~java
@Service
public class AccountAuditService {

    private final AccountAuditRepository repository;

    public AccountAuditService(AccountAuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(AccountBalanceChangedEvent event) {
        repository.save(new AccountAudit(
                event.accountId(),
                event.newBalance()));
    }
}
~~~

The listener calls through another service bean so the Spring transaction proxy applies `REQUIRES_NEW`. Avoid self-invocation inside the same bean because internal calls can bypass the proxy.

## 18. Consider Transactional Outbox When Reliable Message Publishing Is Required

`@TransactionalEventListener` ensures the listener runs only after commit within the current process. It does not guarantee a message will be sent successfully if the application crashes right after the database commits and before publishing to the broker.

When you must ensure events are never lost, use a Transactional Outbox:

1. In the same transaction as the business change, write an outbox record.
2. Commit business data and the outbox record together.
3. A separate publisher reads the outbox and sends messages.
4. Mark messages as published or rely on a retry mechanism.
5. Consumers process idempotently to tolerate duplicate messages.

Example:

~~~java
@Transactional
public Account adjustBalance(
        Long accountId,
        BigDecimal delta) {

    AccountEntity account = accountRepository.findById(accountId)
            .orElseThrow(AccountNotFoundException::new);

    account.setBalance(account.getBalance().add(delta));

    outboxRepository.save(
            OutboxEvent.accountBalanceChanged(
                    accountId, account.getBalance()));

    return new Account(account.getId(), account.getName());
}
~~~

DataLoader does not need to participate in the outbox. DataLoader solves batching and per-request caching; the outbox solves reliable event emission after transaction commit.

## 19. Lazy Loading and Detached Entities After Commit

A common issue with JPA is a mutation returning an entity with lazy relationships. Once the transaction finishes, GraphQL continues resolving nested fields. If the default property fetcher accesses a lazy association, the application can throw `LazyInitializationException`.

Example:

~~~java
@Entity
public class AccountEntity {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;
}
~~~

If the mutation returns `AccountEntity` and the GraphQL `customer` field resolves by calling `getCustomer()` after commit, the persistence context may already be closed.

How to handle this:

- Return a DTO or record containing the IDs needed by nested resolvers.
- Use DataLoader to load `customer` by customer ID after commit.
- Use projections or tailored queries inside the transaction.
- Do not keep transactions open solely to avoid lazy loading.
- Do not serialize uncontrolled entity graphs directly.

DTO example:

~~~java
public record Account(
        Long id,
        String name,
        Long customerId) {
}
~~~

Nested resolver:

~~~java
@SchemaMapping(typeName = "Account", field = "customer")
public CompletableFuture<Customer> customer(
        Account account,
        DataLoader<Long, Customer> customerLoader) {

    return customerLoader.load(account.customerId());
}
~~~

The DTO carries enough information for DataLoader to read the required data after the mutation transaction has ended.

## 20. Multiple Mutations in the Same Request and Atomicity

GraphQL permits a `Mutation` operation to have multiple root fields. Root mutation fields execute sequentially, but that does not mean all of them automatically run within one transaction.

If each controller method has `@Transactional`, each root mutation method can have its own transaction:

~~~graphql
mutation {
  first: reserveInventory(input: { productId: "p-1", quantity: 1 }) {
    id
  }

  second: chargePayment(input: { orderId: "o-1" }) {
    id
  }
}
~~~

If `reserveInventory` commits successfully and `chargePayment` fails, the first transaction does not automatically roll back just because the second mutation failed.

When two steps require atomicity, design a single mutation command:

~~~graphql
type Mutation {
  placeOrder(input: PlaceOrderInput!): Order!
}
~~~

The resolver calls a single `@Transactional` service method:

~~~java
@Service
public class OrderApplicationService {

    @Transactional
    public Order placeOrder(PlaceOrderInput input) {
        InventoryReservation reservation =
                inventoryService.reserve(input);

        Payment payment =
                paymentService.authorize(input);

        return orderService.create(input, reservation, payment);
    }
}
~~~

Called services join the existing transaction under default `REQUIRED` propagation if they share the same transaction manager and thread-bound transaction.

If a workflow spans multiple systems like databases, payment providers, and message brokers, a single database transaction does not create distributed atomicity. Design sagas, compensating actions, or an outbox as required by the business logic.

## 21. Reactive Transactions and DataLoader

With Spring WebFlux and R2DBC, transactions can be managed by `ReactiveTransactionManager`. The transaction context lives in the Reactor Context rather than a traditional `ThreadLocal`.

Reactive service example:

~~~java
@Service
public class ReactiveAccountService {

    private final ReactiveAccountRepository repository;

    public ReactiveAccountService(
            ReactiveAccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Account> adjustBalance(
            Long accountId,
            BigDecimal delta) {

        return repository.findById(accountId)
                .switchIfEmpty(Mono.error(
                        new AccountNotFoundException(accountId)))
                .flatMap(account -> {
                    account.setBalance(
                            account.getBalance().add(delta));
                    return repository.save(account);
                })
                .map(account -> new Account(
                        account.getId(), account.getName()));
    }
}
~~~

With reactive `@Transactional`, the transaction is maintained across the publisher's lifecycle and completes when the publisher terminates. The GraphQL adapter waits for the mutation's publisher to complete before continuing to process child fields.

If invalidation is needed after a reactive commit, use reactive transaction synchronization or sequence the clear step after the publisher completes under `TransactionalOperator`. The example below illustrates the boundary with `TransactionalOperator`:

~~~java
public Mono<Account> adjustBalance(
        Long accountId,
        BigDecimal delta,
        DataLoader<Long, AccountBalance> balanceLoader) {

    return transactionalOperator.transactional(
                    accountService.adjustBalanceInTransaction(
                            accountId, delta))
            .flatMap(updated ->
                    Mono.fromRunnable(() -> balanceLoader.clear(accountId))
                            .thenReturn(updated));
}
~~~

In this example, `adjustBalanceInTransaction` does not open another transaction itself; `TransactionalOperator` owns the transaction for the publisher. The downstream publisher only runs after the transaction operator succeeds. If the transaction errors or rolls back, the clear step does not run.

A reactive batch loader can return `Mono<Map<K,V>>`. It runs in its own transaction if the read service is annotated with `@Transactional` and uses a reactive transaction manager.

Do not use thread-bound `TransactionSynchronizationManager` to manage reactive transactions. For transactional events in Spring Framework 6.1 and later, the reactive transaction context must be propagated via `TransactionalEventPublisher` as guided by Spring.

Do not mix blocking JDBC/JPA transactions with reactive R2DBC transactions and expect them to participate in the same unit of work. Choose one transaction model per execution flow or design explicit boundaries between them.

## 22. DataLoader Context and Per-Request Security

Batch loaders sometimes need information about the current user, tenant, or permissions to filter data.

Spring for GraphQL recommends registering loaders via `BatchLoaderRegistry` because the registry supports sharing `GraphQLContext` and context propagation to batch-loading functions.

Example:

~~~java
registry.forTypePair(Long.class, Customer.class)
        .registerMappedBatchLoader((customerIds, environment) -> {
            String tenantId =
                    environment.getGraphQlContext().get("tenantId");

            return customerService.findVisibleCustomers(
                    tenantId, customerIds);
        });
~~~

The batch loader must ensure each key is only accessed within a valid tenant or principal scope. Do not rely on DataLoader caching by key ID as sufficient for security.

If the loader key is only a customer ID while results also depend on tenant, the loader must be created per request and the query service must apply tenant filtering. Never share a DataLoader across requests belonging to different principals.

## 23. Testing That DataLoader Reads Post-Commit Data

An integration test can verify that nested fields observe committed values.

Example mutation with two root fields updating the same account:

~~~graphql
mutation {
  first: adjustBalance(accountId: "42", delta: 10) {
    id
    availableBalance {
      amount
    }
  }

  second: adjustBalance(accountId: "42", delta: 5) {
    id
    availableBalance {
      amount
    }
  }
}
~~~

Suppose the initial balance is 100. Expected results:

| Field | Expected Value |
|---|---:|
| `first.availableBalance.amount` | 110 |
| `second.availableBalance.amount` | 115 |

Test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class AccountMutationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Autowired
    AccountRepository accountRepository;

    @Test
    void shouldReloadBalanceAfterEachMutationCommit() {
        accountRepository.save(
                new AccountEntity(42L, "Main", new BigDecimal("100")));

        graphQlTester.document("""
                mutation {
                  first: adjustBalance(
                    accountId: "42",
                    delta: 10
                  ) {
                    id
                    availableBalance {
                      amount
                    }
                  }
                  second: adjustBalance(
                    accountId: "42",
                    delta: 5
                  ) {
                    id
                    availableBalance {
                      amount
                    }
                  }
                }
                """)
                .execute()
                .path("first.availableBalance.amount")
                .entity(BigDecimal.class)
                .isEqualTo(new BigDecimal("110"))
                .path("second.availableBalance.amount")
                .entity(BigDecimal.class)
                .isEqualTo(new BigDecimal("115"));
    }
}
~~~

The test assumes:

- The test database initially has account ID 42 with balance 100.
- Each mutation commits in its own transaction.
- The `afterCommit` callback clears key 42 in the DataLoader.
- The batch loader reads the balance from the database after commit.
- The test method does not run inside an enclosing transaction that alters the lifecycle under test.

If cache clearing were omitted, the second mutation could read the cached value from the first mutation. This test catches that bug.

## 24. Testing That Rollback Does Not Prime Uncommitted Data

Another test should verify that a rolled-back mutation does not put uncommitted data into the DataLoader cache.

Example service updating data and then throwing an exception:

~~~java
@Transactional
public Account adjustBalanceAndFail(
        Long accountId,
        BigDecimal delta) {

    AccountEntity account = repository.findById(accountId)
            .orElseThrow();

    account.setBalance(account.getBalance().add(delta));
    repository.save(account);
    repository.flush();

    throw new IllegalStateException("Simulated failure");
}
~~~

The `flush` example assumes the repository is a `JpaRepository` or exposes an equivalent method. Flushing forces SQL to execute inside the transaction before the exception is thrown, allowing the test to verify rollback of changes already sent to the database.

If the mutation fails:

- The transaction must roll back.
- The `afterCommit` callback must not run.
- No uncommitted value is primed into DataLoader.
- The database retains the original balance.
- The GraphQL response contains an error on the mutation field.

Test:

~~~java
@Test
void shouldRollbackAndKeepCommittedBalance() {
    graphQlTester.document("""
            mutation {
              adjustBalanceAndFail(
                accountId: "42",
                delta: 50
              ) {
                id
              }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors ->
                    assertThat(errors).isNotEmpty());

    AccountEntity account = accountRepository.findById(42L)
            .orElseThrow();

    assertThat(account.getBalance())
            .isEqualByComparingTo("100");
}
~~~

Do not run the test inside an outer transaction if the goal is verifying commit/rollback of the request. An enclosing test transaction can alter how the inner transaction joins or rolls back.

## 25. Testing Cache Invalidation Independently

You can test the DataLoader cache directly in a unit test:

~~~java
@Test
void shouldClearAndPrimeChangedValue() {
    DataLoader<Long, AccountBalance> loader =
            createAccountBalanceLoader();

    loader.prime(42L, new AccountBalance(
            new BigDecimal("100"), "VND"));

    loader.clear(42L).prime(
            42L,
            new AccountBalance(
                    new BigDecimal("115"), "VND"));

    AccountBalance value = loader.load(42L).join();

    assertThat(value.amount())
            .isEqualByComparingTo("115");
}
~~~

This example demonstrates the DataLoader cache API. In GraphQL integration tests, do not create a new loader manually when testing the real request's cache; invoke multiple mutation fields in a single GraphQL operation and verify the results.

Also verify:

- Loading the same key twice in one request invokes the batch loader according to the expected cache behavior.
- `clear(key)` causes the next load to re-fetch data.
- `clearAll()` refreshes all keys.
- `prime()` does not overwrite an already-cached entry.
- `clear(key).prime(key, value)` replaces the stale cache entry.
- Subsequent requests create fresh DataLoaders and do not reuse a previous request's cache.

## 26. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Nested field reads stale data | DataLoader cache still holds key from an earlier load | Clear key after commit |
| Mutation commits, yet DataLoader misses new data | Batch loader uses an application cache or replica lag exists | Invalidate cache, review consistency and read routing |
| `LazyInitializationException` | GraphQL resolves a lazy relation after transaction closes | Return DTOs/IDs and use DataLoader |
| Cache cleared even though transaction rolled back | Clear was called before commit | Use `afterCommit` when invalidation should happen only on commit |
| Cache holds a non-existent value | Primed with an uncommitted entity | Prime only after commit and when the value is complete |
| Second mutation receives stale data | DataLoader cache is shared across the request | Invalidate between mutation root fields |
| Long-running transaction | Transaction spans the entire GraphQL request | Prefer transaction per mutation method |
| Batch loader lacks a transaction | Loader runs outside the mutation transaction | Place a dedicated read transaction on the batch service if needed |
| Blocking JPA on the event loop | Batch loader calls a blocking repository directly in WebFlux | Offload blocking work to `boundedElastic` or use R2DBC |
| DataLoader shared across users | Loader stored as singleton or global cache | Use per-request `BatchLoaderRegistry` |
| `AFTER_COMMIT` listener does not run | Event published outside a transaction or transaction rolled back | Check transaction presence and `fallbackExecution` |
| DB writes inside `AFTER_COMMIT` are not saved | Changes hit an already-committed resource without a new transaction | Use `REQUIRES_NEW` |
| Messages lost when the app crashes | In-process listener is not durable messaging | Use Transactional Outbox |

## 27. Checklist for DataLoader After Commit

Before deploying mutations and DataLoader to production:

- [ ] Clearly define the mutation's transaction boundary.
- [ ] Use transaction per controller/service method for standard mutations.
- [ ] Do not assume nested fields automatically join the mutation's transaction.
- [ ] Register DataLoaders via `BatchLoaderRegistry`.
- [ ] Let GraphQL Java manage dispatch; do not call `dispatch()` manually.
- [ ] Keep DataLoader scoped to each GraphQL request.
- [ ] Use DTOs or IDs so nested resolvers do not rely on lazy entities after commit.
- [ ] Identify which loader keys are affected by each mutation.
- [ ] Clear affected keys after commit when data changes.
- [ ] Prime only complete and already-committed values.
- [ ] Account for multiple root mutation fields within the same request.
- [ ] Separate the batch loader's read transaction from the mutation's write transaction when needed.
- [ ] Never run blocking JDBC/JPA on the event loop.
- [ ] Ensure batch loaders enforce tenant and authorization filters.
- [ ] Use `@TransactionalEventListener` for post-commit side effects.
- [ ] Use `REQUIRES_NEW` if an `AFTER_COMMIT` listener must write to the database.
- [ ] Use an outbox when reliable message publishing is required.
- [ ] Maintain integration tests for commit, rollback, and stale caches.

## Conclusion

DataLoader and transactions solve two different problems. Transactions guarantee atomicity and consistency of write operations; DataLoader batches reads and caches results within the scope of a GraphQL request.

With a transaction per mutation method, Spring completes the commit when the mutation method returns. GraphQL then continues resolving nested fields and dispatching DataLoader batches. This allows the batch loader to read committed state without keeping a write transaction open across the entire object graph resolution.

However, DataLoader's cache persists within the same request. When multiple root mutation fields modify the same key, clear the cache after commit so subsequent nested fields load fresh data. Only prime the cache with complete, committed values. For side effects that must run after commit, use `@TransactionalEventListener`; for messages that must not be lost, consider a Transactional Outbox.

## References

- [Spring for GraphQL — Data Integration and Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [GraphQL Java — java-dataloader](https://github.com/graphql-java/java-dataloader)
