# Using onErrorMap and onErrorResume with Business Semantics

In Spring Data R2DBC applications, database errors propagate through `Mono` and `Flux` publishers as error signals. The Service layer must decide what each error means for the business domain: data already exists, a record is no longer at the expected version, the database is temporarily unreachable, or a data constraint was violated. Reactor provides two key operators to express these decisions: `onErrorMap` transforms one error into another, whereas `onErrorResume` replaces a failing stream with a fallback publisher.

These two operators serve different purposes. Use `onErrorMap` when you want to preserve failure semantics while translating the exception into one meaningful at the application layer. Use `onErrorResume` when the business domain has an explicit recovery path, such as returning cached data, reading from a standby source, or returning an accepted default result. If you are only renaming an error to a business exception, do not turn it into a successful outcome. If no valid recovery exists, let the error propagate to higher-level error handling.

## 1. Errors in Reactive Pipelines

A Reactor publisher can emit three primary signals:

- `onNext`: emits a value.
- `onComplete`: completes normally.
- `onError`: terminates with an error.

An error signal is terminal: once a publisher emits an error, that publisher stops emitting any further values or completion signals. Error-handling operators create a new downstream flow that can change the exception type or swap the error for another publisher.

Example repository operation:

```java
Mono<CustomerEntity> customer = customerRepository.findById(customerId);
```

The publisher can:

- Emit a `CustomerEntity` and complete.
- Complete empty if no record exists.
- Emit an error if the database, driver, or mapping fails.

These three cases are not equivalent. `Mono.empty()` is not an error, whereas `Mono.error(...)` is an error. Therefore, `onErrorMap` and `onErrorResume` do not handle empty completion; use `switchIfEmpty` for that case.

## 2. Comparing onErrorMap and onErrorResume

| Operator | Behavior | Result after handling | When to use |
|---|---|---|---|
| `onErrorMap` | Transforms the current exception into another exception | Remains an error signal | Translating infrastructure errors into application/business errors while preserving the cause |
| `onErrorResume` | Chooses an alternative publisher when upstream fails | May emit values, complete empty, or still error | A valid business fallback exists |
| `switchIfEmpty` | Replaces an empty-completing publisher with another publisher | Alternative publisher runs when no value was emitted | Handling missing data when a repository returns `Mono.empty()` |

Brief example:

```java
// Still fails, but the error has a meaningful application-layer name.
return repository.findById(id)
        .onErrorMap(DataAccessException.class,
                error -> new CustomerStorageException(id, error));

// Has a fallback: if cache fails, read from the primary source.
return cache.get(id)
        .onErrorResume(CacheAccessException.class,
                error -> repository.findById(id));
```

Do not use `onErrorResume` merely to avoid declaring or handling exceptions. Converting errors into `Mono.empty()` or a default value can hide missing data, database failures, or business rule violations.

## 3. Using onErrorMap to Translate Persistence Errors into Application Errors

### 3.1. Separating exceptions by layer

Repositories and drivers work with data access errors. Services should express failures in domain terms or according to the application's contract. Controllers and APIs do not need to know the exact exception names of the PostgreSQL driver or another database engine.

Examples of common Spring exceptions:

| Spring exception | Typical meaning | Business-layer interpretation |
|---|---|---|
| `DuplicateKeyException` | Unique or primary key violation | Resource or identifier already exists |
| `DataIntegrityViolationException` | Data constraint violation | Data does not satisfy storage constraints |
| `OptimisticLockingFailureException` | Entity updated based on a stale version | Concurrent modification conflict |
| `TransientDataAccessResourceException` | Potentially temporary data resource error | May consider bounded retry if operation is safe |
| `DataAccessResourceFailureException` | Cannot access data resource | Database/connection issue; usually propagate error or use explicit fallback |
| `DataAccessException` | Base class for many Spring data access errors | Use only when handling a broad group whose meaning is well defined |

Which specific exception is emitted depends on the driver, Spring Framework, Spring Data, and the data access path. Verify actual exceptions in your application version rather than assuming every database error translates to the same subtype.

### 3.2. Creating business exceptions

Example when a customer's email already exists:

```java
public class EmailAlreadyRegisteredException extends RuntimeException {

    public EmailAlreadyRegisteredException(String email, Throwable cause) {
        super("Email is already registered: " + email, cause);
    }
}
```

The service can translate `DuplicateKeyException` into a business exception:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<CustomerEntity> register(String email, String displayName) {
        CustomerEntity customer = new CustomerEntity(
                null, email, displayName, null);

        return repository.save(customer)
                .onErrorMap(DuplicateKeyException.class,
                        error -> new EmailAlreadyRegisteredException(email, error));
    }
}
```

Here `onErrorMap` preserves the failure nature. It only replaces the persistence exception with one the Service/API understands. The original cause stays attached in `cause`, which helps with logging, tracing, and diagnostics.

This example assumes the violated constraint is the unique email constraint. If the table has multiple unique constraints, do not blindly map every `DuplicateKeyException` to `EmailAlreadyRegisteredException`. Distinguish the exact constraint using driver metadata/exceptions or design the operation so you know which condition triggered the failure. If you cannot distinguish them, use a more general exception like `CustomerConflictException`.

### 3.3. Using predicates to map a selected group of errors

Besides class-based overloads, `onErrorMap` accepts a predicate:

```java
return repository.save(customer)
        .onErrorMap(
                error -> error instanceof DataIntegrityViolationException,
                error -> new InvalidCustomerDataException(
                        "Customer data violates a storage constraint", error));
```

Predicates let you apply a rule when multiple exception subtypes should map to one application error type. Only group errors that truly share the same business meaning. Do not convert every `RuntimeException` into a validation error; programming bugs, configuration errors, and transient database failures must remain distinct.

### 3.4. Preserving the cause

When creating a new exception, pass the original exception as `cause`:

```java
error -> new CustomerStorageException(customerId, error)
```

Avoid:

```java
error -> new CustomerStorageException(customerId)
```

when root-cause diagnostics are needed. Dropping the cause can lose the original stack trace and driver details. Still, never expose SQL messages, internal table names, or sensitive connection info directly in HTTP responses.

## 4. Using onErrorResume When a Recovery Path Exists

`onErrorResume` receives the exception and returns another publisher. The replacement publisher may emit a value, complete empty, or emit another error.

### 4.1. Falling back to a cache or secondary read source

For example, an endpoint reads customer info from cache first; if cache access fails, the Service queries the database:

```java
public Mono<CustomerView> findCustomer(Long id) {
    Mono<CustomerView> cacheOrDatabase = cacheRepository.findById(id)
            .switchIfEmpty(Mono.defer(() -> customerRepository.findById(id)
                    .map(CustomerView::fromEntity)));

    return cacheOrDatabase.onErrorResume(CacheAccessException.class,
            cacheError -> customerRepository.findById(id)
                    .map(CustomerView::fromEntity));
}
```

This example demonstrates two distinct cases:

- Cache emits an access error: `onErrorResume` falls back to the database.
- Cache completes empty: `switchIfEmpty` falls back to the database.

If cache returns data, the database is not called. `switchIfEmpty` is attached to the cache publisher before the error fallback, so the database is invoked only once per fallback path. In a real application, also define how to repopulate cache after reading the primary source and record metrics when cache is unavailable.

### 4.2. Returning a default result when business rules allow

Some auxiliary data can have a valid default value. For instance, if a statistics service is unavailable, the UI might display a "data unavailable" state instead of breaking the whole page:

```java
public Mono<DashboardStats> loadOptionalStats() {
    return statsRepository.loadStats()
            .onErrorResume(StatsUnavailableException.class,
                    error -> Mono.just(DashboardStats.unavailable()));
}
```

This fallback is only valid if the product clearly distinguishes "no statistics" or "statistics temporarily unavailable" from real figures. Never return a zero statistic if users might mistake it for an accurate measurement.

### 4.3. Falling back to an empty publisher

`Mono.empty()` can be used when the domain defines a specific failure as meaning no result should be returned:

```java
return recommendationService.findFor(customerId)
        .onErrorResume(RecommendationUnavailableException.class,
                error -> Mono.empty());
```

Use this only when callers understand that an empty result is an acceptable state. If recommendation failures need observation, metrics, or user notice, record them before returning empty. Do not convert arbitrary database errors into empty because that eliminates the distinction between "no data" and "unable to read data."

### 4.4. A fallback publisher can still fail

`onErrorResume` does not guarantee recovery succeeds. If the replacement publisher also emits an error, the new error flows downstream:

```java
return primaryRepository.findById(id)
        .onErrorResume(PrimaryStoreUnavailableException.class,
                error -> replicaRepository.findById(id));
```

If the replica is also unreachable, the caller still receives an error signal. Never wrap a fallback in a synthetic success value just to force an endpoint to succeed.

## 5. Distinguishing Not Found from Data Access Failures

In Spring Data R2DBC, `findById` normally returns `Mono.empty()` when no record exists. This is a normal completion, not an exception. To turn that case into a business error, use `switchIfEmpty`:

```java
public Mono<CustomerEntity> getRequiredCustomer(Long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
```

If the database is unreachable, the publisher emits an error and `switchIfEmpty` does not run. If you also want to translate persistence errors, combine them:

```java
public Mono<CustomerEntity> getRequiredCustomer(Long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .onErrorMap(DataAccessException.class,
                    error -> new CustomerStorageException(id, error));
}
```

In this example, `CustomerNotFoundException` is not a `DataAccessException`, so it passes through untouched. Data access errors are translated into `CustomerStorageException`.

Do not use `onErrorResume` to handle not-found cases when the repository already signals them with `Mono.empty()`. Choosing the right operator makes the code's intent explicit.

## 6. Operator Placement Determines Error-Handling Scope

Each operator only observes errors from the pipeline upstream of it. Operator ordering therefore changes behavior.

### 6.1. Map error first, then fall back

```java
return repository.save(customer)
        .onErrorMap(DuplicateKeyException.class,
                error -> new EmailAlreadyRegisteredException(
                        customer.email(), error))
        .onErrorResume(EmailAlreadyRegisteredException.class,
                error -> Mono.error(new RegistrationConflictException(error)));
```

`onErrorMap` converts `DuplicateKeyException` into `EmailAlreadyRegisteredException`. The downstream `onErrorResume` sees the mapped exception and can act on it.

In practice, when no fallback is needed, translating once at the Service boundary and letting the API layer map it to an HTTP response is usually enough. Avoid adding extra wrapper exception classes unless they convey additional meaning.

### 6.2. Fall back first, then map remaining errors

```java
return primaryRepository.findById(id)
        .onErrorResume(PrimaryStoreUnavailableException.class,
                error -> replicaRepository.findById(id))
        .onErrorMap(DataAccessException.class,
                error -> new CustomerStorageException(id, error));
```

The fallback handles failures from the primary store. If the replica emits a `DataAccessException`, the downstream mapper still sees it and converts it to an application error. This is helpful when you want a fallback for a specific source while still normalizing any remaining errors.

### 6.3. A fallback can introduce new errors

If `onErrorMap` precedes `onErrorResume`, it only maps errors from upstream before it. If the fallback publisher emits a new error, that error will not flow backward through an earlier mapper. To normalize errors from both the primary and fallback sources, place a shared error operator after the branches converge.

### 6.4. Placing error handling inside vs. outside flatMap

Handling errors inside `flatMap` affects only the corresponding inner publisher:

```java
return Flux.fromIterable(customerIds)
        .flatMap(id -> repository.findById(id)
                .onErrorResume(DataAccessException.class,
                        error -> Mono.empty()), 8);
```

Here, a single ID encountering a data access failure can be skipped while the remaining IDs continue. This is only valid if partial results are acceptable to the business.

If error handling is placed outside:

```java
return Flux.fromIterable(customerIds)
        .flatMap(repository::findById, 8)
        .onErrorResume(DataAccessException.class,
                error -> fallbackForWholeBatch());
```

an error from any inner publisher terminates the outer stream and triggers the fallback for the whole batch. Choose the scope based on business intent: skip one element, substitute a group of records, or fail the whole request.

## 7. Preserving Transaction Boundaries When Handling Errors

This is especially important in Spring Data R2DBC. A reactive transaction is coordinated around the publisher returned by a transactional method. When an error escapes the transaction boundary, the transaction manager can roll back. However, if an `onErrorResume` inside the pipeline converts the error into a normal result, the transaction manager may see the publisher complete successfully and commit earlier operations.

Dangerous example:

```java
@Transactional
public Mono<OrderEntity> placeOrder(OrderEntity order) {
    return inventoryRepository.reserve(order)
            .then(orderRepository.save(order))
            .onErrorResume(DataAccessException.class,
                    error -> Mono.just(order));
}
```

If a write operation fails and `onErrorResume` turns it into `Mono.just(order)` before the transaction completes, the error may never reach the transaction boundary. Depending on rollback-only status and the failure cause, the transaction might not roll back as intended. Moreover, returning the unsaved `order` can mislead callers into thinking the order was created.

If the business requires the entire operation to fail when any write step errors, let the error escape:

```java
@Transactional
public Mono<OrderEntity> placeOrder(OrderEntity order) {
    return inventoryRepository.reserve(order)
            .then(orderRepository.save(order));
}
```

Once the transaction finishes and rolls back, an outer caller can translate the exception into a response or trigger a fallback outside that transaction:

```java
public Mono<OrderResponse> placeOrderCommand(OrderEntity order) {
    return transactionalOrderService.placeOrder(order)
            .map(OrderResponse::fromEntity)
            .onErrorMap(OptimisticLockingFailureException.class,
                    error -> new OrderConflictException(order.id(), error));
}
```

Here the error crosses the transaction boundary as an error signal; exception translation occurs in the outer orchestrating layer. If a fallback itself writes data, design a new transaction or a separate compensating flow rather than swallowing an error mid-transaction when rollback is needed.

## 8. Handling Errors by Business Category

### 8.1. Unique constraint violation

Typical meaning: the resource already exists or the request conflicts with existing data.

```java
return customerRepository.save(customer)
        .onErrorMap(DuplicateKeyException.class,
                error -> new EmailAlreadyRegisteredException(
                        customer.email(), error));
```

The API layer can map this business exception to `409 Conflict` or a validation error per the API contract. If the violated constraint is not guaranteed to be email, use a more general exception type.

Checking existence before inserting can produce friendlier messages, yet it cannot replace a unique constraint. Two requests can both pass the check before either inserts. The database constraint remains the final safeguard.

### 8.2. Optimistic locking conflict

Meaning: the entity was updated by another request after the current read.

```java
return repository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .map(customer -> customer.rename(newName))
        .flatMap(repository::save)
        .onErrorMap(OptimisticLockingFailureException.class,
                error -> new CustomerConflictException(id, error));
```

Do not automatically return the stale entity or treat the update as successful. The client may need to reload the data, review the latest changes, and resubmit according to business rules.

### 8.3. Database temporarily unavailable

Meaning: the system cannot complete the operation due to connection errors, timeouts, or transient data resource issues.

```java
return repository.findById(id)
        .onErrorMap(DataAccessResourceFailureException.class,
                error -> new CustomerStoreUnavailableException(error));
```

Do not translate this into `CustomerNotFoundException` because data was never read successfully. If a replica/cache exists, you can use `onErrorResume` to hit a designed fallback source. Otherwise, propagate the error so the API returns an appropriate service error response.

### 8.4. Invalid data errors

Meaning: data violates domain rules or schema constraints. If the exact constraint can be identified, map it to the corresponding business error. Do not map every `DataIntegrityViolationException` to a single field error when the database enforces multiple distinct constraints.

### 8.5. Auxiliary service failures

If auxiliary data is optional, falling back may make sense:

```java
return customerRepository.findById(id)
        .flatMap(customer -> loyaltyService.findPoints(customer.id())
                .onErrorResume(LoyaltyServiceUnavailableException.class,
                        error -> Mono.just(0L))
                .map(points -> new CustomerProfile(customer, points)));
```

This example is valid only if `0` is a product-accepted default that cannot be confused with an actual point balance. Representing an explicit `UNAVAILABLE` state is often better than fabricating a numeric value.

## 9. Retries and Ordering with onErrorMap / onErrorResume

Retrying is a separate decision. `retryWhen` resubscribes to upstream when an error matches the retry policy. Only retry transient errors and operations that are safe to repeat.

Example:

```java
return repository.findById(id)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .filter(TransientDataAccessResourceException.class::isInstance))
        .onErrorMap(DataAccessException.class,
                error -> new CustomerStorageException(id, error));
```

Retry sits before `onErrorMap`, so the predicate sees the original persistence exception type. If you map the error before retrying, the predicate must recognize the new business exception or inspect its cause. Clear ordering avoids accidentally retrying unrecoverable errors.

Never blindly retry failures such as:

- A unique constraint already violated.
- Invalid input data.
- An optimistic locking conflict without reloading state.
- Programming or configuration bugs.

For writes, retries demand extra caution. If the client does not know whether the previous write committed due to a lost connection after database processing, resending can create duplicate records or repeat side effects. Use idempotency keys, unique constraints, or idempotent operations whenever business logic requires safe write retries.

`onErrorResume` can replace a failing publisher with a successful publisher before a downstream `retryWhen` ever sees the error, preventing retries from running. If you want to retry the primary source first and fall back only afterward, place retry before fallback:

```java
return primaryRepository.findById(id)
        .retryWhen(transientReadRetry())
        .onErrorResume(PrimaryStoreUnavailableException.class,
                error -> replicaRepository.findById(id));
```

## 10. Logging and Error Observability

Handling errors in business terms does not mean sacrificing observability. When mapping or falling back, consider:

- Logging at a single appropriate boundary to avoid logging the same failure across every layer.
- Preserving the original exception as `cause` when changing exception types.
- Attaching correlation IDs, trace IDs, or safe business identifiers to logs.
- Recording metrics for conflicts, duplicates, fallbacks, and database unavailability.
- Never logging passwords, tokens, personal data, or full sensitive SQL parameters.
- Distinguishing fallback successes from primary-operation successes; both may warrant separate metrics.

You do not need to log every error inside `onErrorMap`. If a higher layer already logs the exception, logging again in the Service creates duplicate entries. Agree on which layer owns final error logging and where fallback metrics are emitted.

## 11. Testing onErrorMap and onErrorResume

`StepVerifier` from `reactor-test` lets you assert values, completion, and error signals from publishers. Test mapped errors, successful fallbacks, and failing fallbacks.

### 11.1. Verifying onErrorMap preserves failure and cause

```java
DuplicateKeyException persistenceError =
        new DuplicateKeyException("unique constraint violation");

when(repository.save(any(CustomerEntity.class)))
        .thenReturn(Mono.error(persistenceError));

StepVerifier.create(service.register("an@example.com", "An"))
        .expectErrorSatisfies(error -> {
            assertThat(error)
                    .isInstanceOf(EmailAlreadyRegisteredException.class);
            assertThat(error.getCause()).isSameAs(persistenceError);
        })
        .verify();
```

The test confirms the stream still terminates with an error and preserves the cause. In real test suites, tailor matchers and mocks to your project's repository types.

### 11.2. Verifying onErrorResume invokes the fallback

```java
when(primaryRepository.findById(10L))
        .thenReturn(Mono.error(new PrimaryStoreUnavailableException()));
when(replicaRepository.findById(10L))
        .thenReturn(Mono.just(customer));

StepVerifier.create(service.findFromPrimaryOrReplica(10L))
        .expectNext(customer)
        .verifyComplete();

verify(replicaRepository).findById(10L);
```

This test confirms a failure from the primary source triggers the fallback publisher and emits the expected result normally.

### 11.3. Verifying the fallback does not catch out-of-scope errors

If a fallback is intended only for `CacheAccessException`, validation errors or programming bugs must continue propagating. Write tests confirming that errors outside the predicate are not converted into default values.

### 11.4. Testing empty separately from errors

```java
when(repository.findById(10L)).thenReturn(Mono.empty());

StepVerifier.create(service.getRequiredCustomer(10L))
        .expectError(CustomerNotFoundException.class)
        .verify();
```

This test verifies that `switchIfEmpty` handles missing records. It is not a test for `onErrorResume`.

### 11.5. Testing transaction rollback

For multi-step write flows, integration tests against a real database are required to verify that errors escape the transaction and roll back data. Unit tests with mocked repositories cannot prove the transaction manager rolls back properly.

Cover cases such as:

- First write succeeds, second write fails, and the entire transaction rolls back.
- `onErrorMap` translates the exception while the error still escapes the transaction boundary.
- An `onErrorResume` inside a transaction converts an error to completion; confirm actual commit/rollback behavior to avoid masking failures.
- Fallbacks placed outside the transaction run only after the primary transaction finishes.

## 12. Common Mistakes

### Using onErrorResume solely to change the exception type

When no recovery path exists, `onErrorMap` expresses intent more clearly. Using `onErrorResume` with `Mono.error(new ...)` works technically, yet it is harder to read and obscures intent.

### Collapsing every error into one generic exception

Merging duplicate keys, timeouts, optimistic locking conflicts, and programming errors into one exception removes the ability to handle them distinctly in the business layer. Group only errors that share the same meaning.

### Returning default data when the database fails

An empty list or zero can be mistaken for real data. Only fall back when the product defines an explicit degraded state and clients can tell the difference.

### Confusing Mono.empty with onError

No matching record is an empty completion. Use `switchIfEmpty`; do not use `onErrorResume` for missing-record handling.

### Placing onErrorResume inside a transaction

Swallowing errors before a transaction boundary can stop the transaction from rolling back as intended. Let errors escape when rollback is needed; place fallbacks at the right outer boundary.

### Retrying after a successful fallback

If `onErrorResume` turns an error into a normal outcome, a downstream `retryWhen` never sees the error to trigger a retry. Place retry before fallback if you want to retry the primary source first.

### Dropping cause when creating a new exception

Omitting the cause loses diagnostic context. Pass the original exception into your application exception's constructor.

### Using overly broad fallbacks

`onErrorResume(Throwable.class, ...)` or always-true predicates can swallow programming errors, validation failures, and configuration bugs. Prefer specific classes or narrow predicates.

### Calling subscribe inside a fallback branch

Fallbacks must return a `Mono`/`Flux` so the outer pipeline controls results, errors, and cancellation. Never call `subscribe()` manually and return an empty publisher.

## 13. Decision Workflow for Error Handling

When an R2DBC operation emits an error, follow these steps:

1. Determine whether it is an error signal or an empty-completing publisher.
2. Classify the error by its actual exception type and root cause.
3. Determine the business meaning: conflict, invalid data, temporarily unavailable resource, or unexpected bug.
4. If you need to preserve failure while changing exception semantics, use `onErrorMap` and keep the cause.
5. If a business-approved recovery path exists, use `onErrorResume` with a specific class or predicate.
6. If no valid fallback exists, let the error propagate to the caller.
7. Handle missing-record cases with `switchIfEmpty`.
8. Check operator placement relative to `flatMap`, `retryWhen`, and transaction boundaries.
9. Emit appropriate metrics and logs without leaking sensitive data.
10. Test mapped errors, successful/failing fallbacks, empty publishers, and transaction rollbacks.

## 14. Quick Decision Table

| Scenario | Typically appropriate action |
|---|---|
| Unique constraint violated | `onErrorMap` to a business conflict/duplicate error |
| Entity modified by another request | `onErrorMap` to a conflict; require reload or merge |
| Database temporarily unreachable, replica available | Bounded retry, then `onErrorResume` to replica |
| Cache fails, database remains readable | `onErrorResume` to database |
| Repository returns `Mono.empty()` | `switchIfEmpty` |
| Optional auxiliary data with clear degraded state | `onErrorResume` to a degraded result |
| Validation error or programming bug | Propagate or translate to corresponding application error; never fall back arbitrarily |
| Write step in transaction fails and must roll back | Never swallow inside the transaction; let the error cross the boundary |
| No valid recovery path exists | Let the error signal propagate to higher-level error handling |

## 15. Checklist to Remember

- [ ] `onErrorMap` changes the exception type while keeping the error signal.
- [ ] New exceptions retain the original exception as `cause` when diagnostics are needed.
- [ ] `onErrorResume` is used only when a fallback publisher has clear business meaning.
- [ ] Fallbacks are scoped to specific exception classes or predicates.
- [ ] Never convert database errors to empty/default if callers could mistake them for real data.
- [ ] Distinguish `Mono.empty()` from `onError`; use `switchIfEmpty` for missing records.
- [ ] Place operators carefully to handle errors from upstream, fallbacks, and inner publishers as intended.
- [ ] Apply retries only to transient failures and operations safe to repeat.
- [ ] Never swallow errors inside a transaction when business rules require rollback.
- [ ] Bulk or custom SQL paths handle errors explicitly if they bypass Repository mechanisms.
- [ ] Logs and metrics reflect both final failures and fallback usage.
- [ ] Unit tests with `StepVerifier` and integration tests for transaction rollbacks are in place.

`onErrorMap` and `onErrorResume` help turn technical failures into meaningful business behavior, provided boundaries are chosen properly. Use `onErrorMap` to preserve failure under an application-appropriate exception; use `onErrorResume` when a truly acceptable alternative source or outcome exists; use `switchIfEmpty` for missing data. Above all, always verify where error handling sits relative to transaction boundaries so you never accidentally turn a transaction that should roll back into a normally completing publisher.
