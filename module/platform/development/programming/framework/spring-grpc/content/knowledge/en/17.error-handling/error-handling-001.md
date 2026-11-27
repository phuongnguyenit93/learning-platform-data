# StatusRuntimeException and StatusException

**Chapter:** Error handling  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and unary or streaming RPCs. This lesson focuses on the two gRPC Java exception types used to represent a gRPC status: `StatusRuntimeException` and `StatusException`.

## 1. Two exception types representing the same RPC error type

When the server needs to reject a request, gRPC does not send a Java exception over the network. The server terminates the RPC with a **gRPC status** consisting of a status code, a description, and optional metadata trailers. In Java, the library provides two exception classes to carry that status:

| Characteristic | `StatusRuntimeException` | `StatusException` |
| --- | --- | --- |
| Java type | Extends `RuntimeException` | Extends `Exception` |
| Category | Unchecked exception | Checked exception |
| `throws` declaration | Not required to declare | Must be caught or declared on methods that can throw it |
| Created from `Status` | `status.asRuntimeException()` | `status.asException()` |
| Passed via gRPC callback | Can be passed to `responseObserver.onError(...)` | Can be passed to `responseObserver.onError(...)` |
| Meaning on the wire | Sends gRPC status and trailers | Sends gRPC status and trailers |

**The main difference lies in how Java requires exception handling, not in the gRPC protocol.** If both carry the same status code and trailers, the client receives the same RPC error meaning. Using a checked or unchecked exception does not produce two different status types on the network.

For example, both ways below create an `INVALID_ARGUMENT` error:

```java
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;

Status invalid = Status.INVALID_ARGUMENT
        .withDescription("customer_id is required");

StatusRuntimeException unchecked = invalid.asRuntimeException();
StatusException checked = invalid.asException();
```

Do not choose the exception type arbitrarily or assume that `StatusException` is a "lighter" error. Choose based on the Java API boundary and keep handling consistent.

## 2. Creating exceptions from Status

`io.grpc.Status` is the object that describes the RPC result. Constants such as `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAUTHENTICATED`, and `INTERNAL` provide standard codes. You can add a description and trailers before converting it to an exception.

### Using StatusRuntimeException

In an asynchronous Spring gRPC handler, the common approach is to call `responseObserver.onError(...)`:

```java
responseObserver.onError(
        Status.NOT_FOUND
                .withDescription("Order not found")
                .asRuntimeException());
```

`asRuntimeException()` creates a `StatusRuntimeException`. Because this is an unchecked exception, the code does not need to declare `throws`. However, in a callback API, **passing the exception to `onError`** is usually clearer than throwing the exception out of the callback.

### Using StatusException

`StatusException` is suitable when a helper or business layer wants to represent an error with a checked exception:

```java
private void validateCustomerId(String customerId)
        throws StatusException {
    if (customerId == null || customerId.isBlank()) {
        throw Status.INVALID_ARGUMENT
                .withDescription("customer_id is required")
                .asException();
    }
}
```

At the gRPC boundary, catch the exception and convert it into a terminal callback:

```java
@Override
public void findCustomer(
        FindCustomerRequest request,
        StreamObserver<Customer> responseObserver) {
    try {
        validateCustomerId(request.getCustomerId());
        Customer customer = service.find(request.getCustomerId());
        responseObserver.onNext(customer);
        responseObserver.onCompleted();
    } catch (StatusException statusError) {
        responseObserver.onError(statusError);
    }
}
```

Generated service methods usually do not declare `throws StatusException`; therefore you cannot arbitrarily throw a checked exception out of the override. Catch it at the adapter and forward it via `responseObserver.onError`. With `StatusRuntimeException`, you can also pass it directly to the callback.

## 3. Passing trailers with status

Trailers are metadata sent when the RPC finishes. They can carry machine-readable error codes or non-sensitive diagnostic information. For example:

```java
import io.grpc.Metadata;
import io.grpc.Status;

private static final Metadata.Key<String> ERROR_CODE =
        Metadata.Key.of(
                "error-code",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata trailers = new Metadata();
trailers.put(ERROR_CODE, "CUSTOMER_NOT_ACTIVE");

responseObserver.onError(
        Status.FAILED_PRECONDITION
                .withDescription("Customer cannot perform this operation yet")
                .asRuntimeException(trailers));
```

If an internal API uses a checked exception, you can create the same status and trailers with `asException(trailers)`. When received on the client, trailers can be retrieved using `Status.trailersFromThrowable(error)`.

Rules when using trailers:

- Metadata key names must follow gRPC rules; binary keys have the `-bin` suffix and use a binary marshaller.
- Only include information needed by the client for handling or to support operations.
- Do not send access tokens, passwords, personal data, or stack traces in trailers.
- Avoid putting large payloads into trailers; metadata has size limits depending on the transport/proxy.
- Error descriptions for clients should be stable and safe; internal details belong in server-side logs with a correlation ID.

## 4. Spring gRPC server: mapping business errors to status

Do not let every error turn into `INTERNAL`, nor return raw internal exceptions to the client. The gRPC adapter must distinguish input errors, missing resources, and system failures.

```java
@GrpcService
public class CustomerGrpcService
        extends CustomerServiceGrpc.CustomerServiceImplBase {

    private final CustomerApplicationService service;

    public CustomerGrpcService(CustomerApplicationService service) {
        this.service = service;
    }

    @Override
    public void findCustomer(
            FindCustomerRequest request,
            StreamObserver<Customer> responseObserver) {
        try {
            if (request.getCustomerId().isBlank()) {
                responseObserver.onError(
                        Status.INVALID_ARGUMENT
                                .withDescription("customer_id is required")
                                .asRuntimeException());
                return;
            }

            Customer customer = service.find(request.getCustomerId());
            if (customer == null) {
                responseObserver.onError(
                        Status.NOT_FOUND
                                .withDescription("Customer not found")
                                .asRuntimeException());
                return;
            }

            responseObserver.onNext(customer);
            responseObserver.onCompleted();
        } catch (CustomerRuleException ruleError) {
            responseObserver.onError(
                    Status.FAILED_PRECONDITION
                            .withDescription("Customer operation is not allowed")
                            .asRuntimeException());
        } catch (RuntimeException unexpected) {
            // Log internal details on the server; do not send the exception externally.
            log.error("Unexpected error in findCustomer", unexpected);
            responseObserver.onError(
                    Status.INTERNAL
                            .withDescription("Internal server error")
                            .asRuntimeException());
        }
    }
}
```

The example uses `StatusRuntimeException` because the callback handler does not need to declare a checked exception. If the application layer has methods that throw `StatusException`, the adapter can catch and pass that exception to `onError` as in section 2.

Some principles:

1. **Client-sent errors:** use a status such as `INVALID_ARGUMENT` when the request has an invalid structure or value.
2. **Not found:** use `NOT_FOUND` if the requested resource does not exist.
3. **Business state violation:** use `FAILED_PRECONDITION` or a status appropriate to the contract.
4. **Unexpected server-side errors:** log the internal exception and return a generic description with `INTERNAL`.
5. **Terminate exactly once:** after `onError`, do not call `onNext` or `onCompleted` on the same response observer.

Do not arbitrarily catch `Throwable` to turn even serious JVM errors into normal statuses. Only map error types that the application layer can handle intentionally.

## 5. Client reading StatusRuntimeException and StatusException

On the client, a blocking stub typically reports RPC errors with `StatusRuntimeException`. With an async stub, the `onError(Throwable)` callback receives the error cause; the application should use the gRPC API to extract the status instead of comparing message strings.

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

try {
    Customer customer = blockingStub.findCustomer(request);
    // Process customer.
} catch (StatusRuntimeException error) {
    Status status = Status.fromThrowable(error);
    Metadata trailers = Status.trailersFromThrowable(error);

    switch (status.getCode()) {
        case NOT_FOUND -> showNotFound();
        case INVALID_ARGUMENT -> showInvalidInput();
        case UNAVAILABLE -> scheduleRetry();
        default -> logRpcFailure(status.getCode());
    }

    if (trailers != null) {
        String code = trailers.get(ERROR_CODE);
        if (code != null) {
            logSafeErrorCode(code);
        }
    }
}
```

`Status.fromThrowable(Throwable)` extracts the gRPC status from the exception or cause chain. `Status.trailersFromThrowable(Throwable)` retrieves trailers if the exception carries them. With Java-layer helpers that may throw `StatusException`, client code can also use these same two methods; there is no need to branch by class to understand the error code.

In an async callback:

```java
StreamObserver<Customer> responseObserver = new StreamObserver<>() {
    @Override
    public void onNext(Customer customer) {
        handleCustomer(customer);
    }

    @Override
    public void onError(Throwable error) {
        Status status = Status.fromThrowable(error);
        handleRpcStatus(status.getCode());
    }

    @Override
    public void onCompleted() {
        finishRequest();
    }
};
```

Do not assume every `UNAVAILABLE` or `DEADLINE_EXCEEDED` error is guaranteed safe to retry. For RPCs with side effects, the client needs an idempotency key or status lookup before resending.

## 6. Choosing status codes by meaning, not exception class

`StatusRuntimeException` and `StatusException` do not determine the error code. The code is determined by the `Status` object used to create them.

| Status | Use when | Retry? |
| --- | --- | --- |
| `INVALID_ARGUMENT` | Argument or message is invalid | Usually no; fix the request first |
| `NOT_FOUND` | Resource does not exist | Depends on business logic; usually do not retry immediately |
| `ALREADY_EXISTS` | Resource or key already exists | Check current state |
| `FAILED_PRECONDITION` | Current state does not allow the operation | Preconditions must change first |
| `UNAUTHENTICATED` | Missing or invalid authentication credentials | Refresh credentials per policy |
| `PERMISSION_DENIED` | Caller is authenticated but lacks permission | Do not retry as-is |
| `RESOURCE_EXHAUSTED` | Quota exceeded or resources temporarily exhausted | Throttle/wait per retry policy |
| `UNAVAILABLE` | Service temporarily unavailable | Can retry with backoff if operation is safe |
| `DEADLINE_EXCEEDED` | RPC exceeded time budget | Outcome may be unknown; verify before retrying |
| `INTERNAL` | Unexpected internal error | Investigate; do not expose internal details |

Choose statuses according to the API contract so clients can handle them consistently. Do not use `INTERNAL` for all validation errors, and do not use `INVALID_ARGUMENT` to mask database errors or programming bugs.

## 7. Testing the two exception types

You can test creating and extracting statuses directly without a transport:

```java
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GrpcStatusExceptionTest {

    @Test
    void bothExceptionTypesCarryTheSameGrpcCode() {
        Status status = Status.INVALID_ARGUMENT
                .withDescription("missing customer_id");

        StatusRuntimeException runtimeError =
                status.asRuntimeException();
        StatusException checkedError =
                status.asException();

        assertEquals(Status.Code.INVALID_ARGUMENT,
                Status.fromThrowable(runtimeError).getCode());
        assertEquals(Status.Code.INVALID_ARGUMENT,
                Status.fromThrowable(checkedError).getCode());
    }
}
```

Integration tests should call the service via in-process gRPC or a real transport, then verify the **status code and trailers** received by the client. Do not assert that the client always receives the exact same Java class created by the server: across the RPC boundary, what matters is the status/trailers on the wire, not the server-side exception object identity.

Cases to include:

- Invalid request receives `INVALID_ARGUMENT`.
- Missing resource receives `NOT_FOUND`.
- Business error receives the contracted status.
- Internal error does not leak stack traces or sensitive information.
- Trailers contain the expected error code and no secrets.
- Client handles status with `Status.fromThrowable`, without parsing the description string.

## 8. Selection rules in a Spring gRPC project

| Code boundary | Appropriate choice |
| --- | --- |
| Async gRPC handler calling `responseObserver.onError` | Can create `StatusRuntimeException` directly |
| Business helper wanting to force caller error handling | Can declare `throws StatusException` |
| Adapter receiving checked exceptions from lower layers | Catch and forward via `responseObserver.onError` |
| Client needing to classify RPC errors | Use `Status.fromThrowable` and `Status.trailersFromThrowable` |

There is no need to convert all code from one type to the other just to "standardize gRPC". Choose a convention based on your project's Java boundaries, while keeping **status codes, safe descriptions, and trailers** consistent so clients do not depend on how the server represents exceptions internally.

## 9. Self-practice

1. Write a validation helper declaring `throws StatusException`; convert that error into `responseObserver.onError` in the service adapter.
2. Convert the same helper to return `StatusRuntimeException`. What differences appear in the method signature and where the compiler requires handling?
3. Add an `error-code` trailer for a `FAILED_PRECONDITION` error; write a client that reads the trailer using `Status.trailersFromThrowable`.
4. A database error occurs while finding a customer. Why shouldn't you send the raw exception message or SQL to the client?
5. Write an integration test proving both exception types produce the same gRPC status code when sent across an RPC.

**Remember:** `StatusRuntimeException` is unchecked and `StatusException` is checked; both carry a gRPC `Status` and trailers. Choose the type based on Java boundaries, map business errors to meaningful status codes, send them via `responseObserver.onError`, and have clients read them with `Status.fromThrowable` instead of relying on exception classes or message strings.
