# Reading status codes and status descriptions

**Chapter:** Error handling  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers, generated Java code, and unary or streaming RPCs. This lesson focuses on how to **read and interpret a gRPC status** on the client: the status code for machine-readable logic and the description for explanatory information.

## 1. What information does a gRPC error carry?

When an RPC ends in failure, the client usually receives a `StatusRuntimeException` or `StatusException`. This object carries a `Status`, which has two pieces of information applications commonly care about:

- **Status code:** a standard code, such as `NOT_FOUND`, `INVALID_ARGUMENT`, `UNAVAILABLE`. This is a stable signal for programs to classify errors.
- **Status description:** an optional descriptive string, such as `Customer not found`. The value may be `null`, may change across versions or languages, and should not be used as a control key.

In addition, the error may carry a Java-side cause and metadata trailers. Those two pieces serve distinct purposes; do not confuse them with the status code or description.

```text
RPC failed
    |
    v
StatusRuntimeException / StatusException
    |
    +-- Status code       -> classify by enum
    |
    +-- Description       -> explanatory info, may be null
    |
    +-- Cause             -> Java cause if present
    |
    +-- Trailers          -> end-of-RPC metadata if present
```

**Principle:** use the code to decide behavior; use the description for display or diagnostic support after checking safety.

## 2. Extracting Status from Throwable

The standard API is `Status.fromThrowable(Throwable)`. This method searches for a gRPC status in the exception or its cause chain. If the throwable does not contain a `StatusException` or `StatusRuntimeException`, the result is status `UNKNOWN` attached to that cause; therefore, do not assume every exception contains a status intentionally chosen by the server.

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

try {
    Customer customer = blockingStub.findCustomer(request);
    use(customer);
} catch (StatusRuntimeException error) {
    Status status = Status.fromThrowable(error);

    Status.Code code = status.getCode();
    String description = status.getDescription(); // May be null.

    handle(code, description);
}
```

You can read directly from the exception:

```java
Status status = error.getStatus();
Status.Code code = status.getCode();
String description = status.getDescription();
```

However, `Status.fromThrowable` is more convenient when the calling layer only has a `Throwable`, such as in an async callback or when the error is wrapped inside another exception.

### Handling a possibly null description

`getDescription()` is not guaranteed to always return a string. The server may return only a status code without setting a description. Therefore, avoid calling `description.toLowerCase()`, `description.contains(...)`, or passing a null value directly to the UI without a fallback.

```java
String description = status.getDescription();
String safeDescription =
        (description == null || description.isBlank())
                ? "The request could not be completed"
                : description;
```

The fallback is only for display. Business logic must still rely on `status.getCode()`.

## 3. Status code is a machine-readable contract

gRPC codes are a standard enum. Some common codes:

| Code | General meaning | Typical application reaction |
| --- | --- | --- |
| `INVALID_ARGUMENT` | Invalid parameter/request | Show input error; fix request |
| `NOT_FOUND` | Resource does not exist | Show not-found state |
| `ALREADY_EXISTS` | Resource already exists | Look up or handle conflict |
| `UNAUTHENTICATED` | Missing or invalid credentials | Sign in/refresh credentials per policy |
| `PERMISSION_DENIED` | Authenticated but lacks permission | Stop operation and report access denied |
| `FAILED_PRECONDITION` | Current state does not allow the operation | Change conditions before retrying |
| `ABORTED` | Operation aborted due to conflict | Can retry at transaction/workflow level |
| `RESOURCE_EXHAUSTED` | Quota or resources exhausted | Reduce load, wait, or split work |
| `DEADLINE_EXCEEDED` | RPC exceeded time budget | Verify outcome if operation has side effects |
| `CANCELLED` | RPC was cancelled | Stop work; do not auto-retry |
| `UNAVAILABLE` | Service temporarily unavailable | Can retry with backoff if operation is safe |
| `UNIMPLEMENTED` | Method is not supported | Check client-server version/contract |
| `INTERNAL` | Internal error | Log safely and investigate |
| `DATA_LOSS` | Severe data loss or corruption | Report error and follow recovery procedure |
| `UNKNOWN` | Specific cause could not be determined | Investigate cause/logs; do not infer from description |

Not all of these codes mean "server error". For example, `INVALID_ARGUMENT` usually means an invalid request; `PERMISSION_DENIED` is an authorization decision; `UNAVAILABLE` may be a transient outage.

## 4. Status description is explanatory information, not an error code

The server may create a status as follows:

```java
responseObserver.onError(
        Status.NOT_FOUND
                .withDescription("Customer not found")
                .asRuntimeException());
```

The client receives:

- `getCode() == NOT_FOUND`
- `getDescription() == "Customer not found"` if the description is transmitted intact.

The description helps humans understand the error, but should not be used to drive program flow:

```java
// Avoid: depends on wording that may change.
if ("Customer not found".equals(status.getDescription())) {
    showNotFound();
}

// Prefer: use standard status codes.
if (status.getCode() == Status.Code.NOT_FOUND) {
    showNotFound();
}
```

Another server might use the description `No customer for id`, or send no description at all. Both can still carry the `NOT_FOUND` code. The description can also be localized or changed to avoid disclosing internal information.

### Do not display every description verbatim to users

The description is generated by the server, but it may contain technical details or input data. Applications should map the code to controlled user-facing messages; the description should only be used for logs or approved technical interfaces.

## 5. Classifying errors in a Spring gRPC client

Putting classification logic into a small helper lets blocking and async clients share the same policy:

```java
import io.grpc.Status;

enum RpcFailureAction {
    FIX_REQUEST,
    AUTHENTICATE,
    STOP,
    RETRY_WITH_BACKOFF,
    CHECK_OPERATION_RESULT,
    INVESTIGATE
}

RpcFailureAction classify(Status.Code code) {
    return switch (code) {
        case INVALID_ARGUMENT -> RpcFailureAction.FIX_REQUEST;
        case UNAUTHENTICATED -> RpcFailureAction.AUTHENTICATE;
        case CANCELLED, PERMISSION_DENIED, NOT_FOUND ->
                RpcFailureAction.STOP;
        case UNAVAILABLE, RESOURCE_EXHAUSTED ->
                RpcFailureAction.RETRY_WITH_BACKOFF;
        case DEADLINE_EXCEEDED ->
                RpcFailureAction.CHECK_OPERATION_RESULT;
        default -> RpcFailureAction.INVESTIGATE;
    };
}
```

This is an illustrative policy, not an automatic retry rule for every system. In particular:

- `RESOURCE_EXHAUSTED` should only be retried after shedding load or waiting out the quota window; retrying immediately can worsen the situation.
- `UNAVAILABLE` can be retried with exponential backoff and jitter, but only when the operation is safe or has an idempotency key.
- `DEADLINE_EXCEEDED` does not prove the server did not perform the operation. For write operations, check the state or use idempotency before resending.
- `ABORTED` usually requires retrying a larger workflow/transaction, not just repeating the exact same unchanged request.
- `FAILED_PRECONDITION` requires fixing the state or preconditions first, not blind retries.

### Using in async callbacks

```java
StreamObserver<UploadReceipt> responseObserver = new StreamObserver<>() {
    @Override
    public void onNext(UploadReceipt receipt) {
        showReceipt(receipt);
    }

    @Override
    public void onError(Throwable error) {
        Status status = Status.fromThrowable(error);
        Status.Code code = status.getCode();
        String description = status.getDescription();

        RpcFailureAction action = classify(code);
        reportFailure(action, code, safeForDiagnostics(description));
    }

    @Override
    public void onCompleted() {
        finishUpload();
    }
};
```

With client streaming, the response observer's `onCompleted()` only runs when the response ends normally. If the server returns an error, the client receives `onError()`; do not mark the batch as successful simply because the client called `requestObserver.onCompleted()` to half-close the send side.

## 6. Status trailers are separate metadata

Status code and description are not the entire error information. The server can send **trailers** to provide detailed error codes or a safe correlation token:

```java
Metadata trailers = new Metadata();
Metadata.Key<String> errorCode =
        Metadata.Key.of(
                "error-code",
                Metadata.ASCII_STRING_MARSHALLER);
trailers.put(errorCode, "CUSTOMER_SUSPENDED");

responseObserver.onError(
        Status.FAILED_PRECONDITION
                .withDescription("Customer cannot perform this operation")
                .asRuntimeException(trailers));
```

The client reads trailers with:

```java
Status status = Status.fromThrowable(error);
Metadata trailers = Status.trailersFromThrowable(error);

String applicationCode =
        trailers == null ? null : trailers.get(errorCode);
```

Use the status code for general classification, trailers for structured business codes when needed, and the description for explanation. Do not put tokens, passwords, stack traces, or large payloads into description/trailers.

## 7. Cause and status are not the same

On the server, an internal exception can be the cause that produces a status:

```java
try {
    repository.save(entity);
} catch (DataAccessException databaseError) {
    log.error("Cannot persist customer", databaseError);
    responseObserver.onError(
            Status.INTERNAL
                    .withDescription("Internal server error")
                    .withCause(databaseError)
                    .asRuntimeException());
}
```

`withCause` preserves the cause in the server-side Java exception. **The cause is not a status field sent verbatim over the wire**; the client should not expect to receive the server's stack trace or database exception class. The client should read status/trailers; the server logs the cause internally with a correlation ID.

When `Status.fromThrowable(error)` cannot find a gRPC status in the cause chain, the result is `UNKNOWN` associated with the throwable. Therefore, if the client sees `UNKNOWN`, inspect the cause/logs and adapter boundaries; do not look for a specific description phrase to infer the cause.

## 8. Testing status codes and descriptions

Unit tests verify code and description independently:

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class StatusReadingTest {

    @Test
    void readsCodeAndDescription() {
        StatusRuntimeException error = Status.NOT_FOUND
                .withDescription("Customer not found")
                .asRuntimeException();

        Status status = Status.fromThrowable(error);

        assertEquals(Status.Code.NOT_FOUND, status.getCode());
        assertEquals("Customer not found", status.getDescription());
    }

    @Test
    void descriptionCanBeAbsent() {
        StatusRuntimeException error =
                Status.INVALID_ARGUMENT.asRuntimeException();

        Status status = Status.fromThrowable(error);

        assertEquals(Status.Code.INVALID_ARGUMENT, status.getCode());
        assertNull(status.getDescription());
    }
}
```

Integration tests via in-process gRPC or a real transport should verify:

1. The server returns the right code when the request is invalid or the resource does not exist.
2. The client extracts the right code using `Status.fromThrowable`.
3. The description can be absent; the client does not throw `NullPointerException`.
4. Trailers are extracted separately and are not confused with the description.
5. The client does not rely on description wording to decide retries or display business state.

Do not inspect the exception class on the client to deduce which class the server threw. The RPC boundary transfers status and metadata, not server-side Java objects.

## 9. Checklist when reading RPC errors

- Read `Status.Code` first; this is the basis for error classification.
- Read the description as nullable and use a fallback if missing.
- Do not parse the description or compare it verbatim to control logic.
- Read trailers separately if the contract includes business error codes.
- Keep cause/stack traces in internal logs; do not assume the client receives the server cause.
- Decide retries based on the code, idempotency, remaining deadline, and retry budget.
- For `DEADLINE_EXCEEDED` or `UNAVAILABLE` after a write operation, verify the outcome before resending.

## 10. Self-practice

1. Two servers return different descriptions but the same `NOT_FOUND` code. Why should the client still handle them the same way?
2. `Status.getDescription()` returns `null`. Write a way to produce a default message without affecting error classification.
3. An async callback receives a `CompletionException` wrapping a `StatusRuntimeException`. Which API should be used to get the code without string parsing?
4. The server hits a database error and returns `INTERNAL` with a generic description. Why shouldn't the client receive the stack trace via description?
5. The client receives `DEADLINE_EXCEEDED` after sending an order creation request. What must be checked before retrying?

**Remember:** `status code` is the standard signal for programs to classify errors; `status description` is optional explanatory information and can be null. Use `Status.fromThrowable()` to extract status, handle errors by enum code, read trailers separately, and do not depend on description wording for logic or retries.
