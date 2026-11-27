# Representing Not-Found Data and Update Conflicts

In a Spring WebFlux application using Spring Data R2DBC, a read or write request can end in several ways: finding a record, finding no matching record, invalid data, business rule violations, or an update failing because another request modified the data earlier.

These outcomes must be clearly represented in the reactive pipeline and translated into appropriate HTTP statuses. `Mono.empty()` typically represents no result; it is not an error. An update conflict is a business/technical error with a different meaning, usually returned as HTTP 409 Conflict or 412 Precondition Failed if the request uses a version precondition such as `If-Match`.

With Spring Data R2DBC, optimistic locking via `@Version` detects when an entity has been modified since it was read. With direct SQL updates, the application must include the version in the `WHERE` predicate, increment the version in the same statement, and check the affected row count. WebFlux then turns these results into clear responses without calling `block()` or creating manual subscriptions.

## 1. Distinguishing Not-Found Data, Null Data, and Errors

An API must distinguish at least three scenarios:

1. **No matching row:** the query returns no rows. Repositories typically represent this with `Mono.empty()`.
2. **Row exists, but a column is SQL `NULL`:** the repository still returns an entity/DTO; the corresponding property may hold a Java `null` if the target type allows it.
3. **Query failure:** the publisher emits an error, such as a connection error, SQL error, conversion error, or constraint error.

Example:

~~~java
Mono<Customer> findById(Long id);
~~~

- If the customer exists, `Mono` emits one `Customer` and completes.
- If no customer exists, `Mono` completes empty.
- If the database encounters an error, `Mono` emits an error.

Do not convert all cases into `null`. In a reactive API, `Mono` does not emit a Java `null` value. `Mono.empty()` is a completion signal with no element; SQL `NULL` is data belonging to an existing row.

### 1.1. Mono.empty() Is Not an Exception

A repository method returning `Mono<Customer>` that does not find an ID usually does not emit an exception. Therefore, the following code does not handle the missing-data case:

~~~java
return customerRepository.findById(id)
        .onErrorResume(error -> Mono.just(fallbackCustomer));
~~~

`onErrorResume` only handles error signals. If the publisher completes empty, the fallback does not run.

To handle absence, use `switchIfEmpty`:

~~~java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
~~~

Or represent absence directly at the HTTP layer using `defaultIfEmpty`/`switchIfEmpty`, depending on the service contract.

### 1.2. An Empty Collection Is Usually a Successful Result

With `Flux<Customer>`, no matching rows usually means `Flux` completes without emitting any elements:

~~~java
Flux<Customer> customers = customerRepository.findAllByStatus("ARCHIVED");
~~~

A list API should usually return HTTP 200 OK with an empty array `[]`, because the list query succeeded and simply returned no items. Do not automatically return 404 Not Found just because a `Flux` emits no elements.

Conversely, an endpoint reading a specific resource such as `GET /customers/{id}` typically returns 404 if the ID does not exist or falls outside the caller's access scope.

## 2. Turning Mono.empty() into HTTP 404 in WebFlux

With annotated controllers, an explicit pattern is returning `Mono<ResponseEntity<T>>`. When the repository returns a result, return 200 OK; when the publisher is empty, return 404 Not Found.

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerRepository repository;

    public CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<CustomerResponse>> findById(
            @PathVariable Long id) {

        return repository.findById(id)
                .map(CustomerResponse::from)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
~~~

`defaultIfEmpty` executes when the publisher completes empty. If the repository emits an error, the error still routes to WebFlux error handling.

### 2.1. Using switchIfEmpty to Emit Another Response

Equivalently:

~~~java
@GetMapping("/{id}")
public Mono<ResponseEntity<CustomerResponse>> findById(
        @PathVariable Long id) {

    return customerService.findById(id)
            .map(CustomerResponse::from)
            .map(ResponseEntity::ok)
            .switchIfEmpty(Mono.just(ResponseEntity.notFound().build()));
}
~~~

`defaultIfEmpty` is suitable when the fallback value is ready upfront. `switchIfEmpty` is suitable when switching to another publisher, such as recording metrics, calling a fallback service, or building a response asynchronously.

### 2.2. Should the Service Emit Mono.empty() or Throw an Exception?

Either approach can be right depending on responsibility boundaries:

- If absence is a normal outcome of the use case, the service can keep `Mono.empty()` and let the controller decide the HTTP status.
- If the use case requires the resource to exist, the service can turn absence into `CustomerNotFoundException`.

Example service keeping absence semantics:

~~~java
public Mono<Customer> findById(Long id) {
    return customerRepository.findById(id);
}
~~~

Controller mapping to 404:

~~~java
return customerService.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
~~~

Example service treating a missing resource as a business error:

~~~java
public Mono<Customer> requireById(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
~~~

The controller can return `Mono<CustomerResponse>` and let `@RestControllerAdvice` map the exception to 404.

What matters is never having the same use case sometimes return empty and sometimes throw an exception depending on code paths without a clear contract.

## 3. Returning 404 via Exception and @RestControllerAdvice

If you want centralized error mapping, define a domain exception:

~~~java
public class CustomerNotFoundException extends RuntimeException {

    public CustomerNotFoundException(Long id) {
        super("Customer " + id + " was not found");
    }
}
~~~

Service:

~~~java
public Mono<Customer> requireById(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
~~~

Controller:

~~~java
@GetMapping("/{id}")
public Mono<CustomerResponse> findById(@PathVariable Long id) {
    return customerService.requireById(id)
            .map(CustomerResponse::from);
}
~~~

Global exception handler:

~~~java
public record ApiError(String code, String message) {
}

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(
            CustomerNotFoundException exception) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("CUSTOMER_NOT_FOUND", exception.getMessage()));
    }
}
~~~

This lets multiple controllers share the same rules. Never include stack traces, SQL, connection URLs, or internal database details in client responses.

### 3.1. Using ResponseStatusException When Appropriate

For a small endpoint, you can use `ResponseStatusException`:

~~~java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Customer not found")));
~~~

For applications with many use cases, dedicated domain exceptions are easier to govern because the domain does not depend directly on HTTP. Controller advice takes responsibility for translating domain/application errors into statuses.

### 3.2. Do Not Leak the Existence of Another Tenant's Data

In multi-tenant applications or systems with sensitive data, when an ID does not exist within the current tenant, the response should typically be 404. Do not reveal that the record exists under another tenant if doing so leaks data.

Repository queries should scope from the start:

~~~java
Mono<Customer> findByIdAndTenantId(Long id, Long tenantId);
~~~

Never load a record globally and check the tenant afterward in the controller.

## 4. Functional Endpoints Also Need Explicit Absence Representation

With WebFlux functional routing, handlers can convert `Mono.empty()` into `ServerResponse.notFound()`:

~~~java
public Mono<ServerResponse> getCustomer(ServerRequest request) {
    Long id = Long.valueOf(request.pathVariable("id"));

    return customerRepository.findById(id)
            .flatMap(customer -> ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(CustomerResponse.from(customer)))
            .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

Here:

- Customer exists: creates a 200 OK response with body.
- No customer: creates a 404 Not Found response.
- Repository error: the error signal propagates to `WebExceptionHandler` or the configured error-handling mechanism.

For a list endpoint:

~~~java
public Mono<ServerResponse> listCustomers(ServerRequest request) {
    return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(customerRepository.findAll(), Customer.class);
}
~~~

If there are no customers, the body is an empty collection per response serialization; the endpoint still returns 200.

## 5. HTTP Statuses for Update Conflicts

Not every write failure should return the same status. Common statuses include:

| HTTP Status | Meaning | Examples |
| --- | --- | --- |
| 400 Bad Request | Malformed request or invalid validation | Missing required field, version wrong type |
| 404 Not Found | Resource does not exist in caller's scope | ID missing in current tenant |
| 409 Conflict | Valid request conflicts with current state | Optimistic locking failure, unique business constraint |
| 412 Precondition Failed | Client-supplied HTTP precondition is no longer true | `If-Match` contains stale ETag |
| 422 Unprocessable Content | Syntactically valid data violates domain rules | Disallowed state transition, per API convention |
| 500 Internal Server Error | Unexpected server error | Bug or unclassified error |
| 503 Service Unavailable | Service temporarily unable to handle request | Database/downstream dependency unavailable, per ops policy |

Choose statuses consistently across the entire API. In particular, distinguish conflicts caused by domain state from HTTP preconditions sent by the client.

### 5.1. 409 Conflict

409 Conflict fits when an operation cannot complete because the current state of the resource conflicts with the request. For example, two users edit the same customer and one saves first.

The response can include a stable error code:

~~~json
{
  "code": "CUSTOMER_VERSION_CONFLICT",
  "message": "Customer was modified by another request",
  "resourceId": 42
}
~~~

Do not return the full current entity if the caller lacks permission to read those fields. You can provide the current version or instruct the client to reload the resource via a protected endpoint.

### 5.2. 412 Precondition Failed

If the API uses HTTP conditional requests like `If-Match`, the client asks the server to update only if the resource still has the ETag the client read. If the condition no longer holds, 412 Precondition Failed indicates the precondition failed.

Example:

~~~http
PUT /customers/42
If-Match: "7"
Content-Type: application/json
~~~

If the current version is already 8, the server does not execute the update for version 7 and returns 412. Database-level optimistic locking is still required to handle races occurring after the server checks the header.

## 6. Detecting Conflicts with @Version

Spring Data Relational supports optimistic locking via `@Version`. The entity holds a version property; when the entity is saved, the version identifies which snapshot the application read.

Entity:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;
    private String status;

    // Constructors, getters, and setters omitted.
}
~~~

Schema:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    name VARCHAR(160) NOT NULL,
    status VARCHAR(30) NOT NULL
);
~~~

When saving a new entity, Spring Data initializes `version` according to the rules of the version type. On update, the framework includes the current version in the write predicate and increments `version` upon success.

### 6.1. Scenario: Two Requests Editing the Same Entity

Suppose a customer has version 4:

| Step | Request A | Request B |
| ---: | --- | --- |
| 1 | Reads customer, version 4 | |
| 2 | | Reads customer, version 4 |
| 3 | Edits name and saves with version 4 | |
| 4 | Database updates successfully, version becomes 5 | |
| 5 | | Edits status and saves with version 4 |
| 6 | | No row matches version 4; optimistic locking fails |

Request B does not silently overwrite A's changes. Spring Data raises an optimistic locking error, typically a subclass of `OptimisticLockingFailureException`.

### 6.2. Service Updating an Entity

~~~java
public Mono<Customer> rename(Long id, String newName) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                customer.setName(newName);
                return customerRepository.save(customer);
            });
}
~~~

If two requests load the stale version simultaneously, only one save can succeed. The other emits an optimistic locking error. Let the error propagate to the HTTP handling layer or map it to an appropriate business exception.

### 6.3. Do Not Blindly Retry a Stale Entity

When optimistic locking fails, the entity in memory is already stale. Calling `save()` again on that same object with the old version will continue to fail.

To retry, you must:

1. Reload the fresh entity.
2. Re-check business conditions.
3. Reapply the command if still valid.
4. Save the new version.

Not every command can be reapplied automatically. If a user edited the same field as someone else, the application may need to return a conflict so the user can review and decide how to merge.

## 7. Translating Optimistic Locking Failures into HTTP 409

Handling can be centralized in `@RestControllerAdvice`:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OptimisticLockingFailureException.class)
    public ResponseEntity<ApiError> handleOptimisticLocking(
            OptimisticLockingFailureException exception) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "UPDATE_CONFLICT",
                        "The resource was modified by another request"));
    }
}
~~~

The returned message should explain that the client needs to reload the data or resolve the conflict. Do not expose SQL, table names, internal versions, or stack traces in the response.

### 7.1. Distinguishing Conflicts from Nonexistent Resources

An update using `@Version` can fail because the entity was modified or no longer exists. Depending on the execution path and data state, an optimistic locking exception may represent multiple concurrency causes.

If the API must precisely distinguish 404 and 409, define the contract and re-query within the tenant scope:

- Resource does not exist in current tenant: 404.
- Resource still exists, but version changed: 409.

Re-reading after a failed update only classifies the response; it does not make the prior update succeed. Avoid revealing the existence of resources belonging to other tenants.

### 7.2. Do Not Catch Every Error as 409

Only map optimistic locking errors or identified conflict errors to 409. Connection errors, timeouts, SQL syntax errors, or database unavailability are not optimistic conflicts and must be handled under their own error categories.

## 8. Direct SQL Needs Explicit Version Checks

`@Modifying @Query`, `DatabaseClient`, or `R2dbcEntityTemplate.update(Query, Update)` statements do not automatically apply entity `@Version` optimistic locking the way repository `save` does. When using direct updates, add the version to the predicate and increment the version in the same statement.

~~~java
@Modifying
@Query("""
       UPDATE customers
       SET name = :name,
           version = version + 1,
           last_modified_at = :modifiedAt
       WHERE id = :id
         AND tenant_id = :tenantId
         AND version = :expectedVersion
       """)
Mono<Integer> updateIfVersionMatches(
        @Param("id") Long id,
        @Param("tenantId") Long tenantId,
        @Param("name") String name,
        @Param("expectedVersion") Long expectedVersion,
        @Param("modifiedAt") Instant modifiedAt);
~~~

If the statement updates a single resource with a unique key:

- `rowsUpdated == 1`: update succeeded.
- `rowsUpdated == 0`: no row matched all of ID, tenant, and version; either the resource does not exist or the version is stale.

Incrementing `version` inside the statement guarantees a successful update changes the version, even if the new business value matches the old value.

### 8.1. Distinguishing 404 and 409 After a Conditional Update

The service can re-read the tenant-scoped resource when the update returns 0:

~~~java
public Mono<Customer> updateName(
        Long tenantId,
        Long id,
        Long expectedVersion,
        String newName) {

    return repository.updateIfVersionMatches(
                    id, tenantId, newName, expectedVersion, clock.instant())
            .flatMap(rows -> {
                if (rows == 1) {
                    return repository.findByIdAndTenantId(id, tenantId)
                            .switchIfEmpty(Mono.error(
                                    new CustomerNotFoundException(id)));
                }

                return repository.findByIdAndTenantId(id, tenantId)
                        .flatMap(current -> Mono.<Customer>error(
                                new CustomerConflictException(id)))
                        .switchIfEmpty(Mono.error(
                                new CustomerNotFoundException(id)));
            });
}
~~~

This is an application-level classification. State could change again between the update statement and the classifying read; the response reflects the state observed during the subsequent read. If the API does not need to distinguish them, it can return a generic conflict or an outcome that does not disclose resource existence.

### 8.2. Conditional Update with R2dbcEntityTemplate

You can include the version in the predicate and increment it using appropriate SQL/template updates:

~~~java
Query condition = query(
        where("id").is(id)
                .and("tenantId").is(tenantId)
                .and("version").is(expectedVersion));

Update update = Update.update("name", newName)
        .set("version", expectedVersion + 1)
        .set("lastModifiedAt", clock.instant());

return template.update(Customer.class)
        .matching(condition)
        .apply(update);
~~~

The example uses the expected version read from the request. If you need to increment the version atomically based on the current database value, native SQL `version = version + 1` expresses that more directly. Do not omit the version predicate when using template updates and assume `@Version` applies automatically.

## 9. Using ETag and If-Match for Conditional Updates

HTTP provides conditional requests so clients avoid overwriting data changed since their last read.

### 9.1. Returning ETag When Reading a Resource

If the version is an integer, it can be represented as an ETag:

~~~java
@GetMapping("/{id}")
public Mono<ResponseEntity<CustomerResponse>> getCustomer(
        @PathVariable Long id) {

    return customerService.requireById(id)
            .map(customer -> ResponseEntity.ok()
                    .eTag("\"" + customer.getVersion() + "\"")
                    .body(CustomerResponse.from(customer)));
}
~~~

The client receives the header:

~~~http
ETag: "4"
~~~

The ETag must reflect a version representing the resource content. If the response includes fields depending on data outside the entity's version, ensure the version increments when that data changes or construct an appropriate composite ETag.

### 9.2. Accepting If-Match on Update

~~~java
@PutMapping("/{id}")
public Mono<ResponseEntity<CustomerResponse>> updateCustomer(
        @PathVariable Long id,
        @RequestHeader(HttpHeaders.IF_MATCH) String ifMatch,
        @RequestBody UpdateCustomerRequest request) {

    Long expectedVersion = etagParser.parseVersion(ifMatch);

    return customerService.updateIfVersionMatches(
                    id, expectedVersion, request)
            .map(updated -> ResponseEntity.ok()
                    .eTag("\"" + updated.getVersion() + "\"")
                    .body(CustomerResponse.from(updated)));
}
~~~

If `If-Match` does not match the current version, the service can throw `PreconditionFailedException`; the exception handler converts it to 412.

### 9.3. Why Database-Level Optimistic Locking Is Still Required?

Suppose the server reads version 4 and compares it against `If-Match: "4"`. Immediately after the comparison, another request updates the entity to version 5. If the server then performs an update without a version predicate, it can still overwrite the newer data.

Therefore, checking the header is only an application-layer HTTP condition. The final update statement still needs `WHERE version = :expectedVersion` or entity `@Version` to catch races at the database.

### 9.4. Distinguishing 409 and 412

- Use 409 when a conflict arises from business state or optimistic locking where the API does not represent it via an HTTP precondition.
- Use 412 when the request includes `If-Match`/precondition and that condition no longer holds.
- You may require clients to always send `If-Match`; if the header is missing, the API can return 428 Precondition Required per contract.

## 10. Handling Reactive Errors with the Right Operators

Reactor operators play distinct roles:

| Operator | Handles |
| --- | --- |
| `switchIfEmpty` | Runs an alternative publisher when the source completes empty |
| `defaultIfEmpty` | Emits a default value when the source completes empty |
| `onErrorMap` | Transforms one exception into another |
| `onErrorResume` | Replaces an error with an alternative publisher |
| `doOnError` | Observes/logs an error without turning it into success |
| `retryWhen` | Resubscribes to the publisher when an error satisfies retry criteria |

### 10.1. Mapping Exceptions at the Service Boundary

~~~java
public Mono<Customer> updateName(Long id, String name) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                customer.setName(name);
                return customerRepository.save(customer);
            })
            .onErrorMap(
                    OptimisticLockingFailureException.class,
                    error -> new CustomerConflictException(id, error));
}
~~~

After converting technical exceptions into application/domain exceptions, `@RestControllerAdvice` can map `CustomerConflictException` to 409.

### 10.2. Never Use onErrorResume to Turn All Errors into Empty

Avoid:

~~~java
return customerRepository.findById(id)
        .onErrorResume(error -> Mono.empty());
~~~

This turns database failures into a "not found" result. Callers cannot distinguish an absent resource from an unavailable database, invalid SQL, or connection reset.

Only handle specific exceptions:

~~~java
return customerRepository.findById(id)
        .onErrorMap(
                DataAccessResourceFailureException.class,
                error -> new CustomerStoreUnavailableException(error));
~~~

There is no need to convert every exception if the global handler already has proper rules. The goal is preserving the meaning of the error.

### 10.3. doOnError Does Not Handle Errors

~~~java
return customerRepository.save(customer)
        .doOnError(error -> log.error("Customer update failed", error));
~~~

`doOnError` only observes errors; the error continues downstream. To convert it into a conflict, use `onErrorMap` or let the exception handler process it.

### 10.4. Do Not Subscribe Manually in Controller/Service

Avoid:

~~~java
customerRepository.save(customer).subscribe();
return Mono.just(ResponseEntity.ok().build());
~~~

The response may be sent before the database finishes. The caller does not receive write errors and cannot know whether the update succeeded.

Return the publisher to WebFlux instead:

~~~java
return customerRepository.save(customer)
        .map(ResponseEntity::ok);
~~~

WebFlux manages the subscription and writes the response based on the reactive result.

## 11. Standardizing Error Responses

An API can use a unified error structure:

~~~java
public record ApiError(
        String code,
        String message,
        String resourceId
) {
}
~~~

Advice:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            CustomerNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "CUSTOMER_NOT_FOUND",
                        "Customer was not found",
                        exception.getResourceId()));
    }

    @ExceptionHandler(CustomerConflictException.class)
    public ResponseEntity<ApiError> conflict(
            CustomerConflictException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "CUSTOMER_UPDATE_CONFLICT",
                        "Customer changed before this update could be applied",
                        exception.getResourceId()));
    }

    @ExceptionHandler(PreconditionFailedException.class)
    public ResponseEntity<ApiError> preconditionFailed(
            PreconditionFailedException exception) {
        return ResponseEntity.status(HttpStatus.PRECONDITION_FAILED)
                .body(new ApiError(
                        "ETAG_MISMATCH",
                        "Reload the resource before updating it",
                        exception.getResourceId()));
    }
}
~~~

Exception classes and getters in the example must be defined according to your project structure. `ProblemDetail` in Spring Framework 6+ can be used if the application standardizes responses around Problem Details.

### 11.1. Mapping Duplicate Key Errors

When a unique constraint is violated, Spring may translate the driver error into `DuplicateKeyException`. This can represent a business conflict, such as an email already in use.

~~~java
@ExceptionHandler(DuplicateKeyException.class)
public ResponseEntity<ApiError> duplicateKey(DuplicateKeyException exception) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError(
                    "DUPLICATE_RESOURCE",
                    "A resource with the same unique value already exists",
                    null));
}
~~~

Do not map every `DataIntegrityViolationException` to 409 without classification. Foreign key, not-null, check constraint, and other data violations may require different responses depending on the API contract. Never include internal constraint names or sensitive values in the response body.

## 12. Transactions and Update Conflicts

An update operation may involve reading an entity, checking rules, saving the entity, and writing an audit record. If these operations must be atomic, place them inside a reactive transaction:

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String newStatus) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                customer.changeStatus(newStatus);
                return customerRepository.save(customer);
            });
}
~~~

`@Transactional` ensures database operations participate in the same transaction when they use the proper R2DBC transaction manager and `ConnectionFactory`. It does not automatically prevent lost updates without `@Version`, conditional updates, or appropriate locking.

### 12.1. Do Not Blindly Retry After a Conflict

An optimistic locking failure means the data changed compared to the version the request used. Retrying with the same stale entity will not resolve the conflict.

An API should usually return 409/412 so the client can:

1. Reload the fresh resource.
2. Display current changes if needed.
3. Merge data or ask the user to confirm.
4. Submit a new update with the new version.

Only retry automatically if the command can be safely reapplied after reading the fresh version and business rules still hold.

### 12.2. Distinguishing Conflict Errors from Ambiguous Post-Commit Outcomes

An optimistic locking failure is an identifiable conflict. A timeout or connection reset during commit can leave the outcome unknown. Do not map all of them to 409.

For writes with side effects, use an idempotency key so callers can resend the same intent without creating duplicate data. When the commit state is unknown, the response may be a transient error per the API contract; retries must reuse the same idempotency key.

## 13. End-to-End Example: GET and PUT with Version

Response DTO:

~~~java
public record CustomerResponse(
        Long id,
        String name,
        String status,
        Long version
) {
    static CustomerResponse from(Customer customer) {
        return new CustomerResponse(
                customer.getId(),
                customer.getName(),
                customer.getStatus(),
                customer.getVersion());
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<CustomerResponse>> get(@PathVariable Long id) {
        return service.findById(id)
                .map(customer -> ResponseEntity.ok()
                        .eTag("\"" + customer.getVersion() + "\"")
                        .body(CustomerResponse.from(customer)))
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @PutMapping("/{id}")
    public Mono<ResponseEntity<CustomerResponse>> update(
            @PathVariable Long id,
            @RequestBody UpdateCustomerRequest request) {

        return service.update(id, request)
                .map(customer -> ResponseEntity.ok()
                        .eTag("\"" + customer.getVersion() + "\"")
                        .body(CustomerResponse.from(customer)));
    }
}
~~~

Service:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> findById(Long id) {
        return repository.findById(id);
    }

    @Transactional
    public Mono<Customer> update(Long id, UpdateCustomerRequest request) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
                .flatMap(customer -> {
                    customer.setName(request.name());
                    customer.setStatus(request.status());
                    return repository.save(customer);
                })
                .onErrorMap(
                        OptimisticLockingFailureException.class,
                        error -> new CustomerConflictException(id, error));
    }
}
~~~

The example illustrates optimistic locking via `@Version`. If the endpoint requires `If-Match`, parse the ETag and compare/pass the expected version into the update operation; merely returning `ETag` on GET without checking it on PUT does not provide conditional updates.

## 14. Testing Absence and Conflict

Combine service unit tests with integration tests using a real R2DBC database or Testcontainers. Unit tests verify publisher transformation logic; integration tests verify mapping, optimistic locking, and actual database exceptions.

### 14.1. Service Returning Empty When Not Found

~~~java
StepVerifier.create(customerService.findById(999L))
        .verifyComplete();
~~~

This test verifies the service preserves empty semantics. If the service uses `requireById`, verify the exception:

~~~java
StepVerifier.create(customerService.requireById(999L))
        .expectError(CustomerNotFoundException.class)
        .verify();
~~~

### 14.2. Controller Returning 404

With `WebTestClient`:

~~~java
webTestClient.get()
        .uri("/customers/999")
        .exchange()
        .expectStatus().isNotFound();
~~~

Also assert the error body if the API uses `@RestControllerAdvice`.

### 14.3. Empty List Returning 200

~~~java
webTestClient.get()
        .uri("/customers?status=UNKNOWN")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("[]");
~~~

This distinguishes a collection with zero items from a missing individual resource.

### 14.4. Optimistic Locking with Two Entities Sharing a Version

Integration test:

1. Create a customer.
2. Read the entity twice to obtain two objects with the same version.
3. Modify and save the first object; verify success.
4. Modify and save the second object; verify optimistic locking failure.
5. Re-read from the database and verify only the first save's changes persisted.

~~~java
Mono<Void> testConflict(Long id) {
    return customerRepository.findById(id)
            .zipWith(customerRepository.findById(id))
            .flatMap(tuple -> {
                Customer first = tuple.getT1();
                Customer stale = tuple.getT2();

                first.setName("First update");
                stale.setName("Stale update");

                return customerRepository.save(first)
                        .then(customerRepository.save(stale))
                        .then();
            });
}
~~~

The actual test must assert that the publisher terminates with an optimistic locking exception. The example shows how to obtain two entity snapshots; do not run both `save()` calls in parallel if the goal is deterministic win/lose ordering.

### 14.5. Testing Conditional SQL Update

Prepare version 3:

- Updating with `expectedVersion` 3 must affect 1 row and advance version to 4.
- A subsequent update with `expectedVersion` 3 must affect 0 rows.
- Updating with an ID belonging to another tenant must modify 0 rows.
- Verify status and audit columns after each attempt.

### 14.6. Testing HTTP Conflict

Have two requests read the same ETag, then send two PUTs:

1. Both read version 4.
2. Request A updates with version 4 and succeeds, returning ETag version 5.
3. Request B submits version 4 and receives 409 or 412 per the API contract.
4. The database retains A's changes.

## 15. Common Mistakes When Representing Absence and Conflict

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| GET finds no data but returns 200 empty body | Controller did not turn `Mono.empty()` into 404 | Use `Mono<ResponseEntity<T>>` and `defaultIfEmpty` |
| Database fails but API returns 404 | Using `onErrorResume(error -> Mono.empty())` | Map only specific errors; preserve infrastructure errors |
| Empty list returns 404 | Confusing empty `Flux` with missing single resource | Return 200 with an empty collection |
| Updates silently overwrite each other | Entity lacks `@Version` or SQL lacks version predicate | Use optimistic locking or conditional update |
| Conflict returns 500 | Optimistic locking exception not mapped | Use `@RestControllerAdvice` returning 409/412 |
| Every database error becomes 409 | Exception handler is too broad | Map only identified conflict errors |
| Repeated save retries keep failing | Retrying with the same stale entity/version | Reload fresh entity and re-evaluate command |
| Direct SQL bypasses version | Assuming `@Version` applies to all DML statements | Add expected version to `WHERE` and increment version |
| 404 leaks data of another tenant | Querying globally then checking tenant later | Query by ID and tenant directly in repository |
| `If-Match` checked yet updates still lost | Comparing header before write without DB version predicate | Use `@Version` or conditional SQL |
| Timeout treated as conflict | Confusing ambiguous commit with optimistic locking | Classify errors; use idempotency for writes with unknown outcome |
| Controller responds before write finishes | Calling `subscribe()` independently | Return publisher so WebFlux manages subscription |

## 16. Workflow for Designing Safe Read and Update APIs

1. Determine whether the endpoint returns a single resource or a collection.
2. For single resources, decide whether absence is an empty result or a domain exception.
3. Map absence to HTTP 404; empty collections typically return 200 with an empty list.
4. Distinguish SQL `NULL` in an existing row from `Mono.empty()`.
5. Choose a concurrent update detection mechanism: `@Version`, conditional SQL, or appropriate locking.
6. Specify whether conflicts map to 409 or 412 when using HTTP preconditions.
7. For direct DML, include both tenant predicates and version predicates in the statement.
8. Map specific exceptions via `@RestControllerAdvice`.
9. Never swallow database errors or blindly retry stale entities.
10. Test with `WebTestClient`, `StepVerifier`, and two independent snapshots/transactions.

## 17. Processing Flow Diagram

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Reactive service / repository]
    B --> C{How does the publisher end?}
    C -->|Has entity| D[Return resource]
    C -->|Mono.empty| E[404 for single resource]
    C -->|Empty collection| F[200 with []]
    C -->|Validation/domain error| G[Map status per error]
    C -->|Optimistic locking failure| H[409 Conflict]
    C -->|If-Match no longer valid| I[412 Precondition Failed]
    C -->|Infrastructure error| J[500/503 per policy]
    D --> K[WebFlux writes response]
    E --> K
    F --> K
    G --> K
    H --> K
    I --> K
    J --> K
~~~

## 18. Conclusion

In Spring Data R2DBC and WebFlux, `Mono.empty()` means no elements were found, not a database error. For single-resource endpoints, convert empty to 404; for collection endpoints, an empty list typically remains 200. SQL `NULL` is a column value inside an existing row and must be handled separately.

For concurrent updates, use `@Version` so Spring Data detects stale entities, or include the expected version in direct SQL predicates and increment it in the same statement. Map optimistic locking conflicts to 409; when requests use `If-Match` and the ETag no longer matches, 412 usually expresses the precondition failure more clearly. Checking headers at the HTTP layer does not replace database version predicates because races can still occur between check and write.

Finally, preserve meaningful error signals, use `switchIfEmpty` for absence, `@RestControllerAdvice` for centralized error mapping, and let WebFlux manage subscriptions. Test both HTTP responses and database concurrency behavior to ensure one request never silently overwrites another's changes.
