# Transactions in Mutations

## Objectives

After this lesson, you will be able to:

- Explain why GraphQL does not automatically define transactions for mutations.
- Distinguish sequential execution of mutation fields from an atomic database transaction.
- Design a transaction boundary for a mutation using `@Transactional`.
- Understand where the transaction ends when a mutation returns an object with nested fields.
- Choose how to combine multiple business steps into a single transaction.
- Configure appropriate rollback rules, propagation, and transaction managers.
- Distinguish imperative transactions from reactive transactions.
- Handle side effects to message brokers or external systems using an outbox.
- Test commit, rollback, and partial GraphQL responses.

## Why Do Mutations Need Transactions?

Mutations typically create, update, or delete data. A single business operation may consist of multiple database statements that must all succeed or all fail together.

For example, placing an order might perform:

1. Create Order.
2. Create OrderItems.
3. Decrease inventory.
4. Record internal payment.
5. Write an audit record.

If steps 1 through 3 write data but step 4 fails, the system can end up in an inconsistent state. Transactions group operations sharing the same transaction manager into a single unit of work with atomicity and isolation.

GraphQL provides mutations to represent data-modifying operations, but GraphQL does not specify where a database transaction must start or end. The server and application decide the transaction boundary based on the use case. Spring for GraphQL integrates with Spring transaction management to implement that decision. [Spring for GraphQL – Data Integration: Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html)

## Mutation Order Does Not Mean Transaction

GraphQL executes fields on the root `Mutation` type sequentially in document order. The next field only starts after the previous field completes. This rule prevents two root mutation fields in the same operation from racing against each other.

According to GraphQL, side effects belong to the root `Mutation` fields. Nested fields in a mutation's selection set are still data-resolution fields and should remain side-effect-free; do not use nested resolvers to silently perform additional writes.

Example:

~~~graphql
mutation {
  reserveDraft: reserveBook(id: "book-101") {
    id
  }
  publishDraft: publishBook(id: "book-101") {
    id
    status
  }
}
~~~

`publishDraft` runs after `reserveDraft`. However, sequential execution is only an execution order; it does not mean the entire operation is wrapped in a single database transaction.

Suppose:

- `reserveDraft` completes and its transaction commits.
- `publishBook` runs afterward and encounters an error.

GraphQL returns an error for the `publishDraft` field, yet there is no mechanism to automatically undo the data committed by `reserveDraft`. Nor does GraphQL automatically roll back previously succeeded side effects. [GraphQL Specification – Mutation Execution](https://spec.graphql.org/September2026/#sec-Mutation)

| Concept | What Is Guaranteed |
| --- | --- |
| Mutation root fields execute sequentially | The next field starts after the previous field |
| Database transaction | Operations within the same transaction commit or roll back together |
| A GraphQL operation | Can contain multiple fields and return partial data alongside errors |

If a use case requires multiple steps to be atomic, model it as a single business mutation and run all write steps within the same transaction.

## Transaction Boundaries at the Mutation Controller Method

Spring for GraphQL recommends the straightforward approach of applying Spring transaction management to methods annotated with `@MutationMapping` or `@SchemaMapping`. The transaction starts when the method is called and ends when the method returns. Any operations using the same transaction manager during that time can participate in the same transaction.

Schema example:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): BookPayload!
}

input CreateBookInput {
  title: String!
  authorId: ID!
  initialStock: Int!
}

type BookPayload {
  book: BookView!
}

type BookView {
  id: ID!
  title: String!
  status: String!
}
~~~

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;
import org.springframework.transaction.annotation.Transactional;

@Controller
public class BookMutationController {

    private final BookService bookService;
    private final InventoryService inventoryService;
    private final AuditService auditService;

    public BookMutationController(
            BookService bookService,
            InventoryService inventoryService,
            AuditService auditService) {
        this.bookService = bookService;
        this.inventoryService = inventoryService;
        this.auditService = auditService;
    }

    @MutationMapping
    @Transactional
    public BookPayload createBook(
            @Argument("input") @Valid CreateBookInput input) {

        Book book = bookService.create(input.title(), input.authorId());
        inventoryService.initializeStock(book.id(), input.initialStock());
        auditService.recordBookCreated(book.id());

        return new BookPayload(BookView.from(book));
    }
}
~~~

In this example, the three write operations execute within the same transaction if they use the same transaction manager and participate under the default `REQUIRED` propagation. If any call throws a runtime exception out of the method, the transaction can roll back all previously executed operations.

`@Transactional` can be placed on the mutation controller method so that the transaction boundary matches a single mutation field. This is the approach recommended by the Spring for GraphQL documentation for typical cases. An application can also place the transaction on a single application service/facade invoked by the mutation; in that case, ensure the entire use case executes within a single call through the Spring proxy and is not inadvertently split into multiple independent transactions.

### The Transaction Ends Before Nested Fields Are Resolved

Suppose a mutation returns an object with nested fields:

~~~graphql
type BookPayload {
  book: Book!
}

type Book {
  id: ID!
  title: String!
  author: Author
}
~~~

Mutation controller:

~~~java
@MutationMapping
@Transactional
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

After the `createBook` method returns, the method's transaction is completed. GraphQL continues resolving the selection set, such as `book.author.name`. The `Book.author` resolver runs afterward and does not automatically belong to `createBook`'s transaction.

If the nested resolver is also annotated with `@Transactional`, it will create or join a transaction according to propagation rules and the active transaction context at the time the resolver is called. Typically this is a separate transaction, not the already-completed transaction of the mutation method. Two separate transactions can observe different state if data changes between reads.

This is especially important when returning a JPA entity with lazy associations. A transaction that has already closed before the nested resolver accesses an association can cause a `LazyInitializationException`. This can be solved by:

- Returning a DTO or projection already materialized within the mutation transaction.
- Eagerly reading the required data inside the service method and returning an object that does not rely on lazy loading.
- Using a dedicated nested resolver to load the data, with appropriate transaction boundaries and consistency.

Do not rely on GraphQL keeping the transaction open until the entire JSON response is serialized.

## Combining Multiple Business Steps in One Transaction

When multiple operations must succeed or fail together, create one mutation representing the entire use case:

~~~graphql
type Mutation {
  placeOrder(input: PlaceOrderInput!): OrderPayload!
}

input PlaceOrderInput {
  customerId: ID!
  items: [OrderItemInput!]!
}

input OrderItemInput {
  productId: ID!
  quantity: Int!
}
~~~

Controller:

~~~java
@MutationMapping
@Transactional
public OrderPayload placeOrder(
        @Argument("input") @Valid PlaceOrderInput input) {

    Order order = orderService.createPendingOrder(input);
    inventoryService.reserve(order.items());
    paymentService.recordInternalAuthorization(order.id());
    auditService.recordOrderPlaced(order.id());

    return OrderPayload.from(order);
}
~~~

The service methods are called within the active transaction. If they also have `@Transactional` with `REQUIRED` propagation, they join the existing transaction instead of creating a new one.

This establishes a clear business boundary:

- The GraphQL client sends a single `placeOrder` mutation.
- The server executes the required steps inside one transaction.
- If a write step fails and the exception triggers a rollback, all changes in that transaction are rolled back.
- GraphQL translates the exception into an error according to the configured exception resolver.

If the client sends multiple separate root mutation fields, each controller method may have its own transaction. When atomicity is required, replace fragmented operations with a single composite mutation.

## Transactions in the Controller or the Service?

Both approaches can work when the method is called through a Spring transaction proxy. Choose one boundary that represents the use case:

| Placement | Best Suited When | Notes |
| --- | --- | --- |
| `@Transactional` on `@MutationMapping` | You want the transaction boundary to match a single mutation field | Spring for GraphQL recommends this as a simple, clear approach |
| `@Transactional` on application service/facade | You want to keep business use cases independent of GraphQL and callable from multiple entry points | The resolver calls a single facade method; sub-steps join the same transaction |
| `TransactionOperations` or `TransactionTemplate` | You need an explicit transaction boundary within a block of code | Uses a callback to clearly define the work inside the transaction |
| Request-wide transactional instrumentation | You need one transaction spanning multiple data fetchers in an operation | Complex configuration with execution strategy and concurrency constraints |

There is no need to place `@Transactional` on every repository call or every nested resolver. Spring Data repositories typically already have transaction semantics for individual operations, but those individual operations do not automatically form a larger business transaction.

### TransactionOperations

Transactions can be managed programmatically:

~~~java
import org.springframework.transaction.support.TransactionOperations;

@Controller
public class AccountController {

    private final TransactionOperations transactionOperations;
    private final AccountRepository accountRepository;
    private final AuditRepository auditRepository;

    public AccountController(
            TransactionOperations transactionOperations,
            AccountRepository accountRepository,
            AuditRepository auditRepository) {
        this.transactionOperations = transactionOperations;
        this.accountRepository = accountRepository;
        this.auditRepository = auditRepository;
    }

    @MutationMapping
    public Account addAccount(@Argument("input") AccountInput input) {
        return transactionOperations.execute(status -> {
            Account account = accountRepository.save(Account.from(input));
            auditRepository.save(AuditRecord.accountCreated(account.id()));
            return account;
        });
    }
}
~~~

`TransactionOperations.execute` starts or joins a transaction per configuration, runs the callback, and commits/rolls back when the callback finishes. This is an imperative API, typically used with `PlatformTransactionManager`.

## Request-Wide Transactional Instrumentation

Spring for GraphQL also describes an advanced approach: opening a transaction before GraphQL invokes the first data fetcher and closing the transaction after request execution completes. Multiple `@SchemaMapping` methods can then participate in the same transaction.

This is not GraphQL's default automatic behavior. The application must implement custom transaction instrumentation or a custom `ExecutionStrategy`, and must ensure data fetcher invocations align with the transaction manager type.

With imperative transactions managed by `PlatformTransactionManager`, the transaction context is typically bound to the thread via `ThreadLocal`. Therefore, for all data fetchers to participate in the same transaction, the execution strategy must invoke them sequentially on the same thread. `AsyncSerialExecutionStrategy` is a starting point to consider for this approach.

Trade-offs:

- Multiple nested fields that could read data independently must wait sequentially.
- Transactions may stay open longer and hold connections/locks for a longer duration.
- One slow field can extend the transaction for the entire operation.
- Commit/rollback and translating transaction failures into GraphQL responses must be handled consistently.
- Do not use this approach merely to avoid designing proper transaction boundaries for mutations.

For most mutations, a transaction per controller method is easier to understand and test. Only consider request-wide transaction instrumentation when consistency requirements truly demand all data fetchers inside a single transaction.

## Commit and Rollback Rules

Spring declarative transactions use an AOP proxy and a transaction manager to wrap method calls. When the method finishes normally, the transaction is committed; when an exception matching the rollback rules escapes the method, the transaction is marked for rollback.

Defaults of `@Transactional`:

| Attribute | Default Value |
| --- | --- |
| Propagation | `REQUIRED` |
| Isolation | `DEFAULT` of the transaction system |
| Read-only | `false` |
| Timeout | Default of the transaction system, or unlimited if unsupported |
| Rollback | `RuntimeException` and `Error` trigger rollback |
| Checked exception | Does not roll back by default |

Example of rolling back on a checked exception:

~~~java
@MutationMapping
@Transactional(rollbackFor = InventoryUnavailableException.class)
public OrderPayload placeOrder(@Argument("input") PlaceOrderInput input)
        throws InventoryUnavailableException {

    Order order = orderService.createPendingOrder(input);
    inventoryService.reserve(order.items()); // May throw a checked exception.
    return OrderPayload.from(order);
}
~~~

`noRollbackFor` can be used if a specific exception should not trigger a rollback, but only choose this when the business logic genuinely intends to commit changes made before that exception.

### Exceptions Must Escape the Transactional Method

Error-prone example:

~~~java
@MutationMapping
@Transactional
public BookPayload createBook(@Argument("input") CreateBookInput input) {
    try {
        Book book = bookService.create(input);
        auditService.recordBookCreated(book.id());
        return BookPayload.success(book);
    }
    catch (AuditException ex) {
        return BookPayload.failure("AUDIT_FAILED");
    }
}
~~~

The method catches the exception and returns normally. The transaction interceptor does not see an exception escaping the method, so the transaction may commit. The GraphQL response might represent a business error in the payload, yet that does not automatically roll back the database.

If an error must roll back:

- Allow the exception to escape the transactional method.
- Or configure rollback rules for the appropriate exception.
- Only use `TransactionStatus.setRollbackOnly()` or the corresponding API when you genuinely need to mark rollback programmatically.

A GraphQL exception resolver or `@GraphQlExceptionHandler` can convert an exception into a GraphQL error after the exception leaves the resolver. Response translation is not a rollback mechanism; the rollback decision belongs to the transaction manager at the boundary.

### Propagation

`REQUIRED` is the default: if a transaction already exists, join it; if none exists, create a new transaction.

`REQUIRES_NEW` suspends the current transaction and creates a new one. The new transaction can commit independently even if the outer transaction rolls back. This is useful for certain audit logs or independent tasks, but can break atomicity if used carelessly.

Example:

~~~java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordIndependentAudit(AuditRecord record) {
    auditRepository.save(record);
}
~~~

If an audit record must always accompany the business change, let it join the `REQUIRED` transaction. Only use `REQUIRES_NEW` when it is acceptable for the audit to commit independently of the mutation.

### Spring AOP Proxies and Self-Invocation

Transaction annotations are applied via a Spring proxy. Calling a method from another bean goes through the proxy and triggers transaction advice. An internal call on the same object such as `this.saveAndAudit()` can bypass the proxy and fail to create a new transaction according to the annotation on the target method.

Place transaction boundaries on methods called from outside the bean, or extract the use case into a separate Spring bean. Do not rely on annotations on private helper methods or self-invocation to open transactions.

In Spring Boot, transaction auto-configuration typically sets up transaction management when a suitable transaction manager is present. Non-Boot Spring applications may need explicit configuration for transaction management and the transaction manager.

## Transaction Managers and Data Types

A transaction only manages resources supported by its corresponding transaction manager:

| Technology | Common Transaction Manager |
| --- | --- |
| JDBC | `DataSourceTransactionManager` or `JdbcTransactionManager` |
| JPA/Hibernate | `JpaTransactionManager` |
| R2DBC | `R2dbcTransactionManager` |
| JTA multiple managed resources | `JtaTransactionManager` |

Spring Boot typically auto-configures the transaction manager based on the starters and data sources on the classpath. If an application has multiple transaction managers, specify which manager to use via the `transactionManager` attribute of `@Transactional`.

A JPA transaction does not automatically include a REST call to a payment service or a Kafka publish. Achieving atomicity across multiple systems requires an appropriate distributed design; a local database transaction cannot automatically roll back side effects that already occurred in a remote system.

## Reactive Transactions in Mutations

With Spring WebFlux and Spring Data R2DBC, mutations can return `Mono` or `Flux`. When using reactive transactions, a `ReactiveTransactionManager` is required. Spring uses the Reactor Context to propagate the transaction instead of `ThreadLocal`.

Example:

~~~java
@MutationMapping
@Transactional
public Mono<BookView> createBook(
        @Argument("input") CreateBookInput input) {

    return bookRepository.save(Book.from(input))
            .flatMap(saved ->
                    inventoryRepository.initialize(saved.id())
                            .thenReturn(BookView.from(saved)));
}
~~~

Reactive operations participating in the same transaction must remain in the same Reactor pipeline/context. Do not call `block()` to force a reactive repository into imperative execution inside a reactive transaction. If both imperative and reactive transaction managers exist, explicitly specify the appropriate manager on the method.

`TransactionalOperator` can be used to wrap a pipeline:

~~~java
public Mono<BookView> createBook(CreateBookInput input) {
    Mono<BookView> work = bookRepository.save(Book.from(input))
            .flatMap(saved ->
                    inventoryRepository.initialize(saved.id())
                            .thenReturn(BookView.from(saved)));

    return work.as(transactionalOperator::transactional);
}
~~~

For long-lived subscriptions returning a `Flux`, do not open a single database transaction spanning the entire event stream. Use short transactions for individual write or read operations that require consistency, then emit events outside the transaction.

## Side Effects to Message Brokers and External Systems

A mutation may write to the database while also sending an email, calling a payment gateway, or publishing a message. A database transaction does not automatically guarantee that both systems commit together.

Unsafe example:

~~~java
@Transactional
public Order placeOrder(PlaceOrderInput input) {
    Order order = orderRepository.save(Order.from(input));
    paymentClient.charge(order); // Calls an external system.
    messageBroker.publish(new OrderPlaced(order.id()));
    return order;
}
~~~

If the database rolls back after the payment or message has succeeded, the external system still retains its side effect. If the remote call is slow, the database transaction also holds connections and locks for longer.

### Transactional Outbox

A common pattern is writing an outbox record in the same transaction as the business data:

~~~java
@Transactional
public Order placeOrder(PlaceOrderInput input) {
    Order order = orderRepository.save(Order.from(input));
    outboxRepository.save(OutboxEvent.orderPlaced(order.id()));
    return order;
}
~~~

A separate publisher reads unsent outbox records and publishes messages after the transaction commits. Upon successful delivery, the publisher marks the record as processed.

Benefits:

- The order and the outbox record commit or roll back together.
- If the process stops after committing, the outbox record remains for the publisher to process again.
- Publishing can be retried without recreating the order.

Publishers usually need an idempotency mechanism because a message may be resent if a failure occurs after the broker receives it but before the outbox record is marked complete. Consumers should recognize already-processed event IDs.

### AFTER_COMMIT Event Listener

For lightweight side effects or when guaranteed delivery is not strictly required, `@TransactionalEventListener` can be used:

~~~java
@Component
public class BookCreatedListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onBookCreated(BookCreated event) {
        notificationService.notifyBookCreated(event.bookId());
    }
}
~~~

The listener runs after the transaction commits. However, the process can still stop after commit and before the listener finishes; in-memory events cannot replace a durable outbox when reliable delivery is required.

## Isolation, Concurrency, and Idempotency

Transactions help group operations and control consistency, but they do not automatically resolve all concurrent conflicts.

For example, two clients updating the same Book concurrently:

1. Both read version 4.
2. Client A updates and commits version 5.
3. Client B attempts to write data based on version 4.

With optimistic locking, a JPA entity can use `@Version`:

~~~java
@Entity
public class BookEntity {

    @Id
    private Long id;

    @Version
    private long version;

    private String title;
}
~~~

If the version has changed, Client B's write can fail with an optimistic locking exception. The API should translate that failure into an appropriate conflict error, such as code `VERSION_CONFLICT`, so the client can reload the data and decide whether to retry the update.

Transactions also do not automatically prevent a client from sending the same mutation multiple times due to retries or timeouts. For payment/order operations, consider an idempotency key with a database unique constraint. When receiving the same key again, the server returns the previously created result instead of executing the side effect again.

Only raise the isolation level when business requirements demand it and you have measured the impact. Higher isolation can increase lock contention, retries, or deadlocks. Have a strategy for handling transaction conflict errors rather than assuming every request will commit.

## Testing Commit and Rollback

To verify transaction boundaries, tests must go through the Spring proxy and the real GraphQL resolver. Calling a method directly on an object created with `new` does not trigger transaction advice.

For integration tests, you can boot the application context and send GraphQL operations through `WebGraphQlTester` or `HttpGraphQlTester`. After the request, read the repository to verify the database state.

Example illustrating a rollback test when the audit service throws a runtime exception:

~~~java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.graphql.test.tester.WebGraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.willThrow;

@SpringBootTest
class BookMutationTransactionTests {

    @Autowired
    WebGraphQlHandler handler;

    @Autowired
    BookRepository bookRepository;

    @MockitoBean
    AuditService auditService;

    WebGraphQlTester tester;

    @BeforeEach
    void setUp() {
        tester = WebGraphQlTester.builder(handler).build();
    }

    @Test
    void rollsBackBookWhenAuditFails() {
        willThrow(new AuditException("Audit unavailable"))
                .given(auditService).recordBookCreated(anyString());

        GraphQlTester.Response response = tester.document("""
                mutation CreateBook($input: CreateBookInput!) {
                    createBook(input: $input) {
                        book {
                            id
                            title
                        }
                    }
                }
                """)
                .variable("input", Map.of(
                        "title", "Transaction sample",
                        "authorId", "author-1",
                        "initialStock", 5))
                .execute();

        response.errors().satisfy(errors ->
                assertThat(errors).isNotEmpty());

        assertThat(bookRepository.existsByTitle("Transaction sample"))
                .isFalse();
    }
}
~~~

The fixtures and repository methods in the example should be replaced with the application's actual models. The key point is that the test sends the operation through the configured handler so the controller call goes through the Spring transaction proxy. `WebGraphQlTester` does not test HTTP filters or networking; it is sufficient for testing transactions at the web GraphQL handler layer.

Do not annotate the test method itself with `@Transactional` if the goal is to verify independent commit/rollback of the mutation. An outer test transaction can cause the service to join the test transaction, obscuring the actual commit timing. If the test method already has a transaction, explicitly control `TestTransaction` and verify the state after the transaction ends.

### Recommended Test Cases

| Case | What to Verify |
| --- | --- |
| Successful mutation | Data is committed and readable after the request |
| Runtime exception in final step | Previous writes in the same transaction are rolled back |
| Checked exception without rollback rule | Transaction may commit by default; test verifies the configuration |
| Checked exception with `rollbackFor` | Data is rolled back |
| Exception caught and error payload returned | Transaction does not automatically roll back just because the payload represents an error |
| Two root mutation fields in one operation | First field can commit even if the second field fails |
| Single composite mutation | All write steps roll back together when one step fails |
| Nested field failure after mutation returns | Already-committed mutation transaction does not roll back automatically |
| Outbox record | Business data and outbox commit/roll back together |
| Reactive mutation | Operations in the pipeline share the reactive transaction context |

## Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Mutation writes partial data | Each repository call commits in its own transaction | Place the transaction boundary around the entire use case |
| Mutation fields run sequentially, but the first field does not roll back | Sequential execution is not an atomic transaction | Combine operations into a single mutation and one transaction |
| `@Transactional` has no effect | Method is not called via a Spring proxy or transaction manager is missing | Check bean/proxy invocation and transaction manager configuration |
| Nested field fails after mutation has written | Nested resolver runs after the mutation transaction finishes | Return materialized DTOs or design a separate transaction for nested reads |
| `LazyInitializationException` reading a nested field | Returning a JPA entity with lazy associations after transaction closes | Use DTOs/projections or fetch data within the proper boundary |
| Exception occurs, yet data still commits | Checked exception lacks rollback rule or exception was caught | Configure `rollbackFor` and let the exception escape the method |
| Audit commits even though mutation rolls back | Audit uses `REQUIRES_NEW` | Use `REQUIRED` if audit must belong to the same atomic unit |
| Remote API succeeds, but database rolls back | Local transaction does not include external systems | Use an outbox, saga, or compensating mechanism |
| Reactive mutation does not roll back as expected | Wrong transaction manager used or work escaped Reactor Context | Use `ReactiveTransactionManager` and keep the same reactive pipeline |
| Long-lived transaction while subscription stays open | Wrapping a long-lived `Flux` inside a transaction | Use short transactions per event/operation |
| Two clients overwrite each other's data | Missing concurrency control | Use optimistic locking, constraints, or appropriate locks |
| Retries create duplicate orders/payments | Missing idempotency key | Store and check idempotency keys with a unique constraint |

## Comprehensive Practice

Build the `placeOrder` mutation for a bookstore API:

1. Declare `Mutation.placeOrder(input)` and input types including customer and item list.
2. Write a controller method with `@MutationMapping` and `@Transactional`.
3. Create the order, order items, reserve inventory, and write the audit record in the same transaction.
4. Verify that sub-services use the same transaction manager and `REQUIRED` propagation.
5. Intentionally make the inventory reservation step throw a runtime exception; verify that the order and order items are no longer in the database.
6. Add a checked exception and configure `rollbackFor`; verify rollback works properly.
7. Send an operation with two root mutation fields and observe that the first field still commits when the second fails.
8. Create a single composite mutation to ensure multiple business steps are atomic.
9. Return a DTO instead of a JPA entity with lazy associations; test nested selections after the mutation.
10. Write an outbox event in the same transaction and verify the publisher processes it after commit.
11. Add an idempotency key and test client retries of the same request.
12. For an R2DBC application, use `ReactiveTransactionManager` and test rollback within the same Reactor pipeline.

After completing this, explain why mutation root fields executing sequentially still lack shared atomicity, why nested resolvers do not belong to the mutation method's transaction, and when an outbox is needed instead of calling remote services directly.

## Key Takeaways

GraphQL does not define database transactions. Mutation root fields execute sequentially, but that order does not create an atomic transaction for the entire operation. Spring for GraphQL recommends placing `@Transactional` on the mutation controller method so the transaction wraps a single field; the transaction ends when the method returns, before nested fields continue resolving. When multiple business steps must commit or roll back together, combine them into a single mutation/use case. Understand rollback rules, propagation, AOP proxies, and transaction manager types. Local transactions do not cover remote side effects; use an outbox when reliable message delivery is required. Test through the real GraphQL handler and verify database state after commit or rollback.

## References

- [Spring for GraphQL – Data Integration: Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html)
- [Spring for GraphQL – Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Framework – Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework – Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework – Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [GraphQL Specification – Mutation Execution](https://spec.graphql.org/September2026/#sec-Mutation)
