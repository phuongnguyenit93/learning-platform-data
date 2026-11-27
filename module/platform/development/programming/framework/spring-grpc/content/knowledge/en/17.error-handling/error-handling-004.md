# Mapping domain errors to gRPC status

**Chapter:** Error handling  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers, generated Java code, and unary or streaming RPCs. This lesson focuses on converting **domain/application business errors into a gRPC status** at the server boundary, so clients receive stable error codes without the business layer depending on gRPC.

## 1. Why is a mapping layer needed?

Suppose an ordering application has business errors: customer does not exist, order was already created, order state does not allow cancellation, or inventory is insufficient. These are domain concepts. When exposing the API over gRPC, the server must convert them into standard statuses such as `NOT_FOUND`, `ALREADY_EXISTS`, or `FAILED_PRECONDITION`.

The domain should not throw `StatusRuntimeException` everywhere. Doing so couples the domain to the transport library and makes reuse difficult when the same business logic is called from REST, a message consumer, or a batch job.

A sensible boundary:

```text
gRPC request
    |
    v
Generated service / gRPC adapter
    |
    v
Application service
    |
    v
Domain logic
    |
    +-- CustomerNotFound
    +-- DuplicateOrder
    +-- OrderStateConflict
    +-- InventoryUnavailable
    |
    v
DomainStatusMapper
    |
    +-- NOT_FOUND
    +-- ALREADY_EXISTS
    +-- FAILED_PRECONDITION
    +-- RESOURCE_EXHAUSTED
    |
    v
responseObserver.onError(Status...)
```

The mapper translates business meaning into the **API error contract**. Clients rely on status codes to decide behavior; the server can change storage or domain structure without forcing clients to parse Java exception names.

## 2. Map by semantics, not mechanically by exception name

A domain exception should express what happened in the business domain. A gRPC status must express how the client should interpret the RPC outcome.

| Domain error | Typically appropriate gRPC status | Reason |
| --- | --- | --- |
| Customer/order not found | `NOT_FOUND` | The requested resource does not exist |
| Input violates formatting rules | `INVALID_ARGUMENT` | The client needs to fix the request |
| Creating an already-existing resource | `ALREADY_EXISTS` | Operation conflicts with an existing resource |
| Cancelling a shipped order or invalid state action | `FAILED_PRECONDITION` | Current state does not allow the operation |
| Optimistic locking conflict on update | `ABORTED` | May need to rerun the entire transaction/workflow |
| Quota or business limit exceeded | `RESOURCE_EXHAUSTED` | Request exceeds resource budget |
| Dependency temporarily unavailable | `UNAVAILABLE` | Potentially recoverable; retries need backoff and idempotency |
| Authenticated caller lacks permission | `PERMISSION_DENIED` | Identity is valid but not authorized |
| Unexpected internal error | `INTERNAL` | Do not disclose implementation details |

Some choices require contextual consideration:

- **`ALREADY_EXISTS` vs. `ABORTED`:** creating an order ID that already exists is usually `ALREADY_EXISTS`; a version conflict during an update can be `ABORTED` because the client needs to re-read and rerun the transaction.
- **`FAILED_PRECONDITION` vs. `INVALID_ARGUMENT`:** the current order state disallowing cancellation is usually `FAILED_PRECONDITION`; a malformed request field is usually `INVALID_ARGUMENT`.
- **`UNAVAILABLE` vs. `INTERNAL`:** a dependent service temporarily losing connectivity can be `UNAVAILABLE`; a programming bug or broken invariant is usually `INTERNAL`.
- **`UNAUTHENTICATED` vs. `PERMISSION_DENIED`:** missing/invalid credentials is `UNAUTHENTICATED`; authenticated without sufficient rights is `PERMISSION_DENIED`. Authentication errors are typically handled at the security/interceptor boundary.

Do not map every exception to `INTERNAL`, and do not use `INVALID_ARGUMENT` for every error so the client will "fix it itself". Status is part of the API contract and should accurately reflect an actionable cause.

## 3. Keeping the domain independent of gRPC

A simple approach is to use dedicated domain error codes without importing `io.grpc.Status` in the domain:

```java
public enum DomainErrorCode {
    CUSTOMER_NOT_FOUND,
    DUPLICATE_ORDER,
    ORDER_STATE_CONFLICT,
    OPTIMISTIC_LOCK_CONFLICT,
    QUOTA_EXCEEDED,
    DEPENDENCY_UNAVAILABLE,
    ACCESS_DENIED
}

public class DomainException extends RuntimeException {
    private final DomainErrorCode code;

    public DomainException(DomainErrorCode code) {
        super(code.name());
        this.code = code;
    }

    public DomainErrorCode code() {
        return code;
    }
}
```

The domain service throws errors semantically:

```java
if (customer == null) {
    throw new DomainException(DomainErrorCode.CUSTOMER_NOT_FOUND);
}
if (orderAlreadyExists(command.orderId())) {
    throw new DomainException(DomainErrorCode.DUPLICATE_ORDER);
}
if (!order.canBeCancelled()) {
    throw new DomainException(DomainErrorCode.ORDER_STATE_CONFLICT);
}
```

The example uses a single `DomainException` with an enum code to clarify the mechanism. Larger projects may use specialized exception classes (`CustomerNotFoundException`, `DuplicateOrderException`, etc.) instead of an enum. Either way, the domain still does not need to know gRPC status codes.

Do not put `Status.Code` directly into `DomainErrorCode`: doing so couples the domain layer to the transport again and makes the mapper meaningless.

## 4. Building DomainStatusMapper at the adapter layer

The mapper takes a domain error and returns a `StatusRuntimeException` for the adapter to send via `responseObserver.onError()`.

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Component;

@Component
public class DomainStatusMapper {

    public StatusRuntimeException map(DomainException error) {
        Status status = switch (error.code()) {
            case CUSTOMER_NOT_FOUND ->
                    Status.NOT_FOUND.withDescription("Customer not found");
            case DUPLICATE_ORDER ->
                    Status.ALREADY_EXISTS.withDescription("Order already exists");
            case ORDER_STATE_CONFLICT ->
                    Status.FAILED_PRECONDITION
                            .withDescription("Order state does not allow this action");
            case OPTIMISTIC_LOCK_CONFLICT ->
                    Status.ABORTED.withDescription("Order changed; reload and retry");
            case QUOTA_EXCEEDED ->
                    Status.RESOURCE_EXHAUSTED.withDescription("Quota exceeded");
            case DEPENDENCY_UNAVAILABLE ->
                    Status.UNAVAILABLE.withDescription("A required service is unavailable");
            case ACCESS_DENIED ->
                    Status.PERMISSION_DENIED.withDescription("Operation is not permitted");
        };
        return status.asRuntimeException();
    }
}
```

Because the switch covers the enum, adding a new `DomainErrorCode` lets the compiler catch that the mapper has not handled it yet. This is the benefit of having an explicit catalog of domain errors.

The descriptions in the example are controlled public strings. Do not arbitrarily take `error.getMessage()` and return it to the client: the message may contain SQL, table names, personal data, internal paths, or information unsuitable for exposure.

If detailed error codes are needed for the client, you can add an `error-code` trailer or use protobuf error details per the API contract. Do not turn the description into an implicit protocol that clients must parse.

## 5. Applying the mapper in a Spring gRPC service

The service adapter calls the application service, converts domain exceptions into gRPC statuses, and terminates the RPC exactly once:

```java
@GrpcService
public class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderApplicationService applicationService;
    private final DomainStatusMapper statusMapper;

    public OrderGrpcService(
            OrderApplicationService applicationService,
            DomainStatusMapper statusMapper) {
        this.applicationService = applicationService;
        this.statusMapper = statusMapper;
    }

    @Override
    public void cancelOrder(
            CancelOrderRequest request,
            StreamObserver<Order> responseObserver) {
        try {
            Order order = applicationService.cancel(request.getOrderId());
            responseObserver.onNext(toProto(order));
            responseObserver.onCompleted();
        } catch (DomainException domainError) {
            responseObserver.onError(statusMapper.map(domainError));
        } catch (RuntimeException unexpected) {
            log.error("Unexpected error while cancelling order", unexpected);
            responseObserver.onError(
                    Status.INTERNAL
                            .withDescription("Internal server error")
                            .asRuntimeException());
        }
    }
}
```

The mapper is invoked at the gRPC boundary, where the application knows how domain errors should be exposed over the API. Domain/application services can still be called from REST or jobs without having to handle gRPC exceptions.

### Do not write a response before knowing the outcome

With unary RPCs, only call `onNext(response)` after the application service finishes successfully. If `onNext` is called first and an error is detected later followed by `onError`, the client may observe a response message before the terminal status; that usually makes the contract confusing.

With server streaming or client streaming, the terminal rule is similar: when a domain error is detected, convert it to a status and call `onError` once; do not continue sending messages or calling `onCompleted` afterward.

## 6. Mapping errors in streaming callbacks

In streaming RPCs, a domain exception can occur while processing a message in `onNext()` or while aggregating/committing in `onCompleted()`. Maintain terminal state so two terminal callbacks are never sent:

```java
return new StreamObserver<OrderItem>() {
    private boolean terminated;

    @Override
    public void onNext(OrderItem item) {
        if (terminated) return;
        try {
            applicationService.accept(item);
        } catch (DomainException domainError) {
            terminated = true;
            responseObserver.onError(statusMapper.map(domainError));
        }
    }

    @Override
    public void onError(Throwable inboundError) {
        terminated = true;
        // Client cancelled/inbound error: clean up resources; do not send a receipt.
    }

    @Override
    public void onCompleted() {
        if (terminated) return;
        try {
            OrderSummary summary = applicationService.finish();
            terminated = true;
            responseObserver.onNext(toProto(summary));
            responseObserver.onCompleted();
        } catch (DomainException domainError) {
            terminated = true;
            responseObserver.onError(statusMapper.map(domainError));
        }
    }
};
```

This illustration assumes callbacks are dispatched sequentially within one RPC and processing does not run concurrently across multiple threads. If there are async tasks, cancellation handlers, or multiple workers, atomic/synchronized terminal state and idempotent cleanup are required. Do not call the response observer concurrently from multiple threads.

An inbound `onError(Throwable)` is not a domain error intentionally created by the server; it indicates the client/transport ended the request stream with an error. Do not map all such errors to `INTERNAL`.

## 7. Errors that should not go through DomainStatusMapper

Not every exception on the server is a domain error:

| Cause | Appropriate handling |
| --- | --- |
| Protobuf request missing required field or invalid format | Validate at adapter; return `INVALID_ARGUMENT` |
| Domain cannot find the order | Domain exception → `NOT_FOUND` |
| Order state does not allow cancellation | Domain exception → `FAILED_PRECONDITION` |
| Missing/invalid credentials | Security layer/interceptor → `UNAUTHENTICATED` |
| Caller lacks permission | Authorization boundary → `PERMISSION_DENIED` |
| RPC deadline/cancellation | Preserve gRPC `DEADLINE_EXCEEDED`/`CANCELLED` semantics; clean up |
| Unexpected database error | Log internally, appropriate status such as `INTERNAL`; only use `UNAVAILABLE` when a dependency is truly temporarily unavailable |
| Bug or broken invariant | `INTERNAL`, do not disguise as an input error |

If a lower layer already produced a gRPC status exception, the adapter should preserve that status instead of turning it into a new domain error. Similarly, do not turn `CancellationException` or deadline errors into `INTERNAL` just because they appear as Java exceptions.

## 8. Testing mapping standalone and across RPCs

The mapper is pure logic, so it can be unit tested without starting a server:

```java
import io.grpc.Status;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DomainStatusMapperTest {

    private final DomainStatusMapper mapper = new DomainStatusMapper();

    @Test
    void customerNotFoundMapsToNotFound() {
        var grpcError = mapper.map(
                new DomainException(DomainErrorCode.CUSTOMER_NOT_FOUND));

        assertEquals(Status.Code.NOT_FOUND,
                grpcError.getStatus().getCode());
    }

    @Test
    void orderStateConflictMapsToFailedPrecondition() {
        var grpcError = mapper.map(
                new DomainException(DomainErrorCode.ORDER_STATE_CONFLICT));

        assertEquals(Status.Code.FAILED_PRECONDITION,
                grpcError.getStatus().getCode());
    }

    @Test
    void duplicateOrderMapsToAlreadyExists() {
        var grpcError = mapper.map(
                new DomainException(DomainErrorCode.DUPLICATE_ORDER));

        assertEquals(Status.Code.ALREADY_EXISTS,
                grpcError.getStatus().getCode());
    }
}
```

Unit tests verify the mapping table. Integration tests via in-process gRPC should also verify that the client actually receives the right status:

- Calling cancel on a non-existent order returns `NOT_FOUND` to the client.
- Calling cancel on a delivered order returns `FAILED_PRECONDITION` to the client.
- Creating an order with an existing ID returns `ALREADY_EXISTS` to the client.
- Unexpected errors do not leak exception messages or stack traces.
- With streaming, an error mid-stream terminates the response once without a success receipt.

Tests should not rely on verbatim description wording if it is not part of a stable contract. Check the status code first; only assert on the description when the API intentionally commits to that content.

## 9. Operational and retry rules

Status mapping also directly affects retries:

- `INVALID_ARGUMENT`, `NOT_FOUND`, `PERMISSION_DENIED` should usually not be retried with the same unchanged request.
- `ALREADY_EXISTS` requires looking up the resource or treating the create operation as having reached the desired state under an idempotency contract.
- `FAILED_PRECONDITION` requires changing the state or preconditions before retrying.
- `ABORTED` may require re-reading data and rerunning the entire transaction.
- `RESOURCE_EXHAUSTED` requires shedding load or waiting per quota, not aggressive retries.
- `UNAVAILABLE` can be retried with exponential backoff and jitter if the operation is safe.
- `DEADLINE_EXCEEDED` does not prove the server did not execute the operation; for write operations, an idempotency key or status lookup API is needed.

Log domain errors with a correlation ID, operation, and status code; do not log tokens or sensitive payloads. Monitor the frequency of each status to spot validation issues, business conflicts, quota exhaustion, and dependency outages. If status mapping changes, treat it as an API contract change and evaluate the impact on clients.

## 10. Self-practice

1. An order has already been delivered, yet the client requests cancellation. Why is `FAILED_PRECONDITION` more appropriate than `INVALID_ARGUMENT`?
2. One order creation fails with a duplicate ID and one update hits an optimistic locking conflict. When should you choose `ALREADY_EXISTS`, and when `ABORTED`?
3. Design an additional `DomainErrorCode.PAYMENT_DECLINED`. Choose a gRPC status and a safe description so the client can take action.
4. Why should `DomainException` not contain or directly depend on `io.grpc.Status.Code`?
5. A client receives `UNAVAILABLE` after an order write operation. What must be ensured before retrying to avoid creating a duplicate order?

**Remember:** The domain states **what went wrong in the business logic**; the gRPC adapter converts that error into a **status code that clients can understand consistently**. Keep the domain independent of transport, centralize semantic mapping, avoid exposing internal details, and test statuses at both the mapper and the RPC boundary.
