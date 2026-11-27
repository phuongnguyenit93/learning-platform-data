# Migrating Service Contracts from Direct Values to Publisher

When migrating a Spring Data Relational R2DBC application from synchronous data access to reactive, the key change does not stop at repositories. Service contracts and all callers must also express that results will be delivered asynchronously through a publisher.

A synchronous service may return an entity, a list, a boolean, or nothing directly. With R2DBC, repositories typically return **Mono<T>** or **Flux<T>**. Services must keep that publisher in the processing chain, compose steps with reactive operators, and let the framework at the appropriate boundary subscribe.

For example, the old contract:

~~~java
Customer findById(Long id);
~~~

can become:

~~~java
Mono<Customer> findById(Long id);
~~~

This change impacts controllers, other services, tests, transactions, exception handling, and how empty results are represented. You cannot simply change the return type and keep synchronous calling patterns.

This lesson explains the meaning of `Publisher` in service contracts, how to choose between `Mono` and `Flux`, converting each return type, rewriting callers using reactive composition, handling errors and empty results, preserving transactions/context, HTTP integration, maintaining compatibility with legacy code, and testing the migration.

## 1. How Synchronous and Reactive Contracts Differ

In the synchronous model, a method typically returns a result as soon as the method finishes:

~~~java
public Customer getCustomer(Long id) {
    return customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
~~~

The caller receives a `Customer` or an exception directly on the calling thread. If the repository must access the database, the calling thread typically waits for I/O to complete.

In the reactive model, the method returns a publisher describing the result that will be emitted upon subscription:

~~~java
public Mono<Customer> getCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

Calling the service returns `Mono<Customer>`. The result may be emitted later, complete empty, or emit an error. Execution is usually triggered when the publisher is subscribed to.

| Synchronous Contract | Common Reactive Contract |
|---|---|
| Customer | Mono<Customer> |
| Optional<Customer> | Mono<Customer> |
| List<Customer> | Flux<Customer> or Mono<List<Customer>> |
| boolean | Mono<Boolean> |
| long / Long | Mono<Long> |
| void | Mono<Void> |
| T that may not exist | Mono<T> |
| Multiple streaming results | Flux<T> |

The core differences:

- A direct value is an already-computed result.
- A publisher is a description of a computation that may emit data, complete, or emit an error in the future.
- Callers cannot read the value inside a publisher as they would a plain object.
- Callers must chain subsequent steps onto the publisher or subscribe at an appropriate application boundary.

A publisher is not simply a value wrapped in a box. It is part of the execution contract.

## 2. Publisher, Mono, and Flux

Reactive Streams defines the `Publisher<T>` interface. A publisher emits 0 to many elements, may complete or terminate with an error, and follows the subscription and backpressure protocol.

Reactor provides two common types:

- **Mono<T>:** emits at most one element and completes, completes empty, or emits an error.
- **Flux<T>:** emits 0 to many elements, then completes or emits an error.

~~~text
Publisher<T>
    |
    +-- Mono<T>  : 0 or 1 element
    |
    +-- Flux<T>  : 0 to N elements
~~~

Example:

~~~java
Mono<Customer> oneCustomer =
        customerRepository.findById(42L);

Flux<Customer> manyCustomers =
        customerRepository.findAll();
~~~

### 2.1. Choosing Mono or Flux by Semantics

Choose the return type based on the cardinality of the use case, not merely the old data type.

| Use Case | Suggested Return Type |
|---|---|
| Find a customer by ID | Mono<Customer> |
| Find a customer by email, at most one row | Mono<Customer> |
| List customers | Flux<Customer> |
| Check whether a customer exists | Mono<Boolean> |
| Count customers | Mono<Long> |
| Save a customer | Mono<Customer> |
| Delete a customer | Mono<Void> |
| Build a report requiring all rows aggregated | Mono<Report> or Mono<List<T>> |
| Emit events over time | Flux<Event> |

If business logic needs a complete list for computation, `Mono<List<T>>` can be suitable. If the caller can process items one by one, `Flux<T>` usually preserves streaming and backpressure benefits.

Do not turn every `List<T>` into `Mono<List<T>>` out of habit. Nor should you turn every list into `Flux` if the use case must know the entire set before proceeding.

### 2.2. Publishers Can Complete Empty

`Mono<T>` does not guarantee there will always be a `T`. It can:

1. Emit one element and complete.
2. Complete without emitting any element.
3. Emit an error.

`Flux<T>` can emit zero elements or many elements.

Therefore, `Mono<T>` is not identical to a nullable `T`. Absence of a result is represented by `Mono.empty()`, not `null`.

## 3. Migrating Service Contracts by Result Type

### 3.1. From Direct Entity to Mono<Entity>

Before:

~~~java
public Customer findCustomer(Long id) {
    return customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
~~~

After:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

`switchIfEmpty` emits the error only when the repository completes empty. It does not swallow database errors; errors from the repository still propagate downstream to the subscriber.

### 3.2. From Optional<T> to Mono<T>

Before:

~~~java
public Optional<Customer> findByEmail(String email) {
    return customerRepository.findByEmail(email);
}
~~~

After:

~~~java
public Mono<Customer> findByEmail(String email) {
    return customerRepository.findByEmail(email);
}
~~~

If you have an `Optional` in memory and want to turn it into a publisher:

~~~java
Optional<Customer> result = findInCache(email);

return Mono.justOrEmpty(result);
~~~

Never use `Mono.just(optional.orElse(null))`, because `Mono.just(null)` is invalid.

### 3.3. From List<T> to Flux<T>

Before:

~~~java
public List<Customer> findActiveCustomers() {
    return customerRepository.findAllActive();
}
~~~

After:

~~~java
public Flux<Customer> findActiveCustomers() {
    return customerRepository.findAllActive();
}
~~~

If the data is already in memory:

~~~java
List<Customer> customers = loadInMemory();

return Flux.fromIterable(customers);
~~~

This only wraps an existing collection as a `Flux`; it does not make the preceding synchronous collection creation non-blocking.

### 3.4. From List<T> to Mono<List<T>>

If the caller genuinely needs the entire list:

~~~java
public Mono<List<Customer>> findActiveCustomers() {
    return customerRepository.findAllActive()
            .collectList();
}
~~~

`collectList()` waits for the `Flux` to complete and emits a single `List`. This consumes memory proportional to the row count. Do not use it for potentially very large results if the caller can handle items incrementally.

### 3.5. From boolean to Mono<Boolean>

Before:

~~~java
public boolean emailExists(String email) {
    return customerRepository.existsByEmail(email);
}
~~~

After:

~~~java
public Mono<Boolean> emailExists(String email) {
    return customerRepository.existsByEmail(email);
}
~~~

The caller must use `flatMap`, `filter`, `map`, or another operator to act on the boolean value once emitted:

~~~java
return customerService.emailExists(command.email())
        .flatMap(exists -> {
            if (exists) {
                return Mono.error(
                        new EmailAlreadyRegisteredException(
                                command.email()));
            }

            return customerService.create(command);
        });
~~~

Do not write `if (customerService.emailExists(email))`, because that expression has type `Mono<Boolean>`, not `boolean`.

### 3.6. From void to Mono<Void>

Before:

~~~java
public void deleteCustomer(Long id) {
    customerRepository.deleteById(id);
}
~~~

After:

~~~java
public Mono<Void> deleteCustomer(Long id) {
    return customerRepository.deleteById(id);
}
~~~

`Mono<Void>` represents an operation where only completion or error matters. It typically emits no data item.

If you want to verify the row exists before deleting:

~~~java
public Mono<Void> deleteCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)))
            .flatMap(customer ->
                    customerRepository.delete(customer));
}
~~~

### 3.7. From Count or Aggregate to Mono

Before:

~~~java
public long countActiveCustomers() {
    return customerRepository.countActive();
}
~~~

After:

~~~java
public Mono<Long> countActiveCustomers() {
    return customerRepository.countActive();
}
~~~

Database aggregations are typically represented with `Mono` because they emit a single scalar result.

## 4. Changing Service Interfaces and Callers

Suppose the old contract is:

~~~java
public interface CustomerService {
    Customer getById(Long id);
    List<Customer> findAll();
    Customer create(CreateCustomerCommand command);
    void delete(Long id);
}
~~~

The reactive contract:

~~~java
public interface CustomerService {
    Mono<Customer> getById(Long id);
    Flux<Customer> findAll();
    Mono<Customer> create(CreateCustomerCommand command);
    Mono<Void> delete(Long id);
}
~~~

Changing return types is a contract change. All callers must be updated accordingly.

An old caller:

~~~java
Customer customer = customerService.getById(id);
return customer.getEmail();
~~~

Reactive caller:

~~~java
return customerService.getById(id)
        .map(Customer::getEmail);
~~~

The caller does not read the property immediately. It declares the transformation to apply when `customer` is emitted.

### 4.1. Changing Return Types Is an API Change

In Java, return types do not participate in method overloading. You cannot declare two methods with the same name and parameter list differing only in return type:

~~~java
// Invalid within the same class/interface.
Customer getById(Long id);
Mono<Customer> getById(Long id);
~~~

If a transition period is needed, use different method names or interfaces:

~~~java
public interface LegacyCustomerService {
    Customer getById(Long id);
}

public interface ReactiveCustomerService {
    Mono<Customer> getById(Long id);
}
~~~

Or use a temporary distinct method name such as `getByIdReactive`, though maintaining two contracts long-term should be avoided unless necessary.

Changing public interfaces can also break source and binary compatibility for dependent modules. Check implementations, mocks, tests, controllers, event listeners, and external module consumers.

### 4.2. Bottom-Up Migration

A usually manageable order:

1. Migrate repositories to the R2DBC reactive API.
2. Migrate services that directly call repositories to `Mono`/`Flux`.
3. Migrate services that call those services.
4. Migrate controllers or message handlers.
5. Migrate tests and fixtures.
6. Remove old blocking bridges once no callers remain.

Migrating top-down before lower layers have reactive contracts easily produces unnecessary blocking calls or wrappers.

## 5. map and flatMap When Callers Use Reactive Services

This is the most important change in code that invokes services.

### 5.1. Use map for Synchronous Transformations

`map` takes a value `T` and returns `R`:

~~~java
return customerService.getById(id)
        .map(Customer::getEmail);
~~~

The result is `Mono<String>`.

Use `map` for pure, fast transformations that do not return another publisher.

### 5.2. Use flatMap When the Next Step Is Also Reactive

If the next step calls a service/repository returning a publisher, use `flatMap`:

~~~java
return customerService.getById(id)
        .flatMap(customer ->
                orderService.findLatestOrder(customer.getId()));
~~~

The result is `Mono<Order>`, not `Mono<Mono<Order>>`.

Wrong:

~~~java
return customerService.getById(id)
        .map(customer ->
                orderService.findLatestOrder(customer.getId()));
~~~

The wrong expression produces `Mono<Mono<Order>>`: the inner publisher is not subscribed to or flattened into the outer stream.

Rule of thumb:

- `map`: `T` to `R`.
- `flatMap`: `T` to `Publisher<R>`, then flattens the publisher.

### 5.3. Chaining Dependent Steps

For example, creating a customer and then creating a profile using the generated ID:

~~~java
public Mono<CustomerProfile> register(
        RegisterCustomerCommand command) {

    return customerRepository.save(
                    Customer.from(command))
            .flatMap(customer ->
                    profileRepository.save(
                            CustomerProfile.forCustomer(
                                    customer.getId(),
                                    command.profileName())));
}
~~~

The second step executes only after the first step emits the saved customer.

Do not call `subscribe()` between the two steps. Doing so splits the two execution flows and provides no ordering guarantee.

## 6. Migrating Synchronous Logic Chains to Reactive

### 6.1. From if/else to flatMap

Synchronous:

~~~java
public Customer register(RegisterCommand command) {
    if (customerRepository.existsByEmail(command.email())) {
        throw new EmailAlreadyRegisteredException();
    }

    return customerRepository.save(Customer.from(command));
}
~~~

Reactive:

~~~java
public Mono<Customer> register(RegisterCommand command) {
    return customerRepository.existsByEmail(command.email())
            .flatMap(exists -> {
                if (exists) {
                    return Mono.error(
                            new EmailAlreadyRegisteredException());
                }

                return customerRepository.save(
                        Customer.from(command));
            });
}
~~~

This is a mechanical control-flow translation. However, checking `exists` before inserting does not prevent race conditions under concurrent requests. A database unique constraint must still protect the data; the service must translate constraint violations into the appropriate business error.

### 6.2. Combining Two Independent Sources with zip

If two queries are independent and both results are needed:

~~~java
return customerRepository.findById(customerId)
        .zipWith(addressRepository.findByCustomerId(customerId))
        .map(tuple ->
                CustomerSummary.from(
                        tuple.getT1(),
                        tuple.getT2()));
~~~

`zipWith` emits only when both publishers emit an element. If either publisher completes empty, the zipped result also completes empty.

If one source can be empty while the business logic still proceeds, handle empty beforehand or choose an appropriate combination strategy.

### 6.3. Waiting on Multiple Operations Without Values Using when

If you need to execute two independent operations and only care that both complete:

~~~java
return Mono.when(
        auditRepository.save(auditRecord),
        notificationStateRepository.save(notificationState))
        .then();
~~~

`Mono.when` subscribes to the provided publishers and completes when all complete; an error from any publisher fails the combined stream. This does not automatically make the two operations atomic in the same transaction unless both participate in the same reactive transaction context.

### 6.4. Processing Multiple Elements with flatMap, concatMap, and flatMapSequential

With `Flux`:

~~~java
return customerRepository.findAllActive()
        .flatMap(customer ->
                riskService.calculateScore(customer));
~~~

`flatMap` can execute inner publishers concurrently and emit results in completion order. If sequential processing is required:

~~~java
return customerRepository.findAllActive()
        .concatMap(customer ->
                riskService.calculateScore(customer));
~~~

If you want concurrent execution while preserving source emission order:

~~~java
return customerRepository.findAllActive()
        .flatMapSequential(customer ->
                riskService.calculateScore(customer));
~~~

Choose bounded concurrency when downstream services or the database have finite resources. Never apply unbounded `flatMap` over a very large `Flux` without considering pressure on the connection pool and dependent services.

## 7. Publishers Are Lazy: Execution Timing Changes

In Reactor, most publishers are cold and lazy: creating a publisher does not execute the database query. Execution is triggered when subscribed to.

Example:

~~~java
Mono<Customer> customerMono =
        customerRepository.findById(42L);
~~~

This merely constructs a publisher. It does not guarantee the database has been accessed yet.

If nobody subscribes, the operation may never run. In WebFlux, the framework subscribes when handling the response publisher. In `StepVerifier`, the verifier subscribes when the test runs.

### 7.1. Do Not Call subscribe() Inside Services

Avoid:

~~~java
public void createCustomer(CreateCustomerCommand command) {
    customerRepository.save(Customer.from(command))
            .subscribe();
}
~~~

The method returns immediately, errors are not propagated to the caller, the caller does not know when the operation completes, and transactions/context can become detached from the request.

Prefer:

~~~java
public Mono<Customer> createCustomer(CreateCustomerCommand command) {
    return customerRepository.save(Customer.from(command));
}
~~~

The caller decides how to compose the publisher. The framework at the HTTP or message consumer boundary subscribes according to its lifecycle.

### 7.2. Use defer When Computation Must Run Per Subscription

~~~java
public Mono<String> nextReference() {
    return Mono.defer(() -> {
        String reference = referenceGenerator.next();
        return Mono.just(reference);
    });
}
~~~

`defer` invokes the supplier at subscription time, producing a fresh value per subscription.

If you use `Mono.just(referenceGenerator.next())`, the generator executes immediately when the method is called, not when subscribed.

### 7.3. Side Effects Must Be Inside the Publisher Chain

Synchronous:

~~~java
public void recordAccess(Long customerId) {
    accessLogRepository.save(new AccessLog(customerId));
}
~~~

Reactive:

~~~java
public Mono<Void> recordAccess(Long customerId) {
    return accessLogRepository.save(new AccessLog(customerId))
            .then();
}
~~~

If you create a publisher without returning or chaining it, the operation will never be triggered.

## 8. Converting Direct Values into Publishers Properly

Reactor factories have distinct semantics:

| Factory | When to Use | Notes |
|---|---|---|
| Mono.just(value) | Value is already computed and non-null | Emits that value immediately on subscribe |
| Mono.justOrEmpty(value) | Value may be null or Optional | Null/Optional.empty becomes empty |
| Mono.fromSupplier(supplier) | Produce a value synchronously on subscribe | Returning null completes empty |
| Mono.fromCallable(callable) | Invoke work that may throw an exception | Exception becomes onError; null becomes empty |
| Mono.fromRunnable(runnable) | Run an action with no return value | Completes as Mono<Void> |
| Flux.fromIterable(values) | Wrap an existing collection as a Flux | Collection was already constructed earlier |
| Flux.defer(supplier) | Create a fresh Flux per subscription | Supplier must return an appropriate Publisher/Flux |

Examples:

~~~java
return Mono.justOrEmpty(customerCache.get(id));
~~~

~~~java
return Mono.fromSupplier(() -> calculateDisplayName(customer));
~~~

~~~java
return Mono.fromRunnable(() -> localAuditBuffer.record(event));
~~~

These factories do not turn a blocking API into a non-blocking one. If the supplier invokes JDBC, file I/O, or a blocking HTTP client, it still blocks the executing thread unless scheduled appropriately.

## 9. Integrating Legacy Blocking Services During Transition

A large system may not be able to migrate every dependency at once. You can place a reactive adapter around a blocking API as a transitional step.

Example:

~~~java
public Mono<Customer> findLegacyCustomer(Long id) {
    return Mono.fromCallable(() ->
                    legacyCustomerService.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

`boundedElastic` is more appropriate than event-loop threads for some blocking tasks because it uses a scheduler intended for bounded blocking work. Still:

- It remains a blocking operation.
- The thread pool is finite and can saturate.
- Timeouts and cancellation may not interrupt the underlying blocking call.
- A wrapper should not be treated as a substitute for a reactive driver.
- Measure load and plan to remove the adapter if the goal is a non-blocking stack.

Do not wrap JDBC in `Mono.fromCallable` and claim the application has migrated to R2DBC. It only isolates blocking calls from the event loop.

### 9.1. When Imperative Callers Need Results from Reactive Services

A synchronous facade may be needed during transition:

~~~java
public Customer findCustomerBlocking(Long id) {
    return reactiveCustomerService.findById(id)
            .block(Duration.ofSeconds(3));
}
~~~

Use this only at controlled imperative boundaries, with a timeout, on an appropriate thread, and with clear empty/error handling. Never invoke such a method from a WebFlux event loop, a reactive transaction, or an executing publisher.

Keeping adapters at clean boundaries is far better than letting internal reactive services block whenever legacy callers invoke them.

## 10. Do Not Block to Extract Values from Mono/Flux

A common anti-pattern:

~~~java
public String getCustomerEmail(Long id) {
    Customer customer =
            customerRepository.findById(id).block();

    return customer.getEmail();
}
~~~

This approach:

- Blocks the thread until the database responds.
- Can cause deadlocks or exhaust event-loop threads if invoked from a reactive pipeline.
- Loses backpressure and composition benefits.
- Can throw errors or return `null` when the publisher is empty depending on how it is called.
- Blurs synchronous/reactive boundaries.

Return the publisher instead:

~~~java
public Mono<String> getCustomerEmail(Long id) {
    return customerRepository.findById(id)
            .map(Customer::getEmail);
}
~~~

Do not use `blockOptional()` as a workaround; it is still blocking.

## 11. Empty, null, and Optional When Changing Contracts

In synchronous code, a method may return `null` or `Optional.empty()`. In reactive contracts, represent absence using `Mono.empty()`.

Example:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

If business logic requires a customer to exist:

~~~java
public Mono<Customer> requireCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

Never return `Mono.just(null)`. Reactor forbids emitting `null` as an element.

### 11.1. Do Not Turn Every Empty Result into an Error

A search query can validly return no matches:

~~~java
public Flux<Customer> search(String keyword) {
    return customerRepository.search(keyword);
}
~~~

`Flux.empty()` is an empty result set, not an error.

Use `switchIfEmpty` only when the business contract requires a result to be present. Otherwise, converting empty to an error alters API semantics.

### 11.2. Nested Optional Inside Mono Is Usually Unnecessary

Avoid:

~~~java
Mono<Optional<Customer>> findCustomer(Long id);
~~~

Usually `Mono<Customer>` already represents both presence and absence of a customer. Use `Mono<Optional<T>>` only when `Optional` is genuinely part of the payload being emitted, not as a redundant encoding of not-found.

## 12. Converting Synchronous Exceptions into onError Signals

In synchronous code:

~~~java
public Customer getCustomer(Long id) {
    try {
        return repository.findById(id)
                .orElseThrow(() ->
                        new CustomerNotFoundException(id));
    } catch (DataAccessException ex) {
        throw new CustomerPersistenceException(ex);
    }
}
~~~

In a reactive flow, exceptions occurring when the publisher executes must be handled with operators:

~~~java
public Mono<Customer> getCustomer(Long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)))
            .onErrorMap(
                    DataAccessException.class,
                    CustomerPersistenceException::new);
}
~~~

A `try`/`catch` around constructing the publisher will typically not catch errors raised later upon subscription.

Use:

- `doOnError`: log/record metrics while preserving the error.
- `onErrorMap`: translate exception types.
- `onErrorResume`: substitute an erroring publisher with a fallback publisher when a valid fallback exists.
- `retryWhen`: conditional, bounded retries.

Never turn every error into `Mono.empty()`, because database failures could then be mistaken for not-found.

### 12.1. Preserve the Cause When Translating Errors

~~~java
public class CustomerPersistenceException extends RuntimeException {
    public CustomerPersistenceException(Throwable cause) {
        super("Unable to access customer data", cause);
    }
}
~~~

Preserving the cause allows logs and traces to track back to the underlying R2DBC error. Never expose raw SQL messages or internal stack traces directly to clients.

## 13. Migrating Control Flow and Loops

### 13.1. Do Not Use for-each to Wait on Publishers

Wrong:

~~~java
for (Customer customer : customers) {
    orderRepository.findByCustomerId(customer.getId())
            .subscribe();
}
~~~

Independent subscriptions are not combined into a single result, errors are detached, and there is no backpressure coordination.

Prefer:

~~~java
return Flux.fromIterable(customers)
        .concatMap(customer ->
                orderRepository.findByCustomerId(customer.getId()));
~~~

Or if the customer data also comes from a repository:

~~~java
return customerRepository.findAll()
        .concatMap(customer ->
                orderRepository.findByCustomerId(customer.getId()));
~~~

### 13.2. When Sequential vs. Concurrent Processing Fits

`concatMap` processes items one at a time and preserves order. `flatMap` allows multiple inner publishers to run concurrently. `flatMapSequential` runs concurrently while emitting in source order.

Choose based on business requirements:

- Order-dependent state updates: consider `concatMap`.
- Independent service calls with bounded concurrency: `flatMap` with an explicit concurrency limit.
- Need ordered results while allowing concurrent work: `flatMapSequential`.

Do not convert a sequential loop into `flatMap` by default without checking race conditions, ordering requirements, and connection pool limits.

## 14. Migrating Transactions to Reactive Contracts

Spring supports reactive transactions for R2DBC via a reactive transaction manager and Reactor Context. A service method must return the publisher participating in the execution chain so the transaction manager can manage its lifecycle.

Example:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return customerRepository.findById(command.customerId())
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(
                            command.customerId())))
            .flatMap(customer ->
                    orderRepository.save(Order.from(customer, command)))
            .flatMap(order ->
                    orderLineRepository.saveAll(
                                    command.lines().stream()
                                            .map(line ->
                                                    OrderLine.from(order, line))
                                            .toList())
                            .then(Mono.just(order)));
}
~~~

This example assumes `@Transactional` is handled by Spring's reactive transaction manager and all repositories share the same transaction-aware `ConnectionFactory` configuration.

Key points:

- The method must return the publisher so the transaction boundary spans subscription and terminal signals.
- Do not call `subscribe()` inside the method.
- Do not block between steps.
- Do not swallow errors with fallbacks if business logic requires rollback.
- Operations must participate in the same reactive transaction context.
- External side effects such as sending email do not automatically roll back with the database.

If explicit transaction control is needed, use `TransactionalOperator` and return the wrapped publisher:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    Mono<Order> work = performOrderCreation(command);

    return transactionalOperator.transactional(work);
}
~~~

### 14.1. Do Not Keep @Transactional on Direct-Value Methods Calling Reactive Repositories

A synchronous method returning `Order` cannot wait on an R2DBC operation while properly maintaining a reactive transaction. Calling `block()` reverts to a blocking model and can break the execution context.

Migrate both the contract and the transaction boundary to publishers.

### 14.2. Place Retries Outside the Appropriate Transaction Boundary

If a transaction needs retries, typically wrap the transactional publisher with retry so each resubscription opens a fresh transaction:

~~~java
return transactionalOperator.transactional(
                performOrderCreation(command))
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                        .filter(this::isRetryable));
~~~

Retry only appropriate transient errors and operations that are safe to re-execute. Never retry blindly when transaction commit status is uncertain or external side effects exist.

## 15. Context Propagation and Security Once Services Are Reactive

In WebFlux, `SecurityContext` and reactive metadata are typically propagated via Reactor Context. When services return publishers and callers chain them together, context can be preserved across supported operators.

For example, reading the auditor or authentication in a reactive context must use the corresponding reactive API, such as `ReactiveSecurityContextHolder`.

Do not rely on reading user identity from `ThreadLocal` or imperative `SecurityContextHolder` inside reactive services. Execution threads can change.

Also avoid:

~~~java
repository.save(entity).subscribe();
~~~

Detached subscriptions may lose the original request context and transaction. Chain publishers into the active execution flow.

## 16. Controllers and HTTP Contracts After Services Become Reactive

Once services return `Mono`/`Flux`, WebFlux controllers can return publishers directly.

GET example:

~~~java
@GetMapping("/customers/{id}")
public Mono<CustomerResponse> getById(@PathVariable Long id) {
    return customerService.getById(id)
            .map(CustomerResponse::from);
}
~~~

List example:

~~~java
@GetMapping("/customers")
public Flux<CustomerResponse> findAll() {
    return customerService.findAll()
            .map(CustomerResponse::from);
}
~~~

POST example:

~~~java
@PostMapping("/customers")
public Mono<ResponseEntity<CustomerResponse>> create(
        @RequestBody @Valid CreateCustomerRequest request) {

    return customerService.create(request.toCommand())
            .map(CustomerResponse::from)
            .map(response ->
                    ResponseEntity.created(
                            URI.create("/api/customers/" + response.id()))
                            .body(response));
}
~~~

The WebFlux framework subscribes to the publisher to produce the HTTP response. Controllers should never call `block()` or `subscribe()`.

### 16.1. Define Not-Found Responses Explicitly

If a service returns `Mono.empty()`, decide what HTTP response the API should return. The controller can map empty to 404:

~~~java
@GetMapping("/customers/{id}")
public Mono<ResponseEntity<CustomerResponse>> getById(
        @PathVariable Long id) {

    return customerService.findById(id)
            .map(CustomerResponse::from)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Or the service can emit `CustomerNotFoundException` via `switchIfEmpty`, and `@RestControllerAdvice` maps it to 404.

Pick one clear contract. Do not let an empty result silently turn into a 200 with an empty body if the API specifies 404.

### 16.2. Flux Can Be Encoded as a Collection Response

Controllers returning `Flux<T>` can be encoded by WebFlux according to the media type and codecs. If the API contract requires pagination metadata such as total count, page number, and page size, you usually need a page DTO rather than returning a bare `Flux`.

Example:

~~~java
public Mono<CustomerPageResponse> findPage(PageRequest request) {
    return customerRepository.findByPage(request)
            .collectList()
            .zipWith(customerRepository.count())
            .map(tuple ->
                    new CustomerPageResponse(
                            tuple.getT1(),
                            request.page(),
                            request.size(),
                            tuple.getT2()));
}
~~~

This is illustrative. Ensure the data query and count query are consistent if data mutates concurrently, and never collect an unbounded result set.

## 17. Migrating Message Handlers and Background Tasks

Controllers are not the only callers of services. A synchronous service may be called by:

- Schedulers.
- Message consumers.
- Application event listeners.
- Command-line runners.
- Batch jobs.
- Other services in the module.

When migrating to reactive, each adapter must connect the publisher to the lifecycle managed by its framework.

Example reactive consumer:

~~~java
public Mono<Void> handle(OrderCreated event) {
    return orderService.process(event.orderId())
            .then();
}
~~~

If the consumer framework supports returning `Mono<Void>`, return the publisher so the framework coordinates acknowledgment with completion.

If the library callback is an imperative `void`, check whether the API offers a reactive handler option. Never fire a detached `subscribe()` and immediately acknowledge the message; the message could be acknowledged before the database commits.

For schedulers, return `Mono<Void>` if the scheduler integrates reactively. If a scheduler only invokes `Runnable`, use an adapter that manages subscription and errors and prevents unintended overlapping job runs.

## 18. Migrating Tests from Direct Values to StepVerifier

Synchronous tests typically assert directly:

~~~java
Customer customer = service.getById(42L);

assertThat(customer.getId()).isEqualTo(42L);
~~~

Reactive tests should use `StepVerifier`:

~~~java
StepVerifier.create(service.getById(42L))
        .assertNext(customer ->
                assertThat(customer.getId()).isEqualTo(42L))
        .verifyComplete();
~~~

### 18.1. Testing Empty

~~~java
StepVerifier.create(service.findById(999L))
        .verifyComplete();
~~~

### 18.2. Testing Errors

~~~java
StepVerifier.create(service.getRequiredById(999L))
        .expectError(CustomerNotFoundException.class)
        .verify();
~~~

### 18.3. Testing Multi-Element Flux

~~~java
StepVerifier.create(service.findAll())
        .expectNextCount(2)
        .verifyComplete();
~~~

### 18.4. Testing Timeouts

~~~java
StepVerifier.create(service.findById(42L))
        .expectNextCount(1)
        .verifyComplete(Duration.ofSeconds(3));
~~~

Do not use `block()` to test every publisher, because `StepVerifier` explicitly verifies ordering, empty completion, errors, completion, and cancellation.

### 18.5. Repository Mocks Must Return Publishers

With Mockito:

~~~java
when(customerRepository.findById(42L))
        .thenReturn(Mono.just(customer));
~~~

Do not mock a direct entity when the method actually returns `Mono<Customer>`.

Testing error:

~~~java
when(customerRepository.findById(42L))
        .thenReturn(Mono.error(
                new DataAccessResourceFailureException("database unavailable")));
~~~

Testing empty:

~~~java
when(customerRepository.findById(42L))
        .thenReturn(Mono.empty());
~~~

Integration tests against a real database are still necessary for SQL, mapping, transactions, and driver behavior; unit tests mocking publishers do not verify actual persistence.

## 19. Maintaining Compatibility with Synchronous Callers During Transition

If some modules cannot migrate immediately, you can keep a synchronous adapter at the module boundary.

One option:

~~~java
@Component
public class BlockingCustomerFacade {

    private final ReactiveCustomerService reactiveService;

    public Customer findById(Long id) {
        return reactiveService.findById(id)
                .block(Duration.ofSeconds(3));
    }
}
~~~

This facade is strictly for controlled imperative callers. Never inject it into a WebFlux controller or another reactive service.

Another option is maintaining two separate implementations:

- A blocking adapter using JDBC for legacy modules.
- A reactive adapter using R2DBC for new modules.

This increases the cost of maintaining two persistence paths, so keep it only when there is a clear migration rationale and a retirement deadline.

### 19.1. Do Not Create Overloads Differing Only in Return Type

As noted earlier, Java does not allow overloading methods with the same signature differing only by return type. Do not attempt generic tricks or casts to circumvent this limitation.

Use distinct method names or interfaces during transition, then unify the contract once all callers are updated.

### 19.2. Defining Blocking Boundaries

If a reactive service must call a blocking library, isolate it inside an adapter:

~~~java
public Mono<LegacyResult> callLegacy(LegacyCommand command) {
    return Mono.fromCallable(() ->
                    legacyClient.execute(command))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Configure timeouts, concurrency limits, and metrics for the adapter. Never allow blocking calls onto the event loop.

## 20. Backpressure and Resource Limits After Switching to Flux

An older service returning `List<T>` had already loaded all data before returning to the caller. Moving to `Flux` lets callers consume elements incrementally, but only if underlying layers actually support streaming.

Verify:

- Does the repository/driver emit row by row or buffer the entire result?
- Can the caller process slowly?
- Does the query hold a connection open for the entire time `Flux` is consumed?
- Does `collectList()` increase memory usage?
- Does `flatMap` have bounded concurrency?
- Does the HTTP client cancel the subscription when disconnecting?

`Flux` does not guarantee the database is not buffering. Actual behavior depends on the driver, fetch strategy, query, and consumption pattern.

For large result sets, consider pagination or bounded streams. Do not hold a transaction open long just to stream a huge dataset over HTTP when pagination is appropriate.

## 21. Common Mistakes When Migrating Contracts

| Mistake | Consequence | Fix |
|---|---|---|
| Changing `T` to `Mono<T>` while keeping old callers | Callers cannot access properties of `T` | Migrate callers to `map`/`flatMap` |
| Using `map` for methods returning a publisher | Produces `Mono<Mono<T>>` | Use `flatMap` |
| Calling `block()` in WebFlux services/controllers | Blocks the event loop and loses reactive benefits | Return publishers end-to-end |
| Calling `subscribe()` inside services | Detaches lifecycle, errors, and context from callers | Return and chain publishers |
| Turning every `List<T>` into `Mono<List<T>>` | Buffers entire dataset, loses streaming | Use `Flux` if callers process row by row |
| Turning every empty result into an exception | Search with no matches treated as an error | Use `switchIfEmpty` only per contract |
| Returning `Mono.just(null)` | Reactor rejects `null` | Use `Mono.empty()` or `justOrEmpty` |
| Nesting `Optional` inside `Mono` | Encodes emptiness twice | Use `Mono<T>` |
| Assuming query ran immediately upon method call | Publisher has not been executed yet | Verify via subscriber/`StepVerifier` |
| Using unbounded `flatMap` | Spikes concurrency, exhausts pool or overwhelms downstream | Limit concurrency or use `concatMap` |
| Swallowing errors via `onErrorResume` to empty | Hides database errors as not-found | Fall back only when business rules allow |
| Using `try`/`catch` around `Mono` construction | Does not catch errors emitted on subscribe | Use `onErrorMap`/`onErrorResume`/`doOnError` |
| Keeping `@Transactional` on blocking methods calling reactive | Transaction does not span reactive lifecycle | Migrate both contract and boundary to reactive |
| Sending emails directly inside a transaction | Email cannot roll back when DB rolls back | Use outbox/after-commit strategies |
| Using `ThreadLocal` for security context | Context is lost across thread switches | Use Reactor Context/reactive APIs |
| Updating controllers while missing schedulers/consumers | Remaining callers fail to handle publishers | Find and migrate all call sites |
| Creating blocking facades without timeouts | Threads can hang indefinitely | Use only at imperative boundaries with timeouts |
| Calling JDBC inside `Mono.fromCallable` on event loop | Still blocking | `subscribeOn(boundedElastic)` or replace with R2DBC |
| Mocking entities instead of `Mono`/`Flux` | Tests do not match service contract | Mock the corresponding publishers |

## 22. Process for Migrating a Service Module

A practical process keeps changes controlled:

1. List all service methods, return types, and callers.
2. Classify results: single row, multiple rows, optional, boolean, count, command, or stream.
3. Identify which repositories already use the R2DBC reactive API.
4. Change service contracts to `Mono`/`Flux`/`Mono<Void>` according to cardinality.
5. Migrate service calling logic using `map`, `flatMap`, `zip`, `then`, or `concatMap`.
6. Convert synchronous errors to `onError` signals and distinguish empty from errors.
7. Keep all database operations within the same reactive chain/transaction context.
8. Migrate controllers, message handlers, schedulers, and event listeners.
9. Isolate remaining blocking callers in adapters with timeouts and proper schedulers.
10. Migrate unit tests to `StepVerifier` and add integration tests against a real database.
11. Verify cancellation, concurrency, backpressure, and pool capacity.
12. Remove unneeded `subscribe`/`block` bridges once all callers are reactive.

### 22.1. Complete Migration Example

Old contract:

~~~java
public interface OrderService {
    Order getById(Long id);
    List<Order> findByCustomer(Long customerId);
    Order create(CreateOrderCommand command);
    void cancel(Long id);
}
~~~

New contract:

~~~java
public interface OrderService {
    Mono<Order> getById(Long id);
    Flux<Order> findByCustomer(Long customerId);
    Mono<Order> create(CreateOrderCommand command);
    Mono<Void> cancel(Long id);
}
~~~

Implementation:

~~~java
@Service
public class OrderServiceImpl implements OrderService {

    private final OrderRepository orderRepository;
    private final CustomerRepository customerRepository;

    public OrderServiceImpl(
            OrderRepository orderRepository,
            CustomerRepository customerRepository) {
        this.orderRepository = orderRepository;
        this.customerRepository = customerRepository;
    }

    @Override
    public Mono<Order> getById(Long id) {
        return orderRepository.findById(id)
                .switchIfEmpty(Mono.error(
                        new OrderNotFoundException(id)));
    }

    @Override
    public Flux<Order> findByCustomer(Long customerId) {
        return orderRepository.findByCustomerId(customerId);
    }

    @Override
    @Transactional
    public Mono<Order> create(CreateOrderCommand command) {
        return customerRepository.findById(command.customerId())
                .switchIfEmpty(Mono.error(
                        new CustomerNotFoundException(
                                command.customerId())))
                .flatMap(customer ->
                        orderRepository.save(
                                Order.create(customer, command)));
    }

    @Override
    @Transactional
    public Mono<Void> cancel(Long id) {
        return orderRepository.findById(id)
                .switchIfEmpty(Mono.error(
                        new OrderNotFoundException(id)))
                .flatMap(order -> {
                    order.cancel();
                    return orderRepository.save(order);
                })
                .then();
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public Mono<OrderResponse> getById(@PathVariable Long id) {
        return orderService.getById(id)
                .map(OrderResponse::from);
    }

    @GetMapping
    public Flux<OrderResponse> findByCustomer(
            @RequestParam Long customerId) {
        return orderService.findByCustomer(customerId)
                .map(OrderResponse::from);
    }

    @PostMapping
    public Mono<ResponseEntity<OrderResponse>> create(
            @RequestBody @Valid CreateOrderRequest request) {
        return orderService.create(request.toCommand())
                .map(OrderResponse::from)
                .map(response ->
                        ResponseEntity
                                .created(URI.create(
                                        "/api/orders/" + response.id()))
                                .body(response));
    }

    @PostMapping("/{id}/cancel")
    public Mono<ResponseEntity<Void>> cancel(@PathVariable Long id) {
        return orderService.cancel(id)
                .thenReturn(ResponseEntity.noContent().build());
    }
}
~~~

This example assumes reactive repositories, a reactive R2DBC transaction manager, and an exception handler mapping `OrderNotFoundException`/`CustomerNotFoundException` to appropriate HTTP statuses. DTOs, entities, and queries must match your project's types.

Notice there is no `block()` or `subscribe()` in the service or controller. Publishers are returned end-to-end to WebFlux, and errors flow along the same execution chain.

## 23. Key Takeaways

- Migrating a service to reactive changes the contract and callers, not just return types.
- `Publisher<T>` is the Reactive Streams abstraction; Reactor typically uses `Mono<T>` for 0..1 and `Flux<T>` for 0..N elements.
- Choose `Mono`/`Flux` based on cardinality and how callers consume data.
- `Mono.empty()` represents absence of an item; never use `null` or `Mono.just(null)`.
- Convert `Optional<T>` to `Mono<T>`, `List<T>` to `Flux<T>` or `Mono<List<T>>` as needed, and `void` to `Mono<Void>`.
- Use `map` for synchronous transformations and `flatMap` for steps returning publishers.
- Use `zip` for independent sources where all results are needed, `then` when only completion matters, and `concatMap` when ordering is required.
- Publishers are typically lazy; calling a method that returns a `Mono` does not mean the database query has run.
- Never call `subscribe()` or `block()` in reactive services/controllers.
- Use blocking adapters only at controlled imperative boundaries with timeouts and appropriate schedulers.
- Apply `switchIfEmpty` according to business rules; distinguish empty from database errors.
- Use `onErrorMap`, `onErrorResume`, and `doOnError` instead of `try`/`catch` around publishers.
- Reactive transactions must wrap the publisher lifecycle and stay within the same Reactor Context.
- WebFlux controllers can return `Mono`/`Flux` directly; the framework manages subscription.
- Schedulers, message consumers, and event listeners are also callers whose contracts must be migrated.
- Use `StepVerifier` to assert values, empty completion, errors, completion, and cancellation.
- Bound concurrency/backpressure to avoid exhausting the R2DBC connection pool.
- Java does not allow overloading differing only by return type; interface changes need a compatibility plan for callers.
