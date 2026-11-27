# Mapping Not Found to NOT_FOUND

## 1. Why map not found explicitly?

In **SPRING_GRPC**, clients call RPCs to read, update, or delete resources such as accounts, orders, customers, or devices. When an identifier is valid but the record does not exist, the server needs to return a consistent outcome so the client knows the requested resource is absent.

At the persistence layer, this situation typically surfaces as an empty Optional, a query returning zero rows, or a specific repository/ORM exception. At the gRPC layer, the appropriate representation is usually the **NOT_FOUND** status. Clients can rely on this status to display "not found", skip deleted resources, or handle missing parent/child relationships.

Do not map every exception to NOT_FOUND. Database errors, connection failures, mapping bugs, authorization failures, and invalid business states all have different meanings. Misclassifying them causes clients to take the wrong action and masks real failures.

This lesson focuses on:

- Detecting missing resources in repositories and application services.
- Using strongly typed business exceptions.
- Mapping exceptions to gRPC NOT_FOUND at the transport boundary.
- Distinguishing NOT_FOUND from PERMISSION_DENIED, FAILED_PRECONDITION, and INVALID_ARGUMENT.
- Handling nested resources, updates/deletes, and race conditions.
- Preventing leaks of resource or internal data.
- Testing status codes through gRPC integration tests.

## 2. What does NOT_FOUND express?

NOT_FOUND means the resource identified in the request does not exist according to the API contract at the time of processing.

Examples:

- GetOrder receives a valid order_id, but no corresponding order exists.
- GetDevice receives a nonexistent device_id.
- GetOrderLine receives a line_id that does not belong to the specified order_id.
- A parent resource does not exist in a nested resource path.
- A lookup API by external reference finds no matching record.

Example error response:

```text
gRPC status: NOT_FOUND
description: Order not found
```

NOT_FOUND does not mean the request has invalid syntax. If order_id is empty or malformed, that is usually INVALID_ARGUMENT. If the order exists but cannot be canceled because it is already SHIPPED, that is usually FAILED_PRECONDITION.

Define the resource and existence conditions according to the contract. "No results" from a secondary query does not always mean the primary resource is missing; it may simply be a valid empty list.

## 3. Distinguishing persistence errors from domain not found

Repositories should represent absence via an explicit return type when absence is a normal expected outcome.

Spring Data JPA example:

```java
public interface OrderRepository
        extends JpaRepository<Order, String> {
}
```

The application service converts the repository result into a domain outcome:

```java
@Service
@RequiredArgsConstructor
public class OrderApplicationService {
    private final OrderRepository orders;

    @Transactional(readOnly = true)
    public OrderResult getOrder(String orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() ->
                new ResourceNotFoundException(
                    "Order", orderId
                )
            );

        return OrderResult.from(order);
    }
}
```

findById returns an Optional. When the Optional is empty, the application service throws the domain exception ResourceNotFoundException. This exception expresses a domain condition that the transport layer can map, without forcing the application service to depend on gRPC Status.

Do not call Optional.get() and let NoSuchElementException leak out. NoSuchElementException does not describe the resource type, provides no useful context, and is easily misclassified as a programming bug.

## 4. Defining strongly typed business exceptions

An exception can carry the resource type and internal identifier for logging:

```java
public class ResourceNotFoundException
        extends RuntimeException {

    private final String resourceType;
    private final String resourceId;

    public ResourceNotFoundException(
            String resourceType,
            String resourceId) {
        super(resourceType + " not found");
        this.resourceType = resourceType;
        this.resourceId = resourceId;
    }

    public String getResourceType() {
        return resourceType;
    }

    public String getResourceId() {
        return resourceId;
    }
}
```

The application layer can reuse this exception across multiple adapters such as gRPC, REST, or message consumers. Do not embed gRPC StatusRuntimeException in the domain model, as that couples business logic to the transport.

The resource ID in the exception is strictly for internal logging/diagnostics. Never put sensitive identifiers or tenant information into the status description returned to the client by default.

If the codebase has distinct not-found types, you can create specialized exceptions such as OrderNotFoundException or AccountNotFoundException. Choose one consistent pattern so the exception mapper does not have to parse message strings.

## 5. Mapping exceptions at the gRPC boundary

gRPC Java represents errors with Status and RuntimeException. The adapter can catch domain exceptions and call observer.onError:

```java
@Override
public void getOrder(
        GetOrderRequest request,
        StreamObserver<GetOrderReply> observer) {
    try {
        OrderResult result =
            orderApplicationService.getOrder(
                request.getOrderId()
            );

        GetOrderReply reply = GetOrderReply.newBuilder()
            .setOrderId(result.orderId())
            .setStatus(result.status())
            .build();

        observer.onNext(reply);
        observer.onCompleted();

    } catch (ResourceNotFoundException ex) {
        observer.onError(
            Status.NOT_FOUND
                .withDescription("Order not found")
                .asRuntimeException()
        );
    }
}
```

Emit a success response only when the application service returns normally. If the resource does not exist, the adapter emits a single terminal error via onError and must not call onNext/onCompleted afterward.

Do not repeat the same try/catch across dozens of service implementations. In systems with many RPCs, create a shared exception mapper or base adapter so every service maps domain exceptions consistently. How the mapper is registered depends on the Spring gRPC starter and the project's gRPC Java integration; whether via an interceptor or a helper, mapping belongs at the transport boundary.

## 6. Centralized exception mapping

A centralized mapper prevents services from returning inconsistent statuses for the same error:

```java
@Component
public class GrpcExceptionMapper {

    public StatusRuntimeException toStatus(Throwable error) {
        if (error instanceof ResourceNotFoundException) {
            return Status.NOT_FOUND
                .withDescription("Resource not found")
                .asRuntimeException();
        }

        if (error instanceof InvalidCommandException) {
            return Status.INVALID_ARGUMENT
                .withDescription("Invalid request")
                .asRuntimeException();
        }

        if (error instanceof BusinessPreconditionException) {
            return Status.FAILED_PRECONDITION
                .withDescription("Operation is not allowed")
                .asRuntimeException();
        }

        return Status.INTERNAL
            .withDescription("Unexpected server error")
            .asRuntimeException();
    }
}
```

A real mapper can inspect the cause chain to recognize Spring-translated exceptions, but it should not search for keywords like "not found" in message strings. Classifying by exception type is far more reliable.

Do not map every DataAccessException, SQLException, or RuntimeException to NOT_FOUND. Unavailable databases, timeouts, connection pool exhaustion, and SQL syntax errors are not missing resources; unexpected errors should be logged and mapped according to server policy, typically INTERNAL or UNAVAILABLE depending on the cause.

## 7. Distinguishing NOT_FOUND from related statuses

| Situation | Commonly Used Status | Reason |
| --- | --- | --- |
| Valid ID, but resource does not exist | NOT_FOUND | Resource was not found |
| Missing, empty, or malformed ID | INVALID_ARGUMENT | Invalid request |
| Resource exists, but user lacks permission | PERMISSION_DENIED | Resource exists, but caller is not authorized |
| Resource exists, but state forbids operation | FAILED_PRECONDITION | State must change first |
| Concurrent update leaves version stale | ABORTED | Re-read and retry the workflow |
| Database/service temporarily unavailable | UNAVAILABLE | Recoverable infrastructure error |
| Query exceeded deadline | DEADLINE_EXCEEDED | Time budget exhausted |

Do not pick NOT_FOUND merely because you want the client to stop retrying. The status must reflect the true cause and the published contract.

Some systems intentionally return NOT_FOUND when the caller is not allowed to know whether a resource exists. That is an existence-hiding policy; it must be applied consistently and decided at the authorization boundary, not by repositories arbitrarily rewriting errors.

## 8. Validating identifiers before querying

Distinguish invalid identifiers from valid identifiers that match no record:

```java
public OrderResult getOrder(String orderId) {
    if (orderId == null || orderId.isBlank()) {
        throw new InvalidCommandException(
            "order_id is required"
        );
    }

    if (!orderId.matches("[A-Za-z0-9-]{1,64}")) {
        throw new InvalidCommandException(
            "order_id has invalid format"
        );
    }

    Order order = orders.findById(orderId)
        .orElseThrow(() ->
            new ResourceNotFoundException("Order", orderId)
        );

    return OrderResult.from(order);
}
```

The regex format is only an example; real validation must match the identifier type in the contract. If using UUIDs, parse into a UUID before querying. Do not query the database with malformed input and return NOT_FOUND, as that makes it hard for clients to tell input errors apart from missing resources.

For Proto3 validation, remember scalar strings default to the empty string; field presence may not be represented when using implicit presence. The application layer still needs to validate values and semantics.

## 9. Nested resources and parent/child relationships

An RPC may take both a parent ID and a child ID, such as GetOrderLine(order_id, line_id). Several cases exist:

- The order does not exist.
- The order exists, but the line does not exist.
- The line exists, but belongs to a different order.
- The caller is not authorized to access the order or the line.

If the contract treats line as a child resource of order, both "line does not exist" and "line does not belong to this order" can usually return NOT_FOUND so cross-resource relationships are not leaked.

Example scoped query:

```java
Optional<OrderLine> line =
    orderLines.findByOrderIdAndId(orderId, lineId);

OrderLine found = line.orElseThrow(() ->
    new ResourceNotFoundException("OrderLine", lineId)
);
```

Scoped queries prevent fetching a line by ID and accidentally returning data from another order. However, if you need to distinguish missing parent from missing child, follow the contract and security policy.

For multi-tenant resources, every query must be scoped by tenant/owner. Never look up by global ID first and check permissions afterward after already leaking data into logs or response mapping.

## 10. Mapping for get, update, and delete

### Get

Use findById/Optional. If the resource is absent, throw a domain not-found exception and return NOT_FOUND. If present, map to the response.

### Update

If the API updates an existing resource, a missing resource typically returns NOT_FOUND. If the API is an upsert, absence may trigger the creation branch and not be an error. The contract must state the semantics clearly.

Inside a transaction, read the entity, check permissions and preconditions, update, and commit. If the row disappears due to a concurrent delete between read and write, the persistence layer may report stale state/optimistic lock. Do not automatically treat every optimistic lock exception as NOT_FOUND; it may be a concurrent update requiring ABORTED. Only classify resource disappearance as NOT_FOUND with clear evidence and policy.

### Delete

Delete has two common contracts:

- **Strict delete:** if the resource does not exist, return NOT_FOUND.
- **Idempotent delete:** if the resource does not exist, still treat the operation as complete and return success or an empty response.

Pick one semantics and stay consistent. Do not rely on the default behavior of deleteById without checking the Spring Data version/repository contract; some delete APIs silently succeed when the ID does not exist.

If strict delete is required, look up the resource inside a transaction and delete it, or use a conditional DELETE statement and check the affected row count. For concurrent deletes, handle the race according to the documented semantics.

## 11. Do not turn database outages into NOT_FOUND

Some flawed code catches broad exceptions and returns NOT_FOUND:

```java
try {
    return repository.findById(id)
        .orElseThrow(() -> new ResourceNotFoundException("Order", id));
} catch (RuntimeException ex) {
    throw new ResourceNotFoundException("Order", id);
}
```

This hides connection failures, timeouts, SQL errors, mapping bugs, and programming errors. The client will assume the resource does not exist and may purge caches or drop data.

Only throw ResourceNotFoundException when the query completes normally and the result is genuinely absent. If the database fails to respond, preserve the persistence error so the exception mapper classifies it as an infrastructure failure. Logs must retain the full cause chain.

## 12. Security and information disclosure

NOT_FOUND can reveal whether an ID exists. For multi-tenant APIs or sensitive resources, policy must define:

- Is the caller authenticated?
- Is the caller authorized to read this resource type?
- Should "does not exist" be distinguished from "exists but belongs to another tenant"?
- Should NOT_FOUND be returned for out-of-scope resources as well to prevent enumeration?

If policy requires hiding existence, the authorization layer can return the same NOT_FOUND response for missing resources and out-of-scope resources. However, internal logs still need to distinguish the real cause under controlled access.

Do not include sensitive resource IDs, tenant IDs, SQL, or stack traces in status descriptions. Use a correlation ID to link logs with the RPC. Authentication/authorization must execute before replaying cached results or returning data.

## 13. Testing NOT_FOUND mapping

Verify both application behavior and gRPC wire statuses:

| Test | What to verify |
| --- | --- |
| Get existing resource | Returns normal response |
| Get valid ID with no row | Client receives NOT_FOUND |
| Empty/malformed ID | Client receives INVALID_ARGUMENT |
| Resource exists without permission | PERMISSION_DENIED or defined hide-existence policy |
| Parent/child mismatch | NOT_FOUND per nested-resource contract |
| Update missing resource | NOT_FOUND if update is strict |
| Delete missing resource | Matches strict/idempotent delete semantics |
| Database connection failure | Not mapped to NOT_FOUND |
| Optimistic lock conflict | ABORTED, not NOT_FOUND by default |
| Status description | Contains no SQL/stack trace/secrets |

Example integration test with a blocking stub:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> blockingStub.getOrder(
        GetOrderRequest.newBuilder()
            .setOrderId("missing-order")
            .build()
    )
);

assertEquals(
    Status.Code.NOT_FOUND,
    Status.fromThrowable(error).getCode()
);
```

Testing through a real gRPC server verifies that the exception mapper, adapter, and transport work together to produce the expected status code. Unit tests calling the mapper directly do not prove the server actually sends the right status.

## 14. Review checklist

- Repositories represent absence using Optional or explicit outcomes.
- Application services throw typed domain exceptions when a resource truly does not exist.
- Optional.get()/NoSuchElementException is not used as a contract.
- Exception mapper at the gRPC boundary maps NOT_FOUND accurately.
- Not all DataAccessException/RuntimeException instances are mapped to NOT_FOUND.
- INVALID_ARGUMENT is used for malformed identifiers/requests.
- PERMISSION_DENIED and hide-existence policies are clearly defined.
- FAILED_PRECONDITION is used when a resource exists but its state is unsuitable.
- ABORTED is used for concurrency conflicts per contract.
- Nested resource queries are scoped by parent and tenant.
- Get/update/delete have explicit not-found semantics; strict and idempotent delete are not mixed.
- No success response is emitted before the application service finishes.
- Status descriptions do not leak internal data.
- gRPC integration tests cover missing resources and easily confused errors.

In **SPRING_GRPC**, NOT_FOUND is how you express that a resource does not exist under the RPC contract. Detect absence in repositories, convert it to a typed domain exception in the application service, and map it centrally at the gRPC boundary. Clearly distinguish invalid requests, missing permissions, invalid business states, concurrency conflicts, and database outages so clients can react properly without leaking resource information.
