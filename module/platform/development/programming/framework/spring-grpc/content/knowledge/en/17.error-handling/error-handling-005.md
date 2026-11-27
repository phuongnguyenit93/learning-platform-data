# Do not return INTERNAL for every exception

**Chapter:** Error handling  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers, generated Java code, and unary or streaming RPCs. This lesson focuses on **classifying exceptions at the server boundary and semantically mapping them to gRPC statuses**, so clients can fix requests, re-authenticate, wait, or retry properly.

## 1. Why shouldn't every exception become INTERNAL?

`INTERNAL` means the server encountered an unexpected internal error or cannot disclose further details. If every exception is converted to `INTERNAL`, clients cannot distinguish:

- A request with invalid data that needs fixing.
- A resource that does not exist.
- An unauthenticated or unauthorized caller.
- A current business state that does not allow the operation.
- A concurrency conflict that can be resolved by re-reading and starting a new transaction.
- A dependent service that is temporarily unavailable.
- An actual programming bug or internal outage.

Status is part of the **API contract**. Accurate mapping lets clients handle errors purposefully; inaccurate mapping can cause clients to retry permanent errors, ignore recoverable conflicts, or display system failures for an invalid request.

The processing flow should have clear boundaries:

```text
Request / application operation
          |
          v
Domain + infrastructure exceptions
          |
          v
gRPC exception mapper
          |
          +-- Known client / domain / security / dependency errors
          |        -> specific status
          |
          +-- Existing Status exception
          |        -> preserve status and trailers
          |
          +-- Unexpected error
                   -> internal log + safe INTERNAL
          |
          v
responseObserver.onError(...)
```

The goal is not to eliminate `INTERNAL`. The goal is to use it only for genuinely unclassified errors, rather than as the default answer for every situation.

## 2. Mapping table by error meaning

| Cause | Typically appropriate gRPC status | Client action |
| --- | --- | --- |
| Request missing field or invalid format | `INVALID_ARGUMENT` | Fix request; do not retry as-is |
| Resource does not exist | `NOT_FOUND` | Notify or choose another resource |
| Creating an already-existing resource | `ALREADY_EXISTS` | Look up resource or handle duplicate |
| Current state does not allow operation | `FAILED_PRECONDITION` | Change business conditions first |
| Optimistic locking/transaction conflict | `ABORTED` | Re-read and retry the entire transaction |
| Missing valid credentials | `UNAUTHENTICATED` | Sign in or refresh credentials |
| Authenticated but lacks permission | `PERMISSION_DENIED` | Stop operation or request permission |
| Quota/allocated resources exceeded | `RESOURCE_EXHAUSTED` | Shed load or wait per quota |
| Dependency temporarily unavailable | `UNAVAILABLE` | Retry with backoff if operation is safe |
| RPC exceeded deadline | `DEADLINE_EXCEEDED` | Verify outcome if operation has side effects |
| Caller actively cancelled | `CANCELLED` | Stop producer and clean up |
| Unexpected error or broken invariant | `INTERNAL` | Investigate on the server side |

Do not map based solely on exception class names. For example:

- `IllegalArgumentException` may be a programming bug, not necessarily a bad request. Only validation errors identified at the request boundary should become `INVALID_ARGUMENT`.
- `DataIntegrityViolationException` may be a known unique key violation, or it may be a different constraint failure. Only convert to `ALREADY_EXISTS` when you know for sure it is a resource conflict per contract.
- `DataAccessException` does not always mean the database service is temporarily unavailable. Only use `UNAVAILABLE` when the cause is truly a temporary, recoverable dependency failure.
- A `TimeoutException` from a downstream task does not automatically mean the entire RPC exceeded its deadline. Distinguish local timeouts from the gRPC call's deadline.

## 3. Creating meaningful exception types at the application layer

The domain/application should state what happened without depending on `io.grpc.Status`. For example:

```java
public class RequestValidationException extends RuntimeException {
    public RequestValidationException(String message) {
        super(message);
    }
}

public class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(String customerId) {
        super("Customer not found: " + customerId);
    }
}

public class DuplicateOrderException extends RuntimeException {
    public DuplicateOrderException(String orderId) {
        super("Order already exists: " + orderId);
    }
}

public class OrderStateConflictException extends RuntimeException {
    public OrderStateConflictException(String message) {
        super(message);
    }
}

public class DependencyUnavailableException extends RuntimeException {
    public DependencyUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class QuotaExceededException extends RuntimeException {
    public QuotaExceededException(String message) {
        super(message);
    }
}
```

In a real project, existing specialized exceptions can be reused instead of creating new ones. What matters is that the application layer emits **semantic** errors rather than throwing `StatusRuntimeException` in every business method.

Application service example:

```java
public Order createOrder(CreateOrderCommand command) {
    if (command.customerId() == null || command.customerId().isBlank()) {
        throw new RequestValidationException("customerId is required");
    }
    if (!customerRepository.existsById(command.customerId())) {
        throw new CustomerNotFoundException(command.customerId());
    }
    if (orderRepository.existsByExternalId(command.externalId())) {
        throw new DuplicateOrderException(command.externalId());
    }
    return orderRepository.save(Order.create(command));
}
```

The application service does not need to know whether the call came from gRPC or REST. The adapter converts exceptions to the appropriate protocol.

## 4. Building a mapper with clear classification

The mapper should process in order:

1. If the exception already contains a gRPC status, preserve its code, description, and trailers.
2. If it is a known request/domain/security/dependency error, map it to the appropriate status.
3. If unrecognized, log internally and return `INTERNAL` with a generic description.

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import io.grpc.Status.Code;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Component;

@Component
public class GrpcExceptionMapper {

    private static final Logger log =
            LoggerFactory.getLogger(GrpcExceptionMapper.class);

    public StatusRuntimeException toStatusException(Throwable error) {
        Throwable existingGrpcError = findGrpcStatus(error);
        if (existingGrpcError != null) {
            Status existing = Status.fromThrowable(existingGrpcError);
            Metadata trailers =
                    Status.trailersFromThrowable(existingGrpcError);
            // Do not change a gRPC status already intentionally created by a lower layer.
            return trailers == null
                    ? existing.asRuntimeException()
                    : existing.asRuntimeException(trailers);
        }

        if (hasCause(error, RequestValidationException.class)) {
            return Status.INVALID_ARGUMENT
                    .withDescription("Invalid request")
                    .asRuntimeException();
        }
        if (hasCause(error, CustomerNotFoundException.class)) {
            return Status.NOT_FOUND
                    .withDescription("Customer not found")
                    .asRuntimeException();
        }
        if (hasCause(error, DuplicateOrderException.class)) {
            return Status.ALREADY_EXISTS
                    .withDescription("Order already exists")
                    .asRuntimeException();
        }
        if (hasCause(error, OrderStateConflictException.class)) {
            return Status.FAILED_PRECONDITION
                    .withDescription("Order state does not allow this operation")
                    .asRuntimeException();
        }
        if (hasCause(error, OptimisticLockingFailureException.class)) {
            return Status.ABORTED
                    .withDescription("Data has changed; reload and retry")
                    .asRuntimeException();
        }
        if (hasCause(error, AuthenticationException.class)) {
            return Status.UNAUTHENTICATED
                    .withDescription("Valid authentication is required")
                    .asRuntimeException();
        }
        if (hasCause(error, AccessDeniedException.class)) {
            return Status.PERMISSION_DENIED
                    .withDescription("Not permitted to perform this operation")
                    .asRuntimeException();
        }
        if (hasCause(error, QuotaExceededException.class)) {
            return Status.RESOURCE_EXHAUSTED
                    .withDescription("Quota exceeded")
                    .asRuntimeException();
        }
        if (hasCause(error, DependencyUnavailableException.class)) {
            return Status.UNAVAILABLE
                    .withDescription("Dependent service is temporarily unavailable")
                    .asRuntimeException();
        }

        // Only unclassified errors fall into the INTERNAL branch.
        log.error("Unmapped exception at gRPC boundary", error);
        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }

    private Throwable findGrpcStatus(Throwable error) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (current instanceof StatusRuntimeException
                    || current instanceof StatusException) {
                return current;
            }
        }
        return null;
    }

    private boolean hasCause(
            Throwable error, Class<? extends Throwable> expectedType) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

The example preserves an existing status exception before checking domain exceptions. This avoids accidentally turning an `UNAVAILABLE` or `PERMISSION_DENIED` error created by a lower layer into `INTERNAL`.

The descriptions returned to clients are controlled generic strings. The mapper does not put `error.getMessage()` into the response, because the message may contain sensitive IDs, SQL, table names, internal paths, or implementation details.

### Notes when extending the mapper

- Checking order matters if an exception can inherit from multiple exception types.
- Only add a mapping when the semantics and expected client action are clear.
- Do not map every `IllegalArgumentException` to `INVALID_ARGUMENT`; it can be caused by a server bug.
- Do not map every `DataAccessException` to `UNAVAILABLE`; distinguish transient connection errors, conflicts, constraints, and data errors.
- Do not catch `Throwable` to mask serious JVM errors. The mapper accepts `Throwable` to handle wrappers at the boundary, while the adapter should catch exception types the application can handle.

## 5. Invoking the mapper at the Spring gRPC boundary

With unary RPCs, the adapter converts exceptions from the application service into terminal gRPC statuses:

```java
@GrpcService
public class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderApplicationService applicationService;
    private final GrpcExceptionMapper exceptionMapper;

    public OrderGrpcService(
            OrderApplicationService applicationService,
            GrpcExceptionMapper exceptionMapper) {
        this.applicationService = applicationService;
        this.exceptionMapper = exceptionMapper;
    }

    @Override
    public void createOrder(
            CreateOrderRequest request,
            StreamObserver<OrderResponse> responseObserver) {
        try {
            Order order = applicationService.createOrder(
                    toCommand(request));
            responseObserver.onNext(toProto(order));
            responseObserver.onCompleted();
        } catch (Exception error) {
            responseObserver.onError(
                    exceptionMapper.toStatusException(error));
        }
    }
}
```

The adapter does not need to guess each error in every method. Centralized mapping keeps statuses consistent across RPCs. However, only catch `Exception` at boundaries where the application has a clear mapping strategy; do not catch `Throwable` and continue handling JVM errors.

### Streaming callback

With client streaming, errors can occur in `onNext()` or when finalizing in `onCompleted()`. When an error is detected, the server calls `onError` exactly once and sends no success receipt:

```java
return new StreamObserver<OrderItem>() {
    private boolean terminated;

    @Override
    public void onNext(OrderItem item) {
        if (terminated) return;
        try {
            applicationService.accept(item);
        } catch (Exception error) {
            terminated = true;
            responseObserver.onError(
                    exceptionMapper.toStatusException(error));
        }
    }

    @Override
    public void onError(Throwable inboundError) {
        // Client/transport terminated inbound stream: clean up, do not return a receipt.
        terminated = true;
    }

    @Override
    public void onCompleted() {
        if (terminated) return;
        try {
            OrderSummary summary = applicationService.finish();
            terminated = true;
            responseObserver.onNext(toProto(summary));
            responseObserver.onCompleted();
        } catch (Exception error) {
            terminated = true;
            responseObserver.onError(
                    exceptionMapper.toStatusException(error));
        }
    }
};
```

This illustration assumes callbacks are dispatched sequentially. If there are asynchronous workers, cancellation handlers, or multiple threads, atomic/synchronized terminal state and idempotent cleanup are required. Inbound `onError(Throwable)` is an error/cancellation from the client or transport; do not convert it to `INTERNAL` and try sending a status back on an already-terminated call.

## 6. Distinguishing domain, security, dependency, and programming errors

| Error source | Example | Handling at gRPC boundary |
| --- | --- | --- |
| Request validation | Missing customer ID, invalid format | `INVALID_ARGUMENT` |
| Domain | Customer not found, order already exists | `NOT_FOUND`, `ALREADY_EXISTS` |
| Business state | Cannot cancel delivered order | `FAILED_PRECONDITION` |
| Concurrent update | Optimistic lock conflict | `ABORTED` |
| Authentication | Missing/expired token | `UNAUTHENTICATED` |
| Authorization | Caller lacks permission | `PERMISSION_DENIED` |
| Quota | Tenant exceeded limit | `RESOURCE_EXHAUSTED` |
| Transient dependency | Payment service unavailable | `UNAVAILABLE` if recoverable |
| Bug/broken invariant | Unexpected null, programming error | `INTERNAL` |

Authentication/authorization is typically handled earlier in a security interceptor or filter. There is no need to wait for a domain service to throw an exception to decide `UNAUTHENTICATED` or `PERMISSION_DENIED`.

A database error also needs classification by root cause. For instance, a known unique constraint can become `ALREADY_EXISTS`; optimistic locking becomes `ABORTED`; a temporarily unreachable database connection can become `UNAVAILABLE`. A `DataAccessException` with an unknown cause should be investigated and safely fall back, not automatically treated as transient.

## 7. Retries must follow status and idempotency

Specific statuses help clients choose actions:

- `INVALID_ARGUMENT`, `NOT_FOUND`, `PERMISSION_DENIED`: usually do not retry the same unchanged request.
- `ALREADY_EXISTS`: look up the resource; if the creation operation has an idempotency key, check whether the desired outcome already exists.
- `FAILED_PRECONDITION`: change the state or preconditions before retrying.
- `ABORTED`: re-read data and rerun the transaction/workflow.
- `RESOURCE_EXHAUSTED`: back off, wait for quota, or split batches.
- `UNAVAILABLE`: can retry with exponential backoff and jitter if the operation is safe.
- `DEADLINE_EXCEEDED`: does not prove the server did not execute the operation; check status or use an idempotency key before resending.
- `INTERNAL`: investigate; do not retry indefinitely like a transient network glitch.

Do not let the mapper decide retries. The mapper only describes the error via status; retry policy belongs to the client or workflow layer and must consider deadline, retry budget, idempotency, and side effects already applied.

## 8. Testing the mapper and RPC behavior

The mapper can be unit tested by asserting status codes:

```java
import io.grpc.Status;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GrpcExceptionMapperTest {

    private final GrpcExceptionMapper mapper = new GrpcExceptionMapper();

    @Test
    void validationErrorIsNotInternal() {
        var status = mapper.toStatusException(
                new RequestValidationException("missing field"));

        assertEquals(Status.Code.INVALID_ARGUMENT,
                status.getStatus().getCode());
    }

    @Test
    void dependencyFailureIsUnavailable() {
        var status = mapper.toStatusException(
                new DependencyUnavailableException("payment", null));

        assertEquals(Status.Code.UNAVAILABLE,
                status.getStatus().getCode());
    }

    @Test
    void unexpectedFailureFallsBackToInternal() {
        var status = mapper.toStatusException(
                new IllegalStateException("unexpected bug"));

        assertEquals(Status.Code.INTERNAL,
                status.getStatus().getCode());
        assertEquals("Internal server error",
                status.getStatus().getDescription());
    }
}
```

Tests should also be added for:

1. Domain not found → `NOT_FOUND`.
2. Duplicate resource → `ALREADY_EXISTS`.
3. Optimistic locking conflict → `ABORTED`.
4. Authentication and authorization → two distinct statuses.
5. A `StatusRuntimeException` wrapped in the cause chain keeps its code and trailers.
6. Unexpected errors return a generic description without leaking internal messages.
7. Over in-process gRPC, the client receives the exact status created by the mapper.
8. With streaming, a mid-stream error terminates once, with no success response after the error.

Unit testing the mapper does not replace integration testing. Also test across the transport boundary to confirm that statuses and trailers actually reach the client.

## 9. Self-practice

1. A request has an empty customer ID. Why should you return `INVALID_ARGUMENT` instead of letting a `NullPointerException` fall into `INTERNAL`?
2. The database reports an optimistic locking conflict when two clients update the same order. Why is `ABORTED` usually more appropriate than `UNAVAILABLE`?
3. A unique constraint error occurs. What additional context is needed before mapping it to `ALREADY_EXISTS`?
4. A payment service times out, but the outer gRPC deadline has not yet expired. Why should you not necessarily return `DEADLINE_EXCEEDED`?
5. Design a test proving that an existing `StatusRuntimeException` from a lower layer is not converted into `INTERNAL` by the mapper.

**Remember:** Do not return `INTERNAL` for every exception. Classify known errors semantically by request, domain, security, concurrency, and dependency; preserve existing gRPC statuses; only fall back to `INTERNAL` for unexpected errors while logging details on the server and returning a safe message to the client.
